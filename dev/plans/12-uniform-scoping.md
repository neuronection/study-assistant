# 12 — Unified Node Tree & Uniform Scoping (Phase 9)

User decision (2026-08-19, **ADR-039**): retire the separate chapter/section tables in
favor of **one uniform node tree per course** (up to 4 node levels below the course =
5 layers total), and make every study resource placeable at any node — plus course
level — through a single mechanism. This doc is the complete design; it **supersedes
the first Phase-9 draft** (polymorphic `scope_type/scope_id`, ADR-038 as originally
written — never implemented) and the 2-level clause of ADR-035.

## Why this is the robust shape

| Problem in as-built / first draft | Resolution here |
|---|---|
| Chapters and sections are two tables with different rules (sub-chapter special cases, two APIs, two UI paths) | one `tree_nodes` table, one API, one workspace route — no node-type branches anywhere |
| ADR-038 needed polymorphic `scope_type/scope_id` (no DB-enforced integrity — a known anti-pattern) | scope is a plain `node_id` FK; a **composite FK** (`node_id, course_id` → `tree_nodes(id, course_id)`) makes intra-course placement *database-enforced*, not service-hoped |
| Roll-up logic per level ("chapter ⊇ its sections") | one subtree primitive (materialized `path` prefix) serves every scoped query at any depth |
| `material_links.owner_type`, `notes.owner_type`, `section_concepts` — three ad-hoc placement schemes | all migrate to `node_id`; attachment to non-node things (a note pinned to a material) stays a separate, explicit relationship |
| Placement duplicated content semantics (course-level vs chapter-level as different columns) | the course's own level = the course's **root node**; one representation of "course-wide" |

Depth itself is not the win — unification is. Depth is capped at 4 node levels;
deeper trees are structurally refused (service + CHECK), not just discouraged.

## Data model

### New table: `tree_nodes`

```
tree_nodes:
  id           PK
  course_id    FK courses.id            (indexed with parent: (course_id, parent_id))
  parent_id    FK tree_nodes.id NULL    (NULL ⇔ this node IS the course root)
  title, summary, objectives JSON       (carried over from chapters/sections)
  order_idx    INT                      (sibling order, gap-numbered 1000s for cheap inserts)
  depth        INT  CHECK (0 <= depth <= 4)   (0 = course root, 1..4 = layers)
  path         TEXT                     ("/7/31/94/" id-chain from root; unique index)
  sort_path    TEXT                     (zero-padded order_idx chain → ORDER BY = depth-first)
  is_root      BOOL                     (exactly one per course, enforced unique partial index)
```

Invariants (how each is enforced — belt and suspenders by design):

| Invariant | Enforcement |
|---|---|
| One root per course | `UNIQUE(course_id) WHERE is_root` (partial index) |
| Root has no parent, non-root must | service (cheap, with tests) |
| `depth` = parent.depth + 1, ≤ 4 | service on write; CHECK bounds column regardless |
| `path`/`sort_path` correct for all descendants | service rewrites the moved subtree's paths in one transaction; a startup + migration self-check query verifies table-wide consistency |
| Intra-course parenting | composite FK `(parent_id, course_id)` → `tree_nodes(id, course_id)` (same trick as content placement) |

**Why materialized path (not closure table / pure recursive CTE):** subtree membership
becomes an indexed `path LIKE :prefix || '%'` scan and depth-first ordering becomes
`ORDER BY sort_path` — no recursion on read, at the cost of rewriting a subtree's paths
on move/reorder (bounded: ≤ the subtree size; personal scale = hundreds of nodes).
Closure table was rejected: 3× write amplification on every move for query patterns we
can already index. Escape hatch: paths are derived data — rebuildable from
`parent_id`/`order_idx` at any time, so the storage strategy can change later without
a data migration.

### Placement: one column, everywhere

Every placeable resource drops its old scope columns and gains the same pair:

```
node_id   FK tree_nodes.id NULL    (NULL ⇔ unbound/legacy; the course root IS course level)
course_id (existing)               + composite FK (node_id, course_id) → tree_nodes(id, course_id)
```

- **activities** (quizzes), **exercises**, **flashcards**: drop `section_id`, gain
  `node_id`. `course_id` stays the ownership/workspace axis (ADR-033/036 semantics
  untouched — purge, cost grouping, "All courses" mode).
- **notes**: gain `node_id` (placement); `owner_type/owner_id` remain **only** for
  attachment to non-node resources (`material`, `exercise_session`, `chat_message`);
  `section` owner_type migrates to `node_id`; `standalone` ⇔ both null. Fixes the
  chapter-notes hole en route.
- **material_links**: `owner_type/owner_id` → `node_id` (course-level links → root
  node). Rationale/audit columns unchanged. Unlink ≠ delete stays.
- **concept coverage**: `section_concepts` → `node_concepts(node_id, concept_id,
  weight, UNIQUE(node_id, concept_id))`. Concepts stay **course-owned** (one graph per
  course, 8D) — a concept means the same thing at every depth; nodes *cover* it.
- **chat_sessions**: gain `node_id` (binding + retrieval narrowing; root = course-wide).

### What is deliberately NOT unified

- `course_id` remains on every content row (ownership/purge — ADR-036 unchanged).
- Note attachment (`owner_type`) is a different relationship from placement.
- The Library/folder tree (`material_folders`) is a *filing* structure, not a study
  hierarchy — stays separate (a material files into folders, links into nodes).
- Materials are still linked, never copied (8A law).

### Migration 0019 (single migration, clean cut)

1. Create `tree_nodes`; **backfill**: each course gets a root (depth 0); chapters →
   depth-1..k nodes preserving the existing parent chain (chapters could nest one
   level — mapped as-is); sections → children of their chapter's node. `path`/
   `sort_path` computed in the same pass.
2. Remap placements: `material_links.owner_*` → `node_id` (course → root);
   `activities/exercises/flashcards.section_id` → `node_id` (NULL+course_id → root
   node — course-scoped content becomes root-placed, unbound stays NULL);
   `notes.owner_type='section'` → `node_id`; `section_concepts` → `node_concepts`.
3. Drop `chapters`, `sections`, `section_concepts`, `material_links.owner_type/
   owner_id`, `section_id` columns. **No dual source of truth survives the migration.**
4. Mandatory migration test (the 0014 pattern): a fixture DB with nested chapters,
   every placement kind, and unbound content → assert node tree shape, every remap,
   purge integrity, and the path/sort_path self-check query.

## Backend

### `app/services/tree.py` (new) — the only place that touches tree structure

```
create_node / rename / set_summary / reorder / move / delete(merge_into_parent)
subtree_ids(node)          # path-prefix scan
descendants(node, depth?)  # depth-first via sort_path
breadcrumb(node)           # root ▸ … ▸ node (course title first)
scoped_criterion(table, node, include_children=True)  # table.node_id IN subtree or = node
ensure_course_root(course) # created with the course, never deletable
```

- Move/delete enforce depth ≤ 4 (refuse 422 with a clear message, like the 2-level
  rule today); delete **merges**: children + placements + links reparent to the
  deleted node's parent (the outline editor's existing UX, generalized); the root is
  undeletable.
- Every scoped endpoint and every purge goes through this module — no resource
  service re-implements tree logic (the rule that kept 8A honest).
- **Purge**: course deletion already cascades via `course_id` (8A); now also removes
  the node subtree (FK cascade from course → root → descendants).

### API (REST, same conventions as today)

- `POST /courses/{id}/nodes` · `GET /nodes/{id}` · `PATCH /nodes/{id}` (rename/
  summary/objectives) · `POST /nodes/{id}/reorder` · `POST /nodes/{id}/move`
  (cross-course move → 422, intra-course always OK if depth allows) ·
  `DELETE /nodes/{id}` (merge semantics above).
- `GET /nodes/{id}/workspace` — the one workspace payload: breadcrumb, node info,
  children (with per-child quick stats), placed materials (+read-status), notes,
  coverage, scoped counts. Replaces `GET /chapters/{id}/workspace`.
- Scoped lists keep their existing URL shapes, gaining uniform params:
  `?node_id=…&include_children=1` (default 1) on quiz activities, exercises,
  flashcards, notes, chat sessions; create/generate endpoints accept `node_id`.
  `node_id` = root ⇔ course-wide. Unbound content appears only in "All courses"
  (ADR-033 unchanged).
- Old `/chapters/*`, `/sections/*` endpoints are **removed** (clean cut; frontend
  migrates in the same phase — both suites green before commit, per AGENTS.md).

### Generation & retrieval under a scope

- quizgen/exgen/flashcards: optional `node_id` narrows retrieval to the subtree's
  material links + covered concepts; falls back to course-wide when subtree material
  is thin (existing clamping behavior, now depth-general). Titles carry the
  breadcrumb tail ("Ch 3 · Limits — practice").
- Chat: `node_id` binds the session and scopes RAG retrieval to the subtree.
- Organizer (8E) / outline (P3) / concepts (8D) pipelines: vocabulary swap
  chapter/section → node (depth-aware labels below); outline AI keeps drafting
  **2 levels by policy** (ADR-035's outline-quality rationale survives as policy,
  not schema); "review this chapter" becomes "review this node".

### AI / MCP resource layer

The scoped read services are the tool surface — thin, typed, read-only:
`get_node_overview`, `get_materials(node)`, `get_concepts(node)`,
`get_exercises(node)`, `get_quizzes(node)`, `get_notes(node)`, each accepting
`include_children`. The in-app tutor calls them as context tools; slice 9E (stretch,
explicit user go-ahead) wraps the same functions in a local FastMCP server for
external agents. No write tools, by construction.

## UI — one workspace, any depth

One route, one component tree — the course page *is* the root node's workspace:

```
/courses/$courseId              → NodeWorkspace(root)
/courses/$courseId/n/$nodeId    → NodeWorkspace(node)
```

- **Routable tab rail** (`?tab=`, the Settings/Scores pattern):
  `Overview · Materials · Notes · Concepts · Practice · Cards · Tutor` — identical
  components at every depth; only the scope changes. Sections-as-rows disappear;
  the Overview tab shows the node's children as cards with quick actions (open,
  quick-practice, ask tutor) at any depth.
- **Breadcrumb + course accent** (doc 09) = persistent scope identity; every item
  carries a scope chip (course badge / node crumb) so origin is always visible.
- **Tree navigation**: the Outline tab becomes a real collapsible tree (TanStack
  Virtual — doc 09's plan for chapter trees finally lands) with DnD
  move/reorder (generalized from the chapter DnD that exists), inline rename,
  depth-aware insert (child/sibling), depth cap surfaced honestly ("max depth
  reached" instead of silently hiding the action).
- **Depth-aware labels, cosmetic only**: depth 1 "Chapter", 2 "Section",
  3 "Subsection", 4 "Topic" — defaults in UI/AI prompts, never stored per node.
- **"Study here" CTA** adapts by *span*, not type: root → mixed exam-style review;
  mid-tree node → test of its subtree; leaf → quick practice. One flow, one runner.
- **Generate dialogs** default to the current node with a tree picker + "whole
  course" escape (progressive disclosure, doc 09).
- **Roll-up honesty**: counts split "here vs in children" ("6 notes here · 14 in
  sub-sections"); the Notes/Materials tabs show owner chips per row.
- Command palette: node-addressable actions ("quiz me on Ch 3", "notes of §3.2")
  reuse the scoping service; palette tree results gain depth indentation.
- Existing flat pages (Quiz/Exercises/Flashcards/Notes) keep working — they are the
  "All courses" views; workspaces are the structured entry, not a replacement.

## Performance notes (why this is fast)

| Operation | Cost |
|---|---|
| Subtree membership (every scoped query) | indexed `path` prefix scan — one index range, no recursion |
| Depth-first outline ordering | `ORDER BY sort_path` (indexed) |
| Sibling insert | gap-numbered `order_idx` → no renumbering; sort_path rewrite only when a gap is exhausted |
| Move/reorder | rewrite moved subtree's `path`/`sort_path` rows only, one transaction |
| Workspace payload | one `GET /nodes/{id}/workspace` aggregates with the two patterns above; personal scale (≤ ~10⁴ nodes) is far under any budget |

Derived-data rule: `path`/`sort_path`/`depth` are rebuildable from `parent_id` +
`order_idx`; a self-check query runs at migration and startup (cheap COUNT of
violations) so drift is caught, never silently accumulated.

## Phase 9 slices (vertical, shippable in order)

### 9A — Tree schema + service + migration + scoped APIs (backend)
Migration 0019, `services/tree.py`, node CRUD/move/reorder/delete-merge APIs,
scoped list/create params on activities/exercises/flashcards/notes, material_links +
notes + coverage remap, old chapter/section endpoints removed, purge extended.
Rewire outline/organizer/concepts services to node vocabulary (behavior-preserving).
**Accept:** every resource placeable/listable/rolled-up at any node ≤ depth 4 and at
course level; cross-course placement impossible (DB-enforced, tested); unbound
content unaffected; migration test green; full backend suite green.

### 9B — NodeWorkspace (frontend)
One route/scaffold for course + any node, tab rail, Outline-as-tree with DnD,
Study-here CTA, scope chips, generate-dialog tree picker, palette actions, migrated
course/chapter pages (old routes redirect).
**Accept:** zero duplicated scope components; note created in a nested node appears
in its ancestors' rolled-up tabs; quiz generated at a node scopes retrieval and
titles correctly; DnD move/reorder hits the new APIs.

### 9C — Concept coverage per node
`node_concepts` (landed in 9A's migration) surfaced: concepts UI accepts coverage at
any depth; extraction drafts coverage at node granularity; weakness-matrix and
drill-by-concept actions deep-link into the right workspace.
**Accept:** cover a concept at a mid-tree node; roll-up shows it at ancestors;
"drill this concept" starts a session scoped to the concept's nodes.

### 9D — Scope-bound tutor chat
Sessions accept `node_id`; "Ask about this node" button in the workspace header;
Today-screen recommendations link to scoped sessions.
**Accept:** node-scoped session retrieves only that subtree's material; session lists
in the workspace Tutor tab.

### 9E — MCP resource server (stretch — explicit user go-ahead required)
FastMCP localhost server over the read-only resource functions; profile/node args;
no write path. **Accept:** external agent lists a node's exercises/concepts/materials
by id.

## Testing & verification

- Migration 0019 backfill test (nested chapters, every placement kind, unbound rows).
- Tree service tests: depth cap, cycle-safe move (node into own descendant → 422),
  path/sort_path rewrite correctness, merge-delete.
- Composite-FK violation tests (cross-course placement rejected at DB level).
- Roll-up tests at depth 3–4 (the depths that never existed before).
- Frontend: workspace tests at root/mid/leaf depths; tree DnD; palette.
- Suites per AGENTS.md; `docs/data-model.md` + STATUS.md updated in-slice.

## Risks / mitigations

| Risk | Mitigation |
|---|---|
| Largest migration since 8A (many FK remaps) | single transaction, mandatory fixture-based migration test, path self-check query, full backup/restore already exists (I6) |
| Path/sort_path drift after bugs | derived-data rule: startup self-check + rebuild function; drift is detectable and repairable |
| Deep trees hurt AI outline quality (ADR-035's original worry) | outline task drafts 2 levels by policy; deeper levels manual; prompts use depth-aware labels |
| UI clutter at depth 4 | virtualized tree, collapsible default depth 2, quick actions only on hover/focus |
| Generation quality at narrow scopes | retrieval falls back to course scope when subtree material is thin (existing clamp, generalized) |
| Users rely on old /chapters URLs | 9B redirects old routes to the node equivalent for one release |
