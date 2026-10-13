import subprocess

import pytest

from pipeline import check

BLACK_LOG = """[blackdetect @ 0x1] black_start:58.466667 black_end:58.5 black_duration:0.0333333
[blackdetect @ 0x1] black_start:88.733333 black_end:89.4 black_duration:0.666667
[blackdetect @ 0x1] black_start:98.3 black_end:99.766667 black_duration:1.46667"""

EBUR_LOG = """[Parsed_ebur128_1 @ 0x2] t: 99.7  TARGET:-23 LUFS    M: -20.1 S: -18.0     I: -15.2 LUFS       LRA:   5.0 LU
[Parsed_ebur128_1 @ 0x2] Summary:

  Integrated loudness:
    I:         -14.7 LUFS
    Threshold: -25.0 LUFS

  Loudness range:
    LRA:         5.2 LU

  True peak:
    Peak:       -4.5 dBFS"""

# 인왕산 storyboard(youtube) 마지막 세 장면 — 실제 값
TAIL = [
    {"type": "collage", "start": 82.733, "end": 86.773, "kenBurns": "still"},
    {"type": "video", "src": "m.mp4", "start": 86.773, "end": 88.793, "in": 10.247, "out": 12.267, "fadeOut": 0.8},
    {"type": "clip", "src": "cards/o.mp4", "start": 88.793, "end": 99.793, "fadeOut": 2.0, "dissolve": 0.8},
]
SB = {"fps": 30, "formats": {"youtube": {"shots": [{"type": "clip", "start": 0.0, "end": 7.918},
                                                    {"type": "photo", "start": 7.918, "end": 58.468},
                                                    {"type": "collage", "start": 58.468, "end": 82.733}] + TAIL}}}
INFO = {"duration": 99.8, "has_audio": True, "color": ("bt709", "bt709", "bt709")}
GOOD_LOUD = {"I": -14.7, "TP": -4.5}


def test_parsers_read_real_ffmpeg_lines():
    assert check.parse_black(BLACK_LOG)[0] == (58.466667, 58.5)
    assert check.parse_loudness(EBUR_LOG) == {"I": -14.7, "TP": -4.5}  # 진행 줄(-15.2)이 아니라 요약 값
    assert check.parse_freeze("lavfi.freezedetect.freeze_start: 5.2\nlavfi.freezedetect.freeze_end: 6.0\n"
                              "lavfi.freezedetect.freeze_start: 9.0") == [(5.2, 6.0), (9.0, None)]
    assert check.parse_cuts("[Parsed_metadata_3 @ 0x3] lavfi.scd.time=10.033\nlavfi.scd.time: 26.1") == [10.033, 26.1]
    assert check.parse_loudness("no summary") is None


def test_plan_view_marks_fade_then_dissolve_as_intended_black():
    v = check.plan_view(SB, "youtube")
    assert v["duration"] == 99.793
    assert v["intended_black"] == [(87.993, 89.593), (97.793, 99.793)]
    assert v["video_spans"] == [(86.773, 88.793)]
    assert v["cuts"][0] == 7.918


def test_judge_flags_only_unintended_black():
    v = check.plan_view(SB, "youtube")
    issues = check.judge(check.parse_black(BLACK_LOG), [], GOOD_LOUD, INFO, v)
    assert [(i["kind"], round(i["at"], 2)) for i in issues] == [("black", 58.47)]


def test_judge_loudness_limits():
    v = check.plan_view(SB, "youtube")
    hot = check.judge([], [], {"I": -7.2, "TP": 1.0}, INFO, v)  # spike의 Remotion 출력
    assert [i["kind"] for i in hot] == ["loudness"]
    edge = check.judge([], [], {"I": -13.0, "TP": -1.0}, INFO, v)  # 경계값은 통과
    assert edge == []
    peak_only = check.judge([], [], {"I": -14.0, "TP": -0.9}, INFO, v)
    assert [i["kind"] for i in peak_only] == ["loudness"]


def test_judge_silent_track_is_an_issue_and_no_audio_skips_loudness():
    v = check.plan_view(SB, "youtube")
    silent = check.judge([], [], {"I": float("-inf"), "TP": float("-inf")}, INFO, v)
    assert [i["kind"] for i in silent] == ["loudness"]
    assert check.judge([], [], None, INFO | {"has_audio": False}, v) == []


def test_judge_freeze_only_inside_planned_video():
    v = check.plan_view(SB, "youtube")
    inside = check.judge([], [(87.0, 87.5)], GOOD_LOUD, INFO, v)
    assert [i["kind"] for i in inside] == ["freeze"]
    assert check.judge([], [(60.0, 64.0)], GOOD_LOUD, INFO, v) == []  # 사진 장면 정지는 정상
    assert check.judge([], [(87.0, 87.5)], GOOD_LOUD, INFO, None) == []  # 계획 없으면 멈춤 판정 안 함


def test_judge_without_plan_allows_only_edge_black():
    info = INFO | {"duration": 30.0}
    issues = check.judge([(0.0, 0.5), (14.0, 14.1), (29.0, 30.0)], [], GOOD_LOUD, info, None)
    assert [(i["kind"], i["at"]) for i in issues] == [("black", 14.0)]


def test_judge_duration_and_color_tags():
    v = check.plan_view(SB, "youtube")
    issues = check.judge([], [], GOOD_LOUD, INFO | {"duration": 100.0, "color": ("bt709", "unknown", "bt709")}, v)
    assert sorted(i["kind"] for i in issues) == ["color", "duration"]


def test_format_of_matches_output_suffix():
    from pathlib import Path
    assert check.format_of(Path("out/인왕산_youtube.mp4"), SB) == "youtube"
    assert check.format_of(Path("out/shorts/인왕산_01_x.mp4"), SB) is None
    assert check.format_of(Path("out/a_youtube.mp4"), None) is None


def test_plan_view_longform_uses_clip_starts_and_no_freeze_spans():
    sb = {"mode": "longform", "formats": {"longform": {"duration": 40.0, "clips": [
        {"in": 10, "out": 30, "start": 0.0, "end": 20.0}, {"in": 50, "out": 70, "start": 20.0, "end": 40.0}]}}}
    assert check.plan_view(sb, "longform") == {"duration": 40.0, "cuts": [20.0], "intended_black": [], "video_spans": []}


def _make_video(path, *colors_and_seconds):
    parts = "".join(f"color=c={c}:s=320x240:r=30:d={d}[v{i}];" for i, (c, d) in enumerate(colors_and_seconds))
    chain = "".join(f"[v{i}]" for i in range(len(colors_and_seconds)))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-filter_complex",
                    f"{parts}{chain}concat=n={len(colors_and_seconds)}:v=1:a=0,"
                    "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709[out]", "-map", "[out]",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)], check=True)


def test_check_file_finds_mid_black_on_real_ffmpeg(tmp_path):
    mp4 = tmp_path / "x.mp4"
    _make_video(mp4, ("gray", 3), ("black", 0.5), ("gray", 3))
    r = check.check_file(mp4, None, tmp_path / "check")
    assert not r["ok"]
    assert [i["kind"] for i in r["issues"]] == ["black"]
    assert abs(r["issues"][0]["at"] - 3.0) < 0.05
    assert r["loudness"] is None  # 오디오 없음
    assert r["sheets"] and all(p.endswith(".jpg") for p in r["sheets"])


def test_plan_view_treats_credits_last_two_seconds_as_intended_black():
    sb = {"formats": {"youtube": {"shots": [
        {"type": "photo", "start": 0.0, "end": 170.0},
        {"type": "credits", "src": "m.mp4", "in": 0, "out": 17.5, "start": 170.0, "end": 187.5, "lines": [], "liveAudio": True}]}}}
    v = check.plan_view(sb, "youtube")
    assert v["intended_black"] == [(185.5, 187.5)]
    assert check.judge([(187.233, 187.5)], [], GOOD_LOUD, INFO | {"duration": 187.5}, v) == []


def test_plan_view_ignores_list_formats_like_shorts():
    sb = {"mode": "longform", "formats": {"longform": {"duration": 40.0, "clips": []}, "shorts": [{"title": "a"}]}}
    assert check.plan_view(sb, "shorts") is None


def test_freeze_tail_is_not_a_video_span():
    sb = {"formats": {"youtube": {"shots": [
        {"type": "video", "start": 0.0, "end": 4.0, "freeze": 1.5},
        {"type": "video", "start": 4.0, "end": 6.0}]}}}
    assert check.plan_view(sb, "youtube")["video_spans"] == [(0.0, 2.5), (4.0, 6.0)]


def test_dark_frame_with_drawn_lines_is_not_black(tmp_path):
    """어두운 화풍(수학 스타일): 거의 검은 바탕에 얇은 밝은 선 — 그려진 것이 있으면 검은 화면이 아니다. 완전히 검은 구간은 계속 잡는다."""
    mp4 = tmp_path / "dark.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-filter_complex",
                    "color=c=gray:s=320x240:r=30:d=3[a];"
                    "color=c=0x0b0d0e:s=320x240:r=30:d=0.5,drawbox=x=100:y=60:w=120:h=120:color=yellow:t=2[b];"
                    "color=c=gray:s=320x240:r=30:d=3[c];color=c=black:s=320x240:r=30:d=0.5[d];color=c=gray:s=320x240:r=30:d=3[e];"
                    "[a][b][c][d][e]concat=n=5:v=1:a=0,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709[out]",
                    "-map", "[out]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mp4)], check=True)
    r = check.check_file(mp4, None, tmp_path / "check")
    blacks = [i for i in r["issues"] if i["kind"] == "black"]
    assert len(blacks) == 1 and 6.4 < blacks[0]["at"] < 6.6  # 상자가 그려진 3.0–3.5초는 빠지고 6.5초 검정만


def test_black_gap_under_a_burned_caption_is_still_black(tmp_path):
    """자막을 태운 모드(롱폼·edit)에서 빠진 클립 = 검은 화면 + 아래쪽 자막 한 줄. 화면 가운데에 그려진 게 없으면 검정이다."""
    mp4 = tmp_path / "gap.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-filter_complex",
                    "color=c=gray:s=320x240:r=30:d=3[a];"
                    "color=c=black:s=320x240:r=30:d=1,drawbox=x=80:y=212:w=160:h=3:color=white:t=fill[b];"
                    "color=c=gray:s=320x240:r=30:d=3[c];"
                    "[a][b][c]concat=n=3:v=1:a=0,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709[out]",
                    "-map", "[out]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(mp4)], check=True)
    r = check.check_file(mp4, None, tmp_path / "check")
    assert [i["kind"] for i in r["issues"]] == ["black"]


def test_film_look_skips_freeze_check_and_says_so():
    sb = {"effects": {"filmLook": True}, "formats": {"youtube": {"shots": [
        {"type": "clip", "start": 0.0, "end": 2.0}, {"type": "video", "start": 2.0, "end": 6.0}]}}}
    view = check.plan_view(sb, "youtube")
    assert view["skip_freeze"]
    issues = check.judge([], [(3.0, 4.0)], None, {"duration": 6.0, "has_audio": False, "color": ("bt709",) * 3}, view)
    assert issues == []  # 노이즈가 2프레임마다 움직여 멈춤 검출이 원래 안 된다 — 거짓 통과 대신 건너뛰고 알린다
    assert "멈춤 검사 건너뜀" in check.summary("x.mp4", {"ok": True, "issues": [], "loudness": None, "sheets": [], "notes": check.notes(view)})
