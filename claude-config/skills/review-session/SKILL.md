---
name: review-session
version: 2.0
description: Review pending session activity and apply per-project focus updates — pure-CLI wrapper. Reads ~/.claude/pending_focus_reviews.json; delegates focus writes to the `project` CLI.
---

# /review-session

Thin Claude wrapper around `~/agents/review_session/cli.py`. The Python
script is the single source of truth for behavior; this skill just
dispatches.

## Execution

When invoked, run:

```bash
python3 ~/agents/review_session/cli.py "$@"
```

Pass through every argument unchanged. Print the script's stdout verbatim;
print stderr verbatim if non-empty. Use the script's exit code to decide
success — any non-zero is an error you should surface to the user.

Do **not** re-implement any logic on top of the script. Do **not** parse
or paraphrase the output — give the user the raw text the script emitted.

## When the user could just run the shell command

The script is also runnable directly:

```bash
python3 ~/agents/review_session/cli.py [args]
# or with the alias in ~/.zshrc:
alias review-session='python3 ~/agents/review_session/cli.py'
review-session --list           # show pending count + per-project commits
review-session                  # interactive review of all pending
review-session buddy            # only review one project
```

If the user invokes `/review-session` and you suspect they'd be better
served running it directly, mention the alias once per session — not if
they seem to be deliberately using the slash-command form.

## Surface

- **`--list`**: print pending summary; no prompts.
- **No args**: iterate every pending project. Per project, render the
  commit list + current focus and prompt `[a] apply / [s] skip / [q] quit`.
  On `apply`, prompt for the new focus text and shell out to the `project`
  CLI to write it. Processed entries are removed from the pending file
  (atomic rewrite). When the file becomes empty, it is deleted.
- **`<project>`**: only review one specific pending project.
- **`--no-prompt`**: non-interactive; skip any project that needs input
  (intended for tests / scripts).

## Behavior change vs. the v1 skill

The v1 skill had Claude synthesize a proposed focus from the commit
messages. The v2 CLI does **not** auto-propose — the user types the new
focus directly based on the rendered commit list. This matches the
action / dashboard / project pattern (CLIs don't do LLM). If a drafted
default becomes useful again, it would belong in this wrapper layer (the
wrapper can read the commits, propose focus text, and invoke the CLI
with the draft pre-filled), not in the Python script.

## Notes

- Focus writes shell out to `python3 ~/agents/project/cli.py <name>
  --focus "..." --no-prompt`. The Knowledge MCP server retired in
  Phase 6C (#146); this skill no longer calls any MCP tools.
- The pending file at `~/.claude/pending_focus_reviews.json` is written
  by the session-end hook; this CLI consumes and clears it.
- Behavior, prompt copy, file-lifecycle semantics, and atomic-write
  safety are pinned by `~/agents/review_session/cli.py`'s module
  docstring + the test suite at
  `~/agents/review_session/tests/test_cli.py`. If you need to change
  behavior, edit the Python — never re-add logic to this skill.

## Integration with /dashboard

`/dashboard` shows a top-of-output nudge when
`~/.claude/pending_focus_reviews.json` exists with non-empty entries:

```
📝 2 projects have session activity to review — run /review-session
```

This is a passive notice, not a blocker.
