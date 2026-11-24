"""Create the quotes table and the Quote Number counters.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quotes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("quote_number", sa.String(32), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("customer_name", sa.Text(), nullable=False),
        sa.Column("district", sa.Text(), nullable=True),
        sa.Column("province", sa.Text(), nullable=True),
        sa.Column("quote", postgresql.JSONB(), nullable=False),
    )
    op.create_index(
        "ix_quotes_created_at_quote_number",
        "quotes",
        [sa.text("created_at DESC"), sa.text("quote_number DESC")],
    )
    op.create_table(
        "quote_number_counters",
        sa.Column("year", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("last_sequence", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("quote_number_counters")
    op.drop_table("quotes")
