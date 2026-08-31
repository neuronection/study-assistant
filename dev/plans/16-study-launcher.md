# 16 — Study Launcher (AI actions from the node workspace)

**Status:** proposal (2026-08-20) · **ADR:** 044 · **Phase:** post-1.0 backlog (approved by user)

## Problem

The node workspace's **"Study here"** CTA is a single-purpose shortcut: it silently
generates an 8-question quiz for the current node and jumps into the quiz runner
(`NodeWorkspace.tsx`). There is no way to choose a scope, pick sources, or ask for a
different kind of AI help from that one button. The user expects a modern, context-aware
form — select scope (node/subtree/course), select materials/notes/concepts, then choose
what the AI should do (quiz, exercises, flashcards, study guide, summary, practice set,
mindmap, write a note, …).

## What already exists (reuse, don't rebuild)

- `GenerateDialog` (`frontend/src/features/ai/GenerateDialog.tsx`) already has scope
  selection, material include/exclude, notes, concepts, difficulty/count, a context hint,
  a live AI-context preview, and four actions: `quiz`, `exercise`, `flashcards`, `compose`.
- Backend task registry (`app/ai/tasks.py`) + compose pipeline
  (`app/pipelines/compose.py`, kinds `study_guide`/`summary_sheet`/`practice_set`/
  `error_recap`) + note actions (`app/api/notes.py`).
- Context resolution (`app/services/context.py`) is the single way every action scopes
  its sources.

## Design

**"Study here" becomes a launcher**, not a shortcut:

1. Button opens `StudyLauncherDialog` — a grid of AI actions:
   Quiz · Exercises · Flashcards · Study guide · Summary sheet · Practice set ·
   Error recap · **Mindmap** (new) · **Write a note** (new).
2. Each action opens the right tool, pre-scoped to the current node:
   - Quiz / Exercises / Flashcards → existing `GenerateDialog` (task = …).
   - Study guide / Summary sheet / Practice set / Error recap → `GenerateDialog`
     (task `compose`, preselected kind).
   - Mindmap → `GenerateDialog` (task `compose`, kind `mindmap`).
   - Write a note → new `NoteComposeDialog` → `POST /notes/compose`.

### New backend pieces

1. **`mindmap` compose kind** — add to `KINDS` in `app/pipelines/compose.py`; the prompt
   (`COMPOSE_SYSTEM`) asks for a **markdown outline** (nested bullet lists, no headings).
   Output is still a `Material` (consistent with every compose kind), `provenance.kind =
   "mindmap"`. On the material detail page, a mindmap material renders as an **interactive,
   collapsible `markmap` mindmap** (`MindmapViewer`; `markmap-lib` + `markmap-view`, lazy
   loaded so it stays out of the main bundle).
2. **Note compose** — `POST /notes/compose` in `app/api/notes.py`. Reuses the
   `ContextResolver` (same scope + include/exclude + notes + concepts + hint as compose),
   a new `note.compose` skill (`NOTE_COMPOSE_SYSTEM`, task `description` — same routing as
   `notes.action`), a `max_words` contract, and creates a `Note` placed at the node via
   `TreeService.placement_node`. Returns `NoteDetail` so the drawer can open it directly.

### New frontend pieces

- `StudyLauncherDialog` (menu), `NoteComposeDialog` (title + focus + scope + hint),
  `composeNote()` API client, `mindmap` added to `COMPOSE_KINDS`, i18n keys.

## Mindmap node actions (reusable entity-action menu)

Clicking a mindmap branch selects it and opens an **action menu** — this is the same
"selected entity → actions" pattern other surfaces (course tree, concepts, notes) should
reuse, so it's built generically:

- **`NodeSource<T>` adapter** (`components/entity-menu/types.ts`) — the
  "converter/processor" interface: `toEntity`/`toContext` (id, label, courseId,
  scopeNodeId), optional `llmHint` (whole structure + selected node, capped), and optional
  CRUD (`canEdit/edit`, `canRemove/remove`, `canAddChild/addChild`).
- **`EntityActionMenu`** (`components/entity-menu/EntityActionMenu.tsx`) — dumb, reusable
  menu (title + grouped action buttons); `buildEntityActions` assembles the groups from a
  source + handlers.
- **`MindmapSource`** (`features/library/mindmap/mindmapSource.ts`) — the mindmap adapter,
  backed by **`mindmapTree.ts`** (markdown outline ↔ tree; `edit`/`remove`/`addChild` do
  line-level surgery on the markdown and re-`serialize`; saved via `editExtraction`).
- **LLM context**: `llmHint` = "Selected node: X" + the full outline capped at 1800 chars,
  passed through the existing `context_hint`/`instructions` to `GenerateDialog` /
  `NoteComposeDialog` (no backend change).

Actions per node: **Ask** (chat bound to the mindmap's node), **Quiz / Exercises /
Flashcards / Study guide** (`GenerateDialog`, topic = label + hint), **Write note**
(`NoteComposeDialog`), **Add note** (`createNote`, title = label), **Add as section**
(`addNode` under the mindmap's node), and **Add child / Edit / Delete** (mindmap CRUD).

## Non-goals / decisions

- No new task in the registry for note compose — reuses `description` (consistent with
  `notes.action`); avoids a new Settings/Tasks row for a text generation that already has
  a model assigned.
- Mindmap is an interactive `markmap` view over a markdown outline inside a composed
  Material, not a dedicated canvas — the canvas (ADR-012) is out of scope here.
- The launcher does not replace the tab-scoped generate buttons (Practice/Compose/etc.);
  it is an additional, context-first entry point.

## Open questions

- Should "Write a note" get the full source picker (materials/notes/concepts) like
  `GenerateDialog`, or stay a lean title+focus form? (v1: lean; revisit if users ask.)
