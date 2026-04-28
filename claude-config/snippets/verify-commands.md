---
type: snippet
purpose: Canonical verification command catalog (referenced by _base.md, patch.md, prove.md)
---

# Verification Commands

The single source of truth for backend / frontend / scope verification commands
used by PATCH and PROVE. When updating a command, edit it here only.

## Backend

```bash
# Lint
cd backend && ruff check .

# Lint + auto-fix + format only modified files (PATCH usage)
cd backend && ruff check . --fix && ruff format <modified_files>

# Tests
cd backend && pytest -q

# Combined gate
cd backend && ruff check . && pytest -q
```

## Frontend

```bash
cd frontend && npm run lint
cd frontend && npm run build

# Combined gate
cd frontend && npm run lint && npm run build
```

## Scope Verification (no unplanned changes)

```bash
# Should only show files listed in PLAN
git diff --name-only HEAD
git diff --name-only origin/main
```

## Pattern Spot-Checks (when relevant)

```bash
# ENUM_VALUE — verify VALUES not names
grep -A 10 "class.*Enum" backend/backend/*/enums.py

# COMPONENT_API — extract PropTypes / return type
grep -A 20 "PropTypes" frontend/src/components/path/Component.jsx

# MULTI_MODEL — map fields to owning models
grep -rn "class.*Model" backend/backend/*/models.py
```

## Parallel Fullstack Verification

When both backend and frontend changed, fan out via parallel Task calls:

```
Task(description='PROVE-backend', prompt='Run: cd backend && ruff check . && pytest -q')
Task(description='PROVE-frontend', prompt='Run: cd frontend && npm run lint && npm run build')
```

Skip parallel mode for backend-only / frontend-only changes.
