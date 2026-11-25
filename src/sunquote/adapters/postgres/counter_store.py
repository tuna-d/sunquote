"""The Postgres implementation of the domain's `CounterStore` port, used when there is no Redis."""

from datetime import timedelta

from sqlalchemy import case, delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from sunquote.adapters.postgres.tables import rate_limit_counters as counters


class PostgresCounterStore:
    """One row per counter. The upsert locks the row, so concurrent calls count one by one."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def increment(self, key: str, *, ttl_seconds: int) -> int:
        new_expiry = func.now() + timedelta(seconds=ttl_seconds)
        insert_statement = insert(counters).values(key=key, count=1, expires_at=new_expiry)
        expired = counters.c.expires_at <= func.now()
        upsert = insert_statement.on_conflict_do_update(
            index_elements=[counters.c.key],
            set_={
                "count": case((expired, 1), else_=counters.c.count + 1),
                "expires_at": case(
                    (expired, insert_statement.excluded.expires_at), else_=counters.c.expires_at
                ),
            },
        ).returning(counters.c.count)
        async with self._engine.begin() as connection:
            count = (await connection.execute(upsert)).scalar_one()
            if count == 1:
                # A new window just started for this key, so sweep the dead ones: that is
                # cheap, indexed, and keeps the table small without a scheduled job.
                await connection.execute(delete(counters).where(counters.c.expires_at < func.now()))
        return int(count)
