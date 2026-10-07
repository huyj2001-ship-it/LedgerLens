"""The filings manifest: a committed CSV that pins exactly which source files were used.

Raw reports are never committed (they are company documents), but anyone can re-download them
and check the sha256 values here to reproduce the corpus byte for byte.
"""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel


class ManifestRow(BaseModel):
    lei: str
    company: str
    fiscal_year: int
    period_end: date
    filing_id: str
    report_url: str
    json_url: str
    report_sha256: str
    report_bytes: int
    json_sha256: str
    json_bytes: int
    processed: datetime | None
    fetched_at: datetime

    @property
    def report_id(self) -> str:
        """Stable identifier used throughout the pipeline, e.g. ``724500Y6DUVHQD6OXN27_2024``."""
        return f"{self.lei}_{self.fiscal_year}"


FIELDS = list(ManifestRow.model_fields)


def read_manifest(path: Path) -> list[ManifestRow]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return [
            ManifestRow.model_validate({k: (v or None) for k, v in row.items()})
            for row in csv.DictReader(fh)
        ]


def write_manifest(path: Path, rows: list[ManifestRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda r: (r.company.lower(), r.fiscal_year))
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in ordered:
            writer.writerow(row.model_dump(mode="json"))


def upsert(rows: list[ManifestRow], new: ManifestRow) -> list[ManifestRow]:
    """Replace the row for the same (lei, fiscal_year), or append it."""
    kept = [r for r in rows if (r.lei, r.fiscal_year) != (new.lei, new.fiscal_year)]
    return [*kept, new]
