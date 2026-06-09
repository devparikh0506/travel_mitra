"""Xotelo API client (free, no key) — hotel listings per geo location_key."""

from __future__ import annotations

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

_BASE = "https://data.xotelo.com/api"
_RETRY_STATUS = {429, 500, 502, 503, 504}


class _RetryableHTTP(Exception):
    """Transient HTTP status worth retrying."""


@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, max=30),
    retry=retry_if_exception_type((httpx.TransportError, _RetryableHTTP)),
    reraise=True,
)
def list_hotels(location_key: str, offset: int = 0, limit: int = 30,
                sort: str = "best_value") -> dict:
    """One page of hotels for a geo `location_key` (e.g. 'g60763')."""
    params = {"location_key": location_key, "offset": offset, "limit": limit, "sort": sort}
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{_BASE}/list", params=params)
    if resp.status_code in _RETRY_STATUS:
        raise _RetryableHTTP(f"{resp.status_code} for /list")
    resp.raise_for_status()
    return resp.json()
