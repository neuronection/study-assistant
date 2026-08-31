# Plan 47 — Ingestion breadth: office/web formats + lecture audio/video (user request 2026-08-31)

Status: planned (2026-08-31, user-approved) · Phase: post-1.0 · Suggested order: A → B → C → D

## Context

The audit (2026-08-31) found the ingestion pipeline is narrower than the vision doc
promises, and one path is actively broken-feeling:

- **B10 (DOCX/PPTX/EPUB/HTML) is a P1 vision promise that never shipped.** Worse,
  `detect_kind` (`backend/app/services/materials.py:27`) maps every unknown suffix to
  kind `"doc"`, the upload **succeeds**, and the file then fails its ingest job with
  `unsupported material kind`. A first-time user dropping a `.docx` lecture notes gets a
  failed task in the activity rail instead of an honest answer at the door.
- **B13 (audio/video) is P2 backlog but the hard part already exists**: plan 42 shipped
  the `audio` capability + `transcribe` task (`LLMGateway.transcribe`, OpenAI-compatible
  `/audio/transcriptions` + Gemini inline audio). Recordings are a top-3 real-study
  input (lecture recordings, voice memos) and today they can only die as 25 MB
  ephemeral dictation clips.

Breaking changes are fine (no users). Deps added are all small wheels
(`mammoth`, `python-pptx`, `ebooklib`, `html2text` — `python-pptx` pulls `lxml`, already
in the PyInstaller-friendly category since `pymupdf` ships binary).

**ADRs recorded as slices start:**

| # | Decision |
|---|---|
| 103 | Document conversion happens at the ingest boundary into the canonical markdown extraction; unknown/unsupported kinds are **refused at upload (422)** with a machine reason — the upload-then-fail-ingest path is retired |
| 104 | Audio/video ingestion rides the existing `transcribe` task as an ingest stage; transcripts become normal markdown materials (searchable, chunked, embedded, AI-visible); **no ffmpeg is bundled** — containers pass through to the provider and provider limits are surfaced honestly |

## A — Upload honesty + converter architecture (ADR-103)

**Problem.** Unknown suffixes silently become kind `"doc"` and fail later, in a job.

**Design.**

- `services/materials.py`: split the map into
  `KIND_BY_SUFFIX` (pdf/image/md/txt) + new `CONVERTIBLE_SUFFIXES`
  (`.docx`, `.pptx`, `.epub`, `.html`, `.htm`) and `AV_SUFFIXES`
  (`.mp3`, `.m4a`, `.wav`, `.ogg`, `.opus`, `.webm`, `.mp4`, `.mpeg`, `.mpga` — the
  container set OpenAI-compatible STT endpoints document). `detect_kind` returns
  `docx | pptx | epub | html | audio | video` for them; **the `"doc"` fallback is
  removed** — unknown suffixes raise a new `UnsupportedMaterialError(suffix)` that the
  upload endpoint maps to **422** `{reason: "unsupported_type", suffix, accepted: [...]}`
  (machine-readable, i18n-keyed in the UI).
- The upload API validates **before** the blob is stored (fail at the door).
- Frontend: the file pickers' `accept` attributes are generated from one shared list
  (lib constant mirroring the backend map — keep them in sync via a backend
  `GET /materials/accepted` endpoint or a duplicated constant + test that pins both;
  prefer the endpoint), and the error row renders the reason code.
- Junk filter unchanged; `.doc` (legacy binary) and `.pages` etc. stay unsupported on
  purpose — 422 names them so the user knows it wasn't a glitch.
- **Linked sources are the 422's escape valve** (revision 2026-08-31): the
  ScanScheduler auto-ingests what it finds, and a per-file failed-job pile for every
  unsupported file in a linked folder would be exactly the noise this round removes.
  The scanner records a **per-file skip with reason** (surfaced in the source's scan
  report, like `last_scan_error` today) and enqueues nothing — 422 is for humans
  choosing files; skips are for scanners.

**Accept.** Uploading a `.rtf` fails instantly with "unsupported type (.rtf)" — no
material row, no failed job, no activity-rail noise. `.docx` uploads fine and ingests
(slice C).

**Tests.** Backend: detect_kind matrix, 422 contract (reason code, no blob/row
written), accepted-types endpoint. Frontend: accept-attr wiring, 422 error rendering.

## B — HTML → markdown converter core (ADR-103)

**Problem.** Four formats (docx/pptx/epub/html) all want the same target: clean
canonical markdown. One converter, four front doors.

**Design.**

- New package `app/pipelines/convert/`: `html_to_markdown(html) -> str` built on
  `html2text` with house config (headings kept, tables → pipe tables, links/images
  preserved, `<script>/<style>` dropped, whitespace normalized). This module owns
  **fidelity quirks in one place** (the extraction QA editor remains the correction
  surface, exactly like OCR).
- **Math honesty**: HTML/Office math is usually MathML/OMML, which no pure-Python
  converter handles. Best-effort policy: MathML/OMML blocks are converted to a
  `<!-- math-block -->` placeholder with surrounding text preserved; embedded images
  (equation screenshots) are extracted as blobs and routed through the existing vision
  OCR path (slice C/D) so handwritten/picture math still lands as LaTeX. Document the
  limitation in `docs/usage/library.md`; the QA editor fixes the rest.
- **Embedded doc images need a home** (revision 2026-08-31 — the first draft
  hand-waved "inline refs"): they are neither strokes (`material_drawings`) nor PDF
  page artifacts, so they get their own minimal row: **migration 0052** (renumber if
  other plans land first) `material_images` (material_id, blob sha, position ref,
  `ocr_markdown`, `ocr_job_id`) — the plan-46 async pattern reused verbatim. Converters
  replace each embedded image with a `ca-image://`-style ref and enqueue a thin
  `image_ocr` job (drawing_ocr handler shape minus strokes); the reading view resolves
  refs, and OCR text joins FTS/AI chunk context exactly like drawing OCR does.

**Accept.** A saved HTML page with headings/tables/links/images converts to markdown
that renders in the extraction view; images are viewable and searchable after OCR.

**Tests.** Converter unit tests over committed fixtures (tiny html/docx in
`backend/tests/fixtures/convert/`); table/heading/link fidelity; script-strip.

## C — Office/web ingest kinds: docx, pptx, epub, html (ADR-103)

**Problem.** B10: the four most common non-PDF document formats fail ingest.

**Design.**

- `pipelines/ingest.py` gains branches per kind, each producing markdown then flowing
  into the **existing** extraction → chunk → FTS → embed path unchanged:
  - `docx` — `mammoth.convert_to_html` → slice-B converter. Embedded images: mammoth
    image handler → blob + `material_images` row + `image_ocr` enqueue (async, per
    slice B).
  - `pptx` — `python-pptx`: one `## Slide N — <title>` section per slide, body text
    and speaker notes preserved (notes under `> ` blockquote), slide images extracted
    + OCR'd. Deck order is document order.
  - `epub` — `ebooklib`: spine order, one `# <chapter title>` section per spine item,
    HTML items through slice-B converter, images optional (extract + OCR, behind the
    same flag as PDF page images).
  - `html` — slice-B converter directly.
- All four produce an `Extraction` with `provenance: converted` + converter name in
  metadata (mirrors the OCR extraction shape; QA editing, re-chunk, re-embed, derive,
  export all inherit for free).
- Index cards (`description` task) run as today via postprocess.

**Accept.** Drop a `.docx`, a `.pptx`, an `.epub`, and an `.html` into a course → all
four become searchable, AI-visible materials whose extractions render tables/headings;
a quiz generated from the pptx cites slide headings.

**Tests.** Per-kind ingest integration tests with committed micro-fixtures + fake
gateway (no real OCR); postprocess enqueued; search finds converted text; purging a
converted material removes its blobs' rows (reuse cascade tests).

## D — Audio/video lectures → transcript materials (ADR-104)

**Problem.** B13: recordings can't be ingested even though the `transcribe` task and
provider plumbing (plan 42) exist.

**Design.**

- Ingest branch for kinds `audio`/`video`: stage `transcribe` calls
  `LLMGateway.transcribe` (existing; already provider-fallback + ledger + budgeted),
  then wraps the transcript in a small metadata header (source file name, duration if
  the provider reports it, model id) and flows into the standard extraction path.
  Provenance `transcribed` (model + language recorded); one `ai_interactions` row as
  today.
- **No ffmpeg, ever** (ADR-104): audio containers pass through as-is; video containers
  pass through where the provider accepts them (OpenAI-compatible endpoints document
  `mp4/mpeg/webm`), and providers that don't (Gemini inline is audio-only) surface a
  clear `ProviderError` → failed job with reason `video_not_supported_by_provider`.
  The API validates size (existing 200 MB cap) and returns the provider's 25 MB-class
  limits in the error message when they trip.
- Re-ingest (`POST /materials/{id}/reingest`) re-runs transcription (new provider
  model = better transcript), producing a new extraction version — same as OCR
  re-runs.
- Transcript materials are first-class: FTS + embeddings + index card + "generate quiz
  from this" all work unchanged (that's the payoff of riding the standard path).
- **`mutagen` is required, not optional** (revision 2026-08-31): AV kinds read
  duration + bitrate at upload (stored on the material row) and run a **pre-flight
  provider-limit warning** — a 60-minute lecture at 128 kbps (~57 MB) exceeds the
  OpenAI-compatible 25 MB transcription cap, and discovering that after a full upload
  is the exact upload-then-fail UX slice A kills. The check compares file size (an
  estimate — some providers re-encode internally) and warns before the bytes move:
  "likely exceeds <provider>'s transcription limit — use a local whisper server
  (plan 48) or split the file". Without ffmpeg (ADR-104) we cannot split
  server-side; a clear pre-flight warning is the honest answer.

**Accept.** Drop a 40-minute lecture `.m4a` into a course → a transcript material
appears with the audio's content searchable and quotable; ask the tutor "what did the
lecturer say about X" → answer cites the transcript; switching the transcribe task to a
better model and hitting re-ingest upgrades the transcript as a new version.

**Tests.** Ingest integration with fake gateway (transcript → extraction → chunks →
FTS/embed); reingest versions; provider-error mapping (`video_not_supported_by_provider`,
size cap) → failed job + reason; backend 422 for zero-byte AV files.

## Non-goals (this round)

- Real-time/streaming transcription while recording (dictation already covers
  short-form capture).
- Speaker diarization, timestamps in transcript margins (whisper `verbose_json`
  segments → timestamped sections is a natural follow-up once needed).
- `.doc`/`.rtf`/`.pages`/`.odt` legacy formats (converter depth without demand).
- Video frame sampling → visual slides OCR (vision models with video input when
  LangChain partners support it; note as future).
- Subtitle files (`srt/vtt`) as a faster transcript source — small follow-up worth
  doing if a user asks.

## Dependencies & suggested order

A first (upload contract changes everything downstream). B before C (C's formats all
convert through it). D independent of B/C — can go any time after A.

## Verification per slice

Backend: `ruff check . && mypy . && pytest` · Frontend: `pnpm lint && pnpm typecheck &&
pnpm test && pnpm build`. Docs duty (sa-docs-sync): `docs/features.md` (B10/B13 rows),
`docs/usage/library.md` (accepted types + math honesty note), `docs/import-export.md`
if bundle shapes change, `docs/STATUS.md` changelog + module row each slice.
