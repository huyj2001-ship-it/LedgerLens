"""The company universe, loaded from ``configs/companies.yaml``."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

DEFAULT_COMPANIES = Path("configs/companies.yaml")


class Company(BaseModel):
    lei: str = Field(min_length=20, max_length=20)
    name: str
    short_name: str
    aliases: list[str] = Field(default_factory=list)
    country: str
    currency: str
    sector: str

    @property
    def all_names(self) -> list[str]:
        return [self.short_name, self.name, *self.aliases]


def load_companies(path: Path = DEFAULT_COMPANIES) -> list[Company]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    companies = [Company.model_validate(item) for item in data["companies"]]
    leis = [c.lei for c in companies]
    if len(set(leis)) != len(leis):
        raise ValueError(f"duplicate LEI in {path}")
    return companies
