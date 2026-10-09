import json
import os
import subprocess
import time

import pillow_heif
import pytest
from PIL import Image

from pipeline import ff, render_src
from pipeline.convert import convert_project
from pipeline.paths import Project


def _ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def _hdr(path, size="1280x720", seconds=6):
    _ff("-f", "lavfi", "-i", f"testsrc2=size={size}:rate=30:duration={seconds}", "-c:v", "libx265",
        "-pix_fmt", "yuv420p10le", "-x265-params",
        "colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc:log-level=error", "-tag:v", "hvc1", str(path))


@pytest.fixture
def proj(tmp_path):
    src = tmp_path / "영상소스"
    src.mkdir()
    _ff("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=3", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(src / "sdr.mp4"))
    _hdr(src / "hdr.mp4")
    Image.new("RGB", (4000, 3000), (200, 10, 10)).save(src / "p.jpg")
    pillow_heif.from_pillow(Image.new("RGB", (3000, 2000), (10, 200, 10))).save(src / "h.heic")
    p = Project(tmp_path)
    files = {i["src"]: i["file"] for i in convert_project(p)["items"]}
    (p.cache / "cards").mkdir()
    (p.cache / "cards" / "intro.mp4").write_bytes(b"card")
    shots = [{"type": "clip", "src": "cards/intro.mp4", "start": 0, "end": 1},
             {"type": "video", "src": files["sdr.mp4"], "start": 1, "end": 2, "in": 0.5, "out": 1.5, "liveAudio": False},
             {"type": "video", "src": files["hdr.mp4"], "start": 2, "end": 4, "in": 2.5, "out": 4.5, "liveAudio": False},
             {"type": "photo", "src": files["p.jpg"], "start": 4, "end": 5, "kenBurns": "zoom-in"},
             {"type": "collage", "srcs": [files["p.jpg"], files["h.heic"]], "start": 5, "end": 6, "kenBurns": "still"}]
    p.storyboard.write_text(json.dumps({"fps": 30, "music": "music/x.mp3", "formats": {"youtube": {
        "width": 1920, "height": 1080, "musicStart": 0, "musicEnd": 6, "shots": shots, "dropped": 0}}}))
    return p


def _shots(root):
    return json.loads((root / "storyboard.json").read_text())["formats"]["youtube"]["shots"]


def test_sdr_and_jpg_point_at_originals_without_copy(proj):
    root = render_src.build(proj, ["youtube"])
    shots = _shots(root)
    assert shots[1]["src"] == "src/sdr.mp4" and shots[3]["src"] == "src/p.jpg" and shots[0]["src"] == "cards/intro.mp4"
    assert (root / "src").is_symlink() and (root / "cards").is_symlink()
    assert os.path.realpath(root / "src/sdr.mp4") == os.path.realpath(proj.sources / "sdr.mp4")
    walked = {os.path.relpath(d, root) for d, _, _ in os.walk(root)}  # 링크 폴더는 따라 들어가지 않는다
    assert walked <= {".", "hdr", "heic"}  # 실제 파일은 변환본뿐 = 원본 사본 없음


def test_hdr_becomes_tonemapped_segment_of_used_range(proj):
    root = render_src.build(proj, ["youtube"])
    s = _shots(root)[2]
    assert s["src"].startswith("hdr/") and (s["in"], s["out"]) == (1.0, 3.0)  # 구간 시작 = in 2.5 - 여유 1.0
    info = ff.probe(root / s["src"])
    v = next(x for x in info["streams"] if x["codec_type"] == "video")
    assert (v["width"], v["height"], v.get("color_transfer")) == (1280, 720, "bt709")  # 경량 사본(960)이 아닌 원본 해상도
    assert float(info["format"]["duration"]) == pytest.approx(4.0, abs=0.1)  # 1.5~5.5초 (out + 1초 여유)


def test_heic_becomes_full_res_jpg(proj):
    root = render_src.build(proj, ["youtube"])
    a, b = _shots(root)[4]["srcs"]
    assert a == "src/p.jpg" and b.startswith("heic/")
    with Image.open(root / b) as img:
        assert img.size == (3000, 2000) and img.format == "JPEG"  # 사진 사본(2560)이 아닌 원본 해상도


def test_reuses_segments_removes_stale_and_keeps_studio_storyboard(proj):
    before = proj.storyboard.read_text()
    root = render_src.build(proj, ["youtube"])
    seg = root / _shots(root)[2]["src"]
    t0 = seg.stat().st_mtime_ns
    (root / "hdr" / "old.mp4").write_bytes(b"x")
    render_src.build(proj, ["youtube"])
    assert seg.stat().st_mtime_ns == t0  # 다시 변환하지 않음
    assert not (root / "hdr" / "old.mp4").exists()
    assert proj.storyboard.read_text() == before  # Studio용 storyboard는 그대로


def test_replaced_original_reconverts(proj):
    root = render_src.build(proj, ["youtube"])
    old = _shots(root)[2]["src"]
    time.sleep(0.01)
    _hdr(proj.sources / "hdr.mp4", seconds=7)  # 같은 이름으로 교체
    render_src.build(proj, ["youtube"])
    assert _shots(root)[2]["src"] != old and not (root / old).exists()


def test_missing_original_is_korean_error(proj):
    (proj.sources / "sdr.mp4").unlink()
    with pytest.raises(ValueError, match="원본이 없습니다.*sdr.mp4"):
        render_src.build(proj, ["youtube"])


def test_builds_only_requested_formats(proj):
    sb = json.loads(proj.storyboard.read_text())
    sb["formats"]["reels"] = dict(sb["formats"]["youtube"], shots=sb["formats"]["youtube"]["shots"][:2])  # HDR 없음
    proj.storyboard.write_text(json.dumps(sb))
    root = render_src.build(proj, ["reels"])
    assert list(json.loads((root / "storyboard.json").read_text())["formats"]) == ["reels"]
    assert not list((root / "hdr").glob("*.mp4"))  # 유튜브에만 있는 HDR 장면은 변환하지 않음


def test_encode_version_change_reconverts(proj, monkeypatch):
    root = render_src.build(proj, ["youtube"])
    old = _shots(root)[2]["src"]
    monkeypatch.setattr(render_src, "HDR_ENCODE", "next")
    render_src.build(proj, ["youtube"])
    assert _shots(root)[2]["src"] != old


def test_real_dir_at_link_path_is_korean_error(proj):
    (proj.cache / "render" / "src").mkdir(parents=True)
    with pytest.raises(ValueError, match="링크"):
        render_src.build(proj, ["youtube"])


def test_clean_removes_conversions_keeps_links(proj):
    root = render_src.build(proj, ["youtube"])
    render_src.clean(root)
    assert not (root / "hdr").exists() and not (root / "heic").exists()
    assert (root / "src").is_symlink() and (root / "storyboard.json").exists()
