---
name: sa-assistant-ui
description: Use when building UI in study-assistant with @neuronection/assistant-ui — our FIRST-PARTY family library, not a third-party package. Covers what it exports and how to explore the installed API, the check-library-first rule, import/CSS/theming conventions, when to change the library vs keep UI app-side, and how to test and release library changes. Use BEFORE creating any new component under components/ui/ or importing UI primitives.
---

# assistant-ui in study-assistant

`@neuronection/assistant-ui` is **our own library** (repo:
`github.com/neuronection/assistant-ui`, local sibling checkout at
`../assistant-ui`). It is shared with career- and health-assistant. Treat it
as first-party: **if its API doesn't fit, change the library — never fork,
wrap, or hack around it locally.**

## Check library first

Before writing any shared-looking UI (button, modal, menu, popover,
combobox, wizard, form-in-modal, search input, selection bar…), check the
inventory below. If it exists: import it. If something similar exists but
is missing a prop: add the prop in the library (see below).

Local copies of library components are forbidden — the weekly drift-audit
workflow opens an issue if one appears.

## What it exports (quick map)

Full authoritative API for the **installed** version — read the types:

```bash
ls frontend/node_modules/@neuronection/assistant-ui/dist/*.d.ts   # module inventory
cat frontend/node_modules/@neuronection/assistant-ui/dist/<module>.d.ts
```

- Overlays: `Modal` (+ parts), `Popover` (+ parts), `PopoverButton`
  (self-contained trigger+panel), `Menu`/`MenuItem`/`ActionMenu`,
  `ContextMenu` (coordinate-anchored), `Tooltip`/`InfoTooltip`,
  `ConfirmationModal`, `FormModal`
- Inputs: `Input`, `SearchInput`, `ExpandableSearch`, `Combobox` +
  `ComboboxMulti` (async via `onSearchChange`, grouping), `CheckIndicator`
- Layout/lists: `Card` (+ parts), `Badge`, `SelectionBar`, `ViewToggle`,
  `EmptyState`, `ErrorBanner` (presentational — `action` slot),
  `UndoNotice`, `Marquee` (`useMarquee`, `MarqueeSurface`)
- Wizard: `Wizard` (steps config + `renderStep`, validation gates, modal or
  drawer), `Stepper` (dots/labels)
- Foundations: `cn`, `Portal`, `ThemeScope`, token types

Visual reference: https://neuronection.github.io/assistant-ui/
What's new: `frontend/node_modules/@neuronection/assistant-ui/CHANGELOG.md`
(when shipped in the installed version) or CHANGELOG.md on the library
repo's main branch. Installed version: `frontend/package.json`.

## Conventions in this app

- Import from `@neuronection/assistant-ui` or per-module entries
  (`/button`, `/menu`, …). `cn()` is exported too. Never import internals.
- `components/ui/*` are **re-export shims** — the single import path AND the
  exit hatch. When a new library component is adopted, add its shim in the
  same PR. Never re-implement inside a shim.
- Labels: props have English defaults; pass `t(...)` strings at call
  sites (tests query accessible names).
- Styling: `--as-*` tokens and `data-as-*` attributes only — never internal
  class names. App identity lives in `frontend/src/theme.css`.
- App-coupled UI stays app-side (ADR-006): this repo's
  `components/ErrorBanner`, `components/RenameDialog`,
  `components/UndoDeleteNotice`, `lib/useStoredView`, and the AI
  `FloatingPanel` own business logic and compose library primitives —
  that's the pattern for new app components.

## Change the library (when the family needs it)

1. **Two-app rule:** will career or health also need it? Only study → keep
   it app-side. ≥2 apps → it belongs in the library.
2. Work in `../assistant-ui` (this session can edit sibling repos): follow
   its AGENTS.md — boundary (presentational only, data in/events out),
   `--as-*` tokens, forwardRef, tests incl. keyboard-nav + axe, Ladle
   story, changeset, per-module export wiring.
3. Verify against this app:
   `node scripts/verify-in-app.mjs <abs-path>/study-assistant/frontend`
   (from the library repo — packs a tarball, runs our full suite, restores
   the manifest). Dev-server live check: `pnpm watch` + `dev-link`.
4. Release: changeset → library repo PR flow → npm. The bump arrives here
   via dependabot; never commit tarball/linked manifests.
5. Never edit anything inside `node_modules/@neuronection/assistant-ui`.
