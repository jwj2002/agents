"""Markdown fact parsing — pure stdlib (+ optional PyYAML). Client-side only."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from . import SKIP_DIRS, SKIP_NAMES

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


def discover(sources: dict[str, str]):
    """Yield (namespace, abs_path, raw_text) for each fact file under each source."""
    for ns, d in sources.items():
        base = Path(d).expanduser()
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.md")):
            if p.name in SKIP_NAMES or any(part in SKIP_DIRS for part in p.parts):
                continue
            try:
                yield ns, str(p), p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue


def build_records(sources: dict[str, str]) -> list[dict]:
    """Parse all source files into upsertable records (no embedding yet)."""
    recs: list[dict] = []
    for ns, path, raw in discover(sources):
        meta = parse_markdown(raw, fallback_name=Path(path).stem)
        recs.append(
            {
                "namespace": ns,
                "source_path": path,
                "content_hash": content_hash(raw),
                **meta,
            }
        )
    return recs


def embed_text(rec: dict) -> str:
    """Compose the text that gets embedded for a fact."""
    parts = [rec.get("name") or "", rec.get("summary") or "", rec.get("body") or ""]
    return ". ".join(p for p in parts if p).strip()
