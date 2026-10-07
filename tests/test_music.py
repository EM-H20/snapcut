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
