import io
import pytest
from pathlib import Path
from pydub import AudioSegment
from pydub.generators import Sine
from aidente_voice.models import Chunk
from aidente_voice.pipeline.assembler import assemble, _make_silence, _load_sfx


SAMPLE_RATE = 24000


def _make_wav_bytes(duration_ms: int = 500) -> bytes:
    """Generate real WAV bytes for testing."""
    seg = Sine(440).to_audio_segment(duration=duration_ms).set_frame_rate(SAMPLE_RATE).set_channels(1).set_sample_width(2)
    buf = io.BytesIO()
    seg.export(buf, format="wav")
    return buf.getvalue()


def test_make_silence_correct_duration():
    silence = _make_silence(1.0)
    assert len(silence) == pytest.approx(1000, abs=5)  # 1000ms
    assert silence.frame_rate == SAMPLE_RATE
    assert silence.channels == 1


def test_assemble_single_tts():
    wav = _make_wav_bytes(500)
    chunk = Chunk(index=0, type="tts", text="hello")
    result = assemble([(chunk, wav)])
    assert len(result) > 400  # at least ~500ms


def test_assemble_pause_inserts_silence():
    wav = _make_wav_bytes(100)
    tts_chunk = Chunk(index=0, type="tts", text="hello")
    pause_chunk = Chunk(index=1, type="pause", duration=1.0)
    result = assemble([(tts_chunk, wav), (pause_chunk, None)])
    # result should be longer than input wav by ~1000ms
    assert len(result) >= 1000


def test_assemble_sfx_with_fade(tmp_path):
    sfx_path = tmp_path / "laugh.wav"
    sfx_bytes = _make_wav_bytes(300)
    sfx_path.write_bytes(sfx_bytes)

    wav = _make_wav_bytes(200)
    tts_chunk = Chunk(index=0, type="tts", text="hello")
    sfx_chunk = Chunk(index=1, type="sfx", sfx_name="laugh", sfx_fade=0.05)
    result = assemble([(tts_chunk, wav), (sfx_chunk, None)], sfx_dir=tmp_path)
    assert len(result) > 400


def test_assemble_sfx_missing_raises(tmp_path):
    sfx_chunk = Chunk(index=0, type="sfx", sfx_name="laugh", sfx_fade=0.05)
    with pytest.raises(FileNotFoundError, match="SFX file not found"):
        assemble([(sfx_chunk, None)], sfx_dir=tmp_path)


def test_load_sfx_auto_resamples(tmp_path):
    """SFX at 44100Hz stereo should be auto-converted to 24kHz mono."""
    sfx_44k = AudioSegment.silent(duration=200, frame_rate=44100).set_channels(2)
    sfx_path = tmp_path / "laugh.wav"
    sfx_44k.export(sfx_path, format="wav")

    result = _load_sfx(sfx_path, fade_sec=0.0)
    assert result.frame_rate == SAMPLE_RATE
    assert result.channels == 1
