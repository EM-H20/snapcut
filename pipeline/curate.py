import json
import statistics

import cv2
import imagehash
from PIL import Image

from .paths import Project

BLUR_RATIO = 0.10   # 세트 중앙값 대비 이 비율 미만 = 흔들림 (낮은 디테일 풍경 오탐 방지; Task 12에서 실데이터로 조정)
DUP_DISTANCE = 6    # phash 해밍 거리 이하 = 같은 장면 연사


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


def curate(proj: Project) -> dict:
    items = json.loads((proj.cache / "manifest.json").read_text())["items"]
    items = sorted(items, key=lambda i: i["taken_at"])
    photos = [i for i in items if i["type"] == "photo"]
    scores = {p["file"]: sharpness(proj.cache / p["file"]) for p in photos}
    median = statistics.median(scores.values()) if scores else 0.0

    rejected, sharp = [], []
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
