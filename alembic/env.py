"""Alembic environment — async mode."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from museums.config import get_settings

# Alembic Config object providing access to alembic.ini values.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# TODO Phase 2: import Base.metadata and assign to target_metadata
# from museums.models.base import Base
# target_metadata = Base.metadata
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in offline mode (without a live DB connection)."""
    settings = get_settings()
    context.configure(
        url=str(settings.database_url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in online mode using an async engine."""
    settings = get_settings()
    connectable = create_async_engine(str(settings.database_url))

    async with connectable.connect() as connection:
        await connection.run_sync(_run_migrations_sync)

    await connectable.dispose()


def _run_migrations_sync(connection: object) -> None:
    """Configure and run migrations within a sync connection context."""
    context.configure(connection=connection, target_metadata=target_metadata)  # type: ignore[arg-type]
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Entry point for online mode — wraps async runner."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
