-- schema.sql

CREATE TABLE IF NOT EXISTS _meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS patterns (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'pilot', 'validated', 'deprecated')),
    tier TEXT NOT NULL CHECK (tier IN ('primary', 'secondary')),
    description TEXT,
    when_to_use TEXT,
    when_not_to_use TEXT,
    implementation TEXT,          -- JSON blob of implementation details
    dependencies TEXT,            -- JSON array of package dependencies
    tests TEXT,                   -- JSON array of test names
    reference_project TEXT,
    reference_path TEXT,
    related_decisions TEXT,       -- JSON array of decision IDs
    lifecycle TEXT,               -- JSON blob of lifecycle data (see pattern-lifecycle spec)
    consecutive_successes INTEGER DEFAULT 0,
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
    outcome TEXT,                 -- Set at creation time; decisions are append-only (see note below)
    linked_patterns TEXT,         -- JSON array of pattern IDs
    linked_issues TEXT,           -- JSON array of issue references
    linked_prs TEXT,              -- JSON array of PR references
    related_decisions TEXT,       -- JSON array of decision IDs
    created_at TEXT
);

-- Decisions are append-only. To record an outcome or revision, create a new
-- decision that references the original via related_decisions. This avoids
-- mutable-record complexity and matches how decisions work in practice.

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

CREATE TABLE IF NOT EXISTS project_summaries (
    project TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    updated_at TEXT,
    updated_by TEXT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_patterns_category ON patterns(category);
CREATE INDEX IF NOT EXISTS idx_patterns_tier ON patterns(tier);
CREATE INDEX IF NOT EXISTS idx_patterns_status ON patterns(status);
CREATE INDEX IF NOT EXISTS idx_decisions_project ON decisions(project);
CREATE INDEX IF NOT EXISTS idx_decisions_topic ON decisions(topic);
CREATE INDEX IF NOT EXISTS idx_learning_rules_approved ON learning_rules(approved);
CREATE INDEX IF NOT EXISTS idx_velocity_project ON velocity(project);
CREATE INDEX IF NOT EXISTS idx_velocity_task_type ON velocity(task_type);
CREATE INDEX IF NOT EXISTS idx_velocity_complexity ON velocity(complexity);
CREATE INDEX IF NOT EXISTS idx_velocity_date ON velocity(date);

-- Project tracker — one row per tracked project
CREATE TABLE IF NOT EXISTS project_tracker (
    project TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'blocked', 'done')),
    manual_status_override INTEGER DEFAULT 0,  -- 1 = don't auto-transition
    focus TEXT,
    next_steps TEXT,              -- JSON array, ordered
    blockers TEXT,                -- JSON array (prefix [auto] for auto-managed)
    open_questions TEXT,          -- JSON array
    specs TEXT,                   -- JSON array of {path, version, status, summary}
    dependencies TEXT,            -- JSON array of {project, what, status}
    updated_at TEXT,
    updated_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_project_tracker_status ON project_tracker(status);

-- Inbox — quick capture, triage later
CREATE TABLE IF NOT EXISTS inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    project TEXT,                 -- nullable (assign later)
    type TEXT NOT NULL DEFAULT 'task'
        CHECK (type IN ('task', 'question', 'idea', 'concern')),
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'done', 'dismissed')),
    created_at TEXT,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_inbox_status ON inbox(status);
CREATE INDEX IF NOT EXISTS idx_inbox_project ON inbox(project);

-- Journal — chronological log per project
CREATE TABLE IF NOT EXISTS journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project TEXT NOT NULL,
    entry TEXT NOT NULL,
    entry_type TEXT NOT NULL DEFAULT 'update'
        CHECK (entry_type IN ('update', 'decision', 'milestone', 'blocker_resolved', 'focus_change', 'commit', 'status_change')),
    commit_sha TEXT,              -- For dedup of auto-journaled commits
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_journal_project ON journal(project);
CREATE INDEX IF NOT EXISTS idx_journal_date ON journal(created_at);
CREATE INDEX IF NOT EXISTS idx_journal_commit_sha ON journal(commit_sha);

-- Full-text search for decisions (standalone — rebuilt from scratch during build)
CREATE VIRTUAL TABLE IF NOT EXISTS decisions_fts USING fts5(
    id, title, context, decision, reasoning
);
