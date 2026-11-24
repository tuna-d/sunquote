"""Runtime configuration, read from environment variables (and an optional local `.env`)."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from sunquote.adapters.gemini import DEFAULT_GEMINI_BASE_URL, DEFAULT_GEMINI_MODEL
from sunquote.domain.conversation import DEFAULT_ASSISTANT_BUDGET_SECONDS
from sunquote.domain.service import DEFAULT_NARRATIVE_BUDGET_SECONDS


class Settings(BaseSettings):
    """Every setting has a default, so the service starts without any `.env`.

    Each field `name` is read from the environment variable `SUNQUOTE_<NAME>`. Keep
    `.env.example` in step with this class.
    """

    model_config = SettingsConfigDict(
        env_prefix="SUNQUOTE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # Directory holding `catalog.toml`, `assumptions.toml` and `tariff.toml`. None means the
    # placeholder files that ship inside the package.
    data_dir: Path | None = None

    # Where Quotes are stored. The default matches the Postgres service in `compose.yaml` when
    # its port is published on localhost. Compose passes the in-network address instead.
    database_url: str = "postgresql+asyncpg://sunquote:sunquote@localhost:5432/sunquote"
    # Apply the Alembic migrations when the app starts.
    migrate_on_startup: bool = True

    # Cache external lookups only when a Redis URL is supplied.
    redis_url: str | None = None

    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    nominatim_timeout_seconds: float = Field(default=10.0, gt=0)

    pvgis_base_url: str = "https://re.jrc.ec.europa.eu/api/v5_3"
    pvgis_timeout_seconds: float = Field(default=10.0, gt=0)

    # TCMB publishes the daily exchange rate files at <base>/<YYYYMM>/<DDMMYYYY>.xml. No key.
    tcmb_base_url: str = "https://www.tcmb.gov.tr/kurlar"
    tcmb_timeout_seconds: float = Field(default=10.0, gt=0)

    # Total time the Narrative writer gets for both of its attempts when a Quote is created.
    # Past it the Quote records the fixed text and is still created.
    narrative_timeout_seconds: float = Field(default=DEFAULT_NARRATIVE_BUDGET_SECONDS, gt=0)

    # The LLM that writes the Narrative. The writer is wired only when a key is set; without
    # one every Quote shows the fixed text. The key is a secret: it stays out of reprs and logs.
    gemini_api_key: SecretStr | None = None
    # A model on Gemini's free tier; the default and the date it was checked are documented at
    # `sunquote.adapters.gemini.DEFAULT_GEMINI_MODEL`.
    gemini_model: str = DEFAULT_GEMINI_MODEL
    # Per-request timeout of the Gemini call; the Narrative budget above bounds both attempts.
    gemini_timeout_seconds: float = Field(default=10.0, gt=0)
    gemini_base_url: str = DEFAULT_GEMINI_BASE_URL

    # Total time one assistant request gets for its model calls and the Quote creation between
    # them. Past it, a request that already created a Quote gets the fixed confirmation.
    assistant_timeout_seconds: float = Field(default=DEFAULT_ASSISTANT_BUDGET_SECONDS, gt=0)

    @field_validator("gemini_api_key", mode="before")
    @classmethod
    def _blank_key_is_no_key(cls, value: object) -> object:
        """Docker Compose passes an unset variable as an empty string: that means no key."""
        if isinstance(value, str) and not value.strip():
            return None
        return value
