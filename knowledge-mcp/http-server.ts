/**
 * Knowledge MCP HTTP API — lightweight server for dashboard integration.
 * Run: KNOWLEDGE_DB_PATH=... npx tsx http-server.ts
 * Or: starts automatically alongside MCP when KNOWLEDGE_HTTP_PORT is set.
 */

import http from "node:http";
import {
  openDb,
  getPatterns,
  getPatternDetail,
  searchDecisions,
  getDecision,
  getLearningRules,
  getVelocity,
  getProjectSummary,
  getAllProjectSummaries,
  getRecent,
} from "./index.js";

const dbPath =
  process.env.KNOWLEDGE_DB_PATH ||
  new URL("../knowledge/knowledge.db", import.meta.url).pathname;

const port = parseInt(process.env.KNOWLEDGE_HTTP_PORT || "9100", 10);
const db = openDb(dbPath);

function json(res: http.ServerResponse, data: unknown, status = 200) {
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  });
  res.end(JSON.stringify(data));
}

function parseQuery(url: string): Record<string, string> {
  const idx = url.indexOf("?");
  if (idx === -1) return {};
  const params: Record<string, string> = {};
  for (const pair of url.substring(idx + 1).split("&")) {
    const [k, v] = pair.split("=");
    if (k) params[decodeURIComponent(k)] = decodeURIComponent(v || "");
  }
  return params;
}

const server = http.createServer((req, res) => {
  if (req.method === "OPTIONS") {
    json(res, {});
    return;
  }

  const url = req.url || "/";
  const path = url.split("?")[0];
  const query = parseQuery(url);

  try {
    // Health
    if (path === "/health") {
      json(res, { status: "ok" });
      return;
    }

    // Project summaries
    if (path === "/api/v1/knowledge/projects") {
      json(res, { summaries: getAllProjectSummaries(db) });
      return;
    }

    const projectMatch = path.match(/^\/api\/v1\/knowledge\/projects\/(.+)$/);
    if (projectMatch) {
      const result = getProjectSummary(db, decodeURIComponent(projectMatch[1]));
      if (!result) {
        json(res, { error: "not found" }, 404);
        return;
      }
      json(res, result);
      return;
    }

    // Decisions
    if (path === "/api/v1/knowledge/decisions") {
      const results = searchDecisions(
        db,
        query.query || undefined,
        query.project || undefined,
        query.topic || undefined,
        query.limit ? parseInt(query.limit) : undefined
      );
      json(res, { decisions: results });
      return;
    }

    const decisionMatch = path.match(/^\/api\/v1\/knowledge\/decisions\/(.+)$/);
    if (decisionMatch) {
      const result = getDecision(db, decodeURIComponent(decisionMatch[1]));
      if (!result) {
        json(res, { error: "not found" }, 404);
        return;
      }
      json(res, result);
      return;
    }

    // Patterns
    if (path === "/api/v1/knowledge/patterns") {
      const results = getPatterns(
        db,
        query.category || undefined,
        query.tier || undefined,
        query.status || undefined
      );
      json(res, { patterns: results });
      return;
    }

    const patternMatch = path.match(/^\/api\/v1\/knowledge\/patterns\/(.+)$/);
    if (patternMatch) {
      const result = getPatternDetail(db, decodeURIComponent(patternMatch[1]));
      if (!result) {
        json(res, { error: "not found" }, 404);
        return;
      }
      json(res, result);
      return;
    }

    // Learning rules
    if (path === "/api/v1/knowledge/rules") {
      const approvedOnly = query.approved_only !== "false";
      json(res, { rules: getLearningRules(db, approvedOnly) });
      return;
    }

    // Recent activity
    if (path === "/api/v1/knowledge/recent") {
      if (!query.since) {
        json(res, { error: "since parameter required" }, 400);
        return;
      }
      const results = getRecent(
        db,
        query.since,
        query.limit ? parseInt(query.limit) : undefined
      );
      json(res, results);
      return;
    }

    // Velocity
    if (path === "/api/v1/knowledge/velocity") {
      const results = getVelocity(
        db,
        query.task_type || undefined,
        query.complexity || undefined,
        query.project || undefined,
        query.limit ? parseInt(query.limit) : undefined
      );
      json(res, results);
      return;
    }

    json(res, { error: "not found" }, 404);
  } catch (err) {
    console.error("Knowledge HTTP error:", err);
    json(res, { error: "internal error" }, 500);
  }
});

server.listen(port, "0.0.0.0", () => {
  console.error(`[knowledge-http] Listening on http://0.0.0.0:${port}`);
});
