# Plan 43 — Infinite drawing canvas: pan/zoom navigation, fullscreen, crop-on-save + view-box scale metadata

User-requested (2026-08-28, concurrent session). The handwriting canvas was a fixed
1400-px-wide, grow-downward strip — no zoom, no pan, drawings saved with huge margins,
and re-opening a drawing for edit showed it at an arbitrary scale. ADR-098.

## Goal

1. **Infinite canvas** — the drawing surface is pannable/zoomable in every direction;
   strokes live in an unbounded logical coordinate space.
2. **Crop on save** — the exported PNG is the strokes' bounding box + a small padding,
   not a 1400-px strip.
3. **Scale metadata ("view box")** — a saved drawing records the exported region
   `{x, y, width, height}` (1 PNG px = 1 logical px) so re-editing restores the exact
   100% view; notes also render the PNG at natural size (no stretch).
4. **Navigation UX** — wheel = zoom to cursor, middle-drag / Space-drag / hand tool =
   pan, floating bottom bar (zoom −, %, +, fit, 1:1), fullscreen toggle on the dialog.

## Non-goals

- Shape tools, text objects, selections, multi-touch pinch (pointer wheel + buttons
  cover desktop/pywebview).
- Raster-image layers on the canvas.

## Backend

- Migration **0046_drawing_view_box**: nullable JSON `view` on `note_drawings` +
  `material_drawings`.
- `app/api/schemas.py`: `ViewBox` (x, y, width>0, height>0, finite); `DrawingOut.view`;
  `DrawingIn.view` (optional). Notes + materials drawing endpoints persist/return it.
- `course_bundle.py`: `view` exported and re-imported (additive, absent-tolerant).

## Frontend

- `components/canvas/DrawCanvas.tsx` rewritten as a viewport-based infinite canvas:
  `view = {x, y, zoom}` (logical coords at viewport origin), DPR-aware backing canvas,
  native non-passive wheel listener (zoom to cursor), middle/Space/hand panning,
  floating nav bar (zoom out / % / in / fit / 1:1), optional fullscreen button
  (`fullscreen` + `onToggleFullscreen` props), `fillContainer` + `initialView` props.
- `strokeBounds` + `exportDrawing(strokes, pad=24)` → `{dataUrl, view}`; `strokesToPng`
  defaults to the cropped region.
- MarkdownEditor canvas modal + chat `DrawingDialog`: fullscreen toggle, view
  restore on edit (meta.view at zoom 1, else fit content), cropped export, view
  passed to the adapter.
- `DrawingAdapter.create/update` + `lib/api.ts` note/material drawing calls carry
  optional `view`; `NoteDrawingInfo`/`DrawingMeta` expose it.
- `DrawingBlock` renders PNGs at natural size (`max-w-full`, no `w-full` stretch).

## Tests

- Backend: notes/materials drawing view round-trip + 422 on invalid view; bundle
  round-trip keeps `view`.
- Frontend: DrawCanvas pan/zoom/fit/1:1/export-crop tests (rewrite of the old
  height-growth test), edit-restores-view test in MarkdownEditor.

## ADR-098 (append to 06-decisions-and-risks.md on merge-back)

| 098 | **Infinite drawing canvas with crop-on-save + a stored view-box as the scale contract between the saved PNG and the stroke space (plan 43, user request 2026-08-28)** | Strokes stay the single source of truth in an unbounded logical space; the PNG is a derived projection of one region. The `view` JSON column (`note_drawings`/`material_drawings`, 0046) records that region `{x, y, width, height}` at 1 px = 1 logical unit, which is exactly what re-editing needs to restore 100% scale and what lets the note view render the PNG at natural size instead of stretching. Cropping at export (bbox + 24 px pad) shrinks blobs and sharpens OCR; consumers without `view` (old rows, external bundles) fall back to fit-to-content. Navigation follows the Excalidraw/Figma grammar (wheel zoom to cursor, middle/Space/hand pan, floating zoom bar, dialog fullscreen) rather than modal scrollbars. Alternatives rejected: resizing strokes on save to fit the crop (destroys the coordinate space and makes re-edits drift); storing scale as a single float (insufficient once the PNG is cropped, the offset is the information); CSS fullscreen API (unreliable in WebKitGTK — a dialog-level maximize is dependable everywhere); pinch-zoom + shape tools (deferred, pointer-first surfaces). |
