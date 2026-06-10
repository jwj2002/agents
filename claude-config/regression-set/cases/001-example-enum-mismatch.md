---
case_id: 001
title: Frontend uses Python enum NAME instead of VALUE for member role
source: SYNTHETIC — illustrative example, replace with a real PR
project: mymoney-dev
date_added: 2026-04-28
labels: [enum, fullstack, E01]
files_changed: 2
---

# Frontend uses Python enum NAME instead of VALUE for member role

> **Synthetic case** — built from a known historical pattern (E01 = 26% of
> fullstack failures). Replace with a real PR before relying on this.

## Source

- PR: (synthetic)
- Project: mymoney-dev
- Linked rule: `behavioral-evals.md` E01 ENUM_VALUE_MISMATCH

## Issue / Context

> Add support for "co-owner" role on AccountMember. Backend enum already
> includes the value; frontend needs to surface it in the role-picker.

Backend `AccountMemberRole` enum:

```python
class AccountMemberRole(StrEnum):
    OWNER = "OWNER"
    CO_OWNER = "CO-OWNER"   # ← note the hyphen
    VIEWER = "VIEWER"
```

## Diff

```diff
# frontend/src/components/RolePicker.jsx
 const ROLE_OPTIONS = [
   { value: "OWNER", label: "Owner" },
+  { value: "CO_OWNER", label: "Co-owner" },
   { value: "VIEWER", label: "Viewer" },
 ];
```

## Expected Findings

### CRITICAL (reviewer MUST flag)

- [ ] **E01 ENUM_VALUE_MISMATCH**: Frontend uses `"CO_OWNER"` (Python name) where backend expects `"CO-OWNER"` (enum value)
  - Why CRITICAL: silent failure — server rejects the role, UI appears to work but role is never set
  - Where: `frontend/src/components/RolePicker.jsx:3`
  - Fix: change `"CO_OWNER"` → `"CO-OWNER"`

### WARNING

- [ ] **Test gap**: no test exercises the new option end-to-end
  - Where: `frontend/src/components/RolePicker.test.jsx`

### SUGGESTION

- [ ] Consider centralizing role values in a shared constants module so future enum additions don't risk this class of bug

## Known False-Positives

- "label is hardcoded" — labels can be hardcoded; only the `value` must match the backend enum string

## Notes

- This is the canonical example of E01. If a reviewer prompt change does not catch this, it has regressed on the most common fullstack failure mode.
- A reviewer that ALSO suggests "switch to integer enum codes" is being unhelpful — the existing string-enum pattern is intentional.
