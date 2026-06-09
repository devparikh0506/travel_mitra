"""Minimal DAG to confirm the Airflow install parses DAGs and the scheduler runs tasks.

Delete once the real travel_mitra_dag is in place.
"""

from __future__ import annotations

import pendulum
from airflow.sdk import dag, task


@dag(
    dag_id="smoke_test",
    schedule=None,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    tags=["smoke"],
)
def smoke_test():
    @task
    def hello() -> str:
        print("Airflow is alive — Travel Mitra 2.0")
        return "ok"

    hello()


smoke_test()
