---
title: "Cross-Environment Development Platform"
status: FINAL
created: 2026-04-17
updated: 2026-04-18
author: Jason Job
type: Architecture
complexity: COMPLEX
version: v2.0
reviewed: Codex adversarial review — 26 findings resolved
---

# Cross-Environment Development Platform

## Summary

Two-layer development platform for an engineering manager working across personal projects and client engagements. The Operations layer (Flotilla) handles agents, monitoring, and rich UI on the personal laptop only. The Context layer (Knowledge MCP) handles project tracking, captures, and patterns — portable across all environments including air-gapped and GitHub-blocked client networks.

## Goals

- `/dashboard` shows cross-project status at a glance (deep-dive and triage are follow-up actions)
- Capture ideas without interrupting current work (non-interrupting, like `/btw`)
- Reuse engineering patterns across all engagements via shared submodule
- Strict environment isolation — zero client data on personal systems, zero personal data on client hardware
- Works fully offline — `/dashboard`, `/project`, `/capture`, `/inbox` return results from local SQLite with no network dependency

## Scope

### In Scope

- Two-layer architecture (Operations + Context)
- Three-repo isolation model with submodule
- Data ownership rules (PostgreSQL vs SQLite, no bidirectional sync)
- Capture system (one destination per environment, no fallback switching)
- Quarantine branch model for pattern sharing from client environments
- Multi-device topology (macbook + jns-server)
- Client environment security and hardware return procedures
- Flotilla ↔ Knowledge MCP integration (read-only via proxy)
- Pattern staging, transfer, and AI-assisted import review
- Daily workflow with staleness indicators

### Out of Scope

- Flotilla on client laptops
- Pattern marketplace / monetization
- Multi-user / team features
- Cloud hosting of Flotilla
- Mobile interface

---

## Architecture

### System Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    OPERATIONS LAYER                          │
│                    (Personal Laptop Only)                    │
│                                                             │
│  Flotilla Server (127.0.0.1:9000)  Browser Dashboard       │
│  ├── Agent management              ├── ProjectView          │
│  ├── Work queue                    ├── AppLibrary           │
│  ├── GitHub sync                   ├── Terminal drawer      │
│  ├── Health monitoring             ├── CaptureInput         │
│  ├── Daily summary                 └── AgentWorkSection     │
│  └── Terminal WebSocket                                     │
│                                                             │
│  PostgreSQL (:5435)                                         │
│  ├── projects, agents, captures                             │
│  ├── agent_work_queue (FOR UPDATE SKIP LOCKED)              │
│  ├── project_github, project_issues                         │
│  ├── project_endpoints (health)                             │
│  └── messages, escalations                                  │
│                                                             │
│  Why PostgreSQL: concurrent writers (sync loops, agent      │
│  callbacks, API requests), multi-device access, atomic      │
│  lease for work queue. SQLite cannot support this.          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    CONTEXT LAYER                             │
│                    (Everywhere — Portable)                   │
│                                                             │
│  Knowledge MCP Server                                       │
│  ├── Personal: HTTP mode (127.0.0.1:9100) for Flotilla     │
│  ├── Client: stdio mode (no port, no listener)              │
│  ├── get_dashboard, get_project_context                     │
│  ├── update_project_context                                 │
│  ├── capture (inbox)                CLI Skills              │
│  ├── triage_inbox                   ├── /dashboard          │
│  ├── get_patterns                   ├── /project {name}     │
│  ├── get_decisions                  ├── /capture {text}     │
│  └── get_journal                    ├── /inbox              │
│                                     ├── /blockers           │
│  SQLite (knowledge.db)              └── /weekly             │
│  ├── PRAGMA journal_mode=WAL                                │
│  ├── PRAGMA busy_timeout=5000                               │
│  ├── project_tracker (focus, next_steps, blockers)          │
│  ├── inbox (quick captures)                                 │
│  ├── journal (chronological log)                            │
│  ├── patterns, decisions, rules                             │
│  └── velocity_snapshots                                     │
│                                                             │
│  Why SQLite: single file, portable, git-trackable,          │
│  zero infrastructure, works offline/air-gapped.             │
│  WAL mode + busy_timeout handles occasional concurrent      │
│  access (MCP server + sync.py).                             │
└─────────────────────────────────────────────────────────────┘
```

### Integration Point

Flotilla reads from Knowledge MCP for context data. Never writes.

```
Browser → Flotilla API → MCP Proxy → Knowledge MCP (127.0.0.1:9100) → SQLite
```

Context updates (focus, blockers, next steps) go through MCP tools — CLI or Flotilla UI → MCP → SQLite. Flotilla's proxy passes the write through to the MCP server.

### Service Binding

All services bind to `127.0.0.1` (localhost only). No external network exposure.

| Service | Bind | Port |
|---|---|---|
| Flotilla | 127.0.0.1 | 9000 |
| Knowledge MCP (personal) | 127.0.0.1 | 9100 |
| Knowledge MCP (client) | stdio | none |
| PostgreSQL | 127.0.0.1 | 5435 |

If Flotilla is later moved to a network-accessible host (jns-server), authentication must be added (shared secret header `X-Flotilla-Token` on all write endpoints). This is not Phase 1.

---

## Repository Isolation

### Three Repos

```
jwj2002/agent-patterns              ← shared engineering IP
├── patterns/                       ← reusable patterns
├── rules/                          ← learning rules
└── claude-config/                  ← skills, hooks, rules
    ├── skills/
    │   ├── capture.md
    │   ├── dashboard.md
    │   ├── inbox.md
    │   └── project.md
    ├── rules/
    └── hooks/

jwj2002/agents                      ← personal environment
├── knowledge/
│   ├── patterns/ → submodule: agent-patterns/patterns
│   ├── rules/    → submodule: agent-patterns/rules
│   ├── projects/                   ← personal project YAMLs
│   │   ├── flotilla.yaml
│   │   ├── buddy.yaml
│   │   └── temper.yaml
│   ├── decisions/                  ← personal decisions
│   ├── schema.sql
│   ├── sync.py
│   └── knowledge.db                ← gitignored
├── claude-config/ → submodule: agent-patterns/claude-config
├── scripts/
│   └── create-work-seed.sh         ← Phase 3: bootstrap script
└── specs/

jwj2002-work/agents-work             ← client environment
├── knowledge/
│   ├── patterns/ → submodule: agent-patterns/patterns
│   ├── rules/    → submodule: agent-patterns/rules
│   ├── projects/                   ← client project YAMLs
│   ├── decisions/                  ← client decisions
│   └── knowledge.db                ← gitignored
├── claude-config/ → submodule: agent-patterns/claude-config
├── staged-patterns/                ← patterns awaiting transfer (tracked in git)
├── config.yaml                     ← environment config
└── specs/
```

### Isolation Matrix

| Data | agent-patterns | agents (personal) | agents-work (client) |
|---|---|---|---|
| Patterns | Source of truth | Submodule (read + push to main) | Submodule (read + push to review/ only) |
| Learning rules | Source of truth | Submodule (read + push to main) | Submodule (read + push to review/ only) |
| Skills / config | Source of truth | Submodule (read) | Submodule (read) |
| Project tracker | — | Personal only | Client only |
| Decisions | — | Personal only | Client only |
| Inbox / captures | — | Personal only | Client only |

### Submodule Access Model

| Environment | Push access | Target |
|---|---|---|
| Personal laptop | Direct push to `main` | You own the repo |
| Client laptop (GitHub available) | Push to `review/*` branch only | PR reviewed on personal before merge |
| Client laptop (GitHub blocked) | No push — stage locally | Transfer physically, import on personal |

**Branch protection:** `agent-patterns` main branch requires PR. No direct push except from personal laptop (repo owner).

### Submodule Pointer Management

After pushing new patterns, update the parent repo's bookmark:

```bash
cd ~/agents
git submodule update --remote knowledge/patterns
git add knowledge/patterns
git commit -m "chore: update patterns submodule"
git push
```

A `/patterns-sync` skill automates these 4 commands. Without this step, fresh clones get the old bookmark — this is intentional (you control when each environment updates).

---

## Data Ownership

### Rule: Each Store Owns Its Domain. No Exceptions.

| Data | Owner | Storage | Why |
|---|---|---|---|
| Project metadata (name, repo, device, category) | Flotilla | PostgreSQL | Multi-device, concurrent sync |
| Agent sessions, work queue | Flotilla | PostgreSQL | Concurrent writers, atomic lease |
| Captures (text + images, state machine) | Flotilla | PostgreSQL | Image storage, promotion workflow |
| GitHub issues, PRs, commits | Flotilla | PostgreSQL | Auto-sync from GitHub API |
| Health/availability | Flotilla | PostgreSQL | Background monitor loop |
| Project context (focus, next steps, blockers) | Knowledge | SQLite | Portable, offline, CLI-native |
| Quick captures (text-only inbox) | Knowledge | SQLite | Works without Flotilla |
| Patterns, decisions, rules | Knowledge | SQLite (built from YAML source files) | Git-tracked, shared via submodule |
| Journal (chronological log) | Knowledge | SQLite | CLI-native, auto-populated |

### Source of Truth for Knowledge Data

| Data type | Source of truth | SQLite is |
|---|---|---|
| Patterns | YAML files in agent-patterns repo | Built from YAML via `sync.py build` |
| Decisions | YAML files in knowledge/decisions/ | Built from YAML via `sync.py build` |
| Learning rules | YAML files in knowledge/rules/ | Built from YAML via `sync.py build` |
| Project tracker | SQLite (updated by MCP tools) | Primary store, written back to YAML periodically |
| Inbox | SQLite (updated by MCP tools) | Primary store, not in YAML |
| Journal | SQLite (updated by MCP tools) | Primary store, not in YAML |

### No Bidirectional Sync

```
Flotilla reads Knowledge:  ProjectView "Context" section (via MCP proxy)
Knowledge reads Flotilla:  Never
```

Each system reads the other via API/MCP but never writes to the other's store. No reconciliation, no merge conflicts, no ownership ambiguity.

---

## Capture System

### Design Principle

`/capture` is non-interrupting. Fire and forget. One-line acknowledgment, agent continues working.

```
> /capture add dark/light theme toggle to flotilla #idea @flotilla

  ✓ Captured #47: "add dark/light theme toggle..." (idea → flotilla)

> (Claude continues current task uninterrupted)
```

### One Destination Per Environment — No Fallback

| Environment | `/capture` writes to | Always |
|---|---|---|
| Personal laptop | Flotilla API → PostgreSQL | Always |
| Client laptop | Knowledge MCP → SQLite inbox | Always |

The destination is determined by **environment config**, not server reachability. No runtime fallback, no owner switching.

```yaml
# ~/agents/config.yaml (personal)
capture:
  destination: flotilla
  endpoint: http://localhost:9000/api/v1/captures

# ~/agents-work/config.yaml (client)
capture:
  destination: local
  # writes to knowledge.db inbox table
```

**If Flotilla is down on personal laptop:**

```
> /capture some idea

  ✗ Flotilla server unreachable. Restart with: python3 main.py
```

Explicit error. No silent store-switching. You fix the server (5 seconds), not deal with data ownership confusion.

### Capture Types

| System | Types | Features |
|---|---|---|
| Flotilla captures (personal) | idea, bug, decision, feature, reference, incident | Images, state machine, promote to issue/spec/decision |
| Knowledge inbox (client) | task, question, idea, concern | Text-only, assign to project, done/dismiss |

### What Does NOT Cross Environments

Client inbox items stay in `agents-work`. They are never exported, transferred, or visible on the personal laptop. They are client property.

---

## Pattern Sharing

### From Personal Laptop (Direct)

```bash
cd ~/agents/knowledge/patterns
vim new-pattern.yaml
git add . && git commit -m "pattern: rate limiting"
git push origin main

# Update parent repo bookmark
cd ~/agents
git submodule update --remote knowledge/patterns
git add knowledge/patterns && git commit -m "chore: update patterns" && git push
```

### From Client Laptop (GitHub Available) — Quarantine Branch

```bash
cd ~/agents-work/knowledge/patterns
vim new-pattern.yaml
git add . && git commit -m "pattern: rate limiting"
git push origin review/rate-limiting    # NEVER push to main

# On personal laptop — review the PR
# Check for client-specific terms
# Merge to main if clean
```

### From Client Laptop (GitHub Blocked) — Staged Patterns

```bash
# Stage the pattern locally
/pattern-stage rate-limiting.yaml
# Saves to ~/agents-work/staged-patterns/rate-limiting.yaml

# If GitHub available for agents-work repo:
cd ~/agents-work && git add staged-patterns/ && git commit -m "staged: rate limiting" && git push

# If GitHub also blocked:
# ⚠ staged-patterns/ is disk-only. Transfer before returning hardware.

# Transfer physically (USB, AirDrop)
# On personal laptop:
/pattern-import /tmp/staged-patterns/
```

### AI-Assisted Pattern Import

```
> /pattern-import /tmp/staged-patterns/

  ✓ new-pattern.yaml — added (new)
  ⚠ rate-limiting.yaml — exists, content differs

  EXISTING (personal):
    title: API Rate Limiting
    context: Redis sliding window, 1k rps
    last_updated: 2026-04-10

  INCOMING (from client):
    title: API Rate Limiting
    context: Redis sliding window + token bucket, 10k rps
    last_updated: 2026-04-17

  DIFF:
    + Added token bucket algorithm as alternative
    + Updated threshold from 1k to 10k rps
    - No client-specific references detected

  AI RECOMMENDATION: Update — incoming is a superset.

  Action: [update] [keep existing] [merge manually] [skip]
```

### Client Term Detection

```yaml
# ~/agents/config.yaml
pattern_review:
  flag_terms:
    - routeiq
    - docketiq
    - vitalai
    # add client company names, internal hostnames
```

If flagged terms appear:

```
  ⚠ CLIENT REFERENCE DETECTED: "routeiq" found in context field
  AI RECOMMENDATION: Merge manually — sanitize client reference first.
```

### Environment Config for Pattern Sharing

```yaml
# ~/agents-work/config.yaml
pattern_sharing:
  mode: "staged"       # options: github, staged, disabled
  remote_branch: "review/incoming"  # for github mode
  staged_dir: "staged-patterns"     # for staged mode
```

Default: `staged` (safest). Opt into `github` when confirmed available.

---

## Device Topology

```
┌──────────────────────────────────────────────────────┐
│              Personal Laptop (macbook)                │
│                                                       │
│  ~/agents/              Context layer (personal)     │
│  ~/projects/            Code repos                    │
│  Flotilla 127.0.0.1:9000  Operations layer           │
│  Knowledge MCP 127.0.0.1:9100  Context (HTTP mode)   │
│  PostgreSQL 127.0.0.1:5435  Operational data         │
│  tmux sessions          Agent sessions                │
│                                                       │
│  Manages devices:                                     │
│  ├── macbook (is_local=true)                         │
│  ├── jns-server (SSH)                                │
│  └── future devices                                   │
└──────────────────────────────────────────────────────┘
         │
         │ SSH + PostgreSQL network access
         │
┌──────────────────────────────────────────────────────┐
│              Home Server (jns-server)                  │
│                                                       │
│  ~/projects/            Deployed apps                 │
│  Connects to macbook's PostgreSQL                     │
│  Terminal sessions via Flotilla SSH bridge             │
│  Satellite — no independent operation                 │
│  When macbook sleeps, jns-server waits                │
└──────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────┐
│              Client Laptop (varies)                    │
│                                                       │
│  ~/agents-work/         Context layer (client)        │
│  ~/projects/            Client code repos             │
│  Knowledge MCP (stdio)  Context (no port, no listener)│
│  No Flotilla            CLI-only workflow              │
│  No PostgreSQL          SQLite only                    │
│  No tmux agents         Manual Claude sessions         │
└──────────────────────────────────────────────────────┘
```

### Degraded Mode

jns-server is a satellite of macbook. If macbook sleeps/reboots:
- jns-server loses PostgreSQL access
- Terminal sessions break
- Health monitoring stops
- When macbook wakes, everything reconnects automatically

This is acceptable for a single-user personal setup. If Flotilla moves to jns-server (always-on host), this resolves itself — future decision, not Phase 1.

---

## Daily Workflow

### Morning — Personal Laptop

```
1. /dashboard              ← cross-project status at a glance
                             Shows staleness warnings (⚠ 3d stale)
                             Checks services inline (Flotilla ✓ MCP ✓)
2. Open browser :9000      ← Flotilla visual dashboard (optional)
3. /project {name}         ← deep-dive into today's focus (optional)
4. /inbox                  ← triage yesterday's captures (optional)
```

### Morning — Client Laptop

```
1. /dashboard              ← client projects only
2. /project {name}         ← today's focus
3. /inbox                  ← triage
```

### During Work

```
/capture "idea or task" @project #type    ← non-interrupting, 1-line ack
```

### End of Day — Personal Laptop

```
1. /project {name} --focus "what I accomplished"
2. /inbox                  ← triage remaining items
3. cd ~/agents && git add -A && git commit && git push
```

### End of Day — Client Laptop

```
1. /project {name} --focus "what I accomplished"
2. cd ~/agents-work && git add -A && git commit && git push
3. (If new patterns staged: transfer before returning hardware)
```

### Weekly — Personal Laptop

```
1. /weekly                 ← auto-generated digest
2. /blockers               ← cross-project blocker board
```

### Recovery: Missed a Day

`/dashboard` shows staleness warnings:

```
┌─ flotilla ─────────────────────────────────────────┐
│ Focus: Terminal layout + agent sessions    ⚠ 3d stale │
└────────────────────────────────────────────────────────┘
```

No automation, no nag — just visibility. You decide whether to update.

---

## Flotilla Integration Details

### New: ProjectView "Context" Section

A collapsible section in ProjectView between Agent Work and Planned Work:

```
┌─ Context ──────────────────────────────────────────────┐
│ Focus: Terminal layout + agent sessions                 │
│                                                         │
│ Next Steps:                                             │
│ 1. [ ] E2E testing infrastructure                      │
│ 2. [ ] Add Project modal                               │
│ 3. [ ] Startup cleanup                                  │
│                                                         │
│ Blockers:                                               │
│ ! maison-scaffold Jinja syntax error (resolved)        │
│                                                         │
│                                          [Edit Context] │
└─────────────────────────────────────────────────────────┘
```

**Data source:** `GET /api/v1/knowledge/project/{name}` → proxied to Knowledge MCP → `get_project_context(project=name)`

**Edit flow:** Edit button → inline form → `POST /api/v1/knowledge/project/{name}/update` → proxied to Knowledge MCP → `update_project_context()` → writes to SQLite

### Existing Infrastructure (No Changes)

- Knowledge section in ProjectView (patterns, decisions, rules)
- MCP proxy route in `server/main.py`

---

## Security

### Client Hardware Return Checklist

1. Remove git credentials (`git credential reject` or clear keychain)
2. Remove submodule remote (patterns stay as files, no push access): `cd ~/agents-work/knowledge/patterns && git remote remove origin`
3. Delete Claude Code memory files: `rm -rf ~/.claude/memory`
4. Verify no personal data: `grep -r "flotilla\|buddy\|temper\|mymoney" ~/agents-work/` should return nothing
5. `~/agents-work/` stays — it's client property (their project data + shared patterns)
6. Revoke `jwj2002-work` GitHub access remotely if engagement is ending

### What Client Sees

- Their project tracker YAMLs (their property)
- Their decisions (their property)
- Shared patterns (your IP, shared intentionally)
- No personal project names, no Flotilla data, no other client data

### Emergency: Personal Data on Client Laptop

```bash
rm -rf ~/agents                              # if accidentally cloned
rm -rf ~/.claude/projects/*/memory/          # Claude Code memory
cd ~/agents-work && git reflog expire --expire=now --all && git gc --prune=now
```

---

## Build Phases

### Phase 1: Core Project Tracker (~/agents)

| Item | Effort | Location |
|---|---|---|
| Schema: project_tracker, inbox, journal tables | 30 min | knowledge/schema.sql |
| YAML source files for personal projects | 30 min | knowledge/projects/*.yaml |
| sync.py update (new tables, WAL mode, busy_timeout) | 1 hr | knowledge/sync.py |
| MCP tools: get_dashboard, get_project_context, update_project_context, capture, triage_inbox, get_journal | 2 hr | knowledge-mcp/ |
| Skills: /dashboard, /project, /inbox, /capture | 2 hr | claude-config/skills/ |
| config.yaml with capture destination | 15 min | ~/agents/config.yaml |

### Phase 2: Flotilla Integration

| Item | Effort | Location |
|---|---|---|
| ProjectView "Context" section | 1 hr | dashboard/src/components/ |
| MCP proxy extension for project tracker | 30 min | server/main.py |

### Phase 3: Multi-Environment Setup

| Item | Effort | Location |
|---|---|---|
| Create jwj2002/agent-patterns repo | 30 min | GitHub |
| Extract patterns + rules + config into submodule | 1 hr | ~/agents restructure |
| Branch protection on agent-patterns main | 15 min | GitHub settings |
| Create agents-work repo template | 30 min | GitHub |
| /pattern-stage and /pattern-import skills | 1.5 hr | claude-config/skills/ |
| Client term detection config | 30 min | config.yaml + skill logic |
| create-work-seed.sh bootstrap script | 30 min | scripts/ |
| config.yaml with pattern_sharing modes | 15 min | template |
| /patterns-sync skill (submodule pointer update) | 30 min | claude-config/skills/ |

### Phase 4: Weekly Automation

| Item | Effort | Location |
|---|---|---|
| /weekly digest generation | 45 min | skill + MCP tool |
| /blockers cross-project view | 30 min | skill + MCP tool |
| /deps dependency map | 30 min | skill + MCP tool |
| Auto-journal from git activity | 1 hr | MCP tool |
| Staleness warnings in /dashboard | 30 min | skill logic |

---

## Decisions Log

| # | Decision | Resolution | Rationale |
|---|---|---|---|
| D1 | Two layers vs one | Two layers (Operations + Context) | Different access patterns, portability needs |
| D2 | PostgreSQL vs SQLite for Flotilla | PostgreSQL | Concurrent writers, multi-device, atomic lease |
| D3 | SQLite for context | SQLite with WAL + busy_timeout | Portable, offline, git-trackable |
| D4 | No bidirectional sync | Each store owns its domain | Prevents conflicts, clear ownership |
| D5 | Flotilla personal only | No Flotilla on client hardware | Data residue risk, infrastructure footprint |
| D6 | CLI primary for capture | /capture like /btw (non-interrupting) | Minimal friction, works everywhere |
| D7 | One capture destination per env | Config-based, no reachability fallback | Clear ownership, no silent store-switching |
| D8 | Three repos | agent-patterns (shared), agents (personal), agents-work (client) | Isolation with shared IP |
| D9 | Submodule push model | Personal: main. Client: review/ branch or staged-patterns/ | Quarantine prevents client data in shared IP |
| D10 | Export scope | Patterns only. Never context, decisions, or inbox. | Client data stays on client hardware |
| D11 | Knowledge MCP transport | HTTP on personal (Flotilla needs it), stdio on client (no port) | Avoids port restrictions on client |
| D12 | Service binding | All services 127.0.0.1 only | No external exposure without explicit auth |
| D13 | jns-server degraded mode | Accept — satellite of macbook, reconnects on wake | Single-user setup, not production SaaS |
| D14 | Pattern import review | AI-assisted diff + client term detection | Prevents client references in shared IP |

---

## Acceptance Criteria

### Functional

- [ ] `/dashboard` shows all projects with focus, blockers, next steps, staleness warnings
- [ ] `/dashboard` checks service health inline (Flotilla ✓/✗, Knowledge MCP ✓/✗)
- [ ] `/project {name}` shows full context for one project
- [ ] `/capture {text}` returns acknowledgment within 1 second, Claude continues next tool call without pause
- [ ] `/capture` on personal laptop fails with clear error when Flotilla is down (no silent fallback)
- [ ] `/inbox` shows open items, supports triage (assign, done, dismiss)
- [ ] Flotilla ProjectView shows Context section from Knowledge MCP
- [ ] Context editable from Flotilla web UI (writes through MCP proxy)

### Isolation

- [ ] Fresh clone of `agents-work` contains zero files referencing personal project names (verified by grep)
- [ ] `agent-patterns` main branch requires PR (no direct push except owner)
- [ ] Client laptop push to `review/*` branch only (verified by branch protection)

### Portability

- [ ] With Wi-Fi disabled: `/dashboard`, `/project`, `/capture`, `/inbox` all return results from local SQLite
- [ ] `git clone agents && git submodule update` produces patterns directory with files matching the bookmarked commit
- [ ] Knowledge MCP in stdio mode works with no network listener

### Resilience

- [ ] Importing a pattern that already exists with identical content produces no git diff (no-op)
- [ ] Importing a pattern with same name but different content shows diff + AI recommendation
- [ ] Client term detection flags configured terms in incoming patterns
- [ ] Staged patterns survive reboot (persisted to disk in `staged-patterns/`)
- [ ] `/dashboard` shows `⚠ Nd stale` for projects with context older than 48 hours
