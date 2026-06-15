#!/usr/bin/env python3
"""Weekly cost-telemetry report — build locally, then email per machine config.

Run by `com.cost-telemetry-report-weekly` (Mondays). It ALWAYS writes a local
report to ~/.claude/cost-reports/ (the archive/fallback); email delivery is on
top of that and only happens when ~/.claude/cost-telemetry/email.json is
configured + enabled (see usage_email). Never blocks; logs + exits 0.

Pipeline reuses the existing modules:
  usage_aggregator.read_shards + aggregate  ->  usage_report.write_report (html+md)
  ->  usage_email.send_weekly (transport selected by the machine-local config)
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import quality_kpis as KPI  # noqa: E402
import usage_aggregator as A  # noqa: E402
import usage_email as E  # noqa: E402
import usage_report as R  # noqa: E402

TELEMETRY_DIR = (
    Path.home() / ".claude" / "telemetry"
)  # read_shards globs */usage.jsonl under here
REPORTS_DIR = Path.home() / ".claude" / "cost-reports"
EMAIL_STATE = (
    Path.home() / ".claude" / "cost-telemetry" / "email-state.json"
)  # email-only state (no collector races)


def _host() -> str:
    try:
        sys.path.insert(0, str(Path.home() / "agents" / "lib"))
        from project_resolver import get_host_name

        return get_host_name()
    except Exception:
        return socket.gethostname().split(".")[0] or "unknown"


def _load_state() -> dict:
    try:
        return json.loads(EMAIL_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    EMAIL_STATE.parent.mkdir(parents=True, exist_ok=True)
    EMAIL_STATE.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _recall_correlation(metrics_path: Path) -> str:
    """Compute first-pass rate split by recall.fired from metrics.jsonl.

    Returns a markdown subsection when each cohort has N >= 3 qualifying
    records (records with both a recall.fired bool AND a first_pass_correct
    bool). Returns "" when the file is missing, unreadable, or either cohort
    is below the minimum threshold.

    Fail-open: any I/O or parse error returns "". BLE001 exempt — scripts/.
    """
    try:
        if not metrics_path.exists():
            return ""
        records = []
        for line in metrics_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue

        fired_pass = fired_total = 0
        not_fired_pass = not_fired_total = 0
        for rec in records:
            recall = rec.get("recall")
            if not isinstance(recall, dict):
                continue  # pre-L2 record — exclude from split
            fired = recall.get("fired")
            if not isinstance(fired, bool):
                continue
            fpc = rec.get("first_pass_correct")
            if not isinstance(fpc, bool):
                continue
            if fired:
                fired_total += 1
                if fpc:
                    fired_pass += 1
            else:
                not_fired_total += 1
                if fpc:
                    not_fired_pass += 1

        min_n = 3
        if fired_total < min_n or not_fired_total < min_n:
            return ""

        fired_rate = f"{fired_pass / fired_total:.0%}"
        not_fired_rate = f"{not_fired_pass / not_fired_total:.0%}"

        lines = [
            "### Outcome correlation (from metrics.jsonl)",
            "",
            "| cohort | issues | first-pass rate |",
            "|--------|--------|-----------------|",
            f"| recall fired | {fired_total} | {fired_rate} |",
            f"| recall not fired | {not_fired_total} | {not_fired_rate} |",
        ]
        return "\n".join(lines)
    except Exception:
        return ""  # fail-open — BLE001 exempt for scripts/


def format_recall_section(
    bin_path: Path | None = None,
    metrics_path: Path | None = None,
) -> str:
    """Shell out to coding-memory recall-report --json --days 7.

    Fail-open: returns a one-line "data unavailable" notice on any error
    so the weekly report still sends when jns is unreachable or the CLI
    is absent. Broad catch is intentional (BLE001 exempted for scripts/).
    Uses the absolute bin path so launchd's restricted PATH is not a problem.

    Args:
        bin_path: Path to the coding-memory binary. Defaults to
            ~/agents/bin/coding-memory.
        metrics_path: Optional path to metrics.jsonl. When supplied, an
            "Outcome correlation" subsection is appended showing first-pass
            rate split by recall.fired (issue #456). Omitted when None or
            when either cohort has fewer than 3 qualifying records.
    """
    if bin_path is None:
        bin_path = Path.home() / "agents" / "bin" / "coding-memory"
    stub = "## Recall (last 7 days)\n\n_data unavailable this week_"
    try:
        proc = subprocess.run(
            [str(bin_path), "recall-report", "--json", "--days", "7"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return stub
        data = json.loads(proc.stdout)
        n_total = int(data.get("n_total") or 0)
        n_push = int(data.get("n_push") or 0)
        n_pull = int(data.get("n_pull") or 0)
        n_inj = int(data.get("n_injected_total") or 0)
        n_ret = int(data.get("n_returned_total") or 0)
        p50_raw = data.get("p50_latency_ms")
        p50 = int(p50_raw) if p50_raw is not None else None
        top_facts = (
            data.get("top_facts") if isinstance(data.get("top_facts"), list) else []
        )
        days = int(data.get("days") or 7)
    except Exception:
        return stub

    eff_str = f"{n_inj / n_ret:.0%}" if n_ret else "n/a"
    p50_str = f"{p50} ms" if p50 is not None else "n/a"

    lines = [
        f"## Recall (last {days} days)",
        "",
        "| metric | value |",
        "|--------|-------|",
        f"| total queries | {n_total} |",
        f"| push (prompt inject) | {n_push} |",
        f"| pull (interactive) | {n_pull} |",
        f"| gate efficiency (injected/returned) | {eff_str} |",
        f"| p50 latency | {p50_str} |",
    ]
    try:
        if top_facts:
            lines += ["", "**Top surfaced facts:**", ""]
            for f in top_facts:
                lines.append(
                    f"- [{f.get('ns', '?')}] {f.get('name', '?')} ×{int(f.get('count') or 0)}"
                )
    except Exception:
        pass  # malformed top_facts entry — omit the section, report still sends

    if metrics_path is not None:
        try:
            corr = _recall_correlation(metrics_path)
            if corr:
                lines.append("")
                lines.extend(corr.splitlines())
        except Exception:
            pass  # fail-open — BLE001 exempt for scripts/

    return "\n".join(lines)


def main() -> int:
    now = datetime.now(timezone.utc)
    host = _host()
    iso = now.isocalendar()
    wk = f"{iso[0]}-W{iso[1]:02d}"

    records = A.read_shards(TELEMETRY_DIR)
    agg = A.aggregate(records)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    html_path = REPORTS_DIR / f"cost-report-{host}-{wk}.html"
    R.write_report(agg, html_path, records=records)  # writes .html + .md
    md = html_path.with_suffix(".md").read_text(
        encoding="utf-8"
    )  # email body = the local .md
    kpi_section = KPI.format_kpi_section(
        KPI.compute_kpis(
            metrics_path=Path.home() / ".claude" / "memory" / "metrics.jsonl",
            prove_log_path=Path.home() / ".claude" / "memory" / "prove-log.jsonl",
            overrides_paths=[
                Path.home() / ".agents" / "outputs" / "prove-overrides.jsonl"
            ],
        )
    )
    if kpi_section:
        md = md + "\n\n" + kpi_section
    recall_section = format_recall_section(
        metrics_path=Path.home() / ".claude" / "memory" / "metrics.jsonl"
    )
    if recall_section:
        md = md + "\n\n" + recall_section
    print(f"[{now.isoformat()}] local report: {html_path} ({len(records)} records)")

    state = _load_state()
    code, new_state = E.send_weekly(
        md_summary=md,
        html_path=str(html_path),
        state=state,
        host=host,
        now=now,
    )
    if code == E.SENT_OR_SKIP and new_state != state:
        try:
            _save_state(new_state)
        except OSError as e:
            print(f"[{now.isoformat()}] warn: could not persist email state: {e}")
    status = {
        E.SENT_OR_SKIP: "emailed (or already sent this week)",
        E.DISABLED: "email disabled — local report only",
        E.SEND_FAILED: "email FAILED (local report written)",
    }.get(code, str(code))
    print(f"[{now.isoformat()}] email: {status} (exit {code})")
    return 0  # never block the cadence


if __name__ == "__main__":
    raise SystemExit(main())
