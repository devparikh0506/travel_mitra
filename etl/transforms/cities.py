"""simplemaps CSV rows -> lean `cities` table rows (native Python types)."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

# simplemaps CSV column -> our lean `cities` column
_COLUMN_MAP = {
    "id": "id",
    "city": "name",
    "state_id": "state_id",
    "state_name": "state_name",
    "lat": "lat",
    "lng": "lng",
    "population": "population",
    "ranking": "ranking",
    "timezone": "timezone",
}


def _is_missing(v: Any) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def _int(v: Any) -> int | None:
    return None if _is_missing(v) else int(v)


def _float(v: Any) -> float | None:
    return None if _is_missing(v) else float(v)


def _str(v: Any) -> str | None:
    return None if _is_missing(v) else str(v)


def to_city_rows(df: pd.DataFrame) -> list[dict]:
    """Select + rename + cast to native Python types for psycopg.

    Casts to plain int/float/str (psycopg does not adapt numpy scalars).
    """
    subset = df[list(_COLUMN_MAP)].rename(columns=_COLUMN_MAP)
    rows: list[dict] = []
    for r in subset.itertuples(index=False):
        rows.append(
            {
                "id": _int(r.id),
                "name": _str(r.name),
                "state_id": _str(r.state_id),
                "state_name": _str(r.state_name),
                "lat": _float(r.lat),
                "lng": _float(r.lng),
                "population": _int(r.population),
                "ranking": _int(r.ranking),
                "timezone": _str(r.timezone),
            }
        )
    return [r for r in rows if r["id"] is not None and r["name"]]
