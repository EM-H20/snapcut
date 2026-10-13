import wave

import numpy as np
import pytest

from pipeline import sound

needs_kit = pytest.mark.skipif(not (sound.KIT / "sfx" / "synth.py").exists(), reason="claude-motion 키트 필요 (python -m pipeline kits)")
CUES = {"transitions": [{"t": 2.0, "kind": "whip", "len": 0.4}, {"t": 5.0, "kind": "dissolve", "len": 0.6}], "accents": [], "drop": 8.0}


def _read(path):
    with wave.open(str(path), "rb") as w:
        assert (w.getnchannels(), w.getframerate(), w.getsampwidth()) == (2, 48000, 2)
        return np.frombuffer(w.readframes(w.getnframes()), "<i2").reshape(-1, 2).astype(np.float32) / 32768


def _rms(x, a, b):
    s = x[int(a * 48000):int(b * 48000)]
    return float(np.sqrt((s ** 2).mean()))


@needs_kit
def test_sfx_stem_places_whooshes_and_drop(tmp_path):
    out = tmp_path / "sfx.wav"
    sound.render_sfx(CUES, 10.0, out)
    x = _read(out)
    assert len(x) == 480000
    assert _rms(x, 2.0, 2.4) > 20 * _rms(x, 0.5, 1.5) + 1e-4       # 휙 (휩 전환)
    assert _rms(x, 8.0, 8.6) > _rms(x, 3.0, 4.0)                   # 드롭 임팩트
    assert np.abs(x).max() <= sound.PEAK + 1e-3                    # 클리핑 없음


@needs_kit
def test_sfx_stem_is_deterministic(tmp_path):
    a, b = tmp_path / "a.wav", tmp_path / "b.wav"
    sound.render_sfx(CUES, 10.0, a)
    __import__("random").random()  # 다른 코드가 전역 random을 써도
    sound.render_sfx(CUES, 10.0, b)
    assert a.read_bytes() == b.read_bytes()


def test_sfx_without_kit_says_how(tmp_path, monkeypatch):
    monkeypatch.setattr(sound, "KIT", tmp_path / "none")
    with pytest.raises(RuntimeError, match="pipeline kits"):
        sound.render_sfx(CUES, 10.0, tmp_path / "x.wav")
