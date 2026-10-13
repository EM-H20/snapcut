"""window.seek(t) 페이지 → mp4. motion-graphics-skills 등 키트 페이지는 seek만 내놓고 내보내기 도구가 없다(HF 0.8은 seek를 쓰지 않음).
프레임마다 seek(i/fps)를 기다리고(async 가능) 화면을 찍어 ffmpeg로 넘긴다. 소리는 넣지 않는다(무음 트랙은 음량 점검 실패가 된다).
폴더(빌드된 사이트)를 주면 로컬 HTTP로 띄워 index.html을 찍는다 — file://에서는 모듈 스크립트가 막힌다."""
import functools
import subprocess
import threading
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

READY_TIMEOUT_MS = 30_000
INSTALL = "playwright가 없습니다 — .venv/bin/pip install -e '.[promo]' && .venv/bin/python -m playwright install chromium"
TWO_FRAMES = "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))"


def _encoder(out: Path, fps: float) -> subprocess.Popen:
    vf = ("crop=trunc(iw/2)*2:trunc(ih/2)*2,scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,"
          "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv")  # ffmpeg 8은 -color_* 만으로는 태그가 빠진다
    return subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png", "-i", "-",
                             "-vf", vf, "-c:v", "libx264", "-crf", "16", "-preset", "medium",
                             "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                             "-movflags", "+faststart", str(out)], stdin=subprocess.PIPE, stderr=subprocess.PIPE)


def _wait_ready(page, source: str) -> None:
    """seek가 생기고 폰트가 다 읽힌 뒤. 페이지가 __ready/ready 깃발을 쓰면 그것도 기다린다."""
    flags = [f for f in ("__ready", "ready") if f"window.{f}" in source]
    cond = " && ".join(["typeof window.seek === 'function'", *(f"window.{f} === true" for f in flags)])
    try:
        page.wait_for_function(f"() => {cond}", timeout=READY_TIMEOUT_MS)
    except Exception as e:  # playwright TimeoutError
        raise RuntimeError(f"{READY_TIMEOUT_MS // 1000}초 안에 페이지가 준비되지 않았습니다 (window.seek{', ' + ', '.join(flags) if flags else ''})") from e
    page.evaluate("() => document.fonts.ready.then(() => true)")


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@contextmanager
def _served(page: Path):
    """(주소, 깃발을 찾을 소스 글). 폴더면 그 동안만 127.0.0.1의 빈 포트로 띄운다."""
    if not page.is_dir():
        yield page.as_uri(), page.read_text(encoding="utf-8", errors="replace")
        return
    index = page / "index.html"
    if not index.is_file():
        raise RuntimeError(f"{page}에 index.html이 없습니다 (빌드된 사이트 폴더를 주세요)")
    source = "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in [index, *sorted(page.rglob("*.js"))])
    server = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_QuietHandler, directory=str(page)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/index.html", source
    finally:
        server.shutdown()
        server.server_close()


def render(page_file: Path, out: Path, seconds: float, fps: float = 30, size: tuple[int, int] = (1920, 1080),
           query: str = "render") -> int:
    try:
        from playwright.sync_api import Error as PlaywrightError, sync_playwright
    except ImportError:
        raise RuntimeError(INSTALL)
    page_file = Path(page_file).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_name(out.stem + ".part.mp4")
    n = max(1, round(seconds * fps))
    with _served(page_file) as (url, source):
        enc = _encoder(part, fps)
        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch()
                except PlaywrightError as e:  # 패키지는 있는데 브라우저를 안 받은 경우 (pip 업그레이드 뒤 흔함)
                    raise RuntimeError(INSTALL.replace("playwright가 없습니다", "playwright 브라우저가 없습니다")) from e
                try:
                    page = browser.new_page(viewport={"width": size[0], "height": size[1]}, device_scale_factor=1)
                    page.goto(url + (f"?{query}" if query else ""))
                    _wait_ready(page, source)
                    for i in range(n):
                        page.evaluate("t => Promise.resolve(window.seek(t))", i / fps)
                        page.evaluate(TWO_FRAMES)
                        enc.stdin.write(page.screenshot(type="png"))
                finally:
                    browser.close()
            enc.stdin.close()
            if enc.wait():
                raise RuntimeError(f"인코딩 실패: {enc.stderr.read().decode(errors='replace')[-300:]}")
            part.replace(out)
        finally:
            if enc.poll() is None:
                enc.kill()
            part.unlink(missing_ok=True)
    return n
