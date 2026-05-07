---
name: project
version: 2.0
description: View or update a project's tracker YAML — pure-CLI wrapper. Reads/writes ~/agents/knowledge/projects/<name>.yaml directly; no MCP. Subscribe/unsubscribe writes ~/.claude/dashboard-subscriptions.json.
---

# /project

Thin Claude wrapper around `~/agents/project/cli.py`. The Python script
is the single source of truth for behavior; this skill just dispatches.

## Execution

When invoked, run:

```bash
python3 ~/agents/project/cli.py "$@"
```

Pass through every argument unchanged (positional name, all `--*` flags,
quoted values). Print the script's stdout verbatim in your reply; print
stderr verbatim too if non-empty. Use the script's exit code to decide
whether the command succeeded — any non-zero is an error you should
surface to the user.

Do **not** re-implement any logic on top of the script. Do **not** parse
or paraphrase the output — give the user the raw text the script
emitted.

## When the user could just run the shell command

The script is also runnable directly:

```bash
python3 ~/agents/project/cli.py [args]
# or with the alias in ~/.zshrc:
alias project='python3 ~/agents/project/cli.py'
project flotilla                              # view
project flotilla --focus "Phase 4 polish"     # set focus
project flotilla --next "Add E2E tests"       # add next step
```

If the user invokes `/project` and you suspect they'd be better served
running it directly, mention the alias once per session — not if they
seem to be deliberately using the slash-command form.

## Surface

For the full command surface, run `python3 ~/agents/project/cli.py --help`.
Summary:

- **Read**: `project <name>` (or invoke from inside `~/agents/` /
  `~/projects/<name>/` for cwd-detect). Renders status, focus, blockers,
  open questions, next steps.
- **Set fields**: `--focus "..."`, `--status active|paused|blocked|done`.
- **Manage lists**:
  - `--next "..."` add / `--done "..."` remove (next_steps; remove by exact-or-substring match)
  - `--blocker "..."` add / `--unblock "..."` remove (blockers)
  - `--question "..."` add / `--unquestion "..."` remove (open_questions)
- **Subscribe (machine-local)**: `--subscribe` / `--unsubscribe` write
  `~/.claude/dashboard-subscriptions.json`. Subscriptions are
  authoritative for `/dashboard` multi-project mode (per #130).
- **Auto-register**: explicit name + matching local repo dir → auto-creates
  `knowledge/projects/<name>.yaml` with sane defaults and subscribes this
  machine.

## Notes

- The script writes the YAML; **commit and push manually** (it prints
  the suggested git command). Auto-commit was deliberately omitted in v1
  — project YAML mutations are infrequent vs. ACTIONS.md and the user
  was happy committing manually. If multi-machine sync becomes a real
  pain, a follow-up can extract action's git plumbing into a shared
  `lib/git_ops.py` and wire both CLIs to it.
- Reads/writes hit `knowledge/projects/<name>.yaml` and (for
  subscriptions) `~/.claude/dashboard-subscriptions.json` directly.
  The Knowledge MCP server retired in Phase 6C (#146); this skill no
  longer calls any MCP tools.
- Specification of behavior, modes, list-removal semantics, and YAML
  round-trip safety lives in `~/agents/project/cli.py`'s module
  docstring + the test suite at `~/agents/project/tests/test_cli.py`.
  If you need to change behavior, edit the Python — never re-add logic
  to this skill.
