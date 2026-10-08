"""공용/템플릿/<이름>/template.json — 여행처럼 반복되는 영상의 기본값을 selection 아래에 깐다 (selection이 우선)."""
import copy
import json
from pathlib import Path

from .paths import SHARED

TEMPLATES_DIR = SHARED / "템플릿"


def load(name: str, root: Path = TEMPLATES_DIR) -> dict:
    path = root / name / "template.json"
    if not path.exists():
        names = sorted(p.name for p in root.iterdir() if (p / "template.json").exists()) if root.exists() else []
        raise ValueError(f"템플릿 '{name}'이 없습니다 (가능: {', '.join(names) or '없음'})")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise ValueError(f"템플릿 파일을 읽을 수 없습니다 ({path}): {e}")


def apply(selection: dict, tpl: dict) -> dict:
    try:
        return _apply(selection, tpl)
    except (KeyError, AttributeError, TypeError, IndexError) as e:  # 손으로 고친 템플릿·selection의 형식 실수
        raise ValueError(f"템플릿 또는 selection 형식이 맞지 않습니다 ({type(e).__name__}: {e}) — "
                         f"공용/템플릿-예시/의 template.json 형식을 참고하세요")


def _apply(selection: dict, tpl: dict) -> dict:
    sel = copy.deepcopy(selection)
    if not sel.get("place") and "title" not in sel:
        raise ValueError('템플릿 타이틀에 place가 필요합니다 (예: "place": "제주")')
    team = tpl.get("team", {})
    sel.setdefault("title", tpl.get("title", "{place}").format(team=team.get("name", ""), place=sel.get("place", "")))
    sel.setdefault("ending", tpl.get("ending", ""))
    sel.setdefault("intro", tpl.get("card", "basic"))
    for key, val in (tpl.get("sound") or {}).items():
        sel.setdefault(key, val)
    if tpl.get("pace"):
        sel.setdefault("photoSeconds", dict(tpl["pace"]))
    fin = tpl.get("finale") or {}
    sel.setdefault("finaleBars", fin.get("barsAfterFinalChorus", 8))
    cred = tpl.get("credits") or {}
    mine = sel.get("credits") or {}
    if mine.get("video"):
        lines = mine.get("lines") or [cred.get("header", "")] + [f"{m['role']} {m['name']}" for m in team.get("members", [])]
        sel["credits"] = {"lines": [x for x in lines if x], "video": mine["video"],
                          "seconds": mine.get("seconds", cred.get("seconds", 12))}
    else:
        sel.pop("credits", None)  # 배경 영상이 없으면 크레딧을 만들 수 없다 (plan 출력에서 안내)
    opening = tpl.get("opening") or {}
    items, in_finale, content_seen = [], False, 0
    for it in sel.get("items", []):
        it = dict(it)
        if it.get("at") == "피날레":
            in_finale = True
            it.setdefault("photoBeats", fin.get("beatsPerPhoto", 3))
        elif "id" in it:
            if content_seen < opening.get("shots", 0) and opening.get("blur"):
                it.setdefault("blur", opening["blur"])
            if in_finale and fin.get("kenBurns"):
                it.setdefault("kenBurns", fin["kenBurns"])  # 영상 항목에 붙어도 plan은 영상의 kenBurns를 읽지 않는다
            content_seen += 1
        items.append(it)
    sel["items"] = items
    return sel
