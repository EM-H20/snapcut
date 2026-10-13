import subprocess

from pipeline.hf import engine


def test_freeze_still_at_clip_end(tmp_path):
    # out이 파일 끝이면(place가 in을 당긴 흔한 경우) out-1프레임 시점이 마지막 프레임보다 늦어 ffmpeg가 아무것도 못 쓴다
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(tmp_path / "a.mp4")], check=True)
    engine.freeze_stills(tmp_path, "youtube", [{"type": "video", "src": "a.mp4", "freeze": 1.0, "out": 3.0}])
    assert (tmp_path / "freeze" / "youtube_s0.jpg").stat().st_size > 0


def test_render_passes_version_and_workers(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(engine.subprocess, "run", lambda args, **k: calls.append(args) or subprocess.CompletedProcess(args, 0, "", ""))
    engine.render(tmp_path, "index.html", tmp_path / "o.mp4", hf="hyperframes@0.7.109", workers=1)
    engine.render(tmp_path, "a.html", tmp_path / "o.mp4")
    assert calls[0][2] == "hyperframes@0.7.109" and calls[0][calls[0].index("-w") + 1] == "1"
    assert calls[1][2] == engine.HF and "-w" not in calls[1]
