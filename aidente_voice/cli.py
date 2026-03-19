import asyncio
import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from aidente_voice.config import load_config, VoiceProfile
from aidente_voice.models import Chunk
from aidente_voice.parser import parse, ParseError
from aidente_voice.tts.modal_client import ModalTTSClient, CustomVoiceConfig, VoiceDesignConfig, _DEFAULT_LOG_PATH
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
            voice_str = f" voice={c.voice_profile!r}" if c.voice_profile else ""
            console.print(f"  [{c.index}] tts    \"{c.text}\"{speed_str}{style_str}{voice_str}")
        elif c.type == "pause":
            console.print(f"  [{c.index}] pause  {c.duration}s")
        elif c.type == "gacha":
            style_str = f" style={c.instruct!r}" if c.instruct else ""
            voice_str = f" voice={c.voice_profile!r}" if c.voice_profile else ""
            console.print(f"  [{c.index}] gacha  \"{c.text}\" n={c.gacha_n}{style_str}{voice_str}")
        elif c.type == "sfx":
            console.print(f"  [{c.index}] sfx    {c.sfx_name} fade={c.sfx_fade}")
    console.print("No API calls made.")


def _client_from_profile(profile: VoiceProfile, base_url: str, log_path: Path | None) -> ModalTTSClient:
    """Build a ModalTTSClient from a VoiceProfile."""
    config = CustomVoiceConfig(
        speaker=profile.speaker,
        language=profile.language,
        instruct=profile.instruct or None,
    )
    return ModalTTSClient(endpoint_url=base_url, config=config, log_path=log_path)


@app.command()
def generate(
    input: Path = typer.Option(..., "-i", "--input", help="Input script path"),
    output: Path = typer.Option(Path("output.wav"), "-o", "--output"),
    sfx_dir: Optional[Path] = typer.Option(None, "--sfx-dir"),
    max_concurrent: Optional[int] = typer.Option(None, "--max-concurrent"),
    keep_chunks: bool = typer.Option(False, "--keep-chunks"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    # Profile selection
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help="Voice profile name from ~/.aidente/config.toml",
    ),
    # Voice options (override profile / defaults)
    speaker: Optional[str] = typer.Option(
        None,
        "--speaker",
        help="Speaker: Aiden, Dylan, Eric, Ono_anna, Ryan, Serena, Sohee, Uncle_fu, Vivian",
    ),
    language: Optional[str] = typer.Option(
        None,
        "--language",
        help="Language: Auto, Chinese, English, Japanese, Korean, French, German, Spanish, Portuguese, Russian",
    ),
    instruct: Optional[str] = typer.Option(
        None,
        "--instruct",
        help="Global speaking style. Merged with per-sentence <style=...> tags.",
    ),
    voice_design: Optional[str] = typer.Option(
        None,
        "--voice-design",
        help='Use /voice-design endpoint. Describe the voice: "A warm husky male narrator"',
    ),
    # Logging options
    api_log: Optional[Path] = typer.Option(
        None,
        "--api-log",
        help="Path to JSONL API log file. Each call appended as one JSON line.",
    ),
    no_api_log: bool = typer.Option(
        False,
        "--no-api-log",
        help="Disable API call logging.",
    ),
) -> None:
    """Generate TTS audio from a script with control tags.

    Config file ~/.aidente/config.toml is loaded automatically.
    CLI flags override config values.

    In-script tags:
        普通に話す。
        怒りながら叫ぶ。<style=very angry, shouting>
        旁白說話。<voice=narrator>
    """
    # --- Load config ---
    cfg = load_config()

    # --- Resolve settings: config < profile < CLI args ---
    resolved_sfx_dir = sfx_dir or cfg.sfx_dir
    resolved_max_concurrent = max_concurrent or cfg.max_concurrent

    active_profile: VoiceProfile | None = None
    profile_name = profile or cfg.default_profile
    if profile_name:
        if profile_name not in cfg.profiles:
            console.print(f"[red][ERROR][/] Profile {profile_name!r} not found in config.toml")
            raise typer.Exit(code=1)
        active_profile = cfg.profiles[profile_name]

    # Effective values: profile < CLI arg
    eff_speaker = speaker or (active_profile.speaker if active_profile else "Ryan")
    eff_language = language or (active_profile.language if active_profile else "Auto")
    eff_instruct = instruct or (active_profile.instruct or None if active_profile else None)

    # Log path: CLI flag > config > default
    if no_api_log:
        log_path = None
    elif api_log is not None:
        log_path = api_log
    elif cfg.api_log is not None:
        log_path = cfg.api_log
    else:
        log_path = _DEFAULT_LOG_PATH

    # --- Validate input file ---
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

    # --- Resolve Modal URL ---
    modal_url = os.environ.get("MODAL_TTS_URL", "") or cfg.modal_tts_url
    if not modal_url:
        console.print("[red][ERROR][/] MODAL_TTS_URL not set. Set env var or modal_tts_url in config.toml.")
        raise typer.Exit(code=1)

    # --- Build main client ---
    if voice_design is not None:
        base = modal_url.rstrip("/")
        for suffix in ("/custom-voice", "/voice-design", "/voice-clone"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        tts_url = f"{base}/voice-design"
        main_config: CustomVoiceConfig | VoiceDesignConfig = VoiceDesignConfig(
            instruct=voice_design, language=eff_language
        )
    else:
        tts_url = modal_url
        main_config = CustomVoiceConfig(speaker=eff_speaker, language=eff_language, instruct=eff_instruct)

    if log_path:
        console.print(f"[dim]API log → {log_path}[/]")

    client = ModalTTSClient(endpoint_url=tts_url, config=main_config, log_path=log_path)

    # --- Build profile clients for <voice=...> tag support ---
    # Derive base URL (without endpoint suffix) for profile clients
    base_url = tts_url.rstrip("/")
    for suffix in ("/custom-voice", "/voice-design", "/voice-clone"):
        if base_url.endswith(suffix):
            base_url = base_url[: -len(suffix)]
            break
    custom_voice_url = f"{base_url}/custom-voice"

    profile_clients = {
        name: _client_from_profile(p, custom_voice_url, log_path)
        for name, p in cfg.profiles.items()
    } if cfg.profiles else None

    # --- Run pipeline ---
    try:
        results = asyncio.run(run_pipeline(chunks, client=client, profile_clients=profile_clients))
    except RuntimeError as e:
        console.print(f"[red][ERROR][/] {e}")
        raise typer.Exit(code=1)

    if keep_chunks:
        chunks_dir = Path("chunks")
        chunks_dir.mkdir(exist_ok=True)
        for chunk, audio in results:
            if audio:
                (chunks_dir / f"chunk_{chunk.index:03d}_{chunk.type}.wav").write_bytes(audio)

    try:
        assemble(results, sfx_dir=resolved_sfx_dir, output_path=output)
    except FileNotFoundError as e:
        console.print(f"[red][ERROR][/] {e}")
        raise typer.Exit(code=1)

    console.print(f"[green][SUCCESS][/] Saved to {output}")
