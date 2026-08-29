from pathlib import Path

from librelyrics.config import get_default_config
from librelyrics.models import TrackQuery
from librelyrics.registry import (
    discover_directory_plugins,
    get_plugin_by_id,
    get_plugin_for_url,
    merge_plugins,
    validate_plugin,
)
from tests.fakes import ApiV1Plugin, SearchAlpha, UrlPlugin


def test_api_v1_plugin_is_rejected() -> None:
    assert validate_plugin(ApiV1Plugin) is False


def test_api_v2_plugin_with_id_is_accepted() -> None:
    assert validate_plugin(UrlPlugin) is True


def test_merge_directory_replaces_same_id() -> None:
    class DirUrl(UrlPlugin):
        pass

    merged = merge_plugins([UrlPlugin], [DirUrl])
    assert merged == [DirUrl]


def test_merge_sorts_by_id() -> None:
    merged = merge_plugins([UrlPlugin, SearchAlpha], [])
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


def test_discover_directory_plugins(tmp_path: Path) -> None:
    plugin_file = tmp_path / "dirplug.py"
    plugin_file.write_text(
        """
import re
from librelyrics.models import LyricsLine, LyricsResponse
from librelyrics.modules.base import (
    LIBRELYRICS_API_VERSION, LyricsModule, ModuleMeta,
)

class DirPlug(LyricsModule):
    META = ModuleMeta(id="dirplug", name="DirPlug", regex=re.compile(r"dir\\\\.example/"))
    LIBRELYRICS_API_VERSION = LIBRELYRICS_API_VERSION

    def fetch(self):
        return LyricsResponse(
            title="T", artist="A", lyrics=[LyricsLine(text="x")], source="DirPlug",
        )
"""
    )
    found = discover_directory_plugins([tmp_path])
    assert len(found) == 1
    assert found[0].META.id == "dirplug"
    assert validate_plugin(found[0])


def test_default_config_has_search_keys() -> None:
    config = get_default_config()
    assert "synced_lyrics" not in config
    assert config["preferred_lyrics_order"] == ["RICH", "SYNCED", "UNSYNCED"]
    assert config["search_priority"] == []
    assert config["max_search_attempts"] == 5
    assert config["plugin_directories"] == []
    assert config["max_concurrent_tracks"] == 4
