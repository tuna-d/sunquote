"""Applies the Alembic migrations that ship inside the package."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def alembic_config(connection: Connection) -> Config:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    # `migrations/env.py` runs on this connection instead of opening its own.
    config.attributes["connection"] = connection
    return config


async def upgrade_to_head(engine: AsyncEngine) -> None:
    """Bring the database schema up to date. Safe to run on every start."""

    def upgrade(connection: Connection) -> None:
        command.upgrade(alembic_config(connection), "head")

    async with engine.begin() as connection:
        await connection.run_sync(upgrade)
