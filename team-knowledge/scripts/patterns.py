"""Pattern taxonomy, confidence, and schema logic for the Team Knowledge Hub (§1.3, §1.5).

Pure-logic module. Backs issue #239. Two principles are load-bearing (Codex F6 + laptop-wsl):
  1. Confidence is COMPUTED, never authored — and OCCURRENCE confidence (how often seen) is kept
     separate from EFFICACY confidence (does telemetry show it helps; null until powered).
  2. Bootstrap seeds the TAXONOMY only — `observation_count` starts at 0 per dev; the seed corpus's
     `validated`/`validated_count` is NEVER mapped to observations (the fake-consensus guard, §7).
"""
from __future__ import annotations

import math
import re
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

UNMAPPED = "UNMAPPED"  # sentinel: "no pattern_key fits" — never force-bucket to the closest match

DEFAULT_N_CAP = 50
DEFAULT_CONSENSUS_FLOOR = 0.4
_DECLARED_PENALTY = 0.5      # declared-only confidence is halved vs the same observed count
_CORROBORATION_BONUS = 0.2   # only for GENUINELY independent telemetry agreement

REQUIRED_PATTERN_FIELDS = ("id", "dev", "area", "pattern_key", "practice", "source")
_COMPUTED_FIELDS = ("occurrence_confidence", "efficacy_confidence")
_VALID_SOURCES = {"observed", "declared", "observed+declared"}


# --- confidence (§1.3, Codex F6) ------------------------------------------------------------
def compute_occurrence_confidence(
    observation_count: int,
    *,
    source: str = "observed",
    independent_corroboration: bool = False,
    n_cap: int = DEFAULT_N_CAP,
) -> float:
    """A simple, inspectable capped-log of how OFTEN a practice was observed. Never a learned score.

    base = log2(1+obs) / log2(1+n_cap); declared-only is penalized; independent telemetry adds a
    fixed bonus. Clamped to [0, 1]. `observation_count=0 -> 0.0`; `=n_cap -> 1.0`.
    """
    if observation_count <= 0:
        base = 0.0
    else:
        base = math.log2(1 + observation_count) / math.log2(1 + max(1, n_cap))
        base = min(1.0, base)
    conf = base
    if "observed" not in (source or ""):
        conf *= _DECLARED_PENALTY  # declared-only: weaker than the same observed count
    if independent_corroboration:
        conf = min(1.0, conf + _CORROBORATION_BONUS)
    return round(conf, 4)


def compute_efficacy_confidence(*_args, **_kwargs):
    """Efficacy is NOT auto-computed — it stays None until powered outcome evidence exists
    (§1.3, §1.6 step 6). This function exists to make that explicit and is intentionally inert."""
    return None


# --- gating (§1.3) --------------------------------------------------------------------------
def is_consensus_eligible(occurrence_confidence: float, source: str, floor: float = DEFAULT_CONSENSUS_FLOOR) -> bool:
    """CONSENSUS requires occurrence_confidence >= floor AND `source` includes 'observed'.
    The two conditions are checked SEPARATELY so a purely-declared pattern that clears the floor
    (e.g. via bonus) is still excluded (the purely-declared quorum guard)."""
    return occurrence_confidence >= floor and "observed" in (source or "")


def consensus_candidates(patterns: list, floor: float = DEFAULT_CONSENSUS_FLOOR) -> list:
    return [p for p in patterns
            if is_consensus_eligible(p.get("occurrence_confidence", 0.0), p.get("source", ""), floor)]


def conflict_gap_candidates(patterns: list) -> list:
    """CONFLICT/GAP analysis keeps EVERY pattern, including low-confidence ones — a low-confidence
    *contradictory* signal may be the only evidence a consensus is unsafe, so it stays visible
    (§1.3, Codex F6: don't let the floor mute contradiction)."""
    return list(patterns)


# --- pattern_key resolution / UNMAPPED ------------------------------------------------------
def resolve_pattern_key(candidate_key: str, taxonomy_keys) -> str:
    """Return the candidate key if it is in the controlled taxonomy, else UNMAPPED.
    NEVER returns a 'closest match' — an unmapped observation is surfaced as a taxonomy gap."""
    if candidate_key and candidate_key in set(taxonomy_keys):
        return candidate_key
    return UNMAPPED


def is_taxonomy_gap(pattern_key: str) -> bool:
    return pattern_key == UNMAPPED


# --- schema validation (§1.3) ---------------------------------------------------------------
def validate_authored_pattern(pattern: dict, taxonomy: dict | None = None) -> list:
    """Validate a pattern as AUTHORED by a dev (not yet system-computed). Returns errors; empty=valid.

    Rejects any authored `occurrence_confidence`/`efficacy_confidence` — those are COMPUTED by the
    system, never hand-written (authoring one would bypass the gate). Checks required fields,
    a valid `source`, and (if a taxonomy is given) that area + pattern_key are controlled.
    """
    errors: list = []
    if not isinstance(pattern, dict):
        return ["pattern is not a mapping"]
    for f in _COMPUTED_FIELDS:
        if f in pattern:
            errors.append(f"{f!r} is COMPUTED — must not be authored")
    for f in REQUIRED_PATTERN_FIELDS:
        if not pattern.get(f):
            errors.append(f"missing required field {f!r}")
    src = pattern.get("source")
    if src and src not in _VALID_SOURCES:
        errors.append(f"invalid source {src!r} (expected one of {sorted(_VALID_SOURCES)})")
    if taxonomy:
        areas = taxonomy.get("areas", {})
        area = pattern.get("area")
        key = pattern.get("pattern_key")
        if area and area not in areas:
            errors.append(f"area {area!r} not in controlled taxonomy")
        elif area and key and key != UNMAPPED and key not in set(areas.get(area, [])):
            errors.append(f"pattern_key {key!r} not in taxonomy for area {area!r} (use {UNMAPPED} if none fits)")
    return errors


# --- bootstrap (§1.5) -----------------------------------------------------------------------
def _key_from_pattern_file(data: dict) -> str:
    """Derive a canonical pattern_key from a knowledge/patterns/ file (vocabulary only)."""
    raw = data.get("name") or data.get("legacy_id") or data.get("id") or ""
    key = re.sub(r"[^A-Za-z0-9]+", "_", str(raw)).strip("_").upper()
    return key or UNMAPPED


def bootstrap_vocabulary(patterns_dir) -> dict:
    """Extract area -> [pattern_key] VOCABULARY from knowledge/patterns/*.yaml.

    VOCABULARY ONLY. `observation_count` is NOT set here (it starts at 0 per dev elsewhere), and the
    seed corpus's `status: validated` / `validated_count` / `consecutive_successes` are IGNORED —
    mapping them to observations would manufacture consensus from the seed (laptop-wsl, §7).
    """
    if yaml is None:
        raise RuntimeError("PyYAML required to bootstrap vocabulary")
    vocab: dict = {}
    for path in sorted(Path(patterns_dir).glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        area = data.get("category")
        if not area:
            continue
        key = _key_from_pattern_file(data)
        vocab.setdefault(area, [])
        if key not in vocab[area]:
            vocab[area].append(key)
    return vocab


def seed_observation_counts(vocab: dict, devs: list) -> dict:
    """Return {(dev, area, pattern_key): 0} for every bootstrapped key — the zero-start guarantee.
    observation_count accrues only on REAL observation of a dev using a key, never from the seed."""
    return {
        (dev, area, key): 0
        for area, keys in vocab.items()
        for key in keys
        for dev in devs
    }
