"""Usage aggregator + normalization (fleet-usage-monitor §5, §8 step 5).

Reads all `telemetry/<host>/usage.jsonl` shards (cross-fleet = concatenation; the shard path encodes
`inference_host`, the record carries `work_host`) and computes the NORMALIZED efficiency metrics — the
whole point, because raw tokens-by-project is misleading:
  - $/issue, $/task-tier, and $/PR + $/file-changed (joined from git files-changed; missing → `unavailable`)
  - cache_read % and $ saved by cache (the biggest lever)
  - model mix per project + cost-by-(model×tier) (the right-sizing breakdown; the recommendation itself
    is the P2 #268 item)
  - concurrency/utilization: peak concurrent sessions, host-hours by active-count, and host burn-rate
    over the UNION of overlapping session spans (4 parallel ≠ 4× serial wall-clock, §4.4)
  - billing_type propagated to every aggregate; mixed billing types are labeled `mixed`, NEVER summed
    into one cash figure (subscription cost is notional value, not dollars, §6)

Output is structured JSON for the Tier-A report generator (#267). Pure given injected records.
"""

from __future__ import annotations

import glob
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import otel_sink as O  # noqa: E402

TIER_TRIVIAL, TIER_SIMPLE, TIER_COMPLEX, TIER_UNKNOWN = (
    "TRIVIAL",
    "SIMPLE",
    "COMPLEX",
    "unknown",
)
UNAVAILABLE = "unavailable"
_TOKEN = ("input", "output", "cache_read", "cache_creation")


def _parse_ts(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def read_shards(telemetry_dir) -> list:
    """All usage records across `telemetry/*/usage.jsonl` (cross-fleet concatenation)."""
    out = []
    for path in sorted(glob.glob(str(Path(telemetry_dir) / "*" / "usage.jsonl"))):
        for line in (
            Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()
        ):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def task_tier(files_changed) -> str:
    """File-count band: 1→TRIVIAL, 2-3→SIMPLE, 4+→COMPLEX, unknown when files_changed is absent."""
    if not isinstance(files_changed, int) or files_changed <= 0:
        return TIER_UNKNOWN
    if files_changed == 1:
        return TIER_TRIVIAL
    if files_changed <= 3:
        return TIER_SIMPLE
    return TIER_COMPLEX


def cache_pct(rec: dict) -> float:
    inp = int(rec.get("input", 0) or 0)
    cr = int(rec.get("cache_read", 0) or 0)
    denom = inp + cr
    return round(cr / denom, 4) if denom else 0.0


def cache_saved_usd(rec: dict) -> float:
    """$ saved by reading from cache vs paying full input price: cache_read_tokens × (input − cache_read price)."""
    row = O._price_for(rec.get("model", ""))
    cr = int(rec.get("cache_read", 0) or 0)
    return round(cr * (row["input"] - row["cache_read"]), 10)


def _f(v) -> float:
    """Coerce cost_usd to float; malformed values → 0.0 (never crash aggregation, Codex #266)."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _billing_label(records: list) -> str | None:
    """Single billing_type across records, else `mixed`. A MISSING billing_type counts as its own
    `unknown` kind (Codex #266 re-review) — so {metered + unknown} is `mixed`, never folded into a flat
    `metered` cash figure. Empty input → None."""
    if not records:
        return None
    kinds = {r.get("billing_type") or "unknown" for r in records}
    return next(iter(kinds)) if len(kinds) == 1 else "mixed"


def _cost(records: list) -> float:
    return round(sum(_f(r.get("cost_usd", 0)) for r in records), 10)


def _cost_by_billing(records: list) -> dict:
    """Cost split BY billing_type (subscription notional vs metered cash) — the only safe way to total
    a mixed set. `unknown` bucket for records with no billing_type."""
    out: dict = defaultdict(float)
    for r in records:
        out[r.get("billing_type") or "unknown"] += _f(r.get("cost_usd", 0))
    return {bt: round(c, 10) for bt, c in out.items()}


def _cost_group(records: list) -> dict:
    """A cost aggregate that NEVER presents a single mixed cash figure (§6): `cost_usd` is the flat
    total ONLY when billing is single-type, else None; `cost_by_billing` always carries the breakdown."""
    label = _billing_label(records)
    return {
        "cost_usd": _cost(records) if label != "mixed" else None,
        "billing_type": label,
        "cost_by_billing": _cost_by_billing(records),
    }


def by_issue(records: list) -> dict:
    groups = defaultdict(list)
    for r in records:
        groups[r.get("task")].append(r)
    return {
        task: {
            **_cost_group(rs),
            "sessions": sorted(
                {r.get("session_id") for r in rs if r.get("session_id")}
            ),
        }
        for task, rs in groups.items()
    }


def by_tier(records: list, files_by_task: dict | None = None) -> dict:
    files_by_task = files_by_task or {}
    groups = defaultdict(list)
    for r in records:
        tier = task_tier(r.get("files_changed", files_by_task.get(r.get("task"))))
        groups[tier].append(r)
    return {tier: _cost_group(rs) for tier, rs in groups.items()}


def cost_per_pr(records: list, files_by_task: dict) -> dict:
    """$/PR and $/file-changed per task; `unavailable` (not 0) when git files data is missing."""
    out = {}
    groups = defaultdict(list)
    for r in records:
        groups[r.get("task")].append(r)
    for task, rs in groups.items():
        grp = _cost_group(rs)
        cost = grp["cost_usd"]  # None when billing is mixed
        nf = files_by_task.get(task)
        if cost is None:  # mixed billing → no single cash figure to divide (§6)
            per_pr = per_file = "mixed"
        elif nf is None:
            per_pr = per_file = UNAVAILABLE
        else:
            per_pr = cost
            per_file = round(cost / nf, 10) if nf else UNAVAILABLE
        out[task] = {
            **grp,
            "cost_per_pr": per_pr,
            "files_changed": nf if nf is not None else UNAVAILABLE,
            "cost_per_file_changed": per_file,
        }
    return out


def model_mix(records: list) -> dict:
    """Per project, cost share by model. Each model leaf carries its own billing_type (a model maps to
    one provider/account), so no mixed cash sum is hidden (Codex #266)."""
    groups: dict = defaultdict(lambda: defaultdict(list))
    for r in records:
        groups[r.get("project")][r.get("model")].append(r)
    return {
        proj: {m: _cost_group(rs) for m, rs in models.items()}
        for proj, models in groups.items()
    }


def cost_by_model_tier(records: list, files_by_task: dict | None = None) -> dict:
    """cost-by-(project × tier × model) — the right-sizing breakdown (recommendation is P2 #268).
    Each leaf is a billing-aware cost group (no silent mixed cash sum)."""
    files_by_task = files_by_task or {}
    groups: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in records:
        tier = task_tier(r.get("files_changed", files_by_task.get(r.get("task"))))
        groups[r.get("project")][tier][r.get("model")].append(r)
    return {
        p: {t: {m: _cost_group(rs) for m, rs in ms.items()} for t, ms in tiers.items()}
        for p, tiers in groups.items()
    }


def cache_by_project(records: list) -> dict:
    out: dict = defaultdict(list)
    for r in records:
        out[r.get("project")].append(r)
    res = {}
    for proj, rs in out.items():
        inp = sum(int(r.get("input", 0) or 0) for r in rs)
        cr = sum(int(r.get("cache_read", 0) or 0) for r in rs)
        # cache savings is a $ figure too → split by billing; flat only when single-type (Codex #266)
        saved_by_billing: dict = defaultdict(float)
        for r in rs:
            saved_by_billing[r.get("billing_type") or "unknown"] += cache_saved_usd(r)
        label = _billing_label(rs)
        res[proj] = {
            **_cost_group(rs),
            "cache_pct": round(cr / (inp + cr), 4) if (inp + cr) else 0.0,
            "cache_saved_usd": (
                round(sum(saved_by_billing.values()), 10) if label != "mixed" else None
            ),
            "cache_saved_by_billing": {
                bt: round(v, 10) for bt, v in saved_by_billing.items()
            },
        }
    return res


def _merge_intervals(spans: list) -> float:
    """Total duration (seconds) of the UNION of [start,end] spans — overlaps counted once."""
    spans = sorted(
        (s, e) for s, e in spans if s is not None and e is not None and e >= s
    )
    if not spans:
        return 0.0
    total = 0.0
    cur_s, cur_e = spans[0]
    for s, e in spans[1:]:
        if s <= cur_e:
            cur_e = max(cur_e, e)
        else:
            total += cur_e - cur_s
            cur_s, cur_e = s, e
    total += cur_e - cur_s
    return total


def concurrency(records: list) -> dict:
    """Per inference_host: peak concurrent sessions, host-hours by active-session-count, and burn-rate
    ($/wall-clock-hour) over the UNION of overlapping session spans (NOT sum of serial wall-clock)."""
    by_host: dict = defaultdict(
        lambda: defaultdict(list)
    )  # host -> session -> [records]
    for r in records:
        by_host[r.get("inference_host")][r.get("session_id")].append(r)
    out = {}
    for host, sessions in by_host.items():
        spans = []
        events = []  # (ts, +1/-1) for the sweep
        host_records = [r for rs in sessions.values() for r in rs]
        for rs in sessions.values():
            ts = [t for t in (_parse_ts(r.get("ts")) for r in rs) if t is not None]
            if ts:
                s, e = min(ts), max(ts)
                spans.append((s, e))
                events.append((s, 1))
                events.append((e, -1))
        # peak concurrency + host-hours by active count via a sweep
        events.sort()
        active = peak = 0
        hours_by_count: dict = defaultdict(float)
        prev_t = None
        for t, delta in events:
            if prev_t is not None and active > 0:
                hours_by_count[active] += (t - prev_t) / 3600.0
            active += delta
            peak = max(peak, active)
            prev_t = t
        union_hours = _merge_intervals(spans) / 3600.0
        grp = _cost_group(host_records)  # cost_usd None when billing is mixed (§6)
        flat = grp["cost_usd"]
        if flat is None:
            burn = "mixed"
        elif union_hours:
            burn = round(flat / union_hours, 4)
        else:
            burn = UNAVAILABLE
        out[host] = {
            "peak_concurrent_sessions": peak,
            **grp,
            "active_wall_clock_hours": round(union_hours, 4),
            "burn_rate_usd_per_hour": burn,
            "host_hours_by_active_count": {
                str(k): round(v, 4) for k, v in sorted(hours_by_count.items())
            },
        }
    return out


def git_files_by_task(repo_dir) -> dict:
    """Best-effort {`issue:N`: files_changed} from squash-merge commits whose subject ends `(#N)`.
    Returns {} on any git error (the aggregator then marks $/PR `unavailable`)."""
    out: dict = {}
    try:
        log = subprocess.run(
            ["git", "-C", str(repo_dir), "log", "--pretty=%H\t%s", "-n", "500"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return out
    import re

    for line in log.splitlines():
        sha, _, subj = line.partition("\t")
        m = re.search(r"\(#(\d+)\)\s*$", subj)
        if not m:
            continue
        try:
            files = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo_dir),
                    "show",
                    "--stat",
                    "--name-only",
                    "--format=",
                    sha,
                ],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        except (subprocess.CalledProcessError, OSError):
            continue
        n = len([line_ for line_ in files.splitlines() if line_.strip()])
        out.setdefault(f"issue:{m.group(1)}", n)
    return out


def aggregate(records: list, *, files_by_task: dict | None = None) -> dict:
    """The full structured aggregation (consumed by the #267 report)."""
    files_by_task = files_by_task or {}
    return {
        "schema_version": 1,
        "totals": {**_cost_group(records), "records": len(records)},
        "by_issue": by_issue(records),
        "by_tier": by_tier(records, files_by_task),
        "cost_per_pr": cost_per_pr(records, files_by_task),
        "model_mix": model_mix(records),
        "cost_by_model_tier": cost_by_model_tier(records, files_by_task),
        "cache_by_project": cache_by_project(records),
        "concurrency": concurrency(records),
    }
