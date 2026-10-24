import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base class for all CivicLoop database models."""


def normalise_database_url(database_url: str) -> str:
    """Hosts such as Render and Supabase hand out `postgres://` or `postgresql://` addresses; this app talks to PostgreSQL
    with psycopg 3. A Supabase address also gets `sslmode=require`, because it only accepts encrypted connections."""
    for old in ("postgres://", "postgresql://"):
        if database_url.startswith(old):
            database_url = "postgresql+psycopg://" + database_url[len(old):]
            break
    if database_url.startswith("postgresql+psycopg://"):
        parsed = make_url(database_url)
        if (parsed.host or "").endswith((".supabase.co", ".supabase.com")) and "sslmode" not in parsed.query:
            database_url = parsed.update_query_dict({"sslmode": "require"}).render_as_string(hide_password=False)
    return database_url


def uses_transaction_pooler(database_url: str) -> bool:
    """Supabase's transaction pooler (port 6543) and PgBouncer cannot keep prepared statements between queries."""
    parsed = make_url(database_url)
    return parsed.port == 6543 or "pgbouncer" in parsed.query


def create_engine(database_url: str = "sqlite:///civicloop.db", **kwargs: Any) -> Engine:
    """Create a SQLAlchemy engine for SQLite or another supported backend."""
    database_url = normalise_database_url(database_url)
    if database_url.startswith("sqlite"):
        kwargs.setdefault("connect_args", {"check_same_thread": False, "timeout": 10})
        engine = sqlalchemy_create_engine(database_url, **kwargs)
        if ":memory:" not in database_url:

            @event.listens_for(engine, "connect")
            def _sqlite_pragmas(connection, _record):  # noqa: ANN001
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")  # SQLite ignores foreign keys unless asked
                cursor.execute("PRAGMA journal_mode=WAL")  # readers no longer block the writer
                cursor.execute("PRAGMA busy_timeout=5000")  # wait for a lock instead of failing at once
                cursor.close()

        return engine
    # Hosted databases allow only a few connections (Supabase's pooler on the free plan: about 15), so keep the pool small.
    kwargs.setdefault("pool_size", int(os.getenv("CIVICLOOP_DB_POOL_SIZE", "5")))
    kwargs.setdefault("max_overflow", int(os.getenv("CIVICLOOP_DB_MAX_OVERFLOW", "5")))
    kwargs.setdefault("pool_pre_ping", True)
    kwargs.setdefault("pool_recycle", 1800)
    if uses_transaction_pooler(database_url):
        kwargs.setdefault("connect_args", {"prepare_threshold": None})
    return sqlalchemy_create_engine(database_url, **kwargs)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create sessions that do not expire objects after commits."""
    from civicloop import tenancy  # noqa: F401  (registers the per-tenant read and write hooks)

    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    """Create all mapped tables for a fresh database."""
    from civicloop import models  # noqa: F401

    Base.metadata.create_all(engine)


def assert_schema_current(engine: Engine, ini_path: str = "alembic.ini") -> None:
    """Refuse to start on a database the code was not written for (run `alembic upgrade head` first)."""
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    head = ScriptDirectory.from_config(Config(ini_path)).get_current_head()
    with engine.connect() as connection:
        current = MigrationContext.configure(connection).get_current_revision()
    if current != head:
        raise RuntimeError(f"The database is at revision {current}, this version needs {head}. Run: alembic upgrade head")


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    """Commit a unit of work or roll it back when an exception occurs."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()