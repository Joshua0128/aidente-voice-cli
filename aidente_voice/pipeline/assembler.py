import io
import sys
from pathlib import Path
from pydub import AudioSegment
from aidente_voice.models import Chunk

SAMPLE_RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit


def _make_silence(duration_sec: float) -> AudioSegment:
    return AudioSegment.silent(
        duration=int(duration_sec * 1000),
        frame_rate=SAMPLE_RATE,
    ).set_channels(CHANNELS).set_sample_width(SAMPLE_WIDTH)


def _load_sfx(path: Path, fade_sec: float) -> AudioSegment:
    clip = AudioSegment.from_wav(str(path))
    if clip.frame_rate != SAMPLE_RATE or clip.channels != CHANNELS:
        print(
            f"[WARN] {path.name} is {clip.frame_rate}Hz "
            f"{'stereo' if clip.channels == 2 else str(clip.channels) + 'ch'}"
            " — auto-converting to 24kHz mono.",
            file=sys.stderr,
        )
        clip = clip.set_frame_rate(SAMPLE_RATE).set_channels(CHANNELS)
    clip = clip.set_sample_width(SAMPLE_WIDTH)
    if fade_sec > 0:
        fade_ms = int(fade_sec * 1000)
        clip = clip.fade_in(fade_ms).fade_out(fade_ms)
    return clip


def _bytes_to_segment(audio_bytes: bytes) -> AudioSegment:
    return AudioSegment.from_wav(io.BytesIO(audio_bytes))


def assemble(
    chunks_with_audio: list[tuple[Chunk, bytes | None]],
    sfx_dir: Path | None = None,
    output_path: Path | None = None,
) -> AudioSegment:
    """Concatenate chunks into a final AudioSegment. Optionally export to file."""
    if sfx_dir is None:
        sfx_dir = Path.home() / ".aidente" / "sfx"

    result = AudioSegment.empty()

    for chunk, audio_bytes in chunks_with_audio:
        if chunk.type in ("tts", "gacha"):
            result += _bytes_to_segment(audio_bytes)  # type: ignore[arg-type]

        elif chunk.type == "pause":
            result += _make_silence(chunk.duration or 0.0)

        elif chunk.type == "sfx":
            sfx_path = sfx_dir / f"{chunk.sfx_name}.wav"
            if not sfx_path.exists():
                raise FileNotFoundError(
                    f"SFX file not found: {sfx_path}. "
                    f"Add the file or remove the <sfx> tag."
                )
            result += _load_sfx(sfx_path, fade_sec=chunk.sfx_fade)

    if output_path:
        result.export(str(output_path), format="wav")

    return result
