"""The schema as SQLAlchemy Core tables.

The Alembic migrations create the same tables; keep them in step (a repository test fails
when they drift apart).
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

# One row per Quote. The columns serve the listing; `quote` holds the whole Quote, so a new
# field on the Quote needs no schema change. Rows are inserted once and never updated.
quotes = Table(
    "quotes",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("quote_number", String(32), nullable=False, unique=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("customer_name", Text, nullable=False),
    # Null until address geocoding fills them.
    Column("district", Text, nullable=True),
    Column("province", Text, nullable=True),
    Column("is_sample", Boolean, nullable=False, server_default=false()),
    Column("quote", JSONB, nullable=False),
)
Index("ix_quotes_created_at_quote_number", quotes.c.created_at.desc(), quotes.c.quote_number.desc())
Index(
    "uq_quotes_sample_customer_name",
    quotes.c.customer_name,
    unique=True,
    postgresql_where=quotes.c.is_sample,
)

# The last Quote Number sequence issued in each year. The sequence restarts each year because
# each year has its own row.
quote_number_counters = Table(
    "quote_number_counters",
    metadata,
    Column("year", Integer, primary_key=True, autoincrement=False),
    Column("last_sequence", Integer, nullable=False),
)

# Counters behind the rate limits (`CounterStore`), used when there is no Redis. A counter is
# dead once `expires_at` has passed; the store resets it on its next increment and sweeps dead
# rows when it starts a new one.
rate_limit_counters = Table(
    "rate_limit_counters",
    metadata,
    Column("key", Text, primary_key=True),
    Column("count", Integer, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)
Index("ix_rate_limit_counters_expires_at", rate_limit_counters.c.expires_at)
