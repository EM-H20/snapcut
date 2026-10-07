import json
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


def _convert_image(src: Path, dst: Path) -> tuple[datetime | None, dict]:
    with Image.open(src) as img:
        taken = _image_taken_at(img)
        out = ImageOps.exif_transpose(img).convert("RGB")
    out.thumbnail((MAX_PHOTO_SIDE, MAX_PHOTO_SIDE))
    out.save(dst, "JPEG", quality=90)
    return taken, {"width": out.width, "height": out.height}


def _convert_video(src: Path, dst: Path) -> tuple[datetime | None, dict]:
    info = ff.probe(src)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if v is None:
        raise RuntimeError("영상 스트림이 없습니다")
    w, h = _display_size(v)
    scale = min(1.0, MAX_VIDEO_SIDE / max(w, h))
    tw, th = round(w * scale / 2) * 2, round(h * scale / 2) * 2
    ff.run("-i", str(src), "-map", "0:v:0", "-map", "0:a:0?",
           "-vf", f"fps={FPS},scale={tw}:{th}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(dst))
    out = ff.probe(dst)
    return _video_taken_at(info), {
        "width": tw, "height": th,
        "duration": round(float(out["format"]["duration"]), 3),
        "has_audio": any(s["codec_type"] == "audio" for s in out["streams"]),
        "hdr": is_hdr(v),
    }


def convert_project(proj: Project) -> dict:
    proj.media.mkdir(parents=True, exist_ok=True)
    manifest_path = proj.cache / "manifest.json"
    old = {}
    if manifest_path.exists():
        old = {i["src"]: i for i in json.loads(manifest_path.read_text())["items"]}
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
        prev = old.get(rel)
        if prev and dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
            items.append(prev)
            continue
        try:
            taken, meta = (_convert_image if ext in IMAGE_EXT else _convert_video)(src, dst)
        except Exception as e:  # 파일 하나가 깨져도 나머지는 계속
            skipped.append({"src": rel, "reason": str(e)[:200]})
            continue
        source = "mtime" if taken is None else ("exif" if ext in IMAGE_EXT else "metadata")
        taken = taken or datetime.fromtimestamp(src.stat().st_mtime)
        items.append({
            "src": rel, "file": f"media/{dst.name}",
            "type": "photo" if ext in IMAGE_EXT else "video",
            "taken_at": taken.isoformat(timespec="seconds"), "time_source": source, **meta,
        })
    result = {"items": items, "skipped": skipped}
    manifest_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result
