from librelyrics.config import get_default_config
from librelyrics.exceptions import NoPluginsFoundError
from librelyrics.models import TrackQuery
from librelyrics.registry import (
    NO_API2_PLUGINS_MESSAGE,
    NO_PLUGINS_INSTALL_MESSAGE,
    dedupe_plugins_by_id,
    get_plugin_by_id,
    get_plugin_for_url,
    no_compatible_plugins_message,
    plugin_import_failure_message,
    validate_plugin,
)
from tests.fakes import ApiV1Plugin, SearchAlpha, UrlPlugin


def test_api_v1_plugin_is_rejected(caplog) -> None:
    with caplog.at_level("WARNING", logger="librelyrics.registry"):
        assert validate_plugin(ApiV1Plugin) is False
    assert "uses API 1" in caplog.text
    assert "requires API 2" in caplog.text


def test_api_v1_import_error_explains_update() -> None:
    err = TypeError(
        "ModuleMeta.__init__() missing 1 required positional argument: 'id'"
    )
    msg = plugin_import_failure_message("spotify", err)
    assert "spotify" in msg
    assert "API 1" in msg
    assert "API 2" in msg
    assert "argument: 'id'" not in msg


def test_other_import_error_keeps_exception_text() -> None:
    msg = plugin_import_failure_message("spotify", RuntimeError("disk full"))
    assert "disk full" in msg
    assert "API 1" not in msg


def test_no_plugins_message_when_none_installed() -> None:
    assert (
        no_compatible_plugins_message(0, import_failures=[], rejected=[])
        == NO_PLUGINS_INSTALL_MESSAGE
    )


def test_no_plugins_message_when_api1_packages_present() -> None:
    assert (
        no_compatible_plugins_message(
            4, import_failures=["spotify"], rejected=[]
        )
        == NO_API2_PLUGINS_MESSAGE
    )
    assert (
        no_compatible_plugins_message(
            1, import_failures=[], rejected=[ApiV1Plugin]
        )
        == NO_API2_PLUGINS_MESSAGE
    )


def test_no_plugins_found_error_uses_api2_message() -> None:
    err = NoPluginsFoundError(NO_API2_PLUGINS_MESSAGE)
    assert "API 1" in str(err)
    assert "API 2" in str(err)


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
