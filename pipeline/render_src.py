"""Remotion 렌더용 public 폴더(.cache/render). 원본은 복사하지 않고 링크로 가리킨다.
원본을 그대로 못 쓰는 것만, 쓰는 구간만 변환한다: HDR 영상(Chrome 톤매핑은 피부가 분홍으로 과포화), HEIC 사진(Chrome이 못 읽음).
Studio 미리보기는 계속 .cache(경량 사본 + media/ 이름의 storyboard)를 쓴다 — 장면 이름 표시가 그 이름에 기댄다."""
import hashlib
import json
import os
import shutil
from pathlib import Path

from PIL import Image, ImageOps

from . import convert, ff
from .paths import Project

LINKS = ("cards", "music", "fonts")  # .cache에서 그대로 쓰는 폴더
MARGIN = 1.0  # HDR 변환 구간 앞뒤 여유(초) — 다음 장면 디졸브(최대 1초) 동안 이 장면이 더 남는다
HDR_CRF = "12"  # 렌더 직전 한 번뿐인 변환이라 거의 무손실로
HDR_ENCODE = "vt-bt709-grade1"  # 변환 방식 버전 — 바꾸면 기존 변환본을 다시 만든다
CONVERTED = ("hdr", "heic")  # 렌더가 끝나면 지우는 변환본 폴더
HEIC_EXT = {".heic", ".heif"}


def _link(path: Path, target: Path) -> None:
    rel = os.path.relpath(target, path.parent)  # 상대 링크: 프로젝트 폴더를 옮겨도 유지
    if path.is_symlink() and os.readlink(path) == rel:
        return
    if path.is_symlink():
        path.unlink()
    elif path.exists():
        raise ValueError(f"{path}에 파일이 있어 원본 링크를 만들 수 없습니다 — 지우고 다시 실행하세요")
    path.symlink_to(rel)


def _key(src: Path, *extra) -> str:
    st = src.stat()  # 같은 이름으로 교체된 원본은 새로 변환
    return hashlib.sha1(json.dumps([str(src), st.st_size, st.st_mtime_ns, *extra]).encode()).hexdigest()[:12]


def _hdr_segment(root: Path, src: Path, stream: dict, a: float, b: float) -> str:
    name = f"hdr/{_key(src, a, b, HDR_CRF, HDR_ENCODE)}.mp4"
    dst = root / name
    if not dst.exists():
        dst.parent.mkdir(exist_ok=True)
        tmp = dst.with_name(f"{dst.stem}.part.mp4")
        inp, vf = convert.video_input(src, stream, *convert._display_size(stream))
        try:
            ff.run("-ss", f"{a:.3f}", *inp, "-t", f"{b - a:.3f}", "-map", "0:v:0", "-map", "0:a:0?", "-vf", vf,
                   "-c:v", "libx264", "-preset", "medium", "-crf", HDR_CRF, "-pix_fmt", "yuv420p",
                   "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                   "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(tmp))
            os.replace(tmp, dst)
        finally:
            tmp.unlink(missing_ok=True)
    return name


def _heic(root: Path, src: Path) -> str:
    name = f"heic/{_key(src)}.jpg"
    dst = root / name
    if not dst.exists():
        dst.parent.mkdir(exist_ok=True)
        with Image.open(src) as img:
            icc = img.info.get("icc_profile")
            out = ImageOps.exif_transpose(img).convert("RGB")
        tmp = dst.with_name(f"{dst.stem}.part.jpg")
        out.save(tmp, "JPEG", quality=95, **({"icc_profile": icc} if icc else {}))
        os.replace(tmp, dst)
    return name


def original(sources: dict[str, Path], file: str) -> Path:
    if file not in sources:
        raise ValueError(f"{file}: manifest에 없는 파일입니다 — convert와 plan을 다시 실행하세요")
    path = sources[file]
    if not path.exists():
        raise ValueError(f"원본이 없습니다: {path}")
    return path


def _shot(proj: Project, root: Path, s: dict, sources: dict, probes: dict, used: set) -> dict:
    s = dict(s)

    def photo(file: str) -> str:
        src = original(sources, file)
        if src.suffix.lower() not in HEIC_EXT:
            return "src/" + src.relative_to(proj.sources).as_posix()
        name = _heic(root, src)
        used.add(name)
        return name

    if s["type"] == "collage":
        s["srcs"] = [photo(f) for f in s["srcs"]]
    elif s["type"] == "photo":
        s["src"] = photo(s["src"])
    elif s["type"] in ("video", "credits"):
        src = original(sources, s["src"])
        if src not in probes:
            probes[src] = next(x for x in ff.probe(src)["streams"] if x["codec_type"] == "video")
        if convert.is_hdr(probes[src]):
            a = max(0.0, s["in"] - MARGIN)
            name = _hdr_segment(root, src, probes[src], a, s["out"] + MARGIN)
            used.add(name)
            s.update({"src": name, "in": round(s["in"] - a, 3), "out": round(s["out"] - a, 3)})
        else:
            s["src"] = "src/" + src.relative_to(proj.sources).as_posix()
    return s  # clip(카드)은 cards/ 링크로 그대로


def build(proj: Project, formats: list[str]) -> Path:
    """렌더할 형식만으로 렌더용 public 폴더를 맞추고 경로를 돌려준다."""
    root = proj.cache / "render"
    root.mkdir(exist_ok=True)
    _link(root / "src", proj.sources)
    for name in LINKS:
        if (proj.cache / name).exists():
            _link(root / name, proj.cache / name)
    sources = convert.source_map(proj)
    sb = json.loads(proj.storyboard.read_text(encoding="utf-8"))
    sb["formats"] = {f: sb["formats"][f] for f in formats}  # 다른 형식의 HDR 장면은 변환하지 않는다
    probes, used = {}, set()
    for plan in sb["formats"].values():
        plan["shots"] = [_shot(proj, root, s, sources, probes, used) for s in plan["shots"]]
    for sub in CONVERTED:
        for f in (root / sub).glob("*"):
            if f"{sub}/{f.name}" not in used:
                f.unlink()
    tmp = root / "storyboard.json.part"
    tmp.write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, root / "storyboard.json")
    return root


def clean(root: Path) -> None:
    """렌더가 끝난 뒤 변환본을 지운다 — 원본에서 언제든 다시 만들 수 있다."""
    for sub in CONVERTED:
        shutil.rmtree(root / sub, ignore_errors=True)
