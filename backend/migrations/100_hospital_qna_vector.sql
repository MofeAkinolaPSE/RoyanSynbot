-- Phase 2 Bootstrap: QnA table (no pgvector required)
-- Embeddings are stored as a native DOUBLE PRECISION[] array.
-- Cosine similarity is computed in Python (see src/local_db.py RPCQuery).
-- Run this on the synbot_health postgres database before seeding the knowledge base.

ROLLBACK; -- clear any prior aborted transaction
BEGIN;

-- QnA table for RAG retrieval (uses plain Postgres float array — no pgvector needed)
CREATE TABLE IF NOT EXISTS public.qna (
  id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  question  text                NOT NULL,
  answer    text                NOT NULL,
  embedding DOUBLE PRECISION[], -- 384-dim embedding stored as native Postgres array
  source    text
);

-- GIN index on the embedding array is not useful for similarity search;
-- we rely on Python-side cosine similarity in local_db.py RPCQuery.
-- A plain B-tree index on id for fast row fetches:
CREATE INDEX IF NOT EXISTS idx_qna_id ON public.qna (id);

COMMIT;
