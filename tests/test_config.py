"""Tests for aidente_voice.config module."""
import pytest
from pathlib import Path
from aidente_voice.config import load_config, AidenteConfig, VoiceProfile


def _write_toml(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(content, encoding="utf-8")
    return p


def test_load_config_missing_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert isinstance(cfg, AidenteConfig)
    assert cfg.modal_tts_url == ""
    assert cfg.default_profile == ""
    assert cfg.max_concurrent == 10
    assert cfg.profiles == {}


def test_load_config_global_settings(tmp_path):
    p = _write_toml(tmp_path, """
modal_tts_url = "https://example.modal.run/custom-voice"
default_profile = "narrator"
max_concurrent = 5
""")
    cfg = load_config(p)
    assert cfg.modal_tts_url == "https://example.modal.run/custom-voice"
    assert cfg.default_profile == "narrator"
    assert cfg.max_concurrent == 5


def test_load_config_profiles(tmp_path):
    p = _write_toml(tmp_path, """
[profiles.narrator]
speaker = "Ryan"
language = "English"
instruct = "calm and authoritative"
description = "main narrator"

[profiles.sakura]
speaker = "Ono_anna"
language = "Japanese"
instruct = "17歲少女，活潑開朗"
""")
    cfg = load_config(p)
    assert "narrator" in cfg.profiles
    assert "sakura" in cfg.profiles

    narrator = cfg.profiles["narrator"]
    assert narrator.speaker == "Ryan"
    assert narrator.language == "English"
    assert narrator.instruct == "calm and authoritative"
    assert narrator.description == "main narrator"

    sakura = cfg.profiles["sakura"]
    assert sakura.speaker == "Ono_anna"
    assert sakura.language == "Japanese"
    assert sakura.description == ""  # optional field, defaults to ""


def test_load_config_profile_defaults(tmp_path):
    """Profile with only speaker set gets defaults for other fields."""
    p = _write_toml(tmp_path, """
[profiles.minimal]
speaker = "Dylan"
""")
    cfg = load_config(p)
    p = cfg.profiles["minimal"]
    assert p.speaker == "Dylan"
    assert p.language == "Auto"
    assert p.instruct == ""
    assert p.description == ""


def test_load_config_api_log_empty_string_disables(tmp_path):
    """Setting api_log = '' in TOML disables logging."""
    p = _write_toml(tmp_path, 'api_log = ""')
    cfg = load_config(p)
    assert cfg.api_log is None


def test_load_config_api_log_custom_path(tmp_path):
    log_path = tmp_path / "my_log.jsonl"
    p = _write_toml(tmp_path, f'api_log = "{log_path}"')
    cfg = load_config(p)
    assert cfg.api_log == log_path


def test_load_config_sfx_dir(tmp_path):
    sfx = tmp_path / "sounds"
    p = _write_toml(tmp_path, f'sfx_dir = "{sfx}"')
    cfg = load_config(p)
    assert cfg.sfx_dir == sfx
