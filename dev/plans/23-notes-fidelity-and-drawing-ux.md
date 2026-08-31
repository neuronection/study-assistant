# 23 — Notes editing fidelity & drawing UX (post-1.0 round 4)

**Status:** approved 2026-08-21 (user request + review) ·
**Phase:** post-1.0 polish (follows plan 22) · **Order:** A → B → C → D → E → F

## Context

User report after daily-driving plan 22's notes editor + inline drawings:

- **Autosave rewrites the note body.** The save round-trip is lossy: `_md_to_blocks`
  (`api/notes.py`) strips newlines and drops blank segments; the frontend
  (`noteBodyMd`) re-joins with exactly `'\n\n'`. After every save the editor's
  `value` differs from what it emitted → `setContent` rewrites the whole document →
  **caret disappears, typed line spacing visibly collapses, ProseMirror undo
  history is wiped**. Three symptoms, one root cause.
- **Drawings render twice.** `NoteEditor` renders *every* drawing as a card below
  the editor while the save flow also auto-inserts it inline. No dedup against
  body references.
- **OCR naming + prompt.** UI says "transcribe"/"Transcription" everywhere; user
  wants "OCR". The prompt licenses scene description ("a one-line italic
  description in brackets" for sketches) → outputs like *the drawing displays the
  text "Hello"* instead of `Hello`.
- **Toolbar crowding.** Delete/Print/Export/History sit as peers of Save/Draw; the
  four AI actions are a separate row. Rare actions should fold into a kebab; AI
  actions into one dropdown.
- **AI results aren't reviewable.** The summarize/cleanup/explain/expand card is
  read-only with a blind Append; user wants to edit before appending + a close
  button.
- **No in-session rollback affordance.** Version history exists (plan 22 B) but
  the user wants immediate undo/redo when something breaks while editing.
- **Editor toolbar scrolls out of view** in long notes; the rich-text component is
  notes-only while materials extraction editing is a plain textarea.

No migration this round — drawing edit reuses existing columns (`strokes`,
`png_sha`, `ocr_version`, `ocr_markdown`).

**ADRs (recorded in `06-decisions-and-risks.md`):**

| # | Decision (one line) |
|---|---|
| ADR-052 | Note bodies round-trip losslessly: blocks store text segments **verbatim** (split only on `ca-drawing://` refs, boundary-aware rejoin for legacy stripped blocks); `body_md` is canonical; the editor calls `setContent` **only** for genuine external changes (note switch, restore, append, conflict reload) — autosave feedback never rewrites the doc |
| ADR-053 | A drawing renders exactly once: body references are the truth (inline in position, with a per-drawing menu: edit / run OCR / copy OCR text); unreferenced drawings appear as fallback cards below the editor; inline edit = `PUT` strokes+PNG on the same row (version-bumped OCR, cleared when OCR skipped) |
| ADR-054 | `notes_ocr` is **extraction-only** (output exactly the text written in the image, math as LaTeX; no scene description, empty output when nothing legible); UI vocabulary is "OCR" everywhere; the skill key `notes.transcribe` stays (DB-stable), its seed name/description refresh |
| ADR-055 | The tiptap `MarkdownEditor` stays notes-only; extraction editing remains a plain textarea this round (extraction markdown round-trips block types — math/mermaid/geo/chart — that tiptap-markdown cannot serialize faithfully; adopting it there would reintroduce the lossy-rewrite bug class). Sticky-toolbar/scroll-shell polish lands in the shared component; materials adoption deferred until a lossless markdown schema exists |

---

## A — Lossless round-trip + caret never reset

**Problem.** See root cause above. Also: `insertDrawing` writes alt text
`notes.drawingAlt` into the ref, but reconstruction canonicalizes to
`![drawing](ca-drawing://N)` — so even a drawing insert + save rewrites the doc.

**Design.**

Backend (`api/notes.py`):
- `_md_to_blocks`: keep text segments **verbatim** (`before` / `rest` kept when
  non-empty, no `.strip("\n")`, no `.strip()` gate). Blocks become a derived
  index; `body_md` is canonical.
- `_blocks_md`: boundary-aware join — concatenate parts, inserting `"\n\n"` only
  when neither boundary char is a newline. Legacy stripped blocks rejoin exactly
  as before; verbatim blocks rejoin byte-identically. Round-trip
  `md → blocks → md` is the identity for new data.
- Everything downstream of `_blocks_md`/`_search_text`/context resolver keeps
  working; whitespace-only text blocks render harmlessly.

Frontend:
- `noteBodyMd` (`useNoteAutosave.ts`): mirror the boundary-aware join; drop the
  `.filter(part !== '')` + fixed `'\n\n'` join. Keep empty-block skip (backend
  never stores empty text blocks).
- `MarkdownEditor`:
  - `insertDrawing` uses alt `"drawing"` (canonical token, not localized) so the
    emitted markdown equals the reconstruction.
  - External-value effect (unchanged trigger: `value !== lastEmitted`): after
    `setContent`, if the editor **had focus**, `focus('end')` so the caret is
    visible after appends; otherwise leave default. With the lossless round-trip
    autosave never enters this branch, so typing never rewrites the doc → caret,
    line spacing and undo history survive.

**Accept.** Type multiline text, let autosave fire, keep typing — no visible
change, caret stays, Ctrl+Z still steps back through typed text. Insert a
drawing mid-typing → same.
**Tests.** Backend: round-trip identity (multi-paragraph w/ blank lines, leading
newlines, whitespace-only segment between two drawings, adjacent refs), legacy
stripped-blocks rejoin unchanged, search/version-restore paths unaffected.
Frontend: `noteBodyMd` join cases; editor does **not** call `setContent` when the
saved value equals what it emitted; focus-at-end on external change; drawing
insert round-trip equality.

## B — Drawings render once + per-drawing menu + edit + OCR toggle

**Problem.** Duplicate rendering (`NoteEditor.tsx` cards render all drawings);
no inline actions; OCR always-on with no UI control; "edit" means redraw.

**Design.**

Backend:
- `PUT /notes/{note_id}/drawings/{drawing_id}` (`DrawingUpdate`: `strokes`,
  `png_base64`, `ocr: bool = True`): replaces strokes + PNG (new blob), reruns
  OCR when `ocr` (bump `ocr_version`), **clears** `ocr_markdown`/`ocr_blocks`
  and resets `ocr_version` to 0 when OCR skipped (stale text must not survive an
  edit); refreshes `search_text`, bumps `note.updated_at`. 404 on unknown
  drawing/note; same OCR-failure semantics as create (commit + 502).
- `_note_detail` gains `strokes` per drawing (edit needs the source of truth).

Frontend (`NoteEditor` + `DrawingImage`):
- Referenced ids = `ca-drawing://N` matches in the current body (draft-aware);
  cards below the editor render **only unreferenced** drawings (fallback home for
  orphans, incl. "Insert inline").
- Canvas card footer becomes **[OCR toggle (default on)] [Save drawing]**; OCR off
  → `addDrawing(..., ocr: false)` → drawing stored, no extraction, no transcript
  UI. "Convert to text" label retired.
- Inline `DrawingImage` NodeView gains a small **dropdown menu** (DOM menu in the
  NodeView, handler injected via a stable callback ref): *Edit drawing* (opens
  the canvas prefilled with the stored strokes; Save → PUT), *Run OCR again*
  (existing reocr), *Copy OCR text* (clipboard, hidden when no OCR text).
  Transcript `<details>` keeps its collapsible form (renamed in C).
- Existing "Insert inline" stays on fallback cards only.

**Accept.** Save a drawing → it appears exactly once (inline at the cursor);
toggle OCR off → drawing without text extraction; edit a drawing inline →
strokes load, save updates PNG (+OCR if toggled) in place.
**Tests.** Backend: PUT updates strokes/png + bumps version with OCR; clears OCR
when skipped; 404s; search_text refresh. Frontend: referenced drawing renders no
card / unreferenced does; menu actions fire the handlers; OCR toggle sends
`ocr: false`; edit flow prefills + PUTs.

## C — "OCR" wording + extraction-only prompt

**Design.**
- `NOTES_OCR_SYSTEM` rewritten: extract **only text actually written in the
  image**, verbatim, math as precise LaTeX (`$...$` / `$$...$$`), reading order
  preserved; no descriptions, no commentary, no translation; nothing legible →
  empty output. (Drops the old sketch-description license — intended.)
- Seed row for `notes.transcribe`: name → "Handwriting OCR", description updated;
  `seed_skills` now also refreshes name/description of existing system skills
  (currently only the template refreshes). Skill **key unchanged** (DB-stable).
- UI strings (`en.json`): `notTranscribed` → "No OCR text yet",
  `retranscribe` → "Run OCR again", `ocrVersion` → "OCR v{{version}}",
  `transcript` → "OCR text"; `convertDrawing` → "Save drawing" (with B).
  Backend code identifier `transcribe()`/`notes.transcribe` stays.

**Tests.** Backend: seed refresh updates name/description/template of an existing
seeded skill; prompt asserts extraction-only clauses. Frontend: updated label
assertions in existing suites.
**Docs.** `docs/ai.md`, `docs/usage/notes.md` wording (ca-docs-sync pass).

## D — Toolbar restructure + editable AI results

**Design.**
- Editor action row becomes: status chip (left) · right side:
  **[AI ▾ (Sparkles)**: Summarize / Clean up / Explain / Expand] ·
  [Draw] · [Make flashcards] · [Study alongside] ·
  **[⋯ kebab]**: Print / Export .md / History / Delete · **[Save]**.
  Menus are Popover-based (repo has `popover.tsx`; no new shadcn files).
- AI result card: **editable textarea** (mono, full width) seeded with the
  generated markdown + live-updating · **Append** inserts the (possibly edited)
  text at the end of the body via the draft (single undoable setContent, caret
  to end via A) · **Close (X)** discards. BlockRenderer read-only preview is
  replaced by the editable form (raw markdown, same as extraction editing).
- Flashcard-count result message moves into the same card shape (text + Close).

**Tests.** AI dropdown renders four actions + fires the right mutation; kebab
contains the four rare actions and they still work (existing behavior tests
rerouted); AI result: edit textarea updates payload, Append payload is the
edited text, Close clears.

## E — In-session undo/redo surfaced

**Design.** With A fixed, ProseMirror's History (StarterKit) survives the whole
session. Add **Undo/Redo buttons** (leading slots of the formatting toolbar,
disabled via `editor.can().undo()/redo()`) so "rollback/forward" is one click;
History dialog (plan 22 B) remains the coarse-grained net. No new infra.

**Tests.** Buttons render, disabled states reflect `can()`, click runs the
command (spy on editor chain or assert doc reverts).

## F — Sticky toolbar + scrollable editor shell

**Design.** As-built deviation from the original sticky-in-outer-scroller idea
(the FocusShell drawer header is *itself* sticky at `top-0` — a second sticky
bar would collide with it at an unpredictable offset): the editor gets an
**internal scroll area** instead — `EditorContent` sits in a
`max-h-[65vh] overflow-y-auto` framed container with the formatting toolbar
(and undo/redo from E) *outside* it, so the toolset is always visible on every
surface (drawer, full page, split pane) and long bodies scroll inside the
editor. Adopting the component elsewhere stays governed by **ADR-055**
(deferred; extraction markdown cannot round-trip through tiptap-markdown yet).

**Tests.** Body container carries the scroll affordance and excludes the
toolbar; existing editor suites green.

---

## Verification per slice

Backend `ruff check . && mypy . && pytest` · frontend
`pnpm lint && pnpm typecheck && pnpm test && pnpm build` — green before each
commit; docs updated same-commit (`docs/STATUS.md` changelog + module row,
`docs/usage/notes.md`, `docs/ai.md`).
