# Glossary

Terms used throughout this documentation, defined in the context of the agentic engineering workflow.

## A

**Agent**
A specialized AI role with a defined purpose, input requirements, output format, and verification gates. Each agent in the pipeline (MAP, PLAN, PATCH, PROVE) performs one phase of work and produces a named artifact. Agent definitions are markdown files in `~/.claude/agents/`. All agents inherit from `_base.md` which provides pre-flight checklists, artifact naming, and the AGENT_RETURN directive.

**Artifact**
A markdown file produced by an agent during the orchestrate pipeline. Named with the pattern `{agent}-{issue}-{mmddyy}.md` and stored in `.agents/outputs/`. Each agent validates that its required predecessor artifacts exist before starting. After PR merge, artifacts are moved to the `archive/` subdirectory.

**Atomic Commits**
The practice of committing after each logical change group during PATCH, rather than one monolithic commit. Enables `git bisect` and granular revertability. Format: `type(#issue): description`.

**Anti-Rationalization**
A failure mode where AI agents declare a task complete when it is not. The `verify_completion.py` Stop hook combats this by checking for uncommitted changes and TODO/FIXME markers before allowing session completion.

## B

**Behavioral Evals**
A set of verification checks that PROVE runs against changed files. Mapped via `eval-file-mapping.md` so only relevant evals run based on which files changed.

## C

**Context Monitor**
A PostToolUse hook (`context_monitor.py`) that warns when the context window is running low --- WARNING at 35% remaining, CRITICAL at 25%.

**Context Window**
The agent's working memory --- everything it can "see" at once, including instructions, conversation history, file contents, and tool results. When the context fills up, older content gets compressed or dropped. Every token of instructions competes with code context.

**CONTRACT**
An agent phase (phase 2.5) that defines the interface between frontend and backend before implementation begins. Specifies endpoint schemas, enum VALUES, authentication requirements, and authorization patterns. Mandatory for fullstack issues.

**CONTRACT-lite**
An inline version of CONTRACT used for simple fullstack issues (0 new endpoints, 2 or fewer frontend files). Skips spawning a separate agent and documents the contract within the MAP-PLAN artifact instead.

**Complexity Classification**
Two related tier systems are used to categorize and route tasks:

*Routing tiers* (6 levels) determine how a task is handled: TRIVIAL (1 file, routed to `/quick`), SIMPLE (1-3 files, routed to Plan Mode), MODERATE (4-5 files, routed to `/orchestrate` with SIMPLE pipeline), COMPLEX (6+ files, routed to `/orchestrate` with COMPLEX pipeline), FULLSTACK (any file count, routed to `/orchestrate` with mandatory CONTRACT), and PRIOR FAIL (any file count, routed to `/orchestrate` with failure context injection).

*Pipeline tiers* (3 levels) determine which agents run inside `/orchestrate`: TRIVIAL (MAP-PLAN, PATCH, PROVE-lite), SIMPLE (MAP-PLAN, CONTRACT*, PLAN-CHECK, PATCH, PROVE), and COMPLEX (MAP, PLAN, CONTRACT*, PLAN-CHECK, PATCH, PROVE). The MAP or MAP-PLAN agent determines the pipeline tier after investigating the codebase.

## D

**DISCUSS**
An optional agent (phase 0.5) that identifies 2-5 gray areas in issue requirements and captures implementation decisions before MAP-PLAN runs. Triggered by `--discuss` flag.

## F

**FULLSTACK (routing tier)**
A routing tier applied to any task that crosses the frontend/backend boundary, regardless of file count. FULLSTACK tasks are routed to `/orchestrate` with a mandatory CONTRACT agent phase to define the interface between frontend and backend before implementation.

**Failure Taxonomy**
The set of 12 canonical root cause codes used to classify agent failures: VERIFICATION_GAP, ENUM_VALUE, COMPONENT_API, MULTI_MODEL, SQLITE_COMPAT, ACCESS_CONTROL, API_MISMATCH, MISSING_TEST, STRUCTURE_VIOLATION, SCOPE_CREEP, LINT_ERROR, and OTHER. Every failure is classified into exactly one code, enabling automated pattern analysis.

## H

**Hook**
A Python script attached to a Claude Code lifecycle event. Hooks fire at specific moments --- SessionStart, PreCompact, Stop --- to manage state persistence, inject context, and enforce quality gates. Configured in `settings.json`.

## L

**Learning Loop**
The continuous improvement cycle: `/orchestrate` executes issues, PROVE records outcomes to `metrics.jsonl` and `failures.jsonl`, `/learn` extracts patterns from failures, `/learn --apply` writes prevention checklists into agent files, and the next `/orchestrate` session loads the updated agents. This cycle runs weekly.

## M

**MODERATE (routing tier)**
A routing tier for tasks involving 4-5 files with clear requirements. MODERATE tasks are routed to `/orchestrate` using the SIMPLE pipeline tier. Codex review is recommended but not automatic.

**MAP**
The investigation agent for COMPLEX issues (phase 1). Read-only --- it explores the codebase, reads specs, and documents component APIs, enum values, and file structures. Produces a 150-200 line artifact used by the PLAN agent.

**MAP-PLAN**
A combined investigation and planning phase for TRIVIAL and SIMPLE issues. Merges the MAP (investigation) and PLAN (architecture) phases into a single agent pass, reducing overhead for straightforward changes. Produces a 350-450 line artifact.

**MCP (Model Context Protocol)**
A protocol for providing AI agents with structured access to external data sources. In this system, the custom `vault-metrics` MCP server exposes five tools: `vault_status`, `vault_search`, `vault_dashboard`, `agent_metrics`, and `failure_patterns`.

**Metrics**
Structured outcome data recorded as JSON lines in `metrics.jsonl`. Each completed issue gets one record containing: issue number, date, status (PASS/BLOCKED), complexity, stack type, agents run, agent versions, root cause (if failed), and duration. Analyzed by `/learn` and `/metrics`.

## O

**Orchestrate**
The primary workflow command (`/orchestrate`) that takes a GitHub issue number and executes a multi-agent pipeline: MAP, PLAN, CONTRACT, PATCH, PROVE. Supports flags for test planning (`--with-tests`), session resumption (`--resume`), and parallel execution (`--parallel`).

## P

**Pipeline Tier**
One of three agent sequences used inside `/orchestrate`: TRIVIAL (MAP-PLAN, PATCH, PROVE-lite), SIMPLE (full agent chain with MAP-PLAN), or COMPLEX (full agent chain with separate MAP and PLAN). Distinct from routing tiers, which determine whether a task reaches `/orchestrate` at all.

**PRIOR FAIL (routing tier)**
A routing tier applied to any task that previously failed. PRIOR FAIL tasks are routed to `/orchestrate` with the prior failure's root cause and prevention recommendation injected into agent context.

**PATCH**
The implementation agent (phase 3) and the only agent in the pipeline that modifies code. Reads the plan and contract artifacts, runs pre-flight checklists, implements changes, and runs pre-submission gates (lint, format, tests). If fullstack work is detected without a CONTRACT artifact, PATCH stops immediately.

**Pattern**
A documented failure mode with trigger conditions and prevention steps. Patterns are extracted from `failures.jsonl` by the `/learn` command and stored in tiered files: `patterns-critical.md` (always loaded, ~50 lines), `patterns-full.md` (loaded for COMPLEX issues, ~660 lines), and `core-patterns.md` (always-loaded rule, 12 lines).

**PERSISTENT_STATE**
A YAML file (`.agents/outputs/claude_checkpoints/PERSISTENT_STATE.yaml`) that tracks the current workflow state: active issue, branch, phase, completed phases, and worktree path. Managed by `state_manager.py` and used by hooks, orchestrate, `--resume`, and `--parallel`.

**Post-Merge Verification**
An automated ops check added to the `/pr` workflow that verifies main is healthy after merging --- prevents "merged but broken" situations.

**PROVE**
The final agent phase (phase 4) that verifies implementation, records outcomes to `metrics.jsonl` and `failures.jsonl`, and classifies any failures by root cause code. Uses multi-level verification: EXISTS, SUBSTANTIVE, WIRED, FUNCTIONAL.

**PROVE-lite**
A reduced verification pass for TRIVIAL issues. Runs only the basic verification gates (file exists, lint passes, tests pass) without the full multi-level review that PROVE performs on SIMPLE and COMPLEX issues.

**Prompt Template**
A markdown file with variable placeholders used to generate agent spawn prompts. The shared template at `templates/agent-prompt.md` accepts variables like `{AGENT_ROLE}`, `{ISSUE_NUMBER}`, and `{PREDECESSOR_ARTIFACTS}` to produce consistent prompts across all agents.

## R

**Runbook**
A structured troubleshooting reference stored in `.claude/memory/runbooks.md`. Agents check runbooks before investigating from scratch, reducing time on known problems.

**Routing Tier**
One of six classification levels that determine how a task is handled: TRIVIAL (`/quick`), SIMPLE (Plan Mode), MODERATE (`/orchestrate` with SIMPLE pipeline), COMPLEX (`/orchestrate` with COMPLEX pipeline), FULLSTACK (`/orchestrate` with mandatory CONTRACT), or PRIOR FAIL (`/orchestrate` with failure context). See also: Pipeline Tier.

**Rule**
A markdown file in `~/.claude/rules/` that provides instructions to agents. Rules can be always-loaded (`alwaysApply: true`) or conditionally loaded based on file path globs. Rules encode failure prevention, architectural patterns, and workflow constraints.

## S

**Seed**
A deferred idea captured with a trigger condition via `/seed`. Seeds surface automatically during `/orchestrate` when the current issue's scope matches the trigger. Stored in `.planning/seeds/`.

**Skill**
A multi-step workflow defined in `~/.claude/skills/`. Skills are more complex than single commands and include their own reference documentation. Current skills: `orchestrate` (multi-agent pipeline), `test-plan` (test matrix generation), and `spec-review` (spec analysis and issue creation).

**Slash Command**
A user-invokable command defined as a markdown file in `~/.claude/commands/`. Examples: `/orchestrate`, `/pr`, `/learn`, `/metrics`, `/scaffold-project`. Commands encode workflow logic and can spawn agents, create PRs, or analyze data.

**State Manager**
The centralized Python module (`hooks/state_manager.py`) that handles all reads and writes to `PERSISTENT_STATE.yaml`. Used by orchestrate (update phase), precompact hook (save transcript state), sessionstart hook (restore context), and the `--resume`/`--parallel` flags.

## W

**Worktree**
A git worktree created for parallel issue processing. The `--parallel` flag on `/orchestrate` creates an isolated worktree at `.worktrees/issue-{N}/` branched from `origin/main`. Each worktree has its own files, git index, and artifacts. Managed by `worktree_manager.py`.

**Worktree Manager**
The Python module (`hooks/worktree_manager.py`) that handles git worktree lifecycle: creation, branch setup, file overlap detection, and cleanup after PR merge. Called by `/orchestrate --parallel` and `/pr`.
