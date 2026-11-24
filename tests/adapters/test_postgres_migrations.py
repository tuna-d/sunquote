"""The migration scripts, checked without a database."""

from alembic.config import Config
from alembic.script import ScriptDirectory

from sunquote.adapters.postgres.migrate import MIGRATIONS_DIR


def test_migrations_form_one_linear_history() -> None:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))

    heads = ScriptDirectory.from_config(config).get_heads()

    assert len(heads) == 1
