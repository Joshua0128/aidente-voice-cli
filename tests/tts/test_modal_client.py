import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from aidente_voice.tts.modal_client import ModalTTSClient, CustomVoiceConfig, VoiceDesignConfig


@pytest.fixture
def client():
    return ModalTTSClient(
        endpoint_url="https://fake.modal.run/custom-voice",
        config=CustomVoiceConfig(speaker="Ryan", language="Auto"),
        log_path=None,  # disable logging in most tests
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
    client = ModalTTSClient(
        endpoint_url="https://fake.modal.run/custom-voice",
        config=CustomVoiceConfig(speaker="Serena", language="Japanese", instruct="calm and professional"),
        log_path=None,
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
    client = ModalTTSClient(
        endpoint_url="https://fake.modal.run/custom-voice",
        config=CustomVoiceConfig(speaker="Ryan", language="Auto", instruct="slow and warm"),
        log_path=None,
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
    client = ModalTTSClient(
        endpoint_url="https://fake.modal.run/voice-design",
        config=VoiceDesignConfig(instruct="A warm female voice", language="Auto"),
        log_path=None,
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
async def test_successful_call_written_to_log(tmp_path):
    log_file = tmp_path / "api_log.jsonl"
    client = ModalTTSClient(
        endpoint_url="https://fake.modal.run/custom-voice",
        config=CustomVoiceConfig(speaker="Ryan", language="Japanese"),
        log_path=log_file,
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"x" * 1234

    with patch("requests.post", return_value=mock_response):
        await client.synthesize("こんにちは")

    assert log_file.exists()
    entry = json.loads(log_file.read_text())
    assert entry["status"] == 200
    assert entry["request"]["text"] == "こんにちは"
    assert entry["request"]["speaker"] == "Ryan"
    assert entry["bytes"] == 1234
    assert "timestamp" in entry
    assert "duration_ms" in entry


@pytest.mark.asyncio
async def test_failed_call_written_to_log(tmp_path):
    log_file = tmp_path / "api_log.jsonl"
    client = ModalTTSClient(
        endpoint_url="https://fake.modal.run/custom-voice",
        config=CustomVoiceConfig(),
        log_path=log_file,
    )
    fail = MagicMock()
    fail.status_code = 500
    fail.text = "Internal Server Error"

    with patch("requests.post", return_value=fail), patch("asyncio.sleep"):
        with pytest.raises(RuntimeError):
            await client.synthesize("失敗テスト")

    entry = json.loads(log_file.read_text())
    assert entry["status"] == 500
    assert "error" in entry


@pytest.mark.asyncio
async def test_log_path_none_disables_logging(tmp_path):
    """No file created when log_path=None."""
    client = ModalTTSClient(
        endpoint_url="https://fake.modal.run/custom-voice",
        config=CustomVoiceConfig(),
        log_path=None,
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"audio"

    with patch("requests.post", return_value=mock_response):
        await client.synthesize("テスト")

    # No log file should exist anywhere in tmp_path
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_synthesize_retries_on_failure(client):
    fail = MagicMock()
    fail.status_code = 500
    fail.content = b""
    fail.text = "error"

    ok = MagicMock()
    ok.status_code = 200
    ok.content = b"audio"

    with patch("requests.post", side_effect=[fail, fail, ok]):
        with patch("asyncio.sleep"):
            result = await client.synthesize("Test")

    assert result == b"audio"


@pytest.mark.asyncio
async def test_synthesize_raises_after_max_retries(client):
    fail = MagicMock()
    fail.status_code = 500
    fail.content = b""
    fail.text = "error"

    with patch("requests.post", return_value=fail):
        with patch("asyncio.sleep"):
            with pytest.raises(RuntimeError, match="TTS API failed"):
                await client.synthesize("Test")
