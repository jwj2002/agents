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

## Three failure patterns to actively prevent

These three account for >50% of historical agent failures. Apply proactively.

| Pattern | Trigger | Prevention |
|---|---|---|
| **VERIFICATION_GAP** | Any assumption about code structure | Read the actual file. Never assume. |
| **ENUM_VALUE** (26%) | Fullstack work touching role/status/type fields | Use the backend enum **VALUE** string, not the Python NAME (`"CO-OWNER"` not `"CO_OWNER"`) |
| **COMPONENT_API** (17%) | Reusing an existing React component or hook | Read the source / PropTypes before invoking |

Full pattern detail: `~/.claude/rules/core-patterns.md` and any auto-loaded
`patterns-critical.md`.

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
(`~/.claude/rules/behavioral-evals.md`) is authoritative; the highlights:

- **E01 ENUM_VALUE_MISMATCH** — frontend uses backend enum NAME instead of VALUE
- **E02 COMPONENT_API_MISMATCH** — reused component with wrong props
- **E03 HOOK_DEPENDENCY_ARRAY** — missing/incorrect `useEffect` deps
- **E04 MODEL_WITHOUT_MIGRATION** — SQLAlchemy change with no Alembic migration
- **E05 NULLABLE_MISMATCH** — model nullable doesn't match schema Optional
- **E06 SCHEMA_MODEL_DRIFT** — Pydantic schema fields don't match model
- **E07 MIGRATION_NOT_ADDITIVE** — destructive migration (drop/alter type)
- **E08 MIGRATION_MISSING_INDEX** — FK without index
- **E09 SERVICE_BYPASSES_REPO** — service uses raw `db.execute` instead of repo
- **E10 STALE_DATA_UNHANDLED** — flush without `StaleDataError` catch on versioned models
- **E11 AUTH_DEPENDENCY_MISSING** — endpoint without auth dependency
- **E12 AUDIT_LOG_MISSING** — write endpoint without `AuditService` call
- **E13 MISSING_FK_INDEX** — FK column without `index=True`
- **E14 DOCKER_ROOT_USER** — Dockerfile without `USER` directive
- **E15 SECRETS_IN_CODE** — hardcoded API keys, passwords, tokens

File→eval mapping: `~/.claude/rules/eval-file-mapping.md`.

---

## RBAC

Single-org applications use the permission-check dependency pattern:
`User.role` → `ROLE_PERMISSIONS` dict → `require_permission("resource:action")` dependency.
Every endpoint gets a permission check (E11). Detail: `~/.claude/rules/rbac-pattern.md`.

---

## M365 / Microsoft Graph (this laptop)

This laptop has working Graph credentials for Jason's agent identity
**`jjob@vital-enterprises.com`** (parallel to Paul's `ai-coder@vital-enterprises.com`
and Ryan's `ryan-agent@vitalailabs.com`). The app is scoped via
ApplicationAccessPolicy to that single mailbox — it cannot send-as or read
any other address.

| What | Where |
|---|---|
| Credentials (chmod 600, gitignored) | `~/.claude/m365/agent.json` |
| Send helper | `~/agents/m365/send_mail.py --to … --subject … --body … [--attach …]` |
| Read helper | `~/agents/m365/read_mail.py [--top N] [--from …] [--subject-contains …] [--since …] [--unread-only]` |
| Renderer (markdown → HTML for email body) | `~/agents/m365/render_markdown.py` |
| Token cache | `~/.claude/m365/token-cache.bin` (managed by msal) |

**Always send as `jjob@vital-enterprises.com`** — never override the sender.
On other machines this section may not apply (different identity / different
provider); the credential file's absence at the path above is the signal
that the M365 capability isn't configured on that machine.

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
| `fastapi-layered-pattern.md` (in `templates/`, not `rules/`) | Read by `/scaffold-project` and `/scaffold-module` |
| `rbac-pattern.md` | Auth/permissions code |
| `orchestrate-workflow.md` | `/orchestrate` runs |
| `spec-review-workflow.md` | Specs and `.agents/` paths |
| `spec-self-review.md` | Auto-loads on `specs/**` — the loud pre-commit gate for §3 self-review |
| `spec-schema-collision-check.md` | Auto-loads on `specs/**` + `db/migrations/**` — exhaustive grep for drops/extends |
| `spec-state-machine-truth-table.md` | Auto-loads on `specs/**` — for multi-section state contracts |
| `spec-new-substrate-domain-sweep.md` | Auto-loads on `specs/**` — 5-question domain check for NEW substrates |
| `post-merge-verification.md` | After `/pr --merge` |

---

## Promoting project memory to global rules

When a project-memory file under
`~/.claude/projects/<project>/memory/feedback-*.md` captures a lesson
that's **generally applicable to other projects** (not specific to
that project's domain), promote it to a global rule so every project
inherits it.

**Why this exists.** Project memory files are project-local — working
in `safe174th` you won't see `buddy`'s feedback files. Without
promotion, every project relearns the same lessons. The 2026-06-03
Workspace V1 R1 incident documented this gap: 17 of 21 blockers were
preventable by existing project-local feedback that had never been
promoted.

**Procedure:**

1. **Decide it's promotable.** Cross-project relevance test: would a
   teammate working on an unrelated project benefit from this rule
   without seeing the originating incident? If yes, promote.
2. **Write the new rule** in `~/agents/claude-config/rules/<name>.md`
   with appropriate `paths:` frontmatter for auto-load.
3. **Keep the project-memory file as back-reference.** Add a
   `Companion: ~/.claude/rules/<name>.md` line so future readers
   trace from incident → general rule.
4. **Commit + PR + merge to `~/agents`** following the standard git
   workflow (jwj2002 account per `github-accounts.md`).
5. **Run `~/agents/claude-config/install.sh`** to refresh symlinks
   (no-op if the rule directory was already symlinked; only catches
   first-time symlink + missing-target cases).
6. **For jbox06 (if applicable):** `ssh jbox06 'cd ~/agents && git
   pull --ff-only && ./claude-config/install.sh'`. Without this step,
   VitalAILabs app sessions won't see the new rule.

**What counts as "generally applicable":**
- Workflow discipline (review gates, self-checks, sequencing).
- Cross-stack mistakes (enum collisions, schema drift, fence-post
  errors in distributed systems).
- Tool quirks that bite in any project (`codex` CLI, `gh` CLI, `git`
  edge cases).

**What stays project-local:**
- Domain-specific patterns (e.g., a buddy-only entity-grid lesson).
- Architectural choices recorded for context (resume docs,
  pillar-status logs).
- Operational incident notes specific to that project's infra.

## Anti-patterns to avoid

- Long CLAUDE.md (target <200 lines; this file is the target — the
  promotion-path section above adds ~30 lines, balanced by keeping
  rules in their own files).
- Reaching for a subagent before exhausting CLAUDE.md and skills (Anthropic's recommended order).
- Editing `~/.claude/` directly. Always go through `~/agents/claude-config/`.
- Putting secrets, ephemeral state, or large code patterns in CLAUDE.md.
- Bypassing safety with `--no-verify`, `--force`, or `bypassPermissions` without explicit user approval.
- **Letting project-local lessons stay project-local indefinitely.**
  If a `feedback-*.md` file would help another project, promote it
  per the procedure above.

---

## ~/agents — personal velocity rules

`~/agents` is personal tooling, not a product. Preserve fast iteration:

- **TRIVIAL/SIMPLE changes**: no manifest, no spec, no adversarial review.
- **Major refactors (4+ files, new protocol, new command)**: produce a *lightweight*
  code-reality manifest (`specs/<name>.code-reality.md`) before drafting; aim for
  ≤2 review rounds, not the full spec-review-workflow ceremony.
- Route substantive ~/agents work through `/orchestrate`; ad-hoc fixes via `/quick`.
- All telemetry routes through the same `state_manager` hooks as `~/projects/` — no
  separate recording path needed.
