import json
import statistics
from pathlib import PurePosixPath

import cv2
import imagehash
from PIL import Image

from .paths import Project

BLUR_RATIO = 0.10   # 세트 중앙값 대비 이 비율 미만 = 흔들림 (낮은 디테일 풍경 오탐 방지; Task 12에서 실데이터로 조정)
DUP_DISTANCE = 6    # phash 해밍 거리 이하 = 같은 장면 연사
LIVE_PHOTO_SECONDS = 3.5  # 같은 이름의 사진이 있는 이 길이 이하 영상 = 라이브 포토의 MOV


def sharpness(path) -> float:
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise RuntimeError(f"이미지를 읽을 수 없습니다: {path}")
    scale = 800 / max(gray.shape)
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def group_duplicates(hashes, max_distance: int = DUP_DISTANCE) -> list[list[int]]:
    # ponytail: 시간순으로 이웃한 사진끼리만 비교(연사 = 연속 촬영). 시간상 떨어진 중복은 못 잡음 — 필요하면 전체 쌍 비교로
    groups: list[list[int]] = []
    for i, h in enumerate(hashes):
        if groups and h - hashes[groups[-1][-1]] <= max_distance:
            groups[-1].append(i)
        else:
            groups.append([i])
    return groups


def _phash(path) -> imagehash.ImageHash:
    with Image.open(path) as img:
        return imagehash.phash(img)


def _stem_key(item: dict) -> tuple:
    src = PurePosixPath(item["src"])
    return src.parent, src.stem.lower()


def curate(proj: Project) -> dict:
    items = json.loads((proj.cache / "manifest.json").read_text())["items"]
    items = sorted(items, key=lambda i: i["taken_at"])
    photos = [i for i in items if i["type"] == "photo"]
    scores = {p["file"]: sharpness(proj.cache / p["file"]) for p in photos}
    median = statistics.median(scores.values()) if scores else 0.0

    rejected, sharp = [], []
    photo_keys = {_stem_key(p) for p in photos}
    live = {i["file"] for i in items
            if i["type"] == "video" and i["duration"] <= LIVE_PHOTO_SECONDS and _stem_key(i) in photo_keys}
    rejected += [{"file": f, "reason": "라이브 포토"} for f in sorted(live)]
    items = [i for i in items if i["file"] not in live]
    for p in photos:
        if scores[p["file"]] < BLUR_RATIO * median:
            rejected.append({"file": p["file"], "reason": "흔들림"})
        else:
            sharp.append(p)

    keep = set()
    for g in group_duplicates([_phash(proj.cache / p["file"]) for p in sharp]):
        best = max(g, key=lambda k: scores[sharp[k]["file"]])
        keep.add(sharp[best]["file"])
        rejected += [{"file": sharp[k]["file"], "reason": "중복"} for k in g if k != best]

    candidates = [dict(i, sharpness=scores.get(i["file"])) for i in items
                  if i["type"] == "video" or i["file"] in keep]
    result = {"candidates": candidates, "rejected": rejected}
    (proj.cache / "candidates.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result
