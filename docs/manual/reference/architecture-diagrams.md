# Architecture Diagrams

All system diagrams collected in one reference. These diagrams show how the components connect, how data flows, and how lifecycle events are sequenced.

## 1. Repository Structure

The `~/agents/` monorepo contains all Claude Code configuration alongside standalone agent projects.

```
~/agents/                              # Single git repo
  claude-config/                       # Claude Code configuration
    agents/          (11 .md files)    # Agent definitions
    commands/        (15 .md files)    # Slash commands
    hooks/           (6 .py files)     # Lifecycle hooks + shared modules
    rules/           (7 .md files)     # Conditional + always-loaded rules
    skills/          (3 directories)   # Multi-step workflows
    templates/       (2 entries)       # Prompt templates
    settings.json                      # Global settings
    statusline.py                      # Custom status bar
    install.sh                         # Symlink installer
  mcp-server/                          # Custom MCP server (5 tools)
  obsidian-agent/                      # Session -> vault writer
  code-review/                         # Pre-commit review agent
  daily-standup/                       # Standup report generator
  pr-changelog/                        # Post-merge changelog
  doc-reader/                          # Document TTS reader
  youtube-summarizer/                  # Video summarizer
```

## 2. Symlink Deployment

How version-controlled config in the repo maps to the paths Claude Code reads at runtime.

```
~/agents/claude-config/                ~/.claude/
  agents/          ---symlink--->        agents/
  commands/        ---symlink--->        commands/
  hooks/           ---symlink--->        hooks/
  rules/           ---symlink--->        rules/
  skills/          ---symlink--->        skills/
  settings.json    ---symlink--->        settings.json
  statusline.py    ---symlink--->        statusline.py

  NOT symlinked (machine-local):
                                         settings.local.json
                                         memory/
                                         projects/
```

Changes to the repo are live immediately --- symlinks mean no re-install is needed. Run `git pull` on another machine and updates propagate.

## 3. Hook Lifecycle Flow

The sequence of hook events from session start through completion, showing how state is persisted and restored.

```
SESSION START
  sessionstart_restore_state.py
    +- Load PERSISTENT_STATE.yaml
    +- Load patterns-critical.md
    +- Output ~500 tokens restored context
        |
        v
  [ SESSION WORK ]
        |
  Context limit? --YES--> PreCompact Hook
        |                   +- Extract state from transcript
        |                   +- Update PERSISTENT_STATE.yaml
        |                   +- Auto-delete >7 day files
        |<------------------+
        |
  Task complete? --YES--> Stop Hooks (sequential)
        |                   1. verify_completion.py
        |                      Exit 2 = block (uncommitted/TODOs)
        |                   2. notify_completion.py
        |                      macOS notification + iPhone
        v
  [continue working]
```

## 4. Task Routing Decision Tree

How incoming tasks are classified by complexity tier and routed to the appropriate workflow.

```
Task / GitHub Issue
        |
  Classify Routing Tier
        |
  +-----+-------+----------+-----------+-----------+
  |     |       |          |           |           |
TRIVIAL SIMPLE MODERATE  COMPLEX   FULLSTACK  PRIOR FAIL
(1 file)(1-3)  (4-5)     (6+)      (any)      (any)
  |     |       |          |           |           |
/quick  Plan    +--------- /orchestrate -----------+
        Mode    |          |           |           |
              SIMPLE     COMPLEX    SIMPLE or   SIMPLE or
              pipeline   pipeline   COMPLEX +   COMPLEX +
                |          |        CONTRACT    failure ctx
                |          |           |           |
              MAP-PLAN  MAP->PLAN  MAP-PLAN or MAP->PLAN
                |          |           |           |
           PLAN-CHECK  PLAN-CHECK  CONTRACT(*)    |
                |          |           |           |
              PATCH      PATCH      PATCH       PATCH
                |          |           |           |
              PROVE      PROVE      PROVE       PROVE
                |          |           |           |
                +--------- /pr --------+----------+

(*) CONTRACT-lite if 0 new endpoints + <=2 frontend files
```

## 5. Parallel Worktree Sessions

How two concurrent `/orchestrate --parallel` sessions each get isolated worktrees with independent file systems.

```
Tab 1: /orchestrate 42 --parallel    Tab 2: /orchestrate 57 --parallel
  .worktrees/issue-42/ (isolated)      .worktrees/issue-57/ (isolated)
      |                                    |
      v                                    v
  PR from worktree branch              PR from worktree branch
      |                                    |
      v                                    v
  Merge -> worktree removed            Merge -> worktree removed
```

Each worktree has its own files, git index, and `.agents/outputs/`. `PERSISTENT_STATE.yaml` lives in the main repo so `--resume` can locate the worktree.

## 6. State Manager Functions

The `state_manager.py` API surface and which components call each function.

```
state_manager.py
  load_state()            <- read PERSISTENT_STATE.yaml
  update_phase()          <- orchestrate: before each agent
  clear_active()          <- orchestrate: after completion
  get_completed_phases()  <- --resume: skip finished phases
  get_active_work()       <- sessionstart + notify hooks
  get_worktree_for_issue()<- --parallel: find worktree path
  update_from_extracted() <- precompact: save transcript state

Callers: orchestrate (commands/), precompact, sessionstart, notify (hooks/)
```

## 7. Self-Learning Loop

How PROVE outcomes feed back into agent behavior through the `/learn` command and pattern files.

```
/orchestrate --> PROVE --> metrics.jsonl + failures.jsonl
                              |
                              v
                  /learn (weekly) --> patterns.md
                     +--apply     --> agent .md files (prevention checklists)
                     +--validate  --> before/after success rate comparison
                     +--cross-project --> aggregate across all projects
                              |
                              v
                  Next /orchestrate loads updated patterns via:
                    1. MCP failure_patterns() (preferred)
                    2. .claude/memory/patterns-critical.md (fallback)
                              |
                              v
                        Cycle repeats
```

## 8. MCP Pattern Loading

The fallback chain agents use to load failure patterns: MCP first, file-based second.

```
+---------------------+     +---------------------------+
|  Agent Pre-Flight   |---->|  MCP: failure_patterns()  |
|  (all agents via    |     |  MCP: agent_metrics(30d)  |
|   _base.md section 1)|    +-------------+-------------+
|                     |                   |
|                     |                   | fails?
|                     |                   v
|                     |     +---------------------------+
|                     |---->|  File: patterns-critical  |
|                     |     |  File: patterns-full.md   |
+---------------------+     +---------------------------+
```

Agents prefer MCP tools over file reads for pattern data. MCP provides structured JSON responses. File-based loading is the fallback when MCP is unavailable.

## 9. Obsidian Data Flow

How Claude Code session data flows through the Obsidian agent into the vault, and which downstream tools consume it.

```
Claude Code Sessions (.claude/projects/*/session.jsonl)
        |
        v
obsidian-agent (Haiku) --+--> Obsidian Vault (STATUS.md, Daily, DASHBOARD)
                         |       |
                         |       +--> mcp-server (vault_status/search/dashboard)
                         |       +--> daily-standup (reads vault)
                         |       +--> pr-changelog (writes to vault)
                         |
                         +--> .claude/memory/ (metrics.jsonl, failures.jsonl)
                                 +--> /learn, /metrics, mcp-server
```

## 10. Cross-Model Review

How three AI models (Opus, Haiku, Codex) divide responsibilities across implementation, review, and validation.

```
Claude Opus (Primary)          Claude Haiku (Review)
  /orchestrate, /spec-draft      code-reviewer, obsidian-agent
  Implementation, reasoning      Lightweight proactive review
        |                              |
        +----------+-------------------+
                   v
          Codebase (main branch)
                   |
                   v
          Codex (OpenAI) -- Spec validation, secondary check
```

Claude Opus handles primary development. Claude Haiku runs lightweight proactive code reviews and extracts session data to the Obsidian vault. Codex provides an independent review perspective from a different model family.
