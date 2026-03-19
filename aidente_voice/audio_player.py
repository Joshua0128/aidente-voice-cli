import subprocess
from pathlib import Path


def play(path: str | Path) -> None:
    """Play audio file via afplay. Blocks until playback completes."""
    subprocess.run(["afplay", str(path)], check=True)
