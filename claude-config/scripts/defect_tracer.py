"""Precision-tiered behavioral defect tracer (telemetry-validation §2.2, build item 4 — ⭐ long pole).

The defect tracer is THE anchor of the proxy-validation loop. A contaminated anchor invalidates the
entire loop, so the design is **precision ≫ recall**: we would rather miss real defects than
false-accuse a clean PR. Three rules, three precision tiers:

  HIGH   — explicit PR revert ("this reverts #42")            → `correction_or_defect`
  MEDIUM — "fixes regression from #42" referencing the origin → `correction_or_defect` (medium tier)
  NOISE  — same-file edit within a window                     → weak hint ONLY, never auto-marks defect

Operates at **PR granularity via the `gh` API** — NOT commit lineage, because squash-merge collapses
lineage so "reverts commit <sha>" cannot be mapped back to a source PR (§2.2). A revert that names only
a commit SHA is *detected but unmapped* — it never marks any target PR defective.

Because precision≫recall means many real defects go UNSEEN, "no detected correction" is **never**
"correct" — it is `no_observed_defect` *under the tracer's stated coverage* (§0.6). A recall-estimation
layer (§2.2) keeps coverage KNOWN rather than assumed, and positive metrics that depend on
correctness-implied-by-absence are WITHHELD until estimated recall clears a stated threshold.

Calibration is a defined PREFLIGHT control (§2.2, Codex F9) — the one precise exception to "zero
manual": the tracer may emit anchor labels only after a ≥30-case seeded round scores precision ≥ 0.9.

Host-agnostic and pure: detection/labeling logic takes injected PR records (the shape `gh pr list
--json ...` returns, normalized by `from_gh_json`). `fetch_prs_via_gh` is the only live entrypoint.

Owner lane: server-a (implementation) + agent-b (calibration as a non-same-family rater). Built
host-agnostic by scratch against simulated PR payloads while server-a is out.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime

# --- precision tiers -----------------------------------------------------------------------------
TIER_HIGH = "high"
TIER_MEDIUM = "medium"
TIER_NOISE = "noise"
_TIER_RANK = {TIER_NOISE: 0, TIER_MEDIUM: 1, TIER_HIGH: 2}

# --- labels --------------------------------------------------------------------------------------
LABEL_CORRECTION = (
    "correction_or_defect"  # a revert/regression-fix PR: undoes/corrects prior work
)
LABEL_OBSERVED_DEFECT = (
    "observed_defect"  # a target PR that a later correction event references
)
LABEL_NO_DEFECT = (
    "no_observed_defect"  # default — ALWAYS published with a coverage annotation
)
# When coverage is below the recall threshold (or unknown) the "no defect" reading is NOT trustworthy
# as a quality signal — emit a DISTINCT label so a naive consumer cannot read absence as "clean" (§0.6).
LABEL_INDETERMINATE = "indeterminate_coverage"

# --- measurement windows (days) ------------------------------------------------------------------
# A fixed window catches fast crashes but misses slow logic bugs; we compute all three and state the
# per-window bias (§2.2). Windows are CUMULATIVE: a correction at lag 5d is observed in 7/14/30; a
# correction at lag 20d is observed in 30d ONLY (absent from 7d/14d — exactly the slow-bug a short
# window misses). `no_observed_defect_30d` (the metric, §364) is the 30d window.
WINDOWS_DAYS = (7, 14, 30)

# --- calibration preflight defaults (§2.2; v1 starting values, refined in §2.3 pre-registration) --
CALIB_MIN_SAMPLE = 30  # ≥30 stratified cases per round
CALIB_PRECISION_GATE = (
    0.9  # anchor-label emission requires precision ≥ 0.9 on the seeded set
)
CALIB_MAX_AGE_DAYS = (
    90  # recalibrate quarterly (§2.2 cadence); a stale round can't authorize
)

# --- recall-estimation signals (low-precision; coverage ONLY, NEVER an individual defect label) ---
RECALL_SIGNALS = (
    "ci_failed",  # CI failed on the PR
    "reopened",  # PR/issue reopened
    "forward_fix",  # a later PR fixes forward instead of reverting
    "issue_ref",  # references a bug issue
    "review_thread_negative",  # unresolved/negative review outcome
    "same_area_rework",  # semantic same-area rework
)

# --- detection regexes (PR-level #N references only) ----------------------------------------------
# Precision≫recall demands THREE guards beyond "verb near #N", or clean PRs get false-accused:
#   (a) ADJACENCY — the #N must immediately follow the verb (optionally via "of"/"pull request"/an
#       "owner/repo" prefix), so a clause-spanning "...see #42" or a quoted original title like
#       Revert "Fix login #42" does NOT capture the inner #N.
#   (b) NEGATION — a preceding aversion word ("do not revert", "prevents regression", "no regression")
#       flips the meaning; `_negated_before` drops those matches (Codex F2/F3).
#   (c) CROSS-REPO — an "owner/repo#N" qualifier that doesn't match the tracer's own repo is a
#       reference to a DIFFERENT repo's #N, not a local target (Codex F2); `_extract_refs` drops it.
# Requires a #N, so a commit-SHA-only revert (squash-collapsed lineage) does NOT map (§2.2). The verb
# must be ACCOMPLISHED tense ("reverts"/"reverted") — bare imperative "revert #42" is prospective/
# discussed ("a tool to revert #42 if needed", "option considered: revert #42") and must NOT count as
# a correction event (Codex re-review 3).
_REVERT_PR_RE = re.compile(
    r"\brevert(?:s|ed)\b\s*(?:of\s+|pull request\s+)?(?P<repo>[-\w.]+/[-\w.]+)?#(?P<num>\d+)",
    re.IGNORECASE,
)
# "This reverts commit deadbeef" — detected but UNMAPPED (PR-level only; no usable target).
_REVERT_COMMIT_RE = re.compile(
    r"\brevert(?:s|ed|ing)?\b\s+commit\s+[0-9a-f]{7,40}", re.IGNORECASE
)
# "fixes regression from #42", "regression introduced in #42", "regression #42". The qualifier must
# bridge directly to the #N — bare "regression ... #N" across a clause does not match.
_REGRESSION_RE = re.compile(
    r"\bregression\b\s*(?:from\s+|in\s+|introduced(?:\s+in|\s+by)?\s+)?(?P<repo>[-\w.]+/[-\w.]+)?#(?P<num>\d+)",
    re.IGNORECASE,
)
# Aversion words that, when they precede the verb, invert the signal ("do NOT revert #42").
_NEGATION_RE = re.compile(
    r"\b(?:no|not|never|without|avoid(?:s|ing)?|prevent(?:s|ing)?|future|potential|possible|any)\b"
    r"|n't",
    re.IGNORECASE,
)


_CLAUSE_BOUNDARY_RE = re.compile(r"[.;!?\n]")


def _negated_before(text: str, start: int) -> bool:
    """True if an aversion word appears anywhere in the CLAUSE preceding `start` (back to the nearest
    sentence/clause boundary) — meaning the revert/regression mention is negated and must be dropped.
    Clause-scoped (not a fixed char window) so distant negations like "do not under any circumstances
    revert #42" are caught, while a negation in a PRIOR sentence does not bleed in (Codex re-review)."""
    boundaries = list(_CLAUSE_BOUNDARY_RE.finditer(text, 0, start))
    clause_start = boundaries[-1].end() if boundaries else 0
    return _NEGATION_RE.search(text[clause_start:start]) is not None


def _extract_refs(regex: re.Pattern, text: str, *, repo: str | None) -> list:
    """Extract local PR references from `text` for a detection regex, applying the negation and
    cross-repo guards. Precision≫recall: a repo-qualified "owner/repo#N" ref is kept ONLY when the
    local repo is KNOWN and matches — when `repo` is None we cannot confirm it is local, so we DROP it
    (Codex re-review F2). Bare "#N" (same-repo shorthand) is always eligible."""
    refs = []
    for m in regex.finditer(text):
        if _negated_before(text, m.start()):
            continue
        ref_repo = m.group("repo")
        if ref_repo and (repo is None or ref_repo.lower() != repo.lower()):
            continue  # unconfirmed-local or different repo's #N — not a local target
        refs.append(int(m.group("num")))
    return sorted(set(refs))


def _tier_rank(tier: str) -> int:
    return _TIER_RANK.get(tier, 0)


def _parse_ts(value) -> float | None:
    """ISO-8601 (with trailing Z) or epoch seconds → epoch float. None/unparseable → None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _within_window(
    earlier, later, window_days: int, *, strict_after: bool = False
) -> bool:
    """True iff `later` is within `window_days` after `earlier` (INCLUSIVE at the upper boundary).
    With `strict_after`, a zero lag is rejected — a correction must land STRICTLY after the target so
    same-timestamp PRs (or a PR referencing itself) can never be read as a later correction (Codex F4)."""
    e, lt = _parse_ts(earlier), _parse_ts(later)
    if e is None or lt is None:
        return False
    lag = lt - e
    if lag < 0 or (strict_after and lag <= 0):
        return False
    return lag <= window_days * 86400


# --- normalization (gh payload → internal PR record) ---------------------------------------------
def from_gh_json(items: list) -> list:
    """Normalize `gh pr list --json number,title,body,mergedAt,files,labels` output into internal PR
    records. `files` is a list of {path,...}; `labels` a list of {name}. camelCase mergedAt → merged_at.
    Recall-signal booleans (ci_failed/reopened/...) pass through if already present (enriched upstream)."""
    out = []
    for it in items:
        files = it.get("files") or []
        labels = it.get("labels") or []
        rec = {
            "number": it.get("number"),
            "title": it.get("title", "") or "",
            "body": it.get("body", "") or "",
            "merged_at": it.get("mergedAt") or it.get("merged_at"),
            "files": [f.get("path") if isinstance(f, dict) else f for f in files],
            "labels": [l_.get("name") if isinstance(l_, dict) else l_ for l_ in labels],
        }
        for sig in RECALL_SIGNALS:
            if sig in it:
                rec[sig] = it[sig]
        out.append(rec)
    return out


# --- precision-tier classification of a single PR ------------------------------------------------
def classify_pr(pr: dict, *, repo: str | None = None) -> dict | None:
    """Classify a PR by its OWN text into a correction event, or None if it carries no correction
    signal. A correction event references the prior PR(s) it undoes/corrects (`references`). `repo`
    (owner/name) enables the cross-repo guard — repo-qualified refs to other repos are dropped.

    Tiers: explicit PR revert → HIGH; "fixes regression from #PR" → MEDIUM. A commit-SHA-only revert
    is returned UNMAPPED (`references=[]`, `unmapped=True`) — detected for transparency but it labels
    no target defective, because squash-merge collapses commit lineage (§2.2)."""
    text = f"{pr.get('title', '')}\n{pr.get('body', '')}"
    revert_refs = _extract_refs(_REVERT_PR_RE, text, repo=repo)
    if revert_refs:
        return {
            "number": pr.get("number"),
            "label": LABEL_CORRECTION,
            "tier": TIER_HIGH,
            "references": revert_refs,
            "evidence": "explicit_pr_revert",
            "merged_at": pr.get("merged_at"),
        }
    _commit_revert = _REVERT_COMMIT_RE.search(text)
    if _commit_revert and not _negated_before(text, _commit_revert.start()):
        # Revert detected but only a commit SHA — unusable at PR granularity (§2.2).
        return {
            "number": pr.get("number"),
            "label": None,
            "tier": TIER_HIGH,
            "references": [],
            "evidence": "commit_revert_unmapped",
            "unmapped": True,
            "merged_at": pr.get("merged_at"),
        }
    regression_refs = _extract_refs(_REGRESSION_RE, text, repo=repo)
    if regression_refs:
        return {
            "number": pr.get("number"),
            "label": LABEL_CORRECTION,
            "tier": TIER_MEDIUM,
            "references": regression_refs,
            "evidence": "regression_fix",
            "merged_at": pr.get("merged_at"),
        }
    return None


def same_file_noise_hint(pr: dict, prior_prs: list, window_days: int = 14) -> dict:
    """NOISE tier: prior PRs sharing ≥1 file within the window. A weak corroboration hint ONLY — the
    return carries `is_defect_label=False` and `label=None`; this NEVER auto-marks a PR defective
    (files churn for non-defect reasons, §2.2)."""
    target_files = set(pr.get("files") or [])
    hits = []
    for p in prior_prs:
        if p.get("number") == pr.get("number"):
            continue
        if target_files & set(p.get("files") or []) and _within_window(
            p.get("merged_at"), pr.get("merged_at"), window_days
        ):
            hits.append(p.get("number"))
    return {
        "tier": TIER_NOISE,
        "label": None,
        "is_defect_label": False,
        "noise_refs": sorted(n for n in hits if n is not None),
        "window_days": window_days,
    }


def build_correction_index(prs: list, *, repo: str | None = None) -> list:
    """All PRs that are themselves *mapped* correction events (have ≥1 PR reference). Unmapped
    commit-reverts are excluded from the index (they label nothing) but counted elsewhere."""
    events = []
    for pr in prs:
        c = classify_pr(pr, repo=repo)
        if c and c.get("references"):
            events.append(c)
    return events


# --- target labeling across the three windows ----------------------------------------------------
def label_target(
    target_pr: dict,
    correction_events: list,
    *,
    windows: tuple = WINDOWS_DAYS,
    coverage: float | None = None,
    recall_threshold: float = 0.0,
) -> dict:
    """Label one implementation PR. `observed_defect` if any correction event references it within a
    window; otherwise `no_observed_defect` ANNOTATED WITH COVERAGE. The positive label is admissible
    as a quality metric only when coverage ≥ recall_threshold (else withheld from targets, §0.5/§0.6)."""
    num = target_pr.get("number")
    t_ts = target_pr.get("merged_at")
    windows = tuple(sorted(windows))
    # A PR can never label ITSELF defective; corrections must land strictly after the target (Codex F4).
    events = [e for e in correction_events if e.get("number") != num]
    # Admissibility is global (coverage vs threshold) — apply it to EACH per-window non-observed entry
    # too, so a window-level consumer can't read below-coverage absence as "clean" (Codex re-review F5).
    admissible = coverage is not None and coverage >= recall_threshold
    absent_label = LABEL_NO_DEFECT if admissible else LABEL_INDETERMINATE
    per_window: dict = {}
    observed = False
    max_tier = TIER_NOISE
    by: set = set()
    for w in windows:
        hits = [
            e
            for e in events
            if num in e.get("references", [])
            and _within_window(t_ts, e.get("merged_at"), w, strict_after=True)
        ]
        if hits:
            wt = max((e["tier"] for e in hits), key=_tier_rank)
            per_window[w] = {
                "observed": True,
                "label": LABEL_OBSERVED_DEFECT,
                "by": sorted(e["number"] for e in hits),
                "tier": wt,
            }
            observed = True
            if _tier_rank(wt) > _tier_rank(max_tier):
                max_tier = wt
            by |= {e["number"] for e in hits}
        else:
            per_window[w] = {
                "observed": False,
                "label": absent_label,
                "coverage": coverage,
            }
    if observed:
        return {
            "number": num,
            "label": LABEL_OBSERVED_DEFECT,
            "tier": max_tier,
            "by": sorted(by),
            "coverage": coverage,
            "per_window": per_window,
        }
    # No correction observed. The label is admissible as a *quality* signal only if coverage clears the
    # recall threshold; below it (or coverage unknown) emit a DISTINCT label so "absence" can never be
    # silently consumed as "clean" (Codex F5, §0.6).
    return {
        "number": num,
        "label": LABEL_NO_DEFECT if admissible else LABEL_INDETERMINATE,
        "coverage": coverage,
        "metric_admissible": admissible,
        "per_window": per_window,
        "note": None
        if admissible
        else "coverage_below_recall_threshold__withheld_from_targets",
    }


# --- recall estimation (coverage only — never an individual defect label) -------------------------
def recall_candidates(prs: list) -> list:
    """PRs exhibiting ANY low-precision recall signal (CI failure, reopen, forward-fix, ...). These
    feed coverage estimation ONLY — each carries `label=None`; this function NEVER marks a PR
    defective (the §2.2 invariant: recall signals bound coverage, they do not accuse individuals)."""
    out = []
    for pr in prs:
        sigs = [s for s in RECALL_SIGNALS if pr.get(s)]
        if sigs:
            out.append({"number": pr.get("number"), "signals": sigs, "label": None})
    return out


def estimate_coverage(
    *, high_precision_count: int, recall_candidate_count: int, audit: dict | None = None
) -> dict:
    """Estimate the tracer's recall/coverage so positive labels can be published WITH it.

    Gold method (`audit_sample`): a human re-checks a stratified slice → recall = caught/true_defects.
    Fallback (`signal_lower_bound`): high-precision catches over (catches + low-precision candidates
    the precise rules missed) — a conservative lower bound, never asserted as exact recall."""
    if audit and audit.get("true_defects_found", 0) > 0:
        cov = audit.get("tracer_caught", 0) / audit["true_defects_found"]
        return {
            "coverage": round(min(1.0, cov), 4),
            "method": "audit_sample",
            "audit": audit,
        }
    denom = high_precision_count + recall_candidate_count
    cov = (high_precision_count / denom) if denom > 0 else 0.0
    return {
        "coverage": round(cov, 4),
        "method": "signal_lower_bound",
        "high_precision_count": high_precision_count,
        "recall_candidates": recall_candidate_count,
    }


# --- calibration preflight -----------------------------------------------------------------------
def _case_predicted(case: dict) -> str:
    """A seeded case's tracer prediction: explicit `predicted`, else classify its `pr` ('defect' if it
    classifies as a mapped correction event, else 'clean')."""
    if "predicted" in case:
        return case["predicted"]
    c = classify_pr(case.get("pr", {}))
    return "defect" if (c and c.get("references")) else "clean"


def run_calibration(
    seeded_cases: list,
    *,
    min_sample: int = CALIB_MIN_SAMPLE,
    gate: float = CALIB_PRECISION_GATE,
    round_ts: str | None = None,
) -> dict:
    """Calibration preflight (§2.2). Each case: `{truth: 'defect'|'clean', predicted|pr: ...}`.
    Precision = TP / (TP + FP) over cases the tracer PREDICTS defective. Anchor-label emission is
    BLOCKED if the sample is < min_sample or precision < gate; the result is logged with the round
    timestamp, sample size, precision and pass/fail verdict (an audit record)."""
    n = len(seeded_cases)
    if n < min_sample:
        return {
            "passed": False,
            "anchor_emission": "blocked",
            "reason": "insufficient_sample",
            "sample_size": n,
            "min_sample": min_sample,
            "precision": None,
            "gate": gate,
            "round_ts": round_ts,
        }
    tp = fp = 0
    for c in seeded_cases:
        if _case_predicted(c) == "defect":
            if c.get("truth") == "defect":
                tp += 1
            else:
                fp += 1
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    passed = precision >= gate
    return {
        "passed": passed,
        "anchor_emission": "allowed" if passed else "blocked",
        "reason": "ok" if passed else "precision_below_gate",
        "precision": round(precision, 4),
        "sample_size": n,
        "gate": gate,
        "tp": tp,
        "fp": fp,
        "round_ts": round_ts,
    }


def _is_count(x) -> bool:
    """A real non-negative integer count — excludes bool (an int subclass) and negatives."""
    return isinstance(x, int) and not isinstance(x, bool) and x >= 0


def calibration_authorizes_emission(calibration: dict | None) -> bool:
    """Authorize the anchor gate from the calibration round's EVIDENCE, not its summary fields. The
    decision is RE-DERIVED from the confusion-matrix counts (tp/fp) rather than trusting the reported
    `precision`/`passed` flags — so a forged `{"passed": True, "precision": 0.9}` with no real round
    does NOT open the gate (Codex F1 + re-review). NOTE: an in-process dict is NEVER fully tamper-proof
    (a caller can author internally consistent counts); the PRODUCTION gate is `authorized_from_log`,
    which ties authorization to the persisted, freshness-checked audit log. This dict check is the
    in-process/testing path and a defense against ACCIDENTAL bypass.

    Requires: an `allowed` verdict, non-negative-int tp/fp/sample_size (no bools), sample ≥
    CALIB_MIN_SAMPLE, at least one positive prediction (tp+fp > 0), counts not exceeding the sample,
    and RECOMPUTED precision ≥ gate."""
    if not isinstance(calibration, dict):
        return False
    if calibration.get("anchor_emission") != "allowed":
        return False
    tp, fp, sample = (calibration.get(k) for k in ("tp", "fp", "sample_size"))
    # Reject bools (bool IS an int subclass) and negatives — else nonsense like fp=-29 recomputes a
    # passing precision and bypasses the matrix check (Codex re-review 3).
    if not all(_is_count(x) for x in (tp, fp, sample)):
        return False
    if tp + fp <= 0 or sample < CALIB_MIN_SAMPLE or sample < tp + fp:
        return False
    return (tp / (tp + fp)) >= CALIB_PRECISION_GATE


def log_calibration(result: dict, sink_path) -> dict:
    """Append a calibration round to an audit log (one JSON line). Returns the written record."""
    from pathlib import Path

    rec = {"event": "calibration_round", **result}
    p = Path(sink_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return rec


def latest_calibration(log_path) -> dict | None:
    """The most recent `calibration_round` record in the audit log, or None if none/unreadable."""
    from pathlib import Path

    p = Path(log_path)
    if not p.exists():
        return None
    last = None
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("event") == "calibration_round":
            last = rec
    return last


def authorized_from_log(
    log_path, *, now_ts: float | None = None, max_age_days: int = CALIB_MAX_AGE_DAYS
) -> dict:
    """PRODUCTION anchor gate: authorize from the PERSISTED audit log, not a caller-passed dict. The
    authorization is tied to a logged round (written by `run_calibration` → `log_calibration`) AND must
    be within the recalibration cadence (§2.2 quarterly). This raises the bar from "forge an argument"
    to "forge a dated, passing entry in the on-disk audit log within the freshness window". (Full
    tamper-resistance — signing the log — is a documented v2 item.)"""
    rec = latest_calibration(log_path)
    if rec is None:
        return {"authorized": False, "reason": "no_calibration_logged"}
    if not calibration_authorizes_emission(rec):
        return {"authorized": False, "reason": "latest_round_failed"}
    if now_ts is not None and rec.get("round_ts"):
        ts = _parse_ts(rec["round_ts"])
        if ts is not None and (now_ts - ts) > max_age_days * 86400:
            return {"authorized": False, "reason": "calibration_stale", "round": rec}
    return {"authorized": True, "reason": "ok", "round": rec}


# --- session association (#229 dependency) -------------------------------------------------------
def associate_sessions(labeled_prs: list, session_meta: dict) -> list:
    """Attach the session(s) that produced each PR, via the #229 capture meta keyed by PR number — so
    a defect signal can be associated with the session whose work it judges (the proxy-loop input)."""
    by_pr: dict = {}
    for sid, m in (session_meta or {}).items():
        pr_num = m.get("pr")
        if pr_num is not None:
            by_pr.setdefault(pr_num, []).append(sid)
    return [
        {**lp, "sessions": sorted(set(by_pr.get(lp.get("number"), [])))}
        for lp in labeled_prs
    ]


# --- top-level pass ------------------------------------------------------------------------------
def trace_prs(
    prs: list,
    *,
    calibration: dict | None = None,
    calibration_log_path=None,
    now_ts: float | None = None,
    recall_threshold: float = 0.5,
    windows: tuple = WINDOWS_DAYS,
    session_meta: dict | None = None,
    repo: str | None = None,
) -> dict:
    """Full tracer pass over normalized PR records. HONORS THE CALIBRATION GATE. PRODUCTION callers
    pass `calibration_log_path` (+ `now_ts`): authorization comes from the persisted, freshness-checked
    audit log via `authorized_from_log`. The in-process/testing path passes a `calibration` dict, which
    is re-verified from its confusion-matrix evidence. Either way a forged/absent/stale round emits NO
    anchor labels. When authorized, every PR is labeled across the three windows, annotated with
    estimated coverage, with positive labels withheld from targets below the recall threshold."""
    events = build_correction_index(prs, repo=repo)
    candidates = recall_candidates(prs)
    cov = estimate_coverage(
        high_precision_count=len(events), recall_candidate_count=len(candidates)
    )
    coverage = cov["coverage"]
    if calibration_log_path is not None:
        auth = authorized_from_log(calibration_log_path, now_ts=now_ts)
        authorized, reason = auth["authorized"], auth["reason"]
    else:
        authorized = calibration_authorizes_emission(calibration)
        reason = (
            calibration.get("reason", "calibration_unauthorized")
            if isinstance(calibration, dict)
            else "calibration_unauthorized"
        )
    if not authorized:
        # Gate CLOSED: withhold ALL anchor-bearing data — not just `labels`, but `correction_events`
        # too (they carry correction_or_defect classifications + target references). Returning them
        # would let a consumer read anchor signals despite the closed gate (Codex re-review F2). Only
        # non-label counts survive, for diagnostics.
        return {
            "anchor_emission": "blocked",
            "reason": reason,
            "coverage": cov,
            "correction_event_count": len(events),
            "recall_candidate_count": len(candidates),
            "labels": [],
        }
    labels = [
        label_target(
            p,
            events,
            windows=windows,
            coverage=coverage,
            recall_threshold=recall_threshold,
        )
        for p in prs
    ]
    if session_meta:
        labels = associate_sessions(labels, session_meta)
    return {
        "anchor_emission": "allowed",
        "coverage": cov,
        "calibration": calibration,
        "correction_events": events,
        "recall_candidates": candidates,
        "labels": labels,
    }


# --- live entrypoint (not unit-tested; the thin gh adapter) --------------------------------------
def fetch_prs_via_gh(
    repo: str | None = None, *, state: str = "merged", limit: int = 200
) -> list:
    """Pull merged PRs via the `gh` CLI and normalize them. The only live/IO path; all logic above is
    pure and tested against simulated payloads. Requires `gh` authed as the repo's account."""
    cmd = [
        "gh",
        "pr",
        "list",
        "--state",
        state,
        "--limit",
        str(limit),
        "--json",
        "number,title,body,mergedAt,files,labels",
    ]
    if repo:
        cmd += ["--repo", repo]
    raw = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return from_gh_json(json.loads(raw))
