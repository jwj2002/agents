---
type: base-agent
version: 3.0
purpose: Shared behaviors inherited by all agents
---

# Base Agent Behaviors

All agents inherit these behaviors. Read this FIRST before your agent-specific instructions.

---

## 1. Pre-Flight: Load Learned Patterns (TIERED)

**BEFORE investigating or planning**, load accumulated knowledge:

### Preferred: MCP Tools (if vault-metrics MCP available)

Use MCP tools for structured, up-to-date pattern data:

```
# Get failure patterns (structured, with frequency and recent examples)
failure_patterns()

# Get metrics overview (success rates by complexity/stack)
agent_metrics(period="30d")
```

**Why MCP**: Returns parsed JSON with counts, percentages, and recent examples — more actionable than raw markdown files.

### Fallback: File-Based Loading

If MCP tools are not available (tool call fails or returns error), fall back to files:

#### Always Load (Critical Patterns ~50 lines)
```bash
cat .claude/memory/patterns-critical.md
```

#### Load If Needed (Full Patterns ~660 lines)
Only load `.claude/memory/patterns-full.md` when:
- Issue is COMPLEX classification
- Issue involves pattern not in critical file
- You need detailed prevention checklists

**Apply relevant patterns** to your current task. Critical patterns cover 89% of failures.

---

## 2. Pre-Flight: Check Similar Past Work

```bash
# Find similar past artifacts (adjust keywords)
grep -l "KEYWORD" .agents/outputs/*.md 2>/dev/null | head -3
```

If found, read the artifact to learn from past approaches. Note what worked and what caused issues.

---

## 3. Efficiency Rules

### Reference, Don't Re-Quote
```markdown
# ❌ BAD: Re-quoting 50 lines of code
Here's the existing implementation:
[50 lines of code]

# ✅ GOOD: Reference with line numbers
See `backend/accounts/services.py:45-67` for existing pattern.
```

### Single Source of Truth
- Acceptance criteria: Define ONCE in MAP-PLAN or PLAN
- Other agents reference: "See MAP-PLAN acceptance criteria"
- Never duplicate lists across artifacts

### Target Lengths
| Agent | Target Lines | Max Lines |
|-------|--------------|-----------|
| MAP | 150 | 200 |
| MAP-PLAN | 400 | 500 |
| PLAN | 400 | 500 |
| TEST-PLANNER | 250 | 350 |
| CONTRACT | 200 | 300 |
| PLAN-CHECK | 80 | 120 |
| PATCH | 300 | 400 |
| PROVE | 250 | 350 |

### Size Compliance (MANDATORY)

Before writing your final artifact, check line count:

```bash
# Self-check before submission
wc -l < .agents/outputs/$ARTIFACT_NAME
```

| Outcome | Action |
|---------|--------|
| Under target | Submit |
| Between target and max | Submit with note: "Artifact N lines (target: M)" |
| Over max | **STOP**. Compress before submitting |

**Compression checklist** (in priority order):
1. Replace code quotes with line references (`See services.py:45-67`)
2. Remove re-stated acceptance criteria (reference MAP-PLAN)
3. Consolidate duplicate sections
4. Remove appendices and "Future Enhancements"
5. Use exceptions-only reporting (document failures, not successes)

---

## 4. Artifact Naming

**Pattern**: `{agent}-{issue}-{mmddyy}.md`

```bash
# Set these variables at start of run
ISSUE_NUMBER=184
RUN_DATE=$(date +%m%d%y)
ARTIFACT_NAME="{agent}-${ISSUE_NUMBER}-${RUN_DATE}.md"
```

**Output directory**: `.agents/outputs/`

---

## 5. Common Verification Commands

### Backend
```bash
cd backend && ruff check . && pytest -q
```

### Frontend  
```bash
cd frontend && npm run lint && npm run build
```

### Verify Scope (no unplanned changes)
```bash
git diff --name-only HEAD
# Should only show files in PLAN
```

---

## 6. Constraint Enforcement

**Before ANY file operation**, verify:

```bash
# Check constraints file
cat .claude/rules.md | head -50
```

**Forbidden actions** (always blocked):
- Creating top-level directories
- Moving `backend/`, `frontend/`, `.claude/`
- Creating `backend/src/`
- Modifying files on `main` branch
- **Pushing to or committing on `production` branch** (unless user explicitly requests)

---

## 7. AGENT_RETURN Directive

Every agent MUST end output with:

```markdown
AGENT_RETURN: {artifact-filename}
```

Example:
```markdown
AGENT_RETURN: map-184-010325.md
```

This signals successful completion to the orchestrator.

---

## 8. High-Frequency Failure Prevention

**Canonical definitions**: See `~/.claude/rules/core-patterns.md` (auto-loaded).

Use these verification commands when patterns apply:

```bash
# ENUM_VALUE: verify VALUES not names
grep -A 10 "class.*Enum" backend/backend/*/enums.py

# COMPONENT_API: extract PropTypes/return type
grep -A 20 "PropTypes" frontend/src/components/path/Component.jsx

# MULTI_MODEL: map fields to owning models
grep -rn "class.*Model" backend/backend/*/models.py
```

---

## 9. Artifact Validation (MANDATORY)

Before starting work, verify predecessor artifacts exist. **STOP and report** if required artifacts are missing.

| Agent | Required Predecessor | Validation |
|-------|---------------------|------------|
| MAP | None (first agent) | — |
| MAP-PLAN | None (first agent) | — |
| PLAN | MAP artifact | `ls .agents/outputs/map-{issue}-*.md` |
| TEST-PLANNER | MAP or MAP-PLAN artifact | `ls .agents/outputs/map*-{issue}-*.md` |
| CONTRACT | PLAN or MAP-PLAN artifact | `ls .agents/outputs/{plan,map-plan}-{issue}-*.md` |
| PLAN-CHECK | PLAN or MAP-PLAN artifact. CONTRACT if fullstack | `ls .agents/outputs/{plan,map-plan}-{issue}-*.md` |
| PATCH | PLAN or MAP-PLAN artifact. CONTRACT if fullstack. PLAN-CHECK | `ls .agents/outputs/{plan,map-plan}-{issue}-*.md` |
| PROVE | PATCH artifact | `ls .agents/outputs/patch-{issue}-*.md` |

**If missing**: `STOP. Report: "BLOCKED: Required artifact {name} not found for issue #{issue}"`

---

## 10. Root Cause Classification (Canonical Enum)

When recording failures, use ONLY these root cause codes:

| Code | Description | Typical Agent |
|------|-------------|---------------|
| `ENUM_VALUE` | Used enum NAME instead of VALUE | PATCH, PROVE |
| `COMPONENT_API` | Wrong props/hook usage | PATCH |
| `MULTI_MODEL` | Forgot model relationship | PATCH |
| `API_MISMATCH` | Frontend/backend contract violation | PATCH, PROVE |
| `ACCESS_CONTROL` | Missing/wrong permission check | PATCH |
| `MISSING_TEST` | Untested code path | PROVE |
| `SQLITE_COMPAT` | PostgreSQL-only feature used | PATCH |
| `STRUCTURE_VIOLATION` | Violated rules.md constraints | PATCH |
| `SCOPE_CREEP` | Beyond issue scope | MAP-PLAN, PATCH |
| `VERIFICATION_GAP` | Assumptions not verified by reading code | MAP-PLAN |
| `OTHER` | Document specifics in `details` field | Any |

---

## 11. Canonical metrics.jsonl Schema

Every metrics record MUST include these required fields:

```json
{
  "issue": 184,
  "date": "2026-02-06",
  "status": "PASS | BLOCKED",
  "complexity": "TRIVIAL | SIMPLE | COMPLEX",
  "stack": "backend | frontend | fullstack",
  "agents_run": ["MAP-PLAN", "PATCH", "PROVE"],
  "agent_versions": {"map-plan": "1.0", "patch": "1.0", "prove": "1.0"},
  "root_cause": null,
  "blocking_agent": null,
  "duration_minutes": 15
}
```

**Optional fields**: `recovery_attempts`, `notes`

---

## 12. Canonical failures.jsonl Schema

Every failure record MUST include:

```json
{
  "issue": 184,
  "date": "2026-02-06",
  "agent": "PATCH",
  "root_cause": "ENUM_VALUE",
  "details": "Frontend used CO_OWNER instead of CO-OWNER",
  "fix": "Changed string literal to match backend enum VALUE",
  "prevention": "MAP should document enum VALUES explicitly",
  "files": ["frontend/src/components/MemberForm.jsx"]
}
```

**Optional fields**: `severity`, `recovery_minutes`

---

## 13. Outcome Recording (PROVE Agent Only)

After verification, record outcome using the canonical schemas above:

### If PASS
```bash
echo '{"issue":'$ISSUE_NUMBER',"date":"'$(date +%Y-%m-%d)'","status":"PASS","complexity":"'$COMPLEXITY'","stack":"'$STACK'","agents_run":['$AGENTS'],"agent_versions":{'$VERSIONS'},"root_cause":null,"blocking_agent":null}' >> .claude/memory/metrics.jsonl
```

### If BLOCKED
```bash
# Record failure (canonical schema)
echo '{"issue":'$ISSUE_NUMBER',"date":"'$(date +%Y-%m-%d)'","agent":"PATCH","root_cause":"'$CAUSE'","details":"'$DETAILS'","fix":"'$FIX'","prevention":"'$PREVENTION'","files":['$FILES']}' >> .claude/memory/failures.jsonl

# Record metric (canonical schema)
echo '{"issue":'$ISSUE_NUMBER',"date":"'$(date +%Y-%m-%d)'","status":"BLOCKED","complexity":"'$COMPLEXITY'","stack":"'$STACK'","agents_run":['$AGENTS'],"agent_versions":{'$VERSIONS'},"root_cause":"'$CAUSE'","blocking_agent":"PROVE"}' >> .claude/memory/metrics.jsonl
```

---

## 14. Agent Versioning

All agents include `version: X.Y` in their YAML frontmatter.

**Convention**:
- **Minor** (1.0 → 1.1): Pattern additions, wording changes
- **Major** (1.0 → 2.0): Restructure, new sections, workflow changes

When recording outcomes, include agent versions in `agent_versions` field:

```json
"agent_versions": {"map-plan": "1.0", "patch": "1.0", "prove": "1.0"}
```

This enables `/metrics` to correlate success rates with specific agent versions.

---

## 15. When to Escalate

**STOP and report to orchestrator** if:
- Complexity seems wrong (SIMPLE issue is actually COMPLEX)
- Missing information blocks progress
- Constraint violation required to proceed
- Issue scope is ambiguous

**Do NOT** proceed with assumptions. Ask for clarification.

---

## 16. Failure Context Awareness

When spawned with a `## Prior Failure` block in your prompt:
1. Read the root cause and prevention fields carefully
2. Apply the prevention recommendation BEFORE starting work
3. Explicitly verify the prior failure point is addressed
4. Note in artifact: "Prior failure (ROOT_CAUSE) addressed by: [action taken]"

This is the **highest priority** context — a prior PATCH already failed on this exact issue.

---

## 17. Swarm-Aware Behavior

When spawned as a **scoped sub-task** (e.g., PATCH-backend, PATCH-frontend, PROVE-backend):

1. **Respect SCOPE**: Only touch files within your designated scope (backend/ or frontend/)
2. **Use CONTRACT as boundary**: For parallel fullstack PATCH, CONTRACT is the authoritative API spec — both sides implement against it
3. **Write scoped artifacts**: Use `{agent}-{scope}-{issue}-{mmddyy}.md` naming (e.g., `patch-backend-184-020826.md`)
4. **No cross-scope changes**: If you discover a needed change outside your scope, document it in your artifact under "Cross-Scope Dependencies" — do NOT make the change
5. **Report conflicts**: If a file appears in both scopes, flag it immediately in artifact
