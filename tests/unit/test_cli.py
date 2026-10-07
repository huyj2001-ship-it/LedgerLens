from typer.testing import CliRunner

from ledgerlens import __version__
from ledgerlens.cli import app

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_ingest_download_help_lists_options() -> None:
    result = runner.invoke(app, ["ingest", "download", "--help"])
    assert result.exit_code == 0
    assert "--year" in result.output
