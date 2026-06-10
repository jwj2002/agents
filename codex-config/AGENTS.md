# Jason's Codex Global Guidance

This file is the shared global instruction surface for Codex. It is installed
to `~/.codex/AGENTS.md` by `codex-config/install.sh`.

How Codex and Claude share this repo (AGENTS.md is shared policy; CLI-first
shared tooling; per-agent capabilities documented): see
`docs/CLAUDE-CODEX-COLLABORATION.md`.

## Operating Role

Use Codex as a pragmatic implementation and adversarial review partner.
Default to editing code when the user asks for a fix, but preserve user work
and verify behavior before declaring completion.

## Quality Bar

- Read the actual files before making assumptions about APIs, enums, schemas,
  or component props.
- Prefer small, intentional diffs over broad rewrites.
- Keep one logical change per branch or pull request.
- Run the narrowest useful checks first, then the full relevant gate before
  handoff.
- Treat tool failures, skipped tests, and missing dependencies as explicit
  risks, not success.

## Ship by Default

Take issue work end-to-end, including the merge — do not pause to ask for merge
approval. The terminal state of a task is a merged PR: commit → push → PR →
validate/review → squash-merge → prune branch → sync main → close the issue.
Stop before merge ONLY when the user gave a specific instruction for that task
("PR only", "hold") or the issue/spec documents a stop gate (human sign-off,
release coordination, an irreversible/destructive production operation). CI red,
unresolved change requests, and merge conflicts are "fix, then ship" — not
reasons to stop. High-risk work (auth, payments, migrations, data-loss, secrets)
still ships, but runs adversarial review before merge.

## High-Frequency Failure Checks

- `VERIFICATION_GAP`: Do not infer code structure from memory. Inspect source.
- `ENUM_VALUE`: For fullstack enum, status, or role fields, use backend enum
  values, not Python or TypeScript names.
- `COMPONENT_API`: Before reusing a UI component or hook, read its source,
  types, or PropTypes.
- `MODEL_WITHOUT_MIGRATION`: SQLAlchemy or persistence-model changes require a
  migration or an explicit reason.
- `AUTH_DEPENDENCY_MISSING`: New write endpoints need auth and permission
  checks.
- `SECRETS_IN_CODE`: Never read, print, edit, or commit secrets or `.env`
  files.

## Verification Gates

- Backend: `cd backend && ruff check . && pytest -q`
- Frontend: `cd frontend && npm run lint && npm run build`
- Config/tooling: run the repository-specific test or validation script when
  present.
- If a gate cannot run, state exactly why and what remains unverified.

## Claude And Codex Workflow

- Claude is currently the preferred conductor for `/orchestrate`, issue
  routing, and Claude-specific artifact generation.
- Codex is preferred for direct implementation, local test/debug loops, and
  adversarial reviews.
- For complex work, use issue artifacts or plans as shared context. Keep
  Codex findings tied to concrete changed code, tests, contracts, or security
  risk.
- Feed recurring Codex review findings back into shared instructions,
  project `AGENTS.md`, or Claude learning rules as appropriate.

## Active Memory Recall

Before non-trivial implementation, review, or orchestration-adjacent work in a
project with memory, run:

```bash
~/agents/bin/memory recall "<issue title + subsystem terms>" --compact --limit 8
```

Treat recalled facts as prior context, not truth. Read any relevant fact body,
then verify it against current source, specs, and tests before acting.

## Git Safety

- Never use `git reset --hard`, `git checkout -- <file>`, force-push, or
  destructive cleanup unless explicitly requested.
- Do not bypass hooks with `--no-verify` unless explicitly authorized.
- Before commit or PR work, check branch and status.
- For projects bootstrapped by `~/agents`, read project `AGENTS.md` and follow
  the standardized git process in `~/agents/docs/git-process.md`.
- Before agent-owned edits, run `~/agents/bin/agent-git preflight` when it is
  available and treat reported errors as stop gates.
- Before opening or merging an agent-owned PR, run
  `~/agents/bin/agent-git readiness` when it is available.
- Prefer `~/agents/bin/agent-git ship` for end-to-end issue shipping when it is
  available; use `--dry-run` first for high-risk changes.
- Use `~/agents/bin/agent-git cleanup` after manual merges when the ship helper
  was not used.
- For parallel work in one repo, create isolated worktrees with
  `~/agents/bin/agent-git worktree add` and serialize same-file edits.
- Agent-owned issues default to shipped work: commit, PR, validate, squash
  merge, sync `main`, prune stale refs, delete the merged branch, and close or
  update the linked issue unless a documented stop gate applies.
- Do not call work complete until it is implemented, wired through the intended
  entrypoint, exercised, observed with evidence, documented when operationally
  meaningful, and shipped or explicitly blocked.
