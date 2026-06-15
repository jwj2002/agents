"""Markdown fact parsing — pure stdlib (+ optional PyYAML). Client-side only."""

from __future__ import annotations

import hashlib
import os
import re
import socket
from pathlib import Path

from . import REPO_ROOT, SHARED_NAMESPACES, SHARED_ORIGIN, SKIP_DIRS, SKIP_NAMES


def current_origin() -> str:
    """Stable per-machine identity for the shared store. Prefer the explicit config
    value (CODING_MEMORY_ORIGIN, bridged into the env by load_config); fall back to
    the SHORT hostname. NOT the raw FQDN — macOS appends volatile DHCP/domain
    suffixes that would split one machine's facts across multiple origins.
    Resolved lazily (not at import) so it sees the bridged config value."""
    return os.environ.get("CODING_MEMORY_ORIGIN") or socket.gethostname().split(".")[0]


try:
    import yaml
except ImportError:  # pragma: no cover - yaml expected but degrade gracefully
    yaml = None

_FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def content_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _fallback_frontmatter(text: str) -> dict:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line and not line.startswith((" ", "\t", "-")):
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip().strip("'\"")
    return out


def parse_markdown(raw: str, fallback_name: str = "") -> dict:
    """Extract name/type/summary/durability/expires/body from a fact file."""
    meta: dict = {}
    body = raw
    m = _FM.match(raw)
    if m:
        fm_text, body = m.group(1), raw[m.end() :]
        if yaml is not None:
            try:
                meta = yaml.safe_load(fm_text) or {}
            except yaml.YAMLError:
                meta = {}
        if not isinstance(meta, dict) or not meta:
            meta = _fallback_frontmatter(fm_text)

    nested = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}

    def pick(*keys):
        for k in keys:
            for src in (meta, nested):
                val = src.get(k)
                if val not in (None, ""):
                    return val
        return None

    def s(v):
        return None if v is None else str(v)

    return {
        "name": str(pick("name") or fallback_name),
        "type": s(pick("type")),
        "summary": s(pick("summary", "description")),
        "durability": s(pick("durability")),
        "expires": s(pick("expires")),
        "body": body.strip(),
    }


def _record(ns: str, path: str, raw: str) -> dict:
    meta = parse_markdown(raw, fallback_name=Path(path).stem)
    if ns in SHARED_NAMESPACES:
        # git-synced: fixed origin + repo-relative path -> identical on every machine
        origin = SHARED_ORIGIN
        try:
            source_path = os.path.relpath(os.path.realpath(path), REPO_ROOT)
        except ValueError:
            source_path = path
    else:
        origin, source_path = current_origin(), path
    return {
        "origin": origin,
        "namespace": ns,
        "source_path": source_path,
        "content_hash": content_hash(raw),
        **meta,
    }


def build_records(sources: dict[str, str]) -> dict:
    """Parse all source files into upsertable records.

    Returns ``{"records": [...], "prune_namespaces": [...]}``. A namespace is
    prune-safe ONLY if its source root exists, every file read cleanly, and it has
    >=1 record — so a missing / partially-readable / empty source can never trigger
    a destructive prune of previously-ingested rows.
    """
    records: list[dict] = []
    prune_ok: list[str] = []
    for ns, d in sources.items():
        base = Path(d).expanduser()
        if not base.is_dir():
            continue  # missing root -> contribute nothing, never prune this ns
        files = [
            p
            for p in sorted(base.rglob("*.md"))
            if p.name not in SKIP_NAMES
            and not any(part in SKIP_DIRS for part in p.parts)
        ]
        ns_records: list[dict] = []
        errors = 0
        for p in files:
            try:
                raw = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                errors += 1
                continue
            ns_records.append(_record(ns, str(p), raw))
        records.extend(ns_records)
        if ns_records and errors == 0:
            prune_ok.append(ns)
    return {"records": records, "prune_namespaces": prune_ok}


def embed_text(rec: dict) -> str:
    """Compose the text that gets embedded for a fact."""
    parts = [rec.get("name") or "", rec.get("summary") or "", rec.get("body") or ""]
    return ". ".join(p for p in parts if p).strip()
