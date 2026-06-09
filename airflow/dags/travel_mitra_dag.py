"""Travel Mitra ETL DAG.

Built incrementally: cities -> locations -> hotels -> reviews -> embeddings.
Currently implemented stages: load_cities.

All operational knobs are DAG `params` (runtime-overridable via "Trigger DAG
w/ config", each with a default). Secrets/infra live in env (etl.config).
"""

from __future__ import annotations

import time

import pendulum
from airflow.exceptions import AirflowSkipException
from airflow.sdk import Param, Variable, dag, get_current_context, task

from etl.budget import log_call, remaining_budget
from etl.config import settings
from etl.db import get_conn
from etl.embed.embedder import EMBEDDING_MODEL, embed_documents
from etl.load.upserts import (
    find_location_by_city,
    insert_review_embeddings,
    land_raw_tripadvisor,
    land_raw_xotelo,
    mark_reviews_fetched,
    select_cities_for_processing,
    select_hotels_needing_reviews,
    select_reviews_to_embed,
    upsert_cities,
    upsert_hotels,
    upsert_location,
    upsert_reviews,
)
from etl.sources.simplemaps import read_cities_csv
from etl.sources.tripadvisor import get_reviews, search_geos
from etl.sources.xotelo import list_hotels
from etl.transforms.cities import to_city_rows
from etl.transforms.hotels import stratify_top_k, to_hotel_row
from etl.transforms.locations import pick_best_geo, to_location_row
from etl.transforms.reviews import to_embedding_row, to_embedding_text, to_review_row

PARAMS = {
    "csv_path": Param(
        settings.default_csv_path, type="string",
        description="In-container path to the simplemaps uscities CSV.",
    ),
    "city_ranking_max": Param(
        1, type="integer", minimum=1, maximum=5,
        description="Max simplemaps ranking tier to include (1 = major cities).",
    ),
    "top_n_cities": Param(
        25, type="integer", minimum=1,
        description="How many cities (by population) to run the API pipeline over.",
    ),
    # --- knobs for later stages (defined now so the trigger form is complete) ---
    "xotelo_page_limit": Param(50, type="integer", minimum=1, maximum=100),
    "xotelo_max_pages": Param(5, type="integer", minimum=1),
    "review_hotels_per_location": Param(20, type="integer", minimum=1),
    "embed_batch_size": Param(100, type="integer", minimum=1, maximum=100,
                              description="Texts per Gemini batch (max 100)."),
    "embed_pause_seconds": Param(0, type="integer", minimum=0,
                                 description="Pause between embedding batches. 0 on paid tier; raise on free tier to dodge RPM 429s."),
    "min_match_confidence": Param(0.5, type="number", minimum=0, maximum=1),
    "price_tier_budget_max": Param(200, type="integer", minimum=1),
    "price_tier_mid_max": Param(300, type="integer", minimum=1),
}


@dag(
    dag_id="travel_mitra_etl",
    schedule=None,                       # manual trigger (MVP backfill)
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    params=PARAMS,
    tags=["travel-mitra", "etl"],
)
def travel_mitra_etl():

    @task
    def load_cities() -> list[dict]:
        """Load ALL cities (free reference data), return the top-N to process."""
        params = get_current_context()["params"]
        df = read_cities_csv(params["csv_path"])
        rows = to_city_rows(df)
        with get_conn() as conn:
            upserted = upsert_cities(conn, rows)
            selected = select_cities_for_processing(
                conn, params["city_ranking_max"], params["top_n_cities"]
            )
        print(f"[load_cities] upserted={upserted} selected={len(selected)}")
        return selected

    @task
    def resolve_locations(city: dict) -> dict | None:
        """City -> TripAdvisor geo (lat/lng disambiguated). Idempotent + budget-aware."""
        params = get_current_context()["params"]
        monthly_cap = int(Variable.get("TRIPADVISOR_MONTHLY_BUDGET", default=4500))
        min_conf = float(params["min_match_confidence"])

        with get_conn() as conn:
            existing = find_location_by_city(conn, city["id"])
            if existing:                                  # already resolved -> 0 calls
                return {"city_id": city["id"], "location_id": existing["id"],
                        "ta_location_id": existing["ta_location_id"]}

            if remaining_budget(conn, monthly_cap) <= 0:
                raise AirflowSkipException("TripAdvisor monthly budget exhausted")

            query = f"{city['name']}, {city['state_id']}"
            payload = search_geos(query)   # no latLong: it over-localizes to neighborhoods
            log_call(conn, "tripadvisor", "location_search", str(city["id"]))
            land_raw_tripadvisor(conn, "location_search", city["id"], payload)

            geo, confidence = pick_best_geo(city, payload)
            if geo is None or confidence < min_conf:
                print(f"[resolve_locations] no confident geo for '{query}' (conf={confidence})")
                return None

            row = to_location_row(city, geo, confidence)
            saved = upsert_location(conn, row)
            print(f"[resolve_locations] '{query}' -> g{row['ta_location_id']} "
                  f"({row['name']}) conf={confidence}")
            return {"city_id": city["id"], "location_id": saved["id"],
                    "ta_location_id": saved["ta_location_id"]}

    @task
    def fetch_hotels(location: dict | None) -> int:
        """Paginate Xotelo /list for a geo and upsert hotels (free API)."""
        if not location:
            return 0
        params = get_current_context()["params"]
        page_limit = int(params["xotelo_page_limit"])
        max_pages = int(params["xotelo_max_pages"])
        geo_key = f"g{location['ta_location_id']}"
        loc_id = location["location_id"]

        total = 0
        with get_conn() as conn:
            offset = 0
            for _ in range(max_pages):
                payload = list_hotels(geo_key, offset=offset, limit=page_limit)
                if payload.get("error"):
                    print(f"[fetch_hotels] {geo_key} error: {payload['error']}")
                    break
                land_raw_xotelo(conn, geo_key, payload)
                result = payload.get("result") or {}
                items = result.get("list") or []
                if not items:
                    break
                upsert_hotels(conn, [to_hotel_row(it, loc_id) for it in items])
                total += len(items)
                offset += page_limit
                if offset >= int(result.get("total_count") or 0):
                    break
        print(f"[fetch_hotels] {geo_key} -> upserted {total} hotels")
        return total

    @task
    def fetch_reviews(location: dict | None) -> int:
        """Fetch TripAdvisor reviews for the stratified top-K hotels of a location.

        Idempotent (skips hotels already fetched) and budget-gated (stops before
        exceeding the monthly TripAdvisor cap).
        """
        if not location:
            return 0
        params = get_current_context()["params"]
        monthly_cap = int(Variable.get("TRIPADVISOR_MONTHLY_BUDGET", default=4500))
        k = int(params["review_hotels_per_location"])
        budget_max = int(params["price_tier_budget_max"])
        mid_max = int(params["price_tier_mid_max"])
        loc_id = location["location_id"]

        fetched = 0
        with get_conn() as conn:
            candidates = select_hotels_needing_reviews(conn, loc_id)
            selected = stratify_top_k(candidates, k, budget_max, mid_max)
            for hotel in selected:
                if remaining_budget(conn, monthly_cap) <= 0:
                    print("[fetch_reviews] TripAdvisor monthly budget exhausted; stopping")
                    break
                payload = get_reviews(hotel["ta_hotel_id"])
                log_call(conn, "tripadvisor", "reviews", hotel["ta_hotel_id"])
                land_raw_tripadvisor(conn, "reviews", hotel["ta_hotel_id"], payload)
                rows = [to_review_row(r, hotel["id"]) for r in (payload.get("data") or [])]
                upsert_reviews(conn, rows)
                mark_reviews_fetched(conn, hotel["id"])
                fetched += len(rows)
        print(f"[fetch_reviews] location={loc_id} hotels={len(selected)} reviews={fetched}")
        return fetched

    @task
    def embed_reviews() -> int:
        """Embed un-embedded reviews (Gemini, batched) into review_embeddings.

        Idempotent: only reviews without an embedding are processed.
        """
        params = get_current_context()["params"]
        batch = int(params["embed_batch_size"])
        pause = int(params["embed_pause_seconds"])
        total = 0
        with get_conn() as conn:
            pending = select_reviews_to_embed(conn)
            for i in range(0, len(pending), batch):
                chunk = pending[i:i + batch]
                vectors = embed_documents([to_embedding_text(r) for r in chunk])
                insert_review_embeddings(
                    conn,
                    [to_embedding_row(r, v, EMBEDDING_MODEL) for r, v in zip(chunk, vectors)],
                )
                total += len(chunk)
                if pause and i + batch < len(pending):
                    time.sleep(pause)   # stay under free-tier RPM
        print(f"[embed_reviews] embedded {total} reviews")
        return total

    cities = load_cities()
    locations = resolve_locations.expand(city=cities)
    hotels = fetch_hotels.expand(location=locations)
    reviews = fetch_reviews.expand(location=locations)
    embed = embed_reviews()
    hotels >> reviews >> embed   # hotels -> reviews -> embeddings


travel_mitra_etl()
