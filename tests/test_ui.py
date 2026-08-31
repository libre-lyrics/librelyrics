from collections import Counter

from librelyrics.ui import (
    FetchSummary,
    format_grouped_reasons,
    group_failure_reasons,
    print_fetch_summary,
)
from rich.console import Console


def test_group_failure_reasons_counts() -> None:
    failures = [
        ("Ed Sheeran - Sing", "HTTP 429"),
        ("Ed Sheeran - One", "HTTP 429"),
        ("Ed Sheeran - Nina", "Lyrics not found"),
    ]
    counts = group_failure_reasons(failures)
    assert counts == Counter({"HTTP 429": 2, "Lyrics not found": 1})


def test_format_grouped_reasons_orders_by_frequency() -> None:
    counts = Counter({"HTTP 429": 46, "Lyrics not found": 3})
    text = format_grouped_reasons(counts)
    assert text == "HTTP 429 x 46 · Lyrics not found x 3"


def test_print_fetch_summary_truncates_failed_list(capsys) -> None:
    failures = [(f"Track {index}", "HTTP 429") for index in range(8)]
    summary = FetchSummary(
        successful=[],
        failed=failures,
        download_path="downloads",
        total_tracks=8,
    )
    console = Console(file=__import__("io").StringIO(), width=120)
    from librelyrics import ui as ui_module

    original = ui_module.console
    ui_module.console = console
    try:
        print_fetch_summary(summary, verbose=False)
        output = console.file.getvalue()
    finally:
        ui_module.console = original

    assert "Failed" in output
    assert "HTTP 429 x 8" in output
    assert "Track 0" in output
    assert "and 3 more" in output
