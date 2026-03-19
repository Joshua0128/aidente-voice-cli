import io
import asyncio
from pathlib import Path
from pydub import AudioSegment
from pydub.generators import Sine
from aidente_voice.parser import parse
from aidente_voice.pipeline.orchestrator import run_pipeline
from aidente_voice.pipeline.assembler import assemble


def _make_wav_bytes(duration_ms: int = 300) -> bytes:
    seg = (
        Sine(440)
        .to_audio_segment(duration=duration_ms)
        .set_frame_rate(24000)
        .set_channels(1)
        .set_sample_width(2)
    )
    buf = io.BytesIO()
    seg.export(buf, format="wav")
    return buf.getvalue()


class FakeTTSClient:
    async def synthesize(self, text: str, seed: int = 0) -> bytes:
        return _make_wav_bytes(300)


async def _run(script: str, sfx_dir: Path) -> AudioSegment:
    chunks = parse(script)
    results = await run_pipeline(chunks, client=FakeTTSClient())
    return assemble(results, sfx_dir=sfx_dir)


def test_tts_plus_pause(tmp_path):
    script = "Hello world。 <pause=0.5> Goodbye world。"
    result = asyncio.run(_run(script, sfx_dir=tmp_path))
    # 2 × 300ms audio + 500ms pause = ~1100ms
    assert len(result) >= 1000


def test_tts_with_speed(tmp_path):
    script = "Slow sentence。 <speed=1.0>"  # speed=1.0 avoids needing ffmpeg
    result = asyncio.run(_run(script, sfx_dir=tmp_path))
    assert len(result) > 0


def test_sfx_splice(tmp_path):
    sfx = _make_wav_bytes(200)
    (tmp_path / "laugh.wav").write_bytes(sfx)

    script = "Hello。 <sfx=laugh>"
    result = asyncio.run(_run(script, sfx_dir=tmp_path))
    assert len(result) >= 400


def test_full_script(tmp_path):
    sfx = _make_wav_bytes(200)
    (tmp_path / "laugh.wav").write_bytes(sfx)

    script = (
        "接下來我們要講述一個非常關鍵的底層概念。\n"
        "很多人在這裡會搞錯， <pause=0.5> <sfx=laugh>"
    )
    result = asyncio.run(_run(script, sfx_dir=tmp_path))
    assert len(result) >= 1200
