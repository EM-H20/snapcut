import numpy as np

from pipeline import ff
from pipeline.paths import project


def test_probe_reads_video_stream(sample_project):
    info = ff.probe(sample_project / "영상소스" / "IMG_0200.mov")
    assert any(s["codec_type"] == "video" for s in info["streams"])


def test_load_mono_returns_samples(sample_project):
    y = ff.load_mono(sample_project / "song.wav", sr=22050)
    assert y.dtype == np.float32
    assert abs(len(y) / 22050 - 30.0) < 0.1


def test_project_accepts_sources_folder_path(sample_project):
    assert project(str(sample_project / "영상소스")).root == sample_project.resolve()


def test_project_rejects_missing_sources(tmp_path):
    try:
        project(str(tmp_path))
    except SystemExit as e:
        assert "영상소스" in str(e)
    else:
        raise AssertionError("SystemExit 기대")
