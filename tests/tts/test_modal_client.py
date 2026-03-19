import pytest
from unittest.mock import patch, MagicMock
from aidente_voice.tts.modal_client import ModalTTSClient, CustomVoiceConfig, VoiceDesignConfig


@pytest.fixture
def client():
    return ModalTTSClient(
        endpoint_url="https://fake.modal.run/custom-voice",
        config=CustomVoiceConfig(speaker="Ryan", language="Japanese"),
    )


@pytest.mark.asyncio
async def test_synthesize_returns_bytes(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"RIFF....fake_wav_bytes"

    with patch("requests.post", return_value=mock_response):
        result = await client.synthesize("Hello world", seed=42)

    assert isinstance(result, bytes)
    assert result == b"RIFF....fake_wav_bytes"


@pytest.mark.asyncio
async def test_synthesize_sends_correct_payload(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"audio"

    with patch("requests.post", return_value=mock_response) as mock_post:
        await client.synthesize("Test sentence", seed=1337)

    call_kwargs = mock_post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
    assert payload["text"] == "Test sentence"
    assert payload["speaker"] == "Ryan"
    assert payload["language"] == "Japanese"
    assert "seed" not in payload


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
async def test_custom_voice_with_instruct():
    """CustomVoiceConfig with instruct includes it in payload."""
    client = ModalTTSClient(
        endpoint_url="https://fake.modal.run/custom-voice",
        config=CustomVoiceConfig(speaker="Serena", language="Japanese", instruct="Speak slowly"),
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"audio"

    with patch("requests.post", return_value=mock_response) as mock_post:
        await client.synthesize("テスト")

    payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args.args[1]
    assert payload["speaker"] == "Serena"
    assert payload["instruct"] == "Speak slowly"


@pytest.mark.asyncio
async def test_synthesize_retries_on_failure(client):
    fail_response = MagicMock()
    fail_response.status_code = 500
    fail_response.content = b""

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.content = b"audio"

    with patch("requests.post", side_effect=[fail_response, fail_response, ok_response]):
        with patch("asyncio.sleep"):  # skip actual delays
            result = await client.synthesize("Test", seed=0)

    assert result == b"audio"


@pytest.mark.asyncio
async def test_synthesize_raises_after_max_retries(client):
    fail_response = MagicMock()
    fail_response.status_code = 500
    fail_response.content = b""

    with patch("requests.post", return_value=fail_response):
        with patch("asyncio.sleep"):
            with pytest.raises(RuntimeError, match="TTS API failed"):
                await client.synthesize("Test", seed=0)
