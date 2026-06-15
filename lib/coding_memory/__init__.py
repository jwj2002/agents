"""Shared *personal* coding-memory store (client/server).

Architecture (decided 2026-06-14):
  - Storage: Postgres 16 + pgvector on jns-server, database ``coding_memory``.
  - Embedding is CENTRALIZED on jns (FastEmbed ``nomic-embed-text-v1.5``, 768-d)
    so there is exactly one vector space — no cross-device drift.
  - Personal devices (this laptop + jns) share this store. The laptop is a thin
    client: it parses local markdown and ships records over SSH; jns embeds+stores.
  - STRICT RESIDENCY: work memory lives in a separate, never-bridged store on the
    work laptop. This tool's default sources are personal-only and it never holds
    a work DSN.

Config: ``~/.coding_memory.env`` (KEY=VALUE per line), env vars override.
  jns       -> DATABASE_URL=...127.0.0.1:5432... , FASTEMBED_CACHE=...   (local mode)
  laptop    -> CODING_MEMORY_SSH=jns-server                              (remote mode)
"""

from __future__ import annotations

import os
from pathlib import Path

EMBED_MODEL = "nomic-ai/nomic-embed-text-v1.5"
EMBED_DIM = 768
DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
EMBED_MAXCHARS = 2500  # truncate doc text before embedding (attention is O(seq^2));
#                        FTS still covers the full body, so recall keeps full-text reach
EMBED_BATCH = 8  # small batch caps peak memory (O(seq^2)*batch); avoids OOM on jns

CONFIG_PATH = Path(os.path.expanduser("~/.coding_memory.env"))

# laptop-side markdown source -> namespace. Personal only (strict residency).
DEFAULT_SOURCES = {
    "agents": "~/.claude/projects/-Users-jasonjob-agents/memory",
    "buddy": "~/.claude/projects/-Users-jasonjob-projects-buddy/memory",
}
SKIP_NAMES = {"MEMORY.md"}
SKIP_DIRS = {"archive"}

_CFG_KEYS = (
    "DATABASE_URL",
    "CODING_MEMORY_SSH",
    "FASTEMBED_CACHE",
    "CODING_MEMORY_REMOTE_BIN",
)


def load_config() -> dict:
    cfg: dict[str, str] = {}
    if CONFIG_PATH.exists():
        for line in CONFIG_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            cfg[k.strip()] = v.strip()
    for k in _CFG_KEYS:
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    cfg.setdefault("CODING_MEMORY_REMOTE_BIN", "~/agents/bin/coding-memory")
    return cfg


def is_remote(cfg: dict) -> bool:
    """Remote = dispatch over SSH. Local = talk to the DB + embed here (jns)."""
    return not cfg.get("DATABASE_URL") and bool(cfg.get("CODING_MEMORY_SSH"))
