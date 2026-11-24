from pathlib import Path

import pytest
from pydantic import ValidationError

from sunquote.config import Settings


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No SUNQUOTE_* variables and no .env file in the working directory."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SUNQUOTE_LOG_LEVEL", raising=False)


def test_defaults_let_the_service_start_without_any_configuration() -> None:
    assert Settings().log_level == "INFO"


def test_reads_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUNQUOTE_LOG_LEVEL", "DEBUG")

    assert Settings().log_level == "DEBUG"


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
