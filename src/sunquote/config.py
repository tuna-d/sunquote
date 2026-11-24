"""Runtime configuration, read from environment variables (and an optional local `.env`)."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    pvgis_base_url: str = "https://re.jrc.ec.europa.eu/api/v5_3"
    pvgis_timeout_seconds: float = Field(default=10.0, gt=0)

    # TCMB publishes the daily exchange rate files at <base>/<YYYYMM>/<DDMMYYYY>.xml. No key.
    tcmb_base_url: str = "https://www.tcmb.gov.tr/kurlar"
    tcmb_timeout_seconds: float = Field(default=10.0, gt=0)
