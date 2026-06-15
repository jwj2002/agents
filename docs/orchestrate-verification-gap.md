# Orchestrate Verification Gap — Consolidated Review & Action Plan

> Two independent reviews, 2026-06-15: Claude (direct source reads) + Codex
> (gpt-5.5, read-only sandbox, independent pass). Convergent verdict. This doc
> consolidates both, ranks the gaps, and defines the remediation as an umbrella
> issue + six build-slice sub-issues (AC1–AC6).

## Verdict

The `/orchestrate` pipeline enforces **static + unit + lint/build** gates well,
but **nothing executes the built software before merge.** PROVE's "Level 4:
FUNCTIONAL" (`prove.md:175-177`) is the same `ruff`/`pytest`/`npm build` —
a label that over-promises. The deeper issue (surfaced by Codex): the mechanical
merge gate verifies *structure and self-reported status*, not *truth* — almost
nothing re-runs to confirm the claimed verification actually happened.

This maps directly to the agentic-factory research finding: *"the orchestrator
must run quality gates directly, never trusting subagent self-reports"* and
*"verification, not generation, is the bottleneck."* The pipeline currently
trusts PROVE's self-report at its deepest enforcement point.

## Convergent findings (both reviews)

| Finding | Evidence | Both |
|---|---|---|
| "FUNCTIONAL" is not functional | `prove.md:175-177` | ✅✅ |
| No pre-merge boot/endpoint/CLI/worker/e2e gate | whole pipeline | ✅✅ |
| `test_evidence` is free text, never executed | `agent_git.py:525,616-617` | ✅✅ |
| Runtime "Exercised" rule is policy-only, unenforced | `git-process.md:210-211` | ✅✅ |
| Behavioral evals E01–E15 are static diff/AST scans — zero runtime | `evals/common.py:5`, `run_evals.py:7-8` | ✅✅ |

## Findings the Codex pass sharpened (adversarial value)

**1. The merge gate re-runs nothing.** `prove_gate.py::check_gate`
(`:101-142`) reads only frontmatter `status` + `ac_audit` shape; it never
re-executes a command. A stale or fabricated `status: PASS` artifact with clean
AC entries passes. The entire mechanical chain rests on PROVE writing PASS in a
markdown file.

**2. `validate_ac_audit()` checks AC *shape*, not *substance*.** It blocks
`missing`/`partial`/`deferred-without-#`, but `implemented` entries are not
required to cite a real file/test/command. AC-FORBIDS-APPROVE is airtight on
structure, trust-based on content.

**3. The one real runtime check is on the wrong side of the merge.**
`post-merge-verification.md:25-31` boots `uvicorn` + curls `/api/v1/health` +
scans startup logs for `ImportError`/`ModuleNotFoundError` — a genuine smoke
test, but it runs **post-merge** and is "if applicable" (advisory). Broken
wiring lands on `main` first, caught later if at all.

## Unified severity-ranked gaps

1. **🔴 CRITICAL — No pre-merge runtime/smoke gate.** Code can be approved +
   merged without ever executing through its changed entrypoint. (`prove.md:175-177`)
2. **🔴 CRITICAL — Merge gate re-runs nothing.** `prove_gate.py` trusts PROVE's
   frontmatter `status`. (`prove_gate.py:122,131,142`)
3. **🟠 HIGH — `test_evidence` is prose.** `readiness()` only checks non-empty,
   renders to PR body. (`agent_git.py:616-617`)
4. **🟠 HIGH — `validate_ac_audit()` doesn't require real evidence** for
   `implemented`. (`state_manager.py`)
5. **🟡 MEDIUM — Runtime policy exists but is unwired** into
   orchestrate/PROVE/prove_gate/agent_git. (`git-process.md:210`)

## Gate-by-gate map (Codex, corroborated)

| Phase | Gate | Type | Enforcement |
|---|---|---|---|
| PATCH | pre-flight / scope / wiring checklist | static/manual | advisory |
| PATCH | `ruff`, format, `pytest -q`, `npm lint/build` | static + unit/build | advisory (artifact) |
| PROVE Step 0 | executable evals E01/E04/E13/E14/E15 | static diff/file scan | hard if PROVE reports failure |
| PROVE L1 | files exist | static | advisory (artifact) |
| PROVE L2 | grep stubs/placeholders | static | advisory (artifact) |
| PROVE L3 | wired/reachability/registration/enum/path/handoff | static grep/read | advisory (artifact) |
| PROVE L4 | "FUNCTIONAL" | static + unit/build | advisory (artifact) |
| Orchestrator Step 4 | `ac_audit` downgrade | artifact validation | mechanical (shape only) |
| `/ship` Step 7.5 | latest PROVE status + `ac_audit` | artifact validation | mechanical (shape only) |
| `agent-git readiness/ship` | branch/status/commits/scope/non-empty evidence | metadata/text | mechanical, **does not execute tests** |
| `docs/git-process` | integration/smoke/manual | runtime/manual | policy/advisory |
| `post-merge-verification` | uvicorn + health smoke | runtime | post-merge, advisory |

---

# Action Plan — umbrella + six build slices

**Umbrella issue**: tracking-only; holds sequencing, dependency notes, and the
AC1–AC6 checklist. **Sub-issues**: each independently mergeable (`build-slice`),
routed through `/orchestrate` (COMPLEX overall; each slice SIMPLE/MODERATE),
Codex adversarial review before merge (this changes the verification contract).

**AC1 — Add a real runtime floor to PROVE.** In `prove.md`, replace Level 4 with
`Level 4: RUNTIME (smoke)`, mandatory for any change with a runnable surface.
Per-stack recipes: backend → boot app + hit changed route via
`TestClient`/health probe (assert non-5xx); CLI → invoke changed command
(`--help` + one real path); worker/service → confirm startup under
lifespan/container without import error; frontend → Playwright load of the
changed route. Escape hatch: `smoke: n/a (no runnable surface)`. Rename old L4 →
"UNIT/BUILD".

**AC2 — Make smoke a structured, fail-closed artifact field.** Add
`runtime_smoke: {status, command, evidence}` to PROVE frontmatter. Extend
`prove_gate.py::check_gate` to **fail closed** when a runnable-code change lacks
a passing `runtime_smoke` — same hard-gate mechanism as `ac_audit`. *(Closes
gaps 1 + partially 2.)* **Depends on AC1.**

**AC3 — Require real evidence tokens in AC audit.** In
`state_manager.py::validate_ac_audit`, require every `implemented` entry's
`evidence` to contain ≥1 concrete verifier token (`file:line`, `test:`,
`command:`, or `smoke:`); token-less evidence downgrades to FAIL. *(Closes gap
4.)*

**AC4 — Stop accepting prose as test evidence.** In `agent_git.py::readiness`,
add `--validation-log`/`--evidence-file` that must exist, be fresh relative to
HEAD, and contain the required commands; keep `--test-evidence` for the PR body
but no longer treat mere presence as sufficient. *(Closes gap 3.)*

**AC5 — Shared smoke harness + pull the post-merge check forward.** Add
`claude-config/scripts/runtime_smoke_gate.py` mapping changed files → smoke
obligations, callable by PROVE and `/ship`. Reuse the
`post-merge-verification.md` uvicorn/health pattern as the backend recipe but
invoke it **pre-merge**. Per-project `smoke.sh` convention, discovered by the
harness. **Depends on AC1/AC2.**

**AC6 — Reconcile docs.** Update `git-process.md` (Validation Ladder +
"Exercised") and `code-quality-standards.md` to reference the now-enforced
runtime gate instead of aspirational prose. **Depends on AC1–AC5 landing.**

**Sequencing:** AC1+AC2 (floor + teeth) → AC3+AC4 (close trust holes) → AC5
(shared tooling) → AC6 (docs). AC2/AC3/AC4 are highest-leverage: they convert
"trust the narrative" into "re-verify mechanically" — the root cause both
reviews converged on.

## Method note

Reviews were run as cross-model adversarial verification (Claude implements/
reviews, Codex independently reviews — never self-review), per the factory
blueprint's validated pattern. The two passes agreed on all five core gaps;
Codex's independent read surfaced the deeper "merge gate re-runs nothing" and
"AC evidence is unvalidated" points that the first pass under-weighted.
