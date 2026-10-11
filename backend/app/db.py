"""Engine, session dependency and create_all. Tests call configure_engine() with their own URL."""

from collections.abc import Iterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app import audit  # noqa: F401  registers the audit hash-chain flush hook for every session (docs/03 §6.6)
from app.config import get_settings

_engine: Engine | None = None


def configure_engine(url: str | None = None) -> Engine:
    global _engine
    url = url or get_settings().resolved_database_url
    kwargs: dict = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {}
    if url == "sqlite://":
        from sqlalchemy.pool import StaticPool

        kwargs["poolclass"] = StaticPool
    _engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(_engine, "connect")
        def _pragmas(dbapi_conn, _):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

    return _engine


def get_engine() -> Engine:
    return _engine or configure_engine()


def create_all() -> None:
    from app import models  # noqa: F401  (register tables)

    SQLModel.metadata.create_all(get_engine())


def drop_all() -> None:
    from app import models  # noqa: F401

    SQLModel.metadata.drop_all(get_engine())


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


def new_session() -> Session:
    return Session(get_engine())
