"""Command-line entry point: ``ledgerlens <group> <command>``."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from ledgerlens import __version__
from ledgerlens.companies import DEFAULT_COMPANIES, load_companies
from ledgerlens.config import get_settings
from ledgerlens.ingest.catalog import FilingsClient, select_annual_filings
from ledgerlens.ingest.download import download_filing
from ledgerlens.ingest.manifest import read_manifest, upsert, write_manifest

app = typer.Typer(
    help="LedgerLens: agentic RAG over European annual reports.", no_args_is_help=True
)
ingest_app = typer.Typer(help="Download and parse filings.", no_args_is_help=True)
app.add_typer(ingest_app, name="ingest")

console = Console()
MANIFEST = Path("data/manifest/filings_manifest.csv")
DEFAULT_YEARS = [2022, 2023, 2024, 2025]
USER_AGENT = f"ledgerlens/{__version__} (+https://github.com/huyj2001-ship-it/ledgerlens)"


@ingest_app.command("download")
def ingest_download(
    years: Annotated[list[int] | None, typer.Option("--year", help="Fiscal year(s).")] = None,
    lei: Annotated[list[str] | None, typer.Option(help="Only these LEIs.")] = None,
    companies_file: Annotated[Path, typer.Option("--companies")] = DEFAULT_COMPANIES,
    manifest: Annotated[Path, typer.Option()] = MANIFEST,
) -> None:
    """Download annual reports and their xBRL-JSON facts, and update the manifest."""
    settings = get_settings()
    wanted_years = years or DEFAULT_YEARS
    companies = [c for c in load_companies(companies_file) if not lei or c.lei in lei]
    rows = read_manifest(manifest)
    existing = {(r.lei, r.fiscal_year): r for r in rows}

    summary = Table("company", "year", "filing", "status")
    with FilingsClient(user_agent=USER_AGENT) as client:
        for company in companies:
            chosen = select_annual_filings(client.list_filings(company.lei), wanted_years)
            for year in wanted_years:
                record = chosen.get(year)
                if record is None:
                    summary.add_row(company.short_name, str(year), "-", "[yellow]no annual filing")
                    continue
                row, fetched = download_filing(
                    client,
                    record,
                    company.short_name,
                    settings.raw_dir,
                    existing=existing.get((company.lei, year)),
                )
                rows = upsert(rows, row)
                write_manifest(manifest, rows)  # persist progress after every filing
                size_mb = row.report_bytes / 1e6
                status = f"[green]downloaded {size_mb:.0f} MB" if fetched else "up to date"
                summary.add_row(company.short_name, str(year), record.filing_id, status)
    console.print(summary)


@app.command()
def version() -> None:
    """Print the installed version."""
    console.print(__version__)


if __name__ == "__main__":
    app()
