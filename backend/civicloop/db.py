from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base class for all CivicLoop database models."""


def normalise_database_url(database_url: str) -> str:
    """Hosts such as Render hand out `postgres://` or `postgresql://` addresses; this app talks to PostgreSQL with psycopg 3."""
    for old in ("postgres://", "postgresql://"):
        if database_url.startswith(old):
            return "postgresql+psycopg://" + database_url[len(old):]
    return database_url


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
    kwargs.setdefault("pool_size", 20)
    kwargs.setdefault("max_overflow", 10)
    kwargs.setdefault("pool_pre_ping", True)
    kwargs.setdefault("pool_recycle", 1800)
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