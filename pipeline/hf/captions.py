"""롱폼 자막 레이어 HTML (render/src/CaptionLayer.tsx 이식). 치수는 longform.py FORMATS의 chars와 짝:
자막바 글자 h/18(가로)·w/14(세로), 폭 86% / 말풍선 h/24·w/18, 폭 38%·76%. 자막 구성이 바뀌는 구간마다 시간 있는 div 하나."""
import html

from . import timing as T
from .mv import attr

FALLBACK = {  # 스타일이 없는 예전 storyboard — 공용/자막/흰바.json과 같은 값
    "font": '"Apple SD Gothic Neo", "Noto Sans KR", sans-serif',
    "bar": {"background": "#ffffff", "color": "#111111", "border": "3px solid #111111", "radius": 14},
    "name": {"background": "transparent", "color": "#e5484d", "radius": 0, "separator": True},
    "bubble": {"background": "#ffffff", "color": "#111111", "border": "3px solid #111111", "radius": 28},
    "icon": None,
}
TEXT = "word-break:keep-all;overflow-wrap:anywhere;line-height:1.3;font-weight:800"
SHADOW = "0 6px 18px rgba(0,0,0,0.35)"


def _px(v: float) -> str:
    return f"{v:.2f}px"


def active_by_place(caps: list[dict], t: float) -> dict:
    out = {"bar": [], "left": [], "right": []}
    for c in caps:
        if c["start"] <= t < c["end"]:
            out[c.get("place") or "bar"].append(c)
    return out


def states(caps: list[dict], fps: int) -> list[tuple[int, int, dict]]:
    """자막 구성이 바뀌는 프레임 구간마다 (시작, 끝, 자리별 자막). 아무 자막도 없는 구간은 뺀다."""
    edges = sorted({T.frame(c[k], fps) for c in caps for k in ("start", "end")})
    out = []
    for a, b in zip(edges, edges[1:]):
        now = {"bar": [], "left": [], "right": []}
        for c in caps:
            if T.frame(c["start"], fps) <= a < T.frame(c["end"], fps):
                now[c.get("place") or "bar"].append(c)
        if any(now.values()):
            out.append((a, b, now))
    return out


def _name_tag(name: str, s: dict, size: float) -> str:
    pad = "0" if s["background"] == "transparent" else f"{_px(size * 0.08)} {_px(size * 0.45)}"
    return (f'<span style="background:{s["background"]};color:{s["color"]};border-radius:{s["radius"]}px;white-space:nowrap;'
            f'flex-shrink:0;font-weight:900;padding:{pad}">{html.escape(name)}</span>')


def _play_icon(size: float) -> str:
    return (f'<span style="display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;width:{_px(size * 1.3)};'
            f'height:{_px(size * 0.95)};background:#ffffff;border-radius:{_px(size * 0.25)}"><span style="width:0;height:0;'
            f'margin-left:{_px(size * 0.08)};border-top:{_px(size * 0.22)} solid transparent;border-bottom:{_px(size * 0.22)} solid transparent;'
            f'border-left:{_px(size * 0.36)} solid #ff0033"></span></span>')


def _name_above(name: str, s: dict, size: float) -> str:
    stroke = f"-webkit-text-stroke:{_px(size * 0.18)} {s['stroke']};" if s.get("stroke") else ""
    return (f'<span style="position:absolute;bottom:100%;left:{_px(size * 0.5)};margin-bottom:{_px(-size * 0.28)};'
            f'font-size:{_px(size * 0.95)};font-weight:900;line-height:1.15;white-space:nowrap;color:{s["color"]};'
            f'{stroke}paint-order:stroke fill">{html.escape(name)}</span>')


def _bar(c: dict, s: dict, size: float, inline: bool) -> str:
    """가로는 [아이콘][이름 │ ]자막 한 줄, 세로(쇼츠)는 이름표를 위쪽 테두리에 걸친다. position above면 둘 다 바 위."""
    name = s["name"] if c.get("name") and s.get("name") else None
    above = bool(name) and name.get("position") == "above"
    b = s["bar"]
    top = size * 0.75 if above else size * 0.5 if name and not inline else 0
    style = (f"position:relative;display:flex;align-items:center;gap:{_px(size * 0.35)};max-width:86%;font-size:{_px(size)};"
             + ("width:86%;" if b.get("wide") else "")
             + f"justify-content:{'center' if b.get('align') == 'center' else 'flex-start'};background:{b['background']};"
             f"color:{b['color']};border:{b['border']};border-radius:{b['radius']}px;padding:{_px(size * 0.25)} {_px(size * 0.5)};"
             f"margin-top:{_px(top)};box-shadow:{b.get('shadow', SHADOW)}")
    kids = [_play_icon(size)] if s.get("icon") == "play" else []
    if name and above:
        kids.append(_name_above(c["name"], name, size))
    elif name and inline:
        kids.append(_name_tag(c["name"], name, size))
        if name.get("separator"):
            kids.append('<span style="opacity:0.45;flex-shrink:0">│</span>')
    elif name:
        tag = dict(name, background=b["background"]) if name["background"] == "transparent" else name
        kids.append(f'<span style="position:absolute;top:{_px(-size * 0.55)};left:{_px(size * 0.4)};font-size:{_px(size * 0.72)}">'
                    f'{_name_tag(c["name"], tag, size * 0.72)}</span>')
    align = ";text-align:center" if b.get("align") == "center" else ""
    kids.append(f'<span style="{TEXT}{align}">{html.escape(c["text"])}</span>')
    return f'<div style="{attr(style)}">{"".join(kids)}</div>'


def _bubble(c: dict, s: dict, size: float, side: str) -> str:
    """말풍선: 이름은 윗줄 작게, 꼬리는 바깥 가장자리 쪽 아래."""
    b, name = s["bubble"], ""
    if c.get("name") and s.get("name"):
        n = s["name"]
        color = n["color"] if n["background"] == "transparent" else n["background"]
        name = (f'<div style="font-size:{_px(size * 0.72)};font-weight:900;margin-bottom:{_px(size * 0.1)};color:{color}">'
                f'{html.escape(c["name"])}</div>')
    tail = (f'<span style="position:absolute;bottom:{_px(-size * 0.3)};{side}:{_px(size * 0.8)};width:{_px(size * 0.55)};'
            f'height:{_px(size * 0.55)};background:{b["background"]};border-right:{b["border"]};border-bottom:{b["border"]};'
            f'transform:rotate(45deg)"></span>')
    style = (f"position:relative;font-size:{_px(size)};background:{b['background']};color:{b['color']};border:{b['border']};"
             f"border-radius:{b['radius']}px;padding:{_px(size * 0.35)} {_px(size * 0.6)};box-shadow:{b.get('shadow', SHADOW)}")
    return f'<div style="{attr(style)}">{name}<span style="{TEXT}">{html.escape(c["text"])}</span>{tail}</div>'


def layer(caps: list[dict], style: dict, w: int, h: int, vertical: bool, fps: int) -> str:
    bar_size, bubble_size = (w / 14, w / 18) if vertical else (h / 18, h / 24)
    # 세로(쇼츠): 게임 화면(16:9, 폭 맞춤) 바로 아래 — 더 내리면 쇼츠 제목·버튼과 겹친다
    bar_pos = f"top:{_px((h + w * 9 / 16) / 2 + bar_size * 0.3)}" if vertical else f"bottom:{_px(h * 0.06)}"
    out = []
    for k, (a, b, now) in enumerate(states(caps, fps)):
        st, du = T.window(a, b, fps)
        bars = "".join(_bar(c, style, bar_size, not vertical) for c in now["bar"])
        parts = [f'<div style="position:absolute;left:0;right:0;{bar_pos};display:flex;flex-direction:column;align-items:center;'
                 f'gap:{_px(bar_size * 0.3)}">{bars}</div>']
        if vertical:  # 위쪽 흐린 영역에 메신저처럼 한 줄로 쌓고 왼쪽·오른쪽으로 붙인다
            items = sorted([(c, "left") for c in now["left"]] + [(c, "right") for c in now["right"]], key=lambda x: x[0]["start"])
            inner = "".join(f'<div style="align-self:{"flex-start" if side == "left" else "flex-end"};max-width:76%">'
                            f'{_bubble(c, style, bubble_size, side)}</div>' for c, side in items)
            parts.append(f'<div style="position:absolute;top:{_px(h * 0.06)};left:{_px(w * 0.04)};right:{_px(w * 0.04)};'
                         f'display:flex;flex-direction:column;gap:{_px(bubble_size * 0.6)}">{inner}</div>')
        else:  # 가로: 자막바 위 양옆
            for side in ("left", "right"):
                inner = "".join(_bubble(c, style, bubble_size, side) for c in now[side])
                parts.append(f'<div style="position:absolute;{side}:{_px(w * 0.04)};max-width:38%;bottom:{_px(h * 0.28)};display:flex;'
                             f'flex-direction:column;align-items:{"flex-start" if side == "left" else "flex-end"};'
                             f'gap:{_px(bubble_size * 0.6)}">{inner}</div>')
        out.append(f'<div class="clip cap" data-start="{st}" data-duration="{du}" data-track-index="{9000 + k}" '
                   f'style="font-family:{attr(style["font"])}">{"".join(parts)}</div>')
    return "\n".join(out)
