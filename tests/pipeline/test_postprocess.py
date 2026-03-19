import pytest
from unittest.mock import patch, MagicMock, mock_open
from aidente_voice.pipeline.postprocess import build_atempo_chain, apply_speed


def test_chain_single_value_in_range():
    assert build_atempo_chain(0.85) == pytest.approx([0.85])

def test_chain_single_value_boundary():
    assert build_atempo_chain(0.5) == pytest.approx([0.5])
    assert build_atempo_chain(2.0) == pytest.approx([2.0])

def test_chain_below_range():
    chain = build_atempo_chain(0.3)
    product = 1.0
    for f in chain:
        assert 0.5 <= f <= 2.0
        product *= f
    assert product == pytest.approx(0.3, rel=1e-4)

def test_chain_above_range():
    chain = build_atempo_chain(3.0)
    product = 1.0
    for f in chain:
        assert 0.5 <= f <= 2.0
        product *= f
    assert product == pytest.approx(3.0, rel=1e-4)

def test_chain_speed_one_is_noop():
    assert build_atempo_chain(1.0) == pytest.approx([1.0])

def test_apply_speed_calls_ffmpeg_filter(tmp_path):
    """apply_speed calls ffmpeg.filter once per atempo factor."""
    from unittest.mock import call
    fake_bytes = b"RIFF" + b"\x00" * 100

    mock_stream = MagicMock()

    with patch("ffmpeg.input") as mock_input, \
         patch("ffmpeg.filter", return_value=mock_stream) as mock_filter, \
         patch("ffmpeg.output") as mock_output, \
         patch("ffmpeg.run"), \
         patch("builtins.open", mock_open(read_data=b"result_audio")), \
         patch("os.unlink"), \
         patch("tempfile.NamedTemporaryFile") as mock_tmp:

        mock_tmp.return_value.__enter__ = lambda s: s
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)
        mock_tmp.return_value.name = "/tmp/fake.wav"
        mock_input.return_value.audio = mock_stream

        apply_speed(fake_bytes, speed=0.85)

    # Should call ffmpeg.filter once for speed in [0.5, 2.0]
    mock_filter.assert_called_once_with(mock_stream, "atempo", pytest.approx(0.85))


def test_apply_speed_noop_on_speed_one():
    """speed=1.0 returns input bytes unchanged without calling ffmpeg."""
    fake_bytes = b"audio_data"
    result = apply_speed(fake_bytes, speed=1.0)
    assert result == fake_bytes
