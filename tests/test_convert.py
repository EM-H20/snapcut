import json
import os
import subprocess
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageCms
import pytest

from pipeline import ff
from pipeline.convert import (VIDEO_ENCODE, _display_size, _rotation, _transpose, _video_taken_at, convert_project,
                              is_hdr, out_name)
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
    assert (v["width"], v["height"], v["has_audio"], v["hdr"]) == (540, 960, False, False)  # 720x1280 → 긴 변 960
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


def _tiny_project(tmp_path, n=3) -> Project:
    src = tmp_path / "영상소스"
    src.mkdir()
    for i in range(n):
        Image.new("RGB", (64, 48), (i * 60, 10, 10)).save(src / f"a{i}.jpg")
    return Project(tmp_path)


def test_convert_resumes_from_partial_manifest(tmp_path):
    proj = _tiny_project(tmp_path)
    convert_project(proj)
    manifest = proj.cache / "manifest.json"
    data = json.loads(manifest.read_text())
    mtimes = {i["src"]: (proj.cache / i["file"]).stat().st_mtime_ns for i in data["items"]}
    data["items"] = data["items"][:1]  # 중단된 실행 흉내
    manifest.write_text(json.dumps(data))
    convert_project(proj)
    for i, src in enumerate(sorted(mtimes)):
        now = (proj.media / out_name(Path(src))).stat().st_mtime_ns
        assert (now == mtimes[src]) == (i == 0)
    assert len(json.loads(manifest.read_text())["items"]) == 3


def test_convert_survives_corrupt_manifest(tmp_path):
    proj = _tiny_project(tmp_path)
    proj.cache.mkdir()
    (proj.cache / "manifest.json").write_text("{not json")
    assert len(convert_project(proj)["items"]) == 3


def test_convert_reconverts_when_source_replaced_with_older_mtime(tmp_path):
    proj = _tiny_project(tmp_path, 1)
    convert_project(proj)
    out = proj.cache / "media" / "a0_jpg.jpg"
    first = out.read_bytes()
    src = proj.sources / "a0.jpg"
    old = src.stat().st_mtime_ns - 10**12
    Image.new("RGB", (64, 48), (200, 200, 0)).save(src)
    os.utime(src, ns=(old, old))
    convert_project(proj)
    assert out.read_bytes() != first


def _keyframes(path) -> list[float]:
    import subprocess
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
                        "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return [float(x.strip(",")) for x in r.stdout.split()]


def _tiny_video_project(tmp_path) -> Project:
    from tests.conftest import _ffmpeg
    src = tmp_path / "영상소스"
    src.mkdir()
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=4",
            "-c:v", "libx264", "-g", "300", "-pix_fmt", "yuv420p", str(src / "v.mp4"))  # 원본은 키프레임 1개
    return Project(tmp_path)


def test_converted_video_has_a_keyframe_every_second(tmp_path):
    # 키프레임이 드물면 장면 시작점(구간 중간)으로의 탐색이 느려 미리보기 전환마다 멈칫한다
    proj = _tiny_video_project(tmp_path)
    convert_project(proj)
    keys = _keyframes(proj.media / "v_mp4.mp4")
    assert keys[0] == 0.0 and max(b - a for a, b in zip(keys, keys[1:])) <= 1.0 + 1e-6


def test_video_converted_with_old_encoding_is_redone(tmp_path):
    proj = _tiny_video_project(tmp_path)
    convert_project(proj)
    manifest = proj.cache / "manifest.json"
    data = json.loads(manifest.read_text())
    data["items"][0].pop("encode", None)  # 예전 인코딩으로 만든 항목 흉내
    manifest.write_text(json.dumps(data))
    out = proj.media / "v_mp4.mp4"
    before = out.stat().st_mtime_ns
    convert_project(proj)
    assert out.stat().st_mtime_ns != before
    assert json.loads(manifest.read_text())["items"][0]["encode"]


def _hdr_clip(path, size="640x360", pix_fmt="yuv420p10le", seconds=1):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration={seconds}",
                    "-c:v", "libx265", "-pix_fmt", pix_fmt,
                    "-x265-params", "colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc:log-level=error",
                    "-tag:v", "hvc1", str(path)], check=True)


def _vstream(path):
    return next(s for s in ff.probe(path)["streams"] if s["codec_type"] == "video")


def test_rotation_sign():
    assert _rotation({"side_data_list": [{"rotation": 90}]}) == 90
    assert _rotation({"side_data_list": [{"rotation": -90}]}) == -90
    assert _rotation({"tags": {"rotate": "90"}}) == -90  # 구버전 rotate 태그는 시계 방향 = display matrix -90
    assert _rotation({}) == 0


def test_transpose_matches_ffmpeg_autorotate():
    assert _transpose(90) == ["transpose=2"]
    assert _transpose(-90) == ["transpose=1"]
    assert _transpose(180) == ["hflip", "vflip"]
    assert _transpose(0) == []


def test_video_proxy_is_small(tmp_path):
    (tmp_path / "영상소스").mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(tmp_path / "영상소스" / "v.mp4")], check=True)
    item = convert_project(Project(tmp_path))["items"][0]
    assert (item["width"], item["height"], item["encode"]) == (960, 540, VIDEO_ENCODE)


def test_hdr_proxy_is_tagged_sdr_and_keeps_rotation(tmp_path):
    (tmp_path / "영상소스").mkdir()
    _hdr_clip(tmp_path / "hdr.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-display_rotation", "90", "-i", str(tmp_path / "hdr.mp4"),
                    "-c", "copy", str(tmp_path / "영상소스" / "rot.mp4")], check=True)
    item = convert_project(Project(tmp_path))["items"][0]
    assert item["hdr"] is True and (item["width"], item["height"]) == (360, 640)
    s = _vstream(tmp_path / ".cache" / item["file"])
    assert (s["width"], s["height"], s["pix_fmt"]) == (360, 640, "yuv420p")
    assert (s.get("color_transfer"), s.get("color_primaries")) == ("bt709", "bt709")
    assert not any("rotation" in d for d in s.get("side_data_list", []))  # 회전은 픽셀에 반영, 이중 회전 없음


def test_hdr_8bit_hlg_converts(tmp_path):
    (tmp_path / "영상소스").mkdir()
    _hdr_clip(tmp_path / "영상소스" / "kakao.mp4", pix_fmt="yuv420p")  # 카톡 전송본처럼 8비트 HLG
    m = convert_project(Project(tmp_path))
    assert m["skipped"] == []
    assert _vstream(tmp_path / ".cache" / m["items"][0]["file"]).get("color_transfer") == "bt709"


def test_encode_bump_reconverts_videos_only(sample_project):
    proj = Project(sample_project)
    convert_project(proj)
    manifest = proj.cache / "manifest.json"
    data = json.loads(manifest.read_text())
    for i in data["items"]:
        if i["type"] == "video":
            i["encode"] = "gop1s"  # 이전 인코딩 버전
    manifest.write_text(json.dumps(data))
    photo, video = proj.cache / "media" / "IMG_0000_jpg.jpg", proj.cache / "media" / "IMG_0201_mp4.mp4"
    p0, v0 = photo.stat().st_mtime_ns, video.stat().st_mtime_ns
    m = convert_project(proj)
    assert photo.stat().st_mtime_ns == p0 and video.stat().st_mtime_ns != v0
    assert {i["encode"] for i in m["items"] if i["type"] == "video"} == {VIDEO_ENCODE}


def test_hdr_grade_applies_to_hdr_only():
    from pipeline.convert import HDR_GRADE, video_input
    hdr = {"color_transfer": "arib-std-b67", "pix_fmt": "yuv420p", "width": 1920, "height": 1080}
    assert HDR_GRADE in video_input(Path("a.mp4"), hdr, 1920, 1080)[1]  # SDR로 누르면 탁해 보여 대비·채도를 살짝 올린다
    assert HDR_GRADE not in video_input(Path("a.mp4"), {"width": 1920, "height": 1080}, 1920, 1080)[1]
