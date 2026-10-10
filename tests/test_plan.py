import pytest

from pipeline.plan import (CARD_SECONDS, OUTRO_DISSOLVE, OUTRO_FADE, group_photos, FORMATS, INTRO_SECONDS, MAX_PER_COLLAGE, OUTRO_SECONDS, build_format, build_storyboard,
                           card_video, fit, place, resolve_items, subsample)

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


def test_photo_beats_on_one_photo_overrides_pace():
    # 4컷처럼 오래 보여 줄 사진 한 장만 길게: "photoBeats": 6
    items = resolve_items({"items": [{"id": 0, "photoBeats": 6}, {"id": 0}]}, CANDS, HL)
    shots, _ = place(items, BEATS, 3.0, 20.0, 2)
    assert [(s["start"], s["end"]) for s in shots] == [(3.0, 6.0), (6.0, 7.0)]
    assert "photoBeats" not in shots[0]
    with pytest.raises(ValueError, match="photoBeats"):
        resolve_items({"items": [{"id": 0, "photoBeats": 0}]}, CANDS, HL)


def test_place_reports_leftover():
    shots, left = place([photo(i) for i in range(10)], BEATS, 3.0, 6.0, 2)
    assert len(shots) == 3 and left == 7


def srcs(shot):
    return shot.get("srcs") or [shot["src"]]


def test_fit_keeps_single_photos_when_there_is_room():
    shots, dropped = fit([photo(i) for i in range(5)], BEATS, 3.0, 13.0, 2)
    assert dropped == 0 and [s["type"] for s in shots] == ["photo"] * 5


def test_fit_packs_overflow_into_collages_instead_of_dropping():
    items = [photo(i) for i in range(18)]
    shots, dropped = fit(items, BEATS, 3.0, 13.0, 2)  # 10자리에 18장
    assert dropped == 0 and len(shots) == 10
    assert [src for s in shots for src in srcs(s)] == [it["src"] for it in items]  # 순서 유지, 전부 들어감
    assert all(len(srcs(s)) <= MAX_PER_COLLAGE for s in shots)


def test_fit_uses_as_few_collages_as_needed():
    shots, dropped = fit([photo(i) for i in range(12)], BEATS, 3.0, 13.0, 2)
    assert dropped == 0 and sorted(len(srcs(s)) for s in shots) == [1] * 8 + [2] * 2


def test_collage_never_spans_a_video():
    items = [photo(0), photo(1), video(dur=10.0, vin=0.0, vout=1.0), photo(2), photo(3)]
    shots, dropped = fit(items, BEATS, 3.0, 6.0, 2)  # 6비트: 영상 2 + 사진 묶음 2
    assert dropped == 0
    assert [srcs(s) if s["type"] != "video" else "v" for s in shots] == [
        ["media/p0.jpg", "media/p1.jpg"], "v", ["media/p2.jpg", "media/p3.jpg"]]


def test_fit_drops_evenly_keeping_first_and_last_when_even_collages_overflow():
    items = [photo(i) for i in range(100)]
    shots, dropped = fit(items, BEATS, 3.0, 13.0, 2)
    assert len(shots) == 10 and dropped == 100 - 10 * MAX_PER_COLLAGE
    assert srcs(shots[0])[0] == "media/p0.jpg" and srcs(shots[-1])[-1] == "media/p99.jpg"


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
    assert plan["musicEnd"] - plan["musicStart"] < INTRO_SECONDS + OUTRO_SECONDS + 6.0  # 곡 끝(120초)까지 끌지 않음
    assert plan["dropped"] == 0


def test_no_beats_raises_clear_error():
    with pytest.raises(ValueError, match="비트"):
        build_format("youtube", [photo(0)], dict(MUSIC, beats=[]), CARDS)


def test_photos_are_still_by_default():
    plan = build_format("youtube", [photo(i) for i in range(4)], MUSIC, CARDS)
    assert [s["kenBurns"] for s in plan["shots"][1:-1]] == ["still"] * 4


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


def test_late_first_beat_leaves_no_gap_after_intro():
    first = INTRO_SECONDS + 1.0  # 첫 비트가 인트로 길이보다 늦음
    late = dict(MUSIC, beats=[first + 0.5 * i for i in range(200)], downbeats=[])
    shots = build_format("youtube", [photo(i) for i in range(5)], late, CARDS)["shots"]
    assert shots[0]["end"] == shots[1]["start"] == first
    for a, b in zip(shots, shots[1:]):
        assert a["end"] == pytest.approx(b["start"])


def test_sub_beat_video_is_dropped_and_counted():
    items = [photo(0), video(dur=0.3, vin=0.0, vout=0.3), photo(1)]
    plan = build_format("youtube", items, MUSIC, CARDS)
    assert not [s for s in plan["shots"] if s["type"] == "video"]
    assert plan["dropped"] == 1


@pytest.mark.parametrize("sel", [{"items": 3}, {"items": [1, 2]}, {"items": "x"}])
def test_resolve_items_rejects_malformed_items(sel):
    with pytest.raises(ValueError, match="items"):
        resolve_items(sel, CANDS, HL)


@pytest.mark.parametrize("formats", ["reels", [1], [["reels"]], {"reels": 1}])
def test_build_storyboard_rejects_malformed_formats(formats):
    with pytest.raises(ValueError, match="formats"):
        build_storyboard({"formats": formats, "items": [{"id": 0}]}, CANDS, HL, MUSIC, "music/s.mp3", {})


def test_card_video_optional_and_validated():
    cands = [CANDS[0], dict(CANDS[1], duration=CARD_SECONDS + 4.0)]
    assert card_video({}, "introVideo", cands) is None
    assert card_video({"introVideo": {"id": 1, "in": 2.0}}, "introVideo", cands) == ("media/v.mp4", 2.0)
    assert card_video({"outroVideo": {"id": 0}}, "outroVideo", cands) == ("media/a.jpg", 0.0)  # 사진 배경도 가능
    with pytest.raises(ValueError, match="introVideo"):
        card_video({"introVideo": {"id": 99}}, "introVideo", cands)  # 없는 번호
    with pytest.raises(ValueError, match="outroVideo"):
        card_video({"outroVideo": {"id": 1, "in": 8.0}}, "outroVideo", cands)  # 카드 길이가 영상 밖


def test_photo_length_is_seconds_not_beats_so_fast_songs_dont_rush():
    fast = dict(MUSIC, beats=[round(i * 0.35, 3) for i in range(340)])  # 171 BPM
    shots = build_format("youtube", [photo(i) for i in range(5)], fast, CARDS)["shots"]
    assert shots[1]["end"] - shots[1]["start"] == pytest.approx(2.1)  # 2초 → 6비트


def test_photo_seconds_override_and_validation():
    shots = build_format("youtube", [photo(i) for i in range(5)], MUSIC, CARDS, photo_seconds=3.0)["shots"]
    assert shots[1]["end"] - shots[1]["start"] == pytest.approx(3.0)
    sel = {"formats": ["youtube"], "photoSeconds": {"youtube": 3.0}, "items": [{"id": 0}]}
    sb = build_storyboard(sel, CANDS, HL, MUSIC, "music/s.mp3", {"youtube": CARDS})
    s = sb["formats"]["youtube"]["shots"][1]
    assert s["end"] - s["start"] == pytest.approx(3.0)
    with pytest.raises(ValueError, match="photoSeconds"):
        build_storyboard(dict(sel, photoSeconds={"youtube": 0}), CANDS, HL, MUSIC, "music/s.mp3", {"youtube": CARDS})


def test_reels_never_splits_the_screen():
    plan = build_format("reels", [photo(i) for i in range(200)], MUSIC, CARDS)
    assert not [s for s in plan["shots"] if s["type"] == "collage"]


def mark(t):
    return {"type": "mark", "at": t}


def contiguous(shots):
    return all(a["end"] == pytest.approx(b["start"]) for a, b in zip(shots, shots[1:]))


def test_mark_anchors_next_item_and_stretches_previous_photo():
    items = [photo(0), photo(1), mark(20.2), photo(2)]  # 20.2는 비트가 아님
    shots = build_format("youtube", items, MUSIC, CARDS)["shots"]
    assert [s["src"] for s in shots[1:-1]] == ["media/p0.jpg", "media/p1.jpg", "media/p2.jpg"]
    assert shots[3]["start"] == 20.2 and shots[2]["end"] == 20.2
    assert contiguous(shots)


def test_marks_make_beat_hit_bursts():
    hits = [30.1, 30.45, 30.8, 30.97]
    items = [photo(0), mark(hits[0]), photo(1), mark(hits[1]), photo(2), mark(hits[2]), photo(3), mark(hits[3]), photo(4)]
    shots = build_format("youtube", items, MUSIC, CARDS)["shots"][1:-1]
    assert [(s["start"], s["end"]) for s in shots[1:4]] == [(30.1, 30.45), (30.45, 30.8), (30.8, 30.97)]
    assert contiguous(shots)


def test_mark_outside_window_is_ignored():
    plan = build_format("reels", [photo(0), mark(10.0), photo(1)], MUSIC, CARDS)  # 릴스는 60~105초 구간
    assert [s["src"] for s in plan["shots"][1:-1]] == ["media/p0.jpg", "media/p1.jpg"] and contiguous(plan["shots"])


def test_solo_photo_is_never_collaged():
    items = [photo(i) for i in range(12)]
    items[3] = dict(items[3], solo=True)
    items[4] = dict(items[4], solo=True)
    shots, _ = fit(items, BEATS, 3.0, 13.0, 2)
    assert not [s for s in shots if s["type"] == "collage" and ({"media/p3.jpg", "media/p4.jpg"} & set(s["srcs"]))]
    assert not any("solo" in s for s in shots)


def test_resolve_items_marks_and_solo():
    items = resolve_items({"items": [{"at": 12.5}, {"id": 0, "solo": True}]}, CANDS, HL)
    assert items == [{"type": "mark", "at": 12.5}, {"type": "photo", "src": "media/a.jpg", "solo": True}]
    with pytest.raises(ValueError, match="at"):
        resolve_items({"items": [{"at": [1]}]}, CANDS, HL)   # 문자열은 이제 구간 이름 (test_unknown_section_name_is_an_error)


def test_rotate_passes_through_to_video_shot_and_is_validated():
    items = resolve_items({"items": [{"id": 1, "rotate": -90}]}, CANDS, HL)
    shots, _ = place(items, BEATS, 3.0, 20.0, 2)
    assert shots[0]["rotate"] == -90
    assert "rotate" not in place(resolve_items({"items": [{"id": 1}]}, CANDS, HL), BEATS, 3.0, 20.0, 2)[0][0]
    with pytest.raises(ValueError, match="rotate"):
        resolve_items({"items": [{"id": 1, "rotate": 45}]}, CANDS, HL)



def test_photo_ken_burns_override_for_match_cut_into_video():
    # 사진 → 같은 장면 영상으로 이어 붙일 때: zoom-out은 원래 크기(1.0)로 끝나 영상 첫 프레임과 구도가 같다
    items = resolve_items({"items": [{"id": 0, "kenBurns": "zoom-out"}, {"id": 0}]}, CANDS, HL)
    shots, _ = place(items, BEATS, 3.0, 20.0, 2)
    assert shots[0]["kenBurns"] == "zoom-out"
    assert shots[1]["kenBurns"] == "still"  # 지정 안 한 사진은 순서대로 돌아간다
    tall = resolve_items({"items": [{"id": 0, "kenBurns": "scroll-down"}]}, CANDS, HL)  # 4컷 사진: 위→아래로 훑기
    assert place(tall, BEATS, 3.0, 20.0, 2)[0][0]["kenBurns"] == "scroll-down"
    with pytest.raises(ValueError, match="kenBurns"):
        resolve_items({"items": [{"id": 0, "kenBurns": "spin"}]}, CANDS, HL)


def test_dissolve_passes_through_and_is_validated():
    items = resolve_items({"items": [{"id": 0}, {"id": 1, "dissolve": 0.4}]}, CANDS, HL)
    shots, _ = place(items, BEATS, 3.0, 20.0, 2)
    assert "dissolve" not in shots[0] and shots[1]["dissolve"] == 0.4
    for bad in (0, -1, 1.5, "x"):
        with pytest.raises(ValueError, match="dissolve"):
            resolve_items({"items": [{"id": 1, "dissolve": bad}]}, CANDS, HL)


def test_duck_false_passes_through_and_is_validated():
    items = resolve_items({"items": [{"id": 1, "liveAudio": True, "duck": False}, {"id": 1}]}, CANDS, HL)
    shots, _ = place(items, BEATS, 3.0, 20.0, 2)
    assert shots[0]["duck"] is False and "duck" not in shots[1]
    with pytest.raises(ValueError, match="duck"):
        resolve_items({"items": [{"id": 1, "duck": "no"}]}, CANDS, HL)


def test_selection_level_duck_false_applies_to_every_video():
    items = resolve_items({"duck": False, "items": [{"id": 1, "liveAudio": True}, {"id": 1, "duck": True}]}, CANDS, HL)
    assert items[0]["duck"] is False and "duck" not in items[1]  # 항목별 지정이 우선


def test_video_squeezed_to_under_half_at_segment_end_counts_as_not_fitting():
    # 구간 끝에서 영상이 원래 길이의 절반도 안 남으면 잘라 넣지 않고 '자리 없음'으로 알린다 (0.3초 번쩍 방지)
    items = [photo(0), photo(1), video(dur=10.0, vin=0.0, vout=2.5)]   # 사진 2비트씩 = 2초, 영상 5비트
    shots, left = place(items, BEATS, 3.0, 5.5, 2)                       # 2.5초 창: 영상엔 1비트만 남음
    assert left == 1 and [s["type"] for s in shots] == ["photo", "photo"]
    shots, left = place(items, BEATS, 3.0, 6.5, 2)                       # 3비트 남음(절반 이상) → 넣는다
    assert left == 0 and shots[-1]["type"] == "video"


def test_still_photo_has_no_ken_burns_motion():
    items = resolve_items({"items": [{"id": 0, "kenBurns": "still"}, {"id": 0}]}, CANDS, HL)
    shots, _ = place(items, BEATS, 3.0, 20.0, 2)
    assert shots[0]["kenBurns"] == "still" and shots[1]["kenBurns"] == "still"


def test_mark_photo_seconds_sets_pace_for_its_segment_only():
    # 피날레처럼 한 구간만 사진을 빠르게: {"at": t, "photoSeconds": s}
    items = [photo(0), photo(1), {"type": "mark", "at": 30.0, "photoSeconds": 1.0}] + [photo(i) for i in range(2, 8)]
    shots = build_format("youtube", items, MUSIC, CARDS)["shots"][1:-1]
    before, after = [s for s in shots if s["start"] < 30.0], [s for s in shots if s["start"] >= 30.0]
    assert all(s["end"] - s["start"] == pytest.approx(1.0) for s in after)
    assert before[0]["end"] - before[0]["start"] == pytest.approx(2.0)  # 앞 구간은 기본 2초


def test_youtube_never_splits_the_screen():
    plan = build_format("youtube", [photo(i) for i in range(400)], MUSIC, CARDS)
    assert not [s for s in plan["shots"] if s["type"] == "collage"]


CREDITS = {"lines": ["Special 땡스", "운전 OO"], "video": {"id": 1, "in": 1.0}, "seconds": 6}


def test_credits_follow_the_outro_on_youtube_and_music_fades_before_them():
    sel = {"formats": ["youtube", "reels"], "credits": CREDITS, "items": [{"id": 0}, {"id": 1}]}
    sb = build_storyboard(sel, CANDS, HL, MUSIC, "music/s.mp3", {"youtube": CARDS, "reels": CARDS})
    yt = sb["formats"]["youtube"]
    outro, credits = yt["shots"][-2], yt["shots"][-1]
    assert outro["type"] == "clip" and credits["type"] == "credits"
    assert credits["start"] == outro["end"] and credits["end"] - credits["start"] == pytest.approx(6)
    assert credits["lines"] == CREDITS["lines"] and credits["src"] == "media/v.mp4" and credits["in"] == 1.0
    assert yt["musicFadeEnd"] == pytest.approx(credits["start"])          # 음악은 크레딧 전에 끝난다
    assert yt["musicEnd"] - yt["musicStart"] == pytest.approx(credits["end"])
    assert sb["formats"]["reels"]["shots"][-1]["type"] == "clip"           # 릴스엔 크레딧 없음


@pytest.mark.parametrize("bad", [{"lines": [], "video": {"id": 1}}, {"lines": ["a"], "video": {"id": 0}},
                                 {"lines": ["a"], "video": {"id": 1, "in": 9.0}, "seconds": 6}, "x"])
def test_credits_are_validated(bad):
    with pytest.raises(ValueError, match="credits"):
        build_storyboard({"formats": ["youtube"], "credits": bad, "items": [{"id": 0}]}, CANDS, HL, MUSIC, "m", {"youtube": CARDS})



def test_selection_level_live_audio_default():
    hl_off = {"media/v.mp4": {"suggested": {"in": 4.0, "out": 8.0, "liveAudio": False}},
              "media/mute.mp4": {"suggested": {"in": 0.0, "out": 4.0, "liveAudio": False}}}
    assert resolve_items({"items": [{"id": 1}]}, CANDS, hl_off)[0]["liveAudio"] is False   # 기본은 제안값
    items = resolve_items({"liveAudio": True, "items": [{"id": 2}, {"id": 1}, {"id": 1, "liveAudio": False}]}, CANDS, hl_off)
    assert items[0]["liveAudio"] is False      # 소리 없는 영상은 여전히 불가
    assert items[1]["liveAudio"] is True and items[2]["liveAudio"] is False   # 최상위 기본값, 항목별 지정이 우선



def test_outro_card_fades_to_black_at_its_end():
    shots = build_format("youtube", [photo(i) for i in range(5)], MUSIC, CARDS)["shots"]
    assert shots[-1]["type"] == "clip" and shots[-1]["fadeOut"] == OUTRO_FADE
    assert "fadeOut" not in shots[0]   # 인트로는 페이드아웃 없음
    assert "dissolve" not in shots[-1]  # 마지막 영상이 검게 사라질 때만 카드가 검은 화면에서 떠오른다


def test_video_fade_out_makes_outro_rise_from_black():
    items = resolve_items({"items": [{"id": 0}, {"id": 1, "in": 1.0, "out": 3.0, "fadeOut": 1.2}]}, CANDS, HL)
    shots = build_format("youtube", items, MUSIC, CARDS)["shots"]
    assert shots[-2]["fadeOut"] == 1.2 and shots[-1]["dissolve"] == OUTRO_DISSOLVE
    with pytest.raises(ValueError, match="fadeOut"):
        resolve_items({"items": [{"id": 1, "fadeOut": 5}]}, CANDS, HL)


def test_beatless_song_tail_still_holds_shots():
    # 곡 끝 페이드 구간엔 비트가 안 잡힌다 — 마지막 비트 간격으로 격자를 이어서 그 시간도 쓴다
    tail = dict(MUSIC, beats=[b for b in BEATS if b <= 60.0 - OUTRO_SECONDS - 7.0], duration=60.0)
    shots = build_format("youtube", [photo(i) for i in range(40)], tail, CARDS)["shots"]
    content_end = shots[-1]["start"]          # 아웃트로 시작 = 본편 끝
    assert content_end > 60.0 - OUTRO_SECONDS - 5.0  # 마지막 비트에서 멈추지 않고 꼬리까지 채움
    assert content_end <= 60.0 - OUTRO_SECONDS + 1e-6


def test_blur_transition_passes_through_and_is_validated():
    items = resolve_items({"items": [{"id": 0, "blur": 0.6}, {"id": 1, "blur": 0.6}, {"id": 0}]}, CANDS, HL)
    shots, _ = place(items, BEATS, 3.0, 20.0, 2)
    assert shots[0]["blur"] == 0.6 and shots[1]["blur"] == 0.6 and "blur" not in shots[2]
    for bad in (0, -1, 2.0, "x"):
        with pytest.raises(ValueError, match="blur"):
            resolve_items({"items": [{"id": 1, "blur": bad}]}, CANDS, HL)


SECT = dict(MUSIC, downbeats=BEATS[::4],
            sections={"브릿지": 40.0, "브레이크": 70.0, "마지막후렴": 80.0, "estimated": []})


def test_named_marks_become_seconds_and_finale_is_bars_after_final_chorus():
    sel = {"formats": ["youtube"], "items": [{"id": 0}, {"at": "브릿지"}, {"id": 0}, {"at": "피날레", "photoBeats": 3}, {"id": 0}, {"id": 0}]}
    sb = build_storyboard(sel, CANDS, HL, SECT, "m", {"youtube": CARDS})
    sh = sb["formats"]["youtube"]["shots"][1:-1]
    assert sh[1]["start"] == 40.0
    assert sh[2]["start"] == 96.0                       # 마지막후렴 80 + 8마디(2초) = 96
    assert sh[2]["end"] - sh[2]["start"] == pytest.approx(1.5)   # 3비트 × 0.5초
    assert sb["sections"]["피날레"] == 96.0 and sb["sections"]["ignored"] == []


def test_unknown_section_name_is_an_error():
    with pytest.raises(ValueError, match="구간"):
        resolve_items({"items": [{"at": "간주"}]}, CANDS, HL)


def test_finale_past_song_end_is_ignored_and_reported():
    short = dict(SECT, sections={"브릿지": None, "브레이크": 100.0, "마지막후렴": 115.0, "estimated": []})
    sel = {"formats": ["youtube"], "items": [{"id": 0}, {"at": "브릿지"}, {"id": 0}, {"at": "피날레"}, {"id": 0}]}
    sb = build_storyboard(sel, CANDS, HL, short, "m", {"youtube": CARDS})
    sh = sb["formats"]["youtube"]["shots"]
    assert all(a["end"] == pytest.approx(b["start"]) for a, b in zip(sh, sh[1:]))   # 빈틈 없음
    assert set(sb["sections"]["ignored"]) == {"브릿지", "피날레"}


def test_named_marks_ignored_by_reels_window():
    sel = {"formats": ["reels"], "items": [{"id": 0}, {"at": "브릿지"}, {"id": 0}]}
    sb = build_storyboard(sel, CANDS, HL, SECT, "m", {"reels": CARDS})   # 릴스 구간 60~105초 밖의 40초
    assert sb["formats"]["reels"]["shots"]


def test_photo_beats_mark_sets_segment_pace():
    items = [photo(0), {"type": "mark", "at": 30.0, "photoBeats": 3}] + [photo(i) for i in range(1, 5)]
    shots = build_format("youtube", items, MUSIC, CARDS)["shots"][1:-1]
    after = [s for s in shots if s["start"] >= 30.0]
    assert after and all(s["end"] - s["start"] == pytest.approx(1.5) for s in after[:-1])  # 기본 2초와 구별되는 3비트


def test_out_of_order_named_marks_are_reported_not_silently_dropped():
    # 추정값끼리 순서가 뒤집히면(브릿지 120 > 브레이크 100) 뒤 마커는 놓을 수 없다 — 무시하되 보고한다
    odd = dict(SECT, sections={"브릿지": 100.0, "브레이크": 90.0, "마지막후렴": 95.0, "estimated": ["브릿지"]})
    sel = {"formats": ["youtube"], "items": [{"id": 0}, {"at": "브릿지"}, {"id": 0}, {"at": "브레이크"}, {"id": 0},
                                           {"at": "마지막후렴"}, {"id": 0}]}
    sb = build_storyboard(sel, CANDS, HL, odd, "m", {"youtube": CARDS})
    assert set(sb["sections"]["ignored"]) == {"브레이크", "마지막후렴"}


def test_selection_sections_override_estimates_and_moves_finale():
    est = dict(SECT, sections={"브릿지": 40.0, "브레이크": 70.0, "마지막후렴": 80.0, "estimated": ["마지막후렴", "브레이크"]})
    sel = {"formats": ["youtube"], "sections": {"마지막후렴": 60.0},
           "items": [{"id": 0}, {"at": "마지막후렴"}, {"id": 0}, {"at": "피날레"}, {"id": 0}]}
    sec = build_storyboard(sel, CANDS, HL, est, "m", {"youtube": CARDS})["sections"]
    assert sec["마지막후렴"] == 60.0 and sec["피날레"] == 76.0          # 고친 후렴 + 8마디(2초)
    assert "마지막후렴" not in sec["estimated"] and "피날레" not in sec["estimated"]
    plain = build_storyboard(dict(sel, sections={}), CANDS, HL, est, "m", {"youtube": CARDS})["sections"]
    assert "피날레" in plain["estimated"]                                   # 추정 후렴에서 나온 피날레도 추정
    with pytest.raises(ValueError, match="sections"):
        build_storyboard(dict(sel, sections={"간주": 10.0}), CANDS, HL, est, "m", {"youtube": CARDS})


def test_group_photos_splits_runs_and_breaks_on_other_items():
    pic = lambda n, **kw: {"type": "photo", "src": f"p{n}.jpg", "portrait": True, **kw}
    wide = {"type": "photo", "src": "w.jpg"}  # 가로 사진은 혼자 크게
    out = group_photos([pic(0), pic(1), pic(2), pic(3), pic(4, kenBurns="still"), video(), pic(5), pic(6), pic(7, solo=True),
                        pic(8), wide, pic(9)], 3)
    assert [len(it.get("srcs", [0])) for it in out] == [2, 2, 1, 1, 2, 1, 1, 1, 1]  # 4장 → 2+2, still·영상·solo·가로에서 끊김
    assert out[0]["type"] == "collage" and out[0]["span"] == 2


def test_photo_group_gives_collage_two_photo_slots():
    tall = [dict(photo(i), portrait=True) for i in range(3)]
    plan = build_format("youtube", tall, MUSIC, CARDS, photo_group=3)
    shot = plan["shots"][1]
    assert shot["type"] == "collage" and len(shot["srcs"]) == 3 and "span" not in shot and "portrait" not in shot
    solo = build_format("youtube", [photo(0), photo(1), photo(2)], MUSIC, CARDS)["shots"][1]
    assert shot["end"] - shot["start"] == pytest.approx(2 * (solo["end"] - solo["start"]))


def test_duck_level_is_passed_through_and_validated():
    items = resolve_items({"items": [{"id": 1, "duck": 0.6}, {"id": 1}, {"id": 1, "duck": False}], "duck": True}, CANDS, HL)
    assert items[0]["duck"] == 0.6 and "duck" not in items[1] and items[2]["duck"] is False
    for bad in (0, 1, 1.5, -0.2, "x"):
        with pytest.raises(ValueError, match="duck"):
            resolve_items({"items": [{"id": 1, "duck": bad}]}, CANDS, HL)


def test_duck_fade_is_passed_through_and_validated():
    items = resolve_items({"items": [{"id": 1, "duckFade": 2.0}, {"id": 1}]}, CANDS, HL)
    assert items[0]["duckFade"] == 2.0 and "duckFade" not in items[1]
    for bad in (0, 0.05, 5, True, "x"):
        with pytest.raises(ValueError, match="duckFade"):
            resolve_items({"items": [{"id": 1, "duckFade": bad}]}, CANDS, HL)


def test_explicit_ids_make_one_split_screen_and_are_validated():
    cands = [{"type": "photo", "file": f"media/{n}.jpg"} for n in "abc"] + [CANDS[1]]
    items = resolve_items({"items": [{"ids": [2, 0], "kenBurns": "still"}]}, cands, HL)
    assert items == [{"type": "collage", "srcs": ["media/c.jpg", "media/a.jpg"], "span": 2, "kenBurns": "still"}]
    for bad in ([0], [0, 1, 2, 0], [0, 3], [0, 9], "ab"):
        with pytest.raises(ValueError, match="ids"):
            resolve_items({"items": [{"ids": bad}]}, cands, HL)


def test_outro_dissolve_crossfades_last_scene_into_card():
    shots = build_format("youtube", [photo(i) for i in range(4)], MUSIC, CARDS, outro_dissolve=1.5)["shots"]
    assert shots[-1]["dissolve"] == 1.5
    assert "dissolve" not in build_format("youtube", [photo(i) for i in range(4)], MUSIC, CARDS)["shots"][-1]
