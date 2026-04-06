---
title: "Developer Knowledge Base — sync script + knowledge MCP"
status: draft
created: 2026-04-04
author: Jason Job
location: ~/agents/knowledge/ and ~/agents/knowledge-mcp/
type: Integration
complexity: MODERATE
version: v1.0
---

# Developer Knowledge Base

## What This Is

A personal knowledge base for an agentic engineering workflow. YAML files in git are the source of truth. A sync script builds a SQLite database for fast agent queries. A knowledge MCP tool exposes the database to Claude Code agents via MCP tools.

This lives in `~/agents/` — personal infrastructure that works across all projects.

## Problem

Agents working on different projects make inconsistent decisions because they lack access to the developer's accumulated knowledge — proven patterns, past decisions, velocity data, and learning rules. Each project starts from scratch.

## Solution

```
YAML files (git repo, source of truth, portable, human-readable)
    ↕ sync.py
SQLite DB (working copy, fast queries, local, disposable)
    ↕ knowledge MCP
Claude Code agents (query patterns, search decisions, save new knowledge)
```

---

## File Structure

```
~/agents/
├── knowledge/
│   ├── sync.py                  # Sync script: YAML ↔ SQLite
│   ├── schema.sql               # SQLite schema definition
│   ├── patterns/                # Standard implementation patterns
│   │   ├── auth-jwt.yaml
│   │   ├── auth-redis-sessions.yaml
│   │   ├── caching-redis-ttl.yaml
│   │   ├── database-asyncpg.yaml
│   │   ├── export-streaming.yaml
│   │   └── error-handling.yaml
│   ├── decisions/               # Decision history
│   │   ├── index.yaml           # Index by project, topic, pattern
│   │   ├── D-001.yaml
│   │   ├── D-002.yaml
│   │   └── ...
│   ├── learning-rules/          # Extracted patterns from agent sessions
│   │   └── active.yaml
│   ├── velocity/                # Historical performance data
│   │   └── history.yaml
│   ├── knowledge.db             # GENERATED — gitignored
│   └── .gitignore               # Ignores knowledge.db
│
├── knowledge-mcp/
│   ├── index.ts                 # MCP server: exposes query/write tools
│   ├── package.json
│   ├── tsconfig.json
│   └── .env.example             # KNOWLEDGE_DB_PATH
│
├── claude-config/               # (existing)
└── email-helper/                # (existing)
```

---

## Component 1: YAML Schema

### Pattern File

Each pattern is one YAML file in `knowledge/patterns/`.

```yaml
# patterns/auth-jwt.yaml
id: PAT-001
category: auth
name: "JWT with refresh tokens"
tier: primary                    # primary | secondary | deprecated
description: "Stateless authentication using JWT access tokens and refresh tokens"
when_to_use: "API-first services, stateless, multi-client"
when_not_to_use: "Server-rendered apps needing server-side session state"

implementation:
  language: python
  framework: FastAPI
  key_files:
    - "auth/jwt_handler.py — token creation, validation, refresh"
    - "auth/auth_middleware.py — request authentication"
    - "auth/token_service.py — token storage and revocation"
  key_decisions:
    - "Access token TTL: 15 minutes"
    - "Refresh token TTL: 7 days"
    - "Token stored in httpOnly cookie, not localStorage"
  reference_project: vitalailabs
  reference_path: "backend/auth/"

dependencies:
  - "python-jose[cryptography]"
  - "passlib[bcrypt]"

tests:
  - "test_token_creation"
  - "test_token_expiry"
  - "test_refresh_flow"
  - "test_revocation"

related_decisions: [D-015]
validated_count: 3               # number of projects using this successfully
created_at: "2026-02-20"
updated_at: "2026-04-01"
```

### Decision File

Each decision is one YAML file in `knowledge/decisions/`.

```yaml
# decisions/D-015.yaml
id: D-015
date: "2026-02-20"
project: vitalailabs
topic: auth
title: "JWT over sessions for vitalailabs"

context: "vitalailabs is API-first, serving web and mobile clients.
  Need stateless auth that scales horizontally."

decision: "Use JWT with refresh tokens. Access token 15min, refresh 7 days."

alternatives:
  - option: "Redis sessions"
    rejected_because: "Adds infrastructure dependency. Not needed for stateless API."
  - option: "Session cookies"
    rejected_because: "Doesn't work for mobile clients. Not stateless."

reasoning: "JWT is the standard for API-first. No server-side state needed.
  Refresh tokens handle expiry without re-login."

outcome: "Implemented in PR #28. Working in production since Feb 2026."

linked:
  patterns: [PAT-001]
  issues: ["vitalailabs#15"]
  prs: ["vitalailabs#28"]
  related_decisions: [D-042]    # docketiq chose differently (sessions)

created_at: "2026-02-20"
```

### Decision Index

One index file for fast lookup without reading every decision.

```yaml
# decisions/index.yaml
by_project:
  docketiq:
    - { id: D-042, topic: auth, title: "Redis session cache", date: "2026-03-28" }
    - { id: D-087, topic: export, title: "Pluggable export formatters", date: "2026-04-04" }
    - { id: D-091, topic: auth, title: "Async lock for concurrency", date: "2026-04-02" }
  vitalailabs:
    - { id: D-015, topic: auth, title: "JWT over sessions", date: "2026-02-20" }
  flotilla:
    - { id: D-034, topic: database, title: "asyncpg direct, no ORM", date: "2026-04-03" }

by_topic:
  auth: [D-015, D-042, D-091]
  export: [D-087]
  database: [D-034]
  caching: [D-042]

by_pattern:
  PAT-001: [D-015]
  PAT-002: [D-042, D-091]
```

### Learning Rules

```yaml
# learning-rules/active.yaml
rules:
  - id: LR-001
    rule: "Always use custom exception classes per module. Never use bare Exception."
    source: "14 human corrections across docketiq and vitalailabs"
    confidence: 0.97
    applies_to: "all Python projects"
    approved: true
    created_at: "2026-03-15"

  - id: LR-002
    rule: "When fixing a concurrency bug, scan all projects for the same pattern."
    source: "Post-incident from D-091. Bug existed in temper, docketiq, vitalailabs."
    confidence: 1.0
    applies_to: "all projects"
    approved: true
    created_at: "2026-04-02"

  - id: LR-003
    rule: "Use decimal.Decimal for all money amounts, never float."
    source: "3 human corrections on billing code"
    confidence: 0.85
    applies_to: "projects with financial data"
    approved: false              # pending human review
    created_at: "2026-04-03"
```

### Velocity History

```yaml
# velocity/history.yaml
entries:
  - date: "2026-04-02"
    project: docketiq
    task_type: bug_fix
    complexity: moderate
    model: sonnet
    duration_seconds: 840
    cost_dollars: 0.72
    success: true
    description: "Auth concurrency fix"

  - date: "2026-04-04"
    project: docketiq
    task_type: feature
    complexity: simple
    model: sonnet
    duration_seconds: 1080
    cost_dollars: 1.05
    success: true
    description: "CSV export with streaming"
```

---

## Component 2: SQLite Schema

```sql
-- schema.sql

CREATE TABLE IF NOT EXISTS patterns (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    tier TEXT NOT NULL CHECK (tier IN ('primary', 'secondary', 'deprecated')),
    description TEXT,
    when_to_use TEXT,
    when_not_to_use TEXT,
    implementation TEXT,          -- JSON blob of implementation details
    dependencies TEXT,            -- JSON array of package dependencies
    tests TEXT,                   -- JSON array of test names
    reference_project TEXT,
    reference_path TEXT,
    related_decisions TEXT,       -- JSON array of decision IDs
    validated_count INTEGER DEFAULT 0,
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    date TEXT,
    project TEXT,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    context TEXT,
    decision TEXT NOT NULL,
    alternatives TEXT,            -- JSON array of {option, rejected_because}
    reasoning TEXT,
    outcome TEXT,
    linked_patterns TEXT,         -- JSON array of pattern IDs
    linked_issues TEXT,           -- JSON array of issue references
    linked_prs TEXT,              -- JSON array of PR references
    related_decisions TEXT,       -- JSON array of decision IDs
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS learning_rules (
    id TEXT PRIMARY KEY,
    rule TEXT NOT NULL,
    source TEXT,
    confidence REAL,
    applies_to TEXT,
    approved INTEGER DEFAULT 0,  -- 0=pending, 1=approved
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS velocity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    project TEXT,
    task_type TEXT,               -- bug_fix, feature, refactor, test, etc.
    complexity TEXT,              -- trivial, simple, moderate, complex
    model TEXT,                   -- sonnet, opus, haiku
    duration_seconds INTEGER,
    cost_dollars REAL,
    success INTEGER,             -- 0=failed, 1=success
    description TEXT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_patterns_category ON patterns(category);
CREATE INDEX IF NOT EXISTS idx_patterns_tier ON patterns(tier);
CREATE INDEX IF NOT EXISTS idx_decisions_project ON decisions(project);
CREATE INDEX IF NOT EXISTS idx_decisions_topic ON decisions(topic);
CREATE INDEX IF NOT EXISTS idx_learning_rules_approved ON learning_rules(approved);
CREATE INDEX IF NOT EXISTS idx_velocity_project ON velocity(project);
CREATE INDEX IF NOT EXISTS idx_velocity_task_type ON velocity(task_type);
CREATE INDEX IF NOT EXISTS idx_velocity_complexity ON velocity(complexity);
```

---

## Component 3: Sync Script

**File:** `knowledge/sync.py`

**Language:** Python 3.11+ (stdlib only — no pip dependencies)

**Commands:**

| Command | What It Does |
|---------|-------------|
| `python sync.py build` | Read all YAML files → create/rebuild SQLite DB |
| `python sync.py export` | Read SQLite for records newer than last export → write YAML files → update index.yaml |
| `python sync.py sync` | `git pull` → `build` → `export` → `git add` → `git commit` → `git push` |

### `build` behavior

1. Read `schema.sql` → create tables if not exist
2. Clear all tables (rebuild from scratch)
3. Walk `patterns/` → parse each YAML → insert into `patterns` table
4. Walk `decisions/` (skip `index.yaml`) → parse each YAML → insert into `decisions` table
5. Read `learning-rules/active.yaml` → insert each rule into `learning_rules` table
6. Read `velocity/history.yaml` → insert each entry into `velocity` table
7. Print summary: "Built knowledge.db: X patterns, Y decisions, Z rules, W velocity entries"

### `export` behavior

1. Query SQLite for records where `created_at` > last export timestamp (stored in a `_meta` table)
2. For each new/updated pattern: write `patterns/{id}.yaml`
3. For each new decision: write `decisions/{id}.yaml`, update `decisions/index.yaml`
4. For new learning rules: update `learning-rules/active.yaml`
5. For new velocity entries: append to `velocity/history.yaml`
6. Update `_meta.last_export` timestamp

### `sync` behavior

1. `git pull --rebase` (get changes from other machines)
2. Run `build` (rebuild DB from latest YAML)
3. Run `export` (write any local-only changes to YAML)
4. `git add -A knowledge/` (stage changes — excludes knowledge.db via .gitignore)
5. `git commit -m "knowledge sync: {summary}"` (skip if nothing changed)
6. `git push`

### Error Handling

- If YAML is malformed: skip file, log warning, continue
- If git pull has conflicts: abort sync, log error, require manual resolution
- If SQLite is corrupted: delete and rebuild from YAML (DB is disposable)

---

## Component 4: Knowledge MCP Tool

**File:** `knowledge-mcp/index.ts`

**Runtime:** Node.js (tsx for development, compiled for production)

**Transport:** stdio (standard MCP subprocess of Claude Code)

### MCP Server Declaration

```typescript
const server = new Server(
    { name: "knowledge", version: "0.1.0" },
    { capabilities: { tools: {} } }
);
```

No channel capability — this is a tool-only MCP server, not a channel.

### Configuration

| Env Var | Required | Default | Description |
|---------|----------|---------|-------------|
| `KNOWLEDGE_DB_PATH` | no | `~/agents/knowledge/knowledge.db` | Path to SQLite database |
| `KNOWLEDGE_SYNC_SCRIPT` | no | `~/agents/knowledge/sync.py` | Path to sync script (for write operations) |

### Tools

#### `get_patterns`

Get standard patterns by category.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `category` | string | no | Filter by category (auth, caching, database, etc.). Omit for all. |
| `tier` | string | no | Filter by tier (primary, secondary, deprecated). |

**Returns:** Array of pattern objects.

**Example:**
```
Agent calls: get_patterns(category: "auth", tier: "primary")
Returns: [{ id: "PAT-001", name: "JWT with refresh tokens", ... }]
```

#### `get_pattern_detail`

Get full detail for a specific pattern including implementation notes.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | yes | Pattern ID (e.g., "PAT-001") |

**Returns:** Full pattern object with implementation details, key files, dependencies.

#### `search_decisions`

Search decision history.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | no | Full-text search across title, context, decision, reasoning |
| `project` | string | no | Filter by project name |
| `topic` | string | no | Filter by topic (auth, caching, etc.) |
| `limit` | number | no | Max results (default: 10) |

**Returns:** Array of decision objects matching the query.

**Example:**
```
Agent calls: search_decisions(topic: "auth", project: "docketiq")
Returns: [{ id: "D-042", title: "Redis session cache", ... }, { id: "D-091", ... }]
```

#### `get_decision`

Get full detail for a specific decision.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | yes | Decision ID (e.g., "D-015") |

**Returns:** Full decision object with context, alternatives, reasoning, outcome, links.

#### `get_learning_rules`

Get active learning rules.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `approved_only` | boolean | no | Only return approved rules (default: true) |

**Returns:** Array of learning rule objects.

#### `get_velocity`

Get historical velocity data for estimation.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_type` | string | no | Filter by type (bug_fix, feature, refactor) |
| `complexity` | string | no | Filter by complexity (trivial, simple, moderate, complex) |
| `project` | string | no | Filter by project |
| `limit` | number | no | Max results (default: 50) |

**Returns:** Array of velocity entries + summary statistics (avg duration, avg cost, success rate).

#### `save_decision`

Save a new decision to the knowledge base.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project` | string | yes | Project name |
| `topic` | string | yes | Topic category |
| `title` | string | yes | Short title |
| `context` | string | yes | Why this decision was needed |
| `decision` | string | yes | What was decided |
| `alternatives` | string | no | JSON string of alternatives considered |
| `reasoning` | string | no | Why this alternative was chosen |

**Behavior:**
1. Generate ID: `D-{next_sequence_number}`
2. Insert into SQLite `decisions` table
3. Run `sync.py export` to write YAML and push to git
4. Return: `{ id: "D-XXX", status: "saved" }`

#### `save_learning_rule`

Save a new learning rule (pending human approval).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `rule` | string | yes | The rule text |
| `source` | string | yes | How this rule was discovered |
| `confidence` | number | no | Confidence score 0-1 |
| `applies_to` | string | no | Scope of the rule |

**Behavior:**
1. Generate ID: `LR-{next_sequence_number}`
2. Insert into SQLite with `approved=0` (pending)
3. Run `sync.py export`
4. Return: `{ id: "LR-XXX", status: "pending_approval" }`

#### `save_velocity`

Record a completed task for velocity tracking.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project` | string | yes | Project name |
| `task_type` | string | yes | bug_fix, feature, refactor, test |
| `complexity` | string | yes | trivial, simple, moderate, complex |
| `model` | string | yes | sonnet, opus, haiku |
| `duration_seconds` | number | yes | How long the task took |
| `cost_dollars` | number | yes | Token cost |
| `success` | boolean | yes | Did the task complete successfully |
| `description` | string | no | Brief description |

**Behavior:**
1. Insert into SQLite `velocity` table
2. Run `sync.py export`
3. Return: `{ status: "recorded" }`

---

## How Agents Load This

Add to any project's `.mcp.json`:

```json
{
  "mcpServers": {
    "knowledge": {
      "command": "npx",
      "args": ["tsx", "/home/jjob/agents/knowledge-mcp/index.ts"],
      "env": {
        "KNOWLEDGE_DB_PATH": "/home/jjob/agents/knowledge/knowledge.db"
      }
    }
  }
}
```

Or add to `~/.claude/settings.json` to make it available in ALL projects:

```json
{
  "mcpServers": {
    "knowledge": {
      "command": "npx",
      "args": ["tsx", "/home/jjob/agents/knowledge-mcp/index.ts"]
    }
  }
}
```

---

## Integration with vitalai-channels

The knowledge base is **independent infrastructure**. It works without vitalai-channels.

vitalai-channels can **optionally** integrate with it:
- Central server reads the knowledge SQLite to serve patterns via API endpoints
- Dashboard displays patterns alongside project data
- Strategic agents query patterns during work package creation
- Execution agents get pattern references in work package context
- Configured via `KNOWLEDGE_ENABLED=true` and `KNOWLEDGE_DB_PATH` in the server's `.env`

This integration is a separate issue in the vitalai-channels repo. It is NOT part of this spec.

---

## Implementation Order

1. **Create `knowledge/schema.sql`** — SQLite table definitions
2. **Create `knowledge/sync.py`** — build, export, sync commands
3. **Create seed YAML files** — initial patterns from existing projects (auth-jwt, auth-redis, database-asyncpg, export-streaming, error-handling)
4. **Create seed decisions** — key decisions already made (D-015, D-034, D-042, D-087, D-091)
5. **Create `knowledge-mcp/index.ts`** — MCP tool server with all 8 tools
6. **Test**: run `sync.py build` → verify DB. Load MCP in Claude → query patterns.
7. **Add to `~/agents/.mcp.json`** or `~/.claude/settings.json` for global availability

---

## Acceptance Criteria

- [ ] `python sync.py build` creates knowledge.db from YAML files
- [ ] `python sync.py export` writes new SQLite records to YAML and updates index
- [ ] `python sync.py sync` does full git pull → build → export → commit → push
- [ ] knowledge.db is gitignored
- [ ] Knowledge MCP loads in Claude Code via `.mcp.json`
- [ ] `get_patterns("auth")` returns JWT and Redis session patterns
- [ ] `search_decisions(topic="auth", project="docketiq")` returns relevant decisions
- [ ] `get_learning_rules()` returns approved rules only by default
- [ ] `get_velocity(task_type="bug_fix")` returns history + summary stats
- [ ] `save_decision(...)` inserts into SQLite and exports to YAML
- [ ] `save_learning_rule(...)` inserts with approved=false (pending)
- [ ] `save_velocity(...)` records task completion
- [ ] Sync script uses stdlib only (no pip dependencies)
- [ ] Knowledge MCP has no dependency on vitalai-channels
- [ ] Works on any machine where ~/agents is cloned
