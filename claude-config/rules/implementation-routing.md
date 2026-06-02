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

### AC-FORBIDS-APPROVE + scope-freeze clauses

When invoking Codex for any **CODE review** (post-PATCH) or **SPEC review** that
the prompt arguments allow you to extend, **append the per-AC audit + scope-
freeze clauses** from the buddy-managed prompt fragment:

```
specs/../prompts/codex-review-clauses.md      (buddy repo)
```

The fragment contains three sections to append to your Codex prompt:
1. Per-AC audit (`ac_audit` array with `implemented|partial|missing|deferred|n/a` statuses)
2. Scope-freeze (`new_concerns` escape hatch instead of REQUEST_CHANGES drift)
3. Output JSON schema additions

**Why:** issue #1609 (Harold-borrowed loop-closer). Without these clauses,
Codex can return APPROVE on partial AC coverage — the Mavis Surface spec
review hit this 4 rounds in a row. Companion: PROVE-side enforcement of the
same `ac_audit` shape lives in issue #1612.

**Mechanics:** for the spec-review workflow's R1-R4 `/tmp/codex-spec-r*.md`
prompt files, append the three sections at the end before passing to
`codex review`. For `/codex:review` plugin invocations, include the
sections as the `[PROMPT]` positional or via stdin where the plugin allows.

**When to skip:** TRIVIAL changes (one-file typo, copy edit) — the per-AC
overhead isn't worth it. For everything MODERATE+, include the fragment.

### Chokepoint wrapper (buddy#1613)

Buddy ships a Python chokepoint at `scripts/codex_review_gate/main.py` that
every Codex review for buddy work flows through. It runs configured
mechanical gates BEFORE invoking `codex exec`; a gate exit code in `2-8`
synthesizes a `REQUEST_CHANGES` verdict locally without calling Codex.
Other non-zero exits (or crashes) fail-OPEN so Codex still runs.

```bash
python3 -m scripts.codex_review_gate.main \
    --branch-sha $(git rev-parse HEAD) \
    --plan /tmp/codex-1610-review.md \
    --verdict-out /tmp/verdict-1610.json \
    [--gates name="argv ..." ...] \
    --codex-args -- --skip-git-repo-check --sandbox read-only "$(cat /tmp/codex-1610-review.md)"
```

The wrapper writes one row per invocation to
`<store>/codex-gate-log.jsonl` (path resolved with test-isolation
honoring `BUDDY_CODEX_GATE_LOG_PATH` → `BUDDY_TEST_STORE_DIR` →
`PYTEST_CURRENT_TEST` → `BUDDY_HOME` → default). Critically: every row
carries `gatesPassed = passed AND NOT bypassed`. Emergency bypass via
`BUDDY_CODEX_GATE_ENFORCE=0` is allowed but the resulting verdict
carries `bypassed=true, gatesPassed=false`. The pre-push hook at
`buddy/scripts/pre-push` (and equivalent CI check) refuses any branch
SHA whose latest log row lacks `gatesPassed=true`.

**Why** (#1613 Harold loop-closer 5 of 5): the "305 reviews logged, 0
gates ran" + "bypassed bypass" classes are unrecoverable without
structural enforcement. The chokepoint is the structural answer.

**When to skip:** TRIVIAL changes still skip Codex entirely; nothing to
gate. For COMPLEX+ Codex reviews on buddy, prefer the chokepoint over
calling `codex exec` directly. For now, `--gates` may be empty — the
gate scripts are a separate follow-up — but the telemetry + bypass
plumbing already enforces gatesPassed semantics.

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
