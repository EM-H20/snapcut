import unicodedata
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / "공용"


@dataclass(frozen=True)
class Project:
    root: Path

    @property
    def sources(self) -> Path:
        return self.root / "영상소스"

    @property
    def cache(self) -> Path:
        return self.root / ".cache"

    @property
    def media(self) -> Path:
        return self.cache / "media"

    @property
    def output(self) -> Path:
        return self.root / "output"

    @property
    def selection(self) -> Path:
        return self.root / "selection.json"

    @property
    def storyboard(self) -> Path:
        return self.cache / "storyboard.json"


def project(arg: str) -> Project:
    p = Path(arg).expanduser()
    if not p.exists():
        p = ROOT / "projects" / arg
    p = p.resolve()
    if unicodedata.normalize("NFC", p.name) == "영상소스":
        p = p.parent
    proj = Project(p)
    if not proj.sources.is_dir():
        raise SystemExit(f"영상소스 폴더가 없습니다: {proj.sources}")
    return proj
