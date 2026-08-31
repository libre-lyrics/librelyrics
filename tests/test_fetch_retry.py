"""Tests for fetch_with_retry behavior."""
from __future__ import annotations

import pytest

from librelyrics.exceptions import LyricsNotFound, RateLimitError
from librelyrics.models import LyricsResponse, TrackQuery
from librelyrics.modules.base import LyricsModule, ModuleMeta
from tests.fakes import _response


class RetryPlugin(LyricsModule):
    META = ModuleMeta(id="retryplug", name="RetryPlug")
    LIBRELYRICS_API_VERSION = 2
    MAX_RETRIES = 3
    RETRY_BACKOFF = 0.0

    attempts = 0

    def fetch(self) -> LyricsResponse:
        RetryPlugin.attempts += 1
        if RetryPlugin.attempts < 3:
            raise RateLimitError("rate limited")
        return _response(source="RetryPlug", query=self.query)


class NoRetryPlugin(LyricsModule):
    META = ModuleMeta(id="noretry", name="NoRetry")
    LIBRELYRICS_API_VERSION = 2

    def fetch(self) -> LyricsResponse:
        raise LyricsNotFound("not found")


def test_fetch_with_retry_on_rate_limit() -> None:
    RetryPlugin.attempts = 0
    plugin = RetryPlugin(TrackQuery(artist="A", title="T"), {})
    result = plugin.fetch_with_retry()
    assert result.source == "RetryPlug"
    assert RetryPlugin.attempts == 3


def test_fetch_with_retry_does_not_retry_lyrics_not_found() -> None:
    plugin = NoRetryPlugin(TrackQuery(artist="A", title="T"), {})
    with pytest.raises(LyricsNotFound):
        plugin.fetch_with_retry()
