import re

from pipeline.hf import captions, long

CAPS = [
    {"start": 0.3, "end": 2.3, "text": "첫 문장", "name": "나", "place": "bar"},
    {"start": 1.0, "end": 3.0, "text": "친구 말", "name": "친구", "place": "left"},
    {"start": 1.5, "end": 2.0, "text": "또 친구", "name": "셋째", "place": "left"},
    {"start": 5.0, "end": 6.0, "text": "예전 자막"},
]


def test_active_by_place_start_inclusive_end_exclusive():
    assert captions.active_by_place(CAPS, 0.0) == {"bar": [], "left": [], "right": []}
    assert [c["text"] for c in captions.active_by_place(CAPS, 1.6)["left"]] == ["친구 말", "또 친구"]
    assert captions.active_by_place(CAPS, 2.3)["bar"] == []
    assert [c["text"] for c in captions.active_by_place(CAPS, 5.5)["bar"]] == ["예전 자막"]


def test_states_merge_overlaps_and_skip_gaps():
    st = captions.states(CAPS, 30)
    assert [(a, b) for a, b, _ in st] == [(9, 30), (30, 45), (45, 60), (60, 69), (69, 90), (150, 180)]
    assert [c["text"] for c in st[2][2]["left"]] == ["친구 말", "또 친구"]


SB = {"mode": "longform", "fps": 30, "src": "src/game.mkv", "captionStyle": None, "formats": {
    "longform": {"width": 1920, "height": 1080, "duration": 7.8,
                 "clips": [{"in": 1.0, "out": 4.0, "start": 0.0, "end": 3.8, "title": "시작"},
                           {"in": 10.0, "out": 14.0, "start": 3.8, "end": 7.8, "title": ""}],
                 "captions": CAPS},
    "shorts": [{"width": 1080, "height": 1920, "duration": 3.8, "title": "시작",
                "clips": [{"in": 1.0, "out": 4.0, "start": 0.0, "end": 3.8, "title": "시작"}], "captions": []}]}}


def test_longform_clips_and_captions():
    html = long.build(SB, "longform")
    assert re.search(r'<video id="c1" src="src/game.mkv" data-start="3.800000" data-duration="4.000000" data-media-start="10.000000"[^>]*data-has-audio="true"', html)
    assert html.count('class="clip cap"') == 6 and "첫 문장" in html and "친구" in html
    assert 'data-duration="7.8"' in html


def test_shorts_without_captions_builds():
    html = long.build(SB, "shorts", 0)
    assert '<div class="shortsbg">' in html and re.search(r'<video id="b0"[^>]*\bmuted\b[^>]*object-fit:cover', html)
    assert 'class="clip cap"' not in html and 'data-width="1080" data-height="1920"' in html


def test_caption_style_name_variants():
    style = dict(captions.FALLBACK, icon="play", name={"background": "#e5484d", "color": "#fff", "radius": 8, "separator": False, "position": "above", "stroke": "#000"})
    html = captions.layer([CAPS[0]], style, 1920, 1080, False, 30)
    assert "-webkit-text-stroke" in html and "#ff0033" in html
