"""The Postgres implementation of the domain's `QuoteRepository` port."""

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import TypeAdapter
from sqlalchemy import RowMapping, func, insert, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from sunquote.adapters.postgres.tables import quote_number_counters, quotes
from sunquote.domain.ports import QuotePage, StoredQuote
from sunquote.domain.quote import Quote, format_quote_number

# The whole Quote travels as JSON. Pydantic reads the domain's dataclasses as they are, so a
# field added to the Quote is stored and restored without touching this module. Decimals are
# written as strings, so no figure passes through a float.
_QUOTE_JSON = TypeAdapter(Quote)


def create_engine(database_url: str) -> AsyncEngine:
    """An async engine. It connects lazily, so building it needs no running database."""
    return create_async_engine(database_url, pool_pre_ping=True)


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
                quote=_QUOTE_JSON.dump_python(quote, mode="json"),
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
        quote=_QUOTE_JSON.validate_python(row["quote"]),
        district=row["district"],
        province=row["province"],
    )
