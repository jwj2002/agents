# `cap` — quick action capture for project `ACTIONS.md` files

A small Python CLI that appends action items to a project's `ACTIONS.md`.
Deterministic, instant, offline. No AI, no database, no daemon.

This is **layer 1** of a layered capture system. See "Out of scope" below
for what comes next.

## Install

```bash
echo 'export PATH="$HOME/agents/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Verify: `which cap` should print `~/agents/bin/cap`.

## Usage

```bash
cap "Re-check the training video link"           # one action, current project
cap "Fix bug X" "Add test Y" "Update docs"       # N actions
echo -e "thing 1\nthing 2" | cap                 # stdin, one per line
cap --owner Laura "Search SharePoint videos"     # explicit owner
cap --src M1 "..."                               # explicit source ref
cap --project sweetprocess "..."                 # target a specific project
cap -p sweetprocess "..."                        # short form
```

On success: prints assigned IDs (`A-011`, etc.), one per line. Nothing else.
On error: writes to stderr, exits non-zero.

## Project detection

In order:

1. `--project NAME` (or `-p NAME`) — resolves to `~/projects/<name>/`.
   Special case: `--project agents` → `~/agents/`.
2. Otherwise, from cwd:
   - First, `git rev-parse --show-toplevel`. If cwd is in a git repo,
     that's the project root.
   - Else, walk up looking for `ACTIONS.md` or `CLAUDE.md`.
3. If neither resolves a project, `cap` errors out. There is no inbox
   fallback in v1.

If the resolved project has no `ACTIONS.md` yet, `cap` creates one from a
template matching the canonical schema (mirroring
`~/projects/sweetprocess/ACTIONS.md`).

## Schema

8-column, mirrored from `~/projects/sweetprocess/ACTIONS.md`:

```
| ID    | Issue | Action | Owner | Status | Opened       | Src   | Notes |
|-------|-------|--------|-------|--------|--------------|-------|-------|
| A-NNN |       | <text> | Jason | open   | <YYYY-MM-DD> | <src> |       |
```

Defaults: owner=`Jason`, opened=today, status=`open`, Issue/Src/Notes blank
unless flags are passed.

The **Issue** column is left blank by `cap`. It's reserved for the
`gh issue create` workflow you may run separately (see sweetprocess) — a
v2 task may handle that integration. `cap` itself stays offline.

The `Next ID: **A-NNN**` line at the bottom is incremented after each
capture. If your file augments the line with ` · Next issue: **#N**` (as
sweetprocess does), `cap` preserves that trailing token unchanged.

Pipes (`|`) in action text are escaped as `\|`. Newlines are flattened to
spaces (markdown rows must be one line).

## Atomicity

Writes go through a temp file in the same directory, then `os.replace`
swaps atomically. A `kill -9` mid-run leaves `ACTIONS.md` intact (a stray
`ACTIONS.md.*.tmp` may remain — safe to delete).

## Tests

```bash
cd ~/agents/bin && python3 -m pytest tests/
```

## Out of scope (future layers)

This is v1. Built later, in roughly this order:

- **MCP bridge to `/dashboard`** — a new tool like
  `mcp__knowledge__get_actions(project)` that reads `ACTIONS.md` files at
  query time so cross-project action rollup shows up in the dashboard.
  `ACTIONS.md` stays canonical; the DB caches nothing.
- **Other capture surfaces** — iOS Shortcut, Apple Notes, voice, email →
  all eventually write into `ACTIONS.md` (or a shared inbox).
- **`-e` editor mode** — open `$EDITOR` with a template and parse rows.
- **TODO comment scanner** — pull `TODO:` markers out of code into the
  appropriate `ACTIONS.md`.

## Relationship to `/capture` and `/inbox`

The `/capture` slash command and `/inbox` skill in this repo
(`claude-config/skills/capture/`, `claude-config/skills/inbox/`) write
to the **Knowledge MCP** database — a separate, cross-project free-form
inbox. They are **intentionally independent** from `cap` in v1:

| | `/capture` (slash) | `cap` (shell) |
|---|---|---|
| Surface | Claude Code session | Any terminal |
| Storage | Knowledge MCP DB | Per-project `ACTIONS.md` (git-tracked) |
| Tagging | `@project` `#type` | `--owner --src --project`, `A-NNN` IDs |
| Triage | `/inbox` | Edit the markdown file |

`/capture` is for free-form mid-session captures. `cap` is for trackable,
referenceable, project-scoped action items.

## v2 / v3 plan summary

- v2: MCP exposure of `ACTIONS.md` to `/dashboard`.
- v3: alternate surfaces (iOS Shortcut, voice, email) and a TODO scanner.
