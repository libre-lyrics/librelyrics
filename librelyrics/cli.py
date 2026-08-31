"""Command-line interface for librelyrics.

Modern CLI powered by Typer with:
- Declarative subcommands (no manual if/elif routing)
- Lazy plugin loading
- Interactive config editor
- Rich terminal output
- Universal URL handling
"""
from __future__ import annotations

import io
import os
import re
import sys
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from typing import Annotated, Optional

import questionary
import typer

from librelyrics import __version__
from librelyrics.config import ConfigManager, get_config_path, get_default_config
from librelyrics.core import LibreLyrics, fetch_files_lyrics
from librelyrics.exceptions import (
    ConfigurationError,
    DirectModeError,
    LyricsNotFound,
    MissingMetadataError,
    NoMatchingModuleError,
    NoPluginsFoundError,
    UnknownPluginError,
)
from librelyrics.logging_config import setup_logging
from librelyrics.models import TrackQuery
from librelyrics.modules.base import ModuleCapability
from librelyrics.plugin_manager import install_plugin, list_plugins, remove_plugin
from librelyrics.registry import get_plugin_by_id, get_plugin_for_url, load_all_plugins
from librelyrics.ui import (
    FetchSummary,
    console,
    create_progress,
    format_progress_description,
    print_config_table,
    print_download_summary,
    print_error,
    print_fetch_summary,
    print_info,
    print_logo,
    print_plugins_table,
    print_session_header,
    print_success,
    print_warning,
    prompt_url,
)

app = typer.Typer(
    name="librelyrics",
    help="Fetch lyrics from various sources and save as LRC files.",
    rich_markup_mode="rich",
    no_args_is_help=False,
    invoke_without_command=True,
    add_completion=False,
)

config_app = typer.Typer(
    name="config",
    help="View and edit configuration.",
    invoke_without_command=True,
    no_args_is_help=False,
)

plugin_app = typer.Typer(
    name="plugin",
    help="Manage lyrics provider plugins.",
    invoke_without_command=True,
    no_args_is_help=False,
)

app.add_typer(config_app, name="config")
app.add_typer(plugin_app, name="plugin")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"librelyrics {__version__}")
        raise typer.Exit()


def _normalize_cli_url(url: str | None) -> str | None:
    """Strip whitespace and a trailing PowerShell line-continuation backslash."""
    if url is None:
        return None
    return url.strip().rstrip("\\")


# Typer 0.9 cannot convert PEP 604 `str | None` and is unreliable with
# Annotated optional Arguments. Use Optional[...] = typer.Option/Argument.
@app.callback()
def callback(
    ctx: typer.Context,
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Enable verbose debug output.",
    ),
    version: bool = typer.Option(
        False,
        "--version", "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
    directory: Optional[str] = typer.Option(
        None, "--directory", "-d", metavar="PATH",
        help="Output directory for lyrics files.",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Overwrite existing lyrics files.",
    ),
) -> None:
    """Fetch lyrics from various sources and save as LRC files."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["directory"] = directory
    ctx.obj["force"] = force

    setup_logging(verbose=verbose, console=console)


# ── Fetch command (also the implicit default) ──────────────────
@app.command("fetch", hidden=True)
def fetch_command(
    ctx: typer.Context,
    url: Optional[str] = typer.Argument(
        None, help="URL or local path to fetch lyrics for.",
    ),
    artist: Optional[str] = typer.Option(
        None, "--artist", help="Track artist for a metadata search.",
    ),
    title: Optional[str] = typer.Option(
        None, "--title", help="Track title for a metadata search.",
    ),
    album: Optional[str] = typer.Option(
        None, "--album", help="Album name (optional metadata).",
    ),
    direct: bool = typer.Option(
        False, "--direct", "-D",
        help="Fetch only from the plugin that matches the URL.",
    ),
    from_plugin: Optional[str] = typer.Option(
        None, "--from", help="Force lyrics from this plugin id after resolve.",
    ),
) -> None:
    """Fetch lyrics for a URL or local path."""
    obj = ctx.ensure_object(dict)
    verbose = obj.get("verbose", False)
    directory = obj.get("directory")
    force = obj.get("force", False)

    url_was_prompted = False
    if not url and not (artist and title):
        url = prompt_url(show_logo=True)
        url_was_prompted = True
        if not url:
            typer.echo(ctx.get_help())
            raise typer.Exit()

    code = handle_fetch(
        url, verbose=verbose, directory=directory,
        force=force, show_logo=not url_was_prompted,
        artist=artist, title=title, album=album,
        direct=direct, from_plugin=from_plugin,
    )
    raise typer.Exit(code=code)


@config_app.callback()
def config_callback(ctx: typer.Context) -> None:
    """View and edit configuration."""
    if ctx.invoked_subcommand is None:
        config_show()


@config_app.command("show")
def config_show() -> None:
    """Show current configuration."""
    config_path = get_config_path()
    if config_path.exists():
        config = ConfigManager().raw
        print_config_table(config)
    else:
        print_info("No config file found. Run 'librelyrics config edit' to create one.")


@config_app.command("path")
def config_path_cmd() -> None:
    """Print the config file path."""
    console.print(f"[accent]{get_config_path()}[/accent]")


@config_app.command("reset")
def config_reset() -> None:
    """Reset configuration to defaults."""
    cm = ConfigManager(config=get_default_config())
    cm.save()
    print_success("Configuration reset to defaults")


@config_app.command("set")
def config_set(
    key: Annotated[str, typer.Argument(help="Config key (e.g. plugins.spotify.sp_dc).")],
    value: Annotated[str, typer.Argument(help="Value to set.")],
) -> None:
    """Set a single config value."""
    cm = ConfigManager()
    config = cm.raw

    # Handle nested keys like plugins.spotify.sp_dc
    parts = key.split('.')
    current = config
    for part in parts[:-1]:
        if part not in current:
            current[part] = {}
        current = current[part]

    # Convert value types
    converted: str | bool | int = value
    if value.lower() == 'true':
        converted = True
    elif value.lower() == 'false':
        converted = False
    elif value.isdigit():
        converted = int(value)

    current[parts[-1]] = converted
    cm.save()

    print_success(f"Set {key} = {converted}")


@config_app.command("edit")
def config_edit_cmd() -> None:
    """Interactive configuration editor."""
    edit_config_interactive()


def edit_config_interactive() -> int:
    """Interactive config editor using questionary.

    Shows a menu so the user can choose *which* section to edit
    instead of prompting for every option at once.  Plugin config
    fields are driven by each plugin's ``META.config_schema`` and
    ``default_config()`` so adding a new plugin never requires
    touching this function.
    """
    cm = ConfigManager()
    config = cm.raw

    # Ensure nested structure exists
    if 'plugins' not in config:
        config['plugins'] = {}

    # Discover plugins and merge defaults once
    plugins = load_all_plugins(config)
    for plugin_cls in plugins:
        plugin_name = plugin_cls.META.name.lower()
        defaults = plugin_cls.default_config()
        if plugin_name not in config['plugins']:
            config['plugins'][plugin_name] = defaults
        else:
            for key, value in defaults.items():
                config['plugins'][plugin_name].setdefault(key, value)

    # ── Build the section menu ──────────────────────────────────
    GENERAL   = "General Settings"
    FILE_NAME = "File Naming"
    SEARCH    = "Search and lyrics quality"
    SAVE_EXIT = "Save & Exit"

    section_choices: list[str] = [GENERAL, FILE_NAME, SEARCH]

    plugin_map: dict[str, type] = {}
    for plugin_cls in plugins:
        meta = plugin_cls.META
        if meta.config_schema or meta.requires_auth:
            label = f"{meta.name} Plugin"
            section_choices.append(label)
            plugin_map[label] = plugin_cls

    section_choices += [SAVE_EXIT]

    console.print("\n[bold]Configuration[/bold]")
    console.print("[muted]Choose a section to edit. You can edit multiple sections before saving.[/muted]\n")

    while True:
        section = questionary.select(
            "What would you like to configure?",
            choices=section_choices,
        ).ask()

        if section is None or section == SAVE_EXIT:
            break

        if section == GENERAL:
            _edit_general_settings(config)
        elif section == FILE_NAME:
            _edit_file_naming(config)
        elif section == SEARCH:
            _edit_search_settings(config, plugins)
        elif section in plugin_map:
            _edit_plugin_config(config, plugin_map[section])

        console.print()

    cm.save()

    console.print()
    print_success("Configuration saved!")
    return 0


def _edit_plugin_config(config: dict, plugin_cls: type) -> None:
    """Prompt for a single plugin's config fields."""
    meta = plugin_cls.META
    plugin_name = meta.name.lower()
    schema = meta.config_schema

    console.print(f"\n[bold]{meta.name}[/bold]")
    console.print("[muted]Press Enter to keep current value[/muted]")

    for key, description in schema.items():
        current_value = config['plugins'][plugin_name].get(key, '')

        if isinstance(current_value, bool):
            answer = questionary.confirm(
                f"{description}:",
                default=current_value,
            ).ask()
        else:
            answer = questionary.text(
                f"{description}:",
                default=str(current_value),
            ).ask()

        if answer is not None:
            config['plugins'][plugin_name][key] = answer


def _edit_search_settings(config: dict, plugins: list) -> None:
    """Prompt for search priority and preferred lyrics order."""
    console.print("\n[bold]Search and lyrics quality[/bold]")
    console.print("[muted]Order tokens: RICH, SYNCED, UNSYNCED[/muted]")
    ids = [p.META.id for p in plugins]
    if ids:
        console.print(f"[muted]Installed plugin ids: {', '.join(ids)}[/muted]")

    current_order = config.get('preferred_lyrics_order', ['RICH', 'SYNCED', 'UNSYNCED'])
    order_text = questionary.text(
        "Preferred lyrics order (comma-separated):",
        default=', '.join(current_order),
    ).ask()
    if order_text is not None:
        config['preferred_lyrics_order'] = [
            part.strip().upper() for part in order_text.split(',') if part.strip()
        ]

    current_priority = config.get('search_priority', [])
    priority_text = questionary.text(
        "Search priority plugin ids (comma-separated, empty = URL plugin only):",
        default=', '.join(current_priority),
    ).ask()
    if priority_text is not None:
        config['search_priority'] = [
            part.strip() for part in priority_text.split(',') if part.strip()
        ]

    attempts = questionary.text(
        "Max search attempts per track:",
        default=str(config.get('max_search_attempts', 5)),
    ).ask()
    if attempts and attempts.isdigit():
        config['max_search_attempts'] = int(attempts)


def _edit_general_settings(config: dict) -> None:
    """Prompt for general download settings."""
    console.print("\n[bold]General Settings[/bold]")

    download_path = questionary.path(
        "Download directory:",
        default=config.get('download_path', 'downloads'),
        only_directories=True,
    ).ask()
    if download_path:
        config['download_path'] = download_path

    create_folder = questionary.confirm(
        "Create folders for albums/playlists?",
        default=config.get('create_folder', True),
    ).ask()
    if create_folder is not None:
        config['create_folder'] = create_folder

    force = questionary.confirm(
        "Overwrite existing files by default?",
        default=config.get('force_download', False),
    ).ask()
    if force is not None:
        config['force_download'] = force


def _edit_file_naming(config: dict) -> None:
    """Prompt for file/folder naming templates."""
    console.print("\n[bold]File naming[/bold]")
    console.print("[muted]Available: {name}, {artist}, {album_name}, {track_number}[/muted]")

    file_name = questionary.text(
        "File name format:",
        default=config.get('file_name', '{track_number}. {name}'),
    ).ask()
    if file_name:
        config['file_name'] = file_name

    album_folder = questionary.text(
        "Album folder format:",
        default=config.get('album_folder_name', '{name} - {artists}'),
    ).ask()
    if album_folder:
        config['album_folder_name'] = album_folder

    playlist_folder = questionary.text(
        "Playlist folder format:",
        default=config.get('play_folder_name', '{name} - {owner}'),
    ).ask()
    if playlist_folder:
        config['play_folder_name'] = playlist_folder


# ── Plugin sub-commands ─────────────────────────────────────────
@plugin_app.callback()
def plugin_callback(ctx: typer.Context) -> None:
    """Manage lyrics provider plugins."""
    if ctx.invoked_subcommand is None:
        plugin_list()


@plugin_app.command("list")
def plugin_list() -> None:
    """List all plugins in resolved order."""
    config = ConfigManager().raw
    plugins = list_plugins(config)
    print_plugins_table(plugins)


@plugin_app.command("install")
def plugin_install(
    package: Annotated[str, typer.Argument(help="Package name to install (e.g. librelyrics-foo).")],
) -> None:
    """Install an external plugin package."""
    success = install_plugin(package)
    if not success:
        raise typer.Exit(code=1)


@plugin_app.command("remove")
def plugin_remove(
    package: Annotated[str, typer.Argument(help="Package name to remove.")],
) -> None:
    """Remove a plugin package."""
    success = remove_plugin(package)
    if not success:
        raise typer.Exit(code=1)


# ── Fetch logic ─────────────────────────────────────────────────
def _plugin_display_name(plugins, plugin_id: str) -> str:
    """Return a plugin's display name, falling back to the id if unknown."""
    plugin_cls = get_plugin_by_id(plugins, plugin_id)
    if plugin_cls is None:
        return plugin_id
    return plugin_cls.META.name


def handle_fetch(
    url: str | None,
    *,
    verbose: bool = False,
    directory: str | None = None,
    force: bool = False,
    show_logo: bool = True,
    artist: str | None = None,
    title: str | None = None,
    album: str | None = None,
    direct: bool = False,
    from_plugin: str | None = None,
) -> int:
    """Handle fetching lyrics for a URL or metadata query."""
    url = _normalize_cli_url(url)
    if show_logo:
        print_logo()

    if direct and from_plugin:
        print_error("--direct and --from cannot be used together")
        return 1
    if (artist and not title) or (title and not artist):
        print_error("--artist and --title must be used together")
        return 1
    if direct and not url:
        print_error("--direct requires a URL")
        return 1

    try:
        librelyrics = LibreLyrics(verbose=verbose)
    except NoPluginsFoundError as e:
        print_error(str(e))
        return 1
    except ConfigurationError as e:
        print_error(str(e))
        console.print("[dim]Run 'librelyrics config edit' to configure[/dim]")
        return 1
    except Exception as e:
        print_error(f"Failed to initialize: {e}")
        return 1

    if directory:
        librelyrics.config['download_path'] = directory
    if force:
        librelyrics.config['force_download'] = True

    if url and os.path.isdir(url):
        return handle_local_files(librelyrics, url, verbose=verbose)

    query = TrackQuery(url=url, artist=artist, title=title, album=album)
    is_batch = bool(
        url and ('album' in url.lower() or 'playlist' in url.lower())
    )

    folder_name = None
    total_tracks = None
    session_header: dict | None = None
    plugin_cls = get_plugin_for_url(librelyrics.plugins, query) if url else None
    priority_ids = [
        str(item).strip()
        for item in (librelyrics.config_manager.get("search_priority") or [])
        if str(item).strip()
    ]
    search_plugins = [
        _plugin_display_name(librelyrics.plugins, plugin_id)
        for plugin_id in priority_ids
    ]

    if plugin_cls:
        plugin_config = librelyrics.config_manager.for_plugin(plugin_cls)
        if plugin_cls.META.requires_auth:
            try:
                plugin_cls.validate_config(plugin_config)
            except ConfigurationError as e:
                print_error(str(e))
                console.print(
                    f"[muted]Run 'librelyrics config edit' to configure "
                    f"{plugin_cls.META.name}[/muted]"
                )
                return 1
        if is_batch:
            plugin = plugin_cls(query, plugin_config)
            folder_name, total_tracks, session_header = _batch_folder_and_count(
                plugin, url or "", librelyrics.config, verbose,
            )

    if session_header:
        print_session_header(
            resolve_plugin=plugin_cls.META.name if plugin_cls else None,
            search_plugins=search_plugins or None,
            **session_header,
        )

    try:
        if is_batch and url:
            fetch_failures: list[tuple[str, str]] = []
            completed = 0

            with create_progress() as progress:
                fetch_task = progress.add_task(
                    format_progress_description("Fetching"),
                    total=total_tracks,
                )

                def _on_track(track, response, reason) -> None:
                    nonlocal completed
                    completed += 1
                    track_title = track.title or "Unknown"
                    progress.update(
                        fetch_task,
                        completed=completed,
                        description=format_progress_description("Fetching", track_title),
                    )
                    if reason:
                        label = f"{track.artist or 'Unknown'} - {track_title}"
                        fetch_failures.append((label, reason))

                responses = librelyrics.fetch_batch(
                    url,
                    direct=direct,
                    from_plugin=from_plugin,
                    on_track=_on_track,
                )

                if total_tracks is None:
                    progress.update(fetch_task, total=completed)

                successful, save_failed, skipped, download_path = save_responses(
                    responses,
                    librelyrics.config,
                    folder_name,
                    progress=progress,
                )

            all_failed = fetch_failures + [
                (title, "Save failed") for title in save_failed
            ]
            print_fetch_summary(
                FetchSummary(
                    successful=successful,
                    failed=all_failed,
                    skipped=skipped,
                    download_path=download_path,
                    total_tracks=total_tracks,
                ),
                verbose=verbose,
            )
            return 0 if successful else 1

        with create_progress() as progress:
            fetch_task = progress.add_task(format_progress_description("Fetching"), total=1)
            response = librelyrics.fetch_query(
                query, direct=direct, from_plugin=from_plugin,
            )
            progress.update(
                fetch_task,
                completed=1,
                description=format_progress_description("Fetching", response.title),
            )

        quality = (
            "Rich"
            if response.rich_synced
            else ("Synced" if response.synced else "Unsynced")
        )
        print_session_header(
            kind="track",
            title=response.title,
            artist=response.artist,
            album=response.album,
            source=response.source,
            quality=quality,
            resolve_plugin=plugin_cls.META.name if plugin_cls else None,
            search_plugins=search_plugins or None,
        )

        successful, save_failed, skipped, download_path = save_responses(
            [response], librelyrics.config,
        )
        print_fetch_summary(
            FetchSummary(
                successful=successful,
                failed=[(title, "Save failed") for title in save_failed],
                skipped=skipped,
                download_path=download_path,
            ),
            verbose=verbose,
        )

        return 0 if successful else 1

    except DirectModeError as e:
        print_error(str(e))
        return 1
    except ConfigurationError as e:
        print_error(str(e))
        return 1
    except UnknownPluginError as e:
        print_error(str(e))
        return 1
    except MissingMetadataError as e:
        print_error(str(e))
        return 1
    except NoMatchingModuleError as e:
        print_error(str(e))
        if url:
            console.print(f"[dim]URL: {url}[/dim]")
        console.print("\n[dim]Installed plugins:[/dim]")
        for p in librelyrics.plugins:
            pattern = p.META.regex.pattern if p.META.regex else "(search)"
            console.print(f"  • {p.META.id} ({p.META.name}): {pattern}")
        return 1
    except LyricsNotFound as e:
        print_warning(str(e))
        return 1
    except Exception as e:
        print_error(f"Failed to fetch lyrics: {e}")
        if verbose:
            console.print_exception()
        return 1


def _batch_folder_and_count(
    plugin,
    url: str,
    config: dict,
    verbose: bool,
) -> tuple[str | None, int | None, dict | None]:
    """Album/playlist folder name and session header fields from plugin info."""
    folder_name = None
    total_tracks = None
    session_header: dict | None = None
    try:
        if "album" in url.lower() and hasattr(plugin, "get_album_info"):
            info = plugin.get_album_info()
            artists = ", ".join(a["name"] for a in info.get("artists", []))
            session_header = {
                "kind": "album",
                "title": info.get("name", "Unknown"),
                "artist": artists,
                "tracks": info.get("total_tracks", "?"),
            }
            template = config.get("album_folder_name", "{name} - {artists}")
            folder_name = template.replace(
                "{name}", info.get("name", "Album"),
            ).replace("{artists}", artists)
            try:
                total_tracks = int(info.get("total_tracks"))
            except (TypeError, ValueError):
                total_tracks = None
        elif "playlist" in url.lower() and hasattr(plugin, "get_playlist_info"):
            info = plugin.get_playlist_info()
            owner = info.get("owner", {}).get("display_name", "Unknown")
            track_count = info.get("tracks", {}).get("total", "?")
            session_header = {
                "kind": "playlist",
                "title": info.get("name", "Unknown"),
                "owner": owner,
                "tracks": track_count,
            }
            template = config.get("play_folder_name", "{name} - {owner}")
            folder_name = template.replace(
                "{name}", info.get("name", "Playlist"),
            ).replace("{owner}", owner)
            try:
                total_tracks = int(track_count)
            except (TypeError, ValueError):
                total_tracks = None
    except Exception as e:
        if verbose:
            console.print(f"[muted]Could not get album/playlist info: {e}[/muted]")
    return folder_name, total_tracks, session_header


def _format_task_desc(action: str, title: str = "", max_title_len: int = 25) -> str:
    """Format action and track title into a clean description for fixed-width progress bars."""
    if not title:
        return f"[cyan]{action}[/cyan]"
    if len(title) > max_title_len:
        title = title[: max_title_len - 3] + "..."
    return f"[cyan]{action}: {title}[/cyan]"


def fetch_and_save_batch(
    plugin,
    batch_type: str,  # 'album' or 'playlist'
    config: dict,
    folder_name: str | None = None,
    verbose: bool = False,
    total_tracks: int | str | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """Fetch lyrics and save with a progress bar.

    Args:
        plugin: The plugin instance.
        batch_type: 'album' or 'playlist'.
        config: Configuration dictionary.
        folder_name: Optional folder name for output.
        verbose: Enable verbose output.
        total_tracks: Total tracks count if known.

    Returns:
        Tuple of (successful_tracks, failed_tracks, skipped_tracks).
    """
    total_count: int | None = None
    if total_tracks is not None:
        try:
            total_count = int(total_tracks)
        except (TypeError, ValueError):
            total_count = None

    responses = []
    fetched_count = 0

    with create_progress() as progress:
        task = progress.add_task(
            _format_task_desc(f"Fetching {batch_type} lyrics"),
            total=total_count,
        )

        orig_fetch_track = getattr(plugin, '_fetch_track_lyrics', None)

        def _on_track_fetched(response=None):
            nonlocal fetched_count
            fetched_count += 1
            title = response.title if response and hasattr(response, 'title') else ''
            desc = _format_task_desc("Downloading", title)
            progress.update(task, completed=fetched_count, description=desc)

        if orig_fetch_track:
            def wrapped_fetch_track(*args, **kwargs):
                res = orig_fetch_track(*args, **kwargs)
                _on_track_fetched(res)
                return res
            plugin._fetch_track_lyrics = wrapped_fetch_track

        try:
            with ExitStack() as stack:
                if not verbose:
                    stack.enter_context(redirect_stdout(io.StringIO()))
                    stack.enter_context(redirect_stderr(io.StringIO()))
                if batch_type == 'album' and plugin.has_capability(ModuleCapability.ALBUM):
                    responses = plugin.fetch_album()
                elif batch_type == 'playlist' and plugin.has_capability(ModuleCapability.PLAYLIST):
                    responses = plugin.fetch_playlist()
                else:
                    # Fallback: try single fetch
                    responses = [plugin.fetch()]
        except Exception as e:
            if verbose:
                console.print(f"[dim]Batch fetch error: {e}[/dim]")
            raise
        finally:
            if orig_fetch_track:
                plugin._fetch_track_lyrics = orig_fetch_track

        # Update total if total_count was unknown or mismatched
        total_items = len(responses) if responses else (total_count or 0)
        progress.update(task, total=max(total_items, fetched_count), completed=max(fetched_count, total_items))

        # Setup output directory
        download_path = config.get('download_path', 'downloads')
        if folder_name and config.get('create_folder', True):
            folder_name = re.sub(r'[\\/*?:"<>|]', '', folder_name)
            download_path = os.path.join(download_path, folder_name)
        os.makedirs(download_path, exist_ok=True)

        successful = []
        failed = []
        skipped = []

        save_task = progress.add_task(_format_task_desc("Saving lyrics"), total=len(responses))
        for response in responses:
            try:
                desc = _format_task_desc("Saving", response.title)
                progress.update(save_task, description=desc)

                # Build filename
                file_data = {
                    'name': response.title,
                    'artist': response.artist,
                    'album_name': response.album or '',
                    'track_number': str(response.metadata.get('track_number', 0)).zfill(2),
                }

                template = config.get('file_name', '{track_number}. {name}')
                file_name = template
                for key, value in file_data.items():
                    file_name = file_name.replace(f'{{{key}}}', str(value))

                # Sanitize filename
                file_name = re.sub(r'[\\/*?:"<>|]', '', file_name)
                file_path = os.path.join(download_path, f"{file_name}.lrc")

                # Check if exists
                if os.path.exists(file_path) and not config.get('force_download'):
                    skipped.append(response.title)
                    progress.update(save_task, advance=1)
                    continue

                # Write file with optional enhanced LRC format
                enhanced = response.rich_synced
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(response.to_lrc(enhanced=enhanced))

                successful.append(response.title)
                progress.update(save_task, advance=1)

            except Exception as e:
                failed.append(response.title if hasattr(response, 'title') else str(response))
                progress.update(save_task, advance=1)
                if verbose:
                    console.print(f"[dim]Error saving: {e}[/dim]")

    if successful:
        console.print(
            f"[success]Saved[/success]     {len(successful)} "
            f"to [accent]{download_path}[/accent]"
        )

    return successful, failed, skipped


def _format_task_desc(action: str, title: str = "", max_title_len: int = 25) -> str:
    """Format action and track title for progress bars."""
    return format_progress_description(action, title, max_title_len=max_title_len)


def save_responses(
    responses: list,
    config: dict,
    folder_name: str | None = None,
    *,
    progress=None,
) -> tuple[list[str], list[str], list[str], str]:
    """Save lyrics responses to files, optionally within an existing progress display."""
    download_path = config.get("download_path", "downloads")

    if folder_name and config.get("create_folder", True):
        folder_name = re.sub(r'[\\/*?:"<>|]', "", folder_name)
        download_path = os.path.join(download_path, folder_name)

    os.makedirs(download_path, exist_ok=True)

    successful: list[str] = []
    failed: list[str] = []
    skipped: list[str] = []

    if not responses:
        return successful, failed, skipped, download_path

    def _save_one(response) -> None:
        nonlocal successful, failed, skipped
        file_data = {
            "name": response.title,
            "artist": response.artist,
            "album_name": response.album or "",
            "track_number": str(response.metadata.get("track_number", 0)).zfill(2),
        }

        template = config.get("file_name", "{track_number}. {name}")
        file_name = template
        for key, value in file_data.items():
            file_name = file_name.replace(f"{{{key}}}", str(value))

        file_name = re.sub(r'[\\/*?:"<>|]', "", file_name)
        file_path = os.path.join(download_path, f"{file_name}.lrc")

        if os.path.exists(file_path) and not config.get("force_download"):
            skipped.append(response.title)
            return

        enhanced = response.rich_synced
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write(response.to_lrc(enhanced=enhanced))

        successful.append(response.title)

    if progress is not None:
        save_task = progress.add_task(
            format_progress_description("Saving"),
            total=len(responses),
        )
        for response in responses:
            try:
                progress.update(
                    save_task,
                    description=format_progress_description("Saving", response.title),
                )
                _save_one(response)
            except Exception:
                failed.append(response.title)
            progress.update(save_task, advance=1)
    else:
        with create_progress() as local_progress:
            save_task = local_progress.add_task(
                format_progress_description("Saving"),
                total=len(responses),
            )
            for response in responses:
                try:
                    local_progress.update(
                        save_task,
                        description=format_progress_description("Saving", response.title),
                    )
                    _save_one(response)
                except Exception:
                    failed.append(response.title)
                local_progress.update(save_task, advance=1)

    return successful, failed, skipped, download_path


def save_responses_interactive(
    responses: list,
    config: dict,
    folder_name: str | None = None,
) -> tuple[list[str], list[str]]:
    """Backward-compatible save helper returning successful and failed only."""
    successful, failed, _skipped, _path = save_responses(
        responses, config, folder_name,
    )
    return successful, failed



def handle_local_files(librelyrics, path: str, *, verbose: bool = False) -> int:
    """Handle scanning local music files."""
    console.print(f"[muted]Scanning[/muted]   {path}\n")

    try:
        successful, failed = fetch_files_lyrics(librelyrics, path)
        print_download_summary(successful, failed)
        return 0 if successful else 1
    except Exception as e:
        print_error(str(e))
        return 1


# ── Entry point ─────────────────────────────────────────────────
# Known subcommands that should NOT be treated as URLs
_SUBCOMMANDS = {"config", "plugin", "fetch", "--help", "-h"}


def main() -> None:
    """Main entry point.

    If the first positional argument is not a known subcommand,
    transparently insert the hidden ``fetch`` command so that
    ``librelyrics <URL>`` keeps working without the user typing
    ``librelyrics fetch <URL>``.
    """
    args = sys.argv[1:]

    # Find the first arg that isn't an option (--verbose, -d PATH, etc.)
    first_positional = None
    skip_next = False
    value_flags = {
        "-d", "--directory", "--artist", "--title", "--album", "--from",
    }
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in value_flags:
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        first_positional = arg
        break

    # If the first positional arg isn't a subcommand, inject "fetch"
    if first_positional and first_positional not in _SUBCOMMANDS:
        idx = args.index(first_positional)
        args.insert(idx, "fetch")
        sys.argv = [sys.argv[0], *args]

    # If no positional arg at all, also inject "fetch" (triggers interactive prompt)
    if first_positional is None:
        # check that no subcommand flag like --help was given
        if not any(a in ("--help", "-h", "--version", "-V") for a in args):
            sys.argv = [sys.argv[0], *args, "fetch"]

    app()


if __name__ == '__main__':
    main()
