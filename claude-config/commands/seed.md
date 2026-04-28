---
description: Capture a deferred idea with a trigger condition for when it should surface
argument-hint: <idea description>
disable-model-invocation: true
---

# Seed Command

**Role**: Capture forward-looking ideas that aren't actionable now but should surface at the right time.

---

## Usage

```bash
/seed "Add rate limiting to the API"
/seed "Migrate from REST to GraphQL" --trigger "next major version"
/seed --list                          # Show all seeds with status
/seed --check                         # Check which seeds match current work
```

---

## What Seeds Solve

Deferred ideas typically go into GitHub issues or get mentioned in conversations and forgotten. Seeds are different — they attach a **trigger condition** so they surface automatically when the scope matches.

```
Traditional backlog:     "Add rate limiting" → sits in issue list → forgotten
Seed:                    "Add rate limiting" → trigger: "when we add public API" → surfaces during /orchestrate for that issue
```

---

## Process

### Creating a Seed

When the user provides an idea:

1. **Ask for trigger condition** using AskUserQuestion:
   - "When should this idea surface?" with options:
     - "Next major version"
     - "When we add [feature]" (user specifies)
     - "When this module is next modified"
     - "During next refactoring pass"
     - Other (freeform)

2. **Estimate scope** using AskUserQuestion:
   - Small (< 1 day)
   - Medium (1-3 days)
   - Large (3+ days)

3. **Scan for breadcrumbs** — grep the codebase for related files:
   ```bash
   grep -rl "KEYWORD" --include="*.py" --include="*.ts" --include="*.jsx" . 2>/dev/null | head -5
   ```

4. **Write seed file** to `.planning/seeds/`:

```markdown
---
id: SEED-001
status: dormant
created: 2026-04-02
trigger_when: "when we add public API endpoints"
scope: medium
related_files:
  - backend/backend/api/router.py
  - backend/backend/core/middleware.py
---

# Add Rate Limiting to API

## What
Add rate limiting middleware to prevent API abuse. Per-user and per-endpoint limits.

## Why
Currently no rate limiting — any client can make unlimited requests. Risk increases when API is exposed publicly.

## When
When we add public-facing API endpoints (currently all endpoints are internal/authenticated).

## Breadcrumbs
- `backend/backend/api/router.py` — main router where middleware would be added
- `backend/backend/core/middleware.py` — existing middleware pattern to follow
```

### Listing Seeds

`/seed --list` displays all seeds:

```
Seeds (3 total):

  SEED-001 [dormant]  Add rate limiting to API
           Trigger: when we add public API endpoints | Scope: medium

  SEED-002 [dormant]  Migrate to async SQLAlchemy sessions
           Trigger: next major version | Scope: large

  SEED-003 [surfaced] Add dark mode support
           Trigger: when we add user preferences | Scope: small
           ⚡ Matches current work
```

### Checking Seeds Against Current Work

`/seed --check` scans all dormant seeds and compares trigger conditions against:
- Current issue title/body (if in an orchestrate session)
- Recently modified files
- Current branch name

If a match is found, the seed status changes to `surfaced` and the user is notified.

---

## Seed Lifecycle

```
dormant → surfaced → (converted to issue OR dismissed)
                         │
                         ├── /feature "from seed SEED-001" → GitHub issue created
                         └── dismissed (user decides: not now / never)
```

---

## File Location

Seeds are stored per-project in `.planning/seeds/`:

```
.planning/
└── seeds/
    ├── SEED-001-rate-limiting.md
    ├── SEED-002-async-sessions.md
    └── SEED-003-dark-mode.md
```

The `.planning/` directory should be committed to the project repo so seeds persist across machines and sessions.

---

## Integration with /orchestrate

At the start of every `/orchestrate` run (Step 0, after verifying the issue), scan seeds:

```bash
# Check if any dormant seeds match this issue
for seed in .planning/seeds/SEED-*.md; do
  STATUS=$(grep "^status:" "$seed" | awk '{print $2}')
  TRIGGER=$(grep "^trigger_when:" "$seed" | cut -d'"' -f2)
  if [ "$STATUS" = "dormant" ]; then
    # Compare trigger against issue title/body
    # If match: notify user, update status to surfaced
  fi
done
```

If seeds surface, report them before proceeding:

```
⚡ Seed SEED-001 surfaced: "Add rate limiting to API"
   Trigger matched: issue touches public API endpoints
   Action: implement alongside this issue, or dismiss?
```

---

## Rules

**MUST**:
- Always ask for trigger condition (not just "add to backlog")
- Scan for related files (breadcrumbs help future recall)
- Store in `.planning/seeds/` (committed to repo)
- Check seeds during `/orchestrate` Step 0

**MUST NOT**:
- Create seeds for urgent/current work (use `/feature` or `/bug` instead)
- Auto-implement surfaced seeds without user confirmation
- Delete seeds — mark as dismissed with reason
