"""Query embedding — reuses the SAME Gemini model the documents used.

Documents were embedded with gemini-embedding-001 / RETRIEVAL_DOCUMENT (768-d);
queries must use the same model with RETRIEVAL_QUERY for correct asymmetric
retrieval. Reusing etl.embed.embedder guarantees the model matches.
"""

from __future__ import annotations

from etl.embed.embedder import embed_documents


def embed_query(text: str) -> list[float]:
    return embed_documents([text], task_type="RETRIEVAL_QUERY")[0]
