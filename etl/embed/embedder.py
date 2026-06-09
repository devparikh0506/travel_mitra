"""Gemini embeddings via the REST API (httpx — no SDK, avoids dep conflicts).

gemini-embedding-001 @ 768-dim. Documents use RETRIEVAL_DOCUMENT; the agent
should embed user queries with RETRIEVAL_QUERY at search time (asymmetric).
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
from etl.observability import traceable

EMBEDDING_MODEL = "gemini-embedding-001"   # recorded per row in review_embeddings
EMBEDDING_DIM = 768
_MODEL = f"models/{EMBEDDING_MODEL}"
_URL = f"https://generativelanguage.googleapis.com/v1beta/{_MODEL}:batchEmbedContents"
_DIM = EMBEDDING_DIM
_RETRY_STATUS = {429, 500, 502, 503, 504}


class _RetryableHTTP(Exception):
    """Transient HTTP status worth retrying."""


@traceable(run_type="embedding", name="gemini.embed_documents")
@retry(
    # Patient enough to outlast a per-minute RPM window reset on the free tier.
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=2, min=5, max=60),
    retry=retry_if_exception_type((httpx.TransportError, _RetryableHTTP)),
    reraise=True,
)
def embed_documents(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """Embed a batch of texts; returns one 768-dim vector per input, in order."""
    if not texts:
        return []
    body = {
        "requests": [
            {
                "model": _MODEL,
                "content": {"parts": [{"text": t}]},
                "taskType": task_type,
                "outputDimensionality": _DIM,
            }
            for t in texts
        ]
    }
    with httpx.Client(timeout=60) as client:
        resp = client.post(_URL, params={"key": settings.gemini_api_key}, json=body)
    if resp.status_code in _RETRY_STATUS:
        raise _RetryableHTTP(f"{resp.status_code} from batchEmbedContents")
    resp.raise_for_status()
    return [item["values"] for item in resp.json()["embeddings"]]
