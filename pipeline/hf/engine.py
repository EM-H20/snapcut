"""HyperFrames 실행: 렌더·미리보기, 프리즈 프레임용 정지 사진 뽑기."""
import subprocess
from pathlib import Path

from .. import ff, kits
from . import mv

HF = f"hyperframes@{kits.HF_VERSION}"
RENDER_TIMEOUT = 3600


def render(root: Path, comp: str, out: Path, hf: str = HF, workers: int | None = None) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    w = ["-w", str(workers)] if workers else []
    try:
        r = subprocess.run(["npx", "-y", hf, "render", str(root), "-c", comp, "-f", "30", *w, "-o", str(out), "--quiet"],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=RENDER_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"HyperFrames 렌더가 {RENDER_TIMEOUT // 60}분 안에 끝나지 않았습니다 ({out.name})")
    if r.returncode:
        raise RuntimeError(f"HyperFrames 렌더 실패 ({out.name}): {(r.stderr or r.stdout)[-800:]}")


def preview(root: Path, hf: str = HF) -> None:
    """root/index.html을 HF Studio로 띄운다 (끝날 때까지 돈다 — 백그라운드로 실행)."""
    subprocess.run(["npx", "-y", hf, "preview", str(root)])


def freeze_stills(root: Path, fmt: str, shots: list[dict]) -> None:
    """freeze가 있는 영상 장면의 마지막 프레임을 mv.still 경로에 jpg로 뽑는다."""
    for i, s in enumerate(shots):
        if s["type"] == "video" and s.get("freeze"):
            dst = root / mv.still(fmt, i)
            dst.parent.mkdir(exist_ok=True)
            # out 앞 0.5초를 읽어 마지막 프레임만 남긴다 (out이 파일 끝이면 out 바로 앞 시점도 마지막 프레임보다 늦을 수 있다)
            ff.run("-ss", f"{max(0.0, s['out'] - 0.5):.3f}", "-t", "0.5", "-i", str(root / s["src"]), "-update", "1", "-q:v", "2", str(dst))


def cutouts(root: Path, fmt: str, shots: list[dict]) -> None:
    """behindTitle 사진: 사람만 오려낸 PNG를 mv.cutout 경로에 (HF remove-background, u2net_human_seg — 첫 실행 때 모델 176MB)."""
    for i, s in enumerate(shots):
        if s["type"] == "photo" and s.get("behindTitle"):
            dst = root / mv.cutout(fmt, i)
            dst.parent.mkdir(exist_ok=True)
            r = subprocess.run(["npx", "-y", HF, "remove-background", str(root / s["src"]), "-o", str(dst), "--quality", "best"],
                               stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=RENDER_TIMEOUT)
            if r.returncode:
                raise RuntimeError(f"인물 오려내기 실패 ({s['src']}): {(r.stderr or r.stdout)[-400:]}")
