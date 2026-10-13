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
