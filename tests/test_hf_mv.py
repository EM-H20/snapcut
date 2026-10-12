import re
from html.parser import HTMLParser

from pipeline.hf import mv


def _sb(shots, end=None, **plan):
    end = end if end is not None else shots[-1]["end"]
    return {"fps": 30, "music": "music/s.mp3", "formats": {"youtube": {
        "width": 1920, "height": 1080, "musicStart": 1.5, "musicEnd": 1.5 + end, "musicFadeEnd": end, "shots": shots, **plan}}}


ALL = [
    {"type": "clip", "src": "cards/i.mp4", "start": 0.0, "end": 2.0},
    {"type": "photo", "src": "media/p.jpg", "start": 2.0, "end": 4.0, "kenBurns": "zoom-in", "whip": 0.4},
    {"type": "video", "src": "media/v.mp4", "start": 4.0, "end": 6.0, "in": 1.0, "out": 3.0, "liveAudio": True, "dissolve": 0.4},
    {"type": "collage", "srcs": ["media/a.jpg", "media/b.jpg"], "start": 6.0, "end": 8.0, "kenBurns": "still", "wipe": 0.5},
    {"type": "video", "src": "media/w.mp4", "start": 8.0, "end": 12.0, "in": 0.0, "out": 1.25, "liveAudio": False,
     "speed": 0.5, "freeze": 1.5, "shake": 0.5, "dutch": 8.0, "rotate": 90},
    {"type": "video", "src": "media/x.mp4", "start": 12.0, "end": 14.0, "in": 2.0, "out": 4.0, "liveAudio": True,
     "speed": [1.0, 0.3], "blur": 0.6},
    {"type": "video", "src": "media/y.mp4", "start": 14.0, "end": 16.0, "in": 2.0, "out": 4.0, "liveAudio": True,
     "jcut": 0.5, "lcut": 0.4, "fadeOut": 1.0},
    {"type": "clip", "src": "cards/o.mp4", "start": 16.0, "end": 27.0, "fadeOut": 2.0, "dissolve": 0.8},
    {"type": "credits", "src": "media/c.mp4", "in": 0.0, "out": 10.0, "lines": ["운전 A", "총무 B"], "start": 27.0, "end": 37.0, "liveAudio": True},
]


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack, self.found = [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.found.append((tag, a, [x for x in self.stack]))
        if tag not in ("img", "source", "meta", "br"):
            self.stack.append(a)

    def handle_endtag(self, tag):
        if tag not in ("img", "source", "meta", "br") and self.stack:
            self.stack.pop()


def _tags(html):
    t = _Tree()
    t.feed(html)
    return t.found


def test_contract_rules_hold_for_every_shot_type():
    html = mv.build(_sb(ALL), "youtube")
    tags = _tags(html)
    for tag, a, parents in tags:
        if tag == "video" and "data-start" in a:
            assert not any("data-start" in p for p in parents if p.get("id") != "root"), a["id"]  # 시간 있는 조상 금지
        if tag == "audio":
            assert a.get("id")
        assert "crossorigin" not in a
    assert 'window.__timelines["main"] = tl;' in html and 'data-composition-id="main"' in html
    assert not re.search(r'tl\.\w+\("#s\d+",\{[^}]*(visibility|autoAlpha|display)', html)


def test_shot_starts_are_floored():
    shots = [dict(ALL[1], start=0.0, end=1754 / 30, whip=None), dict(ALL[1], start=1754 / 30, end=60.0, whip=None)]
    html = mv.build(_sb([{k: v for k, v in s.items() if v is not None} for s in shots]), "youtube")
    assert 'id="s1" class="clip shot" data-start="58.466666"' in html


def test_dissolve_extends_previous_and_fades_in():
    html = mv.build(_sb(ALL), "youtube")
    assert re.search(r'id="s1" class="clip shot" data-start="2.000000" data-duration="2.400000"', html)
    assert 'tl.fromTo("#s2",{"opacity": 0},{"opacity": 1, "duration": 0.4' in html
    assert re.search(r'id="s2" class="shot" style="z-index:3;opacity:0"', html)


def test_speed_freeze_and_ramp():
    html = mv.build(_sb(ALL), "youtube")
    assert re.search(r'<video id="v4"[^>]*data-duration="2.500000"[^>]*data-playback-rate="0.5"', html)
    assert re.search(r'<img class="clip" src="freeze/youtube_s4.jpg" data-start="10.500000" data-duration="1.500000"', html)
    lane = re.search(r'<video id="v5"[^>]*data-automation="([^"]+)"', html).group(1)
    assert "&quot;rate&quot;" in lane and "0.3" in lane


def test_freeze_still_keeps_rotation():
    html = mv.build(_sb(ALL), "youtube")
    still = re.search(r'<img class="clip" src="freeze/youtube_s4.jpg"[^>]*style="([^"]+)"', html).group(1)
    video = re.search(r'<video id="v4"[^>]*style="([^"]+)"', html).group(1)
    assert "rotate(90deg)" in still and still == video


def test_jcut_lcut_split_sound_from_picture():
    html = mv.build(_sb(ALL), "youtube")
    assert re.search(r'<video id="v6"[^>]*\bmuted\b', html)
    assert re.search(r'<audio id="a6" src="media/y.mp4" data-start="13.500000" data-duration="2.900000" data-media-start="1.500000"', html)


def test_shake_is_deterministic_and_dutch_rotates():
    a, b = mv.build(_sb(ALL), "youtube"), mv.build(_sb(ALL), "youtube")
    assert a == b and 'tl.fromTo("#s4-h"' in a
    assert "rotate(8deg) scale(" in a


def test_whip_wipe_blur_tweens_on_both_sides():
    html = mv.build(_sb(ALL), "youtube")
    assert 'tl.fromTo("#s0",{"xPercent": 0' in html and 'tl.fromTo("#s1",{"xPercent": 30' in html
    assert '"clipPath": "inset(0% 100% 0% 0%)"' in html and "clip-path:inset(0% 100% 0% 0%)" in html
    assert 'tl.fromTo("#s4",{"filter": "blur(0px)"' in html and 'tl.fromTo("#s5",{"filter": "blur(30.0px)"' in html


def test_credits_roll_and_darken():
    html = mv.build(_sb(ALL), "youtube")
    assert 'tl.fromTo("#s8-roll",{"y": 1080},{"y": -' in html
    assert 'tl.fromTo("#s8-dark",{"opacity": 0},{"opacity": 1, "duration": 2.0' in html and ",35.000000);" in html


def test_music_lane_and_root_duration():
    html = mv.build(_sb(ALL), "youtube")
    assert re.search(r'<audio id="music" src="music/s.mp3" data-start="0" data-duration="37.000000" data-media-start="1.500000"', html)
    assert 'data-duration="37.0"' in html  # 루트


def test_preview_adds_labels_render_does_not():
    assert 'class="clip tag"' not in mv.build(_sb(ALL), "youtube")
    p = mv.build(_sb(ALL), "youtube", preview=True)
    assert '>p<' in p and 'addEventListener("keydown"' in p


def test_credits_font_named_only_when_shipped():
    # @font-face 없이 글꼴 이름만 쓰면 lint 오류(font_family_without_font_face) — 크레딧 글꼴이 있을 때만 이름을 쓴다
    assert "SnapcutHand" not in mv.build(_sb(ALL), "youtube")
    html = mv.build(dict(_sb(ALL), font="fonts/hand.ttf"), "youtube")
    assert '@font-face{font-family:SnapcutHand;src:url("fonts/hand.ttf")}' in html and "font-family:SnapcutHand" in html
