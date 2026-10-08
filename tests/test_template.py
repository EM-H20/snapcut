import json

import pytest

from pipeline import template

# 템플릿 = 편집 문법만 (누구와·어떤 문구인지는 여행마다 selection에서)
TPL = {
    "card": "handwritten",
    "sound": {"liveAudio": False, "duck": False}, "pace": {"youtube": 2.0},
    "opening": {"blur": 0.6, "shots": 2},
    "finale": {"barsAfterFinalChorus": 8, "beatsPerPhoto": 3, "kenBurns": "still"},
    "credits": {"seconds": 12},
}


def test_load_reads_template_and_reports_missing(tmp_path):
    (tmp_path / "여행").mkdir()
    (tmp_path / "여행" / "template.json").write_text(json.dumps(TPL), encoding="utf-8")
    assert template.load("여행", tmp_path)["card"] == "handwritten"
    with pytest.raises(ValueError, match="여행"):
        template.load("여해", tmp_path)
    (tmp_path / "깨짐").mkdir()
    (tmp_path / "깨짐" / "template.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="template.json"):
        template.load("깨짐", tmp_path)


def test_apply_fills_editing_defaults_and_selection_wins():
    sel = {"template": "여행", "title": "2026 청년부 수련회", "liveAudio": True,
           "items": [{"id": 1}, {"id": 2, "blur": 0.2}, {"id": 3}, {"at": "피날레"}, {"id": 4}, {"id": 5, "kenBurns": "zoom-in"}]}
    before = json.dumps(sel, ensure_ascii=False)
    out = template.apply(sel, TPL)
    assert json.dumps(sel, ensure_ascii=False) == before                       # 원본 불변
    assert out["title"] == "2026 청년부 수련회" and "ending" not in out          # 문구는 템플릿이 정하지 않음
    assert out["intro"] == "handwritten" and out["liveAudio"] is True and out["duck"] is False   # selection 우선
    assert out["photoSeconds"] == {"youtube": 2.0} and out["finaleBars"] == 8
    it = out["items"]
    assert it[0]["blur"] == 0.6 and it[1]["blur"] == 0.2 and "blur" not in it[2]   # 오프닝 2개만, 지정값 유지
    assert it[3] == {"at": "피날레", "photoBeats": 3}
    assert it[4]["kenBurns"] == "still" and it[5]["kenBurns"] == "zoom-in"


def test_apply_credits_are_per_trip_with_template_seconds():
    lines = ["Special 땡스", "엄마", "아빠"]
    out = template.apply({"credits": {"lines": lines, "video": {"id": 1}}, "items": []}, TPL)
    assert out["credits"] == {"lines": lines, "video": {"id": 1}, "seconds": 12}
    assert "credits" not in template.apply({"items": []}, TPL)               # 크레딧은 넣을 때만


def test_apply_leaves_finale_bars_to_plan_when_template_omits_it():
    tpl = {k: v for k, v in TPL.items() if k != "finale"}
    assert "finaleBars" not in template.apply({"items": []}, tpl)


@pytest.mark.parametrize("bad_tpl", [[1, 2], dict(TPL, opening="블러"), dict(TPL, sound=["x"])])
def test_bad_template_is_a_korean_value_error(bad_tpl):
    with pytest.raises(ValueError, match="템플릿"):
        template.apply({"items": [{"id": 1}]}, bad_tpl)
