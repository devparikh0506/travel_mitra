"""Gemini chat model for the agent (langchain-google-genai)."""

from __future__ import annotations

from langchain_google_genai import ChatGoogleGenerativeAI

from agent.config import settings


def build_llm(temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=settings.model,                 # gemini-2.5-flash
        google_api_key=settings.gemini_api_key,
        temperature=temperature,
    )
