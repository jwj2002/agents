---
paths: ["**"]
---

# Implementation Routing: Right-Sized Claude + Codex Use

Use Codex when a second model materially reduces risk. Do not create ceremony
for trivial work. The default principle:

```text
Simple work gets one agent.
Risky work gets two opinions.
Failed work gets a different model.
```

## Step 1: Assess Risk

Assess before choosing a workflow. Base the decision on changed files, blast
radius, ambiguity, and failure history.

| Tier | Signals | Primary Route | Codex Role |
|---|---|---|---|
| TRIVIAL | Typo, copy, obvious one-file config/import fix | `/quick` | None |
| SIMPLE | 1-3 files, one subsystem, clear behavior | Plan mode or direct implementation | Optional only |
| MODERATE | 4-5 files, shared behavior, meaningful tests | `/orchestrate` SIMPLE tier | Diff review recommended |
| COMPLEX | 6+ files, architecture, migrations, data model, cross-cutting behavior | `/orchestrate` COMPLEX tier | Diff review recommended |
| FULLSTACK | Backend + frontend contract/API/enum behavior | `/orchestrate` + CONTRACT | Diff review with contract/API/enum focus |
| PRIOR FAIL | PROVE blocked, repeated failed attempt, stuck debugging | Reassess before retry | Codex rescue or review recommended |

## Codex Escalation Triggers

Use Codex review when one or more apply:

- Auth, permissions, tenancy, payments, money, migrations, data loss, or secrets.
- Public API, backend/frontend contract, enum/status/role values.
- Shared library behavior or cross-module refactor.
- New tests are hard to reason about or failure modes are subtle.
- Claude already failed PROVE or repeated the same approach twice.

Skip Codex when all apply:

- One obvious file or docs-only change.
- No public/user-facing behavior change.
- Verification is straightforward and passes.
- A second review would cost more than the risk it reduces.

## Review Commands

Use the Codex plugin commands instead of inventing ad-hoc prompts:

```text
/codex:review               # native diff review (no focus text)
/codex:adversarial-review   # adversarial diff review with focus text
/codex:rescue               # delegate implementation when Claude is stuck
```

### Per-AC audit + project review gates

Two generic principles apply to every MODERATE+ Codex review (skip both on
TRIVIAL):

1. **Per-AC audit**: extend the review prompt so the verdict must include an
   `ac_audit` array (`implemented|partial|missing|deferred|n/a` per AC) and a
   scope-freeze escape hatch (`new_concerns` instead of REQUEST_CHANGES
   drift). A reviewer that can APPROVE on partial AC coverage will — the
   per-AC shape forbids it.
2. **Use the repo's review-gate wrapper when it ships one**: if the project
   has a chokepoint that runs mechanical gates before `codex exec` (and logs
   bypass telemetry), route the review through it rather than calling
   `codex exec` directly.

Project-specific mechanics (prompt fragments, wrapper CLIs, env vars,
telemetry paths) live in that project's memory, not here — e.g. buddy's
clauses + `codex_review_gate` chokepoint:
`~/.claude/projects/-Users-jasonjob-projects-buddy/memory/codex_review_gates_buddy.md`.

## Step 2: Announce Routing Briefly

Examples:

```text
Quick: one docs typo. No Codex.
Simple: two backend files. I will implement and offer /codex:review only if risk appears.
Moderate: shared service change. I will run /codex:adversarial-review after verification.
Complex: migration + service + API. I will run /codex:adversarial-review after PATCH.
Fullstack: backend endpoint + UI. /codex:adversarial-review with focus on contract and enum values.
Prior fail: Claude PROVE blocked. I will /codex:rescue as a second-model attempt before retrying.
```

## Step 3: Apply Codex Findings

Codex output is advisory until classified by Claude:

| Finding Type | Action |
|---|---|
| BLOCKING | Fix before PR; rerun relevant verification |
| NON-BLOCKING | Note in PR or backlog if useful |
| CLEAN | Continue |

Do not let broad or speculative Codex feedback expand scope. Only act on
findings tied to concrete changed code, tests, contracts, or security risk.

## Model And Permission Defaults

- Prefer the plugin commands above; they handle execution mode, scope, and
  size estimation. Drop to `codex exec` directly only for ad-hoc one-offs.
- Use `codex-danger` only when the user explicitly wants no prompts and accepts
  unsandboxed execution.
- Keep implementation local to Claude unless Codex has an independent, bounded
  slice or prior Claude attempts failed.
