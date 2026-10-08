"""공용/템플릿/<이름>/template.json — 편집 문법(카드·소리·속도·전환·피날레) 기본값을 selection 아래에 깐다 (selection이 우선).
누구와 갔는지·문구는 템플릿이 아니라 여행마다 정한다 (친구 여행, 수련회, 가족 여행 모두 같은 템플릿)."""
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
                         f"공용/템플릿/여행/template.json 형식을 참고하세요")


def _apply(selection: dict, tpl: dict) -> dict:
    """템플릿은 편집 문법만 정한다. 타이틀·엔딩·크레딧 줄처럼 '누구와, 어떤 자리인지'는 여행마다 selection이 정한다."""
    sel = copy.deepcopy(selection)
    sel.setdefault("intro", tpl.get("card", "basic"))
    for key, val in (tpl.get("sound") or {}).items():
        sel.setdefault(key, val)
    if tpl.get("pace"):
        sel.setdefault("photoSeconds", dict(tpl["pace"]))
    fin = tpl.get("finale") or {}
    if "barsAfterFinalChorus" in fin:  # 없으면 plan의 기본값(FINALE_BARS)
        sel.setdefault("finaleBars", fin["barsAfterFinalChorus"])
    if isinstance(sel.get("credits"), dict):  # 크레딧은 넣을 때만 — 길이만 템플릿 기본값
        sel["credits"] = dict(sel["credits"])
        sel["credits"].setdefault("seconds", (tpl.get("credits") or {}).get("seconds", 12))
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
