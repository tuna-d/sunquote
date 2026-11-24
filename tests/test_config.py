from pathlib import Path

import pytest
from pydantic import ValidationError

from sunquote.config import Settings


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No SUNQUOTE_* variables and no .env file in the working directory."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SUNQUOTE_LOG_LEVEL", raising=False)
    monkeypatch.delenv("SUNQUOTE_REDIS_URL", raising=False)


def test_defaults_let_the_service_start_without_any_configuration() -> None:
    assert Settings().log_level == "INFO"
    assert Settings().redis_url is None


def test_reads_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUNQUOTE_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("SUNQUOTE_REDIS_URL", "redis://localhost:6379/0")

    assert Settings().log_level == "DEBUG"
    assert Settings().redis_url == "redis://localhost:6379/0"


def test_reads_dotenv_file_in_working_directory(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SUNQUOTE_LOG_LEVEL=WARNING\n", encoding="utf-8")

    assert Settings().log_level == "WARNING"


def test_rejects_unknown_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUNQUOTE_LOG_LEVEL", "LOUD")

    with pytest.raises(ValidationError):
        Settings()


def test_env_example_documents_every_setting() -> None:
    env_example = Path(__file__).resolve().parents[1] / ".env.example"
    documented = {
        line.removeprefix("#").strip().split("=", 1)[0]
        for line in env_example.read_text(encoding="utf-8").splitlines()
        if "=" in line
    }

    expected = {f"SUNQUOTE_{name.upper()}" for name in Settings.model_fields}
    assert expected <= documented
