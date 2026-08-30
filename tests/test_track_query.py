from dataclasses import replace

import pytest

from librelyrics.models import TrackQuery


def test_track_query_defaults_are_none() -> None:
    query = TrackQuery()
    assert query.url is None
    assert query.artist is None
    assert query.title is None
    assert query.album is None
    assert query.duration_ms is None


def test_track_query_replace_does_not_mutate() -> None:
    original = TrackQuery(url="https://example.com/track/1")
    updated = replace(original, artist="A", title="T")
    assert original.artist is None
    assert updated.artist == "A"
    assert updated.title == "T"
    assert updated.url == original.url


def test_cli_fields_override_resolved_fields() -> None:
    resolved = TrackQuery(
        url="https://example.com/track/1",
        artist="Resolved Artist",
        title="Resolved Title",
        album="Resolved Album",
        duration_ms=1000,
    )
    merged = replace(resolved, artist="CLI Artist", title="CLI Title")
    assert merged.artist == "CLI Artist"
    assert merged.title == "CLI Title"
    assert merged.album == "Resolved Album"
    assert merged.duration_ms == 1000


def test_frozen_query_rejects_mutation() -> None:
    query = TrackQuery(title="T")
    with pytest.raises(AttributeError):
        query.title = "other"  # type: ignore[misc]
