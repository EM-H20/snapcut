import imagehash

from pipeline.convert import convert_project
from pipeline.curate import curate, group_duplicates
from pipeline.paths import Project


def test_group_duplicates_groups_adjacent_similar():
    a = imagehash.hex_to_hash("0" * 16)
    a2 = imagehash.hex_to_hash("0" * 15 + "1")  # 거리 1
    b = imagehash.hex_to_hash("f" * 16)         # 거리 64
    assert group_duplicates([a, a2, b, a]) == [[0, 1], [2], [3]]


def test_curate_drops_blur_and_burst_duplicate(sample_project):
    proj = Project(sample_project)
    convert_project(proj)
    r = curate(proj)
    reasons = {x["file"]: x["reason"] for x in r["rejected"]}
    assert reasons["media/IMG_blur_jpg.jpg"] == "흔들림"
    assert sum(1 for f, why in reasons.items() if why == "중복" and "IMG_0000" in f) == 1
    assert len(r["candidates"]) == 12  # 사진 12 - 2 + 영상 2
    times = [c["taken_at"] for c in r["candidates"]]
    assert times == sorted(times)
    assert (proj.cache / "candidates.json").exists()
