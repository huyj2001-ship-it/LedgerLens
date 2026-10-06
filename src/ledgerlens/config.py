"""Typed runtime configuration loaded from environment variables and ``.env``."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All settings can be overridden with ``LEDGERLENS_<NAME>`` environment variables.

    Provider API keys also accept their conventional names (e.g. ``DEEPSEEK_API_KEY``).
    """

    model_config = SettingsConfigDict(
        env_prefix="LEDGERLENS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Path("data")
    log_level: str = "INFO"

    deepseek_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("LEDGERLENS_DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY"),
    )
    mistral_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("LEDGERLENS_MISTRAL_API_KEY", "MISTRAL_API_KEY"),
    )

    @property
    def raw_dir(self) -> Path:
        """Downloaded source files (reports, FX rates). Never committed."""
        return self.data_dir / "raw"

    @property
    def interim_dir(self) -> Path:
        """Derived artefacts such as parsed blocks and chunks."""
        return self.data_dir / "interim"

    @property
    def gold_dir(self) -> Path:
        """Answer-key artefacts. Only ``ledgerlens_eval`` reads from here."""
        return self.data_dir / "gold"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
