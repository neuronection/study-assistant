# 20 — Uniform tab actions: one `TabActionBar` for the node workspace

**Status:** complete (S1–S4, 2026-08-21). As-built deviations from the sketch: the
overview bar lives inside `OrganizerCard` as planned; the concepts lift moved the
extract mutation + draft state into `CoverageTab` (bar + `info` slot + error banner
there), leaving `ConceptsPanel` presentational (`draft`/`onDraftChange` props) — its
standalone test now uses a stateful harness, and the extract flow is covered through
the workspace concepts-tab test. `OutlineActions` already conformed to R2/R3 (icons +
spinner), so E2 needed no code change.
**Inputs:** user review of `/courses/{id}` (NodeWorkspace): every tab places, styles, and
sizes its action buttons differently; buttons should be uniform across tabs via a shared
component, with documented exceptions where an action genuinely belongs elsewhere.
**Phase:** post-1.0 polish (follows plans 17/18; pure frontend, no backend, no ADR needed).

---

## Problems (as observed in code)

All in `frontend/src/features/courses/NodeWorkspace.tsx` unless noted:

1. **Five different geometries for the same concept ("this tab's actions"):**
   - Overview (`OrganizerCard`, ~L249): bare `div.flex.flex-wrap.gap-2` mid-page.
   - Notes (~L565): bare `div.flex.flex-wrap.gap-2` at top.
   - Practice (~L825): the *only* tab that wraps its buttons in a `Card` used purely as
     a toolbar (`CardContent` with nothing else).
   - Cards (~L1001) / Tutor (~L1065): bare `<div>` with a single button.
   - Concepts (`ConceptsPanel.tsx` ~L60): `flex items-center justify-between` — button
     pushed to the **right**, opposite of every other tab.
   - Overview root: `OutlineActions.tsx` (~L140) puts its buttons inside a `CardHeader`.
2. **No rule for which button is "primary".** Default variant is used for: New note here,
   Generate quiz, Generate cards, Ask about this node — but structurally similar actions
   (Extract concepts, Draft notes, Cheat sheet, AI outline) are `outline`. The choice
   looks arbitrary per tab.
3. **Icon drift.** `Button` already forces leading icons to `size-4`
   (`[&_svg]:size-4` in `components/ui/button.tsx`), but call sites override with
   `size-3.5` (`ChildCard`, some rows) or omit icons entirely (Practice → "Import" has
   no icon while its siblings do).
4. **Pending/disabled handling is good but hand-copied everywhere** (icon → spinning
   `Loader2` + `disabled`). Should live in one place.
5. **Error placement differs**: NotesTab renders two `ErrorBanner`s under the buttons;
   ConceptsPanel/OutlineActions render inline `<p class="text-danger">`; Practice puts
   the similar-error banner at the very bottom of the tab.

## Design

### S1 — `TabActionBar` component

New `frontend/src/components/layout/TabActionBar.tsx` (same folder as `FocusShell` —
it's layout chrome, not a ui primitive):

```tsx
export type TabAction = {
  label: string
  icon?: LucideIcon
  onAction: () => void
  pending?: boolean
  disabled?: boolean
  title?: string
  primary?: boolean
}

export function TabActionBar({
  actions,
  info,
}: {
  actions: TabAction[]
  info?: ReactNode
})
```

- Renders exactly one row: `flex flex-wrap items-center gap-2`, placed **directly under
  the tab strip as the first child of every tab** — never inside a Card, never
  right-aligned-only, never in a CardHeader.
- Button rendering is owned by the bar, not the caller: `size="sm"`, variant
  `default` when `primary` else `outline`, icon rendered by the bar as
  `<Icon aria-hidden />` (default svg size — no per-call-site `size-3.5` possible) or
  `<Loader2 className="animate-spin" />` when `pending`, plus `disabled={pending || disabled}`.
- `info` slot renders right-aligned (`ml-auto`) for tab meta (counts/summaries).
- Actions with `primary` render first regardless of array order, then the rest in order.
- The bar does **not** own error UI: each tab keeps one `ErrorBanner` immediately below
  the bar for bar-action errors (uniform with NotesTab's current behavior).

### S2 — Button-role rules (codified)

| Rule | Statement |
|---|---|
| R1 | Exactly **one `primary` action per tab** — the tab's headline create/generate verb (variant `default`). Everything else tab-level is `outline` sm. |
| R2 | Every tab-level action has a leading icon at the Button's default svg size. Add the missing one: Import → `FileUp`. |
| R3 | Pending = icon swaps to spinning `Loader2`, button disabled. Handled by `TabActionBar`, deleted from call sites. |
| R4 | Bar is the tab's first element, full stop. Cards below it start the content area. |
| R5 | Bar-action errors render in a single `ErrorBanner` directly under the bar (merge NotesTab's two banners; move Practice's `similarError` handling unchanged — it's a row action, see E3). |

### S3 — Per-tab migration map

| Tab | Bar actions (order) | Notes |
|---|---|---|
| overview | **Compose study material** (primary, `BookOpen`) · Review (outline, `ClipboardList`) · Cheat sheet (outline, `ScrollText`) | Bar extracted out of `OrganizerCard`; findings/cheatsheet cards render below as today. `AIGenerateDialog` trigger state stays in `OrganizerCard` — bar lives inside it as its first element, or the bar is hoisted into `OverviewTab` with dialog state lifted; prefer keeping it inside `OrganizerCard` (state locality) with the bar as the card's first child replacing the bare div. |
| materials | **Add material** (primary, `Plus`) | Today the assign button sits in the first Card's header (`self-start`, ~L422). Move to a bar; the Card keeps its title + count only. |
| notes | **New note here** (primary, `Plus`) · Draft notes (outline, `Sparkles`, keep `title` hint) | Merge the two error banners into one under the bar. |
| concepts | **Extract concepts** (primary, `Sparkles`) | Button moves out of `ConceptsPanel`'s justify-between header into the tab bar; the summary line ("N concepts · M links") moves to the bar's `info` slot. The coverage `<select>` stays in the coverage Card (E3). |
| practice | **Generate quiz** (primary, `Sparkles`) · Generate exercises (outline, `Dumbbell`) · Import (outline, `FileUp`) | Toolbar-only `Card` is deleted — the bar replaces it. |
| cards | **Generate** (primary, `Sparkles`) | Bare div → bar. |
| tutor | **Ask about this node** (primary, `MessageSquare`) | Bare div → bar. |

`Extract concepts` flips outline→primary under R1: it is the tab's only tab-level verb
and the concepts tab's whole point; today's outline variant is exactly the arbitrariness
this plan removes.

### S4 — Documented exceptions (actions that stay out of the bar)

| # | Exception | Why |
|---|---|---|
| E1 | Page-header actions (Study here, Ask — ~L1315) | Page-level, not tab-level; already follow size-sm/icon/spinner conventions. |
| E2 | `OutlineActions` (AI outline, Add node) | Root-only and bound to the *structure card* they act on; a tab bar must be valid for every node, these verbs aren't. Keep in the card, but restyle to R2/R3 conventions (outline sm, icons, spinner). |
| E3 | Row-level actions (quiz export/print, exercise "similar", coverage add/remove + the add-coverage `<select>`, note/material rows) | They act on rows/cards, not the tab. Keep inline; existing ghost/icon conventions there are fine (row chrome ≠ tab chrome). |
| E4 | "Load more" pagination | List control; stays centered under the list (NotesTab already does this). |
| E5 | `ChildCard` mini-actions (Open / Quick practice / Ask) | Card-level; standardize to uniform `outline` sm with default-size icons while in there (drop the `size-3.5`s), but no bar. |
| E6 | Dialog/draft footer buttons (commit/cancel in outline & concept draft cards) | Dialog-context confirmations, unchanged. |
| E7 | `DrillsCard` | Self-contained feature card; owns its own actions. |

## Slices & order

1. **S1**: `TabActionBar` + unit tests (roles, primary-first ordering, pending spinner,
   `info` slot, disabled).
2. **S2**: migrate the simple tabs — cards, tutor, notes (incl. banner merge).
3. **S3**: practice (delete toolbar card), materials (hoist assign button), overview
   (`OrganizerCard` bar), concepts (`ConceptsPanel` header collapse + `info` slot) —
   plus `OutlineActions`/`ChildCard` restyle (E2/E5 conventions).
4. **S4**: docs sync (`docs/STATUS.md` changelog, `docs/usage/courses.md` screenshot-adjacent
   wording, `docs/features.md` if it describes tab anatomy).

Each slice is shippable and independently verifiable; S1 must land first.

## Acceptance

- Every tab on `/courses/{id}` (and `/courses/{id}/n/{nodeId}`) renders the same action
  row as its first element: same position, spacing, button size, icon size, one primary.
- Grep check: no bare `flex flex-wrap gap-2` action rows, no `justify-between`
  button headers, and no Card-used-as-toolbar left in `features/courses/` tab bodies.
- The only buttons outside the bar in tab bodies are row-level (E3), pagination (E4),
  child cards (E5), draft footers (E6), and DrillsCard (E7).
- Concepts tab: summary now in the bar's `info` slot; no behavior change.
- Practice tab: one less Card; visual rhythm matches sibling tabs.

## Tests

- `TabActionBar.test.tsx`: renders labels/aria, primary variant assignment, spinner on
  pending, disabled propagation, `info` alignment, icon default sizing (no `size-3.5`).
- Update `NodeWorkspace.test.tsx`, `ConceptsPanel.test.tsx`, `OutlineActions.test.tsx`
  where they assert button variants/positions (they query by role/name, so expect mostly
  no-op, but ConceptsPanel's layout assertion may move).
- Keep all existing interaction tests green (dialog opens, mutations fire).

## Non-goals

- No backend changes, no route/URL changes, no new buttons or features.
- Not redesigning row-level action chrome (E3) beyond leaving it inline.
- Not touching quiz/exercise/flashcards pages outside the workspace tabs.
- Not introducing a global "action taxonomy" abstraction — one component, one type.

## Verification

Frontend only: `pnpm lint && pnpm typecheck && pnpm test && pnpm build` per slice, then
docs per ca-docs-sync (S4).
