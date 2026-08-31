# 21 — Node settings popover: AI instructions move out of Overview, description becomes editable

**Status:** complete (S1–S5, 2026-08-21). As-built deviations from the sketch:
(1) **root title is editable after all** — user follow-up ("we need edit title too");
root Title+Description route through `PATCH /courses/{id}` together, hint stays a node
PATCH. (2) **One backend fix was needed** (plan said zero): `update_course` never
synced its root node, so course renames/description edits left the workspace header
stale — it now mirrors `course.title`/`course.description` into the root row
(latent title bug fixed en route; test added). (3) `Popover` gained a `closeSignal`
prop so the menu can close itself after a successful save.
**Inputs:** user review of `/courses/{id}`: the **AI Instructions for this node** card takes
prime space in the Overview tab; the node/course **description is never shown in practice**
because nothing in the workspace can set or edit it. User asked for: a dedicated home for
AI instructions (tab vs dropdown) + description display. Discussion decision (2026-08-21):
**header popover** anchored next to the node title — not a Settings tab (tabs are study
content; configuration is header-level and should be reachable from every tab).
**Phase:** post-1.0 polish (follows plan 20; follows the FocusShell uniformity direction —
chrome belongs in chrome).

---

## Problems

1. `AiHintCard` (overview, `NodeWorkspace.tsx` ~L359) is a full Card for one textarea —
   big footprint, only on Overview, feels like content but is configuration.
2. Node/course description (`node.summary`; root mirrors `course.description` — tree
   service already does this) *is* rendered under the workspace title (`~L1311`), but no
   workspace UI can create or edit it: `PATCH /nodes/{id}` accepts `summary` yet the
   frontend only wraps `renameNode` + `updateNodeHint`. Root nodes additionally refuse
   title/summary edits at the node level (`services/tree.py`: "the course root cannot be
   edited here") — root description must go through `PATCH /courses/{id}` (which has
   `description`).
3. No popover/anchored-menu primitive exists in `components/ui/` (dialogs are hand-rolled
   overlays; `EntityActionMenu` is a centered modal, not an anchor dropdown).

## Design

### S1 — `Popover` primitive

`frontend/src/components/ui/popover.tsx`:

```tsx
export function Popover({
  trigger,        // ReactNode (rendered as-is; wrapper owns positioning)
  children,       // panel content
  align = 'end',
  panelClassName,
  label,          // aria-label for the trigger wrapper + panel aria role
})
```

- Wrapper `span.relative.inline-flex`; panel `absolute` under the trigger
  (`top-full mt-2`, `align end` → `right-0`, `start` → `left-0`), `z-40`,
  `bg-surface border rounded-lg shadow-lg w-80 p-3` (size overridable).
- Open on trigger click; close on outside pointerdown, Escape, and focus leaving the
  panel (keyboard-friendly: panel gets `tabIndex={-1}` + autofocus, inputs inside are
  natural tab stops). No portal needed (header has no `overflow` clipping ancestors).
- Deliberately tiny — no Radix dependency, no generic positioning engine. If a second
  anchor use appears later, promote rather than pre-abstract.

### S2 — `NodeSettingsMenu` (feature component)

`frontend/src/features/courses/NodeSettingsMenu.tsx` — the popover content + icon button:

- **Trigger**: `Button variant="ghost" size="icon"` with `Settings2` (lucide) next to the
  workspace title (`NodeWorkspace` header row, after the title block, before the
  Study here/Ask actions — visually grouped with node identity). **Dot badge** on the
  icon (`bg-primary` corner dot) when `node.ai_hint` is non-empty — signals "this node
  has custom AI instructions" at a glance. `title`/`aria-label` = "Node settings".
- **Panel** (one column, `space-y-3`, text-sm):
  1. **Title** input (non-root only; sidebar rename stays as-is — two paths to one
     action is fine, the sidebar is the power path). Root title = course title; editing
     course titles belongs to the Courses list, not here.
  2. **Description** textarea (`min-h-16`): non-root → `node.summary` via
     `updateNode`; root → `course.description` via `updateCourse` (label stays
     "Description" either way — no schema talk in UI).
  3. **AI instructions** textarea: `ai_hint` via the same `updateNode` call (or
     node-level PATCH for root — hint edits on root are allowed by the backend).
- **Save behavior**: single **Save** button (primary sm) at the panel footer, disabled
  until something changed; saves all three fields in their respective calls
  (`updateNode` batches title+summary+ai_hint in one PATCH; root does
  `updateCourse({description})` + node PATCH `{ai_hint}`); spinner while pending;
  success = panel closes; errors render in an `ErrorBanner` inside the panel (keeps the
  user's typed text). Invalidations: `['node-workspace', id]`, `['tree', courseId]`,
  `['courses']` (root description only lives on the course).
- Placeholder copy explains what each field does (i18n keys, no literals):
  description → "Shown under the node title"; AI instructions → reuse the existing
  `generate.hintCardDescription` text.

### S3 — Header description display + AiHintCard retirement

- Header already renders `node.summary` under the title — **keep**, plus
  `line-clamp-2` + full text in the `title` attr (long AI-drafted summaries shouldn't
  stretch the header). Same treatment in `NodeTreeSidebar`? No — out of scope.
- Delete `AiHintCard.tsx` + its mount in `OverviewTab` + `generate.hintCard*` i18n keys
  that no longer apply (retitle the ones reused by the popover). Overview gets visibly
  shorter — objectives chips then straight into the action bar's results.
- `updateNodeHint` API wrapper is superseded by the general `updateNode` — replace and
  delete it (check other callers: none expected, `AiHintCard` is the only one).

### S4 — API wrappers (frontend only)

`frontend/src/lib/api.ts`:

- `updateNode(id, body: { title?; summary?; ai_hint? })` → `PATCH /api/v1/nodes/{id}`
  (backend `NodeUpdate` also takes `objectives` — omit until needed).
- `updateCourse(id, body: { description? ... })` → `PATCH /api/v1/courses/{id}`
  (add fields as needed; `CourseUpdate` already supports them).
- **Backend: zero changes.** Every endpoint + the root-summary-mirrors-course behavior
  already exist.

## Non-goals

- No objectives editing (the Overview chips stay read-only; objectives come from the AI
  outline — revisit when outline UX matures).
- No sidebar changes; right-click rename/delete/add-child untouched.
- No rich-text description (plain textarea, like the hint today).
- Not touching other pages' headers (this is workspace-level chrome).

## Slices & order

1. S1 `Popover` + tests (open/close on click, outside, Escape; align class; aria).
2. S4 API wrappers (compile-only, no UI yet).
3. S2 `NodeSettingsMenu` + header mount + badge; tests (field render per root/non-root,
   save batching, changed-detection, error path).
4. S3 description clamp + `AiHintCard` retirement + i18n cleanup + workspace test updates.
5. Docs: `docs/STATUS.md` (changelog + Courses row), `docs/usage/courses.md` (header
   section: settings popover, badge meaning, description), plan README index row.

## Acceptance

- Overview tab no longer contains the AI instructions card.
- From any tab: gear next to the title → popover with Title (non-root) / Description /
  AI instructions; Save persists and the header description updates in place.
- Root workspace: popover edits Description (course) + AI instructions (node); no title
  field; no 422 from the backend.
- Icon shows the badge iff an AI instruction is set (survives reload — it's server data).
- `AiHintCard.tsx`, `updateNodeHint` gone; grep finds no stragglers.
- Popover closes on outside click and Escape; nothing in it commits on blur/typing.

## Tests

- `Popover.test.tsx`: trigger opens; outside pointerdown + Escape close; `align` class;
  content interactive while open.
- `NodeSettingsMenu.test.tsx`: non-root renders title+description+hint, root omits
  title; save issues the right PATCH(es) (batched node PATCH; root = course PATCH +
  node PATCH); unchanged-save disabled; failed save keeps text + shows banner.
- `NodeWorkspace.test.tsx`: overview no longer renders the old card; badge present iff
  hint set; header shows description with clamp class.
- i18n: no new literal strings (eslint `no-literal-string` covers).

## Verification

Frontend per slice: `pnpm lint && pnpm typecheck && pnpm test && pnpm build`.
Backend untouched — one full `ruff && mypy && pytest` at the end as a sentinel.
Docs per ca-docs-sync (S5 slice above).
