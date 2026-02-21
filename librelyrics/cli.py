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
from typing import Annotated

import questionary
import typer
from rich.status import Status

from librelyrics import __version__
from librelyrics.config import ConfigManager, get_config_path, get_default_config
from librelyrics.core import LibreLyrics, fetch_files_lyrics
from librelyrics.exceptions import ConfigurationError, LyricsNotFound
from librelyrics.logging_config import setup_logging
from librelyrics.modules.base import ModuleCapability
from librelyrics.plugin_manager import install_plugin, list_plugins, remove_plugin
from librelyrics.registry import get_plugin_for_url, load_all_plugins
from librelyrics.ui import (
    console,
    print_config_table,
    print_download_summary,
    print_error,
    print_info,
    print_logo,
    print_plugins_table,
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


@app.callback()
def callback(
    ctx: typer.Context,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable verbose debug output."),
    ] = False,
    version: Annotated[
        bool | None,
        typer.Option(
            "--version", "-V",
            help="Show version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = None,
    directory: Annotated[
        str | None,
        typer.Option("--directory", "-d", metavar="PATH", help="Output directory for lyrics files."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite existing lyrics files."),
    ] = False,
) -> None:
    """Fetch lyrics from various sources and save as LRC files."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["directory"] = directory
    ctx.obj["force"] = force

    setup_logging(verbose=verbose)


# ── Fetch command (also the implicit default) ──────────────────
@app.command("fetch", hidden=True)
def fetch_command(
    ctx: typer.Context,
    url: Annotated[
        str | None,
        typer.Argument(help="URL or local path to fetch lyrics for."),
    ] = None,
) -> None:
    """Fetch lyrics for a URL or local path."""
    obj = ctx.ensure_object(dict)
    verbose = obj.get("verbose", False)
    directory = obj.get("directory")
    force = obj.get("force", False)

    url_was_prompted = False
    if not url:
        url = prompt_url(show_logo=True)
        url_was_prompted = True
        if not url:
            typer.echo(ctx.get_help())
            raise typer.Exit()

    code = handle_fetch(
        url, verbose=verbose, directory=directory,
        force=force, show_logo=not url_was_prompted,
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
    console.print(f"[cyan]{get_config_path()}[/cyan]")


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
    SAVE_EXIT = "Save & Exit"

    section_choices: list[str] = [GENERAL, FILE_NAME]

    plugin_map: dict[str, type] = {}
    for plugin_cls in plugins:
        meta = plugin_cls.META
        if meta.config_schema or meta.requires_auth:
            label = f"{meta.name} Plugin"
            section_choices.append(label)
            plugin_map[label] = plugin_cls

    section_choices += [SAVE_EXIT]

    console.print("\n[bold cyan]LibreLyrics Configuration[/bold cyan]")
    console.print("[dim]Choose a section to edit. You can edit multiple sections before saving.[/dim]\n")

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

    console.print(f"\n[bold green]{meta.name} Plugin[/bold green]")
    console.print("[dim]Press Enter to keep current value[/dim]")

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
    console.print("\n[bold]File Naming[/bold]")
    console.print("[dim]Available: {name}, {artist}, {album_name}, {track_number}[/dim]")

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
def handle_fetch(
    url: str,
    *,
    verbose: bool = False,
    directory: str | None = None,
    force: bool = False,
    show_logo: bool = True,
) -> int:
    """Handle fetching lyrics for a URL - with lazy loading.

    Args:
        url: The URL or path to fetch lyrics for.
        verbose: Enable verbose output.
        directory: Override output directory.
        force: Overwrite existing files.
        show_logo: Whether to print the logo.
    """
    if show_logo:
        print_logo()

    # Initialize librelyrics (lazy load plugins)
    try:
        librelyrics = LibreLyrics(verbose=verbose)
    except ConfigurationError as e:
        print_error(str(e))
        console.print("[dim]Run 'librelyrics config edit' to configure[/dim]")
        return 1
    except Exception as e:
        print_error(f"Failed to initialize: {e}")
        return 1

    # Apply CLI overrides
    if directory:
        librelyrics.config['download_path'] = directory
    if force:
        librelyrics.config['force_download'] = True

    # Check if it's a local path
    if os.path.isdir(url):
        return handle_local_files(librelyrics, url, verbose=verbose)

    # It's a URL - find matching plugin
    plugin_cls = get_plugin_for_url(librelyrics.plugins, url)
    if not plugin_cls:
        print_error("No plugin found that supports this URL")
        console.print(f"[dim]URL: {url}[/dim]")
        console.print("\n[dim]Installed plugins:[/dim]")
        for p in librelyrics.plugins:
            console.print(f"  • {p.META.name}: {p.META.regex.pattern}")
        return 1

    console.print(f"[dim]Using plugin:[/dim] [cyan]{plugin_cls.META.name}[/cyan]\n")

    # Get plugin config
    plugin_config = librelyrics.config_manager.for_plugin(plugin_cls)

    # Check if plugin requires auth
    if plugin_cls.META.requires_auth:
        try:
            plugin_cls.validate_config(plugin_config)
        except ConfigurationError as e:
            print_error(str(e))
            console.print(f"[dim]Run 'librelyrics config edit' to configure {plugin_cls.META.name}[/dim]")
            return 1

    # Instantiate plugin with authentication spinner
    try:
        with Status(f"[cyan]🔐 Authenticating with {plugin_cls.META.name}...[/cyan]", console=console, spinner="dots"):
            plugin = plugin_cls(url, plugin_config)
        print_success(f"Authenticated with {plugin_cls.META.name}")
    except Exception as e:
        print_error(f"Failed to initialize {plugin_cls.META.name}: {e}")
        return 1

    # Determine if batch or single fetch
    is_batch = 'album' in url.lower() or 'playlist' in url.lower()

    successful: list[str] = []
    failed: list[str] = []

    try:
        if is_batch and plugin.has_capability(ModuleCapability.ALBUM) and 'album' in url.lower():
            # Fetch album - get info first with spinner
            album_info = None
            with Status("[cyan] Fetching album info...[/cyan]", console=console, spinner="dots"):
                if hasattr(plugin, 'get_album_info'):
                    try:
                        album_info = plugin.get_album_info()
                    except Exception as e:
                        if verbose:
                            console.print(f"[dim]Could not get album info: {e}[/dim]")

            # Display album info
            folder_name = None
            if album_info:
                console.print(f"\n[bold]📀 Album:[/bold] {album_info.get('name', 'Unknown')}")
                artists = ', '.join(a['name'] for a in album_info.get('artists', []))
                console.print(f"   [dim]Artist:[/dim] {artists}")
                console.print(f"   [dim]Tracks:[/dim] {album_info.get('total_tracks', '?')}\n")

                # Generate folder name from template
                folder_template = librelyrics.config.get('album_folder_name', '{name} - {artists}')
                folder_name = folder_template.replace('{name}', album_info.get('name', 'Album'))
                folder_name = folder_name.replace('{artists}', artists)

            # Fetch and save with status spinner
            successful, failed, skipped = fetch_and_save_batch(
                plugin,
                'album',
                librelyrics.config,
                folder_name,
                verbose,
            )
            _print_batch_summary(successful, failed, skipped, album_info.get('total_tracks') if album_info else None, verbose)

        elif is_batch and plugin.has_capability(ModuleCapability.PLAYLIST) and 'playlist' in url.lower():
            # Fetch playlist - get info first with spinner
            playlist_info = None
            with Status("[cyan] Fetching playlist info...[/cyan]", console=console, spinner="dots"):
                if hasattr(plugin, 'get_playlist_info'):
                    try:
                        playlist_info = plugin.get_playlist_info()
                    except Exception as e:
                        if verbose:
                            console.print(f"[dim]Could not get playlist info: {e}[/dim]")

            # Display playlist info
            folder_name = None
            if playlist_info:
                console.print(f"\n[bold]📝 Playlist:[/bold] {playlist_info.get('name', 'Unknown')}")
                owner = playlist_info.get('owner', {}).get('display_name', 'Unknown')
                console.print(f"   [dim]Owner:[/dim] {owner}")
                track_count = playlist_info.get('tracks', {}).get('total', '?')
                console.print(f"   [dim]Tracks:[/dim] {track_count}\n")

                # Generate folder name from template
                folder_template = librelyrics.config.get('play_folder_name', '{name} - {owner}')
                folder_name = folder_template.replace('{name}', playlist_info.get('name', 'Playlist'))
                folder_name = folder_name.replace('{owner}', owner)

            # Fetch and save with status spinner
            successful, failed, skipped = fetch_and_save_batch(
                plugin,
                'playlist',
                librelyrics.config,
                folder_name,
                verbose,
            )
            total_tracks = playlist_info.get('tracks', {}).get('total') if playlist_info else None
            _print_batch_summary(successful, failed, skipped, total_tracks, verbose)

        else:
            # Single track - use spinner
            with Status("[cyan] Fetching track info...[/cyan]", console=console, spinner="dots"):
                response = plugin.fetch()

            # Show track info
            console.print(f"\n[bold]🎵 Track:[/bold] {response.title}")
            console.print(f"   [dim]Artist:[/dim] {response.artist}")
            if response.album:
                console.print(f"   [dim]Album:[/dim] {response.album}")
            console.print(f"   [dim]Synced:[/dim] {'✓ Yes' if response.synced else '✗ No'}")
            console.print()

            successful, failed = save_responses_interactive([response], librelyrics.config)

        if not is_batch:
            print_download_summary(successful, failed)
        return 0 if successful else 1

    except LyricsNotFound as e:
        print_warning(str(e))
        return 1
    except Exception as e:
        print_error(f"Failed to fetch lyrics: {e}")
        if verbose:
            console.print_exception()
        return 1


def fetch_and_save_batch(
    plugin,
    batch_type: str,  # 'album' or 'playlist'
    config: dict,
    folder_name: str | None = None,
    verbose: bool = False,
) -> tuple[list[str], list[str], list[str]]:
    """Fetch lyrics and save with a status spinner.

    Args:
        plugin: The plugin instance.
        batch_type: 'album' or 'playlist'.
        config: Configuration dictionary.
        folder_name: Optional folder name for output.
        verbose: Enable verbose output.

    Returns:
        Tuple of (successful_tracks, failed_tracks).
    """
    # Fetch all lyrics using the plugin's batch method
    responses = []
    with Status(f"[cyan]🎵 Fetching {batch_type} lyrics...[/cyan]", console=console, spinner="dots"):
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

    # Setup output directory
    download_path = config.get('download_path', 'downloads')
    if folder_name and config.get('create_folder', True):
        folder_name = re.sub(r'[\\/*?:"<>|]', '', folder_name)
        download_path = os.path.join(download_path, folder_name)
    os.makedirs(download_path, exist_ok=True)

    successful = []
    failed = []
    skipped = []

    with Status("[cyan]📝 Saving lyrics...[/cyan]", console=console, spinner="dots") as status:
        for response in responses:
            try:
                status.update(f"[cyan]📝 Saving: {response.title}[/cyan]")
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
                    continue

                # Write file with optional enhanced LRC format
                enhanced = config.get('enhanced_lrc', True) and response.rich_synced
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(response.to_lrc(enhanced=enhanced))

                successful.append(response.title)

            except Exception as e:
                failed.append(response.title if hasattr(response, 'title') else str(response))
                if verbose:
                    console.print(f"[dim]Error saving: {e}[/dim]")

    if successful:
        console.print(f"[green]✓[/green] Saved {len(successful)} lyrics to: [cyan]{download_path}[/cyan]")
    if skipped:
        console.print(f"[dim]⊘ Skipped {len(skipped)} existing files[/dim]")

    return successful, failed, skipped


def _print_batch_summary(
    successful: list[str],
    failed: list[str],
    skipped: list[str],
    total_tracks: int | str | None,
    verbose: bool,
) -> None:
    """Print a concise batch summary without per-track noise."""
    console.print()
    if successful:
        print_success(f"Downloaded lyrics for {len(successful)} tracks")
    if skipped:
        console.print(f"[dim]⊘ Skipped {len(skipped)} existing files[/dim]")

    missing = None
    if total_tracks is not None:
        try:
            missing = int(total_tracks) - len(successful) - len(skipped)
        except (TypeError, ValueError):
            missing = None

    if missing is not None and missing > 0:
        print_warning(f"Unable to download {missing} tracks")
    elif failed:
        print_warning(f"Unable to download {len(failed)} tracks")

    if verbose and failed:
        for title in failed:
            console.print(f"  [dim]- {title}[/dim]")


def save_responses_interactive(
    responses: list,
    config: dict,
    folder_name: str | None = None,
) -> tuple[list[str], list[str]]:
    """Save lyrics responses to files with a status spinner.

    Args:
        responses: List of LyricsResponse objects.
        config: Configuration dictionary.
        folder_name: Optional folder name for album/playlist.
    """
    download_path = config.get('download_path', 'downloads')

    # Create folder if specified
    if folder_name and config.get('create_folder', True):
        # Sanitize folder name
        folder_name = re.sub(r'[\\/*?:"<>|]', '', folder_name)
        download_path = os.path.join(download_path, folder_name)

    os.makedirs(download_path, exist_ok=True)

    successful = []
    failed = []
    skipped = []

    if not responses:
        return successful, failed

    with Status("[cyan]📝 Saving lyrics...[/cyan]", console=console, spinner="dots") as status:
        for response in responses:
            try:
                status.update(f"[cyan]📝 Saving: {response.title}[/cyan]")
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
                    continue

                # Write file with optional enhanced LRC format
                enhanced = config.get('enhanced_lrc', True) and response.rich_synced
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(response.to_lrc(enhanced=enhanced))

                successful.append(response.title)

            except Exception:
                failed.append(response.title)

    # Print summary
    console.print()
    if successful:
        console.print(f"[green]✓[/green] Saved {len(successful)} lyrics to: [cyan]{download_path}[/cyan]")
    if skipped:
        console.print(f"[dim]⊘ Skipped {len(skipped)} existing files[/dim]")
    if failed:
        console.print(f"[red]✗[/red] Failed: {len(failed)} tracks")
        for title in failed:
            console.print(f"   [dim]- {title}[/dim]")

    return successful, failed



def handle_local_files(librelyrics, path: str, *, verbose: bool = False) -> int:
    """Handle scanning local music files."""
    console.print(f"[dim]Scanning directory:[/dim] {path}\n")

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
    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in ("-d", "--directory"):
            skip_next = True  # next arg is the PATH value
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
