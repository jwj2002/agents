---
type: base-agent
version: 4.1
purpose: Shared behaviors inherited by all agents
---

# Base Agent Behaviors

All agents inherit these behaviors. Read this FIRST before your agent-specific instructions.

---

## 1. Pre-Flight: Load Learned Patterns (TIERED)

**BEFORE investigating or planning**, load accumulated knowledge.

**Preferred — MCP tools** (vault-metrics MCP). Always use the `_v1` suffix (versioned alias); unversioned aliases are deprecated.

```
failure_patterns_v1()              # structured failure patterns w/ frequency
agent_metrics_v1(period="30d")     # success rates by complexity/stack
```

**Fallback — files** (if MCP unavailable):

```bash
cat .claude/memory/patterns-critical.md   # always (~50 lines, covers 89% of failures)
cat .claude/memory/patterns-full.md       # COMPLEX issues / unfamiliar patterns only
```

Apply relevant patterns to your task.

---

## 2. Pre-Flight: Check Similar Past Work

```bash
# Find similar past artifacts (adjust keywords)
grep -l "KEYWORD" .agents/outputs/*.md 2>/dev/null | head -3
```

If found, read the artifact to learn from past approaches. Note what worked and what caused issues.

---

## 3. Efficiency Rules

- **Reference, don't re-quote.** Use `See backend/accounts/services.py:45-67` instead of pasting code.
- **Single source of truth.** Acceptance criteria defined ONCE (in MAP-PLAN or PLAN). Other agents reference, don't duplicate.

### Target Lengths

| Agent | Target | Max |
|-------|--------|-----|
| MAP | 150 | 200 |
| MAP-PLAN | 400 | 500 |
| PLAN | 400 | 500 |
| TEST-PLANNER | 250 | 350 |
| CONTRACT | 200 | 300 |
| PLAN-CHECK | 80 | 120 |
| PATCH | 300 | 400 |
| PROVE | 250 | 350 |

Before submitting, run `wc -l < .agents/outputs/$ARTIFACT_NAME`. If over max: **STOP and compress** before submitting. Between target and max: submit with a note.

**Compression order**: (1) replace code quotes with line refs, (2) reference acceptance criteria instead of re-stating, (3) consolidate duplicate sections, (4) drop appendices / "Future Enhancements", (5) report exceptions only (failures, not successes).

---

## 4. Artifact Naming

Pattern: `{agent}-{issue}-{mmddyy}.md` written to `.agents/outputs/`. Set `ISSUE_NUMBER`, `RUN_DATE=$(date +%m%d%y)` at start of run. Full spec: `~/.claude/rules/orchestrate-workflow.md`.

---

## 5. Common Verification Commands

See `~/.claude/snippets/verify-commands.md` for the canonical backend/frontend/scope verification command catalog.

---

## 6. Constraint Enforcement

Git / branch / PR constraints live in `~/.claude/rules/git-workflow.md` (auto-loaded). This section covers only artifact-layer constraints. Before any file operation, also check `.claude/rules.md` for project-specific rules.

**Forbidden actions** (always blocked): create top-level directories, move `backend/` / `frontend/` / `.claude/`, create `backend/src/`, modify files on `main`, push or commit on `production` (unless user explicitly requests).

---

## 7. AGENT_RETURN Directive

Every agent MUST end output with:

```markdown
AGENT_RETURN: {artifact-filename}
```

Example:
```markdown
AGENT_RETURN: map-184-010325.md
```

This signals successful completion to the orchestrator.

---

## 8. High-Frequency Failure Prevention

Canonical definitions: `~/.claude/rules/core-patterns.md` (auto-loaded).
Verification grep snippets for ENUM_VALUE, COMPONENT_API, MULTI_MODEL: see `~/.claude/snippets/verify-commands.md` ("Pattern Spot-Checks").

---

## 9. Artifact Validation (MANDATORY)

Before starting work, verify predecessor artifacts exist via `ls .agents/outputs/<pattern>-{issue}-*.md`. **STOP and report** `"BLOCKED: Required artifact {name} not found for issue #{issue}"` if missing.

| Agent | Required Predecessor(s) |
|-------|-------------------------|
| MAP, MAP-PLAN | none (first agent) |
| PLAN | MAP |
| TEST-PLANNER | MAP or MAP-PLAN |
| CONTRACT | PLAN or MAP-PLAN |
| PLAN-CHECK | PLAN or MAP-PLAN; + CONTRACT if fullstack |
| PATCH | PLAN or MAP-PLAN; + CONTRACT if fullstack; + PLAN-CHECK |
| PROVE | PATCH |

---

## 10. Root Cause Classification (Canonical Enum)

When recording failures, use ONLY these root cause codes:

| Code | Description |
|------|-------------|
| `ENUM_VALUE` | Used enum NAME instead of VALUE |
| `COMPONENT_API` | Wrong props/hook usage |
| `MULTI_MODEL` | Forgot model relationship |
| `API_MISMATCH` | Frontend/backend contract violation |
| `ACCESS_CONTROL` | Missing/wrong permission check |
| `MISSING_TEST` | Untested code path |
| `SQLITE_COMPAT` | PostgreSQL-only feature used |
| `STRUCTURE_VIOLATION` | Violated rules.md constraints |
| `SCOPE_CREEP` | Beyond issue scope |
| `VERIFICATION_GAP` | Assumptions not verified by reading code |
| `OTHER` | Document specifics in `details` field |

---

## 11. Canonical metrics.jsonl Schema

Required fields per record:

```json
{
  "issue": 184, "date": "2026-02-06",
  "status": "PASS | BLOCKED",
  "complexity": "TRIVIAL | SIMPLE | COMPLEX",
  "stack": "backend | frontend | fullstack",
  "agents_run": ["MAP-PLAN", "PATCH", "PROVE"],
  "agent_versions": {"map-plan": "1.0", "patch": "1.0", "prove": "1.0"},
  "root_cause": null, "blocking_agent": null,
  "duration_minutes": 15
}
```

Optional: `recovery_attempts`, `notes`.

---

## 12. Canonical failures.jsonl Schema

Required fields per record:

```json
{
  "issue": 184, "date": "2026-02-06",
  "agent": "PATCH", "root_cause": "ENUM_VALUE",
  "details": "Frontend used CO_OWNER instead of CO-OWNER",
  "fix": "Changed string literal to match backend enum VALUE",
  "prevention": "MAP should document enum VALUES explicitly",
  "files": ["frontend/src/components/MemberForm.jsx"]
}
```

Optional: `severity`, `recovery_minutes`.

---

## 13. Outcome Recording (PROVE Agent Only)

After verification, append a JSON record matching the schemas in §11 and §12.

- **PASS**: append metrics record (status:`PASS`, root_cause:`null`) to `.claude/memory/metrics.jsonl`
- **BLOCKED**: append failure record to `.claude/memory/failures.jsonl` AND metrics record (status:`BLOCKED`, root_cause:`<code>`, blocking_agent:`PROVE`) to `.claude/memory/metrics.jsonl`

Use shell `echo '<json>' >> <file>` with substituted variables. See PROVE agent for full append commands.

---

## 14. Agent Versioning

All agents include `version: X.Y` in YAML frontmatter. Minor (1.0→1.1) for pattern additions / wording; major (1.0→2.0) for restructure / new sections / workflow changes. Include current versions in the `agent_versions` field of each metrics record (see §11) so `/metrics` can correlate success rates with versions.

---

## 15. Escalation Policy

When BLOCKED (waiting on user, ambiguous requirement, missing access):

| Duration | Action |
|----------|--------|
| < 2 min | Wait for user input |
| 2-5 min | Proceed with safest assumption, tag with `[ASSUMED]` in code/artifact |
| > 5 min | STOP, report assumption + what needs human verification |

**Hard escalation (STOP immediately, no assumptions)**: complexity misclassified (SIMPLE actually COMPLEX), constraint violation required, security-sensitive ambiguous scope, same approach failed twice with same root cause.

PROVE flags any `[ASSUMED]` tags for human review — document each assumption (what / why / safest alternative).

**Two-failure rule**: same approach fails twice on the same issue with the same root cause → STOP, escalate to user or delegate to Codex (`/codex:rescue`).

---

## 16. Anti-Pattern Self-Check

Before each phase, name any of these you're exhibiting and course-correct.

| Anti-Pattern | Signal → Correction |
|-------------|----------------------|
| **Kitchen Sink** | Fixing unrelated issues → revert scope; file extras separately |
| **Correcting Over and Over** | Same fix applied 3+ times → approach is wrong, try a different strategy |
| **Infinite Exploration** | Read 15+ files, no plan → stop, write a hypothesis, verify targeted files only |
| **Trust Then Verify Gap** | Assuming code works because it looks right → run it (`ruff`, `pytest`, `npm run build`) |
| **Architectural Astronautics** | Abstractions for hypothetical future needs → delete; build for today's requirement |
| **Flip-Flop** | Implement A → revert → implement B → revert → … → stop, validate with data first |

---

## 17. Runbook Check

On any error, check `cat .claude/memory/runbooks.md 2>/dev/null` BEFORE investigating from scratch. If the error matches a runbook entry, apply the documented fix directly — don't re-diagnose known problems.

---

## 18. Failure Context Awareness

When spawned with a `## Prior Failure` block in your prompt — **highest priority context** (a prior PATCH already failed on this exact issue):

1. Read root cause and prevention fields carefully
2. Apply the prevention recommendation BEFORE starting work
3. Explicitly verify the prior failure point is addressed
4. Note in artifact: `Prior failure (ROOT_CAUSE) addressed by: [action taken]`

---

## 19. Swarm-Aware Behavior

When spawned as a scoped sub-task (e.g., PATCH-backend, PATCH-frontend, PROVE-backend):

- **Respect SCOPE**: only touch files in your designated scope (backend/ or frontend/)
- **CONTRACT is the boundary**: parallel fullstack PATCH implements both sides against CONTRACT
- **Scoped artifacts**: name as `{agent}-{scope}-{issue}-{mmddyy}.md` (e.g., `patch-backend-184-020826.md`)
- **No cross-scope changes**: discovered need outside scope → document under "Cross-Scope Dependencies", do NOT make the change
- **Report conflicts**: file appearing in both scopes → flag immediately in artifact
