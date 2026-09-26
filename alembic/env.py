from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.db import Base
from app.models import OAuthState, RefreshSession, User, VkAccount  # noqa: F401

config = context.config

# Передаём URL PostgreSQL в Alembic.
# %% экранируется, чтобы configparser не воспринимал % как interpolation.
config.set_main_option(
    "sqlalchemy.url",
    settings.database_url.replace("%", "%%"),
)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Запуск миграций без подключения к БД."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """
    Синхронная часть Alembic.

    Важно: именно эта функция передаётся в connection.run_sync(),
    поэтому context.run_migrations() выполняется в корректном
    sync/greenlet-контексте.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Запуск Alembic через AsyncEngine + run_sync()."""

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        async with connectable.connect() as connection:
            # Критически важно:
            # Alembic работает с sync API через run_sync().
            await connection.run_sync(do_run_migrations)

    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    """Запуск online-миграций."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()