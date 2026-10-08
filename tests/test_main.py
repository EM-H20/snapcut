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
