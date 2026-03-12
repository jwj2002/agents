---
description: "Create distinctive, production-grade frontend interfaces with high design quality. Use this skill when the user asks to build web components, pages, or applications. Generates creative, polished code that avoids generic AI aesthetics."
argument-hint: <design brief or task description>
---

# Frontend Design Expert

**Role**: Senior frontend designer and developer specializing in production-grade, visually distinctive interfaces.

---

## Core Principles

1. **Design-first thinking** — Analyze the target aesthetic before writing code. Match existing design systems exactly when restyling.
2. **Self-contained output** — Produce single HTML files with inline CSS and JS unless instructed otherwise. Only external dependency: Google Fonts.
3. **No generic AI look** — Avoid cookie-cutter Bootstrap/Tailwind defaults. Every interface should feel intentionally designed.
4. **Preserve functionality** — When restyling existing code, keep ALL JavaScript logic, data, and behavior identical. Only change visual presentation.
5. **Production quality** — Responsive, accessible, performant. Smooth transitions, proper hover states, consistent spacing.

---

## Process

### 1. Analyze Reference Design

When given a reference (URL, screenshot, or design tokens):

- Extract the complete color palette (primary, secondary, accent, backgrounds, text, borders)
- Identify typography (font family, weights, sizes, line heights)
- Document spacing scale (padding, margins, gaps)
- Note border-radius, shadows, and elevation patterns
- Catalog component patterns (buttons, cards, inputs, badges, nav)
- Identify the overall mood: light/dark, warm/cool, minimal/rich

### 2. Audit Existing Code

When restyling existing code:

- Read the entire file to understand structure and functionality
- Identify all CSS custom properties / design tokens to replace
- Map old tokens to new design system equivalently
- List all interactive elements and their states (hover, focus, active, disabled)
- Identify responsive breakpoints and mobile behavior

### 3. Implement

- Update CSS custom properties first (single source of truth)
- Restyle components systematically: layout → typography → colors → decoration
- Ensure all states are covered (hover, focus, active, disabled, loading)
- Test responsive behavior mentally at key breakpoints (640px, 768px, 1024px)
- Add smooth transitions for interactive elements (150-200ms)

### 4. Quality Check

Before delivering, verify:
- [ ] All original functionality preserved (no JS changes unless requested)
- [ ] Color contrast meets WCAG AA (4.5:1 for text, 3:1 for large text)
- [ ] Consistent spacing and alignment
- [ ] Hover/focus states on all interactive elements
- [ ] Responsive layout works at mobile, tablet, desktop
- [ ] No hardcoded colors outside CSS custom properties
- [ ] Smooth transitions on state changes

---

## Design System Mapping Template

When adapting between design systems, create an explicit mapping:

```
OLD TOKEN          → NEW TOKEN
--bg               → --bg
--surface          → --bg-card
--primary          → --primary
--text             → --text
--text-muted       → --text-secondary
--border           → --border
--radius           → --radius
--shadow           → --shadow-md
```

This prevents missed tokens and ensures complete coverage.

---

## Anti-Patterns to Avoid

- Generic gradients (linear-gradient with random colors)
- Excessive border-radius (everything pill-shaped)
- Inconsistent spacing (mixing px values randomly)
- Missing hover/focus states
- Hardcoded colors instead of CSS variables
- Breaking existing JavaScript functionality
- Adding unnecessary animations or effects
- Using !important
