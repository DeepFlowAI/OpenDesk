import asyncio
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

from app.db.session import Base
from app.configs.settings import settings
from app.models import *  # noqa: ensure all models are registered

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)


def _sync_url(url: str) -> str:
    return url.replace("+asyncpg", "")


def run_migrations_offline() -> None:
    url = _sync_url(config.get_main_option("sqlalchemy.url"))
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_sync_migrations_online() -> None:
    config.set_main_option("sqlalchemy.url", _sync_url(config.get_main_option("sqlalchemy.url")))
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        do_run_migrations(connection)


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url")
    if "+asyncpg" in url:
        asyncio.run(run_async_migrations_online())
        return
    run_sync_migrations_online()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
