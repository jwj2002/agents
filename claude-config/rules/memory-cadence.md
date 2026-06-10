---
description: "Monthly memory doctor + archive + readout routine (manual, ~5 min)"
paths: ["**/memory/**", "**/memory-autoinject*"]
---

# Memory Lifecycle Cadence

Monthly routine (manual, ~5 minutes). Run on the first of each month or when
`memory doctor` is mentioned in a planning session.

## Step 1 — Check store health

    memory doctor

Review: dead pointers, unindexed files, TTL candidates. Note cold% and
active-recall% from the metrics block.

## Step 2 — Preview archives (dry-run)

    memory archive

Review which facts would move. If any surprise entries appear, inspect them
first (`memory recall <name>`).

## Step 3 — Apply (if comfortable)

    memory archive --apply

Facts move to `<project>/memory/archive/` — they are preserved, never deleted.

## Step 4 — Check injection telemetry

    memory readout

Review facts_injected trend, active-recall%, top-skipped topics. If cold% from
`doctor` is above 40% for the store, fact files are not being refreshed —
consider archiving stale perishables or re-tagging facts with shorter TTLs.

## Notes

- No cron or daemon required. Write volume (~2-3 facts/day) does not justify
  automation.
- write:read metric is deferred until a reliable session-level read signal is
  available. Use active-recall% as the proxy.
- The global `memory doctor` checks ALL projects. Use `--project <substr>` to
  focus on one.
- cold% in `memory doctor` is mtime-based: fact files whose mtime is older than
  90 days / total fact files. A high cold% means facts exist but are not being
  updated — a candidate for archiving.
- injection coverage in `memory readout` (avg facts_injected / facts_total per
  session) shows what fraction of the store's indexed facts are actually reaching
  sessions. Low coverage with low active-recall% together indicate a retrieval gap.
