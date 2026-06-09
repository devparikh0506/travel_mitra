"""Emission tools — how the agent talks to the user ("talking is an action").

The agent calls these as steps while it reasons; the app surfaces each as a
chat message. say() text and show_hotels() cards reach the user; the data tools
(search_*) are internal and do not.
"""

from __future__ import annotations

import json

from langchain_core.tools import tool

from agent import queries


@tool
def say(message: str) -> str:
    """Send ONE chat message to the user — an intro, a recommendation, a question,
    or an answer. This is the only way to talk to the user. Call it as many times
    as you need, in the order the user should see the messages."""
    return message            # surfaced verbatim to the user by the app


@tool
def show_hotels(hotel_ids: list[int]) -> str:
    """Show hotel cards to the user as a carousel (max 6). Pass the hotel_ids
    (from search_hotels) you want to display, best first."""
    cards = queries.hotels_by_ids(hotel_ids[:6])
    return json.dumps(cards, default=str)
