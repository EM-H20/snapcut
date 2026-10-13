"""추억 뮤비 storyboard 한 형식 → HyperFrames 구성 HTML. 사진·영상·콜라주·크레딧 + 카메라·전환 효과.
층: #sN(전환: 투명도·블러·휩·와이프) > #sN-k(켄 번스) > #sN-h(흔들림) > 더치 앵글(고정 CSS) > 사진/영상.
영상은 <video>에 시간을 두고 바깥 #sN은 시간 없는 껍데기 — 시간 있는 요소 안의 영상은 HF가 엉뚱한 프레임을 보여 준다."""
import html
import json
import math
import random

from ..plan import avg_speed
from . import timing as T

GSAP = "https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"
CSS = """body{margin:0;background:#000}
#root{position:relative;width:100%;height:100%;overflow:hidden;background:#000}
.shot,.fill{position:absolute;inset:0}
.contain{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}
.grid{position:absolute;inset:0;display:grid;gap:8px;padding:8px}
.cell{position:relative;overflow:hidden}
.bgfill{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;filter:blur(30px) brightness(.6);transform:scale(1.2)}
.credits{position:absolute;inset:0;background:rgba(0,0,0,.35);display:flex;flex-direction:column;align-items:center}
.roll{display:flex;flex-direction:column;align-items:center}
.credit-line{font-family:sans-serif;line-height:1.2;color:#fff;text-shadow:0 2px 12px rgba(0,0,0,.5);white-space:nowrap}
.dark{position:absolute;inset:0;background:#000;opacity:0}
.tag{position:absolute;left:16px;top:16px;padding:6px 12px;background:rgba(0,0,0,.6);color:#fff;font:28px monospace;border-radius:6px;z-index:100000}
"""
COPY_JS = """addEventListener("keydown", (e) => {
  if (e.key.toLowerCase() !== "q" || e.metaKey || e.ctrlKey || e.altKey) return;
  const tag = [...document.querySelectorAll(".tag")].find((el) => getComputedStyle(el).visibility !== "hidden" && el.offsetParent !== null);
  if (tag) navigator.clipboard.writeText(tag.textContent).catch(() => prompt("복사하세요", tag.textContent));
});"""


def attr(v) -> str:
    return html.escape(str(v), quote=True)


def still(fmt: str, i: int) -> str:
    return f"freeze/{fmt}_s{i}.jpg"


def tween(target: str, a: dict, b: dict, frames: int, at: int, fps: int, ease: str = "none") -> str:
    to = dict(b, duration=frames / fps, ease=ease, immediateRender=False)
    return f"tl.fromTo({json.dumps(target)},{json.dumps(a)},{json.dumps(to)},{T.ts(at, fps)});"


def page(w: int, h: int, total_f: int, fps: int, body: str, js: list[str], extra_css: str = "") -> str:
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width={w}, height={h}">
<script src="{GSAP}"></script>
<style>{CSS}{extra_css}</style></head><body>
<div id="root" data-composition-id="main" data-start="0" data-width="{w}" data-height="{h}" data-duration="{total_f / fps!r}">
{body}
</div>
<script>
const tl = gsap.timeline({{paused: true}});
{chr(10).join(js)}
window.__timelines["main"] = tl;
</script></body></html>
"""


def _video(id_: str, src: str, f0: int, f1: int, fps: int, media_in: float, track: int, *,
           audio: bool, attrs: str = "", style: str = "") -> str:
    st, du = T.window(f0, f1, fps)
    snd = 'data-has-audio="true" data-volume="1"' if audio else "muted"
    look = f' style="{style}"' if style else ' class="contain"'
    return (f'<video id="{id_}"{look} src="{attr(src)}" data-start="{st}" data-duration="{du}" '
            f'data-media-start="{max(0.0, media_in):.6f}" data-track-index="{track}" playsinline {snd}{attrs}></video>')


def _rotated(rot, w: int, h: int) -> str:
    """옆으로 찍힌 영상: 돌린 뒤 화면에 맞도록 가로·세로 크기를 바꿔 잡는다."""
    if not rot:
        return ""
    vw, vh = (h, w) if abs(rot) == 90 else (w, h)
    return (f"position:absolute;left:50%;top:50%;width:{vw}px;height:{vh}px;margin-left:{-vw / 2:g}px;"
            f"margin-top:{-vh / 2:g}px;object-fit:contain;transform:rotate({rot}deg)")


def _layers(i: int, s: dict, w: int, h: int, inner: str) -> str:
    if s.get("dutch"):
        a = math.radians(abs(s["dutch"]))
        k = math.cos(a) + math.sin(a) * max(w, h) / min(w, h)  # 기울인 화면이 모서리까지 덮는 배율
        inner = f'<div class="fill" style="transform:rotate({s["dutch"]:g}deg) scale({k:.4f})">{inner}</div>'
    if s.get("shake"):
        inner = f'<div id="s{i}-h" class="fill">{inner}</div>'
    return inner


def _video_shot(i: int, s: dict, sp: dict, fmt: str, fps: int, w: int, h: int) -> str:
    f0, n, end = sp["from"], sp["frames"], sp["from"] + sp["duration"]
    hold = T.frame(s.get("freeze", 0), fps)
    vend = f0 + n - hold if hold else end
    speed, attrs = s.get("speed"), ""
    if isinstance(speed, list):  # 스피드 램프: 장면 동안 배속이 직선으로 바뀐다
        lane = {"version": 1, "lanes": [{"target": "rate", "points": [{"t": 0, "v": speed[0]}, {"t": round((vend - f0) / fps, 3), "v": speed[1]}]}]}
        attrs = f' data-automation="{attr(json.dumps(lane))}"'
    elif speed:
        attrs = f' data-playback-rate="{speed:g}"'
    split = bool(s.get("jcut") or s.get("lcut")) and s["liveAudio"]
    style = _rotated(s.get("rotate"), w, h)
    out = [_video(f"v{i}", s["src"], f0, vend, fps, s["in"], i + 1, audio=s["liveAudio"] and not split, attrs=attrs, style=style)]
    if hold:  # 프리즈 프레임: 영상 마지막 프레임을 멈춘 사진으로 (engine.freeze_stills가 뽑아 둔다)
        st, du = T.window(vend, end, fps)
        look = f' style="{style}"' if style else ""
        out.append(f'<img class="clip{"" if style else " contain"}" src="{still(fmt, i)}" data-start="{st}" data-duration="{du}" data-track-index="{i + 1}"{look}>')
    if split:  # J컷·L컷: 소리를 따로 꺼내 화면보다 먼저 시작하거나 늦게 끝낸다
        j, l = T.frame(s.get("jcut", 0), fps), T.frame(s.get("lcut", 0), fps)
        st, du = T.window(f0 - j, f0 + n - hold + l, fps)  # 멈춘 화면에는 현장 소리가 없다 (L컷만큼만 이어짐)
        out.append(f'<audio id="a{i}" src="{attr(s["src"])}" data-start="{st}" data-duration="{du}" '
                   f'data-media-start="{max(0.0, s["in"] - j / fps):.6f}" data-volume="1" data-track-index="{i + 1}"></audio>')
    return "".join(out)


def _credits(i: int, s: dict, sp: dict, fps: int, h: int, js: list[str]) -> str:
    """노래가 끝난 뒤 크레딧: 영상(자기 소리) 위로 줄이 아래에서 위로 올라가고, 끝 2초는 검게 어두워지며 소리도 줄어든다."""
    f0, n = sp["from"], sp["frames"]
    lay, fade = T.credits_layout(len(s["lines"]), h), T.frame(T.CREDITS_FADE, fps)
    lane = {"version": 1, "lanes": [{"target": "volume", "points": [
        {"t": 0, "v": 1}, {"t": round(max(0, n - fade) / fps, 3), "v": 1}, {"t": round(n / fps, 3), "v": 0}]}]}
    video = _video(f"v{i}", s["src"], f0, f0 + n, fps, s["in"], i + 1, audio=s["liveAudio"], attrs=f' data-automation="{attr(json.dumps(lane))}"')
    st, du = T.window(f0, f0 + n, fps)
    lines = "".join(f'<div class="credit-line" style="font-size:{lay["size"]}px">{html.escape(x)}</div>' for x in s["lines"])
    js.append(tween(f"#s{i}-roll", {"y": h}, {"y": -round(lay["block"], 2)}, n, f0, fps))
    js.append(tween(f"#s{i}-dark", {"opacity": 0}, {"opacity": 1}, fade, f0 + n - fade, fps))
    return (video + f'<div class="clip credits" data-start="{st}" data-duration="{du}" data-track-index="{i + 1}">'
            f'<div id="s{i}-roll" class="roll" style="gap:{lay["gap"]:.2f}px">{lines}</div></div>'
            f'<div id="s{i}-dark" class="clip dark" data-start="{st}" data-duration="{du}" data-track-index="{i + 1}"></div>')


def _shot(i: int, s: dict, sp: dict, fmt: str, fps: int, w: int, h: int, js: list[str]) -> str:
    f0, n = sp["from"], sp["frames"]
    outer = f"z-index:{i + 1}" + (";opacity:0" if sp["fadeIn"] else "") + (";clip-path:inset(0% 100% 0% 0%)" if sp["wipeIn"] else "")
    t = s["type"]
    if t in ("photo", "collage"):
        kb = T.kenburns(s.get("kenBurns", "still"))
        if t == "photo":
            inner = f'<img class="contain" src="{attr(s["src"])}">'
            if kb:
                inner = f'<div id="s{i}-k" class="fill">{inner}</div>'
                js.append(tween(f"#s{i}-k", kb[0], kb[1], n, f0, fps))
        else:
            cols, rows = T.collage_grid(len(s["srcs"]), w > h)
            cells = "".join(f'<div class="cell"><img class="bgfill" src="{attr(x)}"><img class="contain s{i}-fg" src="{attr(x)}"></div>'
                            for x in s["srcs"])  # 사진 전체가 보이게 + 남는 자리는 흐린 같은 사진
            inner = f'<div class="grid" style="grid-template-columns:repeat({cols},1fr);grid-template-rows:repeat({rows},1fr)">{cells}</div>'
            if kb:
                js.append(tween(f".s{i}-fg", {"scale": kb[0]["scale"]}, {"scale": kb[1]["scale"]}, n, f0, fps))
        st, du = T.window(f0, f0 + sp["duration"], fps)
        return (f'<div id="s{i}" class="clip shot" data-start="{st}" data-duration="{du}" data-track-index="{i + 1}" '
                f'style="{outer}">{_layers(i, s, w, h, inner)}</div>')
    if t == "video":
        inner = _video_shot(i, s, sp, fmt, fps, w, h)
    elif t == "clip":  # 인트로/아웃트로 카드 mp4 (intro.py가 미리 렌더)
        inner = _video(f"v{i}", s["src"], f0, f0 + sp["duration"], fps, 0.0, i + 1, audio=False)
    else:
        inner = _credits(i, s, sp, fps, h, js)
    return f'<div id="s{i}" class="shot" style="{outer}">{_layers(i, s, w, h, inner)}</div>'


def _transitions(i: int, s: dict, sp: dict, fps: int, h: int, js: list[str]) -> None:
    f0, n, tgt, px = sp["from"], sp["frames"], f"#s{i}", round(h / 36, 2)
    blur, sharp = f"blur({px}px)", "blur(0px)"
    # 나가는 트윈은 같은 속성의 들어오는 트윈이 끝난 뒤 시작한다 — fromTo가 겹치면 탐색 순서에 따라 화면이 달라진다
    room = max(0, n - max(sp["blurIn"], sp["whipIn"]))
    sp = dict(sp, blurOut=min(sp["blurOut"], room), whipOut=min(sp["whipOut"], room))
    if sp["fadeIn"]:
        js.append(tween(tgt, {"opacity": 0}, {"opacity": 1}, sp["fadeIn"], f0, fps))
    if sp["wipeIn"]:
        js.append(tween(tgt, {"clipPath": "inset(0% 100% 0% 0%)"}, {"clipPath": "inset(0% 0% 0% 0%)"}, sp["wipeIn"], f0, fps, "power1.inOut"))
    if sp["blurIn"]:
        js.append(tween(tgt, {"filter": blur, "scale": T.BLUR_SCALE}, {"filter": sharp, "scale": 1}, sp["blurIn"], f0, fps))
    if sp["blurOut"]:
        js.append(tween(tgt, {"filter": sharp, "scale": 1}, {"filter": blur, "scale": T.BLUR_SCALE}, sp["blurOut"], f0 + n - sp["blurOut"], fps))
    if sp["whipIn"]:
        js.append(tween(tgt, {"xPercent": T.WHIP_SHIFT, "filter": blur}, {"xPercent": 0, "filter": sharp}, sp["whipIn"], f0, fps, "power2.out"))
    if sp["whipOut"]:
        js.append(tween(tgt, {"xPercent": 0, "filter": sharp}, {"xPercent": -T.WHIP_SHIFT, "filter": blur}, sp["whipOut"], f0 + n - sp["whipOut"], fps, "power2.in"))
    fo = min(T.frame(s.get("fadeOut", 0), fps), max(0, n - sp["fadeIn"]))
    if fo:  # 끝 페이드아웃: 마지막 프레임에서 0
        js.append(tween(tgt, {"opacity": 1}, {"opacity": 0}, max(1, fo - 1), f0 + n - fo, fps))


def _shake(i: int, s: dict, sp: dict, fps: int, w: int, h: int, js: list[str]) -> None:
    """핸드헬드: 장면 번호를 씨앗으로 한 무작위 위치를 SHAKE_STEP마다 오간다 (렌더마다 같음). 가장자리가 안 보이게 살짝 확대."""
    rng, amp = random.Random(i), s["shake"] * min(w, h) / 60
    scale, step = round(1 + 2.5 * amp / min(w, h), 4), T.frame(T.SHAKE_STEP, fps)
    prev = {"x": 0, "y": 0, "rotation": 0, "scale": scale}
    for f in range(sp["from"], sp["from"] + sp["duration"], step):
        nxt = {"x": round(rng.uniform(-amp, amp), 2), "y": round(rng.uniform(-amp, amp), 2),
               "rotation": round(rng.uniform(-0.6, 0.6) * s["shake"], 3), "scale": scale}
        js.append(tween(f"#s{i}-h", prev, nxt, step, f, fps, "sine.inOut"))
        prev = nxt


def _tag(i: int, s: dict, sp: dict, fps: int, js: list[str]) -> str:
    """미리보기 전용 이름표 (렌더에는 없음): 파일 이름, 영상이면 원본 몇 초. Q 키로 복사."""
    st, du = T.window(sp["from"], sp["from"] + sp["frames"], fps)
    if s["type"] == "video":
        js.append(f'tl.to({{}},{{duration:{sp["frames"] / fps},onUpdate(){{document.getElementById("t{i}").textContent='
                  f'{json.dumps(T.shot_name(s["src"]))}+" "+({s["in"]}+this.time()*{avg_speed(s)}).toFixed(1)+"초";}}}},{T.ts(sp["from"], fps)});')
    return (f'<div id="t{i}" class="clip tag" data-start="{st}" data-duration="{du}" data-track-index="{8000 + i}">'
            f'{html.escape(T.shot_label(s, 0))}</div>')


def build(sb: dict, fmt: str, preview: bool = False) -> str:
    fps, plan = sb["fps"], sb["formats"][fmt]
    w, h, shots = plan["width"], plan["height"], plan["shots"]
    total_f = T.frame(plan["musicEnd"] - plan["musicStart"], fps)
    body, js = [], []
    for i, s in enumerate(shots):
        sp = T.span(shots, i, fps)
        body.append(_shot(i, s, sp, fmt, fps, w, h, js))
        _transitions(i, s, sp, fps, h, js)
        if s.get("shake"):
            _shake(i, s, sp, fps, w, h, js)
        if preview:
            body.append(_tag(i, s, sp, fps, js))
    lane = {"version": 1, "lanes": [{"target": "volume", "points": T.duck_lane(shots, total_f / fps, plan.get("musicFadeEnd", total_f / fps))}]}
    body.insert(0, f'<audio id="music" src="{attr(sb["music"])}" data-start="0" data-duration="{T.ts(total_f, fps)}" '
                   f'data-media-start="{plan["musicStart"]:.6f}" data-volume="1" data-track-index="0" '
                   f'data-automation="{attr(json.dumps(lane))}"></audio>')
    if preview:
        js.append(COPY_JS)
    css = (f'@font-face{{font-family:SnapcutHand;src:url("{sb["font"]}")}}'  # 크레딧 손글씨 — 글꼴 파일이 있을 때만 이름을 쓴다
           '.credit-line{font-family:SnapcutHand,sans-serif}') if sb.get("font") else ""
    return page(w, h, total_f, fps, "\n".join(body), js, css)
