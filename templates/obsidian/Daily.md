<%*
// Daily.md — Templater template for the daily review.
// Auto-fires at 7am via launchd; queries scope to the current vault automatically.
// Filter: status = "active" — NOT this.subscribed (Codex F1 fix).

const today = tp.date.now("YYYY-MM-DD");
const now   = tp.date.now("YYYY-MM-DD HH:mm");
-%>
# <% today %>

> Generated <% now %>

## ⚠ Focus may be stale (>= 5 days)

```dataview
TABLE focus, (date(today) - date(status_updated)).days as "Days", status_updated as "Set"
FROM "Projects"
WHERE status = "active" AND (date(today) - date(status_updated)).days >= 5
SORT (date(today) - date(status_updated)).days DESC
```

## Active projects — recent activity (latest pulse, 24h rollup)

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
LIMIT 10
```

## Today's tasks

```tasks
not done
sort by priority, due
```

## Yesterday's activity

```dataview
LIST WITHOUT ID
  "**" + project + "** · " + host + " — " +
    string(closed_actions_24h) + " actions closed, " +
    string(commits_24h) + " commits"
FROM "Projects/_pulse"
WHERE (closed_actions_24h > 0 OR commits_24h > 0) AND pulled_at >= date(today) - dur("1 day")
SORT pulled_at DESC
```

## Decisions this week

```dataview
LIST FROM "Decisions"
WHERE created_at >= date(today) - dur("7 days")
SORT created_at DESC
```

## Git — needs attention

One line per (project, host) sidecar that's not clean.

```dataview
LIST WITHOUT ID
  "**" + project + "** · " + host + " · " +
    choice(dirty, "dirty · ", "") +
    choice(ahead_origin > 0, string(ahead_origin) + "↑ · ", "") +
    choice(behind_origin > 0, string(behind_origin) + "↓ · ", "") +
    choice(length(stale_local_branches) > 0,
           "stale local: " + string(length(stale_local_branches)), "")
FROM "Projects/_pulse"
WHERE dirty = true OR ahead_origin > 0 OR behind_origin > 0 OR length(stale_local_branches) > 0
SORT pulled_at DESC
```

## Reachability — sidecars stale or unreachable

```dataview
LIST WITHOUT ID
  "**" + project + "** · " + host + " · " +
    choice(reachable = false,
           "unreachable since " + last_reachable_at,
           "stale: " + pulled_at)
FROM "Projects/_pulse"
WHERE reachable = false OR pulled_at < date(today) - dur("1 day")
```

---

## Notes
*(free-form)*
