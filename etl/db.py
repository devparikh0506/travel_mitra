"""psycopg3 data-DB access helpers. Code owns the SQL — no ORM.

A thin layer: a connection context manager, a fetch helper, and a generic
bulk `INSERT ... ON CONFLICT` upsert used by every load step (idempotency).
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator, Sequence
from typing import Any

import psycopg
from pgvector.psycopg import register_vector
from psycopg import sql
from psycopg.rows import dict_row

from etl.config import settings


@contextlib.contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    """Open a psycopg3 connection to the data DB (rows as dicts).

    Registers the pgvector adapter so Python lists map to the `vector` type.
    """
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        register_vector(conn)
        yield conn


def fetch_all(conn: psycopg.Connection, query: str,
              params: Sequence[Any] | None = None) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()


def upsert(conn: psycopg.Connection, table: str, columns: list[str],
           rows: list[dict], conflict: list[str],
           update: list[str] | None = None) -> int:
    """Bulk `INSERT ... ON CONFLICT (...) DO UPDATE/NOTHING`.

    `update` defaults to all non-conflict columns; pass [] to DO NOTHING.
    Returns the number of rows submitted.
    """
    if not rows:
        return 0
    update = update if update is not None else [c for c in columns if c not in conflict]
    if update:
        action = sql.SQL("DO UPDATE SET {sets}").format(
            sets=sql.SQL(", ").join(
                sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in update
            )
        )
    else:
        action = sql.SQL("DO NOTHING")

    stmt = sql.SQL(
        "INSERT INTO {table} ({cols}) VALUES ({ph}) ON CONFLICT ({conf}) {action}"
    ).format(
        table=sql.Identifier(table),
        cols=sql.SQL(", ").join(map(sql.Identifier, columns)),
        ph=sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        conf=sql.SQL(", ").join(map(sql.Identifier, conflict)),
        action=action,
    )
    with conn.cursor() as cur:
        cur.executemany(stmt, [[r.get(c) for c in columns] for r in rows])
    conn.commit()
    return len(rows)
