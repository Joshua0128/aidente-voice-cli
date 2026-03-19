"""Gacha (variant selection) for TTS audio."""

import subprocess
import sys
import termios
import tty
from pathlib import Path

GACHA_SEEDS = [42, 1337, 7, 999, 2024, 31337, 100, 555]


def _get_key() -> str:
    """Read a single keypress from stdin using raw mode."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def select_gacha(audio_paths: list[Path], text: str, position: int) -> int:
    """Interactive gacha selection UI.

    Shows numbered options, plays audio on keypress, returns selected index.
    - Number keys (1-N): play that variant
    - Enter (without prior play): auto-plays first, returns index 0
    - Enter (after playing): returns last-played index
    - 'q': quit, returns 0

    Args:
        audio_paths: List of audio file paths for each variant
        text: The text that was synthesized (shown in UI)
        position: Chunk index (shown in UI)

    Returns:
        Selected index (0-based)
    """
    n = len(audio_paths)
    print(f"\n[Gacha] Chunk {position}: {text!r}")
    print(f"  Variants: {n} | Keys: 1-{n} to play, Enter to confirm, q to quit")

    last_played = None

    while True:
        key = _get_key()

        if key == '\r' or key == '\n':
            if last_played is None:
                # Auto-play first and return
                subprocess.run(["afplay", str(audio_paths[0])], check=True)
                return 0
            return last_played

        if key == 'q':
            return 0

        if key.isdigit():
            idx = int(key) - 1
            if 0 <= idx < n:
                subprocess.run(["afplay", str(audio_paths[idx])], check=True)
                last_played = idx
