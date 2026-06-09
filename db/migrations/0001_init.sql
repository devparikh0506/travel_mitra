-- Travel Mitra 2.0 — migration 0001: baseline + cities.
--
-- Scope is intentionally limited to what we can model from EVIDENCE:
--   * extension + migration tracking + shared trigger helper
--   * cities       -> derived from the real simplemaps uscities.csv header
--   * raw_* staging -> field-agnostic JSONB landing zones (safe regardless)
-- The API-driven typed tables (locations, hotels, reviews, review_embeddings)
-- are deferred to 0002, to be modeled AFTER sampling Xotelo + TripAdvisor.
--
-- Applied automatically on first init of the postgres-data volume
-- (mounted into /docker-entrypoint-initdb.d). Idempotent: safe to re-run.

BEGIN;

-- --------------------------------------------------------------------------
-- Extensions
-- --------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS vector;

-- --------------------------------------------------------------------------
-- Migration tracking (plain .sql files, not a migration library)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- --------------------------------------------------------------------------
-- updated_at trigger helper (reused by later tables too)
-- --------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- --------------------------------------------------------------------------
-- cities  (source: simplemaps uscities.csv v1.93 basic — LEAN subset)
--   Columns chosen from the real CSV header; `id` is simplemaps' own id.
--   ETL selects "popular" cities via `ranking` (configurable Airflow Variable;
--   MVP uses ranking = 1), ordered by population.
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cities (
    id          BIGINT PRIMARY KEY,                 -- simplemaps id, e.g. 1840034016
    name        TEXT   NOT NULL,                    -- source column "city", e.g. "New York"
    state_id    TEXT,                               -- e.g. "NY"
    state_name  TEXT,                               -- e.g. "New York"
    lat         DOUBLE PRECISION,
    lng         DOUBLE PRECISION,
    population  INTEGER,                             -- sort key for "popular" cities
    ranking     SMALLINT,                           -- simplemaps importance tier (1 = major)
    timezone    TEXT,                               -- IANA tz, e.g. "America/New_York"
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cities_state   ON cities (state_id);
CREATE INDEX IF NOT EXISTS idx_cities_name    ON cities (name);
CREATE INDEX IF NOT EXISTS idx_cities_ranking ON cities (ranking);

DROP TRIGGER IF EXISTS trg_cities_updated ON cities;
CREATE TRIGGER trg_cities_updated BEFORE UPDATE ON cities
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- --------------------------------------------------------------------------
-- raw staging  (land source payloads before transform; field-agnostic)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS raw_tripadvisor (
    id          BIGSERIAL PRIMARY KEY,
    endpoint    TEXT NOT NULL,                       -- e.g. "location_search" / "reviews"
    ref_id      TEXT,                                -- city id / location id this relates to
    payload     JSONB NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_raw_ta_ref ON raw_tripadvisor (endpoint, ref_id);

CREATE TABLE IF NOT EXISTS raw_xotelo (
    id          BIGSERIAL PRIMARY KEY,
    ref_id      TEXT,                                -- location key this list relates to
    payload     JSONB NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_raw_xotelo_ref ON raw_xotelo (ref_id);

-- --------------------------------------------------------------------------
-- record this migration
-- --------------------------------------------------------------------------
INSERT INTO schema_migrations (version) VALUES ('0001_init')
ON CONFLICT (version) DO NOTHING;

COMMIT;
