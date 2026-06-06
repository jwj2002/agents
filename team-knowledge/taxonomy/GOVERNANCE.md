# Taxonomy governance — minting new areas / pattern_keys (§1.5)

The taxonomy is the comparability layer (#223): patterns only align when keyed to a *shared*
vocabulary. So it must be **controlled** — but also **extensible**, or it ossifies and everything
real falls into `UNMAPPED`.

## The signal to extend
`UNMAPPED` is not noise — it's the **taxonomy-gap signal**. When observations repeatedly resolve to
`UNMAPPED` (see `scripts/patterns.py:resolve_pattern_key`), that recurrence is the trigger to
consider a new key/area. An `ALL_CAPS` token recurring in `UNMAPPED` clusters = "add a key" (#223).

## The rule (conservative by design)
Mint a new `area` or `pattern_key` only when **all** hold:
1. **Recurrence:** the same unmapped concern shows up ≥ N times (start N=3) across observations,
   not a one-off.
2. **Distinct concern:** it isn't a rename of an existing key — it captures a genuinely different
   practice (else you fragment the vocabulary and break matching).
3. **Cross-checked:** at least one other roster member agrees it's distinct (avoids one dev's
   idiosyncratic split). Conflicts go to the §arbiter (Jason).

## What NOT to do
- **Never force-bucket** an unmapped observation to the closest existing key — that manufactures
  false matches. `UNMAPPED` is correct until a key is deliberately minted.
- **Never** back-fill `observation_count` from a seed/import — vocabulary is seeded, observations
  are earned (`scripts/patterns.py:bootstrap_vocabulary`).

## Mechanics
Edit `areas.yaml` (add the area/key), reference the recurring `UNMAPPED` evidence in the PR, and
get one other roster member's review. The change is vocabulary-only; it never carries counts.
