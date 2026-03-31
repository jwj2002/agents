# Architecture Diagrams

All system diagrams collected in one reference. These diagrams show how the components connect, how data flows, and how lifecycle events are sequenced.

## 1. Repository Structure

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

## 4. Orchestrate Pipeline Decision Tree

```
GitHub Issue --> Classify Complexity
                    |
    +---------------+---------------+
    |               |               |
  TRIVIAL         SIMPLE          COMPLEX
  (1-2 files)     (3-5 files)     (6+ files)
    |               |               |
  MAP-PLAN        MAP-PLAN      MAP -> PLAN
    |               |               |
    |          fullstack? -----> CONTRACT(*)
    |               |               |
    |          PLAN-CHECK       PLAN-CHECK
    |               |               |
  PATCH           PATCH           PATCH
    |               |               |
  PROVE-lite      PROVE           PROVE
    |               |               |
    +------------- /pr -------------+

(*) CONTRACT-lite if 0 new endpoints + <=2 frontend files
```

## 5. Parallel Worktree Sessions

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
