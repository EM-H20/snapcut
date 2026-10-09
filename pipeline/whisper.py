"""whisper-cli(whisper.cpp) 어댑터. lecture-inbox에서 이식 — 원 출처 Chuseok22/transcribe-inbox (MIT).
`-mc 0`은 반복 루프가 디코딩 창을 넘어 이어지는 것을 막는다. 한 창 안에서 생긴 루프는 그 구간만 다시 디코딩하고,
그래도 남으면 표시만 한다(자막에서는 longform이 뺀다)."""
import json
import logging
import os
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

log = logging.getLogger(__name__)

MODEL_SIZES = ("tiny", "base", "small", "medium", "large-v3")
VAD_MODEL_FILE = "ggml-silero-v6.2.0.bin"
MAX_RETRY_SPAN_SECONDS = 180.0
REPETITION_PLACEHOLDER = "[⚠️ 반복 감지 - 확인 필요] "
RETRY_PERTURBATIONS = ([], ["-et", "2.6", "-tp", "0.5"])
PAD_SECONDS = 0.5
MIN_REPEAT_RUN = 3
SIMILARITY_THRESHOLD = 0.9
MIN_REPEAT_TEXT_LENGTH = 5  # "네" 같은 짧은 맞장구 반복은 정상 발화


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


def model_size() -> str:
    size = os.environ.get("WHISPER_MODEL", "large-v3")
    if size not in MODEL_SIZES:
        raise RuntimeError(f"WHISPER_MODEL은 {', '.join(MODEL_SIZES)} 중 하나여야 합니다.")
    return size


def find_repetition_span(segments: list[Segment]) -> tuple[int, int] | None:
    """거의 같은 문장이 3번 이상 이어지는 첫 구간의 (처음, 끝) 인덱스."""
    run_start = 0
    for i in range(1, len(segments)):
        if SequenceMatcher(None, segments[i - 1].text, segments[i].text).ratio() < SIMILARITY_THRESHOLD:
            span = _qualifying(segments, run_start, i - 1)
            if span:
                return span
            run_start = i
    return _qualifying(segments, run_start, len(segments) - 1) if segments else None


def _qualifying(segments: list[Segment], start: int, end: int) -> tuple[int, int] | None:
    if end - start + 1 < MIN_REPEAT_RUN or len(segments[start].text) < MIN_REPEAT_TEXT_LENGTH:
        return None
    return (start, end)


def extract_wav_span(source: Path, start: float, end: float, dest: Path) -> float:
    """[start-0.5, end+0.5]초를 dest로 복사하고 dest 첫 프레임의 원본 시각을 돌려준다."""
    with wave.open(str(source), "rb") as src:
        rate = src.getframerate()
        total = src.getnframes() / float(rate)
        a = min(max(0.0, start - PAD_SECONDS), total)
        b = max(a, min(total, end + PAD_SECONDS))
        first = int(a * rate)
        src.setpos(first)
        frames = src.readframes(int(b * rate) - first)
        with wave.open(str(dest), "wb") as dst:
            dst.setnchannels(src.getnchannels())
            dst.setsampwidth(src.getsampwidth())
            dst.setframerate(rate)
            dst.writeframes(frames)
    return a


class WhisperCli:
    def __init__(self, binary: str, model_path: str, vad_model_path: str, popen=subprocess.Popen):
        self.binary, self.model_path, self.vad_model_path, self.popen = binary, model_path, vad_model_path, popen

    @classmethod
    def from_env(cls, models: Path) -> "WhisperCli":
        binary = os.environ.get("WHISPER_CLI_BINARY") or shutil.which("whisper-cli")
        if not binary:
            raise RuntimeError("whisper-cli를 찾을 수 없습니다. `brew install whisper-cpp`(또는 ./install.sh)를 실행하세요.")
        return cls(binary, str(models / f"ggml-{model_size()}.bin"), str(models / VAD_MODEL_FILE))

    def transcribe(self, wav: Path, language: str = "ko") -> list[Segment]:
        segments = self._segments(self._run(wav, ["-mc", "0", "-l", language]))
        return self._resolve_repetitions(segments, wav, language)

    def _run(self, wav: Path, extra_args: list[str]) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp) / "result"
            args = [self.binary, "--vad", "--vad-model", self.vad_model_path, "-m", self.model_path,
                    "-oj", "-of", str(prefix), "-f", str(wav), *extra_args]
            process = self.popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            _, stderr = process.communicate()
            if process.returncode != 0:
                raise RuntimeError(f"whisper-cli 실패({process.returncode}): {(stderr or b'').decode(errors='replace')[-500:]}")
            # whisper.cpp는 한글 한 글자를 두 문장에 걸쳐 잘라 깨진 UTF-8을 낼 수 있다(ggml-org/whisper.cpp#1798)
            return json.loads((prefix.parent / "result.json").read_bytes().decode("utf-8", errors="replace"))

    @staticmethod
    def _segments(raw: dict, offset: float = 0.0) -> list[Segment]:
        return [Segment(offset + e["offsets"]["from"] / 1000.0, offset + e["offsets"]["to"] / 1000.0, e["text"].strip())
                for e in raw.get("transcription", []) if e["text"].strip()]

    def _resolve_repetitions(self, segments: list[Segment], wav: Path, language: str) -> list[Segment]:
        search_from = 0
        with tempfile.TemporaryDirectory() as tmp:
            while True:
                span = find_repetition_span(segments[search_from:])
                if span is None:
                    return segments
                start, end = search_from + span[0], search_from + span[1]
                fixed = self._retry_span(segments[start:end + 1], wav, language, Path(tmp))
                segments = segments[:start] + fixed + segments[end + 1:]
                search_from = start + len(fixed)  # 항상 앞으로 가므로 끝난다

    def _retry_span(self, span: list[Segment], wav: Path, language: str, tmp: Path) -> list[Segment]:
        first, last = span[0], span[-1]
        placeholder = [Segment(first.start, last.end, REPETITION_PLACEHOLDER + first.text)]
        if last.end - first.start > MAX_RETRY_SPAN_SECONDS:
            log.warning("반복 구간 %.0f–%.0f초가 너무 길어 재시도 없이 표시만 합니다.", first.start, last.end)
            return placeholder
        clip = tmp / "retry.wav"
        offset = extract_wav_span(wav, first.start, last.end, clip)
        for extra in RETRY_PERTURBATIONS:
            try:
                raw = self._run(clip, ["-mc", "0", *extra, "-l", language])
            except RuntimeError:  # 재시도 실패가 나머지 전사를 망치면 안 된다
                log.warning("반복 구간 재디코딩 실패 (%.0f–%.0f초)", first.start, last.end, exc_info=True)
                continue
            retried = self._segments(raw, offset)
            if retried and find_repetition_span(retried) is None:
                return retried
        return placeholder
