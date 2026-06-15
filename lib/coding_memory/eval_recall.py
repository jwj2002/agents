"""Recall-quality eval: fixed (query -> expected fact) pairs to score recall.

NOT a CI gate (needs the live store + model). Run `coding-memory eval`. The
queries deliberately share few keywords with their target fact, so this measures
SEMANTIC recall (not literal matching) and catches regressions when the embedding
model or ranking changes. Facts are identified by source-file stem (stable across
name edits).
"""

from __future__ import annotations

from pathlib import Path

EVAL_PAIRS = [
    (
        "safely remove a database table without breaking callers",
        "feedback_spec_grep_every_sql_site",
    ),
    (
        "run code review in the foreground instead of the background",
        "feedback_codex_always_inline",
    ),
    (
        "a test flag that hides downstream failures",
        "feedback_pytest_no_dash_x_for_validation",
    ),
    (
        "settings reject an unknown environment variable",
        "gotcha-pydantic-settings-extra-forbid",
    ),
    (
        "when retiring a system audit the storage layer not just the API",
        "retirement_audit_method",
    ),
    (
        "a background pipeline swallowed an exception silently",
        "feedback_silent_fire_and_forget_pipelines_must_be_audited_at_boundaries",
    ),
    ("where does the shared coding memory store live", "coding_memory_store_jns"),
    ("keep telemetry shards out of the git repository", "telemetry_shards_local_only"),
    (
        "verify the real code before locking a spec",
        "feedback_spec_code_reality_manifest_first",
    ),
]
MODES = ("hybrid", "vector", "fts")
KS = (1, 3, 5)


def score(search_fn) -> dict:
    """search_fn(query, mode, k) -> list of dicts with 'source_path'.
    Returns {mode: {k: hit_count}, 'n': len}."""
    out: dict = {m: dict.fromkeys(KS, 0) for m in MODES}
    for query, expected in EVAL_PAIRS:
        for m in MODES:
            stems = [Path(r["source_path"]).stem for r in search_fn(query, m, max(KS))]
            for k in KS:
                if expected in stems[:k]:
                    out[m][k] += 1
    out["n"] = len(EVAL_PAIRS)
    return out
