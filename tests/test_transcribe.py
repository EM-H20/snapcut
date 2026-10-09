import io
import json
import os
import subprocess

import pytest

from pipeline import __main__ as cli
from pipeline import transcribe, whisper
from pipeline.paths import Project
from pipeline.whisper import Segment


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def two_track_video(path, seconds=3):
    """트랙 1 = 무음(믹스 자리), 트랙 2 = 440Hz(목소리 자리)."""
    ffmpeg("-f", "lavfi", "-i", f"testsrc2=size=320x240:rate=30:duration={seconds}",
           "-f", "lavfi", "-i", f"anullsrc=r=48000:cl=stereo:d={seconds}",
           "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
           "-map", "0", "-map", "1", "-map", "2", "-metadata:s:a:1", "title=Mic",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path))


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "영상소스").mkdir()
    two_track_video(tmp_path / "영상소스" / "game.mkv")
    return Project(tmp_path)


class FakeEngine:
    def __init__(self):
        self.calls = []

    def transcribe(self, wav, language="ko"):
        self.calls.append((wav, language))
        assert wav.exists()
        return [Segment(0.5, 1.5, "안녕")]


def test_source_video_needs_exactly_one_or_a_name(proj):
    assert transcribe.source_video(proj, None).name == "game.mkv"
    two_track_video(proj.sources / "other.mp4", 1)
    with pytest.raises(ValueError, match="하나여야"):
        transcribe.source_video(proj, None)
    assert transcribe.source_video(proj, "other.mp4").name == "other.mp4"
    with pytest.raises(ValueError, match="없습니다"):
        transcribe.source_video(proj, "nope.mkv")


def test_audio_tracks_are_numbered_from_one(proj):
    tracks = transcribe.audio_tracks(proj.sources / "game.mkv")
    assert [t["track"] for t in tracks] == [1, 2]
    assert tracks[1]["title"] == "Mic"


def test_extract_wav_uses_the_chosen_track(proj, tmp_path):
    src = proj.sources / "game.mkv"
    transcribe.extract_wav(src, 1, tmp_path / "t1.wav")
    transcribe.extract_wav(src, 2, tmp_path / "t2.wav")
    quiet, loud = transcribe.loudness(tmp_path / "t1.wav"), transcribe.loudness(tmp_path / "t2.wav")
    assert max(quiet) < -80 and min(loud[:3]) > -30  # 기본(1번)과 다른 트랙이 실제로 뽑힌다 (sine 진폭 1/8 ≈ -21dB, 끝 조각은 AAC 패딩)


def test_loud_moments_keep_a_gap():
    db = [-60.0] * 100
    db[20], db[22], db[70] = -5.0, -6.0, -10.0
    assert transcribe.loud_moments(db, n=2, gap=10) == [20, 70]  # 22는 20과 가까워 건너뜀


def test_ensure_models_downloads_missing_only(tmp_path):
    (tmp_path / whisper.VAD_MODEL_FILE).write_bytes(b"vad")
    urls, said = [], []

    def urlopen(url):
        urls.append(url)
        return io.BytesIO(b"model")

    transcribe.ensure_models(tmp_path, urlopen=urlopen, say=said.append)
    assert urls == [transcribe.ASR_URL.format(size="large-v3")]
    assert (tmp_path / "ggml-large-v3.bin").read_bytes() == b"model"
    assert any("3GB" in s for s in said)


def test_failed_download_leaves_no_partial_file(tmp_path):
    class Broken(io.BytesIO):
        def read(self, *a):
            raise OSError("연결 끊김")

    with pytest.raises(RuntimeError, match="연결 끊김"):
        transcribe.ensure_models(tmp_path, urlopen=lambda url: Broken(), say=lambda s: None)
    assert list(tmp_path.iterdir()) == []


def test_transcribe_project_writes_transcript_and_loudness(proj):
    eng = FakeEngine()
    t = transcribe.transcribe_project(proj, tracks=[2], engine_factory=lambda m: eng, download=lambda m: None)
    assert t["source"] == "game.mkv" and 2.9 < t["duration"] < 3.1
    assert t["tracks"] == [{"track": 2, "label": "마이크1", "title": "Mic"}]
    assert t["segments"] == [{"start": 0.5, "end": 1.5, "text": "안녕", "speaker": "마이크1"}]
    assert json.loads((proj.cache / "transcript.json").read_text(encoding="utf-8")) == t
    db = json.loads((proj.cache / "loudness.json").read_text(encoding="utf-8"))["db"]
    assert abs(len(db) - 3) <= 1 and max(db) < -80  # 큰 소리 순간은 고른 2번(사인파)이 아니라 1번(전체 믹스, 여기선 무음) 기준
    assert not (proj.cache / "audio.wav").exists()


def test_transcript_cache_invalidates_on_track_and_source_change(proj):
    eng = FakeEngine()
    run = lambda **kw: transcribe.transcribe_project(proj, engine_factory=lambda m: eng, download=lambda m: None, **kw)
    run(tracks=[1])
    run(tracks=[1])
    assert len(eng.calls) == 1  # 같은 원본·트랙은 캐시
    run(tracks=[2])
    assert len(eng.calls) == 2  # 트랙이 바뀌면 다시
    src = proj.sources / "game.mkv"
    two_track_video(src, 2)  # 같은 이름으로 다른 원본
    os.utime(src, ns=(1, 1))
    run(tracks=[2])
    assert len(eng.calls) == 3


def test_track_out_of_range_and_no_audio(proj):
    with pytest.raises(ValueError, match="트랙 3"):
        transcribe.transcribe_project(proj, tracks=[3], engine_factory=lambda m: FakeEngine(), download=lambda m: None)
    (proj.sources / "game.mkv").unlink()
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           str(proj.sources / "silent.mp4"))
    with pytest.raises(ValueError, match="오디오 트랙이 없습니다"):
        transcribe.transcribe_project(proj, engine_factory=lambda m: FakeEngine(), download=lambda m: None)


def test_cli_transcribe_without_whisper_explains_install(proj, monkeypatch):
    monkeypatch.delenv("WHISPER_CLI_BINARY", raising=False)
    real_which = whisper.shutil.which  # shutil은 전역 모듈 — ffmpeg 검사는 살려 둔다
    monkeypatch.setattr(whisper.shutil, "which", lambda t: None if t == "whisper-cli" else real_which(t))
    downloads = []
    monkeypatch.setattr(transcribe, "ensure_models", lambda m: downloads.append(m))
    with pytest.raises(SystemExit, match="brew install whisper-cpp"):
        cli.main(["transcribe", str(proj.root)])
    assert downloads == []  # whisper-cli가 없으면 3GB 모델을 받지 않는다


def test_truncated_download_is_not_installed(tmp_path):
    class Short(io.BytesIO):
        headers = {"Content-Length": "100"}

    with pytest.raises(RuntimeError, match="중간에 끊"):
        transcribe.ensure_models(tmp_path, urlopen=lambda url: Short(b"only part"), say=lambda s: None)
    assert list(tmp_path.iterdir()) == []


def test_network_error_names_the_url(tmp_path):
    import urllib.error

    def fail(url):
        raise urllib.error.URLError("no route")

    with pytest.raises(RuntimeError, match="huggingface"):
        transcribe.ensure_models(tmp_path, urlopen=fail, say=lambda s: None)


def test_multiple_tracks_are_labelled_in_order_and_merged_by_time(proj):
    class PerTrack:
        def __init__(self):
            self.n = 0

        def transcribe(self, wav, language="ko"):
            self.n += 1
            if self.n == 1:
                return [Segment(2.0, 2.5, "둘째 트랙 말")]
            return [Segment(0.5, 1.0, "첫 트랙 말"), Segment(2.2, 2.8, "겹침")]

    t = transcribe.transcribe_project(proj, tracks=[2, 1], engine_factory=lambda m: PerTrack(), download=lambda m: None)
    assert [(x["label"], x["track"]) for x in t["tracks"]] == [("마이크1", 2), ("마이크2", 1)]
    assert [(s["text"], s["speaker"]) for s in t["segments"]] == [
        ("첫 트랙 말", "마이크2"), ("둘째 트랙 말", "마이크1"), ("겹침", "마이크2")]


def test_parse_tracks():
    assert transcribe.parse_tracks("2, 3") == [2, 3]
    assert transcribe.parse_tracks("1") == [1]
    for bad in ("", "a", "2,2"):
        with pytest.raises(ValueError, match="--track"):
            transcribe.parse_tracks(bad)
