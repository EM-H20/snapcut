import random

import pytest

from pipeline import plan
from pipeline.hf import timing as T


def test_ts_floors_to_microseconds():
    assert T.ts(1754) == "58.466666"  # 반올림(58.466667)이면 그 프레임 시각보다 늦어 1프레임 검정
    assert T.ts(0) == "0.000000"
    assert T.ts(45) == "1.500000"


def test_window_end_never_before_next_start():
    rng = random.Random(1)
    for _ in range(500):
        a = rng.randrange(0, 9000)
        b = a + rng.randrange(1, 300)
        st, du = T.window(a, b)
        nxt, _ = T.window(b, b + 1)
        assert float(st) * 30 <= a + 1e-6  # 시작은 프레임 시각 이하
        assert round((float(st) + float(du)) * 1e6) >= round(float(nxt) * 1e6)  # 끝 ≥ 다음 시작


def test_frame_rounds_half_up_like_js():
    assert (T.frame(0.5, 1), T.frame(2.5, 1)) == (1, 3)  # 파이썬 round는 0, 2 (짝수 쪽)


SHOTS = [
    {"type": "photo", "src": "media/p.jpg", "start": 0, "end": 2, "kenBurns": "zoom-out"},
    {"type": "video", "src": "media/v.mp4", "start": 2, "end": 4, "in": 0, "out": 2, "liveAudio": False, "dissolve": 0.4},
    {"type": "photo", "src": "media/q.jpg", "start": 4, "end": 6, "kenBurns": "zoom-in"},
]


def _span(**kw):
    base = {"from": 0, "frames": 0, "duration": 0, "fadeIn": 0, "wipeIn": 0, "blurIn": 0, "blurOut": 0, "whipIn": 0, "whipOut": 0}
    return {**base, **kw}


def test_span_dissolve_extends_previous_and_fades_in():
    assert T.span(SHOTS, 0) == _span(frames=60, duration=72)
    assert T.span(SHOTS, 1) == _span(**{"from": 60}, frames=60, duration=60, fadeIn=12)
    assert T.span(SHOTS, 2) == _span(**{"from": 120}, frames=60, duration=60)


def test_span_blur_whip_halves_and_wipe_overlap():
    s = [{"type": "clip", "src": "cards/i.mp4", "start": 0, "end": 3},
         {"type": "video", "src": "v", "start": 3, "end": 5, "in": 0, "out": 2, "liveAudio": False, "blur": 0.6},
         {"type": "photo", "src": "p", "start": 5, "end": 7, "kenBurns": "still", "whip": 0.4},
         {"type": "photo", "src": "q", "start": 7, "end": 9, "kenBurns": "still", "wipe": 0.5}]
    assert T.span(s, 0)["blurOut"] == 9 and T.span(s, 1)["blurIn"] == 9 and T.span(s, 1)["blurOut"] == 0
    assert T.span(s, 1)["whipOut"] == 6 and T.span(s, 2)["whipIn"] == 6
    assert T.span(s, 2)["duration"] == 60 + 15 and T.span(s, 3)["wipeIn"] == 15  # 와이프는 디졸브처럼 겹친다


LIVE = {"type": "video", "src": "a.mp4", "start": 5, "end": 8, "in": 0, "out": 3, "liveAudio": True}


@pytest.mark.parametrize("t, shots, expect", [
    (1, [LIVE], 1.0), (6.5, [LIVE], T.DUCK), (6.5, [dict(LIVE, liveAudio=False)], 1.0),
    (20, [], 0.0), (6.5, [dict(LIVE, duck=False)], 1.0), (6.5, [dict(LIVE, duck=0.6)], 0.6),
    (5, [dict(LIVE, duckFade=2)], T.DUCK), (25, [], 0.0), (4.5, [dict(LIVE, jcut=1.0)], T.DUCK),
])
def test_music_volume_cases(t, shots, expect):
    assert T.music_volume(t, shots, 20) == pytest.approx(expect)


def test_music_volume_soft_edges_and_end_fade():
    assert T.DUCK < T.music_volume(4.85, [LIVE], 20) < 1
    assert 0 < T.music_volume(19, [], 20) < 1
    slow = dict(LIVE, duckFade=2)
    assert T.DUCK < T.music_volume(4, [slow], 20) < 1 and T.music_volume(9.5, [slow], 20) < 1


def test_duck_lane_follows_music_volume():
    shots = [LIVE, dict(LIVE, start=8.2, end=10, duck=0.6, duckFade=1.5)]
    lane = T.duck_lane(shots, 30.0, 28.0)
    ts_, vs = [p["t"] for p in lane], [p["v"] for p in lane]
    assert ts_ == sorted(ts_) and ts_[0] == 0 and ts_[-1] == 30.0
    for k in range(3000):
        t = k / 100
        j = max(n for n in range(len(ts_)) if ts_[n] <= t)
        v = vs[j] if j == len(ts_) - 1 else vs[j] + (vs[j + 1] - vs[j]) * (t - ts_[j]) / (ts_[j + 1] - ts_[j])
        assert v == pytest.approx(T.music_volume(t, shots, 28.0), abs=0.03)


def test_kenburns_values_scale_shift_like_css_order():
    assert T.kenburns("still") is None
    a, b = T.kenburns("zoom-in")
    assert (a["scale"], b["scale"]) == (1.0, 1.1)
    a, b = T.kenburns("pan-left")
    assert (a["xPercent"], b["xPercent"]) == (2.16, -2.16)  # CSS scale(1.08) translate(2%) = 화면 기준 2.16%
    a, b = T.kenburns("scroll-down")
    assert (a["scale"], a["yPercent"], b["yPercent"]) == (2.5, 75.0, -75.0)


def test_collage_grid():
    assert T.collage_grid(2, True) == (2, 1)
    assert T.collage_grid(3, False) == (1, 3)
    assert T.collage_grid(4, False) == (2, 2)


def test_credits_layout():
    lay = T.credits_layout(5, 1080)
    assert lay["size"] == 83 and lay["gap"] == pytest.approx(29.05) and lay["block"] == pytest.approx(614.2)


def test_shot_labels():
    v = {"type": "video", "src": "media/_talkv_abc_mp4.mp4", "start": 0, "end": 3, "in": 24.3, "out": 27.3, "liveAudio": False}
    assert T.shot_label(v, 1.25) == "_talkv_abc_mp4 25.6초"
    assert T.shot_label({"type": "collage", "srcs": ["media/a_jpg.jpg", "media/b_jpg.jpg"]}, 0) == "a_jpg, b_jpg"
    assert T.shot_label({"type": "credits"}, 0) == "크레딧"
    assert T.shot_label({"type": "clip"}, 0) == "인트로/아웃트로 카드"


def test_avg_speed():
    assert plan.avg_speed({}) == 1.0
    assert plan.avg_speed({"speed": 0.5}) == 0.5
    assert plan.avg_speed({"speed": [1, 0.5]}) == 0.75


def test_music_returns_during_freeze_of_live_video():
    frozen = dict(LIVE, start=5, end=10, freeze=1.0)  # 9~10초는 멈춘 화면 — 현장 소리가 없으니 음악이 돌아와야 한다
    assert T.music_volume(9.5, [frozen], 20) == pytest.approx(1.0)
    assert T.music_volume(9.5, [dict(frozen, lcut=0.6)], 20) == pytest.approx(T.DUCK)
