from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from civicloop import models  # noqa: F401
from civicloop.db import Base, normalise_database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = os.getenv("CIVICLOOP_DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", normalise_database_url(database_url).replace("%", "%%"))

target_metadata = Base.metadata


def lock_down_tables(connection) -> None:
    """PostgreSQL hosts such as Supabase publish every table in the `public` schema through their own public REST API,
    readable and writable with the project's public key. This app does all its own access control, so no one else may
    reach these tables: switch on row-level security with no policies (the owner role this app connects as is not
    affected) and take every privilege away from the hosted API roles when they exist. Runs after every upgrade, so
    tables added later are covered too. It does nothing on other databases."""
    if connection.dialect.name != "postgresql":
        return
    for (table,) in connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).all():
        connection.execute(text(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'))
    connection.execute(
        text(
            """
            DO $$
            DECLARE api_role text;
            BEGIN
              FOREACH api_role IN ARRAY ARRAY['anon', 'authenticated']
              LOOP
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = api_role) THEN
                  EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', api_role);
                  EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', api_role);
                  EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', api_role);
                END IF;
              END LOOP;
            END $$;
            """
        )
    )


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
            lock_down_tables(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()