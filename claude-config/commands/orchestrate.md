---
description: Execute MAP → PLAN → PATCH → PROVE workflow for GitHub issues
argument-hint: [issue-number] [--with-tests] [--discuss] [--resume] [--parallel]
---

# Orchestrate Command

**Role**: Conductor (ORCHESTRATION ONLY — never implement features yourself).

---

## Usage

```bash
/orchestrate 184
/orchestrate 184 --with-tests    # Include TEST-PLANNER phase
/orchestrate 184 --discuss       # Identify gray areas before planning
/orchestrate 184 --resume        # Resume from last completed phase
/orchestrate 184 --parallel      # Run in isolated worktree
/orchestrate 184 --parallel --resume  # Resume in existing worktree
```

If no issue provided, instruct user to create one with `/feature` or `/bug`.

**Flags**:
- `--with-tests`: Run TEST-PLANNER agent after MAP-PLAN (recommended for calculations/formulas)
- `--discuss`: Run DISCUSS agent before MAP-PLAN. Recommended for COMPLEX and FULLSTACK
- `--resume`: Resume an interrupted workflow from the last completed phase
- `--parallel`: Run workflow in an isolated git worktree (`.worktrees/issue-{N}/`)

---

## Workflow

```
SIMPLE:         [DISCUSS] → MAP-PLAN → [TEST-PLANNER] → CONTRACT* → PATCH → PROVE
COMPLEX:        [DISCUSS] → MAP → PLAN → [TEST-PLANNER] → CONTRACT* → PLAN-CHECK → PATCH → PROVE
```

- TRIVIAL work is **rejected** by Step 1 with a redirect to `/quick` (see `rules/implementation-routing.md`)
- `[TEST-PLANNER]` runs if `--with-tests` is provided
- `CONTRACT*` is **MANDATORY** if fullstack — PATCH will STOP without it
- Codex is not a mandatory phase. Use `/codex:review` or `/codex:adversarial-review`
  only when risk justifies a second model (see `rules/implementation-routing.md`).

---

## Reference Files (load on demand)

When the workflow reaches Step 3, load the relevant reference:

| Reference | Loaded for |
|-----------|------------|
| `templates/orchestrate-pipeline.md` | Per-agent prompt templates, validation gates, failure-context injection |
| `templates/orchestrate-parallel.md` | MAP fan-out, speculative PATCH, worktree mode, resume mode |
| `templates/agent-prompt.md` | The base agent prompt template (variable substitution) |

Don't pre-load all of these. Read only what the current phase needs.

---

## Agent Resolution (Global + Project Override)

Agent instructions are loaded with project-first fallback:

1. `.claude/agents/{agent}.md` (project-specific override)
2. `~/.claude/agents/{agent}.md` (global default)

**Examples**:
- Project has custom `patch.md` → uses project version
- Project has no `map-plan.md` → uses global version
- Artifacts ALWAYS go to project-local `.agents/outputs/`

```bash
AGENT="map-plan"
if [ -f ".claude/agents/${AGENT}.md" ]; then
  AGENT_PATH=".claude/agents/${AGENT}.md"
else
  AGENT_PATH="~/.claude/agents/${AGENT}.md"
fi
```

---

## State Tracking (CRITICAL for Context Continuity)

**Purpose**: Persist orchestrate state so it survives context compaction.

**State file**: `.agents/outputs/claude_checkpoints/PERSISTENT_STATE.yaml`

### Update State Before Each Phase

**MUST** run BEFORE spawning each agent:

```bash
python3 -c "import sys; sys.path.insert(0, '$HOME/.claude/hooks'); from state_manager import update_phase; from pathlib import Path; update_phase(Path('.'), $ISSUE, '$BRANCH', '$PHASE', 'Starting $PHASE phase')"
```

Variables: `$ISSUE` (issue number), `$BRANCH` (current branch), `$PHASE` (`MAP-PLAN`, `PATCH`, `PROVE`, etc.).

### Clear State After Completion

```bash
python3 -c "import sys; sys.path.insert(0, '$HOME/.claude/hooks'); from state_manager import clear_active; from pathlib import Path; clear_active(Path('.'), $ISSUE)"
```

For `--resume` and `--parallel` semantics: see `templates/orchestrate-parallel.md`.

---

## Process

### Step 0: Verify Issue

```bash
gh issue view $ISSUE --json number,title,body
```

If not found, STOP.

### Step 0.5: Scan Seeds

Check if any dormant seeds match this issue:

```bash
if [ -d ".planning/seeds" ]; then
  ISSUE_TITLE=$(gh issue view $ISSUE --json title --jq '.title')
  for seed in .planning/seeds/SEED-*.md; do
    [ -f "$seed" ] || continue
    STATUS=$(grep "^status:" "$seed" | awk '{print $2}')
    if [ "$STATUS" = "dormant" ]; then
      TRIGGER=$(grep "^trigger_when:" "$seed" | cut -d'"' -f2)
      SEED_NAME=$(grep "^# " "$seed" | head -1 | sed 's/^# //')
      SEED_ID=$(grep "^id:" "$seed" | awk '{print $2}')
      echo "Checking $SEED_ID: $SEED_NAME (trigger: $TRIGGER)"
    fi
  done
fi
```

If seeds match, report before proceeding. If no `.planning/seeds/`, skip silently.

### Step 1: Classify Complexity

Four tiers (#387). Estimate the file count from the issue body + a quick grep;
when two tiers both fit, the RISK signals (migrations, endpoints, fullstack,
cross-cutting) win over the file count.

| Tier | Criteria | Pipeline | Notes |
|------|----------|----------|-------|
| TRIVIAL | Typo, single-config-line, obvious one-file fix | — | Rejected below → `/quick` |
| SIMPLE | 1–3 files, one subsystem, clear behavior | MAP-PLAN | Default cheap path |
| MODERATE | 4–5 files, single subsystem, clear pattern | MAP-PLAN | Same pipeline as SIMPLE, but Codex review per Step 1.1 and record `complexity: MODERATE` |
| COMPLEX | 6+ files, OR any migration / new-changed endpoint / cross-cutting refactor / FULLSTACK | MAP → PLAN → PLAN-CHECK | Strong-model overrides at dispatch (Step 3) |

**Canonical complexity enum for telemetry**: `TRIVIAL | SIMPLE | MODERATE |
COMPLEX` — never `MEDIUM`, never `SUCCESS` for status (it's `PASS`). The
telemetry already contains drifted labels from older runs; do not add more.

Report:

```
Issue #184 classified as: SIMPLE (backend)
Using workflow: MAP-PLAN → PATCH → PROVE
```

### Step 1.0.1: Reject TRIVIAL — Redirect to /quick

After classification, if `TIER=TRIVIAL`, exit immediately with a clear pointer
to `/quick`. The full MAP-PLAN → PATCH → PROVE pipeline is over-ceremonious
for a typo-class change.

```bash
if [ "$TIER" = "TRIVIAL" ]; then
  echo "Issue #${ISSUE} classified as TRIVIAL — full orchestrate pipeline is over-ceremonious."
  echo ""
  echo "Use /quick instead:"
  echo "  /quick \"${ISSUE_TITLE}\""
  echo ""
  echo "TRIVIAL work (typo, single-config-line fix, obvious one-file change) doesn't"
  echo "need MAP-PLAN/PATCH/PROVE artifacts. /quick handles it directly without"
  echo "branching, agent dispatches, or PR ceremony for changes that don't warrant them."
  exit 0
fi
```

If you genuinely want the full pipeline for a TRIVIAL issue (tracking,
artifacts, parallel-wave bookkeeping), manually upgrade the classification to
SIMPLE before re-running.

### Step 1.1: Decide Codex Escalation

Apply the right-sized rule from `~/.claude/rules/implementation-routing.md`:

| Tier | Codex Use |
|------|-----------|
| TRIVIAL | Skip |
| SIMPLE | Skip by default; offer only if auth/data/API risk appears |
| MODERATE | Run or recommend `/codex:adversarial-review` after PROVE |
| COMPLEX | Recommend `/codex:adversarial-review` after PROVE |
| FULLSTACK | Use `/codex:adversarial-review` after PROVE with contract/API/enum focus |
| PRIOR FAIL | Use `/codex:rescue` as second-model rescue before another retry |

Do not run Codex just because it exists. The review must reduce concrete risk.

### Step 1.5: Detect Stack

After MAP-PLAN (or MAP), scan its artifact for stack scope:

```bash
PLAN_FILE=$(ls .agents/outputs/{map-plan,plan}-${ISSUE}-*.md 2>/dev/null | head -1)
HAS_BACKEND=$(grep -l "backend/" "$PLAN_FILE" 2>/dev/null)
HAS_FRONTEND=$(grep -l "frontend/" "$PLAN_FILE" 2>/dev/null)

if [ -n "$HAS_BACKEND" ] && [ -n "$HAS_FRONTEND" ]; then
  STACK="fullstack"
elif [ -n "$HAS_FRONTEND" ]; then
  STACK="frontend"
else
  STACK="backend"
fi
```

**If STACK=fullstack**: CONTRACT is MANDATORY. Report:

```
Stack auto-detected: fullstack (plan touches backend/ and frontend/)
CONTRACT agent will run before PLAN-CHECK.
```

### Step 1.6: CONTRACT Weight Assessment (fullstack only)

| Signal | CONTRACT-lite (inline) | CONTRACT-full (agent) |
|--------|------------------------|----------------------|
| New endpoints | 0 | 1+ |
| Enum changes | 0-1 | 2+ |
| Breaking API changes | No | Yes |
| Frontend files touched | 1-2 | 3+ |

**CONTRACT-lite**: Skip the CONTRACT agent. Add an inline contract section to the PATCH prompt instead.
**CONTRACT-full**: Spawn CONTRACT agent (see pipeline reference).

### Step 1.7: Check for File Conflicts with Open PRs

```bash
OPEN_PR_FILES=$(gh pr list --state open --json files --jq '.[].files[].path' 2>/dev/null | sort -u)
PLAN_FILES=$(grep -oP '`[^`]+\.(py|jsx?|tsx?|md|json)`' .agents/outputs/{map-plan,plan}-${ISSUE}-*.md 2>/dev/null | tr -d '`' | sort -u)
CONFLICTS=$(comm -12 <(echo "$OPEN_PR_FILES") <(echo "$PLAN_FILES"))

if [ -n "$CONFLICTS" ]; then
  echo "WARNING: File conflicts with open PRs:"
  echo "$CONFLICTS"
fi
```

Also check active worktrees for file overlap (especially in `--parallel` mode) using `worktree_manager.check_file_conflicts`. Warn but don't block.

### Step 2: Create Feature Branch

If `--parallel`: Branch was already created by worktree setup. Skip.

Otherwise:

```bash
BRANCH=$(git branch --show-current)
if [ "$BRANCH" = "main" ]; then
  git checkout -b feature/issue-$ISSUE-description
fi
```

### Step 2.5: Initialize Task Tracking (TaskCreate)

After classification and stack detection, before agent dispatch, register a
TaskCreate todo list with one task per phase that will actually run. This
surfaces progress as a visible checklist instead of burying it in tool output.

**Phases to register** (omit any flag-gated or stack-gated phase not running):

| Tier | Tasks in order |
|------|----------------|
| SIMPLE  | DISCUSS¹ → MAP-PLAN → TEST-PLANNER¹ → CONTRACT² → PLAN-CHECK → PATCH → PROVE → Record-Outcome |
| COMPLEX | DISCUSS¹ → MAP → PLAN → TEST-PLANNER¹ → CONTRACT² → PLAN-CHECK → PATCH → PROVE → Record-Outcome |

¹ Only when the corresponding flag is set (`--discuss`, `--with-tests`).
² Only when CONTRACT-full applies (Step 1.6). CONTRACT-lite is inline — no task.

**Per task**:
- `subject`: phase + issue, e.g. `"MAP-PLAN issue #184"`
- `description`: one-line phase purpose
- `activeForm`: gerund for the spinner, e.g. `"Running MAP-PLAN"`

**Dependencies**: chain sequentially with `addBlockedBy`. Exception: documented
parallel patterns from Step 1.7's swarm table (e.g. PLAN-CHECK + TEST-PLANNER
fan-out) share a single upstream blocker and do not block each other.

**During Step 3 dispatch**: before each `Task()` call, mark the corresponding
task `in_progress`. After artifact validation passes, mark it `completed`. If
a phase fails, leave the task `in_progress` and STOP per Failure Handling —
the in-flight task documents where the run halted.

**At Step 5**: every task should be `completed`. `Record-Outcome` wraps Step 4.

Skip this step entirely on `--resume` runs unless the resumed phase has no
existing task (re-create only the missing tail of the chain).

### Step 2.8: Recall Project Memory (once per workflow)

Project-memory fact *bodies* are not auto-loaded into subagents. Recall the
relevant ones **once** here and inject them into every phase prompt via the
`{PROJECT_MEMORY_BLOCK}` variable (see `templates/agent-prompt.md`), so MAP /
PLAN / PATCH / PROVE all inherit the same curated context without each running
the CLI:

```bash
~/agents/bin/memory recall "<issue title + key entities/subsystem terms>" --compact --limit 8
```

- Use the issue title plus any distinctive nouns (entity, feature, file/module
  names) as the query.
- Capture the output verbatim as `{PROJECT_MEMORY_BLOCK}`. If it's empty, set
  the block to `(no project-memory facts matched this issue)`.
- The block is a compact index (paths + descriptions), not bodies — agents
  Read the full body of any fact that bears on their work (honors the
  Context-Isolation rule in `templates/agent-prompt.md`).
- On `--resume`, reuse the block if already captured; otherwise re-recall.

### Step 3: Spawn Agents (Task Tool)

**CRITICAL**: Use the Task tool to spawn each phase agent via **native subagent
dispatch**. Each phase agent (MAP, PLAN, PATCH, PROVE, etc.) is a registered
Claude Code subagent at `~/.claude/agents/<file>.md` with a frontmatter
`name:` of `orchestrate-<phase>`. Invoke as:

```python
Task(
    description='<phase> for issue <N>',
    subagent_type='orchestrate-<phase>',  # registered name
    prompt=AGENT_PROMPT,                   # context only — no instructions
    # model=...  ← ONLY per the routing table below; omit otherwise
)
```

Claude Code auto-loads the agent body, applies the agent's `tools:` restriction,
and uses the agent's `model:` frontmatter unless the dispatch overrides it.
Do NOT include "read your instructions from agents/X.md" in the prompt — the
agent body is loaded automatically.

#### Model Routing (#387) — right model for the right step

Frontmatter defaults serve SIMPLE/MODERATE (65%+ of runs — the cheap path).
On COMPLEX and FULLSTACK, override at dispatch: plan errors cascade into
PATCH+PROVE recycles (the most expensive place to be wrong), implementation
correctness is the historical failure bottleneck, and verification rigor
must scale with blast radius (50/50 COMPLEX PASS with 3 lifetime PROVE
blocks is a leniency smell, not a quality proof).

| Phase | SIMPLE / MODERATE | COMPLEX / FULLSTACK |
|-------|-------------------|---------------------|
| MAP-PLAN | sonnet (frontmatter) | — |
| MAP | — | sonnet (frontmatter) |
| PLAN | — | **`model="opus"`** at dispatch |
| PLAN-CHECK | haiku (frontmatter) | haiku (frontmatter) |
| CONTRACT | sonnet (frontmatter) | **`model="opus"`** when FULLSTACK |
| TEST-PLANNER | sonnet (frontmatter) | sonnet (frontmatter) |
| PATCH | sonnet (frontmatter) | **`model="opus"`** at dispatch |
| PROVE | sonnet (frontmatter) | **`model="opus"`** at dispatch |
| DISCUSS | sonnet (frontmatter) | sonnet (frontmatter) |

- "opus" means the strongest model tier available to the session — if the
  main loop is running a stronger model (e.g. Fable), pass that instead
  (`model="fable"`); never dispatch a COMPLEX PLAN/PATCH/PROVE on a model
  weaker than sonnet.
- Do NOT override upward on SIMPLE/MODERATE "just to be safe" — the tiering
  IS the safety design; upgrading everything reintroduces the cost of having
  no tiers.
- PRIOR-FAIL retries (same issue, second attempt after a PROVE FAIL):
  upgrade PATCH one tier (sonnet → opus-class) regardless of complexity —
  failed work gets a different (stronger) model, per
  `implementation-routing.md`.

For per-agent dispatch tables, validation gates, and failure-context injection,
**read `templates/orchestrate-pipeline.md`**.

For parallel patterns (MAP fan-out, speculative PATCH, parallel fullstack PATCH,
worktree setup, resume mode), **read `templates/orchestrate-parallel.md`**.

### Step 4: Record Outcome (MANDATORY)

**This is the canonical outcome-recording site.** PROVE specifies the data
via its artifact frontmatter (`status`, `complexity`, `stack`, `agents_run`,
`ac_audit`, `applicable_evals`, `eval_results`, and — if BLOCKED —
`root_cause`, `blocking_agent`, `files`, `prevention`); this step performs
the deterministic write. PROVE does NOT write to `.claude/memory/` directly
(see issue #104 — embedding the write in PROVE's prompt was unreliable).

**AC-FORBIDS-APPROVE (issue #1612)**: this step also runs
`state_manager.validate_ac_audit` on PROVE's `ac_audit` frontmatter. A
PROVE artifact that emitted `status: PASS` is downgraded to `status: FAIL`
when the audit finds any `missing` / `partial` entry, or any `deferred`
entry whose evidence does not cite a follow-up issue # (`#NNNN` or
`GH-NNNN`). The downgrade reason is persisted in `prove-log.jsonl`. PROVE
cannot defeat the rule by emitting `PASS` directly — the validator is
authoritative.

`agents_run` is **derived from `.agents/outputs/`** by scanning for
`<phase>-<issue>-<mmddyy>.md` artifacts and sorting by mtime — the
artifact directory IS the ground truth for what ran, not state tracked
across phase dispatches (the orchestrator command is stateless between
Task() calls; see issue #107). The `$AGENTS_RUN_JSON` env var is no
longer used.

After PROVE returns, parse its artifact frontmatter and call the
`state_manager` helpers:

```bash
PROVE_ART=$(ls .agents/outputs/prove-${ISSUE}-*.md 2>/dev/null | tail -1)
if [ -z "$PROVE_ART" ] || [ ! -f "$PROVE_ART" ]; then
  echo "WARNING: no PROVE artifact found for issue ${ISSUE}; skipping outcome recording"
else
  python3 - <<PYEOF
import sys, re, subprocess
sys.path.insert(0, '$HOME/.claude/hooks')
from pathlib import Path
from state_manager import (
    count_acceptance_bullets,
    derive_agents_run,
    record_failure,
    record_metrics,
    record_prove_audit,
    validate_ac_audit,
)

# YAML is preferred (per issue #1612 the frontmatter has nested
# ac_audit/applicable_evals/eval_results structures). Fall back to a
# best-effort regex for scalar fields when yaml is unavailable.
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

art = Path("$PROVE_ART").read_text(encoding="utf-8")
fm_match = re.search(r"^---\n(.*?)\n---", art, re.DOTALL | re.MULTILINE)
fm_text = fm_match.group(1) if fm_match else ""

fm_data = {}
if HAS_YAML and fm_text:
    try:
        parsed = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        parsed = None
    # Codex-side concern: yaml.safe_load can return a string/list/None for
    # syntactically valid non-map frontmatter — normalize to dict so
    # downstream .get calls don't crash.
    if isinstance(parsed, dict):
        fm_data = parsed

def field(name, default=None):
    """Get a scalar field. Prefers parsed yaml; falls back to regex."""
    if name in fm_data and not isinstance(fm_data[name], (list, dict)):
        return fm_data[name]
    m = re.search(rf"^{name}:\s*(.+)$", fm_text, re.MULTILINE)
    return m.group(1).strip() if m else default

status     = field("status", "PASS")
complexity = "$COMPLEXITY" or field("complexity", "SIMPLE")
stack      = "$STACK"      or field("stack", "backend")
agents_run = derive_agents_run(Path("."), int("$ISSUE"))
if not agents_run:
    print(f"Warning: no artifacts found for issue $ISSUE; recording with empty agents_run")
    agents_run = []
root_cause = field("root_cause") if status == "BLOCKED" else None

# Issue #1612 — per-AC audit. Validate before recording so the verdict
# we persist reflects AC-FORBIDS-APPROVE.
ac_audit         = fm_data.get("ac_audit")
applicable_evals = fm_data.get("applicable_evals") or []
eval_results     = fm_data.get("eval_results") or {}

# Coverage gate: fetch the issue body and count its AC bullets so the
# validator can detect "PROVE silently omitted an AC" (Codex R1 finding).
# Network/gh failure → fall back to 0 (skip the count check; emit-only
# validation still catches missing/partial/deferred-no-#).
expected_ac_count = 0
try:
    body = subprocess.run(
        ["gh", "issue", "view", str(int("$ISSUE")), "--json", "body", "--jq", ".body"],
        check=True, capture_output=True, text=True, timeout=15,
    ).stdout
    expected_ac_count = count_acceptance_bullets(body)
except (subprocess.SubprocessError, FileNotFoundError, ValueError):
    expected_ac_count = 0

downgrade_reason = None
if status == "PASS":
    audit = validate_ac_audit(
        ac_audit if isinstance(ac_audit, list) else None,
        expected_ac_count=expected_ac_count or None,
    )
    if audit.get("downgrade_to") == "FAIL":
        downgrade_reason = "; ".join(
            f"{m['ac']}: {m['reason']}" for m in audit.get("missing", [])
        )
        status = "FAIL"
        print(f"PROVE PASS downgraded to FAIL: {downgrade_reason}")

record_metrics(
    Path("."), int("$ISSUE"), status, complexity, stack, agents_run,
    root_cause=root_cause,
    blocking_agent=("PROVE" if status in ("BLOCKED", "FAIL") else None),
)

# Always log the per-AC audit row, regardless of verdict — clean PASS
# runs are also valuable signal for the recurring-pattern detector.
record_prove_audit(
    Path("."), int("$ISSUE"), status,
    ac_audit if isinstance(ac_audit, list) else [],
    applicable_evals=applicable_evals if isinstance(applicable_evals, list) else None,
    eval_results=eval_results if isinstance(eval_results, dict) else None,
    downgrade_reason=downgrade_reason,
)

if status == "BLOCKED" and root_cause:
    # PROVE artifact may include a "## Failure Details" section with files /
    # prevention / details / fix. Best-effort extraction; missing fields are OK.
    def section(name):
        m = re.search(rf"^{name}:\s*(.+)$", art, re.MULTILINE)
        return m.group(1).strip() if m else None
    record_failure(
        Path("."), int("$ISSUE"), root_cause,
        files=None, agent="PATCH",
        prevention=section("prevention"),
        details=section("details"),
        fix=section("fix"),
    )
print(f"Recorded outcome for issue {sys.argv[0] or '$ISSUE'}: {status}")
PYEOF
fi
```

If PROVE's frontmatter is malformed, `record_metrics` still writes a minimal
record with sensible defaults (`status=PASS`, `complexity=SIMPLE`,
`stack=backend`) — partial data > no data. If no artifacts are found for
the issue, `agents_run` is recorded as `[]` (clearly wrong, easy to filter
out later) rather than a hardcoded but plausible default that would lie
about what actually ran. The helpers fail open on IOError; losing one
metric line never fails the orchestrate run.

**FAIL halts the workflow (#360).** A recorded verdict of `FAIL` or `BLOCKED`
(including a PASS downgraded by AC-FORBIDS-APPROVE) means the workflow STOPS
here: report the verdict and the failing ACs, do NOT hand off to `/ship`, do
NOT merge. The same verdict is independently enforced at merge time by
`scripts/prove_gate.py` (ship.md Step 7.5), so a FAIL that slips past this
step is still caught — but the orchestrator should never rely on that
backstop deliberately. Fix, re-run PATCH/PROVE, and only then ship.

### Step 5: Report Status

```
✓ Workflow complete for issue #184

Artifacts:
- map-plan-184-010325.md
- patch-184-010325.md
- prove-184-010325.md

PROVE status: PASS ✅
Outcome recorded: ✅ metrics.jsonl (+1 line)
Codex review: skipped | recommended | complete

Next: /pr 184 to create pull request
```

---

## Failure Handling

If any agent fails:

1. STOP workflow
2. Report which agent failed
3. Show expected artifact path
4. Do NOT proceed

If PROVE returns BLOCKED, **Step 4 records** the failure to
`.claude/memory/failures.jsonl` (orchestrator-driven write — not PROVE).
Subsequent runs of `/orchestrate $ISSUE` automatically inject failure
context into the PATCH prompt by reading from that file.

---

## Artifacts

All outputs go to `.agents/outputs/`:
- `map-{issue}-{mmddyy}.md`
- `map-plan-{issue}-{mmddyy}.md`
- `plan-{issue}-{mmddyy}.md`
- `test-plan-{issue}-{mmddyy}.md` (if --with-tests)
- `contract-{issue}-{mmddyy}.md`
- `plan-check-{issue}-{mmddyy}.md`
- `patch-{issue}-{mmddyy}.md`
- `prove-{issue}-{mmddyy}.md`

---

## Rules

**MUST**:
- Require GitHub issue
- Use Task tool for agents
- Validate artifacts before proceeding
- Enforce `.claude/rules.md`

**MUST NOT**:
- Implement features yourself
- Edit code directly
- Skip verification gates
