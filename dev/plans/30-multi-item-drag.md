# 30 — Drag multiple selected items together in Notes, Materials, Library (post-1.0 round 7)

**Status:** COMPLETE 2026-08-22 (A–E in one pass; backend 463 + frontend 586
tests green; ADR-067 recorded) · **Phase:** post-1.0 polish (follows plan 29)

**As-built fix (2026-08-22, user report):** dragging from a selected item
collapsed the selection — a plain `mousedown` on an already-selected row reset
it to just that row before `dragstart` fired (background drags worked because no
item `mousedown` ran). `useSelection.nextSelection` keeps the whole selection
when the pointer-down target is already selected (plain click = no modifiers),
moving the shift-anchor; plain clicks on unselected rows still select just them.
Frontend 587 tests.

**As-built follow-up (2026-08-22, user request):** the workspace Materials tab no
longer renders the collapsible child-material roll-up (`workspace.children` ×
`child_materials`). The tab now lists only assigned folders + materials directly
assigned to the node; the `collapsed` state is gone. Child material counts stay
available via the Overview tab's children cards and the structure sidebar's
per-node badges. This also simplifies the shared marquee surface to a single
section. Frontend 588 tests. · user request ("when multiple selected items in notes, materials and the
library — drag them together with the mouse")

## Context

Plan 24 (ADR-056) gave every list the file-manager grammar: selection
(click/Ctrl/Shift/marquee), context menus, and **multi-id drag payloads**
(`application/x-ca-item` JSON `{folderIds, materialIds}`). Where it landed:

- **Library** — multi-drag already works end to end: `buildDragPayload`
  (LibraryPage.tsx:960) serialises the *whole selection* when the dragged item is
  selected, and folder/pane drops move everything (`moveSelectionTo`).
- **Materials tab (grid)** — the grid item already bundles every selected id into
  `application/x-ca-item` (NodeWorkspace.tsx:906).
- **Materials tab (list)** — `WorkspaceMaterialRow` (NodeWorkspace.tsx:206) only
  sets single-id `application/x-ca-material`. Dragging a selected row from a list
  moves one item, not the selection.
- **Notes tab** — **no drag at all**: `EntityItems` rows aren't draggable; the only
  move path is the context menu → Move-to-node dialog. Multi-drag is impossible.
- **NodeTreeSidebar drop** — reads a **single** material id
  (NodeTreeSidebar.tsx:755 `application/x-ca-material`) and assigns just that one;
  no note drop exists.

**Goal:** in Notes, Materials (list *and* grid) and the Library, when several items
are selected, grabbing any selected row and dragging moves the whole selection
together. Drops apply to everything dragged.

## Scope decisions

- **Library: already done** — verify only (a regression test asserting the multi-id
  payload already exists; no code change planned).
- **Notes drag → drop target is the NodeTreeSidebar**, mirroring the materials
  assign-drop: dropping note(s) on a node **moves** them to that node (placement
  verb, `moveNote` — the same call the context-menu Move-to-node uses). A note drag
  is a distinct MIME payload (`application/x-ca-item` gains `noteIds`), so node-tree
  reorder drags (`application/x-ca-node`) and material assign drags stay unchanged.
- **Materials list view** mirrors the grid: carry the full selection via
  `application/x-ca-item` + first id via `application/x-ca-material` (keeps the
  sidebar's existing material-assign drop working for both views).
- **Sidebar drop upgrades to batches**: a material payload assigns *every* dragged
  material id; a note payload moves *every* dragged note id. Multi-item drop = N
  mutations (no new backend — same endpoints plan 24/9A shipped).
- **Drag image counter**: when >1 item is dragged, replace the native image with a
  small "N items" badge so it's obvious the selection moves (native shows one row).
- **Out of scope:** Practice tab (quizzes/exercises) drag — same `EntityItems`
  surface so it's a follow-up, but the user asked for notes/materials/library only.
  No backend changes, no schema changes, no new ADR needed (extension of ADR-056's
  multi-id payload clause — recorded below as a refinement note, not a new decision).

## A — Shared drag-payload helpers (`frontend/src/lib/dragPayload.ts`)

Extract the library's payload logic into one module both tabs + the sidebar use:

- `const ITEM_MIME = 'application/x-ca-item'`, `const MATERIAL_MIME =
  'application/x-ca-material'`
- `interface DragPayload { folderIds: number[]; materialIds: number[]; noteIds:
  number[] }`
- `buildDragPayload(event, {key, id, kind, selected, selectedPayload,
  setSelection, countLabel?})` — the library rule generalised: if `key` is
  selected, use the caller's `selectedPayload` (the whole selection's ids for
  every kind — library drags keep folder+material, notes drag notes);
  if not selected, select just `[key]` and drag just that one item.
  Sets `ITEM_MIME` (JSON payload), `MATERIAL_MIME` (first material id, for the
  sidebar's existing material-assign drop), `effectAllowed = 'move'`, and when
  the dragged count > 1 calls `setDragCountImage`.
- `parseDragPayload(event): DragPayload | null` — the library's `dropPayload`,
  generalised (noteIds parsed too). Library's local copy moves here.
- `setDragCountImage(event, count, label)` — builds a small badge canvas
  (`setDragImage`) showing `N items` (i18n label via `drag.items`); no-op when
  count ≤ 1. Canvas getContext is null in jsdom → badge skipped in tests,
  native image preserved.
- **Library adopts the helper**: its local `buildDragPayload`/`dropPayload`/
  MIME constants are deleted, call sites switched to the shared functions
  (behavior identical, plus the drag badge for free).

Tests: build (selected→whole-selection per kind, unselected→single+re-select,
mixes), parse (malformed/foreign MIME → null), count image (multi sets a badge,
single leaves native), library still drags the whole selection after the refactor.

## B — `EntityItems` gains optional drag

`components/entity-list/EntityItems.tsx` — additive props (notes-only caller today;
quiz/exercise lists unaffected):

- `onDragStart?: (event: React.DragEvent, item: EntityItemEntry & T) => void`
- rows (grid + list) become `draggable` when the prop is provided, and forward
  `onDragStart`.

Test: draggable attribute + forwarded handler in grid and list layouts; absent prop
→ rows not draggable.

## C — Notes tab: draggable rows with multi-select payload

`NodeWorkspace.tsx` `NotesTab`:

- Build `noteItems` with a key already used by selection (`String(note.id)`).
- `onDragStart` uses `buildDragPayload(event, selection, key, 'n', note.id)` — a
  selected note drags every selected note; an unselected note drags just it (and
  selects it, matching the library/materials grammar).
- Drop target: `NodeTreeSidebar` (section D). No local drop surface needed.

Test: dragging a selected note sets `application/x-ca-item` with *all* selected
note ids; dragging an unselected note carries just that id + selects it.

## D — Materials list view: multi-id payload

`NodeWorkspace.tsx` `renderEntry` list branch:

- `WorkspaceMaterialRow` gains the same drag logic as the grid item: when the row
  is selected, `application/x-ca-item` carries all selected material ids (already
  computed as `dragMaterialIds`); keep `application/x-ca-material` = first id so the
  sidebar's material-assign drop keeps working.

Test: list-row drag of a selected row carries the full selection.

## E — NodeTreeSidebar: batched material assign + note move drops

`NodeTreeSidebar.tsx`:

- Parse `application/x-ca-item` on `onDragOverRow`/`onDropRow` (alongside the
  existing `application/x-ca-material` single-id path).
- Material payload → `allocateMaterial` per id (batch); keep the single-id MIME
  branch for external drags (library/materials both still set it).
- Note payload → `moveNote(noteId, nodeId)` per id (new small mutation, mirrors the
  workspace's `moveNotes`); invalidate `['notes']` + tree on success. A note drag
  highlights the target node like the material drop does (reuse `materialTarget`
  visual).
- Node reorder drags (`application/x-ca-node`) unchanged.

Tests: multi-material drop assigns each id; note drop moves each note + invalidates
notes/tree; node-reorder drag unaffected.

## Verification

Per slice, before commit: `pnpm lint && pnpm typecheck && pnpm test && pnpm build`
(frontend — backend untouched, `ruff check . && mypy . && pytest` stays green).
Docs (`docs/STATUS.md` changelog) updated in the same commits.