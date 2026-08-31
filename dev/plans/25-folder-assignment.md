# 25 — Folder assignment: assign library folders (incl. linked sources) to nodes

**Status:** COMPLETE 2026-08-22 (A committed first, then B–D; 425 backend +
490 frontend tests green) ·
**Phase:** post-1.0 polish (follows plan 24) · user-approved 2026-08-22

**Follow-up same day (ADR-059):** activation grammar across the plan-24
surfaces — single click selects, double-click/Enter opens (see changelog).

## Context

User request: the library supports directories (virtual folders + linked-source
folders), but course assignment is file-only — `material_links` rows point at
individual materials. Assigning a whole directory today means bulk-selecting
its files (`MaterialPickerDialog` FolderToggle / select-shown), which (a) is a
snapshot: files added later (uploads, folder-scans, ingests) never join, and
(b) doesn't work at all for linked-source folders (no bulk toggle there).

**What this round adds (ADR-058):** a second placement type —
`material_folder_links` (folder ↔ node) — with **dynamic membership resolved
at read time**: a node's effective materials = direct material links ∪
members of its assigned folders. Assign once, stay in sync.

### Existing semantics to respect (not change)

- One material = one blob; the ingest/extraction/chunk pipeline is untouched
  (folders never become materials).
- Intra-course placement is DB-enforced (ADR-039 composite FK
  `(node_id, course_id)`); folder links carry the same constraint.
- Linked-source folders: subdirectories are *not* modeled (browsed as `subdir`
  strings); source-scanned materials have `folder_id = NULL` and carry
  `source_id` — folder membership for them resolves via `Material.source_id`.
- Folder delete **cascades**: the folder, its whole subtree and every file in it are
  permanently purged (**ADR-066 supersedes the original "lifts contents to the parent
  (never cascades)" clause**); unlink keeps materials (see below).
- Node merge-delete re-points placements to the parent and dedups; restore
  snapshots (`plan 13` undo) must include the new placement type.
- Compose artifacts and outline commits always write **direct** material
  links — unchanged.

**ADR (recorded in `06-decisions-and-risks.md`):**

| # | Decision (one line) |
|---|---|
| ADR-058 | Folder assignment is a second link table (`material_folder_links`, composite FK like material_links) whose membership is **resolved at read time** — virtual folders by subtree (`path` prefix), linked sources by `source_id` membership — never materialized into material links; direct links win on overlap; unassigning a folder-derived material is refused with an actionable message; deleting/unlinking a folder with active assignments is refused; node merge-delete/restore treats folder links as placements; export/import round-trips them |

Deliberately out of scope: per-material exclusion rows inside an assigned
folder (generation-time opt-out already exists via ContextSpec
`exclude_material_ids`); recursive folder copy; assigning *subdirectories of
linked sources* (no rows exist for them — only the source root folder is
assignable).

---

## A — Backend: model, migration, service, resolution

1. **Migration 0030** + model `MaterialFolderLink` (`material_folder_links`):
   `id`, `course_id` FK, `node_id` Integer, `folder_id` FK →
   `material_folders.id`, `rationale`, `auto_assigned`, `confidence`,
   `created_at`; unique `(node_id, folder_id)`; composite FK
   `(node_id, course_id)` → `tree_nodes(id, course_id)` — mirror of
   `MaterialLink`.
2. **Resolution helpers** (`services/folders.py` — folder domain, models-only
   imports, no cycles):
   - `folder_member_ids(session, folder) -> set[int]` — source folder:
     `Material.source_id == folder.source_id`; virtual folder: materials with
     `folder_id ∈ {folder} ∪ descendants` (path prefix, same profile+course).
   - `folder_links_by_node(session, node_ids) -> dict[node_id, list[link]]`.
3. **StructureService** (`services/courses.py`):
   - `assign_folder(node_id, folder_id, rationale, auto_assigned, confidence)`
     (validates node/folder exist, same course, idempotent update-on-exists)
     and `unassign_folder(node_id, folder_id)`.
   - `unassign` (material): if no direct link exists but the material is
     folder-derived at that node → `CourseError("assigned via folder …")`
     → 422 (UI hides the verb for such rows; error is the API honesty path).
   - `course_materials`: entries gain `via_folder: {id, name} | null`;
     folder-derived materials appear (deduped; direct wins).
   - `material_links` (assigned-to chips): + folder-derived chips with
     `via_folder: {id, name}`.
4. **Read paths made folder-aware** (all through the same helpers):
   - `tree.subtree_material_ids` — union folder-resolved ids (feeds
     ContextResolver subtree scope → generation, chat, MCP).
   - `context._scope_material_ids` node scope — same union.
   - `tree._direct_counts` — materials/studied counts per node = resolved
     sets (grouped-count fast path kept for nodes without folder links).
   - `tree.workspace` — `materials`/`child_materials` entries gain
     `via_folder_id`/`via_folder_name` (dedup, direct wins); new
     `folders: [{folder_id, name, source_id, member_count}]` section for the
     node's folder links (children included via their own links).
   - `tree.tree` — per-node `folder_links: [{folder_id, name, count}]`
     (counts use resolved materials; direct `materials` list unchanged).
   - `organizer` node review — folder-derived counts as linked (no false
     "unlinked material" hints).
   - `proposal_actions.assign_material` revalidation — folder-derived =
     already satisfied.
   - `course_bundle` export/import — folder links section (old bundles
     without it import cleanly; same format version, additive field).
5. **Lifecycle**:
   - `purge_course` deletes `material_folder_links` by course_id.
   - `PLACEMENT_TABLES` += `material_folder_links` (node merge-delete re-points
     + parent-dedup like material links; restore snapshots/undo include them).
   - `FoldersService.delete` + `unlink_source_folder`: refuse (FolderError →
     422) while folder links reference the folder — "unassign it first".
     Rename/move need nothing (links are id-based).
6. **Endpoints** (`api/courses.py`): `POST /nodes/{id}/folder-materials`
   `{folder_id, rationale?}`, `DELETE /nodes/{id}/folder-materials/{folder_id}`,
   + course-level twins (root node) mirroring the material allocation routes.

Tests (`backend/tests/test_folder_links.py`): assign/unassign happy + idempotent
+ cross-course/unknown 422s; membership (virtual subtree, source via
source_id, direct-wins dedup); workspace/tree payloads (folders section, via
flags, counts); course_materials + chips; resolver node/subtree scope includes
folder members; unassign-via-material 422; folder delete/unlink refused while
assigned, rename/move keeps resolution; node merge-delete dedup + restore;
export/import round-trip; purge; organizer no false gap.

## B — Frontend: picker assigns folders

`MaterialPickerDialog`: every folder row (sidebar + list, **including
linked-source folders**) gains an *Assign folder* toggle next to the existing
count/bulk-select affordance; selected folders tracked alongside materials
(`selectedFolders: Map<folderId, name>`); folders already assigned to the
target node are locked (reuse assigned-lock pattern; new prop
`assignedFolderIds: Set<number>` from the workspace payload); Allocate sends
material + folder assignments sequentially, then invalidates
`node-workspace`/`tree`/`materials`. FolderToggle (bulk file select) stays —
the two are visually distinct (folder badge vs count). i18n keys throughout.

Tests: assign-folder toggle + payload, locked folders, both kinds selected at
once, error surfacing.

## C — Frontend: workspace Materials tab

- Folder-derived rows render a `via {folder}` badge; unassign verb hidden on
  them (row button, context menu, and bulk bar skips them — direct-only).
- New **Assigned folders** strip: folder chips (name + member count +
  link-source dot) with per-chip unassign (new endpoint) — the one-click undo
  for B.
- `api.ts`: `assignNodeFolder`/`unassignNodeFolder`, `WorkspaceFolder` +
  `via_folder` fields on workspace material entries.

Tests: badge render + unassign gating (single/bulk), folder strip unassign
mutation + invalidations, child-section badges.

## D — Frontend: library + detail chips

- `AssignToNodeDialog` generalized: accepts `{materialIds} | {folderIds}`
  (title/count/confirm strings already parameterized in plan 24 D).
- Library folder context menu gains **Assign folder to node…** (linked-source
  folders included; disabled where links exist? no — assignment is the
  feature; only delete/unlink are restricted).
- Material detail assigned-to chips render folder-derived chips with a folder
  glyph.

Tests: dialog folder mode payload, library menu wiring, chip rendering.

---

## Verification

Per slice, before commit: `ruff check . && mypy . && pytest` (backend) ·
`pnpm lint && pnpm typecheck && pnpm test && pnpm build` (frontend). Docs
(`docs/STATUS.md`, `docs/features.md`, `docs/data-model.md`, usage guides)
updated in the same commits.
