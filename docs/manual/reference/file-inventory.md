# File Inventory

Complete listing of all files in `~/agents/claude-config/` and related directories. All paths are relative to repo root unless noted.

`claude-config/` is symlinked into `~/.claude/` by `install.sh`. The repo is the source of truth; runtime references via `~/.claude/...` resolve through symlinks.

---

## Agents (12 files)

Located in `claude-config/agents/`. Each agent is a markdown file with frontmatter (`name:`, `description:`, `tools:`, `model:`) followed by the agent's prompt body.

| File | Size | Purpose |
|------|-----:|---------|
| `_base.md` | 9.6 KB | Base prompt inherited by every agent (pre-flight pattern loading, AGENT_RETURN spec, failure prevention, artifact validation). Trimmed in PR #97 — verification commands now live in `snippets/verify-commands.md`. |
| `contract.md` | 3.6 KB | Defines backend ↔ frontend API contract. **Mandatory for fullstack changes.** |
| `discuss.md` | 4.6 KB | Captures design decisions and trade-offs before MAP/PLAN. Runs only when `--discuss` flag is set. |
| `map-plan.md` | 6.8 KB | Combined MAP + PLAN for SIMPLE-tier work — investigates the codebase and produces an implementation plan. |
| `map.md` | 3.9 KB | Investigates current state. Runs in COMPLEX tier as a separate phase before PLAN. |
| `patch.md` | 8.4 KB | Implementation phase. Edits files, writes tests, runs verification commands. |
| `plan-checker.md` | 3.3 KB | Validates a PLAN artifact's completeness before PATCH burns context implementing it. **COMPLEX-only** since v5 dropped PLAN-CHECK from SIMPLE. |
| `plan.md` | 4.4 KB | Authors implementation plan in COMPLEX tier (after MAP). |
| `pr-fresh-reviewer.md` | 1.7 KB | Fresh-context PR reviewer. Spawned by `/pr` to look at the diff with no inheritance from the implementation discussion. |
| `prove.md` | 8.6 KB | Verification phase. Runs lint/tests, validates acceptance criteria, applies behavioral evals (E01–E15) per `eval-file-mapping.md`. |
| `spec-reviewer.md` | 6.4 KB | Reviews a specification document against the codebase, optionally generates GitHub issues. |
| `test-planner.md` | 8.2 KB | Generates pre-implementation test plan with edge cases. Runs when `--with-tests` flag is set. |

---

## Slash Commands (16 files)

Located in `claude-config/commands/`. Each is a markdown file with frontmatter (`description:`, `argument-hint:`, sometimes `disable-model-invocation:`) and a process spec.

### Implementation
| File | Size | Purpose |
|------|-----:|---------|
| `quick.md` | 2.0 KB | Direct executor for TRIVIAL tasks. No pipeline, no artifacts. |
| `orchestrate.md` | 10.8 KB | MAP-PLAN → PATCH → PROVE pipeline for SIMPLE+ tasks. **Rejects TRIVIAL classification** (PR #94) — redirects to `/quick`. |

### Issue creation
| File | Size | Purpose |
|------|-----:|---------|
| `bug.md` | 2.3 KB | Create a bug-report GitHub issue. |
| `feature.md` | 2.8 KB | Create a feature-request GitHub issue. |
| `spec-draft.md` | 7.5 KB | Draft a feature specification via guided Q&A. |
| `spec-review.md` | 3.4 KB | Validate a spec against the codebase, optionally generate issues. |
| `feature-from-spec.md` | 2.7 KB | Internal helper invoked by `/spec-review` to create one issue per spec entry. |

### Quality + review
| File | Size | Purpose |
|------|-----:|---------|
| `review.md` | 0.4 KB | Pre-commit code review. |
| `test-plan.md` | 2.5 KB | Generate edge-case test plan before implementation. |
| `pr.md` | 7.6 KB | Pre-PR fresh-context review, advisory Codex review gate for COMPLEX changes (PR #95), then `gh pr create`. |

### Scaffolding
| File | Size | Purpose |
|------|-----:|---------|
| `scaffold-project.md` | 6.0 KB | Scaffold a complete FastAPI project with layered architecture. |
| `scaffold-module.md` | 7.5 KB | Scaffold a new FastAPI module (model, schema, repo, service, router, deps). |

### Learning + insight
| File | Size | Purpose |
|------|-----:|---------|
| `learn.md` | 11.0 KB | Analyze failure patterns, update learned knowledge base. |
| `metrics.md` | 15.8 KB | Display agent performance metrics and trends. |
| `seed.md` | 5.0 KB | Capture a deferred idea with a trigger condition for when it should surface. |

### Design
| File | Size | Purpose |
|------|-----:|---------|
| `frontend-design.md` | 3.7 KB | Frontend design helpers (per the `frontend-design` plugin). |

---

## Rules (12 files)

Located in `claude-config/rules/`. Rules use `paths: [...]` frontmatter to declare when they auto-load. `paths: ["**"]` means "always load." Only `git-workflow.md` declares `alwaysApply: true`.

| File | Size | Path scope | Purpose |
|------|-----:|-----------|---------|
| `core-patterns.md` | 0.7 KB | `["**"]` | Top 3 failure patterns (VERIFICATION_GAP, ENUM_VALUE, COMPONENT_API). Always loaded. |
| `implementation-routing.md` | 3.5 KB | `["**"]` | Tier classification + Codex routing rules. Always loaded. |
| `git-workflow.md` | 3.8 KB | `["**"]` (`alwaysApply: true`) | Branch naming, conventional commits, squash-merge contract. |
| `github-accounts.md` | 1.6 KB | `["**"]` | Multi-account routing (jwj2002 vs jjob-spec). |
| `dev-environment.md` | 5.0 KB | `["**"]` | Three development modes (laptop / jbox06 / hybrid). |
| `behavioral-evals.md` | 7.2 KB | `["**/backend/**", "**/frontend/**", "**/.agents/**", "**/Dockerfile", "**/*.env*"]` | E01–E15 behavioral evals. |
| `eval-file-mapping.md` | 1.8 KB | `["**/.agents/**", "**/backend/**", "**/frontend/**", "**/PROVE*.md"]` | Maps changed-file globs to applicable E-codes. |
| `gitlab-access.md` | 2.9 KB | `["**/app-repos/**", "**/vitalailabs/**", "**/.gitlab/**"]` | Internal GitLab access for VitalAILabs apps. |
| `post-merge-verification.md` | 1.2 KB | `["**/.github/**", "**/CHANGELOG*", "**/.agents/**"]` | Post-merge health checks. |
| `rbac-pattern.md` | 3.8 KB | `["**/auth/**", ...]` | Permission-check dependency pattern for FastAPI. |
| `orchestrate-workflow.md` | 16.7 KB | `.agents/**/*.md` | Internal workflow rules for orchestrate agents. |
| `spec-review-workflow.md` | 12.0 KB | `["**/specs/**", "**/.agents/**"]` | Spec finalization workflow. |

---

## Hooks (10 files)

Located in `claude-config/hooks/`. Python scripts attached to Claude Code lifecycle events via `settings.json`. Two of these are shared modules (`state_manager.py`, `worktree_manager.py`) imported by other hooks.

| File | Size | Lifecycle event | Purpose |
|------|-----:|----------------|---------|
| `sessionstart_restore_state.py` | 5.5 KB | SessionStart | Restore PERSISTENT_STATE.yaml and critical patterns into context. |
| `load_learning_rules.py` | 1.1 KB | SessionStart | Load learning rules into context at session start. |
| `precompact_checkpoint.py` | 8.1 KB | PreCompact | Checkpoint orchestrate state to YAML before context compaction. |
| `verify_completion.py` | 4.1 KB | Stop | Anti-rationalization gate. Warns on uncommitted files (all types post #84), un-pushed commits, branches ahead of main with no PR (post #85), TODO/FIXME/HACK markers. Always exits 0 (advisory). |
| `notify_completion.py` | 3.1 KB | Stop | macOS Notification Center alert with iPhone Handoff relay. |
| `session_end_context_update.py` | 5.7 KB | Stop | Updates project state YAML with session-end context. |
| `context_monitor.py` | 4.3 KB | PostToolUse | Tracks context usage, flags approaching limits. |
| `secret_guard.py` | 3.2 KB | (not currently wired) | Bash-side secret-exfil guard. Bundled but not registered in `settings.json` — covered by `permissions.deny` rules instead. |
| `state_manager.py` | 4.9 KB | (shared module) | Centralized PERSISTENT_STATE.yaml read/write. |
| `worktree_manager.py` | 6.7 KB | (shared module) | Git worktree lifecycle for `--parallel` flag. |

### Hook registrations in `settings.json`

| Event | Hooks (in order) |
|-------|-----------------|
| `SessionStart` | `sessionstart_restore_state.py`, `load_learning_rules.py` |
| `PreCompact` | `precompact_checkpoint.py` |
| `PostToolUse` | `context_monitor.py` |
| `Stop` | `verify_completion.py`, `notify_completion.py`, `session_end_context_update.py` |
| `PreToolUse` | (none) |

---

## Skills (7 directories)

Located in `claude-config/skills/`. Each is a directory containing a `SKILL.md` (and optionally supporting files). Skills are listed at session start when Claude Code's harness asks "what can I help with?"

| Directory | Purpose |
|-----------|---------|
| `capture/` | Quick non-interrupting capture to inbox. |
| `dashboard/` | Cross-project status overview. |
| `deep-review/` | Comprehensive critical code review. |
| `inbox/` | View and triage inbox captures. |
| `pdf/` | Convert markdown to PDF. |
| `project/` | View or update project context. |
| `review-session/` | Review session commits and propose focus updates. |

---

## Snippets (1 file, growing)

Located in `claude-config/snippets/`. Shared prompt fragments referenced from multiple agents to avoid duplication. Introduced in PR #97.

| File | Size | Purpose |
|------|-----:|---------|
| `verify-commands.md` | 1.6 KB | Canonical backend/frontend verification command catalog. Referenced from `_base.md`, `patch.md`, and `prove.md`. |

---

## Scripts (2 files)

Located in `claude-config/scripts/`. Standalone validators callable independently or from `install.sh`.

| File | Size | Purpose |
|------|-----:|---------|
| `validate-hooks.py` | 5.2 KB | Walks every hook command in `settings.json`, verifies each script path resolves. Skips `${CLAUDE_PLUGIN_ROOT}` references. **PR #82.** |
| `validate-paths-globs.py` | 2.6 KB | Validates rule-file path globs are well-formed. |

---

## Templates (8 entries)

Located in `claude-config/templates/`. Used by scaffolding commands and the orchestrate pipeline.

| Entry | Type | Size | Purpose |
|-------|------|-----:|---------|
| `agent-prompt.md` | file | 4.8 KB | Base agent prompt template (variable substitution). |
| `orchestrate-pipeline.md` | file | 8.2 KB | Per-agent prompt templates, validation gates, failure-context injection. |
| `orchestrate-parallel.md` | file | 7.8 KB | MAP fan-out, speculative PATCH, worktree mode, resume mode. |
| `orchestrate-mymoney-context.md` | file | 7.8 KB | Project-specific context for orchestrate runs in mymoney. |
| `fastapi-layered-pattern.md` | file | 23.6 KB | Layered FastAPI architecture reference (read by `/scaffold-project` and `/scaffold-module`). |
| `scaffold-fastapi-core.md` | file | 15.3 KB | FastAPI core scaffolding spec. |
| `scaffold-fastapi-auth.md` | file | 1.8 KB | FastAPI auth scaffolding spec. |
| `PLAN.md.template` | file | 2.4 KB | Template for per-project `PLAN.md`. |
| `github-actions/` | dir | — | GitHub Actions workflow templates. |

---

## Top-level claude-config files

| File | Size | Purpose |
|------|-----:|---------|
| `CLAUDE.md` | 6.6 KB | Top-level orientation file. Loaded into context at every session start. Symlinked to `~/.claude/CLAUDE.md`. |
| `README.md` | 10.7 KB | Repo README — install instructions, structure overview, command map. |
| `settings.json` | 3.7 KB | Hook registrations, plugin enablement, permissions, statusLine, skipDangerousModePermissionPrompt. Symlinked to `~/.claude/settings.json`. |
| `statusline.py` | 2.0 KB | Custom status bar (hostname, user, date, context %). |
| `install.sh` | 22.4 KB | Symlink installer + dependency setup + MCP registration + warm-up + hook validation. |
| `new-project-claude.sh` | 1.4 KB | Bootstrap a per-project `CLAUDE.md` skeleton. |

---

## Repo-level files (outside claude-config/)

### Knowledge surfaces (`knowledge/`)

Authority/scope/writer/reader for each surface lives in `specs/knowledge-surfaces.md`.

| Path | Count | Scope | Purpose |
|------|------:|-------|---------|
| `knowledge/patterns/pat-*.yaml` | 39 | global | Reusable code patterns with lifecycle metadata. Slug IDs match filename stems. `legacy_id: PAT-NNN` preserved for back-compat. |
| `knowledge/decisions/D-NNN.yaml` | 9 | per-project (`project:` field) | Architecturally significant decisions; cross-references via `linked.related_decisions`. |
| `knowledge/decisions/index.yaml` | 1 | global | By-project / by-topic index over the D-NNN files. |
| `knowledge/learning-rules/LR-NNN.yaml` | 6 | global | Failure-derived rules surfaced at SessionStart. |
| `knowledge/projects/<name>.yaml` | 7 | per-project | Project tracker (focus, status, blockers, next_steps, open_questions). Written by the `project` CLI. |

All forms use `schema_version: 1` (added in #145). The Knowledge MCP server, `knowledge.db`, `sync.py`, `velocity/`, `project-summaries/`, and `knowledge/specs/` were retired in Phase 6C (#146).

### MCP servers (`mcp-server/`)

| Server | Path | Language | Tools |
|--------|------|----------|-------|
| `vault-metrics` | `mcp-server/server.py` | Python (.venv) | `vault_status`, `vault_search`, `vault_dashboard`, `agent_metrics`, `failure_patterns`. |

The TypeScript `knowledge` MCP server was retired in Phase 6C (#146) — its data moved to filesystem YAMLs read directly by the `action`, `dashboard`, `project`, and `review-session` CLIs. The archived source lives at `_archived/knowledge-mcp/`.

### Migration scripts (`scripts/`)

| File | Purpose |
|------|---------|
| `scripts/migrate-pattern-ids-to-slugs.py` | One-shot migration from `PAT-NNN` to slug IDs (PR #87). Idempotent — re-running is a no-op. |

### CI (`.github/workflows/`)

| File | Size | Purpose |
|------|-----:|---------|
| `.github/workflows/validate.yml` | 1.7 KB | Pre-merge config validation. Runs on PRs touching `claude-config/`, `knowledge/`, `codex-config/`, `install*.sh`. **PR #98.** |

---

## Per-project files (in any project's `.agents/outputs/`)

When `/orchestrate` runs in a project, it produces artifacts in that project's `.agents/outputs/`:

| Filename pattern | Producer | When |
|------------------|----------|------|
| `map-{issue}-{mmddyy}.md` | MAP agent | COMPLEX tier |
| `plan-{issue}-{mmddyy}.md` | PLAN agent | COMPLEX tier |
| `map-plan-{issue}-{mmddyy}.md` | MAP-PLAN agent | SIMPLE tier |
| `discuss-{issue}-{mmddyy}.md` | DISCUSS agent | When `--discuss` is set |
| `test-plan-{issue}-{mmddyy}.md` | TEST-PLANNER agent | When `--with-tests` is set |
| `contract-{issue}-{mmddyy}.md` | CONTRACT agent | Fullstack tasks |
| `plan-check-{issue}-{mmddyy}.md` | PLAN-CHECK agent | COMPLEX tier only |
| `patch-{issue}-{mmddyy}.md` | PATCH agent | Always |
| `prove-{issue}-{mmddyy}.md` | PROVE agent | Always (PROVE-lite for TRIVIAL no longer runs through orchestrate) |
| `archive/*.md` | (post-merge) | Archived after PR merges |
| `claude_checkpoints/PERSISTENT_STATE.yaml` | state_manager | Across sessions |

Memory + metrics:

| File | Purpose |
|------|---------|
| `~/agents/.claude/memory/metrics.jsonl` | One JSON-line per orchestrate outcome. |
| `~/agents/.claude/memory/failures.jsonl` | One JSON-line per BLOCKED outcome with root_cause classification. |

---

## Where to look next

- High-level orientation: [`claude-config/CLAUDE.md`](https://github.com/jwj2002/agents/blob/main/claude-config/CLAUDE.md)
- All system diagrams: [Architecture Diagrams](architecture-diagrams.md)
- Term definitions: [Glossary](glossary.md)
