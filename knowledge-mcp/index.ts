import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import Database from "better-sqlite3";
import { z } from "zod";
import path from "path";
import { fileURLToPath } from "url";
import fs from "fs";

// --- DB setup ---

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const dbPath =
  process.env.KNOWLEDGE_DB_PATH ||
  path.resolve(__dirname, "../knowledge/knowledge.db");

function openDb(dbFilePath: string): Database.Database {
  if (!fs.existsSync(dbFilePath)) {
    console.error(
      `Knowledge DB not found at ${dbFilePath}. Run: python sync.py build`
    );
    process.exit(1);
  }
  const db = new Database(dbFilePath);
  db.pragma("journal_mode = WAL");
  return db;
}

// --- JSON field parsing helper ---

function parseJsonFields<T extends Record<string, unknown>>(
  row: T,
  fields: string[]
): T {
  const result = { ...row };
  for (const field of fields) {
    const val = result[field];
    if (typeof val === "string") {
      try {
        (result as Record<string, unknown>)[field] = JSON.parse(val);
      } catch {
        // leave as-is if not valid JSON
      }
    }
  }
  return result;
}

// --- Exported query functions (for testing) ---

export function getPatterns(
  db: Database.Database,
  category?: string,
  tier?: string,
  status?: string
) {
  const conditions: string[] = [];
  const params: Record<string, string> = {};

  const effectiveStatus = status ?? "validated";
  conditions.push("status = :status");
  params.status = effectiveStatus;

  if (category) {
    conditions.push("category = :category");
    params.category = category;
  }
  if (tier) {
    conditions.push("tier = :tier");
    params.tier = tier;
  }

  const where = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";
  const rows = db.prepare(`SELECT * FROM patterns ${where}`).all(params) as Record<string, unknown>[];
  return rows.map((r) =>
    parseJsonFields(r, [
      "implementation",
      "dependencies",
      "tests",
      "lifecycle",
      "related_decisions",
    ])
  );
}

export function getPatternDetail(db: Database.Database, id: string) {
  const row = db.prepare("SELECT * FROM patterns WHERE id = ?").get(id) as
    | Record<string, unknown>
    | undefined;
  if (!row) return null;
  return parseJsonFields(row, [
    "implementation",
    "dependencies",
    "tests",
    "lifecycle",
    "related_decisions",
  ]);
}

export function searchDecisions(
  db: Database.Database,
  query?: string,
  project?: string,
  topic?: string,
  limit?: number
) {
  const effectiveLimit = limit ?? 10;

  if (query) {
    const rows = db
      .prepare(
        `SELECT d.* FROM decisions d
         JOIN decisions_fts fts ON d.id = fts.id
         WHERE decisions_fts MATCH ?
         ORDER BY rank
         LIMIT ?`
      )
      .all(query, effectiveLimit) as Record<string, unknown>[];
    return rows.map((r) =>
      parseJsonFields(r, [
        "alternatives",
        "linked_patterns",
        "linked_issues",
        "linked_prs",
        "related_decisions",
      ])
    );
  }

  const conditions: string[] = [];
  const params: Record<string, unknown> = {};

  if (project) {
    conditions.push("project = :project");
    params.project = project;
  }
  if (topic) {
    conditions.push("topic = :topic");
    params.topic = topic;
  }

  const where = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";
  const rows = db
    .prepare(`SELECT * FROM decisions ${where} LIMIT :limit`)
    .all({ ...params, limit: effectiveLimit }) as Record<string, unknown>[];
  return rows.map((r) =>
    parseJsonFields(r, [
      "alternatives",
      "linked_patterns",
      "linked_issues",
      "linked_prs",
      "related_decisions",
    ])
  );
}

export function getDecision(db: Database.Database, id: string) {
  const row = db.prepare("SELECT * FROM decisions WHERE id = ?").get(id) as
    | Record<string, unknown>
    | undefined;
  if (!row) return null;
  return parseJsonFields(row, [
    "alternatives",
    "linked_patterns",
    "linked_issues",
    "linked_prs",
    "related_decisions",
  ]);
}

export function getLearningRules(
  db: Database.Database,
  approvedOnly?: boolean
) {
  const effective = approvedOnly ?? true;
  if (effective) {
    return db
      .prepare("SELECT * FROM learning_rules WHERE approved = 1")
      .all();
  }
  return db.prepare("SELECT * FROM learning_rules").all();
}

export function getVelocity(
  db: Database.Database,
  taskType?: string,
  complexity?: string,
  project?: string,
  limit?: number
) {
  const effectiveLimit = limit ?? 50;
  const conditions: string[] = [];
  const params: Record<string, unknown> = {};

  if (taskType) {
    conditions.push("task_type = :task_type");
    params.task_type = taskType;
  }
  if (complexity) {
    conditions.push("complexity = :complexity");
    params.complexity = complexity;
  }
  if (project) {
    conditions.push("project = :project");
    params.project = project;
  }

  const where = conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";
  const entries = db
    .prepare(`SELECT * FROM velocity ${where} ORDER BY date DESC LIMIT :limit`)
    .all({ ...params, limit: effectiveLimit }) as Record<string, unknown>[];

  // Compute summary
  const durations = entries
    .map((e) => e.duration_seconds as number)
    .filter((d) => d != null);
  const costs = entries
    .map((e) => e.cost_dollars as number)
    .filter((c) => c != null);
  const successes = entries.filter((e) => e.success === 1).length;

  const summary = {
    count: entries.length,
    avg_duration_seconds:
      durations.length > 0
        ? Math.round(durations.reduce((a, b) => a + b, 0) / durations.length)
        : null,
    avg_cost_dollars:
      costs.length > 0
        ? Math.round((costs.reduce((a, b) => a + b, 0) / costs.length) * 100) / 100
        : null,
    success_rate:
      entries.length > 0
        ? Math.round((successes / entries.length) * 100) / 100
        : null,
  };

  return { entries, summary };
}

export function saveDecision(
  db: Database.Database,
  params: {
    project: string;
    topic: string;
    title: string;
    context: string;
    decision: string;
    alternatives?: { option: string; rejected_because: string }[];
    reasoning?: string;
  }
) {
  // Find max D-NNN and increment
  const maxRow = db
    .prepare(
      "SELECT id FROM decisions WHERE id LIKE 'D-%' ORDER BY CAST(SUBSTR(id, 3) AS INTEGER) DESC LIMIT 1"
    )
    .get() as { id: string } | undefined;

  let nextNum = 1;
  if (maxRow) {
    const num = parseInt(maxRow.id.substring(2), 10);
    if (!isNaN(num)) nextNum = num + 1;
  }
  const id = `D-${String(nextNum).padStart(3, "0")}`;
  const now = new Date().toISOString();

  db.prepare(
    `INSERT INTO decisions (id, date, project, topic, title, context, decision, alternatives, reasoning, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).run(
    id,
    now.split("T")[0],
    params.project,
    params.topic,
    params.title,
    params.context,
    params.decision,
    params.alternatives ? JSON.stringify(params.alternatives) : null,
    params.reasoning ?? null,
    now
  );

  // Also insert into FTS
  db.prepare(
    `INSERT INTO decisions_fts (id, title, context, decision, reasoning)
     VALUES (?, ?, ?, ?, ?)`
  ).run(id, params.title, params.context, params.decision, params.reasoning ?? null);

  return { id, status: "saved" };
}

export function saveLearningRule(
  db: Database.Database,
  params: {
    rule: string;
    source: string;
    confidence?: number;
    applies_to?: string;
  }
) {
  const maxRow = db
    .prepare(
      "SELECT id FROM learning_rules WHERE id LIKE 'LR-%' ORDER BY CAST(SUBSTR(id, 4) AS INTEGER) DESC LIMIT 1"
    )
    .get() as { id: string } | undefined;

  let nextNum = 1;
  if (maxRow) {
    const num = parseInt(maxRow.id.substring(3), 10);
    if (!isNaN(num)) nextNum = num + 1;
  }
  const id = `LR-${String(nextNum).padStart(3, "0")}`;
  const now = new Date().toISOString();

  db.prepare(
    `INSERT INTO learning_rules (id, rule, source, confidence, applies_to, approved, created_at)
     VALUES (?, ?, ?, ?, ?, 0, ?)`
  ).run(
    id,
    params.rule,
    params.source,
    params.confidence ?? null,
    params.applies_to ?? null,
    now
  );

  return { id, status: "pending_approval" };
}

export function saveVelocity(
  db: Database.Database,
  params: {
    project: string;
    task_type: string;
    complexity: string;
    model: string;
    duration_seconds: number;
    cost_dollars: number;
    success: boolean;
    description?: string;
  }
) {
  const now = new Date().toISOString();
  db.prepare(
    `INSERT INTO velocity (date, project, task_type, complexity, model, duration_seconds, cost_dollars, success, description)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).run(
    now.split("T")[0],
    params.project,
    params.task_type,
    params.complexity,
    params.model,
    params.duration_seconds,
    params.cost_dollars,
    params.success ? 1 : 0,
    params.description ?? null
  );

  return { status: "recorded" };
}

// --- Project Summaries ---

export function updateProjectSummary(
  db: Database.Database,
  project: string,
  summary: string,
  updatedBy?: string
) {
  const now = new Date().toISOString();
  db.prepare(
    `INSERT INTO project_summaries (project, summary, updated_at, updated_by)
     VALUES (?, ?, ?, ?)
     ON CONFLICT(project) DO UPDATE SET
       summary = excluded.summary,
       updated_at = excluded.updated_at,
       updated_by = excluded.updated_by`
  ).run(project, summary, now, updatedBy ?? null);
  return { project, status: "updated" };
}

export function getProjectSummary(db: Database.Database, project: string) {
  return db.prepare("SELECT * FROM project_summaries WHERE project = ?").get(project) ?? null;
}

export function getAllProjectSummaries(db: Database.Database) {
  return db.prepare("SELECT * FROM project_summaries ORDER BY project").all();
}

// --- Recent Activity ---

export function getRecent(db: Database.Database, since: string, limit?: number) {
  const effectiveLimit = limit ?? 50;

  const decisions = db
    .prepare("SELECT * FROM decisions WHERE created_at >= ? ORDER BY created_at DESC LIMIT ?")
    .all(since, effectiveLimit) as Record<string, unknown>[];

  const patterns = db
    .prepare("SELECT id, category, name, status, description, created_at FROM patterns WHERE created_at >= ? ORDER BY created_at DESC LIMIT ?")
    .all(since, effectiveLimit);

  const rules = db
    .prepare("SELECT * FROM learning_rules WHERE created_at >= ? ORDER BY created_at DESC LIMIT ?")
    .all(since, effectiveLimit);

  const summaries = db
    .prepare("SELECT * FROM project_summaries WHERE updated_at >= ? ORDER BY updated_at DESC LIMIT ?")
    .all(since, effectiveLimit);

  return {
    decisions: decisions.map((r) =>
      parseJsonFields(r, ["alternatives", "linked_patterns", "linked_issues", "linked_prs", "related_decisions"])
    ),
    patterns,
    rules,
    summaries,
  };
}

// --- MCP Server setup (only when run directly, not when imported for tests) ---

export { openDb };

const isMainModule =
  process.argv[1] &&
  (process.argv[1].endsWith("index.ts") || process.argv[1].endsWith("index.js"));

if (isMainModule) {
  const server = new McpServer(
    { name: "knowledge", version: "0.1.0" },
    { capabilities: { tools: {} } }
  );

  const db = openDb(dbPath);

  // Tool 1: get_patterns
  server.tool(
    "get_patterns",
    "Get standard patterns by category. Returns only validated patterns by default.",
    {
      category: z.string().optional().describe("Filter by category (auth, caching, database, etc.)"),
      tier: z.string().optional().describe("Filter by tier (primary, secondary)"),
      status: z
        .string()
        .optional()
        .describe('Filter by lifecycle status (draft, pilot, validated, deprecated). Defaults to "validated".'),
    },
    async ({ category, tier, status }) => {
      const results = getPatterns(db, category, tier, status);
      return { content: [{ type: "text" as const, text: JSON.stringify(results, null, 2) }] };
    }
  );

  // Tool 2: get_pattern_detail
  server.tool(
    "get_pattern_detail",
    "Get full detail for a specific pattern including implementation notes.",
    {
      id: z.string().describe('Pattern ID (e.g., "PAT-001")'),
    },
    async ({ id }) => {
      const result = getPatternDetail(db, id);
      if (!result) {
        return {
          content: [{ type: "text" as const, text: `Pattern ${id} not found` }],
          isError: true,
        };
      }
      return { content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }] };
    }
  );

  // Tool 3: search_decisions
  server.tool(
    "search_decisions",
    "Search decision history. Uses FTS5 for ranked full-text search when query is provided.",
    {
      query: z.string().optional().describe("Full-text search across title, context, decision, reasoning"),
      project: z.string().optional().describe("Filter by project name"),
      topic: z.string().optional().describe("Filter by topic (auth, caching, etc.)"),
      limit: z.number().optional().describe("Max results (default: 10)"),
    },
    async ({ query, project, topic, limit }) => {
      const results = searchDecisions(db, query, project, topic, limit);
      return { content: [{ type: "text" as const, text: JSON.stringify(results, null, 2) }] };
    }
  );

  // Tool 4: get_decision
  server.tool(
    "get_decision",
    "Get full detail for a specific decision.",
    {
      id: z.string().describe('Decision ID (e.g., "D-015")'),
    },
    async ({ id }) => {
      const result = getDecision(db, id);
      if (!result) {
        return {
          content: [{ type: "text" as const, text: `Decision ${id} not found` }],
          isError: true,
        };
      }
      return { content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }] };
    }
  );

  // Tool 5: get_learning_rules
  server.tool(
    "get_learning_rules",
    "Get active learning rules.",
    {
      approved_only: z.boolean().optional().describe("Only return approved rules (default: true)"),
    },
    async ({ approved_only }) => {
      const results = getLearningRules(db, approved_only);
      return { content: [{ type: "text" as const, text: JSON.stringify(results, null, 2) }] };
    }
  );

  // Tool 6: get_velocity
  server.tool(
    "get_velocity",
    "Get historical velocity data for estimation. Returns entries and summary statistics.",
    {
      task_type: z.string().optional().describe("Filter by type (bug_fix, feature, refactor)"),
      complexity: z.string().optional().describe("Filter by complexity (trivial, simple, moderate, complex)"),
      project: z.string().optional().describe("Filter by project"),
      limit: z.number().optional().describe("Max results (default: 50)"),
    },
    async ({ task_type, complexity, project, limit }) => {
      const results = getVelocity(db, task_type, complexity, project, limit);
      return { content: [{ type: "text" as const, text: JSON.stringify(results, null, 2) }] };
    }
  );

  // Tool 7: save_decision
  server.tool(
    "save_decision",
    "Save a new decision to the knowledge base. SQLite only, no git.",
    {
      project: z.string().describe("Project name"),
      topic: z.string().describe("Topic category"),
      title: z.string().describe("Short title"),
      context: z.string().describe("Why this decision was needed"),
      decision: z.string().describe("What was decided"),
      alternatives: z
        .array(
          z.object({
            option: z.string(),
            rejected_because: z.string(),
          })
        )
        .optional()
        .describe("Array of considered alternatives"),
      reasoning: z.string().optional().describe("Why this alternative was chosen"),
    },
    async ({ project, topic, title, context, decision, alternatives, reasoning }) => {
      const result = saveDecision(db, {
        project,
        topic,
        title,
        context,
        decision,
        alternatives,
        reasoning,
      });
      return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
    }
  );

  // Tool 8: save_learning_rule
  server.tool(
    "save_learning_rule",
    "Save a new learning rule (pending human approval). SQLite only.",
    {
      rule: z.string().describe("The rule text"),
      source: z.string().describe("How this rule was discovered"),
      confidence: z.number().optional().describe("Confidence score 0-1"),
      applies_to: z.string().optional().describe("Scope of the rule"),
    },
    async ({ rule, source, confidence, applies_to }) => {
      const result = saveLearningRule(db, { rule, source, confidence, applies_to });
      return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
    }
  );

  // Tool 9: save_velocity
  server.tool(
    "save_velocity",
    "Record a completed task for velocity tracking. SQLite only.",
    {
      project: z.string().describe("Project name"),
      task_type: z.string().describe("bug_fix, feature, refactor, test"),
      complexity: z.string().describe("trivial, simple, moderate, complex"),
      model: z.string().describe("sonnet, opus, haiku"),
      duration_seconds: z.number().describe("How long the task took"),
      cost_dollars: z.number().describe("Token cost"),
      success: z.boolean().describe("Did the task complete successfully"),
      description: z.string().optional().describe("Brief description"),
    },
    async ({ project, task_type, complexity, model, duration_seconds, cost_dollars, success, description }) => {
      const result = saveVelocity(db, {
        project,
        task_type,
        complexity,
        model,
        duration_seconds,
        cost_dollars,
        success,
        description,
      });
      return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
    }
  );

  // Tool 10: update_project_summary
  server.tool(
    "update_project_summary",
    "Create or update a project's living summary. Overwrites previous summary.",
    {
      project: z.string().describe("Project name"),
      summary: z.string().describe("Current project state, architecture, focus areas"),
      updated_by: z.string().optional().describe("Who updated (agent name or 'human')"),
    },
    async ({ project, summary, updated_by }) => {
      const result = updateProjectSummary(db, project, summary, updated_by);
      return { content: [{ type: "text" as const, text: JSON.stringify(result) }] };
    }
  );

  // Tool 11: get_project_summary
  server.tool(
    "get_project_summary",
    "Get the current summary for a project.",
    {
      project: z.string().describe("Project name"),
    },
    async ({ project }) => {
      const result = getProjectSummary(db, project);
      if (!result) {
        return { content: [{ type: "text" as const, text: `No summary for project "${project}"` }] };
      }
      return { content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }] };
    }
  );

  // Tool 12: get_all_project_summaries
  server.tool(
    "get_all_project_summaries",
    "Get summaries for all projects.",
    {},
    async () => {
      const results = getAllProjectSummaries(db);
      return { content: [{ type: "text" as const, text: JSON.stringify(results, null, 2) }] };
    }
  );

  // Tool 13: get_recent
  server.tool(
    "get_recent",
    "Get all knowledge base activity since a date — decisions, patterns, rules, summaries across all projects.",
    {
      since: z.string().describe("ISO date or datetime (e.g., '2026-04-07' or '2026-04-07T00:00:00Z')"),
      limit: z.number().optional().describe("Max results per category (default: 50)"),
    },
    async ({ since, limit }) => {
      const results = getRecent(db, since, limit);
      return { content: [{ type: "text" as const, text: JSON.stringify(results, null, 2) }] };
    }
  );

  // --- Start server ---
  const transport = new StdioServerTransport();
  server.connect(transport).catch((err) => {
    console.error("Fatal error:", err);
    process.exit(1);
  });
}
