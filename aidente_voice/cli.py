import asyncio
import os
from pathlib import Path

import typer
from rich.console import Console

from aidente_voice.models import Chunk
from aidente_voice.parser import parse, ParseError
from aidente_voice.tts.modal_client import ModalTTSClient, CustomVoiceConfig, VoiceDesignConfig
from aidente_voice.pipeline.orchestrator import run_pipeline
from aidente_voice.pipeline.assembler import assemble

app = typer.Typer(help="aidente-voice: TTS production pipeline with engineering control")
console = Console()


@app.callback()
def main() -> None:
    """aidente-voice: TTS production pipeline with engineering control."""


def _dry_run_report(chunks: list[Chunk]) -> None:
    console.print(f"[bold cyan][DRY RUN][/] Parsed {len(chunks)} chunks:")
    for c in chunks:
        if c.type == "tts":
            speed_str = f" speed={c.speed}" if c.speed != 1.0 else ""
            style_str = f" style={c.instruct!r}" if c.instruct else ""
            console.print(f"  [{c.index}] tts    \"{c.text}\"{speed_str}{style_str}")
        elif c.type == "pause":
            console.print(f"  [{c.index}] pause  {c.duration}s")
        elif c.type == "gacha":
            style_str = f" style={c.instruct!r}" if c.instruct else ""
            console.print(f"  [{c.index}] gacha  \"{c.text}\" n={c.gacha_n}{style_str}")
        elif c.type == "sfx":
            console.print(f"  [{c.index}] sfx    {c.sfx_name} fade={c.sfx_fade}")
    console.print("No API calls made.")


@app.command()
def generate(
    input: Path = typer.Option(..., "-i", "--input", help="Input script path"),
    output: Path = typer.Option(Path("output.wav"), "-o", "--output"),
    sfx_dir: Path = typer.Option(Path.home() / ".aidente" / "sfx", "--sfx-dir"),
    max_concurrent: int = typer.Option(10, "--max-concurrent"),
    keep_chunks: bool = typer.Option(False, "--keep-chunks"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    # Voice options
    speaker: str = typer.Option(
        "Ryan",
        "--speaker",
        help="Speaker: Aiden, Dylan, Eric, Ono_anna, Ryan, Serena, Sohee, Uncle_fu, Vivian",
    ),
    language: str = typer.Option(
        "Auto",
        "--language",
        help="Language: Auto, Chinese, English, Japanese, Korean, French, German, Spanish, Portuguese, Russian",
    ),
    instruct: str | None = typer.Option(
        None,
        "--instruct",
        help='Global speaking style, e.g. "Speak slowly with a warm tone". Overridden per-sentence by <style=...> tags.',
    ),
    voice_design: str | None = typer.Option(
        None,
        "--voice-design",
        help='Use /voice-design endpoint. Describe the voice: "A warm husky male narrator"',
    ),
) -> None:
    """Generate TTS audio from a script with control tags.

    Acoustic attributes can be controlled globally via --instruct,
    or per-sentence in the script using <style=...> tags.

    Examples:
        --instruct "Speak slowly and warmly"
        --speaker Ono_anna --language Japanese
        --voice-design "A young enthusiastic male, slightly sarcastic but friendly"

    In-script style tag:
        普通に話す。
        怒りながら叫ぶ。<style=very angry, shouting>
        そっと囁く。<style=whisper, intimate>
    """
    if not input.exists():
        console.print(f"[red][ERROR][/] Input file not found: {input}")
        raise typer.Exit(code=1)

    text = input.read_text(encoding="utf-8")

    try:
        chunks = parse(text)
    except ParseError as e:
        console.print(f"[red][ERROR][/] {e}")
        raise typer.Exit(code=1)

    if dry_run:
        _dry_run_report(chunks)
        return

    modal_url = os.environ.get("MODAL_TTS_URL", "")
    if not modal_url:
        console.print("[red][ERROR][/] MODAL_TTS_URL environment variable not set.")
        raise typer.Exit(code=1)

    if voice_design is not None:
        # Strip endpoint suffix if user set URL to /custom-voice, swap to /voice-design
        base = modal_url.rstrip("/")
        for suffix in ("/custom-voice", "/voice-design", "/voice-clone"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        tts_url = f"{base}/voice-design"
        config: CustomVoiceConfig | VoiceDesignConfig = VoiceDesignConfig(
            instruct=voice_design, language=language
        )
    else:
        tts_url = modal_url
        config = CustomVoiceConfig(speaker=speaker, language=language, instruct=instruct)

    client = ModalTTSClient(endpoint_url=tts_url, config=config)

    try:
        results = asyncio.run(run_pipeline(chunks, client=client))
    except RuntimeError as e:
        console.print(f"[red][ERROR][/] {e}")
        raise typer.Exit(code=1)

    chunks_dir = Path("chunks") if keep_chunks else None
    if chunks_dir:
        chunks_dir.mkdir(exist_ok=True)
        for chunk, audio in results:
            if audio:
                (chunks_dir / f"chunk_{chunk.index:03d}_{chunk.type}.wav").write_bytes(audio)

    try:
        assemble(results, sfx_dir=sfx_dir, output_path=output)
    except FileNotFoundError as e:
        console.print(f"[red][ERROR][/] {e}")
        raise typer.Exit(code=1)

    console.print(f"[green][SUCCESS][/] Saved to {output}")
