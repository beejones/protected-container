---
name: frontend-ui-engineering
description: "Use when: building or modifying templates, static JavaScript, CSS, dashboards, controls, responsive layouts, charts, UI state, Playwright tests, or user-facing workflows that must feel production-quality and consistent with the existing app."
---

# Frontend UI Engineering Skill

## Principles

Stock Dashboard is an operational market-data and trading tool. UI should be dense, calm, scannable, and efficient for repeated use. Avoid marketing-style layouts, decorative sections, and generic AI-looking surfaces.

Match the existing app before inventing new styling. Controls should help users inspect data, compare states, and act quickly without visual noise.

## When To Use

- Editing HTML templates, static JavaScript, CSS, chart views, dashboards, forms, filters, or controls.
- Adding or changing responsive behavior.
- Building loading, error, empty, disabled, or streaming states.
- Writing Playwright UI tests.
- Fixing a visual, interaction, or accessibility issue.

## UI Design Rules

- Keep page sections unframed; use cards only for repeated items, modals, and genuinely framed tools.
- Do not nest cards inside cards.
- Use compact headings inside panels and dashboards; reserve hero-scale type for true heroes.
- Use stable dimensions for boards, toolbars, counters, grids, and tiles so dynamic text/icons do not shift layout.
- Use icons for tool buttons when an existing icon library is available; otherwise follow local button conventions.
- Use toggles/checkboxes for binary choices, segmented controls for modes, menus for option sets, sliders/inputs for numeric values, and tabs for views.
- Do not rely only on color for state. Pair color with text, icons, or shape.
- Text must not overflow or overlap at mobile or desktop widths.
- Do not introduce one-note purple, beige, dark-slate, or brown/orange palettes unless the existing design already requires it.

## Procedure

### Step 1 - Read The Existing Surface

Inspect nearby templates, CSS, JavaScript, and tests. Identify:
- Existing layout primitives.
- Naming conventions for DOM IDs, classes, and data attributes.
- State-management style in static JS.
- Current API calls and payload shapes.
- Existing Playwright patterns.

### Step 2 - Define States

Before editing, list the states the UI needs:
- Initial/loading.
- Success with normal data.
- Empty/no results.
- Validation error.
- API/server error.
- Disabled or pending action.
- Streaming or stale data when relevant.

UI plans must include a compact mockup or layout sketch.

### Step 3 - Build With Existing Patterns

- Keep data fetching separate from rendering where local JS structure allows it.
- Reuse existing route helpers and API response handling.
- Preserve auth/test-mode behavior.
- Keep controls keyboard-accessible with real `button`, `input`, `select`, and `label` elements when possible.
- Add ARIA labels for icon-only controls.
- Keep IDs/classes stable for Playwright selectors when tests depend on them.

### Step 4 - Verify Runtime Behavior

For UI changes, use `tests/UI/` and browser verification as risk warrants:
- No console errors.
- Main workflow works.
- Responsive widths: mobile, tablet, desktop.
- Text and controls do not overlap.
- Loading, error, and empty states are reachable.
- Network responses match frontend assumptions.

## Accessibility Checklist

- Interactive elements are keyboard reachable.
- Focus is visible and logical.
- Form controls have labels.
- Icon-only buttons have accessible names.
- Dynamic updates use appropriate status text or existing live-region patterns when needed.
- Contrast is sufficient for text and critical states.

## Red Flags

- Generic hero/card-grid treatment for a dashboard tool.
- New arbitrary CSS values where the app has a spacing/type convention.
- Layout verified only at the developer's viewport.
- UI change without empty/error/loading states.
- Click handlers on non-interactive elements without keyboard support.
- API response assumptions copied into multiple JS files.
- Playwright selectors broken by cosmetic markup changes.

## Exit Criteria

- [ ] UI follows existing app patterns and operational-tool design.
- [ ] Required states are implemented or explicitly out of scope.
- [ ] Controls are keyboard-accessible and labelled.
- [ ] Responsive behavior was checked at relevant widths.
- [ ] Playwright/manual browser verification is documented when UI behavior changed.
- [ ] No console errors or obvious text/layout overlap remain.