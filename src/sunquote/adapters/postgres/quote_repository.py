"""The Postgres implementation of the domain's `QuoteRepository` port."""

from typing import Any
from uuid import UUID, uuid4

from pydantic import TypeAdapter
from sqlalchemy import RowMapping, delete, func, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

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
        self,
        quote: Quote,
        *,
        district: str | None = None,
        province: str | None = None,
        is_sample: bool = False,
    ) -> StoredQuote:
        quote_id = uuid4()
        statement = postgres_insert(quotes).values(
            id=quote_id,
            quote_number=quote.quote_number,
            customer_name=quote.customer.name,
            district=district,
            province=province,
            is_sample=is_sample,
            quote=quote_to_json(quote),
        )
        if is_sample:
            # The synthetic Customer name identifies each sample across seed runs.
            statement = statement.on_conflict_do_nothing(
                index_elements=[quotes.c.customer_name], index_where=quotes.c.is_sample
            )
        async with self._engine.begin() as connection:
            result = await connection.execute(statement.returning(quotes.c.created_at))
            created_at = result.scalar_one_or_none()
            if created_at is None:
                existing = await connection.execute(
                    select(quotes).where(
                        quotes.c.is_sample, quotes.c.customer_name == quote.customer.name
                    )
                )
                return _stored_quote(existing.one()._mapping)
        return StoredQuote(
            id=quote_id,
            created_at=created_at,
            quote=quote,
            district=district,
            province=province,
            is_sample=is_sample,
        )

    async def sample_customer_names(self) -> set[str]:
        """Identify existing samples before paying for a new Quote's upstream lookups."""
        async with self._engine.connect() as connection:
            names = await connection.scalars(
                select(quotes.c.customer_name).where(quotes.c.is_sample)
            )
        return set(names)

    async def delete_non_sample_quotes(self) -> int:
        """Delete visitor Quotes in one transaction, leaving samples and numbering intact."""
        async with self._engine.begin() as connection:
            result = await connection.execute(delete(quotes).where(~quotes.c.is_sample))
        return result.rowcount

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
        is_sample=row["is_sample"],
    )
