from aidente_voice.models import Chunk
from aidente_voice.tts.client import TTSClient
from aidente_voice.pipeline.postprocess import apply_speed


async def run_pipeline(
    chunks: list[Chunk],
    client: TTSClient,
) -> list[tuple[Chunk, bytes | None]]:
    """
    Phase 1: sequential TTS synthesis.
    Returns list of (chunk, audio_bytes) pairs.
    audio_bytes is None for pause and sfx chunks.
    """
    results: list[tuple[Chunk, bytes | None]] = []

    for chunk in chunks:
        if chunk.type in ("tts", "gacha"):
            audio = await client.synthesize(chunk.text or "", seed=0, instruct=chunk.instruct)
            if chunk.speed != 1.0:
                audio = apply_speed(audio, chunk.speed)
            results.append((chunk, audio))
        else:
            results.append((chunk, None))

    return results
