"""CLI startup and argument shaping."""
import sys

import pytest
from typer.testing import CliRunner

from librelyrics import cli
from librelyrics.cli import _normalize_cli_url, _normalize_fetch_argv, app

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


def test_main_accepts_bare_url_with_force_after(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_handle_fetch(url: str | None, **kwargs: object) -> int:
        seen["url"] = url
        seen["force"] = kwargs.get("force")
        return 0

    monkeypatch.setattr(cli, "handle_fetch", fake_handle_fetch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "librelyrics",
            "https://open.spotify.com/track/abc",
            "--force",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    assert seen.get("force") is True


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


def test_config_path_command() -> None:
    result = runner.invoke(app, ["config", "path"])
    assert result.exit_code == 0


def test_config_set_updates_value(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from librelyrics.config import ConfigManager

    config_path = tmp_path / "config.json"
    monkeypatch.setattr(
        "librelyrics.config.get_config_path",
        lambda: config_path,
    )
    result = runner.invoke(app, ["config", "set", "download_path", "cli-out"])
    assert result.exit_code == 0
    cm = ConfigManager(config_path=config_path)
    assert cm.get("download_path") == "cli-out"


def test_fetch_exit_code_on_validation_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "handle_fetch", lambda *a, **k: 1)
    result = runner.invoke(
        app,
        ["fetch", "https://example.com/track/1", "--direct", "--from", "alpha"],
    )
    assert result.exit_code == 1


def test_fetch_directory_flag_passed_to_handle_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_handle_fetch(url: str | None, **kwargs: object) -> int:
        seen["directory"] = kwargs.get("directory")
        return 0

    monkeypatch.setattr(cli, "handle_fetch", fake_handle_fetch)
    result = runner.invoke(
        app,
        ["--directory", "mydir", "fetch", "https://example.com/track/1"],
    )
    assert result.exit_code == 0
    assert seen["directory"] == "mydir"


def test_normalize_fetch_argv_promotes_root_flags_after_url() -> None:
    url = "https://open.spotify.com/track/abc"
    args = [url, "--force", "-v"]
    normalized = _normalize_fetch_argv(args)
    assert normalized[0] in {"--force", "-f"}
    assert "fetch" in normalized
    assert url in normalized


def test_normalize_fetch_argv_metadata_only() -> None:
    args = ["--artist", "Ed Sheeran", "--title", "Thinking Out Loud"]
    normalized = _normalize_fetch_argv(args)
    assert normalized[0] == "fetch"
    assert "--artist" in normalized
    assert "--title" in normalized


def test_normalize_fetch_argv_preserves_config_subcommand() -> None:
    args = ["config", "show"]
    assert _normalize_fetch_argv(args) == args


def test_fetch_force_flag_passed_to_handle_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_handle_fetch(url: str | None, **kwargs: object) -> int:
        seen["force"] = kwargs.get("force")
        return 0

    monkeypatch.setattr(cli, "handle_fetch", fake_handle_fetch)
    result = runner.invoke(
        app,
        ["--force", "fetch", "https://example.com/track/1"],
    )
    assert result.exit_code == 0
    assert seen["force"] is True

