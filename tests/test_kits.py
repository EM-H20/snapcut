import json
import subprocess

import pytest

from pipeline import kits

IMAGE_15 = {  # 이미지의 15개 저장소 = lock의 15개 이름 (개수는 이미지에서 센 값)
    "product-launch-motion", "motion-graphics-skills", "claude-motion-design", "hyperframes-student-kit",
    "motion-graphics", "animate", "claude-motion", "claude-remotion-skill", "motion", "motion-dev-animations-skill",
    "hyperframes", "remotion", "remotion-skills", "gsap-skills", "lottiefiles-motion-design",
}


def _lock(tmp_path, kits_list):
    p = tmp_path / "kits.lock"
    p.write_text(json.dumps({"kits": kits_list}))
    return p


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def origin(tmp_path):
    repo = tmp_path / "origin"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "uploadpack.allowReachableSHA1InWant", "true")
    (repo / "skill").mkdir()
    (repo / "skill" / "SKILL.md").write_text("---\nname: x\n---\n")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
    return repo, _git(repo, "rev-parse", "HEAD")


def test_real_lock_lists_exactly_the_15_image_repos():
    assert {k["name"] for k in kits.load_lock()} == IMAGE_15


def test_lock_rejects_short_commit(tmp_path):
    p = _lock(tmp_path, [{"name": "a", "area": "promo", "repo": "o/a", "commit": "abc123", "skills": ["SKILL.md"]}])
    with pytest.raises(ValueError, match="40자리"):
        kits.load_lock(p)


def test_lock_rejects_duplicate_name_and_unknown_area(tmp_path):
    with pytest.raises(ValueError, match="겹칩니다"):
        kits.load_lock(_lock(tmp_path, [{"name": "a", "area": "core", "npm": "x"}] * 2))
    with pytest.raises(ValueError, match="area"):
        kits.load_lock(_lock(tmp_path, [{"name": "a", "area": "games", "npm": "x"}]))


def test_lock_requires_repo_or_npm(tmp_path):
    with pytest.raises(ValueError, match="repo나 npm"):
        kits.load_lock(_lock(tmp_path, [{"name": "a", "area": "core"}]))


def test_sync_checks_out_pinned_commit_and_is_idempotent(tmp_path, origin, monkeypatch):
    repo, sha = origin
    kit = {"name": "k", "area": "core", "repo": f"file://{repo}", "commit": sha, "skills": ["skill/SKILL.md"]}
    dest = tmp_path / "kits"
    assert kits.sync([kit], dest) == []
    assert kits.skill_file(kit, "skill/SKILL.md", dest).is_file()
    calls = []
    real = kits._git
    monkeypatch.setattr(kits, "_git", lambda *a, cwd: calls.append(a) or real(*a, cwd=cwd))
    assert kits.sync([kit], dest) == []
    assert calls == [("rev-parse", "HEAD")]  # 이미 맞으면 fetch하지 않는다


def test_sync_failure_warns_and_continues(tmp_path, origin):
    repo, sha = origin
    bad = {"name": "bad", "area": "core", "repo": f"file://{repo}", "commit": "0" * 40, "skills": ["skill/SKILL.md"]}
    good = {"name": "good", "area": "core", "repo": f"file://{repo}", "commit": sha, "skills": ["skill/SKILL.md"]}
    warnings = kits.sync([bad, good], tmp_path / "kits")
    assert len(warnings) == 1 and warnings[0].startswith("bad:")
    assert (tmp_path / "kits" / "good" / "skill" / "SKILL.md").is_file()


def test_status_reports_missing_skill_files(tmp_path, origin):
    repo, sha = origin
    kit = {"name": "k", "area": "edit", "repo": f"file://{repo}", "commit": sha, "skills": ["skill/SKILL.md", "nope/SKILL.md"]}
    kits.sync([kit], tmp_path / "kits")
    lines = kits.status([kit, {"name": "m", "area": "web", "npm": "motion"}], tmp_path / "kits")
    assert lines == ["edit  k: 스킬 1/2개 (없음: nope/SKILL.md)", "web   m: npm motion"]


def test_node_tools_line_reports_playwright(tmp_path):
    assert "없음" in kits.node_tools(tmp_path) and f"npm i --prefix kits playwright@{kits.PLAYWRIGHT}" in kits.node_tools(tmp_path)
    (tmp_path / "node_modules" / "playwright").mkdir(parents=True)
    (tmp_path / "node_modules" / "playwright" / "package.json").write_text('{"version": "1.63.0"}')
    assert kits.node_tools(tmp_path) == "node  playwright 1.63.0 (animate 도구)"
