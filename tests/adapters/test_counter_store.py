"""The `CounterStore` contract, run against every implementation.

The Redis store needs `SUNQUOTE_TEST_REDIS_URL` and the Postgres one `SUNQUOTE_TEST_DATABASE_URL`;
each is skipped without its URL (and fails in CI when its service is unreachable). Keys carry a
random prefix, so tests never meet each other's counters in a shared Redis.
"""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from sunquote.adapters.postgres.counter_store import PostgresCounterStore
from sunquote.adapters.redis_counter_store import RedisCounterStore
from sunquote.domain.ports import CounterStore
from tests.adapters.conftest import open_migrated_test_schema, open_test_redis
from tests.fakes import InMemoryCounterStore

pytestmark = pytest.mark.anyio


@pytest.fixture(params=["memory", "redis", "postgres"])
async def store(request: pytest.FixtureRequest) -> AsyncIterator[CounterStore]:
    if request.param == "memory":
        yield InMemoryCounterStore(clock=lambda: datetime.now(UTC))
    elif request.param == "redis":
        async with open_test_redis() as redis:
            yield RedisCounterStore(redis)
    else:
        async with open_migrated_test_schema() as engine:
            yield PostgresCounterStore(engine)


@pytest.fixture
def key() -> str:
    return f"test:{uuid4().hex}"


async def test_a_counter_starts_at_one_and_counts_up(store: CounterStore, key: str) -> None:
    values = [await store.increment(key, ttl_seconds=60) for _ in range(3)]

    assert values == [1, 2, 3]


async def test_counters_with_different_keys_are_independent(store: CounterStore, key: str) -> None:
    await store.increment(f"{key}:a", ttl_seconds=60)
    await store.increment(f"{key}:a", ttl_seconds=60)

    assert await store.increment(f"{key}:b", ttl_seconds=60) == 1


async def test_concurrent_increments_each_get_a_distinct_value(
    store: CounterStore, key: str
) -> None:
    values = await asyncio.gather(*(store.increment(key, ttl_seconds=60) for _ in range(20)))

    assert sorted(values) == list(range(1, 21))


async def test_a_counter_starts_again_once_its_ttl_has_passed(
    store: CounterStore, key: str
) -> None:
    await store.increment(key, ttl_seconds=1)
    await store.increment(key, ttl_seconds=1)

    await asyncio.sleep(1.3)

    assert await store.increment(key, ttl_seconds=1) == 1
