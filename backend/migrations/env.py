from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.db.base import Base
import app.models  # noqa: F401


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata

LANGGRAPH_CHECKPOINT_TABLES = {
    "checkpoint_blobs",
    "checkpoint_migrations",
    "checkpoint_writes",
    "checkpoints",
}


def include_object(object_, name: str | None, type_: str, reflected: bool, compare_to) -> bool:  # type: ignore[no-untyped-def]
    """Keep the user migration chain inside its ownership boundary.

    The public LangGraph checkpoint tables are runtime-owned, while every
    admin-schema table except ``expert_reviews`` belongs to the administrator
    service's independent migration chain.
    """
    if type_ == "schema":
        return name in {None, "public", "admin"}
    if type_ == "table":
        schema = getattr(object_, "schema", None)
        if schema == "admin":
            return name == "expert_reviews"
        return schema in {None, "public"} and name not in LANGGRAPH_CHECKPOINT_TABLES
    table = getattr(object_, "table", None)
    if table is None:
        return True
    if getattr(table, "schema", None) == "admin":
        return getattr(table, "name", None) == "expert_reviews"
    return getattr(table, "name", None) not in LANGGRAPH_CHECKPOINT_TABLES


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
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
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_schemas=True,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
