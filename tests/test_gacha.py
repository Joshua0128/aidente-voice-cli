"""Tests for gacha selector."""

from unittest.mock import patch
from pathlib import Path

from aidente_voice.gacha import GACHA_SEEDS, select_gacha


def test_gacha_seeds_count():
    assert len(GACHA_SEEDS) == 8


def test_gacha_seeds_unique():
    assert len(set(GACHA_SEEDS)) == len(GACHA_SEEDS)


def test_select_gacha_returns_valid_index(tmp_path):
    paths = [tmp_path / f"v{i}.wav" for i in range(3)]
    for p in paths:
        p.touch()

    keys = iter(['1', '\r'])
    with patch('aidente_voice.gacha._get_key', side_effect=keys), \
         patch('subprocess.run'):
        result = select_gacha(paths, "hello", 0)
    assert result == 0  # key '1' → index 0


def test_select_gacha_q_returns_zero(tmp_path):
    paths = [tmp_path / f"v{i}.wav" for i in range(2)]
    for p in paths:
        p.touch()

    with patch('aidente_voice.gacha._get_key', return_value='q'), \
         patch('subprocess.run'):
        result = select_gacha(paths, "hello", 0)
    assert result == 0
