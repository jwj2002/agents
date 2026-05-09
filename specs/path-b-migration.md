# Path B Migration — Obsidian + multi-vault topology

> **Status**: FINAL — 2026-05-08
> **Type**: Architectural decision record (ADR)
> **Implementation**: separate big-bang PR after this spec merges
> **Supersedes (in scope of effect):** parts of `specs/cross-device-state.md` Phase 7.2 (now realized via pulse), parts of `specs/knowledge-surfaces.md` (project + decision YAMLs migrate to Obsidian)

---

## TL;DR

After 8+ PRs of homegrown CLI investment, audit revealed ~75% of the system reinvents tools mature open-source projects already solve. Path B keeps the unique-and-valuable parts (per-repo `ACTIONS.md`, action CLI, schema-versioned YAML for tooling) and replaces the rest with **Obsidian + Tasks + Dataview + Templater** as the project-context and daily-review surface.

A multi-vault topology supports the user's actual device fleet:

- **Personal laptop (`jns-mac`)** opens all vaults — single convergence point for cross-context visibility
- **Client laptops** each open exactly one vault — strict data isolation by sync topology
- **Remote dev hosts** (jbox06 / et01 / spark / jns-server) host project repos but never run Obsidian; pulse SSH-reads them

A new `pulse` script (~250 LOC) is the bridge: each laptop runs pulse on a 30-min cron, scraping repo state into Obsidian project-note frontmatter. Daily-review + project-page Dataview queries render against pulse-populated frontmatter.

**Net result:** ~3000 LOC of homegrown rendering / schema-migration code retired. ~300 LOC of pulse + Templater glue replaces it. Mobile/iPad capture available when Obsidian Sync is purchased (deferred — git backup adequate for v1).

---

## Workflow context

User's actual device topology and work pattern (captured 2026-05-08):

| Class | Devices | Runs Obsidian? | Has project repos? | Notes |
|---|---|---|---|---|
| Personal write surfaces | `jns-mac`, future iPad/iPhone | ✅ | jns-mac yes; mobile no | Convergence point for all vaults |
| Work laptops | `vitalai-laptop` (WSL), future `tillamook-laptop` | ✅ (single vault each) | yes (work projects only) | Strict client isolation |
| Remote dev runtime | `jbox06`, `et01`, `spark`, `jns-server` | ❌ | yes (each hosts a subset of project repos) | Reached via SSH from laptops |

**Confirmed work pattern**: user runs Claude on a laptop, has Claude SSH into a dev host, and edits the codebase remotely. Dev hosts execute code; laptops orchestrate. Project state (focus, decisions, daily review) lives on laptops, syncs across devices via vault git remotes.

**Confirmed clients & host conventions**:
- Personal: GitHub `jwj2002`
- VitalAILabs: GitHub `jjob-spec`
- Future Tillamook: GitHub `jjob-tillamook`
- (Maison Financial: not currently active; no vault required)

**The architecture must handle**:
1. Multiple laptops syncing the same vault (concurrent edits)
2. Strict client separation (vault per client; never cross-pollinated)
3. Remote dev hosts reachable via SSH but not Obsidian-aware
4. Single laptop (`jns-mac`) with N+1 vaults open simultaneously
5. New client onboarding as a documented short procedure

---

## Architectural decisions (Q1–Q13)

Each decision was discussed explicitly with the user and locked in before this draft.

### Q1 — CLI fate: hybrid

| Decision | **Hybrid: keep `project` and `decision` as thin Obsidian-frontmatter wrappers; drop `dashboard` and `review-session` (replaced by Daily note + project pages with Dataview).** |
|---|---|
| Why | Project focus updates and decision filing happen mid-flow when a developer is already in a terminal. `project agents --focus "..."` keeps hands on keyboard. Dashboard and review-session are reading/aggregation tasks where Obsidian's UI (clickable wikilinks, rendered tables, mobile access) wins. ~100 LOC of wrappers. |
| How to apply | Keep `~/agents/action/cli.py` (per-repo, unchanged). Reshape `~/agents/project/cli.py` and `~/agents/decision/cli.py` to read/write Obsidian markdown frontmatter instead of `knowledge/projects/*.yaml` and `knowledge/decisions/*.yaml`. Archive `~/agents/dashboard/` and `~/agents/review_session/` to `~/agents/_archived/`. |

### Q2 — Engineering layer (`~/agents/`) on client laptops: per-client default-yes

| Decision | **Default yes — clone the full agents repo on every device. If a specific client's IT/contract policy forbids personal/third-party tooling, fall back to a thin distribution (just action CLI + pulse) for that one laptop.** |
|---|---|
| Why | The agents repo contains zero client IP — it's open-source-shaped engineering tooling. Default-yes handles the common case cleanly. Per-client override handles the conservative client without designing for them upfront. |
| How to apply | `bootstrap-laptop.sh` clones `~/agents/` by default. Future override hook: an env var `JNS_THIN_DIST=1` switches the bootstrap to install only `action` CLI + pulse, no patterns/specs/CLAUDE.md, no Claude config. |

### Q3 — Vault git hosting: per-context GitHub account

| Decision | **Each vault's git remote follows GitHub-account-per-context (matches existing source-code pattern):**<br>• JNS-Personal-Vault → `jwj2002/jns-personal-vault` (private)<br>• Vital-Work-Vault → `jjob-spec/vital-work-vault` (private)<br>• Future Tillamook-Work-Vault → `jjob-tillamook/tillamook-work-vault` (private)<br>• Future clients: GitHub destination negotiated at engagement start; default fallback is dedicated client-named account |
|---|---|
| Why | Off-boarding is clean (close contract → archive vault repo on that account). Source code and meta-notes share GitHub-account context. |
| How to apply | Document the GitHub-account selector in `bootstrap-laptop.sh`; per-client override negotiated at engagement. |

### Q4 — Vault location on disk: `~/vaults/<name>/`

| Decision | **All vaults at `~/vaults/<vault-name>/` uniformly across macOS, Linux, and WSL. WSL specifically: real path is on the Windows side at `C:\Users\<user>\vaults\<name>`, with `~/vaults/` symlinked to `/mnt/c/Users/<user>/vaults/` for script consistency.** |
|---|---|
| Why | Pulse and bootstrap scripts iterate `~/vaults/*` uniformly. Obsidian on Windows accesses Windows-side files natively (avoiding the slow WSL filesystem bridge). User-visible paths identical across devices. |
| How to apply | `bootstrap-laptop.sh` detects WSL via `grep -qi microsoft /proc/version` and sets up the symlink. Native-OS bootstraps create `~/vaults/` as a regular directory. |

### Q5 — Templater templates: master + sync

| Decision | **Master templates in `~/agents/templates/obsidian/`. A small `~/agents/templates/sync-templates.sh` script (~10 LOC) copies them into each vault's `_templates/` folder when invoked.** |
|---|---|
| Why | Vaults stay self-contained for bootstrap (a fresh laptop can clone the vault git remote and Obsidian-open it without depending on `~/agents/` being installed yet). Sync script handles the convenience of one master copy. |
| How to apply | Master copies committed to agents repo. `sync-templates.sh` runs after a master edit (or on cron). Each vault has a copy of the templates that survives standalone. |

### Q6 — Migration cadence: big-bang single PR

| Decision | **Big-bang. One implementation PR migrates project YAMLs → Obsidian project notes; archives existing decision YAMLs (no migration); ships pulse v1 (local-only); introduces Templater templates and Dataview queries; thin-wraps `project` and `decision` CLIs against Obsidian frontmatter; archives the retired CLIs.** |
|---|---|
| Why | Matches user's established sole-validator override of parallel-period gates (per session memory: Phase 6A.2 explicit "I do not want to wait a week"). Heavy test coverage required upfront in lieu of dual-run validation. Existing YAMLs archived to `_archived/` (not deleted) for emergency manual fallback. Rollback = `git revert` of the implementation PR. |
| How to apply | Implementation PR scope: ~800-1200 LOC. Test coverage requirements specified in §13 (Acceptance criteria). |

### Q7 — Phase 7.2 SSH bridge: bundled into the big-bang PR

| Decision | **Pulse ships with full SSH support in the big-bang PR.** Includes `lib/host_resolver.py`, SSH read with timeouts, ~5min cache layer, graceful unreachable handling, tests against jbox06/jns-server. **No separate v2 follow-up.** |
|---|---|
| Why | Revised after Codex adversarial review (2026-05-08). Original plan separated v1 (local-only) and v2 (SSH); review flagged that retiring `dashboard/`+`review_session/` in v1 while pulse can't reach remote hosts creates a visibility gap during the v1→v2 window for any non-local project. User explicitly stated intent to add `jns-server` projects soon — making the gap not theoretical. Bundling avoids the cutover gap entirely; PR is larger (~1100-1450 LOC) but ships in one atomic unit with no fallback path needed. |
| How to apply | Pulse reads project frontmatter; if repo path is local, reads directly. If repo lives on a configured remote (per `ssh_writes` in subscription file — see §8), reads via SSH. If the host is unreachable, the prior sidecar's `pulled_at` timestamp ages but other devices' sidecars still serve fresh data via vault sync. Implementation tracks the design specced in `specs/cross-device-state.md` §"Phase 7.2 sketch" — that doc's "v2 follow-up" framing is now superseded by this bundling. |

### Q8 — Subscription file format: vault-keyed dict

| Decision | **`~/.claude/dashboard-subscriptions.json` becomes a vault-keyed dict; legacy flat list auto-migrated on first read:**<br>```json<br>{<br>  "JNS-Personal-Vault": ["agents", "buddy", "paul-jason"],<br>  "Vital-Work-Vault":   ["vital-app-a"]<br>}<br>``` |
|---|---|
| Why | Per-machine semantic preserved (file is local-only, not synced). Vault key disambiguates which projects pulse refreshes when a laptop has multiple vaults open. Single-vault client laptops only consult their one key; legacy entries (if any) silently ignored. |
| How to apply | `lib/project_resolver` reads the new format; if it detects the old `{"subscribed": [...]}` shape, transparently rewrites as `{"JNS-Personal-Vault": [...]}` on first write. |

### Q9 — Decisions migration: archive existing, restart fresh

| Decision | **Existing 9 D-NNN.yaml files (D-015, D-034, D-042, D-087, D-091, D-095..D-098) and `index.yaml` are NOT migrated. Archived to `~/agents/_archived/decisions-pre-pathb/` (preserve git history). New decisions in Path B start fresh at D-001.** |
|---|---|
| Why | None of the existing decision IDs are referenced from active spec docs as anything that requires preservation. Old decisions are historical artifacts; the cost of mapping `project:` → vault doesn't earn its keep. Fresh D-NNN sequence simplifies the migration script. |
| How to apply | Migration step: `git mv knowledge/decisions/ _archived/decisions-pre-pathb/`. New `decision --new` writes to `<vault>/Decisions/D-001.md` (and increments globally). Cross-vault uniqueness preserved by scanning all vaults before assigning the next ID. |

### Q10 — Email automation: manual trigger only, review before send

| Decision | **No auto-send. Email digests are generated, previewed, and sent only via explicit user action. No cron-scheduled email in v1.** |
|---|---|
| Why | User explicitly requested review-before-send to catch any leakage between client contexts and to ensure the digest reads correctly before reaching the recipient. |
| How to apply | See §9 (email-digest design): YAML config + interactive y/e/s/n prompt. |

### Q10b — Email config + review flow: YAML config + interactive prompt

| Decision | **YAML config at `~/.claude/digest-config.yaml` (per-machine, not synced). Interactive prompt: y (send) / e (edit in $EDITOR) / s (save draft) / n (cancel). Drafts in `~/.claude/digests/draft/`; sent archive in `~/.claude/digests/sent/`.** |
|---|---|
| Why | Configure once per recipient; trigger many times. Interactive prompt mirrors the action CLI's `-i` mode and the `--register-host` command (consistent UX). Drafts/sent folders provide audit trail. |
| How to apply | See §9 for full schema and command surface. |

### Q11 — Project page structure: single page, two halves, minimal starter

| Decision | **One project note per project at `<vault>/Projects/<name>.md`. Body has two halves separated by `---`:**<br>• **Top half (overview)** — minimal starter (Purpose, Stack, Repository, optional Client block); add sections only when a real need emerges. Manually written or Claude-assisted. CLAUDE.md is the source of truth for AI-agent-onboarding context — **not** duplicated here.<br>• **Bottom half (operational)** — pulse + Dataview rendered. Live data. |
|---|---|
| Why | Single source of truth per project. Open `[[agents]]` → see purpose → scroll to see live state. No navigation cost. Starting with a minimal overview prevents premature template bloat; richer sections are added one-at-a-time when felt. Pulse never touches the overview half (additive frontmatter writes only). |
| How to apply | Templater "New Project" command generates the page with the minimal starter shape. Auto-population from CLAUDE.md is best-effort and only fills fields that map cleanly (e.g. stack). See §7 for the template body verbatim. |

### Q12 — Daily review scope: operational + git hygiene only

| Decision | **The Daily note never repeats overview content. It surfaces only operational state and git hygiene that needs attention. Empty sections render as nothing (no noise).** |
|---|---|
| Why | Overview is "what is this?" — read once per project. Daily review is "where are things right now?" — read every day. Mixing them adds visual clutter to the daily ritual. |
| How to apply | Daily review template's Dataview queries pull only operational and git-state frontmatter fields. Overview-half content is structurally separated by the `---` rule and never queried by the daily review. |

### Q13 — Git hygiene tracking: per-host sidecar files, simple rendering

| Decision | **Pulse on each device writes git state to a per-host sidecar file at `<vault>/Projects/_pulse/<project>--<hostname>.md` — never to the human-edited project note's frontmatter. Each pulse owns exactly one sidecar file per (project, host) pair. The daily review's "Git — needs attention" section iterates `_pulse/*.md` and renders one line per non-clean project: `**project** · device · summary`.** |
|---|---|
| Why | Revised after Codex adversarial review (2026-05-08). Original plan had pulse write to `git_state.<hostname>` in shared project frontmatter; review flagged that even with per-host keys, the underlying `git pull → mutate file → push` flow can race across devices and produce YAML conflict markers in frontmatter that break Dataview rendering. Per-host sidecar files eliminate the shared-write surface entirely: each laptop owns one file per project; concurrent collision impossible. |
| How to apply | See §6 for sidecar schema, single-writer-per-host convention, and Dataview-join queries. The human-edited project note holds focus/status/blockers/next_steps only; the operational half renders by `FLATTEN`-ing across that project's sidecars. |

---

## Vault topology + git remotes

```
                  ┌────────────────────────────────────────┐
                  │   ~/agents/  (GitHub: jwj2002, all     │
                  │   personal+work devices via clone)     │
                  │                                        │
                  │   - action CLI                         │
                  │   - pulse script                       │
                  │   - templates/obsidian/                │
                  │   - patterns/, learning-rules/         │
                  │   - specs/, CLAUDE.md, hooks           │
                  │                                        │
                  │   ZERO client IP. ZERO secrets.        │
                  └─────┬────────┬────────┬────────┬───────┘
                        │        │        │        │
        ┌───────────────┴───┐  ┌─┴────┐ ┌─┴─────┐ ┌┴──────┐
        │     jns-mac       │  │vital-│ │tilla- │ │ jbox06│
        │     (personal)    │  │ai-   │ │mook-  │ │ et01  │
        │     N+1 vaults    │  │laptop│ │laptop │ │ spark │
        └───┬─────┬─────┬───┘  └──┬───┘ └───┬───┘ │ jns-server
            │     │     │         │         │      │ (no Obsidian; project
            ▼     ▼     ▼         ▼         ▼      │  repos hosted; pulse
   ┌────────────────────┐    ┌─────────┐ ┌────────┐│  SSH-reads them via
   │ JNS-Personal-Vault │    │  Vital- │ │ Tilla- ││  pulse v2)
   │ jwj2002/jns-       │    │  Work-  │ │ mook-  │└──────┘
   │ personal-vault     │    │  Vault  │ │ Vault  │
   └────────────────────┘    └─────────┘ └────────┘
                              jjob-spec/  jjob-     
                              vital-     tillamook/ 
                              work-vault tillamook- 
                                         work-vault
```

**Vault → device mapping**:

| Vault | git remote | Synced to (devices) |
|---|---|---|
| JNS-Personal-Vault | `jwj2002/jns-personal-vault` (private) | jns-mac (+ future iPad if Obsidian Sync purchased) |
| Vital-Work-Vault | `jjob-spec/vital-work-vault` (private) | jns-mac, vitalai-laptop |
| Tillamook-Work-Vault *(when engagement starts)* | `jjob-tillamook/tillamook-work-vault` (private) | jns-mac, tillamook-laptop |
| `<NewClient>-Work-Vault` *(future)* | `<negotiated>/<vault-repo>` (private) | jns-mac, that client's laptop |

**Sync mechanism (v1):** Obsidian Git plugin per vault. Auto-pull on Obsidian launch; auto-commit + push every 10 min while Obsidian is open. Free; works on macOS + WSL desktops. Mobile (iPad/iPhone) sync requires Obsidian Sync ($96/yr); deferred.

**Why git over Obsidian Sync for v1**: starts free; user controls every key; no third-party-cloud trust; portable. Trade-off: no native iPad sync until upgrade. User accepts this trade-off in v1.

### Client onboarding procedure (canonical)

When a new client engages:

1. Provision the client laptop (client provides hardware).
2. On `jns-mac`: create new Obsidian vault `<Client>-Work-Vault` at `~/vaults/<client>-work/`. Initialize as git repo. Create private remote on negotiated GitHub account (default: dedicated client-named account, e.g. `jjob-<client>`).
3. Copy templates from `~/agents/templates/obsidian/` via `sync-templates.sh`.
4. Add a vault entry to jns-mac's `~/.claude/dashboard-subscriptions.json` and `~/.claude/digest-config.yaml`.
5. On the new client laptop: clone `~/agents/` (or thin-distribute per Q2), run `bootstrap-laptop.sh`, register host via `project --register-host <client>-laptop`.
6. Clone the new vault on the client laptop. Open Obsidian → vault appears.
7. Subscribe the laptop to the client's projects via `project <name> --subscribe`.

Total time: ~30 minutes per onboarding once the pattern is documented.

### Client off-boarding procedure

1. Disable Obsidian Git on the client laptop for that vault.
2. Move the client repo on jns-mac to a read-only archive (`~/vaults/_archived/<client>-work-<date>/`).
3. Remove subscription entries.
4. Optional: delete the GitHub remote (if contract requires) or archive on the dedicated account.

---

## What lives where (post-migration surface map)

| Surface | Pre-migration | Post-migration |
|---|---|---|
| Per-repo actions | `<repo>/ACTIONS.md` (action CLI) | **Same — unchanged** |
| Project tracker (focus, status, next_steps, blockers, open_questions) | `~/agents/knowledge/projects/<name>.yaml` (project CLI) | `<vault>/Projects/<name>.md` (frontmatter + body); thin `project` CLI mutates the markdown |
| Decisions journal | `~/agents/knowledge/decisions/D-NNN.yaml` (decision CLI) | `<vault>/Decisions/D-NNN.md` (MADR format); thin `decision` CLI mutates the markdown |
| Patterns (engineering, cross-client) | `~/agents/knowledge/patterns/pat-*.yaml` | **Same — unchanged.** Read by SessionStart hook (A-020 separately). |
| Learning rules (engineering, cross-client) | `~/agents/knowledge/learning-rules/LR-NNN.yaml` | **Same — unchanged.** |
| Daily review | manual via `dashboard --window daily` | `<vault>/Daily/<date>.md` (Templater-generated, Dataview-rendered) |
| Pending focus reviews | `~/.claude/pending_focus_reviews.json` (session-end hook) | **Removed** — pulse computes `focus_drift_days` directly; daily review's stale-focus query supersedes |
| Subscriptions | `~/.claude/dashboard-subscriptions.json` (flat list) | **Same path; vault-keyed dict format** |
| Per-machine canonical name | `~/.claude/host-name` | **Same — unchanged.** |
| Email digest | manual via `dashboard --format markdown \| email-digest --to ...` | `email-digest preset <name>` with YAML config + review prompt |
| Cross-host project state | future Phase 7.2 (specced) | pulse v1 local-only; pulse v2 SSH-reads (separate PR) |

**Retired CLIs (archived to `~/agents/_archived/`):**
- `dashboard/cli.py` + tests (replaced by Daily note + project page Dataview queries)
- `review_session/cli.py` + tests (replaced by daily review's stale-focus block + git-hygiene block)

**Surviving CLIs (keep, reshape):**
- `action/cli.py` — unchanged
- `project/cli.py` — reshaped to mutate `<vault>/Projects/<name>.md` frontmatter
- `decision/cli.py` — reshaped to mutate `<vault>/Decisions/D-NNN.md` frontmatter
- `email-digest/cli.py` — extended with preset config + interactive prompt

**New CLIs:**
- `pulse/cli.py` — refresh, report, digest subcommands

---

## Pulse design (single-PR with SSH bundled)

### Responsibilities

1. For each subscribed project on each vault this device opens, refresh the project's per-host sidecar file at `<vault>/Projects/_pulse/<project>--<hostname>.md`.
2. Compute derived fields: `focus_drift_days`, `commits_24h`, `commits_7d`, `open_actions`, `open_issues`.
3. Read repo state — locally if `host` matches this device, via SSH if this device owns the remote host (per `ssh_writes` config), gracefully skip otherwise.
4. Provide read commands (`pulse report`, `pulse digest`) and a `pulse audit` subcommand for vault-isolation hygiene.

**Pulse never writes to the human-edited project note (`Projects/<name>.md`) — that file is owned by the user (or by `project` CLI's frontmatter mutations). Pulse owns one sidecar file per (project, host) it's responsible for; concurrent collision impossible because each pulse owns its own files.**

### File layout (per vault)

```
<vault>/Projects/
  agents.md                              ← human-edited only: focus, status, blockers, next_steps, open_questions
                                          (pulse NEVER touches this file)
  vital-app-a.md
  _pulse/                                ← machine-written sidecars; one per (project, host)
    agents--jns-mac.md                   ← jns-mac's pulse owns this file exclusively
    vital-app-a--vitalai-laptop.md       ← vitalai-laptop's pulse owns this file
    vital-app-a--jbox06.md               ← whichever device's `ssh_writes` claims jbox06 owns this file
```

Each laptop only writes the sidecars matching projects/hosts in its scope (see §8 for `ssh_writes` config). Sidecars sync across devices via vault git; each device sees other devices' sidecars even if it can't directly reach those hosts.

### Sidecar schema (`<project>--<host>.md`)

```yaml
---
project: agents                            # which project this sidecar refers to
host: jns-mac                              # which host's state this represents
pulled_at: 2026-05-08T16:30:00Z            # when pulse last wrote this file
reachable: true                            # false if SSH unreachable last attempt

# Activity rollups
last_commit_at: 2026-05-08T16:18:35Z
last_commit_subject: "feat(dashboard,action): split open/closed sections"
last_commit_sha: "8549609"
commits_24h: 8
commits_7d: 14
open_actions: 1
closed_actions_24h: 6
open_issues: 14
closed_issues_24h: 3

# Git hygiene (this host's local clone)
branch: main
ahead_origin: 0
behind_origin: 0
dirty: false
stale_local_branches: []
unpushed_branches: []
---
*(file body unused — sidecars are pure frontmatter)*
```

### Project note schema (human-edited only)

```yaml
---
project: agents
host: jns-mac                      # which laptop owns the repo
client: personal                   # personal | vital | tillamook | etc.
kind: engineering-tool             # personal | client-work | engineering-tool | archive
status: active                     # active | paused | blocked | done
focus: "Path B migration — multi-vault Obsidian"
status_updated: 2026-05-08         # YOU set this when focus changes
blockers:
  - "Waiting on Tillamook laptop provisioning"
next_steps:
  - "Build pulse v1"
  - "Author Templater templates"
open_questions:
  - "Should host_resolver cache live longer than 5 min?"

# Computed by pulse on demand from sidecars (NOT written into this file):
#   focus_drift_days, latest_pulse_at_any_host, etc.
# Dataview queries derive these via FLATTEN on sidecar files.
---
```

### Commands pulse runs (per repo, per refresh)

Cheap (no `git fetch` by default — relies on what was last pulled):

```bash
git -C <repo> rev-parse --abbrev-ref HEAD                    # current branch
git -C <repo> rev-list --count <default>..HEAD               # ahead
git -C <repo> rev-list --count HEAD..<default>               # behind
git -C <repo> status --porcelain                             # dirty?
git -C <repo> branch --merged <default>                      # stale (merged but local)
git -C <repo> for-each-ref --format='%(refname:short) %(upstream:track)' refs/heads/  # unpushed
git -C <repo> log -1 --format='%h — %s'                      # last commit
git -C <repo> log --since '24 hours ago' --oneline | wc -l   # commits_24h
git -C <repo> log --since '7 days ago' --oneline | wc -l     # commits_7d
gh -R <slug> issue list --state open --json number --jq length  # open_issues
gh -R <slug> issue list --state closed --search "closed:>1d" --json number --jq length  # closed_24h
```

`<default>` is auto-detected via `git symbolic-ref refs/remotes/origin/HEAD` (handles `main`, `master`, `develop`).

For ACTIONS.md state, pulse calls `lib/actions_md.parse_file(<repo>/ACTIONS.md)` directly — no shell-out.

### Scheduling

| Trigger | Runs |
|---|---|
| Cron / launchd every 30 min | Full refresh (all subscribed projects) |
| Post-merge git hook on agents repo | Quick refresh of `agents` project only |
| `action --status done` from action CLI | Quick refresh of the current project only |
| Manual `pulse refresh` | Full refresh on demand |
| Laptop wake (launchd `WakeUp` event on macOS) | Full refresh |

Implementation budget for v1: ~250-300 LOC (Python). Tests: ~150 LOC.

### Report and digest commands

```bash
pulse refresh                          # core: refresh all subscribed projects
pulse refresh --project <name>         # quick: just one project
pulse report --project <name>          # emit single-project markdown report
pulse digest --vault <name>            # emit per-vault digest
pulse digest --all-vaults              # cross-vault digest (jns-mac only)
pulse digest --window <daily|weekly|monthly|full>
```

`pulse report` and `pulse digest` are pure-read commands (don't refresh). Refresh is explicit.

### Failure modes

| Mode | Behavior |
|---|---|
| Repo not found at local path | Skip silently; sidecar gets `reachable: false, reason: "no-clone"` |
| SSH host unreachable (off-LAN, tunnel down) | Sidecar's `pulled_at` ages; `reachable: false` with reason; existing data preserved on disk so other devices' Dataview still renders the last-known-good values |
| `gh` unauthenticated | Skip GH issue counts; sidecar omits `open_issues`/`closed_issues_24h` |
| `git` command timeout (>5s) | Skip that field; sidecar `pulled_at` gets the partial-state time |
| ACTIONS.md missing or malformed | Sidecar's `open_actions: -1` flag value; rendering shows "—" |
| Concurrent collision on a sidecar | **Impossible by design** — single-writer-per-host convention enforced by `ssh_writes` config (see §8) |

### SSH host resolution

Pulse uses `lib/host_resolver.py` for remote reads. The module:
- Reads each device's `ssh_writes` list (subscription file, see §8) to know which hosts this laptop is responsible for.
- For each owned remote host, runs the same git/gh commands via `ssh <host>`.
- Honors `~/.ssh/config` aliases (handles Cloudflare tunnels via existing `jns-remote` alias, etc.).
- 5-second connect timeout per host; 10-second per command.
- ~5min in-process cache to avoid SSH cost on rapid successive `pulse refresh` calls.
- On unreachable host: writes sidecar with `reachable: false, last_reachable_at: <prior pulled_at>` so the daily report can show "stale data: jbox06 unreachable since 2h ago" instead of dropping the project from view.

---

## Client isolation guardrails

Confidentiality cannot rely on convention alone. The vault-per-client topology is the foundation; these mechanisms are the enforcement layer that prevents the "wrong preset / wrong vault / wrong remote" class of leak. Added in response to Codex adversarial review (2026-05-08, Finding 4).

### Mandatory mechanisms (must-have in v1)

| # | Mechanism | LOC est. | What it prevents |
|---|---|---|---|
| 1 | **Email-digest preset → vault validation** | ~20 | Before sending, pulse iterates every project mentioned in the rendered digest; fails if any project's `client:` frontmatter doesn't match the preset's expected `client`. Refuses to send with an explicit error pointing at the offending project. |
| 2 | **`pulse digest --all-vaults` jns-mac-only** | ~5 | Pulse on a non-`jns-mac` device refuses the `--all-vaults` flag with an error. Hardcoded check via `get_host_name() == "jns-mac"`. Prevents accidentally running a cross-vault digest from a client laptop. |
| 3 | **Pre-send confirmation context line** | ~10 | The interactive y/e/s/n prompt prepends a one-liner: `Sending to ai-coder@vital-enterprises.com (vault: Vital-Work-Vault, project filter: vital-app-a, owner filter: Paul). Confirm?` Visible context per send eliminates "wrong-recipient-by-tab-completion" errors. |
| 4 | **Per-vault git remote allowlist** | ~10 (in bootstrap) | Each vault's git config lists exactly one valid remote URL. `bootstrap-laptop.sh` enforces; manual `git remote add` to a different account on a vault is detected by `pulse audit` and flagged. Prevents accidental `git push <other-account>:<repo>`. |

Total mandatory LOC: ~45.

### Should-have mechanisms (v1 scope)

| # | Mechanism | LOC est. | Value |
|---|---|---|---|
| 5 | **`pulse audit` subcommand** | ~50 | Scans all vaults; verifies every project note in vault X has `client: <X>`; verifies every sidecar's `project:` matches its filename; verifies vault git remotes are on the allowlist. Run on demand and via cron weekly. Catches drift over time. |
| 6 | **Vault off-boarding script** | ~30 | `pulse vault offboard --vault <name>` moves vault to `~/vaults/_archived/<name>-<date>/`, removes git remote, removes subscription entries, removes digest preset, removes Templater registrations. Single command vs multi-step manual procedure. |

Total should-have LOC: ~80.

### Policy (no code; documented in the spec body)

| # | Policy |
|---|---|
| 7 | **FileVault / encrypted-at-rest required.** Any laptop hosting any vault — personal or client — must have full-disk encryption enabled. Documented as a vault prerequisite. Bootstrap script checks (`fdesetup status` on macOS; warning if disabled). On WSL, BitLocker on the Windows volume hosting the vault. |

### Total cost: ~125 LOC + 1 policy line

The mechanisms compose to make a leakage event require multiple simultaneous failures (wrong preset name + wrong project frontmatter + a clean audit + a misconfigured remote — all four). Independently each is unlikely; together, near-zero.

### Practical example: guardrail (1) preventing a typo error

```bash
$ email-digest preset paul-jason
[generated preview at ~/.claude/digests/draft/paul-jason-2026-05-08.md]

ERROR: digest scope mismatch.
  preset paul-jason expects client = "personal"
  but the rendered digest includes:
    - project "vital-app-a" with client = "vital"

Likely causes:
  (a) project vital-app-a's client: field is set incorrectly
  (b) you meant a different preset (try `email-digest preset list`)

Run `pulse audit --vault Vital-Work-Vault` to investigate (a).
Refusing to send.
```

That stops the wrong-recipient class of error cold without the user having to remember anything.

---

## Templater + Dataview UX

### Project page template (`~/agents/templates/obsidian/Project.md`)

Generated by Templater "New Project" command. Auto-populates from `<repo>/CLAUDE.md` if present.

Two halves separated by `---` rule:

```markdown
---
# Manually edited
project: <%= name %>
host: <%= host %>
client: <%= client %>
kind: <%= kind %>          # personal | client-work | engineering-tool | archive
status: active
focus: ""
status_updated: <%= today %>
blockers: []
next_steps: []
open_questions: []
stack: []
repo_path: ""
repo_remote: ""

# Pulse-managed (do not edit)
last_commit_at: ""
last_commit_subject: ""
commits_7d: 0
open_actions: 0
open_issues: 0
focus_drift_days: 0
pulse_at: ""
git_state: {}
---

# <%= name %>

## Purpose
*(one sentence)*

## Stack
*(languages, frameworks)*

## Repository
- Path: `<%= repo_path %>`
- Remote: `<%= repo_remote %>`

<%* if (kind === "client-work") { %>
## Client
- Contact: 
- Engagement: 
<%* } %>

*(Add more sections — conventions, setup, key dates, contacts, etc. — only when a real need emerges. CLAUDE.md in the repo holds AI-agent-onboarding context; this page is for the project narrative as YOU need it.)*

---

## Status (live)

```dataview
TABLE WITHOUT ID
  string(this.status).toUpperCase() as "Status",
  this.host as "Host",
  this.focus as "Focus"
FROM ""
WHERE file.name = this.file.name
```

## Activity (rolled up across all hosts that pulse this project)

```dataview
TABLE WITHOUT ID
  host as "Host",
  pulled_at as "Last Pulse",
  last_commit_subject as "Last Commit",
  commits_7d as "Commits 7d",
  open_actions as "Open A",
  open_issues as "Open I"
FROM "Projects/_pulse"
WHERE project = this.project
SORT pulled_at DESC
```

## Decisions linked

```dataview
LIST FROM "Decisions"
WHERE project = this.project
SORT created DESC
LIMIT 5
```

## Git on this device

```dataview
LIST WITHOUT ID
  branch + (dirty ? " · dirty" : "") +
    (ahead_origin > 0 ? " · " + string(ahead_origin) + "↑" : "") +
    (behind_origin > 0 ? " · " + string(behind_origin) + "↓" : "") +
    (length(stale_local_branches) > 0 ? " · stale local: " + length(stale_local_branches) : "")
FROM "Projects/_pulse"
WHERE project = this.project AND host = "<%= this_host %>"
```

(Multi-device git state visible in the Activity table above; the "needs attention" rollup across all projects + devices lives in the Daily review.)

## Notes / journal
*(your free-form area)*
```

### Decision template (`~/agents/templates/obsidian/Decision.md`) — MADR format

```markdown
---
schema_version: 1
id: D-<%= id %>
date: <%= today %>
project: <%= project %>
topic: <%= topic %>
title: "<%= title %>"
status: proposed
linked:
  patterns: []
  issues: []
  prs: []
  related_decisions: []
created_at: <%= today %>
---

# D-<%= id %> — <%= title %>

## Context
*(what's the problem; what constraints exist)*

## Decision
*(what we're choosing to do)*

## Alternatives considered
- **Option A**: ...
  - Rejected because: ...
- **Option B**: ...
  - Rejected because: ...

## Reasoning
*(why this is the right call given context + alternatives)*

## Outcome
*(filled in later when shipped — what actually happened)*

## Linked
- Patterns: 
- PRs: 
- Issues: 
- Related decisions: 
```

### Daily review template (`~/agents/templates/obsidian/Daily.md`)

Auto-fires at 7am via launchd. Fully auto-rendered; user edits the bottom Notes section. Queries scope to the current vault automatically (Dataview's `FROM "Projects"` resolves within the vault hosting the daily note).

```markdown
# <%= today %>

> Generated <%= now %>

## ⚠ Focus may be stale (>= 5 days)

```dataview
TABLE focus, (date(today) - date(status_updated)).days as "Days", status_updated as "Set"
FROM "Projects"
WHERE status = "active" AND (date(today) - date(status_updated)).days >= 5
SORT (date(today) - date(status_updated)).days DESC
```

## Active projects — recent activity (latest pulse, 24h rollup)

For each active project in this vault, show the freshest sidecar (any host).

```dataview
TABLE WITHOUT ID
  project as "Project",
  host as "Host",
  last_commit_subject as "Last commit",
  commits_24h as "↑24h",
  open_actions as "Open A",
  open_issues as "Open I"
FROM "Projects/_pulse"
SORT pulled_at DESC
GROUP BY project
LIMIT 10
```

## Today's tasks

```tasks
not done
sort by priority, due
```

## Yesterday's activity

One line per project with activity (any host).

```dataview
LIST WITHOUT ID
  "**" + project + "** · " + host + " — " + 
    string(closed_actions_24h) + " actions closed, " + 
    string(commits_24h) + " commits"
FROM "Projects/_pulse"
WHERE (closed_actions_24h > 0 OR commits_24h > 0) AND pulled_at >= dateadd(date(today), -1, "days")
SORT pulled_at DESC
```

## Decisions this week

```dataview
LIST FROM "Decisions"
WHERE created_at >= dateadd(date(today), -7, "days")
SORT created_at DESC
```

## Git — needs attention

One line per (project, host) sidecar that's not clean. Format: `**project** · host · summary` so you can hand the line to Claude as-is ("clean these up").

```dataview
LIST WITHOUT ID
  "**" + project + "** · " + host + " · " +
    (dirty ? "dirty · " : "") +
    (ahead_origin > 0 ? string(ahead_origin) + "↑ · " : "") +
    (behind_origin > 0 ? string(behind_origin) + "↓ · " : "") +
    (length(stale_local_branches) > 0 ? "stale local: " + length(stale_local_branches) : "")
FROM "Projects/_pulse"
WHERE dirty = true OR ahead_origin > 0 OR behind_origin > 0 OR length(stale_local_branches) > 0
SORT pulled_at DESC
```

When empty, every project is clean on every device that's pulsed recently. When a line appears, copy-paste it into Claude with "address this" and the agent has enough to act.

## Reachability — sidecars stale or unreachable

```dataview
LIST WITHOUT ID
  "**" + project + "** · " + host + " · " +
    (reachable = false ? "unreachable since " + last_reachable_at : "stale: " + pulled_at)
FROM "Projects/_pulse"
WHERE reachable = false OR pulled_at < dateadd(date(today), -1, "days")
```

---

## Notes
*(free-form)*
```

### Required Obsidian plugins

- **Tasks** — `- [ ] task #tag ⏫ 📅 YYYY-MM-DD` syntax + queries
- **Dataview** — table/list queries over frontmatter
- **Templater** — dynamic templates with JS expressions
- **Calendar** — sidebar calendar for daily-note nav
- **Obsidian Git** — vault git sync (free alternative to Obsidian Sync)

Bootstrap script installs these via the Obsidian community-plugins API.

---

## Subscription model

`~/.claude/dashboard-subscriptions.json`:

```json
{
  "JNS-Personal-Vault": {
    "subscribed": ["agents", "buddy", "paul-jason"],
    "ssh_writes": ["jns-server"]
  },
  "Vital-Work-Vault": {
    "subscribed": ["vital-app-a"],
    "ssh_writes": ["jbox06", "et01", "spark"]
  },
  "Tillamook-Work-Vault": {
    "subscribed": ["tillamook-app-x"],
    "ssh_writes": []
  }
}
```

**Two fields per vault:**
- `subscribed`: which projects pulse refreshes for this vault on this device. Drives sidecar refresh scope.
- `ssh_writes`: which remote hosts THIS device is the canonical writer for. Implements the single-writer-per-host convention from Finding 3 — prevents two laptops from racing on `_pulse/<project>--<host>.md` for the same remote host. Per-device declaration; if no device claims a host, that host's sidecar simply doesn't get refreshed.

**Per-machine** (not synced; each device has its own scope and its own SSH-write claims).

**Backwards compatibility**: if pulse encounters a legacy `{"subscribed": [...]}` flat shape on first read, it auto-rewrites as the new vault-keyed dict format with `ssh_writes: []` defaulted. Migration runs once; idempotent.

**Single-vault devices** (e.g. `vitalai-laptop`): the JSON may have other vault keys; pulse only consults the active vault's key. No cross-vault leakage.

**Mutation**:
- `project <name> --subscribe` (vault implied by cwd or active Obsidian vault) — adds to `subscribed`
- `project <name> --unsubscribe` — removes from `subscribed`
- `project --claim-ssh-host <vault> <hostname>` — adds to `ssh_writes`
- `project --release-ssh-host <vault> <hostname>` — removes from `ssh_writes`

`dashboard-subscriptions.json` is the source of truth.

---

## Email digest config + review flow

### Config: `~/.claude/digest-config.yaml` (per-machine)

```yaml
sender: jjob@vital-enterprises.com   # default sender for this machine

presets:
  paul-jason:
    description: "Weekly 1:1 prep digest for Paul"
    vault: JNS-Personal-Vault
    project: paul-jason
    owner_filter: Paul
    default_window: weekly
    recipient: ai-coder@vital-enterprises.com
    subject_template: "Weekly status — paul-jason {date}"

  vital-status:
    description: "Vital project rollup for VitalAILabs leadership"
    vault: Vital-Work-Vault
    project: "*"
    default_window: weekly
    recipient: leadership@vital-enterprises.com
    subject_template: "Weekly Vital status {date}"

  personal-archive:
    description: "Self-send for personal archival"
    vault: JNS-Personal-Vault
    project: "*"
    default_window: weekly
    recipient: jasonwadejob@gmail.com
    subject_template: "Personal digest {date}"
```

### Trigger flow

```bash
$ email-digest preset paul-jason
[generated preview at ~/.claude/digests/draft/paul-jason-2026-05-08.md]

─────────────────────────────────────────────────────────
# paul-jason — weekly summary (2026-05-08)
**Status:** ACTIVE
...
─────────────────────────────────────────────────────────

Send to ai-coder@vital-enterprises.com?
  [y] yes, send now
  [e] edit in $EDITOR before sending
  [s] save draft and exit (review later)
  [n] cancel

Choice [y/e/s/n]:
```

- **(y)**: posts via Microsoft Graph; archives to `~/.claude/digests/sent/<preset>-<date>.md`; prints message-id
- **(e)**: opens `$EDITOR`; on save, re-prompts y/s/n
- **(s)**: keeps draft at `~/.claude/digests/draft/`; resume via `email-digest send <file>`
- **(n)**: deletes draft

### Other commands

```bash
email-digest preset list                  # all configured presets
email-digest preset <name> --window <w>   # override window for this run
email-digest send <draft-file>            # send a saved draft
email-digest sent --since <d>             # list recently sent digests
```

---

## CLIs after migration

| CLI | Status | Notes |
|---|---|---|
| `action` | **Unchanged** — keep current behavior including auto-commit | Per-repo ACTIONS.md is the right shape; well-tested |
| `project` | **Reshaped** — same flag surface; reads/writes `<vault>/Projects/<name>.md` frontmatter instead of YAML | Resolves vault from `--vault` flag, current cwd, or default. Atomic frontmatter mutation preserves body. |
| `decision` | **Reshaped** — same flag surface; reads/writes `<vault>/Decisions/D-NNN.md` frontmatter instead of YAML | Cross-vault uniqueness preserved; `--new` scans all vaults to assign next D-NNN |
| `email-digest` | **Extended** — adds preset config + interactive review flow | Existing Microsoft Graph plumbing preserved |
| `pulse` | **NEW** — `refresh`, `report`, `digest` subcommands | ~250-300 LOC + tests |
| `dashboard` | **Retired** — archived to `~/agents/_archived/` | Replaced by Daily note + project page Dataview |
| `review-session` | **Retired** — archived to `~/agents/_archived/` | Replaced by daily review's stale-focus block + git-hygiene block |

---

## Migration plan (big-bang single PR with SSH bundled)

### Implementation PR scope

```
specs/path-b-migration.md                # this spec (already merged)

# New
~/agents/pulse/cli.py                    # full pulse with SSH support
~/agents/pulse/tests/test_cli.py
~/agents/lib/host_resolver.py            # SSH read + cache
~/agents/lib/tests/test_host_resolver.py
~/agents/templates/obsidian/Project.md
~/agents/templates/obsidian/Decision.md
~/agents/templates/obsidian/Daily.md
~/agents/templates/sync-templates.sh
~/agents/bootstrap-laptop.sh             # one-time per device
~/agents/scripts/migration-manifest.py   # pre-flight dry-run; outputs manifest for PR review
~/.claude/digest-config.yaml.example     # template; user copies + edits

# Reshaped
~/agents/project/cli.py                  # mutate Obsidian frontmatter; new --claim-ssh-host / --release-ssh-host flags
~/agents/project/tests/test_cli.py       # update for new I/O
~/agents/decision/cli.py                 # mutate Obsidian frontmatter
~/agents/decision/tests/test_cli.py      # update for new I/O
~/agents/email-digest/cli.py             # add preset + interactive flow + vault validation guardrail

# Archived (git mv to _archived/)
~/agents/dashboard/                      # retire entirely
~/agents/review_session/                 # retire entirely
~/agents/knowledge/projects/             # archived; Obsidian is source
~/agents/knowledge/decisions/            # archived; Obsidian is source

# Updated
~/agents/CLAUDE.md                       # reflect new architecture
~/agents/PLAN.md                         # mark Path B complete
~/agents/specs/knowledge-surfaces.md     # update for projects/decisions migration
~/agents/specs/cross-device-state.md     # mark Phase 7.2 superseded by pulse with SSH bundled
~/agents/lib/project_resolver.py         # legacy subscription auto-migrate to vault-keyed dict + ssh_writes
```

### Migration steps (in PR order)

1. **Branch** from `origin/main`. Name: `feature/issue-XXX-path-b-implementation`.
2. **Pre-flight dry-run** — run `migration-manifest.py` to generate `_archived/migration-manifest-<date>.md`. Manifest shows source-YAML → destination-Obsidian mapping for every project, field-by-field. **Commit the manifest in the implementation PR** so reviewers can inspect mappings before merge. Catches bad mappings before they're applied.
3. **Vault scaffold** for JNS-Personal-Vault (manual: `mkdir ~/vaults/jns-personal && obsidian://createVault`). Other vaults follow per-engagement.
4. **One-shot migration** converts `knowledge/projects/*.yaml` → `<vault>/Projects/*.md` per the manifest. Body's overview half is the minimal starter (Purpose / Stack / Repository / optional Client); auto-populated from each project's `<repo>/CLAUDE.md` if present. Operational half references the `_pulse/` sidecar files (which don't exist yet — pulse creates them on first run).
5. **Archive** old YAMLs: `git mv knowledge/projects _archived/projects-pre-pathb`, `git mv knowledge/decisions _archived/decisions-pre-pathb`.
6. **New code**: pulse with SSH (host_resolver + cache + tests) + new email-digest preset/interactive flow with vault validation + reshaped project/decision CLIs + `pulse audit` subcommand + vault off-boarding script.
7. **Templates**: copy templates to `~/agents/templates/obsidian/`. Run `sync-templates.sh` to populate vaults.
8. **Bootstrap**: write `bootstrap-laptop.sh` for one-time device setup (handles macOS, Linux, WSL with symlink; FileVault check).
9. **Archive retired CLIs**: `git mv dashboard _archived/dashboard`, `git mv review_session _archived/review_session`.
10. **Update docs**: CLAUDE.md, PLAN.md, knowledge-surfaces.md, cross-device-state.md (mark §Phase 7.2 superseded).
11. **Tests**: full suite green (project + action + email-digest + pulse + lib/host_resolver). Smoke pulse against real data on jns-mac (local) AND against jns-server (Cloudflare-tunneled SSH) to verify SSH path. Smoke `pulse audit` against current vaults.
12. **Open PR**, code review (manifest is the centerpiece), merge.

### Rollback procedure

Big-bang means a single squash-merge commit. Recovery has three layers:

**Layer 1: agents repo state (`git revert`)**
```bash
git -C ~/agents revert <implementation-commit-sha>
```
This restores: `knowledge/projects/*.yaml`, `knowledge/decisions/*.yaml`, the retired CLIs (`dashboard/`, `review_session/`), and the prior `lib/project_resolver.py`. Existing per-repo `ACTIONS.md` files unchanged.

**Layer 2: vault state (manual)**
Vaults at `~/vaults/<name>/` live outside the agents repo and are not affected by `git revert`. To remove them:
```bash
mkdir -p ~/vaults/_rollback-$(date +%Y-%m-%d)
mv ~/vaults/jns-personal ~/vaults/_rollback-$(date +%Y-%m-%d)/jns-personal
# repeat for each vault that was created during the migration
```
The vault directories are preserved (not deleted) so any hand-edits made during the rollback window aren't lost.

**Layer 3: subscription file (manual)**
```bash
cp ~/agents/_archived/dashboard-subscriptions.json ~/.claude/dashboard-subscriptions.json
```
Restores the legacy flat-list format that the now-restored `lib/project_resolver.py` expects.

After all three layers: restart Obsidian (it will note the missing vaults; that's expected). Confirm `pytest project/ action/ decision/` passes against the reverted state. The original `dashboard` and `review-session` CLIs work as before.

**Rollback isn't free** — it discards any focus updates / decisions / notes you made in Obsidian during the migration window. The pre-flight manifest is the primary safety mechanism; rollback is the secondary safety net for catastrophic bugs.

---

## Out of scope (explicit)

| Item | Reason |
|---|---|
| **iPad / iPhone sync** | Requires Obsidian Sync ($96/yr); deferred until mobile capture friction is felt. v1 is desktop-only via Obsidian Git plugin. |
| **A-020 SessionStart → YAML pattern reader** | Independent piece of work (specs/knowledge-surfaces.md follow-up); doesn't depend on Path B. |
| **Migrating existing 9 decisions** | Archived only; not migrated (Q9). Old decisions stay in `_archived/decisions-pre-pathb/`. |
| **Patterns / learning rules to Obsidian** | Stay as YAML in `~/agents/knowledge/`; tooling input, not human-browse data. |
| **Auto-emailing on a schedule** | v1 is manual trigger only with review-before-send (Q10). Cron-based scheduling can be added later. |
| **Obsidian Sync purchase** | User chose git backup for v1; revisit when iPad capture is wanted. |
| **Auto-update GH issue ↔ action linkage** | Out of scope; remains a manual `--issue` flag on `action --new`. Could be a follow-up if the gap is felt. |
| **Post-merge migration validation script** | Considered (Codex Finding 5); rejected as low-ROI for a one-shot migration. Pre-flight manifest is sufficient. |
| **Scripted vault rollback** | Considered (Codex Finding 5); rejected as premature. Manual rollback procedure is documented; if rollback ever needed, the manual steps are 5 lines. |

---

## Risks + mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Pulse has a bug that scrambles a sidecar | Medium | Low (sidecar is regenerable on next refresh; the human-edited project note is untouched) | Pulse writes are atomic (tmpfile + os.replace); each pulse owns its own sidecar files (no shared writes); test coverage on the sidecar-write path |
| Two devices both claim `ssh_writes` on the same host | Low | Low (sidecar gets overwritten by last writer) | `pulse audit` flags duplicate `ssh_writes` claims across vaults; documented "single-writer-per-host" convention; spec §8 calls this out |
| Migration script misformats a project YAML → Obsidian markdown | Low | Medium | Pre-flight manifest committed in PR for review BEFORE merge (Codex Finding 5); reviewers see source→destination mapping field-by-field; one-shot script tested on copy of YAMLs |
| Templater + Dataview update breaks a query | Medium | Low (queries fail silently or render empty) | Pin plugin versions; document upgrade procedure |
| User accidentally sends a client digest to the wrong recipient | Low | **High (confidentiality)** | Email-digest preset → vault validation refuses to send if any project's `client:` doesn't match preset (Codex Finding 4 / spec §6.5 mechanism 1); pre-send confirmation context line; `pulse audit` weekly catches drift |
| User accidentally types client work into wrong vault | Low | High (confidentiality) | Vault title bar; preset name; `pulse audit` flags client-mismatch projects; FileVault-at-rest reduces blast radius if a laptop is lost |
| Wrong git remote on a vault → push to wrong account | Low | High | Per-vault git remote allowlist enforced in bootstrap (spec §6.5 mechanism 4); `pulse audit` flags off-allowlist remotes |
| WSL symlink across `/mnt/c/` boundary breaks | Low | Medium | Bootstrap script tests symlink at install time; documented troubleshooting steps |
| Vault git plugin merge conflict (concurrent user edit on focus from two laptops) | Low | Medium (could lose a focus update) | Single human writer per moment; Obsidian Git plugin's conflict UI handles the rare collision; spec §6 separates pulse-written sidecars from human-written project note so machine state never collides |
| Pulse + git hygiene queries are slow on large vaults | Low | Low | Vault size is small (10s of project notes); Dataview FLATTEN over `_pulse/` is fast under 100 sidecars |

### Off-boarding flow (data preservation)

Use the off-boarding script (spec §6.5 mechanism 6):
```bash
pulse vault offboard --vault <name>
```
Which executes:
1. Disable Obsidian Git plugin on this device for that vault.
2. Move vault to `~/vaults/_archived/<vault-name>-<date>/`.
3. `git tag <vault>-final-<date>` on the archived vault repo.
4. Remove vault entries from `~/.claude/dashboard-subscriptions.json` and `~/.claude/digest-config.yaml`.
5. Print follow-up checklist: which other devices need to repeat steps 1-2; whether to delete the GitHub remote.

Manual fallback if the script isn't available: same five steps, executed by hand.

---

## Acceptance criteria

For the **implementation PR**:

### Pre-flight
- [ ] `~/agents/scripts/migration-manifest.py` exists; running it produces a markdown manifest at `_archived/migration-manifest-<date>.md`
- [ ] The manifest is committed in the implementation PR for reviewer inspection BEFORE merge

### Code present
- [ ] `~/agents/pulse/cli.py` with `refresh`, `report`, `digest`, `audit` subcommands
- [ ] `~/agents/lib/host_resolver.py` with `is_reachable`, `read_remote`, ~5min cache
- [ ] `~/agents/templates/obsidian/{Project,Decision,Daily}.md` exist
- [ ] `~/agents/templates/sync-templates.sh` exists and works
- [ ] `~/agents/bootstrap-laptop.sh` exists (macOS / Linux / WSL — with symlink + FileVault check on macOS)
- [ ] `~/agents/scripts/vault-offboard.sh` (or equivalent `pulse vault offboard` subcommand) exists

### Behavior
- [ ] `pulse refresh` writes a sidecar at `<vault>/Projects/_pulse/<project>--<host>.md` per (project, host) it owns
- [ ] Pulse never modifies the human-edited project note (`<vault>/Projects/<name>.md`)
- [ ] Pulse SSH-reads remote hosts listed in this device's `ssh_writes` config; gracefully marks unreachable with `reachable: false, last_reachable_at: <prior>` when SSH fails
- [ ] `project --focus`, `--status`, `--blocker`, `--unblock`, `--next`, `--done`, `--question`, `--unquestion`, `--subscribe`, `--unsubscribe`, `--claim-ssh-host`, `--release-ssh-host` all reshape to mutate Obsidian frontmatter
- [ ] `decision --new`, `--outcome`, `--add-pattern`, `--add-pr`, `--add-issue`, `--add-related` all reshape to mutate Obsidian frontmatter
- [ ] `email-digest preset <name>` interactive flow (y/e/s/n) works end-to-end against Microsoft Graph
- [ ] `email-digest preset` rejects send when any project's `client:` doesn't match the preset's expected client (Codex Finding 4 / spec §6.5 mechanism 1)
- [ ] `pulse digest --all-vaults` refuses to run on a non-`jns-mac` device with an explicit error
- [ ] `pulse audit` scans all vaults; flags client-mismatch projects, sidecar/filename mismatches, off-allowlist git remotes
- [ ] `~/.claude/digest-config.yaml.example` shipped with paul-jason + personal-archive presets

### Migration
- [ ] Existing 7 project YAMLs migrated to `<vault>/Projects/<name>.md` per the manifest
- [ ] Existing 9 decision YAMLs archived to `_archived/decisions-pre-pathb/` (NOT migrated; per Q9)
- [ ] `dashboard/` and `review_session/` archived to `_archived/`
- [ ] Subscription file auto-migrates from legacy `{"subscribed": [...]}` to `{<vault>: {subscribed: [...], ssh_writes: [...]}}` on first write

### Smoke
- [ ] Daily review renders on jns-mac with the agents project showing live data from sidecar files
- [ ] `email-digest preset paul-jason` previews correctly and sends successfully (test mode)
- [ ] `pulse refresh` populates `_pulse/agents--jns-mac.md` correctly (branch / dirty / ahead / behind / stale / commits_7d / open_actions / open_issues)
- [ ] `pulse refresh` SSH-reads jns-server (Cloudflare-tunneled host) and writes `_pulse/agents--jns-server.md` (smoke test for SSH path)
- [ ] `pulse audit` returns clean against current vaults
- [ ] No leaked data — `~/.claude/dashboard-subscriptions.json` content as expected; no rogue files in any vault

### Documentation
- [ ] CLAUDE.md, PLAN.md, knowledge-surfaces.md, cross-device-state.md updated
- [ ] `cross-device-state.md` §Phase 7.2 marked superseded by pulse with SSH bundled into Path B
- [ ] All tests green: `pytest project/ action/ decision/ pulse/ email-digest/ lib/tests/ -q`

---

## Sign-off

This is a **decision-only spec PR**. No implementation code in this PR. The implementation big-bang PR follows after this spec merges, with full test coverage and a multi-layer rollback path (§11).

This spec was revised after a Codex adversarial review (2026-05-08) surfaced 5 findings:
- **F1 (subscription rendering):** subscriptions removed from Daily-review filtering; daily filters by `status` on existing project frontmatter only.
- **F2 (SSH cutover gap):** SSH support bundled into the big-bang PR (was previously deferred to a v2 follow-up).
- **F3 (concurrent frontmatter writes):** pulse model changed from shared-frontmatter writes to per-host sidecar files in `_pulse/` subfolder; each pulse owns exactly one file per (project, host) it's responsible for; concurrent collision impossible by design.
- **F4 (client isolation guardrails):** added §6.5 with 7 mechanisms (digest-preset → vault validation, `--all-vaults` jns-mac-only, pre-send confirmation context, per-vault git remote allowlist, `pulse audit`, off-boarding script, FileVault policy).
- **F5 (rollback story):** added pre-flight migration manifest committed in the implementation PR + 3-layer rollback procedure documented in §11.

After Path B implementation lands:
- A-020 (SessionStart pattern reader) remains independent in queue
- Future client onboardings (Tillamook etc.) follow §"Client onboarding procedure"
- Future architecture decisions go to `<vault>/Decisions/D-NNN.md` instead of `knowledge/decisions/*.yaml`

The system's center of gravity moves from `~/agents/knowledge/` (engineering tooling for the homegrown CLIs) to `~/vaults/<context>/` (human-and-Claude-curated knowledge surfaces) — with `~/agents/` continuing as the engineering substrate that powers it.
