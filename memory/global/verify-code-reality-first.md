---
name: verify-code-reality-before-locking-a-spec
type: feedback
summary: Read the actual code before locking a spec or asserting behavior. Assumptions about code/spec/data shape are the #1 failure (VERIFICATION_GAP).
durability: durable
---
Before locking a spec or claiming "X is handled/unchanged", read the actual code —
don't assume structure, data shape, or dependency behavior. Unverified assumptions
are the dominant failure mode. A 45-minute code-reality pass up front beats hours
of adversarial-review rework.
