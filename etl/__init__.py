"""Travel Mitra ETL package — sources, transforms, load, embed.

Thin DAG, fat package: all ETL logic lives here so it is unit-testable and
reusable outside Airflow (e.g. in the agent prototype notebook).
"""
