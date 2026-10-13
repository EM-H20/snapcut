import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

from . import capture, check, contact, convert, curate, edit, ff, highlights, intro, kits, longform, master, music, plan, render_src, template, transcribe
from .hf import engine, long as hf_long, mv
from .paths import SHARED, Project, project

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
    key = hashlib.sha1(json.dumps([fmt, video, CARD_BG_SOURCE, plan.CARD_SECONDS]).encode()).hexdigest()[:10]
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


def _card(proj: Project, template: str, fmt: str, text: str, sub: str, video: tuple[str, float] | None = None,
          exit: bool = False, layout: str | None = None) -> str:
    mtime = intro.template_file(template, fmt).stat().st_mtime
    if layout is None:  # 사진 배경이면 글씨를 사진 안쪽으로
        layout = "center" if video and Path(video[0]).suffix.lower() == ".jpg" else "wide"
    key = hashlib.sha1(json.dumps([template, fmt, text, sub, mtime, video, layout, CARD_BG_SOURCE, exit],
                                  ensure_ascii=False).encode()).hexdigest()[:10]
    dst = proj.cache / "cards" / f"{key}.mp4"
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        part = dst.with_name(f"{key}.part.mp4")
        try:
            intro.render_card(template, fmt, text, sub, part, _card_bg(proj, fmt, video), layout, exit)
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
    style = longform.load_style(spec["captionStyle"])
    sb, warnings = longform.build(spec, tr, "src/" + tr["source"], style)
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
    outro_layout = sel.get("outroLayout")
    if outro_layout not in (None, "wide", "center", "top", "low"):
        raise SystemExit(f'selection.json의 outroLayout은 "wide", "center", "top", "low" 중 하나여야 합니다 (top: 단체 사진처럼 사람이 화면을 채울 때 글씨를 위쪽에, low: 화면 2/3 아래쪽 한 줄): {outro_layout!r}')
    cards = {f: {"intro": _card(proj, card_tpl, f, sel.get("title", ""), sel.get("subtitle", ""), intro_video),
                 "outro": _card(proj, card_tpl, f, sel.get("ending", ""), "", outro_video, exit=True, layout=outro_layout)}
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
    if (edit.work(proj) / "index.html").exists():
        return engine.preview(edit.work(proj), hf=edit.HF)
    if not proj.storyboard.exists():
        raise SystemExit(f"먼저 plan을 실행하세요: python -m pipeline plan {args.project}")
    sb = json.loads(proj.storyboard.read_text(encoding="utf-8"))
    if sb.get("mode") == "longform":
        fmt = args.format or next(iter(sb["formats"]))
        page = hf_long.build(sb, fmt)
    else:
        fmt = args.format or next(iter(sb["formats"]))
        if fmt not in sb["formats"]:
            raise SystemExit(f"storyboard에 '{fmt}' 형식이 없습니다 (있는 형식: {', '.join(sb['formats'])})")
        engine.freeze_stills(proj.cache, fmt, sb["formats"][fmt]["shots"])
        page = mv.build(sb, fmt, preview=True)
    (proj.cache / "index.html").write_text(page, encoding="utf-8")
    print(f"미리보기: {fmt} (다른 형식은 --format)")
    engine.preview(proj.cache)


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", name).strip("_") if name else ""


def _render_one(proj: Project, page: str, comp: str, out: Path, captions: list[dict]) -> Path:
    (proj.cache / comp).write_text(page, encoding="utf-8")
    engine.render(proj.cache, comp, out)
    out.with_suffix(".srt").write_text(longform.srt(captions), encoding="utf-8")
    print(f"완성: {out} (+ {out.with_suffix('.srt').name})")
    return out


def _render_longform(proj: Project, sb: dict, formats: list[str]) -> list[Path]:
    outs = []
    for f in formats:
        if f == "shorts":
            for i, s in enumerate(sb["formats"]["shorts"]):
                name = "_".join(x for x in (proj.root.name, f"{i + 1:02d}", _safe(s["title"])) if x)
                outs.append(_render_one(proj, hf_long.build(sb, "shorts", i), f"shorts_{i + 1:02d}.html",
                                        proj.output / "shorts" / f"{name}.mp4", s["captions"]))
        else:
            outs.append(_render_one(proj, hf_long.build(sb, f), f"{f}.html", proj.output / f"{proj.root.name}_{f}.mp4",
                                    sb["formats"][f]["captions"]))
    return outs


def _render_edit(proj: Project) -> None:
    out = proj.output / f"{proj.root.name}_edit.mp4"
    try:
        engine.render(edit.work(proj), "index.html", out, hf=edit.HF, workers=edit.RENDER_WORKERS)
    except RuntimeError as e:
        raise SystemExit(f"{e} — 렌더 실패")
    shutil.copyfile(edit.assets(proj) / "clean.srt", out.with_suffix(".srt"))
    print(f"완성: {out} (+ {out.with_suffix('.srt').name})")
    finish(proj, [out])


def cmd_render(args) -> None:
    proj = project(args.project)
    if (edit.work(proj) / "index.html").exists():
        return _render_edit(proj)
    if not proj.storyboard.exists():
        raise SystemExit(f"먼저 plan을 실행하세요: python -m pipeline plan {args.project}")
    sb = json.loads(proj.storyboard.read_text(encoding="utf-8"))
    formats = args.formats.split(",") if args.formats else list(sb["formats"])
    for f in formats:
        if f not in sb["formats"]:
            raise SystemExit(f"storyboard에 '{f}' 형식이 없습니다. selection.json의 formats에 넣고 plan을 다시 실행하세요.")
    if sb.get("mode") == "longform":
        return finish(proj, _render_longform(proj, sb, formats))
    public = render_src.build(proj, formats)  # 원본을 링크로 가리키는 렌더용 폴더 (미리보기는 계속 .cache)
    rsb = json.loads((public / "storyboard.json").read_text(encoding="utf-8"))
    outs = []
    try:
        for f in formats:
            out = proj.output / f"{proj.root.name}_{f}.mp4"
            engine.freeze_stills(public, f, rsb["formats"][f]["shots"])
            (public / f"{f}.html").write_text(mv.build(rsb, f), encoding="utf-8")
            engine.render(public, f"{f}.html", out)
            print(f"완성: {out}")
            outs.append(out)
    except RuntimeError as e:
        raise SystemExit(f"{e} — 렌더 실패")
    render_src.clean(public)  # HDR·HEIC·멈춘 프레임 변환본은 렌더가 끝나면 지운다
    finish(proj, outs)


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


def cmd_edit(args) -> None:
    proj = project(args.project)
    if args.cuts:
        r = edit.apply(proj)
        index = edit.work(proj) / "index.html"
        print(f"실수 컷 {r['cuts']}구간 적용: {_mmss(r['duration'])} — {edit.assets(proj) / 'clean.mp4'}")
        print(f"{'시작 구성을 만들었습니다' if r['created'] else '기존 구성을 그대로 둡니다'}: {index}")
        if r["resized"]:
            print(f"주의: 길이가 {r['resized'][0]}초 → {r['resized'][1]}초로 바뀌어 구성 길이를 맞췄습니다 — 오버레이 시각을 transcript.json과 다시 맞추세요")
        print(f"다음: 오버레이를 {index.name}에 쓰고 `python -m pipeline studio {proj.root.name}`로 확인")
        return
    r = edit.prepare(proj, args.file, int(args.track))
    a = edit.assets(proj)
    print(f"무음 컷: {r['source']} {_mmss(r['source_duration'])} → {_mmss(r['edited_duration'])} (단어 {r['words']}개)")
    if r["stale"]:
        print(f"주의: 원본·트랙이 바뀌어 예전 자르기 목록을 {edit.assets(proj) / 'approved-cuts.stale.json'}로 옮겼습니다 (시각이 맞지 않음)")
    print(f"실수 후보 {len(r['candidates'])}개: {a / 'candidates.json'} (시간은 silenced.mp4 기준)")
    print(f"다음: 후보와 {a / 'raw.silence-transcript.json'}의 문장을 읽고 {a / 'approved-cuts.json'}에 "
          f'{{"cuts": [{{"start": 초, "end": 초, "reason": "…"}}]}}를 쓴 뒤 `python -m pipeline edit {proj.root.name} --cuts`')


def cmd_words(args) -> None:
    src = Path(args.file).expanduser()
    if not src.is_file():
        raise SystemExit(f"파일이 없습니다: {src}")
    out = Path(args.out).expanduser() if args.out else src.with_name(src.stem + ".words.json")
    d = edit.transcribe_file(src, out)
    print(f"단어 {len(d['words'])}개, {d['audio_duration_secs']:.1f}초 → {out}")


def cmd_capture(args) -> None:
    page = Path(args.page).expanduser()
    if not page.exists():
        raise SystemExit(f"페이지(또는 빌드된 사이트 폴더)가 없습니다: {page}")
    try:
        size = tuple(int(x) for x in args.size.lower().split("x"))
        assert len(size) == 2
    except (ValueError, AssertionError):
        raise SystemExit(f"--size는 WxH 형태여야 합니다 (예: 1080x1920): {args.size}")
    n = capture.render(page, Path(args.out).expanduser(), args.seconds, args.fps, size)
    print(f"완성: {args.out} ({n}프레임, {args.fps:g}fps, 소리 없음)")


def run_checks(proj: Project, files: list[Path], fmt: str | None = None) -> bool:
    """mp4들을 점검하고 output/check.json에 남긴다. 전부 통과하면 True."""
    sb = json.loads(proj.storyboard.read_text(encoding="utf-8")) if proj.storyboard.exists() else None
    results = {}
    for f in files:
        view = check.plan_view(sb, fmt or check.format_of(f, sb))
        results[f.name] = r = check.check_file(f, view, proj.output / "check" / f.stem)
        print(check.summary(f.name, r))
    proj.output.mkdir(exist_ok=True)
    (proj.output / "check.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return all(r["ok"] for r in results.values())


def finish(proj: Project, outs: list[Path]) -> None:
    """렌더 직후: 음량 마스터링 → 품질 점검. 점검 실패는 알리기만 한다 (파일은 남김)."""
    outs = [o for o in outs if o.exists()]
    for o in outs:
        if done := master.master(o):
            print(f"{_mastered(done)}: {o.name}")
    if outs and not run_checks(proj, outs):
        print("주의: 점검 실패 항목이 있습니다 — 완성이라고 하지 말고 위 항목부터 고치세요")


def _mastered(done: list[str]) -> str:
    return ", ".join({"color": "색 bt709 변환", "loudness": "음량 -14 LUFS"}[d] for d in done)


def cmd_master(args) -> None:
    f = Path(args.mp4).expanduser()
    done = master.master(f)
    if done:
        print(f"{_mastered(done)}: {f.name}")
    else:
        print(f"{'이미 기준 안' if check.media_info(f)['has_audio'] else '소리 없음 — 바꿀 것 없음'}: {f.name}")


def cmd_check(args) -> None:
    proj = project(args.project, require_sources=False)
    files = [Path(args.mp4).expanduser()] if args.mp4 else sorted(proj.output.rglob("*.mp4"))
    if not files:
        raise SystemExit(f"점검할 mp4가 없습니다: {proj.output}")
    if not run_checks(proj, files, args.format):
        raise SystemExit("점검 실패 — 위 항목을 고친 뒤 다시 렌더하세요")


def cmd_music(args) -> None:
    for m in list_music():
        print(m.name)


def cmd_kits(args) -> None:
    lock = kits.load_lock()
    for w in kits.sync(lock):
        print(f"경고: {w}")
    for line in kits.status(lock):
        print(line)
    print(kits.node_tools())


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("convert", "plan"):
        sub.add_parser(name).add_argument("project")
    st = sub.add_parser("studio")
    st.add_argument("project")
    st.add_argument("--format", default=None, help="미리볼 형식 (youtube, reels, longform, shorts — 없으면 첫 형식)")
    pr = sub.add_parser("prepare")
    pr.add_argument("project")
    pr.add_argument("--keep-blur", action="store_true", help="흔들린 사진도 후보로 남긴다")
    tr = sub.add_parser("transcribe")
    tr.add_argument("project")
    tr.add_argument("--track", default="1", help="전사할 오디오 트랙 번호. 사람별 트랙이면 2,3처럼 여러 개 (1부터, OBS 1번 = 전체 믹스)")
    tr.add_argument("--file", default=None, help="영상소스에 영상이 여러 개일 때 고를 파일")
    ed = sub.add_parser("edit")
    ed.add_argument("project")
    ed.add_argument("--file", default=None, help="영상소스에 영상이 여러 개일 때 고를 파일")
    ed.add_argument("--track", default="1", help="목소리 오디오 트랙 번호 (1부터)")
    ed.add_argument("--cuts", action="store_true", help="approved-cuts.json을 적용해 clean.mp4와 시작 구성을 만든다")
    wd = sub.add_parser("words")
    wd.add_argument("file", help="음성(또는 영상) 파일")
    wd.add_argument("--out", default=None, help="결과 JSON (기본: <파일>.words.json)")
    cp = sub.add_parser("capture", help="window.seek(t) 페이지(또는 빌드된 사이트 폴더) → mp4")
    cp.add_argument("page")
    cp.add_argument("out")
    cp.add_argument("--seconds", type=float, required=True)
    cp.add_argument("--fps", type=float, default=30.0)
    cp.add_argument("--size", default="1920x1080")
    r = sub.add_parser("render")
    r.add_argument("project")
    r.add_argument("--formats", default=None)
    sub.add_parser("music")
    sub.add_parser("kits")
    ms = sub.add_parser("master")
    ms.add_argument("mp4")
    ck = sub.add_parser("check")
    ck.add_argument("project")
    ck.add_argument("mp4", nargs="?", default=None, help="점검할 파일 (없으면 output/의 mp4 전부)")
    ck.add_argument("--format", default=None, help="storyboard 형식 이름 (파일 이름으로 못 찾을 때)")
    args = p.parse_args(argv)
    needs = ([] if args.cmd in ("music", "kits") else [("ffmpeg", "brew install ffmpeg")]) + \
        ([("npx", "Node.js 설치")] if args.cmd in ("plan", "studio", "render") else []) + \
        ([("node", "Node.js 설치")] if args.cmd == "edit" else [])
    for tool, hint in needs:
        if not shutil.which(tool):
            raise SystemExit(f"{tool}이(가) 없습니다. 설치: {hint}")
    handlers = {"convert": cmd_convert, "prepare": cmd_prepare, "plan": cmd_plan,
                "studio": cmd_studio, "render": cmd_render, "music": cmd_music, "transcribe": cmd_transcribe, "edit": cmd_edit, "words": cmd_words, "capture": cmd_capture, "kits": cmd_kits, "check": cmd_check, "master": cmd_master}
    try:
        handlers[args.cmd](args)
    except (ValueError, RuntimeError, FileNotFoundError) as e:
        raise SystemExit(f"오류: {e}")


if __name__ == "__main__":
    main()
