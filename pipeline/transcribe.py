"""롱폼 전사: 원본의 오디오 트랙 하나 → 16kHz WAV → Whisper → .cache/transcript.json, 초 단위 음량 → .cache/loudness.json.
원본 영상은 다시 인코딩하지 않는다. 모델(약 3GB)은 처음 한 번 공용/모델/에 받는다."""
import hashlib
import http.client
import json
import os
import shutil
import urllib.request
import wave
from pathlib import Path

import numpy as np

from . import ff
from .paths import SHARED, Project
from .whisper import VAD_MODEL_FILE, WhisperCli, model_size

MODELS_DIR = SHARED / "모델"
ASR_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{size}.bin"
VAD_URL = "https://huggingface.co/ggml-org/whisper-vad/resolve/main/" + VAD_MODEL_FILE
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv"}  # mkv = OBS 기본 녹화 형식
LANGUAGE = "ko"


def source_video(proj: Project, name: str | None) -> Path:
    if name:
        p = proj.sources / name
        if not p.is_file():
            raise ValueError(f"영상소스에 {name}이(가) 없습니다")
        return p
    videos = sorted(p for p in proj.sources.rglob("*") if p.suffix.lower() in VIDEO_EXT)
    if len(videos) != 1:
        listing = ", ".join(p.relative_to(proj.sources).as_posix() for p in videos) or "없음"
        raise ValueError(f"롱폼은 영상소스에 영상이 하나여야 합니다 (지금: {listing}) — --file로 고르세요")
    return videos[0]


def audio_tracks(src: Path) -> list[dict]:
    streams = [s for s in ff.probe(src)["streams"] if s["codec_type"] == "audio"]
    return [{"track": i, "channels": s.get("channels", 0), "title": (s.get("tags") or {}).get("title", "")}
            for i, s in enumerate(streams, 1)]


def extract_wav(src: Path, track: int, dst: Path) -> None:
    ff.run("-i", str(src), "-map", f"0:a:{track - 1}", "-vn", "-ar", "16000", "-ac", "1", str(dst))


def _wav_seconds(wav: Path) -> float:
    with wave.open(str(wav), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def loudness(wav: Path) -> list[float]:
    out = []
    with wave.open(str(wav), "rb") as w:
        rate = w.getframerate()
        while frames := w.readframes(rate):
            x = np.frombuffer(frames, "<i2").astype(np.float32) / 32768.0
            out.append(round(float(20 * np.log10(np.sqrt(np.mean(x * x)) + 1e-9)), 1))
    return out


def loud_moments(db: list[float], n: int = 20, gap: int = 10) -> list[int]:
    picked: list[int] = []
    for s in sorted(range(len(db)), key=lambda i: db[i], reverse=True):
        if all(abs(s - p) >= gap for p in picked):
            picked.append(s)
            if len(picked) == n:
                break
    return sorted(picked)


def ensure_models(models: Path, urlopen=urllib.request.urlopen, say=print) -> None:
    size = model_size()
    models.mkdir(parents=True, exist_ok=True)
    for url, name in ((ASR_URL.format(size=size), f"ggml-{size}.bin"), (VAD_URL, VAD_MODEL_FILE)):
        target = models / name
        if target.exists():
            continue
        say(f"Whisper 모델을 받습니다 (large-v3는 약 3GB, 한 번만): {name}")
        part = target.with_name(name + ".part")
        try:
            with urlopen(url) as response, part.open("wb") as out:
                shutil.copyfileobj(response, out)
                expected = (getattr(response, "headers", None) or {}).get("Content-Length")
            if expected and part.stat().st_size != int(expected):  # 연결이 끊겨도 urllib은 조용히 EOF를 낸다
                raise RuntimeError(f"{url}: 다운로드가 중간에 끊겼습니다 ({part.stat().st_size}/{expected}바이트) — 다시 실행하세요")
            part.rename(target)
        except (OSError, http.client.HTTPException) as e:
            raise RuntimeError(f"{url}: 모델을 받지 못했습니다 ({e}) — 인터넷 연결을 확인하고 다시 실행하세요") from e
        finally:
            part.unlink(missing_ok=True)


def _write(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def transcribe_project(proj: Project, file: str | None = None, track: int = 1, engine_factory=WhisperCli.from_env,
                       models: Path = MODELS_DIR, download=None) -> dict:
    src = source_video(proj, file)
    tracks = audio_tracks(src)
    if not tracks:
        raise ValueError(f"{src.name}에 오디오 트랙이 없습니다")
    if not 1 <= track <= len(tracks):
        raise ValueError(f"트랙 {track}이(가) 없습니다 (1~{len(tracks)}번)")
    st = src.stat()
    key = hashlib.sha1(json.dumps([str(src), st.st_size, st.st_mtime_ns, track, model_size(), LANGUAGE]).encode()).hexdigest()[:12]
    out = proj.cache / "transcript.json"
    if out.exists() and (old := json.loads(out.read_text(encoding="utf-8"))).get("key") == key:
        return old
    engine = engine_factory(models)  # whisper-cli가 없으면 여기서 멈춘다 — 모델을 받기 전에
    (download or ensure_models)(models)
    proj.cache.mkdir(exist_ok=True)
    wav = proj.cache / "audio.wav"
    try:
        extract_wav(src, track, wav)
        duration, db = _wav_seconds(wav), loudness(wav)
        segments = engine.transcribe(wav, LANGUAGE)
    finally:
        wav.unlink(missing_ok=True)
    data = {"key": key, "model": model_size(), "language": LANGUAGE, "source": src.relative_to(proj.sources).as_posix(),
            "track": track, "duration": round(duration, 3),
            "segments": [{"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text} for s in segments]}
    _write(proj.cache / "loudness.json", {"key": key, "db": db})
    _write(out, data)
    return data
