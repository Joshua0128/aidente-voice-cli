from aidente_voice.models import Chunk
from aidente_voice.tts.client import TTSClient
from aidente_voice.pipeline.postprocess import apply_speed


async def run_pipeline(
    chunks: list[Chunk],
    client: TTSClient,
    profile_clients: dict[str, TTSClient] | None = None,
) -> list[tuple[Chunk, bytes | None]]:
    """Sequential TTS synthesis.

    Returns list of (chunk, audio_bytes) pairs.
    audio_bytes is None for pause and sfx chunks.

    profile_clients — optional mapping of profile name → TTSClient.
    When a chunk has voice_profile set and that profile is in this dict,
    that client is used instead of the default client.
    """
    results: list[tuple[Chunk, bytes | None]] = []

    for chunk in chunks:
        if chunk.type in ("tts", "gacha"):
            active_client = client
            if profile_clients and chunk.voice_profile:
                active_client = profile_clients.get(chunk.voice_profile, client)
            audio = await active_client.synthesize(chunk.text or "", seed=0, instruct=chunk.instruct)
            if chunk.speed != 1.0:
                audio = apply_speed(audio, chunk.speed)
            results.append((chunk, audio))
        else:
            results.append((chunk, None))

    return results
