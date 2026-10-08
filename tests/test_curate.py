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
    kept = curate(proj, keep_blur=True)
    assert not [x for x in kept["rejected"] if x["reason"] == "흔들림"]  # 이 픽스처의 흔들린 사진은 IMG_0002의 사본이라 중복으로는 빠진다


def test_curate_rejects_live_photo_mov(tmp_path):
    import json
    from PIL import Image
    proj = Project(tmp_path)
    (proj.cache / "media").mkdir(parents=True)
    Image.new("RGB", (64, 64), (9, 9, 9)).save(proj.cache / "media" / "p.jpg")

    def item(src, typ, **kw):
        return {"src": src, "file": f"media/{src.replace('/', '__')}", "type": typ,
                "taken_at": "2026-09-12T10:00:00", **kw}
    items = [item("day1/IMG_1.HEIC", "photo", file="media/p.jpg"),
             item("day1/img_1.MOV", "video", duration=2.0),     # 라이브 포토
             item("day1/IMG_2.MOV", "video", duration=2.0),     # 짝 없음
             item("day2/IMG_1.MOV", "video", duration=2.0),     # 다른 폴더
             item("day1/IMG_1.mp4", "video", duration=9.0)]     # 길다
    (proj.cache / "manifest.json").write_text(json.dumps({"items": items}))
    r = curate(proj)
    assert [x for x in r["rejected"] if x["reason"] == "라이브 포토"] == [
        {"file": "media/day1__img_1.MOV", "reason": "라이브 포토"}]
    assert len(r["candidates"]) == 4
