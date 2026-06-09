"""Pure data-access functions (no LLM, no graph state).

These own the SQL and are reusable directly by FastAPI. The agent tools are thin
wrappers around these that add state handling.
"""

from __future__ import annotations

from agent.db import query
from agent.embeddings import embed_query


def find_locations(name: str, state: str | None = None) -> list[dict]:
    return query(
        """
        SELECT l.id AS location_id, l.name, l.state, c.name AS city
        FROM locations l
        LEFT JOIN cities c ON c.id = l.city_id
        WHERE l.name ILIKE %s
          AND (%s::text IS NULL OR l.state ILIKE %s)
        ORDER BY l.match_confidence DESC NULLS LAST
        LIMIT 10
        """,
        (f"%{name}%", state, f"%{state}%" if state else None),
    )


def find_hotels(location_id: int, price_min: int | None = None,
                price_max: int | None = None, min_rating: float | None = None,
                limit: int = 10) -> list[dict]:
    return query(
        """
        SELECT id AS hotel_id, name, accommodation_type,
               rating::float AS rating, num_reviews,
               price_min, price_max, mentions, url, image_url
        FROM hotels
        WHERE location_id = %s
          AND (%s::int IS NULL OR price_max >= %s)
          AND (%s::int IS NULL OR price_min <= %s)
          AND (%s::numeric IS NULL OR rating >= %s)
        ORDER BY review_score DESC NULLS LAST
        LIMIT %s
        """,
        (location_id, price_min, price_min, price_max, price_max,
         min_rating, min_rating, limit),
    )


def hotels_by_ids(ids: list[int]) -> list[dict]:
    """Card data for specific hotel ids, preserving the given order (for show_hotels)."""
    if not ids:
        return []
    rows = query(
        """
        SELECT id AS hotel_id, name, accommodation_type, rating::float AS rating,
               num_reviews, price_min, price_max, mentions, url, image_url
        FROM hotels WHERE id = ANY(%s)
        """,
        (list(ids),),
    )
    by_id = {r["hotel_id"]: r for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def hotel_details(hotel_id: int) -> dict | None:
    rows = query(
        """
        SELECT h.id AS hotel_id, h.name, h.accommodation_type,
               h.rating::float AS rating, h.num_reviews,
               h.price_min, h.price_max, h.url, h.image_url, h.mentions,
               h.lat, h.lng, l.name AS location, l.state
        FROM hotels h
        LEFT JOIN locations l ON l.id = h.location_id
        WHERE h.id = %s
        """,
        (hotel_id,),
    )
    return rows[0] if rows else None


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def find_reviews(query_text: str, hotel_id: int | None = None,
                 location_id: int | None = None, min_rating: float | None = None,
                 price_max: int | None = None, k: int = 6) -> list[dict]:
    vec = _vector_literal(embed_query(query_text))
    return query(
        """
        SELECT r.id AS review_id, e.hotel_id, h.name AS hotel_name,
               r.rating, r.title, r.text, r.trip_type,
               (1 - (e.embedding <=> %s::vector))::float AS similarity
        FROM review_embeddings e
        JOIN reviews r ON r.id = e.review_id
        JOIN hotels  h ON h.id = e.hotel_id
        WHERE (%s::int IS NULL OR e.hotel_id = %s)
          AND (%s::int IS NULL OR e.location_id = %s)
          AND (%s::numeric IS NULL OR e.hotel_rating >= %s)
          AND (%s::int IS NULL OR e.price_min <= %s)
        ORDER BY e.embedding <=> %s::vector
        LIMIT %s
        """,
        (vec, hotel_id, hotel_id, location_id, location_id,
         min_rating, min_rating, price_max, price_max, vec, k),
    )
