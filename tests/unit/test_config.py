from pathlib import Path

import pytest

from ledgerlens.config import Settings


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Run from an empty directory so a developer's real .env is never read.
    monkeypatch.chdir(tmp_path)
    for name in ("DEEPSEEK_API_KEY", "LEDGERLENS_DEEPSEEK_API_KEY", "LEDGERLENS_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)


def test_defaults() -> None:
    settings = Settings()
    assert settings.data_dir == Path("data")
    assert settings.raw_dir == Path("data/raw")
    assert settings.gold_dir == Path("data/gold")
    assert settings.deepseek_api_key is None


def test_conventional_key_name_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-123")
    settings = Settings()
    assert settings.deepseek_api_key is not None
    assert settings.deepseek_api_key.get_secret_value() == "sk-test-123"


def test_secret_is_not_leaked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-123")
    assert "sk-test-123" not in repr(Settings())


def test_prefixed_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LEDGERLENS_DATA_DIR", str(tmp_path / "elsewhere"))
    assert Settings().interim_dir == tmp_path / "elsewhere" / "interim"


def test_reads_dotenv_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=sk-from-file\n", encoding="utf-8")
    key = Settings().deepseek_api_key
    assert key is not None
    assert key.get_secret_value() == "sk-from-file"
