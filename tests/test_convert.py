import os
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageCms
import pytest

from pipeline import ff
from pipeline.convert import _display_size, _video_taken_at, convert_project, is_hdr, out_name
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


def test_video_taken_at_apple_tag_wins():
    info = {
        "format": {
            "tags": {
                "com.apple.quicktime.creationdate": "2026-09-12T10:30:00+0900",
                "creation_time": "2026-09-12T01:30:00.000000Z"
            }
        }
    }
    result = _video_taken_at(info)
    assert result == datetime(2026, 9, 12, 10, 30)


def test_video_taken_at_empty_tags():
    info = {"format": {"tags": {}}}
    assert _video_taken_at(info) is None


def test_display_size_rotation_side_data():
    result = _display_size({"width": 1920, "height": 1080, "side_data_list": [{"rotation": -90}]})
    assert result == (1080, 1920)


def test_display_size_rotation_tags():
    result = _display_size({"width": 1920, "height": 1080, "tags": {"rotate": "90"}})
    assert result == (1080, 1920)


def test_display_size_no_rotation():
    result = _display_size({"width": 1920, "height": 1080})
    assert result == (1920, 1080)


def test_convert_no_part_files_after_broken_source(sample_project):
    proj = Project(sample_project)
    convert_project(proj)
    # Verify that no .part files remain in the media directory
    part_files = list((proj.cache / "media").glob("*.part*"))
    assert len(part_files) == 0


def test_icc_profile_preserved(tmp_path):
    # Create a test image with an ICC profile
    from PIL import ImageFile
    img = Image.new("RGB", (100, 100), color="red")

    # Create a minimal sRGB ICC profile
    profile = ImageCms.createProfile("sRGB")
    icc = ImageCms.ImageCmsProfile(profile).tobytes()

    src = tmp_path / "test.jpg"
    dst = tmp_path / "output.jpg"

    img.save(src, "JPEG", icc_profile=icc)

    # Convert using _convert_image
    from pipeline.convert import _convert_image
    _convert_image(src, dst)

    # Verify the profile is preserved
    with Image.open(dst) as result:
        assert result.info.get("icc_profile") is not None
