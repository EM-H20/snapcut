import librosa
import numpy as np

from . import ff

SR = 22050
REELS_SECONDS = 45.0
VERSION = 2  # 분석 결과 형식 버전. 바꾸면 예전 캐시는 다시 분석된다 (sections 추가: 2)
HI, LO, DIP = 0.85, 0.65, 0.5  # 마디 에너지(곡 중간값 대비): 고에너지 / 저에너지 / 짧은 꺼짐의 최저값
ESTIMATE = {"브릿지": 0.60, "마지막후렴": 0.75}  # 구간을 못 찾을 때 곡 길이 비율


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


def _runs(mask) -> list[tuple[int, int]]:
    out, i = [], 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j < len(mask) and mask[j]:
                j += 1
            out.append((i, j))
            i = j
        else:
            i += 1
    return out


def find_sections(downbeats, beats, bar_energy, onset_times, onset_strength, duration) -> dict:
    """마디 에너지로 곡 구간을 찾는다. 각 지점은 그 마디 근처의 가장 강한 타격으로 맞춘다.
    DAY6 '한 페이지가 될 수 있게'에서 손으로 찾은 값(126.74 / 153.51 / 163.79)과 1박 이내로 검증."""
    db = np.asarray(downbeats, dtype=float)
    e = np.asarray(bar_energy, dtype=float)
    ot, os_ = np.asarray(onset_times, dtype=float), np.asarray(onset_strength, dtype=float)
    beat = float(np.median(np.diff(beats))) if len(beats) > 1 else 0.5
    out = {"브릿지": None, "브레이크": None, "마지막후렴": None, "estimated": []}
    if len(e) >= 2 and np.median(e) > 0:
        e = e / np.median(e)

    def strongest(lo_t: float, hi_t: float) -> float:
        m = (ot >= lo_t) & (ot <= hi_t)
        return round(float(ot[m][np.argmax(os_[m])]), 3) if m.any() else round(lo_t, 3)

    hi, lo = e >= HI, e < LO
    final = brk = None
    long_hi = [r for r in _runs(hi) if r[1] - r[0] >= 8 and db[r[0]] > duration * 0.5]
    if long_hi:
        final = long_hi[-1][0]
        j = final
        while j > 0 and not hi[j - 1]:
            j -= 1
        if final - j >= 4 and lo[j:final].mean() >= 0.5:
            brk = j
    end = brk if brk is not None else (final if final is not None else len(e))
    bridge = None
    for b in range(1, max(1, end - 1)):
        if db[b] < duration * 0.5:
            continue
        for w in (1, 2):
            if b + w < len(e) and e[b:b + w].min() < DIP and hi[b - 1] and hi[b + w]:
                bridge = (b, b + w)
                break
        if bridge:
            break
    if final is not None:
        out["마지막후렴"] = strongest(db[final] - beat, db[final] + 4 * beat)
    if brk is not None:
        out["브레이크"] = strongest(db[brk] - beat, db[brk] + 4 * beat)
    if bridge is not None:
        out["브릿지"] = strongest(db[bridge[0]] - beat, db[bridge[1]])
    # 못 찾은 구간은 곡 길이 비율로 추정 (마디 첫 박에 맞춤)
    if len(db):
        def near(t: float) -> int:
            return int(np.argmin(np.abs(db - t)))
        for name, ratio in ESTIMATE.items():
            if out[name] is None:
                out[name] = round(float(db[near(duration * ratio)]), 3)
                out["estimated"].append(name)
        if out["브레이크"] is None:
            out["브레이크"] = round(float(db[max(0, near(out["마지막후렴"]) - 8)]), 3)
            out["estimated"].append("브레이크")
    return out


def _bar_energy(rms, times, downbeats) -> list[float]:
    out = []
    for a, b in zip(downbeats, downbeats[1:]):
        m = (times >= a) & (times < b)
        out.append(float(rms[m].mean()) if m.any() else 0.0)
    return out


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
    sections = find_sections(downbeats, beats, _bar_energy(rms, times, downbeats),
                             librosa.times_like(onset, sr=SR), onset, duration)
    return {
        "duration": duration,
        "bpm": round(float(np.atleast_1d(tempo)[0]), 1),
        "beats": [round(float(b), 3) for b in beats],
        "downbeats": downbeats,
        "chorus": chorus,
        "sections": sections,
        "version": VERSION,
    }
