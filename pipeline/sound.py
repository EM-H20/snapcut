"""추억 뮤비 효과음 줄기(stem) — 전환마다 휙, 드롭에 라이저 + 임팩트(영상에 한 번). 강조 플래시에는 소리를 붙이지 않는다
(claude-motion sound-design: "accent, don't narrate"). 합성은 claude-motion 키트의 sfx/synth.py(표준 라이브러리)를 그대로 부르고,
섞기는 numpy, 마스터링 없이 고정 레벨 — 최종 음량은 렌더 뒤 pipeline master가 음악과 함께 맞춘다."""
import random
import sys
import wave
from pathlib import Path

import numpy as np

from . import kits

KIT = kits.KITS_DIR / "claude-motion"
SR = 48000
PEAK = 0.9
SEED = 7
WHOOSH_GAIN, RISER_GAIN, IMPACT_GAIN = 0.16, 0.18, 0.32  # 키트 기준: 주인공 0.25–0.35, 받쳐 주는 소리 0.08–0.2
RISER_SECONDS = 1.4


def _synth():
    if not (KIT / "sfx" / "synth.py").exists():
        raise RuntimeError("효과음(effects.sfx)에는 claude-motion 키트가 필요합니다 — 먼저 `python -m pipeline kits`")
    if str(KIT) not in sys.path:
        sys.path.insert(0, str(KIT))
    from sfx import synth  # 키트의 최상위 패키지 sfx (snapcut에는 같은 이름 모듈이 없다)
    return synth


def render_sfx(cues: dict, duration: float, path: Path, seed: int = SEED) -> None:
    synth = _synth()
    random.seed(seed)  # 키트 합성기는 전역 random을 쓴다 — 씨앗을 정하고 정해진 순서로 만들어야 매번 같은 소리
    mix = np.zeros((int(round(duration * SR)), 2))

    def put(t: float, samples: list[float], gain: float) -> None:
        a = int(round(t * SR))
        s = np.asarray(samples)[max(0, -a):] * gain
        a = max(0, a)
        n = min(len(s), len(mix) - a)
        if n > 0:
            mix[a:a + n] += (s[:n] * np.sqrt(0.5))[:, None]  # 가운데 (등전력)

    for c in cues["transitions"]:  # 휙이 가장 큰 순간 = 전환 한가운데
        put(c["t"], synth.whoosh(min(0.6, max(0.3, c["len"])), 500, 2400, peak=0.5), WHOOSH_GAIN)
    if cues["drop"] is not None:
        put(cues["drop"] - RISER_SECONDS, synth.riser(RISER_SECONDS), RISER_GAIN)
        put(cues["drop"] - 0.01, synth.impact(), IMPACT_GAIN)
    peak = float(np.abs(mix).max())
    if peak > PEAK:
        mix *= PEAK / peak
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mix * 32767).astype("<i2").tobytes())
