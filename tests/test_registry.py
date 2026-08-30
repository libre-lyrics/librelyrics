from librelyrics.config import get_default_config
from librelyrics.models import TrackQuery
from librelyrics.registry import (
    dedupe_plugins_by_id,
    get_plugin_by_id,
    get_plugin_for_url,
    validate_plugin,
)
from tests.fakes import ApiV1Plugin, SearchAlpha, UrlPlugin


def test_api_v1_plugin_is_rejected() -> None:
    assert validate_plugin(ApiV1Plugin) is False


def test_api_v2_plugin_with_id_is_accepted() -> None:
    assert validate_plugin(UrlPlugin) is True


def test_dedupe_later_plugin_replaces_same_id() -> None:
    class OtherUrl(UrlPlugin):
        pass

    merged = dedupe_plugins_by_id([UrlPlugin, OtherUrl])
    assert merged == [OtherUrl]


def test_dedupe_sorts_by_id() -> None:
    merged = dedupe_plugins_by_id([UrlPlugin, SearchAlpha])
    assert [p.META.id for p in merged] == ["alpha", "urlplug"]


def test_get_plugin_for_url_uses_regex_not_search_match() -> None:
    plugins = [SearchAlpha, UrlPlugin]
    found = get_plugin_for_url(
        plugins,
        TrackQuery(
            url="https://example.com/track/1",
            artist="A",
            title="T",
        ),
    )
    assert found is UrlPlugin


def test_get_plugin_for_url_none_without_url() -> None:
    assert get_plugin_for_url([UrlPlugin], TrackQuery(artist="A", title="T")) is None


def test_get_plugin_by_id() -> None:
    assert get_plugin_by_id([UrlPlugin, SearchAlpha], "alpha") is SearchAlpha
    assert get_plugin_by_id([UrlPlugin], "missing") is None


def test_default_config_has_search_keys() -> None:
    config = get_default_config()
    assert "synced_lyrics" not in config
    assert "enhanced_lrc" not in config
    assert "plugin_directories" not in config
    assert config["preferred_lyrics_order"] == ["RICH", "SYNCED", "UNSYNCED"]
    assert config["search_priority"] == []
    assert config["max_search_attempts"] == 5
    assert config["max_concurrent_tracks"] == 4
    assert config["plugins"] == {}
