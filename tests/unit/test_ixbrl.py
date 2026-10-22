from pathlib import Path

import pytest

from ledgerlens.ingest.ixbrl import (
    IX,
    XH,
    IxReport,
    PageMarkup,
    anchors_within,
    load_report,
    text_of,
)

MINI = Path(__file__).parents[1] / "fixtures" / "mini_ixbrl.xhtml"


@pytest.fixture(scope="module")
def report() -> IxReport:
    return load_report(MINI)


def test_pages_are_found_by_class(report: IxReport) -> None:
    markup, pages = report.pages()
    assert markup is PageMarkup.CLASS
    assert len(pages) == 3


def test_every_numeric_fact_gets_an_anchor(report: IxReport) -> None:
    anchors = list(report.anchors.values())
    assert len(anchors) == 11  # including the hidden fact and the one without an id
    assert anchors[0] == "h-1"
    assert "f-2" in anchors
    assert len(set(anchors)) == len(anchors)


def test_missing_id_gets_synthetic_anchor_by_document_order(report: IxReport) -> None:
    no_id = [el for el in report.root.iter(f"{IX}nonFraction") if el.get("id") is None]
    assert [report.anchors[el] for el in no_id] == ["ix-00004"]


def test_anchors_are_stable_across_loads(report: IxReport) -> None:
    again = load_report(MINI)
    assert list(again.anchors.values()) == list(report.anchors.values())


def test_text_excludes_hidden_content_and_separates_blocks(report: IxReport) -> None:
    text = text_of(report.body)
    assert "Invisible text" not in text
    assert "999.9" not in text  # hidden fact inside ix:header
    assert "ACME Annual Report 2024 Strategic report" in text


def test_anchors_within_a_table(report: IxReport) -> None:
    _, pages = report.pages()
    table = pages[1].find(f".//{XH}table")
    assert table is not None
    assert anchors_within(report, table)[:3] == ["f-1", "f-2", "f-3"]


def test_native_table_detection(report: IxReport) -> None:
    assert report.has_native_tables
