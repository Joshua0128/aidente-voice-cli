# aidente-voice-cli Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI tool that provides engineering-level control over Qwen3-TTS audio generation via custom tags for pause, speed, sfx, and interactive gacha selection.

**Architecture:** AsyncIO pipeline — parser produces `Chunk[]` → orchestrator calls Modal API (sequential in Phase 1, concurrent in Phase 3) → postprocess applies atempo → gacha interactive selector → assembler concatenates final WAV. Each stage is a focused module with well-defined interfaces.

**Tech Stack:** Python 3.11+, Typer, pydub, ffmpeg-python, requests, rich (progress), termios/tty (raw input), macOS afplay

---

## File Map

```
aidente_voice/
├── __init__.py
├── models.py           # Chunk dataclass — shared data contract
├── parser.py           # Tag parser + semantic chunker
├── audio_player.py     # macOS afplay wrapper
├── gacha.py            # Terminal interactive gacha UX + seed list
├── tts/
│   ├── __init__.py
│   ├── client.py       # TTSClient Protocol (adapter interface)
│   └── modal_client.py # Modal HTTP implementation
└── pipeline/
    ├── __init__.py
    ├── orchestrator.py # Coordinates parse→TTS→postprocess→gacha→assemble
    ├── postprocess.py  # atempo time-stretch via ffmpeg-python
    └── assembler.py    # Silence + sfx splice + final concatenation

tests/
├── test_models.py
├── test_parser.py
├── test_audio_player.py
├── test_gacha.py
├── tts/
│   └── test_modal_client.py
└── pipeline/
    ├── test_postprocess.py
    ├── test_assembler.py
    └── test_orchestrator.py

pyproject.toml
```

---

## Phase 1: MVP

---

### Task 1: Project Setup

**Files:**
- Create: `pyproject.toml`
- Create: `aidente_voice/__init__.py`
- Create: `aidente_voice/tts/__init__.py`
- Create: `aidente_voice/pipeline/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/tts/__init__.py`
- Create: `tests/pipeline/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "aidente-voice"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "pydub>=0.25",
    "ffmpeg-python>=0.2",
    "requests>=2.31",
    "rich>=13.0",
]

[project.scripts]
aidente-voice = "aidente_voice.cli:app"

[tool.pytest.ini_options]
testpaths = ["tests"]

[dependency-groups]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]
```

- [ ] **Step 2: Create all `__init__.py` files (empty)**

```bash
mkdir -p aidente_voice/tts aidente_voice/pipeline tests/tts tests/pipeline
touch aidente_voice/__init__.py aidente_voice/tts/__init__.py aidente_voice/pipeline/__init__.py
touch tests/__init__.py tests/tts/__init__.py tests/pipeline/__init__.py
```

- [ ] **Step 3: Install dependencies**

```toml
# In pyproject.toml, change [dependency-groups] to [project.optional-dependencies]
# so pip extras syntax works:
[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]
```

```bash
pip install -e ".[dev]"
```

Expected: installs cleanly, `aidente-voice --help` not yet available.

- [ ] **Step 4: Verify ffmpeg is available**

```bash
ffmpeg -version
```

If missing: `brew install ffmpeg`

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml aidente_voice/ tests/
git commit -m "feat: project scaffold and dependencies"
```

---

### Task 2: Chunk Data Model

**Files:**
- Create: `aidente_voice/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from aidente_voice.models import Chunk

def test_tts_chunk_defaults():
    c = Chunk(index=0, type="tts", text="hello")
    assert c.speed == 1.0
    assert c.gacha_n == 1
    assert c.sfx_name is None
    assert c.sfx_fade == 0.05

def test_pause_chunk():
    c = Chunk(index=1, type="pause", duration=0.5)
    assert c.duration == 0.5
    assert c.text is None

def test_sfx_chunk_custom_fade():
    c = Chunk(index=2, type="sfx", sfx_name="laugh", sfx_fade=0.1)
    assert c.sfx_name == "laugh"
    assert c.sfx_fade == 0.1

def test_gacha_chunk():
    c = Chunk(index=3, type="gacha", text="test", gacha_n=3)
    assert c.gacha_n == 3
    assert c.type == "gacha"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'aidente_voice.models'`

- [ ] **Step 3: Implement Chunk dataclass**

```python
# aidente_voice/models.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_models.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add aidente_voice/models.py tests/test_models.py
git commit -m "feat: Chunk dataclass"
```

---

### Task 3: Tag Parser

**Files:**
- Create: `aidente_voice/parser.py`
- Create: `tests/test_parser.py`

The parser tokenizes the input text into a stream of text segments and tags, then builds a `Chunk[]`. Key rules:
- Split text on `[。！？\n]+`
- `<speed=X>` attaches to the **preceding** tts chunk (error if no preceding chunk)
- `<pause=X>` inserts a pause chunk at its position
- `<gacha=N>` marks the **next** text segment as a gacha chunk; any `<sfx>` tags between `<gacha>` and the text are deferred and inserted **after** the gacha chunk
- `<sfx=name>` or `<sfx=name,fade=X>` inserts an sfx chunk at its position (unless deferred by gacha context)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_parser.py
import pytest
from aidente_voice.parser import parse, ParseError

def test_plain_tts():
    chunks = parse("Hello world。")
    assert len(chunks) == 1
    assert chunks[0].type == "tts"
    assert chunks[0].text == "Hello world。"
    assert chunks[0].speed == 1.0

def test_speed_tag_attaches_to_preceding():
    chunks = parse("Slow sentence。 <speed=0.85>")
    assert chunks[0].type == "tts"
    assert chunks[0].speed == 0.85

def test_speed_tag_at_start_raises():
    with pytest.raises(ParseError, match="no preceding sentence"):
        parse("<speed=0.85> Some sentence。")

def test_pause_tag():
    chunks = parse("First。 <pause=1.5> Second。")
    assert chunks[0].type == "tts"
    assert chunks[0].text == "First。"
    assert chunks[1].type == "pause"
    assert chunks[1].duration == 1.5
    assert chunks[2].type == "tts"
    assert chunks[2].text == "Second。"

def test_sfx_tag_simple():
    chunks = parse("Hello。 <sfx=laugh>")
    assert chunks[0].type == "tts"
    assert chunks[1].type == "sfx"
    assert chunks[1].sfx_name == "laugh"
    assert chunks[1].sfx_fade == 0.05

def test_sfx_tag_custom_fade():
    chunks = parse("Hello。 <sfx=laugh,fade=0.1>")
    assert chunks[1].sfx_fade == 0.1

def test_sfx_fade_zero():
    chunks = parse("Hello。 <sfx=laugh,fade=0>")
    assert chunks[1].sfx_fade == 0.0

def test_gacha_consumes_next_text():
    chunks = parse("<gacha=3> Uncertain sentence。")
    assert len(chunks) == 1
    assert chunks[0].type == "gacha"
    assert chunks[0].text == "Uncertain sentence。"
    assert chunks[0].gacha_n == 3

def test_gacha_defers_sfx_after_text():
    chunks = parse("<gacha=3> <sfx=laugh> Uncertain sentence。")
    assert chunks[0].type == "gacha"
    assert chunks[0].text == "Uncertain sentence。"
    assert chunks[1].type == "sfx"
    assert chunks[1].sfx_name == "laugh"

def test_full_example():
    text = "接下來我們要講述一個非常關鍵的底層概念。 <speed=0.85>\n很多人在這裡會搞錯， <pause=0.5> <gacha=3> <sfx=laugh> 其實這沒有想像中困難。"
    chunks = parse(text)
    assert len(chunks) == 5
    assert chunks[0].type == "tts" and chunks[0].speed == 0.85
    assert chunks[1].type == "tts"
    assert chunks[2].type == "pause" and chunks[2].duration == 0.5
    assert chunks[3].type == "gacha" and chunks[3].gacha_n == 3
    assert chunks[4].type == "sfx" and chunks[4].sfx_name == "laugh"
    # verify sequential indexing
    for i, c in enumerate(chunks):
        assert c.index == i

def test_empty_text_segments_ignored():
    chunks = parse("Hello。\n\nWorld。")
    assert len(chunks) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_parser.py -v
```

Expected: all FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement parser**

```python
# aidente_voice/parser.py
import re
from aidente_voice.models import Chunk

TAG_RE = re.compile(r'<(speed|pause|gacha|sfx)=([^>]+)>')
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
    # Tokenize into alternating text and tag segments
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
    gacha_pending: int | None = None   # gacha_n if waiting for next text
    deferred_sfx: list[tuple[str, float]] = []  # sfx tags deferred by gacha

    def add(chunk: Chunk) -> None:
        nonlocal index
        chunk.index = index
        chunks.append(chunk)
        index += 1

    for token in tokens:
        if token[0] == "text":
            # Split on sentence boundaries
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

    return chunks
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_parser.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add aidente_voice/parser.py tests/test_parser.py
git commit -m "feat: tag parser with pause/speed/sfx/gacha support"
```

---

### Task 4: TTSClient Protocol + ModalTTSClient

**Files:**
- Create: `aidente_voice/tts/client.py`
- Create: `aidente_voice/tts/modal_client.py`
- Create: `tests/tts/test_modal_client.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/tts/test_modal_client.py
import pytest
from unittest.mock import patch, MagicMock
from aidente_voice.tts.modal_client import ModalTTSClient


@pytest.fixture
def client():
    return ModalTTSClient(endpoint_url="https://fake.modal.run/tts")


@pytest.mark.asyncio
async def test_synthesize_returns_bytes(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"RIFF....fake_wav_bytes"

    with patch("requests.post", return_value=mock_response):
        result = await client.synthesize("Hello world", seed=42)

    assert isinstance(result, bytes)
    assert result == b"RIFF....fake_wav_bytes"


@pytest.mark.asyncio
async def test_synthesize_sends_correct_payload(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"audio"

    with patch("requests.post", return_value=mock_response) as mock_post:
        await client.synthesize("Test sentence", seed=1337)

    call_kwargs = mock_post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
    assert payload["text"] == "Test sentence"
    assert payload["seed"] == 1337


@pytest.mark.asyncio
async def test_synthesize_retries_on_failure(client):
    fail_response = MagicMock()
    fail_response.status_code = 500
    fail_response.content = b""

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.content = b"audio"

    with patch("requests.post", side_effect=[fail_response, fail_response, ok_response]):
        with patch("asyncio.sleep"):  # skip actual delays
            result = await client.synthesize("Test", seed=0)

    assert result == b"audio"


@pytest.mark.asyncio
async def test_synthesize_raises_after_max_retries(client):
    fail_response = MagicMock()
    fail_response.status_code = 500
    fail_response.content = b""

    with patch("requests.post", return_value=fail_response):
        with patch("asyncio.sleep"):
            with pytest.raises(RuntimeError, match="TTS API failed"):
                await client.synthesize("Test", seed=0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/tts/test_modal_client.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement TTSClient Protocol**

```python
# aidente_voice/tts/client.py
from typing import Protocol


class TTSClient(Protocol):
    async def synthesize(self, text: str, seed: int = 0) -> bytes: ...
```

- [ ] **Step 4: Implement ModalTTSClient**

```python
# aidente_voice/tts/modal_client.py
import asyncio
import requests
from aidente_voice.tts.client import TTSClient  # noqa: F401 (for type checking)

_RETRY_DELAYS = [1.0, 2.0, 4.0]


class ModalTTSClient:
    def __init__(self, endpoint_url: str) -> None:
        self._url = endpoint_url

    async def synthesize(self, text: str, seed: int = 0) -> bytes:
        payload = {"text": text, "seed": seed}
        last_exc: Exception | None = None

        for attempt, delay in enumerate([0.0] + _RETRY_DELAYS):
            if delay:
                await asyncio.sleep(delay)
            try:
                response = requests.post(self._url, json=payload, timeout=60)
                if response.status_code == 200:
                    return response.content
                last_exc = RuntimeError(
                    f"TTS API failed: status {response.status_code}"
                )
            except requests.RequestException as e:
                last_exc = e

        raise RuntimeError(
            f"TTS API failed after {len(_RETRY_DELAYS) + 1} attempts: {last_exc}"
        )
```

- [ ] **Step 5: Add `pytest-asyncio` config to pyproject.toml**

Add to `pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
asyncio_mode = "auto"
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/tts/test_modal_client.py -v
```

Expected: 4 PASSED

- [ ] **Step 7: Commit**

```bash
git add aidente_voice/tts/ tests/tts/ pyproject.toml
git commit -m "feat: TTSClient Protocol and ModalTTSClient with retry"
```

---

### Task 5: Audio Player

**Files:**
- Create: `aidente_voice/audio_player.py`
- Create: `tests/test_audio_player.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_audio_player.py
from unittest.mock import patch
from pathlib import Path
from aidente_voice.audio_player import play


def test_play_calls_afplay(tmp_path):
    fake_wav = tmp_path / "test.wav"
    fake_wav.write_bytes(b"")

    with patch("subprocess.run") as mock_run:
        play(fake_wav)

    mock_run.assert_called_once_with(["afplay", str(fake_wav)], check=True)


def test_play_accepts_string_path(tmp_path):
    fake_wav = tmp_path / "test.wav"
    fake_wav.write_bytes(b"")

    with patch("subprocess.run") as mock_run:
        play(str(fake_wav))

    mock_run.assert_called_once_with(["afplay", str(fake_wav)], check=True)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_audio_player.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement audio_player.py**

```python
# aidente_voice/audio_player.py
import subprocess
from pathlib import Path


def play(path: str | Path) -> None:
    """Play audio file via afplay. Blocks until playback completes."""
    subprocess.run(["afplay", str(path)], check=True)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_audio_player.py -v
```

Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add aidente_voice/audio_player.py tests/test_audio_player.py
git commit -m "feat: audio_player afplay wrapper"
```

---

### Task 6: Post-Processing (atempo time-stretch)

**Files:**
- Create: `aidente_voice/pipeline/postprocess.py`
- Create: `tests/pipeline/test_postprocess.py`

`build_atempo_chain(speed)` factorizes a speed value into a list of floats, each in `[0.5, 2.0]`, whose product equals `speed`. `apply_speed(audio_bytes, speed)` runs the ffmpeg atempo pipeline.

- [ ] **Step 1: Write the failing tests**

```python
# tests/pipeline/test_postprocess.py
import pytest
from unittest.mock import patch, MagicMock, mock_open
from aidente_voice.pipeline.postprocess import build_atempo_chain, apply_speed


def test_chain_single_value_in_range():
    assert build_atempo_chain(0.85) == pytest.approx([0.85])

def test_chain_single_value_boundary():
    assert build_atempo_chain(0.5) == pytest.approx([0.5])
    assert build_atempo_chain(2.0) == pytest.approx([2.0])

def test_chain_below_range():
    chain = build_atempo_chain(0.3)
    # product must equal 0.3, each factor in [0.5, 2.0]
    product = 1.0
    for f in chain:
        assert 0.5 <= f <= 2.0
        product *= f
    assert product == pytest.approx(0.3, rel=1e-4)

def test_chain_above_range():
    chain = build_atempo_chain(3.0)
    product = 1.0
    for f in chain:
        assert 0.5 <= f <= 2.0
        product *= f
    assert product == pytest.approx(3.0, rel=1e-4)

def test_chain_speed_one_is_noop():
    assert build_atempo_chain(1.0) == pytest.approx([1.0])

def test_apply_speed_calls_ffmpeg_filter(tmp_path):
    """apply_speed calls ffmpeg.filter once per atempo factor."""
    from unittest.mock import call
    fake_bytes = b"RIFF" + b"\x00" * 100

    mock_stream = MagicMock()

    with patch("ffmpeg.input") as mock_input, \
         patch("ffmpeg.filter", return_value=mock_stream) as mock_filter, \
         patch("ffmpeg.output") as mock_output, \
         patch("ffmpeg.run"), \
         patch("builtins.open", mock_open(read_data=b"result_audio")), \
         patch("os.unlink"), \
         patch("tempfile.NamedTemporaryFile") as mock_tmp:

        mock_tmp.return_value.__enter__ = lambda s: s
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)
        mock_tmp.return_value.name = "/tmp/fake.wav"
        mock_input.return_value.audio = mock_stream

        apply_speed(fake_bytes, speed=0.85)

    # Should call ffmpeg.filter once for speed in [0.5, 2.0]
    mock_filter.assert_called_once_with(mock_stream, "atempo", pytest.approx(0.85))


def test_apply_speed_noop_on_speed_one():
    """speed=1.0 returns input bytes unchanged without calling ffmpeg."""
    fake_bytes = b"audio_data"
    result = apply_speed(fake_bytes, speed=1.0)
    assert result == fake_bytes
```

- [ ] **Step 2: Run tests to verify chain tests fail**

```bash
pytest tests/pipeline/test_postprocess.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement postprocess.py**

```python
# aidente_voice/pipeline/postprocess.py
import math
import tempfile
import os
import ffmpeg

AUDIO_SAMPLE_RATE = 24000


def build_atempo_chain(speed: float) -> list[float]:
    """Factorize speed into atempo filter values, each in [0.5, 2.0]."""
    if speed == 1.0:
        return [1.0]
    factors: list[float] = []
    remaining = speed
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    factors.append(remaining)
    return factors


def apply_speed(audio_bytes: bytes, speed: float) -> bytes:
    """Apply time-stretch to audio bytes using ffmpeg atempo. Returns WAV bytes."""
    if speed == 1.0:
        return audio_bytes

    factors = build_atempo_chain(speed)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as in_f:
        in_f.write(audio_bytes)
        in_path = in_f.name

    out_path = in_path.replace(".wav", "_out.wav")
    try:
        stream = ffmpeg.input(in_path).audio
        for factor in factors:
            stream = ffmpeg.filter(stream, "atempo", factor)
        ffmpeg.output(stream, out_path).run(quiet=True, overwrite_output=True)
        with open(out_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(in_path)
        if os.path.exists(out_path):
            os.unlink(out_path)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/pipeline/test_postprocess.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add aidente_voice/pipeline/postprocess.py tests/pipeline/test_postprocess.py
git commit -m "feat: atempo time-stretch with auto-chain for speed < 0.5 or > 2.0"
```

---

### Task 7: Assembler (silence + sfx + concatenation)

**Files:**
- Create: `aidente_voice/pipeline/assembler.py`
- Create: `tests/pipeline/test_assembler.py`

The assembler takes a list of `(Chunk, bytes | None)` pairs and produces a final `AudioSegment`. It handles: tts/gacha bytes → AudioSegment, pause → silence, sfx → load clip + auto-resample + fade.

- [ ] **Step 1: Write the failing tests**

```python
# tests/pipeline/test_assembler.py
import io
import pytest
from pathlib import Path
from pydub import AudioSegment
from pydub.generators import Sine
from aidente_voice.models import Chunk
from aidente_voice.pipeline.assembler import assemble, _make_silence, _load_sfx


SAMPLE_RATE = 24000


def _make_wav_bytes(duration_ms: int = 500) -> bytes:
    """Generate a real WAV bytes for testing."""
    seg = Sine(440).to_audio_segment(duration=duration_ms).set_frame_rate(SAMPLE_RATE).set_channels(1).set_sample_width(2)
    buf = io.BytesIO()
    seg.export(buf, format="wav")
    return buf.getvalue()


def test_make_silence_correct_duration():
    silence = _make_silence(1.0)
    assert len(silence) == pytest.approx(1000, abs=5)  # 1000ms
    assert silence.frame_rate == SAMPLE_RATE
    assert silence.channels == 1


def test_assemble_single_tts():
    wav = _make_wav_bytes(500)
    chunk = Chunk(index=0, type="tts", text="hello")
    result = assemble([(chunk, wav)])
    assert len(result) > 400  # at least ~500ms


def test_assemble_pause_inserts_silence():
    wav = _make_wav_bytes(100)
    tts_chunk = Chunk(index=0, type="tts", text="hello")
    pause_chunk = Chunk(index=1, type="pause", duration=1.0)
    result = assemble([(tts_chunk, wav), (pause_chunk, None)])
    # result should be longer than input wav by ~1000ms
    assert len(result) >= 1000


def test_assemble_sfx_with_fade(tmp_path):
    # Create a fake sfx clip
    sfx_path = tmp_path / "laugh.wav"
    sfx_bytes = _make_wav_bytes(300)
    sfx_path.write_bytes(sfx_bytes)

    wav = _make_wav_bytes(200)
    tts_chunk = Chunk(index=0, type="tts", text="hello")
    sfx_chunk = Chunk(index=1, type="sfx", sfx_name="laugh", sfx_fade=0.05)
    result = assemble([(tts_chunk, wav), (sfx_chunk, None)], sfx_dir=tmp_path)
    assert len(result) > 400


def test_assemble_sfx_missing_raises(tmp_path):
    sfx_chunk = Chunk(index=0, type="sfx", sfx_name="laugh", sfx_fade=0.05)
    with pytest.raises(FileNotFoundError, match="SFX file not found"):
        assemble([(sfx_chunk, None)], sfx_dir=tmp_path)


def test_load_sfx_auto_resamples(tmp_path):
    """SFX at 44100Hz stereo should be auto-converted to 24kHz mono."""
    sfx_44k = AudioSegment.silent(duration=200, frame_rate=44100).set_channels(2)
    sfx_path = tmp_path / "laugh.wav"
    sfx_44k.export(sfx_path, format="wav")

    result = _load_sfx(sfx_path, fade_sec=0.0)
    assert result.frame_rate == SAMPLE_RATE
    assert result.channels == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/pipeline/test_assembler.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement assembler.py**

```python
# aidente_voice/pipeline/assembler.py
import io
import sys
from pathlib import Path
from pydub import AudioSegment
from aidente_voice.models import Chunk

SAMPLE_RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit


def _make_silence(duration_sec: float) -> AudioSegment:
    return AudioSegment.silent(
        duration=int(duration_sec * 1000),
        frame_rate=SAMPLE_RATE,
    ).set_channels(CHANNELS).set_sample_width(SAMPLE_WIDTH)


def _load_sfx(path: Path, fade_sec: float) -> AudioSegment:
    clip = AudioSegment.from_wav(str(path))
    if clip.frame_rate != SAMPLE_RATE or clip.channels != CHANNELS:
        print(
            f"[WARN] {path.name} is {clip.frame_rate}Hz "
            f"{'stereo' if clip.channels == 2 else str(clip.channels) + 'ch'}"
            " — auto-converting to 24kHz mono.",
            file=sys.stderr,
        )
        clip = clip.set_frame_rate(SAMPLE_RATE).set_channels(CHANNELS)
    clip = clip.set_sample_width(SAMPLE_WIDTH)
    if fade_sec > 0:
        fade_ms = int(fade_sec * 1000)
        clip = clip.fade_in(fade_ms).fade_out(fade_ms)
    return clip


def _bytes_to_segment(audio_bytes: bytes) -> AudioSegment:
    return AudioSegment.from_wav(io.BytesIO(audio_bytes))


def assemble(
    chunks_with_audio: list[tuple[Chunk, bytes | None]],
    sfx_dir: Path | None = None,
    output_path: Path | None = None,
) -> AudioSegment:
    """Concatenate chunks into a final AudioSegment. Optionally export to file."""
    if sfx_dir is None:
        sfx_dir = Path.home() / ".aidente" / "sfx"

    result = AudioSegment.empty()

    for chunk, audio_bytes in chunks_with_audio:
        if chunk.type in ("tts", "gacha"):
            result += _bytes_to_segment(audio_bytes)  # type: ignore[arg-type]

        elif chunk.type == "pause":
            result += _make_silence(chunk.duration or 0.0)

        elif chunk.type == "sfx":
            sfx_path = sfx_dir / f"{chunk.sfx_name}.wav"
            if not sfx_path.exists():
                raise FileNotFoundError(
                    f"SFX file not found: {sfx_path}. "
                    f"Add the file or remove the <sfx> tag."
                )
            result += _load_sfx(sfx_path, fade_sec=chunk.sfx_fade)

    if output_path:
        result.export(str(output_path), format="wav")

    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/pipeline/test_assembler.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add aidente_voice/pipeline/assembler.py tests/pipeline/test_assembler.py
git commit -m "feat: assembler with silence, sfx splice, auto-resample"
```

---

### Task 8: Phase 1 Orchestrator (sequential)

**Files:**
- Create: `aidente_voice/pipeline/orchestrator.py`
- Create: `tests/pipeline/test_orchestrator.py`

Phase 1 uses sequential `await` — one TTS call at a time. The interface is `async` so Phase 3 only needs to change the gather strategy, not the interface.

- [ ] **Step 1: Write the failing tests**

```python
# tests/pipeline/test_orchestrator.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from aidente_voice.models import Chunk
from aidente_voice.pipeline.orchestrator import run_pipeline


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.synthesize.return_value = b"RIFF" + b"\x00" * 44  # fake WAV
    return client


@pytest.mark.asyncio
async def test_tts_chunks_are_synthesized(mock_client):
    chunks = [
        Chunk(index=0, type="tts", text="Hello world。"),
    ]
    result = await run_pipeline(chunks, client=mock_client)
    mock_client.synthesize.assert_called_once_with("Hello world。", seed=0)
    assert len(result) == 1
    assert result[0][0] == chunks[0]


@pytest.mark.asyncio
async def test_pause_chunks_pass_through(mock_client):
    chunks = [
        Chunk(index=0, type="tts", text="Hello。"),
        Chunk(index=1, type="pause", duration=1.0),
    ]
    result = await run_pipeline(chunks, client=mock_client)
    assert result[1][1] is None  # no audio bytes for pause


@pytest.mark.asyncio
async def test_sfx_chunks_pass_through(mock_client):
    chunks = [
        Chunk(index=0, type="sfx", sfx_name="laugh"),
    ]
    result = await run_pipeline(chunks, client=mock_client)
    assert result[0][1] is None


@pytest.mark.asyncio
async def test_speed_applied_after_synthesis(mock_client):
    chunks = [Chunk(index=0, type="tts", text="Slow。", speed=0.85)]
    with patch("aidente_voice.pipeline.orchestrator.apply_speed", return_value=b"slow_audio") as mock_speed:
        result = await run_pipeline(chunks, client=mock_client)
    mock_speed.assert_called_once()
    assert result[0][1] == b"slow_audio"


@pytest.mark.asyncio
async def test_speed_one_skips_postprocess(mock_client):
    chunks = [Chunk(index=0, type="tts", text="Normal。", speed=1.0)]
    with patch("aidente_voice.pipeline.orchestrator.apply_speed") as mock_speed:
        await run_pipeline(chunks, client=mock_client)
    mock_speed.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/pipeline/test_orchestrator.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement orchestrator.py**

```python
# aidente_voice/pipeline/orchestrator.py
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
            audio = await client.synthesize(chunk.text or "", seed=0)
            if chunk.speed != 1.0:
                audio = apply_speed(audio, chunk.speed)
            results.append((chunk, audio))
        else:
            results.append((chunk, None))

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/pipeline/test_orchestrator.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add aidente_voice/pipeline/orchestrator.py tests/pipeline/test_orchestrator.py
git commit -m "feat: Phase 1 sequential orchestrator"
```

---

### Task 9: CLI (Typer)

**Files:**
- Create: `aidente_voice/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli.py
import os
from pathlib import Path
from typer.testing import CliRunner
from unittest.mock import patch, AsyncMock
from aidente_voice.cli import app

runner = CliRunner()


def test_dry_run_prints_chunks(tmp_path):
    script = tmp_path / "script.txt"
    script.write_text("Hello world。 <pause=1.0>\n接下來。 <speed=0.85>")

    result = runner.invoke(app, ["generate", "-i", str(script), "--dry-run"])

    assert result.exit_code == 0
    assert "DRY RUN" in result.output
    assert "tts" in result.output
    assert "pause" in result.output
    assert "No API calls made" in result.output


def test_missing_input_file_exits_with_error():
    result = runner.invoke(app, ["generate", "-i", "nonexistent.txt"])
    assert result.exit_code != 0


def test_generate_calls_pipeline(tmp_path):
    script = tmp_path / "script.txt"
    script.write_text("Hello。")
    output = tmp_path / "out.wav"

    fake_audio = b"RIFF" + b"\x00" * 100

    with patch("aidente_voice.cli.ModalTTSClient") as MockClient, \
         patch("aidente_voice.cli.run_pipeline", new_callable=AsyncMock) as mock_run, \
         patch("aidente_voice.cli.assemble") as mock_assemble:

        from aidente_voice.models import Chunk
        mock_chunk = Chunk(index=0, type="tts", text="Hello。")
        mock_run.return_value = [(mock_chunk, fake_audio)]
        mock_assemble.return_value = None

        result = runner.invoke(app, [
            "generate", "-i", str(script), "-o", str(output),
        ], env={"MODAL_TTS_URL": "https://fake.modal.run/tts"})

    assert result.exit_code == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_cli.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement cli.py**

```python
# aidente_voice/cli.py
import asyncio
import os
import sys
from pathlib import Path

import typer
from rich.console import Console

from aidente_voice.models import Chunk
from aidente_voice.parser import parse, ParseError
from aidente_voice.tts.modal_client import ModalTTSClient
from aidente_voice.pipeline.orchestrator import run_pipeline
from aidente_voice.pipeline.assembler import assemble

app = typer.Typer(help="aidente-voice: TTS production pipeline with engineering control")
console = Console()


def _dry_run_report(chunks: list[Chunk]) -> None:
    console.print(f"[bold cyan][DRY RUN][/] Parsed {len(chunks)} chunks:")
    for c in chunks:
        if c.type == "tts":
            speed_str = f" speed={c.speed}" if c.speed != 1.0 else ""
            console.print(f"  [{c.index}] tts    \"{c.text}\"{speed_str}")
        elif c.type == "pause":
            console.print(f"  [{c.index}] pause  {c.duration}s")
        elif c.type == "gacha":
            console.print(f"  [{c.index}] gacha  \"{c.text}\" n={c.gacha_n}")
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
) -> None:
    """Generate TTS audio from a script with control tags."""
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

    client = ModalTTSClient(endpoint_url=modal_url)

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_cli.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add aidente_voice/cli.py tests/test_cli.py
git commit -m "feat: Typer CLI with generate command and --dry-run"
```

---

### Task 10: Phase 1 Integration Test

**Files:**
- Create: `tests/test_integration_phase1.py`

This test runs the full pipeline end-to-end with a mocked TTS client to verify all parts connect correctly.

- [ ] **Step 1: Write the integration test**

```python
# tests/test_integration_phase1.py
import io
import asyncio
from pathlib import Path
from pydub import AudioSegment
from pydub.generators import Sine
from aidente_voice.parser import parse
from aidente_voice.pipeline.orchestrator import run_pipeline
from aidente_voice.pipeline.assembler import assemble


def _make_wav_bytes(duration_ms: int = 300) -> bytes:
    seg = (
        Sine(440)
        .to_audio_segment(duration=duration_ms)
        .set_frame_rate(24000)
        .set_channels(1)
        .set_sample_width(2)
    )
    buf = io.BytesIO()
    seg.export(buf, format="wav")
    return buf.getvalue()


class FakeTTSClient:
    async def synthesize(self, text: str, seed: int = 0) -> bytes:
        return _make_wav_bytes(300)


async def _run(script: str, sfx_dir: Path) -> AudioSegment:
    chunks = parse(script)
    results = await run_pipeline(chunks, client=FakeTTSClient())
    return assemble(results, sfx_dir=sfx_dir)


def test_tts_plus_pause(tmp_path):
    script = "Hello world。 <pause=0.5> Goodbye world。"
    result = asyncio.run(_run(script, sfx_dir=tmp_path))
    # 2 × 300ms audio + 500ms pause = ~1100ms
    assert len(result) >= 1000


def test_tts_with_speed(tmp_path):
    script = "Slow sentence。 <speed=1.0>"  # speed=1.0 for test (no ffmpeg needed)
    result = asyncio.run(_run(script, sfx_dir=tmp_path))
    assert len(result) > 0


def test_sfx_splice(tmp_path):
    # Create fake sfx clip
    sfx = _make_wav_bytes(200)
    (tmp_path / "laugh.wav").write_bytes(sfx)

    script = "Hello。 <sfx=laugh>"
    result = asyncio.run(_run(script, sfx_dir=tmp_path))
    assert len(result) >= 400


def test_full_script(tmp_path):
    sfx = _make_wav_bytes(200)
    (tmp_path / "laugh.wav").write_bytes(sfx)

    script = (
        "接下來我們要講述一個非常關鍵的底層概念。\n"
        "很多人在這裡會搞錯， <pause=0.5> <sfx=laugh>"
    )
    result = asyncio.run(_run(script, sfx_dir=tmp_path))
    assert len(result) >= 1200
```

- [ ] **Step 2: Run the integration tests**

```bash
pytest tests/test_integration_phase1.py -v
```

Expected: all PASSED

- [ ] **Step 3: Run the full test suite**

```bash
pytest -v
```

Expected: all tests PASSED

- [ ] **Step 4: Smoke test the CLI**

```bash
echo "Hello world。 <pause=1.0> Goodbye。" > /tmp/test_script.txt
aidente-voice generate -i /tmp/test_script.txt --dry-run
```

Expected output:
```
[DRY RUN] Parsed 3 chunks:
  [0] tts    "Hello world。"
  [1] pause  1.0s
  [2] tts    "Goodbye。"
No API calls made.
```

> **Parser note:** The sentence boundary regex `(?<=[。！？])\s*|\n+` splits on `。！？` and newlines. Chinese commas `，` do NOT trigger a split — they stay within the current text segment. A sentence ending with `，` will be included in the same chunk as the text up to the next `。！？` or newline.

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration_phase1.py
git commit -m "test: Phase 1 integration tests — full pipeline smoke test"
```

---

## Phase 2: Gacha Interactive UX

---

### Task 11: Gacha Selector

**Files:**
- Create: `aidente_voice/gacha.py`
- Create: `tests/test_gacha.py`

`GACHA_SEEDS` is the fixed seed list `[42, 1337, 7, 999, 2024, 31337, 100, 555]`. `select_gacha(options, text, position)` handles the terminal UX: displays the menu, uses `termios` raw mode for single-keypress input, plays audio via `audio_player.play()`. Returns the index (0-based) of the selected option.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gacha.py
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile, io
from pydub import AudioSegment
from aidente_voice.gacha import GACHA_SEEDS, select_gacha


def _make_wav(tmp_path: Path, name: str) -> Path:
    from pydub.generators import Sine
    seg = Sine(440).to_audio_segment(duration=100).set_frame_rate(24000).set_channels(1).set_sample_width(2)
    p = tmp_path / name
    buf = io.BytesIO()
    seg.export(buf, format="wav")
    p.write_bytes(buf.getvalue())
    return p


def test_gacha_seeds_has_enough_values():
    assert len(GACHA_SEEDS) >= 8


def test_gacha_seeds_are_unique():
    assert len(GACHA_SEEDS) == len(set(GACHA_SEEDS))


def test_select_returns_valid_index(tmp_path):
    paths = [_make_wav(tmp_path, f"opt{i}.wav") for i in range(3)]

    # Simulate: user plays option 1, then presses Enter to confirm
    inputs = iter(["1", "\r"])

    with patch("aidente_voice.gacha._get_key", side_effect=inputs), \
         patch("aidente_voice.gacha.play"):
        idx = select_gacha(paths, text="Test sentence。", position=(1, 2))

    assert idx == 0  # "1" → index 0


def test_select_enter_without_play_auto_plays_first(tmp_path):
    paths = [_make_wav(tmp_path, f"opt{i}.wav") for i in range(2)]

    # Simulate: user immediately presses Enter (no prior play), then Enter again
    inputs = iter(["\r", "\r"])

    with patch("aidente_voice.gacha._get_key", side_effect=inputs), \
         patch("aidente_voice.gacha.play") as mock_play:
        idx = select_gacha(paths, text="Test。", position=(1, 1))

    mock_play.assert_called()
    assert idx == 0


def test_select_q_returns_default(tmp_path):
    paths = [_make_wav(tmp_path, f"opt{i}.wav") for i in range(3)]
    inputs = iter(["q"])

    with patch("aidente_voice.gacha._get_key", side_effect=inputs), \
         patch("aidente_voice.gacha.play"):
        idx = select_gacha(paths, text="Test。", position=(1, 1))

    assert idx == 0  # default is option 1 (index 0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_gacha.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement gacha.py**

```python
# aidente_voice/gacha.py
import sys
import tty
import termios
from pathlib import Path
from aidente_voice.audio_player import play

GACHA_SEEDS = [42, 1337, 7, 999, 2024, 31337, 100, 555]


def _get_key() -> str:
    """Read a single keypress without echoing (raw mode)."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch


def select_gacha(
    audio_paths: list[Path],
    text: str,
    position: tuple[int, int],  # (current, total)
) -> int:
    """
    Interactive terminal gacha selector.
    Returns 0-based index of selected option.
    Defaults to 0 (Option 1) if user quits with 'q'.
    """
    n = len(audio_paths)
    current, total = position
    played: set[int] = set()
    selected: int | None = None

    def render(currently_playing: int | None = None) -> None:
        print(f"\n{'━' * 17}  GACHA {current}/{total}  {'━' * 17}")
        print(f' "{text}"')
        print('━' * 47)
        for i, _ in enumerate(audio_paths):
            label = f"[{i + 1}]"
            playing = "▶ " if currently_playing == i else "   "
            checked = " ✓" if i in played and currently_playing != i else ""
            print(f" {label} {playing}Option {i + 1}{checked}")
        print()
        print(" Controls: [1–{}] play option  [Enter] confirm  [q] quit".format(n))
        print("> ", end="", flush=True)

    render()

    while True:
        key = _get_key()

        if key in [str(i + 1) for i in range(n)]:
            idx = int(key) - 1
            print(key)
            render(currently_playing=idx)
            play(audio_paths[idx])
            played.add(idx)
            selected = idx
            render()

        elif key in ("\r", "\n"):
            if selected is None:
                # Auto-play Option 1
                render(currently_playing=0)
                play(audio_paths[0])
                played.add(0)
                selected = 0
                print("\n▶ Played Option 1. Press [Enter] again to confirm, or [1–{}] to play another.".format(n))
                print("> ", end="", flush=True)
            else:
                print()
                print(f"✔ Selected Option {selected + 1}. Continuing...")
                return selected

        elif key == "q":
            print()
            print(
                "[WARN] Gacha aborted. Assembling with selections so far. "
                "Unselected gacha chunks will use Option 1 as default."
            )
            return 0
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_gacha.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add aidente_voice/gacha.py tests/test_gacha.py
git commit -m "feat: gacha interactive terminal selector with GACHA_SEEDS"
```

---

### Task 12: Integrate Gacha into Orchestrator

**Files:**
- Modify: `aidente_voice/pipeline/orchestrator.py`
- Modify: `tests/pipeline/test_orchestrator.py`

Gacha chunks now generate `N` audio versions (using `GACHA_SEEDS[:n]`), then call `select_gacha()` after all synthesis is done, then store only the selected version.

- [ ] **Step 1: Write failing tests for gacha integration**

Add to `tests/pipeline/test_orchestrator.py`:

```python
@pytest.mark.asyncio
async def test_gacha_chunk_generates_n_versions(mock_client):
    chunks = [Chunk(index=0, type="gacha", text="Uncertain。", gacha_n=3)]

    with patch("aidente_voice.pipeline.orchestrator.select_gacha", return_value=1) as mock_gacha, \
         patch("aidente_voice.pipeline.orchestrator.GACHA_SEEDS", [42, 1337, 7]):
        results = await run_pipeline(chunks, client=mock_client)

    assert mock_client.synthesize.call_count == 3
    # synthesize called with seeds 42, 1337, 7
    calls = mock_client.synthesize.call_args_list
    seeds = [c.kwargs["seed"] for c in calls]
    assert seeds == [42, 1337, 7]
    # select_gacha called with 3 audio paths
    assert mock_gacha.called

@pytest.mark.asyncio
async def test_gacha_result_uses_selected_version(mock_client):
    chunks = [Chunk(index=0, type="gacha", text="Test。", gacha_n=2)]
    mock_client.synthesize.side_effect = [b"audio_A", b"audio_B"]

    with patch("aidente_voice.pipeline.orchestrator.select_gacha", return_value=1), \
         patch("aidente_voice.pipeline.orchestrator._write_chunk_to_disk"), \
         patch("tempfile.NamedTemporaryFile") as mock_tmp, \
         patch("os.unlink"):
        # Provide a valid temp file mock so select_gacha receives paths
        mock_tmp.return_value.__enter__ = lambda s: s
        mock_tmp.return_value.__exit__ = MagicMock(return_value=False)
        mock_tmp.return_value.name = "/tmp/fake_gacha.wav"
        results = await run_pipeline(chunks, client=mock_client)

    assert results[0][1] == b"audio_B"  # index 1 selected
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/pipeline/test_orchestrator.py::test_gacha_chunk_generates_n_versions -v
```

Expected: FAIL

- [ ] **Step 3: Update orchestrator.py to handle gacha chunks**

```python
# aidente_voice/pipeline/orchestrator.py
import tempfile
import os
from pathlib import Path
from aidente_voice.models import Chunk
from aidente_voice.tts.client import TTSClient
from aidente_voice.pipeline.postprocess import apply_speed
from aidente_voice.gacha import select_gacha, GACHA_SEEDS


def _write_chunk_to_disk(audio: bytes, path: Path) -> Path:
    path.write_bytes(audio)
    return path


async def run_pipeline(
    chunks: list[Chunk],
    client: TTSClient,
    keep_chunks_dir: Path | None = None,
) -> list[tuple[Chunk, bytes | None]]:
    """
    Phase 1/2: sequential TTS synthesis with gacha interactive selection.
    Returns list of (chunk, audio_bytes) pairs.
    """
    # Step 1: synthesize all non-gacha TTS chunks and all gacha versions
    raw_results: list[tuple[Chunk, bytes | None] | tuple[Chunk, list[bytes]]] = []

    for chunk in chunks:
        if chunk.type == "tts":
            audio = await client.synthesize(chunk.text or "", seed=0)
            if chunk.speed != 1.0:
                audio = apply_speed(audio, chunk.speed)
            raw_results.append((chunk, audio))

        elif chunk.type == "gacha":
            seeds = GACHA_SEEDS[: chunk.gacha_n]
            versions = []
            for seed in seeds:
                v = await client.synthesize(chunk.text or "", seed=seed)
                if chunk.speed != 1.0:
                    v = apply_speed(v, chunk.speed)
                versions.append(v)
            raw_results.append((chunk, versions))  # type: ignore[arg-type]

        else:
            raw_results.append((chunk, None))

    # Step 2: interactive gacha selection for all gacha chunks
    gacha_indices = [i for i, (c, _) in enumerate(raw_results) if c.type == "gacha"]
    gacha_count = len(gacha_indices)

    final: list[tuple[Chunk, bytes | None]] = []
    gacha_pos = 0

    for i, (chunk, audio) in enumerate(raw_results):
        if chunk.type != "gacha":
            final.append((chunk, audio))  # type: ignore[arg-type]
            continue

        gacha_pos += 1
        versions: list[bytes] = audio  # type: ignore[assignment]

        # Write versions to temp files for playback
        tmp_paths = []
        for j, v in enumerate(versions):
            tmp = tempfile.NamedTemporaryFile(
                suffix=f"_gacha_{chunk.index}_opt{j}.wav", delete=False
            )
            tmp.write(v)
            tmp.close()
            tmp_paths.append(Path(tmp.name))

        try:
            selected_idx = select_gacha(
                tmp_paths,
                text=chunk.text or "",
                position=(gacha_pos, gacha_count),
            )
        finally:
            for p in tmp_paths:
                if p.exists():
                    os.unlink(p)

        selected_audio = versions[selected_idx]

        if keep_chunks_dir:
            for j, v in enumerate(versions):
                _write_chunk_to_disk(
                    v, keep_chunks_dir / f"chunk_{chunk.index:03d}_gacha_{chr(65 + j)}.wav"
                )

        final.append((chunk, selected_audio))

    return final
```

- [ ] **Step 4: Run full test suite**

```bash
pytest -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add aidente_voice/pipeline/orchestrator.py tests/pipeline/test_orchestrator.py
git commit -m "feat: gacha multi-seed synthesis and interactive selection in orchestrator"
```

---

### Task 13: Phase 2 Integration Test

**Files:**
- Create: `tests/test_integration_phase2.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/test_integration_phase2.py
import io
import asyncio
from pathlib import Path
from pydub import AudioSegment
from pydub.generators import Sine
from unittest.mock import patch
from aidente_voice.parser import parse
from aidente_voice.pipeline.orchestrator import run_pipeline
from aidente_voice.pipeline.assembler import assemble


def _make_wav_bytes(duration_ms: int = 300) -> bytes:
    seg = (
        Sine(440).to_audio_segment(duration=duration_ms)
        .set_frame_rate(24000).set_channels(1).set_sample_width(2)
    )
    buf = io.BytesIO()
    seg.export(buf, format="wav")
    return buf.getvalue()


class FakeTTSClient:
    async def synthesize(self, text: str, seed: int = 0) -> bytes:
        return _make_wav_bytes(300)


def test_gacha_pipeline_end_to_end(tmp_path):
    script = "Hello。 <gacha=3> Uncertain sentence。"
    chunks = parse(script)

    with patch("aidente_voice.pipeline.orchestrator.select_gacha", return_value=1):
        results = asyncio.run(run_pipeline(chunks, client=FakeTTSClient()))

    final = assemble(results, sfx_dir=tmp_path)
    assert len(final) >= 500


def test_gacha_q_uses_option_1(tmp_path):
    script = "<gacha=2> Some sentence。"
    chunks = parse(script)

    with patch("aidente_voice.pipeline.orchestrator.select_gacha", return_value=0):
        results = asyncio.run(run_pipeline(chunks, client=FakeTTSClient()))

    assert results[0][1] is not None
    final = assemble(results, sfx_dir=tmp_path)
    assert len(final) > 0
```

- [ ] **Step 2: Run Phase 2 integration tests**

```bash
pytest tests/test_integration_phase2.py -v
```

Expected: all PASSED

- [ ] **Step 3: Run full test suite**

```bash
pytest -v
```

Expected: all PASSED

- [ ] **Step 4: Commit**

```bash
git add tests/test_integration_phase2.py
git commit -m "test: Phase 2 gacha integration tests"
```

---

## Phase 3: Async Optimization

---

### Task 14: Concurrent Orchestrator with Progress Bar

**Files:**
- Modify: `aidente_voice/pipeline/orchestrator.py`
- Modify: `tests/pipeline/test_orchestrator.py`

Upgrade the TTS synthesis step to `asyncio.gather()` with `asyncio.Semaphore`. Gacha selection stays sequential (after all synthesis). Add a `rich` progress bar for the synthesis phase.

- [ ] **Step 1: Write the failing concurrency test**

Add to `tests/pipeline/test_orchestrator.py`:

```python
@pytest.mark.asyncio
async def test_concurrent_tts_chunks_all_synthesized(mock_client):
    """All TTS chunks should be synthesized, order preserved."""
    chunks = [Chunk(index=i, type="tts", text=f"Sentence {i}。") for i in range(5)]

    with patch("aidente_voice.pipeline.orchestrator.select_gacha"):
        results = await run_pipeline(chunks, client=mock_client, max_concurrent=3)

    assert mock_client.synthesize.call_count == 5
    # Results preserve original index order
    for i, (chunk, _) in enumerate(results):
        assert chunk.index == i
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/pipeline/test_orchestrator.py::test_concurrent_tts_chunks_all_synthesized -v
```

Expected: FAIL (`run_pipeline` doesn't accept `max_concurrent`)

- [ ] **Step 3: Upgrade orchestrator.py to concurrent gather**

```python
# aidente_voice/pipeline/orchestrator.py
import asyncio
import tempfile
import os
from pathlib import Path
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn

from aidente_voice.models import Chunk
from aidente_voice.tts.client import TTSClient
from aidente_voice.pipeline.postprocess import apply_speed
from aidente_voice.gacha import select_gacha, GACHA_SEEDS


def _write_chunk_to_disk(audio: bytes, path: Path) -> None:
    path.write_bytes(audio)


async def _synthesize_chunk(
    chunk: Chunk,
    client: TTSClient,
    semaphore: asyncio.Semaphore,
    seeds: list[int] | None = None,
) -> bytes | list[bytes]:
    """Synthesize a single tts or gacha chunk under semaphore."""
    async with semaphore:
        if chunk.type == "tts":
            audio = await client.synthesize(chunk.text or "", seed=0)
            if chunk.speed != 1.0:
                audio = apply_speed(audio, chunk.speed)
            return audio
        else:  # gacha
            versions = []
            for seed in (seeds or GACHA_SEEDS[: chunk.gacha_n]):
                v = await client.synthesize(chunk.text or "", seed=seed)
                if chunk.speed != 1.0:
                    v = apply_speed(v, chunk.speed)
                versions.append(v)
            return versions


async def run_pipeline(
    chunks: list[Chunk],
    client: TTSClient,
    keep_chunks_dir: Path | None = None,
    max_concurrent: int = 10,
    show_progress: bool = True,
) -> list[tuple[Chunk, bytes | None]]:
    """
    Phase 3: concurrent TTS synthesis via asyncio.gather + Semaphore.
    Gacha interactive selection happens after all synthesis.
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    tts_chunks = [(i, c) for i, c in enumerate(chunks) if c.type in ("tts", "gacha")]

    synthesis_results: dict[int, bytes | list[bytes]] = {}

    async def synthesize_with_progress(idx: int, chunk: Chunk, progress, task) -> None:
        result = await _synthesize_chunk(chunk, client, semaphore)
        synthesis_results[idx] = result
        if progress:
            progress.advance(task)

    if show_progress and tts_chunks:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
        ) as progress:
            task = progress.add_task(
                "Generating chunks via Qwen3-TTS...", total=len(tts_chunks)
            )
            await asyncio.gather(
                *[synthesize_with_progress(i, c, progress, task) for i, c in tts_chunks]
            )
    else:
        await asyncio.gather(
            *[synthesize_with_progress(i, c, None, None) for i, c in tts_chunks]
        )

    # Assemble raw_results preserving original chunk order
    raw_results: list[tuple[Chunk, bytes | list[bytes] | None]] = []
    for i, chunk in enumerate(chunks):
        if i in synthesis_results:
            raw_results.append((chunk, synthesis_results[i]))
        else:
            raw_results.append((chunk, None))

    # Interactive gacha selection (sequential, after all synthesis)
    gacha_indices = [i for i, (c, _) in enumerate(raw_results) if c.type == "gacha"]
    gacha_count = len(gacha_indices)
    gacha_pos = 0

    final: list[tuple[Chunk, bytes | None]] = []

    for i, (chunk, audio) in enumerate(raw_results):
        if chunk.type != "gacha":
            final.append((chunk, audio))  # type: ignore[arg-type]
            continue

        gacha_pos += 1
        versions: list[bytes] = audio  # type: ignore[assignment]

        tmp_paths = []
        for j, v in enumerate(versions):
            tmp = tempfile.NamedTemporaryFile(
                suffix=f"_gacha_{chunk.index}_opt{j}.wav", delete=False
            )
            tmp.write(v)
            tmp.close()
            tmp_paths.append(Path(tmp.name))

        try:
            selected_idx = select_gacha(
                tmp_paths, text=chunk.text or "", position=(gacha_pos, gacha_count)
            )
        finally:
            for p in tmp_paths:
                if p.exists():
                    os.unlink(p)

        if keep_chunks_dir:
            for j, v in enumerate(versions):
                _write_chunk_to_disk(
                    v, keep_chunks_dir / f"chunk_{chunk.index:03d}_gacha_{chr(65 + j)}.wav"
                )

        final.append((chunk, versions[selected_idx]))

    return final
```

- [ ] **Step 4: Update CLI to pass `max_concurrent` and `keep_chunks_dir`**

In `aidente_voice/cli.py`, replace the `run_pipeline` call and the manual chunks_dir logic:

```python
chunks_dir = None
if keep_chunks:
    chunks_dir = Path("chunks")
    chunks_dir.mkdir(exist_ok=True)

try:
    results = asyncio.run(
        run_pipeline(
            chunks,
            client=client,
            keep_chunks_dir=chunks_dir,
            max_concurrent=max_concurrent,
        )
    )
except RuntimeError as e:
    console.print(f"[red][ERROR][/] {e}")
    raise typer.Exit(code=1)
```

Also remove the manual `for chunk, audio in results:` block that previously wrote chunks to disk — `run_pipeline` now handles this internally.

> **Note on Phase 3 test compatibility:** The Phase 3 orchestrator rewrites the sequential loop into `asyncio.gather`. The Phase 1 unit tests that mock `apply_speed` at `aidente_voice.pipeline.orchestrator.apply_speed` still work because the import path is the same. The test `test_speed_one_skips_postprocess` remains valid — `_synthesize_chunk` still short-circuits when `speed == 1.0`. Run the full test suite after this step to confirm no regressions.

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add aidente_voice/pipeline/orchestrator.py aidente_voice/cli.py tests/pipeline/test_orchestrator.py
git commit -m "feat: Phase 3 concurrent asyncio.gather + Semaphore + rich progress bar"
```

---

## Final Verification

- [ ] **Run full test suite one last time**

```bash
pytest -v --tb=short
```

Expected: all PASSED, no warnings

- [ ] **End-to-end dry-run smoke test**

```bash
cat > /tmp/demo_script.txt << 'EOF'
歡迎來到今天的單元。 <pause=1.0>
接下來我們要講述一個非常關鍵的底層概念。 <speed=0.85>
很多人在這裡會搞錯，<pause=0.5> <gacha=3> <sfx=laugh> 其實這沒有想像中困難。
EOF

aidente-voice generate -i /tmp/demo_script.txt --dry-run
```

> The third line uses `，` (Chinese comma) which does NOT trigger sentence splitting. The text `很多人在這裡會搞錯，` is part of the same line as `其實這沒有想像中困難。` — split only by `<pause>`. Expected:

```
[DRY RUN] Parsed 6 chunks:
  [0] tts    "歡迎來到今天的單元。"
  [1] pause  1.0s
  [2] tts    "接下來我們要講述一個非常關鍵的底層概念。" speed=0.85
  [3] tts    "很多人在這裡會搞錯，"
  [4] pause  0.5s
  [5] gacha  "其實這沒有想像中困難。" n=3
  [6] sfx    laugh fade=0.05
No API calls made.
```

> `很多人在這裡會搞錯，` becomes its own tts chunk because the `<pause=0.5>` tag interrupts it — the text before `<pause>` is tokenized as a separate segment.

- [ ] **Final commit**

```bash
git add -A
git commit -m "feat: aidente-voice-cli complete — Phase 1/2/3 implemented"
```
