"""Fixtures shared by the adapter tests that need a real Postgres or Redis.

Point `SUNQUOTE_TEST_DATABASE_URL` and `SUNQUOTE_TEST_REDIS_URL` at them, for example the
Compose services published on localhost. Without a URL the tests are skipped (in CI, where
`CI=true`, a missing or unreachable service fails them instead).

The connections are async context managers, so a test that is parametrised over several
backends can open the one it needs (`getfixturevalue` cannot run async fixtures).
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from sunquote.adapters.postgres.migrate import upgrade_to_head

DATABASE_URL = os.environ.get("SUNQUOTE_TEST_DATABASE_URL")


def _unavailable(reason: str) -> None:
    if os.environ.get("CI") == "true":
        pytest.fail(reason)
    pytest.skip(reason)


@asynccontextmanager
async def open_migrated_test_schema() -> AsyncIterator[AsyncEngine]:
    """An engine whose connections live in a fresh schema, migrated to head and dropped after."""
    if not DATABASE_URL:
        pytest.skip("SUNQUOTE_TEST_DATABASE_URL is not set")
    schema = f"test_{uuid4().hex}"
    admin = create_async_engine(DATABASE_URL)
    try:
        async with admin.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    except OSError as error:
        await admin.dispose()
        _unavailable(f"the test database is unreachable: {error}")
    test_engine = create_async_engine(
        DATABASE_URL, connect_args={"server_settings": {"search_path": schema}}
    )
    try:
        await upgrade_to_head(test_engine)
        yield test_engine
    finally:
        await test_engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


@asynccontextmanager
async def open_test_redis() -> AsyncIterator[Redis]:
    """A client of the test Redis. Tests share the database, so they use unique keys."""
    url = os.environ.get("SUNQUOTE_TEST_REDIS_URL")
    if not url:
        _unavailable("SUNQUOTE_TEST_REDIS_URL is not set")
    assert url is not None
    async with Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1) as client:
        try:
            await client.ping()
        except (OSError, RedisError) as error:
            _unavailable(f"the test Redis is unreachable: {error}")
        yield client


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    async with open_migrated_test_schema() as test_engine:
        yield test_engine


@pytest.fixture
async def redis_client() -> AsyncIterator[Redis]:
    async with open_test_redis() as client:
        yield client
