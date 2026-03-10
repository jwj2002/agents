# JJob Development Workflow & Best Known Methods

> **Author**: JJob (documented via Claude Code, March 2026)
> **Scope**: Personal development practices, tooling, and workflows refined over 3+ months of AI-assisted development

---

## 1. Development Environment

### Hardware & OS
- **Primary**: Dell workstation, WSL2 (Ubuntu on Windows)
- **Network**: Cato SASE (enterprise firewall — blocks some external requests from CLI)
- **Shell**: Bash in WSL2
- **Python**: 3.10+ (use `python3`, not `python`)

### Core Tools
| Tool | Purpose | Notes |
|------|---------|-------|
| **Claude Code** | Primary AI coding assistant | CLI-based, runs in terminal |
| **OpenAI Codex** | Second-opinion reviews | `/codex-review` for cross-validation |
| **GitHub CLI (`gh`)** | Issue/PR management | Integrated into slash commands |
| **Git** | Version control | "Main stays green" strategy |
| **Obsidian** | Knowledge management | Second brain — sessions captured automatically |

### AI Models Used
| Context | Model | Notes |
|---------|-------|-------|
| Claude Code sessions | Claude Opus 4.6 | Primary development |
| RAG ingestion/queries | Claude Sonnet | Cost-effective for production RAG |
| Local LLM (RAG dev) | Ollama (qwen3:8b, deepseek-r1:32b) | Air-gap deployments |
| Embeddings | nomic-embed-text | Via Ollama |

---

## 2. Configuration Architecture

### The `~/agents/` Repository
All Claude Code configuration lives in a **single portable git repo** (`github.com/jwj2002/agents`) that symlinks into `~/.claude/`:

```
~/agents/                           # Git-tracked, portable across machines
├── claude-config/
│   ├── commands/                   # 14 slash commands
│   ├── agents/                     # 11 agent definitions (orchestrate workflow)
│   ├── hooks/                      # 3 lifecycle hooks
│   ├── rules/                      # 4 global rules (conditional loading)
│   ├── skills/                     # Multi-step skill definitions
│   ├── templates/                  # Project & GitHub templates
│   ├── settings.json               # Hooks, permissions, MCP, statusline
│   ├── install.sh                  # Symlink installer
│   └── new-project-claude.sh       # Bootstrap new projects
├── codex-config/                   # OpenAI Codex configuration
├── mcp-server/                     # Custom MCP: vault + metrics queries
├── obsidian-agent/                 # Session capture → Obsidian vault
├── daily-standup/                  # Vault → standup report
├── code-review/                    # Pre-commit review
├── pr-changelog/                   # PR merge → changelog
├── doc-reader/                     # TTS for documents
├── youtube-summarizer/             # Video → transcript → summary
└── install-all.sh                  # One-command setup (Claude + Codex)
```

### Multi-Machine Sync
```bash
# New machine setup (one command)
git clone https://github.com/jwj2002/agents.git ~/agents
~/agents/install-all.sh

# Update existing machines
cd ~/agents && git pull && ~/agents/install-all.sh
```

### Per-Project Overrides
Each project gets local `.claude/` config that overrides global:
```bash
~/agents/claude-config/new-project-claude.sh /path/to/project
# Creates: CLAUDE.md, .claude/rules/project-rules.md, .claude/context/project-stack.md
```

---

## 3. The Orchestrate Workflow

The centerpiece of the development process. Issue-driven, multi-agent workflow with self-learning.

### Pipeline
```
Issue → Classify → Branch → Agents → Verify → Record → PR
```

### Agent Sequence

**TRIVIAL/SIMPLE issues**:
```
MAP-PLAN → [TEST-PLANNER] → CONTRACT* → PLAN-CHECK → PATCH → PROVE
```

**COMPLEX issues**:
```
MAP → PLAN → [TEST-PLANNER] → CONTRACT* → PLAN-CHECK → PATCH → PROVE
```

\* CONTRACT is **mandatory** for fullstack issues

### Agent Roles
| Agent | Purpose | Key Output |
|-------|---------|------------|
| **MAP** | Read-only codebase investigation | Complexity classification, file inventory |
| **MAP-PLAN** | Combined investigation + planning (simple issues) | Implementation plan with acceptance criteria |
| **PLAN** | File-by-file implementation plan (complex) | Detailed change spec |
| **TEST-PLANNER** | Pre-implementation test matrix | Edge cases, priority levels |
| **CONTRACT** | Backend↔frontend API contract | Authoritative API spec for parallel work |
| **PLAN-CHECK** | Validates plan against codebase | Catches deviations before implementation |
| **PATCH** | Implementation with minimal diffs | Working code changes |
| **PROVE** | Verification + outcome recording | Evidence of completion, metrics |

### Parallel Execution
- MAP + TEST-PLANNER run concurrently (COMPLEX)
- Parallel fullstack PATCH: backend + frontend via CONTRACT
- PROVE verification fan-out: lint/test/build

### Usage
```bash
/orchestrate 184                    # Standard workflow
/orchestrate 184 --with-tests       # Include TEST-PLANNER phase
/quick "fix the login bug"          # Ad-hoc task without full workflow
```

---

## 4. Slash Commands

### Workflow
| Command | Purpose |
|---------|---------|
| `/orchestrate [issue]` | Full multi-agent workflow |
| `/pr` | PR creation with checklist, merge strategy |
| `/review` | Code review staged changes |
| `/quick` | Ad-hoc task without full orchestration |

### Issue Management
| Command | Purpose |
|---------|---------|
| `/feature "title"` | Create feature issue via `gh issue create` |
| `/bug "title"` | Create bug report with investigation |
| `/spec-draft "title"` | Interactive spec creation with codebase discovery |
| `/spec-review` | Review spec against codebase, generate issues |

### Testing & Quality
| Command | Purpose |
|---------|---------|
| `/test-plan [issue]` | Pre-implementation test planning with edge cases |
| `/codex-review` | Second opinion from OpenAI Codex |

### Learning System
| Command | Purpose |
|---------|---------|
| `/learn` | Analyze failures, extract patterns |
| `/learn --cross-project` | Aggregate learnings across all projects |
| `/learn --validate` | A/B test pattern effectiveness |
| `/metrics` | Agent performance dashboard |

### Scaffolding
| Command | Purpose |
|---------|---------|
| `/scaffold-project` | Generate complete FastAPI project |
| `/scaffold-module` | Add module to existing FastAPI project |

### External Agents
| Command | Purpose |
|---------|---------|
| `/obsidian` | Capture session to Obsidian vault |
| `/standup` | Daily standup from vault |
| `/changelog` | Update changelog from merged PRs |

---

## 5. Lifecycle Hooks

Three Python hooks manage session continuity and quality:

### SessionStart — Context Restoration
- Loads `PERSISTENT_STATE.yaml` (active issue, phase, branch)
- Injects critical failure patterns (~500 tokens)
- Detects active orchestrate workflows and provides continue instructions
- 85% token reduction vs. prior approach

### PreCompact — State Preservation
- Fires before Claude Code compresses context
- Extracts structured state from transcript (issue, phase, artifacts, decisions)
- Updates `PERSISTENT_STATE.yaml` for next session
- Backs up raw transcript for recovery
- Auto-cleans checkpoints older than 7 days

### Stop — Completion Verification
- Anti-rationalization gate — blocks premature task completion
- Checks for uncommitted changes that should have been committed
- Checks for TODO/FIXME/HACK markers in changed files
- Exit code 2 sends feedback to continue working

---

## 6. Rules System

### Always-Loaded (~10 lines)
**`core-patterns.md`** — Top 3 failure patterns causing >50% of agent failures:

| Pattern | Frequency | Prevention |
|---------|-----------|------------|
| **ENUM_VALUE** | 26% | Read backend enum, use VALUE string not Python name |
| **COMPONENT_API** | 17% | Read actual source file, extract PropTypes before using |
| **VERIFICATION_GAP** | — | Verify by reading actual code, never assume |

### Conditionally-Loaded
| Rule | Loads When | Size |
|------|-----------|------|
| `fastapi-layered-pattern.md` | Working in `**/backend/**` or `**/api/**` | ~500 lines |
| `orchestrate-workflow.md` | Working in `.agents/**` | Multi-phase definition |
| `spec-review-workflow.md` | Working in `**/specs/**` | Spec finalization gate |

---

## 7. Self-Learning System

### How It Works
```
/orchestrate (issue)
    → MAP → PLAN → PATCH → PROVE
                               │ Record outcome
                  ┌────────────┴────────────┐
            metrics.jsonl              failures.jsonl
                  └────────────┬────────────┘
                          /learn (weekly)
                               │
                         patterns.md
                               │
                        /agent-update (Edit tool, version++)
                               │
                        Next /orchestrate → agents read patterns.md
```

### Root Cause Taxonomy
Canonical codes for classifying failures:

| Code | Description |
|------|-------------|
| `ENUM_VALUE` | Used enum NAME instead of VALUE |
| `COMPONENT_API` | Wrong props/hook usage |
| `MULTI_MODEL` | Forgot model relationship |
| `API_MISMATCH` | Frontend/backend contract violation |
| `ACCESS_CONTROL` | Missing/wrong permission check |
| `MISSING_TEST` | Untested code path |
| `SQLITE_COMPAT` | PostgreSQL-only feature used |
| `STRUCTURE_VIOLATION` | Violated rules.md constraints |
| `SCOPE_CREEP` | Beyond issue scope |
| `VERIFICATION_GAP` | Assumptions not verified by reading code |

### Operational Cadence
- **Weekly**: Run `/learn` to extract new patterns
- **Monthly**: Run `/learn --validate` to prune ineffective patterns
- **Quarterly**: Run `/learn --cross-project` to cross-pollinate

---

## 8. MCP Servers

| Server | Purpose |
|--------|---------|
| **context7** | Injects version-specific library documentation (eliminates stale API hallucinations) |
| **apple-mcp** | Apple platform integration |
| **mcp-server** (custom) | Query agent metrics and failure patterns from within Claude Code |

Custom MCP tools:
- `agent_metrics` — Query metrics.jsonl for success rates and trends
- `failure_patterns` — Read failures.jsonl for top failure patterns
- `vault_status` — Read Obsidian STATUS.md
- `vault_search` — Search daily logs
- `vault_dashboard` — Cross-project overview

---

## 9. Git Workflow

### Branch Strategy
```
main (protected — always green)
├── feat/issue-XXX-description    # New features
├── fix/issue-XXX-description     # Bug fixes
├── chore/description             # Maintenance
├── docs/spec-name                # Specifications
└── test/description              # Test additions
```

### Rules
- **NEVER commit directly to main** (except emergency fixes)
- **NEVER push broken code to main**
- Run tests before every merge
- Branch names include issue number when applicable
- Specs require review before committing (no draft specs on main)

### PR Workflow (`/pr`)
1. Pre-PR checklist (tests, lint, build)
2. `gh pr create` with template
3. Copilot automatic code review
4. Merge strategy selection
5. Post-merge branch cleanup

---

## 10. Project Portfolio

### Active Projects

| Project | Stack | Purpose |
|---------|-------|---------|
| **VE-RAG-System** | FastAPI + React + PostgreSQL + pgvector + Ollama | Enterprise RAG for NVIDIA DGX Spark (air-gap) |
| **vaultiq-snow** | Snowflake Cortex + Streamlit + Python | RAG chat app powered by Snowflake |
| **vaultiq** | FastAPI + React + PostgreSQL + pgvector + Claude API | Insurance document intelligence platform |
| **ingestkit** | Python monorepo (openpyxl + pandas + Pydantic v2) | Plugin-based Excel ingestion for RAG |
| **fastapi-architect-agent** | Python CLI + Claude Code | Standalone FastAPI project scaffolding |

### Common Architecture Patterns

**FastAPI Layered Architecture** (used across projects):
```
Model → Schema → Repository → Service → Router → Deps
```
- Repository pattern with `BaseRepository[T]` generic
- Service layer with `BaseService[T, R]` generic
- Dependency injection via FastAPI `Depends()`
- Structural subtyping via `typing.Protocol` (not ABCs)

**RAG Pipeline** (used across VE-RAG, VaultIQ, IngestKit):
```
Document → Parse → Chunk → Embed → Store → Search → Generate → Cite
```

---

## 11. CLAUDE.md Best Practices

Every project gets a CLAUDE.md at the root with:

1. **Project overview** — What it is, what it's not
2. **Development commands** — Setup, run, test, lint
3. **Architecture** — Component diagram, data flow, key decisions
4. **Technology stack** — Versions, dependencies
5. **Project structure** — Directory layout with descriptions
6. **Git workflow** — Branch strategy, commit conventions
7. **Forbidden changes** — Things Claude should never do
8. **Key configuration** — Environment variables, defaults

### Key Principles
- Be explicit about what's deprecated ("Gradio is deprecated, do not use")
- Call out platform-specific requirements ("Use `python3` not `python`")
- Document test credentials and default URLs
- Include forbidden patterns to prevent AI from making common mistakes
- Reference authoritative specs ("Read SPEC.md before making design decisions")

---

## 12. Standalone Agents

| Agent | Trigger | What It Does |
|-------|---------|--------------|
| **obsidian-agent** | `/obsidian` or session end | Captures Claude Code sessions to Obsidian vault (STATUS.md + Daily logs + Dashboard) |
| **daily-standup** | `/standup` | Aggregates vault entries into standup report |
| **code-review** | Pre-commit hook | Reviews staged changes before commit |
| **pr-changelog** | Post-merge hook | Updates CHANGELOG.md from merged PRs |
| **doc-reader** | `/doc-reader` | Text-to-speech for documents (Edge TTS) |
| **youtube-summarizer** | Manual | Video → local Whisper transcription → Claude summary |

---

## 13. Key Lessons Learned

### From Failure Analysis
1. **Read before assuming** — The #1 failure pattern. Always read the actual code/enum/component before using it.
2. **Use enum VALUES not names** — `"CO-OWNER"` not `"CO_OWNER"`. Backend enum values are strings, not Python identifiers.
3. **Read PropTypes before reusing components** — Never guess a component's API.
4. **CONTRACT is not optional for fullstack** — Without an explicit API contract, frontend and backend will diverge.
5. **Anti-rationalization** — AI agents will declare tasks complete prematurely. The Stop hook catches this.

### From Workflow Optimization
6. **Symlink-based config** — One repo, multiple machines, instant updates.
7. **Conditional rule loading** — Don't bloat context with irrelevant rules. Load FastAPI patterns only in backend contexts.
8. **Structured state extraction** — Extract issue/phase/artifacts from transcripts, not raw text dumps.
9. **Canonical schemas** — Define metrics and failure formats once in `_base.md`, reference everywhere.
10. **Agent versioning** — Track which agent version produced which outcome for correlation.

### From Product Development
11. **Demo datasets matter** — Seeded "gotchas" in demo data create memorable moments (e.g., 3 contracts missing privacy clauses).
12. **Revenue models need Excel formulas** — Use cell references, not hardcoded values. Everything should recalculate dynamically.
13. **WSL path mounting** — Access Windows files via `/mnt/c/Users/...` when CLI tools can't reach external URLs.
14. **Enterprise firewalls block CLI requests** — Cato SASE intercepts `curl`/`wget`. Save files via browser, copy through WSL mount.

---

## 14. Environment Quick Reference

### New Machine Setup
```bash
git clone https://github.com/jwj2002/agents.git ~/agents
~/agents/install-all.sh
```

### New Project Setup
```bash
~/agents/claude-config/new-project-claude.sh /path/to/project
# Edit: CLAUDE.md, .claude/rules/project-rules.md
```

### Daily Workflow
```bash
# Start work
cd ~/projects/<project>
claude                              # Opens Claude Code

# Feature development
/orchestrate <issue-number>         # Full workflow
/quick "description"                # Ad-hoc task

# Quality
/test-plan <issue>                  # Pre-implementation planning
/review                             # Code review
/codex-review                       # Second opinion

# Ship
/pr                                 # Create PR
/changelog                          # Update changelog

# Capture
/obsidian                           # Save session to vault
/standup                            # Generate standup
```

### Weekly Maintenance
```bash
/learn                              # Extract failure patterns
/metrics                            # Check agent performance
cd ~/agents && git pull             # Update config on all machines
```
