"""Tests for gacha integration in the orchestrator."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from aidente_voice.gacha import GACHA_SEEDS
from aidente_voice.models import Chunk
from aidente_voice.pipeline.orchestrator import run_pipeline


class FakeTTSClient:
    def __init__(self, audio_by_seed: dict[int, bytes] | None = None):
        self.calls = []
        self._audio = audio_by_seed or {}

    async def synthesize(self, text: str, seed: int = 0) -> bytes:
        self.calls.append((text, seed))
        return self._audio.get(seed, b"FAKE_AUDIO_" + str(seed).encode())


@pytest.mark.asyncio
async def test_gacha_synthesizes_n_variants():
    """Gacha chunk should call synthesize for each seed in GACHA_SEEDS[:n]."""
    n = 3
    chunk = Chunk(index=0, type="gacha", text="テスト", gacha_n=n)
    client = FakeTTSClient()

    with patch("aidente_voice.pipeline.orchestrator.select_gacha", return_value=0):
        results = await run_pipeline([chunk], client)

    assert len(results) == 1
    # Should have called synthesize n times with the first n seeds
    assert len(client.calls) == n
    seeds_used = [call[1] for call in client.calls]
    assert seeds_used == GACHA_SEEDS[:n]


@pytest.mark.asyncio
async def test_gacha_returns_selected_audio():
    """Orchestrator should return the audio for the user-selected variant."""
    n = 2
    seed_audio = {
        GACHA_SEEDS[0]: b"AUDIO_VARIANT_0",
        GACHA_SEEDS[1]: b"AUDIO_VARIANT_1",
    }
    chunk = Chunk(index=0, type="gacha", text="テスト", gacha_n=n)
    client = FakeTTSClient(audio_by_seed=seed_audio)

    # User selects variant 1 (index 1)
    with patch("aidente_voice.pipeline.orchestrator.select_gacha", return_value=1):
        results = await run_pipeline([chunk], client)

    _, audio = results[0]
    assert audio == b"AUDIO_VARIANT_1"
