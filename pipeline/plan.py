"""selection.json + 분석 결과 → storyboard. 결정적 계산만 — 같은 입력이면 같은 타임라인."""
import statistics

FPS = 30
INTRO_SECONDS = 3.0
OUTRO_SECONDS = 3.0
MIN_INTRO_SECONDS = 1.5
CARD_SECONDS = 3.0  # 인트로/아웃트로 카드 mp4 길이 (render/src/ClipShot.tsx와 같아야 함)
MAX_PER_COLLAGE = 2  # 자리가 모자랄 때 한 화면에 묶는 사진 수 상한 (3·4분할은 보기 답답함)
FORMATS = {
    # photo_seconds: 사진 한 장면 목표 길이. 비트 수로 고정하면 빠른 곡(172 BPM 등)에서 컷이 너무 빨라진다
    # per_collage: 자리가 모자랄 때 한 화면에 묶는 사진 수 상한. 릴스는 짧은 하이라이트라 묶지 않고 덜어낸다
    "reels": {"width": 1080, "height": 1920, "photo_seconds": 1.0, "per_collage": 1},
    "youtube": {"width": 1920, "height": 1080, "photo_seconds": 2.0, "per_collage": MAX_PER_COLLAGE},
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
        if it["type"] != "video":  # photo 또는 collage
            j = min(i + beats_per_photo, len(grid) - 1)
            shots.append({**{k: v for k, v in it.items() if k != "solo"}, "start": grid[i], "end": grid[j],
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


def _photo_srcs(it: dict) -> list[str]:
    return it.get("srcs") or [it["src"]]


def _count(items: list) -> int:
    return sum(len(_photo_srcs(it)) if it["type"] != "video" else 1 for it in items)


def pack(items: list, groups: int, per_collage: int = MAX_PER_COLLAGE) -> list:
    """사진들을 약 groups개 장면으로 고르게 묶는다. 이웃한 사진만 묶고(영상을 건너뛰지 않음) 묶음은 collage가 된다."""
    total = sum(it["type"] == "photo" for it in items)
    cuts = {round(j * total / groups) for j in range(1, groups)}
    out, n = [], 0
    for it in items:
        prev = out[-1] if out else None
        if it["type"] == "photo" and prev and prev["type"] != "video" and n not in cuts \
                and len(_photo_srcs(prev)) < per_collage and not it.get("solo") and not prev.get("solo"):
            out[-1] = {"type": "collage", "srcs": _photo_srcs(prev) + [it["src"]]}
        else:
            out.append(it)
        n += it["type"] == "photo"
    return out


def fit(items: list, beats: list[float], start: float, end: float, beats_per_photo: int,
        per_collage: int = MAX_PER_COLLAGE) -> tuple[list[dict], int]:
    """전부 넣는 게 우선: 자리가 모자라면 사진을 분할 화면으로 필요한 만큼만 묶고, 4장씩 묶어도 넘칠 때만 균등하게 뺀다."""
    photos = sum(it["type"] == "photo" for it in items)
    # ponytail: 묶음 수를 하나씩 줄여 가며 place를 다시 돈다(O(n²)). 사진 수천 장이면 이분 탐색으로
    for groups in range(photos, -(-photos // per_collage) - 1, -1):
        keep = packed = pack(items, groups, per_collage)
        shots, left = place(packed, beats, start, end, beats_per_photo)
        if left == 0:
            return shots, 0
    while left:
        keep = subsample(packed, len(keep) - left)
        shots, left = place(keep, beats, start, end, beats_per_photo)
    return shots, _count(items) - _count(keep)


def _stretch(shots: list, end: float) -> list:
    """마커 앞 구간이 일찍 끝나면 마지막 사진 장면을 늘려 마커까지 빈틈 없이 잇는다."""
    gap = round(end - shots[-1]["end"], 3) if shots else 0.0
    k = next((n for n in range(len(shots) - 1, -1, -1) if shots[n]["type"] != "video"), None)
    if gap <= 0 or k is None:
        return shots  # ponytail: 영상만 있는 구간은 빈틈이 남는다 — 사진을 하나 섞으면 해결
    return shots[:k] + [dict(shots[k], end=round(shots[k]["end"] + gap, 3))] + \
        [dict(x, start=round(x["start"] + gap, 3), end=round(x["end"] + gap, 3)) for x in shots[k + 1:]]


def place_segments(items: list, beats: list[float], start: float, limit: float, beats_per_photo: int,
                   per_collage: int) -> tuple[list[dict], int]:
    """{"at": 초} 마커로 나눈 구간마다 따로 배치한다. 마커 다음 항목은 정확히 그 시각에 시작한다 (비트 쪼개짐·브릿지 맞추기)."""
    segs = [[start, []]]
    for it in items:
        if it["type"] != "mark":
            segs[-1][1].append(it)
        elif segs[-1][0] < it["at"] < limit:  # 곡 구간 밖 마커(릴스 등)는 무시
            if segs[-1][1]:
                segs.append([it["at"], []])
            elif len(segs) > 1:
                segs[-1][0] = it["at"]
    shots, dropped = [], 0
    for n, (s, seg) in enumerate(segs):
        last = n == len(segs) - 1
        e = limit if last else segs[n + 1][0]
        grid = [s] + [b for b in beats if s + 1e-6 < b < e - 1e-6] + ([b for b in beats if abs(b - e) <= 1e-6] if last else [e])
        part, d = fit(seg, grid, s, e, beats_per_photo, per_collage)
        shots += part if last else _stretch(part, e)
        dropped += d
    return shots, dropped


def selected_formats(selection: dict) -> list[str]:
    formats = selection.get("formats") or list(FORMATS)
    if not (isinstance(formats, list) and all(isinstance(f, str) for f in formats)):
        raise ValueError(f'selection.json의 formats는 문자열 목록이어야 합니다 (예: ["reels", "youtube"]): {formats!r}')
    return formats


def card_video(selection: dict, key: str, candidates: list[dict]) -> tuple[str, float] | None:
    """introVideo/outroVideo: 카드 배경으로 쓸 영상 후보와 시작 초. 없으면 None."""
    spec = selection.get(key)
    if spec is None:
        return None
    cid = spec.get("id") if isinstance(spec, dict) else None
    if not (isinstance(cid, int) and 0 <= cid < len(candidates) and candidates[cid]["type"] == "video"):
        raise ValueError(f'{key}: 영상 후보 번호가 필요합니다 (예: {{"id": 12, "in": 2.0}})')
    c, vin = candidates[cid], float(spec.get("in", 0.0))
    if not 0 <= vin <= c["duration"] - CARD_SECONDS:
        raise ValueError(f"{key}: {vin}초부터 {CARD_SECONDS:g}초가 영상 길이 {c['duration']}초를 벗어납니다")
    return c["file"], vin


def resolve_items(selection: dict, candidates: list[dict], highlights: dict) -> list[dict]:
    raw = selection.get("items", [])
    if not (isinstance(raw, list) and all(isinstance(s, dict) for s in raw)):
        raise ValueError('selection.json의 items는 객체 목록이어야 합니다 (예: [{"id": 0}, {"id": 3}])')
    items = []
    for k, sel in enumerate(raw):
        if "at" in sel:
            if isinstance(sel["at"], bool) or not isinstance(sel["at"], (int, float)):
                raise ValueError(f'items[{k}]: at은 곡 기준 초여야 합니다 (예: {{"at": 126.7}}): {sel["at"]!r}')
            items.append({"type": "mark", "at": float(sel["at"])})
            continue
        cid = sel.get("id")
        if not (isinstance(cid, int) and 0 <= cid < len(candidates)):
            raise ValueError(f"items[{k}]: 후보 번호 {cid!r}가 없습니다 (0~{len(candidates) - 1})")
        c = candidates[cid]
        if c["type"] == "photo":
            items.append({"type": "photo", "src": c["file"], **({"solo": True} if sel.get("solo") else {})})
            continue
        sug = highlights.get(c["file"], {}).get("suggested") or {"in": 0.0, "out": min(4.0, c["duration"]), "liveAudio": False}
        vin, vout = float(sel.get("in", sug["in"])), float(sel.get("out", sug["out"]))
        if not 0 <= vin < vout <= c["duration"] + 0.01:
            raise ValueError(f"items[{k}]: 구간 {vin}~{vout}초가 영상 길이 {c['duration']}초를 벗어납니다")
        live = bool(sel.get("liveAudio", sug["liveAudio"])) and bool(c.get("has_audio"))
        items.append({"type": "video", "src": c["file"], "in": vin, "out": vout,
                      "duration": c["duration"], "liveAudio": live})
    return items


def build_format(fmt: str, items: list[dict], music: dict, cards: dict, photo_seconds: float | None = None) -> dict:
    spec = FORMATS[fmt]
    m_start, m_end = (music["chorus"] if fmt == "reels" else (0.0, music["duration"]))
    beats = [round(b - m_start, 3) for b in music["beats"] if m_start <= b <= m_end]
    if len(beats) < 2:
        raise ValueError(f"{fmt}: 음악에서 비트를 찾지 못했습니다 — 다른 곡을 골라주세요")
    intro_end = max((b for b in beats if b <= INTRO_SECONDS), default=0.0)
    if intro_end < MIN_INTRO_SECONDS:
        intro_end = next((b for b in beats if b >= MIN_INTRO_SECONDS), INTRO_SECONDS)
    interval = statistics.median([b - a for a, b in zip(beats, beats[1:])])
    usable = [it for it in items if it["type"] != "video" or it["duration"] >= interval]  # 한 비트보다 짧은 영상은 제외
    beats_per_photo = max(1, round((photo_seconds or spec["photo_seconds"]) / interval))
    usable = [dict(it, at=round(it["at"] - m_start, 3)) if it["type"] == "mark" else it for it in usable]
    shots, dropped = place_segments(usable, beats, intro_end, (m_end - m_start) - OUTRO_SECONDS, beats_per_photo,
                                    spec["per_collage"])
    dropped += len(items) - len(usable)
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
    formats = selected_formats(selection)
    unknown = [f for f in formats if f not in FORMATS]
    if unknown:
        raise ValueError(f"알 수 없는 형식: {unknown} (가능: {list(FORMATS)})")
    items = resolve_items(selection, candidates, highlights)
    pace = selection.get("photoSeconds") or {}
    if not (isinstance(pace, dict) and all(isinstance(v, (int, float)) and v > 0 for v in pace.values())):
        raise ValueError(f'selection.json의 photoSeconds는 형식별 양수 초여야 합니다 (예: {{"youtube": 2.5}}): {pace!r}')
    return {"fps": FPS, "title": selection.get("title", ""), "ending": selection.get("ending", ""),
            "music": music_src, "formats": {f: build_format(f, items, music, cards[f], pace.get(f)) for f in formats}}
