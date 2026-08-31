# 22 — Durability, sharing & study experience (post-1.0 round 3)

**Status:** planned (2026-08-21, user-approved direction after the full project review) ·
**Phase:** post-1.0 polish (follows plans 16–21) · **Suggested order:** A → B → C → D → E → F → G → H → J → I

## Context

The 2026-08-21 review of the whole app surfaced one systemic weakness and several
high-leverage opportunities:

- **Data safety has a hole in the middle of the app.** The DB itself is solid (WAL,
  snapshot-based backup export, integrity-checked restore — `api/backup.py`), but
  (a) note editing is a manual Save button away from losing everything typed
  (`NoteEditor.tsx` keeps the draft in React state; no autosave, no `beforeunload`
  guard, no crash recovery), (b) notes have no version history (PATCH is an
  irreversible overwrite — materials' extractions have versions, notes don't),
  (c) backups exist only if the user remembers to click Download (the
  `backups/` dir is created by `ensure_dirs` and never written to), and
  (d) destructive ops (delete note/quiz/exercise/chat, course purge) are immediate
  and permanent — only tree nodes have undo.
- **Sharing advanced work is half-there.** Quizzes (caq/qpkg), decks (.apkg) and
  skills packs travel; whole *courses* don't. A classmate (or next-semester self)
  can't receive materials + tree + notes + practice items without also receiving
  personal data — the backup zip is all-or-nothing.
- **Handwriting is second-class.** Drawings are separate cards below the markdown
  body on a fixed 900×480 canvas with one pen (`DrawCanvas.tsx`). Students who
  want text *and* diagrams interleaved (the Xournal++ use case) can't do it.
  Full Xournal++ is rejected (free-position layered pages would break
  markdown-canonical notes, OCR-to-LaTeX, AI note actions, chat context, card
  generation) — but interleaving + a real canvas is achievable and is slice E.
- **The core study loop toggles too much.** Reading material and taking notes is
  the primary laptop workflow, and today it is two surfaces swapped via
  navigation. Laptops have the width for split-view; slice G.

This plan is deliberately ordered **risk-first**: A–D make existing data
unloseable, E–F upgrade the daily surfaces, G–H are new student value, I is
cheap wins. Slices are vertical and shippable independently; dependencies are
noted per slice (D needs C's `POST /backup/create`; G benefits from A's autosave
but doesn't require it).

**ADRs to record in `06-decisions-and-risks.md` as each slice starts:**

| # | Decision (one line) |
|---|---|
| ADR-046 | Never-lose-notes: debounced autosave + localStorage draft mirror + beforeunload flush; server-side coalesced pre-write snapshots (note_versions) instead of per-save versions |
| ADR-047 | Automatic local backups on a scheduler + optional user sync-folder target; backups/ becomes populated by the app, manual export stays |
| ADR-048 | Trash = snapshot-based `deleted_items` (restore re-inserts with original ids) for notes/quizzes/exercises/chats; course deletion is guarded by a required fresh backup instead of trash |
| ADR-049 | Notes stay markdown/blocks-canonical; drawings become an inline *block type* (`ca-drawing://` images in tiptap), not a free-position canvas (Xournal++ model rejected) |
| ADR-050 | Course bundles (`ca-course/v1`): content-only JSON+zips export/import with id remapping; personal data (attempts, analytics, chats, scheduling state) never travels |
| ADR-051 | Organizer/compose artifacts are materials with **one live artifact per (node, kind)**: regenerate = new extraction version on the same material (never a duplicate file); the existing artifact rides in context and the skill *revises* it; `node_review` kind excluded from retrieval (meta-content); review history accumulates dated entries instead of overwriting |

Migration numbers below (0027+) are indicative — renumber if other plans land first.

---

## Part 1 — Durability (stop the bleeding)

## A — Note autosave & crash-safe drafts

**Problem.** `NoteEditor.tsx` holds the body in `useState` (line ~51); the only
write path is the manual Save button (PATCH `/notes/{id}`, wholesale body replace
in `api/notes.py:378`). Closing the drawer, navigating, reload, OS crash, or
battery death silently destroys everything since the last Save. Title/tags are
safer (saved on blur) — the body is the gap.

**Design.**

- **Debounced autosave** in `NoteEditor.tsx`: 1.5 s after the last keystroke
  (or 10 s max latency after the first unsaved change, whichever first) fire the
  existing `save` mutation. Status chip near the title: *Saving… / Saved HH:MM*;
  manual Save stays (it becomes "flush now"). Not optimistic — cache update on
  success as today; keep the existing `ErrorBanner` path and **queue a retry**
  (every 5 s while dirty+failed) instead of dropping edits on a transient error.
- **Draft mirror** in localStorage: key `ca-note-draft:{id}` →
  `{body_md, savedAt}` written on the same debounce. Cleared after every
  successful PATCH. On editor mount: if a mirror exists and `savedAt` is newer
  than the note's `updated_at` (fetched note), show a recovery banner —
  *Unsaved changes from a previous session · Restore · Discard*.
- **Close/leave flush:** `beforeunload` guard while dirty (browser mode);
  drawer close (X / backdrop / Escape / back-button param strip) and route-away
  (`useBlocker` or effect cleanup) attempt one final PATCH before unmount
  (best-effort; the mirror is the real safety net).
- **Stale-write guard (optional hardening, ~20 lines):** PATCH accepts optional
  `base_updated_at`; mismatch → 409; frontend offers *Reload / Overwrite*. Two
  tabs editing one note is rare locally but cheap to make honest.
- Applies to both editor surfaces (drawer + `/note/$id`) since both render
  `NoteEditor`. i18n keys for all new strings (no-literal-string rule).

**Accept.** Type in a note, kill the browser process, reopen the note → text is
there (server autosave) or one click away (mirror banner). The dirty indicator
is always truthful; closing the drawer never loses typed text.
**Tests.** Frontend: debounce fires PATCH (fake timers), mirror write/clear
cycle, recovery banner on newer mirror, retry-on-failure, close-flush on drawer
close. Backend (if 409 guard): stale-write conflict test.

## B — Note version history (coalesced snapshots)

**Problem.** `PATCH /notes/{id}` overwrites `body` irreversibly. A bad AI note
action (summarize/cleanup/expand replace the body), a restore mistake, or an
errant select-all+type destroys content with no undo. Materials have the
extraction-version chain; notes have nothing.

**Design.**

- Migration **0027**: `note_versions(id, note_id FK→notes ON DELETE CASCADE,
  profile_id, title, tags, body JSON, cause, created_at)`; index
  `(note_id, id)`. Cap **50 per note**, prune oldest on insert.
- **Server-side coalesced snapshots** (ADR-046): on every successful note
  PATCH, snapshot the *pre-update* row into `note_versions` **only if** the
  latest version for that note is ≥ 10 min old **or** the request passes
  `force_version=true`. Autosave spam therefore creates ≤ ~6 versions/hour of
  actual editing, while discrete events always snapshot.
- `force_version=true` callers: **AI note actions** (`notes.action` in
  `api/notes.py` — the dangerous overwrite path), **restore** (below), and the
  editor's explicit *Save version* button (History dialog footer).
- Endpoints: `GET /notes/{id}/versions` → `[{version_id, cause, created_at,
  chars, title}]` newest-first (cap 50); `GET /notes/{id}/versions/{vid}` →
  full body; `POST /notes/{id}/restore` `{version_id}` → writes that body as a
  new forced version + updates the note (restore is itself undoable — same
  semantics as mindmap history, plan 17 B).
- Frontend: **History…** in the NoteEditor action row → dialog mirroring
  `MindmapHistoryDialog`: version list (cause chip: *autosave / AI action /
  restore / manual*, timestamp, size), preview pane rendering the body through
  BlockRenderer, Restore + Save-version-now actions.
- `cause` values: `autosave-coalesced`, `manual`, `ai-action:{action}`,
  `restore`.

**Accept.** Run an AI "clean up" that mangles a note → History shows the
pre-AI version → Restore returns the text; the restore itself appears in
history and can be reverted.
**Tests.** Backend: coalescing window (two PATCHes < 10 min → one snapshot;
forced → always), cap pruning, list/get/restore round-trip, 404s, cascade on
note delete. Frontend: dialog renders versions, restore calls the endpoint and
refreshes the editor.

## C — Automatic backups (scheduler + sync-folder + boot integrity)

**Problem.** `api/backup.py` export is correct (sqlite backup API snapshot →
portable DELETE-journal DB → zip + blobs + `ca-backup/v1` manifest) but
manual-download-only; `settings.backups_dir` (`core/config.py:48`) is created
and never used. If the user never clicks Download, a disk failure or a bad
restore loses everything. The user's stated requirement: *secure all the time
that notes and material would not be lost.*

**Design.**

- `services/backup_scheduler.py` (mirror `scan_scheduler.py`'s pattern: startup
  + periodic, error isolation, clock-injectable for tests):
  - Runs every `CA_BACKUP_INTERVAL_HOURS` (default 24) and **once ~60 s after
    clean startup** (so a daily-use laptop always has a same-day backup even if
    it never stays open long enough for the interval).
  - Refactor: extract the zip-building core from `api/backup.py` into
    `services/backup.py` (`create_backup(target_dir) -> Path`), reused by the
    scheduler, a new `POST /backup/create` endpoint, and slice D's guards. The
    existing GET download stays a thin wrapper.
  - Files land in `settings.backups_dir` as `auto-YYYYMMDD-HHMMSS.zip`
    (manual/"Back up now" ones as `manual-….zip`).
  - **Retention rotation:** keep the newest N dailies (default 14) + first
    backup of each week as weeklies (default 8); older files deleted. Rotation
    never deletes files it didn't name (`auto-`/`manual-` prefixes).
  - **Post-write validation:** re-open the finished zip, check manifest +
    `PRAGMA integrity_check` on the embedded DB before considering it good
    (a corrupt backup is worse than none); failed attempts logged + surfaced.
- **Optional sync-folder target** (`CA_BACKUP_SYNC_DIR` / Settings): after a
    successful backup, copy the zip into the user's folder (e.g. a
    Nextcloud/Dropbox synced directory) with the same retention applied there.
    The zip is self-contained → this is free offsite redundancy. Copy is
    atomic (tmp name → rename) so a synced peer never sees a partial file.
- **Boot integrity check:** on startup (after migrations), run
  `PRAGMA integrity_check`; on failure: rename `app.db` →
  `corrupt-YYYYMMDD-HHMMSS.db`, auto-restore the newest *valid* backup
  (validate before replacing), and record the event for the UI. The app must
  never silently run on a corrupt DB nor lose the corrupt file (forensics).
- **Settings → Data tab** (`DataTab.tsx`) grows an *Automatic backups* card:
  enable toggle, interval, retention, sync-folder picker (reuse the
  `GET /fs/dirs` server-side browser from linked sources), *Back up now*
  (POST /backup/create), and the list of existing backups (name, size, date,
  Restore button reusing the existing restore flow, Delete). `docs/usage/backup.md`
  rewritten from "your responsibility" to "automatic by default + how to verify".
- Config: `CA_AUTO_BACKUP` (default on), `CA_BACKUP_INTERVAL_HOURS`,
  `CA_BACKUP_KEEP_DAILY`, `CA_BACKUP_KEEP_WEEKLY`, `CA_BACKUP_SYNC_DIR`.

**Accept.** Leave the app running (or restart it) → dated zips accumulate in
`backups/`, old ones rotate out per retention, the newest also appears in the
configured sync folder; a deliberately corrupted `app.db` is detected on boot
and recovered from the latest backup with a visible notice.
**Tests.** Backend: scheduler fires on injectable clock; rotation keeps
14+8 correctly across a simulated two-month clock; failed integrity → file
quarantined not counted; boot-restore path (corrupt db → restored + event
recorded); `POST /backup/create` round-trip. Frontend: DataTab card renders,
Back up now / Restore / picker interactions.

## D — Trash & destructive-op guards

**Problem.** Deleting a note, quiz, exercise or chat session is immediate and
permanent (the rename/delete round wired the UI to real DELETEs); course
deletion purges *everything* in the course permanently. Mis-clicks and
regret have no remedy; the only safety net is a full-backup restore
(all-or-nothing, destructive itself).

**Design.** Snapshot-based trash (ADR-048) — no soft-delete columns, so no
list query anywhere changes:

- Migration **0028**: `deleted_items(id, profile_id, entity_type, payload JSON,
  deleted_at, purge_after)` with `purge_after = deleted_at + 7 days`.
- On DELETE of a note / quiz activity / exercise / chat session: serialize the
  entity **and children** into `payload` (notes: body + tags + drawings with
  strokes **and base64 PNG** — the blob store is append-only today but the
  snapshot must be self-sufficient; quizzes: questions + options; exercises:
  steps + for `card_*` kinds their `fsrs_states`/`review_log` rows; chats:
  messages + mentions + proposals), then run the existing deletion cascades,
  then insert the `deleted_items` row. One transaction.
- `POST /deleted-items/{id}/restore` re-inserts with the **original ids**
  (sqlite allows explicit rowid inserts; placements `node_id`/`course_id` are
  columns on the entities so they come back placed; sqlite_sequence untouched
  since ids only recur if never reallocated). Restore re-writes drawing PNGs
  to the blob store from the embedded base64. `GET /deleted-items` lists the
  trash (per-profile, grouped by type, with title + date + size); DELETE
  `/deleted-items/{id}` purges one now; a startup + daily job purges expired
  rows (7-day guarantee).
- **Course deletion guard:** a course is too big to snapshot into a row —
  instead the delete-confirm dialog (Settings-adjacent flow in the course
  workspace) requires a **fresh backup**: it offers *Back up & delete* (calls
  C's `POST /backup/create`, waits for the zip, then purges) or
  *I have a backup* (checkbox asserting the newest existing backup is
  acceptable). No path purges a course silently anymore.
- Frontend: **Trash** dialog from Settings → Data tab (next to backups) +
  a line in the delete-confirm toasts ("Deleted — Undo (7 days)" toast on
  every trashed delete, mirroring the node-delete undo toast pattern).
- Scope guard: **materials/folders are not trashed** (blob refcounting +
  extraction versions make it disproportionate); their delete keeps the
  existing confirm, now backed by automatic backups (C) instead.

**Accept.** Delete a quiz with attempts from the Practice tab → toast with
Undo → it's back with questions, attempts intact and placed on its node. Wait
past `purge_after` (simulated clock) → row purged. Course delete without a
backup → refused until *Back up & delete* runs.
**Tests.** Backend: snapshot+delete+restore round-trips per entity type (incl.
card exercise with review history; quiz with attempts/mistakes/item_stats),
id-preservation, expiry purge, trash list scoping. Frontend: trash dialog
restore, delete toast undo, course-delete guard flow.

---

## Part 2 — Handwriting & diagrams (the Xournal++ answer)

## E — Canvas v2 + inline drawing blocks

**Problem.** Two gaps: (1) `DrawCanvas` is a fixed 900×480 canvas, one
hard-coded pen (`#1a1a1a`/2.5 px), undo/clear only — no eraser, sizes, colors,
or space to actually write a derivation; (2) drawings are appended *below* the
markdown body as cards (`NoteEditor.tsx:366-405`) — text and diagrams cannot
be interleaved, which is the real Xournal++-shaped need.

**Design.** Markdown/blocks stay canonical (ADR-049). Two sub-slices:

**E1 — DrawCanvas v2** (`components/canvas/DrawCanvas.tsx`, stays inside the
lazy note-editor chunk):

- Stroke model extends to `{points, color, width, tool}` (old strokes
  deserialize fine — defaults fill in). Keep strokes as the source of truth;
  PNG rasterization unchanged (`strokesToPng`).
- Toolbar: pen / eraser (stroke-hit erase) / lasso-move optional-deferred;
  3 pen widths; a small palette (ink, red, blue, green — colors readable on
  white and in dark mode the canvas keeps a paper-white background);
  undo/redo (stroke stack + redo buffer), clear-confirm; pressure → width
  modulation via `PointerEvent.pressure` where available.
- **Variable size:** the canvas grows vertically with content (min one
  viewport-height of the panel; strokes beyond the bottom extend it; a
  width-lock at ~1400 px logical) — writing a long derivation no longer
  fights a fixed box. DPR-aware rendering (crisp on hidpi laptops).
- The same component serves quiz write-mode (C18) — its callers get the
  toolbar for free; the quiz flow keeps the existing size until its own
  polish round.

**E2 — Inline drawing blocks:**

- Note `body` blocks gain `{"type":"drawing","drawing_id":N}` (blocks are
  already the storage format; only text blocks exist today). Markdown
  serialization: `![drawing](ca-drawing://{id})` — a custom scheme survives
  tiptap-markdown round-trips as a plain image node.
- **Tiptap custom node** `drawing` in `MarkdownEditor.tsx`: renders the PNG
  (`GET /api/v1/blobs/{png_sha}`) with a collapsed **transcript** line
  (OCR'd markdown, from `NoteDrawing.ocr_markdown`) and a *re-open in canvas*
  action; NodeView keeps it non-editable-as-text (select/resize-width only,
  aspect preserved).
- Editor flow: *Insert drawing* toolbar action drops a drawing block at the
  cursor and opens the canvas in a focused overlay (draw → Convert to text →
  block commits with strokes saved + OCR run — the existing
  `POST /notes/{id}/drawings` flow, plus returning the drawing id to the
  editor). Existing below-body drawing cards remain for old notes and gain an
  *Insert inline* action (moves the reference into the body at the end of the
  current paragraph; no data migration — cards and blocks can coexist, cards
  are just the fallback rendering for drawings not referenced by any block).
- `BlockRenderer` gains a `drawing` case (PNG + optional transcript) so chat
  answers, explanations and previews render inline drawings too.
- **AI context:** the ContextResolver's note serialization renders a drawing
  block as its OCR'd markdown in a fenced block at the position it appears —
  quizgen/tutor see the handwriting as text, interleaved correctly with the
  note's prose.
- Search already works (`search_text` includes drawing OCR). Print: drawing
  PNGs are images in the print path — ride slice F's print work.

**Accept.** Write a note that alternates prose, an inline derivation sketch,
more prose; the note reads as one document; ask the tutor about the note and
it quotes the sketch's OCR content in position; the sketch is editable later
(re-open in canvas, strokes preserved).
**Tests.** Frontend: DrawCanvas v2 (eraser, sizes, growth, undo/redo),
tiptap node round-trip (`![drawing](ca-drawing://42)` ⇄ node), insert-at-cursor
flow, transcript toggle, BlockRenderer case. Backend: drawing-block body PATCH
round-trip; resolver renders block as OCR markdown (extend the context
fixture).

---

## Part 3 — Sharing

## F — Course bundle export/import + print/PDF for single artifacts

**Problem.** No way to hand a *course* to a classmate/teacher/next-semester
self: the backup zip is whole-profile and includes personal data; the
alternative (re-upload everything) loses extractions, notes, tree, quizzes.
Also: notes/composed materials/cheat sheets — the artifacts people actually
share — have no export beyond raw markdown.

**Design.**

**F1 — `ca-course/v1` course bundles** (ADR-050):

- `GET /courses/{id}/export` → zip:
  - `manifest.json`: format/version, app version, course meta (title,
    subject, description, exam date), entity counts, per-file sha256s.
  - `course.json`, `tree.json` (nodes with paths/order), `concepts.json`,
    `materials/<id>.json` (+ `materials/<id>.extraction.md` — latest
    extraction), `notes/<id>.json` (blocks + drawings w/ strokes + OCR),
    `quizzes.json`, `exercises.json` (incl. `card_*` kinds, no scheduling),
    `skills-overrides.json` (course-level skill forks, if any).
  - `blobs/<sha256>` for every referenced original (content-addressed, deduped).
  - **Never exported:** profiles, attempts/answers/mistakes/help events,
    analytics tables, chat sessions/messages/proposals, fsrs/review rows,
    read-status, AI-hint? → *is* exported (it's course content shaping).
- `POST /courses/import` (multipart; `dry_run` flag):
  - Dry-run: validate zip + manifest + counts + per-entity schema (reuse the
    quiz-import preview UX pattern) → preview card (title, counts by type,
    warnings: unknown block kinds, missing blobs).
  - Commit: create a **new course** (always import-as-copy; title unchanged,
    " (imported)" suffix only on collision), **remap all ids** (old→new map
    for every FK incl. material↔extraction↔note-drawing refs), write
    extractions directly (no re-OCR/re-ingest; jobs skipped — the extraction
    *is* the content), copy blobs, rebuild FTS rows. Placement columns
    (`node_id`) remap through the tree map. Skills overrides land as forked
    v2 templates (never overwrite).
- Frontend: Courses page header actions — *Export course* (on each course
  card menu) and *Import course* (next to Create). Settings → Data stays
  backup-only (different mental model, keep them separate).

**F2 — Single-artifact export:**

- **Print/PDF** (extends the existing print CSS, currently quiz-only): a
  generic print stylesheet for notes (note editor action row → *Print*) and
  for markdown/composed materials in `MaterialDetailBody` — hides rails/
  drawers/actions, renders blocks (math via KaTeX, drawings/mindmaps as PNG —
  mindmaps rasterize through markmap's export if cheap, else link out and
  note it). Browser print-to-PDF does the rest; no PDF library.
- **Export .md** for notes: download with `ca-drawing://{id}` and blob links
  resolved to inline data URIs (self-contained single file; drawing strokes
  stay in the app, the .md carries images).

**Accept.** Export a course with 10 materials, notes with inline drawings,
quizzes and cards → import on a second profile → tree/notes/practice intact,
searchable, no personal history came along; print a note with math + a sketch
from the browser to PDF and it looks right.
**Tests.** Backend: export→import round-trip (all entity types, id remap
integrity, FTS rebuilt, exclusions asserted absent), dry-run preview counts,
corrupt-manifest rejection. Frontend: export/import dialogs, print button
wires `window.print()` with print class toggling, .md download.

---

## Part 4 — Study experience

## G — Split-view study mode (material ⇄ note)

**Problem.** The core laptop workflow — read material, take notes on it —
means swapping between the Materials tab/detail drawer and the note editor
drawer over the same workspace. Context is lost on every toggle; laptop
screens have the width for both.

**Design.**

- New `components/layout/SplitStudyPane.tsx`: two resizable panes with a drag
  divider (width persisted per-course in localStorage, clamped 30–70%), left =
  material reader, right = note editor. Shown ≥ `lg` breakpoint; below it the
  current drawer flow stays (untouched).
- Entry points (both open the pane over the workspace, URL-addressable):
  - Material side: **Take notes** button in `MaterialDetailDrawer` header and
    `MaterialDetailPage` actions → `?material=<id>&study=<noteId|new>` on the
    workspace route; note defaults to *new note placed on the material's
    node*; a note picker (scoped to the node's subtree + recent) offers an
    existing one.
  - Note side: the drawer's **Study alongside** action on a note opens the
    pane with a material picker (reverse direction).
- Left pane reuses `MaterialDetailBody` tabs (Extraction / Original /
  Side-by-side) read-only (study-state control kept); right pane reuses
  `NoteEditor` as-is — **it must ride slice A's autosave** (closing the pane
  with dirty text is the exact loss scenario A fixed; hard dependency in
  practice, soft in code).
- **Selection → note bridge (the delight):** text selected in the extraction
  pane shows a floating *Quote* affordance → inserts a blockquote of the
  selection (+ a `ca-material://{id}` source link line) at the note cursor.
  Cheap, uses the existing clipboard-free path, and mirrors how students
  actually annotate. No highlight-store v1 (backlog if loved).
- The pane is an overlay on the workspace (FocusShell overlay chrome pattern:
  course crumb, ✕ closes with A's flush), so tab state behind is preserved.

**Accept.** On a 1440px laptop: open a PDF's extraction left, take notes
right with autosave, quote two passages, resize to taste, close → note is
saved and placed; re-opening restores the split width.
**Tests.** Frontend: pane open/param flow, width persistence, quote-bridge
inserts blockquote at cursor, note picker create-existing paths, close-flush
(with A's tests), below-lg falls back to drawer.

## H — Exam planner + course formula sheet

**Problem.** Analytics know *how* the student performs but nothing about
*when* it matters: no exam dates, no coverage-vs-deadline signal, no paced
plan. And the highest-value math artifact — a course-wide formula sheet —
requires manual assembly even though every formula already exists in notes
and extractions.

**Design.**

**H1 — Exam countdown & pacing (planner v1, deliberately small):**

- Migration **0029**: `courses.exam_date` (nullable DATE). Editable in the
  course settings popover (plan 21's `NodeSettingsMenu` on the root) — one
  field, no per-node dates in v1.
- Coverage signal: reuse the tree counts (`studied` materials, practiced
  nodes from existing telemetry) → **Exam card on the Today screen** when any
  course has an exam within 30 days: countdown, coverage bar (nodes with any
  practice/read vs total), and a *pace line* (nodes remaining ÷ days left →
  "≈2 nodes/day", red when coverage × pace can't finish in time — arithmetic
  only, no scheduler). One-tap action deep-links to the most-behind node's
  workspace (the tree already knows which nodes have zero activity).
- No calendar/ICS/notification spam in v1 (backlog).

**H2 — Course formula sheet (aggregate compose):**

- New compose kind `formula_sheet` on the existing `material_compose` task
  (pipelines/compose.py): **deterministic collector first** — walk course
  notes + material extractions, extract math blocks (`$…$`/`$$…$$`/math
  blocks; for notes with drawings, the OCR'd math at block position),
  normalize LaTeX whitespace, dedupe by normalized form, group by source node
  (and concept where tagged); the LLM's job is only *organize + title + drop
  trivial arithmetic* (validated: every output formula must appear in the
  collected set after normalization — no invented formulas; a `review`-style
  flag if the validator strips >20%).
- Output: an AI-badged composed material (existing provenance path) placed at
  the course root, rendered/printed via F2. Launch point: study launcher at
  course root (alongside Study guide / Summary sheet). Regeneration follows
  slice J's one-live-artifact rule (one formula sheet per course root).

**Accept.** Set an exam 10 days out → Today shows the card with an honest
pace line and jumps to the untouched chapter; generate a formula sheet for a
calculus course → printable, formulas traceable to notes/extractions, no
fabricated entries.
**Tests.** Backend: exam-date CRUD + pace computation (boundary: today,
past-date handling), collector (dedupe/normalization, drawing-OCR inclusion,
empty course), compose validator (invented-formula rejection), placement.
Frontend: Today card render + deep-link, settings field, launcher entry.

## J — Organizer artifacts become materials (one live artifact per node+kind)

**Problem.** The Phase 8E organizer outputs are second-class citizens, and
regeneration everywhere is duplicative (verified 2026-08-21):

- **Node review** (`POST /nodes/{id}/review` → `review_node()`) and **cheat
  sheet** (`POST /nodes/{id}/cheatsheet` → `cheat_sheet_markdown()`,
  `services/organizer.py`) return ephemeral JSON — `OrganizerCard` holds them
  in `useState` and they're **gone when the workspace closes**: not editable,
  not searchable, invisible to every AI task.
- **AI-drafted node notes** (`POST /nodes/{id}/draft-note`) create a new Note
  on **every click** — no find-existing check, duplicates pile up.
- **Compose kinds** (`study_guide`, `summary_sheet`, `practice_set`,
  `error_recap`, `mindmap` — `pipelines/compose.py`) persist correctly as
  `.md` Materials (provenance `ai-composed`, node-linked, ingested, editable
  via extraction edit) but dedup is content-hash only — LLM output is never
  byte-identical, so **every Generate click adds another library file**.

Meanwhile the compose path already proves the target model: materials are
AI-visible (the ContextResolver includes `ai-composed` materials in every
task's retrieval except compose itself), user-editable (extraction edit →
new version → re-chunk → re-index), and versioned. Slice J brings review +
cheat sheet onto that path and fixes regeneration for all kinds.

**Design.** (ADR-051)

- **`cheat_sheet` becomes a compose kind** on `material_compose`
  (pipelines/compose.py), generated via the standard GenerateDialog/study
  launcher flow — persisted as a material linked to the node, AiBadge,
  printable via F. The ephemeral `POST /nodes/{id}/cheatsheet` endpoint is
  retired (one-release redirect/deprecation note per house convention);
  `OrganizerCard`'s cheat-sheet section becomes a launcher: *Generate / Open
  existing / Regenerate* (below) + a deep-link into the material drawer.
- **`node_review` findings persist as dated materials** — a new compose kind
  whose markdown is the rendered findings report (coverage table, gaps,
  ordering, orphans), title `"{node} — Review YYYY-MM-DD"`. **Dated, not
  one-live**: reviews are point-in-time diagnostics whose value is the trend,
  so re-running accumulates an honest history (the tree's Review action shows
  the latest in-card + a short history list). OrganizerCard still renders the
  fresh findings inline after a run — persistence is additive, not a detour
  through the library.
- **`node_review` is excluded from retrieval by default**: findings are
  *meta*-content ("no material covers topic X") that would pollute quiz/tutor
  context if retrieved as course content. Extend the ContextResolver's
  provenance filter (today's `exclude_ai_composed` keys off `provenance IS
  NULL`) with a kind-based exclusion for `node_review` — compose's existing
  self-exclusion (`exclude_ai_composed=True`) keeps preventing
  composed-feeds-compose loops. `cheat_sheet` and `formula_sheet` are real
  study content → **included** in retrieval.
- **One live artifact per (node, kind):** the generate flow (study launcher +
  GenerateDialog + chat compose proposal) checks for an existing material
  with `provenance.kind == kind` linked to the scope node:
  - Exists → offer **Open existing** / **Regenerate** (and *Delete* from the
    material's own menu as today).
  - **Regenerate = new extraction version on the same material** (the
    `editExtraction` path, exactly like mindmap history in plan 17 B) —
    never a second file. History + restore come free.
  - Scope/placement changes (user moved the node, regenerates at the parent)
    → new material at the new node; the old one stays where it is (explicit,
    not magic).
- **Revision-aware regeneration:** when regenerating, the existing artifact's
  current markdown rides into the ContextSpec as an explicit include (not
  retrieval) and the compose skill prompt gains an `{existing}` slot — the
  task becomes *revise this sheet against the current material* instead of a
  cold start. Better output, less drift, and the model sees the user's manual
  edits to the previous version.
- **Draft-note dedup:** `POST /nodes/{id}/draft-note` finds an existing
  `ai-draft`-tagged note on the node → returns it (frontend opens it in the
  editor) instead of inserting a duplicate. Regeneration semantics for notes
  = overwrite-in-place through the editor (slice B's note versions protect
  it), no new surface.

**Accept.** Generate a cheat sheet for a node → it's a normal material in the
library + Materials tab, AI badge, editable; ask the tutor about the node and
the sheet's content is retrievable; regenerate → same file, new version,
previous version restorable; edit the sheet by hand, regenerate → the revision
reflects the manual edits. Run Review twice on different days → two dated
materials, neither leaking into quiz context; draft-note twice → one note.
**Tests.** Backend: cheat_sheet/node_review compose round-trips (placement,
provenance kind), one-live-artifact check (existing → regenerate → version
count 2, material count 1), `{existing}` context inclusion, resolver excludes
`node_review` + includes `cheat_sheet`, draft-note find-existing. Frontend:
OrganizerCard launcher states (none / exists → open/regenerate), GenerateDialog
existing-artifact branch, review history list deep-links.

---

## Part 5 — Small wins (bundleable, any time)

## I — Palette content search + katex dedupe

- **I1 — Palette full-content search:** Ctrl+K currently fuzzy-searches titles
  (+ note titles). Add a `?`-prefixed content mode (or automatic fallback when
  title hits are weak) hitting the existing hybrid search API → results as
  material/chunk deep-links (material drawer `?material=`). Keyboard-first,
  zero new backend.
- **I2 — katex dedupe:** pnpm override to collapse the dual katex (0.18
  direct + 0.16 transitive — open issue in STATUS). Verify rendering
  (chat + BlockRenderer + MathInput) after; expected ~270 kB off the boot
  closure.

**Tests.** I1: palette mode results + navigation; I2: existing suites +
build output recorded in STATUS.

---

## Non-goals (this round)

- **Xournal++ as a format** — free-position layered pages, PDF-anchored
  annotations (that one is the natural follow-up to E: a stroke layer over
  original PDFs in the blob store — explicitly backlog, needs its own plan).
- Graph-sketch grading (G7), local OCR adapter, Tauri, audio/video, plugins,
  collaboration/cloud sync (backlog unchanged).
- Highlight/annotation store for materials (G's quote-bridge is the probe).
- Calendar integrations, reminders/notifications.
- Soft-delete columns on entities (trash is snapshot-based by design).

## Dependencies & suggested order

A → B (same surface, B's dialog sits in A's editor). C independent (backend
only). D after C (needs `POST /backup/create` for the course guard). E
independent (frontend-heavy). F independent (backend-heavy). G after A
(needs autosave to be safe). H anytime (H2's formula sheet rides J's
one-live-artifact rule — land J first or accept a tiny follow-up). J
independent (compose pipeline + organizer; closes the draft-note duplicate
bug). I anytime.

Order A, B, C, D ships the *never lose data* guarantee within the first four
slices; E–F upgrade the daily surfaces; G–H–J add the new student value.

## Verification per slice

Backend (`backend/`): `ruff check . && mypy . && pytest` — mandatory before
commit. Frontend (`frontend/`): `pnpm lint && pnpm typecheck && pnpm test &&
pnpm build`. Docs: STATUS.md changelog per slice; `docs/features.md` /
`docs/usage/` (backup.md rewrite in C, notes/study guides in E/G) where
user-visible; ADR-046…051 recorded in `dev/plans/06` as slices start. Plan
docs stay local-only (gitignored).
