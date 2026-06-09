"""Request/response models for the API boundary (validated input)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    thread_id: str = Field(..., min_length=1, max_length=128,
                           description="Conversation id; carries multi-turn context.")
    message: str = Field(..., min_length=1, max_length=4000)


class HealthResponse(BaseModel):
    status: str
    db: bool
