from pipeline import edit
from pipeline.whisper import Segment

SILENCE_LOG = """[silencedetect @ 0x1] silence_start: 2.66
[silencedetect @ 0x1] silence_end: 4.3 | silence_duration: 1.64
[silencedetect @ 0x1] silence_start: 5.9
"""


def test_parse_silence_closes_open_silence_at_duration():
    assert edit.parse_silence(SILENCE_LOG, 6.5) == [(2.66, 4.3), (5.9, 6.5)]


def test_fit_words_moves_edges_out_of_silence():
    silences = [(2.66, 4.3), (5.9, 6.5)]
    words = edit.fit_words([Segment(0.03, 0.54, "안녕하세요."),
                            Segment(1.72, 2.9, "갑니다."),        # 끝이 무음에 걸침 → 무음 시작에서 끝
                            Segment(2.63, 4.49, "날씨가"),        # 무음을 품음, 뒤쪽이 김 → 무음 끝에서 시작
                            Segment(4.8, 6.2, "좋네요."),         # 끝이 무음에 걸침
                            Segment(6.0, 6.4, "감사합니다.")], silences)  # 통째로 무음 안 → 환청
    assert [(w["text"], w["start"], w["end"]) for w in words] == [
        ("안녕하세요.", 0.03, 0.54), ("갑니다.", 1.72, 2.66), ("날씨가", 4.3, 4.49), ("좋네요.", 4.8, 5.9)]
    assert all(w["type"] == "word" for w in words)


def test_fit_words_keeps_zero_length_words():
    words = edit.fit_words([Segment(4.4, 4.4, "정말")], [(2.66, 4.3)])
    assert [(w["start"], w["end"]) for w in words] == [(4.4, 4.4)]


def test_kit_transcript_shape():
    words = [{"text": "안녕.", "start": 0.1, "end": 0.5, "type": "word"}, {"text": "네", "start": 0.6, "end": 0.8, "type": "word"}]
    t = edit.kit_transcript(words, 3.21)
    assert t == {"language_code": "ko", "audio_duration_secs": 3.21, "text": "안녕. 네", "words": words}


def test_cues_break_on_sentence_end_gap_and_length():
    w = lambda t, a, b: {"text": t, "start": a, "end": b}
    cues = edit.cues([w("안녕하세요.", 0.0, 0.5), w("오늘은", 0.6, 0.9), w("산에", 1.0, 1.2),
                      w("갑니다", 2.0, 2.4), w("아주아주아주아주", 2.5, 3.0), w("길어요길어요", 3.1, 3.3)])
    assert [(c["text"], c["start"], c["end"]) for c in cues] == [
        ("안녕하세요.", 0.0, 0.5), ("오늘은 산에", 0.6, 1.2), ("갑니다 아주아주아주아주", 2.0, 3.0), ("길어요길어요", 3.1, 3.3)]


def test_stutters_match_korean_tokens_like_the_kit_rule():
    w = lambda t, a, b: {"text": t, "start": a, "end": b}
    c = edit.stutters([w("오늘은", 0.2, 1.0), w("오늘은,", 1.05, 1.8), w("산에", 1.9, 2.3), w("산에", 3.0, 3.4)])
    assert c == [{"id": "k001", "type": "stutter", "confidence": "high", "recommend": "cut",
                  "cut": {"start": 0.2, "end": 1.05}, "removes": "오늘은", "keeps": "오늘은,", "note": '반복 "오늘은"'}]


# ---- prepare: 실제 ffmpeg + 실제 키트 스크립트, 가짜 whisper ----
import json
import subprocess

import pytest

from pipeline.paths import Project

needs_kit = pytest.mark.skipif(not edit.CUT_SILENCES.exists(), reason="student-kit 필요 (python -m pipeline kits)")
TALK = [Segment(0.2, 1.0, "오늘은"), Segment(1.05, 1.8, "오늘은"), Segment(2.3, 4.9, "산에"), Segment(5.0, 5.8, "갑니다.")]


class FakeEngine:
    def __init__(self, segs):
        self.segs, self.calls = segs, 0

    def transcribe(self, wav, language="ko", words=False):
        assert words
        self.calls += 1
        return self.segs


def _talk_project(tmp_path, tracks=1) -> Project:
    """6초 영상: 0–2.5초·4.5–6초 소리, 사이 2초 무음. tracks=2면 두 번째 오디오 트랙(무음)을 덧붙인다."""
    (tmp_path / "영상소스").mkdir()
    tone = "aevalsrc='if(between(t,2.5,4.5),0,0.3*sin(2*PI*440*t))':s=48000:d=6"
    extra = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-map", "0:v", "-map", "1:a", "-map", "2:a"] if tracks == 2 else []
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=320x240:r=30:d=6", "-f", "lavfi", "-i", tone,
                    *extra, "-t", "6", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    str(tmp_path / "영상소스" / "talk.mov")], check=True)
    return Project(tmp_path)


@needs_kit
def test_prepare_writes_kit_transcript_and_runs_silence_cut(tmp_path):
    proj = _talk_project(tmp_path, tracks=2)
    eng = FakeEngine(TALK)
    r = edit.prepare(proj, engine_factory=lambda m: eng, download=lambda m: None)
    a = edit.assets(proj)
    raw = json.loads((a / "raw.json").read_text(encoding="utf-8"))
    assert [w["text"] for w in raw["words"]] == ["오늘은", "오늘은", "산에", "갑니다."]
    assert raw["words"][2]["start"] >= 4.4  # 무음을 삼킨 단어가 무음 끝으로
    streams = [s["codec_type"] for s in __import__("pipeline").ff.probe(a / "raw.mp4")["streams"]]
    assert streams == ["video", "audio"]  # 키트는 영상 1·오디오 1
    assert (a / "silenced.mp4").exists() and r["edited_duration"] < r["source_duration"] - 1.0
    assert [c["id"] for c in r["candidates"]] == ["k001"]
    assert json.loads((a / "candidates.json").read_text(encoding="utf-8"))["candidates"] == r["candidates"]
    edit.prepare(proj, engine_factory=lambda m: eng, download=lambda m: None)
    assert eng.calls == 1  # 같은 원본·트랙이면 전사를 다시 하지 않는다


def test_prepare_without_kit_says_how_to_get_it(tmp_path, monkeypatch):
    monkeypatch.setattr(edit, "CUT_SILENCES", tmp_path / "none.mjs")
    with pytest.raises(RuntimeError, match="python -m pipeline kits"):
        edit.prepare(Project(tmp_path))


def test_prepare_rejects_missing_track(tmp_path):
    proj = _talk_project(tmp_path)
    with pytest.raises(ValueError, match="트랙 3"):
        edit.prepare(proj, track=3, engine_factory=lambda m: FakeEngine(TALK), download=lambda m: None)


def test_starter_fits_long_side_and_floors_to_frames():
    page = edit.starter(3840, 2160, 5.4321)
    assert 'data-width="1920" data-height="1080"' in page
    assert 'data-duration="5.4"' in page  # 162프레임
    assert '<video id="clean" src="assets/clean.mp4"' in page and "muted" in page
    assert '<audio id="clean-audio" src="assets/clean.mp4"' in page
    assert 'data-width="1080" data-height="1920"' in edit.starter(1080, 1920, 3.0)


def test_apply_needs_prepare_first(tmp_path):
    with pytest.raises(RuntimeError, match="pipeline edit"):
        edit.apply(Project(tmp_path))


@needs_kit
def test_apply_cuts_writes_transcript_srt_and_keeps_existing_index(tmp_path):
    proj = _talk_project(tmp_path)
    r = edit.prepare(proj, engine_factory=lambda m: FakeEngine(TALK), download=lambda m: None)
    a = edit.assets(proj)
    with pytest.raises(RuntimeError, match='{"cuts": \\[\\]}'):
        edit.apply(proj)
    k = r["candidates"][0]["cut"]
    (a / "approved-cuts.json").write_text(json.dumps({"cuts": [{**k, "reason": "말더듬"}]}), encoding="utf-8")
    out = edit.apply(proj)
    words = json.loads((a / "transcript.json").read_text(encoding="utf-8"))["words"]
    assert [w["text"] for w in words] == ["오늘은", "산에", "갑니다."]
    assert "오늘은 산에" in (a / "clean.srt").read_text(encoding="utf-8")
    assert out["created"] and (edit.work(proj) / "index.html").exists()
    (edit.work(proj) / "index.html").write_text("mine", encoding="utf-8")
    assert not edit.apply(proj)["created"]
    assert (edit.work(proj) / "index.html").read_text(encoding="utf-8") == "mine"
