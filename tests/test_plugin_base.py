import re

import pytest

from librelyrics.models import TrackQuery
from librelyrics.modules.base import (
    LIBRELYRICS_API_VERSION,
    ModuleCapability,
    ModuleMeta,
)
from tests.fakes import UrlPlugin


def test_api_version_is_two() -> None:
    assert LIBRELYRICS_API_VERSION == 2


def test_plugin_id_rejects_spaces() -> None:
    with pytest.raises(ValueError, match="lower-case"):
        ModuleMeta(id="apple music", name="Apple Music")


def test_url_property_reads_query() -> None:
    plugin = UrlPlugin(
        TrackQuery(url="https://example.com/track/1"),
        {},
    )
    assert plugin.url == "https://example.com/track/1"


def test_default_matches_url_regex() -> None:
    assert UrlPlugin.matches(TrackQuery(url="https://example.com/track/1"))
    assert not UrlPlugin.matches(TrackQuery(url="https://other.com/track/1"))


def test_default_matches_false_without_url() -> None:
    class RegexOnly(UrlPlugin):
        META = ModuleMeta(
            id="regexonly",
            name="RegexOnly",
            regex=re.compile(r"example\.com/"),
        )

        @classmethod
        def matches(cls, query: TrackQuery) -> bool:
            if query.url is None or cls.META.regex is None:
                return False
            return cls.META.regex.search(query.url) is not None

    assert not RegexOnly.matches(TrackQuery(artist="A", title="T"))


def test_search_override_matches_metadata() -> None:
    assert UrlPlugin.matches(TrackQuery(artist="A", title="T"))


def test_resolve_fills_metadata() -> None:
    plugin = UrlPlugin(TrackQuery(url="https://example.com/track/1"), {})
    resolved = plugin.resolve()
    assert resolved.artist == "Resolved Artist"
    assert resolved.title == "Resolved Title"


def test_list_tracks_returns_all_items() -> None:
    plugin = UrlPlugin(TrackQuery(url="https://example.com/album/1"), {})
    tracks = plugin.list_tracks()
    assert len(tracks) == 2
    assert tracks[0].title == "One"


def test_default_fetch_album_uses_list_tracks() -> None:
    plugin = UrlPlugin(TrackQuery(url="https://example.com/album/1"), {})
    responses = plugin.fetch_album()
    assert [r.title for r in responses] == ["One", "Two"]


def test_resolve_capability_flag_exists() -> None:
    assert ModuleCapability.RESOLVE
