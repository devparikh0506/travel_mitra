"""Agent settings from environment.

Defaults target HOST access (localhost:5433) since the notebook/venv runs on
the host; inside Docker (FastAPI later) DATABASE_URL is overridden to
postgres-data:5432.
"""

from __future__ import annotations

import os


class Settings:
    def __init__(self) -> None:
        self.database_url = os.getenv(
            "DATABASE_URL", "postgresql://app:app@localhost:5433/travelmitra"
        )
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.model = os.getenv("AGENT_MODEL", "gemini-2.5-flash")


settings = Settings()
