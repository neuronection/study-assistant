# Plan 46 — OCR image efficiency + async drawing OCR (user request 2026-08-29)

Status: in progress · ADR-102

## Problem

1. Drawing saves block on the vision model: `POST/PUT /notes|materials/{id}/drawings`
   and `…/reocr` run `NotesOcrEngine.transcribe` inside the request. A slow or broken
   provider stalls the editor and surfaces 502s even though the drawing row committed.
2. Every OCR call sends the image as-is: drawings are full-resolution PNGs base64'd
   into the prompt; ingest does the same for uploaded images and 150-DPI rasterized
   PDF pages. Vision tokens scale with pixel dimensions and PNG payloads are heavy.

## Decisions (user-confirmed 2026-08-29)

- **Long-edge cap with presets** Off / 1024 / **1568 (default)** / 2048 px.
- **Re-encode to WebP q85** (JPEG fallback if WebP encode unavailable); only the
  payload sent to the model is touched — stored blobs stay full-resolution PNG.
- **Setting UI**: Settings → Search tab renamed **Search & OCR** (profile preference,
  JSON column — no migration for the setting itself).
- **re-OCR becomes async too** (same job path as create/update).

## Design

### A. Image prep (`app/ocr/imaging.py`)

`prepare_ocr_image(data, mime, max_edge) -> (bytes, mime)`:

- `max_edge <= 0` → passthrough (except PNG still re-encoded when WebP is smaller).
- Long edge > cap → LANCZOS downscale to the cap.
- Encode flattened-RGB WebP q85; use it when a resize happened or when it is
  actually smaller than the input (never grow a payload). JPEG fallback.
- Any decode/encode error → return the original bytes (preprocessing must never
  break OCR; also keeps fake-PNG tests meaningful).
- `ocr_image_max_edge(session)` reads profile preference `ocr_image_max_edge`
  (validated against the preset set, junk → default).

Wired into `GatewayOcr.ocr_image` (new optional `session=` kwarg — ingest passes
its session) and `NotesOcrEngine.transcribe`; quiz `/recognize` inherits via
`transcribe`.

### B. Async drawing OCR (ADR-102)

- Migration **0047**: `ocr_job_id INTEGER NULL` on `note_drawings` +
  `material_drawings`.
- New job type `drawing_ocr`; handler `app/pipelines/drawing_ocr.py`
  (`make_drawing_ocr_handler(gateway, blobs)`, payload
  `{kind: "note"|"material", note_id?/material_id?, drawing_id}`): transcribe →
  bump `ocr_version`, set blocks/markdown, clear `ocr_job_id`, refresh note
  `search_text` / material FTS. `TaskUnassigned`/`ProviderError` → `JobError`
  (retriable, activity rail). Handler must tolerate the drawing being deleted
  mid-queue (drawing/owner gone → JobError → stale detection already flags it).
- API: POST/PUT store the drawing + enqueue + return the detail immediately
  (no 502 path anymore). `reocr` enqueues too; **409** when the drawing already
  has a queued/running job. `ocr=false` PUT still clears the OCR fields.
- Serializers emit `ocr_job_id` only while that job is queued/running (crash-safe:
  a stale id never shows as pending).
- Jobs API: note-drawing jobs get the note title as label (material ones already
  resolve via `material_id`).

### C. Frontend

- `NoteDrawingInfo`/`DrawingMeta` gain `ocr_job_id`.
- DrawingBlock + unreferenced card: pending spinner ("Transcribing…") when
  `ocr_job_id` is set and no transcript yet.
- New `useDrawingOcrSync(drawings, onSettled)` hook (WS `jobs:{id}` subscription →
  invalidate host queries on done/failed); wired into NoteEditor, ExtractionView
  (and the material reading view host if it renders drawings).
- Search & OCR card: max-edge select, saves via partial `PUT /profiles/preferences`.

## Tests

- Backend: imaging unit tests (real PIL fixtures); preferences round-trip + 422;
  async note/material drawing flows (poll for OCR completion, ADR job-determinism
  rule); failure → retriable job; reocr 409; serializer hides stale ids; head
  assertion bumps (3 files).
- Frontend: DrawingBlock pending/transcript states; hook subscription test;
  SearchTab OCR select.

## Docs

- STATUS.md changelog + module rows; `docs/data-model.md` migration note 0047;
  usage docs touch-up (notes drawing OCR behaviour) if present.
