import json
import subprocess

import numpy as np


def run(*args: str) -> None:
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or f"ffmpeg 실패: {' '.join(args)}")


def probe(path) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True,
    )
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or f"ffprobe 실패: {path}")
    return json.loads(r.stdout)


def load_mono(path, sr: int = 22050) -> np.ndarray:
    """오디오 스트림을 모노 float32로. 오디오가 없는 파일은 호출 전에 걸러야 한다."""
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True,
    )
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors="replace").strip() or f"오디오 읽기 실패: {path}")
    return np.frombuffer(r.stdout, dtype="<f4")
