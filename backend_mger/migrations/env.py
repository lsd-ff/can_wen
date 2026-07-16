from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.config import get_settings
from app.models import Base


config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(object_, name: str | None, type_: str, reflected: bool, compare_to) -> bool:  # type: ignore[no-untyped-def]
    """The admin service owns only the isolated ``admin`` schema.

    The user-facing API owns the public schema in the same PostgreSQL database.
    Excluding it here is essential: otherwise ``alembic check`` would suggest
    dropping every user business table from an administrator migration.
    """
    if type_ == "schema":
        return name == "admin"
    if type_ == "table":
        return getattr(object_, "schema", None) == "admin"
    table = getattr(object_, "table", None)
    return table is None or getattr(table, "schema", None) == "admin"


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="alembic_version_mger",
        version_table_schema="admin",
        include_schemas=True,
        include_object=include_object,
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
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS admin"))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table="alembic_version_mger",
            version_table_schema="admin",
            include_schemas=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
