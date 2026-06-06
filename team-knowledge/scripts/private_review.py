"""Private developer review (team-knowledge-mvp-v1 Pillar 2, §9.6) — Owner lane: scratch.

A LOCAL, on-demand audit of a dev's OWN workflow/config/behavior. It scores three dimensions
(Quality / Efficiency / Tooling-cost & utilization) against three benchmarks — (1) team patterns,
(2) the dev's own trend, (3) external best-practice — and returns a prioritized TOP-3 improvement list
with expected impact + trend direction.

PRIVACY INVARIANT (the whole point of Pillar 2): runs locally, treats shared artifacts as READ-ONLY
benchmarks, and emits NOTHING outside the dev's machine — `private_review` is pure (returns a dict,
writes no files). Benchmark 4 (top-performer comparison) is DEFERRED to the public tier: k-anonymity is
un-private at 4 devs (§6.2). No cross-dev/percentile/cohort language is ever produced.

Host-agnostic: takes injected config + telemetry + the team's published patterns. The `/private-review`
command is a thin wrapper around `private_review`; tests target the functions directly.
"""

from __future__ import annotations

# Benchmarks (§Pillar 2) — exactly these three for team v1.
BENCHMARK_TEAM = "team_patterns"
BENCHMARK_OWN_TREND = "own_trend"
BENCHMARK_EXTERNAL = "external_best_practice"

# Dimensions.
DIM_QUALITY = "quality"
DIM_EFFICIENCY = "efficiency"
DIM_TOOLING = "tooling"

# Team-pattern states that constitute an advisory worth adopting (assembler #244 emits these).
_ADVISORY_STATES = {"not-disconfirmed", "published-advisory", "accepted-local"}
# Routing tiers considered "heavy" — using them for a light task is an over-route (mis-tier).
_HEAVY_ROUTES = {"orchestrate", "complex"}
_LIGHT_COMPLEXITY = {"TRIVIAL", "SIMPLE"}

# Benchmark 4 deferral — phrased WITHOUT percentile/cohort language (§6.2).
BENCHMARK_4_DEFERRED = "top-performer comparison DEFERRED to public tier — k-anonymity is un-private at 4 devs (§6.2)"


def _finding(
    dimension,
    kind,
    description,
    *,
    expected_impact,
    benchmark,
    trend="n/a",
    severity=1,
    **extra,
):
    return {
        "dimension": dimension,
        "kind": kind,
        "description": description,
        "expected_impact": expected_impact,
        "benchmark": benchmark,
        "trend": trend,
        "severity": severity,
        **extra,
    }


def compute_trend(recent: float, prior: float) -> str:
    """Own-trend direction between two telemetry windows (last-30d vs prior-30d)."""
    if recent > prior:
        return "improving"
    if recent < prior:
        return "degrading"
    return "flat"


def score_tooling(
    *, mcp_configured, mcp_invocations, tool_invocations=None, env_overhead=None
) -> list:
    """Tooling cost & utilization (the §9.6 dimension): dead MCP config (connected but never invoked =
    a token-context tax), per-tool invocation counts, and environment-setup overhead → prune/pin/
    pre-provision recommendations."""
    findings = []
    invocations = mcp_invocations or {}
    dead = sorted(s for s in (mcp_configured or []) if invocations.get(s, 0) == 0)
    if dead:
        findings.append(
            _finding(
                DIM_TOOLING,
                "mcp_dead_config",
                f"{len(dead)} MCP server(s) connected but never invoked (dead config + token-context tax): "
                f"{', '.join(dead)}",
                expected_impact="prune to recover context budget + remove dead config",
                benchmark=BENCHMARK_EXTERNAL,
                severity=len(dead) + 1,
                recommendation="prune",
                dead_servers=dead,
            )
        )
    if env_overhead and (
        env_overhead.get("setup_tokens", 0) or env_overhead.get("events", 0)
    ):
        findings.append(
            _finding(
                DIM_TOOLING,
                "env_setup_overhead",
                f"environment-setup overhead: {env_overhead.get('events', 0)} mid-task installs/cold starts, "
                f"~{env_overhead.get('setup_tokens', 0)} tokens",
                expected_impact="pre-provision base env / pin deps to cut setup tax",
                benchmark=BENCHMARK_EXTERNAL,
                severity=1,
                recommendation="pre-provision",
            )
        )
    if tool_invocations:
        findings.append(
            _finding(
                DIM_TOOLING,
                "tool_utilization",
                f"per-tool invocation counts: {dict(sorted(tool_invocations.items()))}",
                expected_impact="informational — confirm high-cost tools earn their keep",
                benchmark=BENCHMARK_EXTERNAL,
                severity=0,
            )
        )
    return findings


def score_quality(
    *, declared=None, telemetry=None, team_patterns=None, dev_patterns=None
) -> list:
    """Quality: declared-vs-observed delta, gaps vs team patterns, guard presence, first-pass
    correctness, prompt anti-patterns."""
    findings = []
    declared = declared or {}
    telemetry = telemetry or {}
    # declared-vs-observed: a CLAUDE.md claim contradicted by telemetry
    mis_tier = telemetry.get("mis_tier_events", []) or []
    if declared.get("routing_discipline") and mis_tier:
        findings.append(
            _finding(
                DIM_QUALITY,
                "declared_vs_observed",
                f"CLAUDE.md claims routing discipline, but {len(mis_tier)} mis-tier events observed",
                expected_impact="align config with behavior or fix routing",
                benchmark=BENCHMARK_EXTERNAL,
                severity=len(mis_tier),
            )
        )
    # gaps vs team patterns: an advisory team key the dev has no entry for
    dev_keys = {(p.get("area"), p.get("pattern_key")) for p in (dev_patterns or [])}
    for tp in team_patterns or []:
        if tp.get("state") in _ADVISORY_STATES:
            key = (tp.get("area"), tp.get("pattern_key"))
            if key not in dev_keys:
                findings.append(
                    _finding(
                        DIM_QUALITY,
                        "team_pattern_gap",
                        f"team advisory {tp.get('pattern_key')} in {tp.get('area')} "
                        f"({tp.get('state')}) — no entry for this dev",
                        expected_impact="adopt the team pattern or record why not",
                        benchmark=BENCHMARK_TEAM,
                        severity=2,
                        area=tp.get("area"),
                        pattern_key=tp.get("pattern_key"),
                    )
                )
    # guard presence
    if telemetry.get("guards_absent"):
        findings.append(
            _finding(
                DIM_QUALITY,
                "guard_absent",
                f"failure guards absent for: {telemetry['guards_absent']}",
                expected_impact="add guards to catch known failure modes",
                benchmark=BENCHMARK_EXTERNAL,
                severity=2,
            )
        )
    return findings


def score_efficiency(*, telemetry=None) -> list:
    """Efficiency: routing mis-tiers, token/ceremony bloat, rework/bounce, Codex over/under-trigger,
    cycle time."""
    findings = []
    telemetry = telemetry or {}
    over = [
        r
        for r in (telemetry.get("routing_events", []) or [])
        if str(r.get("complexity", "")).upper() in _LIGHT_COMPLEXITY
        and str(r.get("route", "")).lower() in _HEAVY_ROUTES
    ]
    if over:
        findings.append(
            _finding(
                DIM_EFFICIENCY,
                "routing_mis_tier",
                f"routing mis-tier: {len(over)} over-routed (light task via a heavy route)",
                expected_impact="right-size the model/route tier to cut token + cycle cost",
                benchmark=BENCHMARK_EXTERNAL,
                severity=len(over),
                over_routed=len(over),
            )
        )
    rework = telemetry.get("rework_rate")
    if rework is not None and rework > 0.2:
        findings.append(
            _finding(
                DIM_EFFICIENCY,
                "rework_rate",
                f"rework/bounce rate {rework:.0%} above the 20% guideline",
                expected_impact="reduce rework with earlier verification",
                benchmark=BENCHMARK_EXTERNAL,
                severity=2,
            )
        )
    return findings


def score_trend(*, telemetry=None) -> list:
    """Own-trend benchmark: surface the direction of first-pass correctness across two windows."""
    telemetry = telemetry or {}
    if "fpc_recent" in telemetry and "fpc_prior" in telemetry:
        direction = compute_trend(telemetry["fpc_recent"], telemetry["fpc_prior"])
        sev = 3 if direction == "degrading" else 1
        return [
            _finding(
                DIM_QUALITY,
                "own_trend_fpc",
                f"first-pass correctness {direction} ({telemetry['fpc_prior']:.0%} → {telemetry['fpc_recent']:.0%})",
                expected_impact="sustain improvement"
                if direction != "degrading"
                else "investigate regression",
                benchmark=BENCHMARK_OWN_TREND,
                trend=direction,
                severity=sev,
            )
        ]
    return []


def private_review(
    *,
    config=None,
    telemetry=None,
    team_patterns=None,
    dev_patterns=None,
    top_n: int = 3,
) -> dict:
    """The private review. PURE: returns a report dict, writes nothing (the privacy invariant). Scores
    all three dimensions + own trend, then ranks the top-N improvements. Benchmark 4 is recorded as a
    DEFERRED note, never computed (no cross-dev/percentile/cohort comparison)."""
    config = config or {}
    findings = []
    findings += score_quality(
        declared=config.get("declared"),
        telemetry=telemetry,
        team_patterns=team_patterns,
        dev_patterns=dev_patterns,
    )
    findings += score_efficiency(telemetry=telemetry)
    findings += score_tooling(
        mcp_configured=config.get("mcp_configured"),
        mcp_invocations=(telemetry or {}).get("mcp_invocations"),
        tool_invocations=(telemetry or {}).get("tool_invocations"),
        env_overhead=(telemetry or {}).get("env_overhead"),
    )
    findings += score_trend(telemetry=telemetry)

    # Top-N by severity (stable for ties). Only actionable findings (severity>0) compete.
    actionable = [f for f in findings if f.get("severity", 0) > 0]
    ranked = sorted(actionable, key=lambda f: f["severity"], reverse=True)
    top = [
        {
            "description": f["description"],
            "expected_impact": f["expected_impact"],
            "benchmark": f["benchmark"],
            "trend": f["trend"],
            "dimension": f["dimension"],
            "kind": f["kind"],
        }
        for f in ranked[:top_n]
    ]
    return {
        "private": True,
        "top_improvements": top,
        "dimensions": {
            DIM_QUALITY: [f for f in findings if f["dimension"] == DIM_QUALITY],
            DIM_EFFICIENCY: [f for f in findings if f["dimension"] == DIM_EFFICIENCY],
            DIM_TOOLING: [f for f in findings if f["dimension"] == DIM_TOOLING],
        },
        "benchmarks_used": [BENCHMARK_TEAM, BENCHMARK_OWN_TREND, BENCHMARK_EXTERNAL],
        "deferred": {"benchmark_4": BENCHMARK_4_DEFERRED},
    }


def render_report(report: dict) -> str:
    """Local human-readable view. Never written off-machine by this module."""
    lines = ["# Private review (LOCAL — not shared)"]
    for i, t in enumerate(report.get("top_improvements", []), 1):
        lines.append(f"{i}. [{t['dimension']}] {t['description']}")
        lines.append(
            f"   impact: {t['expected_impact']} | benchmark: {t['benchmark']} | trend: {t['trend']}"
        )
    lines.append(f"# benchmark 4: {report['deferred']['benchmark_4']}")
    return "\n".join(lines)
