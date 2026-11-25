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
    for name in ("API_KEY", "MODEL", "TIMEOUT_SECONDS", "BASE_URL"):
        monkeypatch.delenv(f"SUNQUOTE_GEMINI_{name}", raising=False)


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


def test_the_narrative_time_budget_defaults_to_fifteen_seconds_and_must_be_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Settings().narrative_timeout_seconds == 15

    monkeypatch.setenv("SUNQUOTE_NARRATIVE_TIMEOUT_SECONDS", "4.5")
    assert Settings().narrative_timeout_seconds == 4.5

    monkeypatch.setenv("SUNQUOTE_NARRATIVE_TIMEOUT_SECONDS", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_gemini_settings_default_to_no_key_and_a_free_tier_model() -> None:
    settings = Settings()

    assert settings.gemini_api_key is None
    assert settings.gemini_model == "gemini-3.5-flash-lite"
    assert settings.gemini_timeout_seconds == 10
    assert settings.gemini_base_url == "https://generativelanguage.googleapis.com/v1beta"


def test_gemini_settings_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUNQUOTE_GEMINI_API_KEY", "key-123")
    monkeypatch.setenv("SUNQUOTE_GEMINI_MODEL", "gemini-3.1-flash-lite")
    monkeypatch.setenv("SUNQUOTE_GEMINI_TIMEOUT_SECONDS", "7.5")

    settings = Settings()

    assert settings.gemini_api_key is not None
    assert settings.gemini_api_key.get_secret_value() == "key-123"
    assert settings.gemini_model == "gemini-3.1-flash-lite"
    assert settings.gemini_timeout_seconds == 7.5


def test_a_blank_gemini_key_counts_as_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # Docker Compose passes an unset variable through as an empty string.
    monkeypatch.setenv("SUNQUOTE_GEMINI_API_KEY", "  ")

    assert Settings().gemini_api_key is None


def test_the_gemini_key_is_masked_in_the_settings_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUNQUOTE_GEMINI_API_KEY", "key-123-secret")

    settings = Settings()

    assert "key-123-secret" not in repr(settings)
    assert "key-123-secret" not in str(settings)


def test_the_gemini_timeout_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUNQUOTE_GEMINI_TIMEOUT_SECONDS", "0")

    with pytest.raises(ValidationError):
        Settings()


def test_the_assistant_time_budget_defaults_to_thirty_seconds_and_must_be_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Settings().assistant_timeout_seconds == 30

    monkeypatch.setenv("SUNQUOTE_ASSISTANT_TIMEOUT_SECONDS", "12.5")
    assert Settings().assistant_timeout_seconds == 12.5

    monkeypatch.setenv("SUNQUOTE_ASSISTANT_TIMEOUT_SECONDS", "0")
    with pytest.raises(ValidationError):
        Settings()


def test_the_database_keeps_a_client_pool_by_default_and_can_drop_it_for_serverless(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Settings().database_client_pool is True

    monkeypatch.setenv("SUNQUOTE_DATABASE_CLIENT_POOL", "false")
    assert Settings().database_client_pool is False


def test_the_redis_timeout_defaults_to_a_quarter_second_and_must_be_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Settings().redis_timeout_seconds == 0.25

    monkeypatch.setenv("SUNQUOTE_REDIS_TIMEOUT_SECONDS", "1.5")
    assert Settings().redis_timeout_seconds == 1.5

    monkeypatch.setenv("SUNQUOTE_REDIS_TIMEOUT_SECONDS", "0")
    with pytest.raises(ValidationError):
        Settings()
