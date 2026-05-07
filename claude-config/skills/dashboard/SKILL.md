---
name: dashboard
version: 7.0
description: Cross-project status overview (or single-project deep view via cwd detection / explicit name) — pure-read CLI wrapper. Subscription-filtered in multi-project mode; flags --window daily|weekly|monthly|full, --for owner, --status, --format terminal|markdown.
---

# /dashboard

Thin Claude wrapper around `~/agents/dashboard/cli.py`. The Python script
is the single source of truth for behavior; this skill just dispatches.

## Execution

When invoked, run:

```bash
python3 ~/agents/dashboard/cli.py "$@"
```

Pass through every argument unchanged (positional project name, all
`--*` flags, any quoted values). Print the script's stdout verbatim in
your reply; print stderr verbatim too if non-empty. Use the script's
exit code to decide whether the command succeeded — any non-zero is an
error you should surface to the user.

Do **not** re-implement any logic on top of the script. Do **not** parse
or paraphrase the output — give the user the raw text the script
emitted. The point of this wrapper is that Claude burns minimal tokens
and behavior stays identical to the shell-only path.

## When the user could just run the shell command

The script is also runnable directly:

```bash
python3 ~/agents/dashboard/cli.py [args]
# or with the alias in ~/.zshrc:
alias dashboard='python3 ~/agents/dashboard/cli.py'
dashboard
dashboard agents --window weekly
dashboard --format markdown
```

If the user invokes /dashboard and you suspect they'd be better served
running it directly in the shell (tight loops, piping to mail, scripting),
mention the alias once — but only once per session, and never if they
seem to be deliberately using the slash-command form.

## Surface

For the full command surface, run `python3 ~/agents/dashboard/cli.py --help`
(the script prints help verbatim). Summary:

- **Single-project deep view**: `dashboard <name>`, or invoke from cwd
  inside `~/agents/` or `~/projects/<name>/`. Renders frame, actions,
  issues, and decisions.
- **Multi-project overview**: `dashboard` from elsewhere — subscription-
  filtered. Subscriptions live in `~/.claude/dashboard-subscriptions.json`
  and are **authoritative** (no `--all` bypass; missing/empty/all-stale
  → instructive error).
- **Filters**: `--window daily|weekly|monthly|full` (default daily),
  `--for <owner>` (Actions only — Issues/Decisions/Captures stay shared),
  `--status active|paused|blocked|done` (multi-project filter).
- **Format**: `--format terminal` (default ASCII cards) or
  `--format markdown` (parseable digest with stable
  `<!-- dashboard-digest v1 {project_or_multi} {window} {YYYY-MM-DD} -->`
  header for downstream agent consumption — e.g. `/email-digest`).

## Notes

- The script is **pure-read**. Writes to project state belong to other
  surfaces:
  - `action` CLI for ACTIONS.md (auto-commits per #121)
  - `gh issue create/close` and `/orchestrate` for GitHub issues
  - `knowledge/decisions/*.yaml` (hand-edit) for decisions
  - `/project --focus`, hand-edit for project YAML frame
- The script **does not run** the legacy automation
  (`syncBlockers`, `recomputeStatus`, `autoJournalCommits`) that the
  previous MCP-backed /dashboard ran on every call. If those automations
  are still useful, Phase 6B audit (A-011) will decide where they live —
  likely a separate `automation.py` invoked from a hook/cron, not on
  every dashboard render.
- Sources: `knowledge/projects/*.yaml`, `knowledge/decisions/*.yaml`,
  per-project `ACTIONS.md`, `gh issue list` per resolved repo. Inbox
  reads from `knowledge/knowledge.db` (the one knowledge subsystem
  without a YAML form yet).
- Specification of behavior, modes, filters, rendering, and degradation
  rules lives in `~/agents/dashboard/cli.py`'s module docstring + the
  test suite at `~/agents/dashboard/tests/test_cli.py`. If you need to
  change behavior, edit the Python — never re-add logic to this skill.
- This is a single-machine CLI. Cross-device project state is Phase 7
  (see `~/agents/PLAN.md` and `specs/toolchain-consolidation.md`).
