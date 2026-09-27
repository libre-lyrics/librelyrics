"""LibreLyrics core orchestrator.

Main entry point for the librelyrics library. Provides a unified interface
for fetching lyrics using the plugin system.
"""

from __future__ import annotations

import re

from librelyrics.config import ConfigManager
from librelyrics.logging_config import get_logger, setup_logging
from librelyrics.models import LyricsResponse, TrackQuery
from librelyrics.modules.base import LyricsModule
from librelyrics.pipeline import fetch_batch_query, fetch_query
from librelyrics.registry import load_all_plugins

logger = get_logger("core")


LOGO = """
  _     _ _              _               _
 | |   (_) |__  _ __ ___| |   _   _ _ __(_) ___ ___
 | |   | | '_ \\| '__/ _ \\ |  | | | | '__| |/ __/ __|
 | |___| | |_) | | |  __/ |__| |_| | |  | | (__\\__ \\
 |_____|_|_.__/|_|  \\___|_____\\__, |_|  |_|\\___|___/
                              |___/
"""


class LibreLyrics:
    """Main librelyrics orchestrator.

    Provides a high-level interface for fetching lyrics from URLs
    using the plugin system.
    """

    def __init__(
        self,
        config: dict | None = None,
        verbose: bool = False,
        plugins: list[type[LyricsModule]] | None = None,
    ) -> None:
        """Initialize LibreLyrics.

        Args:
            config: Optional pre-loaded configuration dictionary.
            verbose: Enable verbose logging.
            plugins: Optional plugin list (tests). Loads from disk when omitted.
        """
        if verbose:
            from librelyrics.ui import console as rich_console

            setup_logging(verbose=True, console=rich_console)
        else:
            setup_logging(verbose=False)

        self.config_manager = ConfigManager(config)
        if plugins is None:
            self.plugins = load_all_plugins(self.config_manager.raw)
        else:
            self.plugins = plugins

        if self.config_manager.merge_plugin_defaults(self.plugins):
            self.config_manager.save()

        logger.debug(f"Loaded {len(self.plugins)} plugins")

    @property
    def config(self) -> dict:
        """Get the raw configuration dictionary."""
        return self.config_manager.raw

    def fetch(
        self,
        url: str,
        *,
        direct: bool = False,
        from_plugin: str | None = None,
    ) -> LyricsResponse:
        """Fetch lyrics for a URL."""
        return self.fetch_query(
            TrackQuery(url=url),
            direct=direct,
            from_plugin=from_plugin,
        )

    def fetch_query(
        self,
        query: TrackQuery,
        *,
        direct: bool = False,
        from_plugin: str | None = None,
    ) -> LyricsResponse:
        """Fetch lyrics for a TrackQuery."""
        return fetch_query(
            query,
            self.plugins,
            self.config_manager,
            direct=direct,
            from_plugin=from_plugin,
        )

    def fetch_batch(
        self,
        url: str,
        *,
        direct: bool = False,
        from_plugin: str | None = None,
        on_track=None,
        on_phase=None,
    ) -> list[LyricsResponse]:
        """Fetch lyrics for multiple tracks (album/playlist) or one track URL."""
        return fetch_batch_query(
            TrackQuery(url=url),
            self.plugins,
            self.config_manager,
            direct=direct,
            from_plugin=from_plugin,
            on_track=on_track,
            on_phase=on_phase,
        )

    def list_plugins(self) -> list[type[LyricsModule]]:
        """Get list of loaded plugins.

        Returns:
            List of plugin classes.
        """
        return self.plugins


def rename_using_format(template: str, data: dict) -> str:
    """Format a string using template variables.

    Args:
        template: Template string with {variable} placeholders.
        data: Dictionary of variable values.

    Returns:
        Formatted string with invalid filename characters removed.
    """
    matches = re.findall(r"{(.+?)}", template)
    result = template
    for match in matches:
        placeholder = f"{{{match}}}"
        value = str(data.get(match, ""))
        result = result.replace(placeholder, value)
    return re.sub(r'[\\/*?:"<>|]', "", result)
