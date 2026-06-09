"""Idempotent upserts + selection queries for the ETL stages."""

from __future__ import annotations

from psycopg.types.json import Jsonb

from etl.db import fetch_all, upsert

_CITY_COLUMNS = [
    "id", "name", "state_id", "state_name",
    "lat", "lng", "population", "ranking", "timezone",
]


def upsert_cities(conn, rows: list[dict]) -> int:
    """Upsert all cities on natural key `id` (simplemaps id)."""
    return upsert(conn, "cities", _CITY_COLUMNS, rows, conflict=["id"])


def select_cities_for_processing(conn, ranking_max: int, top_n: int) -> list[dict]:
    """Top-N cities to run the API pipeline over (most populous within ranking).

    Includes lat/lng so resolve_locations can pass them to the TripAdvisor
    geo search (latLong) to disambiguate same-named cities across states.
    """
    return fetch_all(
        conn,
        """
        SELECT id, name, state_id, state_name, lat, lng
        FROM cities
        WHERE ranking <= %s
        ORDER BY population DESC NULLS LAST
        LIMIT %s
        """,
        (ranking_max, top_n),
    )


# --- locations -------------------------------------------------------------

_LOCATION_COLUMNS = [
    "ta_location_id", "name", "city_id", "state", "country",
    "match_confidence", "verified", "raw",
]


def find_location_by_city(conn, city_id: int) -> dict | None:
    rows = fetch_all(
        conn,
        "SELECT id, ta_location_id FROM locations WHERE city_id = %s LIMIT 1",
        (city_id,),
    )
    return rows[0] if rows else None


def land_raw_tripadvisor(conn, endpoint: str, ref_id, payload: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw_tripadvisor (endpoint, ref_id, payload) VALUES (%s, %s, %s)",
            (endpoint, str(ref_id), Jsonb(payload)),
        )
    conn.commit()


def upsert_location(conn, row: dict) -> dict:
    """Upsert one geo on `ta_location_id`; return its {id, ta_location_id}."""
    row = {**row, "raw": Jsonb(row["raw"]) if row.get("raw") is not None else None}
    upsert(conn, "locations", _LOCATION_COLUMNS, [row], conflict=["ta_location_id"])
    return fetch_all(
        conn,
        "SELECT id, ta_location_id FROM locations WHERE ta_location_id = %s",
        (row["ta_location_id"],),
    )[0]


# --- hotels ----------------------------------------------------------------

_HOTEL_COLUMNS = [
    "ta_hotel_id", "xotelo_key", "location_id", "name", "accommodation_type",
    "url", "rating", "num_reviews", "price_min", "price_max", "lat", "lng",
    "image_url", "mentions", "review_score", "raw",
]


def land_raw_xotelo(conn, ref_id: str, payload: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO raw_xotelo (ref_id, payload) VALUES (%s, %s)",
            (str(ref_id), Jsonb(payload)),
        )
    conn.commit()


def upsert_hotels(conn, rows: list[dict]) -> int:
    """Upsert hotels on `ta_hotel_id`. Does NOT touch reviews_fetched_at
    (not in the column set) so the incremental review gate is preserved."""
    if not rows:
        return 0
    rows = [{**r, "raw": Jsonb(r["raw"]) if r.get("raw") is not None else None} for r in rows]
    return upsert(conn, "hotels", _HOTEL_COLUMNS, rows, conflict=["ta_hotel_id"])


# --- reviews ---------------------------------------------------------------

_REVIEW_COLUMNS = [
    "ta_review_id", "hotel_id", "rating", "title", "text",
    "trip_type", "travel_date", "published_at", "lang", "raw",
]


def select_hotels_needing_reviews(conn, location_id: int) -> list[dict]:
    """Hotels in a location whose reviews haven't been fetched yet (incremental)."""
    return fetch_all(
        conn,
        """
        SELECT id, ta_hotel_id, price_min, review_score
        FROM hotels
        WHERE location_id = %s AND reviews_fetched_at IS NULL
        ORDER BY review_score DESC NULLS LAST
        """,
        (location_id,),
    )


def upsert_reviews(conn, rows: list[dict]) -> int:
    if not rows:
        return 0
    rows = [{**r, "raw": Jsonb(r["raw"]) if r.get("raw") is not None else None} for r in rows]
    return upsert(conn, "reviews", _REVIEW_COLUMNS, rows, conflict=["ta_review_id"])


def mark_reviews_fetched(conn, hotel_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE hotels SET reviews_fetched_at = now() WHERE id = %s", (hotel_id,))
    conn.commit()


# --- embeddings ------------------------------------------------------------

_EMBEDDING_COLUMNS = [
    "review_id", "embedding", "hotel_id", "location_id", "city_id",
    "accommodation_type", "price_min", "price_max", "hotel_rating",
    "review_rating", "model",
]


def select_reviews_to_embed(conn) -> list[dict]:
    """Un-embedded reviews joined with hotel/location metadata for denormalization."""
    return fetch_all(
        conn,
        """
        SELECT r.id AS review_id, r.title, r.text, r.rating AS review_rating,
               h.id AS hotel_id, h.location_id, l.city_id,
               h.accommodation_type, h.price_min, h.price_max,
               h.rating AS hotel_rating
        FROM reviews r
        JOIN hotels h    ON h.id = r.hotel_id
        JOIN locations l ON l.id = h.location_id
        LEFT JOIN review_embeddings e ON e.review_id = r.id
        WHERE e.review_id IS NULL
        """,
    )


def insert_review_embeddings(conn, rows: list[dict]) -> int:
    """Insert embeddings; conflict-skip already-embedded reviews (idempotent)."""
    return upsert(conn, "review_embeddings", _EMBEDDING_COLUMNS, rows,
                  conflict=["review_id"], update=[])
