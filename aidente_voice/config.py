"""Centralized config loader for ~/.aidente/config.toml.

Supports voice profiles — named presets combining speaker, language,
acoustic style (instruct), and a human-readable description.

Example config.toml:
    modal_tts_url = "https://....modal.run/custom-voice"
    default_profile = "narrator"
    max_concurrent = 10

    [profiles.narrator]
    speaker = "Ryan"
    language = "Auto"
    instruct = "calm and authoritative, documentary narrator style"
    description = "主旁白"

    [profiles.sakura]
    speaker = "Ono_anna"
    language = "Japanese"
    instruct = "17歲少女，活潑開朗，緊張時聲音會輕微顫抖"
    description = "主角，高中生"
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_CONFIG_PATH = Path.home() / ".aidente" / "config.toml"


@dataclass
class VoiceProfile:
    """A named voice preset.

    speaker   — Qwen3-TTS built-in voice name (used by /custom-voice endpoint).
                Leave empty ("") when using /voice-design endpoint.
    language  — Language hint: Auto, Chinese, English, Japanese, Korean, …
    instruct  — Acoustic style in natural language. Merged with per-sentence
                <style=...> tags at synthesis time.
    description — Free-form human note. Not sent to the API.
    """

    speaker: str = "Ryan"
    language: str = "Auto"
    instruct: str = ""
    description: str = ""


@dataclass
class AidenteConfig:
    """Top-level config loaded from ~/.aidente/config.toml.

    All fields have safe defaults so the tool works without any config file.
    """

    modal_tts_url: str = ""
    default_profile: str = ""
    max_concurrent: int = 10
    sfx_dir: Path = field(default_factory=lambda: Path.home() / ".aidente" / "sfx")
    api_log: Path | None = field(default_factory=lambda: Path.home() / ".aidente" / "api_log.jsonl")
    profiles: dict[str, VoiceProfile] = field(default_factory=dict)


def load_config(path: Path = _DEFAULT_CONFIG_PATH) -> AidenteConfig:
    """Load config from *path*.

    Returns an AidenteConfig with defaults if the file doesn't exist.
    Raises ValueError for schema errors in the TOML file.
    """
    if not path.exists():
        return AidenteConfig()

    with path.open("rb") as f:
        raw = tomllib.load(f)

    profiles: dict[str, VoiceProfile] = {}
    for name, data in raw.get("profiles", {}).items():
        if not isinstance(data, dict):
            raise ValueError(f"config.toml: [profiles.{name}] must be a table")
        profiles[name] = VoiceProfile(
            speaker=data.get("speaker", "Ryan"),
            language=data.get("language", "Auto"),
            instruct=data.get("instruct", ""),
            description=data.get("description", ""),
        )

    api_log_raw = raw.get("api_log")
    if api_log_raw is None:
        api_log: Path | None = Path.home() / ".aidente" / "api_log.jsonl"
    elif api_log_raw == "":
        api_log = None  # empty string → disable logging
    else:
        api_log = Path(api_log_raw).expanduser()

    return AidenteConfig(
        modal_tts_url=raw.get("modal_tts_url", ""),
        default_profile=raw.get("default_profile", ""),
        max_concurrent=int(raw.get("max_concurrent", 10)),
        sfx_dir=Path(raw.get("sfx_dir", Path.home() / ".aidente" / "sfx")).expanduser(),
        api_log=api_log,
        profiles=profiles,
    )
