# 27 — Materials tab gets the library create grammar (+ menu, right-click, marquee)

**Status:** COMPLETE 2026-08-22 (A+B in one pass; frontend 542 tests green,
backend untouched) ·
**Phase:** post-1.0 polish (follows plan 26) · user-approved 2026-08-22

**As-built deltas:** the library pane menu's **Paste** entry now *appears only
when something is pasteable* (was always rendered, disabled — the shared
prepend slot made hiding the cleaner shape; no test asserted the disabled
state); the tab's **New…** button is disabled with a spinner while an upload
runs; the materials-tab hidden inputs reset `event.target.value` after a pick
(re-selecting the same file works, unlike the library's old inputs); the
`UploadButton` split control survives only in the `MaterialPickerDialog`
footer (the tab's copy was the one retired).

**Same-day follow-up (user request): assigned folders are folder tiles/rows,
not a chip strip.** The "Assigned folders: …" chip strip is replaced by real
folder tiles/rows at the top of the materials grid/list (`WorkspaceFolderItem`
— folder icon, name, member count, link badge). Double-click opens the folder
**in the Library**; right-click = Open in library / Unassign folder; list rows
keep a hover ✕. Folders join the selection grammar: marquee/click select them
(`f{id}` keys) and the selection bar's Unassign / Assign-to-node handle them
(`deallocateNodeFolder`/`allocateNodeFolder`). Opening a linked-source folder
deep-links the Library through a new `?source=` search param on `/library`
(validateSearch extended; LibraryPage restores link mode from it when
linkState is null). Empty state counts folders (dropzone only when both are
empty). Refines ADR-062's "strip" wording — assignment semantics unchanged.

**Same-day follow-up (user request): selection verbs migrate into the
right-click menu; the banner is gone.** The `SelectionBar` ("N selected —
Unassign / Assign to node…") is removed from the Materials tab. Selection
still works like the library (click/Ctrl/Shift/marquee, folders included);
right-clicking an item that is not part of the selection resets the selection
to it (library `materialMenu` semantics, done in the event handler to avoid
setState-during-render), then the menu shows **Open** (single), **Assign to
node…** (always; acts on the whole selection incl. folders), and **Unassign**
(single: *Remove from node* / *Unassign folder*; multi: bulk, skipping
folder-derived rows and folders via `deallocateNodeFolder`). Every material
row/tile now opens a context menu — the `canUnassign` gate now only controls
whether *Remove from node* appears (child-section and via-folder entries can
still be opened and re-assigned). **Escape** clears the selection (library
keyboard handler pattern). Tests rerouted from the banner buttons to the
context-menu flows.

**Same-day refinement (user request): right-click always focuses the hovered
item.** The follow-up above kept the library's "keep the multi-selection if the
clicked item is part of it" rule; the user wants classic single-focus:
`openContextMenu`/`openFolderContextMenu` now **unconditionally reset** the
selection to the hovered material/folder, so the context menu always acts on
one item (Open / Assign-to-node / Remove-from-node | Unassign-folder). The
bulk `unassignSelected` path and the multi labels were deleted; the drag
payload still carries the whole selection (re-assign by drag remains).

## Context

The workspace **Materials tab** (`/courses/{id}?tab=materials`, `NodeWorkspace →
MaterialsTab`) is the placement view over a node's materials (ADR-056), but its
create affordances lag the Library: it has a split `UploadButton` (files/folder
only) and no way to create a text/Markdown file or a folder from there — the
user must detour to the Library. The user asked for the library's **+ ("New…")
dropdown** here too, plus **right-click → pane menu** and **rectangular marquee
selection**, reusing the library implementation for a single source.

What already exists and is shared (plan 24/25 groundwork):

| Piece | Status |
|---|---|
| Selection grammar (`useSelection`, `data-selectable-id`, `SelectionBar`) | already wired in MaterialsTab (plan 24 D) |
| Marquee (`useMarquee` + `MarqueeBand`, `components/ui/Marquee.tsx`) | shared primitive, Library is first consumer |
| `NewTextFileDialog` (now with the rich editor), `useMaterialUpload`, `ContextMenu`, `AssignToNodeDialog` | shared |
| Library pane menu item list (`paneMenu()` in `LibraryPage`) | **inline, not shared — the actual gap** |

### ADR-062 (recorded in `06-decisions-and-risks.md`)

The workspace Materials tab adopts the Library create grammar: one **+ New…**
primary affordance (dropdown: New text file / New Markdown file / New folder /
Upload files… / Upload folder… — the `UploadButton` split control is retired
there, matching the user's own library simplification of 2026-08-22), the same
items on **right-click over empty pane**, and **rectangular marquee**
selection. Created content lands per ADR-056's "workspace = placement" rule:
new files are created **unfiled in the course library and auto-allocated to
the opened node** (same semantics as tab uploads); a new folder is created at
library root **and assigned to the node** via `material_folder_links`
(ADR-058) so it appears in the *Assigned folders* strip — otherwise it would
be invisible (the tab is not a folder browser). The item list + hidden upload
inputs live in **one shared hook** (`useCreateMaterialMenu`) used by
LibraryPage and MaterialsTab; clipboard verbs (Cut/Copy/Paste) and *Add linked
folder* stay library-only. Alternatives rejected: reusing `UploadButton`
alongside a second + button (two create affordances — the thing the user
removed from the library); filesystem verbs in the tab (ADR-056 already
rejected); creating files *inside* a node-scoped folder view (nodes own no
folders).

## A — Shared create-menu primitive (`components/materials/`)

1. `createMaterialMenu.tsx` — `useCreateMaterialMenu({ upload, onNewText,
   onNewFolder, prepend?, append? })` → `{ items, inputs }`:
   - `items`: New folder / New text file / New Markdown file / Upload files… /
     Upload folder… (existing `library.*` i18n keys, upload entries gated on
     `upload.uploading` with pending spinner).
   - `inputs`: the two hidden file inputs (plain + `webkitdirectory`) wired to
     `upload.uploadFiles`, same aria-labels as today.
   - Callers compose: `prepend`/`append` carry surface-specific items.
2. `LibraryPage` adopts the hook: its own hidden inputs and the five inline
   `paneMenu()` entries are replaced by the hook (`prepend` = Paste when
   pasteable, `append` = Add linked folder); the inline folder-create form in
   the grid stays (library UX unchanged; `onNewFolder → setCreating(true)`).
   The + button and the pane right-click both use the same composed items.

## B — MaterialsTab wiring (`NodeWorkspace.tsx`)

1. Action row: **New…** primary trigger (PopoverMenu with the hook's items,
   Plus + chevron, spinner while uploading) + outline **Assign material**
   (Library icon instead of the second Plus). `UploadButton` import dropped;
   the empty-state `UploadDropzone` stays.
2. Pane right-click on the tab container: skip when `defaultPrevented` (entry
   menus) or when the target sits inside an interactive/selectable element;
   otherwise open `ContextMenu` at the cursor with the same items.
3. **New text/Markdown file**: `NewTextFileDialog` (shared) →
   `createTextFile({course_id, folder_id: null, …})` → `allocateMaterial(node,
   material.id)` → refresh `['tree']` + `['node-workspace']` + `['materials']`.
4. **New folder**: new small `components/materials/NewFolderDialog.tsx`
   (name input, Create/Cancel, Enter submits — `NewTextFileDialog` chrome
   without the editor) → `createFolder(name, null, courseId)` →
   `allocateNodeFolder(node, folder.id)` → refresh + invalidate `['folders']`.
   Errors surface in an `ErrorBanner` under the action row.
5. **Marquee**: `useMarquee` + `MarqueeBand` on the tab container
   (`data-marquee-surface`), unioned with the existing `useSelection` state —
   band spans sections; selection keys are already `m{id}` everywhere.

## C — Tests

- `NodeWorkspace.test.tsx`: + menu opens with all five items (replaces the
  split-button test); New Markdown file → dialog → `createTextFile` +
  `allocateMaterial(node, id)`; New folder → dialog → `createFolder(name,
  null, course)` + `allocateNodeFolder(node, id)`; right-click on empty pane
  shows the menu; marquee drag selects intersecting entries (rect-spy pattern
  from `LibraryPage.test`); existing upload tests keep passing (hidden inputs
  keep their labels; the split-button test is rerouted to the menu).
- `LibraryPage.test.tsx`: pane-menu/plus-button label tests keep passing
  (items identical, inputs still rendered by the hook); upload-from-menu test
  unchanged.

## D — Docs (same commit)

`docs/STATUS.md` (phase header + changelog + courses module row),
`docs/usage/courses.md` (Materials tab create verbs), ADR-062 in
`dev/plans/06-decisions-and-risks.md` (local-only).

## Verification

Full gate per AGENTS.md (backend untouched: ruff/mypy/pytest; frontend lint/
typecheck/test/build). CI mirrors.
