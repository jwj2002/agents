---
description: Create a new feature request issue in GitHub
argument-hint: <feature title> [--from-spec specs/name.md]
---

# Feature Request Command

Creates a feature request issue in GitHub with proper labels and template.

## Usage

```bash
/feature Add user profile settings page
/feature --from-spec specs/user-profiles-v2.md Add profile photo upload
```

---

## Process

### Step 1: Parse Input

Extract title from the argument. If `--from-spec` provided, read the spec file for requirements.

### Step 2: Classify

Determine from context:
- **Stack**: backend / frontend / fullstack
- **Complexity**: TRIVIAL / SIMPLE / COMPLEX

| Level | Criteria |
|-------|----------|
| TRIVIAL | Config changes, docs, single-file edits |
| SIMPLE | 1-3 files, follows existing pattern exactly |
| COMPLEX | 4+ files, new patterns, migrations, fullstack |

### Step 3: Check for Duplicates

```bash
gh issue list --state open --search "KEYWORD" --label "feature"
```

### Step 4: Create Issue

```bash
TITLE="$1"

gh issue create \
  --title "[Feature] ${TITLE}" \
  --label "feature,${COMPLEXITY},${STACK}" \
  --body "$(cat <<'EOF'
## Specification Reference
**Source**: `specs/[spec-file].md` or "N/A (ad-hoc feature)"
**Section**: [Specific section] or "N/A"

## Feature Description
[Clear 1-2 sentence description]

## User Story
**As a** <persona>
**I want** <capability>
**So that** <value>

## Scope / Stack
- [ ] Backend
- [ ] Frontend
- [ ] Fullstack

## Requirements
### Functional
- [ ] [Requirement 1]
- [ ] [Requirement 2]

### Non-Functional
- [ ] Minimal diffs / no drive-by refactors
- [ ] Security / tenancy enforced via deps (backend)

## Technical Context
### Affected Areas
**Backend (if applicable)**:
- Models / Schemas / Services / Routers

**Frontend (if applicable)**:
- Components / Context / API layer

## Acceptance Criteria
- [ ] Feature works end-to-end
- [ ] Backend: `ruff check .` + `pytest -q` pass
- [ ] Frontend: `npm run lint` + `npm run build` pass
- [ ] Loading / empty / error states handled (if UI)

## Complexity: COMPLEXITY_PLACEHOLDER

**Justification**: [Why this complexity level]
EOF
)"
```

### Step 5: Report

```
Created issue #N: [Feature] Title
Labels: feature, SIMPLE, backend
URL: https://github.com/...

Next: /orchestrate N
```

---

## With --from-spec

When a spec is provided:
1. Read the spec file
2. Extract requirements from relevant sections
3. Pre-populate the issue body with spec references and line numbers
4. Add `from-spec` label

```bash
gh issue create \
  --title "[Feature] ${TITLE}" \
  --label "feature,from-spec,${COMPLEXITY},${STACK}" \
  --body "..."
```

---

## Related Commands

- `/orchestrate N` — Implement the feature
- `/bug` — Create bug report instead
- `/spec-draft` — Create a spec first
