"""TripAdvisor review objects -> `reviews` rows."""

from __future__ import annotations

from typing import Any


def to_review_row(review: dict, hotel_id: int) -> dict[str, Any]:
    # Date/timestamp strings are cast by Postgres on insert (ISO formats).
    return {
        "ta_review_id": str(review["id"]),
        "hotel_id": hotel_id,
        "rating": review.get("rating"),
        "title": review.get("title"),
        "text": review.get("text"),
        "trip_type": review.get("trip_type"),
        "travel_date": review.get("travel_date"),      # "YYYY-MM-DD" or None
        "published_at": review.get("published_date"),  # ISO-8601 or None
        "lang": review.get("lang"),
        "raw": review,  # owner_response / user / subratings kept here
    }


def to_embedding_text(r: dict) -> str:
    """Text to embed: title + body (a `select_reviews_to_embed` row)."""
    return f"{r.get('title') or ''}\n{r.get('text') or ''}".strip()


def to_embedding_row(r: dict, vector: list[float], model: str) -> dict[str, Any]:
    """Build a review_embeddings row with denormalized filter metadata + model."""
    return {
        "review_id": r["review_id"],
        "embedding": vector,
        "hotel_id": r["hotel_id"],
        "location_id": r["location_id"],
        "city_id": r["city_id"],
        "accommodation_type": r["accommodation_type"],
        "price_min": r["price_min"],
        "price_max": r["price_max"],
        "hotel_rating": r["hotel_rating"],
        "review_rating": r["review_rating"],
        "model": model,
    }
