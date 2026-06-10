# Coordinator Spec — Per-Domain Coordinators + Shared Portfolio

**Status**: PROPOSED — handed to the ~/agents session owner for implementation
**Author**: drafted with Jason, 2026-06-10 (superior project session)
**Tier**: COMPLEX (new protocol, cross-cutting) → per ~/agents velocity rules,
produce a lightweight code-reality manifest before drafting code; aim ≤2 review rounds.

---

## 1. Problem

Jason runs one Claude session per project folder. Per-project memory
(`~/.claude/projects/<project>/memory/`) works well — it is curated, fresh, and
owned by the session that touches it. What's missing is the layer above:
an agent that can see across all projects to coordinate priorities, deadlines,
and dependencies.

Evidence that hand-curated cross-project state rots: `knowledge/projects/superior.yaml`
sat at `focus: ""`, `updated_at: 2026-05-08` while the project's own session
memory stayed rich and current through a release cycle. Nothing that requires
manual upkeep by "nobody's session" survives.

Additional constraint: work content (Superior/VitalAI/Maison summaries) must
not accumulate in the personal-account repo. Work and personal domains map to
the work laptop and home laptop respectively.

## 2. Decisions already made (do not relitigate without Jason)

| # | Decision | Rationale |
|---|---|---|
| D1 | **Two coordinators, one per domain** (work, personal) — not one global | Governance boundary matches the two-account setup; each coordinator can only deeply read project memories on its own machine anyway |
| D2 | **Infra is shared and lives in ~/agents; data is separate per domain** | Jason 2026-06-10: "The data is separate. The infrastructure support for the coordinator should be the same and managed from git. Otherwise I end up with drift." One implementation, two deployments |
| D3 | **Federation = shared portfolio file(s)**, not live digest exchange | Jason picked the portfolio-file option. ai-channels digests are a possible later enhancement, not in scope |
| D4 | **Coordinators auto-write their own portfolio section** at session end | Jason 2026-06-10. Manual curation is the rot pattern (see §1) |
| D5 | **Derived views are never committed** — regenerated per session | Committed derived state bloats diffs and goes stale; the rebuild is cheap |
| D6 | **Work data repo remote = private GitHub under `jjob-spec`** | Jason 2026-06-10. Unattended pushes must work from anywhere; laptop cannot reach internal GitLab; credential pattern proven by ai-channels. Use a username-qualified remote (`https://jjob-spec@github.com/...`) per `github-accounts.md` |
| D7 | **Retire `knowledge/projects/*.yaml` after migrating vaultiq's payload** | Jason 2026-06-10. Usage audit: 9 commits ever (all infra), both files content-frozen since 2026-05-08, superior.yaml empty through its busiest month. vaultiq.yaml's rich snapshot (focus narrative + 5 next_steps + 2 open_questions) migrates to vaultiq's project memory / ACTIONS.md first — zero information loss. Dashboard/`project` skills then read coordinator data (Phase 4) |
| D8 | **The coordinator runs where the sessions run; sweep is local-only** | Jason 2026-06-10: all work development happens from agent sessions on the work laptop (revisit if that changes — a best-effort SSH sweep of jbox06 with timeout+cache is the designed escape hatch). Personal sessions run on a server Jason tmuxes into → the personal coordinator runs ON that server (`profile=personal`); the home laptop is a terminal |
| D9 | **Machine→domain mapping lives in `machines/<profile>/config.toml`** as a `[coordinator]` section | Jason 2026-06-10. Reuses the existing profile mechanism applied by `install-all.sh`; versioned; new-machine bootstrap inherits coordinator wiring. Generalize the file's header comment (currently obsidian-agent-scoped) rather than forking |

## 3. Architecture overview

```
~/agents/  (shared infra repo — jwj2002, synced to BOTH laptops)
  coordinator/                  ← NEW: all coordinator CODE + templates
    bin/ or lib/                  (CLI: rebuild, event-append, portfolio-update)
    templates/                    (AGENTS.md template for a domain data repo)
    schema/                       (event JSONL schema, portfolio section schema)
  knowledge/portfolio/          ← NEW: the shared portfolio DATA (the one
    work.md                       cross-domain artifact; sanitized by rule §7)
    personal.md
  docs/coordinator-spec.md      ← this file

<domain data repo>  (one per domain — NOT in ~/agents)
  work:     ~/coordinator-data/ on the WORK LAPTOP
            → private GitHub repo under jjob-spec (D6), username-qualified remote
  personal: ~/coordinator-data/ on the PERSONAL SERVER (where sessions run, D8)
            → private remote under jwj2002
  AGENTS.md                     ← instantiated from template; domain config
  memory/                       ← coordinator's CURATED cross-project facts
  events/
    events-<hostname>.jsonl     ← append-only event shards
  dashboard.md                  ← derived, GITIGNORED (D5)
```

Placement rule (D8): each coordinator runs on the host where that domain's
agent sessions actually run — work laptop for work, the tmux server for
personal. Its sweep is therefore always local; no remote sweeping in v1.
Machine→domain resolution: `[coordinator]` section in
`machines/<profile>/config.toml` (D9) — `domain`, `data_repo`, portfolio path —
applied at install time by `install-all.sh`.

The coordinator session runs in the domain data repo directory (so its
project-memory dir, CLAUDE.md/AGENTS.md, and hooks are domain-scoped), but all
executable behavior comes from `~/agents/coordinator/` — the data repo contains
no logic. Same pattern as claude-config: source of truth in ~/agents, deployed
by `install.sh`-style wiring.

**Implementation note (D2 corollary):** any script, hook, or prompt the
coordinator needs lives in `~/agents/coordinator/` and is invoked by path or
symlink from the data repo. If the implementer finds themselves writing logic
into the data repo, that's drift — stop and move it.

## 4. The three memory layers (per coordinator)

### 4.1 Derived layer — rebuilt every session, never authoritative

On SessionStart (hook) the coordinator:

1. `git pull` on ~/agents (picks up the other domain's portfolio section) and on its data repo.
2. Sweeps, for every local project:
   - `~/.claude/projects/<project>/memory/MEMORY.md` (index lines only — never bulk-inject fact bodies)
   - state_manager project state (`active_work`: issue/branch/phase/last_action)
   - `git log --since=<last session>` across `~/projects/*` (and jbox06 app repos where configured)
   - open `ACTIONS.md` items where present
3. Renders `dashboard.md` (gitignored). The existing `dashboard` skill is the
   starting point — extend it rather than building parallel rendering.

Depth on demand: when the coordinator needs detail on one project, it reads
that project's fact files directly. Index-first, bodies-as-needed.

### 4.2 Event log — append-only, the temporal record

Each **project session** (not the coordinator) appends one line at session end
via the existing Stop/state_manager hook chain:

```json
{"ts": "2026-06-10T17:42:00Z", "project": "superior", "machine": "<hostname>",
 "type": "released|shipped|decided|blocked|unblocked|milestone|note",
 "summary": "one sentence, telegraphic", "refs": ["issue#130", "commit 4576f0b"]}
```

- One shard per machine (`events-<hostname>.jsonl`) — single writer per file,
  no merge conflicts. `.gitattributes`: `*.jsonl merge=union` as backstop.
- Hook commits + pushes the shard (single-file commit; failure to push is
  non-fatal — next session's push carries it).
- The coordinator reads the union of shards sorted by `ts`. This answers
  "what changed since X" without any graph/vector infrastructure, and is the
  ingestion source if a temporal store is ever wanted later.
- Emission must be **automatic and low-bar**: if a session ends without a
  noteworthy event, emit nothing (no noise quota).

### 4.3 Curated layer — small by construction

The coordinator's own memory holds ONLY facts that exist *between* projects:

- relative priorities ("superior v0.7a release trumps all until 2026-06-15")
- cross-project dependencies ("ai-channels protocol change blocks mcp-server")
- external commitments with dates ("status email to Paul Fridays")
- people/context ("Dave = superior customer; Paul = platform owner")

**Membership test**: if a candidate fact names only one project, it belongs in
that project's memory — reject it here. Reuse the existing memory file format
+ frontmatter convention (`~/.claude/CLAUDE.md` §Memory Frontmatter) and
`~/agents/bin/memory` tooling so doctor/archive/recall work unchanged.

## 5. Ownership matrix

| Artifact | Writer | Readers |
|---|---|---|
| Project memory (`~/.claude/projects/<p>/memory/`) | That project's session ONLY | Same-machine coordinator (read-only) |
| Event shard `events-<host>.jsonl` | Project-session end hook on that host | Both: domain coordinator; (other domain never reads it) |
| Coordinator curated memory | That domain's coordinator | That coordinator |
| `knowledge/portfolio/<domain>.md` | That domain's coordinator ONLY (D4) | Both coordinators |
| `dashboard.md` | Rebuilt by SessionStart; never committed | That coordinator + Jason |
| Tracker YAMLs (`knowledge/projects/*.yaml`) | Hook-written going forward (see §9 open item) | Dashboard skill |

A coordinator NEVER writes another domain's portfolio section, NEVER writes
project memory, and NEVER copies project facts into its curated store.

## 6. Portfolio contract

One file per domain under `~/agents/knowledge/portfolio/` — separate files so
the two writers can never conflict (same trick as event shards). Suggested
shape (implementer may adjust; keep it diff-able and under ~30 lines each):

```markdown
# Portfolio — work
updated: 2026-06-10T17:45:00Z by coordinator@<hostname>

## Priorities (ordered)
1. superior — v0.7a customer release 2026-06-15; version/0.8 continues as dev
2. docketiq — <one line>

## Dated commitments
- 2026-06-15: superior v0.7a release day (Dave)
- every Friday: status email to Paul

## Load
~N active projects; heaviest: superior
```

Auto-write protocol (D4): at coordinator session end, the coordinator rewrites
its own file from current knowledge, commits with message
`portfolio(<domain>): update`, pushes. Pull happens at the other side's next
SessionStart. Eventual consistency is acceptable; the portfolio carries
calendar-grade facts, not operational state.

## 7. Content governance (the firewall)

Only these may appear in `~/agents` (the personal-account repo) from the work
domain: **project codenames, dates, priority ordering, one-line statuses**.
Never: customer data, credentials, financial figures, document contents,
internal hostnames beyond what ~/agents already contains. The portfolio
template should carry this rule as a comment at the top of each file.

The work domain's full-fidelity state (curated memory, events) lives in the
work data repo on a work-appropriate remote — that's the D2 split doing its job.

## 8. Implementation phases (each leaves the system usable)

1. **Phase 1 — event emission.** Schema + append helper in
   `~/agents/coordinator/`; wire into the existing session-end hook; shards
   committed/pushed. Acceptance: end a superior session, see the event line
   land in the work data repo.
2. **Phase 2 — coordinator bootstrap.** Data-repo template (AGENTS.md, layout,
   gitignore), SessionStart rebuild producing `dashboard.md` from §4.1 inputs.
   Acceptance: cold-start a coordinator session on the work laptop; dashboard
   lists all local projects with last-activity + active_work; asking a depth
   question makes it read the right project's fact files.
3. **Phase 3 — portfolio.** Template + auto-write-on-end + pull-on-start.
   Acceptance: work coordinator writes `portfolio/work.md`; home coordinator
   (or a simulated second clone) reads it after pull.
4. **Phase 4 — hygiene + tracker retirement.** `memory doctor`-style checks
   for the coordinator store (membership-test violations, stale dated
   commitments past their date); migrate vaultiq.yaml's payload and retire
   `knowledge/projects/*.yaml`, pointing the `dashboard`/`project` skills at
   coordinator data (D7).

Phases 1–2 deliver most of the value; 3–4 can trail.

## 9. Open items for the implementer

The four originally-open decisions are now settled — see D6–D9 in §2. What
remains is implementation detail:

- **Tracker migration (per D7)**: move `knowledge/projects/vaultiq-platform.yaml`'s
  payload into vaultiq's project memory / ACTIONS.md before removing the
  mechanism; update the `dashboard` and `project` skills to read coordinator
  data (Phase 4). `superior.yaml` is empty — delete outright.
- **Mode-2 freshness display**: with a local-only sweep (D8), jbox06-hosted
  projects show last-event/last-memory-touch recency instead of last-commit.
  Acceptable per Jason; if work patterns change, the upgrade path is a
  best-effort SSH sweep with ~5s timeout + cached as-of snapshot.
- **Personal server bootstrap**: the tmux server installs `~/agents` with
  `profile=personal`; verify `install-all.sh` runs cleanly there (it has
  historically targeted laptops; `bootstrap-laptop.sh` may need a sibling or
  a rename).
- **Per-project memory health on the dashboard (Phase 2/4)**: the §4.1 sweep
  already opens each project's `MEMORY.md`; surface a one-line health signal per
  project using the `~/agents/bin/memory` tooling shipped in #429–#431 — cold%
  (>30d), active-recall%, dead pointers, unindexed facts (`memory doctor` /
  `memory readout`). This is the agreed home for memory-health automation: a
  standalone per-session doctor-nudge was rejected because it would touch
  per-project mechanics (§10) and "nobody's session" upkeep rots (§1) — the
  coordinator is the cross-project health surface, so the signal lives here.
  Surfacing only; archiving stays a human-reviewed `memory archive --apply`,
  never automatic.
- **Coordinator refresh trigger (availability)**: capture is coordinator-independent
  (events emit from project-session hooks, §4.2), so an absent coordinator loses
  no data — but **synthesis** (sweep → rebuild `dashboard.md` → auto-write the
  portfolio section, D4 → memory-health check) only happens when a coordinator
  session runs. If that depends on Jason manually starting one, the portfolio
  rots exactly like §1 (`superior.yaml`) — the rot risk moved up a level, not
  removed. Split the two: the **non-interactive synthesis** (`git pull` + sweep +
  portfolio write + health) must run on a **schedule** (cron/timer), not only on
  manual session start; the interactive coordinator session is then for
  asking/briefing, not the sole path to a fresh portfolio. D4's session-end
  write stays as one trigger; the scheduled job is the other. (Personal is
  partly covered by the always-on tmux server per D8; the work laptop is not.)

## 10. Explicitly out of scope

- Live digest exchange over ai-channels (future enhancement; D3)
- Vector/embedding recall and temporal-graph stores (revisit only when the
  event log is large enough that grep hurts — the JSONL is the migration path)
- Any change to per-project memory mechanics (they work; don't touch)
- Multi-user / team coordination (this is single-operator, two-domain)
