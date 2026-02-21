"""Rich UI helpers for librelyrics CLI.

Provides styled console output, progress bars, and formatted displays.
"""
from __future__ import annotations

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.theme import Theme

from librelyrics.models import LyricsResponse

LIBRELYRICS_THEME = Theme({
    "info": "cyan",
    "success": "green",
    "warning": "yellow",
    "error": "red bold",
    "highlight": "magenta",
    "muted": "dim",
})

console = Console(theme=LIBRELYRICS_THEME)

LOGO = """[bold magenta]
  _     _ _              _               _
 | |   (_) |__  _ __ ___| |   _   _ _ __(_) ___ ___
 | |   | | '_ \\| '__/ _ \\ |  | | | | '__| |/ __/ __|
 | |___| | |_) | | |  __/ |__| |_| | |  | | (__\\__ \\\\
 |_____|_|_.__/|_|  \\___|_____\\__, |_|  |_|\\___|___/
                              |___/
[/bold magenta]
"""


def print_logo() -> None:
    """Print the librelyrics logo."""
    console.print(LOGO)


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[success]✓[/success] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[error]✗ Error:[/error] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[warning]⚠[/warning] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[info]ℹ[/info] {message}")


def print_panel(title: str, content: str, style: str = "cyan") -> None:
    """Print content in a styled panel."""
    console.print(Panel(content, title=title, border_style=style))


def create_progress() -> Progress:
    """Create a progress bar for batch operations."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def print_plugins_table(plugins: list[dict]) -> None:
    """Print plugins in a formatted table.

    The table shows plugins in the order they will be tried.
    Position #1 is checked first; the first match wins.
    """
    if not plugins:
        print_warning("No plugins installed.")
        return

    table = Table(
        title="Installed Plugins",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", justify="right", style="bold")
    table.add_column("Name", style="green")
    table.add_column("Auth", justify="center")
    table.add_column("Lyrics Types")
    table.add_column("Description")

    for plugin in plugins:
        auth_badge = "[yellow]●[/yellow]" if plugin['requires_auth'] else "[dim]○[/dim]"

        pos_str = str(plugin.get('position', '?'))

        # Format lyrics types with color coding
        lyrics_types = plugin.get('lyrics_types', [])
        lyrics_badges = []
        for lt in lyrics_types:
            if lt == 'Rich Synced':
                lyrics_badges.append('[magenta]Rich[/magenta]')
            elif lt == 'Synced':
                lyrics_badges.append('[cyan]Synced[/cyan]')
            else:
                lyrics_badges.append('[dim]Plain[/dim]')
        lyrics_str = ', '.join(lyrics_badges) if lyrics_badges else '[dim]N/A[/dim]'

        table.add_row(
            pos_str,
            plugin['name'],
            auth_badge,
            lyrics_str,
            plugin.get('description', ''),
        )

    console.print(table)


def print_config_table(config: dict, title: str = "Current Configuration") -> None:
    """Print configuration in a formatted table."""
    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("Key", style="green")
    table.add_column("Value")

    def add_rows(d: dict, prefix: str = "") -> None:
        for key, value in d.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                add_rows(value, full_key)
            else:
                # Mask sensitive values
                if 'sp_dc' in key.lower() or 'token' in key.lower() or 'secret' in key.lower():
                    display_val = f"[dim]{'*' * 8}...{str(value)[-4:]}[/dim]" if value else "[dim]<not set>[/dim]"
                else:
                    display_val = str(value)
                table.add_row(full_key, display_val)

    add_rows(config)
    console.print(table)


def print_lyrics_result(response: LyricsResponse) -> None:
    """Print a single lyrics result."""
    console.print(
        f"  [success]✓[/success] {response.title} - [dim]{response.artist}[/dim]"
    )


def print_download_summary(successful: list[str], failed: list[str]) -> None:
    """Print download summary."""
    console.print()

    if successful:
        print_success(f"Downloaded lyrics for {len(successful)} tracks")

    if failed:
        print_warning(f"Failed to get lyrics for {len(failed)} tracks:")
        for track in failed:
            console.print(f"  [dim]- {track}[/dim]")


def confirm(message: str, default: bool = True) -> bool:
    """Ask for confirmation."""
    return questionary.confirm(message, default=default).ask() or False


def prompt_url(show_logo: bool = True) -> str | None:
    """Prompt for a URL.

    Args:
        show_logo: Whether to print the logo before prompting.
    """
    if show_logo:
        print_logo()
    return questionary.text(
        "Enter URL or path:",
        instruction="(Enter track/album/playlist URL, or local music folder)",
    ).ask()
