import json

import numpy as np
import pytest
from PIL import Image

from pipeline import __main__ as cli
from pipeline.paths import Project


def _project(tmp_path, n=3) -> Project:
    (tmp_path / "영상소스").mkdir()
    for i in range(n):
        add_photo(tmp_path, i)
    return Project(tmp_path)


def add_photo(root, seed):
    rng = np.random.default_rng(seed)
    Image.fromarray(rng.integers(0, 256, (64, 64, 3), dtype=np.uint8)).save(root / "영상소스" / f"n{seed}.jpg")


def test_help_and_music_need_no_tools(monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda _: None)
    with pytest.raises(SystemExit) as e:
        cli.main(["--help"])
    assert e.value.code == 0
    cli.main(["music"])
    with pytest.raises(SystemExit, match="ffmpeg"):
        cli.main(["convert", "x"])


def test_npx_checked_only_for_render_commands(monkeypatch, tmp_path):
    proj = _project(tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda t: "/bin/ffmpeg" if t == "ffmpeg" else None)
    cli.main(["convert", str(proj.root)])  # npx 없어도 통과
    with pytest.raises(SystemExit, match="npx"):
        cli.main(["plan", str(proj.root)])


@pytest.mark.parametrize("selection", [
    {"music": "x", "items": 3},
    {"music": "x", "items": [1]},
    {"music": "x", "formats": "reels"},
    [1, 2],
])
def test_plan_malformed_selection_is_korean_error(tmp_path, selection):
    proj = _project(tmp_path, 0)
    proj.selection.write_text(json.dumps(selection))
    proj.cache.mkdir()
    (proj.cache / "candidates.json").write_text('{"candidates": []}')
    (proj.cache / "highlights.json").write_text("{}")
    with pytest.raises(SystemExit, match="오류"):
        cli.main(["plan", str(proj.root)])


def test_prepare_warns_when_candidate_numbers_change(tmp_path, capsys):
    proj = _project(tmp_path)
    proj.selection.write_text("{}")
    cli.main(["prepare", str(proj.root)])
    assert "후보 번호가 바뀌었습니다" not in capsys.readouterr().out
    cli.main(["prepare", str(proj.root)])
    assert "후보 번호가 바뀌었습니다" not in capsys.readouterr().out
    add_photo(proj.root, 9)
    cli.main(["prepare", str(proj.root)])
    assert "주의: 후보 번호가 바뀌었습니다" in capsys.readouterr().out


def test_card_render_timeout_is_korean_runtime_error(monkeypatch, tmp_path):
    import subprocess
    from pipeline import intro
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(kw)
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])
    monkeypatch.setattr(intro.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="HyperFrames"):
        intro.render_card("basic", "reels", "t", "", tmp_path / "c.mp4")
    assert seen["stdin"] == subprocess.DEVNULL and seen["timeout"] == 600


def _captured_variables(monkeypatch, template, layout):
    import json as _json
    from pipeline import intro
    seen = {}

    def fake_run(cmd, **kw):
        seen.update(_json.loads(open(cmd[cmd.index("--variables-file") + 1], encoding="utf-8").read()))
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    monkeypatch.setattr(intro.subprocess, "run", fake_run)
    from pathlib import Path as _P
    intro.render_card(template, "youtube", "다음 행선지는 어디?", "", _P("x.mp4"), layout=layout)
    return seen


def test_card_layout_passed_only_to_templates_that_declare_it(monkeypatch):
    # 사진 배경(양옆 검은 띠) 카드는 글씨를 사진 안쪽 가운데로 모은다 — layout 변수를 아는 템플릿에만 넘긴다
    assert _captured_variables(monkeypatch, "handwritten", "center")["layout"] == "center"
    assert "layout" not in _captured_variables(monkeypatch, "basic", "center")


def test_old_music_cache_without_version_is_reanalyzed(tmp_path, monkeypatch):
    import shutil
    from pipeline import music
    from tests.conftest import make_click_track
    proj = _project(tmp_path, 0)
    song = tmp_path / "s.wav"
    make_click_track(song, seconds=8.0)
    cache_dir = proj.cache / "music"
    cache_dir.mkdir(parents=True)
    shutil.copy2(song, cache_dir / "s.wav")
    (cache_dir / "s.wav.json").write_text('{"bpm": 1, "beats": [], "downbeats": [], "duration": 8, "chorus": [0, 8]}')
    calls = []
    monkeypatch.setattr(music, "analyze", lambda p: calls.append(p) or {"version": music.VERSION, "sections": {}})
    _, analysis = cli._music(proj, song)
    assert calls and analysis["version"] == music.VERSION


def test_plan_reports_unknown_template_in_korean(tmp_path):
    proj = _project(tmp_path, 0)
    proj.selection.write_text(json.dumps({"template": "없는템플릿", "place": "x", "music": "x", "items": []}))
    proj.cache.mkdir()
    (proj.cache / "candidates.json").write_text('{"candidates": []}')
    (proj.cache / "highlights.json").write_text("{}")
    with pytest.raises(SystemExit, match="템플릿"):
        cli.main(["plan", str(proj.root)])


def test_section_report_line():
    line = cli.section_report({"브릿지": 126.76, "브레이크": 153.51, "마지막후렴": 163.79, "피날레": 174.78,
                               "estimated": ["브릿지"], "ignored": []})
    assert line == "구간: 브릿지 2:06.8(추정), 브레이크 2:33.5, 마지막후렴 2:43.8, 피날레 2:54.8"


def test_render_uses_render_public_dir(monkeypatch, tmp_path):
    from pipeline import render_src
    proj = _project(tmp_path)
    proj.cache.mkdir()
    proj.storyboard.write_text(json.dumps({"formats": {"youtube": {}}}))
    monkeypatch.setattr(render_src, "build", lambda p, f: p.cache / "render")
    monkeypatch.setattr(render_src, "clean", lambda root: None)
    monkeypatch.setattr(cli.shutil, "which", lambda t: f"/bin/{t}")
    seen = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **kw: seen.append(cmd) or type("R", (), {"returncode": 0})())
    cli.main(["render", str(proj.root)])
    assert f"--public-dir={proj.cache / 'render'}" in seen[0]


def test_card_bg_comes_from_hdr_original_as_sdr(tmp_path):
    import subprocess
    from pipeline import convert, ff
    (tmp_path / "영상소스").mkdir()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30:duration=4",
                    "-c:v", "libx265", "-pix_fmt", "yuv420p10le",
                    "-x265-params", "colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc:log-level=error",
                    "-tag:v", "hvc1", str(tmp_path / "영상소스" / "hdr.mp4")], check=True)
    proj = Project(tmp_path)
    item = convert.convert_project(proj)["items"][0]
    (proj.cache / item["file"]).unlink()  # 경량 사본이 없어도 원본에서 뽑아야 한다 (지금 코드는 사본을 읽다 실패)
    bg = cli._card_bg(proj, "reels", (item["file"], 0.5))
    s = next(x for x in ff.probe(bg)["streams"] if x["codec_type"] == "video")
    assert (s["width"], s["height"], s.get("color_transfer")) == (1080, 1920, "bt709")


def test_render_validates_formats_before_building(monkeypatch, tmp_path):
    from pipeline import render_src
    proj = _project(tmp_path)
    proj.cache.mkdir()
    proj.storyboard.write_text(json.dumps({"formats": {"youtube": {}}}))
    built = []
    monkeypatch.setattr(render_src, "build", lambda p, f: built.append(f))
    monkeypatch.setattr(cli.shutil, "which", lambda t: f"/bin/{t}")
    with pytest.raises(SystemExit, match="bogus"):
        cli.main(["render", str(proj.root), "--formats", "bogus"])
    assert built == []  # 잘못된 형식이면 변환 전에 멈춘다


def test_render_cleans_conversions_only_after_success(monkeypatch, tmp_path):
    from pipeline import render_src
    proj = _project(tmp_path)
    proj.cache.mkdir()
    proj.storyboard.write_text(json.dumps({"formats": {"youtube": {}}}))
    monkeypatch.setattr(render_src, "build", lambda p, f: p.cache / "render")
    cleaned = []
    monkeypatch.setattr(render_src, "clean", lambda root: cleaned.append(root))
    monkeypatch.setattr(cli.shutil, "which", lambda t: f"/bin/{t}")
    code = {"rc": 1}
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, **kw: type("R", (), {"returncode": code["rc"]})())
    with pytest.raises(SystemExit, match="렌더 실패"):
        cli.main(["render", str(proj.root)])
    assert cleaned == []  # 실패하면 남겨 둔다
    code["rc"] = 0
    cli.main(["render", str(proj.root)])
    assert cleaned == [proj.cache / "render"]


def test_card_bg_missing_manifest_entry_is_korean_error(tmp_path):
    from pipeline import convert
    proj = _project(tmp_path)
    convert.convert_project(proj)
    with pytest.raises(ValueError, match="manifest"):
        cli._card_bg(proj, "reels", ("media/nope_mp4.mp4", 0.0))


def _longform_project(tmp_path):
    (tmp_path / "영상소스").mkdir()
    (tmp_path / "영상소스" / "game.mkv").write_bytes(b"x")  # plan은 원본을 읽지 않는다
    (tmp_path / ".cache").mkdir()
    tr = {"key": "k", "source": "game.mkv", "track": 1, "duration": 60.0,
          "segments": [{"start": 1.0, "end": 3.0, "text": "첫 문장"}]}
    (tmp_path / ".cache" / "transcript.json").write_text(json.dumps(tr, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "longform.json").write_text(json.dumps({"clips": [{"in": 2.0, "out": 5.0}]}), encoding="utf-8")
    return Project(tmp_path)


def test_plan_longform_writes_storyboard_and_source_link(monkeypatch, tmp_path, capsys):
    proj = _longform_project(tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda t: f"/bin/{t}")
    cli.main(["plan", str(proj.root)])
    sb = json.loads(proj.storyboard.read_text(encoding="utf-8"))
    assert sb["mode"] == "longform" and sb["src"] == "src/game.mkv"
    assert (proj.cache / "src").is_symlink() and (proj.cache / "src" / "game.mkv").exists()
    assert "자막 1개" in capsys.readouterr().out


def test_plan_longform_needs_transcript(monkeypatch, tmp_path):
    proj = _longform_project(tmp_path)
    (proj.cache / "transcript.json").unlink()
    monkeypatch.setattr(cli.shutil, "which", lambda t: f"/bin/{t}")
    with pytest.raises(SystemExit, match="transcribe"):
        cli.main(["plan", str(proj.root)])


def test_render_longform_uses_cache_as_public_dir_and_writes_srt(monkeypatch, tmp_path):
    proj = _longform_project(tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda t: f"/bin/{t}")
    cli.main(["plan", str(proj.root)])
    calls = []
    monkeypatch.setattr(cli.subprocess, "run", lambda args, **kw: calls.append(args) or type("R", (), {"returncode": 0})())
    cli.main(["render", str(proj.root)])
    assert calls[0][4:6] == ["longform", str(proj.output / f"{proj.root.name}_longform.mp4")]  # npx remotion render src/index.ts <comp> <out>
    assert f"--public-dir={proj.cache}" in calls[0]
    srt = (proj.output / f"{proj.root.name}_longform.srt").read_text(encoding="utf-8")
    assert srt.startswith("1\n00:00:00,300 --> 00:00:02,300\n첫 문장")
