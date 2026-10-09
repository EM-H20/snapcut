"""롱폼 계획: Claude가 쓴 longform.json(구간)과 transcript.json(문장)으로 storyboard를 만든다 — 결정적 계산만.
경계 스냅(말 중간에 자르지 않기), 자막 쪼개기, 원본 시각 → 출력 시각, SRT."""
import json
from pathlib import Path

from .paths import SHARED
from .whisper import REPETITION_PLACEHOLDER

FPS = 30
PAD = 0.3  # 스냅한 경계 앞뒤 여유(초)
MAX_SNAP_GROWTH = 10.0  # 스냅으로 이보다 길어지면 스냅하지 않는다
MIN_VISIBLE = 0.2  # 클립 경계에 걸려 이보다 짧게 보일 자막은 뺀다
STYLES_DIR = SHARED / "자막"  # 자막바·말풍선 스타일 (공용, git 포함)
DEFAULT_STYLE = "흰바"
# chars = 자막 한 장(2줄) 최대 글자 수 — CaptionLayer.tsx의 폭·글자 크기와 짝 (bar: 자막바, bubble: 말풍선)
FORMATS = {"longform": {"width": 1920, "height": 1080, "chars": {"bar": 40, "bubble": 30}},
           "shorts": {"width": 1080, "height": 1920, "chars": {"bar": 22, "bubble": 22}}}


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
        if c["out"] - c["in"] < 1 / FPS:
            raise ValueError(f"clips {k}번: 구간이 너무 짧습니다 (한 프레임 미만)")
    fixes = spec.get("fixes", {})
    if not (isinstance(fixes, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in fixes.items())):
        raise ValueError('fixes는 {"틀린 말": "고친 말"} 형태여야 합니다')
    formats = spec.get("formats", list(FORMATS))
    if not isinstance(formats, list) or not formats or any(f not in FORMATS for f in formats):
        raise ValueError(f"formats는 {', '.join(FORMATS)} 중에서 고릅니다: {formats!r}")
    style = spec.get("captionStyle", DEFAULT_STYLE)
    if not isinstance(style, str):
        raise ValueError("captionStyle은 공용/자막의 스타일 이름이어야 합니다")
    speakers = spec.get("speakers", {})
    if not isinstance(speakers, dict):
        raise ValueError('speakers는 {"마이크1": "이름"} 형태여야 합니다')
    for label, v in speakers.items():
        name = v if isinstance(v, str) else v.get("name") if isinstance(v, dict) else None
        side_ok = not isinstance(v, dict) or v.get("side", "left") in ("left", "right")
        if not isinstance(name, str) or not side_ok:
            raise ValueError(f'speakers의 {label}: "이름" 또는 {{"name": "이름", "side": "left"|"right"}} 형태여야 합니다')
    for key in ("pov", "speaker"):
        if key in spec and not isinstance(spec[key], str):
            raise ValueError(f"{key}는 문자열이어야 합니다")
    return {**spec, "fixes": fixes, "formats": formats, "captionStyle": style, "speakers": speakers}


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


def load_style(name: str, root: Path = STYLES_DIR) -> dict:
    path = root / f"{name}.json"
    if not path.is_file():
        names = sorted(p.stem for p in root.glob("*.json")) if root.exists() else []
        raise ValueError(f"자막 스타일 '{name}'이 없습니다 (가능: {', '.join(names) or '없음'})")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise ValueError(f"자막 스타일 파일을 읽을 수 없습니다 ({path}): {e}")


def layout(spec: dict, transcript: dict) -> tuple[dict, list[str]]:
    """이름표(마이크k) → {"name", "place"}. 시점 주인은 자막바, 나머지는 고정된 쪽 말풍선(기본: 트랙 순서대로 왼쪽·오른쪽 교대)."""
    labels = [t["label"] for t in transcript.get("tracks", [])] or [""]  # 예전 transcript는 이름표 없음
    multi = len(labels) > 1
    pov = spec.get("pov", labels[0])
    speakers = spec.get("speakers", {})
    who, others = {}, 0
    for label in labels:
        m = speakers.get(label)
        name = m if isinstance(m, str) else m["name"] if m else (label if multi else spec.get("speaker", ""))
        if not multi or label == pov:
            place = "bar"
        else:
            place = (m.get("side") if isinstance(m, dict) else None) or ("left", "right")[others % 2]
            others += 1
        who[label] = {"name": name, "place": place}
    unknown = [x for x in [*speakers, *([spec["pov"]] if "pov" in spec else [])] if x not in labels]
    warnings = [f"transcript에 없는 이름표: {', '.join(unknown)} (전사한 이름표: {', '.join(x for x in labels if x) or '없음'})"] \
        if unknown else []
    return who, warnings


def captions(clips: list[dict], segments: list[dict], fixes: dict, chars: dict, who: dict | None = None) -> list[dict]:
    who = who or {}
    cues = []
    for s in segments:
        if s["text"].startswith(REPETITION_PLACEHOLDER):
            continue
        text = s["text"]
        for wrong, right in fixes.items():
            text = text.replace(wrong, right)
        w = who.get(s.get("speaker", ""), {"name": "", "place": "bar"})
        limit = chars["bar"] if w["place"] == "bar" else chars["bubble"]
        cues += [{**q, **w} for q in _timed(s["start"], s["end"], text, limit)]
    out = []
    for c in clips:
        for q in cues:
            a, b = max(q["start"], c["in"]), min(q["end"], c["out"])
            if b - a >= MIN_VISIBLE:
                out.append({"start": round(a - c["in"] + c["start"], 3), "end": round(b - c["in"] + c["start"], 3),
                            "text": q["text"], "name": q["name"], "place": q["place"]})
    return out


def _mmss(t: float) -> str:
    m, s = divmod(int(t), 60)
    return f"{m}:{s:02d}"


def build(spec: dict, transcript: dict, src: str, style: dict | None = None) -> tuple[dict, list[str]]:
    segs, duration = transcript["segments"], transcript["duration"]
    warnings = [f"반복 감지로 자막에서 뺀 구간 {_mmss(s['start'])}–{_mmss(s['end'])}"
                for s in segs if s["text"].startswith(REPETITION_PLACEHOLDER)]
    who, speaker_warnings = layout(spec, transcript)
    warnings += speaker_warnings
    clips, kept, t, prev_out = [], [], 0.0, None
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
        if b - a < 1 / FPS:  # 앞 클립의 스냅이 이 구간을 이미 덮었다
            warnings.append(f"clips {k}번: 앞 구간에 이미 들어 있어 뺍니다")
            prev_out = c["out"]
            continue
        end = round(t + (b - a), 3)
        clips.append({"in": a, "out": b, "start": t, "end": end, "title": c.get("title", "")})
        kept.append(c)
        t, prev_out = end, c["out"]
    formats = {}
    for f in spec["formats"]:
        fmt = FORMATS[f]
        if f == "shorts":  # 클립마다 0초부터 시작하는 계획 하나 (편집본과 같은 스냅 결과)
            formats[f] = []
            for c, orig in zip(clips, kept):
                if orig.get("shorts", True) is False:
                    continue
                one = {**c, "start": 0.0, "end": round(c["out"] - c["in"], 3)}
                formats[f].append({"width": fmt["width"], "height": fmt["height"], "duration": one["end"],
                                   "title": c["title"], "clips": [one],
                                   "captions": captions([one], segs, spec["fixes"], fmt["chars"], who)})
        else:
            formats[f] = {"width": fmt["width"], "height": fmt["height"], "duration": t, "clips": clips,
                          "captions": captions(clips, segs, spec["fixes"], fmt["chars"], who)}
    sb = {"mode": "longform", "fps": FPS, "src": src, "formats": formats}
    if style is not None:
        sb["captionStyle"] = style
    return sb, warnings


def _ts(t: float) -> str:
    ms = round(t * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def srt(caps: list[dict]) -> str:
    def line(c):
        return f"{c['name']}: {c['text']}" if c.get("name") else c["text"]
    return "\n".join(f"{i}\n{_ts(c['start'])} --> {_ts(c['end'])}\n{line(c)}\n" for i, c in enumerate(caps, 1))
