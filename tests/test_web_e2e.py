"""web E2E (spec §9): 빌드된 사이트 폴더(모듈 스크립트) → pipeline capture → master → check 통과."""
import json
import subprocess
import sys

import pytest

pytestmark = pytest.mark.slow
pytest.importorskip("playwright")

INDEX = ('<!doctype html><html lang="ko"><head><meta charset="utf-8"><link rel="stylesheet" href="./assets/app.css"></head>'
         '<body><main><section class="hero"><h1 id="h">걸은 길이 지도가 됩니다</h1></section><section class="band"></section></main>'
         '<script type="module" crossorigin src="./assets/app.js"></script></body></html>')
CSS = ("body{margin:0;font-family:sans-serif;background:#F4EFE6}.hero{height:100vh;display:flex;align-items:center;justify-content:center}"
       "h1{font-size:120px;color:#23302A}.band{height:150vh;background:linear-gradient(#DDE8DF,#2F7D5B)}")
APP = ("window.seek = t => { const h = document.getElementById('h'); const k = Math.min(1, t / 1.5);"
       " h.style.opacity = k; h.style.transform = `translateY(${(1 - k) * 40}px)`;"
       " scrollTo(0, Math.max(0, t - 2) / 3 * (document.documentElement.scrollHeight - innerHeight)); };"
       " document.fonts.ready.then(() => { window.__ready = true; });")


def test_site_folder_preview_passes_check(tmp_path):
    (tmp_path / "영상소스").mkdir()
    site = tmp_path / "output" / "site"
    (site / "assets").mkdir(parents=True)
    (site / "index.html").write_text(INDEX, encoding="utf-8")
    (site / "assets" / "app.css").write_text(CSS, encoding="utf-8")
    (site / "assets" / "app.js").write_text(APP, encoding="utf-8")
    out = tmp_path / "output" / "x_web.mp4"
    run = lambda *a: subprocess.run([sys.executable, "-m", "pipeline", *a], capture_output=True, text=True)
    for args in (("capture", str(site), str(out), "--seconds", "5", "--size", "1280x720"), ("master", str(out)), ("check", str(tmp_path), str(out))):
        r = run(*args)
        assert r.returncode == 0, r.stdout + r.stderr
    assert json.loads((tmp_path / "output" / "check.json").read_text(encoding="utf-8"))["x_web.mp4"]["ok"]
