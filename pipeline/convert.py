import json
import os
import unicodedata
from datetime import datetime
from pathlib import Path

import pillow_heif
from PIL import Image, ImageOps

from . import ff
from .paths import Project

pillow_heif.register_heif_opener()

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
IGNORED_EXT = {".aae"}  # 아이폰 편집 정보 사이드카
MAX_PHOTO_SIDE = 2560
MAX_VIDEO_SIDE = 960  # 영상 사본은 분석·Studio 미리보기용 — 렌더는 원본을 쓴다 (render_src.py)
FPS = 30
# 영상 인코딩 버전. 바꾸면 다음 convert에서 영상만 다시 변환한다 (사진은 그대로).
# proxy960: 긴 변 960 경량 사본, HDR은 VideoToolbox로 bt709 SDR 톤매핑 + 색 태그,
# 1초마다 키프레임 — 장면 시작점(구간 중간)으로의 탐색이 빨라 미리보기 전환이 멈칫하지 않는다
VIDEO_ENCODE = "proxy960-grade1"
VIDEO_CRF = "26"
HDR_TRANSFERS = {"arib-std-b67", "smpte2084"}
# HDR을 SDR로 누르면 밝은 부분의 폭이 줄어 탁해 보인다 → 대비·채도를 살짝 올린다 (2026-10-09 사용자가 비교 후 선택)
HDR_GRADE = "eq=contrast=1.08:saturation=1.12"


def out_name(rel: Path) -> str:
    ext = rel.suffix.lower()
    target = "jpg" if ext in IMAGE_EXT else "mp4"
    stem = "__".join(rel.with_suffix("").parts)
    return unicodedata.normalize("NFC", f"{stem}_{ext.lstrip('.')}.{target}")


def is_hdr(stream: dict) -> bool:
    return stream.get("color_transfer") in HDR_TRANSFERS


def _exif_time(raw) -> datetime | None:
    try:
        return datetime.strptime(str(raw).strip("\x00 "), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def _image_taken_at(img: Image.Image) -> datetime | None:
    exif = img.getexif()
    raw = exif.get_ifd(0x8769).get(36867) or exif.get(306)  # DateTimeOriginal → DateTime
    return _exif_time(raw) if raw else None


def _video_taken_at(info: dict) -> datetime | None:
    tags = info.get("format", {}).get("tags", {})
    apple = tags.get("com.apple.quicktime.creationdate")
    if apple:  # 촬영지 현지 시각 + 오프셋 — 사진 EXIF와 같은 벽시계 기준
        try:
            return datetime.fromisoformat(apple).replace(tzinfo=None)
        except ValueError:
            pass
    utc = tags.get("creation_time")
    if utc:
        # ponytail: UTC→이 Mac의 시간대. 해외 촬영분은 시차만큼 어긋날 수 있음 — 필요하면 GPS로 시간대 추정
        try:
            return datetime.fromisoformat(utc.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
        except ValueError:
            pass
    return None


def _rotation(stream: dict) -> int:
    """display matrix 기준 회전(도). 구버전 rotate 태그는 시계 방향이라 부호가 반대다."""
    for sd in stream.get("side_data_list", []):
        if "rotation" in sd:
            return int(sd["rotation"])
    return -int(stream.get("tags", {}).get("rotate", 0) or 0)


def _display_size(stream: dict) -> tuple[int, int]:
    w, h = int(stream["width"]), int(stream["height"])
    return (h, w) if abs(_rotation(stream)) % 180 == 90 else (w, h)


def _transpose(rot: int) -> list[str]:
    """ffmpeg 자동 회전과 같은 방향의 필터 (VideoToolbox 경로는 자동 회전이 안 된다)."""
    return {90: ["transpose=2"], 270: ["transpose=1"], 180: ["hflip", "vflip"]}.get(rot % 360, [])


def video_input(src: Path, stream: dict, tw: int, th: int) -> tuple[list[str], str]:
    """원본을 화면 방향 tw×th의 SDR bt709 yuv420p 프레임으로 읽는 ffmpeg 입력 인자와 필터 앞부분.
    HDR은 VideoToolbox(scale_vt)로 톤매핑한다 — macOS가 사진 앱·파이널컷에서 보여 주는 색과 같다."""
    if not is_hdr(stream):
        return ["-i", str(src)], f"scale={tw}:{th}"
    rot = _rotation(stream)
    sw, sh = (th, tw) if abs(rot) % 180 == 90 else (tw, th)  # scale_vt는 회전 전 크기로
    download = "p010le" if "10" in stream.get("pix_fmt", "") else "nv12"
    chain = [f"scale_vt=w={sw}:h={sh}:color_matrix=bt709:color_primaries=bt709:color_transfer=bt709",
             "hwdownload", f"format={download}", "format=yuv420p", HDR_GRADE, *_transpose(rot)]
    return (["-noautorotate", "-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld", "-i", str(src)],
            ",".join(chain))


def _part_path(dst: Path) -> Path:
    return dst.with_name(f"{dst.stem}.{os.getpid()}.part{dst.suffix}")


def _write_manifest(path: Path, data: dict) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.part")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    os.replace(tmp, path)


def _load_old(path: Path) -> dict:
    try:
        return {i["src"]: i for i in json.loads(path.read_text())["items"]}
    except (OSError, ValueError, KeyError, TypeError):  # 없거나 깨진 manifest = 빈 것으로 취급
        return {}


def source_map(proj: Project) -> dict[str, Path]:
    """media/ 사본 → 영상소스 원본 (manifest 기준)."""
    items = json.loads((proj.cache / "manifest.json").read_text(encoding="utf-8"))["items"]
    return {i["file"]: proj.sources / i["src"] for i in items}


def _convert_image(src: Path, dst: Path) -> tuple[datetime | None, dict]:
    tmp = _part_path(dst)
    try:
        with Image.open(src) as img:
            taken = _image_taken_at(img)
            icc_profile = img.info.get("icc_profile")
            out = ImageOps.exif_transpose(img).convert("RGB")
        out.thumbnail((MAX_PHOTO_SIDE, MAX_PHOTO_SIDE))
        save_kwargs = {"quality": 90}
        if icc_profile:
            save_kwargs["icc_profile"] = icc_profile
        out.save(tmp, "JPEG", **save_kwargs)
        os.replace(tmp, dst)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return taken, {"width": out.width, "height": out.height}


def _convert_video(src: Path, dst: Path) -> tuple[datetime | None, dict]:
    tmp = _part_path(dst)
    try:
        info = ff.probe(src)
        v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
        if v is None:
            raise RuntimeError("영상 스트림이 없습니다")
        w, h = _display_size(v)
        scale = min(1.0, MAX_VIDEO_SIDE / max(w, h))
        tw, th = round(w * scale / 2) * 2, round(h * scale / 2) * 2
        inp, vf = video_input(src, v, tw, th)
        tags = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"] if is_hdr(v) else []
        ff.run(*inp, "-map", "0:v:0", "-map", "0:a:0?",
               "-vf", f"{vf},fps={FPS}",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", VIDEO_CRF, "-pix_fmt", "yuv420p", "-g", str(FPS), *tags,
               "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(tmp))
        out = ff.probe(tmp)
        os.replace(tmp, dst)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return _video_taken_at(info), {
        "width": tw, "height": th,
        "duration": round(float(out["format"]["duration"]), 3),
        "has_audio": any(s["codec_type"] == "audio" for s in out["streams"]),
        "hdr": is_hdr(v),
        "encode": VIDEO_ENCODE,
    }


def convert_project(proj: Project) -> dict:
    proj.media.mkdir(parents=True, exist_ok=True)
    manifest_path = proj.cache / "manifest.json"
    old = _load_old(manifest_path)
    pending = dict(old)  # 중간 저장용: 아직 처리 못 한 옛 항목도 함께 남긴다
    items, skipped = [], []
    files = sorted(p for p in proj.sources.rglob("*") if p.is_file() and not p.name.startswith("."))
    for src in files:
        rel_path = src.relative_to(proj.sources)
        rel = unicodedata.normalize("NFC", str(rel_path))
        ext = src.suffix.lower()
        if ext in IGNORED_EXT:
            continue
        if ext not in IMAGE_EXT | VIDEO_EXT:
            skipped.append({"src": rel, "reason": "지원하지 않는 형식"})
            continue
        dst = proj.media / out_name(rel_path)
        st = src.stat()
        prev = old.get(rel)
        if prev and dst.exists() and (prev.get("src_size"), prev.get("src_mtime")) == (st.st_size, st.st_mtime_ns) \
                and (ext in IMAGE_EXT or prev.get("encode") == VIDEO_ENCODE):
            items.append(prev)
            pending[rel] = prev
            continue
        try:
            taken, meta = (_convert_image if ext in IMAGE_EXT else _convert_video)(src, dst)
        except Exception as e:  # 파일 하나가 깨져도 나머지는 계속
            skipped.append({"src": rel, "reason": str(e)[:200]})
            continue
        source = "mtime" if taken is None else ("exif" if ext in IMAGE_EXT else "metadata")
        taken = taken or datetime.fromtimestamp(st.st_mtime)
        item = {
            "src": rel, "file": f"media/{dst.name}",
            "type": "photo" if ext in IMAGE_EXT else "video",
            "taken_at": taken.isoformat(timespec="seconds"), "time_source": source, **meta,
            "src_size": st.st_size, "src_mtime": st.st_mtime_ns,
        }
        items.append(item)
        pending[rel] = item
        _write_manifest(manifest_path, {"items": list(pending.values()), "skipped": skipped})  # 중단돼도 진행분 보존
    result = {"items": items, "skipped": skipped}
    _write_manifest(manifest_path, result)
    return result
