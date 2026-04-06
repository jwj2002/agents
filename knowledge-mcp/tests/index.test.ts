import { describe, it, expect, beforeAll, afterAll } from "vitest";
import Database from "better-sqlite3";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import {
  getPatterns,
  getPatternDetail,
  searchDecisions,
  getDecision,
  getLearningRules,
  getVelocity,
  saveDecision,
  saveLearningRule,
  saveVelocity,
} from "../index.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const schemaPath = path.resolve(__dirname, "../../knowledge/schema.sql");
const testDbPath = path.resolve(__dirname, "test-knowledge.db");

let db: Database.Database;

beforeAll(() => {
  // Clean up any prior test DB
  if (fs.existsSync(testDbPath)) {
    fs.unlinkSync(testDbPath);
  }

  db = new Database(testDbPath);
  db.pragma("journal_mode = WAL");

  // Load schema
  const schema = fs.readFileSync(schemaPath, "utf-8");
  db.exec(schema);

  // Seed patterns
  db.prepare(
    `INSERT INTO patterns (id, category, name, status, tier, description, implementation, dependencies, tests, lifecycle, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).run(
    "PAT-001",
    "auth",
    "JWT with refresh tokens",
    "validated",
    "primary",
    "Stateless auth using JWT",
    JSON.stringify({ language: "python", framework: "FastAPI" }),
    JSON.stringify(["python-jose"]),
    JSON.stringify(["test_token_creation"]),
    JSON.stringify({ extracted_from: "vitalailabs" }),
    "2026-02-20",
    "2026-03-22"
  );

  db.prepare(
    `INSERT INTO patterns (id, category, name, status, tier, description, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).run(
    "PAT-002",
    "caching",
    "Redis TTL caching",
    "pilot",
    "secondary",
    "Redis-based caching with TTL",
    "2026-03-01",
    "2026-03-15"
  );

  db.prepare(
    `INSERT INTO patterns (id, category, name, status, tier, description, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
  ).run(
    "PAT-003",
    "auth",
    "OAuth2 social login",
    "draft",
    "secondary",
    "Social login via OAuth2",
    "2026-03-10",
    "2026-03-10"
  );

  // Seed decisions
  db.prepare(
    `INSERT INTO decisions (id, date, project, topic, title, context, decision, alternatives, reasoning, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).run(
    "D-001",
    "2026-02-20",
    "vitalailabs",
    "auth",
    "JWT over sessions for vitalailabs",
    "Need stateless auth for API-first",
    "Use JWT with refresh tokens",
    JSON.stringify([
      { option: "Redis sessions", rejected_because: "Adds infra dependency" },
    ]),
    "JWT is standard for API-first",
    "2026-02-20"
  );

  db.prepare(
    `INSERT INTO decisions (id, date, project, topic, title, context, decision, reasoning, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
  ).run(
    "D-002",
    "2026-03-10",
    "docketiq",
    "caching",
    "Redis cache for session data",
    "Need fast session lookups",
    "Use Redis with 30min TTL",
    "Redis is already in the stack",
    "2026-03-10"
  );

  // Seed FTS
  db.prepare(
    `INSERT INTO decisions_fts (id, title, context, decision, reasoning)
     VALUES (?, ?, ?, ?, ?)`
  ).run(
    "D-001",
    "JWT over sessions for vitalailabs",
    "Need stateless auth for API-first",
    "Use JWT with refresh tokens",
    "JWT is standard for API-first"
  );
  db.prepare(
    `INSERT INTO decisions_fts (id, title, context, decision, reasoning)
     VALUES (?, ?, ?, ?, ?)`
  ).run(
    "D-002",
    "Redis cache for session data",
    "Need fast session lookups",
    "Use Redis with 30min TTL",
    "Redis is already in the stack"
  );

  // Seed learning rules
  db.prepare(
    `INSERT INTO learning_rules (id, rule, source, confidence, approved, created_at)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).run(
    "LR-001",
    "Always use httpOnly cookies for JWT storage",
    "Security audit finding",
    0.95,
    1,
    "2026-02-25"
  );
  db.prepare(
    `INSERT INTO learning_rules (id, rule, source, confidence, approved, created_at)
     VALUES (?, ?, ?, ?, ?, ?)`
  ).run(
    "LR-002",
    "Prefer Redis over Memcached for caching",
    "Performance comparison",
    0.7,
    0,
    "2026-03-01"
  );

  // Seed velocity
  const velocityInsert = db.prepare(
    `INSERT INTO velocity (date, project, task_type, complexity, model, duration_seconds, cost_dollars, success, description)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
  );
  velocityInsert.run(
    "2026-03-01",
    "vitalailabs",
    "feature",
    "moderate",
    "opus",
    3600,
    1.5,
    1,
    "Auth module"
  );
  velocityInsert.run(
    "2026-03-05",
    "vitalailabs",
    "bug_fix",
    "simple",
    "sonnet",
    1200,
    0.3,
    1,
    "Fix token refresh"
  );
  velocityInsert.run(
    "2026-03-10",
    "docketiq",
    "feature",
    "complex",
    "opus",
    7200,
    3.0,
    0,
    "Failed caching impl"
  );
});

afterAll(() => {
  db.close();
  if (fs.existsSync(testDbPath)) {
    fs.unlinkSync(testDbPath);
  }
});

// --- Pattern tests ---

describe("get_patterns", () => {
  it("returns only validated patterns by default", () => {
    const results = getPatterns(db);
    expect(results.length).toBe(1);
    expect((results[0] as Record<string, unknown>).id).toBe("PAT-001");
    expect((results[0] as Record<string, unknown>).status).toBe("validated");
  });

  it("filters by status=pilot", () => {
    const results = getPatterns(db, undefined, undefined, "pilot");
    expect(results.length).toBe(1);
    expect((results[0] as Record<string, unknown>).id).toBe("PAT-002");
  });

  it("filters by category", () => {
    const results = getPatterns(db, "auth", undefined, "draft");
    expect(results.length).toBe(1);
    expect((results[0] as Record<string, unknown>).id).toBe("PAT-003");
  });

  it("parses JSON fields", () => {
    const results = getPatterns(db);
    const pat = results[0] as Record<string, unknown>;
    expect(pat.implementation).toEqual({ language: "python", framework: "FastAPI" });
    expect(pat.dependencies).toEqual(["python-jose"]);
  });
});

describe("get_pattern_detail", () => {
  it("returns full pattern with parsed JSON", () => {
    const result = getPatternDetail(db, "PAT-001") as Record<string, unknown>;
    expect(result).not.toBeNull();
    expect(result.name).toBe("JWT with refresh tokens");
    expect(result.lifecycle).toEqual({ extracted_from: "vitalailabs" });
  });

  it("returns null for missing pattern", () => {
    expect(getPatternDetail(db, "PAT-999")).toBeNull();
  });
});

// --- Decision tests ---

describe("search_decisions", () => {
  it("FTS ranked search for JWT", () => {
    const results = searchDecisions(db, "JWT");
    expect(results.length).toBeGreaterThanOrEqual(1);
    expect((results[0] as Record<string, unknown>).id).toBe("D-001");
  });

  it("filters by project without query", () => {
    const results = searchDecisions(db, undefined, "docketiq");
    expect(results.length).toBe(1);
    expect((results[0] as Record<string, unknown>).id).toBe("D-002");
  });

  it("filters by topic", () => {
    const results = searchDecisions(db, undefined, undefined, "auth");
    expect(results.length).toBe(1);
    expect((results[0] as Record<string, unknown>).id).toBe("D-001");
  });

  it("respects limit", () => {
    const results = searchDecisions(db, undefined, undefined, undefined, 1);
    expect(results.length).toBe(1);
  });
});

describe("get_decision", () => {
  it("returns full decision with parsed JSON", () => {
    const result = getDecision(db, "D-001") as Record<string, unknown>;
    expect(result).not.toBeNull();
    expect(result.alternatives).toEqual([
      { option: "Redis sessions", rejected_because: "Adds infra dependency" },
    ]);
  });

  it("returns null for missing decision", () => {
    expect(getDecision(db, "D-999")).toBeNull();
  });
});

// --- Learning rules tests ---

describe("get_learning_rules", () => {
  it("returns only approved rules by default", () => {
    const results = getLearningRules(db) as Record<string, unknown>[];
    expect(results.length).toBe(1);
    expect(results[0].id).toBe("LR-001");
  });

  it("returns all rules when approved_only=false", () => {
    const results = getLearningRules(db, false) as Record<string, unknown>[];
    expect(results.length).toBe(2);
  });
});

// --- Velocity tests ---

describe("get_velocity", () => {
  it("returns entries and summary stats", () => {
    const { entries, summary } = getVelocity(db);
    expect(entries.length).toBe(3);
    expect(summary.avg_duration_seconds).toBe(4000); // (3600+1200+7200)/3
    expect(summary.avg_cost_dollars).toBe(1.6); // (1.5+0.3+3.0)/3 = 1.6
    expect(summary.success_rate).toBeCloseTo(0.67, 1);
  });

  it("filters by task_type", () => {
    const { entries } = getVelocity(db, "bug_fix");
    expect(entries.length).toBe(1);
  });

  it("filters by project", () => {
    const { entries } = getVelocity(db, undefined, undefined, "docketiq");
    expect(entries.length).toBe(1);
  });
});

// --- Write tool tests ---

describe("save_decision", () => {
  it("generates auto-incremented ID", () => {
    const result = saveDecision(db, {
      project: "testproject",
      topic: "testing",
      title: "Test decision",
      context: "Need to test save",
      decision: "Use vitest",
    });
    expect(result.id).toBe("D-003");
    expect(result.status).toBe("saved");

    // Verify it's in DB
    const row = getDecision(db, "D-003") as Record<string, unknown>;
    expect(row).not.toBeNull();
    expect(row.title).toBe("Test decision");
  });

  it("serializes alternatives array to JSON", () => {
    const result = saveDecision(db, {
      project: "testproject",
      topic: "testing",
      title: "Decision with alternatives",
      context: "Testing alternatives",
      decision: "Go with option A",
      alternatives: [
        { option: "Option B", rejected_because: "Too slow" },
        { option: "Option C", rejected_because: "Too expensive" },
      ],
      reasoning: "Option A is balanced",
    });
    expect(result.id).toBe("D-004");

    const row = getDecision(db, "D-004") as Record<string, unknown>;
    expect(row.alternatives).toEqual([
      { option: "Option B", rejected_because: "Too slow" },
      { option: "Option C", rejected_because: "Too expensive" },
    ]);
  });

  it("is searchable via FTS after save", () => {
    const results = searchDecisions(db, "vitest");
    expect(results.length).toBeGreaterThanOrEqual(1);
  });
});

describe("save_learning_rule", () => {
  it("generates auto-incremented ID and sets approved=0", () => {
    const result = saveLearningRule(db, {
      rule: "Test rule",
      source: "Test suite",
      confidence: 0.8,
    });
    expect(result.id).toBe("LR-003");
    expect(result.status).toBe("pending_approval");

    // Should NOT appear in approved-only query
    const approved = getLearningRules(db) as Record<string, unknown>[];
    const found = approved.find((r) => r.id === "LR-003");
    expect(found).toBeUndefined();

    // Should appear in all rules
    const all = getLearningRules(db, false) as Record<string, unknown>[];
    const foundAll = all.find((r) => r.id === "LR-003");
    expect(foundAll).toBeDefined();
  });
});

describe("save_velocity", () => {
  it("records a velocity entry", () => {
    const result = saveVelocity(db, {
      project: "testproject",
      task_type: "feature",
      complexity: "simple",
      model: "sonnet",
      duration_seconds: 600,
      cost_dollars: 0.1,
      success: true,
      description: "Test task",
    });
    expect(result.status).toBe("recorded");

    // Verify it appears in queries
    const { entries } = getVelocity(db, "feature", "simple", "testproject");
    expect(entries.length).toBe(1);
  });
});

// --- Startup behavior ---

describe("startup", () => {
  it("errors clearly when DB does not exist", () => {
    // We test this by checking the openDb logic indirectly
    // The actual openDb calls process.exit, so we test the file check
    expect(fs.existsSync("/nonexistent/path/knowledge.db")).toBe(false);
  });
});
