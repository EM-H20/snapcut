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
MAX_VIDEO_SIDE = 1920
FPS = 30
# 영상 인코딩 버전. 바꾸면 다음 convert에서 영상만 다시 변환한다 (사진은 그대로).
# gop1s: 1초마다 키프레임 — 장면 시작점(구간 중간)으로의 탐색이 빨라 미리보기 전환이 멈칫하지 않는다
VIDEO_ENCODE = "gop1s"
HDR_TRANSFERS = {"arib-std-b67", "smpte2084"}


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


def _display_size(stream: dict) -> tuple[int, int]:
    w, h = int(stream["width"]), int(stream["height"])
    rot = int(stream.get("tags", {}).get("rotate", 0) or 0)
    for sd in stream.get("side_data_list", []):
        rot = int(sd.get("rotation", rot))
    return (h, w) if abs(rot) % 180 == 90 else (w, h)


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
        ff.run("-i", str(src), "-map", "0:v:0", "-map", "0:a:0?",
               "-vf", f"fps={FPS},scale={tw}:{th}",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-g", str(FPS),
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
