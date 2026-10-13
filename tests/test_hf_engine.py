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


def test_cutouts_run_remove_background_only_for_behind_title(monkeypatch, tmp_path):
    from PIL import Image
    (tmp_path / "media").mkdir()
    Image.new("RGB", (8, 8)).save(tmp_path / "media" / "b.jpg")
    calls = []
    monkeypatch.setattr(engine.subprocess, "run", lambda args, **k: calls.append(args) or subprocess.CompletedProcess(args, 0, "", ""))
    shots = [{"type": "photo", "src": "media/a.jpg"}, {"type": "photo", "src": "media/b.jpg", "behindTitle": "산"}]
    engine.cutouts(tmp_path, "youtube", shots)
    assert len(calls) == 1
    a = calls[0]
    assert a[:4] == ["npx", "-y", engine.HF, "remove-background"] and a[4] == str(tmp_path / "cutout" / "youtube_s1.src.jpg")
    assert not (tmp_path / "cutout" / "youtube_s1.src.jpg").exists()  # 세운 사본은 지운다
    assert a[a.index("-o") + 1] == str(tmp_path / "cutout" / "youtube_s1.png") and a[a.index("--quality") + 1] == "best"


def test_cutouts_failure_is_korean(monkeypatch, tmp_path):
    import pytest
    from PIL import Image
    (tmp_path / "media").mkdir()
    Image.new("RGB", (8, 8)).save(tmp_path / "media" / "b.jpg")
    monkeypatch.setattr(engine.subprocess, "run", lambda args, **k: subprocess.CompletedProcess(args, 1, "", "boom"))
    with pytest.raises(RuntimeError, match="오려내기"):
        engine.cutouts(tmp_path, "youtube", [{"type": "photo", "src": "media/b.jpg", "behindTitle": "산"}])


def test_cutouts_feed_an_upright_copy_of_exif_rotated_photos(monkeypatch, tmp_path):
    from PIL import Image
    (tmp_path / "src").mkdir()
    img = Image.new("RGB", (40, 20), "red")
    exif = img.getexif()
    exif[0x0112] = 6  # 오른쪽으로 90도 돌려 보여야 하는 아이폰 사진
    img.save(tmp_path / "src" / "a.jpg", exif=exif)
    seen = []
    monkeypatch.setattr(engine.subprocess, "run", lambda args, **k: seen.append(Image.open(args[4]).size) or subprocess.CompletedProcess(args, 0, "", ""))
    engine.cutouts(tmp_path, "reels", [{"type": "photo", "src": "src/a.jpg", "behindTitle": "산"}])
    assert seen == [(20, 40)]  # 크롬이 보여 주는 방향 그대로 오려낸다
