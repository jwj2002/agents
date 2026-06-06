"""Auto-observe — derive each dev's practices from telemetry and write patterns/<area>/<dev>.yaml.

team-knowledge-mvp-v1 §1.1 (bottom-up discovery) / §1.2 (AUTO-OBSERVE primary) / §1.3 (Pattern schema).
Practices are DISCOVERED from telemetry + git history + decision fields (guards_fired / codex_overturned),
NOT declared by the dev. Each observed behavior is mapped onto a controlled `pattern_key` via the
taxonomy (#223/#239); a behavior that fits NO key is written `pattern_key: UNMAPPED` (a taxonomy-gap
signal for map_patterns #244 — NEVER force-bucketed to the closest match).

Invariants (the spec's teeth):
- `occurrence_confidence` is COMPUTED by `patterns.compute_occurrence_confidence` — never authored;
  an authored literal in the input does not propagate.
- `efficacy_confidence` stays None until powered outcome evidence exists — no telemetry populates it.
- `source: observed` for auto-derived entries; `observed+declared` when a declared entry also exists;
  a declared practice contradicted by observation is surfaced as a flagged DELTA, never suppressed.
- DEV ISOLATION: a dev's agent observes only ITS OWN behavior and writes only its own
  patterns/<area>/<dev>.yaml — it never touches another dev's path.
- INCREMENTAL: re-running with new telemetry increments `observation_count` and recomputes confidence
  on the SAME entry (keyed by id) — it does not create duplicates.

Owner lane: all (§9.3 — each agent runs this on its own machine; the implementation is shared).
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

sys.path.insert(0, str(Path(__file__).resolve().parent))
import patterns as P  # noqa: E402

SCHEMA_VERSION = 1


def _require_yaml():
    if yaml is None:
        raise RuntimeError("PyYAML required for auto-observe")


def _area_keys(taxonomy: dict, area: str) -> list:
    return list((taxonomy.get("areas") or {}).get(area, []))


def _n_cap(taxonomy: dict) -> int:
    return int((taxonomy.get("config") or {}).get("n_cap", P.DEFAULT_N_CAP))


def extract_observations(records: list, *, dev: str | None = None) -> list:
    """Normalize raw telemetry/decision records into observations `{dev, area, candidate_key}`.

    Reads `guards_fired` (str or list of guard names → candidate keys), `codex_overturned` (truthy →
    a CODEX_OVERTURNED candidate), and explicit `{area, pattern_key}` records. If `dev` is given, only
    that dev's records are kept (a dev observes its OWN practices). Records without an `area` are skipped
    — an area is required to resolve against the taxonomy."""
    out = []
    for r in records:
        if not isinstance(r, dict):
            continue  # skip malformed telemetry items (None/str/…) — never crash on them
        rdev = r.get("dev")
        if dev is not None and rdev != dev:
            continue
        area = r.get("area")
        if not area:
            continue
        candidates = []
        gf = r.get("guards_fired")
        if isinstance(gf, str):
            candidates.append(gf)
        elif isinstance(gf, (list, tuple)):
            candidates.extend(gf)
        if r.get("codex_overturned"):
            candidates.append("CODEX_OVERTURNED")
        if r.get("pattern_key"):
            candidates.append(r["pattern_key"])
        for c in candidates:
            if c:
                out.append({"dev": rdev, "area": area, "candidate_key": str(c)})
    return out


def _entry_id(dev: str, area: str, pattern_key: str, candidate: str) -> str:
    """Stable id. UNMAPPED entries also carry the raw candidate so DISTINCT unmapped behaviors stay
    separate (never collapsed into one UNMAPPED bucket)."""
    if pattern_key == P.UNMAPPED:
        return f"{dev}:{area}:{P.UNMAPPED}:{candidate}"
    return f"{dev}:{area}:{pattern_key}"


def _patterns_file(patterns_dir, area: str, dev: str) -> Path:
    return Path(patterns_dir) / area / f"{dev}.yaml"


def _load_existing(path: Path) -> dict:
    """Existing patterns/<area>/<dev>.yaml as {id: entry}, or empty."""
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        e["id"]: dict(e)
        for e in data.get("patterns", [])
        if isinstance(e, dict) and e.get("id")
    }


def _practice(pattern_key: str, candidate: str, area: str, count: int) -> str:
    if pattern_key == P.UNMAPPED:
        return f"auto-observed unmapped behavior {candidate!r} ({count}x) in {area}"
    return f"auto-observed {pattern_key} ({count}x) in {area}"


def auto_observe(
    dev: str,
    records: list,
    *,
    taxonomy: dict,
    patterns_dir,
    declared: list | None = None,
) -> dict:
    """Observe `dev`'s practices from `records` and write patterns/<area>/<dev>.yaml (incrementally).

    Returns {written: [paths], entries: [entry], deltas: [delta]}. Only `dev`'s observations are used
    and only `dev`'s files are written (isolation). `declared` is an optional list of the dev's declared
    patterns ({area, pattern_key, practice}) used for the declared-vs-observed delta."""
    _require_yaml()
    observations = extract_observations(records, dev=dev)
    n_cap = _n_cap(taxonomy)
    declared = declared or []

    # Count new observations per (area, resolved_key, candidate).
    new_counts: dict = {}
    for o in observations:
        area = o["area"]
        candidate = o["candidate_key"]
        key = P.resolve_pattern_key(candidate, _area_keys(taxonomy, area))
        eid = _entry_id(dev, area, key, candidate)
        bucket = new_counts.setdefault(
            eid, {"area": area, "pattern_key": key, "candidate": candidate, "n": 0}
        )
        bucket["n"] += 1

    declared_by_area = {}
    for d in declared:
        declared_by_area.setdefault(d.get("area"), {})[d.get("pattern_key")] = d

    # Group new observations + existing entries by area, then write each area's file once.
    areas = {b["area"] for b in new_counts.values()} | set(declared_by_area)
    written, all_entries, deltas = [], [], []
    for area in sorted(a for a in areas if a):
        path = _patterns_file(patterns_dir, area, dev)
        existing = _load_existing(path)
        entries = dict(existing)  # id -> entry

        # apply declared entries first (so observed can upgrade source to observed+declared)
        for dkey, d in declared_by_area.get(area, {}).items():
            did = _entry_id(dev, area, dkey, dkey)
            if did not in entries:
                entries[did] = {
                    "id": did,
                    "dev": dev,
                    "area": area,
                    "pattern_key": dkey,
                    "practice": d.get("practice") or f"declared {dkey} in {area}",
                    "source": "declared",
                    "observation_count": 0,
                    "occurrence_confidence": P.compute_occurrence_confidence(
                        0, source="declared", n_cap=n_cap
                    ),
                    "efficacy_confidence": None,
                }

        # merge observed counts (incremental: add to any existing observation_count)
        for eid, b in new_counts.items():
            if b["area"] != area:
                continue
            prior = entries.get(eid, {})
            count = int(prior.get("observation_count", 0) or 0) + b["n"]
            both = b["pattern_key"] in declared_by_area.get(area, {})
            source = "observed+declared" if both else "observed"
            entry = {
                "id": eid,
                "dev": dev,
                "area": area,
                "pattern_key": b["pattern_key"],
                "practice": _practice(b["pattern_key"], b["candidate"], area, count),
                "source": source,
                "observation_count": count,
                "occurrence_confidence": P.compute_occurrence_confidence(
                    count, source=source, n_cap=n_cap
                ),
                "efficacy_confidence": None,
            }
            if b["pattern_key"] == P.UNMAPPED:
                entry["raw_behavior"] = b["candidate"]
            entries[eid] = entry

        # declared-vs-observed delta: a declared key with NO observed support, while a DIFFERENT key in
        # the same area DID get observed → flag the observed entries as a conflict (never suppress).
        observed_keys = {
            e["pattern_key"]
            for e in entries.values()
            if "observed" in e.get("source", "") and e.get("observation_count", 0) > 0
        }
        for dkey in declared_by_area.get(area, {}):
            did = _entry_id(dev, area, dkey, dkey)
            d_observed = entries.get(did, {}).get("observation_count", 0) > 0
            if not d_observed and observed_keys - {dkey}:
                for e in entries.values():
                    if (
                        "observed" in e.get("source", "")
                        and e.get("observation_count", 0) > 0
                        and e["pattern_key"] != dkey
                    ):
                        e["conflict"] = True
                        e["conflicts_with_declared"] = dkey
                        deltas.append(
                            {
                                "area": area,
                                "declared": dkey,
                                "observed": e["pattern_key"],
                            }
                        )

        # Normalize EVERY entry before writing (incl. untouched existing ones): occurrence_confidence
        # is always recomputed from observation_count+source and efficacy_confidence forced to None, so
        # an authored/stale computed field in a prior file can never leak through (Codex).
        for e in entries.values():
            e["efficacy_confidence"] = None
            e["occurrence_confidence"] = P.compute_occurrence_confidence(
                int(e.get("observation_count", 0) or 0),
                source=e.get("source", "observed"),
                n_cap=n_cap,
            )

        _write_area_file(path, dev, area, entries)
        written.append(str(path))
        all_entries.extend(entries.values())

    return {"written": written, "entries": all_entries, "deltas": deltas}


def _write_area_file(path: Path, dev: str, area: str, entries: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": SCHEMA_VERSION,
        "dev": dev,
        "area": area,
        "patterns": [entries[k] for k in sorted(entries)],
    }
    path.write_text(yaml.safe_dump(doc, sort_keys=True), encoding="utf-8")


def validate_observed_entry(entry: dict, taxonomy: dict | None = None) -> list:
    """Validate a SYSTEM-WRITTEN observed entry against the §1.3 schema. Unlike
    `patterns.validate_authored_pattern`, the computed fields are REQUIRED here (the system computes
    them) — but `efficacy_confidence` must be None and `occurrence_confidence` a float."""
    errors = []
    for f in P.REQUIRED_PATTERN_FIELDS:
        if not entry.get(f):
            errors.append(f"missing required field {f!r}")
    if entry.get("source") not in P._VALID_SOURCES:
        errors.append(f"invalid source {entry.get('source')!r}")
    if not isinstance(entry.get("occurrence_confidence"), (int, float)):
        errors.append("occurrence_confidence must be a computed float")
    if entry.get("efficacy_confidence") is not None:
        errors.append(
            "efficacy_confidence must be None until powered outcome evidence exists"
        )
    if taxonomy is not None:
        area, key = entry.get("area"), entry.get("pattern_key")
        if key != P.UNMAPPED and key not in set(_area_keys(taxonomy, area)):
            errors.append(f"pattern_key {key!r} not in taxonomy for area {area!r}")
    return errors
