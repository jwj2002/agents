# Jason's Claude Code Global Config

This file is your top-level orientation for every session. Detailed rules live
in `~/.claude/rules/` and are loaded conditionally — read this first.

---

## Who & where

- **User**: Jason Job (jasonwadejob@gmail.com)
- **Source of truth**: `~/agents/claude-config/` (version-controlled)
- **Deployed**: `~/.claude/` (symlinks from claude-config; see `install.sh`)
- **Sibling repos**: `~/agents/mcp-server/` (vault-metrics MCP), `~/agents/obsidian-agent/`, etc.

If you ever need to change the deployed config, edit `~/agents/claude-config/`
and let `install.sh` handle the symlinks. Don't edit `~/.claude/` directly.

This repo is shared with **Codex**. `AGENTS.md` is shared policy; `CLAUDE.md`
and Codex config are adapters. When changing shared instructions, verify both
surfaces. See `~/agents/docs/CLAUDE-CODEX-COLLABORATION.md`.

---

## Failure patterns to actively prevent

Top clusters from the 2026 failure corpus: **VERIFICATION_GAP** (read the
actual file — assumptions about code/spec/data are the #1 failure) and
**AMBIGUITY_UNRESOLVED** (pick one, document it, flag the alternative). Full
table + provenance: `~/.claude/rules/core-patterns.md` (auto-loaded) and any
auto-loaded `patterns-critical.md`.

---

## Routing: which workflow for which task

Before starting any task, classify it:

| Tier | Files | Signal | Use |
|---|---|---|---|
| TRIVIAL | 1 | Typo, rename, obvious fix | `/quick` |
| SIMPLE | 1–3 | Clear single-subsystem | Plan mode |
| MODERATE | 4–5 | Clear pattern, single subsystem | `/orchestrate` (SIMPLE tier), Codex review recommended |
| COMPLEX | 6+ | Cross-cutting / architectural | `/orchestrate` (COMPLEX tier), Codex review recommended |
| FULLSTACK | any | Backend + frontend | `/orchestrate` with CONTRACT phase |

**Modifiers:** `--parallel` for independent issues, `--resume` for interrupted
workflows, `--discuss` for ambiguous requirements (recommended on COMPLEX/FULLSTACK).

Codex rule: simple work gets one agent; risky work gets two opinions; failed
work gets a different model. Do not use Codex for trivial ceremony.

Full routing logic: `~/.claude/rules/implementation-routing.md`.

---

## Multi-environment routing

Three development modes in active use:

| Mode | Where code lives | How to edit | Git host |
|---|---|---|---|
| Local | `~/projects/<repo>` on laptop | Direct Edit/Write | GitHub |
| jbox06 (VitalAILabs) | `~/app-repos/<repo>` on jbox06 | `ssh jbox06 'cat > … << EOF …'` | Internal GitLab |
| Hybrid | both (rare) | Edit local, sync to jbox06 | GitLab via jbox06 |

Detect mode before writing code. Detail: `~/.claude/rules/dev-environment.md`.

---

## GitHub multi-account

Two accounts; switch before any git/gh work:

| Account | Used for | Email |
|---|---|---|
| `jwj2002` | Personal projects, agents repo | jasonwadejob@gmail.com |
| `jjob-spec` | Maison Financial projects | jason@maisonfinancial.com |

Run `gh auth status` first; switch with `gh auth switch -u <user>` if needed.
Detail: `~/.claude/rules/github-accounts.md`.

GitLab access (jbox06 only): `~/.claude/rules/gitlab-access.md`.

---

## Git workflow essentials

- Canonical process: `~/agents/docs/git-process.md`
- Claude rule adapter: `~/.claude/rules/git-workflow.md`
- Project-local instructions: read `AGENTS.md` first when present.
- **Ship by default.** Agent-owned issues are taken end-to-end — commit, PR,
  validate, squash-merge, sync `main`, prune the branch, post-merge verify,
  close the issue — **without pausing to ask for merge approval.** Stop before
  merge ONLY on a specific agreement ("PR only" / "hold") or a documented stop
  gate. CI-red / unresolved REQUEST_CHANGES / conflicts are "fix then ship",
  not stop gates. Full rule: `~/.claude/rules/git-workflow.md`.
- Completion requires implementation to be wired through its intended
  entrypoint and exercised with evidence, not merely present in files.

Post-merge verification: `~/.claude/rules/post-merge-verification.md`.

---

## Behavioral evals (PROVE phase reference)

E01–E15 are run by PROVE based on changed files. The catalog
`~/.claude/rules/behavioral-evals.md` is authoritative (what/why/how per eval);
`~/.claude/rules/eval-file-mapping.md` selects which evals run for which files.

---

## RBAC

Single-org applications use the permission-check dependency pattern:
`User.role` → `ROLE_PERMISSIONS` dict → `require_permission("resource:action")` dependency.
Every endpoint gets a permission check (E11). Detail: `~/.claude/rules/rbac-pattern.md`.

---

## M365 / Microsoft Graph (this laptop)

This laptop sends/reads mail as agent identity `jjob@vital-enterprises.com` via
Graph, and reads/writes VitalAILabs client documents on SharePoint (same app
reg, `Sites.Selected`). Helpers, credential paths, the "always send as" rule,
and the SharePoint helper: `~/.claude/rules/m365-graph.md` (on-demand).
Credential absence at `~/.claude/m365/agent.json` signals the capability isn't
configured here.

---

## Reference files (load on demand)

| Rule | Loaded for |
|---|---|
| `core-patterns.md` | Always (auto-injected by SessionStart hook) |
| `implementation-routing.md` | Any non-trivial task |
| `dev-environment.md` | Anything touching jbox06 or remote dev |
| `git-workflow.md` | Any commit/branch/PR work |
| `github-accounts.md` / `gitlab-access.md` | Before any push or auth-sensitive op |
| `behavioral-evals.md` + `eval-file-mapping.md` | PROVE phase, code review |
| `code-quality-standards.md` | Auto-loads on code paths — quantified, command-checkable standards (coverage delta, lint, LR-001, evals) |
| `fastapi-layered-pattern.md` (in `templates/`, not `rules/`) | Read by `/scaffold-project` and `/scaffold-module` |
| `rbac-pattern.md` | Auth/permissions code |
| `orchestrate-workflow.md` | `/orchestrate` runs |
| `spec-review-workflow.md` | Specs and `.agents/` paths |
| `spec-self-review.md` | Auto-loads on `specs/**` — the loud pre-commit gate for §3 self-review |
| `spec-schema-collision-check.md` | Auto-loads on `specs/**` + `db/migrations/**` — exhaustive grep for drops/extends |
| `spec-state-machine-truth-table.md` | Auto-loads on `specs/**` — for multi-section state contracts |
| `spec-new-substrate-domain-sweep.md` | Auto-loads on `specs/**` — 5-question domain check for NEW substrates |
| `post-merge-verification.md` | After `/pr --merge` |
| `m365-graph.md` | On-demand — mail + SharePoint client docs via Microsoft Graph |
| `memory-promotion.md` | On-demand — promoting a project lesson to a global rule |

---

## Recalling project memory (active recall)

Project facts live under `~/.claude/projects/<project>/memory/`. SessionStart
auto-injects summaries for all facts + full bodies for top-N (two-pass, 6000-char
budget). Manual recall: `~/agents/bin/memory recall "<keywords>"`. Also:
`memory doctor` (index drift + TTL) and `memory archive [--apply]`.

### Memory Frontmatter Convention (on-touch only)

Canonical fields: `name`, `type` (feedback|user|reference|project), `expires` (YYYY-MM-DD),
`summary` (1-3 sentences; auto-recall uses verbatim, falls back to first sentence),
`durability` (durable|session|handoff|temporary).

`durability` effects: `durable` → resists freshness/size rank penalties, never flagged
stale. `session`/`temporary` → summary-only injection, TTL candidate at 30d. Normalize
on-touch only — no mass migration.

## Promoting project memory to global rules

When a `feedback-*.md` lesson is **generally applicable**, promote it to a
global rule. Full procedure: `~/.claude/rules/memory-promotion.md` (on-demand).

## Anti-patterns to avoid

- Long CLAUDE.md (target <200 lines; `claude-config/scripts/check-context-budgets.py`).
- Reaching for a subagent before exhausting CLAUDE.md and skills.
- Editing `~/.claude/` directly. Always go through `~/agents/claude-config/`.
- Putting secrets, ephemeral state, or large code patterns in CLAUDE.md.
- Bypassing safety with `--no-verify`, `--force`, or `bypassPermissions`.
- **Letting project-local lessons stay project-local.** Promote per the procedure above.

---

## ~/agents — personal velocity rules

`~/agents` is personal tooling. Preserve fast iteration:

- **TRIVIAL/SIMPLE**: no manifest, no spec, no adversarial review.
- **Major refactors (4+ files)**: lightweight code-reality manifest before drafting.
- Route substantive work through `/orchestrate`; ad-hoc fixes via `/quick`.
- Telemetry routes through `state_manager` hooks — no separate recording path.
