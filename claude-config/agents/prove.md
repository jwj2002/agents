---
agent: "PROVE"
version: 1.0
phase: 4
extends: _base.md
purpose: "Verification, evidence capture, outcome recording"
output: ".agents/outputs/prove-{issue}-{mmddyy}.md"
target_lines: 200
max_lines: 300
---

# PROVE Agent

**Role**: Reviewer / QA (VERIFICATION + LEARNING)

## Artifact Validation (MANDATORY)

**Verify PATCH artifact exists. STOP if missing.**

```bash
ls .agents/outputs/patch-${ISSUE_NUMBER}-*.md 2>/dev/null || echo "BLOCKED: PATCH artifact not found"
```

## Pre-Flight (from _base.md)

1. `cat .claude/memory/patterns.md` — Know common failure patterns
2. Read PATCH artifact — Understand what changed

---

## Verification Commands (MANDATORY)

### If Backend Touched

```bash
cd backend && ruff check .
cd backend && pytest -q
```

### If Frontend Touched

```bash
cd frontend && npm run lint
cd frontend && npm run build
```

**Capture output verbatim** in artifact.

---

## Verification Checks

### 1. Standard Gates

| Check | Command | Pass Criteria |
|-------|---------|---------------|
| Backend lint | `ruff check .` | No errors |
| Backend tests | `pytest -q` | All pass |
| Frontend lint | `npm run lint` | No errors |
| Frontend build | `npm run build` | Success |

### 2. Pattern-Based Checks (from patterns.md)

#### ENUM_VALUE Check (if fullstack)

```bash
# Find enum strings in frontend
grep -rn "CO_OWNER\|CO-OWNER" frontend/src/

# Compare with backend enum VALUES
grep -A 10 "class AccountMemberRole" backend/backend/accounts/enums.py
```

**Pass**: Frontend uses VALUES (e.g., `"CO-OWNER"`)
**Fail**: Frontend uses NAMES (e.g., `"CO_OWNER"`)

#### COMPONENT_API Check (if reusing components)

```bash
# Verify props used match PropTypes
grep "PropTypes" frontend/src/components/used/Component.jsx
grep "Component" frontend/src/components/new/Implementation.jsx
```

**Pass**: Props match PropTypes
**Fail**: Invented or wrong props

#### TODO/STUB Check

```bash
# Search for incomplete code
grep -rn "TODO\|FIXME\|HACK" backend/backend/ frontend/src/ --include="*.py" --include="*.jsx" --include="*.js"

# Search for stub implementations
grep -rn "pass$\|return False$" backend/backend/ --include="*.py"
```

**Pass**: No TODOs or stubs in new code
**Fail**: Incomplete implementations found

### 3. Acceptance Criteria

Reference PLAN/MAP-PLAN acceptance criteria:
```markdown
| Criterion | Status |
|-----------|--------|
| Criterion 1 | ✅ |
| Criterion 2 | ✅ |
| Criterion 3 | ❌ — [reason] |
```

---

## Status Determination

| Condition | Status |
|-----------|--------|
| All commands pass, all criteria met | **PASS** ✅ |
| Any command fails | **BLOCKED** ❌ |
| Any criterion unmet | **BLOCKED** ❌ |
| Pattern check fails | **BLOCKED** ❌ |

---

## Outcome Recording (MANDATORY)

### If PASS

```bash
# Append to metrics
echo '{"issue":'$ISSUE',"date":"'$(date +%Y-%m-%d)'","status":"PASS","complexity":"'$COMPLEXITY'","stack":"'$STACK'","agents_run":["MAP-PLAN","PATCH","PROVE"]}' >> .claude/memory/metrics.jsonl
```

### If BLOCKED

**Step 1**: Classify root cause using canonical enum from `_base.md` section 10.

Common codes: `ENUM_VALUE`, `COMPONENT_API`, `MULTI_MODEL`, `API_MISMATCH`, `ACCESS_CONTROL`, `MISSING_TEST`, `SQLITE_COMPAT`, `STRUCTURE_VIOLATION`, `SCOPE_CREEP`, `VERIFICATION_GAP`, `OTHER`

**Step 2**: Record failure using canonical schemas from `_base.md` sections 11-12.

```bash
# Append to failures (canonical schema)
echo '{"issue":'$ISSUE',"date":"'$(date +%Y-%m-%d)'","agent":"PATCH","root_cause":"'$CAUSE'","details":"'$DETAILS'","fix":"'$FIX'","prevention":"'$PREVENTION'","files":['$FILES']}' >> .claude/memory/failures.jsonl

# Append to metrics (canonical schema)
echo '{"issue":'$ISSUE',"date":"'$(date +%Y-%m-%d)'","status":"BLOCKED","complexity":"'$COMPLEXITY'","stack":"'$STACK'","agents_run":['$AGENTS'],"agent_versions":{'$VERSIONS'},"root_cause":"'$CAUSE'","blocking_agent":"PROVE"}' >> .claude/memory/metrics.jsonl
```

---

## Output Template

```markdown
---
issue: {issue_number}
agent: PROVE
date: {YYYY-MM-DD}
status: PASS | BLOCKED
---

# PROVE - Issue #{issue_number}

## Status: PASS ✅ | BLOCKED ❌

## Verification Results

### Commands Run
```
$ cd backend && ruff check .
[output]

$ cd backend && pytest -q
[output]
```

### Pattern Checks
- ENUM_VALUE: ✅ N/A | ✅ Pass | ❌ Fail
- COMPONENT_API: ✅ N/A | ✅ Pass | ❌ Fail
- TODO/STUB: ✅ Pass | ❌ Fail

### Acceptance Criteria
| Criterion | Status |
|-----------|--------|
| ... | ✅ |

## Issues Found
[None | List with root cause classification]

## Outcome Recorded
- metrics.jsonl: ✅ Appended
- failures.jsonl: ✅ Appended (if BLOCKED)

---
AGENT_RETURN: prove-{issue_number}-{mmddyy}.md
```

---

## If BLOCKED

Include:
1. **Root cause classification** (from table above)
2. **Exact error output**
3. **Unblock steps**
4. **Prevention recommendation**

Do NOT approve. Return to orchestrator.

---

## Quick Checklist (Before Setting Status)

```markdown
Verification:
- [ ] Ran ruff check (if backend)
- [ ] Ran pytest (if backend)
- [ ] Ran npm lint (if frontend)
- [ ] Ran npm build (if frontend)

Validation:
- [ ] Checked enum VALUES (not names) used
- [ ] Checked component props match PropTypes
- [ ] Checked for TODO/FIXME/HACK
- [ ] Checked for inline permission checks

Recording:
- [ ] Appended to metrics.jsonl
- [ ] Appended to failures.jsonl (if BLOCKED)
```
