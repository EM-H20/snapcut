import json
import subprocess
import tempfile
from pathlib import Path

from .paths import SHARED

HYPERFRAMES = "hyperframes@0.8.140"
ORIENTATION = {"reels": "portrait", "youtube": "landscape"}


def template_file(template: str, fmt: str) -> Path:
    path = SHARED / "인트로아웃트로" / template / f"{ORIENTATION[fmt]}.html"
    if not path.exists():
        raise FileNotFoundError(f"인트로/아웃트로 템플릿이 없습니다: {path}")
    return path


def render_card(template: str, fmt: str, text: str, sub: str, dst: Path) -> None:
    comp = template_file(template, fmt)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"text": text, "sub": sub}, f, ensure_ascii=False)
    try:
        r = subprocess.run(["npx", "-y", HYPERFRAMES, "render", str(comp.parent), "-c", comp.name, "-f", "30",
                            "-o", str(dst), "--variables-file", f.name, "--strict-variables", "--quiet"],
                           capture_output=True, text=True)
    finally:
        Path(f.name).unlink(missing_ok=True)
    if r.returncode:
        raise RuntimeError(f"HyperFrames 렌더 실패: {(r.stderr or r.stdout)[-800:]}")
