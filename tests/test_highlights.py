import numpy as np

from pipeline.convert import convert_project
from pipeline.curate import curate
from pipeline.highlights import analyze_clips, loud_segments, suggest_segment
from pipeline.paths import Project


def test_loud_segments_finds_spike():
    rms = np.full(100, 0.1)
    rms[40:70] = 1.0
    assert loud_segments(rms, hop_s=0.05) == [(2.0, 3.5)]


def test_loud_segments_ignores_silence_and_short_blips():
    assert loud_segments(np.zeros(50), hop_s=0.05) == []
    rms = np.full(100, 0.1)
    rms[10:13] = 1.0  # 0.15초 — min_len 0.5 미만
    assert loud_segments(rms, hop_s=0.05) == []


def test_suggest_prefers_loud_and_marks_live():
    s = suggest_segment(10.0, [(0.0, 10.0)], [(6.0, 7.0)])
    assert s == {"in": 4.5, "out": 8.5, "liveAudio": True}


def test_suggest_clamps_to_clip_and_short_clip():
    assert suggest_segment(10.0, [(0.0, 10.0)], [(9.5, 10.0)])["out"] == 10.0
    assert suggest_segment(2.0, [], []) == {"in": 0.0, "out": 2.0, "liveAudio": False}


def test_suggest_segment_rounding_stays_in_bounds_nonround_duration():
    # Ensure out doesn't exceed duration after rounding
    result = suggest_segment(10.037, [(0.0, 10.037)], [(9.5, 10.037)])
    assert result["out"] <= 10.037
    assert abs((result["out"] - result["in"]) - 4.0) <= 0.01


def test_suggest_segment_short_nonround_duration():
    # Ensure out stays within bounds for short nonround durations
    result = suggest_segment(3.996, [], [])
    assert result["in"] == 0.0
    assert result["out"] <= 3.996


def test_analyze_clips_on_sample(sample_project):
    proj = Project(sample_project)
    convert_project(proj)
    h = analyze_clips(proj, curate(proj)["candidates"])
    assert set(h) == {"media/IMG_0200_mov.mp4", "media/IMG_0201_mp4.mp4"}
    silent = h["media/IMG_0201_mp4.mp4"]
    assert silent["loud"] == [] and silent["suggested"]["liveAudio"] is False
    assert (proj.cache / "highlights.json").exists()
