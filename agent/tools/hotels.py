"""search_hotels + get_hotel_details."""

from __future__ import annotations

from langchain_core.tools import tool

from agent import queries


@tool
def search_hotels(location_id: int, price_min: int | None = None,
                  price_max: int | None = None, min_rating: float | None = None,
                  limit: int = 10) -> list[dict]:
    """List hotels in a resolved location, best-reviewed first.

    Requires a location_id from search_locations.

    Each hotel's price_min/price_max is its NIGHTLY PRICE RANGE (cheapest to
    priciest room/date) — not a single price. A hotel "matches a budget" if it has
    rooms within it: price_max filters to hotels with a room at/under that amount
    (price_min <= price_max), so "under $300" returns hotels starting under $300
    even if their range tops out higher. Treat such hotels as valid matches and
    present them as "from $price_min/night".

    Optional filters: price_min / price_max (USD budget window), min_rating (e.g.
    4.0 for "4+ stars"). Returns ranked [{hotel_id, name, accommodation_type,
    rating, num_reviews, price_min, price_max, mentions}].
    """
    return queries.find_hotels(location_id, price_min, price_max, min_rating, limit)


@tool
def get_hotel_details(hotel_id: int) -> dict | None:
    """Full details for one hotel (name, rating, price range, #reviews, type,
    url, image, mentions, location). Use after the user settles on a hotel."""
    return queries.hotel_details(hotel_id)
