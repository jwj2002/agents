"""FastEmbed wrapper — server-side (jns) only. Imports fastembed lazily."""

from __future__ import annotations

import os

from . import DOC_PREFIX, EMBED_BATCH, EMBED_MAXCHARS, EMBED_MODEL, QUERY_PREFIX

_model = None


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


def embed_docs(texts: list[str], cache_dir: str | None = None) -> list[list[float]]:
    m = _get(cache_dir)
    prepped = [DOC_PREFIX + (t or "")[:EMBED_MAXCHARS] for t in texts]
    return [[float(x) for x in v] for v in m.embed(prepped, batch_size=EMBED_BATCH)]


def embed_query(text: str, cache_dir: str | None = None) -> list[float]:
    m = _get(cache_dir)
    return [float(x) for x in next(iter(m.embed([QUERY_PREFIX + text])))]
