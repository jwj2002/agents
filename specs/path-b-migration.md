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

### Q7 — Phase 7.2 SSH bridge: separate follow-up

| Decision | **Pulse v1 (in big-bang PR) is local-only. Pulse v2 (SSH support for jbox06 / et01 / spark / jns-server) is an immediate follow-up PR within ~1 week.** |
|---|---|
| Why | Splits scope: v1 is the architectural migration; v2 is host_resolver + SSH error handling + cache layer + tests. Each PR has a clean review surface. Until v2 lands, projects with `host: <non-local>` render with a `⚠ pending pulse v2 SSH support` placeholder gracefully. |
| How to apply | Pulse v1 reads project frontmatter; if `host == get_host_name()` (or repo path is local), refreshes; otherwise emits `reachable: deferred-pulse-v2` and continues. Pulse v2 follows the design in `specs/cross-device-state.md` §"Phase 7.2 sketch". |

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

### Q11 — Project page structure: single page, two halves

| Decision | **One project note per project at `<vault>/Projects/<name>.md`. Body has two halves separated by `---`:**<br>• **Top half (overview)** — manually written + Claude-assisted, auto-populated from `<repo>/CLAUDE.md` when present. Near-static.<br>• **Bottom half (operational)** — pulse + Dataview rendered. Live data. |
|---|---|
| Why | Single source of truth per project. Open `[[agents]]` → see purpose → scroll to see live state. No navigation cost. Pulse never touches the overview half (additive frontmatter writes only). |
| How to apply | Templater "New Project" command generates a templated page with both halves. CLAUDE.md auto-populate (best-effort regex extraction of stack/setup sections). See §7 for full template. |

### Q12 — Daily review scope: operational + git hygiene only

| Decision | **The Daily note never repeats overview content. It surfaces only operational state and git hygiene that needs attention. Empty sections render as nothing (no noise).** |
|---|---|
| Why | Overview is "what is this?" — read once per project. Daily review is "where are things right now?" — read every day. Mixing them adds visual clutter to the daily ritual. |
| How to apply | Daily review template's Dataview queries pull only operational and git-state frontmatter fields. Overview-half content is structurally separated by the `---` rule and never queried by the daily review. |

### Q13 — Git hygiene tracking: per-device frontmatter

| Decision | **Pulse on each device collects git state for each subscribed project's repo and writes to `git_state.<this-hostname>` in the project's frontmatter (additive — preserves other devices' entries). Daily review surfaces non-clean states across all devices via a "Git hygiene" Dataview block.** |
|---|---|
| Why | Multi-device git cleanliness is a real ongoing concern. Showing per-device branch / ahead / behind / dirty / stale-local-branches surfaces "I committed on vitalai-laptop but never pushed; jns-mac is now N behind" as a punch list of cleanup actions. |
| How to apply | See §6 for `git_state` schema and pulse commands. See §7 for the Daily review's Git hygiene Dataview block. |

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

## Pulse design (v1 local-only)

### Responsibilities

1. For each subscribed project on each vault this device opens, refresh the corresponding `<vault>/Projects/<name>.md` frontmatter with current repo state.
2. Compute derived fields: `focus_drift_days`, `commits_24h`, `commits_7d`, `open_actions`, `open_issues`.
3. Collect per-device git hygiene state into `git_state.<this-hostname>`.
4. Render reports and digests via the same data.

### Data shape (project frontmatter after pulse refresh)

```yaml
---
# Manually edited (pulse never touches these)
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

# Pulse-managed (additive; rewritten on every refresh)
last_commit_at: 2026-05-08T16:18:35Z
last_commit_subject: "feat(dashboard,action): split open/closed sections"
last_commit_sha: "8549609"
commits_24h: 8
commits_7d: 14
open_actions: 1
closed_actions_24h: 6
open_issues: 14
closed_issues_24h: 3
focus_drift_days: 2                # computed: now - status_updated, in days
pulse_at: 2026-05-08T16:30:00Z

# Per-device git state (additive; preserves other devices' entries)
git_state:
  jns-mac:
    pulled_at: 2026-05-08T16:30:00Z
    branch: main
    last_commit: "8549609 — feat(dashboard,action): split open/closed"
    ahead_origin: 0
    behind_origin: 0
    dirty: false
    stale_local_branches: []
    unpushed_branches: []
  vitalai-laptop:                  # written by THAT device's pulse
    pulled_at: 2026-05-08T08:15:00Z
    branch: feature/issue-201
    last_commit: "c8f4d23 — wip: pool exhaustion fix"
    ahead_origin: 3
    behind_origin: 0
    dirty: true
    stale_local_branches: ["feature/issue-150-host-field"]
    unpushed_branches: ["feature/issue-201"]
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

### Failure modes (v1)

| Mode | Behavior |
|---|---|
| Repo not found at expected path | Skip silently; mark `git_state.<host>: { reachable: false, reason: "no-clone" }` |
| `gh` unauthenticated | Skip GH issue counts; project page renders without those fields |
| `git` command timeout (>5s) | Skip that field; preserve previous frontmatter value; mark `pulse_at` with the partial-state time |
| ACTIONS.md missing or malformed | Mark `actions: error` in frontmatter; preserve other fields |
| Concurrent vault sync write | Obsidian Git plugin's conflict handler; rare since pulse writes are tiny additive frontmatter mutations |

### Unreachable hosts (placeholder until pulse v2)

For projects with `host:` other than `get_host_name()`:
- Pulse v1 emits `git_state.<remote-host>: { reachable: deferred-pulse-v2 }`.
- Project page renders "⚠ pending pulse v2 SSH support — see specs/cross-device-state.md §Phase 7.2".
- No data lost; v2 fills it in.

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
*(one sentence — what is this for?)*

## Why it exists
*(1-3 paragraphs — origin, problem, goals)*

## Stack & dependencies
- Language(s): <%= stack_languages %>
- Key libs:
- External:

## Repository
- Path: `<%= repo_path %>`
- Remote: `<%= repo_remote %>`
- Branch model:
- CI:

## Conventions
*(commit format, test layout, deployment, etc.)*

## Setup / quickstart
```bash
*(clone, install, run)*
```

## Common commands
| Task | Command |
|---|---|

## Architecture notes
*(high-level — major components, key decisions, trade-offs)*

## Onboarding for AI agents working here
- [ ] Read [CLAUDE.md](<%= repo_path %>/CLAUDE.md) at repo root
- [ ] Run tests to confirm clean state
- [ ] Check `ACTIONS.md` for current open work

## Reference links
*(specs, related repos, docs)*

<%* if (kind === "client-work") { %>
## Client info
- **Client**: <%= client %>
- **Engagement**: 
- **Primary contact**: 
- **My role**: 

## Key dates
- Kickoff: 
- Major milestones: 
- Contract end / renewal: 

## Access requirements
- VPN: 
- SSH host: 
- GitHub account context: 
- Special credentials: *(meta only — never the creds themselves)*

## Communication channels
- Slack:
- Standup cadence:
<%* } %>

<%* if (kind === "personal") { %>
## Audience / users
*(who uses this?)*

## Distribution
*(where it ships)*

## Roadmap
*(high-level direction)*
<%* } %>

---

## Status (live)

> Last pulse: `<%- tp.frontmatter.pulse_at %>` · Reachable: `<%- tp.frontmatter.git_state[tp.user.host()] ? "✓" : "⚠" %>`

```dataview
TABLE WITHOUT ID
  string(this.status).toUpperCase() as "Status",
  this.host as "Host",
  this.focus as "Focus",
  string(this.focus_drift_days) + "d" as "Focus Drift"
FROM ""
WHERE file.name = this.file.name
```

## Recent activity (7d)

```dataview
TABLE commits_7d as "Commits", closed_actions_24h as "Closed (24h)", open_actions as "Open Actions"
FROM ""
WHERE file.name = this.file.name
```

## Open work

### Open actions
*(rendered from <repo>/ACTIONS.md by pulse — see project frontmatter)*

### Open GitHub issues
*(count surfaced via pulse; full list via `gh issue list -R <slug>`)*

## Decisions linked

```dataview
LIST FROM "Decisions"
WHERE project = this.project
SORT created DESC
LIMIT 5
```

## Git state across devices

```dataview
TABLE WITHOUT ID
  key as "Device",
  value.pulled_at as "Pulled",
  value.branch as "Branch",
  string(value.ahead_origin) + "↑ / " + string(value.behind_origin) + "↓" as "↑↓",
  value.dirty as "Dirty",
  join(value.stale_local_branches, ", ") as "Stale"
FROM ""
WHERE file.name = this.file.name
FLATTEN this.git_state as state
GROUP BY state
```

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

Auto-fires at 7am via launchd. Fully auto-rendered; user edits the bottom Notes section.

```markdown
# <%= today %>

> Generated <%= now %> · last pulse: <%- tp.user.last_pulse() %>

## ⚠ Focus may be stale (>= 5 days)

```dataview
TABLE focus, focus_drift_days as "Days", commits_7d as "Commits since"
FROM "Projects"
WHERE status = "active" AND focus_drift_days >= 5
SORT focus_drift_days DESC
```

## Active projects — recent activity (24h)

```dataview
TABLE host, focus, last_commit_subject as "Last commit", commits_24h as "↑24h", open_actions as "Open"
FROM "Projects"
WHERE status = "active" AND contains(this.subscribed, file.name)
SORT last_commit_at DESC
```

## Today's tasks

```tasks
not done
sort by priority, due
```

## Yesterday's activity

```dataview
LIST WITHOUT ID
  "**" + file.link + "** — " + closed_actions_24h + " actions closed, " + commits_24h + " commits"
FROM "Projects"
WHERE closed_actions_24h > 0 OR commits_24h > 0
```

## Decisions this week

```dataview
LIST FROM "Decisions"
WHERE created_at >= dateadd(date(today), -7, "days")
SORT created_at DESC
```

## Git hygiene — needs attention

```dataview
TABLE WITHOUT ID
  file.link as "Project",
  device as "Device",
  state.branch as "Branch",
  (string(state.ahead_origin) + "↑ " + string(state.behind_origin) + "↓") as "↑↓",
  state.dirty as "Dirty",
  join(state.stale_local_branches, ", ") as "Stale"
FROM "Projects"
FLATTEN this.git_state as state, key(this.git_state) as device
WHERE state.dirty = true
   OR state.ahead_origin > 0
   OR state.behind_origin > 0
   OR length(state.stale_local_branches) > 0
SORT state.pulled_at DESC
```

## Reachability (last pulse)

```dataview
TABLE pulse_at, host
FROM "Projects"
WHERE status = "active" AND contains(this.subscribed, file.name)
SORT pulse_at DESC
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
  "JNS-Personal-Vault": ["agents", "buddy", "paul-jason"],
  "Vital-Work-Vault": ["vital-app-a"],
  "Tillamook-Work-Vault": ["tillamook-app-x"]
}
```

**Per-machine** (not synced; each device has its own scope).

**Backwards compatibility**: if pulse encounters a legacy `{"subscribed": [...]}` shape on first read, it auto-rewrites as `{"JNS-Personal-Vault": [...]}` on next write.

**Single-vault devices** (e.g. `vitalai-laptop`): the JSON may have other vault keys (left over from sync of subscription edits made on jns-mac); pulse only consults the active vault key. No leakage.

**Mutation**: `project <name> --subscribe` (vault implied by current cwd or active Obsidian vault); `project <name> --unsubscribe` to remove. The `dashboard-subscriptions.json` is the source of truth.

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

## Migration plan (big-bang single PR)

### Implementation PR scope

```
specs/path-b-migration.md                # this spec (already merged)

# New
~/agents/pulse/cli.py                    # pulse v1 (local-only)
~/agents/pulse/tests/test_cli.py
~/agents/templates/obsidian/Project.md
~/agents/templates/obsidian/Decision.md
~/agents/templates/obsidian/Daily.md
~/agents/templates/sync-templates.sh
~/agents/bootstrap-laptop.sh             # one-time per device
~/.claude/digest-config.yaml.example     # template; user copies + edits

# Reshaped
~/agents/project/cli.py                  # mutate Obsidian frontmatter
~/agents/project/tests/test_cli.py       # update for new I/O
~/agents/decision/cli.py                 # mutate Obsidian frontmatter
~/agents/decision/tests/test_cli.py      # update for new I/O
~/agents/email-digest/cli.py             # add preset + interactive flow

# Archived (git mv to _archived/)
~/agents/dashboard/                      # retire entirely
~/agents/review_session/                 # retire entirely
~/agents/knowledge/projects/             # archived; Obsidian is source
~/agents/knowledge/decisions/            # archived; Obsidian is source

# Updated
~/agents/CLAUDE.md                       # reflect new architecture
~/agents/PLAN.md                         # mark Path B complete
~/agents/specs/knowledge-surfaces.md     # update for projects/decisions migration
~/agents/specs/cross-device-state.md     # update Phase 7.2 status (now pulse v2)
~/agents/lib/project_resolver.py         # legacy subscription auto-migrate
```

### Migration steps (in PR order)

1. **Branch** from `origin/main`. Rename to `feature/issue-XXX-path-b-implementation`.
2. **Vault scaffold** for JNS-Personal-Vault (manual: `mkdir ~/vaults/jns-personal && obsidian://createVault`). Other vaults follow per-engagement.
3. **One-shot script** converts `knowledge/projects/*.yaml` → `<vault>/Projects/*.md` (frontmatter + body skeleton). Body's overview half left blank for user / Claude to populate; operational half includes Dataview placeholders.
4. **Archive** old YAMLs: `git mv knowledge/projects _archived/projects-pre-pathb`, `git mv knowledge/decisions _archived/decisions-pre-pathb`.
5. **New code**: pulse v1 + new email-digest preset/interactive flow + reshaped project/decision CLIs.
6. **Templates**: copy templates to `~/agents/templates/obsidian/`. Run `sync-templates.sh` to populate vaults.
7. **Bootstrap**: write `bootstrap-laptop.sh` for one-time device setup.
8. **Archive retired CLIs**: `git mv dashboard _archived/dashboard`, `git mv review_session _archived/review_session`.
9. **Update docs**: CLAUDE.md, PLAN.md, knowledge-surfaces.md, cross-device-state.md.
10. **Tests**: full suite green (project + action + email-digest + pulse). Smoke against real data on jns-mac.
11. **Open PR**, code review, merge.

### Rollback procedure

The implementation PR is a single squash-merge commit. Rollback = `git revert <commit-sha>`. After revert:
- YAMLs restored from `_archived/`
- Retired CLIs restored from `_archived/`
- Existing per-repo ACTIONS.md still works (action CLI unchanged)
- Vault data is preserved (lives outside the agents repo, in `~/vaults/`)

Loss on revert: pulse-populated frontmatter on Obsidian project notes is now stale; manual cleanup or re-run pulse after fix-forward.

---

## Out of scope (explicit)

| Item | Reason |
|---|---|
| **Pulse v2 SSH bridge** | Separate PR within ~1 week of implementation PR (Q7). Spec for SSH support already exists in `cross-device-state.md` §Phase 7.2. |
| **iPad / iPhone sync** | Requires Obsidian Sync ($96/yr); deferred until mobile capture friction is felt. v1 is desktop-only via Obsidian Git plugin. |
| **A-020 SessionStart → YAML pattern reader** | Independent piece of work (specs/knowledge-surfaces.md follow-up); doesn't depend on Path B. |
| **Migrating existing 9 decisions** | Archived only; not migrated (Q9). Old decisions stay in `_archived/decisions-pre-pathb/`. |
| **Patterns / learning rules to Obsidian** | Stay as YAML in `~/agents/knowledge/`; tooling input, not human-browse data. |
| **Auto-emailing on a schedule** | v1 is manual trigger only with review-before-send (Q10). Cron-based scheduling can be added later. |
| **Obsidian Sync purchase** | User chose git backup for v1; revisit when iPad capture is wanted. |
| **Auto-update GH issue ↔ action linkage** | Out of scope; remains a manual `--issue` flag on `action --new`. Could be a follow-up if the gap is felt. |

---

## Risks + mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Pulse v1 has a bug that scrambles frontmatter | Medium | Low (frontmatter is regenerable; body is user-edited and preserved) | Pulse writes are atomic (tmpfile + os.replace); test coverage on additive frontmatter merging; manual `pulse refresh --project X` in case |
| Obsidian Git plugin merge conflict on a project frontmatter | Low | Medium (could lose a focus update) | Pulse mutates additively (one device writes one `git_state.<host>:` key; other devices preserved); user-edited fields rarely change concurrently |
| Migration script misformats a project YAML → Obsidian markdown | Low | Medium | Spec'd in §"Migration steps"; one-shot script tested on copy of YAMLs; easy fix-forward |
| Templater + Dataview update breaks a query | Medium | Low (queries fail silently or render empty) | Pin plugin versions; document upgrade procedure |
| User accidentally types client work into wrong vault | Low | High (confidentiality) | Vault status visible in Obsidian title bar; templates display vault name in note frontmatter |
| WSL symlink across `/mnt/c/` boundary breaks | Low | Medium | Bootstrap script tests symlink at install time; documented troubleshooting steps |
| pulse v1 + git hygiene queries are slow on large vaults | Low | Low | Vault size is small (10s of project notes); negligible |

### Off-boarding flow (data preservation)

When a client engagement ends:
1. Disable Obsidian Git on client laptop for that vault.
2. Move vault on jns-mac to `~/vaults/_archived/<client>-<date>/`.
3. Mark frozen: `git tag <client>-final-<date>` on the vault repo.
4. Remove subscription entries.
5. Optional: delete client laptop's local vault per client policy.

---

## Acceptance criteria

For the **implementation PR** that follows:

- [ ] `~/agents/pulse/cli.py` exists with `refresh`, `report`, `digest` subcommands
- [ ] `pulse refresh` updates project frontmatter with the schema in §6 (last_commit, commits_24h/7d, open_actions, open_issues, focus_drift_days, git_state.<host>)
- [ ] Templater templates exist at `~/agents/templates/obsidian/{Project,Decision,Daily}.md`
- [ ] `~/agents/templates/sync-templates.sh` copies masters into each vault's `_templates/`
- [ ] `bootstrap-laptop.sh` covers macOS, native Linux, and WSL (with symlink for the latter)
- [ ] `project --focus`, `--status`, `--blocker`, `--unblock`, `--next`, `--done`, `--question`, `--unquestion`, `--subscribe`, `--unsubscribe` all reshape to mutate Obsidian frontmatter
- [ ] `decision --new`, `--outcome`, `--add-pattern`, `--add-pr`, `--add-issue`, `--add-related` all reshape to mutate Obsidian frontmatter
- [ ] `email-digest preset <name>` interactive flow (y/e/s/n) works end-to-end against Microsoft Graph
- [ ] `~/.claude/digest-config.yaml.example` shipped with paul-jason + personal-archive presets
- [ ] Existing 7 project YAMLs migrated to `<vault>/Projects/<name>.md`
- [ ] Existing 9 decision YAMLs archived to `_archived/decisions-pre-pathb/`
- [ ] `dashboard/` and `review_session/` archived to `_archived/`
- [ ] CLAUDE.md, PLAN.md, knowledge-surfaces.md, cross-device-state.md updated
- [ ] All tests green: `pytest project/ action/ decision/ pulse/ email-digest/ -q`
- [ ] Smoke: full daily-review render on jns-mac with the agents project showing live data
- [ ] Smoke: `email-digest preset paul-jason` previews and (test mode) sends successfully
- [ ] Smoke: `git_state.jns-mac` populated correctly with current branch / dirty / ahead / behind / stale
- [ ] Subscription file auto-migrates from legacy `{"subscribed": [...]}` to `{"JNS-Personal-Vault": [...]}` on first write
- [ ] No leaked data — `~/.claude/dashboard-subscriptions.json` content unchanged otherwise; no rogue files in any vault

For the **pulse v2 PR** (separate, within ~1 week):

- [ ] `lib/host_resolver.py` exists per `cross-device-state.md` §Phase 7.2 sketch
- [ ] Pulse SSH-reads project state from non-`get_host_name()` hosts
- [ ] Cache layer (~5 min TTL) prevents per-render SSH cost
- [ ] Graceful degradation when host unreachable (renders placeholder, doesn't crash)
- [ ] Per-device `git_state.<remote-host>` populated correctly via SSH
- [ ] Tests cover: reachable, unreachable, timeout, malformed config

---

## Sign-off

This is a **decision-only spec PR**. No implementation code in this PR. The implementation big-bang PR follows after this spec merges, with full test coverage and a single-commit revert path for rollback.

After Path B implementation lands:
- Pulse v2 (SSH bridge) follows within ~1 week
- A-020 (SessionStart pattern reader) remains independent in queue
- Future client onboardings (Tillamook etc.) follow §"Client onboarding procedure"
- Future architecture decisions go to `<vault>/Decisions/D-NNN.md` instead of `knowledge/decisions/*.yaml`

The system's center of gravity moves from `~/agents/knowledge/` (engineering tooling for the homegrown CLIs) to `~/vaults/<context>/` (human-and-Claude-curated knowledge surfaces) — with `~/agents/` continuing as the engineering substrate that powers it.
