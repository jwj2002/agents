---
title: "User Guide — Cross-Environment Development Platform"
status: DRAFT
created: 2026-04-17
updated: 2026-04-17
author: Jason Job
type: Documentation
complexity: MODERATE
version: v1.0
---

# User Guide

## Overview

This guide covers setup, daily usage, and maintenance of the two-layer development platform: Flotilla (web dashboard) for operations and Knowledge MCP (CLI) for cross-project context.

---

## Part 1: Setup

### 1.1 Personal Laptop — First Time

#### Prerequisites

- macOS with Homebrew
- Node.js 18+, Python 3.12+, PostgreSQL
- Claude Code CLI installed (`claude`)
- GitHub CLI (`gh`) authenticated as jwj2002
- tmux installed

#### Clone Repos

```bash
# Agents repo (context layer)
cd ~ && git clone git@github.com:jwj2002/agents.git

# Flotilla repo (operations layer)
cd ~/projects && git clone git@github.com:jwj2002/flotilla.git

# Build knowledge database
cd ~/agents/knowledge && python3 sync.py build

# Start Knowledge MCP
cd ~/agents/knowledge-mcp && npx tsx http-server.ts
# Runs on :9100

# Start Flotilla
cd ~/projects/flotilla/server && source .env && .venv/bin/python3 main.py
# Runs on :9000, serves dashboard at http://localhost:9000
```

#### Verify

```bash
# Knowledge MCP health
curl http://localhost:9100/health

# Flotilla health
curl http://localhost:9000/api/v1/health

# CLI skills
/dashboard    # should show project overview
```

### 1.2 Client Laptop — First Time

#### Prerequisites

- Claude Code CLI installed
- Python 3.12+ (for sync.py)
- Node.js 18+ (for knowledge-mcp)

#### Setup (GitHub Available)

```bash
# Clone agents-work
git clone git@github.com:jwj2002-work/agents-work.git ~/agents-work

# Build knowledge database
cd ~/agents-work/knowledge && python3 sync.py build

# Start Knowledge MCP
cd ~/agents-work/knowledge-mcp && npx tsx http-server.ts
```

#### Setup (GitHub Blocked)

```bash
# On personal laptop — create bundle
cd ~/agents && git bundle create /tmp/agents-work-seed.bundle main

# Transfer bundle to client laptop (USB, AirDrop)

# On client laptop
git clone /tmp/agents-work-seed.bundle ~/agents-work
cd ~/agents-work/knowledge && python3 sync.py build
cd ~/agents-work/knowledge-mcp && npx tsx http-server.ts
```

---

## Part 2: Daily Usage

### 2.1 Starting Your Day

#### Personal Laptop

```bash
# 1. Quick status across all projects
/dashboard

# Output:
# ACTIVE
# ┌─ flotilla ──────────────────────────────────────────┐
# │ Focus: Add Project modal + scaffold           1h ago │
# │ Next:  E2E testing > Startup cleanup > Agent escal. │
# └──────────────────────────────────────────────────────┘
# ┌─ buddy ─────────────────────────────────────────────┐
# │ Focus: Meeting transcription pipeline         3d ago │
# │ Next:  Fix audio chunking > Add speaker labels      │
# └──────────────────────────────────────────────────────┘
# INBOX (2 open)

# 2. Open Flotilla dashboard in browser
open http://localhost:9000

# 3. Deep-dive into today's project
/project flotilla

# 4. Triage inbox from yesterday
/inbox
```

#### Client Laptop

```bash
# Same workflow, different data
/dashboard       # shows client projects only
/project routeiq
/inbox
```

### 2.2 Capturing Ideas Mid-Work

The `/capture` command is **non-interrupting**. Claude acknowledges in one line and continues the current task.

```bash
# Basic capture
/capture need to add rate limiting before API launch

# With project tag
/capture check concurrent migration handling @routeiq #task

# With type tag
/capture shared component library across projects #idea

# Quick question for later
/capture ask Paul about staging deploy schedule #question
```

**Tags:**
- `@project` — assigns to a project (optional, triage later if omitted)
- `#type` — task, question, idea, concern (defaults to task)

**Where it goes:**
- Personal laptop (Flotilla running): Flotilla captures table (PostgreSQL)
- Client laptop (no Flotilla): Knowledge inbox (SQLite)

### 2.3 Updating Project Context

```bash
# Update what you're working on
/project flotilla --focus "Terminal layout and agent sessions"

# Mark a step done
/project flotilla --done "Add Project modal"

# Add a next step
/project flotilla --next "Playwright E2E testing"

# Add a blocker
/project routeiq --blocker "Waiting on Paul's API contract"

# Resolve a blocker
/project routeiq --unblock "Waiting on Paul's API contract"

# Add an open question
/project flotilla --question "Should captures merge between CLI and Flotilla?"
```

### 2.4 Using Flotilla Dashboard (Personal Laptop)

Open `http://localhost:9000` in your browser.

**Projects Page:**
- All projects as cards with category, tech stack, agent status
- Start/Stop agent from the card
- "Add Project" button for new projects (Create New or Add Existing)
- Category filter tabs (only shows categories with projects)

**Project View:**
- Agent section: Running/Stopped, Attach/Stop, work queue
- Context section: Focus, next steps, blockers (from Knowledge MCP)
- Planned Work, Issues, Git Status, Daily Summary, Knowledge sections
- Terminal drawer (Ctrl+`) — attaches to project's tmux session
- Capture input at top — text + drag-drop images

### 2.5 Triaging Inbox

```bash
/inbox

# Shows:
# OPEN (3)
# #12 [task]     Check concurrent migrations           @routeiq
# #11 [question] Ask Paul about staging schedule        —
# #10 [idea]     Shared component library               —
#
# Actions: [assign {id} {project}]  [done {id}]  [dismiss {id}]

# Assign to a project
/inbox assign 11 routeiq

# Mark done
/inbox done 12

# Dismiss (not actionable)
/inbox dismiss 10
```

### 2.6 End of Day

#### Personal Laptop

```bash
# Update project focus
/project flotilla --focus "Completed: agent sessions, terminal layout"

# Triage remaining inbox
/inbox

# Commit context updates
cd ~/agents && git add -A && git commit -m "daily: flotilla sessions complete" && git push
```

#### Client Laptop

```bash
# Update project focus
/project routeiq --focus "Completed: migration script draft"

# Export for personal laptop (if new patterns to share)
/export-daily > /tmp/daily-export.json
# Transfer to personal laptop

# Commit
cd ~/agents-work && git add -A && git commit -m "daily: migration progress" && git push
```

---

## Part 3: Weekly Review

```bash
# Auto-generated weekly digest
/weekly

# Shows:
# - Completed items per project
# - Open blockers (aging)
# - Priorities for next week
# - Metrics (sessions, tasks completed, decisions made)

# Cross-project blocker board
/blockers

# Shows:
# - All blockers across all projects
# - Age, owner, impact
# - Recently resolved
```

---

## Part 4: Working with Agents (Flotilla)

### Starting a Project Agent

**From browser:** Click "Start" on the project card → terminal drawer opens → Claude starts with channels

**From CLI:** The agent is available via the terminal drawer in the browser. No CLI equivalent (agents need the Flotilla server for work queue, callbacks).

### Sending Work to an Agent

1. Create a GitHub issue describing the task
2. In Flotilla, the issue syncs automatically (or click ↻ in Issues section)
3. The agent work queue picks it up
4. Agent reads the issue, implements, creates PR, calls back

### Monitoring Agent Work

- Agent Work section in ProjectView shows: in-progress, queued, escalated, completed
- Green dot on project card = agent running
- Terminal drawer to watch agent work in real-time
- Completed items auto-hide after 24h (dismiss button for immediate removal)

---

## Part 5: Patterns & Knowledge

### Discovering a Pattern

While working, you notice a reusable approach:

```bash
# Capture it first
/capture "Pattern: API rate limiting with sliding window + Redis" #idea

# Later, formalize as a pattern file
# Edit ~/agents/knowledge/patterns/rate-limiting.yaml

# Sync to knowledge.db
cd ~/agents/knowledge && python3 sync.py build

# Push to shared patterns repo
cd ~/agents/knowledge/patterns
git add rate-limiting.yaml && git commit -m "pattern: API rate limiting" && git push
```

### Using Patterns on Client Laptop

```bash
# Pull latest patterns (if GitHub available)
cd ~/agents-work/knowledge/patterns && git pull

# Or import via bundle (if GitHub blocked)
# On personal laptop:
cd ~/agents/knowledge/patterns && git bundle create /tmp/patterns.bundle main
# Transfer, then on client:
cd ~/agents-work/knowledge/patterns && git pull /tmp/patterns.bundle main

# Query patterns
/patterns rate limiting
```

### Recording Decisions

```bash
# Through Knowledge MCP
save_decision(
  project="flotilla",
  topic="data-storage",
  title="PostgreSQL for operations, SQLite for context",
  context="Need concurrent writers for agents, portability for CLI",
  decision="Two stores, each owns its domain",
  reasoning="SQLite can't handle concurrent agent callbacks..."
)
```

---

## Part 6: Multi-Environment Security

### What's on Each Machine

| Data | Personal Laptop | Client Laptop |
|---|---|---|
| Personal project names | Yes | No |
| Client project names | No | Yes |
| Shared patterns | Yes | Yes |
| Flotilla (PostgreSQL, agents, captures) | Yes | No |
| Knowledge.db | Personal version | Client version |
| GitHub credentials (jwj2002) | Yes | No |
| GitHub credentials (jwj2002-work) | No | Yes (if available) |

### Returning Client Hardware

```bash
# Remove git credentials
git credential-osxkeychain erase  # or equivalent

# Remove submodule remote (patterns stay as files)
cd ~/agents-work/knowledge/patterns && git remote remove origin

# Delete personal artifacts if any
rm -rf ~/.claude/memory  # Claude Code memory files

# The client keeps:
# - agents-work repo (their project data)
# - Patterns (shared IP — intentional)
# - No access to your personal repos or projects
```

### Emergency: Accidentally Put Personal Data on Client Laptop

```bash
# Remove the agents directory entirely
rm -rf ~/agents  # if accidentally cloned personal repo

# Clear Claude Code memory
rm -rf ~/.claude/projects/*/memory/

# Check git reflog for traces
cd ~/agents-work && git reflog expire --expire=now --all && git gc --prune=now
```

---

## Part 7: Troubleshooting

### Flotilla Server Won't Start

```bash
# Check if port is in use
lsof -ti:9000 | xargs kill

# Check PostgreSQL
pg_isready -h localhost -p 5435

# Check logs
tail -f /tmp/flotilla.log
```

### Knowledge MCP Not Responding

```bash
# Check if running
lsof -ti:9100

# Restart
cd ~/agents/knowledge-mcp && npx tsx http-server.ts
```

### `/dashboard` Shows Nothing

```bash
# Rebuild knowledge.db from YAML
cd ~/agents/knowledge && python3 sync.py build

# Verify project YAMLs exist
ls ~/agents/knowledge/projects/
```

### Agent Session Shows "Not logged in"

```bash
# Open terminal drawer, type:
/login

# Complete browser OAuth
# Claude restarts with Max plan + channels
```

### Stale tmux Sessions

```bash
# Flotilla handles this on startup (cleanup.py)
# Manual:
curl -X POST http://localhost:9000/api/v1/cleanup
```

---

## Quick Reference

| Command | Purpose | Works on Client? |
|---|---|---|
| `/dashboard` | Cross-project overview | Yes |
| `/project {name}` | Full project context | Yes |
| `/capture {text}` | Quick non-interrupting capture | Yes |
| `/inbox` | View + triage captures | Yes |
| `/blockers` | Cross-project blocker board | Yes |
| `/weekly` | Weekly digest | Yes |
| `/export-daily` | Export patterns + context | Yes |
| `/import-daily` | Import from client | Personal only |
| Flotilla (:9000) | Visual dashboard + agents | Personal only |
