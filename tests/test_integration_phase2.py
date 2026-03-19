"""Phase 2 integration tests: gacha workflow."""

import io
import math
import struct
import wave
from pathlib import Path
from unittest.mock import patch

import pytest

from aidente_voice.models import Chunk
from aidente_voice.pipeline.assembler import assemble
from aidente_voice.pipeline.orchestrator import run_pipeline


def _make_wav_bytes(seed: int = 0, duration_ms: int = 100) -> bytes:
    """Generate a minimal valid WAV at 24kHz mono 16-bit.
    Uses seed to produce distinct audio for each variant.
    """
    sample_rate = 24000
    n_samples = int(sample_rate * duration_ms / 1000)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # Use seed to vary the frequency slightly
        freq = 440 + seed * 10
        frames = struct.pack(f'<{n_samples}h', *[
            int(32767 * math.sin(2 * math.pi * freq * i / sample_rate))
            for i in range(n_samples)
        ])
        wf.writeframes(frames)
    return buf.getvalue()


class FakeTTSClient:
    """Returns distinct audio bytes per seed for deterministic testing."""
    async def synthesize(self, text: str, seed: int = 0) -> bytes:
        return _make_wav_bytes(seed=seed)


@pytest.mark.asyncio
async def test_gacha_selects_correct_variant():
    """Pipeline returns audio for the seed at the selected gacha index."""
    from aidente_voice.gacha import GACHA_SEEDS

    chunks = [
        Chunk(index=0, type="gacha", text="テスト", gacha_n=3),
    ]
    client = FakeTTSClient()

    # User selects variant 2 (index 2, which uses GACHA_SEEDS[2])
    with patch("aidente_voice.pipeline.orchestrator.select_gacha", return_value=2):
        results = await run_pipeline(chunks, client)

    assert len(results) == 1
    chunk, audio_bytes = results[0]
    expected = _make_wav_bytes(seed=GACHA_SEEDS[2])
    assert audio_bytes == expected


@pytest.mark.asyncio
async def test_gacha_mixed_with_tts():
    """Pipeline handles a mix of tts and gacha chunks correctly."""
    from aidente_voice.gacha import GACHA_SEEDS

    chunks = [
        Chunk(index=0, type="tts", text="こんにちは"),
        Chunk(index=1, type="gacha", text="笑い", gacha_n=2),
        Chunk(index=2, type="pause", duration=0.5),
    ]
    client = FakeTTSClient()

    with patch("aidente_voice.pipeline.orchestrator.select_gacha", return_value=1):
        results = await run_pipeline(chunks, client)

    assert len(results) == 3

    # TTS chunk: uses seed=0
    _, tts_audio = results[0]
    assert tts_audio == _make_wav_bytes(seed=0)

    # Gacha chunk: user selected index 1, so uses GACHA_SEEDS[1]
    _, gacha_audio = results[1]
    assert gacha_audio == _make_wav_bytes(seed=GACHA_SEEDS[1])

    # Pause chunk: no audio
    _, pause_audio = results[2]
    assert pause_audio is None
