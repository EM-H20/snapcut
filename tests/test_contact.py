import os
import subprocess
import time
from pathlib import Path

from PIL import Image

from pipeline.contact import make_sheets
from pipeline.convert import convert_project
from pipeline.curate import curate
from pipeline.paths import Project


def test_sheets_paginate_by_20(sample_project):
    proj = Project(sample_project)
    convert_project(proj)
    cands = curate(proj)["candidates"]
    assert len(make_sheets(proj, cands)) == 1
    sheets = make_sheets(proj, cands * 2)  # 24개 → 2장, 이전 시트는 지움
    assert [p.name for p in sheets] == ["sheet_01.jpg", "sheet_02.jpg"]
    assert sorted(p.name for p in (proj.cache / "sheets").glob("sheet_*.jpg")) == ["sheet_01.jpg", "sheet_02.jpg"]
    with Image.open(sheets[0]) as img:
        assert img.size == (1600, 1280)


def test_thumbnail_freshness(sample_project):
    """After make_sheets, set thumbnail mtime older than video; re-run should regenerate."""
    proj = Project(sample_project)
    convert_project(proj)
    cands = curate(proj)["candidates"]
    # Get a video candidate
    video_cands = [c for c in cands if c["type"] == "video"]
    assert len(video_cands) > 0, "sample_project must have videos"

    # First run: generate thumbnail
    make_sheets(proj, video_cands)
    thumb_path = proj.cache / "thumbs" / (Path(video_cands[0]["file"]).stem + ".jpg")
    assert thumb_path.exists()

    video_path = proj.cache / video_cands[0]["file"]
    thumb_mtime_before = thumb_path.stat().st_mtime

    # Age the thumbnail to trigger regeneration
    os.utime(thumb_path, (0, 0))
    thumb_mtime_aged = thumb_path.stat().st_mtime
    assert thumb_mtime_aged < video_path.stat().st_mtime

    # Second run should regenerate
    time.sleep(0.01)  # Ensure mtime will differ
    make_sheets(proj, video_cands)
    thumb_mtime_after = thumb_path.stat().st_mtime
    assert thumb_mtime_after > thumb_mtime_aged, "Thumbnail should be regenerated when stale"


def test_thumbnail_seek_fallback(tmp_path):
    """Video with stream shorter than container duration should fall back to frame 0."""
    # Create project structure
    proj_root = tmp_path / "proj"
    proj_root.mkdir()
    media_dir = proj_root / ".cache" / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    # Create a video: 1s video stream, 4s audio (container duration = 4s)
    video_file = media_dir / "v.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=1",
        "-f", "lavfi", "-i", "sine=duration=4",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(video_file)
    ], check=True)

    proj = Project(proj_root)
    # Candidate with container duration (4.0s), but video stream is only 1s
    cand = {"type": "video", "file": "media/v.mp4", "duration": 4.0}

    # Should not raise; should fall back to frame 0
    sheets = make_sheets(proj, [cand])
    assert len(sheets) == 1
    assert sheets[0].exists()
