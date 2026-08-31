"""CLI startup and argument shaping."""
import sys

import pytest
from typer.testing import CliRunner

from librelyrics import cli
from librelyrics.cli import _normalize_cli_url, app

runner = CliRunner()


def test_help_builds() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Fetch lyrics" in result.output


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0


def test_fetch_help_includes_url_argument() -> None:
    result = runner.invoke(app, ["fetch", "--help"])
    assert result.exit_code == 0
    assert "URL" in result.output or "url" in result.output.lower()


def test_main_accepts_bare_url(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str | None] = {}

    def fake_handle_fetch(url: str | None, **kwargs: object) -> int:
        seen["url"] = url
        return 0

    monkeypatch.setattr(cli, "handle_fetch", fake_handle_fetch)
    monkeypatch.setattr(
        sys,
        "argv",
        ["librelyrics", "https://open.spotify.com/album/2S8ZSnpmlReMfteHNp3zju\\"],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    assert seen["url"] is not None
    assert "2S8ZSnpmlReMfteHNp3zju" in seen["url"]


def test_normalize_strips_powershell_backslash() -> None:
    url = "https://open.spotify.com/album/2S8ZSnpmlReMfteHNp3zju\\"
    assert _normalize_cli_url(url) == (
        "https://open.spotify.com/album/2S8ZSnpmlReMfteHNp3zju"
    )
    assert _normalize_cli_url(None) is None


def test_logo_prints_ascii_art() -> None:
    import io

    from rich.console import Console

    from librelyrics import ui as ui_module
    from librelyrics.ui import print_logo

    buffer = io.StringIO()
    original = ui_module.console
    ui_module.console = Console(file=buffer, width=120)
    try:
        print_logo()
        output = buffer.getvalue()
    finally:
        ui_module.console = original

    assert "_     _ _" in output
    assert "|___|" in output


def test_plugin_display_name_uses_meta_name() -> None:
    from librelyrics.cli import _plugin_display_name
    from tests.fakes import SearchAlpha

    assert _plugin_display_name([SearchAlpha], "alpha") == "Alpha"
    assert _plugin_display_name([SearchAlpha], "missing") == "missing"
