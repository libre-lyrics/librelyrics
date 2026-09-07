"""Tests for concurrent batch fetch error handling."""
from __future__ import annotations

from librelyrics.config import ConfigManager, get_default_config
from librelyrics.exceptions import ConfigurationError
from librelyrics.models import LyricsResponse, TrackQuery
from librelyrics.modules.base import (
    LIBRELYRICS_API_VERSION,
    LyricsModule,
    ModuleCapability,
    ModuleMeta,
)
from librelyrics.pipeline import fetch_batch_query
from tests.fakes import UrlPlugin, _response


class ConfigErrorSearch(LyricsModule):
    """Search plugin that raises ConfigurationError for specific titles."""

    META = ModuleMeta(
        id="cfgerr",
        name="CfgErr",
        capabilities=frozenset({
            ModuleCapability.SINGLE_TRACK,
            ModuleCapability.SEARCH,
        }),
    )
    LIBRELYRICS_API_VERSION = LIBRELYRICS_API_VERSION

    def fetch(self) -> LyricsResponse:
        if self.query.title == "Two":
            raise ConfigurationError("bad config for track two")
        return _response(source="CfgErr", query=self.query, synced=True)


def _cm(**overrides) -> ConfigManager:
    data = get_default_config()
    data.update(overrides)
    return ConfigManager(config=data)


def test_concurrent_batch_survives_configuration_error() -> None:
    """Per-track ConfigurationError should not abort the entire batch."""
    plugins = [UrlPlugin, ConfigErrorSearch]
    cm = _cm(search_priority=["cfgerr"])
    url = "https://example.com/album/1"
    failures: list[tuple[str, str]] = []

    def on_track(track, response, reason) -> None:
        if reason:
            failures.append((track.title or "?", reason))

    results = fetch_batch_query(
        TrackQuery(url=url),
        plugins,
        cm,
        on_track=on_track,
    )
    assert len(results) == 1
    assert results[0].title == "One"
    assert len(failures) == 1
    assert failures[0][0] == "Two"
