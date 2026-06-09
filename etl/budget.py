"""TripAdvisor call-budget guardrail backed by the api_call_log table.

The free tier caps total monthly calls; every call is logged and checked so
the ETL stops gracefully before exceeding the cap.
"""

from __future__ import annotations

from etl.db import fetch_all


def calls_this_month(conn, provider: str = "tripadvisor") -> int:
    rows = fetch_all(
        conn,
        """
        SELECT count(*) AS n FROM api_call_log
        WHERE provider = %s AND called_at >= date_trunc('month', now())
        """,
        (provider,),
    )
    return int(rows[0]["n"])


def remaining_budget(conn, monthly_cap: int, provider: str = "tripadvisor") -> int:
    return monthly_cap - calls_this_month(conn, provider)


def log_call(conn, provider: str, endpoint: str, ref_id: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO api_call_log (provider, endpoint, ref_id) VALUES (%s, %s, %s)",
            (provider, endpoint, ref_id),
        )
    conn.commit()
