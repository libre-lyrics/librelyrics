"""Plugin discovery and registration system.

Discovers plugins via Python entry points (group: 'librelyrics.plugins')
and via local plugin directories.
"""
from __future__ import annotations

import importlib.util
import logging
import sys
from importlib.metadata import entry_points
from pathlib import Path

from librelyrics.exceptions import NoPluginsFoundError
from librelyrics.models import TrackQuery
from librelyrics.modules.base import (
    LIBRELYRICS_API_VERSION,
    PLUGIN_ID_PATTERN,
    LyricsModule,
)

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
        eps = entry_points(group='librelyrics.plugins')
    except TypeError:
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


def discover_directory_plugins(directories: list[Path]) -> list[type[LyricsModule]]:
    """Load LyricsModule subclasses from plugin directories."""
    plugins: list[type[LyricsModule]] = []
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.name.startswith('_') or path.name.startswith('.'):
                continue
            module_file: Path | None = None
            if path.is_file() and path.suffix == '.py':
                module_file = path
            elif path.is_dir() and (path / '__init__.py').exists():
                module_file = path / '__init__.py'
            if module_file is None:
                continue
            plugins.extend(_load_module_plugins(module_file))
    return plugins


def _load_module_plugins(module_file: Path) -> list[type[LyricsModule]]:
    module_name = (
        f"librelyrics_dirplugin_{module_file.parent.name}_"
        f"{module_file.stem}_{id(module_file)}"
    )
    spec = importlib.util.spec_from_file_location(module_name, module_file)
    if spec is None or spec.loader is None:
        logger.warning("Cannot load plugin file: %s", module_file)
        return []
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        logger.warning("Failed to load plugin file %s: %s", module_file, exc)
        sys.modules.pop(module_name, None)
        return []

    found: list[type[LyricsModule]] = []
    for value in vars(module).values():
        if (
            isinstance(value, type)
            and issubclass(value, LyricsModule)
            and value is not LyricsModule
            and hasattr(value, 'META')
        ):
            found.append(value)
            logger.debug("Discovered directory plugin: %s", value.META.name)
    return found


def validate_plugin(plugin_cls: type[LyricsModule]) -> bool:
    """Validate that a plugin is compatible with current API version."""
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


def merge_plugins(
    entry_point_plugins: list[type[LyricsModule]],
    directory_plugins: list[type[LyricsModule]],
) -> list[type[LyricsModule]]:
    """Merge plugin lists. Directory plugins replace the same id."""
    by_id: dict[str, type[LyricsModule]] = {}
    for plugin_cls in entry_point_plugins:
        by_id[plugin_cls.META.id] = plugin_cls
    for plugin_cls in directory_plugins:
        existing = by_id.get(plugin_cls.META.id)
        if existing is not None:
            logger.warning(
                "Directory plugin %s replaces entry-point plugin %s",
                plugin_cls.__name__,
                existing.__name__,
            )
        by_id[plugin_cls.META.id] = plugin_cls
    return sorted(by_id.values(), key=lambda p: p.META.id)


def plugin_directories_from_config(
    config: dict | None,
    config_path: Path | None = None,
) -> list[Path]:
    """Resolve plugin directories from config.

    An empty plugin_directories list still uses <config_dir>/plugins.
    """
    from librelyrics.config import get_config_path

    config = config or {}
    configured = config.get('plugin_directories') or []
    if configured:
        return [Path(p).expanduser() for p in configured]
    base = (config_path or get_config_path()).parent
    return [base / 'plugins']


def load_all_plugins(config: dict | None = None) -> list[type[LyricsModule]]:
    """Load all available plugins from entry points and plugin directories."""
    plugins = merge_plugins(
        discover_external_plugins(),
        discover_directory_plugins(plugin_directories_from_config(config)),
    )
    valid_plugins = [p for p in plugins if validate_plugin(p)]

    if not valid_plugins:
        raise NoPluginsFoundError("No plugins found. Install a plugin to continue.")

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
    """Return the plugin with the given id, or None."""
    for plugin_cls in plugins:
        if plugin_cls.META.id == plugin_id:
            return plugin_cls
    return None
