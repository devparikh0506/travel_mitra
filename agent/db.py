"""psycopg3 access for the agent tools (per-call connection; pooled later in FastAPI)."""

from __future__ import annotations

import contextlib
from collections.abc import Iterator, Sequence
from typing import Any

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from agent.config import settings


@contextlib.contextmanager
def get_conn() -> Iterator[psycopg.Connection]:
    with psycopg.connect(settings.database_url, row_factory=dict_row) as conn:
        register_vector(conn)
        yield conn


def query(sql: str, params: Sequence[Any] | None = None) -> list[dict]:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()
