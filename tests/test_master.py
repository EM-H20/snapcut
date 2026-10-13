import subprocess

from pipeline import check, master


BT709 = "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"


def _av(path, volume, seconds=4):
    """bt709 태그가 붙은 영상 + 사인파 (음량 경로만 보는 테스트용)."""
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=gray:s=320x240:r=30:d={seconds}",
                    "-f", "lavfi", "-i", f"sine=f=440:d={seconds},volume={volume}", "-shortest", "-vf", BT709,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)


def _video_md5(path):
    return subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v", "-c", "copy", "-f", "md5", "-"],
                          check=True, capture_output=True, text=True).stdout.strip()


def test_needs_master_window():
    assert master.needs_master({"input_i": "-7.20", "input_tp": "1.00"})
    assert not master.needs_master({"input_i": "-14.30", "input_tp": "-2.00"})
    assert master.needs_master({"input_i": "-14.00", "input_tp": "-0.50"})  # 음량은 맞아도 피크 초과
    assert not master.needs_master({"input_i": "-inf", "input_tp": "-inf"})  # 무음은 증폭하지 않는다


def test_master_brings_hot_audio_into_range_and_keeps_video(tmp_path):
    mp4 = tmp_path / "hot.mp4"
    _av(mp4, volume=8)
    before = _video_md5(mp4)
    assert master.master(mp4) == ["loudness"]
    m = master.measure(mp4)
    assert check.LUFS_RANGE[0] <= float(m["input_i"]) <= check.LUFS_RANGE[1]
    assert float(m["input_tp"]) <= check.MAX_TRUE_PEAK
    assert _video_md5(mp4) == before
    assert not (tmp_path / "hot.master.mp4").exists()


def test_master_skips_in_range_and_no_audio(tmp_path):
    ok = tmp_path / "ok.mp4"
    _av(ok, volume=8)
    master.master(ok)
    stamp = ok.stat().st_mtime_ns
    assert master.master(ok) == [] and ok.stat().st_mtime_ns == stamp
    mute = tmp_path / "mute.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=320x240:r=30:d=2", "-vf", BT709,
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mute)], check=True)
    assert master.master(mute) == []


def _rgb(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1", "-vf", "scale=1:1", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return tuple(raw[:3])


def _untagged_red(path, audio=True, extra=()):
    """키트 출력처럼: RGB → yuv420p를 ffmpeg 기본(bt601) 행렬로, 색 태그 없이."""
    a = ["-f", "lavfi", "-i", "sine=f=440:d=2,volume=0.3", "-c:a", "aac"] if audio else []
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=320x240:r=30:d=2", *a, "-shortest",
                    *extra, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def test_untagged_video_is_converted_not_just_tagged(tmp_path):
    mp4 = _untagged_red(tmp_path / "kit.mp4")
    assert "color" in master.master(mp4)
    info = check.media_info(mp4)
    assert info["color"] == ("bt709", "bt709", "bt709") and info["has_audio"]
    r, g, b = _rgb(mp4)
    assert r > 230 and g < 25 and b < 25  # 태그만 붙이면 bt601 값을 bt709로 읽어 빨강이 바뀐다


def test_silent_untagged_video_gets_color_only(tmp_path):
    mp4 = _untagged_red(tmp_path / "mute.mp4", audio=False)
    assert master.master(mp4) == ["color"]
    assert check.media_info(mp4)["color"] == ("bt709", "bt709", "bt709")


def test_partly_tagged_video_is_converted(tmp_path):
    mp4 = _untagged_red(tmp_path / "half.mp4", extra=("-color_primaries", "bt709"))
    assert "color" in master.master(mp4)
    assert check.media_info(mp4)["color"] == ("bt709", "bt709", "bt709")


def test_loudness_master_keeps_audio_as_long_as_the_video(tmp_path):
    """loudnorm은 끝에 소리를 덧붙여(약 0.1초) 점검의 길이 검사가 실패했다 — 원래 길이로 자른다."""
    mp4 = tmp_path / "hot.mp4"
    _av(mp4, volume=8)
    assert master.master(mp4) == ["loudness"]
    durs = {s["codec_type"]: float(s["duration"]) for s in __import__("pipeline").ff.probe(mp4)["streams"]}
    assert abs(durs["audio"] - durs["video"]) < 1 / 30 + 1e-3
