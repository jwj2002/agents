---
purpose: "Fillable companion to a UI spec — captures verified frontend reality BEFORE drafting"
companion_to: "specs/<spec-name>.md"
filename_convention: "specs/<spec-name>.frontend-manifest.md"
---

# Frontend-Component Manifest — `<spec-name>`

**Verified as of:** YYYY-MM-DD against commit `<hash>`

This document is a **drafting precondition**, not a spec deliverable. Fill it in
BEFORE writing the spec. Every load-bearing claim the spec makes about reusable
components, hooks, or design tokens must be backed by an entry here, copied
verbatim from the actual source files.

When the spec cites a component, hook, or token, the reviewer should be able to
look here first and confirm the claim against the manifest, rather than re-tracing
from scratch every round.

Rationale: see `~/.claude/rules/spec-review-workflow.md` §3.4 (Frontend
component-API verification). UI specs that name vague component intent rather
than real prop contracts lead to re-implemented one-off components and visual
inconsistency — the frontend parallel to the `owner_onboarding_v1` backend
manifest failures.

---

## 1. Reusable components

For every component the spec uses or extends:

| Component | Path:Line | Props (verbatim from PropTypes/interface) | Relevant states | Notes |
|---|---|---|---|---|
| `Button` | `frontend/src/components/ui/button.jsx:12` | `variant, size, disabled, onClick, children` | `disabled` grays out + blocks click | shadcn/ui wrapper; variant values: `"default" \| "destructive" \| "outline" \| "ghost"` |
| ... | | | | |

**Trace rule:** for any component you cite, read the PropTypes/TypeScript interface
AND at least 30 lines of the render return — default prop values and conditional
rendering affect whether a prop is actually required or optional.

---

## 2. Shared hooks and state patterns

For every hook or global state pattern the spec relies on:

| Hook | Path:Line | Return shape (verbatim) | Side effects | Notes |
|---|---|---|---|---|
| `useEntity` | `frontend/src/hooks/useEntity.js:8` | `{ entity, loading, error, refresh }` | Fetches on mount; re-fetches on `entityId` change | Backed by `/api/entities/:id`; no local cache TTL |
| ... | | | | |

---

## 3. Design tokens

Point to the project's `knowledge/design-tokens.yaml` (see schema at
`~/.claude/templates/design-tokens.yaml`). List only the tokens this spec
will use, copied verbatim from that file.

**Token source:** `knowledge/design-tokens.yaml` (or `frontend/tailwind.config.js` / `src/styles/globals.css`)

| Token | Category | Value | Notes |
|---|---|---|---|
| `colors.primary` | colors | `oklch(0.65 0.24 264)` | Button backgrounds, active indicators |
| `spacing.md` | spacing | `1rem` | Card padding, section gaps |
| ... | | | |

If `knowledge/design-tokens.yaml` does not yet exist in this repo, create it
using `~/.claude/templates/design-tokens.yaml` as the schema, then populate by
running `/discover-patterns frontend` and choosing "design tokens" as the focus.

---

## 4. Layout primitives

For grid wrappers, page shells, drawer/modal scaffolds, and responsive containers
the spec relies on:

| Component / CSS class | Path or file | Purpose | Notes |
|---|---|---|---|
| `PageShell` | `frontend/src/layouts/PageShell.jsx:1` | Provides nav sidebar + main content area with correct z-index | All top-level pages wrap in this |
| `DrawerPanel` | `frontend/src/components/ui/DrawerPanel.jsx:1` | Slide-in panel from right, 480px wide on lg+ | Used for detail views |
| ... | | | |

---

## 5. Components to reuse for this feature

Synthesis section — which items from §1–§4 map directly onto this feature's
requirements. This is where the spec author demonstrates the reuse intent before
writing the spec.

| Component | Why / which prop contract it satisfies |
|---|---|
| `Button` (variant="destructive") | Confirms delete action — `onClick` handler triggers the service call; `disabled` set while request in flight |
| `useEntity` hook | Populates the detail view — `entity` shape matches the card props; `loading` drives the skeleton state |
| ... | |

---

## 6. Components NOT available (negative manifest)

Explicitly list components that look like they should exist but don't. Prevents
spec authors from referencing a `<DataGrid />` that lives only in imagination.

- `<DataGrid />` — NOT in `frontend/src/components/`. Closest: `<Table />` at `frontend/src/components/ui/table.jsx`. Use that instead.
- `useInfiniteScroll` hook — NOT in `frontend/src/hooks/`. Closest: react-query `useInfiniteQuery` (already a dep).
- ... etc.

---

## 7. Design system source

Record which design system files and token sources were consulted and at what
commit:

| Token source | Path | Verified at commit |
|---|---|---|
| Tailwind config | `frontend/tailwind.config.js` | `<hash>` |
| shadcn theme | `frontend/src/styles/globals.css:1-40` | `<hash>` |
| Design tokens yaml | `knowledge/design-tokens.yaml` | `<hash>` |

---

## 8. Self-verification checklist (before submitting V1.0)

- [ ] Every reused component in the spec is in §1 with a verified prop contract (PropTypes or TypeScript interface, not assumed)
- [ ] Every hook or global state pattern used is in §2 with a verified return shape
- [ ] Every design token referenced is in §3, copied verbatim from the project's `knowledge/design-tokens.yaml` or design system source
- [ ] Every layout primitive is in §4
- [ ] §5 explicitly maps spec requirements to real, existing components
- [ ] §6 lists every component the spec considered but found absent
- [ ] §7 records where tokens and component APIs were verified and at what commit

If any box is unchecked, V1.0 is not ready for adversarial review.
