"""최종 mp4 음량 마스터링 — 2단계 loudnorm, 영상 스트림은 그대로 복사한다."""
import json
import re
import subprocess
from pathlib import Path

from . import check, ff

TARGET_I, TARGET_TP, TARGET_LRA = -14.0, -1.5, 11.0  # TP는 점검 기준(-1)보다 0.5 여유
SILENCE_LUFS = -70.0


def _loudnorm(extra: str = "") -> str:
    return f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}{extra}"


def measure(path: Path) -> dict:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn", "-af", _loudnorm(":print_format=json"),
                        "-f", "null", "-"], stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace")
    blocks = re.findall(r"\{[^{}]*\}", r.stderr)
    if r.returncode or not blocks:
        raise RuntimeError(f"음량 측정 실패: {path.name}")
    return json.loads(blocks[-1])


def needs_master(m: dict) -> bool:
    i, tp = float(m["input_i"]), float(m["input_tp"])
    if i < SILENCE_LUFS:
        return False  # 무음 트랙은 키워 봐야 잡음뿐 — 점검이 따로 알린다
    return not (check.LUFS_RANGE[0] <= i <= check.LUFS_RANGE[1] and tp <= check.MAX_TRUE_PEAK)


def master(path: Path) -> bool:
    if not check.media_info(path)["has_audio"]:
        return False
    m = measure(path)
    if not needs_master(m):
        return False
    tmp = path.with_name(path.stem + ".master" + path.suffix)
    af = _loudnorm(f":measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
                   f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    try:
        ff.run("-i", str(path), "-map", "0:v", "-map", "0:a", "-c:v", "copy", "-af", af, "-ar", "48000",
               "-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart", str(tmp))
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return True
