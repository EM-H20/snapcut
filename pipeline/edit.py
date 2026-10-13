"""edit 모드(student-kit): 말하는 영상 하나 → 무음 컷 → 실수 컷 → HyperFrames 0.7.109 구성(work/edit/).
키트 컷 스크립트는 kits/에서 그대로 돌린다. 전사는 ElevenLabs 대신 whisper.cpp 단어 단위 + 무음 구간으로 단어 경계를 다듬어
키트 형식(words[{text,start,end}], 초)으로 쓴다."""
import hashlib
import json
import math
import re
import shutil
import subprocess
import wave
from pathlib import Path

from . import convert, ff, kits, longform, transcribe
from .hf import mv
from .paths import Project
from .whisper import Segment, WhisperCli, model_size

KIT = kits.KITS_DIR / "hyperframes-student-kit"
CUT_SILENCES = KIT / ".claude/skills/cut-silences/scripts/cut-silences.mjs"
FIND_CUTS = KIT / ".claude/skills/cut-mistakes/scripts/find-cut-candidates.mjs"
APPLY_CUTS = KIT / ".claude/skills/cut-mistakes/scripts/apply-cuts.mjs"
HF = "hyperframes@0.7.109"  # 키트 고정 버전 — 0.8 스킬·구성과 섞지 않는다
RENDER_WORKERS = 1  # 키트 video-storytelling: 병렬 워커는 영상 층을 검게 칠한다
WORDS_VERSION = 1  # raw.json 만드는 방식이 바뀌면 올린다 — 다시 전사
SILENCE_DB = -35  # 무음 문턱 상한. 작게 녹음된 파일은 평균 음량 − SILENCE_BELOW_MEAN까지 내린다(말이 무음으로 잡혀 단어가 사라지지 않게)
SILENCE_BELOW_MEAN = 20
STUTTER_GAP = 0.5  # 키트 find-cut-candidates와 같은 값
FPS = 30
MAX_SIDE = 1920  # 구성 크기 상한 — 4K 원본도 1080p 급으로 렌더
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
    encode = ["-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", *BT709]
    if convert.is_hdr(stream):
        w, h = convert._display_size(stream)
        inp, vf = convert.video_input(src, stream, w // 2 * 2, h // 2 * 2)
        video = ["-vf", vf, *encode]
    elif stream.get("codec_name") in ("h264", "hevc") and stream.get("pix_fmt") == "yuv420p":
        inp, video = ["-i", str(src)], ["-c:v", "copy"]
    else:  # ProRes·10비트·4:2:2 등은 mp4에 못 담거나 키트 재인코딩 뒤 Chrome이 못 읽는다
        inp, video = ["-i", str(src)], encode
    try:
        ff.run(*inp, "-map", "0:v:0", "-map", f"0:a:{track - 1}", *video, "-c:a", "aac", "-b:a", "192k", str(part))
        part.replace(dst)
    finally:
        part.unlink(missing_ok=True)


def _ffmpeg_log(wav: Path, af: str) -> str:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(wav), "-af", af, "-f", "null", "-"],
                       stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace")
    if r.returncode:
        raise RuntimeError(f"무음 찾기 실패: {r.stderr.strip()[-300:]}")
    return r.stderr


def _silences(wav: Path, duration: float) -> list[tuple[float, float]]:
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", _ffmpeg_log(wav, "volumedetect"))
    noise = min(SILENCE_DB, float(mean.group(1)) - SILENCE_BELOW_MEAN) if mean else SILENCE_DB
    return parse_silence(_ffmpeg_log(wav, f"silencedetect=noise={noise:.1f}dB:d=0.3"), duration)


def words_from_wav(wav: Path, engine) -> tuple[list[dict], float]:
    """16kHz wav → 무음으로 경계를 다듬은 단어 목록, 길이."""
    with wave.open(str(wav), "rb") as w:
        duration = w.getnframes() / float(w.getframerate())
    return fit_words(engine.transcribe(wav, LANGUAGE, words=True), _silences(wav, duration)), duration


def transcribe_file(src: Path, out: Path, engine_factory=WhisperCli.from_env, models: Path = transcribe.MODELS_DIR,
                    download=None) -> dict:
    """음성·영상 파일 하나 → 키트 형식 단어 JSON (product-launch word-timings.mjs 등이 그대로 읽는다)."""
    if not transcribe.audio_tracks(src):
        raise ValueError(f"{src.name}에 소리가 없습니다")
    engine = engine_factory(models)
    (download or transcribe.ensure_models)(models)
    wav = out.with_name(out.stem + ".part.wav")
    try:
        transcribe.extract_wav(src, 1, wav)
        words, duration = words_from_wav(wav, engine)
    finally:
        wav.unlink(missing_ok=True)
    data = kit_transcript(words, duration)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


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
    stale = False
    key = hashlib.sha1(json.dumps([str(src), st.st_size, st.st_mtime_ns, track, model_size(), WORDS_VERSION]).encode()).hexdigest()[:12]
    if not (raw.exists() and rj.exists() and json.loads(rj.read_text(encoding="utf-8")).get("key") == key):
        engine = engine_factory(models)  # whisper-cli가 없으면 여기서 멈춘다 — 모델을 받기 전에
        (download or transcribe.ensure_models)(models)
        stale = _set_aside(a)
        prepare_source(src, track, raw)
        wav = a / "raw.wav"
        try:
            transcribe.extract_wav(raw, 1, wav)
            words, duration = words_from_wav(wav, engine)
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
            "edited_duration": edl["edited_duration"], "candidates": found, "stale": stale}


def _set_aside(a: Path) -> bool:
    """새 원본·트랙이면 silenced 시각이 바뀐다 — 예전 시각의 approved-cuts는 따로 두고 그 결과물은 지운다(index.html은 둔다)."""
    cuts = a / "approved-cuts.json"
    stale = cuts.exists()
    if stale:
        cuts.replace(a / "approved-cuts.stale.json")
    for n in ("clean.mp4", "transcript.json", "clean.srt"):
        (a / n).unlink(missing_ok=True)
    return stale


def starter(w: int, h: int, duration: float) -> str:
    """키트 방식 시작 구성: 시간 없는 감싸개 안 muted 영상 + 같은 파일의 소리. 오버레이는 Claude가 이 아래에 쓴다."""
    k = min(1.0, MAX_SIDE / max(w, h))
    w, h = round(w * k / 2) * 2, round(h * k / 2) * 2
    d = repr(math.floor(duration * FPS) / FPS)
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<script src="{mv.GSAP}"></script>
<style>
html, body {{ margin: 0; width: 100%; height: 100%; overflow: hidden; background: #000; }}
#edit {{ position: relative; width: 100%; height: 100%; overflow: hidden; background: #000; }}
#footage {{ position: absolute; inset: 0; }}
#footage video {{ width: 100%; height: 100%; object-fit: cover; }}
</style></head><body>
<div id="edit" data-composition-id="edit" data-start="0" data-width="{w}" data-height="{h}" data-duration="{d}">
<div id="footage"><video id="clean" src="assets/clean.mp4" data-start="0" data-duration="{d}" data-track-index="0" muted playsinline></video></div>
<audio id="clean-audio" src="assets/clean.mp4" data-start="0" data-duration="{d}" data-track-index="1"></audio>
<!-- 오버레이: 키트 hyperframes-video-beats 규칙대로 이 아래에 (시간은 assets/transcript.json 기준) -->
</div>
<script>
const tl = gsap.timeline({{paused: true}});
window.__timelines = window.__timelines || {{}};
window.__timelines["edit"] = tl;
</script></body></html>
"""


def apply(proj: Project) -> dict:
    """approved-cuts.json(silenced.mp4 기준 초)을 키트로 잘라 clean.mp4·transcript.json·clean.srt, 없으면 시작 index.html."""
    a = assets(proj)
    if not (a / "raw.silence-transcript.json").exists():
        raise RuntimeError(f"먼저 `python -m pipeline edit {proj.root.name}`를 실행하세요")
    cuts = a / "approved-cuts.json"
    if not cuts.exists():
        raise RuntimeError(f'{cuts}이(가) 없습니다 — candidates.json을 보고 자를 구간을 쓰세요 (자를 게 없으면 {{"cuts": []}})')
    _node(APPLY_CUTS, a / "raw.silence-transcript.json", "--cuts", cuts, "--video", a / "silenced.mp4",
          "--out-dir", a, "--output", a / "clean.mp4", "--apply")
    shutil.copyfile(a / "raw.mistakes-transcript.json", a / "transcript.json")  # 키트 validate-beat-sync가 읽는 이름
    words = json.loads((a / "transcript.json").read_text(encoding="utf-8"))["words"]
    (a / "clean.srt").write_text(longform.srt(cues(words)), encoding="utf-8")
    info = ff.probe(a / "clean.mp4")
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    duration = float(info["format"]["duration"])
    index = work(proj) / "index.html"
    created, resized = not index.exists(), None
    if created:
        index.write_text(starter(v["width"], v["height"], duration), encoding="utf-8")
    else:
        resized = _resize(index, repr(math.floor(duration * FPS) / FPS))
    return {"duration": duration, "cuts": len(json.loads(cuts.read_text(encoding="utf-8"))["cuts"]), "created": created,
            "resized": resized}


STARTER_DURATION = re.compile(r'(<(?:div|video|audio) id="(?:edit|clean|clean-audio)"[^>]*?data-duration=")([^"]*)(")')


def _resize(index: Path, d: str) -> tuple[str, str] | None:
    """다시 자르면 clean.mp4 길이가 바뀐다 — 시작 구성의 루트·영상·소리 길이만 맞춘다(Claude가 쓴 오버레이는 그대로)."""
    page = index.read_text(encoding="utf-8")
    old = STARTER_DURATION.search(page)
    if not old or old.group(2) == d:
        return None
    index.write_text(STARTER_DURATION.sub(lambda m: m.group(1) + d + m.group(3), page), encoding="utf-8")
    return old.group(2), d
