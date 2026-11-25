"""How the Postgres engine is built from a database URL and the pooling setting.

No test connects: the engine is lazy, so these check how it is configured.
"""

import pytest
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

from sunquote.adapters.postgres.quote_repository import async_database_url, create_engine

COMPOSE_URL = "postgresql+asyncpg://sunquote:sunquote@postgres:5432/sunquote"
# The shape of the URL Neon shows for the pooled connection.
NEON_URL = (
    "postgresql://owner:s3cret@ep-quiet-sun-123456-pooler.eu-central-1.aws.neon.tech/neondb"
    "?sslmode=require&channel_binding=require"
)


def test_the_engine_keeps_a_client_pool_by_default() -> None:
    engine = create_engine(COMPOSE_URL)

    assert isinstance(engine.pool, AsyncAdaptedQueuePool)


def test_the_engine_has_no_client_pool_for_serverless() -> None:
    engine = create_engine(COMPOSE_URL, client_pool=False)

    assert isinstance(engine.pool, NullPool)


def test_without_a_client_pool_prepared_statements_are_off_for_the_neon_pooler() -> None:
    # PgBouncer in transaction mode hands each transaction to any server connection, so a
    # statement prepared on one is missing on the next.
    engine = create_engine(COMPOSE_URL, client_pool=False)

    url = engine.url
    assert url.query["prepared_statement_cache_size"] == "0"


def test_with_a_client_pool_the_url_is_left_alone() -> None:
    engine = create_engine(COMPOSE_URL)

    assert "prepared_statement_cache_size" not in engine.url.query


def test_a_neon_url_is_rewritten_for_the_asyncpg_driver() -> None:
    url = async_database_url(NEON_URL)

    assert url.drivername == "postgresql+asyncpg"
    assert url.host == "ep-quiet-sun-123456-pooler.eu-central-1.aws.neon.tech"
    assert url.password == "s3cret"
    # asyncpg takes `ssl`, not `sslmode`, and has no `channel_binding` option.
    assert dict(url.query) == {"ssl": "require"}


@pytest.mark.parametrize("scheme", ["postgres", "postgresql", "postgresql+asyncpg"])
def test_every_postgres_scheme_ends_up_on_asyncpg(scheme: str) -> None:
    url = async_database_url(f"{scheme}://u:p@db.example.com/app")

    assert url.drivername == "postgresql+asyncpg"


def test_an_explicit_ssl_option_is_kept() -> None:
    url = async_database_url("postgresql+asyncpg://u:p@db.example.com/app?ssl=disable")

    assert dict(url.query) == {"ssl": "disable"}
