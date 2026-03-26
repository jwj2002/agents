# Agentic Engineering Workflow — Complete Extraction

> **Machine**: Jasons-MacBook-Pro (macOS 26.2, Apple Silicon arm64)
> **Extracted**: 2026-03-10 | **Last Updated**: 2026-03-26
> **Source**: Personal Mac development environment

---

## Part 1: Environment Profile

### Machine Info

| Property | Value |
|----------|-------|
| **OS** | macOS 26.2 (Darwin 25.2.0, arm64) |
| **Shell** | zsh |
| **Hostname** | Jasons-MacBook-Pro-590.local |
| **User** | jasonjob |

### Key Tools

| Tool | Version | Path |
|------|---------|------|
| Python | 3.12.4 | `~/.rye/shims/python3` (Rye managed) |
| Node.js | 25.2.1 | `/opt/homebrew/bin/node` |
| npm | 11.6.2 | `/opt/homebrew/bin/npm` |
| Git | 2.50.1 | `/usr/bin/git` |
| GitHub CLI | 2.85.0 | `/opt/homebrew/bin/gh` |
| Claude Code | latest | `~/.local/bin/claude` |
| Bun | latest | `/opt/homebrew/bin/bun` |

### AI Models Used

| Model | When / Why |
|-------|------------|
| **Claude Opus 4.6** | Primary development model — orchestration, implementation, complex reasoning |
| **Claude Sonnet 4.6** | Fast mode for simpler tasks, quick iterations |
| **Claude Haiku 4.5** | Code review agent (lightweight, runs proactively after changes), Obsidian extraction |
| **GPT-4o / GPT-4o-mini** | Buddy voice pipeline (streaming LLM for real-time conversation) |
| **Whisper** | Local speech-to-text (mlx-whisper on Apple Silicon) |
| **Codex** | Secondary review tool for spec validation |

### MCP Servers

| Server | Source | Purpose |
|--------|--------|---------|
| **apple-mcp** | `bunx apple-mcp@latest` | macOS platform integration (calendar, contacts) |
| **context7** | `npx @upstash/context7-mcp@latest` | Injects current library documentation — eliminates stale API hallucinations |
| **vault-metrics** | `~/agents/mcp-server/server.py` (in settings.json + settings.local.json) | 5 tools: `vault_status`, `vault_search`, `vault_dashboard`, `agent_metrics`, `failure_patterns` — reads Obsidian vault + `.claude/memory/` files. Agents use `failure_patterns()` as preferred pattern source in pre-flight |

### Plugins

| Plugin | Purpose |
|--------|---------|
| **frontend-design** | Official Claude Code plugin for generating distinctive, production-grade frontend interfaces |

---

## Part 2: Configuration Architecture

### Central Repository

All Claude Code customization lives in a single git repository:

```
~/agents/claude-config/     ← Version-controlled source of truth
    │
    ├── agents/             → ~/.claude/agents/      (symlink)
    ├── commands/           → ~/.claude/commands/     (symlink)
    ├── hooks/              → ~/.claude/hooks/        (symlink)
    │   ├── state_manager.py        ← Centralized YAML state management
    │   ├── worktree_manager.py     ← Git worktree lifecycle (--parallel)
    │   ├── notify_completion.py    ← macOS notifications (Stop hook)
    │   ├── verify_completion.py    ← Anti-rationalization (Stop hook)
    │   ├── precompact_checkpoint.py← State extraction (PreCompact hook)
    │   └── sessionstart_restore_state.py ← Context restore (SessionStart hook)
    ├── rules/              → ~/.claude/rules/        (symlink)
    ├── skills/             → ~/.claude/skills/       (symlink)
    ├── templates/          ← Prompt templates (referenced by orchestrate.md)
    │   └── agent-prompt.md         ← Shared agent prompt with variable substitution
    ├── settings.json       → ~/.claude/settings.json (symlink)
    └── statusline.py       → ~/.claude/statusline.py (symlink)
```

**Not symlinked** (machine-local):
- `~/.claude/settings.local.json` — Machine-specific MCP servers (vault-metrics path varies by machine)
- `~/.claude/memory/` — Per-machine learned patterns
- `~/.claude/projects/` — Per-project session data

### Symlink Strategy

The `install.sh` script (352 lines) is idempotent and platform-aware:
1. **Detects platform**: macOS (iCloud drive auto-detect), WSL (Windows-side vault), Linux (local vault)
2. **Backs up existing files** to `~/.claude/config-backup-{timestamp}/`
3. **Creates symlinks** from `~/.claude/` to repo directories
4. **Installs dependencies**: MCP server venv, PyYAML for hooks
5. **Verifies**: Tests all symlinks, MCP server, python3 availability

Safe to run repeatedly — skips existing correct symlinks.

### Global vs Per-Project Config

```
~/.claude/                          ← Global (symlinked from ~/agents/claude-config/)
    ├── settings.json               ← Hooks, MCP, permissions, plugins
    ├── settings.local.json         ← Machine-specific overrides
    ├── agents/                     ← Agent definitions (inherited by all projects)
    ├── commands/                   ← Slash commands (available everywhere)
    ├── rules/                      ← Conditional rules (loaded by path match)
    ├── skills/                     ← Complex workflows
    ├── hooks/                      ← Lifecycle hooks
    └── memory/
        └── patterns-critical.md    ← Global failure patterns (always loaded)

~/projects/<project>/               ← Per-project (committed to project repo)
    ├── CLAUDE.md                   ← Project-specific instructions
    ├── .claude/
    │   ├── settings.json           ← Project permissions
    │   └── memory/
    │       ├── patterns.md         ← Project-specific learned patterns
    │       ├── patterns-full.md    ← Extended patterns (660 lines)
    │       ├── metrics.jsonl       ← Issue outcome tracking
    │       ├── failures.jsonl      ← Failure details
    │       └── pattern-events.jsonl← /learn --apply tracking
    ├── .agents/
    │   └── outputs/                ← Workflow artifacts
    │       ├── map-plan-184-030826.md
    │       ├── patch-184-030826.md
    │       ├── prove-184-030826.md
    │       ├── archive/            ← Post-merge artifact archive
    │       └── claude_checkpoints/
    │           └── PERSISTENT_STATE.yaml
    └── .worktrees/                 ← Isolated worktrees (--parallel mode, gitignored)
        ├── issue-42/               ← Full repo copy on own branch
        └── issue-57/               ← Another parallel issue
```

### Conditional Rule Loading

| Rule File | Loaded When | Size | Purpose |
|-----------|-------------|------|---------|
| `core-patterns.md` | **Always** | 12 lines | Top 3 failure patterns (89% coverage) |
| `fastapi-layered-pattern.md` | `**/backend/**`, `**/api/**`, `**/services/**` | 767 lines | Full layered architecture reference |
| `orchestrate-workflow.md` | `.agents/**/*.md` | 588 lines | Agent efficiency, artifact naming |
| `spec-review-workflow.md` | `**/specs/**`, `**/.agents/**` | 361 lines | Spec finalization gate |

### Hook Lifecycle (Data Flow)

```
┌─────────────────────────────────────────────────────────────┐
│                    SESSION START                             │
│                         │                                    │
│            SessionStart Hook (Python)                        │
│            ├─ Load PERSISTENT_STATE.yaml                     │
│            ├─ Load patterns-critical.md                      │
│            └─ Detect active workflow → continue instructions │
│                         │                                    │
│                    ┌────┴────┐                               │
│                    │ SESSION │                               │
│                    │  WORK   │                               │
│                    └────┬────┘                               │
│                         │                                    │
│              Context approaching limit?                      │
│              ┌──────────┴───────────┐                       │
│              │ YES                  │ NO                     │
│              │                      │                        │
│    PreCompact Hook (Python)         │                        │
│    ├─ Extract state from transcript │                        │
│    ├─ Update PERSISTENT_STATE.yaml  │                        │
│    ├─ Auto-delete >7 day old files  │                        │
│    └─ Context compacts              │                        │
│              │                      │                        │
│              └──────────┬───────────┘                       │
│                         │                                    │
│                  Task complete?                               │
│              ┌──────────┴───────────┐                       │
│              │ YES                  │ NO                     │
│              │                      │                        │
│     Stop Hooks (Python, run sequentially)                    │
│     ├─ verify_completion.py                                  │
│     │   ├─ Check uncommitted changes                         │
│     │   ├─ Check TODO/FIXME/HACK                            │
│     │   └─ BLOCK if issues found                            │
│     └─ notify_completion.py                                  │
│         ├─ macOS: send Notification Center alert (osascript) │
│         ├─ Includes issue/phase context from state_manager   │
│         └─ Auto-forwards to iPhone via Handoff               │
│              │                                               │
│         Exit 0 → Allow    Exit 2 → Block + feedback          │
└─────────────────────────────────────────────────────────────┘
```

**Token Budget**: SessionStart restores ~500 tokens (85% reduction from full context dump of ~3,250 tokens).

---

## Part 3: The Orchestrate Workflow

### Full Pipeline

```
GitHub Issue
     │
     ├─ TRIVIAL ──────────────────────────────────────────────────┐
     │   MAP-PLAN → PATCH → PROVE-lite (gates only)
     │
     ├─ SIMPLE ───────────────────────────────────────────────────┐
     │   MAP-PLAN → [TEST-PLANNER] → CONTRACT* → PLAN-CHECK → PATCH → PROVE
     │
     └─ COMPLEX ──────────────────────────────────────────────────┐
         MAP → PLAN → [TEST-PLANNER] → CONTRACT* → PLAN-CHECK → PATCH → PROVE

     * CONTRACT is MANDATORY for fullstack (PATCH will STOP without it)
       CONTRACT-lite (inline) used for simple fullstack (0 new endpoints, ≤2 frontend files)
     [ ] = Optional (--with-tests flag)
```

### Workflow Decision Diagram

```
                        ┌──────────────┐
                        │ GitHub Issue  │
                        └──────┬───────┘
                               │
                    ┌──────────┴──────────┐
                    │  Classify Complexity │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              ▼                ▼                 ▼
         ┌─────────┐    ┌──────────┐      ┌──────────┐
         │ TRIVIAL  │    │  SIMPLE  │      │ COMPLEX  │
         │ 1-2 files│    │ 3-5 files│      │ 6+ files │
         └────┬─────┘    └────┬─────┘      └────┬─────┘
              │               │                  │
              ▼               ▼                  ▼
         MAP-PLAN         MAP-PLAN          MAP → PLAN
              │               │                  │
              │          ┌────┴────┐        ┌────┴────┐
              │          │fullstack?│        │fullstack?│
              │          └────┬────┘        └────┬────┘
              │           yes │ no           yes │ no
              │               ▼                  ▼
              │          CONTRACT(*)         CONTRACT
              │               │                  │
              │          PLAN-CHECK         PLAN-CHECK
              │               │                  │
              ▼               ▼                  ▼
           PATCH           PATCH              PATCH
              │               │                  │
              ▼               ▼                  ▼
         PROVE-lite        PROVE              PROVE
         (gates only)         │                  │
              │               ▼                  ▼
              └───────────── /pr ────────────────┘

     (*) CONTRACT-lite (inline) if 0 new endpoints + ≤2 frontend files
         CONTRACT-full (agent) otherwise
```

### Agent Roles

| Agent | Version | Phase | Role | Read-Only? | Output Lines |
|-------|---------|-------|------|------------|--------------|
| **MAP** | 1.0 | 1 | Investigator (COMPLEX only) | Yes | 150–200 |
| **MAP-PLAN** | 1.0 | 1+2 | Investigator + Architect (TRIVIAL/SIMPLE) | Yes | 350–450 |
| **PLAN** | 1.0 | 2 | Architect (COMPLEX only) | Yes | 350–450 |
| **TEST-PLANNER** | 1.0 | 1.5 | Test Architect (opt, `--with-tests`) | Yes | 250–350 |
| **CONTRACT** | 1.0 | 2.5 | Interface Designer (fullstack only) | Yes | 180–250 |
| **PLAN-CHECK** | 1.0 | 2.8 | Plan Validator | Yes | 80–120 |
| **PATCH** | 1.2 | 3 | Implementer (CODE CHANGES) | No | 250–350 |
| **PROVE** | 1.3 | 4 | Reviewer + Outcome Recorder | No (writes metrics) | 200–300 |
| **SPEC-REVIEWER** | 1.0 | Pre | Spec Analyst + Issue Creator | No (creates issues) | 300–400 |
| **CODE-REVIEWER** | 1.0 | Post | Proactive Review (Haiku model) | Yes | <30 |

### Complexity Classification

| Complexity | Agents Used | Criteria |
|------------|-------------|----------|
| **TRIVIAL** | MAP-PLAN → PATCH → PROVE-lite | Single file, obvious change (skips PLAN-CHECK) |
| **SIMPLE** | MAP-PLAN → [PLAN-CHECK] → PATCH → PROVE | 2-5 files, clear pattern to follow |
| **COMPLEX** | MAP → PLAN → [PLAN-CHECK] → PATCH → PROVE | 6+ files, architectural decisions, multi-layer |

### Parallel Execution Patterns

#### Within a Session (Agent-Level)

| Pattern | Agents Run in Parallel | Use Case |
|---------|----------------------|----------|
| MAP fan-out | Explore backend + frontend + tests | COMPLEX: parallel codebase investigation |
| MAP + TEST-PLANNER | MAP + TEST-PLANNER | Same input, separate outputs |
| Speculative PATCH | PLAN-CHECK + PATCH | SIMPLE backend: PATCH starts before PLAN-CHECK finishes |
| Fullstack PATCH | Backend PATCH + Frontend PATCH | Separate scopes with CONTRACT |
| PROVE verification | Backend verify + Frontend verify | Independent test suites |

#### Across Sessions (Worktree-Level) — `--parallel` flag

```
Terminal Tab 1                    Terminal Tab 2
─────────────                    ─────────────
/orchestrate 42 --parallel       /orchestrate 57 --parallel
     │                                │
     ▼                                ▼
.worktrees/issue-42/             .worktrees/issue-57/
├── backend/  (isolated)         ├── backend/  (isolated)
├── frontend/ (isolated)         ├── frontend/ (isolated)
└── .agents/outputs/ (isolated)  └── .agents/outputs/ (isolated)
     │                                │
     ▼                                ▼
PR from worktree branch          PR from worktree branch
     │                                │
     ▼                                ▼
Merge → git worktree remove      Merge → git worktree remove
```

**Conflict prevention**: Step 1.7 checks both active worktrees AND open PRs for file overlap before proceeding. If overlap detected, recommends serialization.

**State isolation**: Each worktree has its own `.agents/outputs/`, but PERSISTENT_STATE.yaml lives in the main repo (tracked via `worktree_path` field in state_manager).

### Artifact Naming and Validation Chain

**Pattern**: `{agent}-{issue}-{mmddyy}.md` in `.agents/outputs/`

```
map-plan-184-030826.md
    └─→ validates → contract-184-030826.md (if fullstack)
                        └─→ validates → plan-check-184-030826.md
                                            └─→ validates → patch-184-030826.md
                                                                └─→ validates → prove-184-030826.md
```

Each agent checks for required predecessor artifacts before starting. If missing, the agent **STOPS** and reports the gap.

### CONTRACT as Mandatory for Fullstack

When PATCH detects fullstack work:
1. Checks for `contract-{issue}-*.md` artifact
2. If **missing**: STOP immediately, report "CONTRACT artifact required for fullstack"
3. If **present**: Read contract, verify enum VALUES, verify API schemas

The CONTRACT agent defines:
- Endpoint specifications (METHOD, path, request/response schemas)
- Authentication (Bearer JWT)
- Authorization (account_id scoping, access control deps)
- **Enum definitions** (CRITICAL: backend VALUE must match frontend usage)
- Frontend integration notes

### State Management

State persists in `.agents/outputs/claude_checkpoints/PERSISTENT_STATE.yaml`, managed by `hooks/state_manager.py`:

```yaml
active_work:
  issue: 775
  branch: feature/issue-775-asset-form-fields
  phase: PATCH
  last_action: Starting PATCH phase
  completed_phases: [MAP-PLAN, PLAN-CHECK]
  worktree_path: null                      # set when --parallel used
meta:
  updated: '2026-03-26'
```

**State Manager** (`hooks/state_manager.py`) — centralized module used by:
- `orchestrate.md` — calls `update_phase()` before each agent, `clear_active()` after completion
- `precompact_checkpoint.py` — calls `update_from_extracted()` to update state from transcript
- `sessionstart_restore_state.py` — calls `get_active_work()` to restore context
- `--resume` flag — calls `get_completed_phases()` to skip already-finished phases
- `--parallel` flag — calls `get_worktree_for_issue()` to locate worktree path

```
┌──────────────────────────────────────────────────────────┐
│                   state_manager.py                        │
│                                                           │
│  load_state()          ← read PERSISTENT_STATE.yaml      │
│  update_phase()        ← orchestrate: before each agent  │
│  clear_active()        ← orchestrate: after completion   │
│  get_completed_phases()← --resume: skip finished phases  │
│  get_active_work()     ← sessionstart: restore context   │
│  get_worktree_for_issue()← --parallel: find worktree     │
│  update_from_extracted()← precompact: transcript state   │
└──────────────────────────────────────────────────────────┘
```

---

## Part 4: Command Reference

### Workflow Commands

| Command | Usage | Purpose |
|---------|-------|---------|
| `/orchestrate` | `/orchestrate 184 [--with-tests] [--parallel] [--resume]` | Run full agent pipeline for a GitHub issue |
| `/quick` | `/quick 184` | Ad-hoc fix without full orchestrate overhead |
| `/pr` | `/pr [--merge]` | Create PR with checklist, optionally merge |
| `/review` | `/review` | Code review of staged changes |

### Issue Management

| Command | Usage | Purpose |
|---------|-------|---------|
| `/feature` | `/feature "Add payment module"` | Create feature request issue |
| `/bug` | `/bug "Login fails on Safari"` | Create bug report with investigation |
| `/spec-draft` | `/spec-draft payments` | Interactive specification creation |
| `/spec-review` | `/spec-review specs/payments.md [--create-issues]` | Analyze spec vs codebase, find gaps |
| `/feature-from-spec` | `/feature-from-spec specs/payments.md` | Create issues from spec gaps |

### Testing

| Command | Usage | Purpose |
|---------|-------|---------|
| `/test-plan` | `/test-plan 184` | Pre-implementation test planning with edge cases |

### Learning & Metrics

| Command | Usage | Purpose |
|---------|-------|---------|
| `/learn` | `/learn [--cross-project] [--validate] [--apply]` | Extract patterns from failures, update knowledge. `--apply` writes prevention checklists into agent files |
| `/metrics` | `/metrics [--week] [--json]` | Display agent performance dashboard |

### Scaffolding

| Command | Usage | Purpose |
|---------|-------|---------|
| `/scaffold-project` | `/scaffold-project myapp --with-auth` | Generate complete FastAPI project (33 files) |
| `/scaffold-module` | `/scaffold-module items -f "name:str, amount:Decimal"` | Add domain module to existing project |

### Common Workflows

**Daily**:
1. Open project → SessionStart auto-restores context
2. `/orchestrate <issue>` for planned work (add `--parallel` for concurrent issues)
3. `/quick <issue>` for small fixes
4. `/pr` when implementation complete (auto-archives artifacts, cleans worktrees)
5. macOS notifications alert when sessions complete (+ iPhone via Handoff)

**Weekly (Friday)**:
1. `/learn --apply` — Extract patterns and write prevention into agent files
2. `/metrics` — Review performance trends
3. `/learn --validate` — Check if applied patterns improved success rates

**Per-Feature (large)**:
1. `/spec-draft` — Create specification
2. `/spec-review` — Analyze gaps, create issues
3. `/orchestrate <issue>` — Implement each issue
4. `/pr` — Create pull request

---

## Part 5: Self-Learning System

### Metrics Schema (metrics.jsonl)

One JSON line per completed issue:

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

### Failure Taxonomy (Root Cause Codes)

| Code | Frequency | Description | Detection Agent |
|------|-----------|-------------|-----------------|
| **VERIFICATION_GAP** | 63% | Proceeded without verifying spec/code | MAP-PLAN |
| **ENUM_VALUE** | 26% | Used enum NAME instead of VALUE | PATCH, PROVE |
| **COMPONENT_API** | 17% | Wrong props/hook usage | PATCH |
| **MULTI_MODEL** | 13% | Forgot to update related model | PATCH |
| **SQLITE_COMPAT** | 8% | Used PostgreSQL-only feature in tests | PATCH |
| **ACCESS_CONTROL** | 7% | Missing/wrong permission dependency | PATCH |
| **API_MISMATCH** | — | Frontend/backend contract violation | PATCH, PROVE |
| **MISSING_TEST** | — | Code path not covered by tests | PROVE |
| **STRUCTURE_VIOLATION** | — | Violated project rules (e.g., created `src/`) | PATCH |
| **SCOPE_CREEP** | — | Beyond issue scope | MAP-PLAN, PATCH |
| **LINT_ERROR** | — | Code style violations | PROVE |
| **OTHER** | — | Document specifics in details field | Any |

### Failures Schema (failures.jsonl)

Recorded only when status is BLOCKED:

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

### Pattern Extraction (/learn)

```
Step 1: Load metrics.jsonl + failures.jsonl
Step 2: Cluster failures by root_cause (jq grouping)
Step 3: Analyze clusters with 3+ occurrences
Step 4: Calculate success rates (overall, by complexity, by stack, by week)
Step 5: Generate updated patterns.md
Step 6: Identify agent update candidates (5+ occurrences)
Step 7: Output summary with trend analysis
```

**Options**:
- `--since DATE` — Analyze from specific date
- `--dry-run` — Preview without updating files
- `--apply` — Write prevention checklists into agent files (+ `--dry-run` for preview)
- `--cross-project` — Aggregate across all projects (reads paths from `github-accounts.md`)
- `--validate` — Compare before/after success rates per pattern

### Agent Update Process (`/learn --apply`)

When `/learn` identifies patterns with 5+ occurrences:
1. Reads target agent file, finds insertion point (after Pre-Flight, before Process)
2. Generates prevention checklist section with failure count and date
3. Shows diff to user for review
4. If `--apply` (not `--dry-run`): writes changes, bumps agent minor version
5. Records to `.claude/memory/pattern-events.jsonl` for `/learn --validate` tracking
6. Next `/orchestrate` loads updated agents with new prevention checks

### The Complete Learning Loop

```
/orchestrate (issue execution)
        │
        ▼
PROVE records outcome → metrics.jsonl + failures.jsonl
        │
        ▼
/learn (weekly) → clusters failures → updates patterns.md
        │
        ├──→ /learn --apply → writes prevention checklists
        │    directly into agent .md files + bumps version
        │    + records to pattern-events.jsonl
        │
        ├──→ /learn --validate → compares success rates
        │    before/after each pattern was added
        │
        └──→ /learn --cross-project → aggregates patterns
             across all projects (paths from github-accounts.md)
        │
        ▼
Next /orchestrate → agents load patterns via:
  1. MCP failure_patterns() (preferred, structured JSON)
  2. cat .claude/memory/patterns-critical.md (fallback)
        │
        ▼
Cycle repeats (continuous improvement)
```

### Pattern Loading (MCP-First)

Agents prefer MCP tools over file reads for pattern data:

```
┌─────────────────────┐     ┌──────────────────────────┐
│  Agent Pre-Flight   │────▶│  MCP: failure_patterns() │
│                     │     │  MCP: agent_metrics(30d)  │
│  (all agents via    │     └──────────┬───────────────┘
│   _base.md §1)      │               │ fails?
│                     │               ▼
│                     │     ┌──────────────────────────┐
│                     │────▶│  File: patterns-critical │
│                     │     │  File: patterns-full.md  │
└─────────────────────┘     └──────────────────────────┘
```

### Real Data (from mymoney-dev)

- **Issues analyzed**: 86 (2026-01-06 to 2026-02-11)
- **Failures recorded**: 24 distinct failure records
- **Success rate**: ~92% (2 BLOCKED, 86 PASS)
- **Most common failure**: VERIFICATION_GAP (63% in patterns-full.md)
- **Agent versions**: map-plan 1.0, patch 1.2, prove 1.3

### Pattern Tiering (Token Optimization)

| Tier | File | Size | Loaded When |
|------|------|------|-------------|
| **Critical** | `patterns-critical.md` | ~50 lines | Always (via SessionStart hook) |
| **Full** | `patterns-full.md` | ~660 lines | COMPLEX issues or on demand |
| **Project** | `patterns.md` | Variable | Auto-updated by `/learn` |

---

## Part 6: Project Patterns

### Active Projects

| Project | Type | Backend | Frontend | Database | Status |
|---------|------|---------|----------|----------|--------|
| **Buddy** | Voice AI Assistant | FastAPI, AsyncPG, pgVector | Web (text chat) | PostgreSQL + pgVector | Active, Production |
| **MyMoney** | Financial Planning | FastAPI, SQLAlchemy 2.0, Alembic | React 19, Vite, Tailwind | PostgreSQL | Active, Multi-branch |
| **Temper** | SDLC Orchestrator | FastAPI, SQLAlchemy 2.0, ARQ/Redis | React 19, Vite | PostgreSQL, Redis | In Development |
| **FastAPI Architect** | CLI Scaffolding Tool | Click, Claude Agent SDK | — | — | Active |
| **Safe174th** | Community Advocacy | Cloudflare Pages Functions | Vanilla HTML/CSS/JS | Cloudflare D1 (SQLite) | Deployed |

### Common Architecture (Layered Pattern)

All Python/FastAPI projects follow strict layered architecture:

```
Request → Router (HTTP) → Service (Business Logic) → Repository (Data Access) → DB
            ↑                    ↑                         ↑
          deps.py             schemas.py               models.py
       (access control)    (Pydantic v2)            (SQLAlchemy 2.0)
```

**Module Structure** (standard across projects):
```
module/
├── models.py      # SQLAlchemy 2.0 (UUID PK, TimestampMixin, Mapped[T])
├── schemas.py     # Pydantic v2 (ConfigDict, from_attributes=True)
├── repository.py  # Data access (BaseRepository[T], never commits)
├── services.py    # Business logic (calls commit(), raises AppError)
├── deps.py        # FastAPI DI (access control, repo factories)
└── router.py      # HTTP endpoints (thin, no business logic)
```

**Key Rules Enforced**:

| Rule | Enforcement |
|------|-------------|
| Repositories NEVER commit | Service calls `commit()` |
| Services NEVER raise HTTPException | Raise AppError subclasses |
| Routers have ZERO business logic | Call service, return response |
| UUID primary keys | `default=uuid.uuid4` |
| Timestamps | `TimestampMixin` (created_at, updated_at) |
| Account-scoped entities | `account_id` FK with CASCADE |
| Access control | Always via dependencies, never inline |

### Shared Technology Choices

| Choice | Why |
|--------|-----|
| **FastAPI** | Async-first, Pydantic integration, dependency injection |
| **SQLAlchemy 2.0** | Type-safe ORM (`Mapped[T]`, `mapped_column()`, `select()`) |
| **Pydantic v2** | Fast validation, `from_attributes` for ORM integration |
| **PostgreSQL** | Production DB (with pgVector for Buddy) |
| **SQLite** | Test DB only (in-memory, no PostgreSQL-specific syntax) |
| **Ruff** | Fast Python linter/formatter (replaces black + isort + flake8) |
| **React 19 + Vite** | Modern frontend with fast HMR |
| **Tailwind CSS** | Utility-first, consistent styling |

### Git Workflow

- **Main branch**: Protected, always green
- **Feature branches**: `feature/issue-{N}-{description}`
- **PR workflow**: `/pr` command creates PR with checklist
- **Production branch** (MyMoney): Separate, never pushed without explicit request
- **Pre-commit hooks**: Buddy auto-increments version; MyMoney uses ruff/prettier

### Testing Strategy

| Layer | Tool | Pattern |
|-------|------|---------|
| Backend | pytest + pytest-asyncio | SQLite in-memory, no PostgreSQL syntax |
| Frontend | Vitest | Component tests, integration tests |
| Linting | Ruff (backend), ESLint (frontend) | Pre-submission gate in PATCH |
| Build | pytest + npm run build | PROVE verification gate |

### Documentation Standards (CLAUDE.md Best Practices)

Projects use a 3-tier documentation structure:

1. **CLAUDE.md** (root) — Project-specific instructions for AI agents
   - Tech stack, architecture, conventions
   - Forbidden actions (never create `src/`, never push to production)
   - Development commands
   - Testing requirements

2. **specs/** — Technical specifications and ADRs
   - Feature specs (implement in order)
   - Architecture decision records

3. **ai_docs/** (optional) — AI-optimized context
   - Onboarding fast-path
   - Gotchas reference
   - Postmortem analyses

---

## Part 7: Failure Prevention

### Top Failure Patterns with Frequency Data

#### 1. VERIFICATION_GAP (63% of all failures)

**What happens**: Agent proceeds without reading spec, verifying code structure, or resolving ambiguities.

**Example**: Plan deferred spec requirement to add `after_tax_contributions`, citing issue #155 pattern. Spec v1.3 explicitly required both locations.

**Prevention**:
- Read specification file FIRST if referenced in issue
- Verify EVERY assumption by reading actual code (use Read tool)
- Pick ONE approach if multiple valid options exist
- Document verification steps in artifact

**Encoded in**: MAP-PLAN agent (Mandatory Verification Protocol), `core-patterns.md` rule

#### 2. ENUM_VALUE (26% of fullstack failures)

**What happens**: Frontend sends Python enum NAME (`CO_OWNER`) when backend expects VALUE (`CO-OWNER`).

**Example**: Backend defines `CO_OWNER = "CO-OWNER"` (underscore in NAME, hyphen in VALUE). Frontend used `role: "CO_OWNER"` instead of `role: "CO-OWNER"`.

**Prevention**:
- Read backend enum definitions (`grep -A 5 "class.*Enum" backend/*/enums.py`)
- Use enum VALUE (right side of `=`), not NAME (left side)
- CONTRACT agent documents enum VALUES explicitly
- PROVE agent verifies frontend strings match backend VALUES

**Encoded in**: CONTRACT agent (Enum Definitions section), PATCH pre-flight checklist, `core-patterns.md` rule

#### 3. COMPONENT_API (17% of frontend failures)

**What happens**: Agent assumes component props or hook return structure without reading source.

**Example**: Assumed `const { session } = useSession()` but hook returns context directly: `const session = useSession()`.

**Prevention**:
- Read actual component/hook source file before using
- Extract PropTypes: `grep -A 15 "PropTypes" frontend/src/components/path/Component.jsx`
- Never invent props that don't exist
- MAP agent documents reusable component APIs

**Encoded in**: MAP agent (Document reusable components), PATCH verification table, `core-patterns.md` rule

### How Rules Encode Prevention

```
core-patterns.md (Always loaded, 12 lines)
    └── Decision matrix: Issue references spec? → Read spec FIRST
    └── Decision matrix: Reusing component? → Read PropTypes
    └── Decision matrix: Fullstack with enums? → Check VALUE vs NAME

fastapi-layered-pattern.md (Loaded in backend contexts, 767 lines)
    └── Layer rules: Repos never commit, Services never raise HTTPException
    └── Enum rules: member names = UPPER_SNAKE, values = stored in DB
    └── Access control: Always via dependencies, never inline

orchestrate-workflow.md (Loaded in .agents contexts, 588 lines)
    └── Artifact validation: Each agent checks predecessors
    └── Size compliance: Target lines with compression checklist
    └── CONTRACT mandatory for fullstack
```

### The "Read Before Assuming" Principle

Every agent in the pipeline has verification gates:

| Agent | What It Verifies |
|-------|-----------------|
| MAP/MAP-PLAN | Reads spec, reads actual code, documents component APIs and enum values |
| CONTRACT | Defines exact enum VALUES, endpoint schemas, auth requirements |
| PLAN-CHECK | Validates plan covers all acceptance criteria, enum VALUES explicit |
| PATCH | Pre-flight: reads plan + contract + rules. Pre-submission: runs ruff + pytest |
| PROVE | Verification levels: EXISTS → SUBSTANTIVE → WIRED → FUNCTIONAL |

---

## Part 8: Lessons Learned

### What Worked and Why

1. **Symlink-based configuration**: Single source of truth in git, deployed everywhere via symlinks. Changes propagate immediately. No copy-paste drift.

2. **Mandatory CONTRACT for fullstack**: Before CONTRACT was mandatory, ENUM_VALUE failures were 26% of all fullstack issues. CONTRACT forces explicit documentation of enum VALUES before PATCH starts.

3. **Pre-flight checklists in agents**: Agents that verify prerequisites before starting catch problems early, before burning context on implementation.

4. **PERSISTENT_STATE.yaml**: YAML-based state (not markdown dumps) survives context compaction with 85% token reduction. Agents can resume after interruption.

5. **Pattern tiering**: Loading only critical patterns (~50 lines) by default, full patterns (~660 lines) only for COMPLEX issues. Saves ~3,000 tokens per session.

6. **Anti-rationalization hook (Stop)**: Prevents agents from declaring "done" when uncommitted changes or TODO markers exist. Forces actual completion.

7. **Outcome recording in PROVE**: Every issue gets a metrics.jsonl entry. This data feeds the learning loop — no manual tracking needed.

8. **Centralized state manager**: Three codepaths (orchestrate inline blocks, precompact hook, sessionstart hook) independently manipulated PERSISTENT_STATE.yaml. Extracted to single `state_manager.py` module — one place to maintain, testable, enables `--resume` and `--parallel`.

9. **Prompt template extraction**: 11 inline Task() prompts in orchestrate.md (627 lines) made prompt iteration difficult. Extracted to `templates/agent-prompt.md` with variable tables. Each agent section is now a variable table + reference, not a full prompt block.

10. **Worktree isolation for parallel sessions**: Running two orchestrate sessions on the same checkout caused file conflicts. `--parallel` flag creates isolated git worktrees per issue — zero disk conflicts, state tracked in main repo.

11. **macOS notifications for session completion**: Borrowed from Boris Cherny's workflow (10-15 parallel sessions with iTerm2 alerts). Stop hook sends Notification Center alerts that relay to iPhone via Handoff.

### What Failed and What Was Changed

1. **Full context restoration** (v1): SessionStart loaded entire conversation summary (~3,250 tokens). Changed to compact YAML + critical patterns (~500 tokens). 85% reduction.

2. **Agent artifacts too long**: Early agents produced 600-700 line artifacts. Phase 1 optimization (Dec 2025) set target lengths and compression checklists. 32% reduction.

3. **Issues created before spec finalized**: Created GitHub issues from draft specs, then spec changed. Added `spec-review-workflow.md` rule: "Finalize spec BEFORE creating issues."

4. **Postmortem data not machine-readable**: Human postmortems were useful but couldn't feed the learning loop. Added `/postmortem-extract` to convert to failures.jsonl format.

5. **No plan validation before PATCH**: PATCH would start implementing a plan with gaps, burning context. Added PLAN-CHECK agent (phase 2.8) to validate plans before PATCH.

### Key Insights About Working with AI Agents

1. **Agents don't remember across sessions** — State persistence must be engineered (hooks, YAML, patterns). Without it, every session starts from zero.

2. **Agents trust their own output** — Without verification gates, agents will declare success after producing plausible-looking but incorrect code. The PROVE agent and Stop hook combat this.

3. **Context is the scarcest resource** — Every token of instructions competes with code context. Pattern tiering and compact artifacts are essential, not optional.

4. **Structured failure data enables improvement** — Unstructured postmortems are useful for humans but useless for automation. JSON schemas (metrics.jsonl, failures.jsonl) enable the learning loop.

5. **Agents need explicit prohibitions** — "Don't create `src/`", "Don't push to production", "STOP if CONTRACT missing" — agents will do anything not explicitly forbidden.

6. **Read-only phases prevent waste** — MAP, MAP-PLAN, and PLAN are read-only. They can't break anything. This separation means investigation happens before implementation, catching issues early.

### Anti-Patterns to Avoid

| Anti-Pattern | Why It Fails | Better Approach |
|-------------|-------------|-----------------|
| Assuming code structure | 63% of failures | Always read actual code |
| Using enum Python names | 26% of fullstack failures | Read enum VALUES from source |
| Inventing component props | 17% of frontend failures | Read PropTypes/source |
| Creating issues from draft specs | Specs change, issues become stale | Finalize spec first, then create issues |
| Dumping full context on restore | Wastes tokens | Compact YAML + critical patterns |
| No plan validation | PATCH implements flawed plans | PLAN-CHECK before PATCH |
| Manual failure tracking | Data not machine-readable | Structured JSONL schemas |
| Duplicating pattern definitions | Updates require editing 4 files | Single source in `core-patterns.md`, reference everywhere else |
| Inline state manipulation | Fragile, untestable, 3 codepaths | Centralized `state_manager.py` |
| Sequential issue processing | One issue at a time | `--parallel` with worktree isolation |
| Polling terminal tabs | Wasted attention | macOS notifications + iPhone relay |

---

## Part 9: Quick Reference

### New Machine Setup (Step by Step)

```bash
# 1. Clone the agents repository
git clone https://github.com/jwj2002/agents.git ~/agents

# 2. Run the unified installer
cd ~/agents
./install-all.sh          # Installs both claude-config and codex-config

# Or just Claude Code:
cd ~/agents/claude-config
./install.sh

# 3. Create machine-local settings (MCP servers with local paths)
cat > ~/.claude/settings.local.json << 'EOF'
{
  "mcpServers": {
    "vault-metrics": {
      "command": "python3",
      "args": ["~/agents/mcp-server/server.py", "--mcp"]
    }
  }
}
EOF

# 4. Verify installation
ls -la ~/.claude/settings.json    # Should be symlink
ls -la ~/.claude/agents/          # Should be symlink
ls -la ~/.claude/commands/        # Should be symlink
claude --version                  # Should work
```

### New Project Setup (Step by Step)

```bash
# 1. Create project directory
mkdir -p ~/projects/myapp && cd ~/projects/myapp
git init

# 2. Bootstrap Claude Code config
~/agents/claude-config/new-project-claude.sh .

# 3. Or scaffold a full FastAPI project
# (inside Claude Code):
/scaffold-project myapp --with-auth

# 4. Create CLAUDE.md with project-specific instructions
# 5. Create .claude/memory/ for project patterns
# 6. Start working: /orchestrate <first-issue>
```

### Daily Workflow Checklist

- [ ] Open project → SessionStart auto-restores context
- [ ] Check `git status` for any pending work
- [ ] `/orchestrate <issue>` for planned implementation
- [ ] `/orchestrate <issue> --parallel` for concurrent independent issues
- [ ] `/quick <issue>` for small fixes
- [ ] `/review` before committing
- [ ] `/pr` when implementation complete (auto-archives artifacts + cleans worktrees)
- [ ] macOS notifications ping when parallel sessions complete

### Weekly Maintenance Checklist

- [ ] `/learn --apply` — Extract patterns and write into agent files
- [ ] `/learn --validate` — Verify applied patterns improved success rates
- [ ] `/metrics` — Review performance trends
- [ ] `/learn --cross-project` — Aggregate patterns across all projects
- [ ] `cd ~/agents && git pull` — Sync config across machines
- [ ] Check for stale issues/PRs

---

## Appendix A: Sibling Projects in ~/agents/

| Project | Purpose | Tech | Integration |
|---------|---------|------|-------------|
| **mcp-server/** | MCP server for vault + metrics | Python, MCP SDK | Configured in settings.local.json, provides 5 tools |
| **obsidian-agent/** | Session → Obsidian vault writer | Python, Claude haiku | Parses session JSONL → vault STATUS.md + daily logs |
| **code-review/** | Pre-commit code review | Python, Git hooks | Installs as pre-commit hook, blocks on CRITICAL issues |
| **daily-standup/** | Standup report generator | Python | Reads Obsidian vault → cross-project standup |
| **doc-reader/** | Document reader with TTS | Python, Edge TTS/macOS TTS | Standalone, reads markdown/PDF/summaries |
| **pr-changelog/** | PR changelog automation | Python, GitHub CLI | Post-merge hook, writes to CHANGELOG.md + vault |
| **youtube-summarizer/** | YouTube summarizer | Python, yt-dlp, Whisper, Claude | Offline transcription (mlx-whisper on Apple Silicon) |
| **orchestrate-workflow/** | Legacy orchestrate (superseded) | Markdown agents | Replaced by claude-config agents |
| **codex-config/** | Codex configuration | Bash installer | Symlinks to ~/.codex/ |

### Data Flow Between Projects

```
Claude Code Sessions (.claude/projects/*/session.jsonl)
        │
        ▼
obsidian-agent (Claude haiku extraction)
        │
        ├──→ Obsidian Vault (STATUS.md, Daily logs, DASHBOARD.md)
        │         │
        │         ├──→ mcp-server (vault_status, vault_search, vault_dashboard)
        │         ├──→ daily-standup (reads vault → standup report)
        │         └──→ pr-changelog (writes changelog to vault)
        │
        └──→ .claude/memory/ (metrics.jsonl, failures.jsonl)
                  │
                  ├──→ /learn (pattern extraction)
                  ├──→ /metrics (performance dashboard)
                  └──→ mcp-server (agent_metrics, failure_patterns)
```

---

## Appendix B: Complete File Inventory

### ~/agents/claude-config/ (Source of Truth)

**Agents** (12 files, symlinked to `~/.claude/agents/`):
`_base.md` (10.3 KB), `map.md` (3.6 KB), `map-plan.md` (6.5 KB), `plan.md` (4.1 KB), `contract.md` (3.3 KB), `plan-checker.md` (3.1 KB), `patch.md` (5.8 KB), `prove.md` (7.3 KB), `test-planner.md` (7.9 KB), `spec-reviewer.md` (6.1 KB), `code-reviewer.md` (1.3 KB)

**Commands** (16 files, symlinked to `~/.claude/commands/`):
`orchestrate.md` (18.4 KB), `learn.md` (8.5 KB), `metrics.md` (15.8 KB), `pr.md` (3.1 KB), `spec-review.md` (3.4 KB), `feature.md` (2.8 KB), `bug.md` (2.3 KB), `feature-from-spec.md` (2.7 KB), `test-plan.md` (2.5 KB), `spec-draft.md` (7.5 KB), `scaffold-project.md` (22.4 KB), `scaffold-module.md` (7.5 KB), `quick.md` (2.0 KB), `review.md` (0.4 KB)

**Rules** (4 files, symlinked to `~/.claude/rules/`):
`core-patterns.md` (0.7 KB), `fastapi-layered-pattern.md` (23.6 KB), `orchestrate-workflow.md` (16.7 KB), `spec-review-workflow.md` (12.0 KB)

**Hooks** (5 files, symlinked to `~/.claude/hooks/`):
`precompact_checkpoint.py` (7.5 KB), `sessionstart_restore_state.py` (4.8 KB), `verify_completion.py` (3.3 KB), `notify_completion.py` (3.5 KB), `state_manager.py` (4.5 KB), `worktree_manager.py` (6.5 KB)

**Skills** (3 directories, symlinked to `~/.claude/skills/`):
`orchestrate/` (SKILL.md 2.4 KB + ORCHESTRATE_REFERENCE.md 7.5 KB), `test-plan/` (SKILL.md 2.1 KB), `spec-review/` (SKILL.md 1.2 KB)

**Templates** (2 files):
`agent-prompt.md` (2.5 KB — shared prompt template with variables for all agents), `github-actions/copilot-review-setup.md`

**Config**: `settings.json` (2.1 KB), `statusline.py` (1.2 KB), `install.sh` (11.5 KB), `.gitignore`

### ~/projects/ (Active Projects)

| Project | CLAUDE.md | .claude/memory/ | .agents/outputs/ | specs/ |
|---------|-----------|----------------|-----------------|--------|
| buddy | Yes | metrics, failures, patterns | Yes | — |
| mymoney-dev | Yes | metrics (86), failures (24), patterns-full (660 lines) | Yes (many artifacts) | Yes |
| temper | Yes | — | Yes | Yes |
| fastapi-architect-agent | README | — | — | — |
| safe174th | ARCHITECTURE.md | — | — | — |
