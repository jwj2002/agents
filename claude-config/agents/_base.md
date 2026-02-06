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

### Always Load (Critical Patterns ~50 lines)
```bash
cat .claude/memory/patterns-critical.md
```

### Load If Needed (Full Patterns ~660 lines)
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
| PATCH | 300 | 400 |
| PROVE | 250 | 350 |

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

These patterns cause >50% of failures. Check proactively:

### ENUM_VALUE (26% of failures)
**Trigger**: Fullstack issue with role/status/type fields
**Check**: Read backend enum, verify VALUES not names
```bash
grep -A 10 "class.*Enum" backend/backend/*/enums.py
```
**Prevention**: Frontend must use VALUE string (e.g., `"CO-OWNER"` not `"CO_OWNER"`)

### COMPONENT_API (17% of failures)
**Trigger**: Reusing existing frontend component/hook
**Check**: Read actual source, extract PropTypes/return type
```bash
grep -A 20 "PropTypes" frontend/src/components/path/Component.jsx
```
**Prevention**: Document API explicitly before using

### MULTI_MODEL (13% of failures)
**Trigger**: CRUD operation with 5+ fields
**Check**: Map each field to its owning model
**Prevention**: Service layer must coordinate all model updates atomically

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
| PATCH | PLAN or MAP-PLAN artifact. CONTRACT if fullstack | `ls .agents/outputs/{plan,map-plan}-{issue}-*.md` |
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
- **Minor** (1.0 → 1.1): Pattern additions, wording changes via `/agent-update`
- **Major** (1.0 → 2.0): Manual restructure, new sections, workflow changes

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
