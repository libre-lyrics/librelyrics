"""Tests for configuration management."""
from __future__ import annotations

from pathlib import Path

import pytest

from librelyrics.config import ConfigManager, as_list, get_default_config
from librelyrics.exceptions import CorruptedConfig
from tests.fakes import SearchAlpha


def test_as_list_normalizes_none_list_and_string() -> None:
    assert as_list(None) == []
    assert as_list("alpha,beta") == ["alpha", "beta"]
    assert as_list([" alpha ", "", "beta"]) == ["alpha", "beta"]


def test_get_default_config_has_expected_keys() -> None:
    config = get_default_config()
    assert config["download_path"] == "downloads"
    assert config["search_priority"] == []
    assert "plugins" in config


def test_config_manager_with_inline_config(tmp_path: Path) -> None:
    custom_path = tmp_path / "config.json"
    data = get_default_config()
    data["download_path"] = "custom"
    cm = ConfigManager(config=data, config_path=custom_path)
    assert cm.get("download_path") == "custom"


def test_config_save_and_reload(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    cm = ConfigManager(config=get_default_config(), config_path=config_path)
    cm.set("download_path", "saved")
    cm.save()
    cm2 = ConfigManager(config_path=config_path)
    assert cm2.get("download_path") == "saved"


def test_corrupted_config_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(CorruptedConfig):
        ConfigManager(config_path=config_path)


def test_for_plugin_merges_defaults_and_stored_by_name(tmp_path: Path) -> None:
    data = get_default_config()
    data["plugins"] = {"alpha": {"custom_key": "value"}}
    cm = ConfigManager(config=data, config_path=tmp_path / "c.json")
    merged = cm.for_plugin(SearchAlpha)
    assert merged.get("custom_key") == "value"


def test_for_plugin_falls_back_to_id_key(tmp_path: Path) -> None:
    data = get_default_config()
    data["plugins"] = {"alpha": {"from_id": True}}
    cm = ConfigManager(config=data, config_path=tmp_path / "c.json")
    merged = cm.for_plugin(SearchAlpha)
    assert merged.get("from_id") is True


def test_merge_plugin_defaults_adds_missing_sections(tmp_path: Path) -> None:
    data = get_default_config()
    cm = ConfigManager(config=data, config_path=tmp_path / "c.json")

    class WithDefaults(SearchAlpha):
        @staticmethod
        def default_config() -> dict:
            return {"api_key": "default"}

    modified = cm.merge_plugin_defaults([WithDefaults])
    assert modified
    assert cm.raw["plugins"]["alpha"]["api_key"] == "default"


def test_validate_plugin_configs_raises_on_invalid(tmp_path: Path) -> None:
    data = get_default_config()
    cm = ConfigManager(config=data, config_path=tmp_path / "c.json")

    class BadAuth(SearchAlpha):
        @staticmethod
        def validate_config(config: dict) -> None:
            if not config.get("token"):
                from librelyrics.exceptions import ConfigurationError

                raise ConfigurationError("token required")

        @staticmethod
        def default_config() -> dict:
            return {"token": ""}

    with pytest.raises(Exception) as exc:
        cm.validate_plugin_configs([BadAuth])
    assert "token required" in str(exc.value)
