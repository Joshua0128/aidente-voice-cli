import pytest
from aidente_voice.parser import parse, ParseError

def test_plain_tts():
    chunks = parse("Hello world。")
    assert len(chunks) == 1
    assert chunks[0].type == "tts"
    assert chunks[0].text == "Hello world。"
    assert chunks[0].speed == 1.0

def test_speed_tag_attaches_to_preceding():
    chunks = parse("Slow sentence。 <speed=0.85>")
    assert chunks[0].type == "tts"
    assert chunks[0].speed == 0.85

def test_speed_tag_at_start_raises():
    with pytest.raises(ParseError, match="no preceding sentence"):
        parse("<speed=0.85> Some sentence。")

def test_pause_tag():
    chunks = parse("First。 <pause=1.5> Second。")
    assert chunks[0].type == "tts"
    assert chunks[0].text == "First。"
    assert chunks[1].type == "pause"
    assert chunks[1].duration == 1.5
    assert chunks[2].type == "tts"
    assert chunks[2].text == "Second。"

def test_sfx_tag_simple():
    chunks = parse("Hello。 <sfx=laugh>")
    assert chunks[0].type == "tts"
    assert chunks[1].type == "sfx"
    assert chunks[1].sfx_name == "laugh"
    assert chunks[1].sfx_fade == 0.05

def test_sfx_tag_custom_fade():
    chunks = parse("Hello。 <sfx=laugh,fade=0.1>")
    assert chunks[1].sfx_fade == 0.1

def test_sfx_fade_zero():
    chunks = parse("Hello。 <sfx=laugh,fade=0>")
    assert chunks[1].sfx_fade == 0.0

def test_gacha_consumes_next_text():
    chunks = parse("<gacha=3> Uncertain sentence。")
    assert len(chunks) == 1
    assert chunks[0].type == "gacha"
    assert chunks[0].text == "Uncertain sentence。"
    assert chunks[0].gacha_n == 3

def test_gacha_defers_sfx_after_text():
    chunks = parse("<gacha=3> <sfx=laugh> Uncertain sentence。")
    assert chunks[0].type == "gacha"
    assert chunks[0].text == "Uncertain sentence。"
    assert chunks[1].type == "sfx"
    assert chunks[1].sfx_name == "laugh"

def test_full_example():
    text = "接下來我們要講述一個非常關鍵的底層概念。 <speed=0.85>\n很多人在這裡會搞錯， <pause=0.5> <gacha=3> <sfx=laugh> 其實這沒有想像中困難。"
    chunks = parse(text)
    assert len(chunks) == 5
    assert chunks[0].type == "tts" and chunks[0].speed == 0.85
    assert chunks[1].type == "tts"
    assert chunks[2].type == "pause" and chunks[2].duration == 0.5
    assert chunks[3].type == "gacha" and chunks[3].gacha_n == 3
    assert chunks[4].type == "sfx" and chunks[4].sfx_name == "laugh"
    for i, c in enumerate(chunks):
        assert c.index == i

def test_empty_text_segments_ignored():
    chunks = parse("Hello。\n\nWorld。")
    assert len(chunks) == 2
