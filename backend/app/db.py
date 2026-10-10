"""SQLAlchemy engine/session management (SQLite by default)."""
from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class Database:
    """Owns one engine + session factory. SQLite writes are serialised with a lock
    because analyses run on background threads."""

    def __init__(self, url: str) -> None:
        self.url = url
        kwargs: dict = {}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
            if ":memory:" in url or url == "sqlite://":
                kwargs["poolclass"] = StaticPool
        self.engine: Engine = create_engine(url, future=True, **kwargs)
        if url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                if ":memory:" not in url:
                    cur.execute("PRAGMA journal_mode=WAL")
                cur.close()
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)
        self.write_lock = threading.RLock()

    def create_all(self) -> None:
        from app import models  # noqa: F401  (register mappers)

        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @contextmanager
    def write(self) -> Iterator[Session]:
        with self.write_lock:
            with self.session() as session:
                yield session

    def dispose(self) -> None:
        self.engine.dispose()
