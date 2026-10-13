"""edit 모드(student-kit): 말하는 영상 하나 → 무음 컷 → 실수 컷 → HyperFrames 0.7.109 구성(work/edit/).
키트 컷 스크립트는 kits/에서 그대로 돌린다. 전사는 ElevenLabs 대신 whisper.cpp 단어 단위 + 무음 구간으로 단어 경계를 다듬어
키트 형식(words[{text,start,end}], 초)으로 쓴다."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

from . import convert, ff, kits, transcribe
from .paths import Project
from .whisper import Segment, WhisperCli, model_size

KIT = kits.KITS_DIR / "hyperframes-student-kit"
CUT_SILENCES = KIT / ".claude/skills/cut-silences/scripts/cut-silences.mjs"
FIND_CUTS = KIT / ".claude/skills/cut-mistakes/scripts/find-cut-candidates.mjs"
APPLY_CUTS = KIT / ".claude/skills/cut-mistakes/scripts/apply-cuts.mjs"
WORDS_VERSION = 1  # raw.json 만드는 방식이 바뀌면 올린다 — 다시 전사
SILENCE_FILTER = "silencedetect=noise=-35dB:d=0.3"  # ponytail: 고정 문턱, 잡음 큰 녹음에서 무음을 못 찾으면 조절
STUTTER_GAP = 0.5  # 키트 find-cut-candidates와 같은 값
BT709 = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
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


def _token(text: str) -> str:
    return re.sub(r"^\W+|\W+$", "", text.lower())


def stutters(words: list[dict]) -> list[dict]:
    """같은 단어가 0.5초 안에 바로 이어지면 앞의 것을 자르는 후보. 키트 규칙과 같고 한글을 읽는다(키트는 영문만)."""
    out = []
    for a, b in zip(words, words[1:]):
        t = _token(b["text"])
        if t and t == _token(a["text"]) and b["start"] - a["end"] < STUTTER_GAP:
            out.append({"id": f"k{len(out) + 1:03d}", "type": "stutter", "confidence": "high", "recommend": "cut",
                        "cut": {"start": a["start"], "end": b["start"]}, "removes": a["text"], "keeps": b["text"],
                        "note": f'반복 "{t}"'})
    return out


def work(proj: Project) -> Path:
    return proj.root / "work" / "edit"


def assets(proj: Project) -> Path:
    return work(proj) / "assets"


def _node(script: Path, *args) -> None:
    r = subprocess.run(["node", str(script), *map(str, args)], stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace")
    if r.returncode:
        raise RuntimeError(f"키트 {script.name} 실패: {(r.stderr or r.stdout).strip()[-600:]}")


def prepare_source(src: Path, track: int, dst: Path) -> None:
    """키트는 영상 1·오디오 1을 요구한다. HDR은 SDR bt709로 바꾼다(키트의 libx264 재인코딩은 색을 다루지 않는다)."""
    stream = next(s for s in ff.probe(src)["streams"] if s["codec_type"] == "video")
    part = dst.with_name(dst.stem + ".part.mp4")
    if convert.is_hdr(stream):
        w, h = convert._display_size(stream)
        inp, vf = convert.video_input(src, stream, w // 2 * 2, h // 2 * 2)
        video = ["-vf", vf, "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", *BT709]
    else:
        inp, video = ["-i", str(src)], ["-c:v", "copy"]
    try:
        ff.run(*inp, "-map", "0:v:0", "-map", f"0:a:{track - 1}", *video, "-c:a", "aac", "-b:a", "192k", str(part))
        part.replace(dst)
    finally:
        part.unlink(missing_ok=True)


def _silences(wav: Path, duration: float) -> list[tuple[float, float]]:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(wav), "-af", SILENCE_FILTER, "-f", "null", "-"],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace")
    if r.returncode:
        raise RuntimeError(f"무음 찾기 실패: {r.stderr.strip()[-300:]}")
    return parse_silence(r.stderr, duration)


def prepare(proj: Project, file: str | None = None, track: int = 1, engine_factory=WhisperCli.from_env,
            models: Path = transcribe.MODELS_DIR, download=None) -> dict:
    """원본 → assets/raw.mp4·raw.json(단어 전사) → 키트 무음 컷(silenced.mp4) → 실수 후보(candidates.json)."""
    if not CUT_SILENCES.exists():
        raise RuntimeError("student-kit이 없습니다 — 먼저 `python -m pipeline kits`로 받으세요")
    src = transcribe.source_video(proj, file)
    n = len(transcribe.audio_tracks(src))
    if not 1 <= track <= n:
        raise ValueError(f"트랙 {track}이(가) 없습니다 (1~{n}번)")
    a = assets(proj)
    a.mkdir(parents=True, exist_ok=True)
    raw, rj = a / "raw.mp4", a / "raw.json"
    st = src.stat()
    key = hashlib.sha1(json.dumps([str(src), st.st_size, st.st_mtime_ns, track, model_size(), WORDS_VERSION]).encode()).hexdigest()[:12]
    if not (raw.exists() and rj.exists() and json.loads(rj.read_text(encoding="utf-8")).get("key") == key):
        engine = engine_factory(models)  # whisper-cli가 없으면 여기서 멈춘다 — 모델을 받기 전에
        (download or transcribe.ensure_models)(models)
        prepare_source(src, track, raw)
        wav = a / "raw.wav"
        try:
            transcribe.extract_wav(raw, 1, wav)
            duration = float(ff.probe(raw)["format"]["duration"])
            words = fit_words(engine.transcribe(wav, LANGUAGE, words=True), _silences(wav, duration))
        finally:
            wav.unlink(missing_ok=True)
        rj.write_text(json.dumps({"key": key, **kit_transcript(words, duration)}, ensure_ascii=False, indent=1), encoding="utf-8")
    _node(CUT_SILENCES, rj, "--video", raw, "--out-dir", a, "--output", a / "silenced.mp4", "--apply")
    _node(FIND_CUTS, a / "raw.silence-transcript.json", "--out-dir", a)
    edl = json.loads((a / "raw.silence-edl.json").read_text(encoding="utf-8"))
    silenced = json.loads((a / "raw.silence-transcript.json").read_text(encoding="utf-8"))["words"]
    kit_found = json.loads((a / "raw.cut-candidates.json").read_text(encoding="utf-8"))["candidates"]
    found = kit_found + [c for c in stutters(silenced) if c["cut"] not in [k["cut"] for k in kit_found]]
    (a / "candidates.json").write_text(json.dumps({"timeline": "silenced.mp4", "candidates": found}, ensure_ascii=False, indent=1),
                                       encoding="utf-8")
    return {"source": src.name, "words": len(silenced), "source_duration": edl["source_duration"],
            "edited_duration": edl["edited_duration"], "candidates": found}
