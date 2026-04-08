# Knowledge Base

Centralized knowledge system for patterns, decisions, and learning rules. Used by Claude Code agents at runtime via MCP to make better implementation decisions.

## Quick Start

```bash
# 1. Install dependencies
cd ~/agents/knowledge-mcp && npm install

# 2. Build database from YAML sources
cd ~/agents/knowledge && python3 sync.py build

# 3. Verify
sqlite3 knowledge.db "SELECT COUNT(*) || ' patterns' FROM patterns; SELECT COUNT(*) || ' decisions' FROM decisions; SELECT COUNT(*) || ' learning_rules' FROM learning_rules;"
# Expected: 23 patterns, 8 decisions, 6 learning rules

# 4. Claude Code auto-starts the MCP server — no manual action needed
```

## How It Works

```
YAML files (source of truth, committed to git)
     │
     │  python3 sync.py build
     ▼
SQLite database (queryable store, gitignored)
     │
     │  Claude Code auto-starts MCP server
     ▼
knowledge-mcp (TypeScript MCP server, 13 tools)
     │
     │  Claude calls tools during sessions
     ▼
Agents get patterns, decisions, rules at runtime
```

You edit YAML files. `sync.py build` rebuilds the database. Claude queries via MCP. The database is never edited directly — YAML is the source of truth.

## Directory Structure

```
knowledge/
├── README.md                    # This file
├── schema.sql                   # SQLite schema (tables, indexes, FTS)
├── sync.py                      # YAML ↔ SQLite bidirectional sync
├── knowledge.db                 # SQLite database (gitignored, rebuilt from YAML)
├── patterns/                    # Code patterns (23 files)
│   ├── auth-jwt.yaml
│   ├── fastapi-database-layer.yaml
│   ├── fastapi-service-layer.yaml
│   └── ...
├── decisions/                   # Architectural decision records (8 files)
│   ├── index.yaml               # Decision index by project and topic
│   ├── D-001.yaml
│   └── ...
└── learning-rules/              # Rules extracted from failures (6 files)
    ├── LR-001.yaml
    └── ...

knowledge-mcp/                   # TypeScript MCP server
├── index.ts                     # 13 MCP tools
├── package.json                 # Dependencies (better-sqlite3, zod)
└── tests/                       # Vitest test suite
```

## Three Types of Knowledge

### Patterns (`knowledge/patterns/*.yaml`)

Reusable code patterns validated across projects. Each pattern has:

| Field | Purpose |
|-------|---------|
| `id` | Unique identifier (PAT-001, PAT-002, ...) |
| `category` | auth, database, repository, service, router, schema, etc. |
| `status` | draft → pilot → validated (lifecycle tracking) |
| `when_to_use` | Conditions where this pattern applies |
| `when_not_to_use` | Conditions where this pattern is wrong |
| `implementation` | How to implement (steps, file structure) |
| `reference_code` | Actual code from validated projects |
| `gotchas` | Real pitfalls discovered during use |
| `tests` | Test cases that verify correct implementation |
| `dependencies` | Required packages/frameworks |
| `lifecycle` | Validation history (extracted_at, pilot_started_at, validated_at) |

**Creating a new pattern:**

```yaml
# knowledge/patterns/my-new-pattern.yaml
id: PAT-024
category: caching
name: Redis Cache-Aside Pattern
status: draft
tier: secondary
description: Cache-aside pattern with TTL and invalidation
when_to_use: Read-heavy endpoints with stable data
when_not_to_use: Real-time data, write-heavy workloads
implementation:
  steps:
    - Add redis dependency
    - Create cache service
    - Wire into endpoints
reference_code: |
  # Your validated code here
gotchas:
  - Always set TTL — unbounded caches cause memory leaks
  - Invalidate on write, not on a timer
tests:
  - test_cache_hit_returns_cached
  - test_cache_miss_fetches_and_caches
  - test_cache_invalidation_on_write
dependencies:
  - redis>=5.0
```

### Decisions (`knowledge/decisions/D-*.yaml`)

Architectural decision records that capture WHY something was chosen:

```yaml
# knowledge/decisions/D-099.yaml
id: D-099
date: '2026-04-08'
project: flotilla
topic: database
title: Use asyncpg directly instead of SQLAlchemy async
context: Need high-throughput database access for real-time features
decision: Use asyncpg with raw SQL and connection pooling
alternatives:
  - option: SQLAlchemy async
    rejected_because: ORM overhead unacceptable for 10K+ queries/sec
reasoning: Performance benchmarks showed 3x throughput with asyncpg
linked_patterns: [PAT-004]
```

Decisions are **append-only**. To revise a decision, create a new one that references the original via `related_decisions`.

### Learning Rules (`knowledge/learning-rules/LR-*.yaml`)

Rules extracted from real agent failures:

```yaml
# knowledge/learning-rules/LR-007.yaml
id: LR-007
rule: Always include API response shapes in frontend work packages
source: "Agent wrote device.device_id instead of device.id because response shape was not specified"
confidence: 0.95
applies_to: all projects with frontend + API
approved: 1
```

Rules with `approved: 1` are loaded into context at session start via the `load_learning_rules.py` hook.

## Sync Commands

```bash
cd ~/agents/knowledge

# Rebuild SQLite from YAML (use after editing YAML files or pulling from git)
python3 sync.py build

# Export new SQLite records to YAML (use after MCP tools create records)
python3 sync.py export

# Full sync: git pull → export → build → git commit → git push
python3 sync.py sync
```

**When to run each:**

| Scenario | Command |
|----------|---------|
| Pulled latest from git | `python3 sync.py build` |
| Claude created a decision via MCP during a session | `python3 sync.py export` |
| Syncing between machines | `python3 sync.py sync` |
| After editing a YAML pattern file manually | `python3 sync.py build` |

## MCP Tools (13 total)

Claude calls these automatically — you don't invoke them manually.

### Query Tools

| Tool | Purpose |
|------|---------|
| `get_patterns` | List patterns by category, tier, or status |
| `get_pattern_detail` | Full detail for one pattern including code |
| `search_decisions` | Full-text search across decisions |
| `get_decision` | Full detail for one decision |
| `get_learning_rules` | List approved or all learning rules |
| `get_velocity` | Historical task velocity data |
| `get_project_summary` | Current summary for one project |
| `get_all_project_summaries` | All project summaries |
| `get_recent` | All activity since a date |

### Write Tools

| Tool | Purpose |
|------|---------|
| `save_decision` | Record a new decision (SQLite only — run `sync.py export` to create YAML) |
| `save_learning_rule` | Record a new rule as pending approval |
| `save_velocity` | Record a completed task for velocity tracking |
| `update_project_summary` | Create or update a project summary |

## New Machine Setup

```bash
# 1. Pull latest repo
cd ~/agents && git pull

# 2. Run installer (sets up hooks, plugins, symlinks)
cd ~/agents/claude-config && ./install.sh

# 3. Install knowledge-mcp dependencies
cd ~/agents/knowledge-mcp && npm install

# 4. Build database from YAML
cd ~/agents/knowledge && python3 sync.py build

# 5. Verify counts
sqlite3 knowledge/knowledge.db "SELECT COUNT(*) FROM patterns;"  # Should be 23+

# 6. Launch Claude Code — MCP server starts automatically
claude
```

## Validation

To verify the knowledge system is working in Claude Code, ask:

```
List all patterns in the knowledge base
```

Claude will call `get_patterns` via MCP and return results. If you see patterns listed, the system is working.

## Maintenance

### Weekly
- Run `python3 sync.py export` to capture any decisions Claude created during sessions
- Commit and push YAML changes: `cd ~/agents && git add knowledge/ && git commit -m "chore: sync knowledge" && git push`

### After Pattern Validation
- Update pattern status from `pilot` to `validated` in the YAML file
- Increment `consecutive_successes` count
- Run `python3 sync.py build` to update database

### After Agent Failure
- Claude records learning rules via `save_learning_rule` MCP tool
- Review pending rules: `sqlite3 knowledge.db "SELECT id, rule FROM learning_rules WHERE approved = 0;"`
- Approve valid rules by setting `approved: 1` in the YAML file
- Run `python3 sync.py build`
