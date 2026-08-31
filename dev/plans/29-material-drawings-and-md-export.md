# 29 — Text/markdown materials get drawings: editable in-app, embedded images on .md export

**Status:** COMPLETE 2026-08-22 (A–E in one pass; backend 460 + frontend 561 tests
green; ADR-064 recorded) · **Phase:** post-1.0 (follows plan 28) · user request
("drawings in the text/markdown-file editor; export .md with drawings as embedded
images; drawings stay editable while the file lives in the app")

**As-built deltas:** the material **AI-context** integration appends drawing OCR to
the **chunk source** in `edit_extraction`/ingest (materials reach the AI via chunk
retrieval, not the manifest — unlike notes' explicit serialization). **Derive**
copies drawings synchronously and **rewrites the derived material's blob** to the
remapped markdown before the ingest job runs (ingest builds the extraction from
blob bytes), so the derived material is self-contained; two derives of the same
source dedup against each other (same remapped content). **Bundle import**
recomputes `extraction.blocks` from the remapped markdown (never trusts the bundle's
blocks, which carry old drawing ids). **The create-file dialog DOES host the pen
after all** — implemented as a **buffered, commit-with-create** flow (the plan's
original "dialog does not host drawings" is superseded, see ADR-064 refinement):
the dialog keeps drawings in memory (placeholder `ca-drawing://-N` refs; negative
ids now accepted by the drawing-image node, data-URI previews in `DrawingBlock`,
re-OCR hidden for unsaved drawings) and on *Create* runs
`createTextFileWithDrawings`: create the material → wait for ingest (so the
placeholder extraction v1 exists and is superseded) → POST each buffered drawing
(real ids) → remap placeholder refs → `editExtraction` (v2, real refs). Nothing is
created until the user clicks Create; cancel drops the buffer. The trade-off
(deliberate): **re-OCR is not available in the dialog** for unsaved drawings — OCR
runs once at commit, and drawings stay re-OCR-able in-app afterward.

## Context

Notes already own drawings end to end: `note_drawings` table, `ca-drawing://{id}`
refs inside the body markdown, the tiptap `DrawingImage`/`DrawingBlock` nodes, the
`DrawCanvas` modal, the host-injected `DrawingAdapter`
(`create`/`update`/`reocr`/`remove`), BlockRenderer's `drawing` case, and the note
"Export .md" that resolves refs to inline data URIs (`NoteEditor.exportMd`). All of
that is host-agnostic except the persistence surface: `DrawingAdapter` is only wired
in `NoteEditor`, and the pen toolbar button is hidden on every other surface because
no host provides an adapter (`MarkdownEditor.tsx:359` `{drawingAdapter ? … : null}`).

Materials are the missing surface. Text/markdown materials are edited through the
shared Tiptap editor (`ExtractionView` → `LazyMarkdownEditor`) and read through
`MaterialDetailBody` → `BlockRenderer`. They have **no drawings store**, so the pen
button doesn't exist there and their markdown can't carry persistent drawings.

User goal: (1) draw inside text/markdown materials and re-edit those drawings while
the file lives in the app; (2) export/download the material as a self-contained
`.md` with drawings embedded as images. The stored markdown must keep refs (not data
URIs) so strokes stay re-editable and OCR stays re-runnable; embedding happens only
at export/download time.

## Proposed ADR-064 (record in `06-decisions-and-risks.md` at slice start)

**Text/markdown materials own drawings exactly like notes do — a `material_drawings`
table + `ca-drawing://` refs in the extraction markdown; `ca-course/v1` bundles carry
them; the .md export embeds them as images.**

- New `material_drawings` table mirrors `note_drawings` (strokes = source of truth,
  content-addressed PNG blob, re-runnable OCR w/ version counter). No polymorphic
  sharing — one table per owner, consistent with the note precedent and with the
  codebase's rejection of the ADR-038 polymorphism.
- Drawings are referenced from the material's **extraction markdown** with
  `![drawing](ca-drawing://{id})` — the same scheme notes use, already in the tiptap
  Link parse allowlist (ADR-060). The stored markdown keeps refs; embedding to
  `data:image/png;base64` happens only in the export/download path.
- The extraction QA editor (`ExtractionView`) provides a `DrawingAdapter` wired to
  material drawing endpoints, so the pen button appears there. The create-file
  dialog (`NewTextFileDialog`) **also hosts the pen** via a buffered in-memory
  `DrawingAdapter` — drawings are committed with the create (create material →
  POST drawings → remap placeholder refs → save extraction), never created early
  (no orphan/cancel bookkeeping; nothing exists until the user clicks Create).
- Derive ("Save as material") **copies** the source material's drawings and remaps
  `ca-drawing://` ids so the derived material is self-contained; it never writes into
  the source.
- `ca-course/v1` stays version 1 with an **additive** `drawings` field on each
  material entry (older bundles lack it — importers must tolerate absence; the field
  is ignored by any older reader, which is safe because it's optional).
- A drawing's OCR text joins the material's FTS/search and the AI context exactly as
  note-drawing OCR does.

Alternatives rejected:

- **Embed data-URIs in the stored markdown.** Inflates every extraction, fights the
  plan-26/ADR-060 byte-identity round-trip guards, and ProseMirror/tiptap degrade on
  huge base64 attributes; a raster can't reload strokes or re-OCR. The user's own
  spec ("editable if not exported") is the ref-in-store + resolve-on-export split.
- **Reuse `note_drawings` with an owner column.** Polymorphic owner FKs were rejected
  once already (ADR-038); the note path is the proven shape, copy it.
- **Deferred material creation in the dialog (create the material on first draw).**
  Rejected in favor of buffering: deferred creation silently creates the file early,
  then needs rename-on-commit and delete-on-cancel to avoid orphans — more failure
  modes for the same result; buffering keeps the dialog non-destructive (cancel just
  drops the buffer) at the cost of no in-dialog re-OCR (OCR runs at commit).
- **No bundle support.** Course export/import would silently drop material drawings
  and ship dangling `ca-drawing://` refs — a data-integrity regression.

Non-goals: drawings in PDF/image materials (their editable content is the OCR
extraction, not a document we let users author); a drawings store for quiz
explanations or chat; print/PDF for materials (exists conceptually, out of scope);
stroke export in the .md (the file is meant to be portable text+images).

## Data model (migration 0032)

`material_drawings`

| Column | Type | Notes |
|---|---|---|
| `id` | int PK | |
| `material_id` | int FK→materials | cascade delete-orphan, indexed |
| `strokes` | JSON | replayable vector strokes — the source of truth |
| `png_sha` | str FK→blobs, nullable | content-addressed PNG render |
| `ocr_version` | int, default 0 | |
| `ocr_blocks` | JSON, nullable | latest OCR result as blocks |
| `ocr_markdown` | text, nullable | latest OCR result as markdown (search + AI context) |
| `created_at` | datetime | |

- Mirror of `note_drawings` (`models.py:667`). Relationship
  `Material.drawings → material_drawings` with `cascade="all, delete-orphan"`.
- `purge_material` (`services/materials.py:44`) deletes material drawings (their rows;
  blobs are content-addressed, orphans are already the accepted norm — note updates
  orphan old PNG blobs too).
- Course deletion already purges materials → cascades.

## A — Backend: material drawing API (`api/materials.py`)

Mirror the notes drawing surface (reuse the `notes.py` shapes):

- `POST /materials/{id}/drawings` (201 → `MaterialDetailOut`): decode png_base64,
  `blobs.put`, OCR via `NotesOcrEngine` when `ocr` is on (unassigned/error → 502
  pattern), insert row, resync FTS (drawing OCR joins material search), return the
  material detail. Body schema = the `DrawingIn` shape (`strokes`, `png_base64`,
  `ocr`).
- `PUT /materials/{id}/drawings/{did}`: replace strokes + PNG, rerun or clear OCR,
  bump `ocr_version`, resync FTS, return detail. 404 on unknown drawing/owner.
- `DELETE /materials/{id}/drawings/{did}`: remove the row **and** strip any
  `![drawing](ca-drawing://{did})` refs from the **latest extraction markdown**
  (write a new extraction version via `edit_extraction`, so reading view, chunks,
  FTS and AI context all agree), then resync FTS. 404 on unknown.
- `POST /materials/{id}/drawings/{did}/reocr`: rerun OCR on the stored PNG, bump
  version, resync FTS.
- `get_material` (`MaterialDetailOut`) gains `drawings: list[DrawingOut]` so the
  editor and reading view resolve refs without a second call.

Validation contract: `edit_extraction` today accepts any `ca-drawing://` ref. Add the
notes' `_validate_drawing_blocks` equivalent — when saving extraction markdown, every
`ca-drawing://{id}` ref must resolve to a drawing of **this** material (else 422 with
the unknown ids). This is the same invariant notes enforce, and it makes
"delete strips refs" safe.

Ref parsing helpers: extract the notes' `DRAWING_MD` regex + `_md_to_blocks` into a
shared module (`app/services/drawings.py`) that notes and materials both import.

## B — Reading view, context, FTS, derive

- **Reading view:** `extraction_to_blocks` (`services/materials.py:469`) currently
  emits only text blocks; teach it to split `![…](ca-drawing://{id})` refs into
  `{"type":"drawing","drawing_id":N}` blocks exactly like notes' `_md_to_blocks`
  (text segments before/after stay text). `MaterialDetailBody` passes
  `resolveDrawing` into `BlockRenderer` resolving from the material's drawings
  (fetched with `getMaterial`). Existing materials without refs are byte-identical.
- **AI context:** `services/context.py` material serialization includes drawing OCR:
  inline drawing blocks rendered as fenced OCR at position; unreferenced drawings
  appended (mirror the note branch at `context.py:440`).
- **FTS/search:** `sync_material_fts` indexes title+markdown; extend the material
  search text with each drawing's `ocr_markdown`. Re-sync on every drawing
  create/update/reocr/delete and on extraction save. This is the materials analogue
  of notes' `search_text` recompute.
- **Derive (`services/materials.py:272`):** after `create_text`, copy the source
  material's drawings to the derived material and remap `ca-drawing://{old}` →
  `ca-drawing://{new}` in the derived extraction markdown (rewrite markdown, then
  rebuild blocks/chunks/FTS). Dedup-by-content-hash excludes the source already; a
  remapped copy never dedups against the source. If the source has no drawings,
  behavior is unchanged.
- **Purge:** `purge_material` deletes `material_drawings` rows.

## C — Frontend: material editor gains the pen (ExtractionView adapter)

- `LazyMarkdownEditor` forwards `drawings?: DrawingMeta[]` and
  `drawingAdapter?: DrawingAdapter` (today it drops every prop but
  value/onChange/ariaLabel).
- `ExtractionView` builds a `DrawingAdapter` (create/update/reocr/remove) against the
  new material endpoints + cache invalidation (`['material', id]`, `['materials']`)
  and passes `drawings={data.drawings}` — the pen button, inline rendering, the
  unreferenced-drawings panel and the delete flow all appear for free
  (they're host-agnostic).
- Reading view (shared `MaterialDetailBody`, used by library page + workspace
  drawer) passes `resolveDrawing` so drawings render inline, not as broken images.
- The `ca-drawing://` refs already round-trip through the editor (ADR-060 allowlist);
  no editor changes needed beyond the props.

## D — Export .md (embedded images)

- New action **Export .md** on the material detail (shared `MaterialDetailBody`
  header): fetch `getMaterial`, take the latest extraction markdown, resolve
  `ca-drawing://{id}` → `data:image/png;base64` (fetch `/api/v1/blobs/{png_sha}`;
  skip if a drawing lost its blob), download `{title}.md` — the exact
  `NoteEditor.exportMd` algorithm (`NoteEditor.tsx:150`). Self-contained single
  file; strokes stay in the app.
- i18n keys for the action; a small shared helper
  (`components/materials/exportMarkdown.ts`) used by both note and material export so
  the resolution logic lives once.

## E — Bundle round-trip (ca-course/v1, additive)

- Export (`_export_materials`, `course_bundle.py:165`): each material entry gains
  `drawings` (strokes, png_sha, ocr_blocks, ocr_markdown, ocr_version) and each
  drawing's `png_sha` joins `shas` → `blobs/<sha256>`. Missing blobs degrade to
  `png_sha: null` like notes (`course_bundle.py:475`).
- Import (`course_bundle.py:747`): after creating a material + extraction, create
  `MaterialDrawing` rows (write blobs; ids are fresh), and remap
  `ca-drawing://{old}` → `ca-drawing://{new}` in the extraction markdown **and**
  blocks (notes import keeps note-drawing refs as-is because those ids don't change
  meaning; for materials the ref embeds the old drawing id, so it must remap).
  Include drawing OCR in the material FTS sync. Reject-only-if-broken: a bundle whose
  drawing blob is missing degrades `png_sha` to null (drawing renders as a
  placeholder), matching the notes import behavior.

## Tests

- **Backend:**
  - `material_drawings` CRUD + reocr (create returns detail w/ OCR version, update
    reruns/clears OCR, delete strips inline refs from the latest extraction and
    removes it from FTS, 404s);
  - extraction-save validation: unknown `ca-drawing://` ref → 422;
  - `extraction_to_blocks` emits `drawing` blocks for refs (and stays byte-identical
    for ref-less markdown);
  - FTS: material search matches drawing OCR after add/reocr, stops matching after
    delete;
  - derive copies drawings + remaps refs (round-trip: derived material is
    self-contained, source untouched);
  - context render includes drawing OCR at position;
  - bundle round-trip: material drawings export→import intact (refs remapped, blobs
    present, FTS searchable), missing-blob degradation.
- **Frontend:**
  - `LazyMarkdownEditor` forwards drawings/adapter;
  - `ExtractionView` shows the pen button, create/insert-inline flow, delete flow
    (adapter wired to material endpoints);
  - reading view renders drawings inline via `resolveDrawing`;
  - Export .md resolves refs to data URIs and downloads `{title}.md`.

## Docs (same commit)

`docs/STATUS.md` (changelog + materials & notes module rows), `docs/data-model.md`
(`material_drawings`), `docs/ai.md` (context includes material-drawing OCR),
`docs/features.md` (materials drawings + export), `docs/import-export.md`
(`ca-course/v1` additive `drawings` field, unchanged format version),
`docs/usage/library.md` + `docs/usage/notes.md` (draw + export .md for materials),
ADR-064 in `dev/plans/06-decisions-and-risks.md` (local-only).

## Migration & rollback

Migration 0032 creates `material_drawings` (+ index on `material_id`, FK to
`materials`/`blobs`). Downgrade drops the table; existing materials' markdown refs
would dangle, so a downgrade is only safe if no drawings were added — the endpoint
validation (422 on unknown refs) becomes the visible failure mode. No existing data
is mutated; drawings are new rows.

## Sequencing & open questions

1. Slice order: A (schema+migration+API) → B (reading/context/FTS/derive) → C
   (editor pen) → D (export .md) → E (bundle). A+B+C+D ship the user's ask end to
   end; E is the durability half and can land last.
2. Open: should the material **search box** results surface drawing OCR? Yes — notes
   already do via `search_text`; materials get the same via FTS. Confirmed in B.
3. Open: bundle remap — notes' import leaves `ca-drawing://` ids alone because a note
   drawing's id has no meaning to the reader; but the material editor resolves ids
   against the material's own drawings, so import must remap. Handled in E; the
   notes path is out of scope (no regression).
4. Open: does derive copy OCR too, or re-run it? Copy (strokes + PNG + OCR rows) —
   re-running OCR would burn a model call for identical content; re-OCR stays
   available on demand.

## Verification

Full gate per AGENTS.md (backend ruff/mypy/pytest; frontend lint/typecheck/test/build).
CI mirrors; no golden-set eval changes expected (drawing OCR rides the existing
`notes_ocr` engine, no prompt change).