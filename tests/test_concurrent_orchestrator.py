"""Tests for concurrent pipeline orchestrator."""

import asyncio
from unittest.mock import patch, MagicMock
import pytest

from aidente_voice.models import Chunk
from aidente_voice.pipeline.orchestrator import run_pipeline


class FakeTTSClient:
    def __init__(self):
        self.calls: list[tuple[str, int]] = []
        self.concurrent_count = 0
        self.max_concurrent_seen = 0

    async def synthesize(self, text: str, seed: int = 0) -> bytes:
        self.concurrent_count += 1
        self.max_concurrent_seen = max(self.max_concurrent_seen, self.concurrent_count)
        self.calls.append((text, seed))
        await asyncio.sleep(0)  # yield - concurrent tasks can run here
        self.concurrent_count -= 1
        return f"AUDIO_{text}_{seed}".encode()


@pytest.mark.asyncio
async def test_concurrent_synthesis_respects_semaphore():
    """max_concurrent=2 should limit concurrent API calls to 2."""
    chunks = [
        Chunk(index=i, type="tts", text=f"chunk{i}")
        for i in range(5)
    ]
    client = FakeTTSClient()

    results = await run_pipeline(chunks, client, max_concurrent=2)

    assert len(results) == 5
    # All chunks synthesized
    assert all(audio is not None for _, audio in results)
    # Concurrency was bounded
    assert client.max_concurrent_seen <= 2


@pytest.mark.asyncio
async def test_output_order_preserved():
    """Results must match input chunk order regardless of completion order."""
    chunks = [
        Chunk(index=0, type="tts", text="first"),
        Chunk(index=1, type="pause", duration=0.5),
        Chunk(index=2, type="tts", text="third"),
    ]
    client = FakeTTSClient()

    results = await run_pipeline(chunks, client, max_concurrent=3)

    assert results[0][0].text == "first"
    assert results[1][1] is None  # pause has no audio
    assert results[2][0].text == "third"


@pytest.mark.asyncio
async def test_gacha_processed_after_tts():
    """Gacha chunks are handled after all TTS chunks complete."""
    from aidente_voice.gacha import GACHA_SEEDS

    chunks = [
        Chunk(index=0, type="tts", text="intro"),
        Chunk(index=1, type="gacha", text="laugh", gacha_n=2),
    ]
    client = FakeTTSClient()

    with patch("aidente_voice.pipeline.orchestrator.select_gacha", return_value=0):
        results = await run_pipeline(chunks, client, max_concurrent=3)

    assert len(results) == 2
    # TTS chunk present
    assert results[0][1] is not None
    # Gacha chunk returns audio for selected seed
    assert results[1][1] == f"AUDIO_laugh_{GACHA_SEEDS[0]}".encode()


@pytest.mark.asyncio
async def test_pause_sfx_chunks_have_no_audio():
    """Pause and sfx chunks should produce None audio."""
    chunks = [
        Chunk(index=0, type="pause", duration=1.0),
        Chunk(index=1, type="sfx", sfx_name="bell"),
    ]
    client = FakeTTSClient()

    results = await run_pipeline(chunks, client, max_concurrent=3)

    assert len(results) == 2
    assert results[0][1] is None
    assert results[1][1] is None
    # No TTS calls made
    assert len(client.calls) == 0


@pytest.mark.asyncio
async def test_empty_chunks():
    """Empty chunk list returns empty results."""
    client = FakeTTSClient()
    results = await run_pipeline([], client, max_concurrent=3)
    assert results == []


@pytest.mark.asyncio
async def test_tts_audio_content_correct():
    """Each TTS chunk gets the right audio bytes."""
    chunks = [
        Chunk(index=0, type="tts", text="hello"),
        Chunk(index=1, type="tts", text="world"),
    ]
    client = FakeTTSClient()

    results = await run_pipeline(chunks, client, max_concurrent=3)

    # seed=0 is used for regular TTS
    assert results[0][1] == b"AUDIO_hello_0"
    assert results[1][1] == b"AUDIO_world_0"
