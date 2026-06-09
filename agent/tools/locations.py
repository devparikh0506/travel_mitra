"""search_locations — resolve a user's place text to known location_id(s)."""

from __future__ import annotations

from langchain_core.tools import tool

from agent import queries


@tool
def search_locations(query_text: str, state: str | None = None) -> list[dict]:
    """Resolve a city/area name to known locations in the catalog.

    Turns place text ("New York", "LA") into a location_id used by other tools.
    Optionally filter by US state name ("California") to disambiguate same-named
    cities. Returns [{location_id, name, state, city}]; empty means not covered.
    """
    return queries.find_locations(query_text, state)
