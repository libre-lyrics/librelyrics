"""CLI startup and argument shaping."""
from typer.testing import CliRunner

from librelyrics.cli import _normalize_cli_url, app

runner = CliRunner()


def test_help_builds() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Fetch lyrics" in result.output


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "librelyrics" in result.output


def test_normalize_strips_powershell_backslash() -> None:
    url = "https://open.spotify.com/album/2S8ZSnpmlReMfteHNp3zju\\"
    assert _normalize_cli_url(url) == (
        "https://open.spotify.com/album/2S8ZSnpmlReMfteHNp3zju"
    )
    assert _normalize_cli_url(None) is None
