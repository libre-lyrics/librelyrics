"""Plugin discovery and registration system.

Discovers plugins via Python entry points (group: 'librelyrics.plugins').
"""
from __future__ import annotations

import logging
from importlib.metadata import entry_points

from librelyrics.exceptions import NoPluginsFoundError
from librelyrics.modules.base import LIBRELYRICS_API_VERSION, LyricsModule

logger = logging.getLogger('librelyrics.registry')


def discover_external_plugins() -> list[type[LyricsModule]]:
    """Discover external plugins via Python entry points.

    External plugins register themselves in pyproject.toml:

        [project.entry-points."librelyrics.plugins"]
        myplugin = "librelyrics_myplugin:MyPluginModule"

    Returns:
        List of discovered plugin classes.
    """
    plugins: list[type[LyricsModule]] = []

    try:
        # Python 3.10+ API
        eps = entry_points(group='librelyrics.plugins')
    except TypeError:
        # Python 3.9 compatibility
        all_eps = entry_points()
        eps = all_eps.get('librelyrics.plugins', [])

    for ep in eps:
        try:
            plugin_cls = ep.load()

            if not isinstance(plugin_cls, type) or not issubclass(plugin_cls, LyricsModule):
                logger.warning(
                    f"Entry point '{ep.name}' does not point to a LyricsModule subclass"
                )
                continue

            if not hasattr(plugin_cls, 'META'):
                logger.warning(f"Plugin '{ep.name}' missing META attribute")
                continue

            plugins.append(plugin_cls)
            logger.debug(f"Discovered external plugin: {plugin_cls.META.name}")

        except Exception as e:
            logger.warning(f"Failed to load external plugin '{ep.name}': {e}")

    return plugins


def validate_plugin(plugin_cls: type[LyricsModule]) -> bool:
    """Validate that a plugin is compatible with current API version.

    Args:
        plugin_cls: Plugin class to validate.

    Returns:
        True if plugin is compatible, False otherwise.
    """
    plugin_version = getattr(plugin_cls, 'LIBRELYRICS_API_VERSION', None)

    if plugin_version is None:
        logger.warning(
            f"Plugin '{plugin_cls.__name__}' missing LIBRELYRICS_API_VERSION"
        )
        return False

    if plugin_version != LIBRELYRICS_API_VERSION:
        logger.warning(
            f"Plugin '{plugin_cls.__name__}' requires API version {plugin_version}, "
            f"but current version is {LIBRELYRICS_API_VERSION}"
        )
        return False

    return True


def load_all_plugins(config: dict | None = None) -> list[type[LyricsModule]]:
    """Load all available plugins.

    Discovers plugins via entry points (librelyrics.plugins group).

    Plugins are sorted alphabetically by name for deterministic ordering.

    Args:
        config: Optional configuration dict.

    Returns:
        List of plugin classes sorted alphabetically.
    """
    plugins: list[type[LyricsModule]] = []

    # Discover external plugins via entry points
    plugins.extend(discover_external_plugins())

    # Filter invalid plugins
    valid_plugins = [p for p in plugins if validate_plugin(p)]

    # Sort alphabetically for deterministic ordering
    valid_plugins.sort(key=lambda p: p.META.name.lower())

    if not valid_plugins:
        raise NoPluginsFoundError("No plugins found. Install a plugin to continue.")

    logger.debug(f"Loaded {len(valid_plugins)} plugins")
    return valid_plugins


def get_plugin_for_url(
    plugins: list[type[LyricsModule]],
    url: str
) -> type[LyricsModule] | None:
    """Find the first plugin that matches the given URL.

    Plugins are checked in the resolved order.

    Args:
        plugins: List of plugin classes to check.
        url: URL to match against.

    Returns:
        First matching plugin class, or None if no match.
    """
    for plugin_cls in plugins:
        if plugin_cls.matches(url):
            logger.debug(f"URL matched by plugin: {plugin_cls.META.name}")
            return plugin_cls
    return None
