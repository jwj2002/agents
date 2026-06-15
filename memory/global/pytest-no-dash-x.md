---
name: pytest-no-dash-x-for-validation
type: feedback
summary: Don't use `pytest -x` for validation runs — it stops at the first failure and hides downstream regressions. Run the full suite to see every failure.
durability: durable
---
`pytest -x` stops at the first failure, so it hides downstream regressions you
introduced. For a validation run (PROVE, pre-PR), run the full suite without `-x`
so every failure surfaces at once. A clean `-x` run is not evidence the suite passes.
