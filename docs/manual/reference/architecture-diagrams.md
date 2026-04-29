# Architecture Diagrams

All system diagrams in one reference. These show how the components connect, how data flows, and how lifecycle events sequence.

---

## 1. Repository Structure

The `~/agents/` monorepo contains all Claude Code configuration alongside standalone agent projects.

```
~/agents/                                # single git repo
  claude-config/                         # Claude Code configuration (symlinked into ~/.claude/)
    agents/          (12 .md files)      # Agent definitions
    commands/        (16 .md files)      # Slash commands
    rules/           (12 .md files)      # Always-loaded + path-scoped rules
    hooks/           (10 .py files)      # Lifecycle hooks + shared modules
    skills/                              # Workflow skills (linked from ~/.claude/skills)
    snippets/                            # Shared prompt snippets (verify-commands.md)
    scripts/                             # Validators (validate-hooks.py, validate-paths-globs.py)
    templates/       (8 entries)         # Prompt + scaffold templates
    settings.json                        # Hook registrations, plugins, permissions
    statusline.py                        # Custom status bar
    install.sh                           # Symlink + dependency installer
    CLAUDE.md                            # Top-level orientation file
  knowledge/                             # Knowledge graph (YAML source of truth)
    patterns/        (39 .yaml files)    # Patterns with slug IDs (pat-<stem>)
    decisions/                           # Decision log
    learning_rules/                      # Learning rules
    projects/                            # Project state snapshots
    specs/                               # Spec docs
    sync.py                              # Builds knowledge.db from YAMLs
  knowledge-mcp/                         # MCP server for knowledge graph
  mcp-server/                            # MCP server for vault-metrics
  obsidian-agent/                        # Session → Obsidian vault writer
  code-review/                           # Pre-commit review agent
  daily-standup/                         # Standup report generator
  pr-changelog/                          # Post-merge changelog
  doc-reader/                            # Document TTS reader
  youtube-summarizer/                    # Video summarizer
  email-helper/                          # Mail integration
  frontend-design/                       # Frontend design helpers
  scripts/                               # Repo-wide tooling
  docs/                                  # This manual + supporting docs
  .github/
    workflows/validate.yml               # CI: validates config on PR
```

---

## 2. Symlink Deployment

`install.sh` installs the Claude config by symlinking pieces of `claude-config/` into `~/.claude/`. The repo is the source of truth; `~/.claude/` is the runtime view.

```mermaid
flowchart LR
    subgraph repo["~/agents/claude-config/ (source of truth, version-controlled)"]
        rc_settings[settings.json]
        rc_claude[CLAUDE.md]
        rc_agents[agents/]
        rc_cmds[commands/]
        rc_rules[rules/]
        rc_hooks[hooks/]
        rc_skills[skills/]
        rc_snip[snippets/]
        rc_status[statusline.py]
    end

    subgraph deployed["~/.claude/ (runtime, machine-specific)"]
        d_settings[settings.json]
        d_claude[CLAUDE.md]
        d_agents[agents/]
        d_cmds[commands/]
        d_rules[rules/]
        d_hooks[hooks/]
        d_skills[skills/]
        d_status[statusline.py]
        d_mcp[".claude.json (MCP servers)"]
    end

    install["install.sh"]
    mcpadd["claude mcp add --scope user"]
    npmwarm["npm cache warm-up<br/>(context7, apple-mcp)"]

    install -.symlinks.-> d_settings
    install -.symlinks.-> d_claude
    install -.symlinks.-> d_agents
    install -.symlinks.-> d_cmds
    install -.symlinks.-> d_rules
    install -.symlinks.-> d_hooks
    install -.symlinks.-> d_skills
    install -.symlinks.-> d_status

    rc_settings -.-> d_settings
    rc_claude -.-> d_claude
    rc_agents -.-> d_agents
    rc_cmds -.-> d_cmds
    rc_rules -.-> d_rules
    rc_hooks -.-> d_hooks
    rc_skills -.-> d_skills
    rc_status -.-> d_status

    install --> mcpadd
    mcpadd --> d_mcp
    install --> npmwarm
```

`settings.json` lives in the repo and is symlinked, so editing the runtime config means editing source. MCP servers are not symlinked — they're registered per machine via `claude mcp add --scope user` which writes to `~/.claude.json`.

---

## 3. Configuration Loading at Session Start

When you start `claude`, the harness loads configuration in a specific order and triggers SessionStart hooks before you can interact.

```mermaid
sequenceDiagram
    participant User
    participant CLI as Claude Code CLI
    participant Settings as ~/.claude/settings.json
    participant Hooks as SessionStart hooks
    participant State as PERSISTENT_STATE.yaml
    participant MCP as MCP servers
    participant Plugins as Plugin commands

    User->>CLI: claude (start session)
    CLI->>Settings: load permissions, plugins, hook table
    CLI->>Plugins: load enabled plugin commands
    CLI->>MCP: spawn each registered MCP server (~/.claude.json)
    Note over MCP: knowledge, vault-metrics, context7, apple-mcp
    CLI->>Hooks: fire SessionStart hooks in order
    Hooks->>State: sessionstart_restore_state.py reads PERSISTENT_STATE
    Hooks->>Hooks: load_learning_rules.py (LR-001, LR-002, ...)
    Hooks-->>CLI: stdout becomes session context
    CLI-->>User: ready prompt
```

---

## 4. Issue → PR Pipeline (Orchestrate)

The full flow from a GitHub issue to a merged PR. Tier classification routes the work; some phases are conditional.

```mermaid
flowchart TD
    issue([GitHub issue #N])
    classify{"Classify<br/>complexity"}

    issue --> classify

    classify -- "TRIVIAL" --> redirect["/orchestrate rejects<br/>→ redirect to /quick"]
    classify -- "SIMPLE" --> simple_branch["create feature/issue-N-...<br/>off origin/main"]
    classify -- "COMPLEX" --> complex_branch["create feature/issue-N-...<br/>off origin/main"]
    classify -- "FULLSTACK" --> complex_branch

    simple_branch --> simple_pipeline

    subgraph simple_pipeline["SIMPLE pipeline"]
        s_discuss["[DISCUSS]<br/>(if --discuss)"] --> s_mapplan[MAP-PLAN]
        s_mapplan --> s_test["[TEST-PLANNER]<br/>(if --with-tests)"]
        s_test --> s_contract["[CONTRACT]<br/>(if fullstack)"]
        s_contract --> s_patch[PATCH]
        s_patch --> s_prove[PROVE]
    end

    complex_branch --> complex_pipeline

    subgraph complex_pipeline["COMPLEX pipeline"]
        c_discuss["[DISCUSS]<br/>(if --discuss)"] --> c_map[MAP]
        c_map --> c_plan[PLAN]
        c_plan --> c_test["[TEST-PLANNER]<br/>(if --with-tests)"]
        c_test --> c_contract["[CONTRACT]<br/>(if fullstack)"]
        c_contract --> c_check[PLAN-CHECK]
        c_check --> c_patch[PATCH]
        c_patch --> c_prove[PROVE]
    end

    s_prove --> pr_workflow
    c_prove --> pr_workflow

    subgraph pr_workflow["/pr workflow"]
        pr_fresh[Fresh-context review]
        pr_codex{"COMPLEX-tier<br/>signals?"}
        pr_codex_run["recommend<br/>/codex:adversarial-review"]
        pr_create[gh pr create]
        pr_ci[".github/workflows/<br/>validate.yml"]
        pr_squash[squash merge]
        pr_postmerge[post-merge hook<br/>rebuilds knowledge.db]

        pr_fresh --> pr_codex
        pr_codex -- yes --> pr_codex_run
        pr_codex_run --> pr_create
        pr_codex -- no --> pr_create
        pr_create --> pr_ci
        pr_ci --> pr_squash
        pr_squash --> pr_postmerge
    end

    pr_postmerge --> learn[record outcome to<br/>metrics.jsonl + failures.jsonl]
```

---

## 5. Tier Routing Decision Tree

Every task is classified by complexity. The routing is mostly deterministic; gray areas use `--discuss` to capture design decisions before MAP/PLAN runs.

```mermaid
flowchart TD
    task([Task arrives])
    files{"How many<br/>files?"}

    task --> files

    files -- "1, obvious" --> trivial["TRIVIAL<br/>→ /quick<br/>(no pipeline)"]
    files -- "1-3" --> simple_q
    files -- "4-5" --> moderate_q
    files -- "6+" --> complex_q
    files -- "any (cross-stack)" --> fullstack_q

    simple_q{"Risk profile?"}
    simple_q -- low --> simple["SIMPLE<br/>→ /orchestrate"]
    simple_q -- medium --> moderate["MODERATE<br/>→ /orchestrate SIMPLE tier<br/>+ Codex review recommended"]

    moderate_q{"Cross-cutting?"}
    moderate_q -- yes --> complex
    moderate_q -- no --> moderate

    complex_q{"Cross-cutting<br/>or migration?"}
    complex_q -- yes --> complex["COMPLEX<br/>→ /orchestrate COMPLEX tier<br/>+ Codex review recommended"]
    complex_q -- no --> moderate

    fullstack_q{"Backend +<br/>frontend?"}
    fullstack_q -- yes --> fullstack["FULLSTACK<br/>→ /orchestrate + CONTRACT<br/>+ Codex review (enum/API focus)"]

    classDef trivialStyle fill:#e0f7e0,stroke:#2d8a2d
    classDef simpleStyle fill:#e0f0ff,stroke:#3060c0
    classDef complexStyle fill:#fff0d0,stroke:#c08030
    classDef fullStackStyle fill:#ffe0e0,stroke:#c03030
    class trivial trivialStyle
    class simple,moderate simpleStyle
    class complex complexStyle
    class fullstack fullStackStyle
```

---

## 6. Hook Lifecycle

Hooks attach to specific Claude Code lifecycle events. Each hook is a Python script registered in `settings.json`.

```mermaid
sequenceDiagram
    participant User
    participant CLI as Claude Code
    participant SS as SessionStart
    participant PT as PreToolUse
    participant Tool as Tool execution
    participant PoT as PostToolUse
    participant PC as PreCompact
    participant Stop as Stop

    User->>CLI: start session
    CLI->>SS: fire SessionStart hooks
    Note over SS: sessionstart_restore_state.py<br/>load_learning_rules.py
    SS-->>CLI: hooks return stdout to context

    loop tool calls
        CLI->>PT: fire PreToolUse hooks (if any)
        PT-->>CLI: exit 0 (allow) or exit 2 (block)
        CLI->>Tool: execute tool
        Tool-->>CLI: result
        CLI->>PoT: fire PostToolUse hooks
        Note over PoT: context_monitor.py
    end

    opt context approaching limit
        CLI->>PC: fire PreCompact hooks
        Note over PC: precompact_checkpoint.py<br/>(saves state to PERSISTENT_STATE.yaml)
        PC-->>CLI: state saved
    end

    User->>CLI: stop / end session
    CLI->>Stop: fire Stop hooks in order
    Note over Stop: 1. verify_completion.py<br/>2. notify_completion.py<br/>3. session_end_context_update.py
    Stop-->>CLI: warnings / notifications
    CLI-->>User: end
```

---

## 7. Self-Learning Loop

Every orchestrate outcome is recorded. Failures get root-cause classified, aggregated into patterns, and surface back through the agent pre-flight.

```mermaid
flowchart LR
    issue([Issue]) --> orchestrate[/orchestrate run]
    orchestrate --> outcome{"PROVE result"}

    outcome -- PASS --> metrics_pass["metrics.jsonl<br/>(success record)"]
    outcome -- BLOCKED --> failure_record["failures.jsonl<br/>(root_cause, files, prevention)"]
    outcome -- BLOCKED --> metrics_fail["metrics.jsonl<br/>(failure record)"]

    failure_record --> learn["/learn (weekly)"]
    metrics_pass --> learn
    metrics_fail --> learn

    learn --> patterns["knowledge/patterns/*.yaml<br/>(new + updated)"]
    learn --> rules["knowledge/learning_rules/<br/>(prevention rules)"]

    patterns --> sync[knowledge/sync.py build]
    rules --> sync
    sync --> db[(knowledge.db)]

    db --> mcp[vault-metrics MCP]
    mcp --> preflight[Agent pre-flight<br/>at next session start]

    preflight --> orchestrate

    classDef recordStyle fill:#fff0d0,stroke:#c08030
    classDef knowledgeStyle fill:#e0f0ff,stroke:#3060c0
    classDef agentStyle fill:#e0f7e0,stroke:#2d8a2d
    class metrics_pass,metrics_fail,failure_record recordStyle
    class patterns,rules,db,mcp knowledgeStyle
    class orchestrate,preflight agentStyle
```

---

## 8. MCP Server Topology

Five MCP servers extend Claude Code with structured tool APIs. Two are local processes from this repo; three come from npm packages.

```mermaid
flowchart TB
    cli[Claude Code session]

    subgraph local["Local processes (this repo)"]
        knowledge["knowledge<br/>(tsx + index.ts)"]
        vault["vault-metrics<br/>(.venv/python + server.py)"]
    end

    subgraph npm["npm-launched (warmed by install.sh)"]
        context7["context7<br/>(npx -y @upstash/context7-mcp@latest)"]
        apple["apple-mcp<br/>(npx -y apple-mcp@latest)<br/>macOS only"]
        playwright["playwright<br/>(via Claude plugin)"]
    end

    cli -- "stdio" --> knowledge
    cli -- "stdio" --> vault
    cli -- "stdio" --> context7
    cli -- "stdio" --> apple
    cli -- "stdio" --> playwright

    knowledge --> kdb[(knowledge.db)]
    vault --> vault_data["~/agents/.claude/memory/<br/>+ Obsidian vault"]
    context7 --> registry["upstash docs registry<br/>(network)"]
    apple --> apple_apps["macOS apps<br/>(Calendar, Mail, Notes...)"]
    playwright --> browser["headless browser<br/>(navigate, click, screenshot)"]

    classDef localStyle fill:#e0f7e0,stroke:#2d8a2d
    classDef remoteStyle fill:#fff0d0,stroke:#c08030
    class knowledge,vault localStyle
    class context7,apple,playwright remoteStyle
```

---

## 9. Knowledge Graph Data Flow

The knowledge graph is YAML files in git, built into a local SQLite database, surfaced to agents via the MCP server.

```mermaid
flowchart LR
    subgraph yaml["YAML source (git)"]
        patterns["knowledge/patterns/*.yaml<br/>(39 files, slug IDs)"]
        decisions["knowledge/decisions/*.yaml"]
        rules["knowledge/learning_rules/*.yaml"]
        projects["knowledge/projects/*.yaml"]
    end

    subgraph build["Build (local)"]
        guard["sync.py:<br/>uniqueness guard<br/>(refuses duplicate IDs)"]
        sync["knowledge/sync.py build"]
    end

    db[(knowledge.db<br/>SQLite)]

    subgraph access["Access"]
        mcp["knowledge MCP server<br/>(query interface)"]
        agents["Agents<br/>(pre-flight pattern lookup)"]
        cli["Manual queries<br/>(agents/_base.md)"]
    end

    posthook["post-merge hook<br/>(install.sh-installed)"]
    pull["git pull"]

    pull --> posthook
    posthook --> sync

    patterns --> guard
    guard --> sync
    decisions --> sync
    rules --> sync
    projects --> sync
    sync --> db

    db --> mcp
    mcp --> agents
    mcp --> cli

    classDef sourceStyle fill:#e0f0ff,stroke:#3060c0
    classDef buildStyle fill:#fff0d0,stroke:#c08030
    classDef accessStyle fill:#e0f7e0,stroke:#2d8a2d
    class patterns,decisions,rules,projects sourceStyle
    class guard,sync,posthook buildStyle
    class mcp,agents,cli accessStyle
```

---

## 10. Codex × Claude Collaboration

Two AI models, complementary roles. Claude is the conductor; Codex is the second-opinion reviewer for risky work.

```mermaid
flowchart TD
    task([Task])

    claude["Claude<br/>(implementation, orchestration)"]
    task --> claude
    claude --> impl[implements via /orchestrate or /quick]

    impl --> prove[PROVE pass]

    prove --> tier_check{"Tier signals<br/>(MODERATE+,<br/>auth/data/migration)?"}

    tier_check -- "TRIVIAL/SIMPLE,<br/>low risk" --> commit_simple["commit + /pr<br/>(no Codex)"]

    tier_check -- "MODERATE/COMPLEX/<br/>FULLSTACK" --> pr_gate["/pr advisory gate"]

    pr_gate --> codex_review["/codex:adversarial-review<br/>(separate model, fresh context)"]

    codex_review --> findings{"Findings?"}
    findings -- "BLOCKING" --> fix[fix issues<br/>re-run PROVE]
    findings -- "NON-BLOCKING" --> commit_pr["commit + /pr<br/>(notes in PR body)"]
    findings -- "CLEAN" --> commit_pr

    fix --> prove

    commit_simple --> ci[".github/workflows/<br/>validate.yml"]
    commit_pr --> ci
    ci --> merge[squash merge]

    classDef claudeStyle fill:#fff0d0,stroke:#c08030
    classDef codexStyle fill:#e0f0ff,stroke:#3060c0
    classDef gateStyle fill:#e0f7e0,stroke:#2d8a2d
    class claude,impl,prove,fix claudeStyle
    class codex_review codexStyle
    class pr_gate,ci,tier_check gateStyle
```

---

## 11. Multi-Machine Pattern Coordination

Pattern IDs use slugs derived from filenames. This makes multi-machine pattern authoring collision-free by construction — git's filename-uniqueness handles the coordination.

```mermaid
sequenceDiagram
    participant LapA as Laptop A
    participant Git as origin/main
    participant LapB as Laptop B

    Note over LapA,LapB: Both clone the repo and run install.sh

    par Same starting state
        LapA->>Git: git pull
        LapB->>Git: git pull
    end

    Note over LapA,LapB: Different patterns scenario (no conflict)
    LapA->>LapA: author pat-fastapi-foo.yaml
    LapB->>LapB: author pat-react-bar.yaml
    LapA->>Git: PR #X (merges)
    LapB->>Git: PR #Y (merges)
    Note over Git: Both land cleanly — different filenames, different IDs

    Note over LapA,LapB: Same pattern scenario (conflict surfaces)
    LapA->>LapA: author pat-auth-jwt.yaml (content A)
    LapB->>LapB: author pat-auth-jwt.yaml (content B)
    LapA->>Git: PR #X (merges first)
    LapB->>Git: PR #Y push
    Git-->>LapB: real merge conflict<br/>(same filename, different content)
    Note over LapB: Human resolves consciously — are they actually the same pattern?

    Note over Git: sync.py duplicate-ID guard fires post-merge<br/>if anything slips past
```

---

## 12. Pre-Merge Gate Stack

A PR passes through several gates before reaching `main`. Each gate catches a different class of regression.

```mermaid
flowchart TD
    branch[Feature branch<br/>committed + pushed]

    gate1[/pr command]
    branch --> gate1

    subgraph local_gates["Local-machine gates (in /pr)"]
        fresh["Pre-PR fresh-context review<br/>(pr-fresh-reviewer subagent)"]
        codex_check{"COMPLEX<br/>signals?"}
        codex_run["/codex:adversarial-review<br/>(advisory; user invokes)"]
    end

    gate1 --> fresh
    fresh --> codex_check
    codex_check -- yes --> codex_run
    codex_check -- no --> create_pr
    codex_run --> create_pr

    create_pr[gh pr create]

    subgraph ci_gates["GitHub Actions gates (.github/workflows/validate.yml)"]
        v_json["settings.json valid JSON"]
        v_bash["install.sh syntax (bash -n)"]
        v_hooks["validate-hooks.py<br/>(every hook script path resolves)"]
        v_sync["sync.py build<br/>(catches duplicate pattern IDs,<br/>schema drift)"]
        v_slug["pattern slug invariant<br/>(every id matches filename)"]
    end

    create_pr --> v_json
    v_json --> v_bash
    v_bash --> v_hooks
    v_hooks --> v_sync
    v_sync --> v_slug
    v_slug --> ready{"All<br/>green?"}

    ready -- no --> fail[block merge]
    ready -- yes --> merge[squash merge]

    merge --> postmerge["post-merge hook<br/>(rebuilds knowledge.db,<br/>re-runs install.sh if config changed)"]

    classDef localStyle fill:#fff0d0,stroke:#c08030
    classDef ciStyle fill:#e0f0ff,stroke:#3060c0
    classDef finalStyle fill:#e0f7e0,stroke:#2d8a2d
    class fresh,codex_check,codex_run localStyle
    class v_json,v_bash,v_hooks,v_sync,v_slug ciStyle
    class merge,postmerge finalStyle
```

---

## 13. Failure → Pattern Feedback Cycle

Detail of how a single failure becomes a prevention rule that future agents apply automatically.

```mermaid
flowchart LR
    failure([Agent fails PROVE])

    classify["Classify root cause<br/>(11 codes: ENUM_VALUE,<br/>COMPONENT_API, etc.)"]
    failure --> classify

    record["Append to failures.jsonl<br/>{root_cause, files, agent,<br/>prevention}"]
    classify --> record

    weekly["/learn (weekly)<br/>aggregate by root_cause"]
    record --> weekly

    threshold{"Frequency<br/>≥ threshold?"}
    weekly --> threshold

    threshold -- no --> hold[remain in failures.jsonl<br/>for next aggregation]
    threshold -- yes --> author["Author or update<br/>knowledge/patterns/<br/>pat-rootcause.yaml"]

    author --> review["Human review<br/>+ commit"]
    review --> sync[sync.py rebuild]
    sync --> mcp[vault-metrics MCP<br/>now exposes the pattern]

    mcp --> preflight[next agent pre-flight<br/>loads pattern automatically]
    preflight --> avoidance[future agents<br/>avoid the failure mode]

    classDef failStyle fill:#ffe0e0,stroke:#c03030
    classDef analysisStyle fill:#fff0d0,stroke:#c08030
    classDef knowledgeStyle fill:#e0f0ff,stroke:#3060c0
    classDef preventionStyle fill:#e0f7e0,stroke:#2d8a2d
    class failure,record failStyle
    class classify,weekly,threshold,author analysisStyle
    class sync,mcp knowledgeStyle
    class preflight,avoidance preventionStyle
```

---

## 14. State Continuity Across Sessions

Orchestrate workflows can span multiple sessions. State persists via the PreCompact and SessionStart hooks.

```mermaid
sequenceDiagram
    participant S1 as Session 1
    participant State as PERSISTENT_STATE.yaml
    participant Disk as disk
    participant S2 as Session 2

    S1->>S1: /orchestrate 184<br/>completes MAP-PLAN
    S1->>State: state_manager.update_phase(PATCH, "starting")
    State->>Disk: write yaml

    Note over S1: context approaching limit
    S1->>State: PreCompact hook checkpoints transcript
    State->>Disk: write checkpoint
    Note over S1: session ends

    S2->>S2: claude (start new session)
    S2->>Disk: SessionStart reads PERSISTENT_STATE
    Disk-->>S2: active_work {issue 184, phase PATCH}
    S2->>S2: SessionStart hook injects state into context
    Note over S2: User can /orchestrate 184 --resume<br/>and skip MAP-PLAN
    S2->>S2: continue PATCH where Session 1 left off
    S2->>State: update_phase(PROVE, "passed")
    S2->>State: clear_active(184) when done
```

---

## 15. Slash Command Surface

The 16 user-facing slash commands grouped by purpose.

```mermaid
flowchart TB
    subgraph implementation["Implementation"]
        quick[/quick<br/>TRIVIAL/]
        orchestrate[/orchestrate<br/>SIMPLE+/]
    end

    subgraph issue_creation["Issue creation"]
        bug[/bug/]
        feature[/feature/]
        spec_draft[/spec-draft/]
        spec_review[/spec-review/]
        feature_from_spec["/feature-from-spec<br/>(internal helper)"]
    end

    subgraph quality["Quality + review"]
        review[/review/]
        test_plan[/test-plan/]
        pr[/pr/]
    end

    subgraph scaffolding["Scaffolding"]
        scaffold_proj[/scaffold-project/]
        scaffold_mod[/scaffold-module/]
    end

    subgraph learning["Learning + insight"]
        learn[/learn/]
        metrics[/metrics/]
        seed[/seed/]
    end

    subgraph design["Design"]
        frontend[/frontend-design/]
    end

    classDef impStyle fill:#fff0d0,stroke:#c08030
    classDef issueStyle fill:#e0f0ff,stroke:#3060c0
    classDef qualStyle fill:#e0f7e0,stroke:#2d8a2d
    classDef scafStyle fill:#ffe0ff,stroke:#a030a0
    classDef learnStyle fill:#ffe0e0,stroke:#c03030

    class quick,orchestrate impStyle
    class bug,feature,spec_draft,spec_review,feature_from_spec issueStyle
    class review,test_plan,pr qualStyle
    class scaffold_proj,scaffold_mod scafStyle
    class learn,metrics,seed learnStyle
```

---

## Where to look next

- Pipeline phases in detail: [The Pipeline](../workflow/orchestrate.md)
- Agent definitions: [Agent Roles](../agents/overview.md)
- Hook contracts: [Hook Lifecycle](../hooks/lifecycle.md)
- Codex integration: [Codex Plugin](../integrations/codex-plugin.md)
- Self-learning system: [Self-Learning Loop](../learning/self-learning-loop.md)
- File-by-file inventory: [File Inventory](file-inventory.md)
