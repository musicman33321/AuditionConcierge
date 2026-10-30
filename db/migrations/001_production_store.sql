-- 001_production_store.sql
-- AuditionConcierge production store: Postgres + pgvector.
-- Apply with: psql "$DATABASE_URL" -f db/migrations/001_production_store.sql
-- Embedding dimension: 1536 is the default for common embedding models.
-- If you use a different model (or the test stub, dimension 64), change
-- the vector dimension below BEFORE first use; pgvector dimensions are
-- fixed per column. Heights are stored in inches only (see
-- docs/data-storage-draft.md); centimeters are a display conversion.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS postings (
    posting_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    park_location TEXT,
    city TEXT,
    state TEXT,
    venue TEXT,
    talent_type TEXT,
    audition_date DATE,
    audition_time TEXT,
    timezone TEXT,
    source_url TEXT,
    raw_text TEXT NOT NULL,
    first_seen DATE NOT NULL DEFAULT CURRENT_DATE,
    last_seen DATE NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE IF NOT EXISTS roles (
    role_id TEXT PRIMARY KEY,
    posting_id TEXT NOT NULL REFERENCES postings (posting_id),
    title TEXT NOT NULL,
    role_name TEXT NOT NULL,
    location TEXT,
    audition_date DATE,
    deadline DATE,
    height_min_in DOUBLE PRECISION,
    height_max_in DOUBLE PRECISION,
    performer_presentation TEXT,
    equity_status TEXT,
    source_url TEXT,
    raw_text TEXT NOT NULL,
    clean_text TEXT NOT NULL,
    field_hash TEXT NOT NULL,
    parse_confidence TEXT NOT NULL DEFAULT 'low',
    embedding vector(1536),
    status TEXT NOT NULL DEFAULT 'active',
    first_seen DATE NOT NULL DEFAULT CURRENT_DATE,
    last_seen DATE NOT NULL DEFAULT CURRENT_DATE
);

-- Same shape as roles, for roles removed from active search.
CREATE TABLE IF NOT EXISTS roles_archive (
    LIKE roles INCLUDING ALL,
    removal_reason TEXT,
    removed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS roles_active_deadline_idx
    ON roles (deadline) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS roles_height_idx
    ON roles (height_min_in, height_max_in) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS roles_equity_idx
    ON roles (equity_status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS roles_embedding_idx
    ON roles USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Structured-filter-then-vector search (mirrors app/query.py):
--   SELECT * FROM roles
--   WHERE status = 'active'
--     AND (deadline IS NULL OR deadline >= $deadline_after)
--     AND ($height_in IS NULL OR (height_min_in <= $height_in AND height_max_in >= $height_in))
--     AND ($equity IS NULL OR equity_status = $equity)
--   ORDER BY embedding <=> $query_embedding
--   LIMIT $limit;
