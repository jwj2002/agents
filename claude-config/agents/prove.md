---
agent: "PROVE"
version: 1.3
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

### Parallel Verification (Fullstack)

When both backend and frontend were touched, fan out verification using parallel Task calls for faster wall-clock time:

```
# Spawn in parallel (single message, multiple Task calls):
Task(description='PROVE-backend: lint+test for issue N',
  prompt='Run: cd backend && ruff check . && pytest -q
  Return results as plain text with exit codes.')

Task(description='PROVE-frontend: lint+build for issue N',
  prompt='Run: cd frontend && npm run lint && npm run build
  Return results as plain text with exit codes.')
```

**Collect results** from both tasks, then proceed to Verification Levels.

**Skip parallel mode** when:
- Backend-only or frontend-only change (no fan-out needed)
- Total verification time is under 30s (overhead exceeds benefit)

### Focused Test Strategy

**Step 1**: Identify changed modules from PATCH artifact:
```bash
# Get changed files from PATCH
CHANGED=$(git diff --name-only HEAD~1 -- backend/)
MODULES=$(echo "$CHANGED" | grep -oP 'backend/backend/\K[^/]+' | sort -u)
```

**Step 2**: Run focused tests first (fast feedback):
```bash
# Run only affected module tests
for mod in $MODULES; do
  cd backend && pytest "backend/${mod}/tests/" -q 2>/dev/null
done
```

**Step 3**: Run full suite (safety net):
```bash
cd backend && pytest -q
cd frontend && npm run lint && npm run build
```

**Report both**:
- Focused: X/X passing (Nms)
- Full suite: Y/Y passing (Nms)

**Skip focused mode** when:
- Fullstack change (run full suite directly)
- Refactoring or cross-module changes
- Less than 50 total tests (full suite is fast enough)

---

## Verification Checks

### 1. Standard Gates

| Check | Command | Pass Criteria |
|-------|---------|---------------|
| Backend lint | `ruff check .` | No errors |
| Backend tests | `pytest -q` | All pass |
| Frontend lint | `npm run lint` | No errors |
| Frontend build | `npm run build` | Success |

### 2. Verification Levels

#### Level 1: EXISTS

Verify every file listed in PATCH artifact exists on disk.

```bash
# Check files from PATCH artifact
for f in <files_from_patch>; do [ -f "$f" ] || echo "MISSING: $f"; done
```

**Fail**: Any file from PATCH artifact missing.

#### Level 2: SUBSTANTIVE (no stubs)

```bash
# Extended stub detection in new/modified files
grep -rn "TODO\|FIXME\|HACK\|PLACEHOLDER" <modified_files>
grep -rn "pass$\|return False$\|return \[\]$\|return \{\}$\|raise NotImplementedError" <backend_files>
grep -rn "onClick={() => {}}\|onChange={() => {}}\|return <div>Placeholder\|return null$" <frontend_files>
```

**Fail**: Stubs or placeholders in new/modified files.

#### Level 3: WIRED (integration)

```bash
# New components imported somewhere
# New endpoints called from frontend
# New repos injected into services
# ENUM_VALUE check (if fullstack)
# COMPONENT_API check (if reusing components)
```

**Fail**: Isolated artifacts with no integration, wrong enum values/props.

#### Level 4: FUNCTIONAL

Standard Gates from Section 1 (`ruff check`, `pytest`, `npm run lint`, `npm run build`).

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
$ Focused: backend/accounts/tests/ — 12/12 passing (2.1s)
$ Full: pytest -q — 45/45 passing (8.3s)
$ cd backend && ruff check .
[output]
```

### Verification Levels
- Level 1 EXISTS: ✅ All N files present
- Level 2 SUBSTANTIVE: ✅ No stubs | ❌ [detail]
- Level 3 WIRED: ✅ Pass | ❌ [detail]
- Level 4 FUNCTIONAL: ✅ All gates pass | ❌ [detail]

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

Levels:
- [ ] Level 1: All PATCH files exist
- [ ] Level 2: No stubs/TODOs/placeholders
- [ ] Level 3: New code wired (imports, routes, injection)
- [ ] Level 3: Enum VALUES correct (if fullstack)
- [ ] Level 3: Component APIs correct (if reusing)

Recording:
- [ ] Appended to metrics.jsonl
- [ ] Appended to failures.jsonl (if BLOCKED)
```
