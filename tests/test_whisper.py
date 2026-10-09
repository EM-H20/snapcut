import json
import wave
from pathlib import Path

import pytest

from pipeline import whisper
from pipeline.whisper import REPETITION_PLACEHOLDER, VAD_MODEL_FILE, Segment, WhisperCli, find_repetition_span

LOOP = "같은 문장을 계속 반복합니다"


def silent_wav(path: Path, seconds: float, rate: int = 16000) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0\0" * int(seconds * rate))
    return path


def raw(*entries):
    """(from_ms, to_ms, text) — whisper-cli -oj 출력 모양."""
    return {"transcription": [{"offsets": {"from": a, "to": b}, "text": t} for a, b, t in entries]}


def looping(start_ms=0, count=4, step_ms=2000):
    return raw(*[(start_ms + i * step_ms, start_ms + (i + 1) * step_ms, " " + LOOP) for i in range(count)])


class FakeProcess:
    def __init__(self, args, output):
        self.args, self.output, self.returncode = args, output, None

    def communicate(self):
        if self.output is None:
            self.returncode = 1
            return None, b"boom"
        Path(self.args[self.args.index("-of") + 1] + ".json").write_text(json.dumps(self.output), encoding="utf-8")
        self.returncode = 0
        return None, b""


class FakeRun:
    def __init__(self, *outputs):
        self.outputs, self.calls = list(outputs), []

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        return FakeProcess(args, self.outputs.pop(0))


@pytest.fixture
def wav(tmp_path):
    return silent_wav(tmp_path / "a.wav", 12)


def engine(*outputs):
    run = FakeRun(*outputs)
    return WhisperCli("whisper-cli", "m/ggml-small.bin", "m/vad.bin", popen=run), run


def test_transcribes_with_vad_and_no_context(wav):
    e, run = engine(raw((0, 2400, " 안녕하세요"), (2400, 3000, "  "), (3000, 5000, " 두 번째")))
    assert e.transcribe(wav) == [Segment(0.0, 2.4, "안녕하세요"), Segment(3.0, 5.0, "두 번째")]
    args = run.calls[0]
    assert "--vad" in args and "-oj" in args
    assert args[args.index("-mc") + 1] == "0"
    assert args[args.index("-l") + 1] == "ko"
    assert args[args.index("-f") + 1] == str(wav)


def test_loop_is_redecoded_with_absolute_times(wav):
    first = raw((0, 2000, " 안녕하세요 시작합니다"), *[(2000 + i * 2000, 4000 + i * 2000, " " + LOOP) for i in range(4)])
    retry = raw((500, 1500, " 정상 문장입니다"))  # 1.5초부터 자른 조각에서 디코딩됨
    e, run = engine(first, retry)
    assert e.transcribe(wav) == [Segment(0.0, 2.0, "안녕하세요 시작합니다"), Segment(2.0, 3.0, "정상 문장입니다")]
    assert len(run.calls) == 2


def test_unresolved_loop_becomes_placeholder(wav):
    e, run = engine(looping(), looping(), looping())
    assert e.transcribe(wav) == [Segment(0.0, 8.0, REPETITION_PLACEHOLDER + LOOP)]
    assert len(run.calls) == 3


def test_failed_retry_falls_back_to_placeholder(wav):
    e, _ = engine(looping(), None, None)
    assert e.transcribe(wav) == [Segment(0.0, 8.0, REPETITION_PLACEHOLDER + LOOP)]


def test_overlong_loop_is_not_retried(wav):
    e, run = engine(raw(*[(i * 60000, (i + 1) * 60000, " " + LOOP) for i in range(4)]))
    assert e.transcribe(wav) == [Segment(0.0, 240.0, REPETITION_PLACEHOLDER + LOOP)]
    assert len(run.calls) == 1


def test_nonzero_exit_raises(wav):
    e, _ = engine(None)
    with pytest.raises(RuntimeError, match="whisper-cli"):
        e.transcribe(wav)


def test_invalid_utf8_is_replaced_not_fatal(wav):
    class BytesProcess:
        returncode = 0

        def __init__(self, args):
            self.args = args

        def communicate(self):
            body = b'{"transcription":[{"offsets":{"from":0,"to":1000},"text":" \xed\x95"}]}'
            Path(self.args[self.args.index("-of") + 1] + ".json").write_bytes(body)
            return None, b""

    e = WhisperCli("w", "m.bin", "v.bin", popen=lambda args, **kw: BytesProcess(args))
    assert "�" in e.transcribe(wav)[0].text


def test_short_repeats_are_normal_speech():
    assert find_repetition_span([Segment(i, i + 1, "네") for i in range(5)]) is None


def test_from_env_paths_and_model_size(monkeypatch, tmp_path):
    monkeypatch.delenv("WHISPER_CLI_BINARY", raising=False)
    monkeypatch.setattr(whisper.shutil, "which", lambda _: "/opt/homebrew/bin/whisper-cli")
    monkeypatch.setenv("WHISPER_MODEL", "small")
    e = WhisperCli.from_env(tmp_path)
    assert (e.binary, e.model_path, e.vad_model_path) == \
        ("/opt/homebrew/bin/whisper-cli", str(tmp_path / "ggml-small.bin"), str(tmp_path / VAD_MODEL_FILE))
    monkeypatch.delenv("WHISPER_MODEL")
    assert WhisperCli.from_env(tmp_path).model_path.endswith("ggml-large-v3.bin")
    monkeypatch.setenv("WHISPER_MODEL", "../x")
    with pytest.raises(RuntimeError, match="WHISPER_MODEL"):
        WhisperCli.from_env(tmp_path)


def test_from_env_missing_binary_explains_install(monkeypatch, tmp_path):
    monkeypatch.delenv("WHISPER_CLI_BINARY", raising=False)
    monkeypatch.setattr(whisper.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="brew install whisper-cpp"):
        WhisperCli.from_env(tmp_path)
