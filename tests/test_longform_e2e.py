"""롱폼 E2E. 렌더 테스트는 고정 transcript로 Whisper 없이 돈다. 실제 Whisper 스모크는 모델·whisper-cli·say가 있을 때만."""
import json
import shutil
import subprocess
import sys

import pytest

from pipeline import ff, transcribe

pytestmark = pytest.mark.slow


def _cli(*args):
    r = subprocess.run([sys.executable, "-m", "pipeline", *args], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def test_longform_plan_render_mkv(tmp_path):
    (tmp_path / "영상소스").mkdir()
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=60:duration=20",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=20",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(tmp_path / "영상소스" / "game.mkv"))
    (tmp_path / ".cache").mkdir()
    tr = {"key": "fixture", "source": "game.mkv", "track": 1, "duration": 20.0,
          "segments": [{"start": 0.5, "end": 2.5, "text": "첫 번째 문장"}, {"start": 5.2, "end": 7.0, "text": "안 쓰는 문장"},
                       {"start": 11.0, "end": 12.5, "text": "세 번째 문장"}]}
    (tmp_path / ".cache" / "transcript.json").write_text(json.dumps(tr, ensure_ascii=False), encoding="utf-8")
    spec = {"clips": [{"in": 1.0, "out": 4.0, "title": "시작"}, {"in": 10.0, "out": 14.0}], "formats": ["longform", "shorts"]}
    (tmp_path / "longform.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")

    out = _cli("plan", str(tmp_path))
    assert "구간 2개, 자막 2개" in out
    assert "shorts: 2개" in out
    _cli("render", str(tmp_path))

    video = tmp_path / "output" / f"{tmp_path.name}_longform.mp4"
    info = ff.probe(video)
    assert abs(float(info["format"]["duration"]) - 7.8) < 0.1  # (4.0−0.2) + (14−10)
    assert {s["codec_type"] for s in info["streams"]} == {"video", "audio"}
    srt = (tmp_path / "output" / f"{tmp_path.name}_longform.srt").read_text(encoding="utf-8")
    assert "00:00:00,300 --> 00:00:02,300\n첫 번째 문장" in srt
    assert "00:00:04,800 --> 00:00:06,300\n세 번째 문장" in srt
    assert "안 쓰는 문장" not in srt
    short = tmp_path / "output" / "shorts" / f"{tmp_path.name}_01_시작.mp4"
    s_info = ff.probe(short)
    v = next(s for s in s_info["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (1080, 1920)
    assert abs(float(s_info["format"]["duration"]) - 3.8) < 0.1
    assert (tmp_path / "output" / "shorts" / f"{tmp_path.name}_02.mp4").exists()


@pytest.mark.skipif(not (shutil.which("whisper-cli") and shutil.which("say")
                         and (transcribe.MODELS_DIR / "ggml-large-v3.bin").exists()),
                    reason="whisper-cli·say·공용/모델/ggml-large-v3.bin 필요")
def test_transcribe_real_whisper_korean(tmp_path):
    (tmp_path / "영상소스").mkdir()
    subprocess.run(["say", "-v", "Yuna", "안녕하세요. 오늘은 게임을 합니다.", "-o", str(tmp_path / "speech.aiff")], check=True)
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=6", "-i", str(tmp_path / "speech.aiff"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(tmp_path / "영상소스" / "game.mkv"))
    out = _cli("transcribe", str(tmp_path))
    assert "오디오 트랙: 1번" in out and "전사 완료" in out
    t = json.loads((tmp_path / ".cache" / "transcript.json").read_text(encoding="utf-8"))
    assert any("안녕" in s["text"] for s in t["segments"])
