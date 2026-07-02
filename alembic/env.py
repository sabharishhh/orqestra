"""Alembic env, wired to Orqestra's models and DATABASE_URL."""
from logging.config import fileConfig
import os

from sqlalchemy import engine_from_config, pool
from alembic import context

# Import Base + all models so autogen sees the full metadata graph.
# Also import Vector so pgvector column types render correctly.
from pgvector.sqlalchemy import Vector  # noqa: F401
from models.database import Base
import models.database  # noqa: F401  — ensures every model class is registered

config = context.config

# Pull DATABASE_URL from environment (matches how core/database.py loads it
# in the api container). Overrides the placeholder in alembic.ini.
db_url = os.environ.get("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()