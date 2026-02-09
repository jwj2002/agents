---
description: Execute ad-hoc task without full orchestrate workflow
argument-hint: <task description>
---

# Quick Command

**Role**: Direct executor for small, well-scoped tasks.

---

## Usage

```bash
/quick Fix typo in README
/quick Add missing import in accounts/services.py
/quick Update env example with new variable
```

---

## When to Use

| Criteria | `/quick` | `/orchestrate` |
|----------|----------|----------------|
| Scope | 1-2 files, obvious fix | Multi-file, needs planning |
| Tracking | No GitHub issue needed | Requires GitHub issue |
| Branching | Stay on current branch | Creates feature branch |
| Artifacts | None | Full MAP→PATCH→PROVE |
| Patterns | Loaded (critical only) | Loaded (full if COMPLEX) |

**Rule**: If you hesitate, use `/orchestrate`.

---

## Process

### 1. Load Critical Patterns

```bash
cat .claude/memory/patterns-critical.md
```

Apply VERIFICATION_GAP, ENUM_VALUE, COMPONENT_API checks as relevant.

### 2. Classify Scope

Determine which area is affected:
- **Backend**: `backend/backend/`
- **Frontend**: `frontend/src/`
- **Config**: `.claude/`, root files

### 3. Execute Directly

Follow `.claude/rules.md` constraints. Make changes directly — no sub-agents.

### 4. Verify

```bash
# If backend touched
cd backend && ruff check . && pytest -q

# If frontend touched
cd frontend && npm run lint && npm run build
```

### 5. Report

```
Quick task complete:
- Files changed: [list]
- Verification: PASS ✅ | FAIL ❌
- Summary: [what was done]
```

---

## Optional: Metrics Recording

```bash
echo '{"date":"'$(date +%Y-%m-%d)'","source":"quick","task":"DESCRIPTION","status":"PASS","files_changed":N}' >> .claude/memory/metrics.jsonl
```

---

## Rules

**MUST**:
- Load critical patterns before executing
- Run verification commands for touched areas
- Stay on current branch

**MUST NOT**:
- Create feature branches
- Create GitHub issues
- Spawn sub-agents
- Touch more than 3 files (use `/orchestrate` instead)
