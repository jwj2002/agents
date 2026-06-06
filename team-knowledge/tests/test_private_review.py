"""Acceptance tests for issue #245 — private developer review (Pillar 2, §9.6)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import private_review as R  # noqa: E402


# MCP dead-config: 3 configured, 1 invoked → flag 2 as dead config + prune ---------------------------
def test_mcp_dead_config_detection():
    findings = R.score_tooling(
        mcp_configured=["gmail", "playwright", "vault-metrics"],
        mcp_invocations={"gmail": 5},  # only gmail used
    )
    dead = next(f for f in findings if f["kind"] == "mcp_dead_config")
    assert set(dead["dead_servers"]) == {"playwright", "vault-metrics"}
    assert dead["recommendation"] == "prune"
    assert "token-context tax" in dead["description"]


# Declared-vs-observed delta in quality -------------------------------------------------------------
def test_declared_vs_observed_quality():
    findings = R.score_quality(
        declared={"routing_discipline": True},
        telemetry={"mis_tier_events": [1, 2, 3]},  # 3 mis-tier events
    )
    f = next(f for f in findings if f["kind"] == "declared_vs_observed")
    assert "routing discipline" in f["description"]
    assert "3 mis-tier" in f["description"]
    assert f["dimension"] == R.DIM_QUALITY


# Routing mis-tier efficiency score -----------------------------------------------------------------
def test_routing_mis_tier_efficiency():
    telemetry = {
        "routing_events": [
            {"complexity": "TRIVIAL", "route": "orchestrate"} for _ in range(5)
        ]
    }
    findings = R.score_efficiency(telemetry=telemetry)
    f = next(f for f in findings if f["kind"] == "routing_mis_tier")
    assert f["over_routed"] == 5
    assert "5 over-routed" in f["description"]


# Trend direction (own-trend benchmark) -------------------------------------------------------------
def test_trend_direction():
    assert R.compute_trend(0.8, 0.6) == "improving"
    assert R.compute_trend(0.5, 0.7) == "degrading"
    assert R.compute_trend(0.7, 0.7) == "flat"
    up = R.score_trend(telemetry={"fpc_recent": 0.8, "fpc_prior": 0.6})[0]
    assert up["trend"] == "improving" and up["benchmark"] == R.BENCHMARK_OWN_TREND
    down = R.score_trend(telemetry={"fpc_recent": 0.5, "fpc_prior": 0.7})[0]
    assert down["trend"] == "degrading"


# Team pattern gap ----------------------------------------------------------------------------------
def test_team_pattern_gap():
    findings = R.score_quality(
        team_patterns=[
            {
                "area": "error-handling",
                "pattern_key": "CUSTOM_EXC_PER_MODULE",
                "state": "not-disconfirmed",
            }
        ],
        dev_patterns=[],  # dev has no entry for that key
    )
    f = next(f for f in findings if f["kind"] == "team_pattern_gap")
    assert f["pattern_key"] == "CUSTOM_EXC_PER_MODULE"
    assert f["benchmark"] == R.BENCHMARK_TEAM
    # an advisory the dev ALREADY has is not flagged
    none = R.score_quality(
        team_patterns=[
            {
                "area": "error-handling",
                "pattern_key": "CUSTOM_EXC_PER_MODULE",
                "state": "not-disconfirmed",
            }
        ],
        dev_patterns=[
            {"area": "error-handling", "pattern_key": "CUSTOM_EXC_PER_MODULE"}
        ],
    )
    assert not any(f["kind"] == "team_pattern_gap" for f in none)


# Benchmark-4 absent: no percentile/cohort language anywhere in output -------------------------------
def test_benchmark_4_not_implemented():
    report = R.private_review(
        config={"mcp_configured": ["a"]},
        telemetry={"mcp_invocations": {}},
    )
    blob = json.dumps(report) + R.render_report(report)
    # no cross-dev comparison language at all (Codex): percentile/cohort/top-performer/cross-dev
    for forbidden in ("percentile", "cohort", "top-performer", "cross-dev"):
        assert forbidden not in blob.lower()
    # the deferral is still explicitly recorded (AC: an explicit deferred note)
    assert "DEFERRED" in report["deferred"]["benchmark_4"]
    assert R.BENCHMARK_OWN_TREND in report["benchmarks_used"]


# Privacy invariant: running the review writes NOTHING to team-knowledge/ ----------------------------
def test_privacy_no_outbound_writes(tmp_path):
    tk = tmp_path / "team-knowledge"
    (tk / "patterns").mkdir(parents=True)
    (tk / "audit").mkdir(parents=True)
    before = {p for p in tk.rglob("*")}
    R.private_review(
        config={
            "mcp_configured": ["gmail", "x"],
            "declared": {"routing_discipline": True},
        },
        telemetry={"mcp_invocations": {"gmail": 1}, "mis_tier_events": [1, 2]},
        team_patterns=[{"area": "a", "pattern_key": "K", "state": "not-disconfirmed"}],
        dev_patterns=[],
    )
    after = {p for p in tk.rglob("*")}
    assert before == after  # no new files created anywhere under team-knowledge/


# Output format: exactly three top improvements, each fully described -------------------------------
def test_output_format_top3():
    report = R.private_review(
        config={
            "mcp_configured": ["gmail", "playwright", "vault-metrics"],
            "declared": {"routing_discipline": True},
        },
        telemetry={
            "mcp_invocations": {"gmail": 3},
            "mis_tier_events": [1, 2, 3],
            "routing_events": [
                {"complexity": "TRIVIAL", "route": "orchestrate"} for _ in range(5)
            ],
            "fpc_recent": 0.5,
            "fpc_prior": 0.7,  # degrading
        },
        team_patterns=[
            {
                "area": "error-handling",
                "pattern_key": "CUSTOM_EXC_PER_MODULE",
                "state": "not-disconfirmed",
            }
        ],
        dev_patterns=[],
    )
    top = report["top_improvements"]
    assert len(top) == 3
    for t in top:
        for field in ("description", "expected_impact", "benchmark", "trend"):
            assert field in t and t[field] is not None
    # highest-severity item leads (routing mis-tier, severity 5)
    assert top[0]["kind"] == "routing_mis_tier"


# On-demand purity: no scheduler/loop hooks — the entrypoint is a plain call ------------------------
def test_is_pure_function_returns_report():
    report = R.private_review(config={}, telemetry={})
    assert report["private"] is True
    assert isinstance(report["top_improvements"], list)
