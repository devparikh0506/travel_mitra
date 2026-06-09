"""search_reviews — hybrid semantic + metadata search over hotel reviews."""

from __future__ import annotations

from langchain_core.tools import tool

from agent import queries


@tool
def search_reviews(query_text: str, hotel_id: int | None = None,
                   location_id: int | None = None, min_rating: float | None = None,
                   price_max: int | None = None, k: int = 6) -> list[dict]:
    """Find reviews relevant to a specific aspect of a stay.

    Pass concise aspect KEYWORDS as query_text (e.g. "quiet noise sleep" for "is it
    quiet?", "kids family spacious" for family-friendliness) rather than the user's
    raw sentence — it retrieves better. Scope to one hotel via hotel_id, or a city
    via location_id. Optional min_rating / price_max filters. Returns up to k
    reviews ordered by semantic relevance: [{review_id, hotel_id, hotel_name,
    rating, title, text, trip_type, similarity}]. Use these to summarize sentiment;
    higher similarity = more on-topic. Empty means no relevant reviews.
    """
    return queries.find_reviews(query_text, hotel_id, location_id,
                                min_rating, price_max, k)
