# Cross-Device Project State

> **Status (2026-05-13)**: Phase 7.1 still describes the live `host:` field
> convention on project notes. **Phase 7.2 (SSH bridge) is superseded by
> Path B** — see `specs/path-b-migration.md`. The SSH-bridge concept was
> redesigned around per-host sidecars at
> `<vault>/Projects/_pulse/<project>--<host>.md` written by `pulse refresh`
> (using `lib/host_resolver.py`), under a single-writer-per-host
> convention declared in `~/.claude/dashboard-subscriptions.json`. The
> `pulse digest` / `pulse audit` CLIs then read the sidecars. Phase 7.3
> (write-from-anywhere) remains out of scope.
>
> **Phase 7.1 historical context** (FINAL — 2026-05-08): A-013 closed the
> investigation half of `PLAN.md` Phase 7. This doc was the architectural
> decision record. Implementation was split: Phase 7.1 (the spec + the
> cheap-insurance `host:` schema field) shipped first; Phase 7.2 was
> deferred. Path B then absorbed and reshaped 7.2.

---

## TL;DR

- **Agents repo is the central state substrate.** All cross-cutting state
  (`knowledge/projects/*.yaml`, `knowledge/decisions/*.yaml`, patterns,
  learning rules, agents-repo-level `ACTIONS.md`) syncs across machines via
  GitHub.
- **Each project YAML carries a `host:` field** declaring which host owns
  the project. Per-project `ACTIONS.md` lives inside the project's repo on
  that host; cross-host visibility for it is a Phase 7.2 concern.
- **Per-machine canonical name** lives in `~/.claude/host-name` (one line
  of text). The `lib/project_resolver` autodetect reads this file or falls
  back to a sanitized `socket.gethostname()`.
- **No SSH bridge today.** Phase 7.1 is the schema decision and the
  bookkeeping field. Phase 7.2 implements `lib/host_resolver.py` and the
  dashboard's multi-host merge; ship it when an actual non-`jns-mac`
  project is added and the asymmetry becomes felt.
- **No write-from-anywhere today.** Existing pattern (Claude on a laptop
  SSHs into the host and runs the CLI there) covers it. Phase 7.3 only if
  that becomes a real friction point.

---

## Workflow context

User's actual two-laptop, multi-host pattern (captured 2026-05-07/08):

| Laptop | Class | Use |
|---|---|---|
| `vitalai-laptop` | work (WSL) | Primary daily driver. Runs Claude. SSHs into work hosts to manage codebases. |
| `jns-mac` | personal (this MacBook) | Secondary. Same Claude-into-SSH pattern, lower frequency. |

| Remote host | Class | Reachability |
|---|---|---|
| `jbox06` | work | LAN-only (172.16.20.58). Internal GitLab projects (172.16.20.50). Off-LAN today (laptop is at 10.20.30.54), `jbox06` is unreachable. |
| `et01` | work | TBD network shape. |
| `spark` | work | TBD network shape. |
| `jns-server` | personal | LAN via `jns` (192.168.1.100). Cloudflare-tunneled via `jns-remote` (`mavisssh.jasonjob.com`) — reachable from anywhere. |

The laptops both reach **GitHub** (HTTP 200, ~80ms). Internal GitLab is
reachable only from `jbox06`'s network. Cloudflare-tunneled SSH (`jns-remote`)
is reachable from anywhere.

The user's verbalized usage pattern: *"I run Claude on the work laptop and
have Claude ssh into the device to modify the codebase. This is a daily
pattern. I do not do this as much from this MacBook. I intend to add
projects to the jns-server in the near future and may do similar work
pattern."*

**Implications:**

1. **Laptops are the state-management surface; remote hosts are runtime.**
   Project tracker YAMLs, decisions, patterns, learning-rules — all live
   on a laptop and sync via GitHub. Remote hosts run code; they don't
   typically run `dashboard` or `decision new`.
2. **Per-project `ACTIONS.md` is the asymmetric piece.** It lives inside
   each project's repo (e.g., `~/app-repos/<vitalai-app>/ACTIONS.md` on
   `jbox06`), reachable only on the host that clones the repo.
3. **Reachability is mixed.** GitHub-reachable everywhere; LAN-only
   `jbox06`; tunnel-reachable `jns-server`. A robust solution must
   degrade gracefully when a host is unreachable.

---

## Architectural decisions

### D-S1 — Agents repo is the central state substrate

All cross-cutting state lives under `~/agents/knowledge/` and syncs via
GitHub from any host that can reach GitHub. This includes:

- `knowledge/projects/<name>.yaml` (per-project tracker)
- `knowledge/decisions/D-NNN.yaml` + `index.yaml`
- `knowledge/patterns/pat-*.yaml`
- `knowledge/learning-rules/LR-*.yaml`
- `~/agents/ACTIONS.md` (the agents repo's own actions)
- `~/agents/PLAN.md`, `~/agents/specs/*.md`, `~/agents/CLAUDE.md`

**Why:** GitHub is universally reachable. Git's merge-on-pull handles the
low collision rate (different machines tend to edit different YAMLs).
Filesystem-as-truth keeps tooling independent of any sync service.

**How to apply:** every new laptop in the user's set should clone the
agents repo. Pulls/pushes happen on the cadence the user prefers
(typically post-merge hooks already trigger reinstall on changed config).

### D-S2 — `host:` field on project YAMLs

Every `knowledge/projects/<name>.yaml` MUST have a `host:` field whose
value is the canonical name of the host that owns the project (where its
repo is cloned and where its per-project `ACTIONS.md` lives).

**Field position:** between `project:` and `status:` (declared in
`project/cli.py PROJECT_FIELDS_ORDER`).

**Allowed values:** any host name the user uses. Current canonical set:

| Name | Class |
|---|---|
| `jns-mac` | personal — this MacBook |
| `jns-server` | personal — home server |
| `vitalai-laptop` | work — WSL laptop |
| `jbox06` | work — internal LAN host |
| `et01` | work — TBD |
| `spark` | work — TBD |

**Why:** Without this field, future tooling (dashboard SSH-bridge in
Phase 7.2) has to guess where a project lives based on
`~/projects/<name>` directory existence, which won't work cross-machine.
The field is cheap insurance and decouples Phase 7.1 (decision +
bookkeeping) from Phase 7.2 (implementation).

**How to apply:**

- New projects: `register_project()` autodetects the host and stamps it.
- Existing projects: backfilled to `host: jns-mac` in this PR (the only
  host any of them currently lives on).
- Migration: `project <name> --set-host <new-host>` updates the field
  without bumping `updated_at` (host is operational, not content).

### D-S3 — Per-machine canonical name in `~/.claude/host-name`

Each machine declares its own canonical name in `~/.claude/host-name`
(one line of text). The `lib/project_resolver.get_host_name()` function
reads this file; if absent, falls back to a sanitized `socket.gethostname()`
(lowercased, first-segment-only).

**Why:** OS hostnames don't match the user's mental model.
`socket.gethostname()` on this MacBook returns
`Jasons-MacBook-Pro-1805.local`, not the desired `jns-mac`. Hard-coding a
mapping is brittle. A per-machine override file is the cleanest solution
and matches the existing per-machine convention
(`dashboard-subscriptions.json`, `pending_focus_reviews.json`).

**How to apply:**

- Each laptop runs `project --register-host <canonical-name>` once on setup.
- The CLI never asks Claude (or any LLM) for the host name — it's a
  three-line file read.

### D-S4 — SSH bridge is Phase 7.2, not Phase 7.1

Phase 7.1 captures the architecture and adds the schema field. It does
**not** implement multi-host reads in `dashboard/cli.py`.

**Why:**

- Today, all 7 tracked projects are on `jns-mac`. Multi-host read has
  zero data points to operate on.
- Empirical-usage discipline (the same one that killed `/capture` and
  `/inbox`) says: don't build for theoretical needs.
- Phase 7.2 is real work (~400-600 LOC across `lib/host_resolver.py`,
  dashboard integration, caching, tests). Stacking it on the architecture
  decision blurs the review boundary.

**Trigger to ship Phase 7.2:** a `knowledge/projects/<name>.yaml` is added
with `host:` other than `jns-mac` (e.g., when the first `jns-server`
project is tracked). When that happens, refile A-013 with Phase 7.2
scope — see "Phase 7.2 sketch" below.

### D-S5 — Write-from-anywhere is Phase 7.3, deferred indefinitely

The user's existing pattern of "Claude on the laptop SSHs into the host
and runs the CLI there" already provides write-from-anywhere semantically.
A native multi-host write (`dashboard --host jbox06 --action-new "..."`)
would be more convenient but adds significant scope (auth handling,
remote command construction, error propagation).

**Trigger to ship Phase 7.3:** real friction with the SSH-then-run pattern
becomes felt and articulated. Not until.

---

## Phase 7.2 sketch (NOT in this PR)

For when the trigger fires:

### `lib/host_resolver.py` (new)
- `is_reachable(host: str, timeout: float = 3.0) -> bool` — TCP check on
  port 22; respects `~/.ssh/config` aliases.
- `read_remote(host: str, cmd: list[str]) -> tuple[int, str, str]` — runs
  `ssh <host> <cmd>` with a timeout; returns `(returncode, stdout, stderr)`.
- Optional: ~5 minute LRU cache for results, keyed by `(host, cmd)`.
- Optional: `~/.claude/host-map.json` for nicknames / preferred-tunnel
  routing (e.g., always use `jns-remote` for `jns-server` if local LAN
  resolution fails).

### `dashboard/cli.py` integration
- New flag `--include-host <name>` (repeatable) or auto-aggregate via
  the subscription file plus the per-project `host:` field.
- Per-project rendering checks `host`:
  - `host == get_host_name()` → read locally as today.
  - `host` reachable → SSH out, read remote `ACTIONS.md` + `git log` +
    `gh issue list` from the project's checkout location on that host.
  - `host` not reachable → render a placeholder line: `(remote
    unreachable; switch to LAN or use jns-remote tunnel)`.

### Tests
- Mock `subprocess.run` to simulate reachable / unreachable / timeout.
- Cache TTL behavior.
- Multi-host aggregation order (local first, remote alphabetical).

Sizing: ~400–500 LOC + tests. One PR, MODERATE tier.

---

## What stays out of scope forever (or until really proven)

- Centralized state server / database. Agents-repo-on-GitHub already plays
  that role for the only data that needs to be shared.
- Auto-cloning project repos on multiple hosts. Repos live where they live;
  cross-host visibility is via Phase 7.2 SSH bridge, not via parallel
  clones.
- Renaming the existing per-machine subscription file. Subscriptions
  remain "which projects this machine sees" independent of `host:`.

---

## Acceptance for Phase 7.1 (this PR)

- [x] `host:` field added to all 7 existing project YAMLs (`host: jns-mac`).
- [x] `lib/project_resolver.register_project` autodetects host via
      `get_host_name()`; accepts explicit `host=` override.
- [x] `~/.claude/host-name` mechanism documented + bootstrapped for this
      machine (`jns-mac`).
- [x] `project <name> --set-host <hostname>` updates the field without
      bumping `updated_at`.
- [x] `project --register-host <hostname>` writes the per-machine file.
- [x] `project <name>` read mode renders `Host: <name>` on the status
      line.
- [x] `specs/knowledge-surfaces.md` updated to reflect `host:` in the
      project YAML schema row.
- [x] Tests covering autodetect, override, fallback, `--set-host`,
      `--register-host`, field-order preservation.
- [x] No regressions in `pytest project/ action/ review_session/ decision/`.

## Sign-off

Decision-only architecture record + cheap-insurance schema field.
Phase 7.2 (SSH bridge) and 7.3 (write-from-anywhere) are explicitly
deferred with documented trigger conditions.
