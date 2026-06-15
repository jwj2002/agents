"""Embedding — server-side (jns) only.

Two layers:
  * ``_embed_local_*`` load the FastEmbed model in-process (the ~5s cold start on
    first use). The warm embed service calls these directly.
  * public ``embed_docs`` / ``embed_query`` try the warm localhost service first
    (when ``CODING_MEMORY_EMBED_URL`` is set) and fall back to the in-process model
    if the service is unreachable — so a coding-memory call never hard-depends on
    the service being up.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from . import DOC_PREFIX, EMBED_BATCH, EMBED_MAXCHARS, EMBED_MODEL, QUERY_PREFIX

_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})

_model = None
_SERVICE_TIMEOUT = 30  # seconds; warm calls return in well under this


def _get(cache_dir: str | None = None):
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        cd = cache_dir or os.environ.get("FASTEMBED_CACHE") or None
        # max_length caps the tokenizer sequence so a stray long doc can't blow up
        # attention memory (O(seq^2)); not all fastembed versions accept the kwarg.
        try:
            _model = TextEmbedding(EMBED_MODEL, cache_dir=cd, max_length=768)
        except TypeError:
            _model = TextEmbedding(EMBED_MODEL, cache_dir=cd)
    return _model


# ---- in-process (model) path: also the warm-service worker + fallback ----


def _embed_local_docs(
    texts: list[str], cache_dir: str | None = None
) -> list[list[float]]:
    m = _get(cache_dir)
    prepped = [DOC_PREFIX + (t or "")[:EMBED_MAXCHARS] for t in texts]
    return [[float(x) for x in v] for v in m.embed(prepped, batch_size=EMBED_BATCH)]


def _embed_local_query(text: str, cache_dir: str | None = None) -> list[float]:
    m = _get(cache_dir)
    return [float(x) for x in next(iter(m.embed([QUERY_PREFIX + text])))]


# ---- warm-service path (opt-in via CODING_MEMORY_EMBED_URL) ----


def _try_service(texts: list[str], kind: str) -> list[list[float]] | None:
    """POST to the warm embed service; return vectors, or None to fall back."""
    base = os.environ.get("CODING_MEMORY_EMBED_URL")
    if not base:
        return None
    # Residency: only ever POST memory text to a loopback service. A misconfigured
    # (or hostile) non-local URL must never receive fact text — fall back to local.
    if urllib.parse.urlparse(base).hostname not in _LOOPBACK:
        return None
    payload = json.dumps({"texts": texts, "kind": kind}).encode()
    req = urllib.request.Request(
        base.rstrip("/") + "/embed",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_SERVICE_TIMEOUT) as resp:
            vecs = json.loads(resp.read()).get("vectors")
        if isinstance(vecs, list) and len(vecs) == len(texts):
            return vecs
        return None
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None  # service down/slow/garbled -> caller falls back to local


def embed_docs(texts: list[str], cache_dir: str | None = None) -> list[list[float]]:
    vecs = _try_service(texts, "doc")
    return vecs if vecs is not None else _embed_local_docs(texts, cache_dir)


def embed_query(text: str, cache_dir: str | None = None) -> list[float]:
    vecs = _try_service([text], "query")
    return vecs[0] if vecs is not None else _embed_local_query(text, cache_dir)
