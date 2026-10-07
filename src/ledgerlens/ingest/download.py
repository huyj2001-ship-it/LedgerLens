"""Download annual reports (XHTML) and their xBRL-JSON renderings to ``data/raw``."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from ledgerlens.ingest.catalog import FilingRecord, FilingsClient
from ledgerlens.ingest.manifest import ManifestRow

_CHUNK = 1 << 20


def filing_dir(raw_dir: Path, lei: str, fiscal_year: int) -> Path:
    return raw_dir / "filings" / lei / str(fiscal_year)


def report_path(raw_dir: Path, lei: str, fiscal_year: int) -> Path:
    return filing_dir(raw_dir, lei, fiscal_year) / "report.xhtml"


def facts_json_path(raw_dir: Path, lei: str, fiscal_year: int) -> Path:
    return filing_dir(raw_dir, lei, fiscal_year) / "report.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _is_current(path: Path, expected_sha: str | None) -> bool:
    return expected_sha is not None and path.exists() and sha256_file(path) == expected_sha


def download_filing(
    client: FilingsClient,
    record: FilingRecord,
    company: str,
    raw_dir: Path,
    *,
    existing: ManifestRow | None = None,
) -> tuple[ManifestRow, bool]:
    """Fetch one filing. Returns the manifest row and whether anything was downloaded.

    Files already on disk are kept when they belong to the same filing and their hashes match
    the manifest, so re-running the command is cheap and idempotent.
    """
    if record.report_url is None or record.json_url is None:
        raise ValueError(f"{record.filing_id} has no report or JSON URL")

    xhtml = report_path(raw_dir, record.lei, record.fiscal_year)
    facts = facts_json_path(raw_dir, record.lei, record.fiscal_year)
    same_filing = existing is not None and existing.filing_id == record.filing_id
    if (
        same_filing
        and existing is not None
        and _is_current(xhtml, existing.report_sha256)
        and _is_current(facts, existing.json_sha256)
    ):
        return existing, False

    report_sha, report_bytes = client.download(record.report_url, xhtml)
    json_sha, json_bytes = client.download(record.json_url, facts)
    row = ManifestRow(
        lei=record.lei,
        company=company,
        fiscal_year=record.fiscal_year,
        period_end=record.period_end,
        filing_id=record.filing_id,
        report_url=client.url(record.report_url),
        json_url=client.url(record.json_url),
        report_sha256=report_sha,
        report_bytes=report_bytes,
        json_sha256=json_sha,
        json_bytes=json_bytes,
        processed=record.processed,
        fetched_at=datetime.now(UTC).replace(microsecond=0),
    )
    return row, True
