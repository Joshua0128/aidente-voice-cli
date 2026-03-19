from unittest.mock import patch
from pathlib import Path
from aidente_voice.audio_player import play


def test_play_calls_afplay(tmp_path):
    fake_wav = tmp_path / "test.wav"
    fake_wav.write_bytes(b"")

    with patch("subprocess.run") as mock_run:
        play(fake_wav)

    mock_run.assert_called_once_with(["afplay", str(fake_wav)], check=True)


def test_play_accepts_string_path(tmp_path):
    fake_wav = tmp_path / "test.wav"
    fake_wav.write_bytes(b"")

    with patch("subprocess.run") as mock_run:
        play(str(fake_wav))

    mock_run.assert_called_once_with(["afplay", str(fake_wav)], check=True)
