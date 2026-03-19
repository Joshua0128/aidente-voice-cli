import pytest
from unittest.mock import patch, MagicMock
from aidente_voice.tts.modal_client import ModalTTSClient, CustomVoiceConfig, VoiceDesignConfig


@pytest.fixture
def client():
    return ModalTTSClient(
        endpoint_url="https://fake.modal.run/custom-voice",
        config=CustomVoiceConfig(speaker="Ryan", language="Auto"),
    )


@pytest.mark.asyncio
async def test_synthesize_returns_bytes(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"RIFF....fake_wav_bytes"

    with patch("requests.post", return_value=mock_response):
        result = await client.synthesize("Hello world")

    assert isinstance(result, bytes)
    assert result == b"RIFF....fake_wav_bytes"


@pytest.mark.asyncio
async def test_custom_voice_payload(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"audio"

    with patch("requests.post", return_value=mock_response) as mock_post:
        await client.synthesize("Test sentence")

    payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args.args[1]
    assert payload["text"] == "Test sentence"
    assert payload["speaker"] == "Ryan"
    assert payload["language"] == "Auto"
    assert "seed" not in payload


@pytest.mark.asyncio
async def test_per_call_instruct_merges_with_config():
    """<style=...> tag instruct is merged with config-level instruct."""
    client = ModalTTSClient(
        endpoint_url="https://fake.modal.run/custom-voice",
        config=CustomVoiceConfig(speaker="Serena", language="Japanese", instruct="calm and professional"),
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"audio"

    with patch("requests.post", return_value=mock_response) as mock_post:
        await client.synthesize("テスト", instruct="very angry, shouting")

    payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args.args[1]
    assert payload["instruct"] == "calm and professional; very angry, shouting"


@pytest.mark.asyncio
async def test_per_call_instruct_none_falls_back_to_config():
    """When no per-call instruct, config-level instruct is used."""
    client = ModalTTSClient(
        endpoint_url="https://fake.modal.run/custom-voice",
        config=CustomVoiceConfig(speaker="Ryan", language="Auto", instruct="slow and warm"),
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"audio"

    with patch("requests.post", return_value=mock_response) as mock_post:
        await client.synthesize("Hello")

    payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args.args[1]
    assert payload["instruct"] == "slow and warm"


@pytest.mark.asyncio
async def test_voice_design_payload():
    """VoiceDesignConfig sends instruct instead of speaker."""
    client = ModalTTSClient(
        endpoint_url="https://fake.modal.run/voice-design",
        config=VoiceDesignConfig(instruct="A warm female voice", language="Auto"),
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"audio"

    with patch("requests.post", return_value=mock_response) as mock_post:
        await client.synthesize("Hello")

    payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args.args[1]
    assert payload["instruct"] == "A warm female voice"
    assert payload["language"] == "Auto"
    assert "speaker" not in payload


@pytest.mark.asyncio
async def test_synthesize_retries_on_failure(client):
    fail_response = MagicMock()
    fail_response.status_code = 500
    fail_response.content = b""
    fail_response.text = "Internal Server Error"

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.content = b"audio"

    with patch("requests.post", side_effect=[fail_response, fail_response, ok_response]):
        with patch("asyncio.sleep"):
            result = await client.synthesize("Test")

    assert result == b"audio"


@pytest.mark.asyncio
async def test_synthesize_raises_after_max_retries(client):
    fail_response = MagicMock()
    fail_response.status_code = 500
    fail_response.content = b""
    fail_response.text = "error"

    with patch("requests.post", return_value=fail_response):
        with patch("asyncio.sleep"):
            with pytest.raises(RuntimeError, match="TTS API failed"):
                await client.synthesize("Test")
