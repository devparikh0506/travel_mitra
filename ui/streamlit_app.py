"""Travel Mitra chat UI — agent emits messages step by step.

- status  -> transient loader ("🔎 Searching…")
- message -> a text bubble (say)
- hotels  -> a horizontal card carousel (show_hotels), each card has an in-card
             "💬 Ask" button (native widget -> no page reload, same thread)
Sidebar lists previous chats; each conversation has its own thread_id (durable
context via the API's Postgres checkpointer).
"""

from __future__ import annotations

import json
import os
import uuid

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Travel Mitra", page_icon="🏨", layout="wide")

# Make the hotel-card row a horizontally-scrollable carousel WITHOUT affecting
# other column layouts — scoped via :has() to the row containing a card marker.
st.markdown(
    """
    <style>
    div[data-testid="stHorizontalBlock"]:has(.tm-card-marker){
        overflow-x:auto; flex-wrap:nowrap; gap:12px; padding-bottom:8px;
    }
    div[data-testid="stHorizontalBlock"]:has(.tm-card-marker) > div[data-testid="column"]{
        min-width:240px; flex:0 0 240px;
    }
    .tm-card-marker{display:none;}
    </style>
    """,
    unsafe_allow_html=True,
)


# --- renderers -------------------------------------------------------------
def render_hotels(hotels: list[dict], key: str) -> None:
    hotels = hotels[:6]
    if not hotels:
        return
    cols = st.columns(len(hotels))
    for i, h in enumerate(hotels):
        with cols[i]:
            st.markdown('<span class="tm-card-marker"></span>', unsafe_allow_html=True)
            with st.container(border=True):
                if h.get("image_url"):
                    st.image(h["image_url"], use_container_width=True)
                st.markdown(f"**{h.get('name')}**")
                price = h.get("price_min")
                price_txt = f"from ${price}/night" if price else "price varies"
                st.caption(f"⭐ {h.get('rating')} · {price_txt}")
                mentions = ", ".join((h.get("mentions") or [])[:3])
                if mentions:
                    st.caption(mentions)
                if h.get("url"):
                    st.markdown(f"[TripAdvisor ↗]({h['url']})")
                if st.button("💬 Ask", key=f"ask_{key}_{h.get('hotel_id')}",
                             use_container_width=True):
                    st.session_state.pending_prompt = f"Tell me more about {h.get('name')}"
                    st.rerun()


def _render_body(seg: dict, key: str) -> None:
    if seg["type"] == "text":
        st.markdown(seg["content"])
    elif seg["type"] == "hotels":
        render_hotels(seg["data"], key)


def render_segment(seg: dict, key: str) -> None:
    with st.chat_message("assistant"):
        _render_body(seg, key)


# --- SSE ------------------------------------------------------------------
def iter_sse(resp):
    event, data_lines = None, []
    for raw in resp.iter_lines():
        line = raw.rstrip("\r")
        if line == "":
            if event:
                yield event, "\n".join(data_lines)
            event, data_lines = None, []
            continue
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            d = line[5:]
            if d.startswith(" "):
                d = d[1:]
            data_lines.append(d)


def run_turn(message: str, thread_id: str, turn_key: str) -> list[dict]:
    segments: list[dict] = []
    loader = st.empty()
    loader.markdown("_Thinking…_")
    payload = {"thread_id": thread_id, "message": message}

    with httpx.stream("POST", f"{API_URL}/chat", json=payload, timeout=120) as resp:
        for event, data in iter_sse(resp):
            if event == "done":
                break
            if event == "status":                # transient loader, not a saved bubble
                loader.markdown(f"_{data}_")
                continue
            if event == "message":
                seg = {"type": "text", "content": data}
            elif event == "hotels":
                seg = {"type": "hotels", "data": json.loads(data)}
            else:
                continue
            segments.append(seg)
            render_segment(seg, f"{turn_key}_{len(segments) - 1}")

    loader.empty()
    return segments


# --- conversations ---------------------------------------------------------
def _new_conversation() -> str:
    tid = str(uuid.uuid4())
    st.session_state.conversations[tid] = {"title": "New chat", "messages": []}
    st.session_state.current = tid
    return tid


if "conversations" not in st.session_state:
    st.session_state.conversations = {}
    _new_conversation()

convo = st.session_state.conversations[st.session_state.current]
thread_id = st.session_state.current
messages = convo["messages"]

with st.sidebar:
    st.title("🏨 Travel Mitra")
    if st.button("➕ New chat", use_container_width=True):
        _new_conversation()
        st.rerun()
    st.divider()
    st.caption("Previous chats")
    for tid, c in reversed(list(st.session_state.conversations.items())):
        is_current = tid == st.session_state.current
        if st.button(c["title"][:32] or "New chat", key=f"conv_{tid}",
                     use_container_width=True,
                     type="primary" if is_current else "secondary"):
            st.session_state.current = tid
            st.rerun()

# history
for idx, m in enumerate(messages):
    if m["role"] == "user":
        with st.chat_message("user"):
            st.markdown(m["content"])
    else:
        for sidx, seg in enumerate(m.get("segments", [])):
            render_segment(seg, f"{idx}_{sidx}")

# new turn (typed input or an in-card "Ask" click)
prompt = st.chat_input("Ask about hotels (e.g. 'hotels in NYC under $300, 4+ stars')")
prompt = prompt or st.session_state.pop("pending_prompt", None)

if prompt:
    if convo["title"] == "New chat":             # name the chat from its first message
        convo["title"] = prompt
    messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    segments = run_turn(prompt, thread_id, str(len(messages)))
    messages.append({"role": "assistant", "segments": segments})
