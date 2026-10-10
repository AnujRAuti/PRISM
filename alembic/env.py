from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

import logging
import os
import sys

# make project package importable
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from backend.core.config import settings
from backend.db import safety
from backend.db.models import Base
from backend.db.schema_drift_policy import (
    include_object,
    process_revision_directives,
)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
fileConfig(config.config_file_name)

# Set the SQLAlchemy URL from settings
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata

# Two exclusions, both owned by backend/db/schema_drift_policy.py so this file and
# the schema-drift gate cannot disagree about them:
#
# * ``include_object`` -- PostGIS installs ``spatial_ref_sys``, which no model
#   describes; without this hook autogenerate proposes dropping it.
# * ``process_revision_directives`` -- Alembic 1.11.2 discards the
#   ``postgresql_nulls_not_distinct`` dialect option when it rebuilds the
#   reflected ``uq_user_role_scoped`` constraint, so every autogenerate pass
#   proposes dropping and re-adding a constraint that is already correct. This
#   hook drops exactly that named pair from revision generation and from
#   ``alembic check``; it does not touch the model, and the drift gate still
#   measures the pair because it calls ``compare_metadata()`` directly.

#: Guards migrations the same way the test suite guards writes (BE-029). Alembic
#: is the most destructive database entry point in the project, so it states its
#: target on every run: the name the *server* reports when it can connect, and a
#: hard refusal before any DDL when an armed context forbids that database.
_target_logger = logging.getLogger("alembic.env")


def declare_target(url: str, bind=None) -> str:
    """Log the migration target and enforce the armed context; returns the name."""
    context_name = safety.current_context()
    if context_name:
        # Refuse on the configured name first: no connection, no DDL.
        safety.guard_url(url, context_name)
    if bind is not None:
        # confirm_server_database asks the server *and* enforces, so the armed
        # path needs only this one connection.
        actual = (
            safety.confirm_server_database(bind, context_name)
            if context_name
            else safety.server_database_name(bind)
        )
    else:
        actual = safety.database_name(url) or url
    _target_logger.info("Alembic target database: %s", actual)
    return actual


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    declare_target(url, bind=None)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        process_revision_directives=process_revision_directives,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    declare_target(config.get_main_option("sqlalchemy.url"), bind=connectable)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
