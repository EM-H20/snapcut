"""edit E2E: 한국어 TTS 말소리 영상 → 무음 컷 → 말더듬 컷 → HF 0.7.109 렌더 → 점검. whisper 모델·say·student-kit이 있을 때만."""
import json
import shutil
import subprocess
import sys

import pytest

from pipeline import edit, ff, transcribe

pytestmark = [pytest.mark.slow, pytest.mark.skipif(
    not (shutil.which("whisper-cli") and shutil.which("say") and (transcribe.MODELS_DIR / "ggml-large-v3.bin").exists()
         and edit.CUT_SILENCES.exists()),
    reason="whisper-cli·say·공용/모델/ggml-large-v3.bin·student-kit 필요")]


def _cli(*args):
    r = subprocess.run([sys.executable, "-m", "pipeline", *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def test_edit_korean_talk_to_checked_render(tmp_path):
    src = tmp_path / "영상소스"
    src.mkdir()
    speech = tmp_path / "speech.aiff"
    subprocess.run(["say", "-v", "Yuna", "-o", str(speech),
                    "안녕하세요. 오늘은 오늘은 산에 갑니다. [[slnc 2000]] 날씨가 정말 좋네요."], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30", "-i", str(speech),
                    "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "48000",
                    str(src / "talk.mp4")], check=True)
    before = float(ff.probe(src / "talk.mp4")["format"]["duration"])

    out = _cli("edit", str(tmp_path))
    assert "실수 후보" in out
    a = tmp_path / "work" / "edit" / "assets"
    silenced = float(ff.probe(a / "silenced.mp4")["format"]["duration"])
    assert silenced < before - 1.0  # 2초 쉼이 줄었다
    cands = json.loads((a / "candidates.json").read_text(encoding="utf-8"))["candidates"]
    assert any(c["type"] == "stutter" and "오늘은" in c["removes"] for c in cands)

    cuts = [{**c["cut"], "reason": c["type"]} for c in cands if c["recommend"] == "cut"]
    (a / "approved-cuts.json").write_text(json.dumps({"cuts": cuts}, ensure_ascii=False), encoding="utf-8")
    _cli("edit", str(tmp_path), "--cuts")
    words = [w["text"] for w in json.loads((a / "transcript.json").read_text(encoding="utf-8"))["words"]]
    assert sum("오늘은" in w for w in words) == 1

    lint = subprocess.run(["npx", "-y", edit.HF, "lint", str(tmp_path / "work" / "edit"), "--json"], capture_output=True, text=True)
    assert '"errorCount":0' in lint.stdout.replace(" ", ""), lint.stdout[-1500:]
    _cli("render", str(tmp_path))
    video = tmp_path / "output" / f"{tmp_path.name}_edit.mp4"
    assert abs(float(ff.probe(video)["format"]["duration"]) - float(ff.probe(a / "clean.mp4")["format"]["duration"])) < 0.1
    result = json.loads((tmp_path / "output" / "check.json").read_text(encoding="utf-8"))[video.name]
    assert result["ok"], result["issues"]
