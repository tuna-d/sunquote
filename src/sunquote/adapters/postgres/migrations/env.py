"""Alembic environment. Migrations run on the connection `upgrade_to_head` hands in."""

from alembic import context

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("run the migrations through sunquote.adapters.postgres.migrate")

context.configure(connection=connection)
with context.begin_transaction():
    context.run_migrations()
