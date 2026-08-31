# 26 — Extraction QA editor upgrade + "Save as material" (derive)

**Status:** COMPLETE 2026-08-22 (A+B+C in one pass; 434 backend + 507 frontend
tests green) ·
**Phase:** post-1.0 polish (follows plan 25) · user-approved 2026-08-22

**As-built deltas:** the corpus round-trip probe anchors every case with a
leading paragraph (insertQuote at a doc-start cursor lands inside the first
table cell otherwise); display-math decode also collapses the serializer's
hard-break emission (`\`+newline → newline) inside math spans; `_find_duplicate`
gained `exclude_id` so a text material's derive cannot dedup against **itself**
(its extraction equals its bytes); MindmapViewer ⋯ menu entry dropped in favor
of the single header button (both branches share it).

**Follow-up 2 (ADR-060a): math rendering + MathLive editing.** Math is now a
`caMath` inline-atom node (KaTeX node view, double-click → MathLive popover in
a body portal; see ADR-060a). The decode-side hard-break/backslash unprotect
was removed (nodes serialize latex verbatim); encode keeps doubling but spares
`\|` (table cells) and cloaks display-math newlines (U+2063 vs `breaks:true`).
Also fixed en route: tiptap-markdown's table serializer dropped atom-only
cells (`MarkdownTable` replaces it, `childCount`-aware guard).

**Follow-up 3 (ADR-060b): Mermaid diagrams + close buttons.** `caMermaid`
block-atom node renders fenced sources via the shared lazy engine
(`components/blocks/MermaidDiagram.tsx`, extracted from BlockRenderer);
double-click opens a centered source-editor modal (live updates, Escape/
backdrop/Close/Done). The equation popover gained a Close (X) button.

## Context

Two user requests, one round:

1. **Extraction QA editing still uses a plain textarea** (`ExtractionView.tsx`)
   while notes have had the Tiptap `MarkdownEditor` since plan 17/23. The user
   wants the shared rich-text component here too. ADR-055 kept the textarea
   because tiptap-markdown could not round-trip extraction-specific markdown —
   **empirically re-verified 2026-08-22** (scratch probes against tiptap
   3.30 + tiptap-markdown 0.9):

   | Construct | Behavior before this round |
   |---|---|
   | GFM tables | **destroyed** — `| a | b |` row → `ab12` (no table nodes in schema) |
   | `$…$` / `$$…$$` math | **corrupted** — `\,` eaten by the parser, `\int` re-emitted as `\\int` |
   | `[..](mention:M1 "t")`, `[..](ca-material://5)` | **link stripped to plain text** (Link `protocols` allowlist) |
   | code fences, headings, lists, quotes, blank lines | round-trip fine (plan 23) |

   All three gaps are fixable (see slice A), which un-supersedes the blocker
   clause of ADR-055 — recorded as **ADR-060**.

2. **"Create a material file from the extracted text"** — users who finished QA
   on an OCR/PDF extraction want a standalone markdown material and to drop the
   original image/PDF. The compose flow (`pipelines/compose.py`) already
   proves the pattern: `create_text` → provenance → standard ingest. Recorded
   as **ADR-061**.

### ADRs (recorded in `06-decisions-and-risks.md`)

| # | Decision (one line) |
|---|---|
| ADR-060 | Extraction QA editing uses the shared Tiptap `MarkdownEditor` (lazy-loaded) once the round-trip guards exist: table extensions in the schema, Link `protocols` allowing `ca-material:`/`ca-drawing:`/`mention:`, and math-span backslash protection in the encode/decode fidelity helpers; supersedes ADR-055's textarea clause (known normalizations documented: table alignment `:--`→`---`, `\|` inside math canonicalized like every other markdown consumer in the app). |
| ADR-061 | "Save as material" (derive) is an explicit user action (`POST /materials/{id}/derive`) that creates a **real md material** via `create_text` from the latest extraction markdown (`provenance = {source: "derived", from_material_id, from_version}`), rides the standard ingest pipeline (native extractor, chunks/FTS/embeddings), inherits the source's virtual folder (linked-source folders → course root), is subject to per-course content-hash dedup (surface `deduped`), and is never automatic (ADR-051 pile-up rule); title = uniqued `"{title} (extracted)"`. |

Deliberately out of scope: table toolbar insert button (extraction tables arrive
via markdown; users rarely hand-author), MathLive insert in the extraction
editor (later polish), replacing the original material in place (destructive —
derive is additive and reversible).

**Same-day follow-up (user decision): derive carries placement.** The
"auto-assigning the derived material to the source's nodes" exclusion above is
**reversed**: derive copies the original's direct `material_links` and accepts
an optional `node_id` (validated: exists + same course → 422) that the UI fills
with the currently opened node (`ExtractionView`'s `scopeNodeId`); both merge
into one deduped set with rationale `Derived from <title>`; on `deduped` the
existing material stays untouched. ADR-061 amended accordingly.

---

## A — Editor fidelity upgrades (`components/editor/`)

1. **Math-span protection in `markdownFidelity.ts`** (pure functions, fully
   unit-tested):
   - `encodeMarkdownForParse`: inside math spans (`$$…$$` multiline,
     `$…$` single-line, conservative edges: no leading/trailing space in the
     span, skip fenced/inline code), double every `\` (`\int` → `\\int`) so
     markdown-it cannot eat escapable sequences (`\,` `\;` `\(` …), and first
     canonicalize `\|` → `|` inside math (GFM table-cell escaping is not LaTeX;
     every markdown consumer in the app already renders it as `|`).
   - `decodeMarkdownFromSerialize`: inside math spans halve `\\` → `\`
     (inverting the serializer's backslash escaping). Pairwise halving keeps
     genuine LaTeX `\\` line breaks stable.
   - Blank-line handling unchanged.
2. **`MarkdownEditor.tsx` schema upgrades:**
   - Add `Table, TableRow, TableCell, TableHeader` (**named imports** — the
     ESM build has no default export; a default import silently yields
     `undefined`, which was the scratch-probe failure mode).
   - `StarterKit.configure({ link: { protocols: [...] } })` extended with
     `ca-material`, `ca-drawing`, `mention` (+ http/https/mailto) so mention
     chips and material links survive re-parse. **Also fixes the latent
     notes-editor link-loss bug** (a saved `ca-material://` quote link was
     dropped on the next re-parse).
3. **Round-trip identity tests**: for a corpus of extraction-representative
   markdown (headings/lists/quotes/blank lines, GFM tables incl. bold cells,
   inline+display math with `\,` `\int` `\alpha` `\\` breaks, mention +
   ca-material links, code fences), a parse→serialize cycle through the real
   editor emits **byte-identical** markdown (probe pattern: `insertQuote`
   prefix, assert `"> probeq\n\n" + original`).

## B — ExtractionView rich editor (`features/library/`)

1. `components/editor/LazyMarkdownEditor.tsx` — `React.lazy` wrapper
   (`LazyNoteEditor` pattern) so tiptap stays out of the boot chunk
   (`MaterialDetailPage` is statically routed).
2. `ExtractionView.tsx`: textarea → `LazyMarkdownEditor` (both the ordinary
   and the mindmap branch share the same edit surface; mindmap outlines are
   markdown lists). Cancel/Save buttons and `editExtraction` flow unchanged;
   Save disabled while empty/pending.
3. Tests (`ExtractionView.test.tsx`): mock the editor component, assert edit
   wiring (draft init, save payload, cancel), plus derive tests from slice C.

## C — Derive material ("Save as material")

**Backend:**

1. `MaterialsService.derive(material, folder_id, runner)`:
   - latest extraction required (else `ValueError("material has no extraction")`
     → 422); non-empty markdown.
   - Target folder: explicit `folder_id` else the source's `folder_id`, except
     linked-source folders → course root (`None`). Validated via
     `_validated_target_folder`.
   - `filename = "{uniqued title}.md"` with suffix ` (extracted)` /
     ` (extracted 2)` … computed in the target folder (generalize
     `_copy_title` to take the suffix); title sanitization strips path
     separators and caps length (`create_text` validates the rest).
   - `create_text(...)` → if content-hash dedup hits, return
     `(existing, True)` **without touching provenance** (the duplicate may be
     an unrelated user file; compose-style overwrite is wrong here).
   - Else set `provenance = {source: "derived", from_material_id,
     from_version}` and `queue_ingest` (native extractor; chunks/FTS/
     embeddings/index card via the standard jobs).
2. Endpoint `POST /materials/{id}/derive` (`MaterialDeriveIn {folder_id}` →
   `MaterialUploadOut`, 201) in `api/materials.py` next to `/copy`.
3. Tests `backend/tests/test_material_derive.py`: happy path (md kind,
   provenance, ingest → native v1 extraction equals the QA-edited markdown,
   FTS hit); repeat derive → deduped; edit extraction then derive → new
   material (different content hash); 404 unknown; 422 no extraction;
   folder validation + linked-folder fallback; title suffix uniquing.

**Frontend:**

1. `api.ts`: `deriveMaterial(id, folderId)` → `UploadResult`.
2. `ExtractionView.tsx` header (both branches): **Save as material** button
   (FileOutput icon) → mutation → invalidate `['materials']` → inline success
   row: title + **Open** (navigates `/library/$materialId`) or a
   "already exists" note when `deduped`. Error surfaced inline.
3. i18n keys under `library.*` (`deriveMaterial`, `deriveSuccess`,
   `deriveOpen`, `deriveDuplicate`, `deriveFailed`) — no literal strings
   (`no-literal-string` lint).
4. Tests: derive button calls the API with the material id, success state
   shows title/Open, deduped state shows the duplicate notice.

## Verification

Full gate per AGENTS.md (backend ruff/mypy/pytest, frontend lint/typecheck/
test/build), plus: the new round-trip identity corpus must pass byte-exact;
CI mirrors. Docs updated same-commit via `ca-docs-sync` (STATUS.md phase +
changelog, features.md, usage/library.md, ai.md provenance note).
