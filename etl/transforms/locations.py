"""Pick the best TripAdvisor geo for a city and shape the `locations` row.

Scoring is name- and state-driven (NOT lat/lng biased — passing latLong to the
search over-localizes to neighborhood geos and drops the city geo entirely).
A candidate with no name match scores low so the caller's confidence threshold
skips wrong neighborhoods (e.g. "Universal Studios Hollywood" for Los Angeles)
rather than silently choosing them.
"""

from __future__ import annotations

from typing import Any


def _norm(s: Any) -> str:
    return (s or "").strip().lower()


def pick_best_geo(city: dict, search_payload: dict) -> tuple[dict | None, float]:
    data = search_payload.get("data") or []
    if not data:
        return None, 0.0

    state = _norm(city.get("state_name"))
    cname = _norm(city.get("name"))

    best: dict | None = None
    best_score = 0.0
    for cand in data:
        addr = cand.get("address_obj") or {}
        if (addr.get("country") or "") != "United States":
            continue
        cand_name = _norm(cand.get("name"))
        cand_state = _norm(addr.get("state"))

        score = 0.0
        if cname and cand_name == cname:
            score += 0.6                                   # exact name match
        elif cname and cand_name and (cname in cand_name or cand_name in cname):
            score += 0.35                                  # partial (e.g. "New York" ⊂ "New York City")
        if state and cand_state == state:
            score += 0.4                                   # state match

        if score > best_score:
            best_score, best = score, cand

    if best is None:
        return None, 0.0
    return best, round(min(best_score, 1.0), 2)


def to_location_row(city: dict, geo: dict, confidence: float) -> dict[str, Any]:
    addr = geo.get("address_obj") or {}
    return {
        "ta_location_id": str(geo["location_id"]),
        "name": geo.get("name"),
        "city_id": city["id"],
        "state": addr.get("state"),
        "country": addr.get("country"),
        "match_confidence": confidence,
        "verified": False,
        "raw": geo,  # wrapped as Jsonb in the upsert layer
    }
