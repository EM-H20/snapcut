import subprocess

import numpy as np
import pytest

from pipeline import capture, ff

pytest.importorskip("playwright")

SYNC = """<!doctype html><html><body style="margin:0"><div id="b" style="width:100vw;height:100vh;background:#000"></div>
<script>window.seek = t => { document.getElementById('b').style.background = `rgb(${Math.round(t * 255)},0,0)`; };</script></body></html>"""
ASYNC = """<!doctype html><html><body style="margin:0"><div id="b" style="width:100vw;height:100vh;background:#000"></div>
<script>window.seek = async t => { await new Promise(r => setTimeout(r, 5));
  document.getElementById('b').style.background = `rgb(0,${Math.round(t * 255)},0)`; };
setTimeout(() => { window.__ready = true; }, 300);</script></body></html>"""


def _frames(path, w, h):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3)


@pytest.mark.parametrize("page,channel", [(SYNC, 0), (ASYNC, 1)])
def test_capture_steps_seek_per_frame(tmp_path, page, channel):
    html = tmp_path / "p.html"
    html.write_text(page, encoding="utf-8")
    out = tmp_path / "o.mp4"
    capture.render(html, out, seconds=1.0, fps=10, size=(64, 48))
    f = _frames(out, 64, 48)
    assert len(f) == 10
    assert f[0, 24, 32, channel] < 20 and f[-1, 24, 32, channel] > 200  # t=0 → 검정, t=0.9 → 밝음 (기다린 뒤 캡처)
    v = next(s for s in ff.probe(out)["streams"] if s["codec_type"] == "video")
    assert (v["color_primaries"], v["color_transfer"], v["color_space"]) == ("bt709", "bt709", "bt709")
    assert [s["codec_type"] for s in ff.probe(out)["streams"]] == ["video"]


def test_capture_rounds_odd_size_to_even(tmp_path):
    html = tmp_path / "p.html"
    html.write_text(SYNC, encoding="utf-8")
    out = tmp_path / "o.mp4"
    capture.render(html, out, seconds=0.2, fps=10, size=(65, 49))
    v = next(s for s in ff.probe(out)["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (64, 48)


def test_capture_page_without_seek_times_out_in_korean(tmp_path, monkeypatch):
    monkeypatch.setattr(capture, "READY_TIMEOUT_MS", 500)
    html = tmp_path / "p.html"
    html.write_text("<html><body>no seek</body></html>", encoding="utf-8")
    with pytest.raises(RuntimeError, match="window.seek"):
        capture.render(html, tmp_path / "o.mp4", seconds=0.2, fps=10, size=(64, 48))


def test_capture_without_browser_says_how_to_install(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "none"))
    html = tmp_path / "p.html"
    html.write_text(SYNC, encoding="utf-8")
    with pytest.raises(RuntimeError, match="playwright install chromium"):
        capture.render(html, tmp_path / "o.mp4", seconds=0.2, fps=10, size=(64, 48))
