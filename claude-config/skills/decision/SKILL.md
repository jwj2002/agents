---
name: decision
version: 1.0
description: View, list, create, and update entries in knowledge/decisions/ — pure-CLI wrapper. Per-project decisions; canonical YAML schema with `linked` cross-references; maintains decisions/index.yaml.
---

# /decision

Thin Claude wrapper around `~/agents/decision/cli.py`. The Python script
is the single source of truth for behavior; this skill just dispatches.

## Execution

When invoked, run:

```bash
python3 ~/agents/decision/cli.py "$@"
```

Pass through every argument unchanged (positional ID, all `--*` flags,
quoted values). Print stdout verbatim. Surface non-zero exits as errors.

Do **not** re-implement any logic on top of the script. Do **not** parse
or paraphrase the output — give the user the raw text the script emitted.

## When the user could just run the shell command

The script is also runnable directly:

```bash
python3 ~/agents/decision/cli.py [args]
# or with the alias in ~/.zshrc:
alias decision='python3 ~/agents/decision/cli.py'
decision --list                                            # all decisions, newest first
decision --list --project docketiq                         # filter
decision D-042                                             # render one
decision --new --title "..." --decision "..." \
         --project agents --topic infrastructure           # create
decision D-042 --outcome "Shipped to prod" \
         --add-pr 147                                      # update later
```

If the user invokes `/decision` and you suspect they'd be better served
running it directly, mention the alias once per session — not if they
seem to be deliberately using the slash-command form.

## Surface

- **Read**: `decision <D-NNN>` renders one decision; `--list` renders the
  full table newest-first. `--list --project X` and `--list --topic Y`
  filter.
- **Create**: `--new --title "..." --decision "..."` writes a new
  `D-NNN.yaml` (auto-numbered, max-existing + 1) AND updates
  `decisions/index.yaml` (`by_project.<name>` + `by_topic.<topic>`).
  Project resolves from cwd / picker (same flow as `action`/`project`);
  topic prompts from a known list (auth, database, api, frontend,
  infrastructure, workflow, testing, observability, orchestration,
  philosophy, architecture, export) or accepts free-text via the picker.
- **Update**: positional `D-NNN` plus any of `--outcome "..."`,
  `--add-pattern pat-X`, `--add-issue 148`, `--add-pr 147`,
  `--add-related D-091` (all repeatable). Issue/PR numbers are normalized
  with a leading `#`. Adding a pattern also updates
  `decisions/index.yaml` `by_pattern.<id>`.

## Schema notes

The CLI normalizes legacy D-098-style records (top-level `linked_patterns`,
`linked_issues`, `linked_prs`, `related_decisions`) into the canonical
D-042 nested form (`linked: {patterns, issues, prs, related_decisions}`)
on every write. New decisions always emit the canonical form with
`schema_version: 1`. See `specs/knowledge-surfaces.md` for surface-level
scoping (decisions are per-project; patterns are global).

## Notes

- The script writes the YAML and index but **does not auto-commit**.
  Print suggested git command after writes (consistent with #141 / #143
  precedent). If multi-machine sync becomes a real pain, a follow-up can
  extract action's git plumbing into a shared `lib/git_ops.py`.
- `alternatives:` array is hand-edited for v1; the CLI writes an empty
  list on `--new`. Adding an `--alt "name|why-rejected"` repeatable flag
  is reasonable scope for v2 if it becomes a friction point.
- Behavior, ID assignment, schema-normalization rules, and atomic-write
  semantics are pinned by `~/agents/decision/cli.py`'s module docstring +
  the test suite at `~/agents/decision/tests/test_cli.py`. If you need
  to change behavior, edit the Python — never re-add logic to this skill.
