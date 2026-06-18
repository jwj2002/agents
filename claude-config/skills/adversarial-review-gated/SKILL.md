---
name: adversarial-review-gated
description: Run an adversarial review as a non-blocking pipeline gate — try Codex first, and on any Codex fault (rate-limit, timeout, auth, sandbox/runtime error) fall back to a fresh-context internal adversarial review. NEVER block the pipeline on Codex availability; always write a verdict to a writable path and return RISK + PROCEED/REVISE. Use in autonomous/orchestrate runs where review must happen but Codex may be unavailable.
---

# adversarial-review-gated

`/codex:adversarial-review` is review-only and assumes Codex is reachable: it
runs Codex and returns the output verbatim. It has **no fallback** — if Codex
is rate-limited, timing out, unauthenticated, or sandbox-denied, the review
step stalls or fails, which in an autonomous pipeline silently drops the review
gate. This skill wraps that gap: Codex-first, internal-fallback, never-block,
always-emit-a-verdict.

Use this instead of calling `/codex:adversarial-review` directly when:

- You are in an autonomous / `/orchestrate` / scheduled run where a human is not
  watching to retry Codex.
- The change is risk-class (auth, payments, migrations, data-loss, secrets,
  contracts) and a review MUST be on record before merge — but Codex outages
  must not block shipping.
- Codex is known-down or rate-limited (e.g. the buddy "Codex resets <date>"
  windows) and you still need an adversarial pass.

If you are at a normal interactive keyboard and Codex is up, just use
`/codex:adversarial-review` — this skill's only added value is the
fallback + non-blocking gate + persisted verdict.

## The gate (procedure)

1. **Pick a writable verdict path.** Codex's sandbox denies writes under
   `.agents/outputs/`. Write verdicts to a repo-writable path instead — default
   `.codex-verdicts/<issue-or-slug>-<UTC-timestamp>.md`. Create the dir if
   absent; ensure it is gitignored or intended-to-commit per the repo.

2. **Try Codex first.**
   ```bash
   /codex:adversarial-review --wait --base origin/main <focus text>
   ```
   Treat as a Codex FAULT (→ fallback) any of: non-zero exit, rate-limit /
   quota message, timeout, auth failure, empty output, or a sandbox/runtime
   error. A real review verdict (even REQUEST_CHANGES) is NOT a fault — that is
   a successful review; record it and act on findings.

3. **On fault, run a fresh-context internal adversarial review.** Spawn a
   subagent with NO inheritance from the implementation discussion (a fresh
   reviewer, e.g. the `claude` or `Explore`-then-review agent) and the prompt
   skeleton below. In-house adversarial review is a legitimate stand-in — in
   the buddy thinker work it caught 3 real bugs in P3 and 2 BLOCKING SSE gaps
   in P4 while Codex was rate-limited.

4. **Always write the verdict file** with: source (`codex` | `internal`),
   `RISK: N/10`, an `ac_audit` array (`implemented|partial|missing|deferred|n/a`
   per AC), `new_concerns` (scope-freeze escape hatch — do NOT drift into
   REQUEST_CHANGES on out-of-scope items), and the decision.

5. **Return a structured result and NEVER block on Codex availability:**
   `RISK: N/10` + `PROCEED` (no blocking findings) or `REVISE` (blocking
   findings, listed). The pipeline continues either way — `REVISE` means fix
   then re-gate, not "stop and wait for Codex to come back."

## Reusable prompt skeleton (internal fallback reviewer)

```
FRESH-CONTEXT ADVERSARIAL REVIEW (Codex unavailable — internal fallback).
You have NO context from how this was implemented. Review the DIFF against the
issue/spec as a skeptic whose job is to find why this is WRONG.

Diff scope: <git diff origin/main...HEAD, or paths>
Issue / spec + acceptance criteria: <paste ACs>
Risk class: <auth|payments|migration|data-loss|secrets|contract|none>

Challenge the APPROACH, not just defects: Is this the right design? What
assumptions does it depend on? Where does it fail under real-world load,
concurrency, partial failure, or malicious input? For risk-class changes,
explicitly check the named hazard (tenant isolation, money math, reversibility,
secret exposure, enum/contract drift).

Output EXACTLY this shape:
  source: internal
  RISK: N/10
  ac_audit:
    - ac: "<criterion>"
      status: implemented|partial|missing|deferred|n/a
      evidence: "<file:line or why>"
  blocking_findings: [ ... tied to concrete changed code ... ]
  new_concerns: [ ... out-of-scope observations, NOT blockers ... ]
  decision: PROCEED | REVISE
A reviewer that APPROVEs on partial AC coverage is wrong — the per-AC shape
forbids it.
```

## Notes

- The fallback is a stand-in, not a replacement: when Codex is back, a risk-class
  change still benefits from a real Codex pass before merge. Note in the PR which
  source produced the gating verdict.
- Verdict path default `.codex-verdicts/` exists precisely because Codex's
  sandbox cannot write under `.agents/outputs/` — do not target that path.
- Classify findings (BLOCKING / NON-BLOCKING / CLEAN) per
  `~/.claude/rules/implementation-routing.md` Step 3 before acting; don't let
  speculative findings expand scope.
