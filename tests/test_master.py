import subprocess

from pipeline import check, master


def _av(path, volume, seconds=4):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c=gray:s=320x240:r=30:d={seconds}",
                    "-f", "lavfi", "-i", f"sine=f=440:d={seconds},volume={volume}", "-shortest",
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
    assert master.master(mp4) is True
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
    assert master.master(ok) is False and ok.stat().st_mtime_ns == stamp
    mute = tmp_path / "mute.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=320x240:r=30:d=2",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mute)], check=True)
    assert master.master(mute) is False
