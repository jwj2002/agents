---
title: "Project Dashboard — Cross-Project Context Tracker"
status: draft
created: 2026-04-17
updated: 2026-04-17
author: Jason Job
type: Tooling
complexity: MODERATE
version: v1.0
location: ~/agents (portable, configurable, opt-in per project)
---

# Project Dashboard — Cross-Project Context Tracker

## Problem Statement

When working across multiple projects (vitalai-channels, routeiq, docketiq, etc.), context is lost between sessions. There is no way to:

- See the current state of all projects at a glance
- Track what was done, what's next, and what's blocked per project
- Quickly capture tasks or questions that arise mid-session for OTHER projects
- Get full cross-project context without reconstructing it manually

Past actions, current actions, and next steps have no persistent home. Tasks and questions that arise during a session have nowhere to go unless you stop and context-switch.

## Requirements

1. **Track context across multiple projects** — past actions, current focus, next steps, blockers, open questions
2. **Quick capture** — add tasks/questions mid-session without losing flow, no project assignment required
3. **Lives in ~/agents** — portable, git-tracked, versioned
4. **Configurable** — opt-in per project, not forced
5. **Fast full-context retrieval** — get cross-project status in seconds, not minutes
6. **Integrated with Claude Code** — works through the existing MCP + skills workflow

## Design Decision: Extend knowledge.db

### Why not Obsidian

Obsidian was considered. It's good for browsing and thinking, but requires switching apps. The primary interface is Claude Code in the terminal. Any system that requires a context switch adds friction and won't be used consistently.

### Why not a new system

The knowledge system (SQLite + YAML source files + MCP server + Claude Code) already works. Adding tables to the same DB means: same sync pipeline, same MCP server, same query patterns. Zero new infrastructure.

### Architecture

```
YAML files (source of truth, ~/agents/knowledge/projects/)
     |
     |  python3 sync.py build
     v
SQLite database (knowledge.db — new tables added)
     |
     |  knowledge-mcp (existing MCP server — new tools added)
     v
Claude Code skills (/dashboard, /project, /inbox, /capture)
     |
     v
User sees cross-project context in terminal
```

---

## Data Model

### New Tables in knowledge.db

#### project_tracker

One row per tracked project. The operational "where am I" state.

```sql
CREATE TABLE IF NOT EXISTS project_tracker (
    project TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'blocked', 'done')),
    focus TEXT,
    next_steps TEXT,          -- JSON array, ordered
    blockers TEXT,            -- JSON array
    open_questions TEXT,      -- JSON array
    specs TEXT,               -- JSON array of {path, version, status, summary}
    dependencies TEXT,        -- JSON array of {project, what, status}
    updated_at TEXT,
    updated_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_project_tracker_status ON project_tracker(status);
```

#### inbox

Quick capture. No project assignment required. Triage later.

```sql
CREATE TABLE IF NOT EXISTS inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    project TEXT,             -- nullable (assign later)
    type TEXT NOT NULL DEFAULT 'task'
        CHECK (type IN ('task', 'question', 'idea', 'concern')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'done', 'dismissed')),
    created_at TEXT,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_inbox_status ON inbox(status);
CREATE INDEX IF NOT EXISTS idx_inbox_project ON inbox(project);
```

#### journal (optional — for `/journal` view)

Chronological log of actions per project. Auto-populated from session updates + manual entries.

```sql
CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    entry TEXT NOT NULL,
    entry_type TEXT NOT NULL DEFAULT 'update'
        CHECK (entry_type IN ('update', 'decision', 'milestone', 'blocker_resolved', 'focus_change')),
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_journal_project ON journal(project);
CREATE INDEX IF NOT EXISTS idx_journal_date ON journal(created_at);
```

### YAML Source Files

```
~/agents/knowledge/projects/
├── vitalai-channels.yaml
├── routeiq.yaml
├── docketiq.yaml
└── ...
```

Example `vitalai-channels.yaml`:

```yaml
project: vitalai-channels
status: active
focus: "Phase 5 onboarding specs"
next_steps:
  - "Finalize 3 onboarding specs (auth, devices, projects)"
  - "Implement email-only login (phase5-auth v4.0)"
  - "Device self-service registration"
  - "Project discovery + scan"
  - "Project agent start/stop"
blockers:
  - "AD connection details — need from infra team before real auth"
open_questions:
  - "Should scan depth be configurable per search path?"
specs:
  - path: "specs/phase5-auth.md"
    version: "v4.0"
    status: "draft"
    summary: "Auth, JWT, user model"
  - path: "specs/onboarding-devices.md"
    version: "v1.0"
    status: "draft"
    summary: "Device registration"
  - path: "specs/projects-page.md"
    version: "v1.0"
    status: "draft"
    summary: "Project discovery, agents"
dependencies:
  - project: "external"
    what: "AD connection details from infra"
    status: "blocked"
updated_at: "2026-04-16"
updated_by: "jason"
```

---

## MCP Tools (add to knowledge-mcp)

### get_dashboard

Returns all active/paused/blocked projects with status, focus, next step, blockers. Plus open inbox count.

**Parameters:** none (or optional `status` filter)

**Returns:** Structured project summaries + inbox summary

### get_project_context

Returns full detail for one project: all fields from project_tracker, recent journal entries, related decisions from existing decisions table.

**Parameters:** `project` (string)

**Returns:** Full project context

### update_project_context

Update focus, add/remove next steps, blockers, questions for a project.

**Parameters:** `project` (string), fields to update (focus, next_steps, blockers, open_questions, status)

**Returns:** Updated project record

### capture

Quick-add to inbox. No project required.

**Parameters:** `content` (string), optional `project`, optional `type` (task/question/idea/concern)

**Returns:** Created inbox item with ID

### triage_inbox

Assign project, mark done, or dismiss inbox items.

**Parameters:** `id` (number), `action` (assign/done/dismiss), optional `project`

**Returns:** Updated inbox item

### get_journal

Get chronological entries for a project.

**Parameters:** `project` (string), optional `limit` (default 20)

**Returns:** Journal entries, newest first

---

## Claude Code Skills

### `/dashboard` (CORE)

Calls `get_dashboard` MCP tool. Formats cross-project overview.

### `/project {name}` (CORE)

Calls `get_project_context` MCP tool. Shows full context for one project.

### `/inbox` (CORE)

Calls inbox query. Shows open items, recently done. Supports triage actions.

### `/capture {text}` (CORE)

Shorthand for quick inbox capture. Parses optional `@project` and `#type` tags.

Examples:
```
/capture Check if routeiq handles concurrent migrations @routeiq #task
/capture Ask Paul about staging deploy schedule #question
/capture Shared component library for dashboards #idea
```

### `/journal {name}` (OPTIONAL)

Calls `get_journal` MCP tool. Shows chronological log.

### `/blockers` (OPTIONAL)

Queries all projects for blockers. Cross-project blocker board.

### `/weekly` (OPTIONAL)

Auto-generates digest from journal entries + inbox resolved items for the past 7 days.

### `/deps` (OPTIONAL)

Renders cross-project dependency map from project_tracker.dependencies fields.

---

## Views — Wire Diagrams

### View Map

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         VIEW MAP — PROJECT TRACKER                          │
│                                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐               │
│  │  /dashboard   │────>│ /project {n} │────>│  /journal {n}│               │
│  │  (CORE)      │     │  (CORE)      │     │  (OPTIONAL)  │               │
│  └──────┬───────┘     └──────────────┘     └──────────────┘               │
│         │                                                                   │
│         ├─────────────┐                                                     │
│         v             v                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  /inbox       │  │  /blockers   │  │  /weekly      │  │  /deps       │  │
│  │  (CORE)      │  │  (OPTIONAL)  │  │  (OPTIONAL)  │  │  (OPTIONAL)  │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1. /dashboard — Cross-Project Overview (CORE)

The home view. Everything at a glance.

```
┌─ Dashboard ─────────────────────────────────────────────────────────────────┐
│                                                                             │
│  ACTIVE ─────────────────────────────────────────────────────────────────   │
│                                                                             │
│  ┌─ vitalai-channels ────────────────────────────────────────────────────┐  │
│  │ Focus: Phase 5 onboarding specs                      Updated: 1h ago │  │
│  │ Next:  Finalize 3 specs > Implement email login > Device self-svc    │  │
│  │ ! Blocked: AD connection details from infra                          │  │
│  │ ? Open: Should scan depth be configurable?                           │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌─ routeiq ────────────────────────────────────────────────────────────┐  │
│  │ Focus: Migration to new schema                       Updated: 2d ago │  │
│  │ Next:  Write migration script > Test rollback > Update seed data     │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  PAUSED ─────────────────────────────────────────────────────────────────   │
│                                                                             │
│  ┌─ docketiq ──────────────────────────────────────────────────────────┐   │
│  │ Focus: Waiting on Paul's API contract                Updated: 5d ago │  │
│  │ Next:  Integrate payment endpoint > Frontend form                    │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  INBOX (3 open) ─────────────────────────────────────────────────────────   │
│                                                                             │
│  * [task]     Check if routeiq handles concurrent migrations                │
│  * [question] Ask Paul about staging deploy schedule                        │
│  * [idea]     Shared component library for dashboards                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2. /project {name} — Single Project Detail (CORE)

Full context for a work session on one project.

```
┌─ vitalai-channels ──────────────────────────────────────────────────────────┐
│                                                                             │
│  Status: ACTIVE           Owner: jason            Updated: 2026-04-16      │
│  Focus:  Phase 5 onboarding specs                                          │
│  Repo:   vitalailabs/vitalai-channels (GitLab)                             │
│                                                                             │
│  NEXT STEPS (ordered) ───────────────────────────────────────────────────   │
│                                                                             │
│  1. [ ] Finalize 3 onboarding specs (auth, devices, projects)              │
│  2. [ ] Implement email-only login (phase5-auth v4.0)                      │
│  3. [ ] Device self-service registration                                    │
│  4. [ ] Project discovery + scan                                            │
│  5. [ ] Project agent start/stop                                            │
│                                                                             │
│  BLOCKERS ───────────────────────────────────────────────────────────────   │
│                                                                             │
│  ! AD connection details — need from infra team                            │
│                                                                             │
│  OPEN QUESTIONS ─────────────────────────────────────────────────────────   │
│                                                                             │
│  ? Should scan depth be configurable per search path?                      │
│  ? Do we need a first-run setup wizard or just docs?                       │
│                                                                             │
│  SPECS ──────────────────────────────────────────────────────────────────   │
│                                                                             │
│  specs/phase5-auth.md          v4.0  draft   Auth, JWT, user model         │
│  specs/onboarding-devices.md   v1.0  draft   Device registration           │
│  specs/projects-page.md        v1.0  draft   Project discovery, agents     │
│                                                                             │
│  RECENT DECISIONS ───────────────────────────────────────────────────────   │
│                                                                             │
│  D-012  Email-only login as AD stopgap               2026-04-16           │
│  D-011  Soft-delete for project removal              2026-04-16           │
│  D-010  Agent naming: {username}-{project_name}      2026-04-16           │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3. /inbox — Quick Capture & Triage (CORE)

Everything captured mid-session. Triage when ready.

```
┌─ Inbox ─────────────────────────────────────────────────────────────────────┐
│                                                                             │
│  OPEN (5) ───────────────────────────────────────────────────────────────   │
│                                                                             │
│  #12 [task]     Check if routeiq handles concurrent migrations              │
│                 Project: routeiq (auto)        Captured: 2026-04-16        │
│                                                                             │
│  #11 [question] Ask Paul about staging deploy schedule                      │
│                 Project: —                     Captured: 2026-04-16        │
│                                                                             │
│  #10 [idea]     Shared component library for dashboards                     │
│                 Project: —                     Captured: 2026-04-15        │
│                                                                             │
│  #9  [task]     Update CLAUDE.md after phase 5 merge                        │
│                 Project: vitalai-channels      Captured: 2026-04-15        │
│                                                                             │
│  #8  [concern]  Health check interval may be too aggressive at scale        │
│                 Project: vitalai-channels      Captured: 2026-04-14        │
│                                                                             │
│  RECENTLY DONE (3) ──────────────────────────────────────────────────────   │
│                                                                             │
│  #7  [task]     Split onboarding into 3 specs          done 2026-04-16    │
│  #6  [question] One project agent or many per repo?    done 2026-04-16    │
│  #5  [task]     Run Q&A for projects page              done 2026-04-16    │
│                                                                             │
│  Actions: [assign {id} {project}]  [done {id}]  [dismiss {id}]            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4. /journal {name} — Project Timeline (OPTIONAL)

Chronological log. Auto-populated from updates + manual entries.

```
┌─ Journal: vitalai-channels ─────────────────────────────────────────────────┐
│                                                                             │
│  2026-04-16 ─────────────────────────────────────────────────────────────   │
│                                                                             │
│  16:30  Focus changed > "Phase 5 onboarding specs"                         │
│  16:15  Spec created: specs/projects-page.md v1.0                          │
│  15:45  Spec created: specs/onboarding-devices.md v1.0                     │
│  15:30  Spec updated: specs/phase5-auth.md v3.0 > v4.0                    │
│         - Removed password_hash, jbox_name, jbox_ip from users             │
│         - Added ad_sid, is_active                                           │
│         - Login changed to email-only                                       │
│  14:00  Completed Q&A for projects page (10 questions resolved)            │
│  13:30  Decision: email-only login as AD stopgap                           │
│  13:00  Started onboarding process discussion                               │
│                                                                             │
│  2026-04-14 ─────────────────────────────────────────────────────────────   │
│                                                                             │
│  17:00  PRD.md finalized — vision document complete                        │
│  15:00  Merged: Phase 4 threading (#55)                                    │
│  11:00  Merged: @mention autocomplete (#57)                                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 5. /blockers — Cross-Project Blocker Board (OPTIONAL)

Everything stuck, across all projects.

```
┌─ Blockers ──────────────────────────────────────────────────────────────────┐
│                                                                             │
│  BLOCKING WORK NOW ──────────────────────────────────────────────────────   │
│                                                                             │
│  vitalai-channels                                                           │
│  ! AD connection details — need from infra team                            │
│    Impact: Can't implement real auth. Stopgap (email) unblocks for now.    │
│    Owner: Jason     Age: 1d     Action: Follow up with infra               │
│                                                                             │
│  docketiq                                                                   │
│  ! Waiting on Paul's API contract for payment endpoint                     │
│    Impact: Frontend integration blocked. Can do backend stubs.             │
│    Owner: Paul      Age: 5d     Action: Ping Paul                          │
│                                                                             │
│  RESOLVED RECENTLY ──────────────────────────────────────────────────────   │
│                                                                             │
│  vitalai-channels                                                           │
│  ok Onboarding process unclear — resolved via Q&A session (2026-04-16)    │
│                                                                             │
│  routeiq                                                                    │
│  ok Schema conflict with legacy table — resolved, migration written        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6. /weekly — Weekly Digest (OPTIONAL)

Auto-generated summary from journal + inbox.

```
┌─ Weekly Digest: 2026-04-10 > 2026-04-16 ───────────────────────────────────┐
│                                                                             │
│  COMPLETED ──────────────────────────────────────────────────────────────   │
│                                                                             │
│  vitalai-channels (12 items)                                                │
│  * PRD finalized — vision document complete                                │
│  * Phase 5 auth spec updated to v4.0 (email-only login, AD-ready)         │
│  * 3 onboarding specs written (auth, devices, projects)                    │
│  * 10 design questions resolved via Q&A                                     │
│                                                                             │
│  routeiq (3 items)                                                          │
│  * Schema migration drafted                                                 │
│  * Legacy table conflict resolved                                           │
│                                                                             │
│  STILL OPEN ─────────────────────────────────────────────────────────────   │
│                                                                             │
│  * AD connection details (vitalai-channels) — 1d                           │
│  * Paul's API contract (docketiq) — 5d, aging                              │
│                                                                             │
│  NEXT WEEK PRIORITIES ───────────────────────────────────────────────────   │
│                                                                             │
│  1. Implement email-only login (vitalai-channels)                          │
│  2. Device self-service registration (vitalai-channels)                    │
│  3. Finish migration script (routeiq)                                       │
│                                                                             │
│  METRICS ────────────────────────────────────────────────────────────────   │
│                                                                             │
│  Sessions: 8    Tasks completed: 15    Decisions made: 6                   │
│  Time in specs: ~60%    Time in code: ~30%    Time in review: ~10%         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7. /deps — Cross-Project Dependencies (OPTIONAL)

Dependency map across projects.

```
┌─ Dependencies ──────────────────────────────────────────────────────────────┐
│                                                                             │
│  vitalai-channels                                                           │
│  |-- Phase 5: Auth (in progress)                                           │
│  |   +-- blocks > Device Registration                                      │
│  |                +-- blocks > Project Discovery                           │
│  |                             +-- blocks > Project Agents                 │
│  |-- AD Integration (blocked — external)                                   │
│  |   +-- blocks > Real auth (email stopgap unblocks dev)                  │
│  +-- Onboard john-agent, ryan-agent                                        │
│      +-- depends on > Auth + Devices + Projects (all three)               │
│                                                                             │
│  docketiq                                                                   │
│  |-- Payment endpoint (blocked — waiting on Paul)                          │
│  |   +-- blocks > Frontend payment form                                    │
│  +-- No deps on other projects                                             │
│                                                                             │
│  routeiq                                                                    │
│  |-- Schema migration (in progress)                                        │
│  |   +-- blocks > Seed data update                                         │
│  +-- No deps on other projects                                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### What to Build

| Piece | Effort | Where |
|-------|--------|-------|
| Schema additions (3 tables) | 30 min | `~/agents/knowledge/schema.sql` |
| YAML source files for projects | 30 min | `~/agents/knowledge/projects/` |
| sync.py update (new tables) | 1 hr | `~/agents/knowledge/sync.py` |
| 5 MCP tools (dashboard, project, update, capture, triage) | 2 hr | `~/agents/knowledge-mcp/index.ts` |
| `/dashboard` skill | 30 min | `~/agents/claude-config/skills/` |
| `/project` skill | 30 min | `~/agents/claude-config/skills/` |
| `/inbox` skill | 30 min | `~/agents/claude-config/skills/` |
| `/capture` skill | 15 min | `~/agents/claude-config/skills/` |
| Optional: `/journal` skill + MCP tool | 30 min | Same locations |
| Optional: `/blockers` skill | 30 min | Same locations |
| Optional: `/weekly` skill | 45 min | Same locations |
| Optional: `/deps` skill | 30 min | Same locations |

**Core system: ~5 hours.** Optional views: ~2 hours additional.

### Build Order

1. Schema + YAML source files + sync.py (data layer)
2. MCP tools (query layer)
3. Core skills: `/dashboard`, `/project`, `/inbox`, `/capture`
4. Optional skills as needed

---

## View Summary

| View | Type | Purpose | Trigger |
|------|------|---------|---------|
| `/dashboard` | CORE | Cross-project status at a glance | Session start, anytime |
| `/project {n}` | CORE | Full context for one project | Starting work on a project |
| `/inbox` | CORE | Quick capture + triage | Mid-session capture, weekly triage |
| `/capture {text}` | CORE | Zero-friction inbox add | Mid-session, something comes up |
| `/journal {n}` | Optional | What happened, when | "What did I do last week on X?" |
| `/blockers` | Optional | Everything stuck, across projects | Weekly review, standup prep |
| `/weekly` | Optional | Auto-generated digest | End of week, standup |
| `/deps` | Optional | Cross-project dependency map | Planning, sequencing work |

---

## Decisions Log

| # | Decision | Resolution | Date |
|---|----------|-----------|------|
| D1 | System location | ~/agents repo (portable, git-tracked) | 2026-04-17 |
| D2 | Storage backend | Extend existing knowledge.db (SQLite) | 2026-04-17 |
| D3 | Not Obsidian | CLI-first — Obsidian requires app switching | 2026-04-17 |
| D4 | Not a new system | Reuse knowledge MCP pipeline (zero new infra) | 2026-04-17 |
| D5 | Source of truth | YAML files synced to SQLite (same as patterns/decisions) | 2026-04-17 |
| D6 | Core views | dashboard, project, inbox, capture (4 skills) | 2026-04-17 |
| D7 | Optional views | journal, blockers, weekly, deps (add as needed) | 2026-04-17 |

---

## Discussion Context

This spec emerged from an onboarding workflow discussion for VitalAI Channels. While building specs for auth, devices, and projects, the lack of a cross-project context system became apparent. Key pain points identified:

1. Context lost between sessions — no "where was I?" on session start
2. Tasks/questions for other projects have nowhere to go mid-session
3. No single view across all active work
4. Reconstructing project state requires reading git logs, specs, and memory files

The system is designed to be project-agnostic — it tracks any project in ~/agents, not just VitalAI Channels.
