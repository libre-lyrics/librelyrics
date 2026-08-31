"""Fake plugins for unit tests. These are not product sources."""
from __future__ import annotations

import re
from dataclasses import replace

from librelyrics.exceptions import LyricsNotFound
from librelyrics.models import LyricsLine, LyricsResponse, TrackQuery
from librelyrics.modules.base import (
    LIBRELYRICS_API_VERSION,
    LyricsModule,
    LyricsType,
    ModuleCapability,
    ModuleMeta,
)


def _response(
    *,
    source: str,
    query: TrackQuery,
    synced: bool = False,
    rich_synced: bool = False,
    title: str | None = None,
) -> LyricsResponse:
    return LyricsResponse(
        title=title or query.title or "Track",
        artist=query.artist or "Artist",
        album=query.album,
        lyrics=[LyricsLine(text="line one", start_ms=0 if synced or rich_synced else None)],
        source=source,
        synced=synced or rich_synced,
        rich_synced=rich_synced,
        duration_ms=query.duration_ms,
    )


class UrlPlugin(LyricsModule):
    """URL plugin that can resolve and list tracks."""

    META = ModuleMeta(
        id="urlplug",
        name="UrlPlug",
        regex=re.compile(r"example\.com/(track|album|playlist)/"),
        lyrics_types=frozenset({LyricsType.PLAIN, LyricsType.SYNCED}),
        capabilities=frozenset({
            ModuleCapability.SINGLE_TRACK,
            ModuleCapability.ALBUM,
            ModuleCapability.PLAYLIST,
            ModuleCapability.RESOLVE,
            ModuleCapability.SEARCH,
        }),
    )
    LIBRELYRICS_API_VERSION = LIBRELYRICS_API_VERSION

    def resolve(self) -> TrackQuery:
        return replace(
            self.query,
            artist=self.query.artist or "Resolved Artist",
            title=self.query.title or "Resolved Title",
            album=self.query.album or "Resolved Album",
            duration_ms=self.query.duration_ms or 180000,
        )

    def list_tracks(self) -> list[TrackQuery]:
        base = self.resolve()
        return [
            replace(base, url="https://example.com/track/1", title="One"),
            replace(base, url="https://example.com/track/2", title="Two"),
        ]

    def fetch(self) -> LyricsResponse:
        if self.query.title == "missing":
            raise LyricsNotFound("no lyrics")
        return _response(source=self.META.name, query=self.query, synced=True)

    @classmethod
    def matches(cls, query: TrackQuery) -> bool:
        if query.url:
            return super().matches(query)
        return bool(query.artist and query.title)

    @classmethod
    def classify_url(cls, url: str | None) -> str | None:
        if not url:
            return None
        match = cls.META.regex.search(url)
        if not match:
            return None
        return match.group(1)


class SearchAlpha(LyricsModule):
    META = ModuleMeta(
        id="alpha",
        name="Alpha",
        lyrics_types=frozenset({LyricsType.SYNCED, LyricsType.RICH_SYNCED}),
        capabilities=frozenset({
            ModuleCapability.SINGLE_TRACK,
            ModuleCapability.SEARCH,
        }),
    )
    LIBRELYRICS_API_VERSION = LIBRELYRICS_API_VERSION

    @classmethod
    def matches(cls, query: TrackQuery) -> bool:
        return bool(query.artist and query.title)

    def fetch(self) -> LyricsResponse:
        return _response(
            source=self.META.name,
            query=self.query,
            synced=True,
            rich_synced=True,
        )


class SearchBeta(LyricsModule):
    META = ModuleMeta(
        id="beta",
        name="Beta",
        lyrics_types=frozenset({LyricsType.PLAIN, LyricsType.SYNCED}),
        capabilities=frozenset({
            ModuleCapability.SINGLE_TRACK,
            ModuleCapability.SEARCH,
        }),
    )
    LIBRELYRICS_API_VERSION = LIBRELYRICS_API_VERSION

    @classmethod
    def matches(cls, query: TrackQuery) -> bool:
        return bool(query.artist and query.title)

    def fetch(self) -> LyricsResponse:
        return _response(source=self.META.name, query=self.query, synced=True)


class PlainOnly(LyricsModule):
    META = ModuleMeta(
        id="plainonly",
        name="PlainOnly",
        lyrics_types=frozenset({LyricsType.PLAIN}),
        capabilities=frozenset({
            ModuleCapability.SINGLE_TRACK,
            ModuleCapability.SEARCH,
        }),
    )
    LIBRELYRICS_API_VERSION = LIBRELYRICS_API_VERSION

    @classmethod
    def matches(cls, query: TrackQuery) -> bool:
        return bool(query.artist and query.title)

    def fetch(self) -> LyricsResponse:
        return _response(source=self.META.name, query=self.query, synced=False)


class ApiV1Plugin(LyricsModule):
    META = ModuleMeta(
        id="oldplug",
        name="OldPlug",
        regex=re.compile(r"old\.example/"),
    )
    LIBRELYRICS_API_VERSION = 1

    def fetch(self) -> LyricsResponse:
        return _response(source=self.META.name, query=self.query)


class NoIdPlugin(LyricsModule):
    """Invalid META is set in tests that skip ModuleMeta validation at class body."""

    LIBRELYRICS_API_VERSION = LIBRELYRICS_API_VERSION

    def fetch(self) -> LyricsResponse:
        return _response(source="noid", query=self.query)


class AlbumFetchOnly(LyricsModule):
    """Album URL plugin with fetch_album but no list_tracks (typical API 1 port)."""

    META = ModuleMeta(
        id="albumonly",
        name="AlbumOnly",
        regex=re.compile(r"albumonly\.example/album/"),
        capabilities=frozenset({
            ModuleCapability.SINGLE_TRACK,
            ModuleCapability.ALBUM,
        }),
    )
    LIBRELYRICS_API_VERSION = LIBRELYRICS_API_VERSION

    def fetch(self) -> LyricsResponse:
        return _response(source="AlbumOnly-fetch", query=self.query)

    def fetch_album(self) -> list[LyricsResponse]:
        return [_response(
            source="AlbumOnly-album",
            query=self.query,
            title="Bulk",
        )]
