"""Pipeline orchestrator with concurrent TTS synthesis."""

import asyncio
import tempfile
from pathlib import Path

from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from aidente_voice.gacha import GACHA_SEEDS, select_gacha
from aidente_voice.models import Chunk
from aidente_voice.pipeline.postprocess import apply_speed
from aidente_voice.tts.client import TTSClient


async def run_pipeline(
    chunks: list[Chunk],
    client: TTSClient,
    max_concurrent: int = 3,
) -> list[tuple[Chunk, bytes | None]]:
    """Run TTS pipeline with concurrent synthesis.

    TTS chunks are synthesized concurrently (bounded by max_concurrent semaphore).
    Gacha chunks are processed sequentially after all TTS synthesis completes.
    Output order matches input chunk order.

    Args:
        chunks: List of parsed chunks to process
        client: TTS client for synthesis
        max_concurrent: Max concurrent TTS API calls (default: 3)

    Returns:
        List of (chunk, audio_bytes | None) in original order
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    results: list[tuple[Chunk, bytes | None]] = [(chunk, None) for chunk in chunks]

    # Phase 1: Synthesize all TTS chunks concurrently
    tts_indices = [i for i, c in enumerate(chunks) if c.type == "tts"]
    gacha_indices = [i for i, c in enumerate(chunks) if c.type == "gacha"]

    if tts_indices:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        ) as progress:
            task = progress.add_task("Synthesizing...", total=len(tts_indices))

            async def _synthesize_tts(idx: int) -> None:
                chunk = chunks[idx]
                async with semaphore:
                    audio = await client.synthesize(chunk.text or "", seed=0)
                if chunk.speed != 1.0:
                    audio = apply_speed(audio, chunk.speed)
                results[idx] = (chunk, audio)
                progress.advance(task)

            await asyncio.gather(*[_synthesize_tts(i) for i in tts_indices])

    # Phase 2: Process gacha chunks sequentially (requires user interaction)
    for idx in gacha_indices:
        chunk = chunks[idx]
        if chunk.gacha_n < 1:
            raise ValueError(f"gacha_n must be >= 1, got {chunk.gacha_n}")
        audio = await _run_gacha(chunk, client, semaphore)
        results[idx] = (chunk, audio)

    return results


async def _run_gacha(chunk: Chunk, client: TTSClient, semaphore: asyncio.Semaphore) -> bytes:
    """Synthesize N gacha variants concurrently, then let user pick one."""
    seeds = GACHA_SEEDS[:chunk.gacha_n]

    async def _synthesize_variant(seed: int) -> bytes:
        async with semaphore:
            return await client.synthesize(chunk.text or "", seed=seed)

    variant_audios = await asyncio.gather(*[_synthesize_variant(s) for s in seeds])

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        paths = []
        for i, audio_bytes in enumerate(variant_audios):
            path = tmp_path / f"gacha_{i}.wav"
            path.write_bytes(audio_bytes)
            paths.append(path)

        selected_idx = select_gacha(paths, chunk.text or "", chunk.index)
        return paths[selected_idx].read_bytes()
