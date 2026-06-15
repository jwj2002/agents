"""Postgres + pgvector access — server-side (jns) only. psycopg imported lazily."""

from __future__ import annotations

import math

from . import EMBED_DIM

_DDL = """
CREATE TABLE IF NOT EXISTS memory_fact (
  id           BIGSERIAL PRIMARY KEY,
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
        # identity is (namespace, source_path); drop the original content_hash unique
        c.execute(
            "ALTER TABLE memory_fact DROP CONSTRAINT IF EXISTS memory_fact_namespace_content_hash_key;"
        )
        c.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_memfact_ns_path ON memory_fact(namespace, source_path);"
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
    conn.commit()


def existing_hashes(conn, namespaces) -> dict:
    with conn.cursor() as c:
        c.execute(
            "SELECT namespace, source_path, content_hash FROM memory_fact WHERE namespace = ANY(%s)",
            (list(namespaces),),
        )
        return {(r[0], r[1]): r[2] for r in c.fetchall()}


def upsert(conn, rec: dict, embedding) -> None:
    params = dict(rec)
    params["emb"] = _vlit(embedding)
    params["expires"] = rec.get("expires") or ""
    sql = """
    INSERT INTO memory_fact
      (namespace,name,type,summary,body,source_path,durability,expires,content_hash,embedding,updated_at)
    VALUES
      (%(namespace)s,%(name)s,%(type)s,%(summary)s,%(body)s,%(source_path)s,%(durability)s,
       NULLIF(%(expires)s,'')::date,%(content_hash)s,%(emb)s::vector,now())
    ON CONFLICT (namespace, source_path) DO UPDATE SET
      name=EXCLUDED.name, type=EXCLUDED.type, summary=EXCLUDED.summary, body=EXCLUDED.body,
      durability=EXCLUDED.durability, expires=EXCLUDED.expires, content_hash=EXCLUDED.content_hash,
      embedding=EXCLUDED.embedding, updated_at=now();
    """
    with conn.cursor() as c:
        c.execute(sql, params)


def delete_missing(conn, namespace: str, keep_paths: list[str]) -> int:
    """Remove rows for a namespace whose source file no longer exists."""
    with conn.cursor() as c:
        c.execute(
            "DELETE FROM memory_fact WHERE namespace=%s AND NOT (source_path = ANY(%s))",
            (namespace, keep_paths),
        )
        return c.rowcount


def stats(conn) -> list[tuple]:
    with conn.cursor() as c:
        c.execute(
            "SELECT namespace, count(*), count(embedding) FROM memory_fact GROUP BY namespace ORDER BY namespace;"
        )
        return c.fetchall()


_COLS = "namespace,name,type,summary,source_path"


def _rows_to_dicts(rows):
    out = []
    for r in rows:
        out.append(
            {
                "namespace": r[0],
                "name": r[1],
                "type": r[2],
                "summary": r[3],
                "source_path": r[4],
                "score": float(r[5]),
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
            key = (r["namespace"], r["source_path"])
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


def drift_rows(conn, namespace, existing_paths):
    """Rows in `namespace` whose source_path is NOT in the caller's existing set.

    Caller must have CLEANLY scanned this namespace (root present, fully readable,
    >=1 file) — otherwise an incomplete scan would mislabel live rows as drift.
    """
    with conn.cursor() as c:
        c.execute(
            "SELECT source_path, name FROM memory_fact "
            "WHERE namespace = %s AND NOT (source_path = ANY(%s)) ORDER BY source_path",
            (namespace, list(existing_paths)),
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
