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

-- Full-text search for decisions (standalone — rebuilt from scratch during build)
CREATE VIRTUAL TABLE IF NOT EXISTS decisions_fts USING fts5(
    id, title, context, decision, reasoning
);
