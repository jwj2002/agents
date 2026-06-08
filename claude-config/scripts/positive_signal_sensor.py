"""`no_observed_defect_30d` positive-signal sensor (telemetry-validation §3 / §0.6, build item 7).

The honest positive metric. It breaks the failure-ONLY dependency (we otherwise only ever learn from
things that broke) WITHOUT manufacturing a false "correct" label. Naming discipline is the whole point
(Codex F3): the metric is **`no_observed_defect_30d`** — NEVER the legacy first-pass-correct naming.
"No defect observed" is NOT "correct"; the tracer is precision≫recall (§2.2), so absence of a signal means
the work *escaped detection*, not that it was right.

A unit (session/task) earns the positive `no_observed_defect` label ONLY when ALL of these hold:
  1. no correction signal within the 30d window (the defect tracer found no observed_defect), AND
  2. deployed/used code path (the change was actually exercised), AND
  3. meaningful test EXECUTION — tests actually ran AND covered the changed paths (not "tests exist"), AND
  4. reviewer coverage (human or qualified automated review occurred), AND
  5. CI scope (CI covered the change's surface), AND
  6. tracer coverage ≥ the stated recall threshold (§2.2) — coverage is KNOWN and adequate.
Miss ANY of 2-6 → `unverified` (NOT "good", never silently dropped). A correction within the window →
`correction_detected` regardless of exposure. Window not yet closed → `pending` (no label emitted yet).

The 30d window is measured from the task-freeze timestamp (frozen at the first implementation artifact,
#229) — never re-anchored after the outcome is known.

Cross-spec gate: a confirmed `no_observed_defect` is the ONLY state the KnowledgeMesh auto-observe
pipeline (jwj2002/knowledgemesh, knowledgemesh-mvp-v1 §1.2) may consume as a positive example — `unverified`/`pending`/
`correction_detected` are not auto-observable. `auto_observe_event` enforces that.

Host-agnostic and pure: takes injected tracer results + exposure evidence. Owner lane: server-a.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import defect_tracer as DT  # noqa: E402

WINDOW_DAYS = 30

# Terminal labels + the non-terminal "window still open" state.
LABEL_GOOD = "no_observed_defect"
LABEL_UNVERIFIED = "unverified"
LABEL_CORRECTION = "correction_detected"
LABEL_PENDING = (
    "pending"  # window not yet closed — NOT one of the three terminal labels
)

# Exposure-evidence booleans that ALL must be true for a positive label (conditions 2-5; condition 3
# is split into ran AND covered, per "tests actually ran and covered the changed paths").
REQUIRED_EXPOSURE = (
    "deployed",  # the change was actually exercised / used
    "tests_ran",  # tests EXECUTED (not merely present)
    "tests_covered_changed",  # and covered the changed paths
    "reviewer_coverage",  # human or qualified automated review occurred
    "ci_scope",  # CI covered the change's surface
)


def _parse_ts(value) -> float | None:
    """ISO-8601 (trailing Z ok) or epoch seconds → epoch float; None/unparseable → None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def window_closed(freeze_ts, now_ts, window_days: int = WINDOW_DAYS) -> bool:
    """True iff ≥ `window_days` have elapsed since the task-freeze timestamp. An unparsable/missing
    timestamp is NOT closed (fail-safe: a unit we can't time stays `pending`, never a premature label)."""
    f, n = _parse_ts(freeze_ts), _parse_ts(now_ts)
    if f is None or n is None:
        return False
    return (n - f) >= window_days * 86400


def missing_exposure(evidence: dict) -> list:
    """The exposure conditions NOT satisfied (empty list ⇒ complete). `evidence` defaults missing keys
    to falsey, so an absent field is a MISSING condition, never an assumed-present one."""
    evidence = evidence or {}
    return [k for k in REQUIRED_EXPOSURE if not evidence.get(k)]


def exposure_complete(evidence: dict) -> bool:
    """All exposure conditions (2-5, with tests split into ran+covered) present and true."""
    return not missing_exposure(evidence)


def classify_unit(
    unit_id,
    *,
    tracer_result: dict,
    exposure: dict,
    recall_threshold: float,
    freeze_ts,
    now_ts,
    window_days: int = WINDOW_DAYS,
    tracer_coverage_pct: float | None = None,
) -> dict:
    """Label one unit. `tracer_result` is the defect tracer's per-PR label dict (`label_target` /
    `trace_prs` output); `exposure` is the evidence dict. Order matters: window gate → correction →
    exposure+coverage. A correction is terminal regardless of exposure; below-threshold tracer coverage
    forces `unverified` even when every other condition is met (Codex F2/§2.2)."""
    coverage = (
        tracer_coverage_pct
        if tracer_coverage_pct is not None
        else (tracer_result or {}).get("coverage")
    )
    base = {
        "unit_id": unit_id,
        "window_days": window_days,
        "tracer_coverage_pct": coverage,
    }
    # 0. window must be closed before ANY terminal label is emitted
    if not window_closed(freeze_ts, now_ts, window_days):
        return {**base, "label": LABEL_PENDING, "reason": "window_open"}
    # 1. a correction observed within the window is terminal — exposure is irrelevant
    if (tracer_result or {}).get("label") == DT.LABEL_OBSERVED_DEFECT:
        return {
            **base,
            "label": LABEL_CORRECTION,
            "correction_by": tracer_result.get("by"),
        }
    # 2-6. A positive requires an EXPLICIT confirmed no-defect tracer result — "not observed_defect"
    # is NOT enough (Codex): a missing/unknown/`indeterminate_coverage` label means the tracer could
    # not confirm, which is `unverified`, never good (§0.6). Then full exposure AND adequate coverage.
    no_correction_confirmed = (tracer_result or {}).get("label") == DT.LABEL_NO_DEFECT
    miss = missing_exposure(exposure)
    coverage_ok = coverage is not None and coverage >= recall_threshold
    exposure_ok = not miss
    if no_correction_confirmed and exposure_ok and coverage_ok:
        label = LABEL_GOOD
    else:
        label = LABEL_UNVERIFIED
    return {
        **base,
        "label": label,
        "no_correction_confirmed": no_correction_confirmed,
        "exposure_evidence": {
            k: bool((exposure or {}).get(k)) for k in REQUIRED_EXPOSURE
        },
        "missing_exposure": miss,
        "coverage_ok": coverage_ok,
    }


def auto_observe_event(classification: dict) -> dict | None:
    """The KnowledgeMesh auto-observe hookpoint (km-mvp-v1 §1.2). Emits a positive-example event ONLY
    for a CONFIRMED `no_observed_defect` — `unverified` / `pending` / `correction_detected` are NOT
    auto-observable (the cross-spec gate). Defense-in-depth (Codex): the label alone is not trusted —
    the classification must ALSO show a confirmed no-correction tracer result, complete exposure, and
    adequate coverage, so an externally-constructed/forged label cannot enter the pipeline."""
    if classification.get("label") != LABEL_GOOD:
        return None
    if (
        classification.get("no_correction_confirmed") is not True
        or classification.get("coverage_ok") is not True
        or classification.get("missing_exposure")
        != []  # explicit empty list, not merely absent
    ):
        return None
    return {
        "event": "positive_example",
        "source": "no_observed_defect_30d",
        "unit_id": classification.get("unit_id"),
        "tracer_coverage_pct": classification.get("tracer_coverage_pct"),
        "window_days": classification.get("window_days"),
    }


def run_sensor(
    prs: list,
    units: list,
    *,
    exposure_by_unit: dict,
    recall_threshold: float,
    now_ts,
    calibration: dict | None = None,
    calibration_log_path=None,
    window_days: int = WINDOW_DAYS,
    repo: str | None = None,
) -> dict:
    """Full pipeline: defect tracer → per-unit exposure check → labels (+ auto-observe events).

    `units` are `{unit_id, pr, freeze_ts}` records; `exposure_by_unit` maps unit_id → evidence dict.
    Honors the tracer's calibration gate: if anchor emission is BLOCKED, no correction signals are
    trustworthy, so every unit is `unverified` (we cannot confirm a positive without a calibrated tracer)."""
    traced = DT.trace_prs(
        prs,
        calibration=calibration,
        calibration_log_path=calibration_log_path,
        now_ts=_parse_ts(now_ts),
        recall_threshold=recall_threshold,
        windows=(window_days,)
        if window_days not in DT.WINDOWS_DAYS
        else DT.WINDOWS_DAYS,
        repo=repo,
    )
    gate_open = traced.get("anchor_emission") == "allowed"
    by_pr = {lbl["number"]: lbl for lbl in traced.get("labels", [])}
    classifications = []
    for u in units:
        tracer_result = by_pr.get(u.get("pr"), {}) if gate_open else {}
        classifications.append(
            classify_unit(
                u.get("unit_id"),
                tracer_result=tracer_result,
                exposure=exposure_by_unit.get(u.get("unit_id"), {}),
                recall_threshold=recall_threshold,
                freeze_ts=u.get("freeze_ts"),
                now_ts=now_ts,
                window_days=window_days,
            )
        )
    events = [
        e for e in (auto_observe_event(c) for c in classifications) if e is not None
    ]
    return {
        "anchor_emission": traced.get("anchor_emission"),
        "classifications": classifications,
        "auto_observe_events": events,
    }
