from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)


def run_migrations_online() -> None:
    engine = create_engine(get_settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, version_table_schema="public")
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("Offline mode is not supported; run against a database.")
run_migrations_online()
