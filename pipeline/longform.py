"""롱폼 계획: Claude가 쓴 longform.json(구간)과 transcript.json(문장)으로 storyboard를 만든다 — 결정적 계산만.
경계 스냅(말 중간에 자르지 않기), 자막 쪼개기, 원본 시각 → 출력 시각, SRT."""
import json
from pathlib import Path

from .whisper import REPETITION_PLACEHOLDER

FPS = 30
PAD = 0.3  # 스냅한 경계 앞뒤 여유(초)
MAX_SNAP_GROWTH = 10.0  # 스냅으로 이보다 길어지면 스냅하지 않는다
MIN_VISIBLE = 0.2  # 클립 경계에 걸려 이보다 짧게 보일 자막은 뺀다
FORMATS = {"longform": {"width": 1920, "height": 1080, "chars": 44}}  # chars = 자막 한 장(2줄) 최대 글자 수


def load_spec(path: Path) -> dict:
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise ValueError(f"longform.json을 읽을 수 없습니다 (JSON 형식 오류): {e}")
    if not isinstance(spec, dict):
        raise ValueError("longform.json은 { ... } 형태의 객체여야 합니다")
    clips = spec.get("clips")
    if not isinstance(clips, list) or not clips:
        raise ValueError("longform.json에 clips(구간 목록)가 없습니다")
    for k, c in enumerate(clips, 1):
        if not (isinstance(c, dict) and all(isinstance(c.get(x), (int, float)) for x in ("in", "out"))):
            raise ValueError(f"clips {k}번: in/out(원본 기준 초)은 숫자여야 합니다: {c!r}")
        if not 0 <= c["in"] < c["out"]:
            raise ValueError(f"clips {k}번: in({c['in']})이 out({c['out']})보다 작아야 합니다")
    fixes = spec.get("fixes", {})
    if not (isinstance(fixes, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in fixes.items())):
        raise ValueError('fixes는 {"틀린 말": "고친 말"} 형태여야 합니다')
    formats = spec.get("formats", list(FORMATS))
    if not isinstance(formats, list) or not formats or any(f not in FORMATS for f in formats):
        raise ValueError(f"formats는 {', '.join(FORMATS)} 중에서 고릅니다: {formats!r}")
    return {**spec, "fixes": fixes, "formats": formats}


def _inside(t: float, segments: list[dict]) -> int | None:
    return next((i for i, s in enumerate(segments) if s["start"] < t < s["end"]), None)


def snap(a: float, b: float, segments: list[dict], duration: float) -> tuple[float, float, float]:
    """문장 안에 떨어진 경계만 그 문장 밖으로 민다(침묵 속 경계는 그대로). 이웃 문장은 침범하지 않는다."""
    na, nb = a, b
    if (i := _inside(a, segments)) is not None:
        s = segments[i]
        na = min(s["start"], max(s["start"] - PAD, segments[i - 1]["end"] if i else 0.0))
    if (j := _inside(b, segments)) is not None:
        s = segments[j]
        nb = max(s["end"], min(s["end"] + PAD, segments[j + 1]["start"] if j + 1 < len(segments) else duration))
    growth = (a - na) + (nb - b)
    return (a, b, round(growth, 3)) if growth > MAX_SNAP_GROWTH else (round(na, 3), round(nb, 3), 0.0)


def pieces(text: str, limit: int) -> list[str]:
    out, cur = [], ""
    for w in text.split():
        while len(w) > limit:  # 띄어쓰기 없는 긴 말("ㅋㅋㅋ…")은 강제로 자른다
            if cur:
                out.append(cur)
                cur = ""
            out.append(w[:limit])
            w = w[limit:]
        if not w:
            continue
        if cur and len(cur) + 1 + len(w) > limit:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    if cur:
        out.append(cur)
    return out


def _timed(start: float, end: float, text: str, limit: int) -> list[dict]:
    ps = pieces(text, limit)
    if not ps:
        return []
    total, t, out = sum(len(p) for p in ps), start, []
    for p in ps:  # 글자 수에 비례해 시간을 나눈다
        nxt = t + (end - start) * len(p) / total
        out.append({"start": t, "end": nxt, "text": p})
        t = nxt
    out[-1]["end"] = end
    return out


def captions(clips: list[dict], segments: list[dict], fixes: dict, limit: int) -> list[dict]:
    cues = []
    for s in segments:
        if s["text"].startswith(REPETITION_PLACEHOLDER):
            continue
        text = s["text"]
        for wrong, right in fixes.items():
            text = text.replace(wrong, right)
        cues += _timed(s["start"], s["end"], text, limit)
    out = []
    for c in clips:
        for q in cues:
            a, b = max(q["start"], c["in"]), min(q["end"], c["out"])
            if b - a >= MIN_VISIBLE:
                out.append({"start": round(a - c["in"] + c["start"], 3), "end": round(b - c["in"] + c["start"], 3),
                            "text": q["text"]})
    return out


def _mmss(t: float) -> str:
    m, s = divmod(int(t), 60)
    return f"{m}:{s:02d}"


def build(spec: dict, transcript: dict, src: str) -> tuple[dict, list[str]]:
    segs, duration = transcript["segments"], transcript["duration"]
    warnings = [f"반복 감지로 자막에서 뺀 구간 {_mmss(s['start'])}–{_mmss(s['end'])}"
                for s in segs if s["text"].startswith(REPETITION_PLACEHOLDER)]
    clips, t, prev_out = [], 0.0, None
    for k, c in enumerate(spec["clips"], 1):
        if c["out"] > duration:
            raise ValueError(f"clips {k}번: out({c['out']})이 영상 길이({duration:.1f}초)를 넘습니다")
        if prev_out is not None and c["in"] < prev_out:
            raise ValueError(f"clips {k - 1}번과 {k}번이 겹치거나 순서가 거꾸로입니다 — 시간순으로, 겹치지 않게 고르세요")
        a, b, grew = snap(c["in"], c["out"], segs, duration)
        if grew:
            warnings.append(f"clips {k}번: 경계를 문장에 맞추면 {grew:.0f}초 늘어나 그대로 둡니다")
        if clips:
            a = max(a, clips[-1]["out"])  # 이웃 클립이 같은 문장으로 스냅되면 겹치지 않게 이어 붙인다
        end = round(t + (b - a), 3)
        clips.append({"in": a, "out": b, "start": t, "end": end, "title": c.get("title", "")})
        t, prev_out = end, c["out"]
    formats = {}
    for f in spec["formats"]:
        fmt = FORMATS[f]
        formats[f] = {"width": fmt["width"], "height": fmt["height"], "duration": t, "clips": clips,
                      "captions": captions(clips, segs, spec["fixes"], fmt["chars"])}
    return {"mode": "longform", "fps": FPS, "src": src, "formats": formats}, warnings


def _ts(t: float) -> str:
    ms = round(t * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt(caps: list[dict]) -> str:
    return "\n".join(f"{i}\n{_ts(c['start'])} --> {_ts(c['end'])}\n{c['text']}\n" for i, c in enumerate(caps, 1))
