"""selection.json + 분석 결과 → storyboard. 결정적 계산만 — 같은 입력이면 같은 타임라인."""
import statistics

FPS = 30
INTRO_SECONDS = 3.0
OUTRO_SECONDS = 3.0
MIN_INTRO_SECONDS = 1.5
FORMATS = {
    "reels": {"width": 1080, "height": 1920, "beats_per_photo": 2},
    "youtube": {"width": 1920, "height": 1080, "beats_per_photo": 4},
}
KEN_BURNS = ["zoom-in", "pan-left", "zoom-out", "pan-right"]


def subsample(items: list, n: int) -> list:
    if n >= len(items):
        return list(items)
    if n <= 0:
        return []
    if n == 1:
        return [items[0]]
    return [items[round(k * (len(items) - 1) / (n - 1))] for k in range(n)]


def place(items: list, beats: list[float], start: float, end: float, beats_per_photo: int) -> tuple[list[dict], int]:
    grid = [b for b in beats if start - 1e-6 <= b <= end + 1e-6]
    interval = statistics.median([b - a for a, b in zip(grid, grid[1:])]) if len(grid) > 1 else 0.5
    shots, i, photo_no = [], 0, 0
    for k, it in enumerate(items):
        if i >= len(grid) - 1:
            return shots, len(items) - k
        if it["type"] == "photo":
            j = min(i + beats_per_photo, len(grid) - 1)
            shots.append({"type": "photo", "src": it["src"], "start": grid[i], "end": grid[j],
                          "kenBurns": KEN_BURNS[photo_no % len(KEN_BURNS)]})
            photo_no += 1
        else:
            n = max(1, round((it["out"] - it["in"]) / interval))
            j = min(i + n, len(grid) - 1)
            while j > i + 1 and grid[j] - grid[i] > it["duration"]:
                j -= 1
            length = grid[j] - grid[i]
            vin = min(it["in"], max(0.0, it["duration"] - length))
            shots.append({"type": "video", "src": it["src"], "start": grid[i], "end": grid[j],
                          "in": round(vin, 3), "out": round(vin + length, 3), "liveAudio": it["liveAudio"]})
        i = j
    return shots, 0


def fit(items: list, beats: list[float], start: float, end: float, beats_per_photo: int) -> tuple[list[dict], int]:
    keep = list(items)
    while True:
        shots, left = place(keep, beats, start, end, beats_per_photo)
        if left == 0:
            return shots, len(items) - len(keep)
        keep = subsample(items, len(keep) - left)


def resolve_items(selection: dict, candidates: list[dict], highlights: dict) -> list[dict]:
    items = []
    for k, sel in enumerate(selection.get("items", [])):
        cid = sel.get("id")
        if not (isinstance(cid, int) and 0 <= cid < len(candidates)):
            raise ValueError(f"items[{k}]: 후보 번호 {cid!r}가 없습니다 (0~{len(candidates) - 1})")
        c = candidates[cid]
        if c["type"] == "photo":
            items.append({"type": "photo", "src": c["file"]})
            continue
        sug = highlights.get(c["file"], {}).get("suggested") or {"in": 0.0, "out": min(4.0, c["duration"]), "liveAudio": False}
        vin, vout = float(sel.get("in", sug["in"])), float(sel.get("out", sug["out"]))
        if not 0 <= vin < vout <= c["duration"] + 0.01:
            raise ValueError(f"items[{k}]: 구간 {vin}~{vout}초가 영상 길이 {c['duration']}초를 벗어납니다")
        live = bool(sel.get("liveAudio", sug["liveAudio"])) and bool(c.get("has_audio"))
        items.append({"type": "video", "src": c["file"], "in": vin, "out": vout,
                      "duration": c["duration"], "liveAudio": live})
    return items


def build_format(fmt: str, items: list[dict], music: dict, cards: dict) -> dict:
    spec = FORMATS[fmt]
    m_start, m_end = (music["chorus"] if fmt == "reels" else (0.0, music["duration"]))
    beats = [round(b - m_start, 3) for b in music["beats"] if m_start <= b <= m_end]
    if len(beats) < 2:
        raise ValueError(f"{fmt}: 음악에서 비트를 찾지 못했습니다 — 다른 곡을 골라주세요")
    intro_end = max((b for b in beats if b <= INTRO_SECONDS), default=INTRO_SECONDS)
    if intro_end < MIN_INTRO_SECONDS:
        intro_end = next((b for b in beats if b >= MIN_INTRO_SECONDS), INTRO_SECONDS)
    shots, dropped = fit(items, beats, intro_end, (m_end - m_start) - OUTRO_SECONDS, spec["beats_per_photo"])
    if not shots:
        raise ValueError(f"{fmt}: 넣을 수 있는 장면이 없습니다 — 곡이 너무 짧거나 고른 항목이 없습니다")
    content_end = shots[-1]["end"]
    total = round(content_end + OUTRO_SECONDS, 3)  # 사진이 모자라면 음악을 여기서 끝냄
    timeline = ([{"type": "clip", "src": cards["intro"], "start": 0.0, "end": intro_end}] + shots +
                [{"type": "clip", "src": cards["outro"], "start": content_end, "end": total}])
    return {"width": spec["width"], "height": spec["height"], "musicStart": m_start,
            "musicEnd": round(m_start + total, 3), "shots": timeline, "dropped": dropped}


def build_storyboard(selection: dict, candidates: list[dict], highlights: dict, music: dict,
                     music_src: str, cards: dict) -> dict:
    formats = selection.get("formats") or list(FORMATS)
    unknown = [f for f in formats if f not in FORMATS]
    if unknown:
        raise ValueError(f"알 수 없는 형식: {unknown} (가능: {list(FORMATS)})")
    items = resolve_items(selection, candidates, highlights)
    return {"fps": FPS, "title": selection.get("title", ""), "ending": selection.get("ending", ""),
            "music": music_src, "formats": {f: build_format(f, items, music, cards[f]) for f in formats}}
