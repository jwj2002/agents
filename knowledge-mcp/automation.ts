/**
 * Phase 4 automation — auto-sync blockers, auto-transition status, auto-journal commits.
 *
 * All functions are idempotent and safe to call on every /dashboard invocation.
 * They read from Flotilla API (http://localhost:9000) and update knowledge.db.
 */

import type Database from "better-sqlite3";

const FLOTILLA_URL = process.env.FLOTILLA_URL || "http://localhost:9000";
const AUTO_PREFIX = "[auto]";

async function fetchWithTimeout(url: string, timeoutMs = 2000): Promise<any | null> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);
    const r = await fetch(url, { signal: controller.signal });
    clearTimeout(timeout);
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  }
}

function parseJsonArray(raw: string | null): string[] {
  if (!raw) return [];
  try { return JSON.parse(raw); } catch { return []; }
}

function nowIso(): string {
  return new Date().toISOString().replace("T", " ").slice(0, 19) + "Z";
}

/**
 * Sync escalated Flotilla work items into project_tracker.blockers with [auto] prefix.
 * Removes [auto] blockers whose escalations have been resolved.
 * Preserves manual (non-[auto]) blockers.
 */
export async function syncBlockers(db: Database.Database): Promise<void> {
  const projects = await fetchWithTimeout(`${FLOTILLA_URL}/api/v1/projects`);
  if (!projects) return; // Flotilla down, skip

  for (const p of projects.projects || []) {
    const work = await fetchWithTimeout(`${FLOTILLA_URL}/api/v1/projects/${p.id}/work`);
    if (!work) continue;

    const escalated = (work.items || []).filter((i: any) => i.status === "escalated");
    const autoBlockers = escalated.map((i: any) =>
      `${AUTO_PREFIX} #${i.issue_number} escalated: ${i.escalation_reason || "no reason"}`
    );

    // Get current blockers, preserve manual ones, replace auto ones
    const current = db.prepare("SELECT blockers FROM project_tracker WHERE project = @project").get({ project: p.name }) as any;
    if (!current) continue; // Project not tracked in knowledge

    const currentList = parseJsonArray(current.blockers);
    const manual = currentList.filter(b => !b.startsWith(AUTO_PREFIX));
    const merged = [...manual, ...autoBlockers];

    // Only update if changed
    const mergedJson = JSON.stringify(merged);
    if (mergedJson === (current.blockers || "[]")) continue;

    db.prepare("UPDATE project_tracker SET blockers = @blockers, updated_at = @now WHERE project = @project")
      .run({ project: p.name, blockers: mergedJson, now: nowIso() });
  }
}

/**
 * Auto-transition project status based on activity signals.
 * - Has [auto] or manual blockers → blocked
 * - Activity within 7d → active
 * - No activity >14d → paused
 * - Otherwise: keep current
 *
 * Respects manual_status_override flag.
 */
export async function recomputeStatus(db: Database.Database): Promise<void> {
  const flotillaData = await fetchWithTimeout(`${FLOTILLA_URL}/api/v1/projects`);
  const flotillaMap = new Map<string, any>();
  if (flotillaData) {
    for (const p of flotillaData.projects || []) {
      flotillaMap.set(p.name.toLowerCase(), p);
    }
  }

  const trackers = db.prepare("SELECT project, status, blockers, updated_at, manual_status_override FROM project_tracker").all() as any[];
  const now = Date.now();
  const day = 24 * 60 * 60 * 1000;

  for (const t of trackers) {
    if (t.manual_status_override) continue;

    const blockers = parseJsonArray(t.blockers);
    const flotilla = flotillaMap.get(t.project.toLowerCase());
    const lastCommit = flotilla?.last_commit_at ? Date.parse(flotilla.last_commit_at) : 0;
    const lastUpdate = t.updated_at ? Date.parse(t.updated_at.replace(" ", "T")) : 0;
    const lastActivity = Math.max(lastCommit, lastUpdate);
    const ageDays = lastActivity ? (now - lastActivity) / day : 999;

    let newStatus = t.status;
    if (blockers.length > 0) newStatus = "blocked";
    else if (ageDays <= 7) newStatus = "active";
    else if (ageDays >= 14) newStatus = "paused";

    if (newStatus !== t.status) {
      db.prepare("UPDATE project_tracker SET status = @status WHERE project = @project")
        .run({ status: newStatus, project: t.project });
      db.prepare(
        "INSERT INTO journal (project, entry, entry_type, created_at) VALUES (@project, @entry, 'status_change', @now)"
      ).run({
        project: t.project,
        entry: `Status auto-transitioned: ${t.status} → ${newStatus}`,
        now: nowIso(),
      });
    }
  }
}

/**
 * Auto-journal recent commits from Flotilla's GitHub sync.
 * Uses last_commit_message/last_commit_at from /projects endpoint.
 * Dedupes by commit message+date (since sha not exposed).
 *
 * TODO: When Flotilla exposes recent_commits in /projects/{id}, use full history
 * and dedupe by sha.
 */
export async function autoJournalCommits(db: Database.Database): Promise<void> {
  const projects = await fetchWithTimeout(`${FLOTILLA_URL}/api/v1/projects`);
  if (!projects) return;

  for (const p of projects.projects || []) {
    if (!p.last_commit_message || !p.last_commit_at) continue;

    // Only journal if project is tracked in knowledge
    const tracked = db.prepare("SELECT 1 FROM project_tracker WHERE project = @project").get({ project: p.name });
    if (!tracked) continue;

    // Dedupe key: message + date (stable identifier since no sha exposed)
    const dedupeKey = `${p.last_commit_at}|${p.last_commit_message}`.slice(0, 200);
    const exists = db.prepare("SELECT 1 FROM journal WHERE commit_sha = @key AND project = @project")
      .get({ key: dedupeKey, project: p.name });
    if (exists) continue;

    const created = p.last_commit_at.replace("T", " ").replace("+00:00", "Z");
    db.prepare(
      "INSERT INTO journal (project, entry, entry_type, commit_sha, created_at) VALUES (@project, @entry, 'commit', @key, @created)"
    ).run({
      project: p.name,
      entry: p.last_commit_message,
      key: dedupeKey,
      created,
    });
  }
}

/**
 * Run all automation tasks. Called from get_dashboard so it runs on every dashboard view.
 * All errors are swallowed — automation is best-effort.
 */
export async function runAutomation(db: Database.Database): Promise<void> {
  try { await syncBlockers(db); } catch (e) { console.error("syncBlockers:", e); }
  try { await recomputeStatus(db); } catch (e) { console.error("recomputeStatus:", e); }
  try { await autoJournalCommits(db); } catch (e) { console.error("autoJournalCommits:", e); }
}
