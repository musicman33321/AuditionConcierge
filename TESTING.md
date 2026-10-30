# Testing the production store slice

This slice is on branch `build/production-store`. It does not touch
`disneyauditionsearch.ipynb`, does not deploy anything, and does not
spend money. Tests use only the standard library, a deterministic
stub embedding, and local fixture files. No live feed, database, or
paid API is needed.

## Run the tests

From the repo root:

```
python3 -m unittest discover -s tests -v
```

Expected result: 16 tests, OK. Coverage:

- Height parsing: feet/inches, plain inches, centimeters, ranges,
  mixed units, missing height.
- Role splitting: one posting, two roles, different heights, with
  Equity and presentation detected per role.
- Sync with fixtures: new role added, changed role updated and
  re-embedded, unchanged role skipped with no re-embed, expired role
  removed, disappeared role removed from active search.
- Query: height overlap (with a 0.5 in tolerance for cm rounding),
  Equity filter, deadline filter, and only filtered records reaching
  the LLM context step.
- End-to-end: fixture feed parsed, synced, and queried, no network.

## Run the sync against a fixture

```
python3 -m app.sync --fixture tests/fixtures/feed_v1.xml --today 2026-10-30
```

Expected output for feed_v1 on 2026-10-30: 4 added, 1 removed as
expired (the 2026-10-01 audition), 3 total active. The sync in this
slice runs against an in-memory store and prints stats; it does not
persist between runs. That is intentional for the fixture path.

## Run against a real Postgres + pgvector database

Still needed before live use (see below). When a database is ready:

1. Create a Postgres database with pgvector, for example Supabase
   or Neon. Set `DATABASE_URL` to its connection string.
2. Apply the migration, changing the embedding dimension first if
   your embedding model is not 1536-dimensional:

```
psql "$DATABASE_URL" -f db/migrations/001_production_store.sql
```

3. Install the Postgres driver and run the sync with a real store.
   The `PostgresStore` class in `app/store.py` implements the same
   upsert/expiry rules as the in-memory store. The live feed URL is
   the one the notebook uses:
   `https://services2.tmpwebeng.com/feed/disney-event-feed-proxy.aspx`
   (see `app/parse.py`, `fetch_disney_auditions`).

## What is still needed from the user

- A Postgres + pgvector connection string (`DATABASE_URL`), hosted
  outside Vercel. No database has been provisioned in this slice.
- An embedding model choice and its dimension. The migration defaults
  to 1536; the test stub uses 64. These must match before real data
  is embedded, or the column dimension must be changed first.
- A daily-run decision: Vercel Cron or GitHub Actions. Both are
  named in the design doc; neither is wired up in this slice.
- A stable-id decision for Disney reposts with a new URL (listed as
  an open question in `docs/data-storage-draft.md`).
