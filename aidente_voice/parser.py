import re
from aidente_voice.models import Chunk

TAG_RE = re.compile(r'<(speed|pause|gacha|sfx|style)=([^>]+)>')
SENTENCE_END_RE = re.compile(r'(?<=[。！？])\s*|\n+')


class ParseError(ValueError):
    pass


def _parse_sfx_args(value: str) -> tuple[str, float]:
    """Parse sfx tag value like 'laugh' or 'laugh,fade=0.1'."""
    parts = value.split(",")
    name = parts[0].strip()
    fade = 0.05
    for part in parts[1:]:
        if part.strip().startswith("fade="):
            fade = float(part.strip()[5:])
    return name, fade


def parse(text: str) -> list[Chunk]:
    """Parse script text with control tags into a Chunk list."""
    tokens = []
    last = 0
    for m in TAG_RE.finditer(text):
        if m.start() > last:
            tokens.append(("text", text[last:m.start()]))
        tokens.append(("tag", m.group(1), m.group(2)))
        last = m.end()
    if last < len(text):
        tokens.append(("text", text[last:]))

    chunks: list[Chunk] = []
    index = 0
    gacha_pending: int | None = None
    deferred_sfx: list[tuple[str, float]] = []

    def add(chunk: Chunk) -> None:
        nonlocal index
        chunk.index = index
        chunks.append(chunk)
        index += 1

    for token in tokens:
        if token[0] == "text":
            segments = [s.strip() for s in SENTENCE_END_RE.split(token[1])]
            segments = [s for s in segments if s]
            for seg in segments:
                if gacha_pending is not None:
                    add(Chunk(index=0, type="gacha", text=seg, gacha_n=gacha_pending))
                    gacha_pending = None
                    for sfx_name, sfx_fade in deferred_sfx:
                        add(Chunk(index=0, type="sfx", sfx_name=sfx_name, sfx_fade=sfx_fade))
                    deferred_sfx.clear()
                else:
                    add(Chunk(index=0, type="tts", text=seg))

        elif token[0] == "tag":
            _, name, value = token
            if name == "speed":
                if not chunks or chunks[-1].type not in ("tts", "gacha"):
                    raise ParseError(
                        f"<speed> tag has no preceding sentence to attach to."
                    )
                chunks[-1].speed = float(value)

            elif name == "pause":
                add(Chunk(index=0, type="pause", duration=float(value)))

            elif name == "gacha":
                gacha_pending = int(value)

            elif name == "sfx":
                sfx_name, sfx_fade = _parse_sfx_args(value)
                if gacha_pending is not None:
                    deferred_sfx.append((sfx_name, sfx_fade))
                else:
                    add(Chunk(index=0, type="sfx", sfx_name=sfx_name, sfx_fade=sfx_fade))

            elif name == "style":
                if not chunks or chunks[-1].type not in ("tts", "gacha"):
                    raise ParseError("<style> tag has no preceding sentence to attach to.")
                chunks[-1].instruct = value.strip()

    return chunks
