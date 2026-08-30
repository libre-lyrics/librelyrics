"""Single-track and batch lyrics fetch pipeline."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from librelyrics.config import ConfigManager
from librelyrics.exceptions import (
    ConfigurationError,
    DirectModeError,
    LyricsNotFound,
    MissingMetadataError,
    NoMatchingModuleError,
    ProviderError,
    UnknownPluginError,
)
from librelyrics.models import LyricsResponse, TrackQuery
from librelyrics.modules.base import LyricsModule, ModuleCapability
from librelyrics.quality import (
    fallback_sort_key,
    is_good_enough,
    meets_any_listed,
    plugin_can_satisfy,
)
from librelyrics.registry import get_plugin_by_id, get_plugin_for_url
from librelyrics.search_query import search_query_variants

logger = logging.getLogger("librelyrics.pipeline")


def _search_priority_ids(config_manager: ConfigManager) -> list[str]:
    raw = config_manager.get("search_priority") or []
    return [str(item).strip() for item in raw if str(item).strip()]


def apply_cli_overrides(resolved: TrackQuery, original: TrackQuery) -> TrackQuery:
    """CLI (original) fields win when they are set."""
    return TrackQuery(
        url=original.url if original.url is not None else resolved.url,
        artist=original.artist if original.artist is not None else resolved.artist,
        title=original.title if original.title is not None else resolved.title,
        album=original.album if original.album is not None else resolved.album,
        duration_ms=(
            original.duration_ms
            if original.duration_ms is not None
            else resolved.duration_ms
        ),
    )


def resolve_query(
    query: TrackQuery,
    plugins: list[type[LyricsModule]],
    config_manager: ConfigManager,
) -> TrackQuery:
    if not query.url:
        return query
    url_plugin = get_plugin_for_url(plugins, query)
    if url_plugin is None or not url_plugin.has_capability(ModuleCapability.RESOLVE):
        return query
    plugin = url_plugin(query, config_manager.for_plugin(url_plugin))
    resolved = plugin.resolve()
    return apply_cli_overrides(resolved, query)


def fetch_query(
    query: TrackQuery,
    plugins: list[type[LyricsModule]],
    config_manager: ConfigManager,
    *,
    direct: bool = False,
    from_plugin: str | None = None,
) -> LyricsResponse:
    if direct and from_plugin:
        raise ConfigurationError("--direct and --from cannot be used together")
    if direct:
        return _fetch_direct(query, plugins, config_manager)
    if from_plugin:
        return _fetch_from(query, plugins, config_manager, from_plugin)
    return _fetch_default(query, plugins, config_manager)


def fetch_batch_query(
    query: TrackQuery,
    plugins: list[type[LyricsModule]],
    config_manager: ConfigManager,
    *,
    direct: bool = False,
    from_plugin: str | None = None,
) -> list[LyricsResponse]:
    if not query.url:
        return [fetch_query(
            query, plugins, config_manager, direct=direct, from_plugin=from_plugin,
        )]

    plugin_cls = get_plugin_for_url(plugins, query)
    if plugin_cls is None:
        raise NoMatchingModuleError(
            f"No plugin found that can handle URL: {query.url}"
        )

    plugin = plugin_cls(query, config_manager.for_plugin(plugin_cls))
    url_l = query.url.lower()
    is_album = plugin_cls.has_capability(ModuleCapability.ALBUM) and "album" in url_l
    is_playlist = (
        plugin_cls.has_capability(ModuleCapability.PLAYLIST) and "playlist" in url_l
    )
    priority = _search_priority_ids(config_manager)
    logger.debug("search_priority=%s", priority)

    if direct:
        if is_album:
            return plugin.fetch_album()
        if is_playlist:
            return plugin.fetch_playlist()
        return [plugin.fetch_with_retry()]

    if is_album or is_playlist:
        if priority:
            try:
                tracks = plugin.list_tracks()
            except NotImplementedError as exc:
                kind = "album" if is_album else "playlist"
                raise ConfigurationError(
                    f"{plugin_cls.META.name} does not implement list_tracks(), "
                    f"which is required to use search_priority on an {kind} URL. "
                    f"Update the URL plugin, or pass --direct to fetch lyrics from "
                    f"{plugin_cls.META.name}."
                ) from exc
            logger.debug(
                "Listed %s tracks; searching lyrics via %s",
                len(tracks),
                ", ".join(priority),
            )
            return _fetch_tracks_concurrent(
                tracks, plugins, config_manager, from_plugin=from_plugin,
            )
        try:
            tracks = plugin.list_tracks()
        except NotImplementedError:
            if is_album:
                return plugin.fetch_album()
            return plugin.fetch_playlist()
        return _fetch_tracks_concurrent(
            tracks, plugins, config_manager, from_plugin=from_plugin,
        )

    return [fetch_query(
        query, plugins, config_manager, direct=False, from_plugin=from_plugin,
    )]


def _fetch_direct(
    query: TrackQuery,
    plugins: list[type[LyricsModule]],
    config_manager: ConfigManager,
) -> LyricsResponse:
    if not query.url:
        raise DirectModeError("--direct requires a URL")
    plugin_cls = get_plugin_for_url(plugins, query)
    if plugin_cls is None:
        raise NoMatchingModuleError(
            f"No plugin found that can handle URL: {query.url}"
        )
    plugin = plugin_cls(query, config_manager.for_plugin(plugin_cls))
    return plugin.fetch_with_retry()


def _fetch_from(
    query: TrackQuery,
    plugins: list[type[LyricsModule]],
    config_manager: ConfigManager,
    plugin_id: str,
) -> LyricsResponse:
    plugin_cls = get_plugin_by_id(plugins, plugin_id)
    if plugin_cls is None:
        raise UnknownPluginError(f"No plugin installed with id: {plugin_id}")
    query = resolve_query(query, plugins, config_manager)
    if not query.artist or not query.title:
        raise MissingMetadataError(
            "Artist and title are required (pass --artist and --title, or a URL that can resolve)"
        )
    if not plugin_cls.has_capability(ModuleCapability.SEARCH):
        raise UnknownPluginError(f"Plugin '{plugin_id}' does not support SEARCH")
    return _try_search_plugin(plugin_cls, query, config_manager)


def _try_search_plugin(
    plugin_cls: type[LyricsModule],
    query: TrackQuery,
    config_manager: ConfigManager,
) -> LyricsResponse:
    """Run SEARCH fetch across artist/title variants. Counts as one plugin attempt."""
    last_error: Exception | None = None
    for variant in search_query_variants(replace(query, url=None)):
        logger.debug(
            "Search %s with artist=%r title=%r",
            plugin_cls.META.id,
            variant.artist,
            variant.title,
        )
        plugin = plugin_cls(variant, config_manager.for_plugin(plugin_cls))
        try:
            return plugin.fetch_with_retry()
        except LyricsNotFound as exc:
            last_error = exc
            logger.info("%s: %s", plugin_cls.META.name, exc)
            continue
        except ProviderError as exc:
            last_error = exc
            logger.info("%s failed: %s", plugin_cls.META.name, exc)
            continue
    if last_error is not None:
        raise last_error
    raise LyricsNotFound("Lyrics not found")


def _fetch_default(
    query: TrackQuery,
    plugins: list[type[LyricsModule]],
    config_manager: ConfigManager,
) -> LyricsResponse:
    query = resolve_query(query, plugins, config_manager)
    priority = _search_priority_ids(config_manager)
    logger.debug("search_priority=%s", priority)

    if priority:
        logger.debug("Searching lyrics via %s", ", ".join(priority))
        return _search_loop(query, plugins, config_manager, priority)

    if query.url:
        plugin_cls = get_plugin_for_url(plugins, query)
        if plugin_cls is None:
            raise NoMatchingModuleError(
                f"No plugin found that can handle URL: {query.url}"
            )
        plugin = plugin_cls(query, config_manager.for_plugin(plugin_cls))
        return plugin.fetch_with_retry()

    search_plugins = [
        p for p in plugins if p.has_capability(ModuleCapability.SEARCH)
    ]
    search_plugins.sort(key=lambda p: p.META.id)
    if not search_plugins:
        raise LyricsNotFound("No search plugin available for artist and title")
    return _search_loop(
        query, plugins, config_manager, [search_plugins[0].META.id],
    )


def _search_loop(
    query: TrackQuery,
    plugins: list[type[LyricsModule]],
    config_manager: ConfigManager,
    priority: list[str],
) -> LyricsResponse:
    preferred = list(config_manager.get("preferred_lyrics_order") or [])
    cap = int(config_manager.get("max_search_attempts") or 5)
    search_query = replace(query, url=None)
    attempts = 0
    fallback: LyricsResponse | None = None
    fallback_key: tuple[int, int] | None = None
    last_resort: LyricsResponse | None = None

    for plugin_id in priority:
        plugin_cls = get_plugin_by_id(plugins, plugin_id)
        if plugin_cls is None:
            logger.warning("Unknown plugin id %s in search_priority; skip", plugin_id)
            continue
        if not plugin_cls.has_capability(ModuleCapability.SEARCH):
            logger.warning("Plugin %s is not a SEARCH plugin; skip", plugin_id)
            continue
        if not plugin_can_satisfy(plugin_cls, preferred):
            logger.debug("Pre-filter skip %s for preferred %s", plugin_id, preferred)
            continue
        if attempts >= cap:
            break
        attempts += 1
        try:
            result = _try_search_plugin(plugin_cls, search_query, config_manager)
        except LyricsNotFound as exc:
            logger.info("%s: %s", plugin_cls.META.name, exc)
            continue
        except ConfigurationError as exc:
            logger.warning("Skip %s: %s", plugin_id, exc)
            continue
        except ProviderError as exc:
            logger.info("%s failed: %s", plugin_cls.META.name, exc)
            continue

        last_resort = result
        if is_good_enough(result, preferred):
            return result
        if meets_any_listed(result, preferred):
            key = fallback_sort_key(result, preferred, plugin_id, priority)
            if fallback is None or key < fallback_key:
                fallback = result
                fallback_key = key

    if fallback is not None:
        return fallback
    if last_resort is not None:
        return last_resort
    raise LyricsNotFound("Lyrics not found")


def _fetch_tracks_concurrent(
    tracks: list[TrackQuery],
    plugins: list[type[LyricsModule]],
    config_manager: ConfigManager,
    *,
    from_plugin: str | None,
) -> list[LyricsResponse]:
    workers = max(1, int(config_manager.get("max_concurrent_tracks") or 4))
    results: list[LyricsResponse | None] = [None] * len(tracks)

    def _one(index: int, track: TrackQuery) -> tuple[int, LyricsResponse | None]:
        try:
            return index, fetch_query(
                track, plugins, config_manager, from_plugin=from_plugin,
            )
        except LyricsNotFound:
            logger.warning("No lyrics for %s - %s", track.artist, track.title)
            return index, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_one, i, track) for i, track in enumerate(tracks)]
        for fut in futs:
            index, response = fut.result()
            results[index] = response

    return [item for item in results if item is not None]
