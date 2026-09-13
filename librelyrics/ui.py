"""Rich UI helpers for librelyrics CLI.

Provides styled console output, progress bars, and formatted displays.
"""
from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass, field

import questionary
from rich.console import Console
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

if sys.platform == "win32":
    for stream in filter(
        None,
        (
            sys.stdout,
            sys.stderr,
            getattr(sys, "__stdout__", None),
            getattr(sys, "__stderr__", None),
        ),
    ):
        stream.reconfigure(encoding="utf-8", errors="replace")

LIBRELYRICS_THEME = Theme({
    "info": "default",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "label": "dim",
    "value": "default",
    "accent": "cyan",
    "muted": "dim",
    "dim": "dim",
})

console = Console(file=sys.__stdout__, theme=LIBRELYRICS_THEME)

_LABEL_WIDTH = 9
_MAX_FAILED_LIST = 5


@dataclass
class FetchSummary:
    """Aggregated fetch/save results for end-of-session output."""

    successful: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    download_path: str | None = None
    total_tracks: int | None = None


LOGO = """[bold]
  _     _ _              _               _
 | |   (_) |__  _ __ ___| |   _   _ _ __(_) ___ ___
 | |   | | '_ \\| '__/ _ \\ |  | | | | '__| |/ __/ __|
 | |___| | |_) | | |  __/ |__| |_| | |  | | (__\\__ \\\\
 |_____|_|_.__/|_|  \\___|_____\\__, |_|  |_|\\___|___/
                              |___/
[/bold]
"""


def print_logo() -> None:
    """Print the LibreLyrics ASCII art logo."""
    console.print(LOGO)


def _header_row(label: str, value: str) -> None:
    console.print(f"  [label]{label:<{_LABEL_WIDTH}}[/label] {value}")


def print_session_header(
    *,
    kind: str,
    title: str,
    artist: str | None = None,
    album: str | None = None,
    owner: str | None = None,
    tracks: int | str | None = None,
    resolve_plugin: str | None = None,
    search_plugins: list[str] | None = None,
    source: str | None = None,
    quality: str | None = None,
) -> None:
    """Print a labeled session header for fetch operations."""
    console.print()
    _header_row(kind.capitalize(), title)
    if artist:
        _header_row("Artist", artist)
    if album:
        _header_row("Album", album)
    if owner:
        _header_row("Owner", owner)
    if tracks is not None:
        _header_row("Tracks", str(tracks))
    if resolve_plugin:
        _header_row("Resolve", resolve_plugin)
    if search_plugins:
        _header_row("Search", ", ".join(search_plugins))
    if source:
        _header_row("Source", source)
    if quality:
        _header_row("Quality", quality)
    console.print()


def print_success(message: str, *, label: str = "Saved") -> None:
    """Print a success message with an optional status label."""
    console.print(f"[success]{label}[/success]     {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[error]Error[/error]     {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[warning]Warning[/warning]   {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[info]Info[/info]      {message}")


def create_progress(transient: bool = False) -> Progress:
    """Create a progress bar for batch operations."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=28),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=transient,
    )


def format_progress_description(action: str, title: str = "", max_title_len: int = 28) -> str:
    """Format a progress task description."""
    if not title:
        return action
    if len(title) > max_title_len:
        title = title[: max_title_len - 3] + "..."
    return f"{action}  {title}"


def group_failure_reasons(failures: list[tuple[str, str]]) -> Counter[str]:
    """Count failures by normalized reason label."""
    return Counter(reason for _, reason in failures)


def format_grouped_reasons(reason_counts: Counter[str]) -> str:
    """Format grouped failure reasons for summary output."""
    parts = [f"{reason} x {count}" for reason, count in reason_counts.most_common()]
    return " · ".join(parts)


def print_fetch_summary(summary: FetchSummary, *, verbose: bool = False) -> None:
    """Print a single end-of-session summary with grouped failure reasons."""
    console.print()

    if summary.download_path and summary.successful:
        console.print(
            f"[success]Saved[/success]     {len(summary.successful)} "
            f"to [accent]{summary.download_path}[/accent]"
        )
    elif summary.successful:
        console.print(f"[success]Saved[/success]     {len(summary.successful)} tracks")

    if summary.skipped:
        console.print(f"[muted]Skipped[/muted]   {len(summary.skipped)} existing files")

    failed_count = len(summary.failed)
    if summary.total_tracks is not None and not summary.failed:
        inferred = summary.total_tracks - len(summary.successful) - len(summary.skipped)
        if inferred > 0:
            failed_count = inferred

    if failed_count > 0 or summary.failed:
        count = failed_count or len(summary.failed)
        reason_line = ""
        if summary.failed:
            reason_line = format_grouped_reasons(group_failure_reasons(summary.failed))
        if reason_line:
            console.print(f"[error]Failed[/error]    {count}  ·  {reason_line}")
        else:
            console.print(f"[error]Failed[/error]    {count}")

        show_all = verbose
        to_show = summary.failed if show_all else summary.failed[:_MAX_FAILED_LIST]
        for title, _reason in to_show:
            console.print(f"            [muted]{title}[/muted]")
        if not show_all and len(summary.failed) > _MAX_FAILED_LIST:
            remaining = len(summary.failed) - _MAX_FAILED_LIST
            console.print(f"            [muted]… and {remaining} more[/muted]")


def print_plugins_table(plugins: list[dict]) -> None:
    """Print plugins in a formatted table."""
    if not plugins:
        print_warning("No plugins installed.")
        return

    print_logo()
    table = Table(
        title="Installed plugins",
        show_header=True,
        header_style="bold",
        border_style="dim",
    )
    table.add_column("#", justify="right", style="muted")
    table.add_column("Id")
    table.add_column("Name")
    table.add_column("Auth", justify="center")
    table.add_column("Lyrics")
    table.add_column("Description", style="muted")

    for plugin in plugins:
        auth_badge = "[warning]yes[/warning]" if plugin["requires_auth"] else "[muted]no[/muted]"
        pos_str = str(plugin.get("position", "?"))

        lyrics_types = plugin.get("lyrics_types", [])
        lyrics_badges = []
        for lt in lyrics_types:
            if lt == "Rich Synced":
                lyrics_badges.append("Rich")
            elif lt == "Synced":
                lyrics_badges.append("Synced")
            else:
                lyrics_badges.append("Plain")
        lyrics_str = ", ".join(lyrics_badges) if lyrics_badges else "-"

        table.add_row(
            pos_str,
            plugin.get("id", ""),
            plugin["name"],
            auth_badge,
            lyrics_str,
            plugin.get("description", ""),
        )

    console.print(table)


def print_config_table(config: dict, title: str = "Configuration") -> None:
    """Print configuration in a formatted table."""
    print_logo()
    table = Table(title=title, show_header=True, header_style="bold", border_style="dim")
    table.add_column("Key", style="muted")
    table.add_column("Value")

    def add_rows(d: dict, prefix: str = "") -> None:
        for key, value in d.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                add_rows(value, full_key)
            else:
                table.add_row(full_key, str(value))

    add_rows(config)
    console.print(table)


def print_lyrics_result(response: LyricsResponse) -> None:
    """Print a single lyrics result."""
    console.print(f"  [success]ok[/success]  {response.title} - [muted]{response.artist}[/muted]")


def print_download_summary(successful: list[str], failed: list[str]) -> None:
    """Print download summary for simple flows."""
    summary = FetchSummary(
        successful=successful,
        failed=[(title, "Lyrics not found") for title in failed],
    )
    print_fetch_summary(summary)


def confirm(message: str, default: bool = True) -> bool:
    """Ask for confirmation."""
    return questionary.confirm(message, default=default).ask() or False


def prompt_url(show_logo: bool = True) -> str | None:
    """Prompt for a URL."""
    if show_logo:
        print_logo()
    return questionary.text(
        "Enter URL or path:",
        instruction="(track/album/playlist URL, or local music folder)",
    ).ask()
