"""map_patterns — the divergence-map assembler (team-knowledge-mvp-v1 §1.0/§1.4/§1.6, build item §9.4).

The TARGET stage of SENSE→TARGET→INVEST: it POINTS at where a shared pattern would pay off; it does
NOT decide. It reads every patterns/<area>/<dev>.yaml (written by auto-observe #243), builds the
`CELL[area][dev]` matrix, classifies each area row, and enforces the §1.6 adopted-pattern lifecycle
gates — producing states only up through `published-advisory` (validated-and-beyond is per-dev and
needs `efficacy_confidence`, which no assembler step provides).

Row classification (§1.4), precedence CONFLICT → CONSENSUS → DIVERGENCE → GAP:
- CONFLICT  — ≥2 mutually-exclusive keys present in the same area → arbiter = Jason, NEVER auto-promoted.
- CONSENSUS — a key reaches quorum (3/4) of devs with `occurrence_confidence ≥ floor` AND `source`
  including `observed`. Purely-declared agreement NEVER trips quorum (§1.3 guard).
- DIVERGENCE — ≥2 different, non-contradictory observed keys, none at quorum.
- GAP — coverage missing for some/all devs, only sub-floor/declared support, or only UNMAPPED.

§1.6 gates on a CONSENSUS candidate:
- DISCONFIRM: is there a clear signal that devs practicing key K have WORSE outcomes in area A?
  contradicted → `blocked-contradicted` (route to arbiter, never publish); else → `not-disconfirmed`
  (cleared for ADVISORY publish — NEVER renamed `validated`; the §1.6 step-2 name is enforced).
- Low-confidence CONTRADICTORY signals STAY VISIBLE (§1.3 rule 3): the floor mutes a key from quorum,
  never from the conflict/gap surface.
- UNMAPPED entries are surfaced as taxonomy-gap signals (counted toward GAP), never force-bucketed.

Owner lane: server-a (§9.4/§11). Reads via PyYAML; pure classification otherwise.
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

QUORUM = 3  # 3 of 4 devs (§1.4)
# Lifecycle states the ASSEMBLER may emit (the rest are per-dev, efficacy-gated — §1.6).
STATE_NOT_DISCONFIRMED = "not-disconfirmed"
STATE_BLOCKED = "blocked-contradicted"
# Row outcomes (§1.4).
CONSENSUS, DIVERGENCE, CONFLICT, GAP = "CONSENSUS", "DIVERGENCE", "CONFLICT", "GAP"


def _require_yaml():
    if yaml is None:
        raise RuntimeError("PyYAML required for map_patterns")


def build_cell(patterns_dir, devs=None) -> dict:
    """CELL[area][dev] = list of pattern entries, read from patterns/<area>/<dev>.yaml."""
    _require_yaml()
    root = Path(patterns_dir)
    cell: dict = {}
    if not root.exists():
        return cell
    for area_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        area = area_dir.name
        for f in sorted(area_dir.glob("*.yaml")):
            dev = f.stem
            if devs is not None and dev not in devs:
                continue
            data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
            cell.setdefault(area, {})[dev] = data.get("patterns", []) or []
    return cell


def within_dev_divergence(cell: dict) -> dict:
    """Per dev: areas where the dev applies ≥2 different observed `pattern_key`s — i.e. diverges from
    THEMSELVES across their own work (§1.4 within-developer scope)."""
    out: dict = {}
    for area, devmap in cell.items():
        for dev, entries in devmap.items():
            keys = sorted(
                {
                    e.get("pattern_key")
                    for e in entries
                    if e.get("pattern_key")
                    and e.get("pattern_key") != P.UNMAPPED
                    and "observed" in (e.get("source") or "")
                }
            )
            if len(keys) >= 2:
                out.setdefault(dev, {})[area] = keys
    return out


def taxonomy_gaps(cell: dict) -> list:
    """All UNMAPPED entries, surfaced as taxonomy-gap signals (never force-bucketed)."""
    gaps = []
    for area, devmap in cell.items():
        for dev, entries in devmap.items():
            for e in entries:
                if e.get("pattern_key") == P.UNMAPPED:
                    gaps.append(
                        {
                            "area": area,
                            "dev": dev,
                            "raw_behavior": e.get("raw_behavior"),
                            "observation_count": e.get("observation_count", 0),
                        }
                    )
    return gaps


def classify_row(
    area: str,
    devmap: dict,
    *,
    team_devs,
    quorum: int = QUORUM,
    floor: float = P.DEFAULT_CONSENSUS_FLOOR,
    contradictions: dict | None = None,
    is_disconfirmed=None,
) -> dict:
    """Classify one area row across devs. `contradictions[area]` is a list of mutually-exclusive key
    groups; `is_disconfirmed(area, key) -> bool` is the telemetry-outcome gate (§1.6 step 2)."""
    contradictions = contradictions or {}
    present = sorted(devmap)
    missing = sorted(set(team_devs) - set(present))

    key_devs: dict = {}  # observed, non-UNMAPPED key -> set(devs present with it)
    elig_devs: dict = {}  # key -> set(devs whose entry is consensus-eligible)
    declared_keys: set = set()
    low_conf: list = []  # sub-floor observed entries — kept VISIBLE (§1.3 rule 3)
    for dev, entries in devmap.items():
        for e in entries:
            k = e.get("pattern_key")
            if not k or k == P.UNMAPPED:
                continue
            src = e.get("source") or ""
            conf = e.get("occurrence_confidence", 0.0) or 0.0
            if "observed" in src:
                key_devs.setdefault(k, set()).add(dev)
                if conf < floor:
                    low_conf.append(
                        {
                            "dev": dev,
                            "area": area,
                            "pattern_key": k,
                            "occurrence_confidence": conf,
                        }
                    )
            else:
                declared_keys.add(k)
            if P.is_consensus_eligible(conf, src, floor):
                elig_devs.setdefault(k, set()).add(dev)

    row = {
        "area": area,
        "present_devs": present,
        "missing_devs": missing,
        "keys": {k: sorted(d) for k, d in key_devs.items()},
        "contradictions_visible": low_conf,
    }

    # 1. CONFLICT — mutually-exclusive keys present in the same area (never auto-promoted)
    present_keys = set(key_devs)
    for grp in contradictions.get(area, []):
        inter = sorted(k for k in grp if k in present_keys)
        if len(inter) >= 2:
            row.update(outcome=CONFLICT, conflict_keys=inter, arbiter="jason")
            return row

    # 2. CONSENSUS — a key at quorum of eligible devs → run the §1.6 disconfirm gate
    consensus_key = next((k for k, d in elig_devs.items() if len(d) >= quorum), None)
    if consensus_key:
        row.update(
            outcome=CONSENSUS,
            consensus_key=consensus_key,
            consensus_devs=sorted(elig_devs[consensus_key]),
        )
        contradicted = (
            bool(is_disconfirmed(area, consensus_key)) if is_disconfirmed else False
        )
        if contradicted:
            row.update(state=STATE_BLOCKED, arbiter="jason")
        else:
            row.update(state=STATE_NOT_DISCONFIRMED, advisory_publishable=True)
        return row

    # 3. DIVERGENCE — ≥2 different non-contradictory observed keys, none at quorum
    if len(present_keys) >= 2:
        row.update(outcome=DIVERGENCE)
        return row

    # 4. GAP — missing coverage / declared-only / sub-floor / single-key-without-quorum
    note = None
    if not present_keys and declared_keys:
        note = "quorum_blocked_purely_declared"
    elif present_keys and not elig_devs:
        note = "quorum_blocked_subfloor"
    row.update(outcome=GAP, note=note)
    return row


def assemble(
    patterns_dir,
    *,
    team_devs,
    quorum: int = QUORUM,
    floor: float = P.DEFAULT_CONSENSUS_FLOOR,
    contradictions: dict | None = None,
    is_disconfirmed=None,
    devs=None,
) -> dict:
    """Full divergence map: classified rows + within-dev divergence + taxonomy gaps + the visible
    low-confidence contradictions. Machine-readable; `render_map` produces the human view."""
    cell = build_cell(patterns_dir, devs=devs)
    rows = {
        area: classify_row(
            area,
            devmap,
            team_devs=team_devs,
            quorum=quorum,
            floor=floor,
            contradictions=contradictions,
            is_disconfirmed=is_disconfirmed,
        )
        for area, devmap in cell.items()
    }
    return {
        "areas": rows,
        "within_dev_divergence": within_dev_divergence(cell),
        "taxonomy_gaps": taxonomy_gaps(cell),
        "low_confidence_contradictions": [
            c for r in rows.values() for c in r["contradictions_visible"]
        ],
    }


def render_map(result: dict) -> str:
    """Human-readable divergence map. Mirrors the machine output; emits no lifecycle state the
    assembler isn't allowed to ('validated' never appears here)."""
    lines = ["# Divergence map (TARGET stage — advisory, not a decision)"]
    for area, r in sorted(result["areas"].items()):
        seg = f"- {area}: {r['outcome']}"
        if r.get("consensus_key"):
            seg += f" key={r['consensus_key']} state={r.get('state')}"
        if r.get("arbiter"):
            seg += f" arbiter={r['arbiter']}"
        if r.get("note"):
            seg += f" ({r['note']})"
        if r.get("missing_devs"):
            seg += f" missing={','.join(r['missing_devs'])}"
        lines.append(seg)
    if result["taxonomy_gaps"]:
        lines.append(f"# taxonomy gaps (UNMAPPED): {len(result['taxonomy_gaps'])}")
    if result["within_dev_divergence"]:
        lines.append(
            f"# within-dev divergence: {sorted(result['within_dev_divergence'])}"
        )
    return "\n".join(lines)
