import json

import pytest

from pipeline import template

TPL = {
    "team": {"name": "팀", "members": [{"name": "가", "role": "사장"}, {"name": "나", "role": "인턴"}]},
    "title": "{team} in {place}", "ending": "다음 행선지는 어디?", "card": "handwritten",
    "sound": {"liveAudio": False, "duck": False}, "pace": {"youtube": 2.0},
    "opening": {"blur": 0.6, "shots": 2},
    "finale": {"barsAfterFinalChorus": 8, "beatsPerPhoto": 3, "kenBurns": "still"},
    "credits": {"header": "Special 땡스", "seconds": 12},
}


def test_load_reads_template_and_reports_missing(tmp_path):
    (tmp_path / "여행").mkdir()
    (tmp_path / "여행" / "template.json").write_text(json.dumps(TPL), encoding="utf-8")
    assert template.load("여행", tmp_path)["title"] == "{team} in {place}"
    with pytest.raises(ValueError, match="여행"):
        template.load("여해", tmp_path)
    (tmp_path / "깨짐").mkdir()
    (tmp_path / "깨짐" / "template.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="template.json"):
        template.load("깨짐", tmp_path)


def test_apply_fills_defaults_and_selection_wins():
    sel = {"template": "여행", "place": "제주", "ending": "또 가자",
           "credits": {"video": {"id": 5, "in": 0.0}},
           "items": [{"id": 1}, {"id": 2, "blur": 0.2}, {"id": 3}, {"at": "피날레"}, {"id": 4}, {"id": 5, "kenBurns": "zoom-in"}]}
    before = json.dumps(sel, ensure_ascii=False)
    out = template.apply(sel, TPL)
    assert json.dumps(sel, ensure_ascii=False) == before                       # 원본 불변
    assert out["title"] == "팀 in 제주" and out["ending"] == "또 가자"           # selection 우선
    assert out["intro"] == "handwritten" and out["liveAudio"] is False and out["duck"] is False
    assert out["photoSeconds"] == {"youtube": 2.0} and out["finaleBars"] == 8
    assert out["credits"]["lines"] == ["Special 땡스", "사장 가", "인턴 나"] and out["credits"]["seconds"] == 12
    assert out["credits"]["video"] == {"id": 5, "in": 0.0}
    it = out["items"]
    assert it[0]["blur"] == 0.6 and it[1]["blur"] == 0.2 and "blur" not in it[2]   # 오프닝 2개만, 지정값 유지
    assert it[3] == {"at": "피날레", "photoBeats": 3}
    assert it[4]["kenBurns"] == "still" and it[5]["kenBurns"] == "zoom-in"


def test_apply_selection_credits_lines_replace_whole_list():
    out = template.apply({"place": "x", "credits": {"lines": ["감사합니다"], "video": {"id": 1}}, "items": []}, TPL)
    assert out["credits"]["lines"] == ["감사합니다"]


def test_apply_without_place_is_an_error():
    with pytest.raises(ValueError, match="place"):
        template.apply({"items": []}, TPL)


def test_apply_without_credits_video_drops_credits():
    assert "credits" not in template.apply({"place": "x", "items": []}, TPL)


@pytest.mark.parametrize("bad_tpl, bad_sel", [
    (dict(TPL, team={"name": "팀", "members": [{"name": "가"}]}), {"place": "x", "credits": {"video": {"id": 1}}, "items": []}),
    (dict(TPL, title="{팀} in {place}"), {"place": "x", "items": []}),
    (TPL, {"place": "x", "credits": "영상", "items": []}),
    ([1, 2], {"place": "x", "items": []}),
])
def test_bad_template_or_selection_is_a_korean_value_error(bad_tpl, bad_sel):
    with pytest.raises(ValueError, match="템플릿"):
        template.apply(bad_sel, bad_tpl)
