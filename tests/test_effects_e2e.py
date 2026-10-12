"""효과 10개를 한 영상에 넣어 실제 HF 렌더 → 점검 통과 (검정·멈춤·음량·길이)."""
import json
import subprocess
import sys

import pytest

from pipeline import check
from tests.conftest import make_click_track

pytestmark = pytest.mark.slow


def _cli(*args):
    r = subprocess.run([sys.executable, "-m", "pipeline", *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def test_all_effects_render_and_pass_check(sample_project):
    _cli("prepare", str(sample_project))
    cands = json.loads((sample_project / ".cache" / "candidates.json").read_text(encoding="utf-8"))["candidates"]
    vids = [i for i, c in enumerate(cands) if c["type"] == "video"]
    photos = [i for i, c in enumerate(cands) if c["type"] == "photo"]
    v_audio = next(i for i in vids if cands[i].get("has_audio"))
    items = [{"id": photos[0], "whip": 0.4}, {"id": vids[0], "in": 0.0, "out": 1.0, "speed": 0.5, "freeze": 0.6},
             {"id": photos[1], "wipe": 0.6, "shake": 0.6}, {"id": v_audio, "in": 1.0, "out": 2.5, "liveAudio": True, "jcut": 0.5, "lcut": 0.4},
             {"id": photos[2], "dutch": 8}, {"id": vids[-1], "in": 0.0, "out": 2.0, "speed": [1.0, 0.4], "blur": 0.6},
             {"id": photos[3]}, {"id": vids[0], "in": 0.0, "out": 2.5, "speed": 4}]
    song = sample_project / "long.wav"  # 기본 30초 곡은 인트로·아웃트로를 빼면 11초뿐이라 효과 장면이 빠진다
    make_click_track(song, seconds=60.0)
    sel = {"title": "효과", "ending": "끝", "formats": ["youtube"], "music": str(song), "items": items}
    (sample_project / "selection.json").write_text(json.dumps(sel, ensure_ascii=False), encoding="utf-8")
    _cli("plan", str(sample_project))
    sb = json.loads((sample_project / ".cache" / "storyboard.json").read_text(encoding="utf-8"))
    keys = {k for s in sb["formats"]["youtube"]["shots"] for k in s}
    assert {"whip", "wipe", "shake", "dutch", "speed", "freeze", "jcut", "lcut", "blur"} <= keys
    _cli("render", str(sample_project), "--formats", "youtube")
    out = sample_project / "output" / f"{sample_project.name}_youtube.mp4"
    r = check.check_file(out, check.plan_view(sb, "youtube"), sample_project / "output" / "check" / "fx")
    # 클릭음 곡은 피크가 커서 피크 한도(-1 dBTP) 안에서 -14 LUFS까지 못 올린다 — 음량은 실제 곡 렌더(인왕산)에서 본다
    assert not [x for x in r["issues"] if x["kind"] != "loudness"], r["issues"]
    js = next(s for s in sb["formats"]["youtube"]["shots"] if s.get("jcut"))
    tone = lambda t: _tone(out, t)  # 현장 소리(440Hz 사인)는 J컷만큼 먼저 들리고 L컷만큼 이어진다
    assert tone(js["start"] - js["jcut"] - 0.5) < -35 < tone(js["start"] - js["jcut"] + 0.1)
    assert tone(js["end"] + js["lcut"] - 0.35) > -35 > tone(js["end"] + js["lcut"] + 0.3)


def _tone(path, t):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-ss", f"{t:.3f}", "-t", "0.25", "-i", str(path),
                        "-af", "bandpass=f=440:width_type=h:w=40,volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    return float(r.stderr.split("mean_volume: ")[1].split(" dB")[0])
