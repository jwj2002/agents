---
description: Create a new bug report issue in GitHub
argument-hint: <bug title>
---

# Bug Report Command

Creates a bug report issue in GitHub with proper labels and template.

## Usage

```bash
/bug Login fails with expired JWT token
/bug --severity high Database connection timeout on large queries
```

---

## Process

### Step 1: Parse Input

Extract title from the argument. If no argument provided, ask the user.

### Step 2: Investigate Context

Before creating the issue, gather context:

```bash
# Check for recent related errors in git log
git log --oneline -20 | grep -i "fix\|bug\|error"

# Check if similar issues exist
gh issue list --state open --search "KEYWORD"
```

### Step 3: Classify

Determine from investigation:
- **Stack**: backend / frontend / fullstack
- **Severity**: critical / high / medium / low
- **Complexity**: TRIVIAL / SIMPLE / COMPLEX

### Step 4: Create Issue

```bash
TITLE="$1"
SEVERITY="${SEVERITY:-medium}"

gh issue create \
  --title "[Bug] ${TITLE}" \
  --label "bug,${COMPLEXITY},${STACK}" \
  --body "$(cat <<'EOF'
## Reported Issue

**What's broken**: [Description from user input]

**Expected behavior**: [What should happen instead]

**Severity**: SEVERITY_PLACEHOLDER

## Scope / Stack
- [ ] Backend
- [ ] Frontend
- [ ] Fullstack

## Error Details (if applicable)
**Error type**:
**Error message**:
**Location (file:line)**:
**Endpoint/route (method path)**:

## Reproduction Steps
1.
2.
3.

## Notes / Logs
```text
[Paste relevant logs or error output]
```

## Acceptance Criteria
- [ ] Root cause identified
- [ ] Fix is minimal and scoped
- [ ] No project structure violations
- [ ] Backend: `ruff check .` + `pytest -q` pass
- [ ] Frontend: `npm run lint` + `npm run build` pass

## Complexity: COMPLEXITY_PLACEHOLDER
EOF
)"
```

### Step 5: Report

```
Created issue #N: [Bug] Title
Labels: bug, SIMPLE, backend
URL: https://github.com/...
```

---

## Labels

| Label | When |
|-------|------|
| `bug` | Always |
| `TRIVIAL` / `SIMPLE` / `COMPLEX` | Based on complexity |
| `backend` / `frontend` / `fullstack` | Based on stack |
| `critical` | If severity is critical |

---

## Related Commands

- `/orchestrate N` — Fix the bug using workflow
- `/feature` — Create feature request instead
