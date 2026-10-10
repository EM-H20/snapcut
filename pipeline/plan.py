"""selection.json + 분석 결과 → storyboard. 결정적 계산만 — 같은 입력이면 같은 타임라인."""
import statistics

FPS = 30
INTRO_SECONDS = 8.0
OUTRO_SECONDS = 11.0  # 아웃트로: 글씨 → 8초에 글씨가 사라짐 → 9초부터 화면이 어두워짐
MIN_INTRO_SECONDS = 1.5
CARD_SECONDS = 11.0  # 인트로/아웃트로 카드 mp4 길이 (render/src/ClipShot.tsx와 같아야 함)
OUTRO_DISSOLVE = 0.8  # 마지막 영상이 fadeOut이면 아웃트로 카드가 검은 화면에서 떠오르는 초
OUTRO_FADE = 2.0    # 아웃트로 카드 끝에서 검은 화면으로 페이드아웃하는 초
MAX_PER_COLLAGE = 2  # 자리가 모자랄 때 한 화면에 묶는 사진 수 상한 (3·4분할은 보기 답답함)
FORMATS = {
    # photo_seconds: 사진 한 장면 목표 길이. 비트 수로 고정하면 빠른 곡(172 BPM 등)에서 컷이 너무 빨라진다
    # per_collage: 자리가 모자랄 때 한 화면에 묶는 사진 수 상한. 릴스는 짧은 하이라이트라 묶지 않고 덜어낸다
    "reels": {"width": 1080, "height": 1920, "photo_seconds": 1.0, "per_collage": 1},
    "youtube": {"width": 1920, "height": 1080, "photo_seconds": 2.0, "per_collage": 1},
}
DEFAULT_KEN_BURNS = "still"  # 기본은 멈춘 사진. 확대·이동은 어지럽다는 반응이라 지정한 사진만 움직인다
KEN_BURNS_ANY = ["zoom-in", "zoom-out", "pan-left", "pan-right", "still", "scroll-down"]  # still: 멈춘 사진 (사진 피날레), scroll-down: 세로로 긴 사진(4컷) 확대해 위→아래
SECTION_NAMES = ("브릿지", "브레이크", "마지막후렴", "피날레")  # {"at": 이름} 마커로 쓰는 곡 구간
FINALE_BARS = 8  # 피날레 = 마지막후렴 + 이 마디 수 (selection "finaleBars"로 덮어씀)


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
    shots, i = [], 0
    for k, it in enumerate(items):
        if i >= len(grid) - 1:
            return shots, len(items) - k
        if it["type"] != "video":  # photo 또는 collage
            j = min(i + it.get("photoBeats", beats_per_photo * it.get("span", 1)), len(grid) - 1)
            shots.append({**{k: v for k, v in it.items() if k not in ("solo", "photoBeats", "span", "portrait")}, "start": grid[i], "end": grid[j],
                          "kenBurns": it.get("kenBurns") or DEFAULT_KEN_BURNS})
        else:
            n = max(1, round((it["out"] - it["in"]) / interval))
            if k > 0 and 2 * (len(grid) - 1 - i) < n:  # 남은 자리가 절반도 안 되면 잘라 넣지 않는다 (0.3초 번쩍 방지)
                return shots, len(items) - k
            j = min(i + n, len(grid) - 1)
            while j > i + 1 and grid[j] - grid[i] > it["duration"]:
                j -= 1
            length = grid[j] - grid[i]
            vin = min(it["in"], max(0.0, it["duration"] - length))
            shots.append({"type": "video", "src": it["src"], "start": grid[i], "end": grid[j],
                          "in": round(vin, 3), "out": round(vin + length, 3), "liveAudio": it["liveAudio"],
                          **{key: it[key] for key in ("rotate", "dissolve", "duck", "duckFade", "blur", "fadeOut") if key in it}})
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


def group_photos(items: list, size: int) -> list:
    """이웃한 세로 사진을 2~size장씩 한 화면(collage)에 나란히 묶는다 (16:9에서 세로 사진 한 장은 양옆이 텅 빈다).
    가로 사진은 혼자 크게 보이는 게 낫다 — 묶지 않는다. 영상·마커·세로 사진·solo·kenBurns/photoBeats를 지정한 사진(피날레 등)에서 끊긴다.
    한 화면은 사진 두 장 몫(span 2)의 시간을 쓴다 — 장면이 줄어도 곡 길이를 채운다."""
    out, run = [], []

    def flush():
        n_groups = -(-len(run) // size)
        k = 0
        for g in range(n_groups):
            cnt = len(run) // n_groups + (g < len(run) % n_groups)
            part = run[k:k + cnt]
            k += cnt
            out.append(part[0] if cnt == 1 else {"type": "collage", "srcs": [x["src"] for x in part], "span": 2})
        run.clear()

    for it in items:
        if it["type"] == "photo" and it.get("portrait") and not (it.get("solo") or it.get("kenBurns")):
            run.append(it)
        else:
            flush()
            out.append(it)
    flush()
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
        keep = subsample(packed, len(keep) - 1)  # 하나씩: 긴 영상이 있으면 left 개수만큼 덜면 너무 많이 빠진다
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
    interval = statistics.median([b - a for a, b in zip(beats, beats[1:])])
    # 곡 끝 페이드 구간엔 비트가 안 잡힌다: 마지막 비트 간격으로 격자를 이어 그 시간도 장면에 쓴다
    n_tail = int((limit - beats[-1]) / interval + 1e-6) if beats[-1] < limit else 0
    beats = list(beats) + [round(beats[-1] + k * interval, 3) for k in range(1, n_tail + 1)]
    segs = [[start, [], beats_per_photo]]
    for it in items:
        if it["type"] != "mark":
            segs[-1][1].append(it)
        elif segs[-1][0] < it["at"] < limit:  # 곡 구간 밖 마커(릴스 등)는 무시
            bpp = it["photoBeats"] if "photoBeats" in it else \
                max(1, round(it["photoSeconds"] / interval)) if "photoSeconds" in it else beats_per_photo
            if segs[-1][1]:
                segs.append([it["at"], [], bpp])
            elif len(segs) > 1:
                segs[-1][0], segs[-1][2] = it["at"], bpp
    shots, dropped = [], 0
    for n, (s, seg, seg_bpp) in enumerate(segs):
        last = n == len(segs) - 1
        e = limit if last else segs[n + 1][0]
        grid = [s] + [b for b in beats if s + 1e-6 < b < e - 1e-6] + ([b for b in beats if abs(b - e) <= 1e-6] if last else [e])
        part, d = fit(seg, grid, s, e, seg_bpp, per_collage)
        shots += part if last else _stretch(part, e)
        dropped += d
    return shots, dropped


def selected_formats(selection: dict) -> list[str]:
    formats = selection.get("formats") or list(FORMATS)
    if not (isinstance(formats, list) and all(isinstance(f, str) for f in formats)):
        raise ValueError(f'selection.json의 formats는 문자열 목록이어야 합니다 (예: ["reels", "youtube"]): {formats!r}')
    return formats


def card_video(selection: dict, key: str, candidates: list[dict]) -> tuple[str, float] | None:
    """introVideo/outroVideo: 카드 배경으로 쓸 후보(영상이면 시작 초부터 3초, 사진이면 멈춘 사진). 없으면 None."""
    spec = selection.get(key)
    if spec is None:
        return None
    cid = spec.get("id") if isinstance(spec, dict) else None
    if not (isinstance(cid, int) and 0 <= cid < len(candidates)):
        raise ValueError(f'{key}: 후보 번호가 필요합니다 (예: {{"id": 12, "in": 2.0}})')
    c, vin = candidates[cid], float(spec.get("in", 0.0))
    if c["type"] == "photo":
        return c["file"], 0.0
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
            at = sel["at"]
            if isinstance(at, str):
                if at not in SECTION_NAMES:
                    raise ValueError(f"items[{k}]: 알 수 없는 구간 이름 {at!r} (가능: {', '.join(SECTION_NAMES)})")
            elif isinstance(at, bool) or not isinstance(at, (int, float)):
                raise ValueError(f'items[{k}]: at은 곡 기준 초나 구간 이름이어야 합니다 (예: {{"at": 126.7}}, {{"at": "브릿지"}}): {at!r}')
            ps, pb = sel.get("photoSeconds"), sel.get("photoBeats")
            if ps is not None and (isinstance(ps, bool) or not isinstance(ps, (int, float)) or ps <= 0):
                raise ValueError(f"items[{k}]: photoSeconds는 양수 초여야 합니다: {ps!r}")
            if pb is not None and (isinstance(pb, bool) or not isinstance(pb, int) or pb <= 0):
                raise ValueError(f"items[{k}]: photoBeats는 양의 정수여야 합니다: {pb!r}")
            items.append({"type": "mark", "at": at if isinstance(at, str) else float(at),
                          **({"photoSeconds": float(ps)} if ps else {}), **({"photoBeats": pb} if pb else {})})
            continue
        if "ids" in sel:  # 지정한 사진들을 한 분할 화면에 (순서대로 왼쪽→오른쪽). 피날레처럼 자동 묶기를 안 쓰는 곳에서 쓴다
            ids = sel["ids"]
            if not (isinstance(ids, list) and 2 <= len(ids) <= 3 and all(isinstance(i, int) and 0 <= i < len(candidates) and
                                                                        candidates[i]["type"] == "photo" for i in ids)):
                raise ValueError(f'items[{k}]: ids는 사진 후보 번호 2~3개여야 합니다 (예: {{"ids": [96, 98]}}): {ids!r}')
            kb = sel.get("kenBurns")
            if kb is not None and kb not in KEN_BURNS_ANY:
                raise ValueError(f"items[{k}]: kenBurns는 {KEN_BURNS_ANY} 중 하나여야 합니다: {kb!r}")
            items.append({"type": "collage", "srcs": [candidates[i]["file"] for i in ids], "span": 2,
                          **({"photoBeats": sel["photoBeats"]} if isinstance(sel.get("photoBeats"), int) and sel["photoBeats"] > 0 else {}),
                          **({"kenBurns": kb} if kb else {})})
            continue
        cid = sel.get("id")
        if not (isinstance(cid, int) and 0 <= cid < len(candidates)):
            raise ValueError(f"items[{k}]: 후보 번호 {cid!r}가 없습니다 (0~{len(candidates) - 1})")
        c = candidates[cid]
        dis = sel.get("dissolve")
        if dis is not None and (isinstance(dis, bool) or not isinstance(dis, (int, float)) or not 0 < dis <= 1.0):
            raise ValueError(f"items[{k}]: dissolve는 0~1초여야 합니다 (앞 장면 위로 서서히 겹쳐 들어오는 길이): {dis!r}")
        fade = {"dissolve": float(dis)} if dis else {}
        blur = sel.get("blur")
        if blur is not None and (isinstance(blur, bool) or not isinstance(blur, (int, float)) or not 0 < blur <= 1.5):
            raise ValueError(f"items[{k}]: blur는 0~1.5초여야 합니다 (앞 장면에서 흐려졌다 선명해지는 전환 길이): {blur!r}")
        if blur:
            fade["blur"] = float(blur)
        if c["type"] == "photo":
            kb = sel.get("kenBurns")
            if kb is not None and kb not in KEN_BURNS_ANY:
                raise ValueError(f"items[{k}]: kenBurns는 {KEN_BURNS_ANY} 중 하나여야 합니다: {kb!r}")
            pb = sel.get("photoBeats")  # 이 사진만 길게/짧게 (4컷 사진 등). 분할 화면으로 묶지 않는다
            if pb is not None and (isinstance(pb, bool) or not isinstance(pb, int) or pb <= 0):
                raise ValueError(f"items[{k}]: photoBeats는 양의 정수여야 합니다: {pb!r}")
            items.append({"type": "photo", "src": c["file"], **({"portrait": True} if c.get("height", 0) > c.get("width", 0) else {}),
                          **({"solo": True} if sel.get("solo") or pb else {}),
                          **({"photoBeats": pb} if pb else {}), **({"kenBurns": kb} if kb else {}), **fade})
            continue
        sug = highlights.get(c["file"], {}).get("suggested") or {"in": 0.0, "out": min(4.0, c["duration"]), "liveAudio": False}
        vin, vout = float(sel.get("in", sug["in"])), float(sel.get("out", sug["out"]))
        if not 0 <= vin < vout <= c["duration"] + 0.01:
            raise ValueError(f"items[{k}]: 구간 {vin}~{vout}초가 영상 길이 {c['duration']}초를 벗어납니다")
        live = bool(sel.get("liveAudio", selection.get("liveAudio", sug["liveAudio"]))) and bool(c.get("has_audio"))
        duck = sel.get("duck", selection.get("duck", True))  # 최상위 "duck": false = 모든 영상에서 음악을 줄이지 않음
        if not (isinstance(duck, bool) or (isinstance(duck, (int, float)) and 0 < duck < 1)):
            raise ValueError(f"items[{k}]: duck은 true/false나 0~1 사이 음악 볼륨이어야 합니다 (false면 현장 소리 구간에도 음악을 줄이지 않음, 0.6이면 60%로만 줄임): {duck!r}")
        df = sel.get("duckFade")
        if df is not None and (isinstance(df, bool) or not isinstance(df, (int, float)) or not 0.1 <= df <= 4.0):
            raise ValueError(f"items[{k}]: duckFade는 0.1~4초여야 합니다 (현장 소리 앞뒤로 음악이 서서히 줄었다 커지는 길이): {df!r}")
        if df:
            fade["duckFade"] = float(df)
        fo = sel.get("fadeOut")
        if fo is not None and (isinstance(fo, bool) or not isinstance(fo, (int, float)) or not 0 < fo <= 3.0):
            raise ValueError(f"items[{k}]: fadeOut은 0~3초여야 합니다 (영상 끝에서 검은 화면으로 서서히 어두워지는 길이): {fo!r}")
        if fo:
            fade["fadeOut"] = float(fo)
        rot = sel.get("rotate")
        if rot is not None and rot not in (90, -90, 180):
            raise ValueError(f"items[{k}]: rotate는 90, -90, 180 중 하나여야 합니다 (옆으로 찍힌 영상 바로 세우기): {rot!r}")
        items.append({"type": "video", "src": c["file"], "in": vin, "out": vout,
                      "duration": c["duration"], "liveAudio": live, **({"rotate": rot} if rot else {}), **fade,
                      **({} if duck is True else {"duck": float(duck)} if duck and duck is not True else {"duck": False})})
    return items


def build_format(fmt: str, items: list[dict], music: dict, cards: dict, photo_seconds: float | None = None,
                 credits: dict | None = None, photo_group: int = 0, outro_dissolve: float = 0.0) -> dict:
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
    short = len(items) - len(usable)
    beats_per_photo = max(1, round((photo_seconds or spec["photo_seconds"]) / interval))
    usable = [dict(it, at=round(it["at"] - m_start, 3)) if it["type"] == "mark" else it for it in usable]
    if fmt == "youtube" and photo_group >= 2:
        usable = group_photos(usable, photo_group)
    shots, dropped = place_segments(usable, beats, intro_end, (m_end - m_start) - OUTRO_SECONDS, beats_per_photo,
                                    spec["per_collage"])
    dropped += short
    if not shots:
        raise ValueError(f"{fmt}: 넣을 수 있는 장면이 없습니다 — 곡이 너무 짧거나 고른 항목이 없습니다")
    content_end = shots[-1]["end"]
    total = round(content_end + OUTRO_SECONDS, 3)  # 사진이 모자라면 음악을 여기서 끝냄
    outro = {"type": "clip", "src": cards["outro"], "start": content_end, "end": total, "fadeOut": OUTRO_FADE,
             **({"dissolve": outro_dissolve} if outro_dissolve else {"dissolve": OUTRO_DISSOLVE} if shots[-1].get("fadeOut") else {})}
    # 마지막 영상이 검게 사라지면 카드도 검은 화면에서 떠오른다. outroDissolve면 마지막 장면(사진)이 카드로 서서히 바뀐다
    timeline = [{"type": "clip", "src": cards["intro"], "start": 0.0, "end": intro_end}] + shots + [outro]
    fade_end = total  # 음악은 여기서 페이드아웃이 끝난다
    if credits:  # 노래가 끝난 뒤 멤버별 역할 크레딧 (참고 영상 문법) — 영상 자체 소리만
        end = round(total + credits["seconds"], 3)
        timeline.append({"type": "credits", "src": credits["src"], "in": credits["in"],
                         "out": round(credits["in"] + credits["seconds"], 3), "lines": credits["lines"],
                         "start": total, "end": end, "liveAudio": True})
        total = end
    return {"width": spec["width"], "height": spec["height"], "musicStart": m_start,
            "musicEnd": round(m_start + total, 3), "musicFadeEnd": fade_end, "shots": timeline, "dropped": dropped}


def resolve_credits(selection: dict, candidates: list[dict]) -> dict | None:
    """{"lines": [...], "video": {"id": n, "in": s}, "seconds": 12} → 크레딧 장면 정보. 없으면 None."""
    spec = selection.get("credits")
    if spec is None:
        return None
    ex = '예: {"lines": ["Special 땡스", "운전 OO"], "video": {"id": 12, "in": 0.0}, "seconds": 12}'
    if not isinstance(spec, dict):
        raise ValueError(f"selection.json의 credits는 객체여야 합니다 ({ex})")
    lines, sec = spec.get("lines"), spec.get("seconds", 12)
    if not (isinstance(lines, list) and lines and all(isinstance(x, str) and x for x in lines)):
        raise ValueError(f"credits.lines는 글자 줄 목록이어야 합니다 ({ex})")
    if isinstance(sec, bool) or not isinstance(sec, (int, float)) or not 3 <= sec <= 30:
        raise ValueError(f"credits.seconds는 3~30초여야 합니다: {sec!r}")
    v = spec.get("video") if isinstance(spec.get("video"), dict) else {}
    cid, vin = v.get("id"), float(v.get("in", 0.0))
    if not (isinstance(cid, int) and 0 <= cid < len(candidates) and candidates[cid]["type"] == "video"):
        raise ValueError(f"credits.video는 영상 후보 번호여야 합니다 ({ex})")
    if not 0 <= vin <= candidates[cid]["duration"] - sec:
        raise ValueError(f"credits.video: {vin}초부터 {sec}초가 영상 길이 {candidates[cid]['duration']}초를 벗어납니다")
    return {"src": candidates[cid]["file"], "in": vin, "seconds": float(sec), "lines": lines}


def resolve_sections(music: dict, finale_bars: int, override: dict | None = None) -> dict:
    """분석 sections (+ selection "sections"로 직접 고친 값) + 피날레(마지막후렴 + N마디 첫 박) → 이름별 곡 시각."""
    override = override or {}
    sec = dict(music.get("sections") or {})
    estimated = [n for n in sec.get("estimated", []) if n not in override]
    sec.update({k: v for k, v in override.items() if k != "피날레"})
    db = music.get("downbeats") or []
    final = sec.get("마지막후렴")
    finale = None
    if "피날레" in override:
        finale = override["피날레"]
    elif final is not None and db:
        k = min(range(len(db)), key=lambda i: abs(db[i] - final)) + finale_bars
        finale = db[k] if k < len(db) else None
        if "마지막후렴" in estimated:
            estimated.append("피날레")  # 추정 후렴에서 나온 피날레도 추정
    out = {name: sec.get(name) for name in SECTION_NAMES[:3]}
    out["피날레"] = finale
    out["estimated"] = estimated
    return out


def _section_override(selection: dict) -> dict:
    ov = selection.get("sections") or {}
    ex = '예: {"sections": {"마지막후렴": 160.2}}'
    if not isinstance(ov, dict) or any(k not in SECTION_NAMES for k in ov) or \
            any(isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0 for v in ov.values()):
        raise ValueError(f"selection.json의 sections는 구간 이름({', '.join(SECTION_NAMES)}) → 곡 기준 초여야 합니다 ({ex}): {ov!r}")
    return {k: float(v) for k, v in ov.items()}


def build_storyboard(selection: dict, candidates: list[dict], highlights: dict, music: dict,
                     music_src: str, cards: dict) -> dict:
    formats = selected_formats(selection)
    unknown = [f for f in formats if f not in FORMATS]
    if unknown:
        raise ValueError(f"알 수 없는 형식: {unknown} (가능: {list(FORMATS)})")
    items = resolve_items(selection, candidates, highlights)
    bars = selection.get("finaleBars", FINALE_BARS)
    if isinstance(bars, bool) or not isinstance(bars, int) or bars < 0:
        raise ValueError(f"selection.json의 finaleBars는 0 이상의 정수여야 합니다: {bars!r}")
    sections = resolve_sections(music, bars, _section_override(selection))
    # 이름 마커 → 초. 곡 밖이거나, 앞 마커보다 이르면(추정값끼리 순서가 뒤집힘 등) 놓을 수 없으니 빼고 보고한다
    limit, prev, ignored, kept = music["duration"] - OUTRO_SECONDS, float("-inf"), [], []
    for it in items:
        if it["type"] == "mark":
            name = it["at"] if isinstance(it["at"], str) else None
            t = sections[name] if name else it["at"]
            if name and (t is None or t >= limit or t <= prev):
                ignored.append(name)
                continue
            prev = t
            it = dict(it, at=t)
        kept.append(it)
    items, ignored = kept, sorted(set(ignored))
    credits = resolve_credits(selection, candidates)
    pace = selection.get("photoSeconds") or {}
    if not (isinstance(pace, dict) and all(isinstance(v, (int, float)) and v > 0 for v in pace.values())):
        raise ValueError(f'selection.json의 photoSeconds는 형식별 양수 초여야 합니다 (예: {{"youtube": 2.5}}): {pace!r}')
    od = selection.get("outroDissolve", 0)
    if isinstance(od, bool) or not isinstance(od, (int, float)) or not 0 <= od <= 3:
        raise ValueError(f"selection.json의 outroDissolve는 0~3초여야 합니다 (마지막 장면이 아웃트로 카드로 서서히 바뀌는 길이): {od!r}")
    pg = selection.get("photoGroup", 0)
    if isinstance(pg, bool) or not isinstance(pg, int) or pg == 1 or not 0 <= pg <= 3:
        raise ValueError(f"selection.json의 photoGroup은 0(끔) 또는 2~3이어야 합니다 (유튜브에서 이웃한 사진을 한 화면에 묶는 최대 장수): {pg!r}")
    return {"fps": FPS, "title": selection.get("title", ""), "ending": selection.get("ending", ""),
            "music": music_src, "sections": dict(sections, ignored=ignored),
            "formats": {f: build_format(f, items, music, cards[f], pace.get(f), credits if f == "youtube" else None, pg, float(od))
                        for f in formats}}
