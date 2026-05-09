<%*
// Project.md — Templater template for Path B project notes.
// Invoke via Templater "Create new note from template" → fill prompts.
// Frontmatter is human-edited only; pulse never writes to this file
// (it writes to <vault>/Projects/_pulse/<project>--<host>.md sidecars).

const name        = await tp.system.prompt("Project slug (lowercase, hyphens)", tp.file.title);
const host        = await tp.system.prompt("Owning host (e.g. jns-mac, vitalai-laptop)");
const client      = await tp.system.suggester(
  ["personal", "vital", "tillamook", "other"],
  ["personal", "vital", "tillamook", "other"],
  false, "Client (vault scope)");
const kind        = await tp.system.suggester(
  ["personal", "client-work", "engineering-tool", "archive"],
  ["personal", "client-work", "engineering-tool", "archive"],
  false, "Kind");
const repo_path   = await tp.system.prompt("Repo path (e.g. ~/projects/buddy)", "");
const repo_remote = await tp.system.prompt("Repo remote URL (origin)", "");
const today       = tp.date.now("YYYY-MM-DD");
const this_host   = host;  // dataview substitution below uses this
-%>
---
project: <% name %>
host: <% host %>
client: <% client %>
kind: <% kind %>
status: active
focus: ""
status_updated: <% today %>
blockers: []
next_steps: []
open_questions: []
stack: []
repo_path: "<% repo_path %>"
repo_remote: "<% repo_remote %>"
---

# <% name %>

## Purpose
*(one sentence — what this project exists for)*

## Stack
*(languages, frameworks, key dependencies)*

## Repository
- Path: `<% repo_path %>`
- Remote: `<% repo_remote %>`
<%* if (kind === "client-work") { -%>

## Client
- Contact: 
- Engagement: 
<%* } -%>

*(Add more sections — conventions, setup, key dates — only when a real need emerges.
CLAUDE.md in the repo holds AI-agent onboarding context; this page is for the
project narrative as YOU need it.)*

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
SORT created_at DESC
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
WHERE project = this.project AND host = "<% this_host %>"
```

(Multi-device git state visible in the Activity table above; the cross-project
"needs attention" rollup lives in the Daily review.)

## Notes / journal
*(your free-form area)*
