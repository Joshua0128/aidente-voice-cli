from dataclasses import dataclass
from typing import Literal


@dataclass
class Chunk:
    index: int
    type: Literal["tts", "pause", "sfx", "gacha"]
    text: str | None = None
    duration: float | None = None
    speed: float = 1.0
    gacha_n: int = 1
    sfx_name: str | None = None
    sfx_fade: float = 0.05
    instruct: str | None = None
