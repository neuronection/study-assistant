# 13 — Sidebar-Navigation & Tree Telemetry (Phase 10 proposal)

Follow-up to the structure sidebar (commit `1d598b9`): the sidebar is now the primary
navigation surface, so it should behave like one — remember its state, find nodes fast,
support full drag ordering and keyboard use, show *study* state (not just content
counts), and destructive actions should be reversible. Plus small link-tying work so
every surface that names a node can jump to it.

All slices are frontend-first; two touch the backend tree payload, one adds a backend
undo mechanism. No schema migrations (undo uses an in-process snapshot registry —
local-first, single user; see Slice E rationale).

## Slices

| Slice | What | Layer |
|---|---|---|
| A | Sidebar polish: persisted state, fuzzy filter, keyboard navigation, drop-between reordering | FE |
| B | Drag materials from the workspace Materials tab onto sidebar nodes to assign | FE |
| C | Study telemetry on the tree: material progress (studied/total) + due-card counts per node | BE+FE |
| D | Node deep-links everywhere: scope chips + assigned-to chips become links | FE |
| E | Undo node delete (snapshot registry + restore API + undo toast) | BE+FE |

## Slice A — sidebar polish

**A1 Persisted state.** `localStorage`: `ca-tree-sidebar-open` ("1"/"0", read by
NodeWorkspace for the toggle) and `ca-tree-expanded-{courseId}` (JSON array of expanded
node ids, read by NodeTreeSidebar as the initial state). The auto-expand-to-current
effect is gated to run only when no stored state exists for the course (first visit);
after that the stored expansion is authoritative — the user's collapses must survive
navigation and reload. Stale ids (deleted nodes) are ignored harmlessly.

**A2 Fuzzy filter.** A small input in the sidebar header (reuse `lib/fuzzy.ts`).
With a non-empty query the tree renders a **flat scored match list** (depth indent +
count badges kept, current-node highlight kept, chevrons hidden); match count shown;
Escape/× clears and restores the tree. Keyboard navigation (A3) operates on the visible
list either way — unify on a `rows` array = filtered ? matches : expanded-flattened.

**A3 Keyboard navigation.** The tree container is focusable (`tabIndex=0`,
`aria-activedescendant` on the focused row). Keys: ↑/↓ move focus (with
`scrollIntoView({block:'nearest'})`), → expands a collapsed row else moves to first
child, ← collapses else moves to parent, Enter opens the focused node (same route as
clicking). Focus initializes at the current node. Focused ≠ current: focus gets a
subtle ring; current keeps `bg-primary/10`.

**A4 Drop-between reordering.** Node DnD gains edge detection from `clientY` vs the
row rect: top 30% = *before*, bottom 30% = *after*, middle = *into* (current
behavior). Indicators: a 2px primary line at the row's top/bottom edge for
before/after; the ring stays for *into*. Before/after against the root is ignored
(root has no siblings). Drop mapping: `position` = target's index in its parent
(before) / index+1 (after); `parent_id` = target's parent. Guards unchanged (no drop
onto self/descendant). Sibling indices come from the tree data (children arrays are
already in order).

## Slice B — drag materials onto sidebar nodes

`MaterialRow` in the workspace Materials tab becomes draggable
(`application/x-ca-material`, data = material id). Sidebar rows accept that MIME with
the ring indicator; drop calls `allocateMaterial(nodeId, materialId)` and invalidates
workspace + tree. This makes one-off reassignment a gesture instead of a dialog round
trip. Only assignment rows (Materials tab) are sources — the picker stays the bulk
tool.

## Slice C — study telemetry on the tree

**Backend.** `TreeService.tree(course_id)` → `tree(course_id, profile_id)`; each
node's `counts` gains:

- `studied` — material_links at the node joined to `material_study_state` with
  `status == 'studied'` for the profile (progress ring numerator; denominator is the
  existing `materials` count).
- `cards_due` — flashcards at the node that are due **now** under FSRS semantics:
  has an `fsrs_states` row with `due_at <= now`, or has no state row at all (new =
  immediately reviewable — mirrors `metrics.due_cards_count`).

Both are grouped queries like the existing `_direct_counts`. The API route passes the
profile (same `ensure_default_profile` dependency as other routes).

**Frontend.** `NodeCounts` type extended. Per row (only when the denominator > 0 /
count > 0): a small SVG progress ring around/next to the title showing
studied/materials (tooltip "x of y materials studied"); a due badge (layers icon + n,
warning tint, tooltip "n cards due") next to the count badges.

## Slice D — node deep-links everywhere

- `ScopeChip` (notes/practice/cards rows) renders as a router `Link` to the node
  workspace when the title is known — everywhere a row says *which node*, you can go
  there.
- MaterialDetailPage `assigned-to` chips become links to `node_id` (they already
  carry `node_id` + breadcrumb; the root/course-level chip links to the course
  workspace).
- Closes the STATUS "section deep-link" leftover in spirit: search → material detail
  → assigned chip → node workspace is now a complete chain.

Mistake-notebook → node links are **deferred**: mistakes payload carries no node
binding and the mapping (mistake → quiz → node) would need a backend field; not worth
it until requested.

## Slice E — undo node delete

**Problem.** Merge-delete is destructive (children reparented, placements moved up,
links deduped away) and only confirm-guarded.

**Design.** In-process snapshot registry — no schema change, deliberately local-first:
one user, one process; a restart inside the undo window (~30 s) is an accepted,
documented loss. A `deleted_nodes` table was rejected for this slice: it drags in
purge/backup/restore semantics for a transient UX affordance.

- `TreeService.delete_node(node_id, snapshot=True)` first captures, inside the same
  transaction: node attrs (title/summary/objectives/parent/order_idx), child ids in
  order, the node's `material_links` rows, the node's `node_concepts` rows, and per
  `PLACEMENT_TABLES` the PKs of rows whose `node_id` is about to be repointed to the
  parent. Returns an opaque token (uuid) into a module-level registry (TTL 5 min, cap
  20 entries, pruned on access).
- `POST /nodes/restore {token}`: recreates the node under its original parent at its
  original sibling index (`create_node` + `move_node`), re-moves the captured
  children back under it, re-inserts the captured material links and concept rows
  (skipping ones that now duplicate), and repoints the captured placement rows to the
  new node id **only if they still sit at the old parent** (defensive against edits
  during the window). Returns the new node id.
- **Frontend:** on delete success the sidebar shows an undo toast ("Node deleted —
  Undo") for ~8 s at the sidebar bottom; clicking Undo calls restore, invalidates
  tree/workspace, and navigates nowhere (the tree re-renders in place).

## Verification per slice

A/B/D: frontend suite only (+ new tests: persistence round-trip, filter list, keyboard
moves, drop-edge mapping, chip links, material-drop assignment).
C/E: backend tests (tree counts incl. `studied`/`cards_due` with study states + fsrs
rows; delete→restore round-trip incl. children, links, placements, TTL/expiry,
cross-course token refusal) + frontend tests for ring/badge/toast.
Docs: STATUS.md module row + changelog, features.md ✅ entries, usage/courses.md
(sidebar section), this doc stays the design record.

## 2026-08-27 follow-up (branch feat/tree-bg-context-menu)

Panel-wide right-click: the handler now lives on the aside, so every non-row area (empty space, chrome) opens the menu targeting the active node (currentId), falling back to the course root; rows win via role="treeitem" check, input/textarea defer to the native text menu. +4 tests.
