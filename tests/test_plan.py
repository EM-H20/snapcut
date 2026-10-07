import pytest

from pipeline.plan import (FORMATS, INTRO_SECONDS, OUTRO_SECONDS, build_format, build_storyboard,
                           fit, place, resolve_items, subsample)

BEATS = [round(i * 0.5, 3) for i in range(0, 241)]  # 120 BPM, 120초
MUSIC = {"duration": 120.0, "bpm": 120.0, "beats": BEATS, "downbeats": BEATS[::4], "chorus": [60.0, 105.0]}
CARDS = {"intro": "cards/i.mp4", "outro": "cards/o.mp4"}


def photo(n):
    return {"type": "photo", "src": f"media/p{n}.jpg"}


def video(dur=10.0, vin=0.0, vout=2.6, live=False):
    return {"type": "video", "src": "media/v.mp4", "in": vin, "out": vout, "duration": dur, "liveAudio": live}


def test_subsample_keeps_ends_evenly():
    assert subsample(list(range(10)), 4) == [0, 3, 6, 9]
    assert subsample([1, 2], 5) == [1, 2]
    assert subsample([1, 2, 3], 0) == []


def test_place_photos_on_beats():
    shots, left = place([photo(0), photo(1)], BEATS, 3.0, 20.0, 2)
    assert left == 0
    assert [(s["start"], s["end"]) for s in shots] == [(3.0, 4.0), (4.0, 5.0)]


def test_place_video_snaps_length_to_beats_and_stays_in_clip():
    shots, _ = place([video(dur=3.0, vin=1.0, vout=3.6)], BEATS, 3.0, 20.0, 2)
    s = shots[0]
    assert (s["start"], s["end"]) == (3.0, 5.5)            # 2.6초 → 5비트
    assert s["out"] - s["in"] == pytest.approx(2.5)
    assert s["out"] <= 3.0                                  # 원본 길이 안


def test_place_reports_leftover():
    shots, left = place([photo(i) for i in range(10)], BEATS, 3.0, 6.0, 2)
    assert len(shots) == 3 and left == 7


def test_fit_drops_evenly_keeping_first_and_last():
    items = [photo(i) for i in range(100)]
    shots, dropped = fit(items, BEATS, 3.0, 13.0, 2)
    assert len(shots) == 10 and dropped == 90
    assert shots[0]["src"] == "media/p0.jpg" and shots[-1]["src"] == "media/p99.jpg"


@pytest.mark.parametrize("fmt", ["reels", "youtube"])
def test_build_format_contiguous_on_beats_with_cards(fmt):
    items = [photo(i) for i in range(200)] + [video(live=True)]
    plan = build_format(fmt, items, MUSIC, CARDS)
    shots = plan["shots"]
    assert shots[0] == {"type": "clip", "src": "cards/i.mp4", "start": 0.0, "end": shots[1]["start"]}
    assert shots[1]["start"] <= INTRO_SECONDS
    assert shots[-1]["type"] == "clip" and shots[-1]["end"] - shots[-1]["start"] == pytest.approx(OUTRO_SECONDS)
    for a, b in zip(shots, shots[1:]):
        assert a["end"] == pytest.approx(b["start"])
    grid = {round(b - plan["musicStart"], 3) for b in BEATS}
    assert all(round(s["start"], 3) in grid for s in shots[1:-1])
    assert plan["musicEnd"] - plan["musicStart"] == pytest.approx(shots[-1]["end"])
    assert (plan["width"], plan["height"]) == (FORMATS[fmt]["width"], FORMATS[fmt]["height"])


def test_reels_uses_chorus_window():
    plan = build_format("reels", [photo(i) for i in range(200)], MUSIC, CARDS)
    assert plan["musicStart"] == 60.0 and plan["musicEnd"] <= 105.0


def test_too_few_items_ends_music_early():
    plan = build_format("youtube", [photo(0), photo(1)], MUSIC, CARDS)
    assert plan["musicEnd"] - plan["musicStart"] < 20.0
    assert plan["dropped"] == 0


def test_no_beats_raises_clear_error():
    with pytest.raises(ValueError, match="비트"):
        build_format("youtube", [photo(0)], dict(MUSIC, beats=[]), CARDS)


def test_ken_burns_alternates():
    plan = build_format("youtube", [photo(i) for i in range(4)], MUSIC, CARDS)
    assert [s["kenBurns"] for s in plan["shots"][1:-1]] == ["zoom-in", "pan-left", "zoom-out", "pan-right"]


CANDS = [
    {"type": "photo", "file": "media/a.jpg"},
    {"type": "video", "file": "media/v.mp4", "duration": 10.0, "has_audio": True},
    {"type": "video", "file": "media/mute.mp4", "duration": 5.0, "has_audio": False},
]
HL = {"media/v.mp4": {"suggested": {"in": 4.0, "out": 8.0, "liveAudio": True}},
      "media/mute.mp4": {"suggested": {"in": 0.0, "out": 4.0, "liveAudio": True}}}


def test_resolve_items_uses_suggestion_and_overrides():
    items = resolve_items({"items": [{"id": 0}, {"id": 1}, {"id": 1, "in": 1.0, "out": 2.0, "liveAudio": False}, {"id": 2}]}, CANDS, HL)
    assert items[0] == {"type": "photo", "src": "media/a.jpg"}
    assert (items[1]["in"], items[1]["out"], items[1]["liveAudio"]) == (4.0, 8.0, True)
    assert (items[2]["in"], items[2]["out"], items[2]["liveAudio"]) == (1.0, 2.0, False)
    assert items[3]["liveAudio"] is False  # 오디오 없는 영상은 현장 소리 불가


def test_resolve_items_rejects_bad_id_and_range():
    with pytest.raises(ValueError, match="후보 번호"):
        resolve_items({"items": [{"id": 9}]}, CANDS, HL)
    with pytest.raises(ValueError, match="영상 길이"):
        resolve_items({"items": [{"id": 1, "in": 8.0, "out": 12.0}]}, CANDS, HL)


def test_build_storyboard_rejects_unknown_format():
    with pytest.raises(ValueError, match="형식"):
        build_storyboard({"formats": ["tiktok"], "items": [{"id": 0}]}, CANDS, HL, MUSIC, "music/s.mp3", {})


def test_build_storyboard_shape():
    sel = {"title": "제주", "ending": "끝", "formats": ["youtube"], "items": [{"id": 0}, {"id": 1}]}
    sb = build_storyboard(sel, CANDS, HL, MUSIC, "music/s.mp3", {"youtube": CARDS})
    assert sb["fps"] == 30 and sb["music"] == "music/s.mp3" and list(sb["formats"]) == ["youtube"]
