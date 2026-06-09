"""Build the ReAct agent: gemini-2.5-flash + the 4 constrained tools.

Optionally pass a checkpointer (e.g. PostgresSaver) for durable per-thread
conversation state.
"""

from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from agent.llm import build_llm
from agent.prompts import SYSTEM_PROMPT
from agent.tools.emit import say, show_hotels
from agent.tools.hotels import get_hotel_details, search_hotels
from agent.tools.locations import search_locations
from agent.tools.reviews import search_reviews

# Data tools gather info for the agent; emission tools (say/show_hotels) talk to the user.
TOOLS = [search_locations, search_hotels, get_hotel_details, search_reviews, say, show_hotels]


def build_agent(checkpointer=None):
    return create_react_agent(
        build_llm(),
        TOOLS,
        prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )


def chat(agent, text: str, thread_id: str = "default") -> str:
    """Send one user message; return the assistant's final reply text."""
    result = agent.invoke(
        {"messages": [("user", text)]},
        config={"configurable": {"thread_id": thread_id}},
    )
    return result["messages"][-1].content


def chat_verbose(agent, text: str, thread_id: str = "default") -> str:
    """Stream the run, pretty-printing each step (tool calls, tool results,
    reasoning) using LangChain's structured message formatting. Returns the
    final reply text.
    """
    config = {"configurable": {"thread_id": thread_id}}
    last = None
    for state in agent.stream({"messages": [("user", text)]}, config,
                              stream_mode="values"):
        last = state["messages"][-1]
        last.pretty_print()   # human / AI(tool_calls) / tool / AI(final)
    return last.content if last is not None else ""
