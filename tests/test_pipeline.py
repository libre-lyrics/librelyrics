import pytest

from librelyrics.config import ConfigManager, get_default_config
from librelyrics.exceptions import (
    ConfigurationError,
    DirectModeError,
    LyricsNotFound,
    NoMatchingModuleError,
    ProviderError,
    UnknownPluginError,
)
from librelyrics.models import TrackQuery
from librelyrics.pipeline import (
    _search_priority_ids,
    fetch_batch_query,
    fetch_query,
    normalize_failure_reason,
)
from librelyrics.quality import is_good_enough, plugin_can_satisfy
from tests.fakes import AlbumFetchOnly, PlainOnly, SearchAlpha, SearchBeta, UrlPlugin


def _cm(**overrides) -> ConfigManager:
    data = get_default_config()
    data.update(overrides)
    return ConfigManager(config=data)


PLUGINS = [UrlPlugin, SearchAlpha, SearchBeta, PlainOnly]
URL = "https://example.com/track/1"


def test_empty_priority_url_uses_url_plugin_only() -> None:
    result = fetch_query(TrackQuery(url=URL), PLUGINS, _cm(search_priority=[]))
    assert result.source == "UrlPlug"


def test_empty_priority_metadata_uses_first_search_id() -> None:
    result = fetch_query(
        TrackQuery(artist="A", title="T"),
        PLUGINS,
        _cm(search_priority=[]),
    )
    assert result.source == "Alpha"


def test_priority_resolves_then_uses_list_not_url_host() -> None:
    result = fetch_query(
        TrackQuery(url=URL),
        PLUGINS,
        _cm(search_priority=["alpha"]),
    )
    assert result.source == "Alpha"
    assert result.artist == "Resolved Artist"


def test_cli_overrides_win_after_resolve() -> None:
    result = fetch_query(
        TrackQuery(url=URL, artist="CLI Artist", title="CLI Title"),
        PLUGINS,
        _cm(search_priority=["alpha"]),
    )
    assert result.artist == "CLI Artist"
    assert result.title == "CLI Title"


def test_prefilter_skips_plain_when_rich_required() -> None:
    assert not plugin_can_satisfy(PlainOnly, ["RICH"])
    result = fetch_query(
        TrackQuery(artist="A", title="T"),
        [PlainOnly, SearchAlpha],
        _cm(search_priority=["plainonly", "alpha"], preferred_lyrics_order=["RICH"]),
    )
    assert result.source == "Alpha"


def test_stop_at_rich_when_first_token_is_rich() -> None:
    result = fetch_query(
        TrackQuery(artist="A", title="T"),
        PLUGINS,
        _cm(search_priority=["alpha", "beta"], preferred_lyrics_order=["RICH"]),
    )
    assert result.source == "Alpha"
    assert result.rich_synced


def test_fallback_when_only_synced_available() -> None:
    result = fetch_query(
        TrackQuery(artist="A", title="T"),
        [SearchBeta],
        _cm(search_priority=["beta"], preferred_lyrics_order=["RICH", "SYNCED"]),
    )
    assert result.source == "Beta"
    assert result.synced
    assert not result.rich_synced


def test_max_search_attempts_cap(caplog) -> None:
    calls: list[str] = []

    class CountBeta(SearchBeta):
        def fetch(self):
            calls.append("beta")
            return super().fetch()

    class CountAlpha(SearchAlpha):
        def fetch(self):
            calls.append("alpha")
            return super().fetch()

    with caplog.at_level("WARNING", logger="librelyrics.pipeline"):
        fetch_query(
            TrackQuery(artist="A", title="T"),
            [CountAlpha, CountBeta],
            _cm(
                search_priority=["beta", "alpha"],
                preferred_lyrics_order=["RICH", "SYNCED"],
                max_search_attempts=1,
            ),
        )
    assert calls == ["beta"]
    assert "never tried: alpha" in caplog.text


def test_direct_does_not_call_search_plugins() -> None:
    class Boom(SearchAlpha):
        def fetch(self):
            raise AssertionError("search must not run in --direct")

    result = fetch_query(
        TrackQuery(url=URL),
        [UrlPlugin, Boom],
        _cm(search_priority=["alpha"]),
        direct=True,
    )
    assert result.source == "UrlPlug"


def test_direct_without_url_errors() -> None:
    try:
        fetch_query(TrackQuery(artist="A", title="T"), PLUGINS, _cm(), direct=True)
        raise AssertionError("expected DirectModeError")
    except DirectModeError:
        pass


def test_from_missing_plugin_errors() -> None:
    try:
        fetch_query(TrackQuery(url=URL), PLUGINS, _cm(), from_plugin="missing")
        raise AssertionError("expected UnknownPluginError")
    except UnknownPluginError:
        pass


def test_unknown_id_in_priority_is_skipped() -> None:
    result = fetch_query(
        TrackQuery(artist="A", title="T"),
        PLUGINS,
        _cm(search_priority=["nope", "alpha"]),
    )
    assert result.source == "Alpha"


def test_search_uses_primary_artist_and_short_title() -> None:
    seen: list[tuple[str | None, str | None]] = []

    class Picky(SearchAlpha):
        def fetch(self):
            seen.append((self.query.artist, self.query.title))
            if self.query.artist == "Aksomaniac" and self.query.title == "Amsham":
                return super().fetch()
            raise LyricsNotFound("no match")

    result = fetch_query(
        TrackQuery(
            artist="Aksomaniac, M.H.R, Bhumi, Circle Tone",
            title="Amsham - അംശം",
        ),
        [Picky],
        _cm(search_priority=["alpha"]),
    )
    assert result.source == "Alpha"
    assert seen[0] == ("Aksomaniac", "Amsham")


def test_list_tracks_then_per_track_pipeline() -> None:
    responses = fetch_batch_query(
        TrackQuery(url="https://example.com/album/1"),
        PLUGINS,
        _cm(search_priority=["alpha"]),
    )
    assert len(responses) == 2
    assert all(r.source == "Alpha" for r in responses)
    assert [r.title for r in responses] == ["One", "Two"]


def test_priority_album_does_not_use_url_fetch_album() -> None:
    try:
        fetch_batch_query(
            TrackQuery(url="https://albumonly.example/album/1"),
            [AlbumFetchOnly, SearchAlpha],
            _cm(search_priority=["alpha"]),
        )
        raise AssertionError("expected ConfigurationError")
    except ConfigurationError as exc:
        assert "list_tracks" in str(exc)
        assert "search_priority" in str(exc)


def test_empty_priority_album_uses_fetch_album() -> None:
    responses = fetch_batch_query(
        TrackQuery(url="https://albumonly.example/album/1"),
        [AlbumFetchOnly],
        _cm(search_priority=[]),
    )
    assert [r.source for r in responses] == ["AlbumOnly-album"]


def test_direct_batch_stays_on_url_plugin() -> None:
    responses = fetch_batch_query(
        TrackQuery(url="https://example.com/album/1"),
        PLUGINS,
        _cm(search_priority=["alpha"]),
        direct=True,
    )
    assert all(r.source == "UrlPlug" for r in responses)


def test_good_enough_rich() -> None:
    from tests.fakes import _response

    rich = _response(
        source="x",
        query=TrackQuery(title="T", artist="A"),
        rich_synced=True,
    )
    assert is_good_enough(rich, ["RICH"])


def test_search_not_found_raises() -> None:
    class Empty(SearchAlpha):
        def fetch(self):
            raise LyricsNotFound("none")

    try:
        fetch_query(
            TrackQuery(artist="A", title="T"),
            [Empty],
            _cm(search_priority=["alpha"]),
        )
        raise AssertionError("expected LyricsNotFound")
    except LyricsNotFound:
        pass


def test_normalize_failure_reason_spotify_429() -> None:
    exc = ProviderError("Spotify search failed: HTTP 429")
    assert normalize_failure_reason(exc) == "Spotify HTTP 429"


def test_normalize_failure_reason_lyrics_not_found() -> None:
    assert normalize_failure_reason(LyricsNotFound("none")) == "Lyrics not found"


def test_batch_on_track_callback_reports_failures() -> None:
    events: list[tuple[str | None, str | None]] = []

    class FailSecond(SearchAlpha):
        def fetch(self):
            if self.query.title == "Two":
                raise ProviderError("Spotify search failed: HTTP 429")
            return super().fetch()

    def on_track(track: TrackQuery, response, reason) -> None:
        events.append((track.title, reason))

    responses = fetch_batch_query(
        TrackQuery(url="https://example.com/album/1"),
        [UrlPlugin, FailSecond],
        _cm(search_priority=["alpha"]),
        on_track=on_track,
    )
    assert len(responses) == 1
    assert responses[0].title == "One"
    assert ("One", None) in events
    assert ("Two", "Spotify HTTP 429") in events


def test_fetch_batch_on_phase_reports_listing_and_fetching() -> None:
    phases: list[str] = []

    fetch_batch_query(
        TrackQuery(url="https://example.com/album/1"),
        [UrlPlugin],
        _cm(search_priority=["urlplug"]),
        on_phase=phases.append,
    )
    assert phases == ["listing", "fetching"]


def test_unknown_url_with_search_priority_raises_no_matching() -> None:
    with pytest.raises(NoMatchingModuleError):
        fetch_query(
            TrackQuery(url="https://example.com/foo"),
            PLUGINS,
            _cm(search_priority=["alpha"]),
        )


def test_search_priority_accepts_comma_separated_string() -> None:
    cm = _cm(search_priority="alpha,beta")
    assert _search_priority_ids(cm) == ["alpha", "beta"]


def test_search_priority_accepts_list_and_whitespace() -> None:
    cm = _cm(search_priority=[" alpha ", "", "beta"])
    assert _search_priority_ids(cm) == ["alpha", "beta"]


def test_provider_specific_url_shapes_classify() -> None:
    """Provider-specific URL shapes map to track/album/playlist correctly."""
    import re

    from librelyrics.modules.base import LyricsModule, ModuleMeta

    class ShapePlugin(LyricsModule):
        META = ModuleMeta(
            id="shapeplug",
            name="ShapePlug",
            regex=re.compile(r"(music\.apple\.com|open\.spotify\.com)"),
        )

        def fetch(self):  # pragma: no cover - never called
            raise AssertionError("fetch must not run")

    # Apple Music links a track "?" inside an album URL via ?i=<trackId>
    assert ShapePlugin.classify_url(
        "https://music.apple.com/us/album/thinking-out-loud/1440871909?i=1440872388"
    ) == "track"
    assert ShapePlugin.classify_url(
        "https://music.apple.com/us/album/x-deluxe-edition/1440871909"
    ) == "album"
    assert ShapePlugin.classify_url("https://open.spotify.com/track/abc") == "track"
    assert ShapePlugin.classify_url("https://open.spotify.com/album/abc") == "album"
    assert ShapePlugin.classify_url("https://open.spotify.com/playlist/abc") == "playlist"


def test_search_keeps_resolved_album_on_response() -> None:
    result = fetch_query(
        TrackQuery(url=URL),
        PLUGINS,
        _cm(search_priority=["alpha"]),
    )
    assert result.album == "Resolved Album"
