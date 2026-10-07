from pathlib import Path

import pytest

from ledgerlens.companies import load_companies


def test_config_loads_and_has_unique_valid_leis() -> None:
    companies = load_companies(Path("configs/companies.yaml"))
    assert len(companies) >= 5
    assert all(len(c.lei) == 20 for c in companies)
    asml = next(c for c in companies if c.short_name == "ASML")
    assert asml.currency == "EUR"
    assert "ASML Holding" in asml.all_names


def test_duplicate_lei_is_rejected(tmp_path: Path) -> None:
    entry = (
        "  - {lei: AAAAAAAAAAAAAAAAAAAA, name: A, short_name: A, country: NL,"
        " currency: EUR, sector: x}\n"
    )
    path = tmp_path / "c.yaml"
    path.write_text("companies:\n" + entry * 2, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate LEI"):
        load_companies(path)
