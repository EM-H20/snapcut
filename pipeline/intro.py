import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from .paths import SHARED

HYPERFRAMES = "hyperframes@0.8.140"
CARD_TIMEOUT = 600
ORIENTATION = {"reels": "portrait", "youtube": "landscape"}


def template_file(template: str, fmt: str) -> Path:
    path = SHARED / "인트로아웃트로" / template / f"{ORIENTATION[fmt]}.html"
    if not path.exists():
        raise FileNotFoundError(f"인트로/아웃트로 템플릿이 없습니다: {path}")
    return path


def render_card(template: str, fmt: str, text: str, sub: str, dst: Path, bg: Path | None = None,
                layout: str = "wide") -> None:
    """bg가 있으면 템플릿을 임시 폴더에 복사하고 bg.mp4로 넣어 렌더한다 (템플릿이 쓰면 배경 영상이 된다).
    layout: "center"면 글씨를 가운데로 모은다 (사진 배경의 검은 띠를 피함) — layout 변수를 선언한 템플릿에만 넘긴다."""
    comp = template_file(template, fmt)
    variables = {"text": text, "sub": sub}
    if '"id":"layout"' in comp.read_text(encoding="utf-8").replace(" ", ""):
        variables["layout"] = layout
    with tempfile.TemporaryDirectory() as tmp:
        if bg:
            work = Path(tmp) / "card"
            shutil.copytree(comp.parent, work)
            shutil.copyfile(bg, work / "bg.mp4")
            comp = work / comp.name
        _render(comp, variables, dst)


def _render(comp: Path, variables: dict, dst: Path) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(variables, f, ensure_ascii=False)
    try:
        r = subprocess.run(["npx", "-y", HYPERFRAMES, "render", str(comp.parent), "-c", comp.name, "-f", "30",
                            "-o", str(dst), "--variables-file", f.name, "--strict-variables", "--quiet"],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=CARD_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"HyperFrames 렌더가 {CARD_TIMEOUT}초 안에 끝나지 않았습니다. 네트워크(첫 실행 시 다운로드)를 확인하고 다시 실행하세요")
    finally:
        Path(f.name).unlink(missing_ok=True)
    if r.returncode:
        raise RuntimeError(f"HyperFrames 렌더 실패: {(r.stderr or r.stdout)[-800:]}")
