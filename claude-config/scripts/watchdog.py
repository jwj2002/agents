"""Dead-man's-switch watchdog — alarm logic core (telemetry-validation §0.1 / §2.5, build item 3).

"A host that goes silent IS the fleet alarm" — but absence is only a signal if something OWNS the
expectation and no component watches only itself (§0.1). This module is the host-agnostic ALARM LOGIC:
pure functions that turn observations into DISTINCT named alerts. The deploy that produces those
observations — the launchd poller (#221), the hub-side expected-host registry, the poller-health
heartbeat — is server-a's lane and is DEFERRED (documented), exactly like #230's collector deploy.
The logic here is what the hub/poller call; it is fully tested against simulated observations.

Two watchdog families:

  LIVENESS (§0.1) — FIVE distinct reporting-failure states, each its OWN named alert (never one generic
  "silent"): `hub-unreachable`, `poller-down` (poller heartbeat absent/stale — distinct from the capture
  heartbeat, so the watchdog can't die silently), `heartbeat-only` (capture alive but empty payload),
  `corrupt-payload` (malformed record, names the offending shard), `stale-exporter` (OTEL sink past SLA,
  wired from #230). Plus a roster check: an expected host past its `last_seen` SLA → `host-silent`.

  EXCLUSION (§2.5, Codex F7) — the watchdog must NOT share the classifier's eyes, so these use evidence
  INDEPENDENT of per-session capture: `exclusion-rate`/`unclassified-rate` too high, an
  `implementation-like-but-excluded` session (code artifacts inside a deliberative/ops session),
  `prove-coverage-missing` (code change with no PROVE/CI/test evidence), and a `reconciliation-gap`
  (a file changed on disk that the session never reported).

Pure + host-agnostic. Owner lane: server-a (deploy); built host-agnostic by scratch.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import otel_sink as O  # noqa: E402  (reuse the #230 exporter-freshness check)

DEFAULT_SLA_SECONDS = 24 * 3600  # matches otel_sink's exporter SLA

# --- liveness alert names (the five distinct failure states + the roster signal) ------------------
ALERT_HUB_UNREACHABLE = "hub-unreachable"
ALERT_POLLER_DOWN = "poller-down"
ALERT_HEARTBEAT_ONLY = "heartbeat-only"
ALERT_CORRUPT = "corrupt-payload"
ALERT_STALE_EXPORTER = "stale-exporter"
ALERT_HOST_SILENT = (
    "host-silent"  # roster: an expected host past its last_seen SLA (§0.1)
)

# --- content-completeness + exclusion alert names -------------------------------------------------
ALERT_SEQUENCE_GAP = "sequence-gap"
ALERT_FIELD_INCOMPLETE = "field-incomplete"
ALERT_EXCLUSION_RATE = "exclusion-rate-high"
ALERT_UNCLASSIFIED_RATE = "unclassified-rate-high"
ALERT_IMPL_EXCLUDED = "implementation-like-but-excluded"
ALERT_PROVE_COVERAGE = "prove-coverage-missing"
ALERT_RECONCILIATION_GAP = "reconciliation-gap"

# Work types with no valid code-quality measurement — they should carry NO implementation artifacts.
EXCLUDED_WORK_TYPES = frozenset({"deliberative", "ops"})
# Artifact fields that indicate implementation work happened in a session.
IMPL_ARTIFACT_KEYS = ("files_edited", "commits", "prs", "tests_changed")


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


def _stale(last, now_ts, sla_seconds: int) -> bool:
    """True if `last` is absent or older than the SLA. An ABSENT beat is stale (fail-safe: a missing
    heartbeat is the alarm, never silently 'ok')."""
    lt, n = _parse_ts(last), _parse_ts(now_ts)
    if lt is None:
        return True
    if n is None:
        return False
    return (n - lt) > sla_seconds


# --- liveness: five distinct states per reporting source -----------------------------------------
def classify_liveness(
    obs: dict, *, now_ts, sla_seconds: int = DEFAULT_SLA_SECONDS
) -> list:
    """Distinct named liveness alerts for ONE reporting source. `obs`: {host, hub_reachable(bool),
    poller_last_beat, capture_last_beat, payload(dict|None), payload_valid(bool), shard}. Each failure
    mode is its OWN alert (§0.1) — never collapsed into one generic 'silent'."""
    host = obs.get("host")
    if obs.get("hub_reachable") is False:
        # the hub is the source of truth; if it's unreachable, downstream beats are unknowable
        return [{"alert": ALERT_HUB_UNREACHABLE, "host": host}]
    alerts = []
    # poller-down: the poller's OWN heartbeat is absent/stale (distinct from the capture heartbeat —
    # else the watchdog dies silently and every host looks fine)
    if _stale(obs.get("poller_last_beat"), now_ts, sla_seconds):
        alerts.append({"alert": ALERT_POLLER_DOWN, "host": host})
    # capture heartbeat present & fresh, but...
    if not _stale(obs.get("capture_last_beat"), now_ts, sla_seconds):
        if not obs.get("payload"):
            # ...payload empty → heartbeat-only (alive but emitting nothing), NOT poller-down
            alerts.append({"alert": ALERT_HEARTBEAT_ONLY, "host": host})
        elif obs.get("payload_valid") is False:
            # ...payload present but malformed → corrupt, naming the offending shard
            alerts.append(
                {"alert": ALERT_CORRUPT, "host": host, "shard": obs.get("shard")}
            )
    return alerts


def check_exporter(
    sink_path, *, now_ts, sla_seconds: int = DEFAULT_SLA_SECONDS
) -> dict | None:
    """Stale-exporter alert, wired from #230's `otel_sink.check_exporter_freshness`. `sink_missing`
    and `stale_exporter` both surface as a `stale-exporter` alert carrying the underlying reason."""
    res = O.check_exporter_freshness(sink_path, now_ts=now_ts, sla_seconds=sla_seconds)
    if res.get("alarm"):
        return {
            "alert": ALERT_STALE_EXPORTER,
            "reason": res.get("reason"),
            "sink": str(sink_path),
        }
    return None


def check_roster(
    expected_hosts,
    last_seen_by_host: dict,
    *,
    now_ts,
    sla_seconds: int = DEFAULT_SLA_SECONDS,
) -> list:
    """Expected-host registry cross-check (§0.1): an expected host that is never-seen or past its
    `last_seen` SLA → `host-silent`. This is the 'absence is the signal' alarm — the hub OWNS the
    roster, so a missing member is detectable (a host can't report its own silence)."""
    last_seen_by_host = last_seen_by_host or {}
    alerts = []
    for h in expected_hosts:
        ls = last_seen_by_host.get(h)
        if _stale(ls, now_ts, sla_seconds):
            alerts.append(
                {
                    "alert": ALERT_HOST_SILENT,
                    "host": h,
                    "reason": "never_seen" if ls is None else "last_seen_exceeded_sla",
                }
            )
    return alerts


# --- content-completeness ------------------------------------------------------------------------
def sequence_gaps(shard, records: list) -> dict | None:
    """Per-shard monotonic sequence check: `records` carry int `seq`; a missing or duplicated seq means
    dropped/replayed data. Returns one alert naming the shard + the missing/duplicate seqs, or None."""
    seqs = [r.get("seq") for r in records if isinstance(r.get("seq"), int)]
    if not seqs:
        return None
    full = set(range(min(seqs), max(seqs) + 1))
    missing = sorted(full - set(seqs))
    seen, dups = set(), set()
    for s in seqs:
        (dups if s in seen else seen).add(s)
    if missing or dups:
        return {
            "alert": ALERT_SEQUENCE_GAP,
            "shard": shard,
            "missing": missing,
            "duplicates": sorted(dups),
        }
    return None


def field_completeness(record: dict, expected_fields, *, shard=None) -> dict | None:
    """Expected-field-count check: a present record missing expected fields is incomplete (catches the
    heartbeat-present-but-payload-thin case at the field granularity)."""
    missing = [f for f in expected_fields if record.get(f) in (None, "")]
    if missing:
        return {
            "alert": ALERT_FIELD_INCOMPLETE,
            "shard": shard,
            "missing_fields": missing,
        }
    return None


# --- exclusion watchdog (evidence INDEPENDENT of per-session capture, §2.5) -----------------------
def _impl_artifacts(session: dict) -> list:
    return [k for k in IMPL_ARTIFACT_KEYS if session.get(k)]


def implementation_like_but_excluded(session: dict) -> dict | None:
    """A session marked deliberative/ops that nonetheless carries implementation artifacts (edits/
    commits/PRs/tests) — its work was misclassified out of the targets (§2.5, Codex F7)."""
    wt = session.get("work_type")
    artifacts = _impl_artifacts(session)
    if wt in EXCLUDED_WORK_TYPES and artifacts:
        return {
            "alert": ALERT_IMPL_EXCLUDED,
            "session_id": session.get("session_id"),
            "work_type": wt,
            "artifacts": artifacts,
        }
    return None


def prove_coverage_alarm(session: dict) -> dict | None:
    """Code change present but NO PROVE/CI/test evidence — the change was never verified (§2.5). Uses
    independent artifact evidence, not the session's self-reported success."""
    has_code = bool(session.get("files_edited") or session.get("commits"))
    has_prove = bool(
        session.get("prove") or session.get("ci") or session.get("tests_ran")
    )
    if has_code and not has_prove:
        return {"alert": ALERT_PROVE_COVERAGE, "session_id": session.get("session_id")}
    return None


def reconciliation_gap(reported_files, filesystem_changed_files) -> dict | None:
    """Ground-truth reconciliation (§2.5): files changed ON DISK that the session never reported —
    independent of capture, so it catches gaps the capture hook itself missed."""
    gap = sorted(set(filesystem_changed_files or []) - set(reported_files or []))
    if gap:
        return {"alert": ALERT_RECONCILIATION_GAP, "unreported_changed_files": gap}
    return None


def exclusion_rate_alarm(sessions: list, *, threshold: float = 0.5) -> list:
    """High excluded-/unclassified-token share is target-disqualifying (§0.5) until resolved. Alarms
    when either rate exceeds `threshold`."""
    total = len(sessions)
    if total == 0:
        return []
    excluded = sum(1 for s in sessions if s.get("work_type") in EXCLUDED_WORK_TYPES)
    unclassified = sum(1 for s in sessions if not s.get("work_type"))
    alerts = []
    if excluded / total > threshold:
        alerts.append(
            {
                "alert": ALERT_EXCLUSION_RATE,
                "rate": round(excluded / total, 4),
                "threshold": threshold,
            }
        )
    if unclassified / total > threshold:
        alerts.append(
            {
                "alert": ALERT_UNCLASSIFIED_RATE,
                "rate": round(unclassified / total, 4),
                "threshold": threshold,
            }
        )
    return alerts


# --- aggregators ---------------------------------------------------------------------------------
def run_liveness_watchdog(
    observations: list,
    *,
    now_ts,
    expected_hosts=None,
    last_seen_by_host: dict | None = None,
    sink_path=None,
    sla_seconds: int = DEFAULT_SLA_SECONDS,
) -> list:
    """All liveness alerts across reporting sources + the roster cross-check + the exporter freshness
    check. Returns a flat list of distinct named alerts."""
    alerts = []
    for obs in observations:
        alerts.extend(classify_liveness(obs, now_ts=now_ts, sla_seconds=sla_seconds))
    if expected_hosts is not None:
        alerts.extend(
            check_roster(
                expected_hosts,
                last_seen_by_host or {},
                now_ts=now_ts,
                sla_seconds=sla_seconds,
            )
        )
    if sink_path is not None:
        ex = check_exporter(sink_path, now_ts=now_ts, sla_seconds=sla_seconds)
        if ex:
            alerts.append(ex)
    return alerts


def run_exclusion_watchdog(
    sessions: list, *, reconciliation: dict | None = None, threshold: float = 0.5
) -> list:
    """All exclusion-family alerts: rate alarms + per-session impl-excluded / prove-coverage +
    (optionally) a filesystem reconciliation gap."""
    alerts = list(exclusion_rate_alarm(sessions, threshold=threshold))
    for s in sessions:
        for detector in (implementation_like_but_excluded, prove_coverage_alarm):
            a = detector(s)
            if a:
                alerts.append(a)
    if reconciliation:
        g = reconciliation_gap(
            reconciliation.get("reported_files"),
            reconciliation.get("filesystem_changed_files"),
        )
        if g:
            alerts.append(g)
    return alerts
