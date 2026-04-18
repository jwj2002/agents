---
title: "Daily Operations — Cross-Project Workflow & Environment Architecture"
status: draft
created: 2026-04-17
updated: 2026-04-17
author: Jason Job
type: Architecture
complexity: COMPLEX
version: v1.0
---

# Daily Operations

## Overview

This document describes how an engineering manager works across multiple projects, environments, and devices — daily routines, tool interactions, data flows, and isolation boundaries.

---

## Environments

### Personal (jwj2002)

- **Machine:** macbook (primary dev machine)
- **GitHub:** jwj2002
- **Projects:** flotilla, buddy, mymoney-dev, temper, safe174th, maison-scaffold
- **Repos:** ~/agents, ~/projects/*
- **Flotilla server:** localhost:9000
- **Knowledge MCP:** localhost:9100

### Work / Client (jwj2002-work)

- **Machine:** client-provided laptop (varies per engagement)
- **GitHub:** jwj2002-work (separate account, client doesn't control)
- **Projects:** client-specific (routeiq, docketiq, vitalai-channels, etc.)
- **Repos:** ~/agents-work, ~/projects/*
- **Flotilla server:** not installed (CLI-only workflow)
- **Knowledge MCP:** localhost:9100 (local to work laptop)

### Shared IP (agent-patterns)

- **Repo:** jwj2002/agent-patterns (private or public)
- **Contains:** patterns, learning rules, skills, Claude config
- **Consumed as:** git submodule in both ~/agents and ~/agents-work
- **Push from:** either environment (only contains reusable, non-client-specific IP)

---

## Repository Architecture

```
jwj2002/agent-patterns          ← shared IP (patterns, rules, skills)
│
├── patterns/                   ← reusable engineering patterns
├── rules/                      ← learning rules
├── claude-config/              ← skills, hooks, rules
│   ├── skills/
│   ├── rules/
│   └── hooks/
└── README.md

jwj2002/agents                  ← personal environment
│
├── knowledge/
│   ├── patterns/ → submodule: jwj2002/agent-patterns/patterns
│   ├── rules/    → submodule: jwj2002/agent-patterns/rules
│   ├── projects/               ← personal project tracker YAMLs
│   │   ├── flotilla.yaml
│   │   ├── buddy.yaml
│   │   └── temper.yaml
│   ├── decisions/              ← personal architectural decisions
│   ├── schema.sql
│   ├── sync.py
│   └── knowledge.db            ← gitignored, built from YAML
├── claude-config/ → submodule or symlink: jwj2002/agent-patterns/claude-config
├── specs/                      ← cross-project specs
└── docs/

jwj2002-work/agents-work        ← client environment (per engagement)
│
├── knowledge/
│   ├── patterns/ → submodule: jwj2002/agent-patterns/patterns
│   ├── rules/    → submodule: jwj2002/agent-patterns/rules
│   ├── projects/               ← client project tracker YAMLs
│   │   ├── routeiq.yaml
│   │   └── docketiq.yaml
│   ├── decisions/              ← client-specific decisions
│   ├── schema.sql
│   ├── sync.py
│   └── knowledge.db            ← gitignored, built from YAML
├── claude-config/ → submodule or symlink
└── specs/
```

### Isolation Guarantees

| Data | Personal sees | Work sees | Shared |
|---|---|---|---|
| Patterns | All | All | Yes — submodule |
| Learning rules | All | All | Yes — submodule |
| Skills / config | All | All | Yes — submodule |
| Project tracker | Personal only | Client only | No |
| Decisions | Personal | Client | No |
| Inbox / captures | Personal | Client | No |
| Git history | Full personal | Full client | Patterns only |

### Returning Client Hardware

1. Remove submodule remote (patterns remain as files, no git link)
2. Delete `~/agents-work/.git` credentials
3. Client retains: their project YAMLs, their decisions, patterns (your IP, but shared intentionally)
4. Client cannot access: your personal projects, other client projects, your GitHub repos

---

## Daily Routines

### Morning — Session Start (Personal Laptop)

```
1. Open terminal
2. /dashboard                    ← cross-project overview
   Shows: all personal projects with focus, blockers, next steps
   Source: ~/agents/knowledge/knowledge.db via MCP

3. Open Flotilla (browser)       ← visual dashboard
   Shows: project cards, agent status, health, captures
   Source: PostgreSQL + GitHub sync + health monitor

4. Pick a project to work on
   /project flotilla             ← full context for flotilla
   Shows: focus, next steps, blockers, specs, recent decisions

5. Review inbox
   /inbox                        ← things captured mid-session yesterday
   Triage: assign to projects, mark done, dismiss
```

### Morning — Session Start (Client Laptop)

```
1. Open terminal
2. /dashboard                    ← client projects only
   Shows: routeiq, docketiq, vitalai-channels
   Source: ~/agents-work/knowledge/knowledge.db via MCP

3. No Flotilla — CLI workflow only
   /project routeiq              ← full context
   /inbox                        ← triage

4. Start working
```

### During Work — Capturing Context

While working on project A, a thought comes up about project B:

```
# Quick capture — doesn't break flow
/capture "Check if routeiq handles concurrent migrations" @routeiq #task

# Capture for current project
/capture "Need to add rate limiting before launch" #task

# Capture with no project — triage later
/capture "Shared component library idea" #idea
```

These go into the inbox table in knowledge.db. The YAML stays unchanged until you explicitly update it.

### During Work — Updating Project State

When you finish a focus area or hit a blocker:

```
# Update focus
/project flotilla --focus "Terminal layout + agent sessions"

# Add blocker
/project routeiq --blocker "Waiting on Paul's API contract"

# Complete a next step
/project flotilla --done "Add Project modal"

# Add next step
/project flotilla --next "E2E testing infrastructure"
```

These update the project_tracker table in knowledge.db AND write back to the YAML file (so git tracks the change).

### End of Day — Wrap Up

```
# Update project state before closing
/project flotilla --focus "Completed: agent sessions, terminal layout, Add Project"

# Check inbox — anything to triage?
/inbox

# Commit knowledge updates
cd ~/agents && git add -A && git commit -m "daily: flotilla agent sessions complete"
git push origin main

# Optional: push patterns to shared repo
cd ~/agents/knowledge/patterns
git add -A && git commit -m "pattern: tmux session management"
git push origin main
```

### Weekly Review

```
/weekly                          ← auto-generated digest
Shows: completed items, open blockers, priorities for next week

/blockers                        ← cross-project blocker board
Shows: everything stuck, aging, who owns resolution

/deps                            ← dependency map (if enabled)
Shows: what blocks what across projects
```

---

## Flotilla Integration (Personal Laptop)

Flotilla runs on the personal laptop and provides the **visual operations layer**. The knowledge MCP provides the **context layer**. They complement each other.

### Data Flow

```
                    ┌─────────────────────┐
                    │   Personal Laptop    │
                    │                      │
   CLI Terminal     │    Flotilla Server   │     Browser
   ┌──────────┐    │    ┌────────────┐    │    ┌──────────┐
   │ Claude   │    │    │ FastAPI    │    │    │ Dashboard │
   │ Code     │◄───┼───►│ :9000     │◄───┼───►│ React    │
   └────┬─────┘    │    └─────┬──────┘    │    └──────────┘
        │          │          │           │
        │          │    ┌─────┴──────┐    │
        │          │    │ PostgreSQL │    │
        │          │    │ :5435      │    │
        │          │    └────────────┘    │
        │          │                      │
        ▼          │                      │
   ┌──────────┐    │                      │
   │Knowledge │    │                      │
   │ MCP      │◄───┼──────────────────────┘
   │ :9100    │    │   Flotilla proxies to MCP
   └────┬─────┘    │   for Knowledge section
        │          │
   ┌────┴─────┐    │
   │ SQLite   │    │
   │knowledge │    │
   │ .db      │    │
   └──────────┘    │
                    └─────────────────────┘
```

### What Lives Where

| Feature | Flotilla (PostgreSQL) | Knowledge MCP (SQLite) |
|---|---|---|
| Project list + metadata | Yes — projects table | Yes — project_tracker table |
| Agent management | Yes — work queue, sessions | No |
| GitHub issues | Yes — github_sync | No |
| Health monitoring | Yes — endpoints table | No |
| Captures (text + images) | Yes — captures table | No (inbox is text-only) |
| Focus / next steps / blockers | No | Yes — project_tracker |
| Patterns | No | Yes |
| Decisions | No | Yes |
| Learning rules | No | Yes |
| Daily summary | Yes — auto-generated | No |
| Journal | No | Yes — chronological log |

### Flotilla Dashboard — Enhanced with Knowledge Data

The ProjectView in Flotilla can query the knowledge MCP to show:

```
┌─ flotilla ──────────────────────────────────────────────────────┐
│                                                                  │
│  Agent ● Running                              [Attach] [Stop]   │
│  ✅ #153 chore: remove unused ideas.py        PR #179           │
│                                                                  │
│  ┌─ Context (from Knowledge MCP) ───────────────────────────┐   │
│  │ Focus: Terminal layout + agent sessions                    │   │
│  │ Next:  1. E2E testing  2. Add Project modal  3. Cleanup   │   │
│  │ ! Blocker: maison-scaffold Jinja error (resolved)         │   │
│  └───────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ▸ Planned Work                                                  │
│  ▸ Issues (15 open)                                             │
│  ▸ Git Status                                                    │
│  ▸ Daily Summary                                                │
│  ▸ Knowledge                                                     │
└──────────────────────────────────────────────────────────────────┘
```

The "Context" section is a new collapsible in ProjectView that calls:
- `get_project_context(project="flotilla")` via the knowledge MCP proxy
- Renders focus, next steps, blockers, open questions

This section is **read/write** — you can update focus and mark steps done directly from the web UI, which writes back through the MCP.

### Sync Between Systems

Flotilla and Knowledge MCP are **not replicated** — they serve different purposes:

| Event | Flotilla does | Knowledge MCP does |
|---|---|---|
| New project created | Inserts into PostgreSQL | User manually creates YAML + syncs |
| PR merged | GitHub sync records it | Journal entry auto-created (optional) |
| Agent completes work | Updates work queue | No action |
| User updates focus | No action (not Flotilla's data) | Updates project_tracker |
| User captures idea | Inserts into captures table (with images) | Inserts into inbox (text-only) |
| Daily summary generated | Auto from GitHub data | /weekly generates from journal |

**No bidirectional sync.** Each system owns its data. Flotilla handles operations. Knowledge handles context.

---

## New Pattern Workflow (Cross-Environment)

### Pattern Discovered on Client Laptop

```
# 1. Capture the pattern idea
/capture "Pattern: API rate limiting with sliding window" #idea

# 2. Later, formalize it
# Edit ~/agents-work/knowledge/patterns/rate-limiting.yaml

# 3. Push to shared patterns repo
cd ~/agents-work/knowledge/patterns
git add rate-limiting.yaml
git commit -m "pattern: API rate limiting with sliding window"
git push origin main        # pushes to jwj2002/agent-patterns

# 4. On personal laptop — pull the pattern
cd ~/agents/knowledge/patterns
git pull origin main        # gets the new pattern
python3 sync.py build       # updates knowledge.db
```

### Pattern Discovered on Personal Laptop

Same flow, just push from ~/agents side. Both environments share the same patterns submodule remote.

### Reviewing Patterns Before Sharing

If a pattern contains client-specific details:

```
# Before pushing, review:
/pattern-review rate-limiting.yaml
# Checks for: client names, internal URLs, proprietary terms
# Flags anything that should be generalized before sharing
```

---

## Capture Workflow Comparison

### CLI Capture (~/agents — anywhere)

```
/capture "Check concurrent migration handling" @routeiq #task
```
- Text only
- Goes to inbox table in knowledge.db
- Available via /inbox on any machine with this agents repo
- No images, no state machine, no promotion

### Flotilla Capture (browser — personal laptop only)

```
[CaptureInput component — text + drag-drop images]
Type: bug | idea | decision | feature | reference | incident
State: open → in_review → promoted/deferred/closed
Promote to: GitHub issue, spec, knowledge decision
```
- Rich: text + images + type templates
- Goes to captures table in PostgreSQL
- Only on personal laptop (Flotilla server)
- Full lifecycle with state machine

### When to Use Which

| Situation | Use |
|---|---|
| Quick thought mid-coding | `/capture` (CLI) |
| Bug with screenshot | Flotilla capture (drag-drop image) |
| Task for another project | `/capture @project` (CLI) |
| Feature idea with details | Flotilla capture (type: feature, template fields) |
| On client laptop | `/capture` (CLI only option) |
| Triage session | `/inbox` (CLI) or Flotilla captures section (web) |

---

## Device & Machine Topology

```
┌─────────────────────────────────────────────────────────┐
│                   Personal Laptop (macbook)               │
│                                                           │
│  ~/agents/           ← personal context                  │
│  ~/projects/         ← personal code                     │
│  Flotilla :9000      ← web dashboard                     │
│  Knowledge MCP :9100 ← context queries                   │
│  tmux sessions       ← agent sessions                    │
│                                                           │
│  Devices managed by Flotilla:                            │
│  ├── macbook (is_local=true)                             │
│  ├── jns-server (SSH)                                    │
│  └── future devices                                       │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                   Client Laptop (varies)                   │
│                                                           │
│  ~/agents-work/      ← client context                    │
│  ~/projects/         ← client code                       │
│  Knowledge MCP :9100 ← context queries (client only)     │
│  No Flotilla         ← CLI workflow only                 │
│  No tmux agents      ← manual Claude sessions            │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│                   jns-server (home server)                 │
│                                                           │
│  ~/projects/         ← deployed apps                     │
│  SSH from macbook    ← Flotilla terminal sessions        │
│  No agents repo      ← managed by Flotilla remotely     │
└─────────────────────────────────────────────────────────┘
```

---

## Implementation Priority

### Phase 1: Core Project Tracker (build now)

1. Schema additions to knowledge.db (project_tracker, inbox, journal)
2. YAML source files for personal projects
3. sync.py update
4. MCP tools: get_dashboard, get_project_context, update_project_context, capture, triage_inbox
5. Skills: /dashboard, /project, /inbox, /capture

### Phase 2: Flotilla Integration (after Phase 1)

1. ProjectView "Context" section — reads from knowledge MCP
2. Context update from web UI — writes through MCP
3. Inbox section in Flotilla — shows knowledge inbox items

### Phase 3: Multi-Environment (when client engagement starts)

1. Create jwj2002/agent-patterns repo
2. Extract patterns + rules + config into submodule
3. Create agents-work repo template
4. Test isolation guarantees
5. Pattern export/import skill

### Phase 4: Weekly Automation (optional)

1. /weekly digest generation
2. /blockers cross-project view
3. /deps dependency map
4. Auto-journal from git activity

---

## Open Questions

1. Should patterns be public (open source your engineering practices) or private?
2. Should the /weekly digest auto-post to Slack or just render in terminal?
3. When Flotilla moves to jns-server, does the knowledge MCP move too or stay on the laptop?
4. Should inbox items sync between CLI and Flotilla, or stay separate?
