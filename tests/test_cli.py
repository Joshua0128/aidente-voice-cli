import os
from pathlib import Path
from typer.testing import CliRunner
from unittest.mock import patch, AsyncMock
from aidente_voice.cli import app

runner = CliRunner()


def test_dry_run_prints_chunks(tmp_path):
    script = tmp_path / "script.txt"
    script.write_text("Hello world。 <pause=1.0>\n接下來。 <speed=0.85>")

    result = runner.invoke(app, ["generate", "-i", str(script), "--dry-run"])

    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    assert "tts" in result.output
    assert "pause" in result.output
    assert "No API calls made" in result.output


def test_missing_input_file_exits_with_error():
    result = runner.invoke(app, ["generate", "-i", "nonexistent.txt"])
    assert result.exit_code != 0


def test_generate_calls_pipeline(tmp_path):
    script = tmp_path / "script.txt"
    script.write_text("Hello。")
    output = tmp_path / "out.wav"

    fake_audio = b"RIFF" + b"\x00" * 100

    with patch("aidente_voice.cli.ModalTTSClient") as MockClient, \
         patch("aidente_voice.cli.run_pipeline", new_callable=AsyncMock) as mock_run, \
         patch("aidente_voice.cli.assemble") as mock_assemble:

        from aidente_voice.models import Chunk
        mock_chunk = Chunk(index=0, type="tts", text="Hello。")
        mock_run.return_value = [(mock_chunk, fake_audio)]
        mock_assemble.return_value = None

        result = runner.invoke(app, [
            "generate", "-i", str(script), "-o", str(output),
        ], env={"MODAL_TTS_URL": "https://fake.modal.run/tts"})

    assert result.exit_code == 0
