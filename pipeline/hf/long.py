"""롱폼·쇼츠 storyboard → HyperFrames 구성 HTML.
원본 한 파일에서 고른 구간을 이어 붙이고 소리는 원본 그대로. 쇼츠는 같은 구간을 흐린 배경으로 깔고 가운데 원본."""
from . import captions, mv
from . import timing as T

SHORTS_CSS = ".shortsbg{position:absolute;inset:0;filter:blur(40px) brightness(.6);transform:scale(1.15)}"


def _clips(src: str, clips: list[dict], fps: int, prefix: str, *, audio: bool, fit: str) -> str:
    out = []
    for k, c in enumerate(clips):
        st, du = T.window(T.frame(c["start"], fps), T.frame(c["end"], fps), fps)
        snd = 'data-has-audio="true" data-volume="1"' if audio else "muted"
        out.append(f'<video id="{prefix}{k}" src="{mv.attr(src)}" data-start="{st}" data-duration="{du}" '
                   f'data-media-start="{c["in"]:.6f}" data-track-index="{k + 1}" playsinline {snd} '
                   f'style="position:absolute;inset:0;width:100%;height:100%;object-fit:{fit}"></video>')
    return "".join(out)


def build(sb: dict, fmt: str, clip: int = 0) -> str:
    fps = sb["fps"]
    plan = sb["formats"]["shorts"][clip] if fmt == "shorts" else sb["formats"][fmt]
    w, h, vertical = plan["width"], plan["height"], fmt == "shorts"
    body = [f'<div class="shortsbg">{_clips(sb["src"], plan["clips"], fps, "b", audio=False, fit="cover")}</div>'] if vertical else []
    body.append(_clips(sb["src"], plan["clips"], fps, "c", audio=True, fit="contain"))
    body.append(captions.layer(plan["captions"], sb.get("captionStyle") or captions.FALLBACK, w, h, vertical, fps))
    return mv.page(w, h, T.frame(plan["duration"], fps), fps, "\n".join(body), [], SHORTS_CSS if vertical else "")
