# Jason's Codex Global Guidance

This file is the shared global instruction surface for Codex. It is installed
to `~/.codex/AGENTS.md` by `codex-config/install.sh`.

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

## Git Safety

- Never use `git reset --hard`, `git checkout -- <file>`, force-push, or
  destructive cleanup unless explicitly requested.
- Do not bypass hooks with `--no-verify` unless explicitly authorized.
- Before commit or PR work, check branch and status.
- For projects bootstrapped by `~/agents`, read project `AGENTS.md` and follow
  the standardized git process in `~/agents/docs/git-process.md`.
- Agent-owned issues default to shipped work: commit, PR, validate, squash
  merge, sync `main`, prune stale refs, delete the merged branch, and close or
  update the linked issue unless a documented stop gate applies.
- Do not call work complete until it is implemented, wired through the intended
  entrypoint, exercised, observed with evidence, documented when operationally
  meaningful, and shipped or explicitly blocked.
