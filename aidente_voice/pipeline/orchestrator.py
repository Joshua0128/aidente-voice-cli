"""Sequential TTS pipeline orchestrator."""

import asyncio
import tempfile
from pathlib import Path

from aidente_voice.gacha import GACHA_SEEDS, select_gacha
from aidente_voice.models import Chunk
from aidente_voice.pipeline.postprocess import apply_speed
from aidente_voice.tts.client import TTSClient


async def run_pipeline(
    chunks: list[Chunk],
    client: TTSClient,
) -> list[tuple[Chunk, bytes | None]]:
    """Run TTS pipeline sequentially, returning (chunk, audio_bytes) pairs."""
    results = []
    for chunk in chunks:
        if chunk.type == "tts":
            audio = await client.synthesize(chunk.text or "", seed=0)
            if chunk.speed != 1.0:
                audio = apply_speed(audio, chunk.speed)
            results.append((chunk, audio))
        elif chunk.type == "gacha":
            audio = await _run_gacha(chunk, client)
            results.append((chunk, audio))
        else:
            results.append((chunk, None))
    return results


async def _run_gacha(chunk: Chunk, client: TTSClient) -> bytes:
    """Synthesize N gacha variants, let user pick one interactively."""
    seeds = GACHA_SEEDS[:chunk.gacha_n]

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        paths = []

        for i, seed in enumerate(seeds):
            audio_bytes = await client.synthesize(chunk.text or "", seed=seed)
            path = tmp_path / f"gacha_{i}.wav"
            path.write_bytes(audio_bytes)
            paths.append(path)

        selected_idx = select_gacha(paths, chunk.text or "", chunk.index)
        return paths[selected_idx].read_bytes()
