"""Stores and embeddings for AuditionConcierge.

InMemoryStore is the test/fixture store and the reference implementation
of the sync and query rules. PostgresStore implements the same rules
against Postgres + pgvector (see db/migrations/001_production_store.sql)
and requires psycopg; it is not exercised by the unit tests, which must
run without a database or a paid API key.
"""

import hashlib
import math
import os


class StubEmbedding:
    """Deterministic, key-free embedding for tests and local runs.

    NOT a semantic embedding: it hashes word tokens into a fixed-size
    vector so sync/query logic can be exercised without an API key.
    Swap it for a real model by implementing embed(text) -> list[float]
    with the dimension in EMBEDDING_DIMENSION.
    """

    def __init__(self, dimension: int = None):
        self.dimension = dimension or int(os.environ.get("EMBEDDING_DIMENSION", "64"))
        self.calls = 0

    def embed(self, text: str):
        self.calls += 1
        vector = [0.0] * self.dimension
        for token in text.lower().split():
            bucket = int(hashlib.sha256(token.encode()).hexdigest(), 16) % self.dimension
            vector[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


def cosine(a, b) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class InMemoryStore:
    def __init__(self):
        self.roles = {}  # role_id -> role dict (active only)
        self.archived = []  # removed roles, kept for audit, never searched

    def get(self, role_id):
        return self.roles.get(role_id)

    def all_active(self):
        return list(self.roles.values())

    def insert(self, role):
        self.roles[role["role_id"]] = dict(role)

    def update(self, role):
        self.roles[role["role_id"]] = dict(role)

    def remove(self, role_id, reason: str):
        role = self.roles.pop(role_id, None)
        if role is not None:
            archived = dict(role)
            archived["status"] = "archived"
            archived["removal_reason"] = reason
            self.archived.append(archived)
        return role


def build_postgres_query(height_in=None, equity=None, deadline_after=None, limit=10):
    """SQL for structured-filter-then-vector search in Postgres + pgvector.

    Callers bind $1 = query embedding, $2.. = filters. Roles with no
    deadline are treated as open; roles with no parsed height do not
    match a height filter. Returns (sql, param_names) for documentation
    and for PostgresStore.query; see the migration for the schema.
    """
    sql = """
        SELECT * FROM roles
        WHERE status = 'active'
          AND (%(deadline_after)s IS NULL OR deadline IS NULL OR deadline >= %(deadline_after)s)
          AND (%(height_in)s IS NULL OR (height_min_in IS NOT NULL AND height_min_in <= %(height_in)s AND height_max_in >= %(height_in)s))
          AND (%(equity)s IS NULL OR equity_status = %(equity)s)
        ORDER BY embedding <=> %(query_embedding)s
        LIMIT %(limit)s
    """
    return sql, ["query_embedding", "deadline_after", "height_in", "equity", "limit"]


class PostgresStore:
    """Postgres + pgvector store. Requires DATABASE_URL and psycopg."""

    def __init__(self, dsn: str = None):
        self.dsn = dsn or os.environ.get("DATABASE_URL")
        if not self.dsn:
            raise ValueError("DATABASE_URL is not set")
        import psycopg  # type: ignore
        from psycopg.rows import dict_row

        self._psycopg = psycopg
        self.conn = psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row)

    def get(self, role_id):
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM roles WHERE role_id = %s", (role_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def all_active(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT * FROM roles WHERE status = 'active'")
            return [dict(r) for r in cur.fetchall()]

    def insert(self, role):
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO roles (role_id, posting_id, title, role_name, location,
                  audition_date, deadline, height_min_in, height_max_in,
                  performer_presentation, equity_status, source_url, raw_text,
                  clean_text, field_hash, parse_confidence, embedding)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                role["role_id"], role["posting_id"], role["title"], role["role_name"],
                role["location"], role["audition_date"] or None,
                role["deadline"] or None, role["height_min_in"], role["height_max_in"],
                role["performer_presentation"], role["equity_status"],
                role["source_url"], role["raw_text"], role["clean_text"],
                role["field_hash"], role["parse_confidence"], role.get("embedding"),
            ))

    def update(self, role):
        with self.conn.cursor() as cur:
            cur.execute("""
                UPDATE roles SET posting_id=%s, title=%s, role_name=%s, location=%s,
                  audition_date=%s, deadline=%s, height_min_in=%s, height_max_in=%s,
                  performer_presentation=%s, equity_status=%s, source_url=%s,
                  raw_text=%s, clean_text=%s, field_hash=%s, parse_confidence=%s,
                  embedding=%s, last_seen=CURRENT_DATE WHERE role_id=%s
            """, (
                role["posting_id"], role["title"], role["role_name"],
                role["location"], role["audition_date"] or None,
                role["deadline"] or None, role["height_min_in"], role["height_max_in"],
                role["performer_presentation"], role["equity_status"],
                role["source_url"], role["raw_text"], role["clean_text"],
                role["field_hash"], role["parse_confidence"], role.get("embedding"),
                role["role_id"],
            ))

    def remove(self, role_id, reason: str):
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO roles_archive SELECT *, %s FROM roles WHERE role_id = %s",
                (reason, role_id),
            )
            cur.execute("DELETE FROM roles WHERE role_id = %s", (role_id,))
