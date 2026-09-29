# UI conventions

These are the rules that keep the Study Assistant interface consistent with the
rest of the Neuronection family and cheap to change. They cover where a
component belongs, how it is styled, the shared workspace pattern, motion and
accessibility, and the testability contracts. For the frontend's structure and
data flow, see [frontend.md](frontend.md).

## Check the shared library first

`@neuronection/assistant-ui` is the family's first-party React component
library (published on npm). The rule is **library first**:

- `frontend/src/components/ui/*` are re-export **shims** — an import path plus
  an exit hatch. Never re-implement a library component inside a shim.
- Adopting a new library component means adding a shim, not copying source.
- If the library's API does not fit, **change the library** — propose the change
  upstream, release it, then adopt the new version here. Do not fork or wrap it.
- A component belongs in the library only when **two or more family apps** need
  it. Single-app UI stays in the app.

Dev-link hygiene: never commit manifest edits while wired to a local checkout
(`link:` in `pnpm-workspace.yaml`). `scripts/check-dev-link.sh` guards this in CI
and as a pre-commit hook (`git config core.hooksPath scripts/githooks`, once per
clone).

## Styling and tokens

- Style with the `--as-*` design tokens and `data-as-*` attributes. Do not
  hardcode colors, shadows or spacing that a token already covers.
- App identity (brand colors, fonts) lives only in `frontend/src/theme.css`.
- Tailwind 4 utility classes are fine for layout; use token-backed utilities
  (`shadow-[var(--as-shadow-2)]`, `bg-subtle`, …) for anything themed.
- Beware unlayered CSS from the bundled library stylesheet: an unlayered
  `.hidden { display:none }` outranks every `@layer utilities` rule, so
  `hidden md:flex` can never win. Use layered `max-*` variants
  (`max-md:hidden`) when a responsive override must beat it. This exact bug is
  pinned by an e2e spec (see [testing.md](testing.md)).

## Component placement

| Kind | Location |
|---|---|
| Library re-export shims | `frontend/src/components/ui/*` |
| Shared renderers/primitives (blocks, editor, canvas, materials, layout) | `frontend/src/components/<area>/` |
| Feature-specific components and hooks | `frontend/src/features/<feature>/` |
| Cross-cutting client state | `frontend/src/lib/<store>.ts` |
| API client functions | `frontend/src/lib/api/<domain>.ts` |

Feature folders own their UI; promote to `components/` only when a second
feature needs it.

## The workspace pattern

The course **node workspace** is the canonical screen: a header, a tab strip,
and one primary action per tab. Shared pieces:

- `TabActionBar` — a uniform action bar across workspace tabs, with a single
  documented primary action per tab.
- The **structure sidebar** is always on (md+ viewports) and the **FileDock**
  right rail mounts materials and notes as docked, non-modal panels driven by
  URL search params (`?material=`, `?note=`) — deep links and the back button
  stay intact. `lib/dock-store.ts` owns the right-rail geometry and the squeeze
  policy when the chat rail and file panel compete for width.
- **FocusShell** provides the focus/expand shell used by the note editor and
  split study; its docked variant is what the FileDock mounts.

Prefer extending these shared shells over inventing a new layout.

## Motion and accessibility

- Use the shared motion presets in `frontend/src/lib/motion.ts`; do not
  hand-roll spring values.
- Respect reduced motion: `MotionConfig` runs with `reducedMotion="user"`, and
  new animated components need a reduced-motion test (the family standard
  requires it).
- Loading states use the library `Skeleton`/`SkeletonText` primitives with
  layout-matched placeholders, not spinners, for content areas. Inline verbs
  (buttons performing an action) keep spinners.
- Keyboard: interactive surfaces are reachable and operable by keyboard;
  dialogs trap focus and close on Escape; the `?` overlay lists the real
  shortcuts from `lib/shortcuts.ts`.
- Prefer semantic elements and ARIA attributes over div soup; decorative
  elements are `aria-hidden`.

## i18n

Every user-facing string is an i18next key — no hardcoded copy (ESLint errors
on it). Labels are passed into library components as props from the app, so the
library stays copy-free. Use `Intl` for dates, numbers and relative time rather
than translated format strings.

## Testability

- Give interactive elements stable roles and accessible names; tests query by
  role/label first.
- Add a `data-testid` only when role/label queries are ambiguous.
- Keep stores injectable and side effects behind hooks so tests can reset
  state; the persisted-localStorage pattern needs explicit cleanup between
  suites.
- A component that can only be verified in a real browser (CSS cascade, real
  layout) gets a Playwright spec rather than a jsdom test.
