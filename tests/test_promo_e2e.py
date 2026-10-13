"""promo E2E (spec §9): seek 페이지 → pipeline capture → 점검 통과. 소리 있는 키트 결과는 예시로 확인(kit-matrix)."""
import json
import subprocess
import sys

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("playwright")

PAGE = """<!doctype html><html><body style="margin:0;background:#F4EFE6"><div id="t" style="position:absolute;top:40%;width:100%;
text-align:center;font:700 120px sans-serif;color:#23302A">산책노트</div>
<script>window.seek = t => { document.getElementById('t').style.transform = `translateY(${(1 - Math.min(1, t)) * 60}px)`;
document.getElementById('t').style.opacity = Math.min(1, t * 2); };</script></body></html>"""


def test_capture_page_to_checked_mp4(tmp_path):
    (tmp_path / "영상소스").mkdir()
    page = tmp_path / "work" / "promo" / "effect.html"
    page.parent.mkdir(parents=True)
    page.write_text(PAGE, encoding="utf-8")
    out = tmp_path / "output" / "x_effect.mp4"
    run = lambda *a: subprocess.run([sys.executable, "-m", "pipeline", *a], capture_output=True, text=True)
    r = run("capture", str(page), str(out), "--seconds", "4", "--size", "1080x1920")
    assert r.returncode == 0, r.stderr
    r = run("check", str(tmp_path), str(out))
    assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads((tmp_path / "output" / "check.json").read_text(encoding="utf-8"))["x_effect.mp4"]["ok"]
