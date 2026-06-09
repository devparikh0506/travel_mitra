"""Travel Mitra FastAPI app — SSE /chat over the LangGraph agent + /health.

The agent and an async Postgres checkpointer are built once at startup and
reused; thread_id in each request carries durable multi-turn context.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sse_starlette.sse import EventSourceResponse
from starlette.concurrency import run_in_threadpool

load_dotenv()  # GEMINI_API_KEY, LANGSMITH_* (DATABASE_URL defaults to localhost:5433)

from agent.config import settings          # noqa: E402  (after load_dotenv)
from agent.db import query                 # noqa: E402
from agent.graph import build_agent        # noqa: E402
from app.runtime import stream_events      # noqa: E402
from app.schemas import ChatRequest, HealthResponse  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Async checkpointer kept open for the app's lifetime.
    async with AsyncPostgresSaver.from_conn_string(settings.database_url) as checkpointer:
        await checkpointer.setup()                  # idempotent
        app.state.agent = build_agent(checkpointer)
        yield


app = FastAPI(title="Travel Mitra", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    try:
        await run_in_threadpool(query, "SELECT 1")
        db_ok = True
    except Exception:
        db_ok = False
    return HealthResponse(status="ok" if db_ok else "degraded", db=db_ok)


@app.post("/chat")
async def chat(req: ChatRequest):
    async def event_stream():
        async for event in stream_events(app.state.agent, req.message, req.thread_id):
            yield event
        yield {"event": "done", "data": "[DONE]"}

    return EventSourceResponse(event_stream())
