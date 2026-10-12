"""storyboard 시각 → HyperFrames 속성·트윈 값. 결정적 계산만 (render/src의 span·duck·kenburns·collage·creditsRoll·shotLabel 이식)."""
import math
import re

FPS = 30
BLUR_SCALE = 1.06  # 블러 전환 중 가장자리로 검은 배경이 번져 보이지 않게 살짝 확대
WHIP_SHIFT = 30    # 휩 팬: 화면 폭의 몇 %를 밀어내며 지나가는지
SHAKE_STEP = 0.2   # 핸드헬드: 이 초마다 다음 흔들림 위치로
CREDITS_FADE = 2.0
DUCK, DUCK_FADE, END_FADE = 0.3, 0.3, 2.0  # 현장 소리 구간 음악 볼륨 / 덕킹 진입·복귀 초 / 곡 끝 페이드 초


def frame(t: float, fps: int = FPS) -> int:
    return math.floor(t * fps + 0.5)  # JS Math.round와 같게 (.5는 올림)


def _sec(us: int) -> str:
    return f"{us // 1_000_000}.{us % 1_000_000:06d}"


def ts(f: int, fps: int = FPS) -> str:
    """프레임 → 초 문자열, 소수 6자리 내림. 반올림하면 프레임 시각보다 늦어져 그 프레임에 클립이 안 보인다 (1프레임 검정)."""
    return _sec(f * 1_000_000 // fps)


def window(f0: int, f1: int, fps: int = FPS) -> tuple[str, str]:
    """[f0, f1) → (data-start, data-duration). 시작은 내림, 끝은 올림이라 끝 ≥ 다음 클립의 시작."""
    a, b = f0 * 1_000_000 // fps, -(-f1 * 1_000_000 // fps)
    return _sec(a), _sec(b - a)


def _frames(s: dict | None, key: str, fps: int, half: bool = False) -> int:
    v = s.get(key) if s else None
    return frame(v / 2 if half else v, fps) if v else 0


def span(shots: list[dict], i: int, fps: int = FPS) -> dict:
    """장면 i의 프레임 구간. 다음 장면이 dissolve·wipe면 이 장면을 그만큼 더 남겨 아래에 깔고,
    blur·whip은 경계 앞뒤 절반씩 (나가는 장면은 끝 절반, 들어오는 장면은 앞 절반)."""
    s, nxt = shots[i], shots[i + 1] if i + 1 < len(shots) else None
    f0 = frame(s["start"], fps)
    n = max(1, frame(s["end"], fps) - f0)
    return {"from": f0, "frames": n, "duration": n + _frames(nxt, "dissolve", fps) + _frames(nxt, "wipe", fps),
            "fadeIn": _frames(s, "dissolve", fps), "wipeIn": _frames(s, "wipe", fps),
            "blurIn": _frames(s, "blur", fps, True), "blurOut": _frames(nxt, "blur", fps, True),
            "whipIn": _frames(s, "whip", fps, True), "whipOut": _frames(nxt, "whip", fps, True)}


def _ducked(s: dict) -> bool:
    return s["type"] == "video" and bool(s.get("liveAudio")) and s.get("duck") is not False


def music_volume(t: float, shots: list[dict], total: float) -> float:
    """현장 소리(liveAudio) 구간에서 음악을 줄이고 곡 끝 END_FADE초 동안 0으로. J/L컷은 소리 구간이 장면 밖으로 늘어난다."""
    v = 1.0
    for s in shots:
        if not _ducked(s):
            continue
        fade = s.get("duckFade", DUCK_FADE)
        a, b = s["start"] - s.get("jcut", 0), s["end"] - s.get("freeze", 0) + s.get("lcut", 0)
        w = min(max(0.0, (t - (a - fade)) / fade), max(0.0, (b + fade - t) / fade), 1.0)
        level = s.get("duck", DUCK)
        v = min(v, level + (1 - level) * (1 - w))  # 1-(1-level)*w는 부동소수 오차로 w=1에서 level과 어긋남
    return v * min(1.0, max(0.0, (total - t) / END_FADE))


def duck_lane(shots: list[dict], total: float, fade_end: float, step: float = 0.1) -> list[dict]:
    """music_volume을 HF volume 레인 점으로: 꺾이는 점 + 줄었다 커지는 구간 안은 step마다 (겹친 덕킹·끝 페이드 곱을 따라가게)."""
    ramps = [(max(0.0, fade_end - END_FADE), fade_end)]
    for s in shots:
        if _ducked(s):
            fd = s.get("duckFade", DUCK_FADE)
            a, b = s["start"] - s.get("jcut", 0), s["end"] - s.get("freeze", 0) + s.get("lcut", 0)
            ramps += [(a - fd, a), (b, b + fd)]
    points = {0.0, total}
    for a, b in ramps:
        n = max(1, math.ceil((b - a) / step))
        points |= {a + (b - a) * k / n for k in range(n + 1)}
    out = {}
    for t in sorted(p for p in points if 0 <= p <= total):
        out[round(t, 3)] = round(music_volume(t, shots, fade_end), 4)
    return [{"t": t, "v": v} for t, v in out.items()]


_KB = {"zoom-in": ((1.0, 0, 0), (1.1, 0, 0)), "zoom-out": ((1.1, 0, 0), (1.0, 0, 0)),
       "pan-left": ((1.08, 2, 0), (1.08, -2, 0)), "pan-right": ((1.08, -2, 0), (1.08, 2, 0)),
       "scroll-down": ((2.5, 0, 30), (2.5, 0, -30))}  # (배율, 가로 %, 세로 %) — render/src/kenburns.ts


def kenburns(kind: str) -> tuple[dict, dict] | None:
    """켄 번스 시작·끝 GSAP 값. CSS scale(s) translate(x%)와 같게 이동량에 배율을 곱한다 (GSAP는 이동 뒤 확대). still은 None."""
    if kind not in _KB:
        return None
    a, b = ({"scale": s, "xPercent": round(s * x, 4), "yPercent": round(s * y, 4)} for s, x, y in _KB[kind])
    return a, b


def collage_grid(n: int, landscape: bool) -> tuple[int, int]:
    """(열, 행): 2·3장은 화면 긴 쪽으로 나란히, 4장은 2x2."""
    if n >= 4:
        return 2, 2
    return (n, 1) if landscape else (1, n)


def credits_layout(n_lines: int, height: int) -> dict:
    size = round(height / 13)
    gap = size * 0.35
    return {"size": size, "gap": gap, "block": n_lines * size * 1.2 + (n_lines - 1) * gap}


def shot_name(src: str) -> str:
    return re.sub(r"\.[^.]+$", "", re.sub(r"^media/", "", src))


def shot_label(shot: dict, sec: float) -> str:
    """미리보기 이름표: 파일 이름(+ 영상이면 원본 몇 초)."""
    t = shot["type"]
    if t == "video":
        return f"{shot_name(shot['src'])} {shot['in'] + sec:.1f}초"
    if t == "photo":
        return shot_name(shot["src"])
    if t == "collage":
        return ", ".join(shot_name(x) for x in shot["srcs"])
    return "크레딧" if t == "credits" else "인트로/아웃트로 카드"
