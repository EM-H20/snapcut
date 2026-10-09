import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

from . import contact, convert, curate, ff, highlights, intro, longform, music, plan, render_src, template, transcribe
from .paths import ROOT, SHARED, Project, project

RENDER_DIR = ROOT / "render"
LONGFORM_FILE = "longform.json"  # 있으면 롱폼 모드 (Claude가 고른 구간)
MUSIC_DIR = SHARED / "음악"
CREDITS_FONT = SHARED / "인트로아웃트로" / "handwritten" / "NanumPenScript-Regular.ttf"  # 크레딧 손글씨
CARD_BG_SOURCE = "original-grade1"  # 카드 영상 배경을 원본에서 뽑는다 — 바꾸면 카드가 다시 만들어진다
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac", ".flac"}


def list_music() -> list[Path]:
    return sorted(p for p in MUSIC_DIR.glob("*") if p.suffix.lower() in AUDIO_EXT) if MUSIC_DIR.exists() else []


def cmd_convert(args) -> Project:
    proj = project(args.project)
    m = convert.convert_project(proj)
    print(f"변환 완료: {len(m['items'])}개, 제외 {len(m['skipped'])}개")
    for s in m["skipped"]:
        print(f"  - {s['src']}: {s['reason']}")
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
    c = curate.curate(proj, keep_blur=args.keep_blur)
    if proj.selection.exists() and before is not None and before != [x["file"] for x in c["candidates"]]:
        print("주의: 후보 번호가 바뀌었습니다 — selection.json의 items를 새 시트 기준으로 다시 고르세요.")
    highlights.analyze_clips(proj, c["candidates"])
    sheets = contact.make_sheets(proj, c["candidates"])
    print(f"후보 {len(c['candidates'])}개 (제외 {len(c['rejected'])}개: {'' if args.keep_blur else '흔들림/'}중복/라이브 포토)")
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
    analysis = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else None
    if not analysis or analysis.get("version") != music.VERSION:  # 예전 형식 캐시는 다시 분석 (sections 추가 등)
        analysis = music.analyze(dst)
        tmp = cache.with_name(cache.name + ".part")
        tmp.write_text(json.dumps(analysis), encoding="utf-8")
        os.replace(tmp, cache)
    return f"music/{dst.name}", analysis


def _card_bg(proj: Project, fmt: str, video: tuple[str, float] | None) -> Path:
    """카드 배경 bg.mp4: 고른 영상 구간을 카드 크기로 자르거나, 없으면 검은 화면."""
    w, h = plan.FORMATS[fmt]["width"], plan.FORMATS[fmt]["height"]
    key = hashlib.sha1(json.dumps([fmt, video, CARD_BG_SOURCE]).encode()).hexdigest()[:10]
    dst = proj.cache / "cards" / f"bg_{key}.mp4"
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        part = dst.with_name(f"bg_{key}.part.mp4")
        photo = bool(video) and Path(video[0]).suffix.lower() == ".jpg"
        if photo:  # 사진 배경: 본편 사진 장면과 같은 배치(전체가 보이게 + 검은 띠)라 사진 → 카드가 이음매 없이 이어진다
            src, fit = ["-loop", "1", "-i", str(proj.cache / video[0])], \
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
        elif video:  # 영상 배경은 원본에서 (경량 사본은 960px라 카드에 부족)
            src = render_src.original(convert.source_map(proj), video[0])
            stream = next(s for s in ff.probe(src)["streams"] if s["codec_type"] == "video")
            dw, dh = convert._display_size(stream)
            k = max(w / dw, h / dh)  # 카드를 꽉 채우게 확대한 뒤 가운데 자르기
            inp, vf = convert.video_input(src, stream, round(dw * k / 2) * 2, round(dh * k / 2) * 2)
            src, fit = ["-ss", str(video[1]), *inp], f"{vf},crop={w}:{h}"
        else:
            src, fit = ["-f", "lavfi", "-i", f"color=c=black:s={w}x{h}"], f"scale={w}:{h}"
        try:
            ff.run(*src, "-t", str(plan.CARD_SECONDS), "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                   "-vf", f"{fit},setsar=1,fps={plan.FPS}",
                   "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", str(part))
            os.replace(part, dst)
        finally:
            part.unlink(missing_ok=True)
    return dst


def _card(proj: Project, template: str, fmt: str, text: str, sub: str, video: tuple[str, float] | None = None) -> str:
    mtime = intro.template_file(template, fmt).stat().st_mtime
    layout = "center" if video and Path(video[0]).suffix.lower() == ".jpg" else "wide"  # 사진 배경이면 글씨를 사진 안쪽으로
    key = hashlib.sha1(json.dumps([template, fmt, text, sub, mtime, video, layout, CARD_BG_SOURCE],
                                  ensure_ascii=False).encode()).hexdigest()[:10]
    dst = proj.cache / "cards" / f"{key}.mp4"
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        part = dst.with_name(f"{key}.part.mp4")
        try:
            intro.render_card(template, fmt, text, sub, part, _card_bg(proj, fmt, video), layout)
            os.replace(part, dst)
        finally:
            part.unlink(missing_ok=True)
    return f"cards/{dst.name}"


def cmd_plan_longform(proj: Project) -> None:
    spec = longform.load_spec(proj.root / LONGFORM_FILE)
    tf = proj.cache / "transcript.json"
    if not tf.exists():
        raise SystemExit(f"먼저 transcribe를 실행하세요: python -m pipeline transcribe {proj.root.name}")
    tr = json.loads(tf.read_text(encoding="utf-8"))
    render_src._link(proj.cache / "src", proj.sources)  # Studio·렌더 모두 .cache를 public dir로 쓰고 원본은 링크로 본다
    sb, warnings = longform.build(spec, tr, "src/" + tr["source"])
    proj.storyboard.write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")
    for f, p in sb["formats"].items():
        if f == "shorts":
            print(f"  shorts: {len(p)}개 ({', '.join(f'{s['duration']:.0f}초' for s in p)})")
        else:
            print(f"  {f}: {p['duration'] / 60:.1f}분, 구간 {len(p['clips'])}개, 자막 {len(p['captions'])}개")
    for w in warnings:
        print(f"  주의: {w}")


def cmd_plan(args) -> None:
    proj = project(args.project)
    if (proj.root / LONGFORM_FILE).exists():
        return cmd_plan_longform(proj)
    if not proj.selection.exists():
        raise SystemExit(f"selection.json이 없습니다: {proj.selection}")
    sel = json.loads(proj.selection.read_text(encoding="utf-8"))
    if not isinstance(sel, dict):
        raise ValueError("selection.json은 { ... } 형태의 객체여야 합니다")
    if sel.get("template"):  # 공용/템플릿/<이름>의 기본값을 깔고 selection 값이 우선
        sel = template.apply(sel, template.load(sel["template"]))
    formats = plan.selected_formats(sel)
    if not sel.get("music"):
        raise SystemExit("selection.json에 music이 없습니다. 공용 음악 파일명이나 경로를 넣어 주세요.")
    cands_f, hl_f = proj.cache / "candidates.json", proj.cache / "highlights.json"
    if not (cands_f.exists() and hl_f.exists()):
        raise SystemExit(f"먼저 prepare를 실행하세요: python -m pipeline prepare {args.project}")
    cands = json.loads(cands_f.read_text(encoding="utf-8"))["candidates"]
    hl = json.loads(hl_f.read_text(encoding="utf-8"))
    plan.resolve_items(sel, cands, hl)  # 오래 걸리는 음악 분석·카드 렌더 전에 selection 오류부터 잡는다
    intro_video, outro_video = plan.card_video(sel, "introVideo", cands), plan.card_video(sel, "outroVideo", cands)
    music_src, analysis = _music(proj, _resolve_music(sel["music"]))
    card_tpl = sel.get("intro") or "basic"
    cards = {f: {"intro": _card(proj, card_tpl, f, sel.get("title", ""), sel.get("subtitle", ""), intro_video),
                 "outro": _card(proj, card_tpl, f, sel.get("ending", ""), "", outro_video)}
             for f in formats if f in plan.FORMATS}
    sb = plan.build_storyboard(sel, cands, hl, analysis, music_src, cards)
    if sel.get("credits") and CREDITS_FONT.exists():
        (proj.cache / "fonts").mkdir(exist_ok=True)
        shutil.copyfile(CREDITS_FONT, proj.cache / "fonts" / CREDITS_FONT.name)
        sb["font"] = f"fonts/{CREDITS_FONT.name}"
    proj.storyboard.write_text(json.dumps(sb, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"음악: {Path(music_src).name} ({analysis['bpm']} BPM)")
    for f, p in sb["formats"].items():
        n = len(p["shots"]) - 2
        print(f"  {f}: {p['musicEnd'] - p['musicStart']:.1f}초, 장면 {n}개" + (f", 자리가 없어 뺀 항목 {p['dropped']}개" if p["dropped"] else ""))
    print(section_report(sb["sections"]))
    if sb["sections"]["ignored"]:
        print(f"  놓을 수 없어 무시한 마커(곡 밖이거나 앞 마커보다 이름): {', '.join(sb['sections']['ignored'])}")


def section_report(sec: dict) -> str:
    def fmt(name):
        t = sec.get(name)
        if t is None:
            return f"{name} 없음"
        m, s = divmod(t, 60)
        return f"{name} {int(m)}:{s:04.1f}" + ("(추정)" if name in sec.get("estimated", []) else "")
    return "구간: " + ", ".join(fmt(n) for n in plan.SECTION_NAMES)


def cmd_studio(args) -> None:
    proj = project(args.project)
    subprocess.run(["npx", "remotion", "studio", "src/index.ts", f"--public-dir={proj.cache}"], cwd=RENDER_DIR)


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_") if name else ""


def _render_one(proj: Project, comp: str, out: Path, captions: list[dict], props: dict | None = None) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["npx", "remotion", "render", "src/index.ts", comp, str(out), f"--public-dir={proj.cache}"]
    if props is not None:
        cmd.append(f"--props={json.dumps(props)}")
    if subprocess.run(cmd, cwd=RENDER_DIR).returncode:
        raise SystemExit(f"{out.name} 렌더 실패")
    out.with_suffix(".srt").write_text(longform.srt(captions), encoding="utf-8")
    print(f"완성: {out} (+ {out.with_suffix('.srt').name})")


def _render_longform(proj: Project, sb: dict, formats: list[str]) -> None:
    for f in formats:
        if f == "shorts":
            for i, s in enumerate(sb["formats"]["shorts"]):
                name = "_".join(x for x in (proj.root.name, f"{i + 1:02d}", _safe(s["title"])) if x)
                _render_one(proj, "shorts", proj.output / "shorts" / f"{name}.mp4", s["captions"], {"clip": i})
        else:
            _render_one(proj, f, proj.output / f"{proj.root.name}_{f}.mp4", sb["formats"][f]["captions"])


def cmd_render(args) -> None:
    proj = project(args.project)
    if not proj.storyboard.exists():
        raise SystemExit(f"먼저 plan을 실행하세요: python -m pipeline plan {args.project}")
    sb = json.loads(proj.storyboard.read_text(encoding="utf-8"))
    formats = args.formats.split(",") if args.formats else list(sb["formats"])
    for f in formats:
        if f not in sb["formats"]:
            raise SystemExit(f"storyboard에 '{f}' 형식이 없습니다. selection.json의 formats에 넣고 plan을 다시 실행하세요.")
    if sb.get("mode") == "longform":
        return _render_longform(proj, sb, formats)
    public = render_src.build(proj, formats)  # 원본을 링크로 가리키는 렌더용 폴더 (Studio는 계속 .cache)
    proj.output.mkdir(exist_ok=True)
    for f in formats:
        out = proj.output / f"{proj.root.name}_{f}.mp4"
        r = subprocess.run(["npx", "remotion", "render", "src/index.ts", f, str(out), f"--public-dir={public}"], cwd=RENDER_DIR)
        if r.returncode:
            raise SystemExit(f"{f} 렌더 실패")
        print(f"완성: {out}")
    render_src.clean(public)  # HDR·HEIC 변환본은 렌더가 끝나면 지운다


def _mmss(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    return f"{m // 60}:{m % 60:02d}:{s:02d}" if m >= 60 else f"{m}:{s:02d}"


def cmd_transcribe(args) -> None:
    proj = project(args.project)
    tracks = transcribe.parse_tracks(args.track)
    src = transcribe.source_video(proj, args.file)
    available = transcribe.audio_tracks(src)
    print(f"원본: {src.relative_to(proj.sources).as_posix()}")
    print("오디오 트랙: " + (", ".join(f"{t['track']}번({t['channels']}ch{' ' + t['title'] if t['title'] else ''})"
                                    for t in available) or "없음"))
    t = transcribe.transcribe_project(proj, args.file, tracks)
    who = ", ".join(f"{x['label']}={x['track']}번" + (f"({x['title']})" if x["title"] else "") for x in t["tracks"])
    print(f"전사 완료 ({t['model']}): {t['duration'] / 60:.1f}분, 문장 {len(t['segments'])}개 — {who}")
    if not t["segments"]:
        print("주의: 인식된 말이 없습니다 — 목소리가 다른 트랙에 있으면 --track으로 다시 실행하세요")
    db = json.loads((proj.cache / "loudness.json").read_text(encoding="utf-8"))["db"]
    print("큰 소리 순간: " + ", ".join(_mmss(s) for s in transcribe.loud_moments(db)))


def cmd_music(args) -> None:
    for m in list_music():
        print(m.name)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("convert", "plan", "studio"):
        sub.add_parser(name).add_argument("project")
    pr = sub.add_parser("prepare")
    pr.add_argument("project")
    pr.add_argument("--keep-blur", action="store_true", help="흔들린 사진도 후보로 남긴다")
    tr = sub.add_parser("transcribe")
    tr.add_argument("project")
    tr.add_argument("--track", default="1", help="전사할 오디오 트랙 번호. 사람별 트랙이면 2,3처럼 여러 개 (1부터, OBS 1번 = 전체 믹스)")
    tr.add_argument("--file", default=None, help="영상소스에 영상이 여러 개일 때 고를 파일")
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
                "studio": cmd_studio, "render": cmd_render, "music": cmd_music, "transcribe": cmd_transcribe}
    try:
        handlers[args.cmd](args)
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        raise SystemExit(f"오류: {e}")


if __name__ == "__main__":
    main()
