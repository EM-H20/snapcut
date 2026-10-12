"""외부 키트(kits.lock) 받기 — 커밋을 고정하고, 실패한 키트만 건너뛴다."""
import json
import re
import subprocess
from pathlib import Path

from .paths import ROOT

LOCK = ROOT / "kits.lock"
KITS_DIR = ROOT / "kits"
HF_VERSION = "0.8.149"
AREAS = {"promo", "edit", "animation", "web", "core"}
SHA = re.compile(r"[0-9a-f]{40}")


def load_lock(path: Path = LOCK) -> list[dict]:
    kits = json.loads(Path(path).read_text(encoding="utf-8"))["kits"]
    seen = set()
    for k in kits:
        n = k.get("name")
        if not n or n in seen:
            raise ValueError(f"kits.lock: 이름이 없거나 겹칩니다: {n}")
        seen.add(n)
        if k.get("area") not in AREAS:
            raise ValueError(f"kits.lock: {n}의 area는 {sorted(AREAS)} 중 하나여야 합니다")
        if "repo" in k:
            if not SHA.fullmatch(k.get("commit", "")):
                raise ValueError(f"kits.lock: {n}의 commit은 40자리 SHA여야 합니다")
            if not k.get("skills"):
                raise ValueError(f"kits.lock: {n}에 skills가 없습니다")
        elif "npm" not in k:
            raise ValueError(f"kits.lock: {n}에 repo나 npm이 필요합니다")
    return kits


def _url(kit: dict) -> str:
    r = kit["repo"]
    return r if "://" in r else f"https://github.com/{r}.git"


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace")


def _head(d: Path) -> str:
    return _git("rev-parse", "HEAD", cwd=d).stdout.strip() if (d / ".git").exists() else ""


def sync(kits: list[dict], dest: Path = KITS_DIR) -> list[str]:
    """repo 키트를 dest/<name>에 고정 커밋으로 맞춘다. 실패는 예외 대신 경고로 돌려준다."""
    warnings = []
    for k in kits:
        if "repo" not in k:
            continue
        d = dest / k["name"]
        if _head(d) == k["commit"]:
            continue
        d.mkdir(parents=True, exist_ok=True)
        for step in (("init", "-q"), ("fetch", "-q", "--depth", "1", _url(k), k["commit"]), ("checkout", "-q", "--force", "FETCH_HEAD")):
            r = _git(*step, cwd=d)
            if r.returncode:
                warnings.append(f"{k['name']}: git {step[0]} 실패 — {r.stderr.strip()}")
                break
    return warnings


def skill_file(kit: dict, rel: str, dest: Path = KITS_DIR) -> Path:
    return dest / kit["name"] / rel


def status(kits: list[dict], dest: Path = KITS_DIR) -> list[str]:
    lines = []
    for k in kits:
        head = f"{k['area']:<5} {k['name']}: "
        if "repo" not in k:
            lines.append(head + f"npm {k['npm']}")
            continue
        missing = [s for s in k["skills"] if not skill_file(k, s, dest).is_file()]
        n = len(k["skills"])
        lines.append(head + f"스킬 {n - len(missing)}/{n}개" + (f" (없음: {', '.join(missing)})" if missing else ""))
    return lines
