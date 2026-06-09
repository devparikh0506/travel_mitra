"""Xotelo /list items -> `hotels` rows, with a Bayesian review_score.

Xotelo hotel key format: "g{geo_id}-d{hotel_id}". We store the full key
(`xotelo_key`, needed for Xotelo /rates) and the bare hotel id (`ta_hotel_id`,
== the TripAdvisor location_id used by the reviews endpoint).
"""

from __future__ import annotations

from typing import Any

# Bayesian (IMDb-style) prior: pulls low-count ratings toward the global mean
# so a 4.9 with 5 reviews ranks below a 4.7 with thousands.
_PRIOR_MEAN = 3.5   # assumed average rating
_PRIOR_COUNT = 50   # strength of the prior (in "virtual reviews")


def _review_score(rating: float | None, count: int | None) -> float | None:
    if rating is None or count is None:
        return None
    v, m, c = float(count), _PRIOR_COUNT, _PRIOR_MEAN
    return round((v / (v + m)) * float(rating) + (m / (v + m)) * c, 4)


def _hotel_id_from_key(key: str) -> str:
    # "g60763-d23448880" -> "23448880"
    return key.rsplit("-d", 1)[-1]


def _tier(price_min: int | None, budget_max: int, mid_max: int) -> str:
    if price_min is None:
        return "mid"                       # unknown price -> treat as mid
    if price_min < budget_max:
        return "budget"
    if price_min < mid_max:
        return "mid"
    return "luxury"


def stratify_top_k(hotels: list[dict], k: int, budget_max: int,
                   mid_max: int) -> list[dict]:
    """Pick up to `k` hotels spread across price tiers, best `review_score` first
    within each tier. Unfilled tier slots are redistributed to the best remaining
    hotels so we always return up to `k` when enough candidates exist.
    """
    if k <= 0 or not hotels:
        return []

    buckets: dict[str, list[dict]] = {"budget": [], "mid": [], "luxury": []}
    for h in hotels:
        buckets[_tier(h.get("price_min"), budget_max, mid_max)].append(h)
    for lst in buckets.values():
        lst.sort(key=lambda h: (h.get("review_score") or 0.0), reverse=True)

    base = k // 3
    alloc = {"budget": base, "mid": base, "luxury": k - 2 * base}

    picked: list[dict] = []
    for name, lst in buckets.items():
        picked.extend(lst[: alloc[name]])

    shortfall = k - len(picked)
    if shortfall > 0:  # some tier was short -> backfill with best leftovers
        leftovers = [h for name, lst in buckets.items() for h in lst[alloc[name]:]]
        leftovers.sort(key=lambda h: (h.get("review_score") or 0.0), reverse=True)
        picked.extend(leftovers[:shortfall])
    return picked[:k]


def to_hotel_row(item: dict, location_id: int) -> dict[str, Any]:
    key = item["key"]
    rs = item.get("review_summary") or {}
    pr = item.get("price_ranges") or {}
    geo = item.get("geo") or {}
    rating = rs.get("rating")
    num_reviews = rs.get("count")
    return {
        "ta_hotel_id": _hotel_id_from_key(key),
        "xotelo_key": key,
        "location_id": location_id,
        "name": item.get("name"),
        "accommodation_type": item.get("accommodation_type"),
        "url": item.get("url"),
        "rating": rating,
        "num_reviews": num_reviews,
        "price_min": pr.get("minimum"),
        "price_max": pr.get("maximum"),
        "lat": geo.get("latitude"),
        "lng": geo.get("longitude"),
        "image_url": item.get("image"),
        "mentions": item.get("mentions") or [],
        "review_score": _review_score(rating, num_reviews),
        "raw": item,  # wrapped as Jsonb in the upsert layer
    }
