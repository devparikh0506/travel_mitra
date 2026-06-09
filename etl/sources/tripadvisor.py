"""TripAdvisor Content API client (geo search + reviews).

Retries only transient failures (network, 429, 5xx) with exponential backoff.
Call accounting/budget is handled by the caller via etl.budget.
"""

from __future__ import annotations

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from etl.config import settings

_BASE = "https://api.content.tripadvisor.com/api/v1"
_RETRY_STATUS = {429, 500, 502, 503, 504}


class _RetryableHTTP(Exception):
    """Transient HTTP status worth retrying."""


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, max=30),
    retry=retry_if_exception_type((httpx.TransportError, _RetryableHTTP)),
    reraise=True,
)
def _get(path: str, params: dict) -> dict:
    params = {**params, "key": settings.tripadvisor_api_key}
    # Referer must match an allowlisted domain on the API key, else 403.
    headers = {"accept": "application/json", "Referer": settings.tripadvisor_referer}
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{_BASE}{path}", params=params, headers=headers)
    if resp.status_code in _RETRY_STATUS:
        raise _RetryableHTTP(f"{resp.status_code} for {path}")
    resp.raise_for_status()
    return resp.json()


def search_geos(query: str, lat: float | None = None, lng: float | None = None,
                language: str = "en") -> dict:
    """location/search restricted to geos; lat/lng narrow to the right city."""
    params: dict = {"searchQuery": query, "category": "geos", "language": language}
    if lat is not None and lng is not None:
        params["latLong"] = f"{lat},{lng}"
    return _get("/location/search", params)


def get_reviews(location_id: str, language: str = "en") -> dict:
    """Up to 5 most-recent reviews for a hotel location_id (no pagination)."""
    return _get(f"/location/{location_id}/reviews", {"language": language})
