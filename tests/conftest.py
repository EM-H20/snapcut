import subprocess
import wave
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pillow_heif
import pytest
from PIL import Image, ImageFilter


def _noise_image(seed: int, size: tuple[int, int]) -> Image.Image:
    rng = np.random.default_rng(seed)
    small = rng.integers(0, 256, (size[1] // 16, size[0] // 16, 3), dtype=np.uint8)
    return Image.fromarray(small).resize(size, Image.NEAREST)  # 블록 경계 = 선명한 에지


def _save_jpg(img: Image.Image, path: Path, taken: datetime | None) -> None:
    exif = Image.Exif()
    if taken:
        exif[306] = taken.strftime("%Y:%m:%d %H:%M:%S")  # DateTime
    img.save(path, "JPEG", quality=92, exif=exif)


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def make_click_track(path: Path, bpm: float = 120.0, seconds: float = 30.0, sr: int = 22050) -> None:
    t = np.arange(int(seconds * sr)) / sr
    y = np.zeros_like(t)
    beat = 60.0 / bpm
    n = int(0.05 * sr)
    for i in range(int(seconds / beat)):
        s = int(i * beat * sr)
        amp = 1.0 if i % 4 == 0 else 0.4
        seg = y[s:s + n]
        seg += amp * np.sin(2 * np.pi * 880 * t[:len(seg)]) * np.exp(-t[:len(seg)] * 60)
    pcm = (np.clip(y, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


@pytest.fixture(scope="session")
def sample_project(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("proj")
    src = root / "영상소스"
    src.mkdir()
    base = datetime(2026, 9, 12, 10, 0, 0)
    for i in range(8):
        size = (1600, 1200) if i % 2 == 0 else (1200, 1600)
        _save_jpg(_noise_image(i, size), src / f"IMG_{i:04d}.jpg", base + timedelta(minutes=10 * i))
    dup = _noise_image(0, (1600, 1200))
    dup.putpixel((5, 5), (0, 0, 0))
    _save_jpg(dup, src / "IMG_0000b.jpg", base + timedelta(seconds=1))  # 연사 중복
    blurred = _noise_image(2, (1600, 1200)).filter(ImageFilter.GaussianBlur(12))
    _save_jpg(blurred, src / "IMG_blur.jpg", base + timedelta(minutes=21))  # 흔들림
    pillow_heif.from_pillow(_noise_image(20, (1200, 900))).save(src / "IMG_0100.heic")  # EXIF 없음
    _noise_image(21, (900, 900)).save(src / "제주 사진.png")  # 한글·공백, EXIF 없음
    (src / "IMG_0000.aae").write_text("<plist/>")  # 아이폰 사이드카 — 조용히 무시
    (src / "broken.jpg").write_bytes(b"not an image")  # 제외 목록에 떠야 함
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=3",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3", "-shortest",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-metadata", "creation_time=2026-09-12T01:30:00.000000Z", str(src / "IMG_0200.mov"))
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=720x1280:rate=60:duration=3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src / "IMG_0201.mp4"))  # 세로, 60fps, 무음
    make_click_track(root / "song.wav")
    return root
