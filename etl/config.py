"""Secrets + infrastructure settings, sourced from environment variables.

These are the values that should NOT live in the Airflow UI (DB DSN, API keys).
Operational knobs (top_n_cities, batch sizes, ...) are DAG `params` instead.

Plain os.getenv — no extra dependency; defaults match docker-compose.
"""

from __future__ import annotations

import os


class Settings:
    def __init__(self) -> None:
        # libpq conninfo — psycopg3 (no SQLAlchemy).
        self.database_url = os.getenv(
            "DATABASE_URL", "postgresql://app:app@postgres-data:5432/travelmitra"
        )
        self.tripadvisor_api_key = os.getenv("TRIPADVISOR_API_KEY", "")
        # Must match an allowlisted domain on the TripAdvisor key (sent as Referer header).
        self.tripadvisor_referer = os.getenv("TRIPADVISOR_REFERER", "https://dev-parikh.com")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        # ./data is mounted to /opt/airflow/seed in docker-compose.
        self.default_csv_path = os.getenv(
            "DEFAULT_CSV_PATH",
            "/opt/airflow/seed/simplemaps_uscities_basicv1.93/uscities.csv",
        )


settings = Settings()
