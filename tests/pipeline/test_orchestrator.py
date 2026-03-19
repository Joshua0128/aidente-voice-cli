import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from aidente_voice.models import Chunk
from aidente_voice.pipeline.orchestrator import run_pipeline


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.synthesize.return_value = b"RIFF" + b"\x00" * 44  # fake WAV
    return client


@pytest.mark.asyncio
async def test_tts_chunks_are_synthesized(mock_client):
    chunks = [
        Chunk(index=0, type="tts", text="Hello world。"),
    ]
    result = await run_pipeline(chunks, client=mock_client)
    mock_client.synthesize.assert_called_once_with("Hello world。", seed=0, instruct=None)
    assert len(result) == 1
    assert result[0][0] == chunks[0]


@pytest.mark.asyncio
async def test_pause_chunks_pass_through(mock_client):
    chunks = [
        Chunk(index=0, type="tts", text="Hello。"),
        Chunk(index=1, type="pause", duration=1.0),
    ]
    result = await run_pipeline(chunks, client=mock_client)
    assert result[1][1] is None  # no audio bytes for pause


@pytest.mark.asyncio
async def test_sfx_chunks_pass_through(mock_client):
    chunks = [
        Chunk(index=0, type="sfx", sfx_name="laugh"),
    ]
    result = await run_pipeline(chunks, client=mock_client)
    assert result[0][1] is None


@pytest.mark.asyncio
async def test_speed_applied_after_synthesis(mock_client):
    chunks = [Chunk(index=0, type="tts", text="Slow。", speed=0.85)]
    with patch("aidente_voice.pipeline.orchestrator.apply_speed", return_value=b"slow_audio") as mock_speed:
        result = await run_pipeline(chunks, client=mock_client)
    mock_speed.assert_called_once()
    assert result[0][1] == b"slow_audio"


@pytest.mark.asyncio
async def test_speed_one_skips_postprocess(mock_client):
    chunks = [Chunk(index=0, type="tts", text="Normal。", speed=1.0)]
    with patch("aidente_voice.pipeline.orchestrator.apply_speed") as mock_speed:
        await run_pipeline(chunks, client=mock_client)
    mock_speed.assert_not_called()


@pytest.mark.asyncio
async def test_profile_client_used_when_chunk_has_voice_profile(mock_client):
    profile_client = AsyncMock()
    profile_client.synthesize.return_value = b"profile_audio"

    chunks = [Chunk(index=0, type="tts", text="旁白說話。", voice_profile="narrator")]
    result = await run_pipeline(
        chunks, client=mock_client, profile_clients={"narrator": profile_client}
    )

    profile_client.synthesize.assert_called_once_with("旁白說話。", seed=0, instruct=None)
    mock_client.synthesize.assert_not_called()
    assert result[0][1] == b"profile_audio"


@pytest.mark.asyncio
async def test_default_client_used_when_profile_not_in_profile_clients(mock_client):
    profile_client = AsyncMock()

    chunks = [Chunk(index=0, type="tts", text="Hello。", voice_profile="unknown")]
    result = await run_pipeline(
        chunks, client=mock_client, profile_clients={"narrator": profile_client}
    )

    mock_client.synthesize.assert_called_once()
    profile_client.synthesize.assert_not_called()


@pytest.mark.asyncio
async def test_default_client_used_when_no_voice_profile(mock_client):
    chunks = [Chunk(index=0, type="tts", text="Hello。")]
    profile_client = AsyncMock()
    await run_pipeline(chunks, client=mock_client, profile_clients={"narrator": profile_client})
    mock_client.synthesize.assert_called_once()
    profile_client.synthesize.assert_not_called()
