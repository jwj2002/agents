---
description: Extract patterns from existing code into knowledge/patterns/
argument-hint: [focus-area]
---

# Discover Patterns

**Role**: Bottom-up pattern extraction. Read working code, surface non-obvious conventions, write them as `knowledge/patterns/pat-<slug>.yaml`.

Complements `/learn` (top-down from failures). Use this when onboarding a new project, inheriting a repo, or auditing established code.

---

## Usage

```bash
/discover-patterns                # interactive — pick focus area
/discover-patterns api            # pre-seed focus area
```

Run from inside the target repo. Writes to `knowledge/patterns/` in the cwd repo root.

---

## Output Prelude (print verbatim on start)

```
Discovering patterns in <repo-name>.
Each pattern captures a non-obvious convention from the codebase
(things a newcomer wouldn't infer from generic best practices).

I'll ask you to pick a focus area, then walk through 3-5 candidates.
For each one you keep, I'll ask why the team does it that way before
drafting. Capped at 3 patterns per run — re-run for more.

Output: knowledge/patterns/pat-<slug>.yaml (status: pilot).
```

`<repo-name>` = `basename "$(git rev-parse --show-toplevel)"` (or cwd basename if not a git repo).

---

## Process

### Step 1 — Determine focus area

Scan top-level dirs. Identify 3-5 major areas (e.g. `api/`, `database/`, `auth/`, `tests/`, `frontend/src/`, `services/`, `config/`). Skip `node_modules/`, `.git/`, `__pycache__/`, `dist/`, `build/`.

Use `AskUserQuestion` to present the candidates. Single-select, single area per run. If `$ARGUMENTS` matches a real directory, use it directly and skip the question.

### Step 2 — Analyze and present findings

Read 5-10 representative files in the chosen area. Prefer files that are central (touched often, imported widely) over leaves.

Identify candidate patterns. A candidate qualifies if it is **unusual, opinionated, or non-obvious** — something a newcomer wouldn't infer from generic best practices. Disqualify generic advice ("use type hints", "write docstrings"). Qualify project-specific conventions (RBAC at the dependency layer, enum VALUE strings, services raising domain exceptions never HTTPException, etc.).

Present 3-5 candidates via `AskUserQuestion`. Multi-select OK; cap drafted patterns at 3 per run.

### Step 3 — Ask why, then draft

For each chosen pattern, ask 1-2 clarifying questions about WHY the team does it that way. Use `AskUserQuestion` with concrete options when enumerable; free-form only when the answer truly isn't.

**Don't skip the why.** Patterns without context don't survive contact with a different project. Wait for the answer before drafting.

### Step 4 — Create pattern file

Write to `knowledge/patterns/pat-<slug>.yaml`. Slug rules:

- All lowercase, hyphens, no underscores
- 3-6 words describing the rule (`pat-permission-dependency`, not `pat-auth`)
- Filename and `id` field MUST match (slug invariant — see `sync.py` duplicate-id guard)

Required fields (per `sync.py` PATTERN_REQUIRED — build rejects anything missing):

```yaml
id: pat-<slug>
category: <auth | database | api | frontend | infrastructure | workflow | testing | observability>
name: <short human label, ≤10 words>
status: pilot
tier: secondary  # only "primary" or "secondary" are valid per sync.py — use "primary" for foundational
description: <lead with the rule, then the why, ≤2 sentences>
```

Strongly recommended:

```yaml
when_to_use: <1-2 sentences>
when_not_to_use: <1-2 sentences>
implementation:
  language: <python | typescript | bash | ...>
  framework: <FastAPI | React | null>
  key_decisions:
    - <bullet>
  reference_code: |
    <minimal snippet>
  gotchas:
    - <pitfall>
reference_project: <repo-name from cwd>
reference_path: <relative-path>:<start-line>-<end-line>
lifecycle:
  created_at: "<today YYYY-MM-DD>"
  extracted_from: <repo-name>
  extracted_by: discover-patterns
created_at: "<today YYYY-MM-DD>"
updated_at: "<today YYYY-MM-DD>"
```

**Body length**: ≤200 words excluding `reference_code`. Lead `description` with the rule, then the why. Terse.

**Confirm before write**: Show drafted YAML, ask via `AskUserQuestion` (Yes / Revise / Skip). All writes go to `knowledge/patterns/` only.

### Step 5 — Validate

After ≥1 pattern written, run:

```bash
cd knowledge && python3 sync.py build
```

Confirm exit 0. If guard fails (likely: duplicate id, missing required field, invalid status/tier):

1. Capture stderr
2. Revert just-written file (`rm` if brand new, `git checkout --` if previously tracked)
3. Report error to user — don't retry blindly

**Don't run `sync.py build` until ≥1 pattern is written.**

### Step 6 — Offer to continue

After validation passes, `AskUserQuestion`:

- "Yes, same area" → return to Step 2
- "Yes, different area" → return to Step 1
- "Stop" → exit and print summary

Hard cap: 3 patterns per run. After 3, force-stop regardless of choice.

---

## Constraints

- **`AskUserQuestion`** for every choice (focus area, pattern selection, why-options, write confirmation, continue prompt). Never free-form prompt for selections.
- **Lead with the rule** in each `description`, then the why.
- **Terse** — ≤200 words per pattern body.
- **Status `pilot`** for all newly extracted patterns.
- **`reference_project` from cwd** + **`reference_path: <file>:<start>-<end>`** so each pattern points back to its source.
- **Cap at 3 patterns per run.**
- **Confirm before each write.**
- **All writes to `knowledge/patterns/` only.**
- **Don't run `sync.py build`** until ≥1 pattern is written.
- **No bulk extraction** — interactive only.
- **No updates** — `/discover-patterns` only creates. Updating existing patterns stays manual or via `/learn`.

---

## Final Report

```
Discovered N patterns in <focus-area>:
  knowledge/patterns/pat-<slug-1>.yaml  — <name>
  knowledge/patterns/pat-<slug-2>.yaml  — <name>

sync.py build: PASS (exit 0)

Patterns are status: pilot. They surface through vault-metrics MCP at
next session start. Promote to validated manually after the convention
holds across at least one new use.
```

---

## Related

- `/learn` — top-down extraction from `failures.jsonl`
- `knowledge/sync.py` — slug-uniqueness guard
- `knowledge/patterns/` — destination; existing files are the schema reference
