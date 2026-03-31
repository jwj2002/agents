# Self-Learning Loop

The self-learning loop is the mechanism that turns agent failures into systematic prevention. Every issue execution generates outcome data, which feeds pattern extraction, which updates agent definitions, which prevents future failures.

## The Complete Feedback Cycle

```
/orchestrate (issue execution)
       |
       v
PROVE records outcome
       |-- metrics.jsonl  (PASS/BLOCKED, complexity, stack)
       |-- failures.jsonl  (root cause, details, prevention)
       |
       v
/learn --apply (weekly)
       |-- Cluster failures by root_cause
       |-- Write prevention checklists into agent .md files
       |-- Bump agent versions automatically
       |-- Record to pattern-events.jsonl
       |
       v
/learn --validate (monthly)
       |-- Compare success rates before/after each pattern
       |
       v
Next /orchestrate loads updated agents
       |-- MCP failure_patterns() (preferred)
       |-- cat patterns-critical.md (fallback)
       |
       +----------- Loop repeats ------------------+
```

## Data Schemas

### metrics.jsonl

One JSON line per completed issue, written automatically by the PROVE agent:

```json
{
  "issue": 184,
  "date": "2026-02-06",
  "status": "PASS",
  "complexity": "SIMPLE",
  "stack": "fullstack",
  "agents_run": ["MAP-PLAN", "CONTRACT", "PATCH", "PROVE"],
  "agent_versions": {"map-plan": "1.0", "patch": "1.2", "prove": "1.3"},
  "root_cause": null,
  "blocking_agent": null,
  "duration_minutes": 15
}
```

**Required fields**: `issue`, `date`, `status`, `complexity` (pipeline tier: TRIVIAL/SIMPLE/COMPLEX), `stack`, `agents_run`, `agent_versions`

### failures.jsonl

Recorded only when `status` is `BLOCKED`:

```json
{
  "date": "2026-01-06",
  "issue": 156,
  "agent": "MAP-PLAN",
  "root_cause": "VERIFICATION_GAP",
  "details": "Plan deferred spec requirement without checking if spec was updated",
  "fix": "Add after_tax_contributions to DataFrame",
  "prevention": "Always validate spec version matches implementation pattern",
  "files": ["backend/projections/models.py"]
}
```

## The /learn Command

### Steps

| Step | Action | Detail |
|------|--------|--------|
| 1 | **Load outcome data** | Read `metrics.jsonl` + `failures.jsonl` from `.claude/memory/` |
| 2 | **Cluster failures** | Group by `root_cause`, count occurrences |
| 3 | **Analyze clusters** | For each cluster with 3+ occurrences, extract common files, trigger conditions, and the agent that should have caught the failure |
| 4 | **Calculate metrics** | Success rates by complexity, stack, and week |
| 5 | **Generate patterns.md** | Write prevention checklists for each high-frequency pattern |
| 6 | **Identify candidates** | Patterns with 5+ occurrences become agent update candidates |

### Usage

```bash
/learn                      # Standard analysis
/learn --since 2026-01-01   # Analyze outcomes since date
/learn --dry-run            # Preview changes without updating files
/learn --verbose            # Show detailed analysis
```

### /learn --apply

Closes the loop automatically. Instead of suggesting agent updates for manual application, `--apply` performs the full write cycle:

1. Reads the target agent file (project-local first, then global)
2. Finds the insertion point (after Pre-Flight, before Process)
3. Generates a `## Learned Prevention: {ROOT_CAUSE}` section with failure count and date
4. Shows a diff to the user for review
5. Writes changes and bumps the agent minor version (e.g., `1.0` to `1.1`)
6. Records the event to `pattern-events.jsonl`

```bash
/learn --apply              # Analyze + write prevention into agent files
/learn --apply --dry-run    # Preview what --apply would write
```

!!! tip "Idempotency"
    Before inserting, `/learn --apply` checks if a `## Learned Prevention: {ROOT_CAUSE}` section already exists. If so, it updates the count and date rather than duplicating.

### /learn --validate

Compares success rates before and after each pattern was added, using timestamps from `pattern-events.jsonl`:

```
Pattern Validation Results:
  ENUM_VALUE:      74% -> 91% (+17%)  Effective
  COMPONENT_API:   81% -> 85% (+4%)   Minor improvement
  SCOPE_CREEP:     88% -> 86% (-2%)   No improvement -- review pattern
```

Patterns that do not improve outcomes get flagged for review or removal.

### /learn --cross-project

Aggregates failure patterns across all projects. Project paths are derived from `github-accounts.md`:

```bash
/learn --cross-project      # Scan all known projects
```

Scans each project for `.claude/memory/failures.jsonl`, merges same root causes across codebases, and writes results to global `~/.claude/memory/patterns.md`. This is how project-local patterns get promoted to global prevention.

## Cadence Table

| Cadence | Action | Command |
|---------|--------|---------|
| **After every issue** | PROVE auto-records outcome | Automatic |
| **Weekly (Friday)** | Extract patterns, apply to agents | `/learn --apply` + `/metrics` |
| **Monthly** | Validate pattern effectiveness | `/learn --validate` |
| **Quarterly** | Cross-project pattern sharing | `/learn --cross-project` |
| **When success rate < 80%** | Emergency pattern review | `/learn --verbose` |

## Pattern Loading (MCP-First)

Agents prefer MCP tools over file reads for pattern data during pre-flight. MCP provides structured JSON responses via `failure_patterns()` and `agent_metrics()`. File-based loading (`patterns-critical.md`, `patterns-full.md`) serves as a fallback when MCP is unavailable.

!!! tip "See also"
    For the full MCP pattern loading diagram and configuration details, see [MCP Servers -- MCP-First Pattern Loading](../integrations/mcp-servers.md#mcp-first-pattern-loading).

## Real-World Results

From one production project (86 issues analyzed over 5 weeks):

- **Success rate**: 92% first-attempt pass
- **Dominant failure**: VERIFICATION_GAP at 63% of all failures
- **Result**: Added Mandatory Verification Protocol to MAP-PLAN agent
- **Impact**: VERIFICATION_GAP dropped from 63% to 12% after agent update

The loop works because every data point is recorded automatically by PROVE -- no manual tracking required.
