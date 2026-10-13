"""animation E2E (spec §9): animate 키트 math 데모 → build → export → pipeline master(색 bt709) → check. 키트·Playwright npm이 있을 때만."""
import json
import shutil
import subprocess
import sys

import pytest

from pipeline import check, kits

pytestmark = pytest.mark.slow
SK = kits.KITS_DIR / "animate" / "plugins" / "animate" / "skills" / "animate"
needs = pytest.mark.skipif(not ((SK / "tools" / "export.mjs").exists() and (kits.KITS_DIR / "node_modules" / "playwright").exists()),
                           reason="animate 키트와 kits/node_modules/playwright 필요")


@needs
def test_animate_demo_to_checked_mp4(tmp_path):
    (tmp_path / "영상소스").mkdir()
    piece = tmp_path / "work" / "animation" / "demo"
    shutil.copytree(SK / "styles" / "math" / "demo", piece)
    for tool, *args in (("build.mjs",), ("export.mjs", "--no-captions")):
        r = subprocess.run(["node", str(SK / "tools" / tool), ".", *args], cwd=piece, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
    out = tmp_path / "output" / "x_animate.mp4"
    out.parent.mkdir()
    shutil.copyfile(piece / "renders" / "final.mp4", out)
    run = lambda *a: subprocess.run([sys.executable, "-m", "pipeline", *a], capture_output=True, text=True)
    assert run("master", str(out)).returncode == 0
    assert check.media_info(out)["color"] == ("bt709", "bt709", "bt709")
    r = run("check", str(tmp_path), str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads((tmp_path / "output" / "check.json").read_text(encoding="utf-8"))["x_animate.mp4"]["ok"]
