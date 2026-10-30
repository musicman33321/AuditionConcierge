# AuditionConcierge data storage draft

Status: draft, not implemented. See the linked tracking issue for build work.

## Goal

Move AuditionConcierge from a notebook that dumps the whole Disney audition feed on every query to a production store where the query agent only sees matching, unexpired auditions.

## Core decision: one canonical unit, display in two

Store heights in inches only. That is the single source of truth.

Convert to centimeters at display time, based on the viewer's locale: centimeters = inches x 2.54.

Do not store both inches and centimeters as editable fields. Two editable copies can drift apart.

Examples:
- "5'4"" becomes 64 inches
- "64 in" becomes 64 inches
- "162 cm" becomes 63.8 inches

## Two layers: raw posting and structured roles

Not every audition is fully structured, so keep both layers.

1. Raw posting text, always kept. Nothing is lost when parsing fails.
2. Structured fields, all nullable, with a confidence flag when a field had to be guessed.

Split a posting into roles. One Disney posting often lists several character roles with different heights. Storing it as one record would let a height filter match the wrong role. One posting can therefore have many role records, each with its own height range, performer presentation, and Equity status, all pointing back to the same posting.

## Record shape

```json
{
  "posting_id": "disney-2026-10-30-1234",
  "role_id": "disney-2026-10-30-1234-role-1",
  "title": "Character Performer",
  "role_name": "Mickey Mouse",
  "location": "Orlando, FL",
  "audition_date": "2026-11-12",
  "deadline": "2026-11-10",
  "height_min_in": 60,
  "height_max_in": 66,
  "performer_presentation": "any",
  "equity_status": "non-equity",
  "source_url": "https://...",
  "raw_text": "original posting text",
  "clean_text": "parsed role text for embedding",
  "field_hash": "abc123",
  "parse_confidence": "high",
  "embedding": [0.012, -0.034],
  "first_seen": "2026-10-30",
  "last_seen": "2026-10-30",
  "status": "active"
}
```

Field notes:
- `height_min_in` and `height_max_in` are in inches, nullable when a posting gives no height.
- `field_hash` is a hash of the normalized structured fields. It is how the sync decides whether a record changed.
- `parse_confidence` is high, medium, or low. Low confidence records still keep their raw text.
- `status` is active, expired, or archived.

## Daily sync

1. Run the existing fetch step once a day, reusing the notebook's cleaning and height normalization, moved into a sync script.
2. Parse each posting into role records.
3. Upsert by stable role id:
   - New role: add it and embed it.
   - Changed fields, shown by a new field hash: update it and re-embed it.
   - Unchanged: skip it. This is where the token saving comes from.
4. Delete roles from the active index after their deadline passes. Moving them to an archive table is optional. Expired roles must not appear in search.
5. Query path: filter structured fields first (deadline in the future, height overlap, Equity when asked), then vector search only within that filtered set, then send only those records to the language model.

## Store choice: Postgres plus pgvector

Recommended store: Postgres with pgvector.

Why: this app needs structured filtering and vectors in the same query, for a small corpus. Auditions are hundreds or low thousands, not millions. Postgres plus pgvector gives one database, one backup, transactions, and a query like "deadline in the future, height overlaps 64 inches, Equity only, then nearest vectors" in one place.

Alternatives considered:
- Qdrant: a good dedicated vector database, with strong payload filtering and a managed cloud option. A sensible migration pick if the corpus grows a lot. For now it adds a second service, second auth, and second backup.
- Weaviate: similar to Qdrant, but heavier to run, with more schema and graph machinery than this needs.
- FAISS: not a database. It is a fast in-process index library. You would have to build persistence, concurrent updates, metadata filtering, and backup yourself around it. Good for a local prototype, not for a production app with daily updates.
- Chroma: fine for a quick local prototype, and easy to start with. It is another separate database to run, and it does not give the same strong structured filtering and transactions as Postgres. It also splits the structured data and the vectors across two stores unless you add a second database for the structured fields.

Migration path: keep the embedding and the metadata together in the record shape above, so moving from pgvector to Qdrant later is a re-index, not a redesign.

## Hosting target

Target hosting is Vercel for the app itself. Vercel is stateless, so the Postgres plus pgvector database lives outside Vercel, for example Supabase or Neon, and the app connects to it over a connection string. The daily sync can run as a Vercel Cron job or a GitHub Actions scheduled job, whichever is easier to observe.

## Open questions

- Where does the daily sync run: GitHub Actions, a small server, or a hosted job?
- Which embedding model, and what vector dimension?
- Archive expired roles, or hard delete them?
- What counts as a stable id when Disney reposts the same audition with a new URL?
