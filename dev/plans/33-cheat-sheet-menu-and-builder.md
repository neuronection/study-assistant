# 33 — Cheat-sheet menu & parameterized builder (ADR-070)

**Status:** NEW 2026-08-23 · **Phase:** post-1.0 polish (plan 33) · user-requested

The Overview tab's cheat-sheet action stops being a one-shot "generate now" button and
becomes a **dropdown menu**: when a cheat sheet already exists for the node the menu
offers **Open existing** and **Regenerate cheat sheet…**; when none exists it offers
**Generate cheat sheet…**. Generation opens the parameterized **compose builder**
(`GenerateDialog` in `compose` mode with the kind pre-locked to `cheat_sheet`) — the same
scope/material/notes/concepts/instructions context form the practice builder uses, which
is what the user asked for ("material to include etc., similar to generate exercises").
The dedicated `POST /nodes/{id}/cheatsheet` one-off and its hand-rolled prompt are retired:
cheat-sheet generation and regeneration now run entirely on the Phase-10/11 compose
pipeline (ContextResolver + TaskRunner + one-live-artifact regeneration, ADR-043/051).

## Context

Honest findings that motivate the round:

1. **There are two overlapping cheat-sheet generators.** The Overview tab's button calls
   the dedicated `POST /nodes/{id}/cheatsheet` (`api/courses.py:806` →
   `services/organizer.py:190 cheat_sheet_markdown`), which accepts **zero user
   parameters** and builds context from a simple node summary (`node_context`: node
   title/summary, child summaries, concept names — no chunk retrieval, no notes, no
   opt-in/out). The **compose pipeline** (`pipelines/compose.py`, `KINDS["cheat_sheet"]`)
   already implements cheat-sheet generation on the full ContextResolver (hybrid
   retrieval, materials include/exclude, notes, concepts, one-time instructions, live
   context preview) **and** one-live-artifact regeneration (existing version passed back
   in for revision, `regenerate` flag, `find_live_artifact`). Two prompts, two entry
   points, two maintenance surfaces for the same artifact kind.
2. **The button has no menu grammar.** `TabActionBar` (`components/layout/TabActionBar.tsx`)
   only renders flat `onAction` buttons; the Overview action row uses it for every tab.
   The cheat-sheet button currently flips its own label between "Cheat sheet" and
   "Regenerate cheat sheet" (`NodeWorkspace.tsx:585`) and a separate banner below shows
   the existing sheet with its own "Open existing" button — the state splits across a
   button *and* a banner, which is exactly the "ask/regenerate/open" menu problem.
3. **The existing sheet is only ever "open" or "regenerate" — never parameterized.**
   The current flow cannot say "regenerate but pull in this extra material" or "keep it
   focused on just the assigned notes". The compose builder already can.
4. **`generate.action.compose` is a missing i18n key** — the compose dialog's primary
   button (shown whenever the kind has no live artifact) renders the literal key string
   today. Adding the key is part of this round since the cheat-sheet menu reuses that
   dialog.

## Slices

### 33A — TabActionBar menu actions (frontend)

`TabAction` gains an optional `menu?: PopoverMenuItem[]`. When present, the bar renders
the existing `PopoverMenu` (the app-wide menu, `components/ui/popover-menu.tsx`) with a
trigger styled exactly like the flat action buttons (outline or primary variant, `size
sm`, trailing chevron). This gives every tab the dropdown grammar without a bespoke
widget — the same argument ADR-062 made for one shared create menu. Flat `onAction`
buttons are unchanged (all existing call sites keep working).

### 33B — Cheat-sheet dropdown + compose wiring (frontend)

`OrganizerCard` (`NodeWorkspace.tsx`) replaces the flat cheat-sheet action with a menu
action:

- **No existing sheet** → one item: **Generate cheat sheet…**.
- **Existing sheet** (`node-artifacts.cheat_sheet`) → two items: **Open existing**
  (opens the material via `onOpenMaterial`) and **Regenerate cheat sheet…**.
- Both generate items open `AIGenerateDialog` (`task="compose"`,
  `initial={{ composeKind: 'cheat_sheet' }}`, scoped to the node) — the dialog already
  detects the live `cheat_sheet` artifact and flips its primary button to **Regenerate**
  (`GenerateDialog.tsx:909`), so the regenerate semantics come for free.
- On successful composition the dialog closes, the artifact list refreshes, and the
  just-written markdown renders in the existing inline preview card (fetched via
  `getMaterial(materialId).extraction`), preserving today's immediate feedback.
- The old existing-sheet banner is removed — the dropdown is the single affordance. The
  review-history row is unchanged.

`COMPOSE_KINDS` gains `cheat_sheet` (frontend), so the pre-locked kind is valid for the
dialog; the general compose kind selector and the study launcher also surface it (a
natural, small consistency win — the backend already accepted it).

### 33C — Retire the dedicated cheat-sheet path (backend)

- `POST /nodes/{id}/cheatsheet` (`api/courses.py`) and `cheat_sheet_markdown`
  (`services/organizer.py`) are deleted — no caller remains. `node_context`,
  `review_report_markdown`, `missing_note_markdown` and `REVIEW_TASK` stay.
- `nodeCheatsheet` + `NodeCheatsheet` removed from `frontend/src/lib/api.ts`.
- Backend tests that exercised the old endpoint are re-based onto `POST /materials/compose`
  with `kind="cheat_sheet"` (`test_organizer_artifacts.py`): persist-and-regenerate
  becomes compose → version-bump-on-regenerate (still one live material, extraction
  history preserved, retrieval inclusion unchanged — only `node_review` is excluded).
  The `test_cheatsheet_*` cases in `test_organizer_api.py` are removed (the
  compose endpoint's own suite already covers no-context / short-document /
  unknown-kind).

## Acceptance

- Overview tab: no sheet → menu offers **Generate cheat sheet…**; sheet exists → menu
  offers **Open existing** + **Regenerate cheat sheet…**; Open existing opens the
  material, both generate items open the compose builder pre-locked to cheat sheet.
- The builder accepts the full context controls (scope, materials add/exclude, notes,
  concepts, instructions) and regeneration revises the live artifact (one material, new
  version) — verified by backend tests on `POST /materials/compose`.
- `generate.action.compose` renders as a real label.
- Backend suite green (`ruff`, `mypy`, `pytest`); frontend suite green (`lint`,
  `typecheck`, `test`, `build`); docs synced (`ca-docs-sync`).

## Risks / non-goals

- Regeneration context changes: the compose prompt (retrieval-grounded, `material.compose`
  skill, `MIN_CHARS=400` document gate) replaces the old ~250-word organizer prompt. This
  is the intended consolidation (ADR-070); cheat sheets still land as one `cheat_sheet`
  provenance material with the old artifact's placement/retrieval behavior.
- The study launcher's fixed grid does **not** grow a cheat-sheet entry (the menu is the
  entry point); the compose kind selector does, since it's driven by `COMPOSE_KINDS`.
- No schema/migration; no analytics/tutor changes.

## Alternatives rejected

- A separate cheat-sheet form/endpoint with its own prompt (rebuilds the compose
  pipeline; duplicates the material/notes/concepts controls — ADR-044's rejection of
  reimplementing GenerateDialog's scope/source/preview logic applies verbatim).
- Keeping `POST /nodes/{id}/cheatsheet` alongside the compose path (two generators for
  one artifact kind, drifting prompts; the dead endpoint would stay untested-by-UI).
- A bespoke dropdown widget in NodeWorkspace instead of a `TabAction.menu` extension
  (repeats the per-surface bespoke wiring ADR-062/056 explicitly consolidated).