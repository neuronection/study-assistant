# 24 — File-manager interactions: selection, clipboard verbs, drag (post-1.0 round 5)

**Status:** COMPLETE 2026-08-22 (A → B → C → D, all committed; 408 backend +
478 frontend tests green) ·
**Phase:** post-1.0 polish (follows plan 23)

## Context

User request: the Library (`/library?course={id}`) and the workspace list tabs
should behave like a classic file browser (Nemo / Cinnamon):

- items/containers are **draggable**
- **marquee select** with mouse drag (on empty pane background)
- **Ctrl/Shift-click** multi-select
- right-click menu with **Cut / Copy / Paste / Delete**
- (separately approved) an **"Assign to node…"** picker that assigns selected
  materials to a tree node

Already present: per-item + pane `ContextMenu`s, rename/delete flows,
`application/x-ca-material` drag MIME (library/workspace → node tree = assign),
`PATCH /folders/{id}/move`, drag-to-reparent patterns in `NodeTreeSidebar`.

**What this round adds (ADR-056):** one shared interaction grammar — a selection
model + typed clipboard — where **the library gets filesystem verbs**
(move/duplicate folders+materials) and **workspace tabs get placement verbs**
(assign/unassign materials, move notes/quizzes/exercises to a node, bulk delete
with trash undo). Drag payloads become multi-id.

### Existing semantics to respect (not change)

- **Folder delete lifts contents to the parent** (never cascades) — confirm copy
  must say so. Linked-source folders keep their special menu (rescan/reveal/
  unlink); they are **never** move/copy/paste targets.
- Materials/folders are **not trashed** (ADR-048: content-addressed blobs +
  backups cover them); delete = hard purge with confirm. Notes/quizzes/
  exercises deletes already snapshot to `deleted_items` → undo strip works.
- Intra-course placement is DB-enforced (ADR-039 composite FK) — every move/
  copy/assign validates same-course server-side.
- Material copy must **bypass upload dedup** (`_find_duplicate` matches
  content_hash per course and would swallow the copy).

**ADR (recorded in `06-decisions-and-risks.md`):**

| # | Decision (one line) |
|---|---|
| ADR-056 | Lists adopt one file-manager grammar: shared selection model (click/Ctrl/Shift/marquee) + typed clipboard store; **library = filesystem verbs** (move folder/material, duplicate material with shared blob + re-derived chunks), **workspace = placement verbs** (assign/unassign, move-to-node, bulk delete via trash where it exists); folders are move-only (no recursive copy in v1); linked-source panes/course home/search stay read-only |
| ADR-057 | Material duplicate = new row sharing the content-addressed blob (`blob_sha`/`content_hash`), **latest extraction deep-copied** (chunks + FTS + index card; new id space), embeddings/description re-queued via the standard `postprocess` job, fresh study state, **no node links**, provenance preserved, title `"{title} (copy)"` |

---

## A — Backend: move + copy endpoints (+ node moves for phase 2)

`backend/app/api/materials.py`, `services/materials.py`:

1. `MaterialPatch` gains `folder_id: int | None` (optional; when present, move).
   New `MaterialsService.move(material, folder_id)`:
   - `folder_id=None` → course root; else folder must exist, same profile,
     **same course**, `source_id is None` (not a linked folder) → else 422.
2. `POST /materials/{id}/copy` → `MaterialOut` (+ optional `folder_id` target):
   - new Material row: same blob/mime/kind/status/filename/pages/language/
     provenance, title `"{title} (copy)"` (trim ≤300; append ` (2)`, `(3)`…
     while a same-titled material exists in the target folder), target folder
     validated like move
   - deep-copy **latest** extraction (version 1, `extractor` kept, markdown/
     blocks kept) + chunks (new ids, same ordinals/text) + `sync_material_fts`
     + index card copied
   - enqueue standard `postprocess` job (embeddings + description backfill)
   - **no** MaterialLink / MaterialStudyState rows copied
3. Node moves for phase 2 (all validate via `TreeService.placement_node` +
   composite FK):
   - `NoteUpdate.node_id: int | None` (move note within its course; None →
     course root placement? **no**: None = unbind check stays — placement_node
     resolves None → course root)
   - quiz `PATCH /activities/{id}` accepts optional `node_id` (rename stays)
   - exercise `PATCH /{id}` accepts optional `node_id`
   - all three commit → tree counts change (frontend invalidates `tree`)

Tests (`backend/tests/`): move happy/422s (cross-course, linked folder,
unknown folder), copy deep-copy assertions (rows, chunks, FTS hit, index card,
no links/study state, postprocess job enqueued, title uniquing), note/quiz/
exercise node moves (+ cross-course 422).

## B — Frontend primitives: selection + marquee + clipboard store

- `frontend/src/lib/useSelection.ts` — id-based selection hook:
  `selected: Set<number>`, `onItemPointerDown(id, event)` (click /
  Ctrl-click toggle / Shift-click range against the visible order),
  `clear()`. Order list supplied by caller (visible rows, folders first).
- `frontend/src/components/ui/Marquee.tsx` — rubber-band overlay for a pane:
  starts on **pointerdown on empty background only** (target === container or
  data-marquee-surface), 4px threshold before arming, rect-intersection
  hit-test against `[data-selectable-id]` children (getBoundingClientRect —
  robust in grid+list, no elementFromPoint), live-updates the selection while
  dragging (union with pre-marquee Ctrl-selection), Escape cancels.
- `frontend/src/lib/clipboard-store.ts` — Zustand store:
  `{ kind: 'library', folderIds: number[], materialIds: number[], mode: 'copy'|'cut', courseId }`
  plus `clear()`. Single selection surface in v1 (library only; workspace
  verbs act on live selection, no cut/copy needed there).

Tests: hook semantics (plain/Ctrl/Shift, anchor reset), marquee
(rect hit-test math incl. union with prior selection, threshold, background-
only start), store transitions.

## C — Library wiring (the Nemo feel)

`LibraryPage.tsx` + `api.ts` additions (`moveMaterial`, `copyMaterial`) +
i18n:

- selection visuals: folders (`tileBase/rowBase` + selected ring/bg) and
  materials (`MaterialTile`/`MaterialRow` gain `selectionState?: 'none'|
  'selected'|'cut'` — ring + bg, cut renders 50% opacity)
- item context menus gain **Cut / Copy** (folders: Cut only — copy disabled
  with hint; linked folders: neither), materials: both; Delete stays
- pane background menu gains **Paste** (+ disabled when clipboard empty or
  foreign course); folder item menu gains **Paste into**
- keyboard on the pane: `Delete`/`Backspace` = delete selection (confirm),
  `Ctrl+X`/`Ctrl+C`/`Ctrl+V` clipboard verbs, `Escape` clears selection —
  only when no input/textarea is focused
- paste behavior: cut+paste = move (folders via existing move endpoint,
  materials via new `folder_id` PATCH; **cut clears the clipboard**),
  copy+paste = material duplicate into target (folders excluded in v1);
  clipboard keeps contents after copy-paste (Nemo behavior)
- **drag**: folder tiles/rows + material tiles/rows become `draggable`,
  payload = `application/x-ca-item` JSON `{folderIds, materialIds}` (and
  material ids also under `application/x-ca-material` for the existing
  node-tree assign drop); drop on folder tile/row = move (linked folders
  reject), drop on pane background = move here; drag image = native
- **Assign to node…** on material selection (context menu + kebab): opens
  `AssignToNodeDialog` (new, `features/courses/`) — course tree radio picker
  reusing `GET /courses/{id}/tree` + existing assign endpoint per material
  (idempotent), success notice with node title
- out of scope: linked-source browse pane, course home, search results view

Tests: menu wiring (cut/copy/paste enabled-states), keyboard handler gating,
move-on-drop (payload, linked-folder rejection), paste-as-move vs copy calls,
assign dialog (renders tree, assigns each id, success notice), selection
classes on tile/row.

## D — Workspace tabs: selection + placement verbs

Shared: selection hook (B) wired into the three tabs' visible items; a slim
**selection action bar** appears when >0 selected (count + verbs + clear).

- **Materials tab**: multi-select; verbs = **Unassign** (bulk
  `DELETE /nodes/{id}/materials/{mid}`), **Assign to node…** (same dialog),
  drag rows carry multi-id payload (feeds node-tree assign)
- **Notes tab**: multi-select; verbs = **Delete** (sequential `deleteNote`,
  one undo strip per round via first `deleted_item_id`), **Move to node…**
  (backend A.3; invalidates notes + tree)
- **Practice tab**: quizzes + exercises lists; multi-select per list; verbs =
  **Delete** (trash-snapshotting endpoints), **Move to node…** (backend A.3)

Tests: bulk unassign, bulk note delete with undo strip, move-to-node mutation
payloads + invalidations, selection bar visibility.

---

## Verification

Per slice, before commit: `ruff check . && mypy . && pytest` (backend) ·
`pnpm lint && pnpm typecheck && pnpm test && pnpm build` (frontend). Docs
(`docs/STATUS.md` + usage docs) updated in the same commits.
