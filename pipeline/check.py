"""렌더된 mp4 품질 점검 — 엔진과 무관하게 완성 파일만 본다 (검은 프레임, 멈춤, 음량, 색 태그, 길이, 컷 시트)."""
import math
import re
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from . import ff

FRAME = 1 / 30
LUFS_RANGE = (-15.0, -13.0)
MAX_TRUE_PEAK = -1.0
DURATION_TOLERANCE = 0.1
CREDITS_FADE = 2.0
EDGE_SECONDS = 2.0  # 계획이 없을 때 처음·끝 이만큼의 검정은 페이드로 본다
STILL_OFFSET = 0.3
SHEET_COLS, SHEET_ROWS, CELL_W = 4, 3, 480
DRAWN_LUMA, DRAWN_SHARE = 80, 0.001  # 밝기 80/255 넘는 픽셀이 0.1% 이상이면 그려진 것이 있는 화면
VIDEO_FILTERS = "blackdetect=d=0.03:pix_th=0.10,freezedetect=n=0.001:d=0.15,scdet=t=12,metadata=print:key=lavfi.scd.time"


def parse_black(log: str) -> list[tuple[float, float]]:
    return [(float(a), float(b)) for a, b in re.findall(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)", log)]


def parse_freeze(log: str) -> list[tuple[float, float | None]]:
    starts = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", log)]
    return [(s, ends[i] if i < len(ends) else None) for i, s in enumerate(starts)]


def parse_cuts(log: str) -> list[float]:
    return [float(x) for x in re.findall(r"lavfi\.scd\.time[=:]\s*([\d.]+)", log)]


def parse_loudness(log: str) -> dict | None:
    i = re.findall(r"\bI:\s+(-?[\d.]+|-inf) LUFS", log)
    tp = re.search(r"True peak:\s+Peak:\s+(-?[\d.]+|-inf) dBFS", log)
    if "Summary:" not in log or not i or not tp:
        return None
    return {"I": float(i[-1]), "TP": float(tp.group(1))}


def plan_view(sb: dict | None, fmt: str | None) -> dict | None:
    if not sb or fmt not in sb.get("formats", {}):
        return None
    f = sb["formats"][fmt]
    if not isinstance(f, dict):
        return None  # 롱폼 shorts는 클립별 목록 — 형식 하나의 계획이 아니다
    if sb.get("mode") == "longform":
        return {"duration": f["duration"], "cuts": [c["start"] for c in f["clips"][1:]], "intended_black": [], "video_spans": []}
    shots = f["shots"]
    intended = []
    for i, s in enumerate(shots):
        if s.get("fadeOut"):
            nxt = shots[i + 1].get("dissolve", 0) if i + 1 < len(shots) else 0
            intended.append((round(s["end"] - s["fadeOut"], 3), round(s["end"] + nxt, 3)))
        if s["type"] == "credits":  # 크레딧은 마지막 2초를 항상 검게 덮는다 (hf/mv.py 크레딧)
            intended.append((round(s["end"] - CREDITS_FADE, 3), s["end"]))
    return {"duration": shots[-1]["end"], "cuts": [s["start"] for s in shots[1:]], "intended_black": intended,
            "video_spans": [(s["start"], round(s["end"] - s.get("freeze", 0), 3)) for s in shots if s["type"] == "video"]}


def format_of(path: Path, sb: dict | None) -> str | None:
    if not sb:
        return None
    return next((k for k in sb.get("formats", {}) if path.stem.endswith(f"_{k}")), None)


def judge(black, freezes, loud, info: dict, view: dict | None) -> list[dict]:
    issues = []
    dur = info["duration"]
    intended = view["intended_black"] if view else [(0.0, EDGE_SECONDS), (dur - EDGE_SECONDS, dur)]
    for a, b in black:
        if not any(x - FRAME <= a and b <= y + FRAME for x, y in intended):
            issues.append({"kind": "black", "at": a, "detail": f"{a:.3f}–{b:.3f}초 검은 화면"})
    for a, b in freezes:
        end = dur if b is None else b
        if any(a < y - 0.05 and end > x + 0.05 for x, y in (view["video_spans"] if view else [])):
            issues.append({"kind": "freeze", "at": a, "detail": f"{a:.3f}–{end:.3f}초 영상 멈춤"})
    if info["has_audio"]:
        if loud is None:
            issues.append({"kind": "loudness", "at": 0.0, "detail": "음량 측정 실패"})
        elif not (LUFS_RANGE[0] <= loud["I"] <= LUFS_RANGE[1] and loud["TP"] <= MAX_TRUE_PEAK):
            issues.append({"kind": "loudness", "at": 0.0,
                           "detail": f"{loud['I']:.1f} LUFS, true peak {loud['TP']:.1f} dBTP (기준 -14±1 LUFS, ≤ -1 dBTP)"})
    if info["color"] != ("bt709", "bt709", "bt709"):
        issues.append({"kind": "color", "at": 0.0, "detail": f"색 태그 {info['color']} (bt709 필요)"})
    if view and abs(dur - view["duration"]) > DURATION_TOLERANCE:
        issues.append({"kind": "duration", "at": 0.0, "detail": f"길이 {dur:.3f}초, 계획 {view['duration']:.3f}초"})
    return issues


def media_info(path: Path) -> dict:
    p = ff.probe(path)
    v = next(s for s in p["streams"] if s["codec_type"] == "video")
    return {"duration": float(p["format"]["duration"]),
            "has_audio": any(s["codec_type"] == "audio" for s in p["streams"]),
            "color": (v.get("color_primaries"), v.get("color_transfer"), v.get("color_space"))}


def _analyze(path: Path, has_audio: bool) -> str:
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vf", VIDEO_FILTERS]
    cmd += ["-af", "ebur128=peak=true"] if has_audio else ["-an"]
    r = subprocess.run([*cmd, "-f", "null", "-"], stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace")
    if r.returncode:
        raise RuntimeError(f"점검 실패: {path.name}: {r.stderr.strip()[-300:]}")
    return r.stderr


def make_sheets(path: Path, times: list[float], duration: float, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("sheet_*.jpg"):
        old.unlink()
    cells = []
    for i, t in enumerate(times):
        at = min(t + STILL_OFFSET, max(0.0, duration - FRAME))
        still = out_dir / f"still_{i:03d}.png"
        ff.run("-ss", f"{at:.3f}", "-i", str(path), "-frames:v", "1", "-vf", f"scale={CELL_W}:-2", str(still))
        img = Image.open(still).convert("RGB")
        still.unlink()
        ImageDraw.Draw(img).text((8, 8), f"#{i} {at:.2f}s", fill=(255, 255, 0))
        cells.append(img)
    per, sheets = SHEET_COLS * SHEET_ROWS, []
    for n in range(0, len(cells), per):
        group = cells[n:n + per]
        h = max(c.height for c in group)
        sheet = Image.new("RGB", (SHEET_COLS * CELL_W, math.ceil(len(group) / SHEET_COLS) * h))
        for k, c in enumerate(group):
            sheet.paste(c, ((k % SHEET_COLS) * CELL_W, (k // SHEET_COLS) * h))
        dst = out_dir / f"sheet_{n // per + 1:02d}.jpg"
        sheet.save(dst, quality=85)
        sheets.append(dst)
    return sheets


def _drawn(path: Path, t: float) -> bool:
    """그 시각 프레임에 밝은 무언가가 그려져 있는가. 어두운 화풍(얇은 선)은 blackdetect가 검정으로 본다(98% 픽셀이 어두움)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1", "-vf", "format=gray",
                          "-f", "rawvideo", "-"], stdin=subprocess.DEVNULL, capture_output=True).stdout
    px = np.frombuffer(raw, np.uint8)
    return px.size > 0 and float((px > DRAWN_LUMA).mean()) >= DRAWN_SHARE


def check_file(path: Path, view: dict | None, out_dir: Path) -> dict:
    info = media_info(path)
    log = _analyze(path, info["has_audio"])
    loud = parse_loudness(log) if info["has_audio"] else None
    black = [(a, b) for a, b in parse_black(log) if not _drawn(path, (a + b) / 2)]
    issues = judge(black, parse_freeze(log), loud, info, view)
    cuts = view["cuts"] if view else parse_cuts(log)
    sheets = make_sheets(path, [0.0, *cuts], info["duration"], out_dir)
    return {"ok": not issues, "issues": issues, "loudness": loud, "sheets": [str(p) for p in sheets]}


def summary(name: str, r: dict) -> str:
    head = f"점검 {'통과' if r['ok'] else '실패'}: {name}"
    loud = f" ({r['loudness']['I']:.1f} LUFS, peak {r['loudness']['TP']:.1f})" if r["loudness"] else ""
    return "\n".join([head + loud, *(f"  - {i['detail']}" for i in r["issues"]), f"  화면 시트: {', '.join(r['sheets'])}"])
