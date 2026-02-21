"""Configuration management for librelyrics.

Handles loading, saving, and validating configuration from config.json.
Supports auto-merging plugin default configurations.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from librelyrics.exceptions import ConfigurationError, CorruptedConfig
from librelyrics.modules.base import LyricsModule

logger = logging.getLogger('librelyrics.config')


def get_config_path() -> Path:
    """Get the platform-specific config file path.

    Returns:
        Path to config.json in the appropriate location.
    """
    if os.name == 'nt':
        config_dir = Path(os.environ.get('APPDATA', '')) / 'librelyrics'
    else:
        config_dir = Path.home() / '.config' / 'librelyrics'

    return config_dir / 'config.json'


def get_default_config() -> dict:
    """Get the default configuration structure.

    Returns:
        Dictionary with default configuration values.
    """
    return {
        'download_path': 'downloads',
        'create_folder': True,
        'album_folder_name': '{name} - {artists}',
        'play_folder_name': '{name} - {owner}',
        'file_name': '{track_number}. {name}',
        'synced_lyrics': True,
        'enhanced_lrc': True,  # Use Enhanced LRC format for rich synced lyrics
        'force_download': False,
        'plugins': {},  # Plugin-specific configs go here
    }


class ConfigManager:
    """Manages configuration loading, saving, and plugin config merging."""

    def __init__(self, config: dict | None = None, config_path: Path | None = None):
        """Initialize the config manager.

        Args:
            config: Optional pre-loaded configuration. If None, loads from file.
            config_path: Optional custom config file path.
        """
        self.config_path = config_path or get_config_path()

        if config is not None:
            self._config = config
        else:
            self._config = self._load_config()

    def _load_config(self) -> dict:
        """Load configuration from file.

        Returns:
            Configuration dictionary.

        Raises:
            CorruptedConfig: If config file cannot be parsed.
        """
        if not self.config_path.exists():
            logger.info(f"Config file not found at {self.config_path}, creating defaults")
            default_config = get_default_config()
            self._config = default_config
            try:
                self.save()
            except Exception as e:
                logger.warning(f"Failed to save default config to {self.config_path}: {e}")
            return default_config

        try:
            with open(self.config_path, encoding='utf-8') as f:
                config = json.load(f)
                logger.debug(f"Loaded config from {self.config_path}")
                return config
        except json.JSONDecodeError as e:
            raise CorruptedConfig(
                f"Config file at {self.config_path} is corrupted: {e}"
            ) from e
        except Exception as e:
            raise CorruptedConfig(
                f"Failed to load config from {self.config_path}: {e}"
            ) from e

    def save(self) -> None:
        """Save current configuration to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self._config, f, indent=4)
        logger.debug(f"Saved config to {self.config_path}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value.

        Args:
            key: Configuration key.
            default: Default value if key not found.

        Returns:
            Configuration value.
        """
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value.

        Args:
            key: Configuration key.
            value: Value to set.
        """
        self._config[key] = value

    def __getitem__(self, key: str) -> Any:
        return self._config[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._config[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._config

    @property
    def raw(self) -> dict:
        """Get the raw configuration dictionary."""
        return self._config

    def for_plugin(self, plugin_cls: type[LyricsModule]) -> dict:
        """Get configuration for a specific plugin.

        Merges plugin defaults with stored plugin config.

        Args:
            plugin_cls: Plugin class to get config for.

        Returns:
            Merged configuration dictionary for the plugin.
        """
        plugin_name = plugin_cls.META.name.lower()

        # Get plugin's default config
        defaults = plugin_cls.default_config()

        # Get stored plugin config
        plugins_config = self._config.get('plugins', {})
        stored = plugins_config.get(plugin_name, {})

        # Merge: stored values override defaults
        merged = {**defaults, **stored}

        return merged

    def merge_plugin_defaults(
        self,
        plugins: list[type[LyricsModule]]
    ) -> bool:
        """Merge default configurations from all plugins.

        Adds missing plugin config sections with their defaults.

        Args:
            plugins: List of plugin classes to merge defaults from.

        Returns:
            True if config was modified and should be saved.
        """
        modified = False

        # Ensure plugins section exists
        if 'plugins' not in self._config:
            self._config['plugins'] = {}
            modified = True

        for plugin_cls in plugins:
            plugin_name = plugin_cls.META.name.lower()
            defaults = plugin_cls.default_config()

            if not defaults:
                continue

            if plugin_name not in self._config['plugins']:
                self._config['plugins'][plugin_name] = defaults
                logger.debug(f"Added default config for plugin: {plugin_name}")
                modified = True
            else:
                # Merge missing keys
                stored = self._config['plugins'][plugin_name]
                for key, value in defaults.items():
                    if key not in stored:
                        stored[key] = value
                        modified = True

        return modified

    def validate_plugin_configs(
        self,
        plugins: list[type[LyricsModule]]
    ) -> None:
        """Validate configuration for all plugins.

        Args:
            plugins: List of plugin classes to validate config for.

        Raises:
            ConfigurationError: If any plugin config is invalid.
        """
        for plugin_cls in plugins:
            plugin_config = self.for_plugin(plugin_cls)
            try:
                plugin_cls.validate_config(plugin_config)
            except Exception as e:
                raise ConfigurationError(
                    f"Invalid config for plugin '{plugin_cls.META.name}': {e}"
                ) from e
