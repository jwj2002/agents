---
paths: ["**/*.py", "**/*.ts", "**/*.tsx", "**/*.jsx", "**/backend/**", "**/frontend/**"]
---

# Code Quality Standards (#364)

Quantified, command-checkable standards. Every standard names the exact
command that verifies it — a standard that can't be checked by command is
prose, and prose is not a gate. Aspirational language ("should", "prefer")
is deliberately absent.

## Coverage

| Standard | Check |
|---|---|
| Changed-code coverage must not DECREASE vs the base branch | `pytest --cov --cov-report=json:cov.json` before and after; compare `totals.percent_covered` (PATCH records the delta; PROVE verdicts on it) |
| New modules: ≥80% line coverage | `pytest --cov=<new_module> --cov-report=term-missing` |
| No test infra in the repo | Standard does not apply — do NOT bolt coverage tooling onto a repo that has none as a side effect of a feature PR; note `coverage: n/a (no test infra)` in the artifact |

An unexplained coverage decrease is a PROVE finding (FAIL-able). An
*explained* decrease (e.g. deleting dead tested code) is recorded with the
explanation and passes.

## Lint & Format

| Standard | Check |
|---|---|
| Lint clean using the project's own config | `ruff check .` (repo's ruff.toml/pyproject wins; no per-PR rule inventions) |
| Format clean where the project enforces it | `ruff format --check <changed files>` — only in repos that already format |
| Frontend | `npm run lint` with the project's config |

## Exceptions (LR-001)

| Standard | Check |
|---|---|
| No bare `except:` / blind `except Exception` in library/CLI code | `ruff check --select E722,BLE001 <changed files>` |
| Fail-open surfaces (session hooks, statuslines, daemons that must never crash the host) may catch broadly ONLY at their top level | per-file-ignores in the repo's ruff config, with a comment saying why — never inline ad-hoc |

## Types

| Standard | Check |
|---|---|
| Repos that already run mypy/pyright: changed files pass at the repo's configured strictness | `mypy <changed files>` / `npx tsc --noEmit` |
| Repos without type-checking | Do not retrofit silently; propose it as its own issue |

## Behavioral evals

| Standard | Check |
|---|---|
| Mechanical evals clean on the diff | `python3 ~/agents/claude-config/scripts/evals/run_evals.py --diff-range origin/main...HEAD` (E01/E04/E13/E14/E15; exit 0) |
| Prose evals (E02/E03/E05–E12) | PROVE per `behavioral-evals.md` |

## Secrets

| Standard | Check |
|---|---|
| No credentials in the diff | E15 via the evals runner (part of the command above) |

## Runtime Smoke

| Standard | Check |
|---|---|
| Any change with a runnable surface must record a passing runtime smoke | `python3 ~/agents/claude-config/scripts/runtime_smoke_gate.py --diff-range origin/main...HEAD` (advisory helper: maps changed files to obligations, runs `smoke.sh` if present; exits 0 = no obligation or passed, 1 = obligation but no `smoke.sh` found) |
| PROVE Level 5 `runtime_smoke` block required in artifact frontmatter | `python3 ~/agents/claude-config/scripts/prove_gate.py --issue <N>` — exit 6 (`GATE_SMOKE_VIOLATION`) when `runtime_smoke` is absent, FAIL, or malformed on a PASS artifact |
| Escape hatch for non-runnable surfaces | `runtime_smoke: {status: "n/a", evidence: "no runnable surface"}` — docs, config, and rename-only changes qualify |

## How the pipeline applies this

- **PATCH** captures the coverage baseline before changes and records the
  delta in its artifact frontmatter (`coverage_before` / `coverage_after`,
  see patch.md §Coverage Delta).
- **PROVE** treats an unexplained coverage decrease, any lint failure on
  changed files, or a mechanical-eval finding as an `ac_audit`-level issue —
  which makes it FAIL-able via AC-FORBIDS-APPROVE and enforced at merge by
  `prove_gate.py` (#360). For runnable surfaces, PROVE Level 5 runtime smoke
  is mandatory; a PASS artifact without a valid `runtime_smoke` block triggers
  `GATE_SMOKE_VIOLATION` (exit 6, fail-closed). See
  `docs/orchestrate-verification-gap.md` for the full gap analysis (#458).
- **agent-git readiness/ship** require a fresh `--validation-log` (file exists,
  newer than HEAD, contains a command) for runnable changes; docs and config
  changes accept prose evidence.
- **/quick** applies the eval gate on risk triggers (quick.md §2.5); lint
  on touched areas is already mandatory there.
