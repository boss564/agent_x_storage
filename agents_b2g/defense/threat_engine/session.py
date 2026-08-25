"""Shared DB session — one connection / transaction for atomic signature+action."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator, Optional, Protocol


class _Cursor(Protocol):
    def execute(self, query: str, params: Any = None) -> Any: ...
    def fetchone(self) -> Any: ...
    def fetchall(self) -> list: ...


class _Connection(Protocol):
    def cursor(self) -> _Cursor: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


def connect_from_env(dsn: Optional[str] = None) -> _Connection:
    """Open a psycopg connection. DSN: WAVE28_THREAT_DSN or DATABASE_URL."""
    url = (dsn or os.environ.get("WAVE28_THREAT_DSN") or os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError(
            "WAVE28_THREAT_DSN (or DATABASE_URL) required for ThreatEngineSession"
        )
    try:
        import psycopg  # type: ignore

        return psycopg.connect(url)
    except ImportError:
        import psycopg2  # type: ignore

        return psycopg2.connect(url)


class ThreatEngineSession:
    """Shared cursor + explicit transaction boundary for adapters."""

    def __init__(self, conn: _Connection):
        self._conn = conn
        self._cur: Optional[_Cursor] = None

    @property
    def cursor(self) -> _Cursor:
        if self._cur is None:
            self._cur = self._conn.cursor()
        return self._cur

    def execute(self, query: str, params: Any = None) -> _Cursor:
        self.cursor.execute(query, params)
        return self.cursor

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        try:
            if self._cur is not None:
                close = getattr(self._cur, "close", None)
                if callable(close):
                    close()
        finally:
            self._cur = None
            self._conn.close()

    @contextmanager
    def transaction(self) -> Iterator["ThreatEngineSession"]:
        try:
            yield self
            self.commit()
        except Exception:
            self.rollback()
            raise
