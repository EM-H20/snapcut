from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import ff
from .paths import Project

COLS, ROWS, CELL = 5, 4, 320


def _thumb(proj: Project, c: dict) -> Image.Image:
    path = proj.cache / c["file"]
    if c["type"] == "video":
        thumb = proj.cache / "thumbs" / (Path(c["file"]).stem + ".jpg")
        thumb.parent.mkdir(exist_ok=True)
        if not thumb.exists():
            ff.run("-ss", f"{c['duration'] / 2:.2f}", "-i", str(path), "-frames:v", "1", str(thumb))
        path = thumb
    with Image.open(path) as img:
        return ImageOps.pad(img.convert("RGB"), (CELL, CELL), color="black")


def make_sheets(proj: Project, candidates: list[dict]) -> list[Path]:
    out_dir = proj.cache / "sheets"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("sheet_*.jpg"):
        old.unlink()
    font = ImageFont.load_default(size=28)
    per = COLS * ROWS
    paths = []
    for s in range(0, len(candidates), per):
        sheet = Image.new("RGB", (COLS * CELL, ROWS * CELL), "black")
        draw = ImageDraw.Draw(sheet)
        for k, c in enumerate(candidates[s:s + per]):
            x, y = (k % COLS) * CELL, (k // COLS) * CELL
            sheet.paste(_thumb(proj, c), (x, y))
            label = f"#{s + k}" + (f" V{c['duration']:.0f}s" if c["type"] == "video" else "")
            draw.rectangle([x, y, x + 18 * len(label) + 12, y + 40], fill="black")
            draw.text((x + 6, y + 4), label, fill="yellow", font=font)
        path = out_dir / f"sheet_{s // per + 1:02d}.jpg"
        sheet.save(path, quality=85)
        paths.append(path)
    return paths
