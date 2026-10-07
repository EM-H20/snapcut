import argparse
import hashlib
import json
import os
import shutil
import subprocess
import unicodedata
from pathlib import Path

from . import contact, convert, curate, highlights, intro, music, plan
from .paths import ROOT, SHARED, Project, project

RENDER_DIR = ROOT / "render"
MUSIC_DIR = SHARED / "음악"
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac", ".flac"}


def list_music() -> list[Path]:
    return sorted(p for p in MUSIC_DIR.glob("*") if p.suffix.lower() in AUDIO_EXT) if MUSIC_DIR.exists() else []


def cmd_convert(args) -> Project:
    proj = project(args.project)
    m = convert.convert_project(proj)
    print(f"변환 완료: {len(m['items'])}개, 제외 {len(m['skipped'])}개")
    for s in m["skipped"]:
        print(f"  - {s['src']}: {s['reason']}")
    hdr = [i["src"] for i in m["items"] if i.get("hdr")]
    if hdr:
        print(f"주의: HDR 영상 {len(hdr)}개 — 색이 바래 보일 수 있습니다: {', '.join(hdr[:5])}")
    no_time = [i["src"] for i in m["items"] if i["time_source"] == "mtime"]
    if no_time:
        print(f"참고: 촬영 시각 정보가 없어 파일 날짜로 정렬한 항목 {len(no_time)}개: {', '.join(no_time[:5])}")
    return proj


def _candidate_files(path: Path) -> list[str] | None:
    try:
        return [c["file"] for c in json.loads(path.read_text(encoding="utf-8"))["candidates"]]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def cmd_prepare(args) -> None:
    proj = cmd_convert(args)
    cands_f = proj.cache / "candidates.json"
    before = _candidate_files(cands_f)  # curate가 덮어쓰기 전에 읽는다
    c = curate.curate(proj)
    if proj.selection.exists() and before is not None and before != [x["file"] for x in c["candidates"]]:
        print("주의: 후보 번호가 바뀌었습니다 — selection.json의 items를 새 시트 기준으로 다시 고르세요.")
    highlights.analyze_clips(proj, c["candidates"])
    sheets = contact.make_sheets(proj, c["candidates"])
    print(f"후보 {len(c['candidates'])}개 (제외 {len(c['rejected'])}개: 흔들림/중복/라이브 포토)")
    print("썸네일 시트:")
    for s in sheets:
        print(f"  {s}")
    print("공용 음악:")
    for m in list_music():
        print(f"  {m.name}")


def _resolve_music(name: str) -> Path:
    p = Path(name).expanduser()
    if not p.is_absolute():
        p = MUSIC_DIR / name
    if not p.is_file():
        raise SystemExit(f"음악 파일이 없습니다: {p}")
    return p


def _music(proj: Project, src: Path) -> tuple[str, dict]:
    dst = proj.cache / "music" / unicodedata.normalize("NFC", src.name)
    dst.parent.mkdir(parents=True, exist_ok=True)
    cache = dst.with_name(dst.name + ".json")
    s = src.stat()
    if not dst.exists() or (dst.stat().st_size, dst.stat().st_mtime) != (s.st_size, s.st_mtime):
        shutil.copy2(src, dst)  # copy2는 mtime을 보존하므로 (크기, mtime) 비교로 교체를 감지한다
        cache.unlink(missing_ok=True)
    if cache.exists():
        analysis = json.loads(cache.read_text(encoding="utf-8"))
    else:
        analysis = music.analyze(dst)
        tmp = cache.with_name(cache.name + ".part")
        tmp.write_text(json.dumps(analysis), encoding="utf-8")
        os.replace(tmp, cache)
    return f"music/{dst.name}", analysis


def _card(proj: Project, template: str, fmt: str, text: str, sub: str) -> str:
    mtime = intro.template_file(template, fmt).stat().st_mtime
    key = hashlib.sha1(json.dumps([template, fmt, text, sub, mtime], ensure_ascii=False).encode()).hexdigest()[:10]
    dst = proj.cache / "cards" / f"{key}.mp4"
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        part = dst.with_name(f"{key}.part.mp4")
        try:
            intro.render_card(template, fmt, text, sub, part)
            os.replace(part, dst)
        finally:
            part.unlink(missing_ok=True)
    return f"cards/{dst.name}"


def cmd_plan(args) -> None:
    proj = project(args.project)
    if not proj.selection.exists():
        raise SystemExit(f"selection.json이 없습니다: {proj.selection}")
    sel = json.loads(proj.selection.read_text(encoding="utf-8"))
    if not isinstance(sel, dict):
        raise ValueError("selection.json은 { ... } 형태의 객체여야 합니다")
    formats = plan.selected_formats(sel)
    if not sel.get("music"):
        raise SystemExit("selection.json에 music이 없습니다. 공용 음악 파일명이나 경로를 넣어 주세요.")
    cands_f, hl_f = proj.cache / "candidates.json", proj.cache / "highlights.json"
    if not (cands_f.exists() and hl_f.exists()):
        raise SystemExit(f"먼저 prepare를 실행하세요: python -m pipeline prepare {args.project}")
    cands = json.loads(cands_f.read_text(encoding="utf-8"))["candidates"]
    hl = json.loads(hl_f.read_text(encoding="utf-8"))
    plan.resolve_items(sel, cands, hl)  # 오래 걸리는 음악 분석·카드 렌더 전에 selection 오류부터 잡는다
    music_src, analysis = _music(proj, _resolve_music(sel["music"]))
    template = sel.get("intro") or "basic"
    cards = {f: {"intro": _card(proj, template, f, sel.get("title", ""), sel.get("subtitle", "")),
                 "outro": _card(proj, template, f, sel.get("ending", ""), "")}
             for f in formats if f in plan.FORMATS}
    sb = plan.build_storyboard(sel, cands, hl, analysis, music_src, cards)
    proj.storyboard.write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"음악: {Path(music_src).name} ({analysis['bpm']} BPM)")
    for f, p in sb["formats"].items():
        n = len(p["shots"]) - 2
        print(f"  {f}: {p['musicEnd'] - p['musicStart']:.1f}초, 장면 {n}개" + (f", 자리가 없어 뺀 항목 {p['dropped']}개" if p["dropped"] else ""))


def cmd_studio(args) -> None:
    proj = project(args.project)
    subprocess.run(["npx", "remotion", "studio", "src/index.ts", f"--public-dir={proj.cache}"], cwd=RENDER_DIR)


def cmd_render(args) -> None:
    proj = project(args.project)
    if not proj.storyboard.exists():
        raise SystemExit(f"먼저 plan을 실행하세요: python -m pipeline plan {args.project}")
    sb = json.loads(proj.storyboard.read_text(encoding="utf-8"))
    formats = args.formats.split(",") if args.formats else list(sb["formats"])
    proj.output.mkdir(exist_ok=True)
    for f in formats:
        if f not in sb["formats"]:
            raise SystemExit(f"storyboard에 '{f}' 형식이 없습니다. selection.json의 formats에 넣고 plan을 다시 실행하세요.")
        out = proj.output / f"{proj.root.name}_{f}.mp4"
        r = subprocess.run(["npx", "remotion", "render", "src/index.ts", f, str(out), f"--public-dir={proj.cache}"], cwd=RENDER_DIR)
        if r.returncode:
            raise SystemExit(f"{f} 렌더 실패")
        print(f"완성: {out}")


def cmd_music(args) -> None:
    for m in list_music():
        print(m.name)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("convert", "prepare", "plan", "studio"):
        sub.add_parser(name).add_argument("project")
    r = sub.add_parser("render")
    r.add_argument("project")
    r.add_argument("--formats", default=None)
    sub.add_parser("music")
    args = p.parse_args(argv)
    needs = ([] if args.cmd == "music" else [("ffmpeg", "brew install ffmpeg")]) + \
        ([("npx", "Node.js 설치")] if args.cmd in ("plan", "studio", "render") else [])
    for tool, hint in needs:
        if not shutil.which(tool):
            raise SystemExit(f"{tool}이(가) 없습니다. 설치: {hint}")
    handlers = {"convert": cmd_convert, "prepare": cmd_prepare, "plan": cmd_plan,
                "studio": cmd_studio, "render": cmd_render, "music": cmd_music}
    try:
        handlers[args.cmd](args)
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        raise SystemExit(f"오류: {e}")


if __name__ == "__main__":
    main()
