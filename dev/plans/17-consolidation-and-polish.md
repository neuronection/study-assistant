# 17 — Consolidation & polish round

**Status:** complete (2026-08-20: A–G all landed; G notes below) · **Phase:** post-1.0 polish (follows plan 16)
**Scope decision:** all quick wins + medium-effort items from the 2026-08-20 review;
**Playwright e2e explicitly excluded** (user decision — too much scaffolding for this round).

## G — as-built notes (2026-08-20)

- Lazy boundary is `LazyNoteEditor` (wraps **NoteEditor**, not MarkdownEditor) — one
  boundary covers drawer + route and also keeps DrawCanvas out of the entry.
- Vendor pinning via rolldown `codeSplitting.groups` (Vite 8): `react-vendor` (prio 40)
  > `framer-motion` (30) > `katex` (20). **No tiptap group**: a group's default
  `includeDependenciesRecursively` merges shared deps (react, use-sync-external-store)
  into the group — with tiptap pinned, the entry statically imported the whole 534 kB
  chunk just for react; with `includeDependenciesRecursively: false` react got
  duplicated + circular chunks (runtime TypeError). Automatic chunking handles tiptap
  correctly inside the lazy NoteEditor chunk (431 kB).
- Results: entry 2,067 → 697 kB min (627 → 192 gzip); boot closure = index +
  runtime + react-vendor + framer-motion + katex; verified via headless-Chromium
  smoke (playwright) on the built bundle.
- Residual (recorded in STATUS open issues): dual katex (0.18 + 0.16 via
  rehype-katex/remark-math/mermaid/markmap) both boot-load; pnpm override dedupe is
  a deliberate follow-up.


Slices are independent and shippable in any order; suggested order A → C → D → B → E → F → G
(A first because later slices render materials; C before B/D polish because they reuse its canvas).

## Context

Plan 16 landed the study launcher, the interactive mindmap with per-node actions
(`EntityActionMenu` + `NodeSource`), AI mindmap editing, and a first shared `MaterialRow`.
This round pays down the duplication and gaps that work exposed, closes the last 10E
remainder (MCP ↔ ContextResolver), and addresses the bundle-size open issue.

---

## A — Material display unification (finish the refactor)

**Problem.** Materials render in four ad-hoc ways: `LibraryPage` inline tile+row
(grid/list), `NodeWorkspace.tsx` local `MaterialRow` (drag/unassign/rationale/read-pill),
`MaterialPickerDialog.tsx` local `MaterialRow` (checkbox/status/assigned-chip), and
`GenerateDialog` (now on the shared `MaterialRow`, minimal fields).

**Design.**
- Extend `components/materials/MaterialRow.tsx` (`MaterialSummary` gains optional
  `status`, read-status/progress, `aiBadge`, `rationale`) with an `actions` ReactNode slot
  and optional `draggable`/`onDragStart` passthrough. Keep it dumb; no data fetching.
- New `components/materials/MaterialTile.tsx` — grid card (KindIcon large, title
  `line-clamp-2`, status pill) for the library grid layout.
- New `components/materials/MaterialList.tsx` — container: `layout: 'list' | 'grid'`,
  maps rows/tiles, empty-state text.
- Migrate call sites: `LibraryPage` (both layouts), `NodeWorkspace` MaterialsTab rows,
  `MaterialPickerDialog` rows. Behavioral parity per site (drag, unassign hover, assigned
  lock, chips stay as `action`/badge props).

**Accept.** No local material-row renderers left outside `components/materials/`;
library grid/list, workspace rows, picker rows visually unchanged.
**Tests.** Extend `MaterialRow.test.tsx` (new slots); add `MaterialTile`/`MaterialList`
render tests; adjust LibraryPage/Picker snapshot-ish assertions if selectors change.

## B — Mindmap history & undo (ride extraction versions)

**Problem.** Mindmap CRUD and AI edits replace the extraction wholesale; a bad edit or
bad AI rewrite is unrecoverable from the UI.

**Design.**
- Backend: `GET /materials/{id}/extractions` → `[{version, extractor, created_at}]`
  (newest first; cap ~50) and `GET /materials/{id}/extractions/{version}` → full
  `ExtractionOut`. Reuses the existing `Extraction.version` chain that `edit_extraction`
  already maintains — **no schema change, no restore endpoint**.
- Frontend: mindmap toolbar "⋯" dropdown gains **History…** → small dialog listing
  versions (extractor + timestamp, "AI edit"/"manual edit"/OCR provenance where
  derivable) with a preview of the selected version (reuses slice C's canvas, readonly)
  and **Restore** = `editExtraction(oldMarkdown)` (creates a new version — honest audit
  trail, trivially re-revertible).
- MindmapEditDialog "Apply" already flows through `editExtraction`, so every AI edit is
  automatically a new history entry — no extra wiring.

**Accept.** Edit a node, AI-edit the map, then restore the pre-AI version from History;
the map live-updates back.
**Tests.** Backend: list/get versions endpoint tests (ordering, 404s). Frontend:
History dialog renders versions and Restore calls `editExtraction` with the old markdown.

## C — Rendered mindmap canvas as a shared component

**Problem.** `MindmapViewer` owns the lazy-markmap bootstrap; `MindmapEditDialog`'s
preview shows raw markdown, and slice B needs a readonly canvas too.

**Design.** Extract `features/library/mindmap/MindmapCanvas.tsx`:
props `{ markdown; className?; onNodeClick? }` — encapsulates the
`Promise.all([import('markmap-lib'), import('markmap-view')])` bootstrap, fit-on-mount,
and the element→node click resolution currently inside `MindmapViewer`.
`MindmapViewer` delegates to it; `MindmapEditDialog` preview step and B's history preview
render `<MindmapCanvas markdown={previewMarkdown} />` (no click handler).

**Accept.** Mindmap behavior unchanged; AI-edit preview and history preview show the
real interactive map (pan/zoom; no selection).
**Tests.** Move/adapt the existing markmap-mock tests to the canvas; MindmapViewer keeps
its selection/delete test via the canvas's `onNodeClick`.

## D — Whole-map toolbar actions

**Problem.** The mindmap toolbar only offers Fit + AI edit; per-node actions exist but
there's no "act on the whole map" path and no way to add a root-level branch.

**Design.**
- `mindmapTree.ts`: `addRootNode(lines, label)` — append a depth-0 bullet after the last
  root node (mirror of `addChildNode` at depth 0).
- Toolbar dropdown gains:
  - **Add root node** — `window.prompt` label → `addRootNode` → `editExtraction` (same
    save path as node CRUD).
  - **Quiz on this mindmap** — opens `GenerateDialog` (task `quiz`) prefilled with
    `topic` = material title and `hint` = the whole-map LLM hint (same shape the node
    actions use), scope = the mindmap's placement node.
  - **Ask about this mindmap** — `createChatSession(courseId, scopeNodeId, material
    title)` + `openChat` (identical to the node-level ask, whole-map scope).
- `MindmapViewer` needs the material title → thread it from `ExtractionView`
  (`data.material.title`, already available).

**Accept.** Each toolbar action works end-to-end from the mindmap view.
**Tests.** `mindmapTree` unit test for `addRootNode`; MindmapViewer test that the
dropdown items invoke generate/chat/save with the right payloads (mocked).

## E — Entity actions on course-tree nodes

**Problem.** `EntityActionMenu`/`NodeSource`/`buildEntityActions` are generic but only
the mindmap implements a source; the course tree has its own ad-hoc context menu
(NodeTreeSidebar: add/rename/delete only).

**Design.**
- New `features/courses/courseNodeSource.ts`: `NodeSource<NodeInfo>` — `toEntity`
  (label = node title), `toContext` (`courseId`, `scopeNodeId = node.id`), no `llmHint`
  (retrieval scope is the node itself), no CRUD through the adapter (the sidebar's
  existing rename/delete/add stay as-is — they already work and are tested).
- `NodeTreeSidebar` context menu gains **Study…** which opens the `EntityActionMenu`
  (generate group only: Ask / Quiz / Exercises / Flashcards / Study guide / Write note /
  AI-edit is mindmap-specific → hidden for non-mindmap sources via the source's
  capabilities). Handlers mirror `MindmapViewer`'s (chat session bound to the node;
  GenerateDialog prefilled to the node; NoteComposeDialog; navigate to quiz on success).
  Factor those shared handlers into `features/ai/useEntityActionHandlers.ts` so the
  mindmap and the tree use one implementation.
- The AI-edit action becomes source-optional: `buildEntityActions` includes it only when
  the source is editable-by-AI (add `canAiEdit?: boolean` to `NodeSource`; mindmap true,
  tree false for now).

**Accept.** Right-click a course node → Study… → same action menu as a mindmap node;
quiz/ask/note generated against that node's scope.
**Tests.** `courseNodeSource` unit test; `buildEntityActions` capability gating test;
NodeTreeSidebar test (menu opens EntityActionMenu; a generate action opens the dialog).

## F — MCP resource server on the ContextResolver (10E remainder)

**Problem.** `app/mcp_resources.py` tools hand-roll their queries; the resolver is the
one context path everywhere else (ADR-042). External agents should see the same
budgeted, inspectable context.

**Design.**
- Add one tool: `get_node_context(node_id, scope='subtree', query?, max_chunks=12)` →
  renders the same `ContextBundle` manifest `POST /ai/context/preview` returns
  (materials with index-card summaries, notes, concepts, numbered excerpts — budgeted).
  No embeddings dependency (query optional → FTS-only is fine for agents).
- Keep the existing read-only tools untouched (they answer different questions);
  `get_node_overview` stays the cheap entry point, context is the deep one.
- Reuses `ContextResolver` + `ContextSpec`; embedder wired the same way `create_app`
  does (`app.state.embedder`). Mind the mcp purity constraint: the launch path must not
  import `app.main` — construct the resolver with the embedder exactly as the mcp server
  already builds its session factory.

**Accept.** `python -m courseassistant mcp` still launches stdio-only; the new tool
returns a manifest consistent with the in-app preview for the same node.
**Tests.** Extend the existing MCP e2e subprocess test with a `get_node_context` call
asserting manifest sections; unit test the resolver wiring.

## G — Bundle code-splitting

**Problem.** Main index chunk ≈ 2.06 MB minified (~625 kB gzip) — katex, framer-motion,
tiptap, cytoscape all land in the entry; open issue in STATUS.md (first-paint target
<1 s, doc 09).

**Design.**
- `React.lazy` the note editor: `components/editor/MarkdownEditor.tsx` is the only
  `@tiptap` import site → dynamic-import it from `NoteEditorDrawer` (and anywhere else
  it's rendered) with a Suspense spinner fallback. Mermaid/markmap/cytoscape are already
  lazy.
- Vite `build.rollupOptions.output.manualChunks` (rolldown `codeSplitting` config as the
  build warning suggests) to pin heavy vendor libs into separate cacheable chunks:
  `katex`, `framer-motion`, `react-vendor`, `tiptap`. framer-motion stays in the entry
  via `MotionConfig` in `main.tsx` — acceptable, it's small relative to katex/tiptap.
- Measure before/after from `pnpm build` output; record the numbers in the STATUS
  changelog. No behavior change.

**Accept.** Entry chunk drops materially (target: index < ~1.2 MB minified; editor +
katex in async/vendor chunks); app still boots, note editor still opens (lazy).
**Tests.** Existing suites; add one test asserting the editor still renders via the lazy
boundary (vitest handles dynamic imports natively).

---

## Non-goals (this round)

- **Playwright e2e smoke** — excluded by user decision (scaffolding cost).
- Tauri shell, offline embeddings (torch), local OCR, new question types, voice I/O —
  stay in the post-1.0 backlog.
- No schema migrations anywhere in this plan (B reuses extraction versions as-is).

## Verification per slice

Backend (`backend/`): `ruff check . && mypy . && pytest` — mandatory before commit.
Frontend (`frontend/`): `pnpm lint && pnpm typecheck && pnpm test && pnpm build`.
Docs: STATUS.md changelog entry per slice; `docs/features.md` / `docs/usage/` / `docs/ai.md`
where user-visible behavior changes (A, B, D, E user-visible; F developer-facing ai.md;
G none beyond STATUS). Plan doc updates stay local-only (gitignored).
