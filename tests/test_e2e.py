import json
import subprocess
import sys

import pytest

from pipeline import ff

pytestmark = pytest.mark.slow


def _cli(*args):
    r = subprocess.run([sys.executable, "-m", "pipeline", *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def test_prepare_plan_render(sample_project):
    out = _cli("prepare", str(sample_project))
    assert "후보 12개" in out and "sheet_01.jpg" in out

    sel = {"title": "테스트 여행", "subtitle": "2026.09", "ending": "끝", "formats": ["reels", "youtube"],
           "music": str(sample_project / "song.wav"), "items": [{"id": i} for i in range(12)]}
    (sample_project / "selection.json").write_text(json.dumps(sel, ensure_ascii=False), encoding="utf-8")
    _cli("plan", str(sample_project))
    sb = json.loads((sample_project / ".cache" / "storyboard.json").read_text(encoding="utf-8"))
    assert set(sb["formats"]) == {"reels", "youtube"}

    _cli("render", str(sample_project), "--formats", "reels")
    video = sample_project / "output" / f"{sample_project.name}_reels.mp4"
    info = ff.probe(video)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1080, 1920)
    assert (v["pix_fmt"], v.get("color_transfer")) == ("yuv420p", "bt709")  # 색 태그 없는 풀레인지면 재생기마다 색이 다름
    assert any(s["codec_type"] == "audio" for s in info["streams"])
    cards = list((sample_project / ".cache" / "cards").glob("*.mp4"))
    assert cards and all(not c.name.endswith(".part.mp4") for c in cards)
    assert abs(float(ff.probe(cards[0])["format"]["duration"]) - 3.0) < 0.1
    plan = sb["formats"]["reels"]
    assert abs(float(info["format"]["duration"]) - (plan["musicEnd"] - plan["musicStart"])) < 0.2
