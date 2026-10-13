"""최종 mp4 마스터링 — 2단계 loudnorm. 영상은 그대로 복사하되, bt709 태그가 없으면(키트 출력: ffmpeg·Chrome 기본 bt601 변환 + 태그 없음)
bt601→bt709로 다시 인코딩한다. 태그만 붙이면 bt601 값을 bt709로 읽어 색이 어긋난다."""
import json
import re
import subprocess
from pathlib import Path

from . import check, ff

TARGET_I, TARGET_TP, TARGET_LRA = -14.0, -1.5, 11.0  # TP는 점검 기준(-1)보다 0.5 여유
SILENCE_LUFS = -70.0
BT709 = ("bt709", "bt709", "bt709")
MATRIX = {"bt709": "bt709", "bt470bg": "bt470", "smpte170m": "smpte170m"}  # ffprobe color_space → scale 행렬 이름


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


def _color_args(space: str | None) -> list[str]:
    vf = (f"scale=in_color_matrix={MATRIX.get(space, 'bt601')}:out_color_matrix=bt709:out_range=tv,format=yuv420p,"
          "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv")
    return ["-vf", vf, "-c:v", "libx264", "-crf", "16", "-preset", "medium",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]


def master(path: Path) -> list[str]:
    """한 일: "color"(bt709로 다시 인코딩), "loudness"(음량). 둘 다 필요 없으면 파일을 건드리지 않는다."""
    info = check.media_info(path)
    color = info["color"] != BT709
    af = None
    if info["has_audio"]:
        m = measure(path)
        if needs_master(m):
            af = _loudnorm(f":measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
                           f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    if not color and not af:
        return []
    video = _color_args(info["color"][2]) if color else ["-c:v", "copy"]
    audio = ([] if not info["has_audio"] else
             ["-map", "0:a", "-af", af, "-ar", "48000", "-c:a", "aac", "-b:a", "320k"] if af else ["-map", "0:a", "-c:a", "copy"])
    tmp = path.with_name(path.stem + ".master" + path.suffix)
    try:
        # loudnorm은 끝에 소리를 0.1초쯤 덧붙인다 — 원래 길이로 자르지 않으면 점검의 길이 검사가 실패한다
        ff.run("-i", str(path), "-map", "0:v", *video, *audio, "-t", f"{info['duration']:.6f}", "-movflags", "+faststart", str(tmp))
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return [x for x, on in (("color", color), ("loudness", af)) if on]
