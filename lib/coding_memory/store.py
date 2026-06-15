"""Postgres + pgvector access — server-side (jns) only. psycopg imported lazily."""

from __future__ import annotations

import json
import math

from . import EMBED_DIM

_DDL = """
CREATE TABLE IF NOT EXISTS memory_fact (
  id           BIGSERIAL PRIMARY KEY,
  origin       TEXT,
  namespace    TEXT NOT NULL,
  name         TEXT,
  type         TEXT,
  summary      TEXT,
  body         TEXT NOT NULL,
  source_path  TEXT,
  tags         TEXT[] NOT NULL DEFAULT '{}',
  durability   TEXT,
  expires      DATE,
  content_hash TEXT NOT NULL,
  embedding    vector(768),
  tsv tsvector GENERATED ALWAYS AS
       (to_tsvector('english', coalesce(name,'')||' '||coalesce(summary,'')||' '||coalesce(body,''))) STORED,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);
"""

_RECALL_DDL = """
CREATE TABLE IF NOT EXISTS recall_event (
  id           BIGSERIAL PRIMARY KEY,
  ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
  origin       TEXT,
  kind         TEXT NOT NULL CHECK (kind IN ('push', 'pull')),
  mode         TEXT,
  n_returned   INT,
  n_injected   INT,
  top_score    REAL,
  facts        JSONB,
  latency_ms   INT
);
"""


def connect(dsn: str):
    import psycopg

    return psycopg.connect(dsn)


def _vlit(vec) -> str:
    vals = [float(x) for x in vec]
    if len(vals) != EMBED_DIM:
        raise ValueError(f"embedding dim {len(vals)} != {EMBED_DIM}")
    if any(not math.isfinite(x) for x in vals):
        raise ValueError("embedding contains non-finite values")
    return "[" + ",".join(f"{x:.7g}" for x in vals) + "]"


def ensure_schema(conn) -> None:
    with conn.cursor() as c:
        c.execute(_DDL)
        # migrate to per-origin identity (origin, namespace, source_path) so multiple
        # machines can share one store without clobbering each other's rows.
        c.execute("ALTER TABLE memory_fact ADD COLUMN IF NOT EXISTS origin TEXT;")
        c.execute(
            "ALTER TABLE memory_fact DROP CONSTRAINT IF EXISTS memory_fact_namespace_content_hash_key;"
        )
        c.execute("DROP INDEX IF EXISTS ux_memfact_ns_path;")
        c.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_memfact_origin_ns_path "
            "ON memory_fact(origin, namespace, source_path);"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_memfact_ns ON memory_fact(namespace);"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_memfact_tsv ON memory_fact USING gin(tsv);"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_memfact_embed ON memory_fact USING hnsw (embedding vector_cosine_ops);"
        )
        # recall telemetry table (#455)
        c.execute(_RECALL_DDL)
        c.execute("CREATE INDEX IF NOT EXISTS idx_recall_event_ts ON recall_event(ts);")
    conn.commit()


def claim_unowned(conn, origin: str, namespaces) -> int:
    """One-time migration: assign legacy rows (origin IS NULL) in the ingested
    namespaces to the ingesting machine, so they participate in per-origin identity."""
    with conn.cursor() as c:
        # First drop any legacy NULL row that already has a claimed counterpart for
        # this origin — otherwise the UPDATE would violate (origin,namespace,source_path).
        c.execute(
            "DELETE FROM memory_fact m WHERE m.origin IS NULL AND m.namespace = ANY(%s) "
            "AND EXISTS (SELECT 1 FROM memory_fact o "
            "WHERE o.origin=%s AND o.namespace=m.namespace AND o.source_path=m.source_path)",
            (list(namespaces), origin),
        )
        c.execute(
            "UPDATE memory_fact SET origin=%s WHERE origin IS NULL AND namespace = ANY(%s)",
            (origin, list(namespaces)),
        )
        return c.rowcount


def existing_hashes(conn, origin: str, namespaces) -> dict:
    with conn.cursor() as c:
        c.execute(
            "SELECT namespace, source_path, content_hash FROM memory_fact "
            "WHERE origin=%s AND namespace = ANY(%s)",
            (origin, list(namespaces)),
        )
        return {(r[0], r[1]): r[2] for r in c.fetchall()}


def upsert(conn, rec: dict, embedding, origin: str) -> None:
    params = dict(rec)
    params["origin"] = origin
    params["emb"] = _vlit(embedding)
    params["expires"] = rec.get("expires") or ""
    sql = """
    INSERT INTO memory_fact
      (origin,namespace,name,type,summary,body,source_path,durability,expires,content_hash,embedding,updated_at)
    VALUES
      (%(origin)s,%(namespace)s,%(name)s,%(type)s,%(summary)s,%(body)s,%(source_path)s,%(durability)s,
       NULLIF(%(expires)s,'')::date,%(content_hash)s,%(emb)s::vector,now())
    ON CONFLICT (origin, namespace, source_path) DO UPDATE SET
      name=EXCLUDED.name, type=EXCLUDED.type, summary=EXCLUDED.summary, body=EXCLUDED.body,
      durability=EXCLUDED.durability, expires=EXCLUDED.expires, content_hash=EXCLUDED.content_hash,
      embedding=EXCLUDED.embedding, updated_at=now();
    """
    with conn.cursor() as c:
        c.execute(sql, params)


def delete_missing(conn, origin: str, namespace: str, keep_paths: list[str]) -> int:
    """Remove THIS machine's rows for a namespace whose source file no longer exists.
    Scoped to origin so one machine never prunes another machine's rows."""
    with conn.cursor() as c:
        c.execute(
            "DELETE FROM memory_fact "
            "WHERE origin=%s AND namespace=%s AND NOT (source_path = ANY(%s))",
            (origin, namespace, keep_paths),
        )
        return c.rowcount


def stats(conn) -> list[tuple]:
    with conn.cursor() as c:
        c.execute(
            "SELECT namespace, count(*), count(embedding) FROM memory_fact GROUP BY namespace ORDER BY namespace;"
        )
        return c.fetchall()


_COLS = "origin,namespace,name,type,summary,source_path"


def _rows_to_dicts(rows):
    out = []
    for r in rows:
        out.append(
            {
                "origin": r[0],
                "namespace": r[1],
                "name": r[2],
                "type": r[3],
                "summary": r[4],
                "source_path": r[5],
                "score": float(r[6]),
            }
        )
    return out


def _vector(conn, qvec, k, namespaces):
    p = {"q": _vlit(qvec), "k": k}
    where = ""
    if namespaces:
        where = "WHERE namespace = ANY(%(ns)s)"
        p["ns"] = list(namespaces)
    sql = f"""SELECT {_COLS}, 1-(embedding <=> %(q)s::vector) AS score
              FROM memory_fact {where}
              ORDER BY embedding <=> %(q)s::vector LIMIT %(k)s;"""
    with conn.cursor() as c:
        c.execute(sql, p)
        return _rows_to_dicts(c.fetchall())


def _fts(conn, text, k, namespaces):
    if not text:
        return []
    p = {"text": text, "k": k}
    where = "WHERE tsv @@ plainto_tsquery('english', %(text)s)"
    if namespaces:
        where += " AND namespace = ANY(%(ns)s)"
        p["ns"] = list(namespaces)
    sql = f"""SELECT {_COLS}, ts_rank(tsv, plainto_tsquery('english', %(text)s)) AS score
              FROM memory_fact {where}
              ORDER BY score DESC LIMIT %(k)s;"""
    with conn.cursor() as c:
        c.execute(sql, p)
        return _rows_to_dicts(c.fetchall())


def search(conn, qvec, text=None, k=8, namespaces=None, mode="hybrid"):
    if mode == "vector":
        return _vector(conn, qvec, k, namespaces)
    if mode == "fts":
        return _fts(conn, text, k, namespaces)
    # hybrid: Reciprocal Rank Fusion (k0=60) over vector + FTS
    over = max(k * 3, 15)
    fused: dict = {}
    for rows in (
        _vector(conn, qvec, over, namespaces),
        _fts(conn, text, over, namespaces),
    ):
        for rank, r in enumerate(rows):
            key = (r["origin"], r["namespace"], r["source_path"])  # per-origin distinct
            slot = fused.setdefault(key, {"rec": r, "rrf": 0.0})
            slot["rrf"] += 1.0 / (60 + rank)
    merged = sorted(fused.values(), key=lambda s: s["rrf"], reverse=True)[:k]
    out = []
    for s in merged:
        rec = dict(s["rec"])
        rec["score"] = round(s["rrf"], 5)
        out.append(rec)
    return out


# ---- doctor: freshness / expiry / drift / duplicates ----


def expired_rows(conn, namespaces=None):
    q = (
        "SELECT namespace, name, source_path, expires FROM memory_fact "
        "WHERE expires IS NOT NULL AND expires < CURRENT_DATE"
    )
    params: tuple = ()
    if namespaces:
        q += " AND namespace = ANY(%s)"
        params = (list(namespaces),)
    q += " ORDER BY namespace, expires"
    with conn.cursor() as c:
        c.execute(q, params)
        return [
            {"namespace": r[0], "name": r[1], "source_path": r[2], "expires": str(r[3])}
            for r in c.fetchall()
        ]


def duplicate_names(conn):
    q = (
        "SELECT namespace, name, count(*), array_agg(source_path) "
        "FROM memory_fact GROUP BY namespace, name HAVING count(*) > 1 "
        "ORDER BY namespace, name"
    )
    with conn.cursor() as c:
        c.execute(q)
        return [
            {"namespace": r[0], "name": r[1], "count": r[2], "paths": r[3]}
            for r in c.fetchall()
        ]


def drift_rows(conn, origin, namespace, existing_paths):
    """THIS machine's rows in `namespace` whose source_path is NOT in the caller's
    existing set. Scoped to origin (one machine's scan can't mislabel another's
    rows). Caller must have CLEANLY scanned this namespace (root present, fully
    readable, >=1 file), else an incomplete scan would mislabel live rows as drift.
    """
    with conn.cursor() as c:
        c.execute(
            "SELECT source_path, name FROM memory_fact "
            "WHERE origin=%s AND namespace=%s AND NOT (source_path = ANY(%s)) "
            "ORDER BY source_path",
            (origin, namespace, list(existing_paths)),
        )
        return [{"source_path": r[0], "name": r[1]} for r in c.fetchall()]


def prune_expired(conn, namespaces=None) -> int:
    q = "DELETE FROM memory_fact WHERE expires IS NOT NULL AND expires < CURRENT_DATE"
    params: tuple = ()
    if namespaces:
        q += " AND namespace = ANY(%s)"
        params = (list(namespaces),)
    with conn.cursor() as c:
        c.execute(q, params)
        return c.rowcount


# ---- recall telemetry (#455) ----


def log_recall(
    dsn: str,
    *,
    origin: str,
    kind: str,
    mode: str,
    n_returned: int,
    n_injected: int,
    top_score: float | None,
    facts: list[dict],
    latency_ms: int,
) -> None:
    """INSERT one recall_event row via an isolated autocommit connection.

    Opens its own autocommit connection so a logging INSERT failure can never
    abort the caller's query transaction. Truncates facts to the top 5 before
    storage (privacy/lean). Callers wrap in a narrow try/except for fail-open.
    """
    import psycopg  # noqa: PLC0415 — lazy; callers may not have psycopg

    top5 = facts[:5]
    sql = """
    INSERT INTO recall_event
      (origin, kind, mode, n_returned, n_injected, top_score, facts, latency_ms)
    VALUES
      (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
    """
    with psycopg.connect(dsn, autocommit=True) as c:
        with c.cursor() as cur:
            cur.execute(
                sql,
                (
                    origin,
                    kind,
                    mode,
                    n_returned,
                    n_injected,
                    top_score,
                    json.dumps(top5),
                    latency_ms,
                ),
            )


def recall_report_agg(conn, *, days: int = 7) -> dict:
    """Aggregate recall_event rows for the last `days` days.

    Returns a dict with keys: n_total, n_push, n_pull, n_injected_total,
    n_returned_total, p50_latency_ms (int|None), top_facts ([{ns,name,count}]
    top 5), days.
    """
    days = max(1, min(int(days), 365))  # clamp to sane range before binding
    agg_sql = """
    SELECT
        count(*)                                         AS n_total,
        count(*) FILTER (WHERE kind='push')              AS n_push,
        count(*) FILTER (WHERE kind='pull')              AS n_pull,
        coalesce(sum(n_injected), 0)                     AS n_injected_total,
        coalesce(sum(n_returned), 0)                     AS n_returned_total,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50_latency_ms
    FROM recall_event
    WHERE ts >= now() - make_interval(days => %(days)s)
    """
    facts_sql = """
    SELECT
        f->>'ns'   AS ns,
        f->>'name' AS name,
        count(*)   AS cnt
    FROM recall_event,
         jsonb_array_elements(facts) AS f
    WHERE ts >= now() - make_interval(days => %(days)s)
    GROUP BY f->>'ns', f->>'name'
    ORDER BY cnt DESC
    LIMIT 5
    """
    with conn.cursor() as c:
        c.execute(agg_sql, {"days": days})
        row = c.fetchone()
        n_total = int(row[0]) if row else 0
        n_push = int(row[1]) if row else 0
        n_pull = int(row[2]) if row else 0
        n_injected_total = int(row[3]) if row else 0
        n_returned_total = int(row[4]) if row else 0
        p50_raw = row[5] if row else None
        p50_latency_ms = int(p50_raw) if p50_raw is not None else None

        c.execute(facts_sql, {"days": days})
        top_facts = [
            {"ns": r[0], "name": r[1], "count": int(r[2])} for r in c.fetchall()
        ]

    return {
        "n_total": n_total,
        "n_push": n_push,
        "n_pull": n_pull,
        "n_injected_total": n_injected_total,
        "n_returned_total": n_returned_total,
        "p50_latency_ms": p50_latency_ms,
        "top_facts": top_facts,
        "days": days,
    }
