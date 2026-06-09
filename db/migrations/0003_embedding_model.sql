-- Travel Mitra 2.0 — migration 0003: track the embedding model per row.
--
-- Vectors from different models live in different spaces and must not be
-- compared. Recording the model lets us find/re-embed stale rows on a model
-- change and enforces query/document model consistency at search time.
--
-- Idempotent. Existing rows backfill to the model they were created with.

BEGIN;

ALTER TABLE review_embeddings
    ADD COLUMN IF NOT EXISTS model TEXT NOT NULL DEFAULT 'gemini-embedding-001';

INSERT INTO schema_migrations (version) VALUES ('0003_embedding_model')
ON CONFLICT (version) DO NOTHING;

COMMIT;
