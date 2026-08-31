"""Tests for core helper functions."""
from __future__ import annotations

from librelyrics.core import rename_using_format


def test_rename_using_format_substitutes_known_keys() -> None:
    result = rename_using_format(
        "{track_number}. {name}",
        {"track_number": "01", "name": "Song"},
    )
    assert result == "01. Song"


def test_rename_using_format_unknown_placeholder_empty() -> None:
    result = rename_using_format("{missing}", {"name": "Song"})
    assert result == ""


def test_rename_using_format_strips_invalid_path_chars() -> None:
    result = rename_using_format("{name}", {"name": "Bad:Title?"})
    assert ":" not in result
    assert "?" not in result


def test_rename_using_format_empty_track_number() -> None:
    result = rename_using_format(
        "{track_number}. {name}",
        {"track_number": "", "name": "Song"},
    )
    assert result == ". Song"
