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

    # Directory holding `catalog.toml` and `assumptions.toml`. None means the placeholder
    # files that ship inside the package.
    data_dir: Path | None = None

    pvgis_base_url: str = "https://re.jrc.ec.europa.eu/api/v5_3"
    pvgis_timeout_seconds: float = Field(default=10.0, gt=0)
