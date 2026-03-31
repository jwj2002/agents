# Metrics Dashboard

The `/metrics` command visualizes agent performance from accumulated outcome data in `.claude/memory/metrics.jsonl` and `.claude/memory/failures.jsonl`.

## Usage

```bash
/metrics              # Last 30 days (default)
/metrics --week       # Last 7 days only
/metrics --month      # Last 30 days
/metrics --all        # All time
/metrics --agent MAP  # Filter by specific agent
/metrics --json       # Machine-readable JSON output
```

## Dashboard Components

The dashboard displays six panels, each calculated from the JSONL data files.

### Overall Metrics

Issues completed, first-attempt success rate, average recovery attempts, and average time to completion. Success rate is the primary KPI: `PASS / (PASS + BLOCKED)`.

### Success by Pipeline Tier

Breakdown across the three pipeline tiers used by `/orchestrate`:

| Pipeline Tier | Typical Rate | Implication |
|---------------|-------------|-------------|
| TRIVIAL | 95% | Single-file, obvious changes |
| SIMPLE | 85% | 1-3 files, clear requirements |
| COMPLEX | 43% | 4+ files, cross-cutting, ambiguous |

!!! info "Pipeline tiers vs routing tiers"
    Metrics track **pipeline tiers** (TRIVIAL, SIMPLE, COMPLEX) — the agent sequence used within `/orchestrate`. The routing tiers (MODERATE, FULLSTACK, PRIOR FAIL) determine which tasks reach `/orchestrate` in the first place. MODERATE routes map to the SIMPLE pipeline; COMPLEX and FULLSTACK route to the COMPLEX pipeline.

!!! tip "COMPLEX below 50%"
    If COMPLEX success rate drops below 50%, the recommendations engine suggests breaking COMPLEX issues into SIMPLE sub-issues before execution.

### Success by Stack

Backend-only issues succeed at higher rates than fullstack issues because fullstack introduces cross-boundary failure modes (ENUM_VALUE, API_MISMATCH).

| Stack | Typical Rate | Key Risk |
|-------|-------------|----------|
| Backend | 91% | SQLITE_COMPAT, STRUCTURE_VIOLATION |
| Frontend | 78% | COMPONENT_API |
| Fullstack | 67% | ENUM_VALUE, API_MISMATCH |

### Top Failure Causes

Ranked by frequency, showing the root cause code, percentage of all failures, and occurrence count. This panel directly feeds `/learn` analysis.

### Agent Blocking Rate

Shows which agents cause workflow blocks. PROVE blocking is expected (it is the verification gate). High blocking rates in MAP or PATCH indicate agent definition gaps.

| Agent | Healthy Rate | Action if High |
|-------|-------------|----------------|
| MAP | < 5% | Improve investigation protocol |
| PLAN | < 5% | Add acceptance criteria checks |
| CONTRACT | < 2% | Review schema completeness |
| PATCH | < 10% | Add pre-flight checklists |
| PROVE | 80%+ | Expected (verification gate) |

### Weekly Trend

Four-week rolling trend showing success rate direction. An upward trend validates that `/learn --apply` updates are working.

```
Week 1:  75%  ===============
Week 2:  81%  ================
Week 3:  85%  =================
Week 4:  91%  ==================  ^ Improving
```

## Recommendations Engine

Based on current metrics, the dashboard generates actionable guidance:

| Condition | Recommendation |
|-----------|----------------|
| ENUM_VALUE > 20% | "Add enum VALUE verification to MAP agent" |
| Fullstack < 70% | "Always use CONTRACT agent for fullstack issues" |
| COMPLEX < 50% | "Break COMPLEX issues into SIMPLE sub-issues" |
| Trend declining | "Run `/learn` to update patterns" |
| Agent blocking > 10% | "Review agent definition for gaps" |

## Agent Version Correlation

The dashboard correlates success rates with agent version numbers to detect whether updates help or hurt:

```bash
# Example output from version correlation
  15 1.0 PASS
   3 1.0 BLOCKED
   8 1.1 PASS
   0 1.1 BLOCKED    <-- v1.1 update was effective
```

This data answers the question: "Did the prevention checklist I added to PATCH v1.1 actually reduce ENUM_VALUE failures?"

## Agent Filter Mode

With `--agent`, the dashboard focuses on a single agent:

```bash
/metrics --agent MAP
```

Shows that agent's invocation count, blocks caused, average duration, issues identified (caught vs missed), common investigation patterns, and targeted recommendations.

## JSON Output

With `--json`, the dashboard outputs structured data for automation or external dashboards:

```json
{
  "period": "30d",
  "generated": "2026-03-26T10:00:00Z",
  "overall": {
    "total": 47,
    "passed": 39,
    "blocked": 8,
    "success_rate": 0.83,
    "avg_recovery": 1.2
  },
  "by_complexity": {
    "TRIVIAL": {"passed": 19, "total": 20, "rate": 0.95},
    "SIMPLE": {"passed": 17, "total": 20, "rate": 0.85},
    "COMPLEX": {"passed": 3, "total": 7, "rate": 0.43}
  },
  "by_stack": {
    "backend": {"passed": 21, "total": 23, "rate": 0.91},
    "frontend": {"passed": 14, "total": 18, "rate": 0.78},
    "fullstack": {"passed": 4, "total": 6, "rate": 0.67}
  },
  "top_failures": [
    {"cause": "ENUM_VALUE", "count": 12, "percentage": 0.26},
    {"cause": "COMPONENT_API", "count": 8, "percentage": 0.17}
  ],
  "trend": {
    "week_1": 0.75, "week_2": 0.81,
    "week_3": 0.85, "week_4": 0.91,
    "direction": "improving"
  }
}
```

!!! note "Data Requirements"
    `/metrics` requires `.claude/memory/metrics.jsonl` to exist. Run issues through `/orchestrate` to generate outcome data. The PROVE agent writes records automatically at the end of every workflow.

## Schema Reference

Metrics records follow the canonical schema from `_base.md`:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `issue` | integer | Yes | GitHub issue number |
| `date` | string | Yes | ISO date (YYYY-MM-DD) |
| `status` | string | Yes | `PASS` or `BLOCKED` |
| `complexity` | string | Yes | Pipeline tier: `TRIVIAL`, `SIMPLE`, or `COMPLEX` |
| `stack` | string | Yes | `backend`, `frontend`, or `fullstack` |
| `agents_run` | array | Yes | List of agent names that executed |
| `agent_versions` | object | Yes | Map of agent name to version string |
| `root_cause` | string | No | Root cause code (null for PASS) |
| `blocking_agent` | string | No | Agent that caused the block (null for PASS) |
| `duration_minutes` | integer | No | Total execution time |
