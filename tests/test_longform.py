import json

import pytest

from pipeline import longform
from pipeline.whisper import REPETITION_PLACEHOLDER


def seg(a, b, text="말"):
    return {"start": a, "end": b, "text": text}


SEGS = [seg(1.0, 3.0, "가"), seg(3.5, 6.0, "나"), seg(10.0, 12.0, "다")]


def test_snap_moves_boundaries_inside_a_sentence_outward_with_pad():
    assert longform.snap(2.0, 5.0, SEGS, 20.0) == (0.7, 6.3, 0.0)


def test_snap_leaves_boundaries_in_silence():
    assert longform.snap(3.2, 8.0, SEGS, 20.0) == (3.2, 8.0, 0.0)


def test_snap_pad_stops_at_the_neighbouring_sentence():
    segs = [seg(1.0, 3.0), seg(3.05, 5.0)]
    a, b, _ = longform.snap(0.5, 2.0, segs, 20.0)
    assert (a, b) == (0.5, 3.05)


def test_snap_never_cuts_into_overlapping_segment():
    segs = [seg(0.0, 5.0), seg(4.8, 9.0)]  # whisper 시각이 겹침
    a, _, _ = longform.snap(6.0, 9.5, segs, 20.0)
    assert a == 4.8  # 앞 문장 끝(5.0)이 아니라 이 문장 시작
    _, b, _ = longform.snap(1.0, 4.9, segs, 20.0)
    assert b == 5.0


def test_snap_refuses_large_growth():
    a, b, grew = longform.snap(20.0, 25.0, [seg(0.0, 30.0)], 40.0)
    assert (a, b) == (20.0, 25.0) and grew == pytest.approx(25.3)


def test_pieces_split_on_spaces_within_limit():
    assert longform.pieces("가나다 라마바 사아자 차카타", 10) == ["가나다 라마바", "사아자 차카타"]


def test_long_word_is_hard_split():
    assert longform.pieces("ㅋ" * 25, 10) == ["ㅋ" * 10, "ㅋ" * 10, "ㅋ" * 5]
    assert longform.pieces("ㅋ" * 20, 10) == ["ㅋ" * 10, "ㅋ" * 10]  # 딱 나눠떨어져도 빈 조각 없음
    assert longform.pieces("   ", 10) == []


CLIPS = [{"in": 10.0, "out": 14.0, "start": 0.0, "end": 4.0}, {"in": 30.0, "out": 33.0, "start": 4.0, "end": 7.0}]


def test_captions_are_remapped_and_clipped_to_each_clip():
    segs = [seg(12.0, 16.0, "첫 클립 끝에 걸침"), seg(29.0, 31.0, "둘째 클립 시작에 걸침"),
            seg(13.9, 14.1, "거의 안 보임"), seg(20.0, 22.0, "클립 밖")]
    assert longform.captions(CLIPS, segs, {}, 44) == [
        {"start": 2.0, "end": 4.0, "text": "첫 클립 끝에 걸침"},
        {"start": 4.0, "end": 5.0, "text": "둘째 클립 시작에 걸침"},
    ]


def test_captions_apply_fixes_split_by_chars_and_skip_placeholders():
    segs = [seg(10.0, 14.0, "바로 스틸 각 잡자 지금 바로 스틸"), seg(30.0, 32.0, REPETITION_PLACEHOLDER + "반복")]
    caps = longform.captions(CLIPS, segs, {"바로 스틸": "바론 스틸"}, 10)
    assert [c["text"] for c in caps] == ["바론 스틸 각 잡자", "지금 바론 스틸"]  # 10자는 한도 안
    assert caps[0]["start"] == 0.0 and caps[-1]["end"] == 4.0
    assert all(c["end"] > c["start"] for c in caps)


def write_spec(tmp_path, spec):
    p = tmp_path / "longform.json"
    p.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    return p


def test_load_spec_defaults_and_errors(tmp_path):
    spec = longform.load_spec(write_spec(tmp_path, {"clips": [{"in": 1, "out": 2}]}))
    assert spec["formats"] == list(longform.FORMATS) and spec["fixes"] == {}
    for bad, msg in [({}, "clips"), ({"clips": [{"in": 5, "out": 2}]}, "1번"),
                     ({"clips": [{"in": "a", "out": 2}]}, "숫자"),
                     ({"clips": [{"in": 1, "out": 2}], "formats": ["tiktok"]}, "formats"),
                     ({"clips": [{"in": 1, "out": 2}], "formats": "longform"}, "formats"),
                     ({"clips": [{"in": 1, "out": 2}], "fixes": ["x"]}, "fixes")]:
        with pytest.raises(ValueError, match=msg):
            longform.load_spec(write_spec(tmp_path, bad))
    (tmp_path / "longform.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON"):
        longform.load_spec(tmp_path / "longform.json")


TRANSCRIPT = {"duration": 60.0, "segments": [seg(1.0, 3.0, "첫 문장"), seg(20.0, 23.0, "둘째 문장"),
                                             seg(40.0, 41.0, REPETITION_PLACEHOLDER + "반복")]}


def test_build_storyboard_times_and_warnings():
    spec = {"clips": [{"in": 2.0, "out": 5.0, "title": "시작"}, {"in": 21.0, "out": 25.0}],
            "fixes": {}, "formats": ["longform"]}
    sb, warnings = longform.build(spec, TRANSCRIPT, "src/game.mkv")
    p = sb["formats"]["longform"]
    assert sb["mode"] == "longform" and sb["src"] == "src/game.mkv" and (p["width"], p["height"]) == (1920, 1080)
    assert p["clips"] == [{"in": 0.7, "out": 5.0, "start": 0.0, "end": 4.3, "title": "시작"},
                          {"in": 19.7, "out": 25.0, "start": 4.3, "end": 9.6, "title": ""}]
    assert p["duration"] == 9.6
    assert p["captions"][0] == {"start": 0.3, "end": 2.3, "text": "첫 문장"}
    assert any("반복" in w for w in warnings)


def test_snap_overlap_is_clamped_but_real_overlap_errors():
    spec = {"clips": [{"in": 18.0, "out": 21.0}, {"in": 22.0, "out": 30.0}], "fixes": {}, "formats": ["longform"]}
    sb, _ = longform.build(spec, TRANSCRIPT, "src/g.mkv")
    a, b = sb["formats"]["longform"]["clips"]
    assert a["out"] == 23.3 and b["in"] == 23.3  # 둘 다 "둘째 문장"으로 스냅 → 겹침 대신 이어 붙임
    spec["clips"] = [{"in": 30.0, "out": 35.0}, {"in": 10.0, "out": 12.0}]
    with pytest.raises(ValueError, match="1번과 2번"):
        longform.build(spec, TRANSCRIPT, "src/g.mkv")


def test_clip_beyond_duration_errors():
    spec = {"clips": [{"in": 50.0, "out": 70.0}], "fixes": {}, "formats": ["longform"]}
    with pytest.raises(ValueError, match="영상 길이"):
        longform.build(spec, TRANSCRIPT, "src/g.mkv")


def test_srt_format():
    caps = [{"start": 0.3, "end": 2.3, "text": "첫 문장"}, {"start": 3661.5, "end": 3662.0, "text": "끝"}]
    assert longform.srt(caps) == ("1\n00:00:00,300 --> 00:00:02,300\n첫 문장\n\n"
                                  "2\n01:01:01,500 --> 01:01:02,000\n끝\n")
