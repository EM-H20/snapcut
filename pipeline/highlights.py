import json

import numpy as np
from scenedetect import ContentDetector, detect

from . import ff
from .paths import Project

SR = 22050
HOP = 512
LOUD_FACTOR = 2.0   # 클립 RMS 중앙값의 몇 배부터 "현장 소리 하이라이트"인가
MIN_LOUD = 0.5
MAX_SEGMENT = 4.0


def loud_segments(rms, hop_s: float, factor: float = LOUD_FACTOR, min_len: float = MIN_LOUD) -> list[tuple[float, float]]:
    if len(rms) == 0:
        return []
    base = float(np.median(rms))
    if base <= 1e-6:
        return []
    above = np.append(rms > factor * base, False)
    segs, start = [], None
    for i, a in enumerate(above):
        if a and start is None:
            start = i
        elif not a and start is not None:
            if (i - start) * hop_s >= min_len:
                segs.append((round(start * hop_s, 2), round(i * hop_s, 2)))
            start = None
    return segs


def suggest_segment(duration: float, scenes, loud, max_len: float = MAX_SEGMENT) -> dict:
    length = min(max_len, duration)
    if loud:
        s, e = max(loud, key=lambda x: x[1] - x[0])
        live = True
    else:
        s, e = max(scenes, key=lambda x: x[1] - x[0]) if scenes else (0.0, duration)
        live = False
    start = min(max(0.0, (s + e) / 2 - length / 2), duration - length)
    return {"in": round(start, 2), "out": round(start + length, 2), "liveAudio": live}


def _rms(path) -> np.ndarray:
    y = ff.load_mono(path, SR)
    frames = len(y) // HOP
    if frames == 0:
        return np.array([])
    return np.sqrt((y[:frames * HOP].reshape(frames, HOP) ** 2).mean(axis=1))


def analyze_clips(proj: Project, candidates: list[dict]) -> dict:
    out = {}
    for c in candidates:
        if c["type"] != "video":
            continue
        path = proj.cache / c["file"]
        scenes = [(round(a.get_seconds(), 2), round(b.get_seconds(), 2)) for a, b in detect(str(path), ContentDetector())]
        loud = loud_segments(_rms(path), HOP / SR) if c.get("has_audio") else []
        out[c["file"]] = {"duration": c["duration"], "scenes": scenes, "loud": loud,
                          "suggested": suggest_segment(c["duration"], scenes, loud)}
    (proj.cache / "highlights.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
