import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
import respx

from ledgerlens.ingest.catalog import FilingRecord, FilingsClient
from ledgerlens.ingest.download import download_filing, report_path, sha256_file
from ledgerlens.ingest.manifest import ManifestRow, read_manifest, upsert, write_manifest

LEI = "724500Y6DUVHQD6OXN27"
REPORT = b"<html>report</html>" * 1000
FACTS = b'{"facts": {}}'


def make_record(filing_id: str = f"{LEI}-2024-12-31-ESEF-NL-0") -> FilingRecord:
    return FilingRecord(
        api_id="1",
        filing_id=filing_id,
        lei=LEI,
        period_end=date(2024, 12, 31),
        country="NL",
        error_count=0,
        report_url="/r/report.xhtml",
        json_url="/r/report.json",
        package_url=None,
        processed=datetime(2025, 3, 6, 13, 27),
    )


@pytest.fixture
def client() -> FilingsClient:
    return FilingsClient(user_agent="test", min_interval=0, sleep=lambda _: None)


@pytest.fixture
def mocked() -> respx.MockRouter:
    with respx.mock(base_url="https://filings.xbrl.org") as router:
        router.get("/r/report.xhtml").respond(content=REPORT)
        router.get("/r/report.json").respond(content=FACTS)
        yield router


def test_download_writes_files_and_hashes(
    client: FilingsClient, mocked: respx.MockRouter, tmp_path: Path
) -> None:
    row, fetched = download_filing(client, make_record(), "ASML", tmp_path)

    assert fetched
    path = report_path(tmp_path, LEI, 2024)
    assert path.read_bytes() == REPORT
    assert row.report_sha256 == hashlib.sha256(REPORT).hexdigest() == sha256_file(path)
    assert row.report_bytes == len(REPORT)
    assert row.report_id == f"{LEI}_2024"
    assert not path.with_name("report.xhtml.part").exists()


def test_second_download_is_skipped_when_hashes_match(
    client: FilingsClient, mocked: respx.MockRouter, tmp_path: Path
) -> None:
    first, _ = download_filing(client, make_record(), "ASML", tmp_path)
    second, fetched = download_filing(client, make_record(), "ASML", tmp_path, existing=first)
    assert not fetched
    assert second == first
    assert mocked.calls.call_count == 2  # only the first run hit the network


def test_corrupted_file_is_downloaded_again(
    client: FilingsClient, mocked: respx.MockRouter, tmp_path: Path
) -> None:
    first, _ = download_filing(client, make_record(), "ASML", tmp_path)
    report_path(tmp_path, LEI, 2024).write_bytes(b"truncated")
    _, fetched = download_filing(client, make_record(), "ASML", tmp_path, existing=first)
    assert fetched


def test_failed_download_leaves_no_partial_file(client: FilingsClient, tmp_path: Path) -> None:
    with respx.mock(base_url="https://filings.xbrl.org") as router:
        router.get("/r/report.xhtml").respond(404)
        with pytest.raises(httpx.HTTPStatusError):
            download_filing(client, make_record(), "ASML", tmp_path)
    assert not report_path(tmp_path, LEI, 2024).exists()


def test_manifest_round_trip_and_upsert(tmp_path: Path) -> None:
    row = ManifestRow(
        lei=LEI,
        company="ASML",
        fiscal_year=2024,
        period_end=date(2024, 12, 31),
        filing_id="f",
        report_url="https://x/r.xhtml",
        json_url="https://x/r.json",
        report_sha256="a" * 64,
        report_bytes=1,
        json_sha256="b" * 64,
        json_bytes=2,
        processed=None,
        fetched_at=datetime(2026, 10, 1, tzinfo=UTC),
    )
    path = tmp_path / "manifest.csv"
    write_manifest(path, [row])
    assert read_manifest(path) == [row]

    newer = row.model_copy(update={"filing_id": "g"})
    rows = upsert(read_manifest(path), newer)
    assert [r.filing_id for r in rows] == ["g"]
