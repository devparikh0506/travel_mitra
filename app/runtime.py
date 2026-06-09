"""Agent streaming for the API — emits typed events for the UI.

Streams two channels from the agent run:
- assistant text tokens  -> {"event": "token", ...}
- structured tool results -> {"event": "hotels"|"hotel"|"reviews", ...}  (JSON)

The structured events let the UI render hotel cards / review panels alongside the
streamed prose, without parsing the assistant's text.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from langchain_core.messages import AIMessageChunk, ToolMessage

# Data tools gather info for the agent (announced as status); emission tools talk to the user.
_DATA_TOOLS = {"search_locations", "search_hotels", "get_hotel_details", "search_reviews"}


def _text_of(chunk: AIMessageChunk) -> str:
    """Extract assistant text from a chunk.

    Gemini 2.5 returns content as a list of blocks (text + thinking/signature
    parts); we keep only the text, dropping reasoning/signature metadata.
    """
    content = chunk.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if isinstance(part, str):
                out.append(part)
            elif isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                out.append(part["text"])
        return "".join(out)
    return ""


def _status_for(tool_call: dict) -> str | None:
    """Human-friendly 'what the agent is doing' line for a tool call."""
    name = tool_call.get("name")
    args = tool_call.get("args") or {}
    if name == "search_locations":
        q = (args.get("query_text") or "").strip()
        return f"🔎 Finding {q}…" if q else "🔎 Finding the location…"
    if name == "search_hotels":
        bits = []
        if args.get("price_max"):
            bits.append(f"under ${args['price_max']}")
        if args.get("min_rating"):
            bits.append(f"{args['min_rating']}★+")
        return "🏨 Searching hotels" + ((" " + ", ".join(bits)) if bits else "") + "…"
    if name == "get_hotel_details":
        return "📋 Pulling hotel details…"
    if name == "search_reviews":
        return "📚 Reading guest reviews…"
    return None


def _tool_calls(chunk: AIMessageChunk) -> list[dict]:
    """Tool calls on a chunk; fall back to (partial) tool_call_chunks for the name."""
    if chunk.tool_calls:
        return chunk.tool_calls
    return [
        {"name": c.get("name"), "args": {}, "id": c.get("id") or c.get("index")}
        for c in (chunk.tool_call_chunks or [])
        if c.get("name")
    ]


async def stream_events(agent, message: str, thread_id: str) -> AsyncIterator[dict]:
    config = {"configurable": {"thread_id": thread_id}}
    seen_calls: set = set()       # data-tool call ids already announced as status
    final_text = ""               # fallback: plain reply if the agent skips say()
    sent_message = False
    async for chunk, _meta in agent.astream(
        {"messages": [("user", message)]}, config, stream_mode="messages"
    ):
        if isinstance(chunk, AIMessageChunk):
            for tc in _tool_calls(chunk):                 # announce data tools as status
                cid = tc.get("id") or tc.get("name")
                if tc.get("name") in _DATA_TOOLS and cid and cid not in seen_calls:
                    seen_calls.add(cid)
                    status = _status_for(tc)
                    if status:
                        yield {"event": "status", "data": status}
            text = _text_of(chunk)                        # accumulate for the fallback
            if text and text != final_text:
                final_text = text if text.startswith(final_text) else final_text + text
        elif isinstance(chunk, ToolMessage):
            if chunk.name == "say":                       # user-facing message
                sent_message = True
                yield {"event": "message", "data": chunk.content}
            elif chunk.name == "show_hotels":             # user-facing cards
                yield {"event": "hotels", "data": chunk.content}
            # data-tool results are internal to the agent — not surfaced

    if not sent_message and final_text.strip():           # agent answered in plain text
        yield {"event": "message", "data": final_text}
