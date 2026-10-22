from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ledgerlens.ingest.ixbrl import load_report
from ledgerlens_eval.facts import Fact, parse_numeric_facts

MINI = Path(__file__).parents[1] / "fixtures" / "mini_ixbrl.xhtml"


@pytest.fixture(scope="module")
def facts() -> dict[str, Fact]:
    parsed, skipped = parse_numeric_facts(load_report(MINI))
    assert skipped == []
    return {f.anchor: f for f in parsed}


def test_scale_is_applied(facts: dict[str, Fact]) -> None:
    revenue = facts["f-2"]
    assert revenue.concept == "ifrs-full:Revenue"
    assert revenue.value == Decimal("1500000000")
    assert revenue.unit == "iso4217:EUR"
    assert revenue.decimals == -5
    assert (revenue.period_start, revenue.period_end) == (date(2024, 1, 1), date(2024, 12, 31))


def test_parentheses_are_presentation_not_sign(facts: dict[str, Fact]) -> None:
    # "(700.0)" in the table, but the concept is a positive cost: no sign attribute.
    assert facts["f-3"].value == Decimal("700000000")
    assert not facts["f-3"].negated


def test_sign_attribute_negates(facts: dict[str, Fact]) -> None:
    assert facts["f-5"].value == Decimal("-12300000")
    assert facts["f-5"].negated


def test_fixed_zero(facts: dict[str, Fact]) -> None:
    assert facts["f-6"].value == 0


def test_no_format_means_plain_decimal_and_divide_unit(facts: dict[str, Fact]) -> None:
    eps = facts["f-8"]
    assert eps.value == Decimal("1.75")
    assert eps.unit == "iso4217:EUR/xbrli:shares"
    assert eps.scale == 0


def test_comma_decimal_and_instant_period(facts: dict[str, Fact]) -> None:
    assets = facts["f-9"]
    assert assets.value == Decimal("3456789000")
    assert assets.is_instant
    assert assets.period_end == date(2024, 12, 31)


def test_dimensions_are_canonicalised(facts: dict[str, Fact]) -> None:
    europe = facts["f-10"]
    assert europe.dims == (("ifrs-full:SegmentsAxis", "acme:EuropeMember"),)
    assert europe.has_dimensions


def test_hidden_fact_is_parsed_and_flagged(facts: dict[str, Fact]) -> None:
    assert facts["h-1"].hidden
    assert not facts["f-2"].hidden


def test_fact_without_id_uses_synthetic_anchor(facts: dict[str, Fact]) -> None:
    assert facts["ix-00004"].value == Decimal("800100000")
