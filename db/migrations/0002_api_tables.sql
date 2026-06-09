-- Travel Mitra 2.0 — migration 0002: API-driven typed tables.
--
-- Modeled from REAL sampled payloads:
--   * locations         <- TripAdvisor location/search?category=geos
--   * hotels            <- Xotelo /api/list
--   * reviews           <- TripAdvisor location/{id}/reviews (5 per call, no pagination)
--   * review_embeddings <- Gemini gemini-embedding-001 (768-dim)
--   * api_call_log      <- budget guardrail for the 5k/month TripAdvisor cap
--
-- Idempotent: safe to re-run / auto-applied via initdb on a fresh volume.
-- Depends on 0001 (vector extension, set_updated_at(), cities).

BEGIN;

-- --------------------------------------------------------------------------
-- locations  (TripAdvisor GEO per city; geo id == Xotelo key minus "g")
--   No lat/lng: we reuse the city's coordinates from 0001.
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS locations (
    id               BIGSERIAL PRIMARY KEY,
    ta_location_id   TEXT NOT NULL UNIQUE,           -- TA geo id, e.g. "60763" -> Xotelo "g60763"
    name             TEXT NOT NULL,                  -- e.g. "New York City"
    city_id          BIGINT REFERENCES cities (id) ON DELETE SET NULL,
    state            TEXT,                           -- address_obj.state (audit/disambiguation)
    country          TEXT,                           -- address_obj.country
    match_confidence REAL,                           -- 0..1 score from city->geo matching
    verified         BOOLEAN NOT NULL DEFAULT FALSE, -- set TRUE after the one-time geo curation pass
    raw              JSONB,                          -- full search result for this geo
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_locations_city ON locations (city_id);

DROP TRIGGER IF EXISTS trg_locations_updated ON locations;
CREATE TRIGGER trg_locations_updated BEFORE UPDATE ON locations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- --------------------------------------------------------------------------
-- hotels  (Xotelo /api/list)
--   key format "g{geo}-d{hotel}"  -> ta_hotel_id = "{hotel}", xotelo_key = full key
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hotels (
    id                 BIGSERIAL PRIMARY KEY,
    ta_hotel_id        TEXT NOT NULL UNIQUE,         -- "d" part, e.g. "23448880" (== TA review location_id)
    xotelo_key         TEXT NOT NULL,               -- full "g60763-d23448880" (for Xotelo /rates later)
    location_id        BIGINT NOT NULL REFERENCES locations (id) ON DELETE CASCADE,
    name               TEXT NOT NULL,
    accommodation_type TEXT,                         -- "Hotel" / "Hostel" / ...
    url                TEXT,
    rating             NUMERIC(2,1),                 -- review_summary.rating (0.0-5.0)
    num_reviews        INTEGER,                      -- review_summary.count
    price_min          INTEGER,                      -- price_ranges.minimum (USD/night)
    price_max          INTEGER,                      -- price_ranges.maximum
    lat                DOUBLE PRECISION,             -- geo.latitude (per-hotel, precise)
    lng                DOUBLE PRECISION,
    image_url          TEXT,
    mentions           TEXT[],                       -- ["Centrally Located","Modern",...]
    -- ETL control:
    review_score       DOUBLE PRECISION,            -- Bayesian weighted rating, drives top-K selection
    reviews_fetched_at TIMESTAMPTZ,                  -- incremental gate: NULL = reviews not yet pulled
    raw                JSONB,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_hotels_location      ON hotels (location_id);
CREATE INDEX IF NOT EXISTS idx_hotels_price         ON hotels (price_min);
CREATE INDEX IF NOT EXISTS idx_hotels_rating        ON hotels (rating);
CREATE INDEX IF NOT EXISTS idx_hotels_review_score  ON hotels (review_score DESC);
-- Fast "which top-K hotels in this location still need reviews?" lookup.
CREATE INDEX IF NOT EXISTS idx_hotels_reviews_todo  ON hotels (location_id, review_score DESC)
    WHERE reviews_fetched_at IS NULL;

DROP TRIGGER IF EXISTS trg_hotels_updated ON hotels;
CREATE TRIGGER trg_hotels_updated BEFORE UPDATE ON hotels
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- --------------------------------------------------------------------------
-- reviews  (TripAdvisor location/{id}/reviews — guest review text for RAG)
--   owner_response / user / subratings intentionally NOT columned (kept in raw).
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reviews (
    id            BIGSERIAL PRIMARY KEY,
    ta_review_id  TEXT NOT NULL UNIQUE,             -- review id, e.g. "1063412804"
    hotel_id      BIGINT NOT NULL REFERENCES hotels (id) ON DELETE CASCADE,
    rating        INTEGER,                           -- 1-5
    title         TEXT,
    text          TEXT,
    trip_type     TEXT,                              -- "Couples" / "Business" / "Solo travel" / ...
    travel_date   DATE,
    published_at  TIMESTAMPTZ,
    lang          TEXT,
    raw           JSONB,                             -- full review (owner_response, user, subratings)
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reviews_hotel  ON reviews (hotel_id);
CREATE INDEX IF NOT EXISTS idx_reviews_rating ON reviews (rating);

-- --------------------------------------------------------------------------
-- review_embeddings  (Gemini gemini-embedding-001, 768-dim; RETRIEVAL_DOCUMENT)
--
--   Denormalized hotel/location metadata enables single-table HYBRID search:
--   vector similarity (embedding <=> query) + structured filters
--   (geo, city, price band, hotel rating, accommodation type) in one query,
--   with no joins. Volatile fields (price/rating/type/location) are kept in
--   sync from `hotels` via the trigger below; the embed task fills them on
--   insert.
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS review_embeddings (
    review_id          BIGINT PRIMARY KEY REFERENCES reviews (id) ON DELETE CASCADE,
    embedding          vector(768) NOT NULL,
    -- denormalized filter metadata:
    hotel_id           BIGINT,                       -- hotel scope
    location_id        BIGINT,                       -- geo (city/area) scope
    city_id            BIGINT,                       -- city scope
    accommodation_type TEXT,                          -- "Hotel" / "Hostel" / ...
    price_min          INTEGER,                       -- hotel nightly price band (USD)
    price_max          INTEGER,
    hotel_rating       NUMERIC(2,1),                  -- hotel overall rating ("above X")
    review_rating      INTEGER,                       -- this review's own rating (1-5)
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Vector index for semantic search.
CREATE INDEX IF NOT EXISTS idx_review_emb_hnsw
    ON review_embeddings USING hnsw (embedding vector_cosine_ops);
-- Scope filters: narrow the candidate set fast before/with vector ranking.
CREATE INDEX IF NOT EXISTS idx_review_emb_hotel    ON review_embeddings (hotel_id);
CREATE INDEX IF NOT EXISTS idx_review_emb_location ON review_embeddings (location_id);
CREATE INDEX IF NOT EXISTS idx_review_emb_city     ON review_embeddings (city_id);
-- Common compound filter: hotels in a geo, by price/rating.
CREATE INDEX IF NOT EXISTS idx_review_emb_geo_filter
    ON review_embeddings (location_id, hotel_rating, price_min);

-- Keep denormalized hotel metadata fresh when a hotel row changes
-- (e.g. price/rating updated on Xotelo refresh).
CREATE OR REPLACE FUNCTION sync_review_embedding_meta() RETURNS TRIGGER AS $$
BEGIN
    UPDATE review_embeddings re
       SET location_id        = NEW.location_id,
           city_id            = (SELECT city_id FROM locations WHERE id = NEW.location_id),
           accommodation_type = NEW.accommodation_type,
           price_min          = NEW.price_min,
           price_max          = NEW.price_max,
           hotel_rating       = NEW.rating
     WHERE re.hotel_id = NEW.id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_hotels_sync_emb ON hotels;
CREATE TRIGGER trg_hotels_sync_emb
    AFTER UPDATE OF rating, price_min, price_max, accommodation_type, location_id ON hotels
    FOR EACH ROW EXECUTE FUNCTION sync_review_embedding_meta();

-- --------------------------------------------------------------------------
-- api_call_log  (TripAdvisor budget guardrail — count calls per month)
-- --------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS api_call_log (
    id         BIGSERIAL PRIMARY KEY,
    provider   TEXT NOT NULL,                        -- "tripadvisor"
    endpoint   TEXT NOT NULL,                        -- "location_search" / "reviews"
    ref_id     TEXT,                                 -- city id / hotel id this call was for
    called_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Supports "calls this calendar month" budget checks.
CREATE INDEX IF NOT EXISTS idx_api_call_log_provider_time
    ON api_call_log (provider, called_at);

-- --------------------------------------------------------------------------
-- record this migration
-- --------------------------------------------------------------------------
INSERT INTO schema_migrations (version) VALUES ('0002_api_tables')
ON CONFLICT (version) DO NOTHING;

COMMIT;
