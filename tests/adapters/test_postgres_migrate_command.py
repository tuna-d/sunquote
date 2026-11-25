"""The command CI runs to migrate production: `python -m sunquote.adapters.postgres.migrate`.

Needs a database server (`SUNQUOTE_TEST_DATABASE_URL`, as the repository tests do). Each test
migrates a database of its own, created and dropped here.
"""

import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from sunquote.adapters.postgres.migrate import migrate_database

pytestmark = pytest.mark.anyio

SERVER_URL = os.environ.get("SUNQUOTE_TEST_DATABASE_URL")


@pytest.fixture
async def empty_database_url() -> AsyncIterator[str]:
    if not SERVER_URL:
        pytest.skip("SUNQUOTE_TEST_DATABASE_URL is not set")
    name = f"migrate_{uuid4().hex}"
    admin = create_async_engine(SERVER_URL, isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as connection:
            await connection.execute(text(f'CREATE DATABASE "{name}"'))
    except OSError as error:
        await admin.dispose()
        if os.environ.get("CI") == "true":
            pytest.fail(f"the test database is unreachable: {error}")
        pytest.skip(f"the test database is unreachable: {error}")
    try:
        yield make_url(SERVER_URL).set(database=name).render_as_string(hide_password=False)
    finally:
        async with admin.connect() as connection:
            await connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        await admin.dispose()


async def _tables(database_url: str) -> set[str]:
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
            return {row[0] for row in result}
    finally:
        await engine.dispose()


async def test_an_empty_database_is_migrated_to_head_without_a_client_pool(
    empty_database_url: str,
) -> None:
    await migrate_database(empty_database_url)

    assert {"alembic_version", "quotes", "quote_number_counters"} <= await _tables(
        empty_database_url
    )


async def test_migrating_twice_is_harmless(empty_database_url: str) -> None:
    await migrate_database(empty_database_url)
    await migrate_database(empty_database_url)

    assert "quotes" in await _tables(empty_database_url)
