"""The Postgres implementation of the domain's `QuoteRepository` port."""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import TypeAdapter
from sqlalchemy import RowMapping, func, insert, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from sunquote.adapters.postgres.tables import quote_number_counters, quotes
from sunquote.domain.ports import QuotePage, StoredQuote
from sunquote.domain.quote import Quote, format_quote_number

# The whole Quote travels as JSON. Pydantic reads the domain's dataclasses as they are, so a
# field added to the Quote is stored and restored without touching this module. Decimals are
# written as strings, so no figure passes through a float.
_QUOTE_JSON = TypeAdapter(Quote)


def quote_to_json(quote: Quote) -> dict[str, Any]:
    """The JSON document stored in the `quote` column. Decimals are strings."""
    document: dict[str, Any] = _QUOTE_JSON.dump_python(quote, mode="json")
    return document


def quote_from_json(document: dict[str, Any]) -> Quote:
    return _QUOTE_JSON.validate_python(document)


def async_database_url(database_url: str) -> URL:
    """The URL in the form the asyncpg driver reads.

    A Postgres host (Neon, for one) shows its connection string as
    `postgresql://...?sslmode=require&channel_binding=require`. asyncpg takes `ssl` instead of
    `sslmode` and has no `channel_binding` option, so the string is rewritten here and can be
    pasted into `SUNQUOTE_DATABASE_URL` as it is.
    """
    url = make_url(database_url).set(drivername="postgresql+asyncpg")
    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)
    if sslmode is not None:
        query.setdefault("ssl", sslmode if isinstance(sslmode, str) else sslmode[0])
    return url.set(query=query)


def create_engine(database_url: str, *, client_pool: bool = True) -> AsyncEngine:
    """An async engine. It connects lazily, so building it needs no running database.

    With `client_pool` off (serverless), every use opens its own connection and closes it
    afterwards: an instance that is frozen between requests must not hold connections that
    the server drops, and the host's own pooler (Neon's PgBouncer) does the pooling. That
    pooler hands each transaction to any server connection, so prepared statements are off
    too: one prepared on a connection would be missing on the next.
    """
    url = async_database_url(database_url)
    if client_pool:
        return create_async_engine(url, pool_pre_ping=True)
    return create_async_engine(
        url.update_query_dict({"prepared_statement_cache_size": "0"}),
        poolclass=NullPool,
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
        },
    )


class PostgresQuoteRepository:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def next_quote_number(self, year: int) -> str:
        """Bump the year's counter in one statement.

        The upsert locks the counter row until it commits, so concurrent callers are served
        one after the other and each gets the next number. The counter commits at once, so a
        number is never handed out twice.
        """
        statement = (
            postgres_insert(quote_number_counters)
            .values(year=year, last_sequence=1)
            .on_conflict_do_update(
                index_elements=[quote_number_counters.c.year],
                set_={"last_sequence": quote_number_counters.c.last_sequence + 1},
            )
            .returning(quote_number_counters.c.last_sequence)
        )
        async with self._engine.begin() as connection:
            sequence = (await connection.execute(statement)).scalar_one()
        return format_quote_number(year, sequence)

    async def save(
        self, quote: Quote, *, district: str | None = None, province: str | None = None
    ) -> StoredQuote:
        quote_id = uuid4()
        statement = (
            insert(quotes)
            .values(
                id=quote_id,
                quote_number=quote.quote_number,
                customer_name=quote.customer.name,
                district=district,
                province=province,
                quote=quote_to_json(quote),
            )
            .returning(quotes.c.created_at)
        )
        async with self._engine.begin() as connection:
            created_at: datetime = (await connection.execute(statement)).scalar_one()
        return StoredQuote(
            id=quote_id, created_at=created_at, quote=quote, district=district, province=province
        )

    async def get(self, quote_id: UUID) -> StoredQuote | None:
        async with self._engine.connect() as connection:
            row = (
                await connection.execute(select(quotes).where(quotes.c.id == quote_id))
            ).one_or_none()
        return None if row is None else _stored_quote(row._mapping)

    async def list_newest_first(self, *, page: int, page_size: int) -> QuotePage:
        statement = (
            select(quotes)
            .order_by(quotes.c.created_at.desc(), quotes.c.quote_number.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        async with self._engine.connect() as connection:
            rows = (await connection.execute(statement)).all()
            total = (
                await connection.execute(select(func.count()).select_from(quotes))
            ).scalar_one()
        return QuotePage(items=tuple(_stored_quote(row._mapping) for row in rows), total=total)


def _stored_quote(row: RowMapping) -> StoredQuote:
    return StoredQuote(
        id=row["id"],
        created_at=row["created_at"],
        quote=quote_from_json(row["quote"]),
        district=row["district"],
        province=row["province"],
    )
