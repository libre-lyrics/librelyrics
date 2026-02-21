"""LibreLyrics core orchestrator.

Main entry point for the librelyrics library. Provides a unified interface
for fetching lyrics using the plugin system.
"""
from __future__ import annotations

import os
import re

from librelyrics.config import ConfigManager
from librelyrics.exceptions import LyricsNotFound, NoMatchingModuleError
from librelyrics.logging_config import get_logger, setup_logging
from librelyrics.models import LyricsResponse
from librelyrics.modules.base import LyricsModule, ModuleCapability
from librelyrics.registry import get_plugin_for_url, load_all_plugins

logger = get_logger('core')


LOGO = '''
  _     _ _              _               _
 | |   (_) |__  _ __ ___| |   _   _ _ __(_) ___ ___
 | |   | | '_ \\| '__/ _ \\ |  | | | | '__| |/ __/ __|
 | |___| | |_) | | |  __/ |__| |_| | |  | | (__\\__ \\
 |_____|_|_.__/|_|  \\___|_____\\__, |_|  |_|\\___|___/
                              |___/
'''


class LibreLyrics:
    """Main librelyrics orchestrator.

    Provides a high-level interface for fetching lyrics from URLs
    using the plugin system.
    """

    def __init__(
        self,
        config: dict | None = None,
        verbose: bool = False,
    ) -> None:
        """Initialize LibreLyrics.

        Args:
            config: Optional pre-loaded configuration dictionary.
            verbose: Enable verbose logging.
        """
        setup_logging(verbose=verbose)

        self.config_manager = ConfigManager(config)
        self.plugins = load_all_plugins(self.config_manager.raw)

        # Merge plugin default configs
        if self.config_manager.merge_plugin_defaults(self.plugins):
            self.config_manager.save()

        logger.debug(f"Loaded {len(self.plugins)} plugins")

    @property
    def config(self) -> dict:
        """Get the raw configuration dictionary."""
        return self.config_manager.raw

    def fetch(self, url: str) -> LyricsResponse:
        """Fetch lyrics for a URL.

        Finds the first matching plugin and uses it to fetch lyrics.

        Args:
            url: URL to fetch lyrics from.

        Returns:
            LyricsResponse with lyrics data.

        Raises:
            NoMatchingModuleError: If no plugin matches the URL.
            LyricsNotFound: If lyrics are not available.
        """
        plugin_cls = get_plugin_for_url(self.plugins, url)

        if not plugin_cls:
            raise NoMatchingModuleError(
                f"No plugin found that can handle URL: {url}"
            )

        # Get plugin-specific config
        plugin_config = self.config_manager.for_plugin(plugin_cls)

        # Instantiate and fetch
        plugin = plugin_cls(url, plugin_config)
        return plugin.fetch_with_retry()

    def fetch_batch(self, url: str) -> list[LyricsResponse]:
        """Fetch lyrics for multiple tracks (album/playlist).

        Args:
            url: Album or playlist URL.

        Returns:
            List of LyricsResponse objects.

        Raises:
            NoMatchingModuleError: If no plugin matches the URL.
        """
        plugin_cls = get_plugin_for_url(self.plugins, url)

        if not plugin_cls:
            raise NoMatchingModuleError(
                f"No plugin found that can handle URL: {url}"
            )

        plugin_config = self.config_manager.for_plugin(plugin_cls)
        plugin = plugin_cls(url, plugin_config)

        # Dispatch based on declared capabilities — no hasattr / URL sniffing
        if plugin.has_capability(ModuleCapability.ALBUM) and 'album' in url.lower():
            return plugin.fetch_album()
        elif plugin.has_capability(ModuleCapability.PLAYLIST) and 'playlist' in url.lower():
            return plugin.fetch_playlist()
        else:
            # Fallback to single fetch
            return [plugin.fetch()]

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
    matches = re.findall(r'{(.+?)}', template)
    result = template
    for match in matches:
        placeholder = f'{{{match}}}'
        value = str(data.get(match, ''))
        result = result.replace(placeholder, value)
    return re.sub(r'[\\/*?:"<>|]', "", result)


def save_lyrics(lyrics: str, path: str) -> None:
    """Save lyrics to a file.

    Args:
        lyrics: Lyrics content to save.
        path: File path to save to.
    """
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, "w+", encoding='utf-8') as f:
        f.write(lyrics)
    logger.debug(f"Saved lyrics to: {path}")


def download_lyrics(
    librelyrics: LibreLyrics,
    url: str,
    folder: str | None = None,
) -> tuple[list[str], list[str]]:
    """Download lyrics for a URL (track, album, or playlist).

    Args:
        librelyrics: LibreLyrics instance.
        url: URL to download lyrics from.
        folder: Optional output folder name.

    Returns:
        Tuple of (successful_tracks, failed_tracks).
    """
    config = librelyrics.config
    download_path = config.get('download_path', 'downloads')

    if folder:
        output_dir = os.path.join(download_path, folder)
    else:
        output_dir = download_path

    # Check if we should skip existing
    if folder and config.get('create_folder') and not config.get('force_download'):
        if os.path.exists(output_dir):
            logger.info("The album/playlist was already downloaded, skipping")
            return [], []

    os.makedirs(output_dir, exist_ok=True)

    successful: list[str] = []
    failed: list[str] = []

    try:
        responses = librelyrics.fetch_batch(url)

        for response in responses:
            try:
                file_data = {
                    'name': response.title,
                    'artist': response.artist,
                    'album_name': response.album or '',
                    'track_number': str(response.metadata.get('track_number', 0)).zfill(2),
                    'explicit': '[E]' if response.metadata.get('explicit') else '',
                }

                file_name = rename_using_format(
                    config.get('file_name', '{track_number}. {name}'),
                    file_data
                )
                file_path = os.path.join(output_dir, f"{file_name}.lrc")

                # Skip if exists and not forcing
                if os.path.exists(file_path) and not config.get('force_download'):
                    logger.debug(f"Skipping existing: {file_path}")
                    continue

                lrc_content = response.to_lrc()
                save_lyrics(lrc_content, file_path)
                successful.append(response.title)

            except Exception as e:
                logger.warning(f"Failed to save lyrics for {response.title}: {e}")
                failed.append(response.title)

    except NoMatchingModuleError as e:
        logger.error(str(e))
        return [], [url]
    except LyricsNotFound as e:
        logger.warning(str(e))
        return [], [url]

    return successful, failed


def fetch_files_lyrics(
    librelyrics: LibreLyrics,
    path: str,
) -> tuple[list[str], list[str]]:
    """Fetch lyrics for music files in a directory.

    Note: This feature requires search functionality which is not available
    with the Partner API. Use track URLs directly instead.

    Args:
        librelyrics: LibreLyrics instance.
        path: Path to directory containing music files.

    Returns:
        Tuple of (successful_tracks, failed_tracks).

    Raises:
        NotImplementedError: Search not available with Partner API.
    """
    raise NotImplementedError(
        "File scanning requires search functionality which is not available with the Partner API. "
        "Please use track/album/playlist URLs directly instead."
    )

