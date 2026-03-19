import tempfile
import os
import ffmpeg

AUDIO_SAMPLE_RATE = 24000


def build_atempo_chain(speed: float) -> list[float]:
    """Factorize speed into atempo filter values, each in [0.5, 2.0]."""
    if speed == 1.0:
        return [1.0]
    factors: list[float] = []
    remaining = speed
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    factors.append(remaining)
    return factors


def apply_speed(audio_bytes: bytes, speed: float) -> bytes:
    """Apply time-stretch to audio bytes using ffmpeg atempo. Returns WAV bytes."""
    if speed == 1.0:
        return audio_bytes

    factors = build_atempo_chain(speed)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as in_f:
        in_f.write(audio_bytes)
        in_path = in_f.name

    out_path = in_path.replace(".wav", "_out.wav")
    try:
        stream = ffmpeg.input(in_path).audio
        for factor in factors:
            stream = ffmpeg.filter(stream, "atempo", factor)
        ffmpeg.output(stream, out_path).run(quiet=True, overwrite_output=True)
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(in_path)
        if os.path.exists(out_path):
            os.unlink(out_path)
