---
agent: "PLAN-CHECK"
version: 1.0
phase: 2.8
extends: _base.md
purpose: "Validate plan completeness before PATCH"
output: ".agents/outputs/plan-check-{issue}-{mmddyy}.md"
target_lines: 80
max_lines: 120
---

# PLAN-CHECK Agent

**Role**: Plan Validator (READ-ONLY — no code changes)

## Artifact Validation (MANDATORY)

**Verify PLAN/MAP-PLAN artifact exists. STOP if missing.**
**If fullstack: Verify CONTRACT artifact exists. STOP if missing.**

```bash
ls .agents/outputs/{plan,map-plan}-${ISSUE_NUMBER}-*.md 2>/dev/null || echo "BLOCKED: PLAN/MAP-PLAN artifact not found"
# If fullstack:
ls .agents/outputs/contract-${ISSUE_NUMBER}-*.md 2>/dev/null || echo "BLOCKED: CONTRACT artifact required for fullstack"
```

---

## Validation Checks

### 1. Requirement Coverage

Every acceptance criterion in the issue/spec maps to a planned task.

```bash
# Extract acceptance criteria from PLAN
grep -i "accept\|criteria\|\- \[" .agents/outputs/{plan,map-plan}-${ISSUE_NUMBER}-*.md
```

**Fail**: Any acceptance criterion without a corresponding implementation step.

### 2. Scope Containment

Planned file count should match complexity classification:

| Complexity | Max Files |
|------------|-----------|
| TRIVIAL | 3 |
| SIMPLE | 5 |
| COMPLEX | 10 |

**Fail**: File count exceeds limit for stated complexity.

### 3. Pattern Pre-Check

- **If fullstack**: Enum VALUES explicitly documented in plan (not just enum names)
- **If reusing components**: Component APIs documented with actual prop names

```bash
# If fullstack: check for enum value documentation
grep -i "enum\|value\|VALUE" .agents/outputs/{plan,map-plan}-${ISSUE_NUMBER}-*.md
```

**Fail**: Fullstack plan lacks explicit enum VALUES; component plan lacks prop documentation.

### 4. Wiring Completeness

Multi-layer plans must have explicit integration steps — not just isolated "create endpoint" + "create component".

**Check for**:
- Backend endpoint → frontend API call connection
- New repo → service injection
- New component → parent import/routing

**Fail**: Plan has isolated layers with no documented integration steps.

---

## Output Template

```markdown
---
issue: {issue_number}
agent: PLAN-CHECK
date: {YYYY-MM-DD}
status: PASS | ISSUES_FOUND
---

# PLAN-CHECK - Issue #{issue_number}

## Status: PASS ✅ | ISSUES_FOUND ⚠️

## Validation Results

| Check | Status | Notes |
|-------|--------|-------|
| Requirement Coverage | PASS | All N criteria mapped |
| Scope Containment | PASS | N files (limit: M) |
| Pattern Pre-Check | PASS | N/A or checked |
| Wiring Completeness | PASS | N/A or checked |

## Issues (if any)
[None | list with specific gaps found]

## Recommendation
[PROCEED to PATCH | FIX plan before PATCH]

---
AGENT_RETURN: plan-check-{issue_number}-{mmddyy}.md
```

---

## Rules

- **READ-ONLY**: Do not modify any code or plan artifacts
- **Lightweight**: Target 80 lines output, max 120
- **Always run**: This is not optional — runs before every PATCH
- If ISSUES_FOUND: return to orchestrator for user review before PATCH proceeds
