from decimal import Decimal
from pathlib import Path

import pytest

from ledgerlens.ingest.ixbrl import load_report
from ledgerlens_eval.facts import (
    Fact,
    FormatError,
    SkippedFact,
    parse_numeric_facts,
    read_transform,
)

EDGE = Path(__file__).parents[1] / "fixtures" / "ixbrl_edge_cases.xhtml"


@pytest.fixture(scope="module")
def parsed() -> tuple[dict[str, Fact], dict[str, SkippedFact]]:
    facts, skipped = parse_numeric_facts(load_report(EDGE))
    return {f.anchor: f for f in facts}, {s.anchor: s for s in skipped}


@pytest.mark.parametrize(
    ("fmt", "displayed", "expected"),
    [
        ("ixt:num-dot-decimal", "1,234.5", "1234.5"),
        ("ixt:num-dot-decimal", "1 234.5", "1234.5"),
        ("ixt:num-dot-decimal", "1\u00a0234", "1234"),
        ("ixt3:numdotdecimal", "176,954", "176954"),
        ("ixt:num-comma-decimal", "3.456.789,0", "3456789.0"),
        ("ixt:fixed-zero", "-", "0"),
        ("ixt3:zerodash", "\u2013", "0"),
        ("ixt:num-unit-decimal", "12 kr 50", "12.50"),
        (None, " 16.08 ", "16.08"),
    ],
)
def test_read_transform(fmt: str | None, displayed: str, expected: str) -> None:
    assert read_transform(fmt, displayed) == Decimal(expected)


def test_unsupported_transform_raises() -> None:
    with pytest.raises(FormatError, match="unsupported"):
        read_transform("ixt:date-day-month-year", "1 January 2024")


def test_garbage_in_plain_decimal_raises() -> None:
    with pytest.raises(FormatError):
        read_transform(None, "n/a")


def test_non_standard_ifrs_prefix_is_canonicalised(
    parsed: tuple[dict[str, Fact], dict[str, SkippedFact]],
) -> None:
    facts, _ = parsed
    assert facts["tr3-dot"].concept == "ifrs-full:Revenue"
    assert facts["tr3-dot"].value == Decimal("176954000000")
    assert facts["tr3-dot"].unit == "iso4217:DKK"


def test_typed_dimension_and_large_scale(
    parsed: tuple[dict[str, Fact], dict[str, SkippedFact]],
) -> None:
    facts, _ = parsed
    assets = facts["tr3-comma"]
    assert assets.value == Decimal("1234500000000")
    assert assets.dims == (("co:PlantAxis", "42"),)


def test_nested_markup_inside_a_fact(
    parsed: tuple[dict[str, Fact], dict[str, SkippedFact]],
) -> None:
    facts, _ = parsed
    assert facts["nested"].value == Decimal("0.25")
    assert facts["nested"].decimals is None  # INF
    assert facts["nested"].unit == "xbrli:pure"


def test_problem_facts_are_skipped_with_reasons(
    parsed: tuple[dict[str, Fact], dict[str, SkippedFact]],
) -> None:
    facts, skipped = parsed
    assert set(skipped) == {"nil", "odd", "dangling"}
    assert skipped["nil"].reason == "nil"
    assert "unsupported" in skipped["odd"].reason
    assert "context" in skipped["dangling"].reason
    assert {"tr3-zero", "unit-dec"} <= set(facts)
