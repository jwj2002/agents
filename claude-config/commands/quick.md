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

### 2.5 Risk Triggers — STOP or Gate (#363)

`/quick` is fast for genuinely trivial work, not a bypass around quality
gates. Before executing, check the task against two trigger sets:

**Route to `/orchestrate` instead (announce it, don't silently continue):**
- The change will touch **more than 3 files**
- It touches a **migration**, **auth/permissions**, or a **backend↔frontend
  contract** (new/changed endpoint, request/response shape)

**Run the eval gate in Step 4 (stay in /quick, but gate):**
- Any changed file matches `~/.claude/rules/eval-file-mapping.md` patterns
  for E01/E04/E13/E14/E15 (frontend sources, model files, Dockerfiles)
- The change touches **enum/role/status/type values** → ALSO read the
  backend enum definition and confirm VALUE-vs-NAME before writing (E01)
- The change **reuses a frontend component or hook** → ALSO read its
  source/PropTypes before invoking (E02)

Docs, typos, copy, comments, pure-markdown changes: no gate — that is what
/quick is for.

### 3. Execute Directly

Follow `.claude/rules.md` constraints. Make changes directly — no sub-agents.

### 4. Verify

```bash
# If backend touched
cd backend && ruff check . && pytest -q

# If frontend touched
cd frontend && npm run lint && npm run build
```

**Eval gate** (when a Step 2.5 trigger fired — mechanical, same floor PROVE
uses):

```bash
python3 ~/agents/claude-config/scripts/evals/run_evals.py --diff-range HEAD
```

Exit 1 → fix the findings before reporting done (or allowlist a false
positive in code with `eval-ok: <ID>` + reason). Exit 2 → the runner broke;
do the E01/E02 source-reading checks by hand and say so in the report.

### 5. Report

```
Quick task complete:
- Files changed: [list]
- Verification: PASS ✅ | FAIL ❌
- Summary: [what was done]
```

---

## Step 6: Record Outcome (MANDATORY)

`/quick` doesn't go through `/orchestrate`, so it records its own outcome
via the same `state_manager` helper the orchestrator uses (see issue #104
for why we no longer rely on free-form `echo >> file` placeholders).

```bash
# After verification passes, always record the /quick outcome.
# /quick changes don't have GitHub issues, so use issue=0 as a sentinel.
# Record REAL complexity (file count), not a hardcoded TRIVIAL (#363):
#   1 file -> TRIVIAL, 2-3 files -> SIMPLE. (>3 files should have routed
#   to /orchestrate at Step 2.5 — if you got here anyway, record MODERATE
#   so the telemetry shows the gate was missed.)
# agents_run notes whether the eval gate ran: ['quick'] or ['quick','evals'].
python3 -c "
import sys
sys.path.insert(0, '$HOME/.claude/hooks')
from state_manager import record_metrics
from pathlib import Path
n = int('$N_FILES')
complexity = 'TRIVIAL' if n <= 1 else ('SIMPLE' if n <= 3 else 'MODERATE')
record_metrics(
    Path('.'), 0, 'PASS', complexity, '$STACK',
    ['quick', 'evals'] if '$GATE_RAN' == 'yes' else ['quick'],
    first_pass_correct=True,
)
"
```

`$STACK` is `backend`, `frontend`, or `config` based on Step 2's
classification; `$N_FILES` is the changed-file count from `git diff
--name-only HEAD | wc -l`; `$GATE_RAN` is `yes` when Step 4's eval gate ran.

For freeform work (no `/quick` command used), run this snippet manually with appropriate `stack` and `complexity` values, or use `/correction` to record a follow-up; automated freeform capture is intentionally out of scope due to signal ambiguity — route substantive work through `/quick` instead.

---

## Rules

**MUST**:
- Load critical patterns before executing
- Check Step 2.5 risk triggers BEFORE executing
- Run verification commands for touched areas
- Run the eval gate when a Step 2.5 trigger fired
- Stay on current branch

**MUST NOT**:
- Create feature branches
- Create GitHub issues
- Spawn sub-agents
- Touch more than 3 files (use `/orchestrate` instead)
- Touch migrations, auth/permissions, or API contracts (use `/orchestrate`)
