"""Applies the Alembic migrations that ship inside the package."""

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from sunquote.adapters.postgres.quote_repository import create_engine
from sunquote.config import Settings

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


async def migrate_database(database_url: str) -> None:
    """Migrate the database at `database_url` to head, on a connection of its own.

    This is what CI runs against production, so the engine has no client pool.
    """
    engine = create_engine(database_url, client_pool=False)
    try:
        await upgrade_to_head(engine)
    finally:
        await engine.dispose()


def main() -> None:
    """`python -m sunquote.adapters.postgres.migrate`: migrate `SUNQUOTE_DATABASE_URL`."""
    settings = Settings()
    asyncio.run(migrate_database(settings.database_url))
    print("Database migrated to head.")


if __name__ == "__main__":
    main()
