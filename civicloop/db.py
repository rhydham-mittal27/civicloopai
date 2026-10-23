from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine as sqlalchemy_create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Base class for all CivicLoop database models."""


def create_engine(database_url: str = "sqlite:///civicloop.db", **kwargs: Any) -> Engine:
    """Create a SQLAlchemy engine for SQLite or another supported backend."""
    if database_url.startswith("sqlite"):
        kwargs.setdefault("connect_args", {"check_same_thread": False})
    else:
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