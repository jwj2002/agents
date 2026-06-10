# Reviewer / Eval Regression Set

A small, hand-labeled corpus of past PRs/diffs used to measure whether
prompt-engineering or eval-suite changes actually improve reviewer quality.

Without this, every "did this help?" question is unanswerable — which is
the trap the Meta semi-formal-reasoning paper itself warns about
(*"more confident wrong answers when the agent follows a plausible-but-
incorrect chain"*).

## Why this exists

You can't tell if a prompt change is +5pp better, equivalent, or worse
without a labeled set to score it against. This directory is that set.

Target size: **10–15 cases** is enough to detect ~10pp differences with
reasonable confidence; 30+ if you want tighter measurement.

## Layout

```
regression-set/
├── README.md                  ← this file
├── cases/
│   ├── 001-<short-slug>.md    ← one labeled case per file
│   ├── 002-<short-slug>.md
│   └── ...
├── results/
│   └── YYYY-MM-DD-<run-name>.md   ← scoring runs go here
└── score.py                   ← simple scorer (see below)
```

## Case authoring rules

**Answer-leak rule**: The `## Diff` section must contain only the patch under
review. Expected findings, bug labels, and corrective hints must never appear
inside a diff hunk or code block in that section. Place explanatory notes in
`## Notes`, `## Expected Findings`, or `## Known False-Positives` only.

## Case file format

Each case captures a real past PR/diff and the findings a *good* reviewer
should produce. See `cases/000-template.md` for the template and
`cases/001-example-enum-mismatch.md` for a worked example.

Required sections:

- **Source**: where the diff came from (PR URL, commit SHA, project)
- **Diff**: the patch under review (or a path to it)
- **Issue / context**: the linked issue text or stated intent
- **Expected findings (CRITICAL)**: real bugs a competent reviewer must catch
- **Expected findings (WARNING)**: should-fix issues
- **Expected findings (SUGGESTION)**: nice-to-have
- **Known false-positives**: things a noisy reviewer might flag that aren't real
- **Notes**: any context that would change interpretation

## How to score a run

1. Pick the prompt / eval-suite version you want to test.
2. Run it against each case (manual or scripted).
3. For each case, record per finding:
   - **TP** — reviewer reported a real expected finding
   - **FN** — reviewer missed a CRITICAL/WARNING expected finding (penalize heavily)
   - **FP** — reviewer flagged something not on the expected list and not a real bug
   - **NP** — reviewer flagged a known false-positive (predictable noise)
4. Save a results file: `results/YYYY-MM-DD-<run-name>.md` (see template).
5. Compare across runs with `score.py`.

## Metrics that matter

- **CRITICAL recall**: of CRITICAL findings expected, what fraction did the reviewer catch?
- **WARNING recall**: same for WARNING.
- **Noise rate**: FP + NP per case (lower is better).
- **Length budget**: average reviewer output length per case (Anthropic warns reviewers grow verbose under structured prompting).

A change is **worth shipping** if CRITICAL recall does not regress AND
(WARNING recall improves OR noise rate drops).

## Building the seed set

Pick PRs that are *informative*, not just "passing":

- 2–3 with **migrations** (E04, E07, E08 risk)
- 2–3 with **fullstack enum touches** (E01 risk)
- 2 with **subtle concurrency / state** issues (semantic, not pattern-shaped)
- 2 with **auth/permissions** changes (E11 risk)
- 2 **clean refactors** (good reviewer should report nothing)
- 1–2 with **secrets accidentally added** (E15 — synthetic if needed)

Mix of clean cases and dirty cases keeps the noise-rate metric honest.

## Honesty tax

Building this is the moat. It takes ~2 hours of focused review of past work.
Without it, you'll keep asking "did this prompt change help?" and never get
a real answer. With it, every future change becomes measurable.

The seed cases below are stubs — fill them in from your actual project
history (mymoney-dev, agents, etc.) before relying on them.
