---
name: action
version: 2.0
description: Create, update, and list actions in a project's ACTIONS.md. Wraps mutations to enforce table format, auto-stamp Closed date, auto-move closed rows to Recently Closed, and auto-bump Next ID. Works on any owner — local file is fully editable.
---

# /action

Thin Claude wrapper around `~/agents/action/cli.py`. The Python script is
the single source of truth for behavior; this skill just dispatches.

## Execution

When invoked, run:

```bash
python3 /home/jjob/agents/action/cli.py "$@"
```

Pass through every argument unchanged (including the positional ID, the
`--*` flags, and any quoted values). Print the script's stdout verbatim
in your reply; print stderr verbatim too if non-empty. Use the script's
exit code to decide whether the command succeeded — any non-zero is an
error you should surface to the user.

Do **not** re-implement any logic on top of the script. Do **not** parse
or paraphrase the output — give the user the raw text the script
emitted. The point of this wrapper is that Claude burns minimal tokens
and behavior stays identical to the shell-only path.

## When the user could just run the shell command

The script is also runnable directly as:

```bash
python3 ~/agents/action/cli.py [args]
# or with an alias in ~/.bashrc:
alias action='python3 ~/agents/action/cli.py'
action --list
```

If the user invokes /action and you suspect they'd be better served
running it directly in the shell (for tight loops, scripting, etc.),
mention the alias once — but only once per session, and never if they
seem to be deliberately using the slash-command form.

## Surface

For the full command surface, run `/action --help` (the script prints
the help text verbatim). Summary:

- Read: `--list`, `--list --status <s>`, `--list --owner <name>`,
  `--list --closed`, `--list --all`, `A-NNN` (show one)
- Update: `A-NNN --status <s>`, `A-NNN --note "..."`,
  `A-NNN --owner <name>`, `A-NNN --reopen`
- Create: `--new "..." --owner <name> [--status <s>] [--note "..."] [--src "..."]`
- Project resolution: `--project <name>`, otherwise inferred from cwd
  (`~/agents → agents`, `~/projects/X → X`).

## Notes

- The script mutates files in place. There is no transaction model; if
  two processes write concurrently the last writer wins.
- The script does not update the Knowledge MCP. Project tracker
  (focus / next steps / blockers) lives in `/project`.
- Specification of the table format and migration rules lives in the
  script's docstring + the test cases. If you need to change behavior,
  edit `~/agents/action/cli.py` — never re-add behavior to this skill.
