import os
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from pipeline import ff
from pipeline.convert import convert_project, is_hdr, out_name
from pipeline.paths import Project


def test_out_name_keeps_extension_and_subfolder():
    assert out_name(Path("IMG_1.HEIC")) == "IMG_1_heic.jpg"
    assert out_name(Path("IMG_1.MOV")) == "IMG_1_mov.mp4"
    assert out_name(Path("day1/IMG_1.jpg")) == "day1__IMG_1_jpg.jpg"


def test_out_name_is_nfc():
    nfd = unicodedata.normalize("NFD", "제주 사진.png")
    assert out_name(Path(nfd)) == unicodedata.normalize("NFC", "제주 사진_png.jpg")


def test_is_hdr():
    assert is_hdr({"color_transfer": "arib-std-b67"})
    assert is_hdr({"color_transfer": "smpte2084"})
    assert not is_hdr({"color_transfer": "bt709"})
    assert not is_hdr({})


def test_convert_project(sample_project):
    src_before = sorted(os.listdir(sample_project / "영상소스"))
    m = convert_project(Project(sample_project))
    items = {i["src"]: i for i in m["items"]}

    assert len([i for i in m["items"] if i["type"] == "photo"]) == 12
    assert len([i for i in m["items"] if i["type"] == "video"]) == 2
    assert [s["src"] for s in m["skipped"]] == ["broken.jpg"]
    assert "IMG_0000.aae" not in items
    assert sorted(os.listdir(sample_project / "영상소스")) == src_before  # 원본 무변경

    portrait = items["IMG_0001.jpg"]
    assert (portrait["width"], portrait["height"]) == (1200, 1600)
    assert portrait["time_source"] == "exif" and portrait["taken_at"] == "2026-09-12T10:10:00"
    with Image.open(sample_project / ".cache" / items["IMG_0100.heic"]["file"]) as img:
        assert img.format == "JPEG"
    assert items["IMG_0100.heic"]["time_source"] == "mtime"
    assert items[unicodedata.normalize("NFC", "제주 사진.png")]["file"].endswith("_png.jpg")

    v = items["IMG_0201.mp4"]
    assert (v["width"], v["height"], v["has_audio"], v["hdr"]) == (720, 1280, False, False)
    stream = next(s for s in ff.probe(sample_project / ".cache" / v["file"])["streams"] if s["codec_type"] == "video")
    assert stream["r_frame_rate"] == "30/1"

    mov = items["IMG_0200.mov"]
    expected = datetime(2026, 9, 12, 1, 30, tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    assert mov["taken_at"] == expected.isoformat(timespec="seconds")
    assert mov["time_source"] == "metadata" and mov["has_audio"] is True


def test_convert_skips_already_converted(sample_project):
    proj = Project(sample_project)
    convert_project(proj)
    out = proj.cache / "media" / "IMG_0000_jpg.jpg"
    before = out.stat().st_mtime_ns
    convert_project(proj)
    assert out.stat().st_mtime_ns == before
