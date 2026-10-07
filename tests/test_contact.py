from PIL import Image

from pipeline.contact import make_sheets
from pipeline.convert import convert_project
from pipeline.curate import curate
from pipeline.paths import Project


def test_sheets_paginate_by_20(sample_project):
    proj = Project(sample_project)
    convert_project(proj)
    cands = curate(proj)["candidates"]
    assert len(make_sheets(proj, cands)) == 1
    sheets = make_sheets(proj, cands * 2)  # 24개 → 2장, 이전 시트는 지움
    assert [p.name for p in sheets] == ["sheet_01.jpg", "sheet_02.jpg"]
    assert sorted(p.name for p in (proj.cache / "sheets").glob("sheet_*.jpg")) == ["sheet_01.jpg", "sheet_02.jpg"]
    with Image.open(sheets[0]) as img:
        assert img.size == (1600, 1280)
