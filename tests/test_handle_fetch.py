"""Tests for handle_fetch validation and exit codes."""
from __future__ import annotations

from pathlib import Path

import pytest

from librelyrics.cli import handle_fetch
from librelyrics.config import ConfigManager, get_default_config
from librelyrics.core import LibreLyrics
from tests.fakes import UrlPlugin


def _patch_librelyrics(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Inject fake plugins and isolated config for handle_fetch tests."""

    def fake_init(self, config=None, verbose=False, plugins=None):
        data = get_default_config()
        data["download_path"] = str(tmp_path)
        data["search_priority"] = []
        self.config_manager = ConfigManager(config=data)
        self.plugins = plugins if plugins is not None else [UrlPlugin]
        self.config_manager.merge_plugin_defaults(self.plugins)

    monkeypatch.setattr(LibreLyrics, "__init__", fake_init)


def test_handle_fetch_rejects_direct_and_from(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_librelyrics(monkeypatch, tmp_path)
    code = handle_fetch(
        "https://example.com/track/1",
        direct=True,
        from_plugin="alpha",
        show_logo=False,
    )
    assert code == 1


def test_handle_fetch_rejects_artist_without_title(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _patch_librelyrics(monkeypatch, tmp_path)
    code = handle_fetch("https://example.com/track/1", artist="Only", show_logo=False)
    assert code == 1


def test_handle_fetch_single_track_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _patch_librelyrics(monkeypatch, tmp_path)
    code = handle_fetch(
        "https://example.com/track/1",
        show_logo=False,
    )
    assert code == 0
    assert list(tmp_path.glob("*.lrc"))


def test_handle_fetch_batch_partial_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _patch_librelyrics(monkeypatch, tmp_path)
    code = handle_fetch(
        "https://example.com/album/1",
        show_logo=False,
    )
    assert code == 0
    assert len(list(tmp_path.glob("*.lrc"))) >= 1


def test_handle_fetch_unknown_url_returns_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _patch_librelyrics(monkeypatch, tmp_path)
    code = handle_fetch("https://unknown.example/track/1", show_logo=False)
    assert code == 1


def test_handle_fetch_local_directory_returns_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _patch_librelyrics(monkeypatch, tmp_path)
    music_dir = tmp_path / "music"
    music_dir.mkdir()
    code = handle_fetch(str(music_dir), show_logo=False)
    assert code == 1


def test_handle_fetch_skip_only_is_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    _patch_librelyrics(monkeypatch, tmp_path)
    assert handle_fetch("https://example.com/track/1", show_logo=False) == 0
    assert handle_fetch("https://example.com/track/1", show_logo=False) == 0
