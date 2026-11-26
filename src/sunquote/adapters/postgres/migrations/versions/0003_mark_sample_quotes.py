"""Mark sample Quotes.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quotes", sa.Column("is_sample", sa.Boolean(), server_default=sa.false(), nullable=False)
    )
    op.create_index(
        "uq_quotes_sample_customer_name",
        "quotes",
        ["customer_name"],
        unique=True,
        postgresql_where=sa.text("is_sample"),
    )


def downgrade() -> None:
    op.drop_index("uq_quotes_sample_customer_name", table_name="quotes")
    op.drop_column("quotes", "is_sample")
