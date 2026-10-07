import librosa
import numpy as np

from . import ff

SR = 22050
REELS_SECONDS = 45.0


def pick_downbeats(beats, strengths, meter: int = 4) -> list[float]:
    # ponytail: 4/4 가정, 강세가 가장 센 위상을 마디 첫 박으로. 3박 곡은 틀림 — 필요하면 meter 추정 추가
    beats = np.asarray(beats)
    if len(beats) < meter:
        return [float(b) for b in beats[:1]]
    phase = max(range(meter), key=lambda p: float(np.mean(strengths[p::meter])))
    return [round(float(b), 3) for b in beats[phase::meter]]


def best_window(energy, times, length: float) -> tuple[float, float]:
    total = float(times[-1]) if len(times) else 0.0
    if total <= length:
        return (0.0, total)
    step = float(times[1] - times[0])
    n = max(1, int(round(length / step)))
    csum = np.concatenate([[0.0], np.cumsum(energy)])
    i = int(np.argmax(csum[n:] - csum[:-n]))
    start = float(times[i])
    return (round(start, 2), round(min(start + length, total), 2))


def analyze(path) -> dict:
    y = ff.load_mono(path, SR)
    if len(y) < SR:
        raise RuntimeError("음악이 너무 짧습니다 (1초 미만)")
    tempo, beats = librosa.beat.beat_track(y=y, sr=SR, units="time")
    beats = np.asarray(beats)
    onset = librosa.onset.onset_strength(y=y, sr=SR)
    idx = np.clip(librosa.time_to_frames(beats, sr=SR), 0, len(onset) - 1)
    rms = librosa.feature.rms(y=y)[0]
    times = librosa.times_like(rms, sr=SR)
    duration = round(len(y) / SR, 3)
    downbeats = pick_downbeats(beats, onset[idx])
    chorus = [0.0, duration]
    if duration > REELS_SECONDS:
        start = best_window(rms, times, REELS_SECONDS)[0]
        if downbeats:  # 릴스는 마디 첫 박에서 시작
            start = min(downbeats, key=lambda d: abs(d - start))
        chorus = [start, round(min(duration, start + REELS_SECONDS), 3)]
    return {
        "duration": duration,
        "bpm": round(float(np.atleast_1d(tempo)[0]), 1),
        "beats": [round(float(b), 3) for b in beats],
        "downbeats": downbeats,
        "chorus": chorus,
    }
