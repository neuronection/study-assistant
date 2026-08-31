# 31 — Inline AI helper in the rich editor (editor-AI)

**Status:** COMPLETE 2026-08-22 (1A–3A in one pass; backend 479 + frontend 599 tests
green; ADR-068 recorded) · **Phase:** post-1.0 (plan 31) · user-requested

**As-built deltas:** `TaskRunner` gained `stream_text` as a **separate** generator
(1B) rather than refactoring `run_text` to collect it — `run_text` is untouched (less
risk; callers unchanged). `parser.parse` in tiptap-markdown 0.9 returns an **HTML
string** (markdown-it render + extension `updateDOM` hooks), not a ProseMirror node, and
tiptap-markdown overrides `insertContentAt` to re-parse input as markdown with
`inline:true` (which flattens blocks) — so insertion uses `createNodeFromContent` +
a manual `tr.replaceWith` dispatch that bypasses the override and keeps math/mermaid/
table fidelity. The sync `transform()` method and
the job endpoints both live on the `EditorTransformService` singleton
(`app.state.editor_ai`); endpoints return `{job_id}` and the poll/WS surface carries the
result. All slices landed in this round; nothing was cut.
**Follow-up fix (user report):** the ✨ trigger's `mousedown` and the `Popover` panel's
`panel.focus()` on open stole focus from the editor and collapsed the selection, so the
popover (which read `editor.state.selection` at render) saw no selection and popup
clicks unselected the text. Final selection handling: `MarkdownEditor` keeps a
`selectionRef` snapshot from `onSelectionUpdate` (kept on non-empty selections; cleared
only on focused empty selections, so a toolbar click never wipes it); the popover reads
the snapshot for detection, the context window and the Replace-selection range. Because
the selection is a **ref mutation (not React state)**, `AiHelperPopover` computed its
view (presets disabled) once in the body and `Popover` rendered that stale tree on open
— so the shared `Popover` now accepts **render-prop children** (`ReactNode | (() =>
ReactNode)`) and the AI helper passes a render function that reads `selectionRef.current`
fresh at open time. `Popover` also gained opt-in `focusOnOpen={false}` + `preserveFocus`
(trigger `mousedown` prevented) and the popover panel `preventDefault`s `mousedown` on
non-text elements — selection highlight survives opening the popup and clicking inside.

The shared Tiptap `MarkdownEditor` gets a ✨ **AI helper** toolbar button that opens a
modern AI popover (Notion/Craft/Google-Docs "Help me write" pattern): a categorized menu
of **transforms** (explain, answer, compact, expand, rewrite, simplify, fix grammar,
structure, bullets, format-as-markdown, translate…), a **free-form prompt box** ("write a
text and process it"), an explicit **context** toggle (selection + bounded surrounding
text, optionally grounded in course material), a **streamed live preview** with repair
indication, and **human-gated insertion** (replace selection / at cursor / new block /
discard) that goes through tiptap-markdown's own parser so math/mermaid/tables survive
byte-faithfully. Every call rides the Phase-10/11 machinery (TaskRunner, skills/contracts,
audit) and is never stored as a material — the editor result is transient UI state that
re-enters the document only through the user's explicit insert (which then flows through
the normal autosave/draft pipeline).

## Context

Honest findings that motivate the round:

1. **The editor is shared and already host-injected per surface.** `MarkdownEditor`
   (`frontend/src/components/editor/MarkdownEditor.tsx`) has a typed toolbar array
   (335–356) and one *conditional* toolbar button — the pen, shown only when a
   `drawingAdapter` prop is present (387–401). The Σ and diagram buttons insert custom
   atoms (`caMath`, `caMermaid`) with `autofocus`. This is exactly the seam an AI button
   should reuse: a new optional prop that hides the button where AI doesn't make sense,
   mirroring `drawingAdapter`. (`LazyMarkdownEditor` must forward it — it currently
   forwards neither `apiRef` nor the adapter: `components/editor/LazyMarkdownEditor.tsx:11–23`.)
2. **Inline insertion is already solved, fidelity included.** `MarkdownEditorApi`
   (`insertQuote`/`insertDrawing`, lines 54–57/177–246) uses `editor.chain().focus()
   .insertContent(...)`. tiptap-markdown 0.9 registers a markdown extension whose
   `storage.markdown.parser.parse(md, opts)` runs every extension's `updateDOM`/`setup`
   parse hooks — the *same* path as document load, so `$…$`→caMath, mermaid fences,
   GFM tables, `ca-material:`/`ca-drawing:`/`mention:` links all round-trip. A generated
   markdown result can be inserted losslessly; nothing is forced through the lossy
   HTML/`inline:true` path.
3. **AI plumbing is uniform and audited.** `TaskRunner.run_text` (repair loop +
   `validate` + `fallback_system` + `skill_key` + `AuditRef`) is the one way text is
   generated (`pipelines/compose.py:311–322` is the closest template — a markdown
   transform with validators). Skills seed idempotently from code (ADR-020,
   `app/ai/skills/__init__.py` `SEEDS` 260–365); tasks seed at boot
   (`app/ai/tasks.py:11–25`, `main.py:164–168`). Contract enforcement is the
   "behavior is contracted" house rule — a transform must be checked deterministically.
4. **Streaming + WS already exist.** Chat streams over WS via `EventBus`/`WsClient`
   (`services/chat.py:answer_streaming` publishes `stream_delta` on `chat:{session_id}`;
   frontend `ChatPanel.tsx:264–304`). A modern AI popover should stream tokens into the
   preview with a stop button and a poll fallback (chat already has a 90 s timeout +
   `refetchInterval` fallback — `ChatPanel.tsx:226,327–338`). No new transport needed.
5. **The AI-append precedent is clunky — the gap this round closes.** `NoteEditor`
   already has a note-level AI menu (`summarize/cleanup/explain/expand`, `runNoteAction`,
   `NoteEditor.tsx:41,300–321`) whose result lands in a **separate append card** with a
   textarea + "Append result" (451–491) — it does not insert at the cursor, does not
   transform a *selection*, and has no context toggle. The inline helper is the modern
   replacement at the *editor* level, shared by notes, extractions and the new-file
   dialog.
6. **The user's ask maps to one contract.** (a) toolbar button → popover of AI features;
   (b) free-form text → process in predefined formats (explain / answer / compact /
   expand / …) or format as markdown; (c) results insert **inline**; (d) an explicit
   **context** option including the selected part of the document. Everything else
   (grounding in course material, streaming, translate) is the "feature rich and very
   modern" surface.

Existing hooks to build on (reuse, don't reinvent):

| Hook | Where | Reuse |
|---|---|---|
| Skills scope chain + code-seeded (ADR-020) | `services/skills.py:49–91`, `ai/skills/__init__.py` | the `editor.transform` seed |
| TaskRegistry + boot seed | `ai/tasks.py:11–25`, `main.py:164–168` | new `editor_transform` task (model picker in Settings→Tasks) |
| `TaskRunner.run_text` + repair loop + audit | `ai/runner.py:136–206`, `AuditRef` 16–20 | the transform core |
| Contract enforcement (`validate` callable) | `pipelines/compose.py:308–329`, `ai/parsing.py` | deterministic contracts + repair |
| WS streaming + EventBus + poll fallback | `services/chat.py:644–876`, `api/ws.py`, `ChatPanel.tsx` | streaming + cancel + poll |
| ContextResolver / `ContextParams` | `services/context.py`, `api/ai.py:40–58` | 3A course grounding |
| Markdown insert with parse hooks | tiptap-markdown 0.9 (`storage.markdown.parser.parse`) | lossless insert |
| Host-injected optional toolbar button | `MarkdownEditor.tsx:387–401` (pen) | the ✨ button prop |
| ai action result preview precedent | `NoteEditor.tsx:451–491` | preview → explicit insert (refined) |

## Proposed ADR-068 (record in `06-decisions-and-risks.md` at slice 1A start)

**The shared rich editor gets an inline AI helper: one `editor.transform` skill, run
through the Phase-10 task layer, streamed over the existing WS EventBus with a poll
fallback, results inserted via tiptap-markdown's own parser (byte-fidelity), context =
selection + bounded document window (+ optional course-material grounding), and
insertion always human-gated (preview → insert). Transforms are contract-checked and
audited like every other AI behavior; nothing is persisted except what the user
explicitly inserts.**

- New `editor_transform` task (code-seeded, gets a Settings→Tasks model row) + seed skill
  `editor.transform` (task `editor_transform`) with a subject-agnostic system prompt and
  deterministic contracts (no-preamble, length cap, preset-specific checks: compact ≤
  input, markdown fence/math balance advisory).
- `POST /ai/editor/transform` (in `api/ai.py`): body `{text, instruction?, preset?,
  mode: transform|write, include_context: bool, ground_in_material: bool, course_id?,
  node_id?}` → returns `{job_id}`; the job streams `editor_delta` events on
  `ai-editor:{job_id}`, final `editor_done {result_md, problems, rounds}`; `POST
  /ai/editor/jobs/{job_id}/cancel` stops the stream (saves tokens); `GET
  /ai/editor/jobs/{job_id}` is the poll/reconnect fallback. Audit
  `AuditRef("editor_transform", …)` written at completion.
- No HITL proposal schema: the user *initiates* every call (ADR-043's whitelist is for
  AI-initiated changes in chat); no material/note is created (ADR-051's one-live-artifact
  is for composed artifacts, not snippets).
- Alternatives rejected: synchronous-only endpoint (no streaming UX); inserting raw text
  (kills math/mermaid/table fidelity); editor-level state persisted to the DB (transient
  UI state; autosave already owns the document); slash-menu or selection-bubble entry
  points this round (scope discipline — the user asked for the toolbar button).

## Part 1 — Backend transform engine

### 1A — `editor.transform` skill + sync transform endpoint

**Problem.** There is no generic "transform this markdown" AI call: `notes.action`
returns a fixed 400-word summary-shaped result and is note-scoped; chat is a
conversation. We need a small, contract-checked, audited text transformer the editor can
hit.

**Design.**

- `backend/app/ai/tasks.py` — add `editor_transform` to the task tuple list
  (`main.py:164–168` seeds it; no migration — code-seeded, ADR-020). Gets a row in the
  Settings→Tasks tab automatically (user-owned model, house principle 7).
- `backend/app/ai/skills/__init__.py` — new `SkillSeed(key="editor.transform",
  task="editor_transform", …)` with a subject-agnostic `EDITOR_TRANSFORM_SYSTEM` prompt:
  output is *only* the transformed markdown (no preamble, no commentary, no fences around
  the result unless the result is a code block), math as `$…$`/`$$…$$`, diagrams as
  mermaid fences, GFM tables, no raw HTML; preserve the input's intent and LaTeX verbatim
  when the preset is not math-rewriting. `CONTEXT_VARS` gains `text`, `instruction`,
  `context_document`, `context_material`.
- `backend/app/services/editor_ai.py` (new):
  - `EDITOR_PRESETS`: `explain | answer | compact | expand | rewrite | simplify |
    grammar | structure | bullets | markdown | translate` — a registry with (a) the
    canonical instruction string injected when `instruction` is absent, and (b) a
    **deterministic validator** per preset. Presets are *hints that also set contracts*,
    not prompt-fragment switches (the skill is one system prompt; the instruction is a
    variable — mirrors how `pattern.discover` reuses the `description` task).
  - `build_prompt(...)` — jinja-renders the skill (`SkillService.render`) with `text`
    (the selection, ≤ 12 000 chars — 422 above), `instruction` (user text or the preset's
    canonical instruction, ≤ 1 000), `mode` (`transform` = operate on `text`; `write` =
    free-form, `text` may be empty and is just context), `context_document` (bounded
    window from 2B), `context_material` (resolver manifest, 3A).
  - `validate(preset)` returns a callable for `TaskRunner.run_text`: non-empty; ≤ 8 000
    chars; **no_preamble** (first non-space token not a chatty greeting/"Here is…" —
    checked with the `ai/parsing.py` helpers); preset-specific — `compact`:
    `len(result) ≤ len(text)`; `markdown`: fence balance + math `$` balance advisory
    (`_math_lint_advisory` pattern from `compose.py:186`); `answer`: non-empty and ≥1
    sentence. Repair loop `max_rounds=2`.
  - `transform(...)` → `TaskRunner.run_text(task="editor_transform",
    skill_key="editor.transform", validate=…, audit=AuditRef("editor_transform",
    course_id, f"editor {preset or 'write'}"))`; unassigned task → 502 (same as the
    drills propose endpoint), contract-failed-after-repair → 422.
- `backend/app/api/ai.py` — new `POST /ai/editor/transform` (this slice: **synchronous**,
  returns `{result_md, problems, rounds}`; 1B moves it to `{job_id}`).

**Accept.** In the note editor, select a sentence → pick "Make it more compact" → the
popover previews a shorter version of exactly that sentence; a provider-error/unassigned
case surfaces a clear error; every call appears in the AI audit trail.

**Tests.** Backend: skill seeded + resolves per course type (SkillService); task seeded;
endpoint 422 on oversized/blank text and unknown preset; transform runs through TaskRunner
with the gateway mocked — audit row `context_type=editor_transform` written with correct
tokens/model; `validate` unit tests: no-preamble rejection + repair, compact shortens,
markdown fence/math balance; 502 unassigned task; 422 contract-failed. Frontend: none
(backend slice; the api.ts client lands in 2A).

### 1B — Streaming + cancel + poll fallback

**Problem.** A synchronous transform blocks the UI for 2–10 s with no feedback; the
modern UX streams tokens into the preview with a Stop affordance. Chat already has the
transport; the transform should too.

**Design.**

- `backend/app/ai/runner.py` — new `TaskRunner.stream_text(...)` alongside `run_text`:
  same signature/repair-loop/audit semantics, but drives `gateway.stream` and yields
  chunks; on round failure it re-streams; it writes the audit *after* completion so
  tokens/cost are final. `run_text` becomes `stream_text` collected (behavior-identical —
  existing callers untouched).
- `backend/app/services/editor_ai.py` — in-memory job registry
  `dict[int, EditorTransformJob]` (`job_id, status: running|done|error|cancelled,
  accumulated_text, result_md, error`). The transform handler runs the stream on a worker
  and publishes on `ai-editor:{job_id}` via `EventBus.publish_threadsafe` (precedent
  `jobs/runner.py:51–54`, `api/ws.py`): `editor_start {job_id}` → `editor_delta {text}`
  → (per repair round) `editor_repair {round, problems}` → `editor_done {result_md,
  problems, rounds}` | `editor_error {message}`.
- `POST /ai/editor/transform` now returns `{job_id}` (supersedes 1A's sync body — same
  request body). `GET /ai/editor/jobs/{job_id}` → `{status, result_md?, error?,
  accumulated_text?}` (poll fallback + reconnect after refresh; 404 when the registry
  lost the job — process restart, acceptable: result is transient). `POST
  /ai/editor/jobs/{job_id}/cancel` sets a flag the streaming loop checks between chunks
  (breaking out of `gateway.stream` stops provider pulls — tokens saved); the job flips
  `cancelled`.
- Frontend has a hard 90 s read timeout + WS reconnect handling (mirror `ChatPanel`).

**Accept.** Click "Answer the question" → tokens stream into the popover preview; a Stop
button halts generation within a chunk and the preview keeps what arrived; closing the
popover and reopening the same surface re-attaches to the job via poll.

**Tests.** Backend: job id returned; `editor_delta`/`editor_done` events observed on the
EventBus for `ai-editor:{id}`; repair round re-streams after an `editor_repair` marker;
cancel stops mid-stream and flips status; poll endpoint returns running→done/error and
404 after registry eviction; `stream_text` unit test = `run_text` behavior identical
(collected stream matches non-stream output on a mocked gateway); unassigned/provider-
error → 502 / `editor_error`. Frontend: `useEditorTransform` hook (WS subscribe + poll
fallback + cancel) — mock `WsClient` and fetch.

## Part 2 — Frontend popover

### 2A — Shared `AiHelperPopover` + lossless insert + toolbar button

**Problem.** No component exists to pick a transform, preview streamed output, and
insert at the caret — `NoteEditor`'s append card is the opposite (full-doc, separate, no
selection).

**Design.**

- `frontend/src/features/ai/editorPresets.ts` (new): the preset catalog —
  `{key, icon (lucide), label(t key), needsSelection, instruction}` rows grouped
  **Transform** (explain, answer, compact, expand, rewrite, simplify, grammar, structure,
  bullets, markdown, translate) and **Write** (the free-form box). Each preset maps to a
  canonical instruction string (localized via `t`) when the user didn't type one.
- `frontend/src/features/ai/useEditorTransform.ts` (new): mutation → `POST
  /ai/editor/transform` (api.ts client, pattern `runNoteAction` 2578–2588) → subscribes
  `WsClient` to `ai-editor:{job_id}`, accumulates `editor_delta`, resolves on
  `editor_done`/`editor_error`, 90 s timeout + `GET .../jobs/{id}` poll fallback, `cancel`
  call. Exposes `{start, stop, status, stream, result, error, reset}`.
- `frontend/src/features/ai/AiHelperPopover.tsx` (new): anchored to the toolbar button;
  three views:
  - **Idle** — free-form prompt textarea (Enter = run, Shift+Enter = newline, focus on
    open); a **context switch** (label + tooltip: "Use the selected text (and surrounding
    note) as context"); the preset grid (Transform section only when a selection exists,
    Write section always); a "no selection" hint line ("Select text to transform, or
    write something new") plus an explicit danger-styled **whole note** chip when nothing
    is selected (confirmed before running).
  - **Running** — read-only streaming preview (mono, growing), pulsing border + animated
    caret, **Stop** button, "fixing…" chip on `editor_repair`.
  - **Review** — editable textarea of the result (user may edit before inserting), char
    count, actions **Replace selection** (only when a selection existed), **Insert at
    cursor**, **Insert below** (new block after the current one), **Regenerate**, and
    **Discard** (✕). Errors show inline with a Retry.
- `MarkdownEditor` changes: `MarkdownEditorApi` gains `insertMarkdown(md, mode:
  'replace-selection' | 'at-cursor' | 'after-block')`; new optional prop `aiHelper?:
  { courseId?: number; nodeId?: number; title: string }` (matches the `drawingAdapter`
  pattern — hidden when absent); a ✨ button added next to the pen (conditional), opening
  the popover with a ref to the live `editor` instance (selection read, insertion).
  Insertion: `editor.storage.markdown.parser.parse(md, { inline: false })` →
  `editor.chain().focus().insertContentAt(range, parsedNode, { updateSelection: true })`
  (replace = the selection range; at-cursor = caret; after-block = end of current block
  +1); ProseMirror history keeps it undoable; the normal `onUpdate`→`onChange` path feeds
  autosave/draft untouched. `LazyMarkdownEditor` forwards `aiHelper`.
- i18n: `editor.ai.*` keys in `frontend/src/locales/en.json` (button label/aria, preset
  labels, views, hints, errors); lint enforces `t()`.

**Accept.** With a paragraph selected: ✨ → "Explain this" → streamed explanation previews
→ edit a word → **Replace selection** swaps the paragraph (math `$…$` inside renders as
math in the doc afterwards, byte-fidelity); with nothing selected: ✨ → type a prompt →
**Insert at cursor** puts the result exactly at the caret; Undo (Ctrl+Z) removes an
insertion; without the `aiHelper` prop (e.g. SplitStudyPane's read-only insert surface)
the button is absent.

**Tests.** Frontend: presets catalog maps to instructions (unit); popover state machine
(idle→running→review, discard, regenerate); selection-aware action enablement + "no
selection" hint + whole-note confirm; `useEditorTransform` (WS mock, poll fallback,
cancel, timeout); `insertMarkdown` in a tiptap harness — replace/at-cursor/after-block,
`$x^2$` round-trips into a caMath node, undo works, `onChange` fires with the new
markdown; toolbar renders ✨ only with `aiHelper`; LazyMarkdownEditor forwards it; i18n
key presence. Backend: untouched (verified).

### 2B — Surface wiring

**Problem.** The popover must know each surface's course/node and have the document body
for the local-context window; three surfaces consume the shared editor with different
contexts.

**Design.**

- **`NoteEditor`** (`features/notes/NoteEditor.tsx`): pass `aiHelper={{ courseId, nodeId,
  title }}` (the note's course from its node/owner; the node the note is bound to) and a
  `documentBody` accessor (the `draft`/`body`). Local context window: selection ± ~2 000
  chars, capped ~6 000 (helper `selectionContextWindow(doc, from, to)` in
  `editorPresets.ts`).
- **`ExtractionView`** (`features/library/ExtractionView.tsx:119–125`): pass
  `aiHelper={{ courseId, title }}` (the material's course) + the extraction markdown as
  the document body.
- **`NewTextFileDialog`** (`features/library/NewTextFileDialog.tsx:109–115`): pass
  `aiHelper={{ courseId, title }}`; the body is the dialog's in-memory draft (nothing
  persisted until Create — consistent with the plan-29 buffered-drawings rule).
- `include_context` in the request body carries the bounded window; the popover shows the
  context switch with a "N chars of context" readout.

**Accept.** In a note, select a sentence with the context switch on → "Answer the
question" answers *within* the note's context; in a brand-new untitled file dialog the
same flow works with zero persistence; a transform in an extraction QA editor stays
scoped to that extraction.

**Tests.** Frontend: `selectionContextWindow` bounds math (unit); each surface passes the
right `courseId`/`nodeId`/body (component tests, asserting the `aiHelper` prop + the
`include_context` payload); regression: surfaces without context (SplitStudyPane
read-only insert) render no ✨. Backend: untouched.

## Part 3 — Course grounding (rich)

### 3A — Ground in course material

**Problem.** "Answer the question" is far better when it can draw on the *course's* notes
and materials (ADR-042's resolver exists precisely for this); the local window alone is
shallow.

**Design.**

- Backend: `ground_in_material: true` (only valid with `course_id`; 422 otherwise) makes
  the transform service call `ContextResolver` with a `ContextSpec` (scope `node` when
  `node_id` is present else `course`, `query` = the selected `text`, bounded
  `max_chunks` ~8) and renders the manifest + top chunks into `context_material` (capped,
  e.g. 6 000 chars — budgeted like chat). Reuses `ContextParams`/`preview_context`
  logic (`api/ai.py:40–58`); deterministic, no new retrieval machinery. The skill prompt
  tells the model the material is *reference* context — it may ground answers in it but
  must not quote verbatim beyond need.
- Frontend: the context switch gains a second tier — "Include course material" (only
  shown when `courseId` is present), sent as `ground_in_material`. The popover shows the
  resolver stats (material/chunk counts) via the job's `editor_done` payload when present.

**Accept.** In a note bound to a course node, select "What is the derivative of x² and
why?" with course-material grounding on → the answer reflects the course's own material
and cites it implicitly (chunk snippets), not just the note window.

**Tests.** Backend: resolver called with `query=text` and node/course scope (mock
resolver); manifest appears in the rendered prompt; 422 when `ground_in_material` without
`course_id`; chunk cap respected; resolver failure degrades to a clear error, never a
crash. Frontend: second-tier switch shown only with `courseId`; toggling sets the request
flag; stats readout renders when present. Backend verified again after frontend-only
changes (463 baseline).

## Non-goals (this round)

- **No HITL proposals** for editor AI (user-initiated only; ADR-043 whitelist untouched).
- **No persistence of transforms** (no table, no material/note creation, no history).
- **No slash-command menu or selection-floating-bubble entry points** — the toolbar
  button only (the user asked for the button; slash/bubble is a later UX round).
- **No translate language picker beyond a fixed, small list** (preset instruction carries
  the target language for v1; a full locale-aware picker is polish).
- **No server-side durability of the job registry** (in-memory; a restart drops active
  jobs → poll 404 → user retries).
- **No change to the note-level `notes.action` menu** — the append-card flow stays; the
  inline helper is additive (its natural successor can retire it in a later round).

## Dependencies & suggested order

1A → 1B (needs 1A's service core + `TaskRunner`) → 2A (needs 1B's `{job_id}` contract) →
2B (needs 2A's `aiHelper` prop) → 3A (needs 1B's `ground_in_material` param + 2A's
context switch). 2B and 3A are independently cuttable without stranding the rest; 1B is
the only slice that changes a shipped contract (1A's sync body), so it lands before any
frontend work.

## Verification per slice

All four suites green before commit (AGENTS.md rule 1): backend `ruff check . && mypy .
&& pytest` · frontend `pnpm lint && pnpm typecheck && pnpm test && pnpm build`. Golden
evals never skipped. Every slice updates `docs/STATUS.md` (phase + module status +
changelog) per `ca-docs-sync`; when the round closes, the STATUS header flips to "plan 31
COMPLETE" with the slice recap, `dev/plans/README.md` gains the 31 row at slice 1A start,
and ADR-068 is recorded in `06-decisions-and-risks.md`.