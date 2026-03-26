# Agentic Engineering — Training Curriculum

> **Target Audience**: Senior developers who are new to AI-assisted development and want to build a systematic, repeatable workflow — not just chat with an AI.
>
> **Synthesized from**: Two workflow extractions — personal Mac (macOS, Apple Silicon) and enterprise WSL2 (Dell workstation, Ubuntu on Windows). The practices described here are battle-tested across both environments and multiple production projects.
>
> **Last Updated**: 2026-03-26

---

## Module 1: Foundations

### What Is Agentic Engineering?

Agentic Engineering is the discipline of designing systems where AI coding agents autonomously execute multi-step software development tasks — investigation, planning, implementation, and verification — with structured feedback loops that improve performance over time.

It is **not** prompt engineering. Prompt engineering optimizes a single request-response cycle. Agentic Engineering designs the entire workflow: which agent runs when, what artifacts flow between agents, how failures are recorded, and how the system learns from them.

**Key distinction**:

| Prompt Engineering | Agentic Engineering |
|-------------------|---------------------|
| Optimizes one prompt | Designs multi-agent pipelines |
| One-shot interaction | Multi-phase workflow with state |
| Manual iteration | Automated verification gates |
| Knowledge stays in your head | Knowledge captured in patterns, metrics, rules |
| Each session starts fresh | Sessions resume from persisted state |

### How AI Coding Agents Work

AI coding agents like Claude Code operate within three fundamental constraints:

**1. Context Windows**

The context window is the agent's working memory — everything it can "see" at once. This includes your instructions, the conversation history, file contents, and tool results. When the context fills up, older content gets compressed or dropped.

This creates a core engineering challenge: **every token of instructions competes with code context**. A 767-line architecture rule loaded unnecessarily costs the same as 767 lines of code the agent could have been reading instead.

Practical implications:
- Tier your rules (always-loaded vs conditional)
- Keep agent artifacts within line limits
- Use compact state formats (YAML, not markdown dumps)
- Measure and optimize token budgets

**2. Tools**

Agents interact with your system through tools — Read files, Write files, Edit files, run Bash commands, search with Grep/Glob, spawn sub-agents, and call MCP servers. The agent decides which tools to call and in what order.

This means the agent's effectiveness depends heavily on what tools are available and what information those tools surface. A well-configured MCP server that surfaces current library documentation eliminates entire categories of hallucination.

**3. Hooks**

Hooks are lifecycle events that fire at specific moments: session start, before context compaction, on task completion. You attach scripts to these events to manage state persistence, inject context, and enforce quality gates.

Hooks are the mechanism that turns a stateless chat session into a stateful development workflow. Without them, every session starts from zero.

### The Shift from Prompt Engineering to Agent Engineering

When you "chat with an AI," you're the orchestrator. You decide what to do next, what to check, when to stop. The AI is a tool you wield.

In Agentic Engineering, the AI is a team of specialized agents, each with defined roles, inputs, outputs, and verification gates. You design the pipeline once, then execute it repeatedly across issues.

**What you engineer**:
- Agent definitions (role, constraints, output format)
- Artifact chains (what flows from one agent to the next)
- Validation gates (what must pass before proceeding)
- Failure recording (how problems become data)
- Learning loops (how data becomes prevention)

**What you stop doing**:
- Manually reminding the AI about project structure
- Repeating the same instructions every session
- Hoping the AI checked its work
- Tracking successes and failures in your head

---

## Module 2: Environment Setup

### Portable Configuration Architecture

The core insight: all AI agent configuration should be **version-controlled in a single git repository** and **deployed via symlinks** to the locations where tools expect to find them.

This solves three problems simultaneously:
1. **Reproducibility** — Any machine can be set up identically in one command
2. **Synchronization** — `git pull` propagates changes to all machines
3. **History** — Git log shows when and why every configuration changed

### The ~/agents/ Repository Pattern

```
~/agents/                           # Single git repo — source of truth
├── claude-config/                  # Claude Code configuration package
│   ├── agents/                     # Agent definitions (.md files)
│   ├── commands/                   # Slash commands (.md files)
│   ├── hooks/                      # Lifecycle hooks + shared modules (Python)
│   │   ├── state_manager.py        #   Centralized YAML state management
│   │   ├── worktree_manager.py     #   Git worktree lifecycle (--parallel)
│   │   ├── notify_completion.py    #   macOS/iPhone notifications (Stop hook)
│   │   ├── verify_completion.py    #   Anti-rationalization (Stop hook)
│   │   ├── precompact_checkpoint.py#   State extraction (PreCompact hook)
│   │   └── sessionstart_restore_state.py # Context restore (SessionStart)
│   ├── rules/                      # Conditional rules (.md files)
│   ├── skills/                     # Multi-step workflow skills
│   ├── templates/                  # Prompt templates for agent spawning
│   │   └── agent-prompt.md         #   Shared agent prompt with variable substitution
│   ├── settings.json               # Global settings (hooks, MCP, permissions)
│   ├── statusline.py               # Custom status bar
│   └── install.sh                  # Idempotent symlink installer
├── codex-config/                   # Secondary tool configuration
├── mcp-server/                     # Custom MCP server (metrics, vault access)
├── obsidian-agent/                 # Session → knowledge base writer
├── code-review/                    # Pre-commit review agent
├── pr-changelog/                   # Post-merge changelog automation
├── daily-standup/                  # Standup report generator
├── doc-reader/                     # Document TTS
├── youtube-summarizer/             # Video → transcript → summary
└── install-all.sh                  # One-command setup for everything
```

The companion projects (obsidian-agent, code-review, etc.) are standalone tools that integrate with the main workflow through shared data: session JSONL files, Obsidian vault entries, and metrics files.

### Symlink-Based Deployment

The `install.sh` script creates symlinks from where Claude Code expects configuration to where the git repo stores it:

```
~/.claude/agents/    →  ~/agents/claude-config/agents/
~/.claude/commands/  →  ~/agents/claude-config/commands/
~/.claude/hooks/     →  ~/agents/claude-config/hooks/
~/.claude/rules/     →  ~/agents/claude-config/rules/
~/.claude/skills/    →  ~/agents/claude-config/skills/
~/.claude/settings.json  →  ~/agents/claude-config/settings.json
```

**What gets symlinked** (shared across machines):
- Agent definitions, commands, hooks, rules, skills
- Global settings (hooks, permissions, MCP servers that use portable paths)

**What stays local** (machine-specific):
- `settings.local.json` — MCP servers with machine-specific paths
- `memory/` — Learned patterns specific to this machine's projects
- `projects/` — Per-project session data

The installer is idempotent — safe to run repeatedly. It detects the platform (macOS, WSL, Linux), backs up existing files, creates symlinks, installs dependencies (MCP server venv, PyYAML), and verifies the installation.

### Multi-Machine Synchronization

**Initial setup** (any new machine):
```bash
git clone https://github.com/<you>/agents.git ~/agents
cd ~/agents && ./install-all.sh
```

**Propagating changes** (after editing agents/commands/rules on any machine):
```bash
cd ~/agents && git add -A && git commit -m "feat: Add enum check to PATCH agent"
git push
# On other machines:
cd ~/agents && git pull
# Symlinks mean changes are live immediately — no re-install needed
```

**Platform-specific handling**:
- macOS: Auto-detects iCloud Drive path for Obsidian vault
- WSL: Uses Windows-side vault path (`/mnt/c/Users/.../Obsidian`)
- Linux: Local vault path

**Machine-local overrides**: `settings.local.json` is not symlinked. Each machine can configure its own MCP servers (e.g., vault-metrics with local paths) without affecting other machines.

---

## Module 3: The Orchestrate Pattern

### Issue-Driven Development with Agents

Every piece of work starts as a GitHub issue. The `/orchestrate` command takes an issue number and executes a multi-agent pipeline to implement it:

```bash
/orchestrate 184                    # Standard workflow
/orchestrate 184 --with-tests       # Include test planning phase
/orchestrate 184 --resume           # Resume from last completed phase
/orchestrate 184 --parallel         # Run in isolated git worktree
/orchestrate 184 --parallel --resume # Resume in existing worktree
```

The issue provides scope boundaries. Agents are instructed to implement exactly what the issue describes — no more, no less. This prevents scope creep, one of the tracked failure patterns.

| Flag | Purpose |
|------|---------|
| `--with-tests` | Include TEST-PLANNER phase for test matrix generation |
| `--resume` | Skip already-completed phases (reads `completed_phases` from state) |
| `--parallel` | Run in isolated git worktree for concurrent issue processing |

For quick fixes that don't warrant the full pipeline:
```bash
/quick "fix the login redirect"     # Ad-hoc, no agents spawned
```

### Agent Pipeline Design

```
TRIVIAL:   MAP-PLAN → PATCH → PROVE-lite (gates only)
SIMPLE:    MAP-PLAN → [TEST-PLANNER] → CONTRACT* → PLAN-CHECK → PATCH → PROVE
COMPLEX:   MAP → PLAN → [TEST-PLANNER] → CONTRACT* → PLAN-CHECK → PATCH → PROVE

* CONTRACT mandatory for fullstack (CONTRACT-lite for simple fullstack)
[ ] = optional with --with-tests
```

**Pipeline Decision Flow**:

```
                    ┌──────────────┐
                    │ GitHub Issue  │
                    └──────┬───────┘
                           │
                ┌──────────┴──────────┐
                │  Classify Complexity │
                └──────────┬──────────┘
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
       ┌─────────┐   ┌─────────┐   ┌──────────┐
       │ TRIVIAL  │   │ SIMPLE  │   │ COMPLEX  │
       │ 1-2 files│   │ 3-5 files│  │ 6+ files │
       └────┬─────┘   └────┬─────┘  └────┬─────┘
            │              │              │
            ▼              ▼              ▼
       MAP-PLAN        MAP-PLAN      MAP → PLAN
            │              │              │
            │         ┌────┴────┐    ┌────┴────┐
            │         │fullstack?│   │fullstack?│
            │         └────┬────┘   └────┬────┘
            │          yes │ no      yes │ no
            │              ▼             ▼
            │         CONTRACT(*)    CONTRACT
            │              │             │
            │         PLAN-CHECK    PLAN-CHECK
            │              │             │
            ▼              ▼             ▼
         PATCH          PATCH         PATCH
            │              │             │
            ▼              ▼             ▼
       PROVE-lite       PROVE         PROVE
       (gates only)        │             │
            │              ▼             ▼
            └──────────── /pr ───────────┘

  (*) CONTRACT-lite (inline) if 0 new endpoints + ≤2 frontend files
      CONTRACT-full (agent) otherwise
```

**Why these phases exist**:

| Phase | Purpose | Key Insight |
|-------|---------|-------------|
| **MAP / MAP-PLAN** | Investigate before acting | 63% of failures come from not reading code first |
| **PLAN** | Design before implementing | Separates architecture decisions from coding |
| **TEST-PLANNER** | Define success before coding | Edge cases discovered before implementation, not after |
| **CONTRACT** | Agree on interface before parallel work | Prevents frontend/backend divergence |
| **PLAN-CHECK** | Validate plan against codebase | Catches plan gaps before PATCH burns context |
| **PATCH** | Implement with verification gates | Pre-flight checklists + pre-submission gates |
| **PROVE** | Verify and record outcome | Evidence-based completion + learning data |

The read-only phases (MAP, MAP-PLAN, PLAN, CONTRACT, TEST-PLANNER, PLAN-CHECK) cannot break anything. They investigate and design. Only PATCH modifies code. This separation means investigation happens before implementation, catching problems when they're cheapest to fix.

### Complexity Classification and Routing

| Complexity | Criteria | Agent Path |
|------------|----------|------------|
| **TRIVIAL** | Single file, obvious change | MAP-PLAN → PATCH → PROVE-lite |
| **SIMPLE** | 2–5 files, clear pattern to follow | MAP-PLAN → [PLAN-CHECK] → PATCH → PROVE |
| **COMPLEX** | 6+ files, architectural decisions, multi-layer | MAP → PLAN → [PLAN-CHECK] → PATCH → PROVE |

The MAP agent classifies complexity after investigating the codebase. **TRIVIAL** issues skip PLAN-CHECK and use PROVE-lite (verification gates only, no Level 2-3 checks). SIMPLE issues use MAP-PLAN (combined investigation + planning in one phase). COMPLEX issues split into separate MAP and PLAN phases for deeper analysis.

### Artifact Chains and Validation Gates

Each agent produces a named artifact:

```
map-plan-184-030826.md  →  contract-184-030826.md  →  plan-check-184-030826.md
                                                              ↓
                                                     patch-184-030826.md
                                                              ↓
                                                     prove-184-030826.md
```

**Naming convention**: `{agent}-{issue}-{mmddyy}.md` in `.agents/outputs/`

**Validation**: Each agent checks that its required predecessor artifact exists before starting. If PATCH can't find a MAP-PLAN or PLAN artifact, it **stops** and reports the gap. If PATCH detects fullstack work but can't find a CONTRACT artifact, it **stops** immediately.

This chain ensures no agent operates on assumptions — every agent has explicit, documented input from the previous phase.

### Parallel Execution Strategies

#### Within a Session (Agent-Level Parallelism)

Certain phases can run concurrently because they have independent inputs and outputs:

| Pattern | What Runs in Parallel | Why It's Safe |
|---------|----------------------|---------------|
| Investigation fan-out | MAP + TEST-PLANNER | Same input (issue), separate outputs |
| Speculative PATCH | PLAN-CHECK + PATCH | SIMPLE backend: PATCH starts before PLAN-CHECK finishes |
| Fullstack PATCH | Backend PATCH + Frontend PATCH | Separate scopes, CONTRACT defines interface |
| PROVE verification | Backend tests + Frontend build | Independent test suites |

The CONTRACT artifact is what makes parallel fullstack PATCH possible — it's the shared interface specification that both sides implement against.

**Speculative PATCH**: For SIMPLE backend-only issues, PATCH can start speculatively alongside PLAN-CHECK. If PLAN-CHECK passes (~90% of the time), the PATCH result is valid — saving one full agent cycle. If PLAN-CHECK fails, PATCH is rolled back via `git checkout -- . && git clean -fd`.

#### Across Sessions (Worktree-Level Parallelism) — `--parallel` flag

Run multiple independent issues simultaneously using git worktree isolation:

```
Terminal Tab 1                    Terminal Tab 2
─────────────                    ─────────────
/orchestrate 42 --parallel       /orchestrate 57 --parallel
     │                                │
     ▼                                ▼
.worktrees/issue-42/             .worktrees/issue-57/
├── backend/  (isolated copy)    ├── backend/  (isolated copy)
├── frontend/ (isolated copy)    ├── frontend/ (isolated copy)
└── .agents/outputs/ (isolated)  └── .agents/outputs/ (isolated)
     │                                │
     ▼                                ▼
PR from worktree branch          PR from worktree branch
     │                                │
     ▼                                ▼
macOS notification ──────────── macOS notification
     │                                │
     ▼                                ▼
Merge → worktree removed        Merge → worktree removed
```

**How it works**:
1. `--parallel` creates a git worktree at `.worktrees/issue-{N}/` branched from `origin/main`
2. All agents run inside the worktree (isolated files, git index, and artifacts)
3. State tracking uses the **main repo** (not worktree) so `--resume` can find the worktree
4. Step 1.7 checks both active worktrees AND open PRs for file overlap
5. After PR merge, `/pr` cleans up the worktree via `git worktree remove`

**When NOT to parallelize**: Issues that touch the same files, schema migrations (ordering matters), or when Step 1.7 detects file overlap.

---

## Module 4: Writing Effective CLAUDE.md Files

### What to Include

Every project should have a `CLAUDE.md` at the root. This is the primary instruction set for AI agents working in your codebase. Based on patterns across multiple production projects, include:

**1. Project Overview** — What it is, what it's not, who uses it
```markdown
## Overview
Multi-tenant financial planning platform. Firm → Advisor → Client hierarchy.
```

**2. Development Commands** — How to set up, run, test, lint
```markdown
## Development
cd backend && ruff check . && pytest -q     # Backend
cd frontend && npm run check                # Frontend (format + lint + test + build)
```

**3. Architecture** — Layered pattern, module structure, data flow
```markdown
## Architecture
Layered: Router → Service → Repository → DB
Module layout: models.py, schemas.py, repository.py, services.py, deps.py, router.py
```

**4. Technology Stack** — Versions, key dependencies
```markdown
## Stack
- Backend: FastAPI, SQLAlchemy 2.0, Pydantic v2, PostgreSQL
- Frontend: React 19, Vite, Tailwind CSS, React Query
```

**5. Project Structure** — Directory layout with descriptions (mark immutable)
```markdown
## Structure (IMMUTABLE — do not reorganize)
backend/backend/    # Flat layout — NEVER create backend/src/
frontend/src/       # React application
```

**6. Forbidden Changes** — Things agents must never do
```markdown
## Forbidden
- NEVER create src/, lib/, or pkg/ directories
- NEVER push to production branch without explicit request
- NEVER use PostgreSQL-specific syntax in tests (SQLite only)
```

**7. Key Configuration** — Environment variables, defaults, credentials for testing

### Forbidden Patterns and Guardrails

The most effective CLAUDE.md entries are **explicit prohibitions** that prevent known failure modes:

| Guardrail | Prevents |
|-----------|----------|
| "NEVER create `backend/src/`" | STRUCTURE_VIOLATION (agents will reorganize if not told otherwise) |
| "Always filter by `account_id`" | ACCESS_CONTROL (multi-tenant data leaks) |
| "Use `require_account_owner` from deps" | Inline permission checks (inconsistent enforcement) |
| "Tests use SQLite in-memory only" | SQLITE_COMPAT (PostgreSQL-only features in tests) |
| "Single source of truth: `pyproject.toml`" | Version drift (agents creating new version files) |

### Architecture Documentation That Agents Can Act On

The most useful architecture documentation is **actionable** — it tells the agent exactly what pattern to follow:

**Good** (actionable):
```markdown
## Module Structure
module/
├── models.py      # SQLAlchemy 2.0 (UUID PK, TimestampMixin)
├── schemas.py     # Pydantic v2 (ConfigDict, from_attributes=True)
├── repository.py  # Never commits — service calls commit()
├── services.py    # Business logic — raises AppError, not HTTPException
├── deps.py        # Access control via Depends()
└── router.py      # Thin — calls service, returns response
```

**Bad** (vague):
```markdown
We use a layered architecture with separation of concerns.
```

### The "Read Before Assuming" Principle

This single principle prevents 63% of all agent failures. Encode it in your CLAUDE.md:

```markdown
## Critical Rule
Before using any existing component, hook, enum, or service:
1. Read the actual source file
2. Verify the API (props, return type, accepted values)
3. Never assume — always confirm
```

This matters because AI agents have training data about common patterns, but your codebase has specific implementations that may differ. An agent "knows" that `useSession()` typically returns `{ session, loading }` — but your hook might return the session directly.

---

## Module 5: Hooks & Lifecycle Management

### Session Continuity (PreCompact → SessionStart)

The fundamental problem: Claude Code sessions lose state when context is compressed. Without intervention, every context compaction restarts the agent from scratch — no knowledge of the current issue, branch, or phase.

The solution is a two-hook cycle:

**PreCompact Hook** (fires before context compression):
1. Reads last 300 lines of transcript
2. Extracts structured state: issue number, current phase, artifacts created, files modified, pending TODOs, key decisions
3. Delegates to `state_manager.update_from_extracted()` to write PERSISTENT_STATE.yaml:

```yaml
active_work:
  issue: 775
  branch: feature/issue-775-asset-form-fields
  phase: PATCH
  last_action: Implemented backend models
  completed_phases: [MAP-PLAN, PLAN-CHECK]   # enables --resume
  worktree_path: null                         # set when --parallel used
meta:
  updated: '2026-03-26'
```

4. Auto-deletes checkpoints older than 7 days

**SessionStart Hook** (fires when a new session begins):
1. Loads `PERSISTENT_STATE.yaml` via `state_manager.get_active_work()`
2. Loads `patterns-critical.md` (project-first, then global, then `rules/core-patterns.md` as fallback)
3. Detects active orchestrate workflow
4. Outputs continuation instructions

**Notify Completion Hook** (fires when session stops):
1. Platform guard: no-op on non-macOS
2. Reads issue/phase context from `state_manager.get_active_work()`
3. Sends macOS Notification Center alert via `osascript display notification`
4. Notifications auto-forward to iPhone via Handoff

**Result**: ~500 tokens restored (85% reduction from the naive approach of dumping raw transcript summaries at ~3,250 tokens).

### Centralized State Management

All state operations flow through `state_manager.py` — a single module used by hooks, orchestrate, and the `--resume`/`--parallel` flags:

```
┌──────────────────────────────────────────────────────────────┐
│                     state_manager.py                          │
│                                                               │
│  load_state(project_dir)        ← read PERSISTENT_STATE.yaml │
│  update_phase(issue, branch,    ← orchestrate: before agents │
│    phase, action, worktree_path)                              │
│  clear_active(issue)            ← orchestrate: after done    │
│  get_completed_phases(issue)    ← --resume: skip finished    │
│  get_active_work(project_dir)   ← sessionstart + notify      │
│  get_worktree_for_issue(issue)  ← --parallel: find worktree  │
│  update_from_extracted(extracted)← precompact: transcript     │
└──────────────────────────────────────────────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
    orchestrate    precompact    sessionstart     notify
    (commands/)    (hooks/)      (hooks/)         (hooks/)
```

**Why centralized**: Previously, 3 separate codepaths independently manipulated the same YAML file with inline `python3 -c` blocks. A quoting error, missing PyYAML, or malformed YAML would silently break state. Now there's one testable module with graceful fallbacks.

### Anti-Rationalization (Stop Hook)

AI agents exhibit a specific failure mode: they will rationalize that a task is complete when it isn't. Common patterns:
- "The implementation is functionally complete" (but uncommitted)
- "Tests would require additional infrastructure" (but the issue says "add tests")
- "The remaining TODOs are minor" (but they're in the acceptance criteria)

The Stop hook fires when the agent attempts to declare a task complete:

1. **Checks for uncommitted changes** in substantive files (ignoring lock files, config)
2. **Scans for TODO/FIXME/HACK markers** in recently changed lines
3. **Exit code 0** = allow completion (task appears genuinely done)
4. **Exit code 2** = block completion, send feedback listing specific issues

The agent receives the feedback and continues working. This catches premature completion that would otherwise require a human to notice.

### State Extraction and Restoration

What gets extracted (by PreCompact):

| State Element | Source | Example |
|---------------|--------|---------|
| `last_issue` | Most recent issue mentioned | 775 |
| `last_phase` | Most recent phase keyword | PATCH |
| `last_action` | Latest artifact or commit | "patch-775-021126.md created" |
| `pending_tasks` | TODOs from transcript (up to 5) | "Add frontend tests" |
| `key_decisions` | Decision statements (up to 5) | "Using Zustand instead of Redux" |
| `files_modified` | Recent file changes (up to 10) | ["backend/assets/models.py"] |
| `artifacts_created` | Agent artifacts from session | ["map-plan-775-021126.md"] |

What gets restored (by SessionStart):
- Active issue, branch, and phase
- Critical failure patterns (~50 lines)
- Continue instructions if workflow was in progress

### Custom Hook Development

Hooks are Python scripts configured in `settings.json`:

```json
{
  "hooks": {
    "PreCompact": [{"type": "command", "command": "python3 ~/.claude/hooks/precompact_checkpoint.py"}],
    "SessionStart": [{"type": "command", "command": "python3 ~/.claude/hooks/sessionstart_restore_state.py"}],
    "Stop": [
      {"type": "command", "command": "python3 ~/.claude/hooks/verify_completion.py"},
      {"type": "command", "command": "python3 ~/.claude/hooks/notify_completion.py"}
    ]
  }
}
```

**Hook execution flow**:

```
┌─ SessionStart ─────────────────────────────────────────────┐
│  sessionstart_restore_state.py                              │
│  ├─ state_manager.get_active_work() → restore context      │
│  ├─ Load patterns (project → global → core-patterns.md)    │
│  └─ Output ~500 tokens of restored context                 │
└─────────────────────────────────────────────────────────────┘
                          │
                    [Session Work]
                          │
┌─ PreCompact ───────────────────────────────────────────────┐
│  precompact_checkpoint.py                                   │
│  ├─ Extract state from last 300 transcript lines            │
│  ├─ state_manager.update_from_extracted() → save state     │
│  ├─ Save transcript checkpoint for recovery                 │
│  └─ Auto-delete checkpoints > 7 days                       │
└─────────────────────────────────────────────────────────────┘
                          │
                    [Session Stop]
                          │
┌─ Stop (2 hooks, sequential) ───────────────────────────────┐
│  1. verify_completion.py                                    │
│     ├─ Check uncommitted changes                            │
│     ├─ Scan for TODO/FIXME/HACK in diff                    │
│     └─ Exit 2 to block, Exit 0 to allow                   │
│                                                             │
│  2. notify_completion.py                                    │
│     ├─ Platform guard (macOS only, no-op elsewhere)        │
│     ├─ state_manager.get_active_work() → context           │
│     ├─ osascript display notification → Notification Center │
│     └─ Auto-forwards to iPhone via Handoff                 │
└─────────────────────────────────────────────────────────────┘
```

**Design principles for custom hooks**:
- **Fail gracefully** — If PyYAML isn't installed, log a warning and continue, don't crash the session
- **Log errors to file** — `~/.claude/hooks.log` (hooks run silently; without logging, failures are invisible)
- **Keep output compact** — SessionStart output goes directly into context. Every line costs tokens
- **Use exit codes** — Exit 0 = success/allow, Exit 2 = block with feedback message
- **Auto-clean old data** — PreCompact deletes checkpoints >7 days old to prevent disk bloat

---

## Module 6: The Self-Learning Loop

### Structured Failure Recording

Every completed issue gets a record in `metrics.jsonl`:

```json
{
  "issue": 184,
  "date": "2026-02-06",
  "status": "PASS",
  "complexity": "SIMPLE",
  "stack": "fullstack",
  "agents_run": ["MAP-PLAN", "CONTRACT", "PATCH", "PROVE"],
  "agent_versions": {"map-plan": "1.0", "patch": "1.2", "prove": "1.3"},
  "root_cause": null,
  "blocking_agent": null,
  "duration_minutes": 15
}
```

When status is BLOCKED, a detailed record goes to `failures.jsonl`:

```json
{
  "date": "2026-01-06",
  "issue": 156,
  "agent": "MAP-PLAN",
  "root_cause": "VERIFICATION_GAP",
  "details": "Plan deferred spec requirement without checking if spec was updated",
  "fix": "Add after_tax_contributions to DataFrame",
  "prevention": "Always validate spec version matches implementation pattern",
  "files": ["backend/projections/models.py"]
}
```

The PROVE agent writes these records automatically at the end of every workflow. No manual tracking required.

### Root Cause Taxonomy

Every failure gets classified into exactly one canonical code. This enables automated pattern analysis:

| Code | Description | Typical Cause |
|------|-------------|---------------|
| `ENUM_VALUE` | Used enum NAME instead of VALUE | Python `CO_OWNER` vs string `"CO-OWNER"` |
| `COMPONENT_API` | Wrong props or hook usage | Assumed API without reading source |
| `VERIFICATION_GAP` | Assumption not verified by reading code | Skipped spec, assumed structure |
| `MULTI_MODEL` | Forgot to update related model | Changed User but not Advisor relationship |
| `API_MISMATCH` | Frontend/backend contract violation | Schema field type mismatch |
| `ACCESS_CONTROL` | Missing/wrong permission dependency | Endpoint allows access without auth |
| `MISSING_TEST` | Code path not covered | New functionality with 0% coverage |
| `SQLITE_COMPAT` | PostgreSQL-only feature in tests | Used ARRAY type (SQLite incompatible) |
| `STRUCTURE_VIOLATION` | Violated project rules | Created `backend/src/` directory |
| `SCOPE_CREEP` | Beyond issue scope | Added feature not in issue |
| `LINT_ERROR` | Code style violations | Unused imports, formatting |
| `OTHER` | Document specifics in details | Project-specific errors |

### Pattern Extraction and Validation

The `/learn` command analyzes accumulated failures:

```
Step 1: Load metrics.jsonl + failures.jsonl
Step 2: Cluster failures by root_cause
Step 3: Analyze clusters with 3+ occurrences
Step 4: Calculate success rates (overall, by complexity, by stack, by week)
Step 5: Generate updated patterns.md with prevention checklists
Step 6: Identify agent update candidates (patterns with 5+ occurrences)
```

**Options**:
- `/learn` — Standard analysis
- `/learn --apply` — Analyze + write prevention checklists directly into agent files
- `/learn --apply --dry-run` — Preview what `--apply` would write without modifying files
- `/learn --cross-project` — Aggregate patterns across all projects (reads paths from `github-accounts.md`)
- `/learn --validate` — Compare before/after success rates per pattern (A/B testing)
- `/learn --dry-run` — Preview changes without writing

**`--apply` closes the loop automatically**: Instead of suggesting agent updates for manual application, `--apply` reads the target agent file, finds the insertion point, generates a prevention checklist, shows a diff, writes the changes, bumps the agent version, and records the event to `pattern-events.jsonl`.

**Validation** (`--validate`) is critical: it checks whether a pattern added in week 2 actually reduced failures in weeks 3–4. Patterns that don't improve outcomes get flagged for review or removal.

### Agent Version Correlation

Every agent definition includes a version number (`v1.0`, `v1.2`, etc.). The PROVE agent records which versions ran for each issue:

```json
"agent_versions": {"map-plan": "1.0", "patch": "1.2", "prove": "1.3"}
```

This enables correlation analysis:
- "After patch agent went from v1.0 to v1.1, ENUM_VALUE failures dropped from 26% to 8%"
- "map-plan v1.0 has 63% VERIFICATION_GAP rate — v1.1 with Mandatory Verification Protocol reduced it to 12%"

Version convention:
- **Minor** (X.Y → X.Y+1): New checks, improved validation
- **Major** (X.Y → X+1.0): Workflow-changing updates

### Continuous Improvement Cadence

| Cadence | Action | Command |
|---------|--------|---------|
| **After every issue** | PROVE auto-records outcome | Automatic |
| **Weekly (Friday)** | Extract patterns, apply to agents | `/learn --apply` + `/metrics` |
| **After significant failure** | Write postmortem, extract to JSONL | `/postmortem-extract` |
| **Monthly** | Validate pattern effectiveness | `/learn --validate` |
| **Quarterly** | Cross-project pattern sharing | `/learn --cross-project` |
| **When success rate < 80%** | Emergency pattern review | `/learn --verbose` |

The complete loop:

```
┌──────────────────────────────────────────────────────────────┐
│                    SELF-LEARNING LOOP                         │
│                                                               │
│  /orchestrate (issue execution)                               │
│       │                                                       │
│       ▼                                                       │
│  PROVE records outcome                                        │
│       ├── metrics.jsonl (PASS/BLOCKED, complexity, stack)    │
│       └── failures.jsonl (root cause, details, prevention)   │
│       │                                                       │
│       ▼                                                       │
│  /learn --apply (weekly)                                      │
│       ├── Cluster failures by root_cause                     │
│       ├── Write prevention checklists → agent .md files      │
│       ├── Bump agent versions automatically                  │
│       └── Record to pattern-events.jsonl                     │
│       │                                                       │
│       ▼                                                       │
│  /learn --validate (monthly)                                  │
│       └── Compare success rates before/after each pattern    │
│       │                                                       │
│       ▼                                                       │
│  Next /orchestrate → agents load updated patterns            │
│       ├── MCP failure_patterns() (preferred)                 │
│       └── cat patterns-critical.md (fallback)                │
│       │                                                       │
│       └──────────────── Loop repeats ────────────────────────┘
```

Real-world result from one project: 86 issues analyzed, 92% success rate, with VERIFICATION_GAP identified as dominant failure at 63% — leading to the Mandatory Verification Protocol in MAP-PLAN.

---

## Module 7: Rules Engineering

### Always-Loaded vs Conditional Rules

Rules are instruction files that Claude Code loads into context. Loading a rule costs tokens — and tokens are the scarcest resource. The solution is conditional loading.

**Always-loaded** (`core-patterns.md`, ~12 lines):
```markdown
| Pattern | Trigger | Prevention |
|---------|---------|------------|
| ENUM_VALUE (26%) | Fullstack with enums | Read backend enum, use VALUE not NAME |
| COMPONENT_API (17%) | Reusing component/hook | Read source, extract PropTypes |
| VERIFICATION_GAP | Any assumption | Verify by reading code, never assume |
```

This covers 89% of failures in 12 lines. It's loaded in every session because the token cost is negligible and the failure prevention is high-value.

**Single source of truth**: `core-patterns.md` is the canonical definition. All other files (agent definitions, orchestrate prompts, sessionstart hook) **reference** it rather than duplicating the pattern text. A pattern update in one file propagates everywhere.

**Conditionally loaded** (only when working in matching paths):

| Rule | Trigger Paths | Size | Purpose |
|------|--------------|------|---------|
| `fastapi-layered-pattern.md` | `**/backend/**`, `**/api/**` | ~767 lines | Full architecture reference |
| `orchestrate-workflow.md` | `.agents/**` | ~588 lines | Agent efficiency, artifact naming |
| `spec-review-workflow.md` | `**/specs/**` | ~361 lines | Spec finalization gate |

When you're editing a React component, the 767-line FastAPI architecture reference is pure waste. Conditional loading means it only appears when you're working in backend files.

### Token Budget Optimization

Rules compete with code for context space. Optimization techniques:

| Technique | Savings | Example |
|-----------|---------|---------|
| **Pattern tiering** | ~3,000 tokens/session | Critical (50 lines) vs Full (660 lines) |
| **Conditional loading** | ~1,700 lines saved | FastAPI rules only in backend |
| **Compact state** | 85% reduction | YAML state vs markdown dump |
| **Line limits on artifacts** | 32% reduction | MAP: 150–200, PATCH: 250–350 |
| **Reference vs re-quote** | ~40% in PATCH | "See map-plan line 45" vs pasting the content |

The general principle: **load the minimum context needed for the current task**. More context doesn't mean better results — it means less room for the agent to read actual code.

### Encoding Failure Patterns as Prevention Rules

When `/learn` identifies a pattern occurring 5+ times, it suggests a rule. The process:

1. **Failure data**: 12 occurrences of ENUM_VALUE across 47 issues
2. **Pattern extraction**: Frontend uses Python enum NAME instead of VALUE
3. **Prevention rule**: "Read `backend/*/enums.py`, use VALUE (right side of `=`), not NAME (left side)"
4. **Encoding**: Added to `core-patterns.md` (always-loaded) and to CONTRACT agent (explicit enum section)
5. **Verification**: PROVE agent checks that frontend strings match backend VALUES

The rule is effective because it's **specific and actionable** — not "be careful with enums" but "read the file, use the right side of the equals sign."

### Project-Specific Overrides

Global rules in `~/.claude/rules/` apply to all projects. Per-project rules go in `<project>/.claude/rules/`:

```
~/.claude/rules/core-patterns.md              # Global: always loaded everywhere
~/projects/myapp/.claude/rules/project-rules.md  # Local: loaded only in myapp
```

Per-project overrides are useful for:
- Project-specific forbidden actions ("NEVER push to production branch")
- Project-specific architecture patterns (RAG pipeline vs web app)
- Technology-specific rules (Snowflake Cortex vs PostgreSQL)

---

## Module 8: Multi-Agent Coordination

### Agent Role Separation

Each agent in the pipeline has a strictly defined role:

| Agent | Can Read Code? | Can Write Code? | Can Create Issues? | Records Metrics? |
|-------|---------------|----------------|-------------------|-----------------|
| MAP | Yes | No | No | No |
| MAP-PLAN | Yes | No | No | No |
| PLAN | Yes | No | No | No |
| TEST-PLANNER | Yes | No | No | No |
| CONTRACT | Yes | No | No | No |
| PLAN-CHECK | Yes | No | No | No |
| **PATCH** | Yes | **Yes** | No | No |
| **PROVE** | Yes | Metrics only | No | **Yes** |
| SPEC-REVIEWER | Yes | No | **Yes** | No |

Only PATCH writes code. Only PROVE records outcomes. This separation prevents agents from overstepping their role (an investigation agent shouldn't start implementing, a verification agent shouldn't start fixing).

### CONTRACT Pattern for Fullstack Work

The CONTRACT agent solves a specific coordination problem: when backend and frontend need to change together, they need a shared agreement on the interface.

**What CONTRACT defines**:
- Endpoint specifications (METHOD, path, request/response schemas)
- Authentication requirements (Bearer JWT)
- Authorization model (which dependency to use, what account scoping)
- **Enum values** — the exact string values both sides must use
- Frontend integration notes (which hooks, which state management)

**Why it's mandatory for fullstack**: Before CONTRACT was mandatory, ENUM_VALUE was 26% of all fullstack failures. Backend would define `CO_OWNER = "CO-OWNER"` and frontend would use `"CO_OWNER"`. CONTRACT forces explicit documentation of the VALUE string, eliminating the ambiguity.

**Enforcement**: PATCH checks for `contract-{issue}-*.md` before starting. If the issue is fullstack and no CONTRACT exists, PATCH **stops immediately** with an error.

### Artifact Naming and Validation Chains

Every artifact follows the pattern `{agent}-{issue}-{mmddyy}.md` in `.agents/outputs/`.

The validation chain works like a pipeline:

```
map-plan-184-030826.md      # MAP-PLAN creates this
    ↓ (PLAN-CHECK reads it)
plan-check-184-030826.md    # PLAN-CHECK validates it
    ↓ (PATCH reads both)
patch-184-030826.md         # PATCH implements from it
    ↓ (PROVE reads it)
prove-184-030826.md         # PROVE verifies it
```

Each agent performs predecessor validation:
- PLAN-CHECK requires MAP-PLAN or PLAN
- PATCH requires MAP-PLAN or PLAN, plus CONTRACT if fullstack
- PROVE requires PATCH

If any predecessor is missing, the agent stops and reports what's needed. This prevents agents from proceeding on assumptions.

### Parallel Execution with Scope Boundaries

Safe parallelism requires scope isolation. There are two levels:

**Agent-level** (within a single session):

| Parallel Pattern | Isolation Mechanism | What Can Go Wrong |
|-----------------|---------------------|-------------------|
| MAP + TEST-PLANNER | Same input, separate output files | Nothing — truly independent |
| Speculative PATCH + PLAN-CHECK | Git save point, rollback if PLAN-CHECK fails | Wasted PATCH work (~10% of the time) |
| Backend PATCH + Frontend PATCH | CONTRACT defines shared interface | Without CONTRACT, enum/API mismatches |
| Backend tests + Frontend build | Independent tools and files | Nothing — truly independent |

**Session-level** (across terminal tabs using `--parallel`):

| Parallel Pattern | Isolation Mechanism | What Can Go Wrong |
|-----------------|---------------------|-------------------|
| Issue A + Issue B (independent) | Separate git worktrees (`.worktrees/issue-{N}/`) | Nothing if no file overlap |
| Issue A + Issue B (shared files) | Step 1.7 detects overlap, warns before branching | Merge conflicts at PR time |

The `worktree_manager.py` module handles the lifecycle: `create_worktree()`, `check_file_conflicts()`, `remove_worktree()`. State is tracked in the main repo via `state_manager.py` so `--resume` can find the worktree.

**Scope boundaries in PATCH**: When PATCH runs in parallel for fullstack, each instance is scoped to its stack. The backend PATCH only touches `backend/` files, the frontend PATCH only touches `frontend/` files. CONTRACT is the coordination mechanism — both sides implement against it.

### Swarm-Aware Behavior

Agents include swarm-awareness rules (from `_base.md`):
- Respect scope boundaries — never modify files outside your designated scope
- Check for concurrent artifacts — if another agent's output already exists, read it
- Coordinate through artifacts, not through shared state — write your output, let the next agent read it

---

## Module 9: Common Failure Patterns

### VERIFICATION_GAP (63% of Failures)

**What happens**: The agent proceeds with implementation based on assumptions about code structure, spec requirements, or component APIs — without actually reading the source.

**Why agents make this mistake**: AI models have strong priors from training data. They "know" what a typical FastAPI endpoint looks like, what a typical React hook returns, what a typical schema includes. These priors are usually correct — but when they're wrong, the agent produces plausible-looking code that doesn't match your actual codebase.

**Real example**: MAP-PLAN deferred a spec requirement ("add `after_tax_contributions` to cashflow summary") because a previous issue (#155) had a similar deferral. But the spec had been updated since #155. The agent assumed the old pattern still applied without reading the current spec.

**Systematic prevention**:
1. **Mandatory Verification Protocol** in MAP-PLAN agent — explicit checklist requiring spec read, assumption verification, and ambiguity resolution
2. **Pre-flight in PATCH** — must read plan, contract, and rules before starting
3. **`core-patterns.md`** loaded in every session — "Verify by reading actual code, never assume"

### ENUM_VALUE (26% of Fullstack Failures)

**What happens**: Frontend sends the Python enum NAME (`CO_OWNER`, underscore) when the backend expects the enum VALUE (`CO-OWNER`, hyphen).

**Why agents make this mistake**: In Python, `Role.CO_OWNER` is how you reference the enum member. The VALUE is `"CO-OWNER"`, assigned with `CO_OWNER = "CO-OWNER"`. Agents see the Python name in code and use it as the string value, not realizing the stored/transmitted value is different.

**Real example**: Backend defines `CO_OWNER = "CO-OWNER"`. Agent writes `role: "CO_OWNER"` in frontend. API returns 422 or silently stores wrong value.

**Systematic prevention**:
1. **CONTRACT agent** explicitly documents enum VALUES (not names) in a dedicated section
2. **PATCH pre-flight** includes "Read backend enum definitions, use VALUE (right side of `=`)"
3. **PROVE verification** checks that frontend strings match backend VALUES
4. **`core-patterns.md`** with `grep` command: `grep -A 5 "class.*Enum" backend/*/enums.py`

### COMPONENT_API (17% of Frontend Failures)

**What happens**: Agent assumes a component's props or hook's return structure without reading the source.

**Why agents make this mistake**: Common patterns from training data. Most `useSession()` hooks return `{ session, loading }`. But your hook might return the context directly. The agent generates code that destructures a non-existent property.

**Real example**: `const { session } = useSession()` (wrong) vs `const session = useSession()` (correct — hook returns context directly).

**Systematic prevention**:
1. **MAP agent** documents reusable component APIs with actual PropTypes
2. **PATCH verification table** lists every reused component and its verified API
3. **`core-patterns.md`** with `grep` command: `grep -A 15 "PropTypes" frontend/src/components/path/Component.jsx`

### The Learning Feedback Loop

These three patterns weren't discovered through intuition — they were extracted from structured failure data:

```
86 issues completed → 24 failures recorded → /learn clusters by root_cause
    → VERIFICATION_GAP: 63% → Added Mandatory Verification Protocol to MAP-PLAN
    → ENUM_VALUE: 26% → Made CONTRACT mandatory for fullstack
    → COMPONENT_API: 17% → Added component API verification table to PATCH
```

Each prevention technique was added to the relevant agent definition, the agent version was incremented, and subsequent issues showed reduced failure rates. The loop continues indefinitely.

---

## Module 10: Scaling & Operations

### Cross-Project Pattern Sharing

Patterns discovered in one project often apply to others. The mechanism:

1. **Project-local patterns** in `.claude/memory/patterns.md` — specific to that codebase
2. **Global patterns** in `~/.claude/memory/patterns-critical.md` — apply everywhere
3. **Cross-pollination**: `/learn --cross-project` aggregates failures across all projects, identifying patterns that recur regardless of codebase

Example: ENUM_VALUE was discovered in a financial planning app (MyMoney) but applies equally to an SDLC orchestrator (Temper) and a RAG platform (VaultIQ). The pattern was promoted from project-local to global.

### Metrics Dashboards and Trend Analysis

The `/metrics` command visualizes performance:

```bash
/metrics              # Last 30 days (default)
/metrics --week       # Last 7 days
/metrics --agent MAP  # Filter by agent
/metrics --json       # Machine-readable output
```

**Dashboard components**:
- Overall success rate (PASS / total)
- Success by complexity (TRIVIAL/SIMPLE/COMPLEX)
- Success by stack (backend/frontend/fullstack)
- Top failure causes (ranked by frequency)
- Agent blocking rate (which agents cause failures)
- Weekly trend (improving/declining)

**Recommendations engine**: Based on metrics, generates actionable guidance:

| Condition | Recommendation |
|-----------|----------------|
| ENUM_VALUE > 20% | "Add enum VALUE verification to MAP agent" |
| Fullstack < 70% | "Always use CONTRACT agent for fullstack issues" |
| COMPLEX < 50% | "Break COMPLEX issues into SIMPLE sub-issues" |
| Trend declining | "Run /learn to update patterns" |

### Agent Performance Optimization

Three levers for improving agent performance:

**1. Token efficiency** — Reduce context consumption without losing information:
- Pattern tiering (critical vs full)
- Conditional rule loading
- Compact artifacts with line limits
- Reference code locations instead of re-quoting

**2. Failure prevention** — Encode known failures as agent checks:
- Pre-flight checklists in each agent
- Verification tables (component APIs, enum values)
- Mandatory predecessor validation

**3. Pipeline optimization** — Reduce unnecessary work:
- Complexity classification routes TRIVIAL issues through fewer agents (skip PLAN-CHECK, use PROVE-lite)
- CONTRACT-lite for simple fullstack (0 new endpoints) avoids spawning a full CONTRACT agent
- Speculative PATCH alongside PLAN-CHECK saves one agent cycle ~90% of the time
- `--parallel` worktree isolation enables concurrent issues instead of sequential processing
- `--resume` skips completed phases after interruption instead of restarting

### When to Use /quick vs /orchestrate

| Use `/quick` when... | Use `/orchestrate` when... |
|----------------------|---------------------------|
| Fix is obvious (typo, config change) | Implementation spans multiple files |
| No tests needed | Tests are required |
| Single-file change | Fullstack changes |
| Time-sensitive fix | Quality and tracking matter |
| Exploratory work | Issue-driven development |

`/quick` skips the agent pipeline entirely — it's direct implementation. `/orchestrate` runs the full pipeline with investigation, planning, verification, and outcome recording. The trade-off is speed vs reliability and learning data.

### Integration with External Tools

**Obsidian** (Knowledge Management):
```
Claude Code session → obsidian-agent → Obsidian vault
    ├── Projects/{name}/STATUS.md (current state)
    ├── Projects/{name}/Log/Daily/*.md (daily activity)
    └── DASHBOARD.md (cross-project overview)
```

The vault feeds downstream tools: daily-standup reads it for reports, mcp-server queries it for Claude Code access, pr-changelog writes merged PR info to it.

**GitHub** (Issue/PR Management):
- Issues created via `/feature`, `/bug`, `/spec-review`
- PRs created via `/pr` with pre-flight checklist
- Branch strategy: `feat/issue-XXX-description`, `fix/issue-XXX-description`
- "Main stays green" — never push broken code to main

**Codex** (Cross-Validation):
- `/codex-review` sends plan or proposal to OpenAI Codex for a second opinion
- Useful for architectural decisions where a different perspective helps
- Configured separately in `codex-config/` with its own rules and skills

**MCP Servers** (Tool Extensions):
- `context7` — Injects version-specific library documentation (eliminates "the API changed since training" hallucinations)
- `vault-metrics` (custom) — Queries metrics.jsonl and failures.jsonl from within Claude Code. Agents use `failure_patterns()` as **preferred pre-flight source** (structured JSON with counts and examples), falling back to file reads when MCP is unavailable
- `apple-mcp` — macOS platform integration (calendar, contacts for Buddy voice assistant)

---

## Appendix: Glossary

| Term | Definition |
|------|-----------|
| **Agent** | An AI model instance with a specific role, instructions, and output format |
| **Artifact** | A markdown file produced by an agent, stored in `.agents/outputs/` |
| **Context window** | The total text an AI model can process at once (instructions + conversation + code) |
| **CONTRACT** | An artifact that defines the backend/frontend API interface for fullstack work |
| **Hook** | A script that runs at a specific lifecycle event (session start, pre-compact, stop) |
| **MCP** | Model Context Protocol — a standard for tools that extend AI agent capabilities |
| **Orchestrate** | The multi-agent pipeline that takes an issue through investigation → implementation → verification |
| **Pattern** | A documented failure mode with trigger conditions and prevention steps |
| **PERSISTENT_STATE** | YAML file tracking active work (issue, branch, phase) across sessions |
| **Rule** | An instruction file loaded into context (always or conditionally by file path) |
| **Skill** | A multi-step workflow definition that orchestrates commands and agents |
| **Slash command** | A user-invocable command (e.g., `/orchestrate`, `/learn`) defined in a markdown file |
| **State manager** | Centralized Python module (`state_manager.py`) for reading/writing PERSISTENT_STATE.yaml |
| **Worktree** | An isolated git working directory for parallel issue processing (`--parallel` flag) |
| **Worktree manager** | Python module (`worktree_manager.py`) for creating, listing, and cleaning up git worktrees |
| **CONTRACT-lite** | Inline contract section in PATCH prompt (replaces full CONTRACT agent for simple fullstack) |
| **PROVE-lite** | Reduced verification (gates only, no Level 2-3) for TRIVIAL issues |
| **Prompt template** | Shared markdown template (`templates/agent-prompt.md`) with variable substitution for agent prompts |
