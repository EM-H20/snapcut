import numpy as np
import pytest

from pipeline.music import analyze, best_window, pick_downbeats


def test_pick_downbeats_follows_accent_phase():
    beats = np.arange(16) * 0.5
    strengths = np.full(16, 0.3)
    strengths[1::4] = 1.0
    assert pick_downbeats(beats, strengths) == [0.5, 2.5, 4.5, 6.5]


def test_best_window_finds_loudest_stretch():
    times = np.arange(0, 60, 0.5)
    energy = np.full(len(times), 0.1)
    energy[(times >= 30) & (times < 40)] = 1.0
    s, e = best_window(energy, times, 10.0)
    assert 29.0 <= s <= 31.0 and abs((e - s) - 10.0) < 0.6


def test_best_window_short_song_returns_whole():
    times = np.arange(0, 20, 0.5)
    assert best_window(np.ones(len(times)), times, 45.0) == (0.0, 19.5)


def test_analyze_click_track(sample_project):
    m = analyze(sample_project / "song.wav")
    assert 117 <= m["bpm"] <= 123
    gaps = np.diff(m["beats"])
    assert abs(float(np.median(gaps)) - 0.5) < 0.03
    assert abs(m["duration"] - 30.0) < 0.1
    assert m["chorus"][0] == 0.0  # 30초 곡 < 45초 → 통째
    assert m["chorus"] == [0.0, m["duration"]]
    assert len(m["downbeats"]) >= 10


def test_long_song_chorus_starts_on_downbeat(tmp_path):
    from tests.conftest import make_click_track
    make_click_track(tmp_path / "long.wav", seconds=90.0)
    m = analyze(tmp_path / "long.wav")
    start, end = m["chorus"]
    assert min(abs(start - d) for d in m["downbeats"]) <= 0.05
    assert end == pytest.approx(min(m["duration"], start + 45.0), abs=1e-3)


from pipeline.music import VERSION, find_sections


def _song(energy_by_bar, bar=2.0):
    """마디 에너지 목록 → find_sections 입력 (4/4, 마디 2초, 각 마디 첫 박에 강한 onset)."""
    n = len(energy_by_bar)
    downbeats = [i * bar for i in range(n + 1)]
    beats = [i * bar / 4 for i in range(4 * n + 1)]
    onset_s = [1.0 if i % 4 == 0 else 0.3 for i in range(len(beats))]
    return dict(downbeats=downbeats, beats=beats, bar_energy=energy_by_bar,
                onset_times=beats, onset_strength=onset_s, duration=n * bar)


def test_find_sections_on_known_shape():
    # 82마디(164초, 50%=82초). 0~41: 보통(1.0), 42~43: 짧은 꺼짐(0.7, 0.3) — 50% 뒤라야 브릿지 후보,
    # 44~57: 후렴(1.1), 58~63: 브레이크(0.5), 64~79: 마지막후렴(1.1), 80~81: 끝 페이드
    e = [1.0] * 42 + [0.7, 0.3] + [1.1] * 14 + [0.5] * 6 + [1.1] * 16 + [0.2, 0.05]
    s = find_sections(**_song(e))
    assert s["마지막후렴"] == 128.0 and s["브레이크"] == 116.0 and s["브릿지"] == 84.0
    assert s["estimated"] == []


def test_find_sections_flat_song_is_estimated():
    s = find_sections(**_song([1.0] * 60))
    assert set(s["estimated"]) == {"브릿지", "브레이크", "마지막후렴"}
    assert s["브릿지"] == 72.0 and s["마지막후렴"] == 90.0 and s["브레이크"] == 74.0  # 0.60·0.75 지점의 마디 첫 박, 브레이크 = 후렴 − 8마디


def test_find_sections_tiny_song_does_not_crash():
    s = find_sections(**_song([1.0] * 3))
    assert set(s) == {"브릿지", "브레이크", "마지막후렴", "estimated"}


def test_analyze_has_sections_and_version(sample_project):
    m = analyze(sample_project / "song.wav")
    assert m["version"] == VERSION and set(m["sections"]) >= {"브릿지", "브레이크", "마지막후렴", "estimated"}
