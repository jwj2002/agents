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
import re
from pathlib import Path

EMBED_MODEL = "nomic-ai/nomic-embed-text-v1.5"
EMBED_DIM = 768
DOC_PREFIX = "search_document: "
QUERY_PREFIX = "search_query: "
EMBED_MAXCHARS = 2500  # truncate doc text before embedding (attention is O(seq^2));
#                        FTS still covers the full body, so recall keeps full-text reach
EMBED_BATCH = 8  # small batch caps peak memory (O(seq^2)*batch); avoids OOM on jns
# Min cosine similarity for a fact to be PUSHED into a phase prompt (--for-prompt).
# Calibrated 2026-06-15: true hits 0.68-0.82; irrelevant-query floor ~0.50; weak
# secondaries ~0.59. 0.62 keeps real hits, gates out the floor + the bloat.
RECALL_MIN_SCORE = 0.62

CONFIG_PATH = Path(os.path.expanduser("~/.coding_memory.env"))

# laptop-side markdown source -> namespace. Personal only (strict residency).
# `global` is git-tracked craft knowledge in the agents repo, shared across machines.
DEFAULT_SOURCES = {
    "agents": "~/.claude/projects/-Users-jasonjob-agents/memory",
    "buddy": "~/.claude/projects/-Users-jasonjob-projects-buddy/memory",
    "global": "~/agents/memory/global",
}
SKIP_NAMES = {"MEMORY.md"}
SKIP_DIRS = {"archive"}

# Shared namespaces are identical on every machine (git-synced), so they get a fixed
# origin + repo-relative source_path -> one row per fact regardless of which machine
# ingests them (no cross-machine duplicates crowding recall). Project namespaces stay
# per-origin (their content differs per machine).
SHARED_NAMESPACES = frozenset({"global"})
SHARED_ORIGIN = "shared"
REPO_ROOT = os.path.realpath(os.path.expanduser("~/agents"))

# Residency allowlist: only these namespaces may be written to the personal store.
# The server (jns) enforces this so a misconfigured client cannot land work data.
# (Includes future namespaces global/craft sourced from the agents git repo.)
ALLOWED_NAMESPACES = frozenset({"agents", "buddy", "global", "craft"})
# Client-side guard: a filesystem --source must be a KNOWN personal namespace AND
# resolve under THAT namespace's canonical root in DEFAULT_SOURCES. The shared
# ~/.claude/projects parent is NOT a boundary (it also holds work-project memory).

_SAFE_REMOTE_BIN = re.compile(r"^[\w/.~ -]+$")


def valid_remote_bin(value: str) -> bool:
    """Remote bin is interpolated raw (the remote shell must expand ~); only allow
    a conservative path-ish charset so config can't smuggle shell metacharacters."""
    return bool(_SAFE_REMOTE_BIN.match(value or ""))


_CFG_KEYS = (
    "DATABASE_URL",
    "CODING_MEMORY_SSH",
    "FASTEMBED_CACHE",
    "CODING_MEMORY_REMOTE_BIN",
    "CODING_MEMORY_EMBED_URL",
    "CODING_MEMORY_ORIGIN",
)


def load_config() -> dict:
    cfg: dict[str, str] = {}
    if CONFIG_PATH.exists():
        mode = CONFIG_PATH.stat().st_mode
        if mode & 0o077:
            import sys

            sys.stderr.write(
                f"warning: {CONFIG_PATH} is group/world-readable; run "
                f"`chmod 600 {CONFIG_PATH}` (it holds the DB password)\n"
            )
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
    # bridge file-configured settings into the process env — the embedder + the
    # origin resolver read these from os.environ (so the CLI uses the warm service
    # and a STABLE per-machine origin, not a volatile hostname).
    for k in ("CODING_MEMORY_EMBED_URL", "FASTEMBED_CACHE", "CODING_MEMORY_ORIGIN"):
        if cfg.get(k) and not os.environ.get(k):
            os.environ[k] = cfg[k]
    return cfg


def is_remote(cfg: dict) -> bool:
    """Remote = dispatch over SSH. Local = talk to the DB + embed here (jns)."""
    return not cfg.get("DATABASE_URL") and bool(cfg.get("CODING_MEMORY_SSH"))
