from aidente_voice.models import Chunk

def test_tts_chunk_defaults():
    c = Chunk(index=0, type="tts", text="hello")
    assert c.speed == 1.0
    assert c.gacha_n == 1
    assert c.sfx_name is None
    assert c.sfx_fade == 0.05

def test_pause_chunk():
    c = Chunk(index=1, type="pause", duration=0.5)
    assert c.duration == 0.5
    assert c.text is None

def test_sfx_chunk_custom_fade():
    c = Chunk(index=2, type="sfx", sfx_name="laugh", sfx_fade=0.1)
    assert c.sfx_name == "laugh"
    assert c.sfx_fade == 0.1

def test_gacha_chunk():
    c = Chunk(index=3, type="gacha", text="test", gacha_n=3)
    assert c.gacha_n == 3
    assert c.type == "gacha"
