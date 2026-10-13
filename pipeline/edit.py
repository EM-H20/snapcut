"""edit 모드(student-kit): 말하는 영상 하나 → 무음 컷 → 실수 컷 → HyperFrames 0.7.109 구성(work/edit/).
키트 컷 스크립트는 kits/에서 그대로 돌린다. 전사는 ElevenLabs 대신 whisper.cpp 단어 단위 + 무음 구간으로 단어 경계를 다듬어
키트 형식(words[{text,start,end}], 초)으로 쓴다."""
import re

from .whisper import Segment

LANGUAGE = "ko"
SILENCE_RE = re.compile(r"silence_(start|end): (-?[\d.]+)")
CUE_CHARS = 16  # srt 한 장 최대 글자 (motion-broll이 단어 시각을 읽는 용도)
CUE_GAP = 0.6


def parse_silence(log: str, duration: float) -> list[tuple[float, float]]:
    """ffmpeg silencedetect 로그 → (시작, 끝). 끝나지 않은 무음은 파일 끝까지."""
    out, start = [], None
    for kind, t in SILENCE_RE.findall(log):
        if kind == "start":
            start = max(0.0, float(t))
        elif start is not None:
            out.append((start, float(t)))
            start = None
    if start is not None:
        out.append((start, duration))
    return out


def fit_words(segs: list[Segment], silences: list[tuple[float, float]]) -> list[dict]:
    """whisper 단어 시각은 쉼 근처에서 무음을 삼킨다(VAD는 무음을 다음 단어에 붙인다). 실제 무음 구간으로 경계를 자른다."""
    out = []
    for s in segs:
        a, b = s.start, s.end
        for s0, s1 in silences:
            if s0 <= a and b <= s1 and b > a:
                break  # 통째로 무음 안 — 환청
            if a < s0 and s1 < b:  # 무음을 품음: 긴 쪽이 진짜 말
                a, b = (s1, b) if b - s1 >= s0 - a else (a, s0)
            elif s0 <= a < s1:
                a = s1
            elif s0 < b <= s1:
                b = s0
        else:
            out.append({"text": s.text, "start": round(a, 3), "end": round(max(a, b), 3), "type": "word"})
    return out


def kit_transcript(words: list[dict], duration: float) -> dict:
    return {"language_code": LANGUAGE, "audio_duration_secs": round(duration, 3),
            "text": " ".join(w["text"] for w in words), "words": words}


def cues(words: list[dict]) -> list[dict]:
    out = []
    for w in words:
        c = out[-1] if out else None
        if c and not c["text"].endswith((".", "?", "!")) and w["start"] - c["end"] <= CUE_GAP \
                and len(c["text"]) + 1 + len(w["text"]) <= CUE_CHARS:
            c["text"] += " " + w["text"]
            c["end"] = w["end"]
        else:
            out.append({"start": w["start"], "end": w["end"], "text": w["text"]})
    return out
