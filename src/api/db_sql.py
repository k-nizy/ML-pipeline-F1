"""Thin MySQL access layer.

One short-lived connection per request keeps the app simple: the dataset is
static, requests are small, and this avoids a stale pooled connection after a
laptop sleeps. Every function takes the SQL and its parameters separately so
values are always bound, never string-formatted.
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Iterator

import pymysql
from pymysql.cursors import DictCursor

from src.api.config import settings


def get_connection() -> pymysql.connections.Connection:
    """Open a connection to the configured MySQL database."""
    return pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
        connect_timeout=5,
    )


@contextmanager
def cursor(commit: bool = False) -> Iterator[DictCursor]:
    """Yield a dict cursor and commit/rollback around the block."""
    connection = get_connection()
    try:
        with connection.cursor() as cur:
            yield cur
            if commit:
                connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _normalise(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Turn MySQL DECIMAL into float.

    PyMySQL hands back ``decimal.Decimal``; JSON-encoding that yields strings
    like ``"12.00"``, which forces every client (including the prediction
    script) to cast. Floats keep the API self-describing.
    """
    if row is None:
        return None
    return {key: float(value) if isinstance(value, Decimal) else value
            for key, value in row.items()}


def fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with cursor() as cur:
        cur.execute(sql, params)
        return [_normalise(row) for row in cur.fetchall()]


def fetch_one(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with cursor() as cur:
        cur.execute(sql, params)
        return _normalise(cur.fetchone())


def execute(sql: str, params: tuple[Any, ...] = ()) -> int:
    """Run a write statement and return the number of affected rows."""
    with cursor(commit=True) as cur:
        cur.execute(sql, params)
        return cur.rowcount
