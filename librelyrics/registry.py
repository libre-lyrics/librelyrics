"""Plugin discovery and registration system.

Discovers plugins via Python entry points (group: 'librelyrics.plugins').
"""
from __future__ import annotations

import logging
import re
from importlib.metadata import entry_points

from librelyrics.exceptions import NoPluginsFoundError
from librelyrics.models import TrackQuery
from librelyrics.modules.base import (
    LIBRELYRICS_API_VERSION,
    PLUGIN_ID_PATTERN,
    LyricsModule,
)

logger = logging.getLogger('librelyrics.registry')

NO_PLUGINS_INSTALL_MESSAGE = "No plugins found. Install a plugin to continue."
NO_API2_PLUGINS_MESSAGE = (
    "No API 2 plugins loaded. LibreLyrics no longer loads API 1 plugins; "
    "update your plugin packages and try again."
)


def plugin_import_failure_message(entry_point_name: str, exc: BaseException) -> str:
    """User-facing reason a plugin module failed to import."""
    if _looks_like_api1_modulemeta_error(exc):
        return (
            f"Plugin '{entry_point_name}' is still API 1 and cannot load. "
            f"LibreLyrics now requires API 2 — update the plugin package."
        )
    return f"Failed to load external plugin '{entry_point_name}': {exc}"


def _looks_like_api1_modulemeta_error(exc: BaseException) -> bool:
    if not isinstance(exc, TypeError):
        return False
    text = str(exc)
    return "ModuleMeta" in text or "argument: 'id'" in text


def no_compatible_plugins_message(
    entry_point_count: int,
    *,
    import_failures: list[str],
    rejected: list[type[LyricsModule]],
) -> str:
    """Message when discovery produced no loadable API 2 plugins."""
    if entry_point_count == 0:
        return NO_PLUGINS_INSTALL_MESSAGE
    if import_failures or rejected:
        return NO_API2_PLUGINS_MESSAGE
    return NO_PLUGINS_INSTALL_MESSAGE


def discover_external_plugins() -> list[type[LyricsModule]]:
    """Discover external plugins via Python entry points.

    External plugins register themselves in pyproject.toml:

        [project.entry-points."librelyrics.plugins"]
        myplugin = "librelyrics_myplugin:MyPluginModule"

    Returns:
        List of discovered plugin classes.
    """
    plugins, _, _ = _discover_plugins()
    return plugins


def _discover_plugins() -> tuple[list[type[LyricsModule]], list[str], int]:
    """Return (imported plugins, failed entry-point names, entry-point count)."""
    plugins: list[type[LyricsModule]] = []
    failed: list[str] = []
    eps = list(entry_points(group='librelyrics.plugins'))

    for ep in eps:
        try:
            plugin_cls = ep.load()

            if not isinstance(plugin_cls, type) or not issubclass(plugin_cls, LyricsModule):
                logger.warning(
                    f"Entry point '{ep.name}' does not point to a LyricsModule subclass"
                )
                failed.append(ep.name)
                continue

            if not hasattr(plugin_cls, 'META'):
                logger.warning(f"Plugin '{ep.name}' missing META attribute")
                failed.append(ep.name)
                continue

            plugins.append(plugin_cls)
            logger.debug(f"Discovered external plugin: {plugin_cls.META.name}")

        except Exception as e:
            logger.warning(plugin_import_failure_message(ep.name, e))
            failed.append(ep.name)

    return plugins, failed, len(eps)


def validate_plugin(plugin_cls: type[LyricsModule]) -> bool:
    """Validate that a plugin is compatible with current API version."""
    plugin_version = getattr(plugin_cls, 'LIBRELYRICS_API_VERSION', None)

    if plugin_version is None:
        logger.warning(
            f"Plugin '{plugin_cls.__name__}' missing LIBRELYRICS_API_VERSION"
        )
        return False

    if plugin_version != LIBRELYRICS_API_VERSION:
        display = getattr(getattr(plugin_cls, 'META', None), 'name', None)
        display = display or plugin_cls.__name__
        logger.warning(
            "Plugin '%s' uses API %s; LibreLyrics now requires API %s. "
            "Update the plugin package.",
            display,
            plugin_version,
            LIBRELYRICS_API_VERSION,
        )
        return False

    if not hasattr(plugin_cls, 'META'):
        logger.warning(f"Plugin '{plugin_cls.__name__}' missing META attribute")
        return False

    plugin_id = getattr(plugin_cls.META, 'id', '')
    if not plugin_id or not PLUGIN_ID_PATTERN.fullmatch(plugin_id):
        logger.warning(
            f"Plugin '{plugin_cls.__name__}' has invalid META.id {plugin_id!r}"
        )
        return False

    return True


def dedupe_plugins_by_id(
    plugins: list[type[LyricsModule]],
) -> list[type[LyricsModule]]:
    """Keep one plugin per META.id. Later entries win. Sort by id."""
    by_id: dict[str, type[LyricsModule]] = {}
    for plugin_cls in plugins:
        existing = by_id.get(plugin_cls.META.id)
        if existing is not None:
            logger.warning(
                "Plugin %s replaces %s for id %s",
                plugin_cls.__name__,
                existing.__name__,
                plugin_cls.META.id,
            )
        by_id[plugin_cls.META.id] = plugin_cls
    return sorted(by_id.values(), key=lambda p: p.META.id)


def load_all_plugins(config: dict | None = None) -> list[type[LyricsModule]]:
    """Load all available plugins from entry points."""
    plugins, failed, entry_point_count = _discover_plugins()
    plugins = dedupe_plugins_by_id(plugins)
    valid_plugins = [p for p in plugins if validate_plugin(p)]

    if not valid_plugins:
        rejected = [p for p in plugins if p not in valid_plugins]
        raise NoPluginsFoundError(
            no_compatible_plugins_message(
                entry_point_count,
                import_failures=failed,
                rejected=rejected,
            )
        )

    logger.debug(f"Loaded {len(valid_plugins)} plugins")
    return valid_plugins


def get_plugin_for_url(
    plugins: list[type[LyricsModule]],
    query: TrackQuery | str,
) -> type[LyricsModule] | None:
    """Find the plugin whose URL regex matches the query URL.

    SEARCH overrides of matches() are ignored so a metadata plugin cannot
    steal a host URL.
    """
    if isinstance(query, str):
        query = TrackQuery(url=query)
    if not query.url:
        return None
    for plugin_cls in plugins:
        regex = plugin_cls.META.regex
        if regex is not None and regex.search(query.url):
            logger.debug("URL matched by plugin: %s", plugin_cls.META.name)
            return plugin_cls
    return None


def get_plugin_by_id(
    plugins: list[type[LyricsModule]],
    plugin_id: str,
) -> type[LyricsModule] | None:
    """Return the plugin with the given id, or a matching display name."""
    key = plugin_id.strip().lower()
    if not key:
        return None
    compact = re.sub(r"[^a-z0-9]", "", key)
    for plugin_cls in plugins:
        if plugin_cls.META.id == key:
            return plugin_cls
    for plugin_cls in plugins:
        name = plugin_cls.META.name.lower()
        if name == key or re.sub(r"[^a-z0-9]", "", name) == compact:
            return plugin_cls
        if plugin_cls.META.id == compact:
            return plugin_cls
    return None
