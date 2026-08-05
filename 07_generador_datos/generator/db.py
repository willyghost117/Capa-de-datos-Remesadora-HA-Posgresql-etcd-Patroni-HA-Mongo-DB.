from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row


@contextmanager
def pg_connection(dsn: str):
    conn = psycopg.connect(dsn, row_factory=dict_row)
    try:
        yield conn
    finally:
        conn.close()


def fetch_map(conn, sql: str, key: str, value: str = "id") -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(sql)
        return {row[key]: row[value] for row in cur.fetchall()}


def execute_many(conn, sql: str, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
