# Project Status

Single source of truth for what exists and what phase we are in. Update per the
`sa-docs-sync` skill with every change (see AGENTS.md).

**Next up (planned 2026-08-31, user-approved):** post-1.0 rounds **51–53** in
`dev/plans/` (local-only), execution order **51 → 52 → 53** — AI-native answer
types (C21/G7/C20/C14 + widened C16/C19/C4/C5/C11), topic explorer & course
genesis, planner & expression. **Plan 51 in progress — slices A (number-line),
C (error-spotting), F (table fill), E (composite) and G (graph reading) landed
2026-09-02/03**; **plan 50 COMPLETE (2026-09-02)** and plan 48
landed 2026-09-01 — see the 2026-09-02 changelog entries.

## Current phase: post-1.0 — **plan 50 (ca-course/v2, skill packs, e2e smoke, OSS readiness) COMPLETE (2026-09-02)** — course bundles carry the full learning state (flashcards + FSRS schedules, exam_date, discovered error patterns, opt-in attempts/note-versions) and **imports self-heal** (postprocess re-embeds every imported material — no more FTS-only degradation), **skill packs** (`ca-skills/v1`) export/import prompt customizations with staged preview + replace/rename/skip collisions, **Playwright e2e smoke** (4 specs against the real backend + mock OpenAI-compatible provider, keyless per plan 48) gates CI and releases, and OSS polish (SECURITY.md, issue/PR templates, About family links, enriched sample course with quiz/6 flashcards/2 due/exam date/concept). Preceded by **plan 48 (local AI engines) COMPLETE (2026-09-01, partial C — Ollama verified live)** — local presets (**llama.cpp** `:8080`/`:8081`, **LM Studio** `:1234` alongside Ollama `:11434`, all keyless — blank keys skip the keyring write and the gateway resolves them to a keyless client), **`GET /providers/detect-local`** probes the local ports (≤300 ms connect + 1.5 s read, hit requires an OpenAI-shaped `/v1/models` 200; localhost-only, read-only, never persisted, base URLs already configured as providers are skipped) with the wizard Provider step auto-probing once per open + one-click **Add** per hit and the same detector in Settings → Providers empty state; the all-local Defaults step gains a "everything runs on this machine" hint; verification matrix executed **live against Ollama** (chat streaming turn, vision `image_url` OCR, `/v1/embeddings` + chunk embed → hybrid search, embeddings ledger row) and **fixed en route: embeddings calls now record `ai_interactions` ledger rows** (`GatewayEmbedder` routed through the gateway; it had bypassed the ledger since plan 37); `docs/usage/local-ai.md` written, README gained a "Runs fully local" bullet. llama.cpp/LM Studio/audio rows of the matrix await the user's engines. Preceded by **plan 47 (ingestion breadth) COMPLETE (2026-08-31)** — uploads are honest (unknown types refused 422 with machine reasons at the door; linked sources skip-with-reason instead of failed-job piles, ADR-103), **office/web materials** (docx/pptx/epub/html) convert to markdown extractions at ingest with embedded images extracted into `material_images` (0048) and async `image_ocr` transcripts, and **lecture audio/video** transcribe through the provider `transcribe` task into searchable transcript materials (mutagen duration/bitrate on the material row, 0049; pre-flight 25 MB warning; no ffmpeg, ADR-104). Preceded by **plan 55 (code quality & typed contracts) COMPLETE (2026-08-31)** — closed vocabularies are StrEnums in `core/vocab.py` (ADR-128); the frontend contract is **OpenAPI-generated** (`pnpm api:types`, committed `openapi.json` + `api-schema.d.ts`, CI drift-guarded — ADR-129); **every JSON endpoint declares a typed pydantic response model** (ADR-130; final survey: 0 untyped 200/201-JSON responses, binary downloads intentionally model-free); WS topics + localStorage keys single-sourced in `lib/constants.ts`; assistant-ui adoption round 2 (copy-button/spinner/empty-state shims + big-surface sweep; family drift audit clean over 335 files). **Next up:** feature rounds **48–53** (`dev/plans/`, local-only) in order 48 → 49 → 50 → 51 → 52 → 53 — see the 2026-08-31 changelog entries and each plan's slices. Prior round: **shared UI library adoption (`@neuronection/assistant-ui`) COMPLETE (2026-08-29, user-requested)** — study consumes the family library (`github.com/neuronection/assistant-ui@0.1.0`, published via Changesets with provenance): `components/ui/button.tsx` and `card.tsx` are now **pure re-exports** from the library (implementations deleted, same-commit rule; 65+35 import sites untouched), `@neuronection/assistant-ui/styles.css` imported after `index.css` in `main.tsx` (token defaults == study's palette), `optimizeDeps.exclude` added to `vite.config.ts` (required for linked local development via the library's `dev-link` tooling); **all 27 `window.confirm` sites across 18 files** (settings, chat, library, notes, courses, practice, jobs, canvas/editor, layout) replaced by a promise-based `lib/use-confirm.tsx` hook over the library's destructive-themed `ConfirmationModal` — existing i18n keys reused (`*.confirmDelete*` → description, short labels → title/confirmLabel, `common.cancel`), and confirm-mocking tests now click the modal's confirm button (`within(dialog)` scoping where labels collide); drift is policed by the library's `audit-usage.mjs` (case-insensitive, study clean over 313 files) plus a weekly drift-audit workflow snippet in the library repo — preceded by **plan 45 (working directory, ADR-101) COMPLETE (2026-08-28, user-requested)** — the app data directory is now user-visible and changeable: `core/working_dir.py` pointer file (`<platform config dir>/StudyAssistant/working-dir.txt`, `SA_CONFIG_DIR` overrides the config dir for tests/packaging), `Settings.data_dir` factory resolves pointer → platform default (env `SA_DATA_DIR`/.env stays strongest), new `api/config.py` — `GET /config/working-dir` (`{path, default_path, custom, restart_pending}`), `POST …/validate` (absolute/writable/empty-or-`app.db` policy with machine reason codes; non-existent targets checked via nearest existing ancestor), `PUT` (write pointer, restart applies), `DELETE` (clear pointer); frontend shared `WorkingDirEditor` (input + Check/Use-after-restart/Use-default/Restore-default + restart-pending banner with Undo) mounted as a **Settings → Data card** and as **wizard step 2** (core-8 steps now) — preceded by **plan 44 (first-run setup wizard, ADR-100) COMPLETE (2026-08-28, user-requested)** — a fresh install (server truth: no provider AND no course) auto-opens a full-screen wizard overlay over the AppShell; `GET /onboarding/state` is the one-round-trip gate/summary aggregate (`has_provider/has_enabled_model/defaults_set/has_course/has_material`); core-7 steps (Welcome → AI provider → Enable models → Capability defaults → First course (create or load sample) → First files via `UploadDropzone`+`useMaterialUpload` on the created course → Done checklist with open-course CTA), every step skippable, dismissal in localStorage `ca-onboarding-done`, re-openable from Settings→Providers empty state and the Home onboarding card; `ProviderFormDialog` create-mode logic extracted into shared `useProviderCreate` + `ProviderCreateFields` so wizard and Settings can't drift — preceded by **plan 43 (infinite drawing canvas: pan/zoom navigation, fullscreen, crop-on-save + view-box scale metadata, ADR-098) COMPLETE (2026-08-28, user-requested)** — an unbounded canvas (wheel = zoom to cursor; middle-drag / Space-drag / hand tool = pan; floating bottom bar: zoom −/%,+, Fit, 1:1), fullscreen toggle on the drawing dialogs, saves crop the PNG to the strokes' bounding box + 24 px pad and persist the exported region as nullable `view` JSON on `note_drawings`/`material_drawings` (0046) so re-editing restores exact 100% scale; drawings render at natural size (no stretch) — preceded by **plan 42 (dictation via Whisper STT, ADR-097) COMPLETE (2026-08-27, user-requested)** — a 🎤 mic button in the shared Tiptap editor toolbar and the chat composer records a clip (MediaRecorder webm/opus, timer + live level strip, cancel), `POST /ai/transcribe` (multipart, ≤25 MB, optional language) returns `{text, model}` inserted at the cursor/draft caret; new `transcribe` task + `audio` capability in the task chain (provider-native STT: `openai_compatible` → `/audio/transcriptions` incl. local whisper servers, Google → `generateContent` inline audio via the `transcribe.audio` seed skill, anthropic unsupported; audio ephemeral, ledgered), Settings caps pickers gained `audio` — preceded by **plan 41 (chat branch-tree rail, ADR-095) COMPLETE (2026-08-27, user-requested)** — a `GitBranch` header popover renders the full conversation tree from a new read-only `GET /chat/sessions/{id}/tree` (commit-graph styling, active path highlighted, click a node = `select` that variant; no schema change, no graph deps) — preceded by **plan 40 (chat turn branches + composer & message actions, ADR-093…094) COMPLETE (2026-08-27, user-requested)** — 40A branch-tree core (migration 0044 `chat_messages.parent_id`/`active_child_id` + `chat_sessions.active_root_id`, active-path history, edit/regenerate/select endpoints, FIFO per-session turn lock); 40B message-action UI (copy/edit/resend/regenerate + ‹k/N› variant switcher); 40C "+"-menu equation editor/drawing canvas/screenshot-crop attachments; 40D stop-generation + scroll-to-bottom pill + code-block copy + session .md export; plan 33 (cheat-sheet menu + compose builder, ADR-070) DONE; plan 34 (interactive widget blocks + AG-UI state channel, ADR-071…076) COMPLETE; plan 35 (chat streaming performance + turn-trace observability + tool-call component system, ADR-077…079) COMPLETE; plan 36 (MCP resource tools as shared chat tools + Settings page, ADR-080) IN PROGRESS; plan 37 (AI gateway framework + reliability, ADR-081…084) **COMPLETE** — 37A LangChain behind the gateway (retry + fallback + real token accounting, socket-guarded no-network suite), 37B native `.bind_tools()` tool calling (cap-gated, prompt fallback), 37C `.with_structured_output()` pre-validation fast path, 37D prompt caching (Anthropic hints + OpenAI accounting, `cached_input_tokens` ledger); plan 32's Ctrl+N palette remains documented-only; **plan 38 (AI gateway best-practices alignment, ADR-085…087 — 2026-08-26) COMPLETE** (reasoning-effort parity incl. Google with per-provider value filtering, real-usage accounting in `generate_structured`, profile-based structured-output pre-gate, gateway cleanups); **plan 39 (jobs hygiene: failed-job delete + stale detection + boot pruning, and the task-defaults persistence fix — ADR-089/090) COMPLETE**

**plan 33 (`dev/plans/33-cheat-sheet-menu-and-builder.md`, ADR-070 — complete
2026-08-23, user-requested)**: the Overview tab's cheat-sheet action is now a **dropdown
menu** — `TabAction` gained a `menu` variant that renders the shared `PopoverMenu` (a
menu grammar every tab can reuse). No sheet → **Generate cheat sheet…**; sheet exists →
**Open existing** + **Regenerate cheat sheet…**. Both generate items open `GenerateDialog`
in `compose` mode pre-locked to `cheat_sheet` (`COMPOSE_KINDS` gained `cheat_sheet`), so
cheat-sheet generation gets the full context controls (materials add/exclude, notes,
concepts, instructions, live context preview); the composed result renders in the
overview preview card. The dedicated `POST /nodes/{id}/cheatsheet` endpoint and its
`cheat_sheet_markdown` prompt are **retired** — cheat sheets are now generated and
regenerated solely by the compose pipeline (`POST /materials/compose kind=cheat_sheet`,
one-live-artifact regeneration per ADR-043/051; backend tests re-based on it). Fixed a
latent i18n bug en route: `generate.action.compose` was missing, so the compose dialog's
primary button showed the literal key. Backend 486 · frontend 641 tests green.

**plan 32 (`dev/plans/32-unified-practice-and-builder.md`, ADR-069 — in progress
2026-08-22, user-requested)**: Practice becomes **one section + one builder** —
the two parallel quiz/exercise lists merge into one list with kind badges and one
primary **New practice** action (`features/practice/PracticeTab.tsx`), and
`GenerateDialog` gains a `practice` task mode: a format picker spanning quiz question
types + exercise kinds, free mixing, and a shuffle toggle; `quiz.generate` accepts a
`question_types` allowlist + `shuffle` (question order + option-order remap); the
`QuizRunner` gains a per-attempt shuffle toggle (localStorage, default off). 32A–32C
done (backend 483 + frontend 620 tests green); **32D materials/notes display +
unified Ctrl+N creation palette — the generate-dialog context picker is modernized
(2026-08-23: material chips + Add/Exclude pickers + a searchable note picker replace
the checkbox lists; frontend 636 tests); the unified Ctrl+N creation palette remains
documented-only**.

Preceded by **plan 31 (`dev/plans/31-inline-ai-helper.md`, ADR-068 — complete 2026-08-22,
user-requested)**: the shared Tiptap `MarkdownEditor` gains an **inline AI helper** — a ✨
toolbar button (new optional `aiHelper` prop, host-injected like the pen adapter) opening
a modern AI popover (Notion/Craft/Google-Docs "Help me write" pattern): transform presets
(explain / answer / compact / expand / rewrite / simplify / grammar / structure / bullets /
format-as-markdown / translate), a free-form prompt box, a **Context** chip (selection +
bounded surrounding text) and a **Course material** chip (only when `course_id` present;
grounds the prompt in the course via the Phase-10 ContextResolver), a **streamed live
preview** with a Stop button and repair re-stream, and **human-gated insertion**
(replace selection / at cursor / insert below / regenerate / discard) that parses the
generated markdown through tiptap-markdown's own parser so math/mermaid/tables insert
byte-faithfully. Backend: new code-seeded `editor_transform` task (Settings→Tasks model
row) + `editor.transform` seed skill (contracts: no-preamble, ≤8k chars, compact ≤ input,
answer needs a sentence, markdown fence/math balance) enforced by `TaskRunner`'s repair
loop, `EditorTransformService` singleton (`app.state.editor_ai`; in-memory job registry),
`TaskRunner.stream_text` (generator; last-round-only text, repair events, `stop` callable),
`POST /ai/editor/transform` → `{job_id}` with WS `ai-editor:{job_id}` streaming + `POST
/ai/editor/jobs/{id}/cancel` + `GET /ai/editor/jobs/{id}` poll fallback, all audited
(`AuditRef("editor_transform", …)`); nothing persisted but what the user inserts. Wired
into NoteEditor, ExtractionView and the new text/markdown file dialog. Frontend 599 ·
backend 479 tests green. Preceded by **plan 29 (`dev/plans/29-…md`, ADR-064 —
complete 2026-08-22)**: text/markdown
materials own drawings exactly like notes — `material_drawings` (migration 0032),
`ca-drawing://` refs in the extraction markdown, editable in-app via a
`DrawingAdapter` in the extraction QA editor, reading view renders them inline,
drawing OCR joins FTS/search + AI chunk context, derive copies + remaps refs,
`ca-course/v1` bundles round-trip them (additive field), and a material **Export
.md** embeds drawings as base64 PNGs (shared helper with the notes export). The
**new text/markdown file dialog also has the pen**: drawings are buffered in
  memory (placeholder `ca-drawing://-N` refs) and committed with the create —
  create the material, POST each buffered drawing, remap refs, save the extraction
  (now via `createTextMaterial`/`updateTextMaterial`); nothing is created until
  Create is clicked, and **the dialog stays open after Create** — Save writes
  again without closing (2026-08-22 follow-up).

Preceded by plan 28 (`dev/plans/28-…md`, ADR-063 — complete 2026-08-22): error-pattern
drills stop being a hardcoded calculus list — patterns become DB-backed,
course-type-scoped data (`error_patterns`, migration 0031; the G10 calculus
taxonomy seeds under the `math` course type), counts are scoped to the open
course (`Mistake→Question→Activity`), deterministic detectors tag
`sign_slip`/`dropped_factor` by code at grade time (equivalence chain, no LLM),
and the AI **proposes** new patterns from recent wrong answers (`pattern.discover`
skill → approve/dismiss, reusing the ADR-043 HITL protocol; approved rows are
`source=discovered`). Drill generation prompt is subject-agnostic (uses the
course subject + pattern description/example instead of hard-coded "calculus").
The DrillsCard shows Seeded/Discovered sections, an honest empty state, and a
*Find more patterns* action.

Then **plan 27 (`dev/plans/27-…md`, ADR-062 — complete 2026-08-22)**: the workspace
**Materials tab** gets the Library create grammar through one shared hook
(`useCreateMaterialMenu` — item list + hidden upload inputs, consumed by both
LibraryPage and MaterialsTab): a **New…** primary menu (New text file / New
Markdown file via the rich editor / New folder / Upload files… / Upload
folder…), the same items on **right-click over empty pane**, and **rectangular
marquee** selection. Placement per ADR-056/058: new files land unfiled in the
course library **+ auto-allocate to the opened node** (upload semantics); a new
folder is created at library root **and assigned to the node** and appears as a
**folder tile at the top of the materials list** (the old chip strip is gone —
2026-08-22 follow-up: assigned folders render as real folder tiles/rows that
double-click open the folder in the Library, linked-source folders deep-link
via a new `?source=` search param; folders join the selection grammar —
Unassign / Assign-to-node — like materials). The tab's split `UploadButton` is
retired (one create
affordance, matching the 2026-08-22 library simplification; the picker footer
keeps its own upload button).

Plan 26 (`dev/plans/26-…md`, ADR-060/061 — complete 2026-08-22): extraction
QA editing upgraded from a textarea to the shared Tiptap `MarkdownEditor`
(lazy-loaded) behind new round-trip guards (table schema nodes, Link protocol
allowlist incl. `ca-material:`/`ca-drawing:`/`mention:`, math-span backslash
protection in the fidelity helpers — byte-identity tests over an extraction
corpus; supersedes ADR-055's textarea clause), plus **Save as material**
(`POST /materials/{id}/derive`): the QA-ed extraction becomes a standalone md
material via `create_text` + `provenance {source: derived, from_material_id,
from_version}` + standard ingest — the original is untouched; the derived
material also inherits the original's node assignments plus the opened node
(plan-26 follow-up).

Plan 25 (ADR-058) — **complete 2026-08-22**: library folders (incl. linked
sources) are assignable to nodes as course material — `material_folder_links`
(0030) with **read-time membership resolution** (new files join automatically),
folder-aware workspace/tree/AI context/organizer, picker + workspace + library
UI, export/import round-trip.

Plan 24 (ADR-056/057) — **complete 2026-08-22**: the
Library behaves like Nemo — **A** backend verbs (`PATCH /materials/{id}/move`,
`POST /materials/{id}/copy` sharing the blob + deep-copying the latest
extraction, `/move` node endpoints for notes/quizzes/exercises), **B** shared
primitives (`useSelection`, `useMarquee`+band, typed clipboard store),
**C** library wiring (Ctrl/Shift/marquee selection, Cut/Copy/Paste +
keyboard, drag-to-folder move with multi-id payload, Assign-to-node dialog),
**D** workspace tabs get the same grammar as **placement verbs** (bulk
unassign/assign materials, bulk delete notes/quizzes/exercises with trash
undo, Move-to-node for all three). Next per `dev/plans/05-roadmap.md`:
post-1.0 backlog (local OCR adapter, Tauri shell, audio/video ingestion,
plugins, PDF stroke-layers, graph-sketch grading, etc.) — plan 34 (interactive
widget blocks + AG-UI state channel, `dev/plans/34-interactive-widgets-and-agui.md`)
is **complete** (ADR-071…076); the graph-sketch/numberline *grading* (G7/C21) is the
natural follow-on, now that the widget state channel exists.

Phase 11 shipped
the AI-as-first-class-actor work end
to end (mentions → on-demand context → HITL proposals → AI-composed material →
companion glue).


Phase 11 (user decision 2026-08-20, **ADR-043, plan `dev/plans/15-ai-companion.md`**):
the AI becomes a first-class actor — entity **mentions** (done, 11A), chat
**on-demand context** via a READ tool (done, 11B), **HITL proposal cards**
(11C1/11C2), **AI-composed material** (11D), companion glue (11E).

**11A — Mentions (done, 2026-08-20)**: `app/ai/mentions.py` (registry + parser;
handles are real ids `[M#][N#][C#][T#]`, `Q/E` reserved), `ContextBundle.mentions()`
+ node manifest section in the resolver prompt, migration **0022**
(`chat_messages.mentions`, `chat_sessions.mention_registry`), chat builds a
**session-stable registry** (accumulates across turns; offers scoped material
titles regardless of retrieval) and stores resolved mentions on messages +
emits them in `assistant_message`; quiz explanations and exercise context/step
blocks carry `mentions`; `mentions_in_range` **advisory** contract constraint
(violations logged, never block — rollout signal); seed prompts teach the
protocol; frontend `features/ai/EntityMention` (one chip: M→library, N→note,
C→concepts tab, T→node workspace, Q/E→runner) + `AiBadge` + inline rendering in
BlockRenderer (markdown `mention:` links + standalone `mention` block type).

Phase 10 (user decision 2026-08-20, **ADR-042, plan `dev/plans/14-ai-task-layer.md`):
a uniform way to invoke AI generation with explicit, inspectable context. **10A**
`ContextResolver` (`app/services/context.py`) — scope (node/subtree/course) +
material opt-in/out + notes + concepts + per-node **AI hints** → one budgeted
prompt manifest; chunk-level **hybrid retrieval** (FTS ⊕ sqlite-vec, RRF) fixing
the embeddings-ignored gap. **10B** `TaskRunner` (`app/ai/runner.py`) — uniform
skill resolution/repair-loop/audit; quizgen/exgen/flashcards migrated, their
duplicated JSON/loop/audit/prompt-constant code deleted (`app/ai/parsing.py`
shared helpers). **10C** migration 0021 `tree_nodes.ai_hint` + context params on
quiz/exercise/flashcard generate + `POST /ai/context/preview` (no LLM call).
**10D** one uniform **GenerateDialog** (frontend `features/ai/`) — task params,
scope picker, material checkboxes (opt-out/add-in), notes + concept selection,
one-time instruction field, live context preview; Practice/Cards tabs
open it (the Flashcards page did too, before its 2026-08-21 retirement);
per-node AI-instructions card in the workspace
overview. **10E deferred**: chat keeps its own context assembly; manifest +
`read_item` tool and MCP sharing the resolver are future work.

Phase 9 (user decision 2026-08-19, **ADR-039, plan `dev/plans/12-uniform-scoping.md`**):
chapters/sections collapse into a **unified node tree** (`tree_nodes`, ≤4 node levels
below the course, undeletable root = course level). All placement (quizzes, exercises,
flashcards, notes, material links, concept coverage, chat) becomes one `node_id`
column with a composite FK `(node_id, course_id)` — intra-course placement is
DB-enforced (replaces the polymorphic ADR-038 design before it shipped; supersedes
ADR-035's fixed-2-level clause — outline AI keeps 2 levels as policy). Ownership
stays `course_id`; concepts stay one course graph with per-node coverage. Materialized
`path`/`sort_path` → indexed subtree roll-up + depth-first ordering. Slices: 9A
migration 0019 + tree service + scoped APIs + **frontend migration to the node APIs
(done — see changelog)** · 9B unified NodeWorkspace UI **(done)** · 9C concept
coverage per node **(done)** · 9D scope-bound tutor chat **(done)** · 9E local
read-only **MCP resource server (done — `python -m studyassistant mcp`, stdio)**.

Phase 8 (user-approved 2026-08-19, ADR-035/036/037; roadmap
`dev/plans/05-roadmap.md`) is complete: **8A** per-course materials & scoped
assignment (0014) · **8B** Nemo library + material page + symlink sources (L1,
0015) + chapter workspace/course tabs + reconciliation automation (L2) +
per-source scan options/error reporting (L3, 0016) · **8C** notes tags +
pagination (0017) + **Tiptap rich editor** · **8D** concepts & knowledge graph
(0018) · **8E** AI chapter organizer — Review findings (gap/ordering/orphan/
coverage, validated), chapter cheat sheets, per-section AI-drafted notes
(tagged `ai-draft`, linked to the section, open in the editor) · **I5 command
palette** (Ctrl+K: fuzzy navigation, quick note, tutor chat, course jumps) ·
concept analytics (weakness matrix + materialize write `concept_id`; quiz
generation accepts `concept_id`).

Plans: `dev/plans/` (01–55; 47–55 planned rounds from the 2026-08-31 audit — order 54 → 55 → 47–53) — **gitignored, local-only**. Roadmap: `dev/plans/05-roadmap.md`. ADRs: `dev/plans/06-decisions-and-risks.md` (102 recorded; 103–130 reserved by plans 47–55 — 046–051 plan 22, 052–055 plan 23, 056–059 plan 24, 058–059 plan 25, 060–061 plan 26, 062 plan 27, 063 plan 28, 064 plan 29, 065 folder delete-refusal UX, 066 folder-delete cascade, 067 multi-item drag, 068 inline editor AI helper plan 31, 069 unified practice plan 32, 070 cheat-sheet compose menu plan 33, 071 AG-UI contract plan 34, 072 widget layer plan 34, 073 renderers plan 34, 074 state channel plan 34, 075 exercise widgets plan 34, 076 chat widgets plan 34, 077 turn-trace observability plan 35, 078 per-tool component registry plan 35, 079 incremental memoized streaming rendering plan 35, 080 shared MCP resource-tool registry + chat resource tools plan 36, 081–084 AI gateway framework plan 37, 085–087 AI gateway best-practices plan 38, 088 per-capability default task models, 090 insert-only seeding of `default_task_assignments` (plan 39 — fixes the restart wipe), 089 job lifecycle hygiene: explicit deletion + stale detection + done-history pruning (plan 39), 097 dictation/transcribe task plan 42, 098 infinite drawing canvas + crop-on-save + view-box scale metadata (plan 43), 102 OCR payload efficiency + async drawing OCR (plan 46), 099 shell reaffirmed (pywebview) + PyInstaller/deb/AppImage/exe packaging + tag-driven release. Tracked docs: AGENTS.md, `docs/` (`.opencode/` and `dev/` are gitignored, local-only).

## Module status

| Module | Status | Notes |
|---|---|---|
| **Working directory (plan 45)** | done | The app data directory (db/blobs/backups/cache) is a first-class setting. Backend: `core/working_dir.py` (pointer file in `SA_CONFIG_DIR`, default `<platform config dir>/StudyAssistant/working-dir.txt`), `Settings.data_dir` factory = pointer → platform default (`SA_DATA_DIR`/`.env` still wins), `api/config.py` — `GET /config/working-dir` (`path`/`default_path`/`custom`/`restart_pending`), `POST /config/working-dir/validate` (absolute, writable, empty **or** existing SA dir with `app.db`; reasons `relative_path`/`already_current`/`inside_current`/`contains_current`/`not_a_directory`/`not_writable`/`not_empty`/`invalid_path`; writability probed with a temp file, creatable paths via nearest existing ancestor), `PUT` (validate + write pointer; applies on restart), `DELETE` (clear). Frontend: shared `features/settings/WorkingDirEditor` (validate feedback, Save gated on a validated changed path, Use-default, Restore-default, restart-pending banner + Undo) in **Settings → Data** (top card) and **wizard step 2** (now 8 steps). No live rebind, no auto-copy — moving data = backup/restore (`usage/getting-started.md`). Tests: `test_working_dir.py` (8) + `WorkingDirEditor.test.tsx` (4) |
| **First-run wizard (plan 44)** | done | Fresh install (no provider AND no course, server truth) auto-opens a full-screen wizard overlay over the AppShell; `GET /onboarding/state` (`has_provider`/`has_enabled_model`/`defaults_set`/`has_course`/`has_material`) is the gate + Done-summary aggregate. Core-7 steps (`features/onboarding/`): Welcome → **Provider** (shared `useProviderCreate`+`ProviderCreateFields` extracted from the Settings dialog; create advances automatically) → **Models** (enable toggles + Enable all over discovered models) → **Defaults** (text/vision/embeddings/audio selects over enabled+cap-matching models, TasksTab pattern) → **Course** (create via `POST /courses` or load `POST /onboarding/sample`, adopts real title from the refreshed list) → **Files** (`UploadDropzone` + `useMaterialUpload` on the created course; ingest continues in background) → **Done** (checklist from refetched state + Open-course/Go-to-Today CTAs). Fully skippable (Back / Skip for now / header X), dismissal in localStorage `ca-onboarding-done` (same `ca-*` convention), re-openable via `useWizardStore.openWizard()` from Settings→Providers empty state + Home onboarding card. Fetch error ⇒ never auto-open. Tests: `test_onboarding_state.py` (2) + `OnboardingWizard.test.tsx` (7) |
| **Job retry + task-activity rail** | done |`api/jobs.py` — `GET /jobs` (status/type filters, labels, errors, `material_id`, `retriable` flag, **+`stale` flag when the job's material/chat-session no longer exists**), `GET /jobs/summary` (queued/running/failed/done + `failed_retryable`, **+`failed_stale`**, **+`cancelled` (54-A)**), `GET /jobs/types`, `POST /jobs/{id}/retry`, `POST /jobs/retry-failed` (optional type filter); retriable = failed + handler registered + not `chat_turn`; retry resets to queued, wakes pool; **plan 39B (ADR-089): `DELETE /jobs/{id}` (204; done/failed only, queued/running → 422) + `DELETE /jobs/failed` bulk delete (optional `{types}` filter, covers non-retriable `chat_turn`; literal route declared before `/{job_id}`)**; **boot-time prune of done history (39C: `prune_done_jobs`, `SA_JOBS_DONE_TTL_DAYS` default 14)**. **Plan 54-A (ADR-126): terminal `cancelled` status — cancel-on-purge for queued jobs, cooperative cancel flags + report checkpoints for running ones, commit-time stale re-checks in ingest/postprocess/drawing_ocr (`app/jobs/cancellation.py`); cancelled rows are grey, non-retriable, excluded from the failure badge, deletable; JobsPage Cancelled tab + ActivityPopover cancelled chips; upload banner treats cancelled as terminal.** Frontend (39D): `/jobs` page per-row delete + header **Delete…** menu (*Delete all failed* incl. Type-filter scope, *Delete source-missing*) + `source removed` chips with retry hidden; activity popover per-row delete + **Delete all failed** icon + **Delete source-missing (N)**; `ActivityButton` (rail footer): red failure badge from summary polling, panel with failed/in-progress/done sections, per-row ⭯ retry + **Retry all N**, 2 s refresh while open, **View all tasks** link → new `/jobs` page (status tabs w/ counts, search, full errors expandable, status·stage chips, material deep links); 3 JobsPage tests; `usage/activity.md`. Plan 39D adds delete/stale UI affordances |
| **Interactive widgets & AG-UI (plan 34)** | done | **34A (ADR-071)** `app/agui/` contract (`events.py`/`state.py`/`mapping.py`); **34B (ADR-072)** `widget` block + `components/widgets/` registry + `app/ai/widgets.py` grammar; **34C (ADR-073)** `PlotlyChart`/`JsxGraphBoard` render `chart`/`geo`; **34D (ADR-074)** migration 0033 `state` columns + `PATCH /chat/messages/{id}/state` + `STATE` tool + `diffState`; **34E (ADR-075)** exgen `steps[].widgets` + `step_attempts.state` recording + player collection; **34F (ADR-076)** `PLOT` tool + ` ```chart `/ ` ```widget ` fence parsing into chat blocks + chat-panel PATCH wiring. Deferred (non-goals): numberline/graph-sketch grading, context-resolver `widget_state` slot, live WS `StateSnapshot` read, `ag-ui-protocol` SDK interop |
| **AI companion (P11)** | done | **11A mentions done** — registry/parser (`app/ai/mentions.py`), session-stable chat handles (0022), mentions on messages + explanation/step blocks, advisory `mentions_in_range`, `EntityMention`/`AiBadge` + BlockRenderer inline chips. **11B chat on-demand context done** — chat on ContextResolver (hybrid retrieval, subtree scope, manifest w/ index-card summaries first), `READ <handle>` tool (own budget 3/turn, 4k chars, model-only results; reads recorded 0023 + shown as eye chips), tool doc generated from `CHAT_TOOL_CATALOG` (single source w/ `/ai/tools`), `GET /chat/sessions/{id}/context` + "What the AI sees" panel, ProviderError logged in postprocess jobs, CONTEXT_VARS extended; **2026-08-21: READ covers quiz/exercise, composer attachments feed the registry (see Chat RAG row + changelog)**. **11C1 HITL
proposals core done** — `app/ai/proposals.py` (create_note whitelist + fence
protocol), blocking `proposal_valid` contract (repair loop; strip-on-failure),
migration **0024** `chat_proposals`, click-gated approve/dismiss endpoints
(create_note → real note via placement rules, tag `ai-proposal`, audited
`context_type=proposal`; 409 on non-proposed), `ProposalCard` UI with payload
preview + note deep-link. **11C2 proposal actions done** — assign_material /
cover_concept / set_node_ai_hint schemas + `services/proposal_actions.py`
executor with **execute-time revalidation** (already-satisfied → executed
no-op note; invalid target → `stale` status + reason), generate_quiz /
generate_exercise approve → `approved` + `open_dialog` params (GenerateDialog
opens prefilled — the Generate click is the approval), dismissal feedback
(≥2 dismissals/session → conservative note in system prompt), ProposalCard
resolved-state rendering + stale explanation + Open-generator handoff.
**11D compose done** — `material_compose` task + `material.compose` skill,
`TaskRunner.run_text` (markdown variant), `pipelines/compose.py` (validators:
length + mention ranges; advisory sampled math lint; repair loop),
`ContextSpec.exclude_ai_composed` self-exclusion, migration **0025**
`materials.provenance`, `POST /materials/compose` (+ auto-assign + ingest),
compose preset on GenerateDialog, chat `compose_material` proposal, AiBadge in
library + workspace rows. **11E glue done** — `notes_ocr` registered through
SkillService (skill override test), exercise-completion **session summary note**
(`POST /exercises/sessions/{id}/summary-note`, deterministic mistakes/hints
recap, tag `session-summary`, Player completion button), Today **Ask the tutor
about {weak concept}** (pre-scoped chat session), Settings Tasks tab
**unassigned-model nudge** (embeddings/concepts consequence text). Skills
sandbox test-run covers the mention/proposal protocol by construction (chat
contract builders now include those constraints) |
| **AI gateway (plan 37A, ADR-081)** | done | `LLMGateway` speaks to providers through **LangChain chat models** behind the same surface (`resolve`/`generate`/`stream`/`stream_events`): `ChatOpenAI` (Ollama via the `openai_compatible` preset) / `ChatAnthropic` / `ChatGoogleGenerativeAI`; budget gate, keyring read, and `ai_interactions` ledger unchanged. **First-class retry loop** (transient-only: ≥500/429 or `httpx` cause; streams retry only before the first chunk) + **ADR-029 fallback chain** now real (`[primary, fallback]`, `_ledger` + trace attributed to the answering model). **Real `usage_metadata` tokens** into the ledger (estimate kept only for offline/mock). Reasoning: OpenAI-compatible `reasoning_content` via the `CaChatOpenAI` subclass, Anthropic/Google `{"type":"thinking"}` content blocks. Mid-stream chat failures persist the streamed prefix with `trace.stream_interrupted` + a `stream_interrupted` event (no replay). **Native tool calling (37B, ADR-082):** `tools`-capable models get `.bind_tools()` schemas (generated from the prompt catalogs) and stream structured `tool_call` events; chat executes the same deterministic tool body and feeds `ToolMessage`s back (prompt-grammar fallback for text-only models, identical `tool_call` events; **auto-degrades to the prompt grammar in-memory when a model's endpoint rejects bound tools**). **Structured generation (37C, ADR-083):** `generate_structured` uses `.with_structured_output()` (cap-gated, permissive Pydantic schemas, degrades to plain `generate` on unsupported errors) as a fast path for quizgen/exgen/flashcards/rubric/pattern.discover. **Prompt caching (37D, ADR-084):** Anthropic `cache_control` on the chat turn's first system block + OpenAI cache-read accounting; ledger persists `cached_input_tokens` (migration 0037) with cost discounted at 0.1×; Google `cachedContent` descoped. **Plan 38 hardening (ADR-085…087):** `reasoning_effort` now reaches Google (filtered to `minimal/low/medium/high`) and is filtered per-provider on Anthropic too — an out-of-set stored value drops to the provider default instead of failing model construction; `generate_structured` bills real `usage_metadata` tokens via `with_structured_output(include_raw=True)`; a `model.profile["structured_output"]` pre-gate skips the structured fast path (no round trip) when the profile confidently says unsupported, keeping the error-based degrade for unknown profiles. New `app/ai/chat_models.py`, `app/ai/types.py`, `app/ai/structured.py`; **socket-blocking suite guard** (no live network in tests) + telemetry-off test (no `LANGSMITH_*`/`LANGCHAIN_TRACING_V2`). **Per-capability default task models (2026-08-26, ADR-088, migration 0041):** `default_task_assignments` keyed by capability (`text`/`vision`/`embeddings`) with `model_id`/`fallback_model_id`; `_resolve_chain` null-coalesces task → capability default (a per-task assignment is an override, partial overrides inherit the default fallback); `GET/PUT /api/v1/tasks/defaults` + `PUT /tasks/defaults/{requires}`; `TaskOut` gains `inherits_default` + default labels; Settings → Tasks shows a Default models section and per-task "(Inherit default)" / custom override; budgets stay per-task; provider/model delete + backup restore null/reseed defaults. |
| **AI task layer & context engine (P10)** | done | `services/context.py` (ContextSpec→ContextBundle: scope/material include-exclude/notes/concepts/hints; hybrid chunk retrieval FTS⊕sqlite-vec via RRF, FTS-only fallback; manifest + budgeted render) · `ai/runner.py` (TaskRunner: skill resolution, JSON repair loop, uniform audit w/ model+latency; **plan 31 added `stream_text`** — streaming generator w/ repair re-stream + `stop` callable) · `ai/parsing.py` (shared extract/fence/blocks→md/tokens) · quizgen/exgen/flashcards run on it · generate endpoints accept `scope/include_material_ids/exclude_material_ids/note_ids/concept_ids/context_hint` · `POST /ai/context/preview` · `tree_nodes.ai_hint` (0021; root = course-level; inherited from ancestors) · frontend `features/ai/GenerateDialog` (uniform dialog + preview) + `AiHintCard` (workspace overview). **Plan 31 inline editor AI**: `editor_transform` task + `editor.transform` seed skill + `EditorTransformService` (`app.state.editor_ai`, in-memory job registry, `POST /ai/editor/transform` → WS `ai-editor:{job_id}` streaming + cancel + poll fallback, optional course grounding via the resolver). Deferred (10E): all closed — chat on the resolver + READ tool (11B), MCP `get_node_context` (plan 17 F). **Per-course task-model overrides (ADR-091, 2026-08-27)**: `course_task_assignments` + `course_default_task_assignments` (0042/0043) with `GET/PUT /courses/{id}/tasks[/{task}]` and `…/tasks/defaults[/{requires}]`; `LLMGateway`/`TaskRunner` thread an optional course_id so resolution is per-slot global default → global task → course default → course task; workspace root **Settings tab** (General: title/description; Tasks subtab: defaults card + override list). **Plan 42 added the `transcribe` task (`audio` capability) for dictation — `LLMGateway.transcribe` (provider-native STT: openai_compatible `/audio/transcriptions`, Gemini inline audio, ledger + fallback like `generate`) behind `POST /ai/transcribe`, mic buttons in the shared editor + chat composer** |
| Repo scaffolding (uv + pnpm workspaces, CI) | done | Root uv workspace → `backend/`, pnpm workspace → `frontend/`; GH Actions runs both suites + `alembic upgrade head` |
| **Packaging & release (ADR-099)** | done (Linux verified locally; Windows pending first tag CI run) | `packaging/studyassistant.spec` (PyInstaller 6: SPA + alembic + sqlite-vec + per-platform pywebview backends; Linux `gi.overrides` + system typelibs `gi_typelibs` + glib schemas; `SA_ONEFILE`/`SA_CONSOLE`), `runtime_hook.py` (windowed logs, GI typelib/schema paths), `build-linux.sh` → `.deb` (system webkit deps) + self-contained `.AppImage` (ldd-closure bundling incl. WebKitGTK + pixbuf loaders); `.github/workflows/release.yml` tag `v*` → test gate → artifacts → draft GH release; Windows onefile `.exe` via the same spec. `default_data_dir` platform-aware (APPDATA / macOS App Support / XDG). See `docs/usage/packaging.md` |
| Backend skeleton (FastAPI, config, keyring, health) | done | `create_app()` factory, `GET /api/v1/health` (db-checking), pydantic-settings (`CA_*` env), keyring wrapper, structlog, in-process EventBus |
| Frontend skeleton (Vite, Tailwind, shadcn, i18n harness) | done | React 19 + TS strict, Tailwind 4 tokens, shadcn (button/card + components.json), react-i18next `en` catalog, `no-literal-string` lint rule, TanStack Router/Query, Zustand, framer-motion. **Bundle split (plan 17 G)**: note editor behind `React.lazy` (tiptap in a lazy chunk); vendor chunks `react-vendor`/`framer-motion`/`katex` via rolldown `codeSplitting.groups`; entry 697 kB min / 192 kB gzip (was 2,067/627) |
| pywebview shell | done | `pnpm app` / `python -m studyassistant` opens the SPA in WebKitGTK — **user-verified on Linux Mint**, incl. env de-snapping (snap VS Code) and `private_mode=False` (localStorage). **Window geometry persisted** (2026-08-28): 1280×800 centered first run, then size/position/maximized restored from `<data_dir>/window-state.json` with work-area clamping + drift-free move tracking. **Native folder picker bridge** (2026-08-30): `js_api DesktopBridge.pick_folder` (GTK SELECT_FOLDER via `webview.FileDialog.FOLDER`) + root-contained `GET /desktop/folder|file` (see `api/desktop.py`) — *Upload folder…* works in WebKitGTK, which can't pick directories natively. **Browser-first pivot (see Open issues)**: `python -m studyassistant web` + `scripts/{webapp,dev,app}.sh` / `pnpm {webapp,dev,app}` are the launch paths; webapp mode serves the built SPA on `SA_PORT` (default 8000) and opens the default browser |
| Design tokens & block renderers | done | Semantic palette (surface/subtle/border/primary/success/warning/danger, light+dark, OS-following theme), BlockRenderer for text(math)/math/diagram/chart/image/table/code/geo + unknown fallback |
| Golden eval fixtures (scans + handwriting) | blocked | Dir `backend/tests/fixtures/golden/` + README conventions ready; **needs the author's real scans (~20 pages, ~10 handwriting)** — see Open issues |
| WS plumbing | done | `/ws` endpoint (subscribe/unsubscribe/publish/ping) + frontend `WsClient`; tested both sides |
| Storage (SQLite, blobs, FTS5, sqlite-vec) | done | Schema (Phase 1–8A tables) + content-addressed blob store + FTS5 table done; embeddings via providers (local embeddings deferred, ADR-032); vec rows cleaned on material purge |
| Ingestion + OCR pipeline (P1) | in progress | Core done: folders (**per-course trees, 8A**), providers/models/tasks, gateway, task-based OCR, **extraction QA editing — now the shared Tiptap rich editor (plan 26, ADR-060: tables/links/math round-trip guarded, supersedes the textarea of ADR-055)** (PATCH → new version → re-chunk → FTS re-sync → re-embed) **+ Save-as-material derive verb (plan 26, ADR-061: `POST /materials/{id}/derive` → standalone md material, provenance `derived`, content-hash dedup excluding the source)**, **material drawings (plan 29, ADR-064, 2026-08-22): `material_drawings` (0032) + `ca-drawing://` refs in the extraction markdown — editable in-app (the extraction editor's pen button via a `DrawingAdapter`; reading view renders them via `resolveDrawing`), drawing OCR joins FTS + AI chunk context, derive copies + remaps refs, `ca-course/v1` carries them, and a material **Export .md** resolves refs to embedded base64 PNGs (shared `exportMarkdownWithDrawings` helper)**; **inline AI helper in the QA editor (plan 31): the shared editor's ✨ button transforms/free-forms the extraction in place**; **OCR image prep (plan 46, ADR-102)**: long-edge cap (`ocr_image_max_edge`, default 1568) + WebP q85 re-encode at the engine boundary for every vision-OCR payload; **drawing OCR is a background `drawing_ocr` job (ADR-102)** — drawing saves/re-OCR return immediately, transcripts arrive over WS, failures are retriable jobs. **originals served** (`GET /api/v1/blobs/{sha}`) for side-by-side view, **hybrid search** (FTS5 + sqlite-vec cosine, RRF fusion; falls back to FTS when embeddings unassigned; **typo-tolerant fuzzy tier via `material_fts_trigram` (0045) — `services/search/` engine shared by `/search` (course-scoped), RAG retrieval and notes search**), **embeddings** via `embeddings` task (google batchEmbedContents / openai-compatible; anthropic N/A), **LLM index cards** via `description` task (postprocess job, best-effort). **plan 47 (2026-08-31, ADR-103/104): upload honesty** — unknown types refused 422 with machine reasons at the door (`GET /materials/accepted` drives the pickers), linked sources skip-with-reason; **office/web kinds** (docx/pptx/epub/html) convert to markdown extractions at ingest (`pipelines/convert/`, provenance `converted`, `material_images` 0048 + async `image_ocr` joining FTS); **AV transcripts** — audio/video transcribe via the provider task into searchable materials (`transcribed` provenance, mutagen 0049 duration/bitrate, pre-flight 25 MB warning, no ffmpeg). Remaining: golden OCR evals (blocked on user fixtures) |
| Courses/outline/allocation (P3) | in progress | Course CRUD; **unified node tree (9A: migration 0019, tree service, node APIs; frontend migrated)** — `GET /courses/{id}/tree` returns the nested node list (undeletable root = course level, ≤4 levels), node CRUD + move (merge-delete: children + placements move to parent); outline **draft → review/edit → commit** flow unchanged (LLM drafts 2 levels; commit writes depth-1/depth-2 nodes); **scoped assignment (8A/9A)**: material_links per node via `/nodes/{id}/materials` (course level = root), `/courses/{id}/materials` listing, per-node manual allocate/deallocate in the outline tab and the workspace Materials tab (**MaterialPickerDialog** catalog picker — folder-tree sidebar, breadcrumbs, fuzzy filter, multi-select incl. whole-subtree/select-shown, assigned-locked rows, linked-source browsing with ingest-&-select, one-click batch allocate, **upload row into the browsed folder w/ auto-select + workspace *Upload files* action & empty-state dropzone (unfiled → auto-allocated, 2026-08-21)**; grid/list `ViewToggle` + right-click Open/Remove-from-node menu since 2026-08-21), drag-to-reparent; read-status (B16) per profile (`unread/reading/studied` + progress); **course deletion purges all owned content** (materials+extractions+FTS+vec, folders, tree, quizzes, exercises, flashcards, notes, chats). Frontend: Courses list + **unified NodeWorkspace (9B)** — one scaffold for the course root (`/courses/$cid`) and every node (`/courses/$cid/n/$nid`; old `/chapters/$nid` URL redirects for one release), routable tabs overview/materials/notes/concepts/practice/tutor (Cards merged into Practice as a Flashcards segment 2026-08-26; `?tab=cards` deep-links to it; underline tabs with icons + tree-count badges incl. a due-cards badge on Practice — restyled from pills 2026-09-01), single-row breadcrumb header (last crumb = bold page title + course accent dot, `aria-current="page"`; no separate title/summary block — 2026-08-27), depth-aware **Study here** (quiz generated at the node, jumps into the runner) and **Ask about this node** (chat session bound to the node, opened in the sidepanel — 2026-08-27), children-as-cards with quick actions, recursive outline editor (9A) embedded as the root overview tab, **node creation in the Overview action bar (2026-08-23: root Structure card and the inner Subsections "Add child" button retired — every node's bar adds Add child (inner) or AI outline + Add node (root) next to Compose/Review/Cheat sheet, with an inline title form below the bar; the sidebar right-click still works)**, scope chips on quiz/exercise/note rows (id→title map from the tree), generate flows default to the current node with a this-node/whole-course picker, concept coverage management (9C: per-node cover/uncover + add-coverage picker over the course graph), node-bound tutor tab (9D: `?node_id=` session list + CTA), palette node actions ("Quiz me on X" / "Open X", depth-indented, depth ≤ 2), **notes-in-context restructure (ADR-040 follow-up)** — NotesTab = search + tag chips + load-more over the node roll-up, rows/create/draft open `NoteEditorDrawer` via the `?note=` search param (no flat notes page, no /notes nav; `/notes` URLs redirect); **practice-in-context
restructure (ADR-040/041 follow-up)** — the Practice tab is the quiz+exercise home
(rolled-up lists with scope chips, question counts, difficulty, export/.qpkg/print on
quiz rows — **now in the row/grid context menu with Rename/Delete +
grid/list toggle (2026-08-21)**, per-row similar on exercises, generate quiz/exercise with this-node/whole-
course scope, quiz ImportDialog course-prebound, DrillsCard bound to the workspace
course; `/quiz` + `/exercises` flat pages removed, URLs redirect to `/courses`;
runners `/quiz/$id` + `/exercises/$id` unchanged as focus modes; palette fuzzy-searches
quiz/exercise titles into the runner/player, flat nav actions gone); **outline tree
collapse + virtualization** — per-node chevron collapse, flattened visible rows
rendered plainly ≤40 or via `@tanstack/react-virtual` (dynamic measurement) above;
**structure sidebar** — `GET /courses/{id}/tree` now carries per-node direct counts
(materials/notes/quizzes/exercises/flashcards, grouped-count queries); the workspace
gained `NodeTreeSidebar` (left panel, sticky, hidden <md + header toggle):
whole-course clickable tree with chevron expand/collapse, auto-expand of the
current node's ancestors, current-node focus style + `aria-current`, non-zero
count badges with tooltips, node total, expand/collapse-all, virtualization above
40 visible rows, tab preserved on navigation, **tree editing** (right-click menu:
add child / rename / delete with merge-confirm; inline forms; drag-to-reparent;
panel-wide right-click on non-row areas acts on the active node — falls back to
the course root, filter input keeps its native text menu);
**embedded outline tree retired** — root overview carries a compact Structure card
(AI outline draft/commit + add node; `OutlineActions.tsx` replaced
`OutlineEditor.tsx`); **chapter/section wording retired**
from the outline UI (single node/child vocabulary — `Add node`, `Node title`);
**plan 13 round**: persisted open/expanded state (localStorage), fuzzy node
filter, keyboard navigation (↑/↓/→/←/Enter, aria-activedescendant),
drop-between reordering (before/after/into edges), material-drop assignment
(`application/x-ca-material` onto rows), study telemetry per node
(`studied`/`cards_due` in tree counts → progress ring + due badge),
scope/assigned-to chips deep-link into the node workspace, **undo node
delete** (snapshot registry + `POST /nodes/restore` + sidebar undo toast);
**plan 17 E**: right-click → **Study…** opens the generic `EntityActionMenu`
via `courseNodeSource` (ask/quiz/exercises/flashcards/study guide/write note,
node-scoped; handlers shared with the mindmap through
`useEntityActionHandlers`); **plan 18 A**: materials open **in place** from the
Materials tab — `MaterialDetailDrawer` over the workspace (`?material=` param,
shared `MaterialDetailBody` with the library page, FocusShell overlay chrome);
**plan 20**: uniform **`TabActionBar`** as every tab's first element (one primary
action per tab — except the Practice tab's two peer generation actions, both
primary since 2026-08-21; ghost secondaries since 2026-09-01, built-in pending spinner,
right-aligned info slot — see changelog 2026-08-21); **plan 27 (2026-08-22)**:
the Materials tab gets the library create grammar via the shared
`useCreateMaterialMenu` hook — **New…** primary menu (text/Markdown file w/
rich editor, folder, uploads) + right-click pane menu + rectangular marquee;
new files auto-allocate to the node, new folders assign to the node
  (ADR-062); the new-file dialog stays open after Create so you can keep editing
  (Save writes without closing, Done exits — 2026-08-22 follow-up); **plan 21**: header **node settings popover**
(title/description/AI instructions; badge when hint set; course PATCH syncs the
root node); **plan 32 (ADR-069)**: the **Practice tab is one merged list** — quizzes +
exercises share one `EntityItems` surface with kind badges and a single primary **New
practice** action (extracted to `features/practice/PracticeTab.tsx`), unified
selection/move/delete/rename/context-menu grammar (per-kind extras preserved: quiz
export/.qpkg/print, exercise similar), while the generate entry point is the unified
**practice**-task builder in `GenerateDialog`; **item detail popovers (2026-08-22)**: the
shared `EntityItems` render a hover-revealed `InfoButton` (modular `InfoButton`/`FieldLabel` +
`info`/`infoTitle` on `EntityItemEntry`) next to the title in list/grid layouts, and the
practice-builder fields/chips show per-option details — all ℹ buttons open on **hover or
click** (`Popover.openOnHover`); **plan 33 (ADR-070, 2026-08-23): the cheat-sheet action is a dropdown menu** (`TabAction.menu` → shared `PopoverMenu`): no sheet → Generate cheat sheet…, sheet exists → Open existing / Regenerate cheat sheet…; both generate items open the compose builder pre-locked to `cheat_sheet` (full context controls) and the result previews inline; the dedicated `POST /nodes/{id}/cheatsheet` + `cheat_sheet_markdown` prompt are retired — `POST /materials/compose kind=cheat_sheet` is the sole cheat-sheet path (one-live-artifact regeneration); remaining: mistake-notebook → node links (needs
a backend node binding) |
| Chat RAG (P7) + contracts engine | in progress | Migration 0005 (chat_sessions/messages, ai_interactions). Working: sessions + messages APIs; RAG turn (course-scoped chunk retrieval → prompt with numbered sources → `chat` task via gateway); **contracts engine live** (`citation_if_context`, `citations_in_range`, `max_words` — deterministic; repair loop 1 round); citations parsed to chunk/material/quote + grounded flag; every turn audited to `ai_interactions`; **token streaming over WS** (`stream_delta` events; transport via LangChain chat models since 37A/ADR-081 — OpenAI-compatible `reasoning_content` via `CaChatOpenAI`, Anthropic/Google `thinking` blocks; retry + fallback + real `usage_metadata` token accounting, see AI infrastructure row); **math tools** (`CALC` sandboxed numeric eval, `SYMPY` solve/simplify/diff/integrate/expand/factor/limit — tool lines extracted, executed, results fed back, stripped from final answer; max 2 tool rounds); **entity mentions (11A)** — session-stable handle registry (0022), resolved mentions stored per message, advisory `mentions_in_range`; **composer attachments (2026-08-21)** — "+ menu" (materials/notes/quizzes/exercises/courses/upload→*Chat uploads* folder), `attachments` on send → registry + user-message chips, READ covers Q/E; frontend chat sidebar with progressive markdown+KaTeX rendering, animated thinking dots, **per-call tool cards (2026-08-25)** — `tool_call` WS events + persisted `chat_messages.tool_calls` (0035) render every `CALC`/`SYMPY`/`READ`/`STATE`/`PLOT` as a collapsible `ToolCallCard` (name + argument, click to expand args + math result; READ shows `read N chars`, content stays model-only), **new-chat-on-open with deferred session creation (created on first send; the sidebar adopts the session in place and stays a sidepanel — 2026-08-25)**; **node-bound sessions (9D)** — create/list by `node_id`, workspace "Ask about this node" + Tutor tab; **since 2026-08-27 every node-ask opens the sidepanel pinned to the new session** (store-driven; full-page ⤡ collapse carries its session back into the panel, existing-session rows still open `/chat/$chatId`). **Turn trace + tool-call registry + streaming perf (plan 35, 2026-08-25, ADR-077…079)** — every assistant message persists a `trace` doc (0036): run_id, model, latency, input/output tokens, repair count, and a `rounds[]` timeline with per-round start/duration/phase; the WS stream carries `elapsed_ms` on every frame, `phase` frames (thinking/computing/reading/plotting/repairing), and `tool_call` frames with `status`/`start_ms`/`duration_ms`; provider reasoning is captured best-effort into `trace.thinking` (`Gateway.stream_events`; OpenAI `reasoning_content`, Anthropic `thinking_delta`, Google `thought`). Frontend: `useStreamBuffer` batches deltas to animation frames, the live bubble renders plain markdown (`StreamingBubble`, KaTeX deferred to the finalized message), `MessageBubble` is memoized, the 800 ms poll is dropped; `ToolCallCard` dispatches through `features/chat/tools/registry.tsx` (per-tool result views + duration/status chips) and a `TraceTimeline` renders the phase/tool timeline + reasoning disclosure; live `TurnTraceStatus` shows phase + elapsed during streaming. **Live reasoning stream + show/hide (2026-08-25)** — when the provider emits reasoning (`reasoning_content`/`thinking_delta`/`thought`), it streams into a collapsible `ReasoningBubble` (chevron toggle, `ca-chat-reasoning-open` preference) separate from the answer; the captured text also lands in `trace.thinking` for the `TraceTimeline` Reasoning disclosure. **Chat resource tools + shared MCP registry (plan 36, 2026-08-25, ADR-080)** — `mcp_resources.py` is a single `RESOURCE_TOOLS` registry (module-level functions) consumed by both the MCP stdio server and the chat; the chat gained `COURSES`/`NODE_OVERVIEW`/`NODE_QUIZZES`/`NODE_EXERCISES`/`NODE_NOTES` (line grammar, `here`/`T#` resolution, budget 5/turn, `tool_call` events with timing); `GET /ai/tools` lists only chat tools, `GET /ai/mcp` serves the MCP tool list + command to the new Settings → MCP server tab. Pending: skills DB versioning (J5) |
| Quiz engine + quizgen (P4) + score page (basic) | done | Full engine + UI (see changelog 2026-08-19 ×2). Tail completed this round: **MathLive equation input** (shared `MathInput`, React-delegated events); **caq/v1 export/import** (export per quiz; import with dry-run validation preview — same validators as quizgen, imported questions graded identically; provenance `caq/v1`); distractor→misconception tags now land on wrong answers/mistakes; **Scores page** (History: attempts w/ score coloring; Mistake notebook: stem excerpts + error tags). Phase 5b added **practice-mode question help** (see Exercises row). Plan 18 A: runner on shared `FocusShell` (context breadcrumb, details meta, progress dots) + `?from=` origin-return; `GET /quiz/activities/{id}` single-object. **Plan 32 (ADR-069)**: `quiz.generate` accepts `question_types` (allowlist — quizgen blueprint + repair-loop validator enforce it; unknown type → 422) and `shuffle` (questions persisted in randomized order; single/multi options shuffled with answers + misconception tags remapped); `QuizRunner` gains a **per-attempt Shuffle toggle** (localStorage `ca-quiz-shuffle`, default off) that randomizes question order and option display order while mapping submitted choices back to stored indices — grading/analytics untouched. **Plan 51-A (ADR-112)**: `numberline` question type + step input kind answered by clicking/dragging on an interactive number line (`components/answers/NumberlineAnswer`), graded by deterministic region math (`math/regions.py`: tolerance, interval containment, boundary-kind strictness, Dice partial credit); `QuestionOut.input` exposes {widget,min,max} publicly; report rows carry `question_type`+`response` for replay. **Plan 51-F (ADR-123)**: `table_fill` question type — per-cell graded grids (text/numeric/equation checkers per cell, locked display cells, partial credit), public grid spec on `QuestionOut.input`, `TableFillAnswer` in the runner + practice builder. **Plan 51-E (ADR-122)**: `composite` question type — 2–4 typed parts with deterministic follow-through credit (SymPy relations over prior answers, proven at generation), per-part feedback + `follow_through` flag, `CompositeAnswer` in the runner + practice builder. **Plan 51-G (ADR-124)**: `graph_read` question type — server-computed curve in the stem (model authors only expression/domain/target), computed expected reading (value or nearest-point), read-a-value + click-a-point answers, `GraphReadAnswer` + plotly click hook |
| Exercises & tutor (P5/P5b) | done | **Exercise kinds (plan 18 B1–B3/ADR-045)**: `exercises.kind` registry — `multi_step`, `card_*` (flashcards, 0026), structural `matching`/`ordering`/`categorize`/`fill_blank` (deterministic), **AI-rubric `explain`/`error_spot`/`correct_solution`** (deterministic-first, `grade.freeform` skill, rationale feedback, AI-graded badges); kind picker in GenerateDialog; engines chain/exact/struct/fsrs/rubric. Migration 0007 (exercises, exercise_steps, exercise_sessions, step_attempts) + 0008 (quiz_help_events, chat_sessions.context). Exercise CRUD + steps; sessions (socratic toggle); step answers checked via equivalence chain w/ error classification; **hint ladder 1–5 with leak guard G11** (`no_answer_reveal` proves no hint math answer-equivalent; repair loop max 2; level 5 lifts the guard); ladder never skips (server-enforced); every hint audited; independence score at completion; session transcript endpoint. Plan 18 A: player on shared `FocusShell` (context breadcrumb, details meta, step progress) + `?from=` origin-return; `GET /exercises/{id}` single-object. **Phase 5 remainder this round**: `exgen` task + pipeline (LLM exercise generator — validators parse every expected answer via the chain, invalid drafts rejected after repair loop); **similar exercises (D7)** — isomorphic variants with answers proven non-equivalent to source; **error-pattern drills (D8)** seeded with the G10 calculus taxonomy (8 patterns), counts from the mistake notebook; **plan 28 (ADR-063) generalized drills**: `error_patterns` DB table (0031, code-seeded per `course_type` — G10 under `math`), course-scoped pattern resolution + counts (`GET /exercises/drills/patterns?course_id=`), deterministic detectors (`sign_slip`, `dropped_factor` proven by the equivalence chain at grade time — no LLM), `pattern.discover` skill proposing new patterns from recent wrong answers (HITL approve/dismiss → `POST /exercises/drills/patterns`), subject-agnostic drill prompt; DrillsCard shows Seeded/Discovered + *Find more patterns*; **P5b quiz-question help** — practice attempts get the hint ladder per question (levels 1–4 pre-submit, 5 post-submit, no-skip), exam mode refused server-side, help events stored (quiz_help_events) and copied onto answers.help_events, "ask about this question" opens a chat session bound to the attempt running under the chat no-answer wrapper (contract-extended with expected_candidates + forbidden_texts for choice questions) until the question is answered. Bug fixed en route: solveset stage wrongly equated expressions sharing root {0} — now equations-only. Frontend: exercise player, generate/similar/drills UI, quiz runner hint cards + ask button (practice only), shared chat store (sidebar opens on a bound session). **Plan 32 (ADR-069)**: exercise generation is reachable from the unified Practice tab via the `practice`-task builder (one exercise per chosen kind); engines unchanged. **Plan 51-A (ADR-112)**: `numberline` step input kind checked by deterministic region grading (`math/regions.py`). **Plan 51-C (ADR-114)**: drills + generic error_spot are proven error-spotting exercises (equivalence-chain proof of exactly one wrong line; detector-seeded flaws for `sign_slip`/`dropped_factor`); pick + chain-graded correction (`requires_fix`), legacy pick responses still deterministic; patterns endpoint gained `spotted` counts (DrillsCard chip) |
| Notes, handwriting, flashcards (P2/P8) | in progress | Slice 1 done. Migration 0009: notes (blocks body + search_text, owner binding, pinned), note_drawings (strokes kept as source of truth + content-addressed PNG + re-runnable OCR w/ version counter), flashcards, fsrs_states, review_log. Notes API + UI (markdown editor, search incl. OCR'd handwriting via search_text, handwriting canvas **inside the shared MarkdownEditor** — pen-button modal + host-injected `DrawingAdapter` (`create`/`update`/`reocr`/`remove`, 2026-08-22), **rewritten as an infinite canvas (plan 43, ADR-098, 2026-08-28)**: unbounded logical space with wheel-zoom-to-cursor, middle/Space/hand pan, floating zoom bar (−/%,+,Fit,1:1), fullscreen dialog toggle, crop-on-save (bbox + 24 px pad; `view` metadata column 0046 restores exact 100% scale on re-edit), natural-size image rendering, toolbar Σ/diagram insert buttons, `notes_ocr` vision task → markdown (LaTeX for any math), re-transcribe; **plan 46/ADR-102: drawing OCR runs as a background `drawing_ocr` job — saves/re-OCR are instant, a *Transcribing…* placeholder resolves over the `jobs:{id}` WS topic (`useDrawingOcrSync`), failures are retriable jobs, vision payloads are capped (`ocr_image_max_edge`, Settings → Search & OCR) and WebP-re-encoded**); **inline AI helper (plan 31, 2026-08-22): the shared editor's ✨ button → `AiHelperPopover` (transform presets + free-form prompt + Context/Course-material chips, streamed preview, human-gated insert; **movable + resizable floating window** — grip to move, edge/corner handles to resize, always clamped inside the window so action buttons stay visible, 2026-08-22)** — NoteEditor passes course/node context; **drawing delete (2026-08-22)**: ⋯ menu (inline + unreferenced cards) has a confirmed **Delete drawing** → `DELETE /notes/{id}/drawings/{did}` — inline refs dropped from the body, OCR text out of search; **list rows are uniform entity items (2026-08-21): grid/list toggle, kebab + right-click Rename/Delete (deleteNote finally wired into the UI)**; **selection parity with the Materials tab (2026-08-22): rectangular marquee via the shared `MarqueeSurface` (with the Materials tab), no "N selected" banner, bulk Move to node…/Delete in the multi-select context menu**. **Multi-item drag (2026-08-22, plan 30/ADR-067): note rows are draggable — a selected-note drag carries the whole selection, dropping onto a sidebar node moves every dragged note**. **Crash-safe editing (plan 22 A, 2026-08-21): debounced autosave + retry + status chip, localStorage draft mirror + recovery banner, unmount/beforeunload flush, `base_updated_at` 409 stale-write guard w/ reload-or-keep-mine UI. Version history (plan 22 B, 0027): server-side coalesced pre-write snapshots (≥10 min / `force_version`, cap 50), History dialog w/ preview + undoable Restore + Save-version-now.** Flashcards: `flashcards` task generation (basic/cloze/reverse; validators incl. cloze-deletion + duplicate-front rejection vs existing cards; repair loop; audited) from notes / material extractions / mistake notebook; manual cards; **stored as `card_*`-kind exercises since plan 18 B1 (ADR-045, migration 0026 — table dropped, `/flashcards` API unchanged)**; FSRS-4.5 scheduler in pure Python (`app/scheduling/fsrs.py`, desired retention 0.9); due queue + review flow (Again/Hard/Good/Easy → interval, review_log). Frontend notes UI lives in the workspace (NotesTab list + `NoteEditorDrawer` overlay via `?note=` param) with a standalone `/note/{id}` page; command palette note-title search. Slice 2: **Anki .apkg import/export** (hand-rolled `app/pipelines/anki.py` — no anki dependency; round-trip tested; cloze `{{c1::}}` detection; import → `source=anki_import` cards); **C18 handwriting input** on text/numeric/equation quiz answers (write mode → DrawCanvas → `POST /quiz/recognize` via notes_ocr → "interpreted as" candidate chips — OCR proposes, the student confirms; strokes + input_mode stored on the answer; grading only ever sees confirmed LaTeX); **AI note actions** (P9: summarize/cleanup/explain/expand, contract-bound, audited as note_action; **plan 23 D**: AI dropdown + editable result drafts w/ append+close); **chat "latest notes" context slot** (latest 3 notes incl. drawing OCR appended as uncited background context); "Make flashcards" button on notes. **Plan 23 (2026-08-21): lossless body round-trip — blocks store verbatim text, boundary-aware rejoin (legacy-compatible), autosave never rewrites the editor (caret/multilines/undo survive); drawings render once (inline ⋯ menu: edit via PUT strokes+PNG / run OCR / copy; OCR-off clears stale text; canvas footer = OCR toggle + Save drawing); "OCR" vocabulary + extraction-only prompt; undo/redo buttons; editor body scrolls under a pinned toolbar.** Remaining: Tiptap rich editing upgrade (markdown textarea serves meanwhile; the editor itself shipped in 8C) |
| Analytics/diagnostics (P7 first slice) | in progress | Migration 0010: concept_skill_stats, daily_rollups, item_stats, study_goals. `services/metrics.py` = single source of truth (doc 10 definitions): weakness matrix (concepts×skills, sample-size aware — <3 answers flagged not-enough-data), error-pattern profile (totals + 7d trend), speed–accuracy quadrants (fluent/rushing/effortful/struggling vs expected time), item analysis (p-correct, avg-time ratio, distractor selection; n≥20 + p outside [0.1,0.95] auto-flags question `review`), streak/daily-history/XP/level, due-card counts, recommendations engine (review > weak cells [conceptual→read, else drill] > strong-but-stale challenge; each with evidence numbers; exam attempts excluded from mastery). API: /analytics/overview, /diagnostics, /recommendations, /items, /goal (PUT), /materialize (writes rollup tables + question flags). Frontend: **Today screen** (streak, goal ring w/ editable daily goal, due reviews, next-best-action cards with evidence + one-tap actions, 90-day heatmap), **Scores page → 4 tabs** (History, Diagnostics w/ matrix heatmap + error tags + quadrants, Tips, Mistakes). Slice 2: **weak-area sessions (H4)** — quiz generate accepts topic+skill focus (FOCUS TOPIC / SKILL FOCUS directives in the quizgen prompt; topic-scoped retrieval; title carries topic); Today drill/challenge buttons generate a targeted quiz and jump straight in. **Backup/restore (I6)** — `GET /backup/export` = consistent sqlite snapshot (backup API, converted to rollback-journal so archives are portable) + all blobs + manifest (`ca-backup/v1`); `POST /backup/restore` validates zip+manifest+integrity+alembic history, replaces DB (WAL sidecars removed) + blobs, re-runs migrations, reseeds; Settings→Data tab. **Automatic backups (plan 22 C, 2026-08-21)**: BackupScheduler (startup + interval), post-write archive validation, 14+8 daily/weekly retention, optional sync-folder copy, boot integrity check w/ auto-recovery + quarantine, `GET /backup/status` · `PUT /backup/settings` · `POST /backup/create` · `POST /backup/{name}/restore` · `DELETE /backup/{name}`, Automatic-backups card in Settings→Data (ADR-047). **Print export (I16 first cut)** — print CSS (rail/buttons hidden) + Print on quiz rows. Pending: mastery rings/tree visualizations, rollups on quiz-finish |

## Changelog

- 2026-09-03 — **feat(quiz): plan 51-G — graph-reading answers over
  server-computed curves (C5, ADR-124).** New `graph_read` question type: the
  stem embeds a **deterministically computed curve** — the model authors only
  the expression, the plotted domain and the target x; `app/math/graphs.py`
  evaluates it (SymPy → lambdify, 20–400 samples, non-finite refused) and the
  curve rides the stem as a standard plotly `chart` block. **The expected
  answer is computed, never authored**: value mode stores
  `f(point_x)` (evalf, 6 decimals) + tolerance (declared or 2% of the curve's
  y-span); point mode stores the nearest-sample index. Validators require the
  expression to parse and be finite over the whole grid, the target inside the
  domain, and any *declared* value/index (caq imports) to match the recomputed
  computation — mismatch goes to repair. **Two answer forms**: read-a-value
  (numeric with tolerance) and click-a-point (plotly click events → nearest
  data point, exact index match) — `PlotlyChart` grew an optional
  `onPointClick` hook. `QuestionOut.input` = `{widget: graph_read, mode}`;
  responses ride the attempt report; caq export keeps the full answer object
  (re-materializable). Deviation (documented in the plan): image-region
  hotspot/label hotspots on arbitrary diagrams are deferred until an
  image-authoring surface exists — the chart-grounded click-a-point form ships
  instead. **Frontend**: `components/answers/GraphReadAnswer` (numeric reading
  input / clickable chart + selection feedback), runner wiring, practice
  builder gains a **Graph reading** chip; i18n `widgets.graphread.*`/
  `generate.questionType.graph_read`. Tests: `test_graphs.py` (14:
  materialization incl. computed value/index/tolerance, non-finite + domain
  rejection, validation incl. declared-value proof, grading matrix) +
  `test_graph_read.py` (3: generate→chart block→public input→grading flows,
  model-authored value ignored) + frontend `GraphReadAnswer.test.tsx` (3);
  GenerateDialog tests re-based on the 10th chip. Docs: features.md (C5 row),
  math-verification.md (graph-reading section), ai.md (quizgen row).

- 2026-09-03 — **feat(quiz): plan 51-E — composite questions with follow-through
  credit (C16, ADR-122).** New `composite` question type: one multi-part
  problem — 2–4 ordered parts, each with its own input kind
  (text/numeric/equation) and expected answer. **Deterministic follow-through**
  (`app/math/composite.py`): a part may declare a `follow_through` relation (a
  SymPy expression over the prior parts' answers, single-letter symbols
  `a`/`b`/`c` — `p1`-style symbols are unparseable by the house parser, which
  reads them as implicit products). Validators prove at generation time that
  the relation parses, references only prior parts, reproduces the part's
  declared value from the declared prior answers, and still evaluates from a
  perturbed prior answer — failures go to the repair loop. **Grading**: each
  part grades with the flat checkers (text normalized match, numeric
  tolerance, equation chain); when a prior part was answered wrong, later
  parts with relations are re-checked against the relation recomputed from the
  *student's* prior values — a correct derivation from a wrong value earns the
  part with a visible **follow-through** flag (`follow_through` error tag +
  per-part feedback "(a): incorrect, (b): correct (follow-through)"); overall
  correctness still requires every part, partial credit = correct parts /
  total. **API**: `QuestionOut.input` carries the part types only
  (`{widget: composite, parts: [{type}]}`); response = per-part value array,
  stored and replayed via the attempt report; `caq/v1` round-trips the answer
  object. **Frontend**: `components/answers/CompositeAnswer` (lettered parts,
  MathInput in equation parts), QuizRunner wiring (submit gated on ≥1 non-empty
  part), practice builder gains a **Multi-part** chip + info; i18n
  `widgets.composite.*`/`generate.questionType.composite`. Tests:
  `test_composite.py` (14: validation matrix incl. relation reference/
  reproduction/perturbation and text-part exclusion, public input, grading
  matrix incl. follow-through credit and equation relations) +
  `test_composite_api.py` (4: generate→public input→exact/follow-through
  flows, report replay, caq round-trip) + frontend `CompositeAnswer.test.tsx`
  (4) + runner flow test; GenerateDialog tests re-based on the 9th chip. Docs:
  features.md (C16 row), math-verification.md (follow-through section),
  ai.md (quizgen row).

- 2026-09-03 — **feat(quiz): plan 51-F — table / matrix completion (C19,
  ADR-123).** New `table_fill` question type: the stem embeds a grid
  (`headers` + row labels + cells), pre-filled cells are declared `"locked"`
  (their text is public, shown read-only) and every other cell is fillable per
  its declared kind — `text` (normalized match + optional `accept`
  alternatives), `numeric` (per-cell `tolerance`, default 1e-6), `equation`
  (SymPy equivalence chain). **Grading is per-cell deterministic** with partial
  credit = fraction of correct fillable cells (`wrong_cell` error tag; malformed
  payloads score 0); the exact filled grid is stored on the answer and carried
  in the attempt report (`question_type` + `response` from 51-A) for replay.
  **Generation**: quizgen may propose table questions — `validate_table_answer`
  (`app/math/tables.py`) enforces alignment (cells = header count, ≤8×10),
  kind validity, parseable values per kind, ≥1 fillable cell — with the
  standard repair loop; the quiz.generate seed prompt teaches the schema;
  `QuestionOut.input` carries the public grid spec (`headers`, `row_labels`,
  cells as `{kind}`/`{kind, text}` for locked — expected values stay
  server-side); `caq/v1` export/import round-trips the whole answer object.
  **Frontend**: new `components/answers/TableFillAnswer` (header row, locked
  text, inputs per kind — MathInput in equation cells), wired into QuizRunner
  (submit gated on ≥1 filled fillable cell, payload = aligned 2D array) and the
  practice builder's format chips + info popover; i18n
  `widgets.tablefill.*`/`generate.questionType.table_fill`. Tests:
  `test_tables.py` (16: validation matrix, public-input hygiene incl. locked
  text exposure, per-cell grading across kinds/tolerances/accept lists/chain,
  malformed payloads) + `test_table_fill.py` (4: generate→public input→answer
  flows exact/partial/garbage, report replay, caq round-trip) + frontend
  `TableFillAnswer.test.tsx` (5) + runner flow test + GenerateDialog tests
  re-based on the 8th type chip. Docs: features.md (C19 row),
  math-verification.md (per-cell grading section), ai.md (quizgen row).

- 2026-09-02 — **feat(exercises): plan 51-C — error-spotting exercises become
  deterministic-first (C20, ADR-114).** Drills (`POST /exercises/drills`) now
  produce **proven `error_spot` exercises** instead of multi-step drills: the
  generator returns both the flawed and the fully-correct solution with a math
  answer per line, and validators prove via the equivalence chain that exactly
  one line is wrong — flawed ≢ correct at `flaw_index`, every other line
  equivalent, all answers parse — before anything banks (repair loop, then
  rejection). **Detector-seeded flaws**: when the pattern carries a code
  detector, the flawed answer must equal the detector's transformation of the
  correct one — `sign_slip` → `-(correct)`, `dropped_factor` → a seeded
  `<factor>*(correct)` — proven by the chain at generation time; the same
  strict proof applies to generic `error_spot` generation (schema +
  `validate_rubric_payload` grew `lines_correct`/`answers_flawed`/
  `answers_correct`/`correct_line`/`requires_fix`). **Grading is deterministic
  end to end**: the pick is exact; drills force `requires_fix`, so the student
  also types the corrected line's answer, graded by the chain against the true
  line (right pick + missing/wrong fix = incorrect with feedback naming the
  failed half; legacy pick-only and bare-index responses still grade
  deterministically — this also fixes the Player previously sending a bare
  index that fell through to LLM grading). **Spotted tracking**: the drill
  patterns endpoint gained additive `spotted` (correct error_spot step attempts
  per pattern, `Exercise.created_from.pattern` join) and the DrillsCard shows a
  green *spotted* chip beside the existing mistake counts — spotting others'
  mistakes vs your own are now separate signals. Frontend: the lines input
  renders a correction `MathInput` under `requires_fix` and emits
  `{picked, fix}`; submit gating via `rubricResponseComplete`. Contract
  regenerated (`PatternOut.spotted`). Tests: `test_error_spot.py` (5: drill
  build + public-input hygiene, fix grading matrix through the chain, spotted
  counts, unseeded flaw → repair, legacy picks), `test_patterns.py`/
  `test_exgen_api.py` re-based on the error-spot drill draft,
  `test_exercise_structs.py` validator proofs extended; frontend
  `RubricInputs.test.tsx` (4) + Player error-spot test updated. Docs:
  features.md (C20 row), math-verification.md (flaw-proofing section),
  ai.md (exgen row).

- 2026-09-02 — **feat(quiz): plan 51-A — number-line & region answers (C21,
  ADR-112).** The quiz engine gains the `numberline` question type and the
  exercise engine a `numberline` step input kind: the student answers
  inequality/interval/solution-set questions by **clicking and dragging on an
  interactive number line** — place points, shade intervals (per-end
  open/closed toggle, draggable endpoints and whole-bar move, click to remove,
  Points/Interval mode toggle + Clear), and the exact shaded answer replays
  after grading. New `app/math/regions.py` (ADR-112 deterministic grading, no
  LLM): points match nearest-within-tolerance, intervals must match position
  **and boundary kind** (open/closed strictness is the concept), partial credit
  is the Dice coefficient over shaded mass (overlap + exact intervals + matched
  points vs expected+actual mass), default tolerance = 0.5% of the displayed
  range so every snapped click always grades (generators may override).
  Payload `{points:[{value}], intervals:[{lo,hi,lo_closed,hi_closed}]}` stored
  on the answer like any other response shape. **Generation**: quizgen/exgen
  may propose numberline questions/steps — validators enforce the payload
  schema (domain min<max, markers within bounds, interval ordering, ≥1 marker,
  ≤12 points/≤6 intervals, non-negative tolerance) with the standard repair
  loop; `quiz.generate` + `exercise.generate` seed prompts teach the format.
  **API**: `QuestionOut` carries an additive public `input` ({widget, min, max}
  — the expected answer stays hidden); exercise `GET /{id}/steps` returns a
  numberline input widget; step checking grades regions deterministically
  (before the chain-engine branch); attempt **report rows gained additive
  `question_type` + `response`** (replay groundwork for plan 51-G); error tags
  (`boundary_kind`/`missed_region`/`extra_region`/`missed_point`/`extra_point`)
  flow into the mistake notebook; `caq/v1` export/import round-trips numberline
  answers. **Frontend**: new shared `components/answers/NumberlineAnswer`
  (interactive + readonly replay) wired into QuizRunner (payload submit gated
  on ≥1 marker) and the exercise Player (third response shape beside string and
  structural); practice builder gains a **Number line** format chip with info
  popover; i18n under `widgets.numberline.*`/`generate.questionType.numberline`.
  Contract regenerated (`QuestionOut.input`, `ReportAnswerOut` additive fields).
  Tests: `test_regions.py` (21: validation matrix, tolerance defaults, grading
  matrix incl. boundary flips/overlap merges/point matching/malformed payloads)
  + `test_numberline.py` (11: generate→public-input→answer flows
  exact/partial/boundary/garbage, repair round, report replay, caq round-trip +
  dry-run reject, exercise step check + public input); frontend
  `NumberlineAnswer.test.tsx` (6) + QuizRunner numberline flow test;
  GenerateDialog practice tests re-based on the 7th type chip. Docs:
  features.md (C21 done row), math-verification.md (region grading section),
  ai.md (quizgen/exgen contracts).

- 2026-09-02 — **feat(oss): plan 50-D — OSS readiness polish.** `SECURITY.md`
  (supported local-app scope, private reporting paths, AI trust-boundary
  notes); `.github/ISSUE_TEMPLATE` (bug/feature) + PR template checklist
  (verification suite + docs duty); the About page gains **Family links**
  (neuronection.com hub + assistant-ui library) beside the project/creator
  links; README badges were already dynamic (release + pre-release — done in
  the 2026-08-31 audit) and Quick Start already links the local-AI guide.
  **Sample course enriched** (plan 50-D, `POST /onboarding/sample`): three
  deterministic validators-passing quiz questions (single/numeric/truefalse,
  concept-tagged) in a "Sample quiz — Derivatives" activity, **6 flashcards in
  the FSRS queue with staggered due dates — 2 due immediately** so
  Home/Review/Today show honest signals, a "Derivatives" concept with root-node
  coverage, and an **exam_date 14 days out**; `SampleCourseOut` gains additive
  `flashcards`/`quiz_questions` counts; `docs/usage/getting-started.md`
  documents the sample contents. Tests: `test_sample_course_study_content`
  (counts, due split, exam date, concept linkage, FSRS rows). Backend 829 ·
  frontend 829+e2e green.

- 2026-09-02 — **feat(skills): plan 50-B — skill packs (`ca-skills/v1`,
  ADR-110).** Skills travel as JSON: **`POST /skills/export` `{keys}`** returns
  skill definitions + their full system-scope version history (templates,
  params, contracts, active flags — course/course-type overrides never travel;
  prompts only, no secrets by construction); **`POST
  /skills/packs/import?dry_run=true|false`** is staged: the preview parses the
  pack and reports per-skill version count, packed-active version, collision
  (key exists locally), and template-validation errors (the editor's jinja
  checks); commit walks each skill with an explicit collision resolution —
  **replace** (packed versions append as new versions on the existing skill,
  history preserved, packed-active wins activation), **rename** (fresh user
  skill under a `-2`/`-3…` suffixed key), **skip** (default); invalid skills
  skip with reasons, unknown tasks/malformed packs 422. Typed contract
  (`SkillPackOut`/`SkillPackPreviewOut`/`SkillPackCommitOut`, ADR-130). UI:
  Settings → Skills gains a per-row **Export** action (downloads
  `<key>.ca-skills.json`) and **Import pack…** (file picker → preview dialog
  with per-skill resolution selects → commit → result summary);
  `docs/import-export.md` documents the format. Tests:
  `test_skill_packs.py` (4: export shape, preview collision/validation,
  replace/skip/rename, cross-machine round trip). Backend + frontend gates
  green.

- 2026-09-02 — **feat(bundle): plan 50-A — `ca-course/v2` (ADR-109).** The
  course bundle now carries the whole learning state: exporter emits v2 only
  (`manifest.format: "ca-course/v2"` + `options`), importer accepts **v1 +
  v2**. **Added**: `courses.exam_date`; `cards.json` — per-flashcard FSRS
  schedule (state/stability/difficulty/reps/lapses/due) with the review log
  behind `include_history`; `patterns.json` — **discovered** error patterns
  only (system rows re-seed, never travel); `history.json` — quiz attempts +
  answers, exercise sessions + step attempts, quiz help events (all
  `include_history`-gated, default off); `note-versions.json` behind
  `include_note_versions`; v2 quiz questions carry their ids for history
  remapping. Export endpoint takes `?include_history` /
  `?include_note_versions`. **Import self-heals**: every imported material
  with an extraction is enqueued for `postprocess` (embeddings + index card)
  exactly like an upload — imported courses stop degrading to FTS-only
  search; the response carries `postprocess_job_ids` (rides the usual jobs
  WS/rail). Validation covers the new sections (card schedules reference
  known exercises, history references known attempts/questions/sessions,
  note versions reference known notes, patterns need key+name; discovered
  patterns import under the new course's course type, existing keys skip).
  **Round-trip pin**: re-exporting an imported v2 course on a fresh machine
  is byte-identical (manifest `created_at` excepted). Contract regenerated.
  Tests: `test_course_bundle.py` grown to 10 (v2 full-fidelity round trip per
  entity class, default-options omission, v1 downgrade import, deterministic
  re-export); `docs/import-export.md` rewritten for v2.

- 2026-09-02 — **feat(e2e): plan 50-C — Playwright e2e smoke against the real
  backend (ADR-111).** New `frontend/e2e/` harness: `playwright.config.ts`
  (project `e2e`, excluded from vitest + eslint, separate `pnpm e2e` script);
  **global setup builds the SPA, spawns the real backend** (`e2e/run_backend.py`
  → `create_app` + uvicorn on a free port, temp `SA_DATA_DIR`, backend-served
  SPA mount) **and a mock OpenAI-compatible provider** (`e2e/mock_provider.py`
  via the backend venv's uvicorn: `/v1/models`, streaming
  `/v1/chat/completions` with a fixed quiz JSON for the quizgen prompt and a
  `CALC 2+2` tool line for chat, `/v1/embeddings`); the provider is seeded
  **keyless per plan 48-A** (blank key — no SecretService needed in CI) with
  caps corrected at seed time exactly like the plan-56 flow. Four smoke specs,
  each 60 s-capped, workers=1, fresh temp data dir per run: **S1** fresh boot →
  wizard auto-opens → skip → shell renders; **S2** create course → upload a
  markdown fixture through the library create-menu input → extraction lands →
  library search finds it; **S3** quiz generated from the mock via
  `POST /quiz/generate` (validators-passing fixed question) → runner answers
  "B 4" → Correct → Finish → "You scored 100%."; **S4** chat turn streams the
  mock's fixed answer **with a prompt-grammar CALC tool card** (tool executed
  server-side, "Show details for Calculate" renders, trace shows 1 tool).
  Harness hardening: children spawn detached with logs piped to
  `test-results/*.log`, teardown kills the whole process group (plain
  `kill <pid>` misses uv's python child; `/bin/sh` kill has no `--`), state
  (ports/pids) rides `e2e/.state.json` (gitignored). CI: new `e2e` job
  (ubuntu, `playwright install --with-deps chromium`, artifact upload on
  failure) and the same smoke added to the **release gate** after the unit
  suites. Known e2e ordering constraint: the chat spec runs before the
  course specs so its session has no course bound (keeps the citation-contract
  repair path out of the smoke). Frontend gate green incl. e2e 4/4; backend
  untouched.

- 2026-09-01 — **feat(ai): plan 48 — local-first AI engines (A/B/D complete, C
  verified against live Ollama; ADR-105).** **48-A presets:** `PRESETS` gained
  `llama_cpp` (`http://localhost:8080/v1`) and `lm_studio`
  (`http://localhost:1234/v1`) beside Ollama; all three flow through
  `GET /providers/presets` into the wizard/settings preset picker with
  `is_local` auto-set and base URLs prefilled. Blank-key pin: provider create
  with `api_key: null/""` writes nothing to the keyring (unit + API tests), and
  the gateway resolves such providers to the `_KEYLESS_API_KEY` ("EMPTY")
  OpenAI client — pinned by a `build_chat_model` test. (The plan's
  Test-connection row item had already landed with plan 56-B2.) **48-B
  detection:** `GET /providers/detect-local` (`LocalEngineHitOut`, ADR-130-typed)
  probes Ollama `:11434`, llama.cpp `:8080` **and `:8081`**, LM Studio `:1234` —
  a hit requires an OpenAI-shaped `{data:[…]}` 200 within httpx
  `Timeout(1.5, connect=0.3)`; localhost-only, read-only, result never
  persisted; **base URLs already configured as providers are skipped** (plan
  revision: no duplicate wizard offers; two-stage timeout revision: fast connect
  probe + longer read for large catalogs). Wizard Provider step auto-probes once
  per open (shared `LocalEngines` component: probe button, per-hit name + model
  count + one-click Add through `createProvider {is_local: true}`) and the
  Settings → Providers empty state carries the same detector; the Defaults step
  shows a local-only hint when every provider `is_local`. OpenAPI artifacts
  regenerated (`LocalEngineHitOut` born in the schema). **48-C verification
  (live, Ollama on this machine):** `detect-local` found the running engine
  (41 models) and correctly returned `[]` after the provider existed; provider
  created with a blank key discovered 41 models over real HTTP; a chat turn
  streamed end-to-end through the gateway (`qwen3.5:2b` → "LOCAL OK", reasoning
  split into trace.thinking); vision `image_url` OCR verified on the raw surface
  (`qwen3-vl:4b` read `2x + 3 = 11` from a rendered PNG); embeddings verified
  end-to-end (`nomic-embed-text-v2-moe` 768-dim → cap corrected via the plan-56
  registry PATCH — the name heuristic guesses `text` for `embed-text` ids,
  exactly the correction flow — → embeddings default assigned → postprocess
  chunk vectors → hybrid search hits). **Fix en route (the C-slice catch):**
  `GatewayEmbedder` had bypassed the `ai_interactions` ledger (raw httpx after
  `resolve()` since plan 37) — embeddings calls now go through the new
  `LLMGateway.record_usage` ledger path (token-estimated, latency-timed), and
  the embedder defaults its transport to the gateway's; regression test asserts
  the ledger row. llama.cpp/LM Studio/audio matrix rows await the user's
  engines (ports closed here). **48-D docs:** `docs/usage/local-ai.md` (engine
  setup, wizard path, verified model matrix, capability-guess guide,
  limitations), README "Runs fully local" bullet, `docs/ai.md` local-first
  intro + Provider row. Tests: `test_local_engines.py` (12: presets, shape
  validation, error/garbage/refused probes, port fallback, configured-skip,
  API contract, blank-key no-keyring + keyless model) + `LocalEngines.test.tsx`
  (4) + wizard detection test. Backend 819 · frontend 827 green.

- 2026-09-01 — **test(chat): load-immune poll deadlines in chat-turn tests.** The
  one-off `test_regenerate_adds_assistant_variant` flake was a deadline blow under
  the saturated `pytest -n auto` run (single-test `--durations` shows the test call
  itself at ~0.4s; product logic — per-session turn lock, atomic finalize commit,
  wake-after-commit, `busy_timeout=30000` — verified race-free), not a product race:
  `test_chat_branches.py` poll helpers now use 30s deadlines (`wait_for_assistant`
  was 5s, the tightest in the suite) and `wait_until`'s timeout error dumps the last
  polled messages instead of a bare "condition never met"; `test_chat_turn_error.py`
  deadline bumped to match. sa-dev skill §4 gained the poll-deadline rule. Backend
  807 tests green.

- 2026-09-01 — **test(scripts): version_manager tests realigned with the
  family-unified config-driven API.** The 4 tests still monkeypatching the removed
  `VERSION_FILE`/`ROOT`-era `set_version`/`current_version` interface now drive the
  b608eb4 surface: `set` runs through `main()` against a tmp repo with its own
  `version_manager.toml` (patched `ROOT`/`CONFIG_PATH`), invalid versions assert
  `SystemExit` + untouched file, `show` compares against `read_version(load_config())`,
  and the release test calls `git_release(cfg, …)` on a tmp git repo (dirty version
  file committed, tagged `v0.1.2`, clean tree). Backend 807 tests green.

- 2026-09-01 — **feat(ui): workspace navigation/action separation + guided
  course onboarding.** The NodeWorkspace tab strip is now **underline tabs** on a
  full-width border (active tab = primary underline) instead of pill buttons — tabs
  and the per-tab action bar can no longer be mistaken for each other
  (`NodeWorkspace.tsx`). `TabActionBar` secondaries are **ghost** buttons (primary
  stays filled; menu triggers match) so the action row reads as a quiet toolbar;
  unit tests updated for the variant change. A **brand-new course root** (no
  children, materials or folders) replaces the Overview action bar with a
  three-step **getting-started card** (`CourseOnboardingCard`): ① Add study
  materials (deep-links to the Materials tab), ② Shape the structure (Generate AI
  outline / Add node), ③ Start studying (opens the study launcher / asks the tutor)
  — new `workspace.onboard*` i18n keys. Empty **Materials/Notes/Tutor** tabs use the
  library `EmptyState` primitive with descriptions and CTAs (Materials keeps its
  upload dropzone as the action; Notes gains *Create your first note*; filtered-empty
  notes now say "Nothing matches this filter"; Tutor gains *Start a chat*). Frontend
  822 tests green (3 new: onboarding render, add-materials navigation, outline
  draft).

- 2026-09-01 — **feat(settings): plan 56-B2 — provider/model generation settings +
  live-tested UI polish (`@neuronection/assistant-ui` 0.13.1).** Backend:
  migration **0050** — `providers.is_local`/`providers.country` (optional
  metadata) and `models.temperature`/`models.max_tokens` (nullable generation
  settings); `ResolvedModel` carries them and all three gateway builders
  (OpenAI/Anthropic/Google) honor them; provider create/patch + model
  create/patch accept the new fields (`model_fields_set`-based clearing —
  temperature/max_tokens/reasoning_effort can be unset); OpenAPI artifacts
  regenerated. Frontend: Models tab modal honors the new fields (reasoning
  dropdown + Custom…, clearable temperature/max-tokens number fields with
  far-right spinners); Providers create/edit gain the **Hosting Local/Cloud
  toggle** and **Country select** (library `ProviderForm` flag-gated optional
  fields) with a local badge / country flag on provider cards. Tasks tab:
  capability-defaults titles beautified (`beautifyId`, new `./fuzzy` subpath),
  **Primary/Fallback badges with click-only info popups**, fallback stacked
  above primary each with its own clear button, per-task budget UI removed
  (limit feature shelved — backend columns/endpoints dormant, re-enable = UI
  only). Combobox: `hideLabel`, modal-popover panel (wheel-scrollable inside
  dialogs) + typo-tolerant ranked search (`gemni`→Gemini). Dev workflow:
  library `dev-link` for live testing (vitest requires the tarball flow — dual
  React), `resolve.dedupe` added to study's Vite config. Gates: frontend 819
  tests ✓ build ✓; backend ruff/mypy ✓ (803 passed; the 4
  `test_version_manager` failures pre-date this work — stale tests vs the
  family-unified version manager, tracked in Open issues).

- 2026-09-01 — **feat(settings): plan 56-B — AI-settings surfaces rebuilt on the
  family library (`@neuronection/assistant-ui` 0.10.x), ADR-131/132.** The
  Settings → Models tab is now a thin composition over the library's new
  `ModelRegistry` module (health-design-language: icon-tile provider cards with
  enabled/total pill, capability chips with icons + `data-as-cap` theming hooks);
  the remote catalog (search, capability filters incl. *Unclassified*, Add-all,
  manual add) is collapsed behind an **Add model** trigger, and every catalog row
  shows the app-guessed capabilities with an inline **draft panel** (label, cap
  chips, reasoning effort) shared by add and edit — `AddModelDialog` +
  `EditModelDialog` (~544 ln) are deleted in the same commit; only enabled models
  list, disabled ones re-enter via the catalog's add path. Providers tab rides the
  library `ConnectionTestRow` (inline variant: Connected/Failed + model count);
  provider create/edit dialogs adopt library `ProviderForm` (`hideBaseUrl` for
  fixed-endpoint types, write-only key field); Tasks tab adopts `TaskAssignmentPicker`
  v2 — capability-defaults section with per-capability **fallback** pickers,
  `requires`-filtered catalogs, require badges + inherit notes + consequence
  nudges + spend/budget via `renderMeta`. New ui shims: model-registry,
  capability-chips, connection-test-row, task-assignment-picker, provider-form,
  model-picker. Library-side commits: `model-registry` module,
  `capability-chips`, task-assignment v2, provider-form/options, CI-canonical
  gallery baselines (`visual-rebaseline` workflow) + date-picker month-rollover
  test fix. Frontend 819 tests green (settings suite re-based; scroll-pagination
  test retired with the old dialog); backend untouched. Known issue opened:
  `backend/tests/test_version_manager.py` (4) stale against the family-unified
  version-manager refactor (fails on clean main — pre-existing, not slice B).
- 2026-09-01 — **Docker web-service tier added (family-standard layout).** Study can now
  run as a self-hosted web service in Docker, mirroring health/career-assistant's `docker/`
  taxonomy: `docker/Dockerfile` (multi-stage: pnpm frontend bundle → uv-managed backend image
  serving API + SPA from one uvicorn process; web mode skips pywebview/PyGObject/pycairo and
  their GTK deps via `uv sync --no-install-package`), `docker/entrypoint.sh` (migrations +
  uvicorn web mode), `docker-compose.standalone.yml` (backend + nginx; **SQLite by design** —
  all state in the `SA_DATA_DIR=/data` volume, single-replica), `nginx.conf`/`nginx-TLS.conf`
  (incl. the `/ws` WebSocket endpoint, SSE-friendly, certbot ACME + HSTS TLS variant),
  `docker/README.md`, and a root `.dockerignore`. Ops scripts `scripts/run-docker.sh`
  (first deploy) and `scripts/update-docker.sh` (git pull + rebuild + health-wait) with the
  shared `scripts/lib-docker.sh` helpers, family-adapted from health-assistant. Release
  workflow gains a `docker` job publishing `ghcr.io/<owner>/<repo>` semver images
  (`STUDY_IMAGE=` override on the compose stacks). Verified: image build, container boot
  (`/api/v1/health` 200, SPA served, DB ok), full standalone stack through nginx (health +
  SPA + WS upgrade 101), nginx -t on both confs.
- 2026-09-01 — **`pnpm dev` moves to the family-uniform `scripts/run-dev.sh` under honcho.**
  The dev entrypoint joins career/health-assistant's uniform interface: `./scripts/run-dev.sh`
  with `--force` / `--force-stop` / `--no-bootstrap` / `--help` (old flags `--reset [--yes] [--all]`
  unchanged, still kills port holders first). Process management switches from
  `trap 'kill 0'` + `wait` to honcho + `Procfile.dev` (same as the sibling assistants): colored
  per-process log prefixes and crash propagation — one dead process stops the group loud instead
  of a half-dead dev environment. `scripts/dev.sh` stays as a thin deprecated alias, so `pnpm dev`
  and muscle memory keep working. honcho added to the backend dev group (`uv add --group dev
  honcho`); ports still `SA_PORT`/8000 + `VITE_PORT`/5173. Shared helpers (port kill, venv/node
  bootstrap, colors, help) come from the family lib `scripts/lib/dev-common.sh` (canonical in
  career-assistant, synced via its `scripts/sync-dev-lib.sh`). Desktop (`pnpm app`) and built-SPA
  (`pnpm webapp`) modes untouched.
- 2026-08-31 — **feat(ingest): plan 47-D — lecture audio/video become
  searchable transcript materials (B13, ADR-104).** Ingest branch for kinds
  `audio`/`video`: stage `transcribe` calls `LLMGateway.transcribe`
  (provider-fallback + ledger + budgeting reused), the `transcribe.audio`
  skill supplies the instruction, and the transcript is wrapped in a metadata
  header (source filename, mutagen duration, model) before the standard
  extraction path — provenance `{source: transcribed, model}`. **No ffmpeg**:
  containers pass through as-is; Google's inline STT now rejects video mimes
  with an explicit "does not accept video" message → failed job with the
  reason visible (the plan's `video_not_supported_by_provider`); OpenAI-
  compatible endpoints accept the documented video containers. **`mutagen`
  is required** (migration 0049: `materials.duration_sec`/`bitrate_kbps`,
  read at upload) and drives the **pre-flight size warning**: uploads above
  the 25 MB transcription cap succeed but return
  `warnings: [{code: transcribe_size_exceeded, limit_mb, file_mb}]` — the
  frontend upload controller collects them and the dropzone renders
  "likely exceeds the transcription size limit (25 MB) — use a local whisper
  server or split the file" before the provider ever sees the bytes.
  Reingest re-transcribes into a new extraction version; `REINGESTABLE_KINDS`
  and linked-source `DEFAULT_GLOBS` include the AV suffixes. Contract grew
  `UploadWarningOut` + `warnings` on `MaterialUploadOut`. Tests:
  `test_av_ingest.py` (5: transcript→search, reingest versions, provider
  rejection → failed job, size warning, zero-byte 422) + dropzone warning
  render. Backend 807 · frontend 820 green.

- 2026-08-31 — **feat(ingest): plan 47-C — docx, pptx, epub and html materials
  are first-class (B10, ADR-103).** Ingest gains a branch per kind producing
  markdown through the converter core, then riding the standard
  extraction → chunk → FTS → embed → postprocess path with
  `provenance {source: converted, converter: …}`: **docx** via mammoth
  (headings/tables/links; embedded images stored as `material_images` +
  `ca-image://{id}` refs), **pptx** via python-pptx (`## Slide N — <title>`
  sections, text frames as bullets, speaker notes as `> ` quotes, slide
  pictures extracted), **epub** via ebooklib (spine order, `# <chapter>`
  sections), **html** directly (data-URI images stored and referenced,
  external URLs untouched). New `ImageStore` collects image rows during
  conversion and enqueues `image_ocr` jobs inside the ingest transaction so
  transcripts arrive async; image OCR text joins FTS via `embedded_ocr_text`.
  Extractions lift `ca-image://` refs into `image_ref` blocks (`md_to_blocks`
  now understands both drawing and image refs); `MaterialDetailOut` carries
  `images[]` (generated contract grew `MaterialImageOut`) and the reading
  view resolves refs to blobs through a new `resolveImage` prop. Reingest
  covers the four kinds; `DEFAULT_GLOBS` for linked sources now includes
  them; derive copies image rows + remaps refs (mirroring drawings).
  mypy overrides for stub-less `mammoth`/`ebooklib`. Committed micro-fixtures
  (handcrafted OOXML docx, python-pptx deck, ebooklib book, html) + 5
  per-kind ingest tests. Backend 802 · frontend 819 green.

- 2026-08-31 — **feat(ingest): plan 47-B — HTML→markdown converter core +
  `material_images` home (ADR-103).** New `app/pipelines/convert/` package:
  `html_to_markdown` (html2text with house config — headings, links, images,
  pipe tables, no width wrapping; script/style dropped; whitespace
  normalized). Math honesty: `<math>` (MathML) blocks become a `[math-block]`
  placeholder token — no pure-Python converter handles MathML, the extraction
  QA editor is the correction surface (same policy as OCR). **Migration 0048
  `material_images`** (model `MaterialImage`): extracted embedded images of
  converted materials — document position, content-addressed blob, async OCR
  state (`ocr_version`/`ocr_markdown`/`ocr_job_id`, the plan-46 pattern).
  New `image_ocr` job type (payload TypedDict, handler registered at boot):
  transcribes from the stored blob via the vision task, clears the pointer,
  and refreshes material FTS — drawing OCR *and* image OCR text now both join
  FTS/AI extra context via `embedded_ocr_text` at every sync site (ingest,
  extraction edit, drawing OCR, service). Purge cascades images with the
  material. Migration-head assertions bumped; `docs/data-model.md` updated.
  Tests: converter fidelity fixtures (`tests/fixtures/convert/`) +
  purge-cascade + live `image_ocr` handler round-trip. Backend 797 green;
  frontend untouched.

- 2026-08-31 — **feat(ingest): plan 47-A — upload honesty + converter
  architecture (ADR-103, ADR-103/104 recorded).** The `doc` fallback is gone:
  `detect_kind` now knows `KIND_BY_SUFFIX` (pdf/image/md/txt),
  `CONVERTIBLE_SUFFIXES` (.docx/.pptx/.epub/.html/.htm → kinds docx/pptx/epub/
  html) and `AV_SUFFIXES` (.mp3/.m4a/.wav/.ogg/.opus/.mpga → audio;
  .webm/.mp4/.mpeg → video); unknown suffixes raise `UnsupportedMaterialError`
  and the upload endpoint maps it to **422
  `{reason: "unsupported_type", suffix, accepted}` — validated before the blob
  is stored**, so nothing is written. New `GET /materials/accepted` publishes
  the accepted list (`{suffixes, accept}`); the frontend file pickers
  (dropzone, create menu, upload button) take their `accept` attribute from a
  shared `useAcceptedTypes` query, and the upload error row renders the
  reason i18n-keyed (`library.uploadUnsupportedType`) via `ApiError.detail` +
  `unsupportedTypeDetail`. **Linked sources skip instead of failing**:
  `SourcesService.scan` returns a `ScanReport` (stats + per-file `skipped`
  reasons surfaced in `POST /sources/{id}/scan`), unsupported files are
  counted and skipped before any material/blob is created, and browse-ingest
  of an unsupported file gets the same 422. New kinds land in the generated
  contract (`MaterialKind` union grows; `AcceptedTypesOut`, `ScanResult.skipped`).
  `.doc`/.rtf/.pages stay unsupported on purpose — the 422 names them.
  Tests: `test_upload_honesty.py` (6: kind matrix, accepted suffixes, 422
  writes-nothing, accepted endpoint, scan skips + ingest 422, docx accepted).
  Backend 790 · frontend 817 green.

- 2026-08-31 — **feat(ui): plan 55-E — assistant-ui adoption round 2; plan 55
  COMPLETE.** The BlockRenderer's inline code copy button (the one verified
  local duplicate) is replaced by the library's `CopyButton` via new shim
  `ui/copy-button.tsx` (i18n label prop, `data-copied` copied-state marker;
  the copy test asserts the marker instead of a title swap). Big-surface
  sweep: inline `Loader2 animate-spin` spinners → library `Spinner` (shim
  `ui/spinner.tsx`) in JobsPage (2) and ExtractionView (3), and ad-hoc empty
  `<p>` blocks → library `EmptyState` (shim `ui/empty-state.tsx`) in JobsPage,
  LibraryPage (2), PracticeTab, ScoresPage (2) — behavior-preserving, i18n
  texts unchanged. **Drift-audit regressions fixed** (the family
  `audit-usage.mjs` flagged app files shadowing library component names):
  `AiBadge.tsx` → `AiGeneratedBadge.tsx`, `Breadcrumbs.tsx` →
  `LibraryBreadcrumbs.tsx`, `UploadDropzone.tsx` → `MaterialUploadDropzone.tsx`
  (renames only — all three are app-glue, not library copies; import sites +
  tests updated); audit now **clean over 335 files**. The library
  `ErrorBanner`/`UndoNotice` were already adopted — the app wrappers in
  `components/` keep direct library imports per the audit's shadow rule (a
  file named like a library component must import the library or be the
  shim), so no unused `ui/error-banner`/`ui/undo-notice` shims were added.
  Frontend 815 green; backend untouched (784 green).

- 2026-08-31 — **feat(api): plan 55-C stragglers — the last untyped JSON
  endpoints now declare response models; plan 55-C endpoint typing is
  COMPLETE** (ADR-130). Config/working-dir (`WorkingDirOut`,
  `ValidateWorkingDirOut`, `SetWorkingDirOut`, `ResetWorkingDirOut`), trash
  (`list[DeletedItemOut]`, `RestoreDeletedOut`), exercises
  (`SummaryNoteOut`, `ExerciseDeletedOut`), folders (`FolderDeleteInfoOut`
  +node-link/breadcrumb models — the delete-info breadcrumb is the 2-field
  `{id,title}` shape, matching `material_links`), notes (`NoteTagCountOut`,
  `NoteDeletedOut`), jobs (`RetryFailedOut`, `DeleteFailedOut`), onboarding
  (`OnboardingStateOut`, `SampleCourseOut`), skills (`ResolutionOut`,
  `TestRunOut` +`ConstraintOut`; `context-vars` stays an honest
  `dict[str, dict[str, str]]`), materials (`list[MaterialLinkInfoOut]`),
  presets likewise stays `dict[str, dict[str, str]]`. Intentionally
  model-free remainder: binary/file downloads only (root, blobs, desktop
  file, backup/course/quiz exports, anki deck). Both flagged in the survey
  as typed-but-anonymous dicts now have real named models in the schema.
  **Final survey: 0 untyped 200/201-JSON endpoints** — every JSON response
  in the API validates against a documented model. Backend 784 · frontend
  815 green; contract drift guard clean.

- 2026-08-31 — **feat(api): plan 55-C ai/chat/sources — twelve more endpoints
  declare typed response models** (ADR-130). AI: `EditorCancelOut`,
  `ToolsOut` (+`ToolInfoOut`/`ToolArgumentOut` — the chat tool catalog and MCP
  resource tools now schema-documented), `McpInfoOut` (+`McpToolOut`); the
  presets endpoint already carried `dict[str, dict[str, str]]`. Chat:
  `SessionDeletedOut`, `MessageStateOut`, `SessionContextOut`
  (+`MentionRefOut`/`ContextNodeOut`/`NotePreviewOut` — the mention-registry
  handle shape), `BranchTreeOut` (serializes `BranchNodeOut` directly),
  `StopOut`. Sources: `SourceBrowseOut` (+`SourceSubdirOut`/
  `SourceMaterialOut` with `MaterialKind`/`MaterialStatus` enums,
  `UningestedFileOut`), `IngestFileOut`, `ScanAllOut`. Survey: ai 4 → 1
  (presets dict-of-dicts remains, typed as a free-form dict), chat 5 → 0,
  sources 3 → 0; remaining untyped 200/201-JSON = 41. Backend 784 · frontend
  815 green; contract drift guard clean.

- 2026-08-31 — **feat(api): plan 55-C backup — six JSON backup endpoints declare
  typed response models** (ADR-130). New inline models in `backup.py`:
  `BackupStatusOut` (+`BackupSettingsInfoOut`, `BackupEntryOut`,
  `BackupRecoveryInfoOut` — mirrors the `last-recovery.json` shape, `quarantined`
  now always present, `null` when absent — additive) shared by `/status`,
  `/create`, `DELETE /{name}`; `BackupSettingsOut` for `PUT /settings`;
  `RestoreOut` for both restore paths. `/export` (zip download) stays
  model-free. Survey: backup 7 → 1 (binary); remaining untyped 200/201-JSON =
  45. Backend 784 · frontend 815 green; contract drift guard clean.

- 2026-08-31 — **feat(api): plan 55-C analytics — all eight analytics endpoints
  declare typed response models** (ADR-130). New inline models in
  `analytics.py`: `OverviewOut` (+`DayActivityOut`), `ExamStatusOut`
  (+`MostBehindNodeOut`), `DiagnosticsOut` (+`WeaknessCellOut`,
  `ErrorTagStatOut`, `SpeedAccuracyCellOut`), `list[RecommendationOut]`,
  `list[ItemStatOut]`, `GoalOut`, `MaterializeOut`, `CostsOut`
  (+`CostTaskOut`). Four new StrEnums in `core/vocab.py` —
  `RecommendationKind`, `SpeedLabel`, `SpeedQuadrant`, `ItemFlag` — swept into
  `metrics.py` (recommendation kinds, speed/quadrant labels, item flag
  computation + materialize's question-flag write; StrEnum dict equality keeps
  every existing assertion valid). Survey: analytics 8 → 0; remaining untyped
  200/201-JSON = 51. Backend 784 · frontend 815 green; contract drift guard
  clean.

- 2026-08-31 — **feat(api): plan 55-C quiz — the nine JSON quiz endpoints
  declare typed response models** (ADR-130). New inline models in `quiz.py`:
  `AttemptListItemOut` (`mode` typed as the `AttemptMode` enum → real union in
  the schema), `MistakeListItemOut`, `CaqImportOut` (+`QuestionCheckOut`;
  `activity` now always present, `null` on dry-run — additive) shared by
  `/import`, `/import-qpkg` and `/inbox/{filename}/import`, `QuizDeletedOut`,
  `QuizHelpEntryOut`, `AttemptReportOut` (+`ReportAnswerOut`),
  `InboxPathOut`. The two file-download exports (`.caq.json` attachment,
  `.qpkg` octet-stream) intentionally stay model-free. Survey: quiz 11 → 2
  (both binary); remaining untyped 200/201-JSON = 59. Backend 784 · frontend
  815 green; contract drift guard clean.

- 2026-08-31 — **feat(api): plan 55-C courses remainder — every JSON endpoint in
  the courses tag now declares a typed response model** (ADR-130). New models in
  `courses_schemas.py`: the workspace payload (`NodeWorkspaceOut` with
  node/breadcrumb/children/folders/materials/notes/counts/concepts — `kind`/
  `status`/`read_status` generate real enum unions), `CourseMaterialsEntryOut`
  (+`ViaFolderOut`), `CourseDeletedOut`, `CourseImportOut` (+`BundlePreviewOut`/
  `ImportedCourseOut`), `OutlineDraftOut`/`OutlineCommitOut`,
  `ConceptDraftOut`/`ConceptsCommitOut`/`ConceptGraphOut` (`from`/`to` via
  serialization/validation aliases), `NodeReviewOut` (+`ReviewFindingOut`),
  `DraftNoteOut`, `NodeArtifactsOut` (+`ArtifactRefOut`; the optional
  `artifact` key is now always present, `null` when unfiltered — additive).
  `PUT /materials/{id}/study-state` now returns the full `StudyStateOut`
  (adds `last_opened_at`, matching `/study-states`). Vocabulary: three new
  StrEnums in `core/vocab.py` — `ConceptRelation`, `ReviewFindingKind`,
  `StudyStatus` — swept into the concepts/organizer/structure/tree write paths
  (relation/kind validation, study-state status, workspace `read_status`
  fallback). Schema 179 → 216 components. Survey refined (old count treated
  204s/binary as untyped): remaining untyped 200/201-JSON endpoints = **61** —
  quiz 11, analytics 8, backup 7, chat 5, ai 4, config 4, skills 3, sources 3,
  exercises 2, jobs 2, notes 2, onboarding 2, trash 2, flashcards/folders/
  materials 1 each; binary responses (root, blobs, desktop file,
  course export) intentionally stay model-free. Backend 783 · frontend 815
  green; contract drift guard clean.

- 2026-08-31 — **feat(api): plan 55-C tranches 3+4 — node CRUD/move/delete/
  restore, folder assignment, study-states, node-concept linking and material
  assignment all declare typed response models** (`NodeDetailOut`,
  `NodeUpdatedOut`, `NodeMovedOut`, `NodeDeletedOut`, `NodeRestoredOut`,
  `FolderAssignedOut`, `StudyStateOut` — progress is float, as the roundtrip
  test proved — `NodeConceptLinkedOut`, `MaterialAssignedOut` in
  `courses_schemas.py`; schema 170 → 179 components). Courses-tag untyped
  endpoints: 32 → 21 (survey recorded; next: quiz 11, analytics 8, backup 7).
  Backend 782 · frontend 815 green; contract drift guard clean.

- 2026-08-31 — **feat(api): plan 55-C tranche 2 — the course tree responses are
  typed (ADR-130).** New `app/api/courses_schemas.py` (`TreeNodeOut` recursive,
  `TreeNodeCounts`, `TreeNodeMaterialLink`, `TreeNodeFolderLink`,
  `NodeCreatedOut`); `GET /courses/{id}/tree` and `POST /courses/{id}/nodes`
  declare `response_model` — FastAPI now validates + documents the shapes (202
  → 170 schemas) and the generated TS contract carries them. Survey added: 32
  courses-tag endpoints remain untyped (the rest of tranche 2+), quiz 11,
  analytics 8. Backend 782 · frontend 815 green; contract drift guard clean.

- 2026-08-31 — **refactor(jobs): plan 55-C tranche 1 — job payloads are typed
  (ADR-130).** New `app/jobs/payloads.py`: `IngestPayload`/`PostprocessPayload`/
  `ChatTurnPayload`/`DrawingOcrPayload` TypedDicts (`Required` keys for mandatory
  fields) documenting the four job payload schemas. `JobRunner.enqueue` is now
  typed against their union — an enqueue with the wrong payload shape for its job
  type is a mypy error at every call site (the drawing-OCR f-string key build
  became a typed conditional in `enqueue_drawing_ocr`), and the
  ingest/postprocess/drawing_ocr handlers read `cast(<Payload>, job.payload or {})`
  so payload access is checked while the Job column legitimately stays
  schema-less JSON. Remaining C tranches (courses/tree, quiz/exercises,
  chat/context, metrics/bundle) add pydantic response models + typed service
  returns per domain. Backend 782 · frontend 815 green.

- 2026-08-31 — **refactor(ui): plan 55-D — WS topics and localStorage keys are
  single-sourced.** New `lib/constants.ts`: `WsTopic` builders mirroring the
  backend's `core/vocab.py` factories (jobs/chat/source/note/material — every
  publish/subscribe site now goes through them; the ChatPanel session topic
  coerces its id explicitly) and `storageKeys` (the 12 real `ca-*` localStorage
  keys — profile/course/onboarding/quiz-shuffle/chat prefs/view toggles/sidebar
  state) replacing every literal. The `ca-material://`/`ca-drawing://` link
  schemes and the SVG gradient id are intentionally untouched (wire formats and
  SVG ids, not storage). New `constants.test.ts` pins the topic strings against
  the backend's values and the `ca-` prefix/uniqueness invariant. Frontend 815
  tests green.

- 2026-08-31 — **feat(types): plan 55-B — the frontend contract is now
  generated from OpenAPI, with drift guards in CI (ADR-129).**
  `scripts/export-openapi.py` boots `create_app` against a throwaway data dir
  (no lifespan/DB) and writes **`frontend/openapi.json`** (202 paths, 165
  schemas, committed); **`openapi-typescript`** (devDep) generates the committed
  **`frontend/src/lib/api-schema.d.ts`**; `pnpm api:types` chains both. **CI
  guards both halves**: the backend job re-exports the schema and
  `git diff --exit-code` on it; the frontend job regenerates the `d.ts` from the
  committed snapshot and diffs it — a backend contract change now fails CI at
  the exact generated diff instead of at runtime. Enum synergy from 55-A:
  `JobOut.status → JobStatus`, `MaterialOut.kind/status → MaterialKind/
  MaterialStatus` generate **real TS unions** in the schema (`"queued" |
  "running" | "failed" | "done" | "cancelled"`). First migrated consumers:
  `lib/api/jobs.ts` (JobInfo/JobsSummary/JobTypeInfo → `components['schemas']`)
  and `lib/api/system.ts` (Health → HealthResponse); new endpoints' types are
  born generated from here on. Workflow pin extended
  (`test_ci_workflow_guards_openapi_and_generated_types_drift`).
  Backend 782 · frontend 813 green; drift guard verified clean locally.

- 2026-08-31 — **refactor(vocab): plan 55-A — closed vocabularies become
  StrEnums; string matching swept off the core surfaces (ADR-128).** New
  `app/core/vocab.py`: JobStatus (incl. `cancelled`), JobType, MaterialKind
  (+`doc`), MaterialStatus, AttemptMode, ComposeKind, Capability, ProvenanceKind,
  a `parse()` classmethod whose ValueError names the allowed set (feeds 422s),
  and `WsTopic` factories (`jobs/chat/source/note/material`) replacing scattered
  f-strings at every publish site (runner, chat API + group key, scan scheduler,
  flashcards). Swept to enums: the jobs stack (runner, cancellation, pruning,
  jobs API, editor-AI job mirror), material kind + status paths (materials
  service, ingest, sources), attempt modes (quiz API, models default, metrics
  exclusion), provenance markers (`ai-composed`/`derived`), capability requires
  tuple. Rules recorded: DB stays strings (StrEnum binds as its value; `.value`
  for dict lookups over DB-string keys — Enum hashes by name); open registries
  (exercise kinds, compose KINDS, TASK_DEFS) keep typed registries. 5 new
  `test_vocab.py` units. Backend 781 · frontend 813 green.

- 2026-08-31 — **refactor: plan 54 COMPLETE — the three structural seams split
  with zero behavior change (ADR-127).** **54-E flake hygiene:** the test
  `client` fixture now points `spa_dist` at a missing dir so the whole backend
  suite is **SPA-mount-independent** (fresh worktrees no longer need
  `pnpm build`; unmatched-path 404/405 semantics deterministic); chat-branch and
  chat-turn-error wait deadlines 5→15 s (the CPU-starvation class from the
  release gate); the folder-cascade test waits for the job queue to drain before
  deleting (plus 54-A's cancel-on-purge closes its postprocess race). **54-B:**
  `lib/api.ts` (3,584 lines) → **`lib/api/` package of 15 domain modules**
  (client/materials/folders/sources/courses/chat/ai/quiz/exercises/notes/
  flashcards/analytics/jobs/settings/system) — `@/lib/api` resolves to the
  package index, all 65+ import sites untouched, exported surface exactly the
  original 380 symbols (`json`/`expectOk`/`audioFilename` stay client-internal);
  new endpoints land in their domain module from now on. **54-C:**
  `domain/models.py` (976 lines) → **`models/` package**
  (core/content/study/chat/ops) whose `__init__` re-exports every public name
  with explicit `as` aliases (mypy-strict-safe); SQLAlchemy string FKs and
  relationships resolve registry-wide, alembic untouched. **54-D:** the 28 flat
  service modules → **content/study/knowledge/platform groups** (`search` stays
  top-level), one-shot import rewrite across app + tests. Enforcement: test-count
  invariance (813/776 unchanged through every split), mypy strict + ruff clean at
  each commit. 5× full backend soak green. Retires the LazyNoteEditor /
  folder-cascade / chat-turn flake watch items and the frontend/dist suite
  dependency from Open issues.

- 2026-08-31 — **feat(jobs): plan 54-A — delete-during-ingest is now a clean
  `cancelled`, not a confusing failure (ADR-126, user-approved round in progress).**
  Deleting a material/folder/course while its background job was queued or running
  used to leave a failed job ("material x not found") or a running job committing
  into a purged entity. New `app/jobs/cancellation.py`: a terminal **`cancelled`
  job status** (no migration — string column), a process-level cancel-flag
  registry, and `cancel_jobs_for(session, material_ids/chat_session_ids/note_ids)`
  which marks matching **queued** jobs cancelled directly and sets **cancel flags**
  on running ones (the just-claimed race is covered by the flag check at
  `_run_handler` start). Every progress `report()` call is now a **cooperative
  cancellation checkpoint** (raises `JobCancelled` when flagged) — no handler code
  needed for the common case — and `JobRunner._run_handler` gained a
  `JobCancelled` branch that marks the row cancelled instead of failed (retry
  refused, excluded from the failure badge and retry-failed). **Commit-time stale
  re-checks** (`ensure_target_exists` — expire_all + existence probe in the same
  transaction) close the delete-between-last-stage-and-commit hole in `ingest`
  (before the final ready-commit), `postprocess` (before the index-card write) and
  `drawing_ocr` (after the long vision call); ingest's `fail()` no longer marks a
  material `failed` when the failure is a cancellation. Wiring:
  `purge_material` cancels the material's jobs, course purge cancels its chat-turn
  and note-drawing jobs, note delete cancels its drawing jobs. API: `/jobs`
  accepts `status=cancelled`, summary gained `cancelled`. Frontend: JobsPage
  **Cancelled** tab + muted chip + delete button on cancelled rows,
  ActivityPopover shows cancelled rows (muted chip) among recent items and the
  failure badge ignores them, and the library upload banner treats `cancelled` as
  terminal (no more stuck 0% banner). Tests: `test_job_cancellation.py` (7:
  purge-cancels-queued, running-flag→cancelled, flag-before-start never runs the
  handler, API summary/retry/delete contract, `ensure_target_exists`, payload
  matching for notes/chats). Backend 776 · frontend 813, full gate green.

- 2026-08-31 — **docs(planning): plan 55 — code quality & typed contracts
  (user-requested best-practices round; runs after 54, before features).**
  Audit with hard numbers: only **2 StrEnum classes** in the backend vs **573
  `dict[str, Any]`** occurrences and bare-literal vocabularies everywhere (job
  statuses, kinds, modes, WS topics as scattered f-strings); the frontend
  hand-maintains **145 interfaces** mirroring the backend; three verified local
  duplicates of assistant-ui modules (`ErrorBanner.tsx`, `UndoDeleteNotice.tsx`,
  `BlockRenderer`'s inline copy button vs library `error-banner`/`undo-notice`/
  `copy-button`). **Restructure verdict: none beyond 54** — the remaining issues
  are typing/vocabulary discipline, not structure. Slices: **A** StrEnum
  vocabularies in `app/core/vocab.py` for every closed set (JobStatus incl.
  `cancelled`, MaterialKind, QuestionType, ComposeKind, AttemptMode, Capability,
  TaskName, WSTopic factories; open registries like exercise kinds keep typed
  registries — ADR-128); **B** OpenAPI-generated frontend types
  (`openapi-typescript`, committed `api-schema.d.ts`, CI drift guard, schema
  exported by a pytest fixture; new endpoints born generated — ADR-129); **C**
  typed service/API boundaries per domain (response models on every endpoint,
  TypedDicts for stable-shape JSON columns; ADR-130); **D** shared constants per
  side (WS topic builders, storage keys); **E** library adoption round 2
  (verified dupes → shims; inline spinner/empty-state sweep; 47–53 surfaces use
  library `Wizard`/`DatePicker`/`ChipList`/`Table` first). User decisions:
  clean-code interpretation, **no-comments rule stays**, TS **generated from
  OpenAPI**. Tracked-code changes: none.

- 2026-08-31 — **docs(planning): plan 54 (consolidation & hardening) + plan-51
  widening + self-review revisions across 47–53.** Follow-up verification answered
  "is anything still missing?" honestly: **plan 54** (user-approved, **runs before
  the feature rounds**) — A: the deferred delete-during-ingest fix (ADR-126: new
  terminal `cancelled` job status, cancel-on-purge for queued jobs, cooperative
  cancel flags at handler stage boundaries, commit-time stale re-check in the same
  transaction); B/C/D: zero-behavior mechanical splits of the three verified
  pressure seams — `lib/api.ts` (3,584 lines → `lib/api/` package behind a
  re-export shim), `domain/models.py` (976 lines → `domain/models/` package,
  alembic-safe), `services/` (31 flat files → content/study/knowledge/platform
  groups, one-shot import updates) with a test-count invariance check (ADR-127);
  E: the four named flakes fixed by waiting on observables (never retry/sleep) +
  removing the folders-tests' hidden `frontend/dist` dependency, ten-run soak.
  **Plan 51 widened** (user-approved) with slices E–H: C16 composite questions with
  deterministic follow-through credit (SymPy recomputes later parts from the
  student's earlier value, ADR-122), C19 per-cell-graded table completion (ADR-123),
  C4/C5 hotspot/labeling + graph-reading over server-computed chart data (ADR-124),
  C11 item-level Elo adaptive difficulty (ADR-125) — all verified missing
  (`QUESTION_TYPES` today = single/multi/truefalse/text/numeric/equation).
  **Same-day revisions** patched into 47–53: plan 47 — linked-source scans
  skip-with-reason instead of failed-job piles, a real `material_images` +
  `image_ocr` home for embedded doc images, `mutagen` required with a pre-flight
  provider-limit warning (25 MB-class caps without ffmpeg); plan 48 — provider
  Test-connection row (library `ConnectionTestRow`), detect-local validates
  OpenAI-shaped responses on collision-prone ports; plan 49 — study-session
  fragmentation guard (resume sessions ended ≤2 min, no confetti rows); plan 50 —
  e2e mock provider uses a blank API key (legal per 48-A) so CI needs no secret
  service; plan 52 — promote-to-course drops concept coverage honestly, scratch
  analytics scoping (streaks yes, forecasting/recommendations no); plan 53 —
  quiz-me `accept` variants (synonyms deterministic, paraphrase-judging never),
  speechSynthesis feature-detect for WebKitGTK, WebKitGTK print verification +
  webapp-mode fallback. Tracked-code changes: none.

- 2026-08-31 — **docs(planning): plans 52–53 close the "ultimate assistant" gaps
  (exploration + planner/expression).** Follow-up to the gap audit: **52 — topic
  explorer & course genesis**: the app was closed-world (every course starts with
  an upload; notes course-bound per ADR-040/036) — a per-profile **Scratchpad**
  system course + Promote-to-course subtree move becomes the sanctioned ADR-040
  exception (0050 `courses.origin`/`hidden`); `course.genesis` drafts a 2-level
  outline from a topic (reuse of the outline task + draft→commit flow) and a
  budget-gated job chain scaffolds `lesson` compose kinds + seeded
  quizzes/flashcards, everything AI-provenance-tagged; SEARCH/FETCH chat research
  tools over a generic Tavily-style/SearXNG search-provider setting (keyring key)
  with optional web grounding of the outline (ADR-116/117). **53 — planner &
  expression**: `plan_items` (0051) + deterministic plan drafting from exam_date ×
  coverage (no scheduler engine), mastery-weighted exam-readiness forecast in
  `exam_status` (evidence lines, not-enough-data gate), **Quiz-me** chat mode
  where the model asks via a QUIZ tool but the *server* grades through the
  equivalence chain — the model never sees the expected answer (ADR-121), teach-back
  flow reusing the rubric `explain` path onto `concept_skill_stats`, TTS read-aloud
  (`speech` capability + `tts` task, ephemeral audio, speechSynthesis fallback,
  ADR-119), and a print/PDF engine of print-HTML templates (quiz paper/key,
  flashcard cut-out sheets, materials, planner week) over the browser's
  print-to-PDF — no weasyprint/Typst bundling (ADR-118…120). Roadmap backlog and
  `dev/plans/README.md` updated. Tracked-code changes: none.

- 2026-08-31 — **docs(planning): post-1.0 gap audit → five approved rounds (plans
  47–51) + `ca-plan` skill renamed `sa-plan`.** A full docs/codebase audit
  (backend + frontend + family alignment vs neuronection.com / assistant-ui) fed
  five slice-level plans in `dev/plans/` (local-only, gitignored): **47**
  ingestion breadth — DOCX/PPTX/EPUB/HTML converters (B10 vision promise, today
  uploads as kind `doc` then fails ingest with `unsupported material kind`) +
  lecture audio/video → transcript materials via the existing `transcribe` task
  (B13), unsupported uploads 422 at the door (ADR-103/104); **48** local-first AI
  engines — llama.cpp/LM Studio presets, `GET /providers/detect-local` probing,
  embeddings via OpenAI-compatible local servers, and **ADR-105 superseding
  ADR-011's sentence-transformers clause: no in-process ML models, ever** (local =
  OpenAI-compatible engines the user runs; no torch in the bundle); **49** study
  experience — cross-course Review queue (`features/flashcards/` dissolves into
  `features/review/`, one queue two scopes), `study_sessions` + focus timer
  (minutes-or-answers goals, activity-based streaks), server-enforced exam timing
  (ADR-106…108); **50** sharing/OSS — `ca-course/v2` (flashcards+FSRS, exam_date,
  error patterns, import enqueues postprocess so imported courses stop degrading
  to FTS-only), skill packs (J7), Playwright e2e smoke vs a mock OpenAI-compatible
  provider gating releases, README/About/sample-course polish (ADR-109…111);
  **51** AI-native answer types — C21 number-line answers, G7 graph-sketch grading
  (keypoint-based v1, freehand out), C20 error-spotting (detector-seeded flaws,
  equivalence-chain proof of wrongness for LLM-proposed ones), C14 code execution
  in Pyodide — server-side execution: none, ever (ADR-112…115). Roadmap
  `dev/plans/05-roadmap.md` post-1.0 backlog rewritten around the rounds;
  `docs/STATUS.md` (this file) stays the tracked source of truth. Repo hygiene
  en route: `.opencode/skills/ca-plan` → `sa-plan` (the AGENTS.md `sa-plan`
  reference now resolves), its content updated (plans 01–46, current
  conventions), `dev/plans/README.md` document table gained rows 43–51 and lost
  its stale CourseAssistant title, README badges now track GitHub releases
  (were hardcoded v0.1.0 / "in development"). Tracked-code changes: none (no
  product code touched this round).

- 2026-08-30 — **feat(library): drop uploads directly (user feedback)** — the
  drag-drop menu (files-vs-folder choice) is gone: dropping now uploads
  immediately with structure auto-detected per item (paths preserved → tree
  recreated; loose files → current location — `uploadFiles` already mapped
  both). The now-unused `useFileDropMenu` hook is deleted; the overlay drops
  straight into the mounted page's controller. Backend untouched · frontend
  812 tests green (user-verified in the desktop shell).

- 2026-08-30 — **fix(desktop): OS file/folder drags now work in the WebKitGTK
  shell (user-reported; root cause proven experimentally)** — verified with a
  forged XDND session on this machine (X11, WebKitGTK 2.52): WebKitGTK
  delivers `dragenter/dragover/drop` but **never puts `Files` in
  `dataTransfer.types`** — external drops arrive as `text/uri-list`+`text/html`
  strings with `files`/`items` empty (browsers wrap drops in File objects),
  so every `'Files' in types` check silently ignored OS drags. Fix: the
  desktop path parses `file://` URIs from `text/uri-list`
  (`parseFileUris`), registers them server-side via a new **desktop-gated
  `POST /desktop/drops`** (`DesktopFileAccess.register_paths` — dropped
  folders are registered as roots and walked with the rooted-rel grammar,
  single files are allow-listed explicitly; non-existent paths skipped), and
  the bytes stream through the existing `/desktop/file` endpoint into the
  normal upload pipeline. `resolveDropItems` (dropFiles.ts) picks the browser
  `File` path first and falls back to the URI flow when `window.pywebview`
  exists; `isFileDrag` now also accepts `text/uri-list`; `hasFolder` means
  "has directory segments" so single-file drops don't offer the folder option.
  Backend 769 · frontend 815 tests green (user-verified in the desktop shell).

- 2026-08-30 — **feat(library): window-wide file/folder drag overlay
  (user-requested)** — dragging files/folders anywhere over the app window now
  shows a full-window "Drop to upload" overlay naming the target; drop opens
  the same files-vs-folder menu as before and uploads through the mounted
  page's `useMaterialUpload` controller (folder trees recreated, workspace
  drops keep node auto-allocation). New `lib/window-drop-store.ts` (module
  store + `useWindowDropRegistration(active, label, getUpload)` — pages
  register while mounted, `getUpload` kept fresh via ref so folder context is
  never stale) and `components/layout/WindowDropOverlay.tsx` (window-level
  dragenter/leave counter, Files-only dragover preventDefault so internal
  node/material drags are untouched, menu reuse from `useFileDropMenu`);
  mounted in AppShell; registered by LibraryPage (course label) and the
  workspace Materials tab (node label) — the pane-level file-drop menus there
  were superseded and removed. On screens without a registered target (e.g.
  Settings, non-materials workspace tabs) no overlay appears.
  Backend 767 · frontend 809 tests green.

- 2026-08-30 — **fix(library): upload progress banner was dead — stuck at 0%
  until page remount (user-reported in the desktop folder-upload flow)** — the
  WS-subscription effect read the upload job id from a ref with `[queryClient]`
  deps, so it evaluated once at mount (ref still null → never subscribed) and
  no job event ever reached the banner; it cleared only on navigation
  (state reset). `uploadJobId` is now state: every job (per uploaded file,
  including the desktop folder flow) (re)subscribes `jobs:{id}`, a stale
  1.5 s hide-timer can no longer clear a newer job's banner, unmount cleans
  the timer, and the pointless reingest-ref writes are gone.
  Regression test drives the banner 0→40→100% over the mocked WS and asserts
  auto-clear. Backend 767 · frontend 804 tests green.

- 2026-08-30 — **test: suite headroom under load** — two contention flakes
  surfaced while running both suites in parallel (release gate): the chat
  turn-error test raced the by-design event-before-status ordering
  (`turn_error` emits before the runner commits `failed` — it now polls the job
  row with `expire_all`, like a real WS+polling consumer), and lazy-tiptap
  tests exceeded testing-library's 1s default under CPU starvation (vitest
  `testTimeout`/`hookTimeout` → 15s, `asyncUtilTimeout` → 5s setup-wide).
  Backend 767 · frontend 803 green under concurrent full-suite load.

- 2026-08-30 — **fix(desktop): folder upload works in the packaged Linux app** —
  WebKitGTK has no directory-picker support for `<input webkitdirectory>` (its
  file-chooser API exposes only filter/mime-types/select-multiple — no directory
  flag), so *Upload folder…* was web-only: the GTK dialog opened in files-only
  mode. The desktop shell now passes a pywebview **JS bridge**
  (`app/shell.py` `DesktopBridge.pick_folder` → `webview.FileDialog.FOLDER` →
  native GTK SELECT_FOLDER dialog) and a **desktop-gated API**
  (`app/api/desktop.py`): `GET /desktop/folder?path=` lists files (rel paths
  rooted at the picked folder name, size, mtime) and `GET /desktop/file?path=`
  streams bytes — both only for **session-picked roots** tracked by
  `DesktopFileAccess` on `app.state.desktop_files`, set **only by the app
  shell** (web/mcp mode → 404; `..`/symlink escapes outside a picked root are
  contained, non-followed symlink dirs aren't descended). Frontend
  `components/materials/desktopFolder.ts`: when `window.pywebview` exists, the
  three folder-upload affordances (`UploadDropzone`, `UploadButton`,
  `createMaterialMenu`) pick via the bridge and stream files sequentially into
  the existing `useMaterialUpload` pipeline (same folder-mapping, junk-filter,
  naming semantics; `relativePath` = `<folder>/<…>` like `webkitRelativePath`);
  browsers keep the native input untouched.
  `MaterialUploadController.reportError` (new) surfaces pick/list/stream
  failures in the existing error row. Backend 767 · frontend 803 tests green.

- 2026-08-29 — **brand assets canonicalized in `assets/` (org convention)** —
  `assets/icon.svg` (the real 512 px app tile) is now the single source of
  truth: `packaging/build-linux.sh` installs it into .deb/AppImage icon paths
  (replacing the old 128 px "ƒ" placeholder `packaging/icon.svg`, which is
  deleted — packaged releases get the actual logo), `frontend/public/icon.svg`
  (served favicon) is a derived copy refreshed via `scripts/sync-brand.sh`,
  README points at the canonical path, and `tests/test_packaging_assets.py`
  guards the new location. Hub `public/logos/` snapshots now sync from the
  canonical path too.
- 2026-08-29 — **plan 46 (OCR payload efficiency + async drawing OCR, ADR-102)
  COMPLETE (user-requested)** — **every image sent to a vision task is now
  preprocessed at the OCR engine boundary** (`app/ocr/imaging.py`): LANCZOS
  long-edge cap (profile preference `ocr_image_max_edge` — Off / 1024 /
  **1568 default** / 2048 px) + flattened-RGB **WebP q85** re-encode (JPEG
  fallback), applied uniformly to drawing OCR, quiz-answer recognition, uploaded
  images and rasterized PDF pages; stored blobs keep full quality, decode errors
  pass the original through, and a payload is never grown (re-encode only when a
  resize happened or the WebP output is actually smaller). Setting lives in
  **Settings → Search & OCR** (Search tab renamed; partial-PUT preferences).
  **Drawing OCR is a background job**: `POST/PUT /notes|materials/{id}/drawings`
  and `…/reocr` store the drawing, enqueue `drawing_ocr` (new job type; handler
  `pipelines/drawing_ocr.py` transcribes from the stored blob, bumps
  `ocr_version`, refreshes note search text / material FTS, clears the pointer)
  and **return immediately** — no blocking on the vision model, no 502s;
  failures are retriable activity-rail jobs instead (TaskUnassigned/ProviderError
  → JobError). Migration **0047** adds `ocr_job_id` to both drawing tables;
  serializers emit it only while its job is queued/running (crash-safe pending
  state) and re-OCR returns **409** while a job is live. Frontend: drawings show
  a *Transcribing…* placeholder (DrawingBlock + unreferenced card), and the new
  `useDrawingOcrSync` hook subscribes to `jobs:{id}` WS topics and invalidates
  the host queries on done/failed (wired into NoteEditor + ExtractionView).
  Deps: +`pillow>=11`. Backend 761 · frontend 844 tests green.

- 2026-08-29 — **fix(packaging): deb white-screen root cause is the bundled
  builder-era GUI stack, not the render mode — deb now bundles ONLY the Python
  world.** Decisive user experiment on the laptop: with the disable-vars forced
  externally the GPU process *still* aborted, and (new this round) **dev mode on
  the same machine renders fine** — so the machine and its system WebKitGTK are
  healthy and the frozen bundle is the variable. The deb's denylist strip
  (glib core only) left jammy `libepoxy`/`libX11`/`libxcb`/`libcairo`/`libgtk-3`/
  `gdk-pixbuf`+loaders/dconf/gvfs modules shadowing the system stack via
  PyInstaller's `LD_LIBRARY_PATH`, breaking WebKit's EGL bootstrap even under
  `LIBGL_ALWAYS_SOFTWARE` (verified: rc.11 still white in software mode). The deb
  stage now strips by **keep-list**: only `libpython3*`, `libmupdf*`,
  `libssl/crypto/sqlite/ffi/zlib-family/expat/gcc_s/readline/tinfo/ncursesw`
  survive; every other root `lib*.so*` is deleted and `gio_modules/` removed, so
  the frozen app resolves GTK/WebKit/GLib/X11 entirely from the system (the same
  all-system stack dev mode uses). Verified locally: stage contains zero GUI
  libs, `_gi`/`_cairo` resolve every GUI dep to `/lib`, staged app launches and
  serves the SPA. Depends unchanged (gtk/webkit/glib/girepository guarantee the
  system side). AppImage untouched (self-contained by design).

- 2026-08-29 — **fix(shell): the laptop experiment proved `WEBKIT_DISABLE_*` are
  no-ops on its webkit — the software rung now uses `LIBGL_ALWAYS_SOFTWARE`
  (Mesa llvmpipe software GL) instead.** User's forced-env test on the broken
  machine: both disable vars set externally → GPU process STILL aborted
  (`EGL_BAD_PARAMETER`) and the page never loaded; the rc.10 ladder then worked
  exactly as built — software relaunch (dead again) → browser mode rendered
  fully, beacon `POST /shell/rendered` 204 confirming a painted frame. Since a
  2.4x GPU process needs *working EGL* (which llvmpipe provides without
  hardware), the software rung sets `LIBGL_ALWAYS_SOFTWARE=1` alongside the
  disable-vars (kept for 2.3x/2.40 honor them; no-ops elsewhere). Ladder is now
  GPU → software-GL → browser. Unit tests updated (23 in the shell suite).

- 2026-08-29 — **fix(shell): rc.9 still white on the broken-EGL laptop — the
  sentinel disarmed in software mode, but software rendering was never proven on
  a broken stack.** The laptop's log (zero HTTP requests, no relaunch) fits the
  sequence: probe fails → disable-vars set → webview white anyway (some 2.4x
  stacks still spawn the aborting GPU process) → sentinel disarmed by the
  `software_active` condition → stuck white. The sentinel is now armed in every
  desktop mode and drives a bounded fallback ladder: GPU → software (one
  relaunch, `SA_WEBKIT_SOFT_FALLBACK`) → **browser mode** (`web` — system
  browser, always renders; `SA_WEBKIT_BROWSER_FALLBACK`), two relaunches max,
  then no loops (browser mode has no sentinel). Startup now logs
  `webkit_render_mode` (gpu/software/forced-gpu) so the chosen path is visible
  in user logs. `_relaunch_argv` gained a mode parameter that replaces any
  existing mode word but keeps flags; `_plan_fallback` is unit-tested for both
  steps.

- 2026-08-29 — **fix(shell): rc.8 still white-screened on the broken-EGL laptop —
  the sentinel's "SPA served = renderer alive" signal was wrong.** The rc.8 probe
  passed on that machine (plain `eglGetDisplay`/`eglInitialize` succeeds via
  glvnd while WebKitGTK's DMABUF/GBM GPU process still aborts — the
  probe-blind-spot class), and the page can *load and run JS* while the
  compositor is dead, so request-based liveness never triggered the fallback.
  The signal is now a **painted-frame beacon**: the SPA fires a
  double-`requestAnimationFrame` `POST /api/v1/shell/rendered` after its first
  rendered frame (rAF never fires when the compositor is dead, so white windows
  can't fake liveness); the sentinel (10 s) relaunches once in software mode if
  no beacon arrives. New endpoint in `api/health.py`, `RenderBeacon` in the SPA
  root, per-load once-guard; backend 748 · frontend 837 tests green (endpoint
  state test, beacon timing/once tests, sentinel matrix updated).

- 2026-08-29 — **feat(shell): WebKitGTK render path is now chosen at runtime —
  GPU/DMABUF by default, software only where EGL is actually broken**
  (replaces rc.7's unconditional software default, which the user rejected for
  drawing performance + battery). `apply_webkit_compat_env` first runs a ~50 ms
  ctypes EGL probe (`eglGetDisplay`/`eglInitialize` on `libEGL.so.1`): healthy →
  leave GPU compositing on; failing (the user's laptop:
  `Could not create default EGL display: EGL_BAD_PARAMETER`) → set
  `WEBKIT_DISABLE_DMABUF_RENDERER/COMPOSITING_MODE=1` before the window opens
  (since WebKitGTK ≥ 2.42 DMABUF is the only accelerated path, disabling it is
  software, so it must not be the default where GPU works). A launch sentinel
  covers the probe-blind spot: in GPU mode a middleware marks the first request
  the embedded server receives; if none arrives within 8 s the renderer died
  white and the app `os.execv`-relaunches itself once in software mode
  (`SA_WEBKIT_SOFT_FALLBACK=1` marker, cancel event on normal window close — no
  loops, no false fires on quick close). `SA_WEBKIT_GPU=1` = expert force-GPU
  (skips probe and sentinel). Verified live on Mint 22.3: probe passes → GPU
  mode renders (SPA serving); marker-forced software mode renders; 11 new unit
  tests cover the decision matrix, relaunch argv (frozen/dev) and sentinel
  paths.

- 2026-08-29 — **fix(shell): white window on WebKitGTK systems whose EGL/DMABUF
  renderer aborts (`Could not create default EGL display: EGL_BAD_PARAMETER`,
  seen on the user's Mint 22 laptop with the rc.6 `.deb`).** WebKitGTK's GPU
  compositing path dies on some driver stacks and the webview stays blank — no
  Python-side error. The desktop shell now sets
  `WEBKIT_DISABLE_DMABUF_RENDERER=1` + `WEBKIT_DISABLE_COMPOSITING_MODE=1`
  (software rasterizer, the Tauri/wry-style safe default) before pywebview
  starts, with `SA_WEBKIT_GPU=1` as the opt-back-in escape hatch. Covers dev
  and frozen desktop mode on all platforms (vars are WebKitGTK-only, inert
  elsewhere); `web` browser mode unaffected. New
  `test_webkit_compat_env.py`; launch-verified locally (15 s survival, SPA
  serving). This closes the rc.6 install-test finding.

- 2026-08-29 — **fix(packaging): `.deb` crashed at launch on Mint 22 —
  `libgudev-1.0.so.0: undefined symbol: g_once_init_enter_pointer` →
  WebKitGTK dlopen failed → pywebview GTK import died.** PyInstaller collects
  the builder's whole GTK stack into the onedir tree; the jammy-built deb
  therefore shipped **glib 2.72** bundled, which shadows the target's system
  glib (bootloader prepends `_internal` to `LD_LIBRARY_PATH`) — while system
  WebKitGTK pulls in system libgudev built against glib ≥ 2.80, whose symbols
  the shadowing glib lacks. (The earlier noble-built debs only appeared healthy
  because builder glib 2.80 ≈ Mint 22's system glib.) Fix: the deb stage now
  **strips the GLib core** (`libglib-2.0`, `libgobject-2.0`, `libgio-2.0`,
  `libgmodule-2.0`, `libgirepository-1.0`) so the system copies always win,
  with `Depends` extended to `libglib2.0-0, libgirepository-1.0-1`; the
  AppImage keeps its bundle (self-contained and internally consistent).
  Verified end to end on Mint 22.3: stripped stage survives a 15 s desktop
  launch (window + SPA serving) with glib resolving to `/lib`. CI gap closed:
  the release `linux` job now also runs a **desktop-launch smoke under xvfb**
  (30 s survival on the stripped deb stage, `WEBKIT_DISABLE_COMPOSITING_MODE=1`)
  — the old `web`-mode smoke never exercised the pywebview import path.
  `test_packaging_assets` pins the strip step, the Depends names and the xvfb
  smoke so this cannot silently regress.

- 2026-08-28 — **fix(storage): `database is locked` killed backup restore under
  concurrent DB access (CI test-job failure).** Three compounding issues: backup
  archives are deliberately rollback-journal (`DELETE`) DBs for portability, so
  after a restore the next new connection must **convert** the file to WAL,
  which needs a brief exclusive lock; `_set_pragmas` ran `PRAGMA
  journal_mode=WAL` **before** setting `busy_timeout`, so the conversion raced
  any concurrent lock-holder (the 5 s jobs-runner poller, whose live connection
  `engine.dispose()` cannot revoke) with timeout 0 and failed instantly; and
  `_apply_restore` wrote the restored file with `write_bytes`
  (truncate-in-place), so a poller reading mid-overwrite saw a half-written DB
  (`no such table: jobs`). Fixes: pragmas reordered with `busy_timeout=30000`
  first, plus a bounded retry loop (10 × 0.25 s) around the WAL conversion —
  verified empirically that `PRAGMA journal_mode=WAL` raises BUSY immediately
  without honoring the busy handler; restore now writes `app.db.restore-tmp`
  and swaps it in with `os.replace` (atomic). New `tests/test_storage_db.py`
  pins all three behaviors (conversion succeeds against a write-locked
  DELETE-mode DB, give-up path, fresh-connection pragma set). Backend 736
  green.

- 2026-08-28 — **fix(ci): `ci.yml` backend job still installed
  `libgirepository-2.0-dev`, so `uv sync` died building pygobject**
  (`Dependency 'gobject-introspection-1.0' is required but not found`) — the
  same failure 55c4379 fixed in `release.yml`, but in the CI workflow, which
  the fix round missed. `libgirepository-2.0-dev` provides the **new**
  `girepository-2.0` API; pygobject 3.50 (pinned `<3.51` for jammy) builds
  against the old `gobject-introspection-1.0` pkg-config, provided by
  `libgirepository1.0-dev` (exists on jammy and noble; verified on
  packages.ubuntu.com). The pin moved pygobject 3.56.3 → 3.50.2 in the lock,
  which invalidated setup-uv's built-wheel cache and exposed the latent wrong
  dep on the `ubuntu-latest` (noble) runner. ci.yml now installs
  `libgirepository1.0-dev` and uses `uv sync --frozen` like release.yml; new
  `test_ci_workflow_installs_girepository_1_0_dev` pins the dep set so CI and
  release workflows can't drift apart again.

- 2026-08-28 — **fix(packaging): Linux `.deb`/`.AppImage` failed on clean Mint 21.x
  machines with `libm.so.6: version 'GLIBC_2.38' not found (required by …
  libpython3.12.so.1.0)`.** The release `linux` job built on `ubuntu-24.04`, where
  uv's interpreter discovery (`setup-uv` `python-version: "3.12"`) picked the
  **distro Python 3.12** — Ubuntu 24.04's `libpython3.12.so.1.0` references
  `__isoc23_*` and `fmod` at `GLIBC_2.38` (verified with `objdump -T`; the `fmod`
  one is the libm error above), and PyInstaller bundles that libpython verbatim, so
  every artifact inherited a glibc ≥ 2.38 floor (Mint 21.x = glibc 2.35 → crash at
  launch; user's own Mint 22.3 = 2.39 → worked, which masked it). Fix: build on
  **`ubuntu-22.04`** (glibc 2.35 floor, build-old/run-new) with the **deadsnakes
  distro Python 3.12**, pinned fail-closed via job env `UV_PYTHON=3.12`,
  `UV_PYTHON_DOWNLOADS=never`, `UV_PYTHON_PREFERENCE=only-system` (without
  `UV_PYTHON` uv settles on `/usr/bin/python3` 3.10 and `uv sync` dies on
  `requires-python`); apt line moved to jammy names (`libgtk-3-0`,
  `libgirepository1.0-dev` — also in the `test` job, replacing
  `libgirepository-2.0-dev`) and `uv sync --frozen`. **PyGObject pinned
  `>=3.50,<3.51`** in `backend/pyproject.toml` (+ `uv lock`, only pygobject moves
  3.56.3 → 3.50.2): 3.51.0 switched to girepository-2.0 and requires glib ≥ 2.80,
  which jammy (glib 2.72) can't provide. Verified in an `ubuntu:22.04` container
  reproducing the job end to end: `uv sync --frozen` + PyInstaller on deadsnakes
  3.12.13, pygobject 3.50.2 against GI 1.72, **every bundled ELF ≤ GLIBC_2.35**
  (and uv's managed python-build-standalone libpython measured at 2.17, so pbs was
  never the offender), `/api/v1/health` smoke test green on glibc 2.35. Deb target
  becomes Debian 12 / Ubuntu 22.04+ / Mint 21+ (docs table updated); local Linux
  builds now need `libgirepository1.0-dev` (`docs/usage/packaging.md` prerequisites).
  `test_release_workflow_covers_tag_and_artifacts` now asserts the runner, the
  deadsnakes pin and the uv env guards so the floor can't silently drift back up;
  if GitHub ever retires the `ubuntu-22.04` image, use `container: ubuntu:22.04`,
  not a newer runner (documented in packaging.md known gaps).

- 2026-08-28 — **feat(config): working directory setting — view + change the app
  data location from Settings and the setup wizard (plan 45, ADR-101).** The data
  directory (`app.db`, `blobs/`, `backups/`, `cache/`) was env-only (`SA_DATA_DIR`);
  it is now a first-class, UI-managed setting that applies on restart. Backend: new
  `core/working_dir.py` pointer file stored in the platform config dir
  (`~/.config/StudyAssistant/working-dir.txt` on Linux; `SA_CONFIG_DIR` overrides for
  tests/packaging) — read by the `Settings.data_dir` factory so resolution is env/
  `.env` (strongest) → pointer → platform default; new `api/config.py` with
  `GET /config/working-dir` (`{path, default_path, custom, restart_pending}`),
  `POST /config/working-dir/validate` (target policy: absolute + writable + **empty
  or existing SA data dir** (`app.db` present); machine-readable reason codes cover
  relative paths, current-dir overlap both ways, junk non-empty dirs, unwritable
  targets; not-yet-existing paths are validated against their nearest existing
  ancestor so creatable deep paths work), `PUT` (validated write of the pointer —
  takes effect on next start), `DELETE` (restore default). Frontend: shared
  `WorkingDirEditor` — path input, **Check** with per-reason feedback (i18n keys for
  every code), **Use after restart** gated on a validated changed path, **Use
  default**, **Restore default**, and a restart-pending banner with **Undo** —
  mounted as the top card of Settings → Data and as wizard step 2 (wizard is now
  core-8: Welcome → Working directory → Provider → Models → Defaults → Course →
  Files → Done; a restart into a fresh dir re-opens the wizard there naturally).
  No live re-binding and no automatic data copy by design (ADR-101) — moving
  existing data is the Settings → Data backup/restore flow, documented in
  `usage/getting-started.md`. Tests: backend `test_working_dir.py` (pointer/env
  precedence incl. the `backend/.env` pin, validation matrix, PUT/DELETE, boot
  resolution) + frontend `WorkingDirEditor.test.tsx` (render, save flow with
  pending banner, invalid reason, restore default); wizard + DataTab tests updated.
  conftest `client` fixture now also isolates `config_dir`.

- 2026-08-28 — **feat(onboarding): first-run setup wizard (plan 44, ADR-100).**
  Fresh installs now get a guided, fully skippable setup: a full-screen wizard
  overlay auto-opens when the server reports no provider AND no course
  (`GET /api/v1/onboarding/state` — new read-only aggregate returning
  `{has_provider, has_enabled_model, defaults_set, has_course, has_material}`;
  also the Done-step summary source). Seven steps: Welcome → AI provider
  (preset/name/base URL/API key — the Settings create-form logic extracted into
  shared `useProviderCreate` + `ProviderCreateFields` so wizard and
  ProviderFormDialog can't drift; a successful create auto-advances) → Enable
  models (checkboxes + Enable all over the auto-discovered list) → capability
  defaults (text/vision/embeddings/audio selects, same assign endpoint as
  Settings → Tasks) → first course (create with name+subject or load the sample
  course; the created course's real title is adopted from the refreshed list) →
  first files (`UploadDropzone` + `useMaterialUpload` targeting the created
  course — junk filtering, nested folders, dedup; ingest jobs continue in the
  background) → Done checklist with Open-course / Go-to-Today CTAs. Back / Skip
  for now / header-X skip everything; dismissal persists in localStorage
  `ca-onboarding-done` (fetch error ⇒ never auto-open). Manual entry points:
  Settings → Providers empty state and the Home onboarding card (new
  **Run setup wizard** button beside Create sample course). Backend:
  `onboarding.py` state endpoint + `test_onboarding_state.py` (fresh-all-false;
  provider/model/default/course/material each flip their flag). Frontend:
  `features/onboarding/` (wizardStore, OnboardingWizard shell + 6 step
  components) + 7 wizard tests (gate, skip persistence, manual open, provider
  advance, full flow with course→files→done). Backend 724 · frontend 830 tests
  green.

- 2026-08-28 — **fix(chat+jobs): release-gate CI flake — send-during-edit-turn race
  crashed the follow-up turn.** `test_select_hidden_subtree_restores_later_turns`
  failed on CI ("no pending user message", job 3): `POST /chat/sessions/{id}/messages`
  enqueued `chat_turn` **without** `user_message_id`, relying on a "last message is
  user" heuristic — when the send landed after the edit job was enqueued but before
  its handler claimed it, the edit's assistant reply committed first, the heuristic
  saw an assistant tail, and the follow-up turn failed; the reply also hijacked the
  active path (branched root's `active_child_id` overwritten). Three-part fix:
  (1) send enqueues the explicit `user_message_id` like edit/regenerate;
  (2) new `ChatService.chain_under_later_reply` — when the pending user message's
  parent gained an assistant reply *after* the pending message was created, the
  pending message chains under it, so a send typed mid-turn linearizes as
  user → reply → follow-up → answer; (3) `JobRunner` gained an optional `group_key`
  and skips claiming a job whose group (chat turns grouped per `chat_session_id`)
  still has an earlier queued/running job — per-session turns now run strictly in
  enqueue order (the FIFO the plan-40A turn lock intended; other job types stay
  fully parallel). Tests: runner group-FIFO test + `chain_under_later_reply` unit
  test; backend 722 green.

- 2026-08-28 — **fix(materials): folder delete racing a still-running ingest job
  crashed with `NOT NULL constraint failed: extractions.material_id`.**
  `test_delete_cascades_subtree` deleted the folder while the upload's async ingest
  job was mid-flight: `purge_material` bulk-deletes extraction rows before
  `session.delete(material)`, but `Material.extractions` had default (non-passive)
  cascade — the flush re-loaded children and any extraction committed by the ingest
  job in between triggered SQLAlchemy's null-the-FK UPDATE against the non-nullable
  column → `IntegrityError` → 500. Relationship now `passive_deletes=True`
  (children are always purged explicitly; the DB FK, not the ORM, is the safety
  net — a material deleted mid-ingest now fails its ingest job loudly instead of
  corrupting the delete). The test now waits for the material to reach `ready`
  before deleting, matching `test_materials_api`. Deeper hardening (cancel/
  re-validate in-flight ingest jobs whose material disappears) deferred — see
  Open issues.

- 2026-08-28 — **fix(ci): release `linux` job could not install WebKitGTK —
  `libwebkit2gtk-4.1-0t64` does not exist.** Ubuntu noble's t64 time_t rename
  hit GTK3 (`libgtk-3-0t64`) but **not** webkit2gtk, whose runtime package on
  24.04 is plain `libwebkit2gtk-4.1-0`; the CI step had copied the t64 suffix
  across, so `apt-get install` failed with "Unable to locate package" on the
  first tag build. Workflow now installs the real name (`libwebkit2gtk-4.1-0`,
  `gir1.2-webkit2-4.1` verified on noble); `packaging/build-linux.sh` deb
  `Depends` was already correct and is unchanged. Fixed the same wrong name in
  the packaging doc's artifact table.

- 2026-08-28 — **fix(release): `scripts/version_manager.py` refused to release when
  only the version file was dirty.** The `run()` helper `.strip()`ed porcelain
  output, eating the leading status space, so `line[3:]` chopped a real path
  character (`ackend/app/__init__.py`) and the dirty-file guard aborted. `run()`
  gained a `strip` flag and the porcelain parse now uses raw output. Regression
  test spins up a throwaway git repo and drives `git_release` end to end;
  `test_cli_show_prints_repo_version` now compares against the parsed source
  version instead of pinning `0.1.0` (which broke on every bump). Released
  **v0.1.1** via `bump patch --push`.

- 2026-08-28 — **feat!: product renamed CourseAssistant → Study Assistant
  (user decision; joins the Health-Assistant / Career-Assistant family).**
  Python package `backend/courseassistant` → `backend/studyassistant`
  (`python -m studyassistant`, console script, wheel packages), MCP server name
  + `/ai/mcp` command, and packaging renamed end to end
  (`packaging/studyassistant.spec`, `StudyAssistant.exe`,
  `studyassistant_<ver>_amd64.deb`, `StudyAssistant-<ver>-x86_64.AppImage`,
  `StudyAssistant-<ver>-windows-x64.exe`, `sa-extra` AppImage lib dir,
  window/desktop/deb/AppImage display names). **Settings env prefix `CA_` → `SA_`**
  (`SA_PORT`, `SA_DATA_DIR`, `SA_ONEFILE`, … — old `CA_*` vars are no longer
  read; update personal exports/`.env`). **Data dir moves to
  `~/.local/share/StudyAssistant`**: `default_data_dir` renames a legacy
  `CourseAssistant` dir automatically when the new one doesn't exist (both
  existing → new one wins, legacy untouched); **keyring service is now
  `StudyAssistant`** with read-through migration — a miss falls back to the
  legacy `CourseAssistant` service and copies the value over (legacy entries
  deliberately kept as backup; writes/deletes target the new service only).
  Display strings renamed (window title "Study Assistant", reset banner, caq
  SCHEMA_CARD title, Anki model "Study Assistant Basic", apkg deck, qpkg
  package name, backup zip filename `studyassistant-<stamp>.zip`), UI strings
  (`app.name`, capture hint, MCP hint, sync-dir placeholder), README/AGENTS/
  docs/usage guides, and the agent skills (`ca-dev`→`sa-dev`,
  `ca-docs-sync`→`sa-docs-sync`, `ca-migration`→`sa-migration`; worktree
  convention `../StudyAssistant-*`). **Wire formats intentionally unchanged**
  (`caq/v1`, `ca-course/v1`, `ca-backup/v1`, `ca-material:`/`ca-drawing:` refs,
  `ca-*` localStorage keys) so existing exports, bundles and DB content keep
  working. Also fixed a pre-existing red test: `test_packaging_assets` still
  asserted `ubuntu-22.04` after cfd87f6 bumped the release runner to 24.04.
  Backend 719 · frontend 823 tests green. Note for the repo itself: folder/
  remote renames (StudyAssistant) are a manual follow-up; local `.env` pin
  updated to `SA_DATA_DIR`.

- 2026-08-28 — **feat(release): `scripts/version_manager.py` (same CLI as
  Health-Assistant's manager).** The version is single-sourced in
  `backend/app/__init__.py`, so the manager is slim: `show` / `set X.Y.Z[-suffix]` /
  `bump major|minor|patch|rc` / `release` (catch-up for an already-set version),
  with `--git` (commit `chore(release): X.Y.Z` + annotated `vX.Y.Z` tag) and
  `--push` (branch + tag to every remote — triggers the Release workflow).
  Safety rail HA lacks: refuses to release when unrelated dirty files exist.
  Semantics preserved from HA (patch promotes `-rc.N` to the full release;
  rc increments `rc.N`). Covered by 7 new tests (`test_version_manager.py`,
  script loaded via importlib); release checklist in `docs/usage/packaging.md`
  now routes through it. Backend 713 tests green.

- 2026-08-28 — **feat(shell): remembered window geometry (size · position ·
  maximized) with sane restore.** The desktop window was pywebview's 800×600
  default on every launch. `app/shell.py` now persists window state to
  `<data_dir>/window-state.json` (machine-level, not per-profile): first run
  opens **1280×800, centered**; afterwards the last size/position/maximized
  state is restored. Restore is sanity-clamped (`clamp_window_state`): size
  bounded to ≥640×480 and ≤ the target screen, position re-based onto the
  screen that contains it, windows stranded by a disconnected monitor pulled
  back on-screen (≥80 px visible). GTK's frame offset between requested and
  reported client position caused per-launch position drift — 
  `WindowGeometryTracker` rebases `moved` deltas against the first mapped
  position so roundtrips are drift-free (verified 3 restart cycles), and
  maximize/restore keeps the pre-maximize size instead of capturing the
  fullscreen geometry. Corrupt/missing state falls back to defaults. Backend
  706 tests green (14 new window-state tests).

- 2026-08-28 — **fix(packaging): frozen Linux builds rendered a white window —
  bundle `gi.overrides` + system typelibs (white-screen root cause found).** A
  pixel-probe harness (launch → X screenshot → dark-pixel share) reproduced the
  white screen only in frozen builds: the SPA loaded and ran (12 assets + API
  calls, WebKit processes alive) but the widget never painted. Root cause:
  PyInstaller never bundles `gi.overrides.*` (nothing imports them statically),
  so frozen apps use raw GI bindings — `GLib.idle_add(webview.set_opacity, 1.0)`
  in pywebview's `on_load_finish` raised `TypeError: Must be number, not method`
  (pywebview creates the webview at opacity 0 and fades it in at load-finish;
  with the override missing, `idle_add` misparses its args, the widget stays
  fully transparent → white window). Fixed in `packaging/courseassistant.spec`:
  hiddenimports += `collect_submodules('gi.overrides')`, system typelibs →
  `gi_typelibs` + glib schemas → `share/glib-2.0/schemas` (dest matches
  PyInstaller's `pyi_rth_gi`), custom `packaging/hooks/hook-gi.repository.WebKit2.py`,
  and explicit `gi.repository.{GLib,GObject,Gio,Gdk,Gtk,Pango,cairo,WebKit2}`
  hiddenimports (PyInstaller's own namespace hooks no-op when the build-env
  pygobject wheel can't see system typelibs — the common wheel case). Dropped
  the `WEBKIT_DISABLE_DMABUF_RENDERER=1` workaround from the runtime hook and
  AppRun — it wasn't the cause and disables the modern renderer. Verified on
  Mint: frozen window paints (dark 2.2%, 0 TypeErrors — was 0%/3), `.deb` +
  `.AppImage` rebuilt and smoke-tested. Backend 692 · frontend 814 tests green.

- 2026-08-28 — **feat(packaging): working installers + tag-driven GitHub release —
  Windows `.exe`, Linux `.deb` + `.AppImage` (ADR-099, user-requested).** The
  phase-7 packaging scaffolding was PyInstaller-4-era and non-functional (spec API
  removed in PyInstaller ≥5, entry script did nothing, alembic datas missing).
  Reworked into a verified pipeline: `packaging/courseassistant.spec` (PyInstaller
  6, spec-relative paths, version read from `app.__version__`, entry =
  `courseassistant/__main__.py` so frozen builds keep `web`/`reset`/`mcp` modes;
  datas = built SPA + `alembic/` + `alembic.ini`; hiddenimports for per-platform
  pywebview backends; sqlite-vec `vec0.so`; Linux bundles the full GI typelib set +
  compiled glib schemas; `CA_ONEFILE`/`CA_CONSOLE` switches), and
  `packaging/runtime_hook.py` (windowed stdout/stderr → `$TMPDIR/courseassistant.log`;
  bundled `GI_TYPELIB_PATH`/`GSETTINGS_SCHEMA_DIR`; sets
  `WEBKIT_DISABLE_DMABUF_RENDERER=1` in frozen Linux builds — the white-screen
  candidate fix). `build_deb.sh`/`build_appimage.sh` replaced by
  `packaging/build-linux.sh [bundle|deb|appimage|all] [version]`: onedir PyInstaller →
  `.deb` (`/usr/lib/courseassistant` + `/usr/bin` wrapper + .desktop + icon;
  Depends: libgtk-3-0, libwebkit2gtk-4.1-0 — typelibs bundled, webkit libs from
  system) and a fully self-contained `.AppImage` (ldd-closure lib collector that
  seeds dlopen-only WebKitGTK + libstdc++, pixbuf loaders with rebuilt cache,
  AppRun env; 160 MB). `packaging/icon.svg` placeholder. New
  `.github/workflows/release.yml`: tag `v*` → full test gate (both suites) →
  ubuntu-22.04 deb+AppImage with headless web-mode smoke → windows-latest onefile
  `CourseAssistant-<ver>-windows-x64.exe` with smoke → draft GitHub release with
  generated notes; tag must match `app.__version__`. App fix:
  `default_data_dir` is platform-aware (Win `%APPDATA%\CourseAssistant`, mac
  `~/Library/Application Support/CourseAssistant`, XDG unchanged) + tests.
  `tests/test_packaging_assets.py` guards spec/hook/script/workflow drift; mypy
  now excludes `backend/dist/`. Locally verified on Mint: frozen web + app modes
  (WebKitGTK window), `.deb`, `.AppImage` all launch and serve. Windows artifact
  pending first tag run (CI-only). Backend 689 · frontend 814 tests green
  (LazyNoteEditor frontend flake now named in Open issues).

- 2026-08-28 — **feat(drawings): infinite drawing canvas — pan/zoom navigation,
  fullscreen, crop-on-save + view-box scale metadata (plan 43, ADR-098).** The
  handwriting canvas was a fixed 1400-px grow-downward strip: no zoom, no pan,
  saves carried huge empty margins, and re-opening a drawing showed it at an
  arbitrary scale. `DrawCanvas` is now an **unbounded viewport** — `view =
  {x, y, zoom}` over a DPR-aware backing canvas with a light dot grid — with
  **wheel = zoom toward the cursor** (non-passive native listener, line-mode
  delta handled), **middle-drag / hold-Space-drag / hand-tool = pan**, and a
  **floating bottom-left bar** (zoom out · percent · zoom in · Fit drawing ·
  1:1; the percent button resets to 100%). Both drawing dialogs (note editor
  + chat composer) gained a **⛶ fullscreen toggle** (CSS maximize — Escape
  exits fullscreen before closing). On save, `exportDrawing` **crops the PNG
  to the strokes' bounding box + 24 px padding** (also used by quiz write-mode
  and chat drawing attachments) and records the region as **`view`
  `{x, y, width, height}`** — 1 PNG px = 1 logical px — stored on
  `note_drawings`/`material_drawings` (migration **0046**, validated
  `ViewBox` schema, carried through notes/materials drawing endpoints,
  derive-copy, and `ca-course/v1` bundle round-trip additively). Editing a
  drawing **restores its saved view at exactly 100% scale** (falls back to
  fit-to-content for legacy rows), and drawing images render at **natural
  size** (`max-w-full`, no more full-width stretching). Backend 684 ·
  frontend 823 tests green. Docs: `features.md`, `data-model.md`,
   `import-export.md`, `usage/notes.md`.

- 2026-08-27 — **fix(settings): `audio` models pass the caps vocabulary; 422
  validation errors render readably.** Follow-up to plan 42: manually adding a
  Whisper-class model (e.g. `whisper-1`, inferred caps `["audio"]`) was rejected
  by `POST /api/v1/models` with 422 — `MODEL_CAPS` in `app/api/schemas.py`
  (shared by the create/update caps validators) didn't include the new
  `audio` capability — and the UI showed `[object Object]` because FastAPI
  validation errors return `detail` as an array of objects which `lib/api.ts`
  interpolated directly. Fixed both: `MODEL_CAPS` gained `"audio"` (unknown
  caps like `telepathy` still rejected), and a new `apiDetailMessage` flattens
  array details into `"caps: Value error, unknown caps: …"`-style messages in
  every `json`/`expectOk` error path. Backend 681 · frontend 814 tests green.

- 2026-08-27 — **feat(ai): dictation — Whisper STT in the rich editor + chat
  composer; new `transcribe` task + `audio` capability (plan 42, ADR-097).**
  Speech-to-text was the post-1.0 backlog item (B13) and now ships as
  **dictation**: the shared Tiptap `MarkdownEditor` (notes, extraction QA
  editor, new text/markdown dialog) and the chat composer (sidebar + page) gain
  a 🎤 button that records a clip in the browser (`MediaRecorder`, mime
  preference webm/opus → ogg/opus → mp4; timer + live level-meter strip with
  Cancel, error variants for unsupported/denied/unassigned/failed) and posts it
  to **`POST /api/v1/ai/transcribe`** (multipart, ≤25 MB, optional ISO
  `language`) → `{text, model}`, inserted at the editor cursor / draft caret.
  Backend: new `audio` capability + `transcribe` task (requires `audio`)
  resolving through the normal chain (global default → task → course default →
  course override); `LLMGateway.transcribe` mirrors `generate` (budget gate,
  fallback chain, transient retry, `ai_interactions` ledger row with
  `[audio N bytes mime]` prompt field); provider calls are raw httpx per the
  embedder precedent — `openai_compatible` → `POST {base}/audio/transcriptions`
  multipart (OpenAI, Groq, or any local whisper server via the
  openai_compatible preset), `google` → `generateContent` inline base64 audio
  guided by the new `transcribe.audio` seed skill (verbatim transcript,
  dictated math as LaTeX), `anthropic` → clear unsupported error. The endpoint
  offloads the blocking call via `run_in_threadpool` (never stalls chat
  streaming) and maps TaskUnassigned→409 / BudgetExceeded→429 /
  ProviderError→502; audio is **ephemeral** — never persisted. `infer_caps`
  infers `audio` for whisper/transcribe ids and all gemini models; Settings
  capability pickers (Tasks defaults, course defaults, edit-model caps) expose
  `audio / speech-to-text`. Frontend: shared `useDictation` hook +
  `DictationStrip`/`DictationMicButton` (`components/dictation/`); both
  surfaces reuse them. Backend 679 · frontend 811 tests green (13 new backend +
  12 new frontend; known `test_delete_cascades_subtree` full-run flake
  unchanged). Docs: `ai.md`, `features.md`, `usage/notes.md`, `usage/chat.md`.

- 2026-08-27 — **feat(search): typo-tolerant fuzzy search everywhere + modular
  `services/search/` engine (migration 0045).** Search was exact-match only — the
  Library page's phrase FTS, RAG chunk retrieval and notes `LIKE` all failed on
  misspellings. `services/search.py` is now a package (`tokens`/`matching`/`fusion`/
  `scoring`/`materials`/`chunks`) with one public API. New trigram FTS5 table
  `material_fts_trigram` (0045, backfilled, synced alongside `material_fts`) powers an
  index-backed fuzzy tier: trigram candidates verified per-token in Python
  (difflib ≥0.8, substring-aware) so nonsense words never match. `/api/v1/search` runs
  weighted-RRF tiers (exact phrase → prefix → fuzzy → vectors; fuzzier tiers only when
  needed) and gains `course_id` scoping — the Library passes its course, so results stay
  in-course. RAG `retrieve_chunks` gets the same fuzzy fallback; notes `q` falls back to
  the shared `fuzzy_text_match` scorer when `LIKE` misses. Client-side filters (workspace
  Materials tab, Courses page) now use the shared `lib/fuzzy` subsequence matcher.
  Backend 665 · frontend 788 tests green. Docs: `data-model.md` (0045 +
  material_fts_trigram), `features.md`, `usage/library.md`.

- 2026-08-27 — **fix(ui): notes and library search now filter live.** The Notes tab and
  the Library page kept their old submit-gated flow (results only after pressing
  Enter); both now debounce the query (250 ms) into the state that drives the
  server query (`submitted` / `submittedQuery`), so results update **as you type** —
  Enter still applies immediately and ✕/Esc reset instantly. Notes/library tests no
  longer submit the form and assert the debounced live update instead; frontend 788
  green. Usage docs updated (`notes.md`, `library.md`).

- 2026-08-27 — **feat(ui): shared `ExpandableSearch` — icon-only search button with an
  animated expand transition.** A new `components/ui/ExpandableSearch` renders as a
  36 px icon-only button (magnifier) that springs open (`transition-[width]` 300 ms
  ease-out, input fade-in, autofocus) into a 256 px search field; **Esc** clears a
  non-empty query then collapses, **blur while empty** collapses, the ✕ clear button
  fires an optional `onClear` hook, and Enter submits (same `value/onChange/onSubmit`
  contract as `SearchInput`, which stays in use for dialogs/panels). Wired into four
  surfaces: the workspace **Notes tab** (right-aligned next to the view toggle; the
  previously-stale submitted query now resets via `onClear`), the workspace
  **Materials tab** (new client-side filter on material/folder names + a
  "Nothing matches this filter." empty state — the tab had no search before), the
  **Library page** (replaces the always-visible inline box in the header), and the
  **Courses page** (new filter on title/subject/description + "No courses match"
  note). i18n keys: `common.search`, `workspace.searchPlaceholder`,
  `workspace.noSearchResults`, `courses.searchPlaceholder`, `courses.noMatch`.
  Tests: 7 component tests + materials-filter and courses-filter tests; notes/library
  search tests updated to click the button first. Frontend 783 · backend 656 green
  (one `test_delete_cascades_subtree` flake in a full run, passes in isolation — same
  known sensitivity recorded on 2026-08-27). Usage docs updated: `library.md`,
  `courses.md`, `notes.md`.

- 2026-08-27 — **feat(ui): the profiles overlay's add-profile flow is two-step.**
  `ProfileDialog` no longer keeps a permanent name field under the profile list —
  it shows an **Add a profile** outline button instead; clicking it reveals the
  creation form (autofocused name input, **Add**, new **Cancel** back to the
  list, which resets name/error). Creating still switches to the new profile and
  closes the overlay. Tests: profiles-overlay test updated to drive both steps
  (form hidden until the button is clicked); frontend 774 green.

- 2026-08-27 — **fix(ui): nav-panel theme toggle works on consecutive clicks.** The
  `ThemeToggle` computed the current theme from `localStorage` during render only, and
  `applyTheme` never triggered a re-render — so after the first click the button kept
  re-applying the same stale "next" theme (second click in a row did nothing until an
  unrelated parent re-render). Current theme now lives in component state (initialized
  from storage), updated on click; `readStoredTheme` also accepts `'system'` so reads
  are symmetric with writes. Regression tests cover the full system→light→dark cycle,
  stale-click protection, stored-theme mount, OS-preference follow, and next-theme
  announcement; frontend 779 green.

- 2026-08-27 — **feat(chat): branch-tree rail (plan 41, ADR-095).** A `GitBranch` button in the chat panel header (session open) opens a popover rendering the conversation's full branch structure as a commit-graph-style indented tree: on-path nodes get a filled dot + `aria-current` + bold excerpt, off-path variants a hollow dot, forks show a sibling-count badge, roles get icons. Backed by a new read-only `GET /chat/sessions/{id}/tree` (`{active_root_id, nodes: [{id, role, excerpt ≤100 chars, parent_id, children, active_child_id}]}` — pure projection of 0044, no schema change); clicking a node calls the existing `POST /chat/messages/{id}/select` (one pointer flip) and invalidates messages + tree. Client-side active-path walk from `active_root_id`/`active_child_id`; no graph library. Tests: endpoint tree-exposure test (hidden branches, parents/children, active root) + panel render/select tests; frontend 774 green.

- 2026-08-27 — **feat(ui): the node workspace header collapses into the breadcrumb
  row.** `/courses/$cid` and every node page no longer show two stacked title
  surfaces (small breadcrumb strip above a large `h1` + summary block): one row now
  carries everything — sidebar toggle, breadcrumb nav, node actions. The **last crumb
  renders as the page heading**: bold (`text-xl font-bold tracking-tight`), with the
  course accent dot beside it, `aria-current="page"`; ancestor crumbs stay small,
  muted links. The separate `text-2xl` title and its description line are removed —
  the summary remains editable in the node settings popover. Study here / Ask about /
  settings stay right-aligned on the same row (wraps on narrow widths). Tests:
  breadcrumb-as-heading test (+1: single heading, no duplicated crumb link,
  aria-current, actions present); settings-popover test updated (page no longer shows
  the clamp — description lives in the popover); frontend 762 · backend 646 green
  (one flaky `test_delete_cascades_subtree` parallel-run failure observed, passes in
  isolation on main and branch).

- 2026-08-27 — **feat(chat): Chat uploads organized per conversation (user request).** Chat file uploads are no longer a flat pile: each conversation gets its own subfolder — `Chat uploads/<session title> (#<session id>)` — created on demand inside the course's *Chat uploads* root, and dialog uploads are enumerated per folder (`Drawing 1.png`, `Drawing 2.png`, `Screenshot 1.png`, …; user-picked files keep their names). To make per-conversation folders possible with deferred session creation, the **first upload now creates the chat session** (same adoption flow as first send — the sidebar adopts it, attachments survive; a failed create is retried on the next upload). Folder lookup is by the ` (#id)` suffix, so renaming a session **renames the folder in place** on the next upload (legacy folders under an older title are found by suffix pattern and renamed, never duplicated); titles are sanitized (filesystem-hostile chars stripped, 60-char cap, `#` removed so titles can't spoof the suffix). Plumbing: `useMaterialUpload` gained a `nameFile` hook (returns the final file name per item; `UploadItem.label` carries the semantic kind — "Drawing"/"Screenshot") and ChatPanel's `ensureChatUploadFolder`/`ensureUploadSession` are shared by the composer dialogs and the attach menu's upload tab (`resolveUploadFolder` prop). Pure helpers + naming rules in `features/chat/uploadCourse.ts`. Frontend 799 green (+9 tests).

- 2026-08-27 — **feat(chat): course-less chats can draw, screenshot and upload (ADR-094 amendment, user request).** The composer's drawing/screenshot actions and the attach menu's upload tab no longer require a course-bound session: `ChatPanel` resolves a fallback upload target from `listCourses()` (`resolveUploadCourse` in `features/chat/uploadCourse.ts` — per-profile **Unsorted** course first (title match, as created by migrations 0014/0020), else the single active course) and files uploads into its *Chat uploads* folder; the backend needed no change (`ChatService.attach` is course-agnostic). Fallback dialogs/hints name the destination ("files into the Unsorted library"), `AttachMenu` gained `uploadCourseId`/`uploadHint` props (material/note listing stays session-scoped — all courses when unbound), and when no target resolves (≥2 courses, none titled Unsorted) the actions stay hidden with the create-a-course hint. Frontend 790 green (+2 tests).

- 2026-08-27 — **feat(chat): stop generation, scroll pill, code-copy, .md export (plan 40D).** Turns can be stopped mid-stream: `POST /chat/sessions/{id}/stop` flips a per-session stop event registered by the turn handler (checked per chunk and between repair/tool rounds); stopping keeps the streamed prefix — persisted like a mid-stream interruption with `trace.stream_interrupted` — and the composer's send button becomes a ■ **Stop** button while a turn is pending; the WS `stream_interrupted` event now finalizes panel state. Assistant **code blocks** (fenced markdown and structured `code` blocks) gained a hover **copy** button (`BlockRenderer`'s `CodeSurface`). Long chats get a sticky **scroll-to-latest** pill when scrolled >120 px from the bottom during history/stream growth. Session ⋯ menus gained **Export as Markdown** (`exportSessionMarkdown.ts`: role headings, citations as block-quotes, `<title>.md` download). Tests: `test_chat_stop.py` (mid-stream stop persists prefix + trace + WS event; endpoint no-active-turn/404) and frontend stop/copy-code/export-builder tests — backend 656 green (serial), frontend 771 green. Findings: the backend pytest suite is flaky **under xdist** on this machine (random `sqlalchemy` contention failures that pass serially — e.g. `test_folders_api.py`, `test_providers_api.py`); also two `folders` delete tests depend on `frontend/dist` existing (SPA mount changes unmatched-path 405-vs-404 semantics), so a fresh worktree needs `pnpm build` before the suite is meaningful. Both are pre-existing environment sensitivities, recorded here for follow-up.

- 2026-08-27 — **feat(chat): composer "+" gains equation, drawing and screenshot (plan 40C).** The attach popover now leads with three actions: **Insert equation…** (shared MathLive `MathInput`, live inline `$…$` vs `$$…$$` toggle, inserted at the composer cursor with restored caret), **Open drawing canvas…** (the shared `DrawCanvas` in a dialog; strokes render to PNG and ride the existing `useMaterialUpload` pipeline into the **Chat uploads** folder, attaching as a material chip), and **Capture screenshot…** (`getDisplayMedia` frame grab → draggable crop overlay over the frozen frame → cropped PNG upload; graceful alert when capture is unsupported, e.g. inside WebKitGTK — use webapp mode in Chrome/Firefox). Draw/screenshot require a course-scoped session (uploads need a folder target) and are hidden otherwise. Frontend 768 green (+3 tests).

- 2026-08-27 — **feat(chat): message action bar + variant switcher (plan 40B).** Hover actions on every bubble — **Copy** (markdown to clipboard with check-flash), user messages gain inline **Edit** (prefilled textarea, Save & resend / Esc cancel; Cmd/Ctrl+Enter submits) hitting `POST /chat/messages/{id}/edit`, assistant bubbles gain **Regenerate** against their parent question (`…/regenerate`). Bubbles with siblings render an OpenWebUI-style ‹index/count› switcher driving `POST /chat/messages/{id}/select`; `MessageOut` now also carries `sibling_ids` so arrows know both neighbors. Actions disable while a turn is pending. Frontend 765 green (+4 tests).

- 2026-08-27 — **fix(ui): full-screen overlays now close floating popovers (cheat-sheet
  dropdown poked through the Study… popup).** Root cause: the shared `Popover` portals
  its panel to `<body>` at `z-[60]`, above every modal's `z-50` backdrop, so a dropdown
  left open around the moment an overlay mounted (e.g. the Overview tab's cheat-sheet
  menu while **Study here…** opens `StudyLauncherDialog`) kept painting above the dimmed
  overlay. Fix is systemic rather than z-index renumbering (which would break popovers
  that legitimately live *inside* dialogs, like the builder's info chips): new
  `lib/ui-overlays.ts` — a zustand signal + `useCloseFloatings()` mount hook; the shared
  `Popover` subscribes and closes itself when any overlay mounts. Wired into every
  full-screen surface (21): GenerateDialog, StudyLauncherDialog, NoteComposeDialog,
  NotePickerDialog, NoteHistoryDialog, EntityActionMenu, MaterialPickerDialog,
  AssignToNodeDialog, RenameDialog, NewTextFileDialog, NewFolderDialog,
  FolderDelete/FolderPicker dialogs, ImportDialog, ToolsDialog, ProfileDialog,
  Edit/AddModel + ProviderForm dialogs, MindmapEdit/History dialogs. Policy for new
  overlays: call `useCloseFloatings()` on mount. Popovers opened *after* the overlay are
  unaffected. Tests: popover suite +2 (overlay closes open popovers; post-overlay popovers
  keep working) and NodeWorkspace integration test (study launcher opening dismisses an
  open cheat-sheet menu); frontend 761 · backend 646 green.

- 2026-08-27 — **feat(courses): the structure sidebar's context menu works across
  the whole panel.** The context dropdown is now bound to the sidebar `<aside>`
  instead of only the tree scroller: right-clicking anywhere in the panel that is
  not a node row — empty space, row gaps, below the last node, or the header /
  filter chrome — opens it and applies it to the **active node** — the one whose
  workspace you are viewing — like a file manager acting on the open directory:
  Add child appends beneath it (the inline title form renders under its row),
  Study… scopes the entity action menu to it, Rename/Delete operate on it with
  the existing confirm/undo flow; with no current node (or at the course root) it
  falls back to the root's menu (no rename/delete, per root protection). Row
  right-clicks are unchanged — the handler defers via a `role="treeitem"`
  ancestor check so the two never double-open, and `input`/`textarea` targets are
  skipped so the search field keeps its native cut/copy/paste menu. No new i18n
  keys (menu grammar reused). Tests: +4 `NodeTreeSidebar` tests (background→rename
  targets active node 4, background→delete confirms against it,
  fallback→add child posts under the course root, whole-chrome coverage incl.
  input deference); frontend 755 · backend 646 green.

- 2026-08-27 — **fix(chat): node-ask opens the tutor sidepanel instead of the full page.**
  Every *Ask about this node* surface (workspace header/overview, Tutor tab CTA, child
  cards' quick ask, sidebar **Study… → Ask**, mindmap ask) now creates its node-bound
  session and opens it in the chat sidepanel over the current route (`chat-store` gained
  an active-session pointer: `openSession({id, publicId})` / `setSession`, `setOpen(false)`
  clears it; AppShell dropped its local `sidebarSession` state for the store). The panel
  header ⤢ still expands to `/chat/$chatId`; full-page collapse (⤡) now carries the
  current session into the sidepanel instead of dropping you into a fresh new chat.
  Existing-session rows in the Tutor tab/session lists keep opening the full page.
  Tests: NodeWorkspace ask asserts panel pinning; AppShell gains open-pinned-session +
  expand test (+1); ChatPage collapse-carries-session tests (+2, `ChatPage.test.tsx`);
  frontend 754 · backend 646 green.

- 2026-08-27 — **feat(settings): per-course capability defaults — four-level model resolution (ADR-092).** Completes the requested chain global default < global task < **course default** < course task, resolved per slot. Migration **0043** `course_default_task_assignments` (course_id+requires composite PK, nullable model_id/fallback_model_id); `assign_course_default_task`/`list_course_default_assignments` in providers; gateway `_resolve_chain` now layers the course default between the global task assignment and the course task override; new endpoints `GET/PUT /courses/{id}/tasks/defaults[/{requires}]`; per-task rows' inherited labels (`global_*_label`) become course-aware (`_course_inherited_labels`) so "— inherit default —" previews exactly what would run incl. the course default. Model deletion nulls the new rows too; course purge removes them. Frontend Tasks subtab gains a *Default models* card (text/vision/embeddings × model+fallback selects, reusing `settings.defaultModel*` keys + new `courseSettings.courseDefaultsHint`, refreshed tasksHint wording). Tests: backend four-level precedence test + defaults round trip/422/purge/delete-model coverage (646); frontend defaults-card test + harness mocks (751).

- 2026-08-27 — **feat(courses): course settings tab with title/description + per-course task-model overrides (ADR-091).** The node workspace gains a seventh pill tab, **Settings**, rendered only on the course root (`?tab=settings` deep-links; chapter workspaces hide it and a forced deep link falls back to Overview). Two subtabs: *General* edits the course title/description via `PATCH /courses/{id}` (root-node sync server-side), and *Tasks* mirrors the global `/settings?tab=tasks` registry as per-course overrides — every `TASK_DEFS` entry lists model + fallback selects whose empty value shows what is inherited ("— inherit default —" over the global label, else unassigned). Backend: migration **0042** `course_task_assignments` (course_id+task composite PK, nullable model_id/fallback_model_id); new endpoints `GET/PUT /courses/{id}/tasks[/{task}]` reusing capability checks + 404/422 contract of the global routes; gateway `_resolve_chain` gains `course_id` — an override wins **per slot** (model vs fallback independently), unset slots fall through task-assignment → capability-default. `LLMGateway.generate/generate_structured/stream/stream_events/resolve` accept optional `course_id`, TaskRunner threads its existing `course_id` param into all gateway calls + audit labels, and every course-scoped caller now passes it (quizgen/exgen/flashcards/compose pipelines, chat turns incl. native-tool resolution/degradation, tutor hint+quiz-help ladders, rubric grading, drills/pattern discovery, outline draft, organizer review/draft-note, concepts extraction, note compose/actions, mindmap-edit, material index cards via describer signature `(title, markdown, course_id?)`). Embeddings stay global. Model deletion nulls course overrides too; `purge_course` deletes them. Tests: 5 new backend tests (API contract incl. 404s/vision gating/delete-model/purge, gateway slot-merge resolution chains) + fake-gateway signatures across the suite extended with `course_id`; frontend CourseSettingsTab component tests (3) + NodeWorkspace harness additions (settings tab root-only + deep link, save flow, override select flow) + en.json i18n keys. Backend 645 · frontend 750 green.

- 2026-08-27 — **fix(library): context-menu re-ingest works on straight right-click;
  unnamed single-file label.** The material context menu computed its items from the
  selection store *after* `selection.set()` on the right-clicked row — a same-tick
  stale read, so **Re-ingest** (and Retry-failed gating) only appeared when the row
  had been selected first; Open worked because it used the clicked id directly.
  `materialMenu` now derives the effective id list synchronously from the clicked row
  when it isn't in the current selection (multi-selection semantics preserved), and
  batches all file-backed rows into one reingest mutation instead of one per row. The
  single-file item reads **Re-ingest this file (OCR again)** — no filename — via an
  updated `jobs.reingestOne` string; multi stays "Re-ingest N files". 2 new
  LibraryPage tests (straight-right-click flow + multi-selection batching); frontend
  744 green.

- 2026-08-27 — **feat(jobs): delete + stale controls on the task-activity surfaces
  (plan 39D complete).** `/jobs` page: per-row 🗑 delete on failed/done rows (confirm);
  header **Delete…** menu (`PopoverMenu`) with *Delete all failed* — scoped to the
  active Type filter when set (the requested "delete selected group") — and *Delete
  source-missing (N)* disabled at 0; stale failed rows render a **source removed** chip,
  muted, with retry hidden. Activity popover: per-row 🗑 + **Delete all failed** icon in
  the Failed section header + **Delete source-missing (N)** shortcut; retry hidden on
  stale rows; badge clears on poll after deletes. Backend bulk-delete gained
  `stale_only` so the source-missing action removes exactly those rows. api client:
  `deleteJob`, `deleteFailedJobs({types?,staleOnly?})`, `JobInfo.stale`,
  `JobsSummary.failed_stale`. Frontend 742 tests green (+7); full backend suite 640.

- 2026-08-27 — **feat(jobs): boot-time pruning of done-job history (ADR-089).** The
  `jobs` table had no GC of any kind since migration 0002. New
  `app/jobs/pruning.py::prune_done_jobs` deletes `done` rows older than
  `CA_JOBS_DONE_TTL_DAYS` (Settings field, default 14, cutoff on
  `coalesce(finished_at, created_at)`), called from `create_app()` right after the trash
  purge; pruned count logged (`jobs_done_pruned`). Failed/queued/running rows are never
  touched — failures keep their red-badge signal until explicitly deleted (39B), which
  stays a manual act by design. 3 new pruning tests; backend 640 green.

- 2026-08-27 — **feat(jobs): delete terminal jobs + stale detection (ADR-089).** New
  endpoints: `DELETE /api/v1/jobs/{id}` (204; done/failed only — queued/running → 422,
  unknown → 404) and `DELETE /jobs/failed` (optional `{types?}` filter, mirrors
  retry-failed; deletes **all** failed rows including non-retriable `chat_turn` —
  hopeless failures are exactly what needs deleting; declared before `/{job_id}` so the
  literal route wins). Failed jobs whose referenced entity is gone (the reported
  `ingest → material {x} not found` class, or a deleted chat session) are now flagged:
  batched existence checks against `materials`/`chat_sessions` set `JobOut.stale`
  (any status with an unresolvable payload reference), and `JobsSummary` gains
  `failed_stale`. The summary endpoint also now computes `failed_retryable` from full
  failed rows (no behavior change). No FK/cascade between entities and jobs — jobs stay
  an append-only audit log; deletion is explicit. Frontend surfaces follow in plan 39D.
  Backend 637 tests green (+4).

- 2026-08-27 — **fix(settings): per-capability task-default models survive restart and
  restore (ADR-090).** The `/settings?tab=tasks` capability defaults were wiped on every
  app start: `create_app()`'s seeding block called `assign_default_task(session,
  requires, None, None)` as an *unguarded upsert*, rewriting each
  `default_task_assignments` row back to NULL before the first request was served — the
  same defect ran in backup `_apply_restore`. Both call sites now use one insert-only
  `seed_default_task_assignments()` seeder (creates missing rows, never mutates existing
  ones), mirroring the long-correct `task_assignments` seeding. New regression tests boot
  a second `create_app()` against the same DB and run an export→restore round trip —
  both red on the old code. Backend 633 tests green.

- 2026-08-27 — **Jobs page deep-dive + library-level retry.** The `/jobs` page tabs,
  type filter, sort key and direction are now URL search params (`?status=&type=&sort=
  &dir=asc`), each status tab being a routable link. A **Type** dropdown filters by
  job type (populated from the new `GET /jobs/types`, which lists handler-registered
  types minus `chat_turn`), and a **Completed / Started / Created** segmented sort
  with an asc/desc toggle orders rows client-side. `POST /materials/{id}/reingest`
  re-runs ingestion (same pipeline as upload: OCR for scanned pdfs/images, native
  extraction for md/txt) for file-backed materials. The Library context menu gains
  two actions: **Re-ingest … (OCR again)** on single or multi selections containing
  pdf/md/txt/image materials, and **Retry failed AI tasks for this file** when failed
  retriable jobs exist for the selected material. Backend 631 · frontend 735 green.

- 2026-08-27 — **Failed-job visibility + retry (ingest/OCR et al.).** New jobs API:
  `GET /api/v1/jobs` (`status`/`type` filters, newest first, material-filename labels,
  error text, per-row `retriable`), `GET /jobs/summary` (queued/running/failed/done +
  `failed_retryable`), `POST /jobs/{id}/retry` and `POST /jobs/retry-failed`
  (optional `types` filter). A failed job is retriable iff its type has a registered
  handler in `JobRunner` (exposed via `retriable_handlers()`) and isn't a chat turn;
  retry resets status→queued, clears error/stage/timestamps, publishes progress and
  wakes the pool. Frontend: rail-footer **activity button** with red failure badge →
  panel listing Failed (per-row ⭯ retry + **Retry all N failed** bulk), In progress
  (stage + progress bar) and Recently completed; polls summary every 10 s and both
  endpoints every 2 s while open. New usage page `docs/usage/activity.md`. Backend 629
  (+4 tests) · frontend 732 (+5 tests) green.

- 2026-08-27 — **`/jobs` full task-activity page.** `JobOut` gains `material_id`
  (parsed from the payload; non-numeric values tolerated — label lookup shares the
  parser). New route `/jobs` (`features/jobs/JobsPage.tsx`, linked from the activity
  panel's *View all tasks*): per-job cards with name → material deep link
  (`/library/{id}`), type chip, **status·stage** chip (shows where a failed job
  stopped), job id + start/finish timestamps, click-to-expand full error text,
  per-row retry, header **Retry all failed**, status tabs with live counts and
  name/id search; 5 s polling; tab/type/sort/dir are **URL search params** so every
  view deep-links. New `GET /jobs/types` exposes retryable handler types (chat_turn
  excluded in `retriable_handlers()`); new `POST /materials/{id}/reingest` re-queues
  ingestion for pdf/md/txt/image materials. Library context menu gains **Re-ingest …
  (OCR again)** for file-backed selections and, when failed jobs exist for the
  selected material, **Retry failed AI tasks for this file** (retries those job
  rows). Backend 631 (+2 tests) · frontend 735 tests green.

- 2026-08-27 — **Rail polish: logo header, select-a-course placeholder, profiles
  overlay.** The app-name header becomes a real **logo** — a gradient rounded tile
  with a graduation-cap glyph next to the wordmark, and the whole thing links to Home.
  With no course picked the course-switcher trigger now reads **"Select a course"**
  (muted, placeholder-style) instead of "All courses"; the explicit **All courses**
  option moved inside the listbox (separator under the course rows), leaving the
  popover footer as a single Courses row. The footer's raw `<select>` + inline create
  form is replaced by a **profile button** (UserRound icon + active profile name)
  opening a centered `ProfileDialog` overlay: selectable rows with color avatars,
  hover trash for non-default profiles (`deleteProfile` new in the API client;
  backend already allowed it), and an add-profile form that creates **and switches**.
  Removed keys `profiles.new/namePlaceholder` usage moved into the dialog; added
  `nav.selectCourse`, `nav.noCoursesMatch`, `profiles.manage/manageHint/confirmDelete/
  addTitle`. Frontend 727 tests green.

- 2026-08-27 — **Command button reads as search.** The rail's Ctrl+K affordance is
  relabeled **"Search…"** with a magnifier icon (goal-oriented naming, per common
  practice of placing the highest-frequency action directly under the logo) and
  input-style chrome; the palette itself is unchanged.


- 2026-08-26 — **Navigation consolidation: one course hub in the rail + Cards folded
  into Practice.** The sidebar's three overlapping course surfaces (switcher dropdown,
  "My courses" quick-jump list, Workspace·Notes micro-links) merge into a single
  **course hub**: a popover switcher whose entries both set the current course *and*
  navigate to its workspace — rows carry a color-letter tile, subject + material count,
  a search box (fuzzy, appears with >5 courses), and footer rows for Manage-courses and
  All courses; the flat nav below gains **Courses** back so the management page is
  always reachable, shrinking to Home · Courses · Tutor · Library · Scores. With an active course the
  hub renders a **2×2 shortcut grid** — **Workspace / Materials / Notes / Practice**
  (`?tab=` deep links, active state from the URL; horizontal icon+label cells so no
  label truncates). In the workspace the tab bar becomes
  pill-style with icons and **live counts** from the tree API (materials/notes and
  quizzes+exercises on Practice) plus a due-cards badge; **Cards is no longer a tab** —
  its review queue, card list and Anki import/export live as a **Flashcards segment**
  inside PracticeTab (`?tab=cards` still deep-links there), taking tabs 7 → 6.
  Removed i18n keys `nav.quickJump/workspaceLink/notesLink/group*`. Frontend 723 tests green.

- 2026-08-26 — **Assigned folders no longer dump their member files into the workspace
  Materials tab.** Previously, assigning a folder to a node flattened every file inside
  it into the node's materials list (each row carrying a "via folder" chip). Now the
  workspace `materials` list contains **direct links only** — folder members stay
  **inside their folder**, which renders as a folder tile/row in the Materials tab
  (double-click opens it in the Library to browse the contents). The workspace payload
  gains `folder_material_ids` (this node's folder-member ids) so the assign-picker and
  bulk-unassign still treat folder members as assigned; `child_materials` (Overview
  child-card counts + GenerateDialog context) is unchanged. Backend `workspace()`
  builds a flat `folders` list with `member_count` instead of the old recursive
  `_folder_entries`. Frontend 722 · backend 625 tests green.

- 2026-08-26 — **Dragging files or a folder over the Library page or the workspace
  Materials tab now opens an upload menu at the drop point instead of nothing.**
  Previously file drops were only handled inside the empty-state `UploadDropzone`
  banner; dragging onto a pane that already had items did nothing. A new shared
  `useFileDropMenu` hook detects external file drags (`dataTransfer` contains `Files`),
  collects the drop via `collectDropFiles`, and opens a `ContextMenu` at the cursor
  with **auto-detected** options: a folder drop offers **Upload folder…** (recreates the
  directory tree) and **Upload files…** (flattens to loose files), a plain file drop
  offers only **Upload files…**. Wired into the Library page pane and the Materials tab
  (`MarqueeSurface` gained `onDragOver`/`onDrop` passthrough); non-file drags
  (internal material moves) keep their existing behavior. Frontend 721 tests green.

- 2026-08-26 — **Uploading a folder in the Materials tab now assigns the folder to the
  node instead of each file.** `useMaterialUpload` gained an `onFolderCreated` callback
  fired once per **top-level** folder created during an upload (deduped per run); the
  workspace Materials tab uses it to `allocateNodeFolder` the new folder and now skips
  per-file `allocateMaterial` when a file arrives inside an uploaded folder
  (`item.relativePath` set) — loose files still link directly. Folder membership
  resolution brings the contents into the node automatically, so the folder shows up as
  an assigned folder rather than a flat list of individually-linked files. `ensureFolderPath`
  reports only folders created at the base level (parent = the upload target), so
  nested subfolders aren't assigned separately. Frontend 715 tests green.

- 2026-08-26 — **Upload banner now offers folder upload too.** The shared
  `UploadDropzone` banner ("Drop files here or click to browse") previously only
  opened a **files** picker on click — the separate *Upload folder* button was the
  only way to browse a directory. The banner is now a single affordance that opens a
  small menu with **Upload files…** / **Upload folder…** (the directory picker was
  already supported for the button and for drag-and-drop). Dragging a folder onto
  the banner already recreated the folder tree via `collectDropFiles` → `uploadFiles`
  relative-path handling; a regression test now pins that behavior (folder drop
  recreates the directory chain, junk files skipped). Added `ContextMenu` to the
  shared dropzone; both `block` and `row` variants get the banner menu. Frontend 714
  tests green.

- 2026-08-26 — **Fix: right-click pane menus now open on empty states.** The Library
  page's pane-level context menu only opened when right-clicking the bare pane element
  (its handler required `event.target === event.currentTarget`), so with no materials
  the empty-state text covered the pane and right-clicking it did nothing; it now uses
  the same interactive-element exclusion as the workspace `MarqueeSurface`, so
  right-clicking anywhere on the empty library pane opens the create menu (New
  text/Markdown file, New folder, uploads, add linked folder…). The workspace **Notes
  tab had no pane context menu at all** — right-clicking its empty state did nothing;
  it now opens a menu with **New note here** / **Draft notes**, matching the toolbar
  (which the Materials tab already had via `MarqueeSurface`). Frontend 711 tests green.

- 2026-08-26 — **Fix: chat turns no longer hold the SQLite write lock during the model
  stream.** A chat turn writes its session's **mention registry** (`chat.py _turn_registry`)
  before calling the model; that write was only **flushed**, so the job session held the
  DB write lock for the entire stream. The gateway's per-call `_ledger` (a second session,
  opened when the stream ends) then blocked on `PRAGMA busy_timeout=30000` — the model
  finished instantly but the turn sat "thinking" ~30 s, and the ledger silently dropped
  the audit row (`except Exception: pass`). Fix: `answer_streaming` now **commits the
  pre-stream writes before the model call** (releases the lock during streaming;
  `expire_on_commit=False` keeps the session usable), and `_ledger` failures are now
  **logged** (`ai_interaction_ledger_failed`) instead of swallowed so lock/storage
  problems surface. Regression test `tests/test_chat_lock.py` proves the registry write is
  visible to a second connection before streaming begins. Backend 625 tests green.

- 2026-08-26 — **Per-capability default task models + per-task override (ADR-088,
  migration 0041).** Settings → Tasks gains a pinned **Default models** section — one
  default (primary + fallback) per capability (`text`/`vision`/`embeddings`) backed by a
  new `default_task_assignments` table. Every task row's model dropdown starts at
  **"(Inherit default)"**; picking a custom model makes it an override, clearing it
  inherits again. Gateway `_resolve_chain` null-coalesces task → capability default
  (`model = task.model_id ?? default(requires).model_id`, same for fallback), so partial
  overrides keep the default fallback and deleting an assignment falls back to the
  default; budgets stay per-task. API: `GET/PUT /api/v1/tasks/defaults` +
  `PUT /tasks/defaults/{requires}`; `TaskOut` gains `inherits_default` +
  `default_model_label`/`default_fallback_model_label`. Capability validation shared
  (`assign_task`/`assign_default_task` → `_check_capability`); provider/model deletion
  nulls default rows and backup restore reseeds them. Backend 624 · frontend 709 tests
  green.

- 2026-08-26 — **AI gateway best-practices alignment (plan 38, ADR-085…087).** (a)
  `reasoning_effort` now reaches **Google** too — filtered to `ChatGoogleGenerativeAI`'s
  accepted set (`minimal/low/medium/high`); out-of-set values (e.g. Anthropic `max` stored on
  a Gemini model) are dropped to the provider default instead of failing model construction
  (google-genai's field is a pydantic `Literal`). OpenAI/Anthropic forwarding unchanged
  (Anthropic also filters to its own set — fixes the same latent crash for `none` stored on a
  Claude model — and the stale `model_kwargs` splat + `# type: ignore[call-arg]` is gone).
  (b) `generate_structured` now calls `.with_structured_output(include_raw=True)` so the
  `ai_interactions` ledger bills **real `usage_metadata` tokens** (incl. 37D cache_read) for
  structured tasks (quizgen/exgen/flashcards/pattern.discover/rubric) instead of `len//4`
  estimates; a `parsed is None` (provider-reported parsing error) degrades to plain generate
  exactly like an unsupported error. (c) New `structured_output_supported()` pre-gate:
  `generate_structured` skips the fast path without a round trip when the model profile
  (`model.profile["structured_output"]`, models.dev-backed) confidently says unsupported,
  falling through to the fallback chain; unknown profiles keep the error-based degrade.
  (d) Cleanups: hoisted `chat_native_schemas`/`stream_message_chunks` to the gateway's top
  imports (deleted redundant local re-imports) and the injected `httpx.Client` now sets
  `follow_redirects=True` like LangChain's own clients. Backend 620 · frontend 706 tests
  green.

- 2026-08-26 — **Chat turns surface persisted warnings (migration 0040).** `chat_messages`
  gains a `warnings` list, surfaced in `MessageOut` and rendered as a subtle ⚠ notice under
  the message bubble (survives refresh — it's on the row). First consumer: when semantic
  search is on but the embeddings call can't run (no embeddings model assigned, or the
  embeddings API failed), the turn persists *"Semantic search is on, but … — using keyword
  search for this answer."* instead of silently degrading to FTS. The general
  warnings field gives future turn-level errors/warnings a home. Backend 611 · frontend 706
  tests green.

- 2026-08-26 — **Query embeddings can be disabled: global preference + per-chat override
  (migration 0039).** Settings → Search adds a global *Use semantic search (embeddings)*
  toggle (`profiles.preferences.use_embeddings`, default on), and the chat header gains a ✦
  toggle that pins *this chat* to keyword-only or semantic search (`chat_sessions.
  use_embeddings`, null = follow the global default). When off, chat retrieval skips the live
  query-embedding call and uses FTS keyword search only — your query text stays local and the
  embeddings API round-trip per turn is saved. The toggle only gates the *query* embedding;
  stored vectors and other features are untouched. Backend 609 · frontend 706 tests green.

- 2026-08-26 — **Per-model `reasoning_effort` setting (migration 0038).** Models gain a
  `reasoning_effort` field in Settings → Providers (edit model): the gateway passes it to
  `ChatOpenAI`/`ChatAnthropic` when set, so a reasoning model like `gpt-5.6-luna` can use
  `none` to enable function tools (OpenAI's own suggestion — previously a hard 400), or
  `low/medium/high` to control cost/latency vs reasoning depth (Anthropic accepts
  `max/xhigh/high/medium/low`). Empty clears it back to the provider default. Backend 604 ·
  frontend 706 tests green.

- 2026-08-26 — **Native-tool auto-degrade + honest failure UX for chat turns.** When a
  `tools`-capped model's endpoint rejects the `.bind_tools()` payload (e.g. OpenAI "Function
  tools with reasoning_effort are not supported for gpt-5.6-luna"), the turn now **degrades to
  the prompt-tool grammar for that model** — immediately retried on the same round, and
  remembered in-memory per provider+model so later turns skip native calling (the Settings
  `tools` override remains the durable fix). Separately, a **provider failure before the first
  streamed chunk no longer persists an empty assistant message** and leaves the UI stuck: it
  now re-raises so the frontend shows the `turn_error` banner (mid-stream failures still
  persist the partial prefix with `trace.stream_interrupted`, per plan 37A). Root cause
  diagnosed from the persisted trace: the model was capped `tools` but OpenAI rejects tools for
  it because reasoning is on by default. Backend 602 tests green.

- 2026-08-26 — **Job runner hardening: worker pool, startup reclaim of interrupted jobs, and
  real failure logging.** The background `JobRunner` (ADR-010) now runs a **pool of 4 worker
  threads** instead of one, so a long OCR no longer blocks chat turns; on **startup it reclaims
  stale `running` jobs left by a restart** (uvicorn `--reload` used to strand a turn forever —
  the "message sent but nothing happens" bug) by marking them `failed` with an
  "interrupted: the backend restarted" error; and **job failures are logged** via structlog
  (`job_failed`, `job_timed_out`, `job_claim_failed`) instead of being silently recorded on the
  jobs row only. An optional per-job timeout (`job_timeout_sec`) is available but off by
  default (a thread-based timeout can't stop a hung handler, only bound the job record). The
  test suite now configures structlog to route through stdlib logging. Backend 600 tests green
  (a pre-existing xdist flake in `test_delete_cascades_subtree` passes in isolation).

- 2026-08-26 — **Prompt caching + real cache accounting for chat turns (plan 37D, ADR-084,
  migration 0037).** Chat turns send Anthropic `cache_control: {type:"ephemeral"}` on the
  first system block (the invariant prefix — system base + tool docs + context manifest) so
  back-to-back turns in a session pay cache-read rates on the stable prefix; OpenAI prefix
  caching is automatic and its cached tokens are now accounted. The `ai_interactions` ledger
  records **`cached_input_tokens`** from provider `usage_metadata` and discounts cost
  (cached input at 0.1× the input rate) — Settings→Tasks spend now reflects real provider
  numbers including cache hits. Google explicit `cachedContent` remains descoped. Migration
  0037 adds the additive column; backend 596 · frontend 706 tests green.

- 2026-08-26 — **Structured JSON generation is a pre-validation fast path on capable models
  (plan 37C, ADR-083).** `LLMGateway.generate_structured` uses LangChain's
  `.with_structured_output()` (cap-gated on `tools`) so quizgen/exgen/flashcards/pattern.
  discover/rubric drafts arrive as schema-shaped JSON on the first round (fewer repair
  rounds); the permissive Pydantic schemas (root wrapper + `extra="allow"` elements) guarantee
  *shape* while the deterministic validators remain the sole gate on *content* (distractor==
  answer still trips repair). Any schema-unsupported error or unassigned task degrades to the
  plain `generate`+`extract_json_object` path — generation never breaks, it just skips the
  fast path. Repair loop, audit, and round caps unchanged. Backend 595 · frontend 706 tests
  green.

- 2026-08-26 — **Chat tools become real function calls on native-capable models (plan 37B,
  ADR-082).** When the assigned model has the `tools` capability, the gateway binds the chat
  tool schemas (generated from the same catalogs as the prompt — CALC/SYMPY/READ/STATE/PLOT +
  COURSES/NODE_*) via `.bind_tools()` and streams each structured call as a `tool_call` event;
  `ChatService.answer_streaming` runs the *same* deterministic execution body (budgets, WS
  `tool_call` cards, `chat_messages.tool_calls` persistence) and feeds results back as real
  `ToolMessage`s instead of the "Verified tool results" system message. Text-only/local models
  keep the exact prompt grammar (`TOOL_LINE_RE`) — one `use_native_tools` gate, byte-identical
  `tool_call` events, so the frontend cards/timeline can't tell which path ran. The native
  system prompt drops the tool-line grammar (schemas carry the contract); the fallback prompt
  is untouched. Deferred: auto-degrade when a model's `tools` cap is a false positive (Settings
  `tools` override remains the durable fix). Backend 589 · frontend 706 tests green.

- 2026-08-26 — **The AI gateway moves to LangChain chat models behind an unchanged surface
  (plan 37A, ADR-081).** `LLMGateway`'s hand-rolled provider adapters (`_call_google/`
  `_call_openai/_call_anthropic` + `_stream_*` SSE parsers) are replaced by LangChain's
  per-provider chat models (`ChatOpenAI`/`ChatAnthropic`/`ChatGoogleGenerativeAI`; Ollama
  stays on the `openai_compatible` preset) — the gateway's `resolve`/`generate`/`stream`/
  `stream_events` surface, the budget gate, the keyring read, and the `ai_interactions`
  ledger are unchanged, so every caller keeps working. New: a **first-class retry loop**
  (transient-only: status ≥500/429 or an `httpx.HTTPError` cause; streams retry only before
  the first chunk) and the ADR-029 fallback chain is now real at the transport level —
  `[primary, fallback]` tried in order, with the `_ledger` row and chat `trace` attributed
  to the **answering** model (was: no retries, no fallback). **Real `usage_metadata` token
  counts** replace the `len//4` estimate (estimate kept only as the offline/mock fallback),
  so Settings→Tasks spend figures reflect provider numbers. Reasoning deltas survive the
  swap: OpenAI-compatible `reasoning_content` (via a `CaChatOpenAI` subclass — `ChatOpenAI`
  drops it) and Anthropic/Google `thinking` blocks. **Mid-stream chat failures now end
  honestly**: no replay/restart, the streamed prefix is persisted with
  `trace.stream_interrupted` + an emitted `stream_interrupted` event (services/chat.py).
  Testability without network is preserved (injected `httpx.MockTransport` client) **and
  enforced by a session-wide socket-blocking suite guard**; a telemetry test asserts no
  `LANGSMITH_*`/`LANGCHAIN_TRACING_V2` is ever set. Shared message dataclasses moved to
  `app/ai/types.py` (re-exported by `gateway.py`). Backend 581 · frontend 706 tests green.

- 2026-08-25 — **The tutor's inner thinking streams live, with a show/hide toggle.** When the
  model exposes reasoning (OpenAI `reasoning_content`, Anthropic `thinking_delta`, Google
  `thought`), the chat now renders it as it arrives in a collapsible **Thinking** bubble above
  the answer (separate from the answer text — reasoning deltas no longer leak into the answer
  stream), with a chevron to hide/show it persisted to `ca-chat-reasoning-open`
  (`ReasoningBubble`). The reasoning is also kept in the per-message `trace.thinking` (plan 35)
  so history shows it via the `TraceTimeline` "Reasoning" disclosure. Frontend 706 tests green
  · backend untouched.

- 2026-08-25 — **The tutor can now browse the learner's data, and the MCP server is documented
  in Settings (plan 36, ADR-080).** The MCP resource tools are a **single shared registry**
  (`mcp_resources.py` module-level functions + `RESOURCE_TOOLS`), so external agents (MCP) and
  the chat call the same read-only functions with no drift. The chat gains a curated subset —
  `COURSES`, `NODE_OVERVIEW`, `NODE_QUIZZES`, `NODE_EXERCISES`, `NODE_NOTES` — using the
  existing line grammar (`here`/`T#` node-handle resolution, `MAX_RESOURCE_ROUNDS = 5` budget,
  `tool_call` events with timing, stripped from the answer); `get_node_context`/materials/
  concepts stay MCP-only (redundant with the chat's own context). `GET /ai/tools` now returns
  only the chat-callable tools (the "Tools the AI can use" dialog no longer lists external-
  agent tools), `GET /ai/mcp` returns the MCP tool list + launch command, and a new
  **Settings → MCP server** tab documents the command (Copy button) and the read-only tool
  list. En route fixed a tool-line regex bug (`\s` separator swallowed consecutive no-arg tool
  lines). Backend 571 · frontend 703 tests green.

- 2026-08-25 — **The tutor now streams the real answer (not the tool line) and exposes turn
  timing.** Two problems made a turn look like "still processing with no text": (1) only the
  *first* LLM round streamed — and that round is usually just a tool line, so the raw
  `CALC …`/`SYMPY …` text flashed in the answer while the *actual* answer (the final
  non-tool round) was generated with a silent `generate()` and never streamed. Now **every
  round streams**, and **tool lines are stripped from the stream** (`TOOL_LINE_RE` line
  filter inside the coalescer) so they only ever appear as `ToolCallCard`s — the final answer
  streams live and no tool text leaks into the bubble. (2) No instrumentation: `started` now
  starts before context assembly, and `answer_streaming` logs `chat_turn_timing` events for
  each phase (`context` / `thinking` / `repairing` / `finalize`) with per-phase ms — together
  with the per-message `trace` (round/tool timings shown in `TraceTimeline`) this pinpoints
  any remaining hang. Backend 565 · frontend 701 tests green.

- 2026-08-25 — **Fix: the tutor now finishes the instant the answer completes (no more
  end-of-turn hang).** The finish signal was being delayed on the *backend*: `answer_streaming`
  emitted a `stream_delta` WS frame **per token**, so the `assistant_message` "done" event sat
  at the back of an asyncio queue behind hundreds/thousands of `send_json` calls. Deltas are
  now **coalesced** server-side (accumulated and flushed every ~30 ms, `STREAM_DELTA_INTERVAL`)
  — a turn now emits tens of frames, not thousands — so the finish event follows immediately.
  Two further hardening fixes: `answer_streaming` **commits the message before emitting**
  `assistant_message` (previously the frontend's invalidate-refetch could race the
  job-thread commit and miss the new message), and the chat panel regains a **2 s** refetch
  fallback (down from the old 800 ms that raced the stream) purely as a WS-loss safety net.
  Backend 564 · frontend 701 tests green.

- 2026-08-25 — **The tutor chat is observant and no longer freezes on long answers (plan 35,
  ADR-077…079).** Three fixes land together. **(1) Streaming is incremental and memoized:**
  the per-token full-tree markdown+KaTeX re-render (the O(n²) freeze — every token re-parsed
  the whole answer *and* re-rendered all history bubbles) is replaced by a `useStreamBuffer`
  hook that batches deltas to one commit per animation frame, an isolated `StreamingBubble`
  that renders plain markdown mid-stream (KaTeX is applied once on the finalized message), a
  `React.memo`'d `MessageBubble`, and removal of the `refetchInterval` 800 ms poll that raced
  the WS stream; auto-scroll moves to `requestAnimationFrame`. **(2) Every turn has a trace:**
  migration **0036** adds `chat_messages.trace` — `run_id`, `model`, `latency_ms`,
  input/output tokens, `repair_rounds`, and a `rounds[]` timeline (per-round
  start/duration/phase), streamed live as `elapsed_ms` on every frame + `phase` events +
  `tool_call` frames carrying `status`/`start_ms`/`duration_ms` (persisted on the message's
  `tool_calls` too). Provider reasoning (OpenAI `reasoning_content`, Anthropic
  `thinking_delta`, Google `thought`) is captured best-effort into `trace.thinking` via a new
  `Gateway.stream_events` (`stream()` now filters text-only), kept out of the visible answer.
  **(3) Tool calls are a registry:** `features/chat/tools/registry.tsx` (`getToolMeta` +
  per-tool result views) backs a slim `ToolCallCard` shell with duration/status chips; the new
  `TraceTimeline` renders the phase/tool timeline with proportional bars plus a Reasoning
  disclosure, and `TurnTraceStatus` shows the live phase + elapsed timer while streaming.
  Backend 563 · frontend 701 tests green.

- 2026-08-25 — **The sidebar tutor's history and streaming now match the full page.** Two
  follow-ups to the sidepanel chat: (1) picking a chat in the sidebar's history popover (and
  its *New chat* / delete actions) now operates within the sidepanel — `ChatSessionList`
  gained `onSelectSession`/`onNewChat`/`activeSessionId`, so the sidebar adopts the chosen
  session (or clears to a new chat) instead of jumping to `/chat/:chatId` (the full page
  keeps navigating as before) and the adopted session is highlighted. (2) The **Thinking…**
  indicator now shows while the first answer streams in the sidebar: `ChatPanel` skips its
  reset-on-session-change when the new session is the one it just created (`adoptingRef`), so
  the in-flight turn's pending/stream state survives the adoption instead of being cleared.
  Frontend 687 tests green (+5) · backend untouched.

- 2026-08-25 — **Fix: the sidebar tutor keeps its sidepanel state when the first answer
  streams in.** A new chat in the sidebar panel used to lazily create its session on first
  send and then jump to the full-page `/chat/:chatId` route (the panel "maximized" as soon as
  the AI started answering). Now the panel stays open in sidepanel mode and **adopts the
  just-created session in place**: `ChatPanel` reports the whole `ChatSession` up through
  `onSessionCreated`, `AppShell` stores it as the sidebar's session and feeds its `id` back
  into the `ChatPanel.sessionId` prop — so the WS stream and follow-up turns target the same
  session while the panel stays a sidepanel. The expand action still opens that session
  full-page via its `public_id`; closing the panel clears the adopted session. Frontend 682
  tests green (+2) · backend untouched.

- 2026-08-25 — **The tutor chat shows its tool calls as collapsible cards.** Every tool the
  model invokes during a turn — `CALC`, `SYMPY`, `READ`, `STATE`, `PLOT` — now streams to the
  UI as a **tool card** (icon + tool name + argument) under the reply, and is **persisted** on
  the message (migration **0035** `chat_messages.tool_calls`) so history shows it too. Click a
  card to expand and inspect the full argument and, for math tools, the exact result; READ
  shows a `read N chars` summary and its content is still never stored (model-only, per the
  READ contract). The old single `tool_round` phase event is replaced by per-call `tool_call`
  events carrying `name`/`argument`/`phase`/`result`, and the AG-UI adapter now maps each call
  to `ToolCallStart`→`ToolCallArgs`→`ToolCallEnd`→`ToolCallResult` (plan 34 contract). New
  `ToolCallCard` component + i18n keys; `MessageOut` gains `tool_calls`. Backend 559 · frontend
  680 tests green.

- 2026-08-24 — **A `--reset` flag wipes local data for a clean slate.** `pnpm dev|webapp|app
  --reset` deletes `app.db` (+ its `-wal`/`-shm` sidecars), `blobs/`, `cache/`, `thumbnails/`
  and `import-inbox/` before starting, with a confirmation prompt by default (`--yes` skips
  it, `--all` also deletes `backups/`). It's implemented as `python -m courseassistant reset`
  (`app/reset.py`), resolving the data dir from `CA_DATA_DIR`/XDG like the rest of the app and
  killing any process holding the port first. Backend 556 tests green (+2).

- 2026-08-24 — **Migration 0034 is now idempotent** so an interrupted dev run can't wedge the
  DB. The `public_id` migration previously assumed a clean run; if the reloader killed the
  process between `ADD COLUMN` and the version stamp, a restart would crash with
  `duplicate column name: public_id`. It now detects an existing column/index, only backfills
  NULL `public_id`s, and completes/stamps cleanly.

- 2026-08-24 — **Chat conversations are routable by an opaque UUID.** `chat_sessions` gains a
  `public_id` (migration 0034: unique UUID, backfilled for existing rows; the integer `id`
  stays the internal key). URLs now use `/chat/:chatId` (UUID): `/chat` = new chat, and the
  active conversation is **derived from the URL** via a new `useActiveChatSession` hook
  (resolves `public_id → id` from the sessions list) instead of in-memory `useChatStore`
  state (the store is reduced to `open`/`setOpen`). Selecting a chat anywhere — the full-page
  history list, the sidebar history popover, "ask about this node/question", the palette, and
  the tutor launch buttons — navigates to `/chat/:chatId`; `ChatPage` shows a "not found"
  state for stale links. `AskOut` (exercises + quiz) and `SessionOut` now return `public_id`.
  Backend 554 · frontend 679 tests green.

- 2026-08-24 — **Chat history is a searchable, two-pane list.** The sidebar's flat session
  `<select>` is replaced by a proper history UI: a new `ChatSessionList` (`features/chat/`)
  with a **search box**, a **New chat** button, per-chat relative time, an active highlight,
  and per-item rename/delete (kebab menu + confirm + trash undo). The full-page `/chat` route
  is now a **two-pane layout** (history list on the left, conversation on the right), while
  the sidebar panel opens the same list in a popover behind a "Chat history" button showing
  the active chat's title. `GET /chat/sessions` now returns `created_at` (`SessionOut`) so the
  list can show recency. Backend 554 · frontend 680 tests green (+5 frontend).

- 2026-08-24 — **The tutor chat is a first-class page and a resizable sidebar.** The chat is
  no longer sidebar-only: a new `/chat` route renders the tutor full-page (`features/chat/
  ChatPage`), and the sidebar panel gained an **expand** action (→ full page) while the full
  page gained a **collapse** action (→ back to the sidebar) — both preserve the active
  session via the shared `useChatStore`. The tutor is also a top-level nav module (`nav.chat`
  = "Tutor", `Bot` icon) in the Study group and a command-palette entry, and the sidebar's
  width is now **draggable** via a pointer-capture resize handle (320–720 px, persisted to
  `ca-chat-width` in localStorage). `ChatPanel` takes `variant="sidebar"|"page"` +
  `onExpand`/`onCollapse`. Frontend 676 tests green (+4) · backend untouched.

- 2026-08-24 — **Fix: chart/geo blocks no longer overflow the chat card.** Plotly and JSXGraph
  set a fixed inline pixel size on their container, which blew past the message bubble's
  `max-w-[92%]` (a flex item whose `min-width: auto` refused to shrink below the chart's
  intrinsic width), overlaying and breaking the UI. Three modern fixes: the message bubble
  gets `min-w-0` (flex items may now shrink), the chart/geo containers get `min-w-0
  overflow-hidden` + a fixed `h-72` height (so the libs size to the constrained card), and
  `PlotlyChart` adds a `ResizeObserver` calling `Plotly.Plots.resize` so the chart re-flows
  when the card/sidebar resizes instead of only on window resize. Frontend 672 tests green
  (+1) · backend untouched.

- 2026-08-24 — **Fix: the tutor no longer hangs when generating a chart/widget answer, and
  follow-up turns survive a widget-first reply.** Two bugs. (1) The chat `max_words` contract
  counted fenced `` ```chart ``/`` ```widget `` JSON as prose words, so any chart (PLOT's ~400
  sampled points) blew past the 400-word cap and forced a redundant non-streaming repair
  round — the UI sat on the thinking dots with no stream events ("stuck with no log"). The
  `_max_words` validator now excludes fenced blocks from the word count (prose-only). (2)
  `_build_messages` read `entry.blocks[0]["md"]`, which raised `KeyError` on the next turn
  whenever a prior assistant message started with a widget/chart block (no `md` key); it now
  renders history through `blocks_to_md`. Backend 554 tests green (+2) · frontend untouched.

- 2026-08-24 — **Widget grammar is single-sourced and injected into both AI prompts (plan
  34 follow-up).** `app/ai/widgets.py` now owns `WIDGET_SPECS` (name → description + props
  for all 7 widgets); `WIDGET_NAMES` derives from it and `build_widget_doc()` renders it
  into `CHAT_WIDGET_DOC` (```chart/```widget fence convention) and `EXGEN_WIDGET_DOC`
  (`steps[].widgets` array). `services/chat.py` appends `CHAT_WIDGET_DOC` to the tutor
  system prompt and `exgen.py` appends `EXGEN_WIDGET_DOC` to the exercise prompt — the
  hardcoded widget text is removed from `CHAT_ANSWER_SYSTEM`/`EXGEN_SYSTEM`, so the model
  always knows every widget + its props and the prompt can't drift from the validator.
  Backend 552 tests green (+4) · frontend untouched.

- 2026-08-24 — **Plan 34 slice 34F (ADR-076): the tutor chat plots and shows interactive
  widgets, and reads their state back.** `PLOT <expr>` joins the chat tool catalog —
  `plot_function` samples f(x) deterministically via SymPy `lambdify` over [-10,10] (non-finite
  → null gaps) and returns plotly scatter JSON the model wraps in a ` ```chart ` fence;
  `parse_answer_blocks` splits the final answer on ` ```chart `/ ` ```widget ` fences into
  `ChatMessage.blocks` (returned in `MessageOut`, mentions attached to text blocks, `markdown` =
  the joined text), and `CHAT_ANSWER_SYSTEM` teaches the fence convention. The frontend
  `MessageBubble` renders `message.blocks` and wires `onWidgetStateChange` → `diffState` →
  `PATCH /chat/messages/{id}/state` (the 34D channel), so a checklist the tutor shows the
  student flows back for the next turn's `STATE` read. **Plan 34 complete.** Backend 548 tests
  green (+10) · frontend 671 (+1).

- 2026-08-24 — **Plan 34 slice 34E (ADR-075): exercises carry interactive widget blocks and
  record their state.** `EXGEN_SYSTEM` teaches an optional `steps[].widgets` list; `_step_problems`
  validates each widget via the 34B grammar and `ExgenService.generate` appends them after the
  step's `prompt_md` text block — so a generated exercise step can render a chart to read or a
  checklist to complete. `AnswerIn` gains `state`; `submit_step_answer` persists it on
  `StepAttempt.state` (the 34D column). Frontend: `submitStepAnswer` takes an optional `state`
  arg, and `Player.tsx` collects step-widget state via `BlockRenderer.onWidgetStateChange` and
  submits it (reset on step advance). Widget-answer grading (numberline/graph-sketch) stays
  deferred. Backend 538 tests green (+3) · frontend 670 (+1).

- 2026-08-24 — **Plan 34 slice 34D (ADR-074): widget state is a first-class, bidirectional
  channel.** Migration 0033 adds `chat_messages.state` + `step_attempts.state` (JSON). New
  `PATCH /chat/messages/{id}/state` reduces an RFC-6902 JSON-Patch delta with the 34A
  `apply_patch` reducer (deep-copies the stored state first, so SQLAlchemy JSON
  change-detection can't swallow the in-place mutation), enforces a 100 KB cap, audits
  (`context_type=widget_state`), and returns the reduced snapshot. The `STATE <widget_id>`
  line joins the chat tool catalog (`app/ai/tools.py`; extracted/stripped like `READ`, 3/turn
  budget, model-only) backed by `_read_widget_state` (`services/chat.py`) + `read_widget_state`
  (`app/ai/widgets.py`) — the tutor reads what the student ticked/slid/plotted. Frontend:
  `BlockRenderer.onWidgetStateChange` (per-widget full-state callback) + `lib/state.ts`
  `diffState` (flat JSON-Patch diff). Backend 535 tests green (+7) · frontend 669 (+6). The
  context resolver's `widget_state` slot, the live WS snapshot read, exercise-widget grading
  and the chat-panel PATCH wiring land in 34E/34F.

- 2026-08-24 — **Plan 34 slice 34C (ADR-073): `chart` and `geo` blocks finally render —
  Plotly.js and JSXGraph, both lazy-loaded.** `ChartBlockView` now draws interactive Plotly
  charts through a new `PlotlyChart` component on `plotly.js-dist-min`'s direct API (no
  `react-plotly.js`), with transparent backgrounds (theme-agnostic) and
  `transition:{duration:0}` under `prefers-reduced-motion`; `GeoBlockView` renders draggable
  JSXGraph constructions through a new `JsxGraphBoard` that runs the block's `jsxgraph` string
  as JessieCode (`board.jc.parse`), freeing the board on unmount. Both dynamic-import so
  plotly + jsxgraph stay out of the boot chunk; the widget registry's `chart`/`geo` entries
  delegate to the same two components. `src/types/plotly.d.ts` adds the ambient module type.
  Frontend 663 tests green (+9). **Finding**: jsxgraph's bundled JessieCode/math evaluation
  uses `eval` internally (library code) — acceptable in the local sandboxed shell, noted as an
  open issue.

- 2026-08-24 — **Plan 34 slice 34B (ADR-072): a `widget` block type + typed component
  registry make interactive UI a first-class block.** `BlockRenderer` gains a `widget`
  dispatch resolved through `components/widgets/registry.tsx` (`getWidgetComponent`): real
  interactive widgets `checklist`/`choice`/`slider`/`equation_input`/`numberline` (each
  driven by a shared `useWidgetState` hook with an optional `onStateChange` seam for the 34D
  state channel), plus `chart`/`geo` placeholder entries pending 34C's Plotly/JSXGraph
  renderers. An unknown widget name renders the safe "unsupported" card — no raw HTML, ever.
  Backend: `app/ai/widgets.py` (`validate_widget_block`/`validate_widget_blocks`) enforces the
  widget grammar — known-name whitelist, per-widget prop typing (required prompt/id, list
  counts + length caps, numeric range sanity, plotly/jsxgraph presence) — so a malformed
  widget spec never reaches the renderer. One i18n key (`widgets.numberlineHint`). Backend 528
  tests green (+15) · frontend 654 tests green (+7).

- 2026-08-24 — **Plan 34 slice 34A (ADR-071): the AG-UI event + state contract lands as a
  new `app/agui/` module (backend).** The agent↔UI contract for interactive widgets is now
  typed and vendored rather than ad-hoc: `agui/events.py` (Pydantic v2 models for the AG-UI
  vocabulary — lifecycle `RunStarted/RunFinished/RunError` + `StepStarted/StepFinished`, text
  `TextMessageStart/Content/End`, tool `ToolCallStart/Args/End/Result`, state
  `StateSnapshot`/`StateDelta`/`MessagesSnapshot`, activity, and `Custom`/`Raw` — with
  camelCase wire aliases and an `EventType` StrEnum), `agui/state.py` (`apply_patch` RFC-6902
  JSON-Patch reducer incl. move/copy/test + pointer escapes, `apply_deltas`, `StateStore`
  with `snapshot()`), and `agui/mapping.py` (`ChatStreamAdapter`/`map_stream` mapping the
  current chat emit stream — `stream_start`/`stream_delta`/`tool_round`/`turn_error`/
  `assistant_message` — losslessly to AG-UI events with `Custom` fallthrough). The `ag-ui-protocol`
  SDK is deliberately **not** a dependency yet (pre-1.0 churn; shapes stay compatible for a
  later swap). Live `/ws` re-labelling is deferred to 34D. Backend 513 tests green (+27 AG-UI:
  events/state/mapping) · frontend untouched.

- 2026-08-23 — **Subsection cards in the workspace Overview tab show each node's
  description (user request).** The child cards under the Subsections heading now render
  `child.summary` (line-clamped to two lines, full text on hover) under the objectives ·
  materials line when a description is set — the same field the node settings popover
  edits. Backend untouched (`node_with_children` already returned `summary`); frontend
  647 tests (+1: child cards render the description when set, omit it when null).

- 2026-08-23 — **Course cards on the Courses page show the course description
  (user request).** The overview list's cards render `course.description` (line-clamped
  to two lines, full text on hover/title) under the subject · material-count line when a
  description is set — the course settings popover (root node) is where it's edited, so
  the same field now surfaces in the list too. Frontend 646 tests (+1: cards render the
  description when set, omit it when null) · backend untouched (486 verified).

- 2026-08-23 — **The sidebar's "Dev" nav group is removed; the rendering spike moves
  under Settings as a **Developer** tab (user request; refined 2026-08-23 — it's a
  proper Settings tab, and it **embeds the spike content inline** rather than linking
  out).** The main navigation no longer has a Dev section (its only item, the rendering
  spike at `/spike`, was dev tooling cluttering the sidebar). Settings gained a
  **Developer** tab (`DeveloperTab`, routable `?tab=developer`) that renders the spike's
  four verification cards (KaTeX / Mermaid / MathLive / canvas) directly in the tab via
  a new shared `SpikeContent` export (the standalone `/spike` route keeps the full-page
  chrome around the same content). `nav.groupDev`/`nav.spike` i18n keys dropped; new
  `settings.tabs.developer`. Frontend 645 tests (+1: Developer tab shows the spike
  content only when selected; AppShell test now asserts Dev is absent) · backend
  untouched (486 verified).

- 2026-08-23 — **The rendering-spike page's canvas is now the real drawing surface
  (user report: the spike canvas didn't draw properly).** `SpikePage`'s hand-rolled
  `CanvasCard` (raw 2D context, fixed 480×200 size, no pressure/undo/eraser) is replaced
  by the shared `DrawCanvas` (`components/canvas/DrawCanvas.tsx`) — the same component
  notes and material drawings use — so the spike page exercises the production drawing
  stack (logical-width scaling, pressure-sensitive strokes, pen/eraser/color/width
  toolbar, undo/redo/clear). `CanvasCard` is exported for testing; the obsolete
  `spike.canvasClear` i18n key is removed. Frontend 644 tests (+1: spike canvas renders
  the shared DrawCanvas toolbar + canvas) · backend untouched (486 verified).

- 2026-08-23 — **Material/notes viewer drawers get a full-width (maximize) mode
  (user request).** The shared `FocusShell` overlay — used by the material detail
  drawer and the note editor drawer — gains a **⤢ / ⤡ toggle** in the header next to
  Close that expands the panel from its default `w-[min(760px,100vw-2rem)]` drawer to
  the full window width (and back), handy for wide tables and side-by-side
  extraction/original views. The choice is **persisted** in localStorage
  (`ca-focus-fullscreen`) so every overlay honors the last preference. The page
  (non-overlay) FocusShell variant is untouched. New i18n keys
  `focus.expand`/`focus.collapse`. Frontend 643 tests (+2: overlay expand/collapse
  toggle incl. width classes + aria-pressed, page variant hides the toggle) · backend
  untouched (486 verified).

- 2026-08-23 — **The cheat-sheet button is a dropdown menu, and generation is a
  parameterized compose builder (plan 33, ADR-070; user request).** The Overview tab's
  flat "Cheat sheet / Regenerate cheat sheet" button and its separate existing-sheet
  banner are replaced by one menu: no sheet → **Generate cheat sheet…**; sheet exists →
  **Open existing** (opens the material) + **Regenerate cheat sheet…**. Both generate
  items open `GenerateDialog` in `compose` mode with the kind pre-locked to `cheat_sheet`
  (`COMPOSE_KINDS` gained `cheat_sheet`, so the compose kind selector and study launcher
  surface it too), giving generation the full context controls — materials add/exclude,
  notes, concepts, one-time instructions, live context preview — and the composed result
  renders in the overview preview card. **Backend**: the dedicated `POST
  /nodes/{id}/cheatsheet` endpoint and `cheat_sheet_markdown` prompt are retired;
  `POST /materials/compose kind=cheat_sheet` is now the sole cheat-sheet path, so
  regenerate revises the live artifact through the compose pipeline (one material, new
  extraction version, manual edits fed back as revision context — the 2026-08-21
  guarantees preserved, now via the standard pipeline). `TabAction` gained a `menu`
  variant (`TabActionBar` renders the shared `PopoverMenu`), giving every tab the
  dropdown grammar. Fixed a latent i18n bug on the reused path: `generate.action.compose`
  was a missing key, so the compose dialog's primary button rendered the literal key.
  Backend 486 tests (+0/‑1 re-based: compose-persist/regenerate now exercises
  `POST /materials/compose`) · frontend 641 tests (+3: TabActionBar menu, cheat-sheet
  menu open-existing, menu → builder prefill + compose-preview flow) · docs synced.

- 2026-08-23 — **Node creation lives in the Overview action bar, on every node
  (user request).** The root's Structure card and the inner nodes' Subsections
  "Add child" button are retired; `OutlineActions.tsx` (+ its test file) is
  deleted. `OrganizerCard` gained an `extraActions?: TabAction[]` prop appended to
  its `TabActionBar`, and `OverviewTab` now passes it for every node: **Add child**
  on inner nodes, **AI outline + Add node** at the root (parent = the open node,
  so at the root that *is* a top-level node — no separate root-id lookup; both
  paths are one `addNodeHere` mutation). The shared inline title form
  (`NodeCreateForm`) + error row render right under the bar on all nodes, and
  `OutlineDraftView` moved into `NodeWorkspace.tsx` (root-only, after the bar).
  The inner Subsections section keeps its heading + children grid + "No
  subsections yet" empty hint. New i18n keys `courses.childrenTitle` /
  `courses.noChildren`. Behaviors covered at the workspace level (NodeWorkspace
  tests: action-bar placement, root add-node, inner add-child, empty-state first
  child, root no-duplicate, draft prune + commit, draft cancel). Frontend 638
  tests green · backend untouched (487 verified).

- 2026-08-23 — **Fix: exgen rejected valid math — absolute values, `\ln`, and
  coefficient equations didn't parse (user report).** The equivalence-chain parser
  (`app/math/equivalence.py`) rejected legitimate expected answers, so generating a
  partial-fractions exercise failed validation with
  "expected_value does not parse as math". The parser now: converts `|…|` (incl.
  `\left|…\right|`, `\lvert/…\rvert`) to SymPy `Abs(...)` (space-separated so `\ln|x-1|`
  parses), treats `A=1/2` as `A−1/2`, and splits `,`/`;`-separated systems into a
  SymPy `FiniteSet` — so `A=1/2,\;B=-1/2` validates *and* grades order-insensitively,
  and `\frac{1}{2}\ln|x-1|-\frac{1}{2}\ln|x+1|+C` / `\ln\left|\frac{x-1}{x+1}\right|`
  parse cleanly. `\,`/`\quad`/`\qquad` normalize to spaces. Backend 487 tests (+4
  equivalence: abs+ln parse, equations/systems parse, order-insensitive system
  equivalence + wrong-system rejection, relational `>=` skip) · frontend untouched.

- 2026-08-23 — **Fix: "database is locked" when generating practice (user report).**
  `generate_quiz` flushed the activity row *before* running the LLM, so the request
  held the SQLite write lock for the whole ~9 s generation. The practice builder fires
  quiz + exercise requests in parallel, so the exercise's final flush blocked on the
  quiz's held lock and failed after the 5 s busy-timeout. Fixes: **`generate_quiz`
  commits the activity before the LLM** (releasing the lock; on generation failure the
  activity is deleted — no orphaned empty quiz) so all generation writes are short
  bursts; **`busy_timeout` raised 5000 → 30000** (`storage/db.py`) so transient
  write-write overlap waits-and-retries instead of erroring; **postprocess embedding
  commits per batch** (`pipelines/postprocess.py`) so background jobs never hold the
  write lock across an embedder call. Backend 483 tests (+1: failed quiz generation
  leaves no orphaned activity) · frontend untouched.

- 2026-08-23 — **The generate/practice dialog's materials + notes context picker is
  modernized: no more checkbox lists (user request; plan 32 D partial).** The
  **Materials** section no longer renders every in-scope material as a scrollable
  checkbox list — in-scope materials stay implicitly included ("All N materials in
  this scope are included"), and only the *deltas* render as removable chips:
  **excluded** (muted, ✕ re-includes) and **added** (accent, ✕ removes). Two menu
  affordances open the existing feature-rich `MaterialPickerDialog` in select mode:
  **Add material…** (pulls out-of-scope materials in → `include_material_ids`) and
  **Exclude from context…** (opts in-scope ones out → `exclude_material_ids`); the
  picker gained optional `confirmLabel` / `lockedLabel` props for the exclude
  flavour. The **Notes as context** section's checkbox list is replaced by an
  **Add note…** menu opening a new feature-rich **`NotePickerDialog`**
  (`features/notes/NotePickerDialog.tsx`): fuzzy search, tag-filter chips, multi-
  select with check indicators, "select all shown", load-more pagination, selected
  count — each attached note is a removable chip (`noteTitles` map state). Native
  `<input type=checkbox>` is gone from the whole flow: a new shared `CheckIndicator`
  (`components/ui/CheckIndicator.tsx`, button `role="checkbox"`) replaces the
  MaterialRow checkbox, so the material picker rows use it too. Backend untouched
  (context semantics unchanged: `exclude_material_ids` / `include_material_ids` /
  `note_ids`). Frontend 636 tests green (+9: NotePickerDialog suite ×6, GenerateDialog
  added-chip remove / excluded re-include / note-chip remove) · backend untouched
  (483 verified).

- 2026-08-22 — **Item info popovers: hover-revealed ℹ that opens on hover or
  click (user request).** The shared `Popover` gains an `openOnHover` mode (opens on
  trigger mouse-enter, closes on leave, click still toggles), and `InfoButton`/
  `FieldLabel` use it. All practice-builder options get details popovers too: quiz
  question types + exercise kinds each show a per-chip ℹ, and the topic/count/
  shuffle/steps/difficulty fields show one next to their label. Buttons are revealed
  only on row/field hover (the `group` pattern), everywhere — EntityItems rows and
  form controls. Frontend 627 tests green (+4: hover-open, click-toggles, practice
  chip/field details) · backend untouched (483 verified).

- 2026-08-22 — **Modular item info popover (user request).** New shared
  `InfoButton` component (`components/ui/InfoButton.tsx`): a hover-revealed ℹ icon
  that opens the shared `Popover` with details. `EntityItemEntry` gains optional
  `info`/`infoTitle`; `EntityItems` renders the button next to the title in both list
  and grid layouts (popover clicks never trigger row selection or open). Wired into
  the unified Practice tab: quiz/exercise rows show scope + question/step counts in
  the popup. Frontend 623 tests green (+3 info-button) · backend untouched (483
  verified).

- 2026-08-22 — **Plan 32 (ADR-069): Practice becomes one section + one builder
  (user request).** The workspace Practice tab merges the two parallel quiz/exercise
  lists into **one list with kind badges** and one primary **New practice** action
  (`PracticeTab` extracted to `features/practice/PracticeTab.tsx`); unified
  selection/move/delete/rename/context-menu grammar across the union (quizzes keep
  export/.qpkg/print/similar per-kind menu items). **`GenerateDialog` gains a
  `practice` task mode** — a format picker grid spanning quiz question types
  (`single`/`multi`/`truefalse`/`text`/`numeric`/`equation`) **and** exercise kinds
  (`multi_step`/`matching`/`ordering`/`categorize`/`fill_blank`/`explain`/
  `error_spot`/`correct_solution`), free mixing (a quiz of chosen types + one exercise
  per chosen kind, each through its own pipeline), a **shuffle** toggle, and the
  existing context/scope/hint/preview section unchanged. **Backend**: `quiz.generate`
  accepts `question_types` (allowlist — quizgen blueprint cycles only those types, the
  repair-loop validator rejects off-list drafts, unknown type → 422) and `shuffle`
  (persists questions in randomized order; single/multi option order shuffled with
  answers + misconception tags remapped). **`QuizRunner` gains a per-attempt Shuffle
  toggle** (persisted in localStorage, default off): randomizes question order and,
  for single/multi, option display order while mapping submitted choices back to the
  stored indices — grading/analytics untouched. Engines, exports, mistake notebook and
  both runners are unchanged (ADR-045: quizzes and exercises stay separate assessment
  entities). Backend 483 · frontend 620 tests green. Slice 32D (materials/notes
  display + unified Ctrl+N creation palette) is documented in `dev/plans/32-…md` as
  the next slice, not yet implemented.

- 2026-08-22 — **UX: creating a text/Markdown file no longer closes the dialog —
  Save keeps you editing (user request).** The new-file dialog's **Create** now
  saves the file and **stays open**: a "Saved — keep editing" note appears, the
  name field locks, and the footer switches to **Save** (disabled while there's
  nothing new) + **Done** (closes). Save writes the current content to the
  already-created material via `editExtraction`; drawings added after the first
  save are committed to the material on the next Save (the dialog remaps its
  local placeholder refs to the real drawing ids after every save, so inline
  drawings stay correct). A deduplicated create (identical content already
  exists) still closes. New API helpers `createTextMaterial` / `updateTextMaterial`
  replace the one-shot `createTextFileWithDrawings` (removed); both LibraryPage
  and NodeWorkspace wire the new callbacks, and the Library's ingest-job
  progress tracking still works (job id rides on the edit state). Frontend 614
  tests (+11 dialog save-flow, reworked create tests) · backend untouched (479
  verified).

- 2026-08-22 — **Fix: the AI helper popover re-clamps to the window as it grows
  during streaming, so the bottom never slides past the window edge (user
  report).** The floatable panel already capped its max height/width to the
  viewport, but the position was only computed once on open — while the AI
  response streamed, the panel got taller and its bottom edge dropped below the
  window border. The shared `Popover` now observes the panel with a
  `ResizeObserver` while open and re-runs `updatePosition` on every size change,
  re-clamping both auto- and manual positions so the panel stays fully on-screen
  at every growth step (it also keeps the panel inside the window if the user is
  mid-drag while content grows). The streaming text itself scrolls within the
  capped panel. Frontend 611 tests (+1 growth-clamp regression) · backend
  untouched (479 verified).

- 2026-08-22 — **UX: the AI helper popover is now a movable, resizable floating
  window that always stays inside the app window (user request).** The shared
  `Popover` gains opt-in `resizable` and `movable` props: `resizable` renders eight
  edge/corner handles (drag to resize, clamped to min sizes and the viewport),
  `movable` renders a top grip bar (drag to reposition). Every floatable panel is
  clamped to the window bounds at all times — auto-positioning, dragging and
  resizing all keep it fully on-screen — and its max height/width are capped to the
  viewport, so the AI helper's action buttons (Run/Replace/
  Insert/Regenerate/Discard) are never cut off by the window edge. **Only the text
  scrolls**: the AI helper lays out as a fixed header + scrollable body + pinned
  action buttons, so long results scroll inside the text area while the header
  and buttons stay visible (2026-08-22 follow-up). The AI helper
  enables both (`AiHelperPopover` passes `resizable` + `movable`); other popovers
  (chat, node settings, popover-menu) are untouched (props default off). Frontend
  609 tests (+7: move/clamp/resize-handles ×4, min-size clamp, no-handles default,
  AI helper handles) · backend untouched (479 verified).

- 2026-08-22 — **UX: the AI helper review view renders the result in the same rich
  editor as notes/material instead of raw markdown (user request).** The "done" view now
  shows the generated markdown through a new read-only `MarkdownPreview` — the same
  Tiptap extensions as `MarkdownEditor` (CaMath/CaMermaid/MarkdownTable + the
  tiptap-markdown parser and fidelity helpers), so the preview is exactly what
  Insert/Replace will write into the document (math, diagrams, tables, links all
  render identically). An **Edit ⇄ Preview** toggle switches to the real
  `LazyMarkdownEditor` (full toolbar rich editor) for tweaking before insert, so the
  result edits through the same editor it will land in. CaMath/CaMermaid double-click
  editing is gated on `editor.isEditable` so read-only previews are inert; the popover
  panel's focus-preserving `mousedown` now also lets the embedded editor's
  `[contenteditable]` receive focus. Frontend 603 tests · backend untouched (479
  verified).

- 2026-08-22 — **Fix: the inline AI helper now enables transform presets when text is
  selected with the mouse (plan 31 follow-up; user report).** The real bug: the
  selection is a ref mutation, not React state, so selecting text did not re-render
  `AiHelperPopover` — the popover had already computed its view (presets disabled) in
  its component body, and `Popover` rendered that stale tree when opened. The shared
  `Popover` now accepts **render-prop children** (`children: ReactNode | (() =>
  ReactNode)`), and the AI helper passes a render function that reads the selection
  snapshot (`selectionRef.current`) fresh at open time, so the transform section
  enables the moment the popup renders. Selection is a `MarkdownEditor`
  `onSelectionUpdate` snapshot (kept on non-empty selections; cleared only on a
  focused collapse); the `Popover` also gained opt-in `focusOnOpen={false}` +
  `preserveFocus` (the trigger `mousedown` is prevented) and the panel prevents
  `mousedown` on non-text elements, so the selection highlight survives opening and
  clicking inside the popup. Frontend 602 tests (+1 "selection set after mount is
  picked up on open" regression; popover tests drive the snapshot directly) · backend
  untouched (479 verified).

- 2026-08-22 — **Feature: the shared rich editor gains an inline AI helper — ✨
  toolbar button → popover with transform presets, a free-form prompt, context +
  course-material chips, a streamed preview, and human-gated insertion (plan 31,
  ADR-068; user request).** `MarkdownEditor` gets an optional `aiHelper` prop
  (host-injected like the pen adapter; hidden without it) that renders
  `AiHelperPopover` (`frontend/src/features/ai/`): transform presets (explain,
  answer, compact, expand, rewrite, simplify, grammar, structure, bullets,
  format-as-markdown, translate), a free-form prompt box (Enter runs; Shift+Enter
  newline), a **Context** chip (selection + bounded surrounding document text,
  default on) and a **Course material** chip (only when `course_id` is present;
  resolves course context via the Phase-10 ContextResolver, node/course scope,
  query = the selection), a **streamed live preview** with a Stop button and
  "fixing…" repair re-stream, and a review view (editable result + char count,
  **Replace selection** / **Insert at cursor** / **Insert below** /
  **Regenerate** / **Discard**). Insertion (`insertMarkdown`, shared helper)
  parses the generated markdown through `storage.markdown.parser.parse`
  (markdown-it HTML + the extension `updateDOM`/`parseHTML` hooks — the same path
  as document load) and dispatches a manual ProseMirror transaction, so
  `$…$`→caMath, mermaid fences, tables and `ca-drawing:`/`ca-material:` links
  round-trip byte-faithfully; undo (Ctrl+Z) reverts an insertion; a DOM-selection
  fallback covers replace-selection before PM syncs. **Backend**: new
  code-seeded `editor_transform` task + `editor.transform` seed skill with
  deterministic contracts (no-preamble, ≤8k chars, compact ≤ input, answer needs
  a sentence, markdown fence/math balance) enforced by `TaskRunner`'s repair
  loop; `TaskRunner.stream_text` (streaming generator — last-round-only text,
  `repair` events, `stop` callable, audit on completion); `EditorTransformService`
  singleton (`app.state.editor_ai`, in-memory job registry); `POST
  /ai/editor/transform` → `{job_id}` streaming `editor_delta`/`editor_repair`/
  `editor_done`/`editor_error` on `ai-editor:{job_id}` (EventBus), `POST
  /ai/editor/jobs/{id}/cancel` (saves tokens — the loop checks a flag between
  chunks), `GET /ai/editor/jobs/{id}` poll/reconnect fallback; every call audited
  (`context_type=editor_transform`). Wired into NoteEditor (course+node), the
  extraction QA editor (course) and the new text/markdown file dialog (course).
  Nothing is persisted but what the user inserts; no HITL proposals. Frontend 599
  tests (+11: insertMarkdown ×4, popover state machine/insert/error/stop/whole-
  note/grounding ×5, NoteEditor aiHelper, NewTextFileDialog aiHelper, ExtractionView
  aiHelper) · backend 479 (+16: task+skill seeded, transform job flow + audit,
  context-in-prompt, streaming parity/repair/stop, grounding manifest, 422/404/502,
  validate units).

- 2026-08-22 — **UX: more space around items so the marquee selection is easier
  to start (user request).** Grid/list gaps in the selectable item lists double
  (`gap-2`→`gap-4`, `gap-1`→`gap-2`) and every item-list container gains edge
  padding (`p-2`). The real blocker was that the workspace tab's marquee surface
  only covered the item rows — the empty area below the last row (page padding /
  spare scroll height) was outside the surface, so mouse-down there couldn't
  start a marquee. The workspace content column is now `flex flex-col
  self-stretch` inside the `min-h-full` row (the Library's `h-full` pattern;
  `min-h-full` alone can't chain past the first level), and the Materials/Notes
  tab `MarqueeSurface`s stretch (`min-h-0 flex-1`), so the whole pane below the
  items is marquee-startable. Frontend 588 tests · backend untouched (463
  verified).

- 2026-08-22 — **UX: the workspace Materials tab lists only this node's materials;
  the collapsible child-material sections are gone (user request).** The tab
  previously rendered a roll-up of every child node's materials below the node's
  own list (`workspace.children` × `child_materials` with per-child collapse).
  Those sections were read-only previews (child entries can't be unassigned
  here), duplicated the Overview tab's children cards and the structure
  sidebar's per-node counts, and made the shared marquee/selection surface span
  multiple sections for no placement benefit — so they're removed. The Materials
  tab is now exactly: assigned folders + materials directly assigned to this
  node. `collapsed` state dropped; child counts remain available via the
  Overview child cards and the sidebar. Frontend 588 tests (+1 materials-tab
  regression asserting no child section renders) · backend untouched (463
  verified).

- 2026-08-22 — **Fix: dragging a selected item no longer collapses the selection
  (plan 30 follow-up; user report).** A plain `mousedown` on an already-selected
  row reset the selection to just that row *before* the browser fired
  `dragstart`, so dragging from a selected item only carried that one item
  (dragging from the pane background worked because no item `mousedown` ran).
  `useSelection.nextSelection` now **keeps the whole selection** when the
  pointer-down target is already selected (plain click = no modifiers), moving
  the shift-anchor to that row; plain clicks on *unselected* rows still select
  just them, and Ctrl/Shift behave as before. En route: removed a stray
  duplicated/corrupted `isKeyboardClick` block in `useSelection.test.ts`.
  Frontend 587 tests (+1 nextSelection keep-selection) · backend untouched
  (463 verified).

- 2026-08-22 — **Multi-item drag everywhere (user request; plan 30, ADR-067).**
  Dragging any selected row now drags the **whole selection** in the Notes tab,
  the Materials tab (list **and** grid) and the Library, and drops apply to
  everything dragged. New shared `lib/dragPayload.ts` (build/parse of the
  `application/x-ca-item` payload, which now carries `noteIds` too, plus a small
  "N items" `setDragImage` badge for multi-drags); the Library's local payload
  code moves into it (behavior unchanged + the badge for free). `EntityItems`
  gains an optional `onDragStart` and rows become draggable when provided.
  **Notes**: a selected-note drag carries every selected note; an unselected one
  drags just it and joins the selection. **NodeTreeSidebar drops become
  batch-aware**: a multi-material payload assigns every id, a note payload moves
  every note to the node (same `moveNote` placement verb as the context menu);
  node-reorder drags unchanged. Backend 463 · frontend 586 (+8: dragPayload
  suite, EntityItems draggable ×3, sidebar multi-material + note drops ×2, notes
  selection-drag + unselected-drag ×2).

- 2026-08-22 — **Library folder delete becomes a full cascade + a "what will go" dialog
  (user request; ADR-065/066).** Deleting a folder now **removes it and everything
  underneath**: the whole subtree (subfolders + all files) is purged via
  `purge_material` (extractions/chunks/vec/FTS/index cards/study states/drawings and
  material↔node links all cleaned), source rows for nested linked-source folders are
  deleted, and folder→node links across the subtree are removed. This **reverses
  ADR-058's "delete lifts contents to the parent" clause** (ADR-066): `FoldersService
  delete` gets `subtree_folder_ids`/`folder_member_ids` helpers, refuses (422) without
  `?force=true` only when the subtree has assignments, and cascades on force (or plain
  delete when unassigned). **Linked-source folders** keep a separate `POST
  /folders/{id}/unlink` (materials kept, moved to course root; refuses while assigned)
  — the old DELETE-as-unlink is gone. New `GET /folders/{id}/delete-info` returns the
  subtree summary + links aggregated per node. **Frontend**: folder Delete always opens
  a `FolderDeleteDialog` showing "removes N subfolders and M files" plus a compact
  per-node link list ("Course / Node — 1 folder · 2 files") and a danger *Delete folder
  and contents* button; Unlink on source folders calls the new endpoint. Bulk selection
  delete keeps the refuse→notice path for assigned folders. Backend 463 tests (+3
  cascade/delete-info/unlink-ish, reworked lift-to-parent and unlink tests) · frontend
  571 (+4 dialog unit, reworked delete/unlink e2e).

- 2026-08-22 — **Notes tab selection matches the Materials tab: rectangular
  marquee, no "N selected" banner, bulk verbs in the context menu (user request).**
  The `SelectionBar` above the notes list is gone (its "N selected" text and
  Move/Delete buttons). A new shared `MarqueeSurface` component
  (`components/ui/Marquee.tsx`) encapsulates the surface div
  (`data-marquee-surface`), `useMarquee` + `MarqueeBand`, and the Escape-to-clear
  key handler (per-tab `clearBlocked` guard) — the Materials tab and the Notes tab
  both use it now (Library keeps its own conditional wiring). Bulk **Move to
  node…** and **Delete** move into the notes **context menu in multi-select mode**
  (mirrors the materials `entryMenu`): right-clicking a selected note when several
  are selected offers Move/Delete acting on the whole selection; a lone note keeps
  the single-item Open/Rename/Move/Delete menu. Right-click fires a button-2
  `mousedown` that `useSelection.pointerDown` ignores, so a multi-selection
  survives opening the menu. Frontend 565 tests (+1 notes marquee drag asserting
  the highlight + Escape clear + no "selected" text; the bulk delete/move test
  rerouted through the context menu) · backend untouched (441 verified).

- 2026-08-22 — **Text/markdown materials get drawings: editable in-app, embedded
  images on .md export (plan 29, ADR-064; user request).** New `material_drawings`
  table (migration 0032) mirrors `note_drawings` (strokes = source of truth,
  content-addressed PNG, re-runnable OCR w/ version counter); drawings are
  referenced from the material's **extraction markdown** via the existing
  `![drawing](ca-drawing://{id})` scheme. **Backend**: `POST/PUT/DELETE/reocr
  /materials/{id}/drawings/*` mirror the notes surface; `getMaterial` returns
  `drawings`; saving an extraction validates refs (unknown → 422);
  `extraction_to_blocks` splits refs into `drawing` blocks for the reading view;
  drawing OCR joins the material FTS (`sync_material_fts` extra arg) and the AI
  context (chunk source in `edit_extraction`/ingest); `purge_material` cleans the
  rows; **derive copies the source's drawings and remaps `ca-drawing://` ids** so
  the derived material is self-contained; `ca-course/v1` exports/imports them
  (additive `drawings` field, refs remapped on import). **Frontend**: the shared
  `LazyMarkdownEditor` forwards `drawings`/`drawingAdapter`, so the extraction QA
  editor (`ExtractionView`) gains the pen button + inline drawing menu + delete
  flow for free; the reading view passes `resolveDrawing`; a new material **Export
  .md** action (shared `exportMarkdownWithDrawings` helper, also used by the note
  export) downloads `{title}.md` with drawings embedded as base64 PNGs. **The new
  text/markdown file dialog gains the pen too**: a buffered in-memory
  `DrawingAdapter` (placeholder `ca-drawing://-N` refs, negative ids now allowed by
  the drawing-image node, data-URI previews in `DrawingBlock`, re-OCR hidden for
  unsaved drawings); on *Create*, `createTextFileWithDrawings` creates the material
  → waits for ingest → POSTs each buffered drawing (real ids) → remaps placeholder
  refs → saves the extraction — nothing is created until the user clicks Create.
  Drawing helpers (`md_to_blocks`, ref strip/remap) extracted to
  `app/services/drawings.py`, shared by notes + materials. Backend 460 tests (+9
  material-drawings: CRUD/OCR/FTS/validation/delete/derive/bundle + remap helpers;
  3 migration head asserts → 0032) · frontend 564 (+3: dialog buffering +
  ref-remap unit ×2).

- 2026-08-22 — **Drawings get a confirmed Delete in the drawing menu; OCR and AI
  prompts stop assuming the content is math (subject-agnostic; user request).**
  **Delete drawing**: both the inline drawing **⋯ menu** (`DrawingBlock`) and the
  unreferenced-drawings card menu now offer a danger **Delete drawing** (confirmed
  via `window.confirm`) → `DrawingAdapter.remove` → new
  `DELETE /api/v1/notes/{note_id}/drawings/{drawing_id}`: the drawing row is removed,
  any inline `drawing` blocks referencing it are dropped from the note body (so the
  note stays valid), `search_text` is recomputed (OCR text stops matching), and
  `updated_at` bumps. The editor removes the inline image node on delete, so a
  pending draft never re-saves a dangling `ca-drawing://` ref. **Prompts
  de-mathed**: `NOTES_OCR_SYSTEM` ("the image contains handwritten work") and the
  page-OCR prompts (`OCR_PAGE_SYSTEM` + the `gateway_ocr.py` copy) now say *if* the
  content contains mathematics, render it as LaTeX — no more "(mathematics,
  derivations, prose)" or imperative "Mathematics:" rules; `EXGEN_SYSTEM` opens
  "You are an exercise designer for the student's course subject" instead of a
  "calculus exercise designer"; the `notes_ocr` task description and note-action
  instructions dropped "math-aware"/"Keep the math"/"tidy LaTeX". **UI strings**:
  the canvas hint reads "Write by hand…" (was "Write math by hand…"), the Notes tab
  empty state / search placeholder / body label are math-neutral too. Backend 451
  tests (+3 delete-drawing API) · frontend 556 (+3 MarkdownEditor delete tests, +1
  NoteEditor adapter-remove wiring; 4 adapter mocks gained `remove`).

- 2026-08-22 — **Error-pattern drills generalize from a hardcoded calculus list to
  course-type taxonomies + agentic discovery (plan 28, ADR-063).** New
  `error_patterns` table (migration 0031, code-seeded via `seed_error_patterns` —
  ADR-020 pattern; the 8 G10 calculus patterns seed under the `math` course type;
  `key` unique, nullable `course_type_id` = global). `services/patterns.py`:
  `ErrorPatternService` resolves active patterns for a course (its type's + global),
  computes course-scoped counts via `Mistake→Question→Activity.course_id`, and
  creates discovered patterns. `GET /exercises/drills/patterns` now requires
  `course_id` and returns `example` + `source` (`seeded|discovered`);
  `POST /exercises/drills` validates the pattern is active + resolvable for the
  course; new `POST /exercises/drills/propose` (digest of the 30 most recent wrong
  answers → `pattern.discover` skill on the `description` task → contract-validated
  proposals, capped 5) and `POST /exercises/drills/patterns` (approve → discovered
  row scoped to the course type). **Deterministic detectors**: `sign_slip`
  (response ≡ −expected) and `dropped_factor` (response ≡ k·expected) are proven by
  the equivalence chain at grade time in `quiz.py submit_answer` — no LLM, tags land
  on `Answer.error_tags`/`Mistake` and drive the drill counts. `exgen._build_prompt`
  no longer hard-codes "calculus error" — it renders the course subject +
  pattern description/example. Frontend `DrillsCard`: Seeded/Discovered sections,
  honest empty state, *Find more patterns* → approve/dismiss proposal cards
  (`ai.proposals.approve/dismiss`), invalidates the list on approve. `ERROR_TAXONOMY`
  constant deleted. Migration head is now **0031** (3 migration tests updated).
  Backend 448 · frontend 552 tests green.

- 2026-08-22 — **UX: the Materials tab selection banner is gone; Unassign and
  Assign-to-node move into the right-click menu (user request).** The
  "N selected" `SelectionBar` above the list is removed. Selection still works
  exactly like the library (click/Ctrl/Shift/marquee, folders included), but
  the verbs now live in the **context menu**: right-clicking an item resets the
  selection to it if it wasn't part of the selection (library semantics), then
  the menu shows **Open** (single), **Assign to node…** (always, acts on the
  selection incl. folders), and **Unassign** — labelled *Remove from node* /
  *Unassign folder* for a single item, *Unassign* for a multi-selection
  (skipping folder-derived rows, folders via `deallocateNodeFolder`). All
  materials now get a context menu (the `canUnassign` gate only hides
  Remove-from-node for child-section/via-folder entries, which can still be
  opened and re-assigned). **Escape** clears the selection (library pattern).
  **Fix en route (user report): right-click no longer collapses a
  multi-selection** — a right-click fires a button-2 `mousedown` that the
  item's `onMouseDown → selection.pointerDown` treated as a plain click and
  reset the selection to the single item before the menu opened;
  `useSelection.pointerDown` now ignores non-left buttons (`event.button !==
  0`), so right-clicking a selected item keeps the whole selection and the
  menu's Unassign / Assign-to-node apply to all of it (fixes the library's
  lists too — shared primitive). Frontend 549 tests (+1 pointerDown
  right-button unit test; 4 selection tests rerouted to right-click with a
  button-2 mousedown simulated; marquee test asserts the selected highlight +
  Escape clear; banner-absence assertion) · backend untouched (441 verified).

- 2026-08-22 — **UX: assigned folders render as real folder tiles/rows in the
  Materials tab and open in the Library (plan 27 follow-up; user request).**
  The "Assigned folders: …" chip strip above the list is gone. Assigned folders
  now render at the top of the materials grid/list as proper folder tiles/rows
  (`WorkspaceFolderItem` in `NodeWorkspace` — folder icon, name, member count,
  link badge for linked-source folders), styled like the library's folder
  tiles. **Double-click opens the folder in the Library**; right-click offers
  **Open in library** / **Unassign folder**; list rows keep a hover ✕.
  Folders **join the selection grammar**: single-click/marquee select them, and
  the selection bar's **Unassign** and **Assign to node…** handle folder keys
  (→ `deallocateNodeFolder`/`allocateNodeFolder`) alongside materials.
  Opening a linked-source folder deep-links the Library via a new `?source=`
  search param on `/library` (LibraryPage restores link mode from it). Empty
  state now considers folders (dropzone only when folders *and* materials are
  empty). Frontend 548 tests (+6: folder rows + unassign ✕, grid tiles,
  double-click→/library, linked-source `source` deep-link, folder context-menu
  unassign, bulk-unassign + assign-to-node with folders; strip test reworked)
  · backend untouched (441 verified).

- 2026-08-22 — **Feature: the Materials tab gets the library create grammar —
  one shared + New… menu, right-click pane menu, marquee (plan 27, ADR-062).**
  New shared hook `components/materials/createMaterialMenu.tsx`
  (`useCreateMaterialMenu`: New folder / New text file / New Markdown file /
  Upload files… / Upload folder… + the two hidden upload inputs) — the Library
  adopts it (its inline `paneMenu` entries and own inputs deleted; + button and
  pane right-click render the same composed items; **Paste appears only when
  pasteable** instead of always-rendered-disabled; the inline folder-create
  form stays). The workspace **Materials tab**: the split `UploadButton` is
  replaced by a primary **New…** button (disabled+spinner while uploading)
  next to outline **Assign material** (clipboard verbs and *Add linked
  folder* stay library-only — the tab is a placement view per ADR-056);
  **right-click on empty pane** opens the same items (skips
  interactive/selectable targets and default-prevented entry menus); **New
  text/Markdown file** reuses the shared `NewTextFileDialog` (rich editor) →
  `createTextFile` unfiled → `allocateMaterial(node)` →
  tree/workspace/materials refresh; **New folder** via new
  `components/materials/NewFolderDialog.tsx` → `createFolder(name, null,
  course)` → `allocateNodeFolder(node)` (lands in the Assigned-folders strip)
  → refresh + folders invalidation; create errors surface inline.
  **Marquee**: `useMarquee`+`MarqueeBand` on the tab container
  (`data-marquee-surface`), unioned with the existing `useSelection` — spans
  the per-child sections. Frontend 542 tests (+5: New… menu entries incl.
  split-button retirement, Markdown-file create+allocate, folder
  create+assign, empty-pane right-click, marquee drag; LazyMarkdownEditor
  mock added to NodeWorkspace.test) · backend untouched (441 verified).

- 2026-08-22 — **Feature: equations, diagrams and drawings are insertable from
  the editor toolbar; the handwriting canvas moves inside MarkdownEditor (user
  request).** Two new toolbar buttons on the shared Tiptap editor, inherited by
  every rich-editor surface at once (notes, extraction QA, the new
  text/Markdown file dialog): **Σ** inserts a `caMath` node and immediately
  opens the MathLive popover, and the **diagram button** inserts a starter
  `flowchart TD` `caMermaid` node with its source editor open — both via a new
  non-serialized `autofocus` node attribute that the node views consume once
  and clear (never serialized to markdown). **Drawing migration**: the canvas
  UI (DrawCanvas + OCR toggle + save/edit flows + the unreferenced-drawings
  panel) moves from `NoteEditor` into `MarkdownEditor` as a body-portal modal
  opened by the existing pen button; persistence stays host-injected via a new
  `DrawingAdapter` (`create`/`update`/`reocr` — notes wire it to
  add/update/reocrDrawing + cache invalidation; surfaces without it simply
  hide the button). `DrawingMeta` gains optional `strokes`/`ocr_version` so
  the editor can load strokes for **Edit drawing** itself; inline edit/reocr/
  copy actions are now internal (the `onInsertDrawing`/`onDrawingAction`
  props are gone). NoteEditor sheds ~150 lines (draw/edit/reocr mutations,
  canvas card, unreferenced panel, header Draw button). Build: DrawCanvas
  stays its own shared chunk (215 kB, shrank from 231), MarkdownEditor lazy
  chunk 508 kB (+5), boot entry unchanged. Frontend 538 tests (+6 editor:
  Σ-insert w/ MathLive, diagram-insert w/ skeleton + round-trip, canvas
  create→insert-ref, OCR-toggle-off, edit→PUT via adapter, unreferenced
  card + insert-inline; menu/click-away tests rerouted to the adapter; 2
  drawing menu tests assert internal edit/reocr; NoteEditor canvas tests
  replaced by an adapter-wiring test) · backend untouched (441).

- 2026-08-22 — **UX: the New text/Markdown file dialog edits in the shared rich
  editor (user request).** `NewTextFileDialog` (library *New…* menu) swaps its
  plain `<textarea>` for the shared Tiptap editor via `LazyMarkdownEditor` —
  the same component notes and extraction QA use (toolbar, live `$…$` math and
  Mermaid rendering, tables/links round-trip guards of ADR-060); tiptap stays
  in the lazy chunk (build verified). Dialog widened to max-w-2xl for the
  toolbar; `contentPlaceholder` i18n key replaced by an aria-label
  (`contentLabel`). Frontend 535 tests (+5 new `NewTextFileDialog` suite:
  md/txt create paths, Enter submit, disabled/cancel, default-kind toggle;
  LibraryPage dialog test rerouted through the mocked editor + lazy-boundary
  mock added) · backend untouched (441).

- 2026-08-22 — **Fix: invalid mermaid diagrams broke the page (plan 26
  follow-up; user report).** Mermaid's `render()` on a parse failure draws a
  "Syntax error in text / mermaid version" SVG into a temp `d<id>` div
  appended to `document.body` and only removes it when
  `suppressErrorRendering` is on — each failed render left a full-size error
  SVG stuck to `<body>` (under the sidebar, page-wide scroll). The shared
  `MermaidDiagram` now (1) initializes mermaid with
  `suppressErrorRendering: true` (clean throw, temp elements removed by
  mermaid itself), (2) sweeps any leaked `body > [id^="dmermaid-"]` nodes on
  failure as belt-and-braces, (3) resets state per code change (a fixed
  diagram recovers from the source fallback), and (4) caps rendered SVGs at
  `max-width: 100%` inside the scroll container. Invalid diagrams degrade to
  the source block exactly like before the mermaid feature. Verified against
  real (unmocked) mermaid 11.16: the user's reported diagram is itself
  syntactically invalid for mermaid v11 (unquoted nested parens in
  `B[(x + 1)(x^2 - x + 1)]` — labels with parens need quotes,
  e.g. `B["(x + 1)(x^2 - x + 1)"]`); it now shows as source with zero body
  strays. Frontend 530 tests (+3 MermaidDiagram: success render, failure
  sweep + source fallback, recover-after-fix) · backend untouched (441).

- 2026-08-22 — **Fix: mermaid fences render in the reading view too; fences
  are never split or stuffed (plan 26 follow-up; user report).** The previous
  round only handled fences inside the editor — the **Extraction reading tab**
  still showed raw ` ```mermaid ` code: the backend's `extraction_to_blocks`
  split markdown on `\n\n` blindly (fences with blank lines were even cut
  mid-fence) and `TextBlockView` had no mermaid handling. Three fixes:
  (1) `TextBlockView` overrides `pre` and renders `language-mermaid` fences
  through the shared `MermaidDiagram` (non-mermaid fences stay code blocks) —
  **existing extractions render diagrams immediately, no re-ingest**;
  (2) backend `extraction_to_blocks` is now fence-aware (`_split_top_level`
  tracks ```/~~~ fences; plain splits unchanged);
  (3) the editor's blank-line nbsp stuffing no longer runs inside fences
  (`stuffBlankLinesOutsideFences`), so diagram sources with blank lines
  survive editing byte-exactly. Also verified the editor captures the user's
  exact fence content (flowchart with bracket labels + Γ). Backend 441 tests
  (+2 splitter) · frontend 527 (+3: fence-in-text-block render, python fence
  passthrough, fence-safe stuffing).

- 2026-08-22 — **Feature: Mermaid diagrams render + edit in the rich editor;
  equation editor gets a close button (plan 26 follow-up; user request).**
  Fenced ` ```mermaid ` blocks in the extraction/notes editor now render as
  real diagrams instead of code: a `caMermaid` block-atom node
  (`components/editor/CaMermaid.tsx`) captures fenced sources in the
  tiptap-markdown `updateDOM` hook, renders through the same lazy mermaid
  engine as BlockRenderer (extracted to shared
  `components/blocks/MermaidDiagram.tsx`, theme/security config unchanged,
  source fallback on parse failure), and **double-click opens a separate
  source editor** — a centered modal with a mono textarea (live document
  updates while typing), Escape/backdrop/**Close (X)**/Done to exit.
  Serialization re-emits the fence verbatim (byte-identity round-trip
  asserted). The MathLive equation popover gained a **Close (X) button**
  alongside Done (user request). Hint line now covers both. Frontend 524
  tests (+3: mermaid render+round-trip, source-editor edit flow with Close,
  equation-popover Close) · backend untouched (439 verified).

- 2026-08-22 — **Feature: math renders + edits inside the rich editors (plan 26
  follow-up; user request).** `$…$` / `$$…$$` no longer display as raw LaTeX
  in the extraction/notes Tiptap editor: a new `caMath` inline-atom node
  (frontend `components/editor/CaMath.tsx`) parses math from the rendered DOM
  (tiptap-markdown `updateDOM` hook; encode cloaks display-math newlines with
  U+2063 so `breaks:true` can't shatter spans into `<br>`), renders live via
  KaTeX (`katex-display` for `$$`, source fallback on parse errors), and
  **double-click opens a MathLive equation editor popover** (the existing
  `MathInput`, body-portal so ProseMirror never sees its events) with live
  attr updates. Serialization emits `$latex$`/`$$latex$$` verbatim — the
  byte-identity corpus now flows through math nodes and still passes.
  En route: **fixed a tiptap-markdown table-serializer bug** — cells whose
  only content is a textless atom (math, images) were dropped
  (`textContent.trim()` guard); `MarkdownTable` replaces the serializer with a
  `childCount`-aware copy. `\|` inside math stays escaped through encode so
  GFM tables keep one cell, then canonicalizes to `|` on capture (KaTeX
  rendering; documented normalization). Hint line updated ("math renders live…
  double-click to edit"). Frontend 521 tests (+4: KaTeX render inline/display,
  MathLive edit flow, math-in-table + escaped-pipe round-trips) · backend
  untouched (439 verified).

- 2026-08-22 — **UX: multiline rename editor + selection-revealing title wraps
  (plan 26 polish; user request).** Library rename (folders + materials) moved
  from a one-line `<input>` to a shared `NameEditor` textarea that wraps long
  names and auto-grows (`scrollHeight` sizing); Enter saves, Shift+Enter breaks
  a line while drafting, Escape cancels; saved names stay single-line (newlines
  fold into spaces via `normalizeName` — filenames/titles never gain `\n`).
  Title clamps now reveal more on selection, per the user's spec: grid tiles
  (folders + `MaterialTile`, so the workspace Materials grid inherits) go
  `line-clamp-3` → `line-clamp-4` when selected; list rows (folder rows +
  `MaterialRow`) go `truncate` → `line-clamp-2` when selected. Frontend 517
  tests (+8: NameEditor keys/autosize/normalize, clamp classes on
  tile/row, LibraryPage multiline-rename normalization) · backend untouched
  (439 verified).

- 2026-08-22 — **Fix: derive refreshes open views without a reload (plan 26
  follow-up; user report).** After "Save as material", only the library list
  (`['materials']`) was invalidated — the workspace Materials tab
  (`['node-workspace', nodeId]`) and the tree sidebar counts (`['tree']`)
  kept stale data until a page reload. The derive success handler now mirrors
  the LibraryPage assignment pattern and also invalidates `['tree']` and
  `['node-workspace']` (the `['materials']` prefix already covers the picker's
  per-course/unfiled catalog queries). Regression test mounts real observers
  and asserts both queries refetch. Frontend 509 tests (+1) · backend
  untouched (439 verified).

- 2026-08-22 — **Feature: derive carries placement (plan 26 follow-up, refines
  ADR-061; user request).** "Save as material" now links the derived material
  to the course tree: it copies the original's direct `material_links`
  (rationale `Derived from <title>`) and additionally accepts a `node_id`
  (validated: exists, same course → 422 otherwise); the UI passes the
  currently opened node (`ExtractionView`'s `scopeNodeId` — the workspace
  drawer context), merged without duplicates against the copied links. On
  `deduped` the existing material is left untouched (no link writes, matching
  the never-overwrite rule). Backend 439 tests (+5: link copy, node merge
  dedup, foreign/unknown node 422s, dedup-untouched) · frontend 508 (+1
  scope-node pass-through).

- 2026-08-22 — **Feature: rich extraction QA editing + "Save as material"
  (plan 26, ADR-060/061; user request).** The extraction editor is no longer a
  plain textarea: `ExtractionView` (both the ordinary and mindmap branches) now
  edits through the shared Tiptap `MarkdownEditor` behind a new
  `LazyMarkdownEditor` boundary, so tiptap stays out of the boot chunk. This was
  blocked by ADR-055 (tiptap-markdown round-trip losses) — re-probed empirically
  and each gap closed (ADR-060): GFM tables get real schema nodes
  (`@tiptap/extension-table` kit — **named imports only**, the package's ESM
  build has no default export), the Link parse allowlist gains
  `ca-material:`/`ca-drawing:`/`mention:` (also fixing a latent notes bug: a
  saved `ca-material://` quote link was stripped on the next re-parse), and the
  plan-23 fidelity helpers now protect math spans (`encodeMarkdownForParse`
  doubles `\` and canonicalizes `\|`→`|` inside `$…$`/`$$…$$`, skipping code;
  `decodeMarkdownFromSerialize` collapses serialized hard breaks then halves
  `\\`), so `\,`/`\int`/`\alpha`/`\\` survive **byte-identically** — asserted by
  a corpus round-trip test through the real editor. Known normalizations
  (documented): table alignment `:--`/`--:` → `---`; `\|` inside math becomes
  `|` (every markdown consumer in the app already renders it that way).
  **Save as material**: `POST /materials/{id}/derive` (ADR-061) turns the latest
  extraction into a standalone md material via `create_text` (compose
  precedent) — `provenance {source: derived, from_material_id, from_version}`,
  title uniqued `"{title} (extracted)"`, inherits the source's virtual folder
  (linked-source folders → course root, explicit `folder_id` validated),
  per-course content-hash dedup applies **excluding the source itself** (a
  text material's extraction equals its bytes — dedup-to-self returned
  nonsense), duplicates surfaced (`deduped`), never provenance-overwritten;
  standard ingest (native extractor, chunks/FTS/embeddings), original
  untouched. UI: "Save as material" button in the extraction header with
  inline success/duplicate/error feedback + Open link to the new material.
  Backend 434 tests (+9 derive API tests) · frontend 507 (+8 ExtractionView
  edit/derive flows; +7 editor/fidelity round-trip) · build keeps
  MarkdownEditor as its own 496 kB lazy chunk.

- 2026-08-22 — **UX: single click selects, double-click opens (ADR-059, refines
  the plan-24 grammar; user request).** In every list carrying the file-manager
  selection grammar — the Library pane (folders + materials, grid + list, incl.
  linked-source browse subdirs), workspace Materials tab (tiles + rows),
  Notes/Practice lists (`EntityItems`) — a plain mouse click now only selects;
  **opening takes a double-click or the keyboard**: Enter on a focused row
  (keyboard-synthesized clicks detected via `detail === 0`, one shared
  `isKeyboardClick` helper) and, on the Library pane, Enter opens the single
  selection. Implemented once in the shared components (`MaterialRow` `onOpen`
  is now activation semantics, `MaterialTile` gained `onDoubleClick`,
  `EntityItems` dropped its `shouldOpen` prop, `useSelection` dropped the
  `click` gate) so every surface inherits it; picker/dialog/search/course-card
  lists keep single-click activation (no selection grammar there). Footer hint
  now reads "Click to select · double-click to open · right-click for actions".
  490 frontend tests (+3: EntityItems list/grid activation grammar,
  isKeyboardClick; open-flow tests rerouted to doubleClick incl. a
  single-click-does-not-open assertion; Library single-select/dblclick-open and
  Enter-opens-folder) · backend untouched (425 verified).

- 2026-08-22 — **Feature: assigning library folders as course material (plan 25
  B/C/D on the 25-A backend, ADR-058).** **Picker** (`MaterialPickerDialog`):
  every folder row — sidebar + list, virtual **and linked-source** — gains an
  *Assign the whole folder* toggle (📁+; locked with a 🔒 when already assigned
  to the target node); folder selections ride the same footer chips + one
  Assign button (`allocateNodeFolder`), hidden in select mode. **Workspace
  Materials tab**: folder-derived rows carry a folder badge with tooltip
  (*move the file out or unassign the folder*) and no per-file ✕ / Remove
  verb (context menu keeps Open only; bulk Unassign skips them); new
  **Assigned folders** chip strip (folder/link glyph, name, live member
  count, ✕ unassign → `DELETE /nodes/{id}/folder-materials/{fid}`). **Library**:
  folder context menu gains **Assign folder to node…** (both folder kinds,
  generic `AssignToNodeDialog` in folder mode). **Material detail**:
  assigned-to chips render `Assigned via "folder": node` for folder-derived
  placement. 487 frontend tests (+9: picker folder assign/lock/alone/chip
  deselect + select-mode gating, workspace badge + strip + unassign +
  context-menu gating + bulk-unassign skip, library folder-assign flow,
  via-folder chip) · backend untouched (425 verified).

- 2026-08-22 — **Backend for folder assignment (plan 25 A, ADR-058).** New
  table **`material_folder_links`** (migration **0030**; composite FK +
  unique (node, folder) — mirrors `material_links`): a folder can be assigned
  to a node (`POST /nodes/{id}/folder-materials` + course-level twins +
  DELETEs) and a node's **effective materials = direct links ∪ folder members,
  resolved at read time** — virtual folders by subtree (path prefix),
  linked-source folders by `materials.source_id`; membership is never
  materialized, so files uploaded/scanned later join assigned nodes
  automatically. Folder-aware everywhere materials are read: workspace
  payload (`materials`/`child_materials` gain `via_folder_id/name`, new
  `folders` section), tree counts + per-node `folder_links`,
  `course_materials` listing (`via_folder` entries, direct wins on overlap),
  material-links chips (`via_folder`), ContextResolver node/subtree scope
  (generation + chat + MCP), organizer review (no false "unlinked" hints),
  assign_material proposal revalidation, node merge-delete dedup + undo
  restore, course purge. Guards: unassigning a folder-derived material → 422
  with actionable message; deleting/unlinking a folder with active
  assignments → 422 (unassign first); rename/move keep links (id-based).
  `ca-course/v1` export/import round-trips folders + folder links
  (additive `folders.json`; source-folder assignments never travel — machine-
  local, warned). 425 backend tests (+17 in `test_folder_links.py`; 3
  head-revision assertions bumped to 0030, links payload gained `via_folder`)
  · frontend untouched.

- 2026-08-22 — **Feature: file-manager selection grammar on the workspace tabs
  (plan 24 D, ADR-056 placement verbs).** `EntityItems` (notes/practice lists)
  gains an optional `selection` prop (pointer-down select, modifier-gated open,
  selected visuals, `data-selectable-id`); new shared `SelectionBar`
  (count + verbs + clear). **Materials tab**: multi-select → bar with **Unassign**
  (bulk) + **Assign to node…** (generalized `AssignToNodeDialog` — now takes
  title/count/confirm strings + `onDone(nodeId)` so every surface reuses it);
  dragged rows carry the whole selection (`x-ca-item` multi-id + first id under
  `x-ca-material` for the sidebar drop). **Notes tab**: multi-select → **Delete**
  (single confirm, sequential trash-snapshotting deletes, undo strip) +
  **Move to node…** (`moveNote` → notes + tree invalidation). **Practice tab**:
  per-list multi-select → **Delete** + **Move to node…** (`moveQuiz`/`moveExercise`
  on plan-24-A endpoints). 478 frontend tests (+4: materials bar unassign+assign,
  notes bulk delete + move-to-node, practice move+delete, EntityItems selection
  gating/visuals) · backend untouched (408 verified).

- 2026-08-22 — **Feature: the Library behaves like a classic file browser —
  selection + clipboard verbs + drag-to-move + assign-to-node (plan 24 B/C,
  ADR-056).** New shared primitives: `lib/useSelection.ts` (click / Ctrl-toggle /
  Shift-range with anchor, `set`/`union` for marquee handoff),
  `components/ui/Marquee.tsx` (`useMarquee` + `MarqueeBand`: background-only
  rubber band, 4px arm threshold, rect-intersection hit-testing over
  `[data-selectable-id]`, ctrl-drag unions, Esc cancels) and
  `lib/clipboard-store.ts` (typed Zustand clipboard: `{kind:'library', course,
  folderIds, materialIds, mode:'copy'|'cut'}`). Library wiring: selection visuals
  on folder tiles + material tiles/rows (`MaterialTile`/`MaterialRow` gain
  `selectionState: none|selected|cut` — cut renders dimmed), item menus gain
  **Cut / Copy / Assign to node… / Paste into folder** (folder Copy disabled with
  a hint — recursive folder copy is future work), pane menu gains **Paste**,
  keyboard **Ctrl+X/C/V, Delete/Backspace, Esc** (gated: no menu/dialog open, no
  input focused — en route fixed a window-dispatch crash when `event.target` is
  the window), cut+paste = move via `PATCH /materials/{id}/move` + folder move,
  copy+paste = `POST /materials/{id}/copy` (clipboard persists — Nemo behavior;
  cut clears after paste), **drag**: folders/materials draggable with
  `application/x-ca-item` multi-id JSON payload (+ single material id under the
  existing `x-ca-material` MIME so node-tree assign keeps working), drop on a
  folder = move (ring highlight, linked folders rejected with a notice), drop on
  the pane background = move into the open folder; marquee clears/limits
  selection on data refresh (stale-key pruning); footer shows an "N items
  selected" clear button; new **AssignToNodeDialog** (course-tree radio picker →
  idempotent assign per material → invalidates tree + workspace). Usage doc
  updated (selecting/moving/copying section). 474 frontend tests (+29: selection
  model incl. ranges/anchors/click-gating, marquee geometry + gesture suite,
  clipboard store, library marquee/cut-paste/copy-paste/keyboard-delete/
  ctrl-x-v/drag-drop-move/assign-to-node, dialog unit suite; 23 pre-existing
  library tests untouched) · backend untouched (408 verified).

- 2026-08-22 — **Backend for file-manager verbs (plan 24 A, ADR-056/057):
  material move/copy + note/quiz/exercise node moves.** New endpoints:
  `PATCH /materials/{id}/move` (`folder_id`, null = course root; validates
  same-course + rejects linked folders — mirrors the folders API), `POST
  /materials/{id}/copy` (ADR-057: new row **sharing the content-addressed
  blob** + `content_hash`, bypassing upload dedup; latest extraction deep-copied
  as version 1 with fresh chunk ids + FTS sync + index-card copy; standard
  `postprocess` job enqueued for embeddings/description backfill; fresh study
  state, **no node links**; uniqued `"{title} (copy)"` title per target
  folder), `PATCH /notes/{id}/move` + `PATCH /quiz/activities/{id}/move` +
  `PATCH /exercises/{id}/move` (all `{node_id: number|null}` through
  `TreeService.placement_node` — null = course root, cross-course 422; tree
  counts change). Dedicated `/move` routes instead of PATCH-field flags: an
  absent field must never be indistinguishable from "move to root". En route:
  fixed a UTC/local date flake in `test_exam_planner` (test used local
  `date.today()` while the app clocks `utcnow().date()` — failed whenever the
  two dates differ). 408 backend tests (+10: move happy/422 paths incl.
  cross-course + linked-folder, copy deep-copy invariants incl. postprocess
  job + FTS + no-links + title uniquing chain, note/quiz/exercise node moves
  incl. foreign-node 422) · frontend untouched.

- 2026-08-22 — **UX: one split Upload button everywhere (user request;
  library simplified same day).** New
  shared `components/materials/UploadButton.tsx` — a split button whose main
  part uploads **files** immediately and whose chevron opens a PopoverMenu
  with **Upload files / Upload a folder** (own hidden inputs incl.
  `webkitdirectory`; spinner while uploading). The workspace **Materials
  tab** action bar uses it next to *Assign material*, and the
  **MaterialPickerDialog footer** gets an outline variant (uploads still
  target the browsed folder and auto-select) while the in-list dropzone row
  stays for drag-and-drop. The **Library toolbar** adopted it briefly, then
  the user simplified: the standalone upload button is **removed** — the +
  (*New…*) pane menu already carries *Upload files… / Upload folder…*, so the
  library exposes one create affordance only (drag-and-drop still works).
  445 frontend tests (library upload tests moved onto the pane-menu inputs +
  picker-invocation spies; split-button menu tests on materials tab) ·
  backend untouched.

- 2026-08-21 — **Feature: whole-folder uploads with directory structure
  preserved (user request).** `useMaterialUpload` now accepts
  `webkitRelativePath`-carrying files (from `webkitdirectory` inputs) or
  explicit `{file, relativePath}` items, **recreates the directory tree in
  the library** via find-or-create chains (`listFolders` snapshot +
  `createFolder` for missing segments — the backend rejects duplicate names,
  so existing folders are reused), skips OS junk files (`.DS_Store`,
  `Thumbs.db`, `desktop.ini`, `._*`), and invalidates `['folders']` when it
  created any. Shared `UploadDropzone` gains an *Upload a folder* control
  (hidden `webkitdirectory` input) in both variants **and folder-aware
  drag-and-drop** — new `components/materials/dropFiles.ts` traverses
  `webkitGetAsEntry()` directory trees (readEntries loop, graceful fallback
  to plain files). Surfaces: Materials tab gets a second **Upload folder**
  action (uploads land in a named folder tree; every material still
  auto-assigned to the node), picker/chat dropzones gain the folder button
  (nesting under the browsed/Chat-uploads base), Library pane menu gains
  **Upload folder…**. Single-file behavior unchanged (still unfiled at
  course root). 443 frontend tests (+7: hook tree-recreation w/ reuse,
  nesting under a base folder, junk-file skip; dropzone directory input;
  DataTransfer entry traversal incl. fallback; workspace folder-upload →
  per-file allocate) · backend untouched (398 verified).

- 2026-08-21 — **Feature: upload materials straight from the course page
  (user request; single-source upload UI).** New shared upload primitive —
  `components/materials/materialUpload.ts` (`useMaterialUpload` hook:
  sequential multi-file, per-file error collection without aborting the
  queue, `['materials']` invalidation, pluggable folder resolution) +
  `UploadDropzone` (block/row variants, drag-and-drop + click-to-browse,
  i18n'd). Surfaces, all on the one primitive: **course Materials tab** —
  *Upload files* primary action + empty-state dropzone; uploads land
  **unfiled in the course library** and are auto-allocated to the current
  node (backend `assign` is idempotent, so deduped re-uploads are safe);
  **MaterialPickerDialog** — *Upload to this folder / course library* row at
  the bottom of the list (hidden in linked-source browsing), uploads land in
  the browsed folder and are auto-selected — same pattern as the existing
  ingest-and-select; **Library page** — its upload mutation replaced by the
  hook (job-progress WS tracking preserved via `onUploaded` job_id); **chat
  AttachMenu upload tab** — inline label/input replaced by the shared
  dropzone ("Chat uploads" folder find-or-create logic preserved, now
  multi-file). Architecture unchanged: files always upload to the course
  library (`POST /materials`); nodes hold assignment links. 436 frontend
  tests (+6: hook semantics incl. error continuation; Materials-tab
  upload→allocate; root empty-state dropzone; picker upload-to-folder +
  auto-select; library toolbar upload flow) · backend untouched (398
  verified).

- 2026-08-21 — **Feature: inline drawings are draggable and show their ⋯ menu
  only when focused (user request, plan 23 B follow-up).** The drawing image
  node is now `draggable` with the image marked `data-drag-handle` (grab
  cursor; native img drag disabled) — ProseMirror moves the node on drop, so
  drawings can be repositioned anywhere in the note body and serialize at
  their new spot. The always-visible ⋯ menu row is replaced by
  **click-to-focus**: clicking a drawing creates a NodeSelection (highlight
  ring) that reveals the ⋯ dropdown; clicking away (or moving the caret)
  unfocuses and hides it. jsdom groundwork: `document.elementFromPoint` stub
  in the test setup (PM posAtCoords needs it) + helpers to aim pointer
  events and emulate native caret placement via `selectionchange`. 430
  frontend tests green · backend untouched (398 verified).

- 2026-08-21 — **Fixed: blank-line fidelity follow-ups — visible nbsp markers,
  edge trimming, and a dead serializer override (user reports).** Two defects
  surfaced after the byte-stable fix. (1) The runtime storage mutation
  (`installMarkdownFidelity`) never took effect on tiptap v3 — `extension.storage`
  is a getter returning a fresh object per access, so typed empty paragraphs
  serialized to nothing; it is replaced by a real **`BlankLineParagraph`**
  extension (`Paragraph.extend` with a markdown `serialize` that emits `\u00A0`
  for empty paragraphs), registered via `StarterKit.configure({ paragraph: false })`
  (new direct dep `@tiptap/extension-paragraph`). (2) The `\u00A0` blank-line
  transport markers were leaking into the visible document as literal spaces on
  every empty line after parse — markers are now **stripped from the doc right
  after parsing** (`stripBlankMarkers`, preventUpdate/addToHistory-safe
  transaction); they exist only in the serialize/parse layer. Per the user's
  preference, **empty lines before the first and after the last text are now
  trimmed** on both encode and decode (interior multiline gaps are preserved
  exactly). Caret preservation on genuine external updates restored (selection
  head re-clamped instead of jumping to end). Tests: fidelity unit shapes,
  extension-level serialization incl. only-empty docs and reparse identity,
  component keyboard paths (Enter creating leading/interior empties), autosave
  full-loop with query invalidation, and no-`\u00A0`-in-document assertions —
  428 frontend tests green · backend untouched (398 verified).

- 2026-08-21 — **Fixed: autosave still collapsed multilines — the loss was in
  the editor's own markdown pipeline (plan 23 A completion, user report).**
  The backend round-trip was verified lossless (live probe), but tiptap-markdown
  is not: markdown-it discards blank-line *runs* at parse (`a\n\n\n\nb` → one
  gap), and empty paragraphs serialize away entirely — so the emitted markdown
  (what gets saved) had already lost the blank lines, and any reload/restore
  rewrote the visible document (the "cursor jumps when saved" companion
  symptom). New `components/editor/markdownFidelity.ts` makes the editor's
  markdown **byte-stable**: blank-line runs ≥3 encode to `&nbsp;` paragraphs
  before parse, serialized `&nbsp;` paragraphs (and empty paragraphs, via a
  paragraph-serializer override installed at runtime) decode back to newlines —
  `md → doc → md` is the identity, so autosave feedback equals what the editor
  emitted, the external-value guard no-ops, and **saving never rewrites the
  document: caret, focus, spacing and undo history are untouched while
  typing**. `setContent` remains reserved for genuine external changes.
  En route: entity → `\u00A0` bridging happens inside markdown-it only (decode
  matches the parsed character, never the literal entity). 419 frontend tests
  (+7: fidelity encode/decode shapes incl. leading/trailing runs and
  in-paragraph hardbreaks untouched; editor preserves `para one\n\n\n\npara
  two` through emit + re-receive without replacing the document; blank-line +
  empty-paragraph survival with no nbsp/entities leaking into saved markdown) ·
  backend untouched (398 verified).

- 2026-08-21 — **Fixed: React 19 render-phase violations in the drawing
  NodeView + tree-row key warning (user report from the dev server).** The
  manual `createRoot().render()/unmount()` inside the tiptap NodeView ran
  synchronously during React's render ("triggering nested component updates
  from render", "attempted to synchronously unmount a root while React was
  already rendering"). The inline drawing NodeView now uses tiptap's
  **`ReactNodeViewRenderer` + `NodeViewWrapper`** — the React component is
  scheduled through React normally (no manual roots; refresh subscribers
  re-render via a listener set as before). En route: `NodeTreeSidebar` passed
  `key` inside the `rowProps` spread object (React warning); the key is now
  passed directly on `<TreeRow>` and removed from the props builder. 412
  frontend tests green (editor suites re-verified against the new renderer) ·
  backend untouched (398 verified).

- 2026-08-21 — **Uniform dropdown menus project-wide (user request, plan 23
  follow-up).** The drawing actions were the odd ones out: a hand-rolled DOM
  menu inside the inline NodeView + plain button rows on the fallback cards.
  New shared **`PopoverMenu`** (`components/ui/popover-menu.tsx`) — composes
  the portal `Popover` with one standard menu layout (items with icons, danger
  red, disabled, pending spinner; closes on select; `w-52 p-1` panel) and a
  shared `menuItemClassName` now also used by `ContextMenu`, so kebab menus,
  right-click menus and popover menus render identically. The inline drawing
  NodeView became a real React component (**`DrawingBlock.tsx`** rendered via
  `createRoot` inside the NodeView, `contenteditable=false` mount, unmount on
  destroy) using the same `PopoverMenu` (Edit drawing / Run OCR again / Copy
  OCR text); fallback cards keep **Insert inline** as the primary button and
  fold Edit/OCR/Copy into a kebab; the editor's AI dropdown and ⋯ overflow menu
  were refactored onto `PopoverMenu` (dropping the ad-hoc menuClose plumbing).
  En route: the no-meta placeholder gained a proper i18n key
  (`notes.drawingMissing`). 412 frontend tests (+3 `PopoverMenu` suite;
  card/menu interaction tests rerouted through the kebab) · backend untouched
  (398 verified).

- 2026-08-21 — **Fixed: popover panels were clipped by the note drawer's edge
  (user report, plan 23 follow-up).** The AI/overflow menus anchored inside the
  FocusShell drawer got cropped — `overflow-y-auto` computes `overflow-x: auto`,
  so the right-aligned panel of the leftmost trigger (AI) overhung the drawer's
  left border and was cut. The shared `Popover` now renders its panel through a
  **`createPortal` to `document.body`** with **`position: fixed`** computed from
  the trigger's `getBoundingClientRect()` (align end/start kept, viewport-clamped
  with an 8 px margin, flips above the trigger when it would overflow the bottom,
  z-`[60]` above the drawer's z-50) — no ancestor can clip it; position
  recomputes on resize + captured scroll, and the measurement first paints
  offscreen (no flash). 409 frontend tests (+1 portal-escape test: panel lands
  on `document.body` outside an `overflow:hidden` ancestor above overlay
  stacking; align assertions rewritten against computed fixed offsets) · backend
  untouched (398 verified).

- 2026-08-21 — **Plan 23 D/E/F — editor chrome: AI dropdown + overflow menu,
  editable AI results, undo/redo buttons, scrollable editor body.** The note
  editor's action row was restructured per user request: the four AI actions
  moved into one **AI dropdown** (Sparkles, Popover-based; pending spinner on
  the running kind); **Print / Export .md / History / Delete** folded into a
  **⋯ overflow menu** (delete styled danger-red); Save, Draw, Make flashcards
  and Study-alongside stay direct buttons. AI results are now an **editable
  markdown draft** (mono textarea) with **Append to note** (appends the edited
  text — the whole-value change is a single undoable step and, since plan 23 A,
  no longer resets the caret mid-typing) and a **✕ Close**; the flashcards
  confirmation message rides a separate closable info card. The formatting
  toolbar gains **Undo/Redo buttons** (disabled via `can()` — session rollback
  the user asked for, on top of plan-22-B version history), and the editor body
  now scrolls **inside a `max-h-[65vh]` frame with the toolbar pinned above it**
  (works on every surface — drawer/full page/split pane; avoids colliding with
  the FocusShell's own sticky header). Hardening en route: the external-value
  sync now no-ops when the editor already serializes to the incoming value
  (absorbs stale renders; caught by a jsdom flush-ordering case that ghost-undid
  an insert). `Popover` gained an optional `triggerClassName`. 408 frontend
  tests (+4: AI menu opens+fires + editable append payload + close, overflow
  menu contents incl. absent-as-buttons, undo/redo revert+restore with disabled
  states, scrollable-body-with-pinned-toolbar; delete tests rerouted through
  the menu) · backend untouched (398 verified).

- 2026-08-21 — **Plan 23 C — `notes_ocr` is extraction-only; UI says OCR
  (ADR-054).** User report: OCR output was descriptive ("the drawing displays
  the text …") because the old prompt licensed one-line sketch descriptions.
  `NOTES_OCR_SYSTEM` rewritten: extract **only the text actually written in the
  image** (math as precise LaTeX, reading order preserved), never describe the
  image, no commentary/translation, empty output when nothing is legible — the
  sketch-description clause is deliberately dropped. UI vocabulary is now OCR
  everywhere ("Run OCR again", "OCR text", "No OCR text yet", "OCR v2" —
  `en.json`; BlockRenderer + NodeView labels), the canvas footer says **Save
  drawing**; the skill **key** `notes.transcribe` is unchanged (DB-stable) but
  its seed name/description became "Handwriting OCR" and `seed_skills` now
  refreshes seed name/description of existing system skills (previously only
  the v1 template refreshed). 398 backend tests (+1: seed rename/description
  refresh; seeded-prompt extraction-only assertions folded into the existing
  seed test) · frontend labels only (404 verified).

- 2026-08-21 — **Plan 23 B — drawings render exactly once; inline menu, edit
  drawing, OCR toggle (ADR-053).** User report: every drawing appeared twice —
  inline in the body *and* again as a card below the editor (the save flow
  auto-inserts inline since plan 22 E, but the cards rendered all drawings
  unconditionally). Now the body's `ca-drawing://` refs are the truth:
  referenced drawings render **only** inline; the cards below the editor are a
  fallback home for **unreferenced** drawings (Insert inline / Edit drawing /
  Run OCR again). Each inline drawing gained a **⋯ menu** (DOM NodeView menu,
  `DrawingImage.ts`): *Edit drawing* (canvas reopens with the stored strokes —
  `strokes` now travels in the note detail — and saving **PUT
  `/notes/{id}/drawings/{id}`** replaces strokes+PNG on the same row: OCR rerun
  bumps `ocr_version`; OCR-off **clears** stale OCR text and resets the
  counter), *Run OCR again* (existing reocr), *Copy OCR text*. The canvas
  footer is **[Run OCR toggle · default on] [Save drawing]** — OCR-off saves
  the drawing with no extraction and no transcript UI ("Convert to text"
  retired). NodeViews refresh live when drawing metadata changes (listener
  registry on the extension — `setNodeMarkup` dispatches are skipped by PM for
  eq-equal nodes). 397 backend tests (+3: PUT replaces strokes/PNG + reruns OCR
  + search refresh; PUT without OCR clears stale text + search deindexed;
  404/404/422 rejects) · 404 frontend (+6: unreferenced card vs referenced
  dedup, inline menu fires edit/copy, OCR toggle off → `ocr:false` payload,
  edit flow PUTs with OCR choice, inline OCR text live-refresh, label renames).

- 2026-08-21 — **Plan 23 A — lossless note-body round-trip; autosave never
  rewrites the editor (ADR-052).** Three user-reported symptoms (autosave
  collapsing multilines, invisible cursor after save, lost in-editor undo) had
  one root cause: the save round-trip was lossy (`_md_to_blocks` stripped
  newlines/dropped blank segments; the frontend re-joined blocks with exactly
  `'\n\n'`), so the post-save value differed from what the editor emitted →
  `setContent` rewrote the document → caret reset + undo history wiped. Now
  blocks store text segments **verbatim** (split only on `ca-drawing://` refs)
  and both sides rejoin **boundary-aware** (insert `"\n\n"` only when neither
  boundary is a newline — legacy stripped blocks rejoin byte-identically to the
  old behavior); `md → blocks → md` is the identity, so autosave feedback never
  triggers `setContent` — caret, line spacing and ProseMirror undo survive.
  `setContent` is reserved for genuine external changes (restore, append,
  conflict reload) and focuses the caret to the end when the editor had focus;
  drawing refs insert with the canonical alt `![drawing]` so emitted markdown
  equals the reconstruction (new i18n token `notes.drawingRefAlt`). 394 backend
  tests (+2: round-trip identity incl. blank lines/whitespace segments/adjacent
  refs, legacy rejoin) · 400 frontend (+3: `noteBodyMd` boundary join ×5 cases,
  editor does not replace the document when the saved value equals the emitted
  markdown, insert-emitted round-trip).

- 2026-08-21 — **Tooling: backend `pytest` 220s → ~37s (6x)** (dev-loop fix;
  no app behavior change). Two changes in `backend/tests/conftest.py` +
  `pyproject.toml`: (1) session-scoped `migrated_db_template` fixture runs the
  Alembic chain to head once per run (shared across xdist workers via
  `filelock`); per-test DB setup now copies that template instead of replaying
  ~26 migrations — an autouse patch on `app.main._run_migrations` fast-paths
  only *fresh* DB files and falls back to real migrations for pre-staged DBs,
  so migration-semantics tests are untouched. (2) `pytest-xdist` added to the
  dev group with `addopts = "-n auto"` (parallel across cores; `-n0` for pdb).
  New dev deps: `pytest-xdist`, `filelock` (mypy override added for the latter).
- 2026-08-21 — **Fixed: course export 500'd (`UnicodeEncodeError`) for courses
  with non-ASCII titles** (user report, second bug on `GET /courses/{id}/export`
  — surfaced right after the blob-path fix landed). HTTP headers are latin-1;
  the raw `course.title` went straight into `Content-Disposition`. New shared
  `content_disposition()` helper (`api/deps.py`): latin-1-safe names pass
  through unchanged; non-latin1 gets an ASCII fallback + RFC 5987
  `filename*=UTF-8''…` percent-encoded form (modern browsers show the real
  title; quotes/CRLF stripped against header injection). Applied to both
  header-building spots: course export and `GET /blobs/{sha}` filename serving
  (same latent crash for Greek/CJK filenames). En route: the frontend suite had
  grown a load-dependent **unhandled jsdom exception** (prosemirror
  `scrollToSelection` → `Range.getClientRects` missing — only
  `Element`/`Text.prototype` were stubbed, and only in one test file); the rect
  stubs now live in the global `src/test/setup.ts` with `Range.prototype`
  covered too — 4 consecutive full runs clean. 392 backend tests (+2: Greek
  course title export + import preview; Greek blob filename serving) ·
  393 frontend (setup change only).

- 2026-08-21 — **Fixed: course export 500'd (`FileNotFoundError`) on any course
  with real blobs** (user report — `GET /courses/{id}/export`). Root cause:
  `build_course_bundle` read blobs from a **hard-coded two-level path**
  (`blobs/<ab>/<sha>`) while `BlobStore` writes **three-level**
  (`blobs/<ab>/<cd>/<sha>`) — the round-trip test seeded only `blob_sha=None`
  materials, so the read path was never exercised (the user's blobs were on
  disk all along). Fix: shared `blob_path()` helper in `storage/blobs.py` used
  by both. En route, export is now **degradation-proof**: a genuinely missing
  blob file no longer 500s — the material/drawing exports without its original
  (`blob_sha`/`png_sha` nulled; extraction + strokes always travel), and
  `manifest.warnings` + the import dry-run preview record what was skipped
  (replaces the old blobs-table 422 check). Round-trip test now seeds real
  blobs (+ asserts archive contents + imported blob file exists) and a new
  missing-file degradation test covers warn → import → search. 390 backend
  tests (+1) · frontend untouched (393 verified).

- 2026-08-21 — **Fixed: course deletion 500'd with a FOREIGN KEY error when the
  course had linked material sources** (user report — `DELETE /courses/{id}`
  → sqlite IntegrityError). `purge_course` deleted `material_sources` before
  `material_folders`, but folders carry `source_id` FK → sources; order is now
  materials → folders → sources (mirrors `delete_source`). 389 backend tests
  (+1 regression: source + scan + linked-folder course deletes clean; frontend
  untouched, 393 verified).

- 2026-08-21 — **Plan 22 complete — small wins: palette content search + katex
  dedupe (plan 22 I).** **I1**: the Ctrl+K palette gains a **content-search
  mode** — prefix the query with `?` (`?chain rule`) and it hits the hybrid
  search API (`GET /search`, FTS⊕vec) instead of fuzzy-filtering titles;
  results render as `In "{title}": {snippet…}` rows that deep-link to the
  material page; a `?`-hint line sits under the input in title mode, a
  searching indicator while the query runs. Plain mode is unchanged. **I2**:
  the long-standing dual-katex open issue is closed by **aligning the direct
  dep to ^0.16** (what rehype-katex/remark-math/mermaid/markmap-lib all
  declare) instead of an override — pnpm now resolves a single katex@0.16.47
  for the whole tree; direct usage is only `renderToString` + the stylesheet,
  verified by the block-renderer suites. The boot-loaded katex chunk dropped
  **~781 → 521 kB min (~260 kB / 33 % off first paint)**; no overrides file
  needed. 393 frontend tests (+3: content-mode hits+snippets, hit → material
  navigation, empty state + hint line toggle) — backend untouched (388,
  verified).

- 2026-08-21 — **Organizer artifacts become materials + one-live-artifact
  regeneration (plan 22 J, ADR-051).** The 8E organizer outputs were ephemeral
  (`useState` cards, gone on navigation) and every repeat click duplicated:
  cheat sheet + review returned raw JSON; draft notes inserted a new `ai-draft`
  note each time; the compose kinds (study guide/practice set/error recap/
  mindmap/formula sheet) deduped by content hash only — LLM output never
  matches, so the library piled up. **Now**: cheat sheet is a **compose kind**
  — `POST /nodes/{id}/cheatsheet` persists a `cheat_sheet` material (provenance
  + node link + ingest) on first run; repeat runs **regenerate as a new
  extraction version on the same material** (mindmap-history semantics —
  restore for free) with the current markdown (incl. the user's manual edits)
  as *revision context* in the prompt ("revise, keep their valid additions").
  **Review findings persist as dated `node_review` materials** ("… — Review
  YYYY-MM-DD"; same-day rerun updates that day's report, different days
  accumulate an honest history, shown as clickable chips in the Overview tab);
  **`node_review` is excluded from AI retrieval** (`RETRIEVAL_EXCLUDED_KINDS`
  in the resolver — filtered from both the materials manifest and chunk
  candidates in every scope branch; meta-content must not leak into
  quiz/tutor context), cheat sheets participate normally. **Draft notes dedup**
  — find existing `ai-draft` note on the node → return it (`existing: true`),
  never a second copy. **One-live-artifact rule for compose**: `POST
  /materials/compose` finds a material of the same kind at the placement node →
  without `regenerate` → **409** (no silent duplicates); with it → new
  extraction version + revision context; scope change → new node → new
  material. `GET /nodes/{id}/artifacts` exposes the live cheat sheet, the
  review history and (with `?kind=`) any kind for the dialog. Frontend:
  OrganizerCard shows the existing sheet ("Open existing" → material drawer)
  and a *Regenerate cheat sheet* action; GenerateDialog queries the live
  artifact for the chosen kind/scope and shows a banner (Open link + submit
  becomes *Regenerate*); compose invalidation covers `node-artifacts`.
  388 backend tests (+4: cheat-sheet persist→manual-edit→regenerate-as-v3 incl.
  revision prompt + single-material assertion; review dated persist + retrieval
  exclusion vs cheat-sheet inclusion + same-day update + artifacts endpoint;
  draft-note dedup; compose 409/regenerate-new-version/other-scope) · 390
  frontend tests (+2: workspace overview existing-sheet banner + regenerate
  label + review-history deep-link; dialog banner + regenerate payload).

- 2026-08-21 — **Exam planner + course formula sheet (plan 22 H, migration
  0029).** Analytics knew *how* the student performs but nothing about *when*
  it matters; and the highest-value math artifact required manual assembly.
  **H1 — exam countdown & pacing**: `courses.exam_date` (nullable Date,
  editable in the root node-settings popover — date input, empty clears via
  `model_fields_set` PATCH semantics); new `GET /analytics/exams`
  (`metrics.exam_status`) — courses with an exam 0–30 days out get days-left,
  engagement coverage (**engaged node** = studied materials, notes, quizzes or
  exercises present — straight from the tree counts), remaining/pace
  (nodes/day, off-track > 1.5), and the **first untouched node** (depth-first)
  for a jump target. Today screen gains an **exam card** (calendar icon,
  countdown, coverage bar, pace line — danger styling when off track, one-tap
  jump into the most-behind node workspace). **H2 — `formula_sheet` compose
  kind**: deterministic collector walks course notes (blocks + drawing OCR) and
  latest material extractions, extracts math spans, drops trivial arithmetic,
  dedupes by whitespace-normalized LaTeX, groups by source node (cap 40/node) —
  422 when nothing collected yet; the LLM's job is only organize + title +
  one-line hints with copy-exactly rules; the output is then **stripped of any
  formula not in the collected set** (no invented formulas, deterministically
  guaranteed) and flagged `needs_review` in provenance when >20 % was
  stripped. Launcher entry at the course root (alongside Study guide);
  `COMPOSE_KINDS` extended. 384 backend tests (+4: exam-date CRUD incl. clear
  + invalid, pacing/coverage/most-behind across engagement states, formula
  collect→compose→strip incl. invented-formula removal + needs_review flag +
  prompt embedding, no-sources 422; head bumped to 0029) · 388 frontend tests
  (+6: exam card hidden/countdown/coverage/jump/off-track, settings date
  set/clear/non-root absent).

- 2026-08-21 — **Split-view study mode: material ⇄ note side by side (plan 22
  G).** The core laptop study loop — read material, take notes — was two
  surfaces swapped by navigation. New `features/library/SplitStudyPane.tsx`:
  a full-height overlay over the workspace (tab state preserved behind) with
  **MaterialDetailBody (Extraction/Original/Side-by-side, study-state controls
  kept) left and the NoteEditor right** — the note rides slice-A autosave, so
  closing never loses text. **Drag divider** with per-course persisted width
  (`ca-study-split:{course}`, clamped 30–70 %); ≥lg only, plain material
  drawer fallback below. URL-addressable on both workspace routes via
  `?material=<id>&study=<noteId|new>` (validated 'new'|number, refresh-safe);
  study='new' creates a note placed on the material's node (material links →
  non-course-level node → course root) titled "Notes — {material}", then the
  param swaps to the created id (no double-create on remount). Entry points:
  **Take notes** in the material drawer header + the library material page
  (navigates into the owning course workspace), **Study alongside** on a note
  drawer (MaterialPickerDialog select mode → reverse split with the existing
  note). **Quote bridge:** text selected in the reader shows a floating
  *Quote into note* button → `insertQuote` (new MarkdownEditor API) inserts a
  blockquote of the selection + a `ca-material://{id}` source-link line at the
  tiptap cursor (structured node insert, round-trips to markdown); selection
  collapses after quoting. jsdom guards en route (range rect fallback).
  382 frontend tests (+9: pane render, new-note creation + placement callback,
  quote bridge incl. insert payload + dismissal, divider resize + persistence,
  escape close; real-editor insertQuote blockquote+link round-trip; study-
  alongside button gating; Take-notes button render/fire + absent) — backend
  untouched (380, verified).

- 2026-08-21 — **Course bundles (`ca-course/v1`) + single-artifact export (plan
  22 F, ADR-050).** Whole courses couldn't travel: the backup zip is whole-
  profile + personal data, and re-uploading loses extractions/notes/tree/
  quizzes. New `services/course_bundle.py`: **`GET /courses/{id}/export`** zips
  manifest + course meta + tree + concepts (links + coverage) + materials
  (latest extraction, index card, node links, provenance) + notes (blocks,
  drawings w/ strokes + OCR) + quizzes (+questions incl. metadata) + exercises
  (all kinds incl. `card_*`) + course-scope skill overrides + content-addressed
  blobs — **personal data never travels** (no attempts/answers/mistakes/
  item_stats/help events, exercise sessions, FSRS/review rows, chats,
  read-status, analytics). **`POST /courses/import`** (raw body, `dry_run`
  param): validation (manifest/format/all FK targets exist/blobs present) →
  preview card (title, counts, warnings); commit imports as a **new course**
  with id remapping everywhere (tree rebuilt via TreeService so paths/sorts are
  native, concept ids remapped into question `concept_ids`, materials written
  `ready` with their extraction + re-chunked + **FTS rebuilt** — no re-OCR,
  no jobs), title collision → " (imported)", skills land as course-scope forks.
  Frontend: Courses page **Export** link per card + **Import course** button
  with dry-run preview → confirm → navigates into the new workspace. **F2**:
  note editor gains **Print** (navigates to the standalone `/note/{id}?print=1`
  page which auto-prints after load; the global print CSS hides chrome) and
  **Export .md** (self-contained file — `ca-drawing://N` refs fetched and
  inlined as base64 data URIs). 380 backend tests (+2: full export→import
  round-trip incl. tree/concepts/materials/links/search FTS/notes+drawings/
  quiz+exercise remaps + collision suffix; bad-archive rejection ×3 shapes) ·
  373 frontend tests (+2: export link href, import dry-run→commit flow).

- 2026-08-21 — **Handwriting becomes first-class: canvas v2 + inline drawing
  blocks (plan 22 E, ADR-049).** Drawings were second-class — a fixed 900×480
  canvas with one hard-coded pen, appended *below* the markdown body as cards;
  text and diagrams couldn't interleave (the Xournal++-shaped gap). **E1 —
  DrawCanvas v2** (`components/canvas/DrawCanvas.tsx`): toolbar with pen /
  **eraser (stroke-hit erase)**, 4 ink colors, 3 pen widths, **undo/redo**
  (redo stack), confirm-gated clear; **pressure-modulated stroke widths**
  (`PointerEvent.pressure`, segment-wise rendering); **variable canvas height**
  (grows with content past the 480 min, width locked at 1400 logical,
  DPR-aware ≤2×); `strokesToPng` derives size from the stroke bbox. Strokes
  gain `tool`; quiz write-mode (C18) rides the same component unchanged.
  **E2 — inline drawing blocks**: note bodies serialize drawings as
  `![drawing](ca-drawing://N)` markdown; server parses `body_md` into
  interleaved `text`/`drawing` blocks (`_md_to_blocks`) with **422 on unknown
  drawing ids** (create/compose/AI-draft route through the same parser);
  `_blocks_md`, search and version history round-trip the refs. Frontend:
  `@tiptap/extension-image` + custom NodeView (`components/editor/DrawingImage.ts`)
  renders the blob PNG + collapsible *Transcript* inline in the editor;
  MarkdownEditor exposes `insertDrawing` (cursor insert) + an Insert-drawing
  toolbar button; **Convert-to-text auto-inserts the fresh drawing at the
  cursor**; drawing cards keep an *Insert inline* action (cards = fallback for
  unreferenced drawings). BlockRenderer gains a `drawing` case (+ optional
  `resolveDrawing`). **ContextResolver** renders a drawing block's OCR markdown
  **in position** (fenced) and appends only unreferenced drawings — quizgen and
  the tutor see handwriting where the student wrote it. En-route:
  jsdom quirks fixed in tests (pointer-capture guard, getClientRects stubs).
  378 backend tests (+3: interleaved-block parse + unknown-ref 422 + restore
  round-trip, resolver in-position ordering, search) · 371 frontend tests
  (+7: DrawCanvas pen/eraser/undo-redo/clear/grow + strokesToPng ×2,
  MarkdownEditor drawing round-trip + insert API, BlockRenderer drawing ×2,
  NoteEditor inline-ref rendering + convert-inserts-inline).

- 2026-08-21 — **Never-lose-notes round 4: trash + course-delete backup guard
  (plan 22 D, ADR-048, migration 0028).** Deleting notes/quizzes/exercises/chats
  was immediate and permanent (only tree nodes had undo); a mis-click had no
  remedy short of a full-backup restore. New `services/trash.py`: every
  `DELETE` of those entities first snapshots the **whole subtree** into
  `deleted_items` (JSON payload — notes incl. drawings w/ embedded PNG base64 +
  note versions; quizzes incl. questions, attempts, answers, mistakes,
  item_stats, help events; exercises incl. steps, sessions, step attempts,
  FSRS state, review log; chats incl. messages + proposals), then runs the
  existing cascades, then returns `{deleted_item_id}` (DELETEs are 200+body
  now, no longer 204). TTL **7 days** (`purge_after`), purged at boot + on
  every trash listing; `GET /deleted-items`, `POST /deleted-items/{id}/restore`
  (re-inserts with **original ids**; if sqlite reused an id meanwhile, the
  collided rows are re-inserted with fresh ids and child FKs remapped),
  `DELETE /deleted-items/{id}` (purge now). Frontend: shared
  `UndoDeleteNotice` ("Deleted — Undo", 8 s, auto-restore) on the Notes tab,
  Practice tab and the chat panel; **Trash card** in Settings → Data
  (entity-type chip, restore, delete-forever). **Course deletion is guarded**:
  `DELETE /courses/{id}` returns 409 without `confirmed_backup=true`; the
  guarded path creates a fresh full backup (plan 22 C machinery) before
  purging — the Courses-page confirm dialog now says so. Materials/folders
  stay untrashed by design (blob store + extraction versions + automatic
  backups cover them). 375 backend tests (+7: per-entity snapshot→delete→
  restore round-trips incl. quiz-with-attempts and exercise-with-review-log,
  expiry purge, purge-one, course guard; 204→200 assertions updated, head
  bumped to 0028) · 364 frontend tests (+6: UndoDeleteNotice ×3, TrashCard
  ×4 — net of suite count).

- 2026-08-21 — **Never-lose-notes round 3: automatic backups + boot recovery
  (plan 22 C, ADR-047).** Backups were manual-download-only — the `backups/`
  dir was created and never written to; a user who never clicked Download had
  no backup at all. New `services/backup.py` (zip core extracted from
  `api/backup.py`) + `BackupScheduler` (startup run ~60 s after boot + every
  interval hours, default 24): writes `auto-/manual-YYYYMMDD-HHMMSS.zip` into
  `backups/`, **validates every archive after writing** (reopen + manifest +
  `PRAGMA integrity_check` — corrupt backups discarded, not counted), rotates
  **14 dailies + 8 weekly representatives** (one per ISO week beyond the daily
  window; only files it named are ever deleted), and **copies each backup into
  an optional sync folder** atomically (`manual-*.part` → rename) with the same
  retention — point it at Nextcloud/Dropbox for off-machine redundancy.
  **Boot integrity check** in `create_app`: corrupt `app.db` → quarantined as
  `corrupt-<ts>.db` (WAL sidecars removed) → newest *valid* backup restored →
  event recorded in `last-recovery.json` and surfaced in Settings → Data; no
  valid backup → fresh DB (corrupt file preserved). New endpoints:
  `GET /backup/status` (settings + list + last recovery), `PUT /backup/settings`
  (validated overrides, persisted to `backup-settings.json`, empty sync_dir
  clears), `POST /backup/create` (manual now), `POST /backup/{name}/restore`
  (server-side restore of a stored backup), `DELETE /backup/{name}`. Settings →
  Data gained the **Automatic backups card** (toggle, interval, retention,
  sync picker, Back up now, backup list w/ confirm-gated restore + delete,
  recovery notice); `docs/usage/backup.md` rewritten. En-route: restore core
  refactored shared between upload + by-name. 368 backend tests (+6:
  validated create, retention arithmetic across weeks, scheduler due-logic +
  sync dir + auto-off, boot recovery from valid backup, quarantine w/o backup,
  API status/create/settings/delete/restore-by-name incl. sync-dir clear) ·
  351 frontend tests (+6 DataTab).

- 2026-08-21 — **Never-lose-notes round 2: version history (plan 22 B, ADR-046,
  migration 0027).** Note PATCHes used to overwrite the body irreversibly — a bad
  edit was unrecoverable. `note_versions` snapshots the **pre-write** note row
  (title, tags, body, cause) **server-side, coalesced**: a snapshot is only taken
  when the latest version for the note is ≥10 min old or the PATCH carries
  `force_version` — autosave spam creates ≤ ~6 versions/hour while discrete
  checkpoints always land; cap 50/note (oldest pruned), FK cascades with the note.
  API: `GET /notes/{id}/versions` (list w/ cause+chars) · `GET
  /notes/{id}/versions/{vid}` (full body) · `POST /notes/{id}/restore` — restore
  writes the old body and force-snapshots the pre-restore state (cause
  `restore`), so restores are themselves undoable (same semantics as mindmap
  history). Frontend `NoteHistoryDialog` (History button in the editor action
  row): version list with cause chips + rendered preview, **Restore** (warns
  when unsaved edits would be discarded, clears the draft after success so the
  restored text is what you see) and **Save version now** (two-step PATCH: persist
  current body, then force-checkpoint it). 362 backend tests (+3: coalescing +
  force + title-only no-snapshot, restore round-trip + 404s, cap-at-50 +
  cascade-on-delete; migration-head assertions bumped to 0027) · 345 frontend
  tests (+5: version list + preview, restore flow, save-version-now, dirty
  warning, empty state).

- 2026-08-21 — **Never-lose-notes round 1: autosave + crash-safe drafts + stale-write
  guard (plan 22 A, ADR-046).** Note bodies were only persisted on an explicit Save
  click — closing the drawer, navigating away or a crash silently destroyed
  everything typed since. `features/notes/useNoteAutosave.ts` (used by both editor
  surfaces): debounced autosave **1.5 s after the last keystroke / 10 s max
  latency**, automatic **5 s retry** while a save fails, a truthful
  *Unsaved / Saving… / Saved* status chip (manual Save = flush now), a
  **localStorage draft mirror** (`ca-note-draft:{id}`, written when the debounce
  fires) with a **restore/discard recovery banner** when the mirror is newer than
  the note (crash/kill recovery), an unmount + `beforeunload` flush (mirror is the
  safety net when the last request can't complete), and a **409 stale-write guard**
  against two-window editing — `PATCH /notes/{id}` accepts `base_updated_at`;
  mismatch → 409 → the editor offers *reload theirs / keep mine* (no silent
  overwrite). En route: `json()` in the API client now throws `ApiError` carrying
  the HTTP status (was a bare `Error`); the guard compares tz-normalized datetimes
  (SQLite round-trips `updated_at` naive, in-memory copies aware — caught red by
  the new backend test). Save-in-flight typing is preserved (draft only clears when
  it still equals the saved body). 359 backend tests (+1 base-guard) · 340
  frontend tests (+6: debounce autosave + mirror clear, retry, 409 reload/overwrite,
  recovery banner restore + discard, unmount flush; AI-append test moved to the
  objectContaining payload shape).

- 2026-08-21 — **Fixed: nested `<button>` hydration error on the Practice tab
  grid (user report).** `EntityItems` grid tiles were `<button>`s containing
  the kebab `<button>` — invalid HTML. Tiles are now divs with button
  semantics (`role="button"`, `tabIndex`, Enter/Space activates, focus ring);
  list rows and the kebab stay real buttons. 334 frontend tests green
  (backend untouched).

- 2026-08-21 — **Global Flashcards page retired — cards are course-workspace
  only (user request).** The rail's *Flashcards* nav entry and the palette
  action are gone; `/flashcards` redirects to `/courses` (same one-release
  convention as the old /quiz + /exercises pages) and `FlashcardsPage` +
  its test were deleted. The workspace **Cards tab** absorbed the page's
  remaining duties: **Import .apkg** and **Export Anki deck** joined its
  action bar (course-scoped, import posts to the workspace course). Deep
  links updated: Today's *Review now* opens the workspace **Cards tab** of
  the selected course (course picker → `/courses` when none), Scores' review
  *go* points at `/courses`. `ReviewQueue` still shared by the tab.
  334 frontend tests (−4: page suite deleted, nav/palette assertions
  inverted; backend untouched, verified green).

- 2026-08-21 — **Fixed: pytest runs clobbered the developer's real keyring API
  keys (user report).** Provider-CRUD tests write secrets through
  `app/core/secrets.py` → the **real OS keyring** under the fixed service
  `CourseAssistant` / refs `provider:N` — and fresh test DBs restart provider
  ids at 1, i.e. the *same refs as the user's live providers*, so every suite
  run overwrote/deleted their actual API keys. Fix: `tests/conftest.py`
  installs an **in-memory keyring backend** for the whole suite
  (`keyring.set_keyring(TestKeyring())` before anything imports the app) —
  verified by running the provider tests and checking the live keyring entry
  survived. Consequence for anyone hit by this: re-enter provider keys once in
  Settings → Providers (overwritten values are unrecoverable). 358 backend
  tests (count unchanged; frontend untouched).

- 2026-08-21 — **Fixed: pending exercise answers showed raw LaTeX in the tutor
  chat** (user report: *"My current answer (not submitted yet):
  \sqrt[23]{233}"* — no rendering). The ask-the-tutor seed message and the
  turn context block injected the pending answer without math delimiters, so
  markdown-math never picked it up; both now wrap it in `$$…$$` (skipped for
  structural JSON answers). 358 backend tests (assertions updated).

- 2026-08-21 — **Fixed: user chat messages rendered as plain text** (user
  report — math (and markdown) typed by the student showed raw LaTeX).
  `MessageBubble` rendered user messages as a bare `<p>`; they now go through
  the same `BlockRenderer` as assistant messages (markdown + KaTeX +
  mention chips). 338 frontend tests (+1: user bubble renders bold + katex;
  backend untouched).

- 2026-08-21 — **Exercise player: "Ask the tutor" with live step context + fixed
  the permanently-disabled hint button (user report).** The hint button's
  disabled condition (`nextHintLevel > hints.length`, i.e. `n+1 > n`) was a
  tautology — the ladder was unreachable from the UI; now disabled only while
  pending or after level 5. New **Ask the tutor** button (Player footer, next
  to hints): `POST /exercises/sessions/{id}/ask` finds-or-creates a chat
  session bound to the exercise session (seeded with the step prompt + current
  typed answer). **The tutor always sees the latest state**: every ask-click
  re-syncs the pending (typed, unsubmitted) answer into the binding, and every
  chat turn rebuilds the context block from the DB — current step (index,
  prompt), pending answer, submitted-attempt count + latest outcome. While the
  current step is unsolved the turn runs under an **exercise no-answer-reveal
  guard** (math expected feeds the leak-guard contract; new
  `EXERCISE_GUARD_RULE` coaches the attempt instead of revealing; lifted on
  solve/completion). `_build_messages` now takes the guard rule text instead
  of a bool. 358 backend tests (+5: bound chat seeded w/ pending answer +
  guard, re-ask updates the same chat, guard lifts after solving, attempt
  status visible, completed-session 422) · 337 frontend tests (button wired;
  suite unchanged).

- 2026-08-21 — **Fixed: exercise/quiz math inputs rendered as an empty box**
  (user report: generated multi-step exercise had no input area — just an
  empty border). Root cause: the `<math-field>` custom element was **never
  registered** — every mathlive import was type-only (plus static.css), so
  mathlive's runtime never loaded and the tag stayed an unknown element.
  Fix: `MathInput` lazily registers it via a shared
  `ensureMathlive()` (module-level memoized dynamic `import('mathlive')`,
  which self-defines the element and guards double registration), showing a
  pulse placeholder until ready; the spike page's hand-rolled field uses the
  same loader. Bundle stays on budget: mathlive (~800 kB / 219 kB gzip) is its
  own **on-demand chunk**, loaded when the first math input mounts — the entry
  chunk is unchanged (~735 kB). 337 frontend tests green (backend untouched).

- 2026-08-21 — **Fixed: exercise generation failed on set-valued answers**
  (user report: *"step 1: expected_value does not parse as math
  ('\{1, -1, i, -i\}')"* — fourth-roots-of-unity style answers). Root cause:
  `parse_math` fed a comma list to `parse_expr`, which returns a Python
  **tuple** → `free_symbols` crashed with `AttributeError` (in exgen
  validation *and* would have crashed grading the same answer). Fix
  (`app/math/equivalence.py`): LaTeX set literals `\{…\}` survive
  normalization as a `__SET__(…)` wrapper and parse to a SymPy `FiniteSet`
  (top-level comma split); bare lowercase `i` now maps to the imaginary unit
  (was a stray symbol); the **symbolic stage** handles sets via
  simplify-equality or empty symmetric difference (order-insensitive:
  `\{1,-1,i,-i\}` ≡ `\{-i,i,-1,1\}`, but ≠ `\{1,i\}`); the sampling stage
  short-circuits for sets. Regression tests ×5 (parse sets, order-insensitive
  equivalence, different-set rejection, set-vs-scalar, lowercase i).
  353 backend tests (frontend untouched, verified green last run).

- 2026-08-21 — **Practice tab: exercise generation is a second primary action
  (user request).** Both **Generate quiz** and **Generate exercise** render as
  blue filled buttons (Import stays outlined) — a documented exception to the
  plan-20 one-primary-per-tab rule, since the two generation flows are peers
  on that tab. The exercise button was also relabeled from the ambiguous
  "Generate" to **"Generate exercise"** (`exercises.generate`, used only
  there). 337 frontend tests green (backend untouched).

- 2026-08-21 — **Standalone note page (`/note/{id}`) gained its focus chrome:
  ✕ close + origin-return + Delete (user report — opened from a chat mention
  chip it had neither).** The route now follows the focus-mode convention:
  `validateSearch` accepts `?from=`, and a new `NoteFocusPage` wrapper
  (`features/notes/NoteFocusPage.tsx`) computes the fallback (the note's own
  workspace Notes tab, `/courses` last resort) and hands `onClose =
  useOriginBack(from, fallback)` to the editor — so the ✕ returns to wherever
  the note was opened from. `NoteEditor` stays router-free and gained a
  **Delete** button in its action row (confirm-gated; invalidates notes/tags/
  tree then closes/returns — works in the drawer too), reusing the notes-tab
  delete flow. Note deep-links now carry their origin: the chat `EntityMention`
  note chip, the ProposalCard *open the note* link and the exercise summary-note
  link all pass `search={{ from }}`. 337 frontend tests (+2: delete confirms/
  cancels incl. onClose, note chip href carries origin; two link assertions
  updated for the `from` param; backend untouched, verified).

- 2026-08-21 — **Workspace Materials tab: grid/list toggle + right-click menu
  (round follow-up).** The tab now reuses the library's material family
  (`MaterialList`/`MaterialRow`/`MaterialTile`) instead of list-only rows: a
  persisted `ViewToggle` (`ca-materials-view`, default list), grid tiles keep
  the AI badge and **drag-to-tree assignment**, and **right-click** on an
  assigned material opens the shared context menu (Open · Remove from node —
  the hover ✕ stays in list mode; child-section rows keep Open-only menus
  since unassign targets the current node). **Styling follows the tab
  convention (user follow-up)**: the Card containers are gone — plain section
  headings + `space-y-2` like the Notes/Practice tabs (no "Assigned materials"
  title card, no borders; child groups are collapsible heading rows).
  **Cross-tab visual unification (second follow-up)**: all item grids/rows
  share one language now — `EntityItems` tiles are borderless like
  `MaterialTile` (resting transparent border, hover border + subtle bg,
  centered icon size-8 + `text-xs` two-line title + `text-[10px]` meta) and
  its list rows match `MaterialRow` (`px-2 py-1.5`, gap-2, rounded-md); the
  library's folder tiles and `MaterialTile` hover moved from the invisible
  `hover:bg-surface` to `hover:bg-subtle`. Tile height became `min-h-28`
  (user follow-up: two-line quiz titles were cropped by the fixed `h-28`).
  335 frontend tests (+2: grid⇄list
  toggle round-trip, right-click unassign; backend untouched, verified).

- 2026-08-21 — **Uniform entity actions: rename/delete + grid/list views for
  notes, quizzes, exercises and chats (user request).** Notes could not be
  deleted from the UI at all (the API existed, nothing called it); chat
  sessions, quizzes and exercises lacked both endpoints and UI. **Backend**:
  new `PATCH`/`DELETE` for `/chat/sessions/{id}` (delete clears proposals →
  messages → session), `/quiz/activities/{id}` (delete clears help events →
  answers → attempts → mistakes → item_stats → questions, then the activity
  with ORM cascades), `/exercises/{id}` (delete clears `review_log`, then ORM
  cascades) — all profile-owned, 404 on miss. En-route fixes in
  `purge_course`: it leaked `ChatProposal`, `ItemStat` and `ReviewLog` rows
  and could FK-fail on answered attempts (answers now deleted before
  questions). **Frontend shared primitives** (promoted from the library's
  golden path): `components/ui/ContextMenu` (moved from features/library),
  `components/ui/ViewToggle` + `useStoredView(key, fallback)` (localStorage),
  new `components/ui/RenameDialog` (overlay, Enter/Escape) and generic
  **`components/entity-list/EntityItems`** — one component rendering list rows
  or grid tiles (icon · title · meta · trailing chips) with a hover **kebab
  (⋯)** *and* **right-click** opening the same context menu, so every entity
  list now feels identical. Wired in: **NotesTab** (view toggle + Open/Rename/
  Delete; invalidates notes + tags + tree counts), **PracticeTab** quizzes
  (Open/Export .caq/.qpkg/Print/Rename/Delete — the row links moved into the
  menu) and exercises (Open/Similar/Rename/Delete), **ChatPanel** (⋯ on the
  active session: Rename/Delete, delete returns to the new-chat state);
  Library/folders unchanged (already the pattern). 349 backend tests (+3:
  rename/delete round-trips with cascade assertions for chat/quiz/exercise +
  404s) · 333 frontend tests (+8: EntityItems ×5, notes rename/delete, quiz
  delete, chat session kebab; 2 practice tests updated to the menu model).

- 2026-08-21 — **Fixed: provider failures on the streaming path surfaced as a
  misleading httpx error** (user report: wrong API key showed *"Attempted to
  access streaming response content, without having called `read()`"* instead
  of the real cause). Chat's first LLM call streams; on an HTTP error (401
  wrong key, 403, 5xx…) `raise_for_status()` fired inside `client.stream()`
  and `_provider_failure` then read `error.response.text` on a body that was
  never streamed — `httpx.ResponseNotRead` replaced the `ProviderError` the
  chat turn was supposed to report. Fix (gateway): new
  `_raise_status_readable` reads the body before re-raising (wired into all
  three `_stream_*` adapters), and `_provider_failure` falls back to the
  status reason phrase if the body still isn't readable — so the UI banner now
  shows **"HTTP 401 …Incorrect API key provided… — check the API key in
  Settings → Providers"**. Regression tests simulate real unread-stream
  bodies (buffered mocks can't reproduce it): 401-with-body and
  503-without-body, both asserting no "without having called" leakage.
  346 backend tests (+2; frontend unchanged, verified green).

- 2026-08-21 — **Fixed: a failed chat turn left the tutor spinning forever**
  (user report — new-chat "hi" endlessly polled messages with no reply). The
  `chat_turn` job handler now catches turn failures and emits a
  **`turn_error`** event (with the error detail, capped at 300 chars) on the
  session's `chat:{id}` WS topic before re-raising, so the job is still marked
  failed with the full error stored in `jobs.error`. Frontend: `turn_error`
  clears the pending/streaming state and shows a dismissible
  **"The tutor failed to answer (…)"** banner; a 90-second pending timeout is
  the belt-and-braces fallback when no WS event arrives at all. 344 backend
  tests (+1: broken gateway → turn_error emitted + job failed + user message
  intact) · 325 frontend tests (+1: turn_error clears pending + banner).

- 2026-08-21 — **Chat opens as a new chat; the session is created only on first
  send.** Clicking the chat icon (or the palette's *tutor chat* action) now
  enters a drafting state instead of requiring a picked/created session: the
  composer, + attach menu and starter prompts are active with no session row
  on the backend; `POST /chat/sessions` fires only when the first message is
  sent (titled from the message, scoped to the current workspace course), then
  the message + attachments go out to it (`chat-store.openChat()` without an
  id now yields the new-chat mode; explicit-id callers — ask-about-node, quiz
  help, Today — unchanged). The panel's **+** button became a local reset to a
  fresh draft (no eager session creation anymore). Race hardening: the messages
  query polls briefly while a turn is pending and pending clears when the
  assistant message lands (guards the WS-subscribe-after-create window);
  switching sessions mid-stream clears the streaming state. 324 frontend tests
  (+2: deferred create-then-send, + reset-without-create; citation rendering
  kept via a picker-based test; backend untouched, verified).

- 2026-08-21 — **Chat attachments: the composer "+" menu + tutor UI polish.** The
  chat composer gained a **+ button** opening a six-tab attach menu
  (`features/chat/AttachMenu.tsx`): materials/notes/quizzes/exercises/courses
  (fuzzy-searched, course-scoped when the session is bound) and **file upload**
  (saved through the normal material pipeline into the course's *Chat uploads*
  folder — find-or-create — so uploads are OCR'd, indexed and READable).
  Backend: `POST /chat/sessions/{id}/messages` accepts
  `attachments: [{kind, id}]` (≤10; `course` maps to its root node as a `[T#]`
  ref); `ChatService.attach` resolves titles + summaries (index card / note
  excerpt / question/step counts / course description), merges into the
  session-stable mention registry before the turn, and stores resolved refs on
  the user message (rendered as chips under the user bubble). The model-visible
  user turn gains a "The student attached these items" line. **READ now covers
  quizzes and exercises** (questions + options + correct answers; steps +
  expected answers, char-budgeted), still-processing materials return a
  friendly note instead of an error (and aren't recorded as reads), and
  `tool_round` stream events carry a `phase` (`read`/`math`/`mixed`). Chat UI
  modernized: auto-growing textarea (Enter sends / Shift+Enter newlines),
  removable attachment chips in a focus-ring composer, animated three-dot
  thinking indicator with per-phase labels (*Reading your items…* etc.),
  blinking streaming caret, message entrance animations, empty-conversation
  starter prompts; `Popover` gained a `side="top"` variant for the upward menu.
  343 backend tests (+6: attachments register/prompt-line, cross-kind
  resolution, course→root mapping, Q/E READ e2e, pending-material note,
  404/422) · 322 frontend tests (+6: attach-note send, user chips, upload flow,
  empty-state prompts, thinking dots, read-phase label).

- 2026-08-21 — **Node settings popover: title/description/AI instructions in the
  workspace header (plan 21).** The **AI Instructions for this node** card left the
  Overview tab — per-node configuration now lives in a header popover: new tiny
  `components/ui/popover.tsx` (no Radix; outside-click/Escape/focus-out close,
  `closeSignal` for programmatic close) + `features/courses/NodeSettingsMenu.tsx`
  mounted next to the workspace title (`Settings2` icon, **dot badge when an AI
  instruction is set**). Panel fields: Title · Description · AI instructions with
  one changed-gated Save — non-root batches them into `PATCH /nodes/{id}`;
  root routes title+description through `PATCH /courses/{id}` (+ node PATCH for the
  hint). **Backend fix en route (found while wiring)**: `update_course` never synced
  its root node — renaming a course or editing its description left the workspace
  header stale; it now mirrors `course.title`/`course.description` into the root
  `tree_nodes` row on PATCH. Node/course **descriptions are now first-class
  editable** (header renders `node.summary` with `line-clamp-2` + full text on
  hover); `AiHintCard.tsx` + `updateNodeHint` deleted, superseded by general
  `updateNode`/`updateCourse` API wrappers. 337 backend tests (+1 root-sync) ·
  316 frontend tests (+13: Popover ×7, NodeSettingsMenu ×5, workspace header ×1
  — incl. root title now editable per user follow-up).

- 2026-08-21 — **Uniform tab action bar across the node workspace (plan 20).**
  Every workspace tab (overview/materials/notes/concepts/practice/cards/tutor) now
  opens with the same **`TabActionBar`** (`components/layout/TabActionBar.tsx`):
  first element under the tab strip, exactly one **primary** (filled) action per
  tab — compose (overview), assign material (materials), new note (notes),
  extract concepts (concepts, was outline), generate quiz (practice), generate
  (cards), ask about this node (tutor) — outlined sm secondaries, icons at the
  Button's default size (Import gained `FileUp`), pending spinner + disabled
  handled by the bar, and a right-aligned `info` slot (concepts graph summary
  moved there). Practice's Card-as-toolbar and Concepts' right-aligned
  justify-between header are gone; notes' two error banners merged into one under
  the bar (bar-action errors render there on every tab); coverage-card +
  `ConceptsPanel` split (extract mutation + draft state lifted into the tab,
  panel presentational via `draft`/`onDraftChange` props); ChildCard actions
  uniform outline sm with default-size icons. Documented exceptions stay out of
the bar: page-header actions, root-only OutlineActions, row-level actions,
load-more, draft footers, DrillsCard. 303 frontend tests (+8: TabActionBar ×6,
concepts extract-from-bar ×1, ConceptsPanel cancel ×1; backend unchanged).

- 2026-08-21 — **Skill prompt sync: `exercise.generate` learns the kind
  families; seeding refreshes unmodified system templates** (pre-plan-19
  hygiene). `EXGEN_SYSTEM` still described only the multi-step JSON shape
  while exgen (since plan 18 B2/B3) also generates structural/rubric kinds —
  the system skill contradicted the per-kind schemas riding in the user
  prompt, wasting repair rounds. The seed now teaches both response families
  (default multi-step schema; when the user message names a kind, follow the
  embedded schema exactly). `seed_skills` + `restore_system` **refresh an
  unmodified v1 system template** in place when the seed text changes —
  existing DBs pick up code updates; user-forked versions (v2+) are never
  touched. Tests: seed-refresh updates v1 only and leaves forks alone ×1,
  exgen skill template carries the families ×1. 336 backend tests (frontend
  unchanged).

- 2026-08-21 — **Fixed: no way to review cards from the workspace Cards
  tab** (user report). The review flow existed only on the Flashcards page;
  the Cards tab showed a generate button + a flat listing. `ReviewQueue`
  extracted to `features/flashcards/ReviewQueue.tsx` and mounted in the
  Cards tab **scoped to the node subtree** (`dueFlashcards` gained a
  `node_id` param, backend already supported it); the Flashcards page reuses
  the same component. Reveal → Again/Hard/Good/Easy works in-place now.
  295 frontend tests (+1: cards tab renders the scoped queue and reviews).

- 2026-08-21 — **AI-rubric exercise kinds: explain, error_spot,
  correct_solution (plan 18 B3 — Part B complete).** Three free-form kinds
  graded against rubrics — determinism first: `error_spot` line picks and
  `correct_solution` exact fixes are checked deterministically and only fall
  through to the LLM when that can't decide (explain always AI-graded).
  Backend: `services/exercise_rubric.py` (payload validators — rubric rows
  1-8 with unique ids, error_spot lines+flaw_index, correct_solution fix;
  `RubricGrader` on the existing `grade.freeform` skill via TaskRunner —
  verdict/score/rationale validated, audited, repair loop; public widget
  specs strip rubric/fix/flaw). Kinds registered in the registry
  (`GENERATABLE_KINDS` now 8); exgen prompts carry per-kind JSON schemas;
  answers store the rationale as feedback blocks and the stage line is
  marked **(AI-graded)**. Frontend: GenerateDialog gains an **exercise kind
  picker** (all 8 kinds, incl. structural — closes the B2 UI gap);
  `RubricStepInput` renders per kind (radio line list / MathInput fix /
  essay textarea); Player shows the stage + rationale feedback. Tests:
  rubric validators, generate→AI-graded e2e ×3 kinds, error_spot
  deterministic right/wrong skip-LLM, Player error_spot + explain flows.
  En-route bug fixed: the API's rubric branch initially only honored
  deterministic *correct* results (wrong picks leaked to the LLM).
  334 backend + 294 frontend tests.

- 2026-08-21 — **Structural exercise kinds: matching, ordering, categorize,
  fill_blank (plan 18 B2).** Four new exercise kinds beyond `multi_step` and
  cards — all deterministic (no LLM in grading). Backend: kind registry entries
  (`services/exercise_kinds.py`), new `services/exercise_structs.py`
  (payload validators — pair/item/category/blank sanity; deterministic
  graders with partial-credit stage text; answer-free **public widget specs**
  seeded per step id so orders shuffle without leaking the canonical one).
  `POST /exercises/generate` accepts `kind` (multi_step | matching | ordering |
  categorize | fill_blank; unknown → 422); exgen builds per-kind prompts with
  exact JSON schemas and validates deterministically before persisting (one
  step; expected = `{kind, ...payload}`). Steps API exposes `kind` + `input`
  (widget + shuffled public data); answers submit as structured JSON
  (`response` widened to any) and are graded by the structural checker
  (math steps unchanged — tutor/equivalence chain); `CheckOut.error_class` is
  nullable for structural steps. Frontend: `components/exercise-inputs/` —
  `ExerciseStructuralInput` dispatch + four accessible widgets (matching
  selects, ordering list with move up/down, categorize category chips,
  fill-blank inline inputs); the Player renders the widget instead of
  MathInput for structural steps, gates Check on completeness, submits the
  structured array, and shows the stage line (e.g. "2/4 pairs correct").
  Tests: backend `test_exercise_structs.py` ×5 (validators, grading,
  answer-hiding, per-kind generate→wrong→right e2e, unknown kind 422);
  frontend ExerciseInput ×4 + Player matching flow ×1. 331 backend + 292
  frontend tests.

- 2026-08-21 — **Flashcards fold into exercises as `card_*` kinds (plan 18 B1;
  ADR-045, migration 0026).** The exercise becomes the generic practice item:
  `exercises.kind` (`multi_step` default) + `deck_ref`; one exercise per
  flashcard (`card_basic`/`card_reverse`/`card_cloze`) with the front on the
  step (prompt) and the back in `expected.back` — `created_from` keeps
  `{source, source_ref}`. **The `flashcards` table is dropped** (0026:
  card→exercise copy, `fsrs_states`/`review_log` re-pointed to `exercises.id`
  via raw-DDL rebuilds — the FKs are unnamed in sqlite, batch alter can't swap
  them; downgrade restores the table). The **`/flashcards` REST surface is
  byte-identical** (same routes, `CardOut` with legacy `basic/cloze/reverse`
  kinds) — the frontend needed zero changes; new
  `services/cards.py` maps cards⇄exercise rows, `services/exercise_kinds.py`
  is the kind registry (engines: chain/exact/struct/fsrs/rubric — more kinds
  land in B2+). Exercise list/get now excludes `card_%` kinds (practice views
  stay clean; `ExerciseOut` gained `kind`/`deck_ref`). En-route fix: card
  delete now clears `review_log` explicitly (no ORM relationship — old code
  relied on nothing referencing a deleted card). Tree counts, analytics
  (due/history/streak) and course purge re-pointed to card-kind exercises;
  Anki import/export ride the same mapping (deck_ref preserved). Tests: new
  `test_exercise_kinds_migration.py` ×3 (0026 fold incl. FSRS/review history
  + unnamed-FK rebuilds, downgrade round-trip, API round-trip on the new
  schema) + 2 migration-head assertions bumped. 326 backend + 287 frontend
  (unchanged, verified).

- 2026-08-20 — **Materials open in place + note drawer on the focus shell (plan 18
  A4/A5 — Part A complete).** Opening a material from a workspace Materials tab no
  longer navigates to `/library/$id`: a **`MaterialDetailDrawer`** opens over the
  workspace via a `?material=<id>` search param (the `?note=` pattern — back
  button works, X strips the param, tab preserved). The drawer + the standalone
  library page now share one **`MaterialDetailBody`** (header chips, study-state,
  Extraction/Original/Side-by-side tabs — extracted from MaterialDetailPage);
  the drawer uses the FocusShell overlay (course crumb + title + X). Library
  rows navigate to the detail page with `?from=`; the page's back arrow/breadcrumb
  returns there (fallback `/library`). `FocusShell` generalized: `title` accepts
  ReactNode, optional `onClose`/`ariaLabel`/`contentClassName` — the note editor
  (drawer + full page) now renders through it (inline title input as the shell
  title, `useFocusContext` breadcrumb replacing `NoteBreadcrumb`, FocusShell X
  replacing the button-row close); `NoteEditorDrawer` shrinks to the lazy
  boundary + search helpers. Dead keys removed (`notes.close`; `backToCourses`
  went in the previous commit). 323 backend (untouched, verified) + 287 frontend
  tests (+1: material drawer open/close param flow; note breadcrumb tests
  updated to the focus-shell contract).

- 2026-08-20 — **Focus-mode chrome + origin-return navigation (plan 18 A1–A3;
  A4/A5 pending).** Runners stopped being "naked" and closing them stopped
  dumping you on `/courses`. New shared `components/layout/FocusShell.tsx`
  (page + overlay variants): course ▸ node breadcrumb (deep-linking), title,
  uniform ✕ close, collapsible **Details** meta strip; `useFocusContext`
  resolves course/node titles via the shared `['tree', cid]` query. New
  `lib/origin.ts` origin-return protocol: every runner/player entry point
  (practice rows, sidebar Study…, study launcher, palette, Today, drills,
  mindmap, scores history, EntityMention chips) passes `?from=` (the full
  location it opened from — typed via `validateSearch` on both routes); closing
  returns there, falling back to the object's **own node workspace** practice
  tab (`GET /quiz/activities/{id}` + `GET /exercises/{id}` — new single-object
  endpoints, so deep links/refreshes return somewhere sensible), last resort
  `/courses`. QuizRunner: FocusShell + meta (question count · practice/exam ·
  live elapsed) + progress bar with per-question dot strip (red = wrong);
  summary gains **Open in workspace** (derived placement). Exercise Player:
  FocusShell + meta (step count · difficulty · guided/socratic) + step progress
  bar. 323 backend (+2 single-object GET tests) + 286 frontend (+15: FocusShell
  ×3, origin ×6, QuizRunner origin/context/meta ×3, Player ×3).

- 2026-08-20 — **Bundle code-splitting (plan 17 G).** The note editor is behind a
  `React.lazy` boundary (`features/notes/LazyNoteEditor.tsx` — Suspense spinner;
  both render sites, the drawer and `/note/$id`, use it), which keeps tiptap +
  prosemirror + markdown-it in one lazy 431 kB chunk instead of the entry.
  `vite.config.ts` pins cacheable vendor chunks via rolldown
  `codeSplitting.groups` (`react-vendor` 190 kB, `framer-motion` 125 kB, `katex`
  781 kB — loaded in parallel, cached across releases). **Entry chunk: 2,067 kB /
  627 kB gzip → 697 kB / 192 kB gzip** (target was < 1.2 MB). Rolldown gotcha
  learned: a group's default `includeDependenciesRecursively` merges shared deps
  (react!) into high-priority groups — priorities are react-vendor > framer >
  katex, and a tiptap group had to be dropped entirely (pinning tiptap either
  made the entry statically import it or duplicated react across chunks).
  Verified with a headless-Chromium smoke of the built bundle: boot loads only
  index + runtime + react-vendor + framer-motion + katex, the lazy editor chunk
  evaluates cleanly. New `LazyNoteEditor.test.tsx` ×2 (renders through the lazy
  boundary; onClose passthrough). Residual (open issue): **two katex versions**
  (0.18 direct + 0.16 via rehype-katex/remark-math/mermaid/markmap) are both
  boot-loaded — a pnpm override dedupe is a follow-up. 321 backend + 271
  frontend tests.

- 2026-08-20 — **MCP `get_node_context` (plan 17 F — 10E remainder closed).**
  Eighth tool on the stdio resource server (`app/mcp_resources.py`):
  `get_node_context(node_id, scope='subtree', query?, max_chunks=12,
  profile_id?)` runs the **ContextResolver** (FTS-only in the MCP path — no
  embeddings dependency) and returns `{node_id, course_id, scope, stats,
  rendered}` where `rendered` is the exact budgeted manifest `POST
  /ai/context/preview` returns (materials with index-card summaries, notes,
  concepts, ancestor hints, numbered excerpts); `query` > 500 chars errors.
  External agents now see the same inspectable context as in-app AI (ADR-042).
  Tests: MCP e2e subprocess test extended (tool set, happy path with query, bad
  scope error) + `/ai/tools` catalog assertions (the catalog introspects live,
  so the old seven-tool assertion was updated — it had been left stale by this
  slice's first pass and caught red by the verification gate).

- 2026-08-20 — **Entity actions on course-tree nodes (plan 17 E).** Right-click
  a node in the structure sidebar → **Study…** opens the same generic
  `EntityActionMenu` the mindmap uses, via a new `NodeSource` adapter
  (`features/courses/courseNodeSource.ts` — label = node title, context =
  `{courseId, scopeNodeId}`, no llmHint/CRUD: the sidebar's own add/rename/
  delete stay). The shared per-entity handlers were factored into
  `features/ai/useEntityActionHandlers.ts` (ask = chat session bound to the
  node + openChat; generate = GenerateDialog prefilled `{task, topic, hint}`;
  writeNote = NoteComposeDialog; addNote = create + navigate) — MindmapViewer
  now uses them too. `NodeSource` gained `canAiEdit?` and the menu's
  AI-edit/add-as-section entries are capability-gated (`buildEntityActions`
  includes aiEdit only for editable-by-AI sources — mindmap yes, tree no).
  Study… actions navigate to the created quiz/note on success. Tests:
  `courseNodeSource` ×1, `buildEntityActions` gating ×1.

- 2026-08-20 — **Whole-map mindmap toolbar actions (plan 17 D).** The mindmap
  toolbar "⋯" dropdown grows **Add root node** (`window.prompt` label → new
  `addRootNode()` in `mindmapTree.ts` — depth-0 mirror of `addChildNode`, saved
  through `editExtraction`), **Quiz on this mindmap** (GenerateDialog prefilled
  with topic = material title + the whole-map LLM hint), and **Ask about this
  mindmap** (chat session scoped to the mindmap's placement node). The
  whole-map hint builder is exported as `mindmapLlmHint()` from
  `mindmapSource.ts` (shared with the per-node path). MindmapViewer takes the
  material title from ExtractionView. Test: `mindmapTree` addRootNode round-trip.

- 2026-08-20 — **Shared `MindmapCanvas` (plan 17 C).** The lazy-markmap
  bootstrap (dynamic `markmap-lib`/`markmap-view` import, fit-on-mount,
  element→node click resolution) moved from `MindmapViewer` into
  `features/library/mindmap/MindmapCanvas.tsx` (`{markdown, onNodeClick?,
  className?, apiRef?}`). MindmapViewer delegates to it (Fit button via the
  apiRef handle); the **AI-edit preview** in MindmapEditDialog now renders the
  real interactive map instead of a raw markdown `<pre>`; slice B's history
  preview reuses it too. Markmap-mock tests moved/adapted.

- 2026-08-20 — **Mindmap history & undo (plan 17 B).** New backend endpoints:
  `GET /materials/{id}/extractions` (newest-first version list — `{version,
  extractor, created_at}`, cap 50) and `GET /materials/{id}/extractions/
  {version}` (full `ExtractionOut`; both 404 on unknown material/version). No
  schema change — it rides the existing extraction-version chain every
  QA-edit/AI-edit already maintains. The mindmap toolbar gains **History…**
  (`MindmapHistoryDialog`): version list (extractor + timestamp), readonly
  canvas preview of the selected version, and **Restore** = `editExtraction`
  with the old markdown — a new version, so restores are themselves undoable;
  the map live-updates. Tests: backend round-trip (list → edit → list → fetch
  old → 404); dialog renders versions + restore calls `editExtraction`.

- 2026-08-20 — **Material display unification (plan 17 A).** The four ad-hoc
  material renderers are one family in `components/materials/`: `MaterialRow`
  extended (`status`, read-status/progress pills, `aiBadge`, rationale tooltip,
  `locked`/`lockedLabel` inert mode, `draggable`/`onDragStart`, `actions` slot,
  `compact`, `onContextMenu`), new `MaterialTile` (grid card: KindIcon,
  line-clamped title, AiBadge, status pill) and `MaterialList`
  (  `layout: 'grid' | 'list'` container with empty-state). Migrated call sites:
  LibraryPage (both layouts, local status-badge code deleted), NodeWorkspace
  MaterialsTab (local row now a thin wrapper; local ReadStatusPill deleted),
  MaterialPickerDialog (local row + StatusPill deleted; assigned rows use the
  locked mode). Visual parity per site. Tests: MaterialRow ×3 new, MaterialTile
  ×2.

- 2026-08-20 — **AI mindmap editing.** New `POST /materials/{id}/mindmap-edit`
  (`app/api/materials.py`, `mindmap.edit` skill prompt) rewrites a mindmap's markdown
  outline via the `material_compose` task given a `mode` (expand / simplify / reorganize /
  add-examples / custom) + optional instruction + optional `focus_node`. The mindmap
  toolbar gains a "⋯" dropdown with **AI edit mindmap**, and each node's action menu gains
  an **AI edit** entry; both open `MindmapEditDialog` (mode + instruction → preview →
  apply via `editExtraction`, which live-updates). Whole-map and per-node edits share the
  same endpoint.

- 2026-08-20 — **Material picker reuse + shared material row.** The GenerateDialog's
  "Add material" is no longer a plain `<select>` — it opens the `MaterialPickerDialog`
  explorer (folder-tree sidebar, fuzzy search, linked-source browse, ingest-and-select)
  in a new `select` mode that returns the chosen ids via `onSelect` (the dialog now
  supports `mode: 'allocate' | 'select'`). Extracted a reusable `MaterialRow`
  (`components/materials/`) used for the dialog's in-scope/added material lists; the
  library/workspace/picker call sites remain ad-hoc for now (migration is a follow-up).

- 2026-08-20 — **Mindmap node actions (reusable entity-action menu, ADR-044
  follow-up).** Clicking a mindmap branch selects it and opens a generic
  `EntityActionMenu` driven by a `NodeSource` adapter (`components/entity-menu/`):
  Ask (chat bound to the node), Quiz/Exercises/Flashcards/Study guide (pre-filled
  `topic` + an LLM hint that states the selected node and includes the whole mindmap,
  capped at 1800 chars, via the existing `context_hint`), Write note, Add note,
  Add as section (`addNode` under the mindmap's node), and Add child / Edit / Delete
  (mindmap markdown editing). The mindmap outline is editable via
  `features/library/mindmap/mindmapTree.ts` (markdown ↔ tree round-trip) and saved
  through `editExtraction`. No new backend endpoints — reuses the compose/generate/
  chat/note/node APIs. Tests: `mindmapTree`, `mindmapSource`, `buildEntityActions`,
  `EntityActionMenu` (+ unit coverage of the round-trip and hint).

- 2026-08-20 — **Study launcher: "Study here" opens an AI action menu (ADR-044,
  post-1.0 backlog, plan 16).** The node-workspace "Study here" CTA no longer
  silently generates an 8-question quiz — it opens a **study launcher** (quiz,
  exercises, flashcards, study guide, summary sheet, practice set, error recap,
  **mindmap**, **write a note**), each routing to the existing `GenerateDialog`
  (pre-scoped to the node) or a new `NoteComposeDialog`. New backend: a `mindmap`
  compose kind (`app/pipelines/compose.py` — a markdown outline rendered as an
  interactive `markmap` mindmap in `MindmapViewer`, replacing the plain Mermaid
  block) and
  `POST /notes/compose` (`app/api/notes.py` — ContextResolver scope → `notes.compose`
  skill on the `description` task → a placed `Note`). Docs: `docs/usage/courses.md`,
  `docs/features.md`, `docs/ai.md`.

- 2026-08-20 — **Settings: load `backend/.env` and document the XDG_DATA_HOME
  gotcha.** API keys are stored only in the OS keyring (`CourseAssistant/provider:{id}`),
  never in the DB — the DB stores just `providers.keyring_ref`. The DB lives under
  `CA_DATA_DIR` → `XDG_DATA_HOME` → `~/.local/share/CourseAssistant`, but the VS Code
  snap rewrites `XDG_DATA_HOME` to a revision-specific path (`~/snap/code/<rev>/…`), so
  a snap update moves the DB and orphaned the provider→key link (keys looked "deleted"
  on restart). `Settings` now reads `env_file=".env"` so `backend/.env` can pin
  `CA_DATA_DIR` to a stable path; documented in `docs/usage/getting-started.md`.

- 2026-08-20 — **Fixed: "Ask about this node" crashed the app** (user report;
  `DOMException: An attempt was made to use an object that is not, or is no
  longer, usable`). The `WsClient` called `socket.send()` on subscribe/
  unsubscribe without checking `readyState`; under React StrictMode the
  ChatPanel effect runs mount→cleanup→mount, so the cleanup fired an
  unsubscribe frame on a socket that was still CONNECTING (or already
  CLOSING), throwing `InvalidStateError` and crashing ChatPanel. Fix: a
  `send()` helper that only writes when `readyState === OPEN` (subscribes are
  re-sent by the `onopen` resubscribe pass; unsubscribes are dropped safely —
  the topic is already removed so a reconnect won't resubscribe it). Added a
  regression test (no-throw/no-send on a closed socket). 228 frontend tests.

- 2026-08-20 — **Phase 11E: companion glue + solidity leftovers (ADR-043) —
  Phase 11 complete.** `notes_ocr` now resolves its prompt through
  `SkillService` (`notes.transcribe`), so hand-written transcription honors
  user/overriding skill versions like every other task (closes §6.4; new
  override test). Exercise-completion **session summary note**: new
  `POST /exercises/sessions/{id}/summary-note` (completed sessions only —
  deterministic recap of hints used + incorrect steps, tag `session-summary`),
  with a Save-summary button + note deep-link on the Player completion screen.
  Today screen: drill/challenge recommendations gain an **Ask the tutor about
  {concept}** one-tap (course-bound chat session, opens the sidebar). Settings
  Tasks tab: an inline nudge with consequence text when `embeddings` or
  `concepts` is unassigned. Skills sandbox covers the mention/proposal
  protocol by construction (chat contract builders add `mentions_in_range` +
  `proposal_valid`). 315 backend tests (+2: summary-note lifecycle, notes_ocr
  override) + 227 frontend tests (+2: Today ask-tutor, tasks nudge).

- 2026-08-20 — **Phase 11D: AI-composed material (ADR-043).** New
  `material_compose` task + `material.compose` skill seed; `TaskRunner`
  gains **`run_text`** (markdown repair-loop variant with the same uniform
  audit). New `app/pipelines/compose.py`: brief + ContextBundle → markdown →
  deterministic validators (400–60k chars, mention handles in range) →
  2-round repair → `create_text` `.md` material → standard ingest queues
  indexing → **auto-assign to the scope node** ("AI-composed" rationale).
  Compositions exclude `ai-composed` materials from their own context
  (`ContextSpec.exclude_ai_composed` — never ground on prior compositions;
  chat retrieval unchanged). Migration **0025** `materials.provenance`
  (`{source, kind, model}`) on all material payloads → `AiBadge` in the
  library grid + workspace material rows. Math lint is advisory + sampled
  (≤5 LaTeX spans parse-checked, logged). Kinds: study guide / summary sheet /
  practice set / error recap. `POST /materials/compose` (context params +
  502 on provider failures); GenerateDialog gains the **compose preset**
  (kind/title/instructions + scope picker + live preview); chat
  `compose_material` proposal executes at approve time (stale on failure).
  311 backend tests (new `test_compose.py` ×5: e2e ready+assigned+indexed,
  self-exclusion, validator rejection leaves no rows, unknown kind 422,
  chat-proposal path) + 225 frontend tests (compose preset ×1).

- 2026-08-20 — **Phase 11C2: proposal actions, revalidation, dismissal
  feedback (ADR-043).** The proposal whitelist grows to six actions:
  `assign_material`, `cover_concept`, `set_node_ai_hint` (pydantic schemas +
  prompt doc), executed by new `services/proposal_actions.py` at
  approve-click time with **execute-time revalidation** against current
  state — satisfied actions complete `executed` with a no-op note, invalid
  targets (deleted node, cross-course material/concept) mark the proposal
  **`stale`** with the reason (new status; card renders the explanation, no
  retry). `generate_quiz`/`generate_exercise` proposals never auto-run:
  approve marks `approved` and returns `open_dialog` params; ChatPanel mounts
  the shared GenerateDialog **prefilled** (new `initial` prop — topic/count/
  steps/difficulty) and the Generate click inside the dialog is the approval.
  Dismissal feedback: ≥2 dismissed proposals in a session inject a
  conservative note into the system prompt (`DISMISSAL_NOTE`). Frontend
  ProposalCard renders from the mutation result (instant status flips), new
  action icons/labels, stale explanations, Open-generator button;
  `GenerateRequest` handoff type. 308 backend tests (test_chat_proposals ×12:
  assign idempotent + 409, stale-on-deleted-target, cover-concept e2e,
  generate→approved+params, dismissal-note prompt injection) + 224 frontend
  tests (ProposalCard ×7: generate handoff ×2, stale rendering).

- 2026-08-20 — **Phase 11C1: HITL proposal cards, core (ADR-043).** New
  `app/ai/proposals.py`: the ```proposal fenced protocol (≤1/turn), pydantic
  payload whitelist (`create_note` this slice), validation + extraction +
  stripping helpers. New blocking contract constraint `proposal_valid`
  (enabled via `proposals_enabled` context — course-bound chats only; unbound
  sessions are not taught and cannot propose): bad JSON / unknown action /
  bad payload / multiple fences trigger the existing repair round, and
  anything still invalid is stripped from the stored message. Migration
  **0024** `chat_proposals` (message FK, action, payload JSON, status
  proposed|dismissed|executed, result, executed_at); chat service extracts the
  valid proposal after the loop, stores the message *without* the fence, and
  emits the proposal in `assistant_message` + the messages API. Execution is
  **click-gated by construction**: `POST /chat/proposals/{id}/approve` is the
  only execution path (create_note → `TreeService.placement_node` → real Note
  tagged `ai-proposal` with search_text; audited `context_type=proposal`;
  re-approve/approve-after-dismiss → 409, no double writes);
  `POST /chat/proposals/{id}/dismiss` records dismissal. Frontend
  `features/ai/ProposalCard.tsx`: status badge (Proposed/Dismissed/Created),
  expandable payload preview (framer-motion), Approve/Dismiss with pending
  spinners, deep-link to the created note; wired into ChatPanel bubbles;
  `ai.proposals.*` i18n keys. 302 backend tests (new
  `test_chat_proposals.py` ×7: protocol validation good/bad/unknown/double,
  repair-loop integration, no-execution-before-approve + audit + 409s,
  dismiss-blocks-execution, unbound-session gating) + 222 frontend tests
  (ProposalCard ×5).

- 2026-08-20 — **Phase 11B: chat on-demand context — READ tool, hybrid
  retrieval, context panel (ADR-043).** Chat now resolves context through the
  Phase-10 `ContextResolver` (subtree scope at the session node, user message
  as query, 6 seeded chunks) — chat retrieval is hybrid (FTS ⊕ sqlite-vec)
  like every other task, closing the last FTS-only path; unbound sessions call
  `retrieve_chunks_hybrid` directly. The prompt is **manifest-first**: the
  registry section (now with index-card summaries via `MentionRef.summary`)
  precedes the numbered sources. New **`READ <handle>`** tool line (catalog +
  regex + execution): deterministic fetch of an offered item (material's latest
  extraction markdown / note body + drawing OCR / concept / node summary),
  char-budgeted 4k, **own budget of 3/turn** on top of the 2 math rounds
  (mixed CALC/SYMPY/READ turns verified in tests), unknown/out-of-scope handles
  → error line to the model (never content); tool results accumulate across
  rounds and stay model-only. Migration **0023** `chat_messages.reads` —
  per-message read records (ref/kind/id/title/course_id/chars) surfaced in
  `MessageOut` + the `assistant_message` WS event, rendered as eye-icon
  `ReadIndicator` chips. Tool documentation is now **generated from
  `CHAT_TOOL_CATALOG`** (`build_tool_doc` → `CHAT_TOOL_DOC`) — the system
  prompt and the Tools dialog share one source (READ listed automatically).
  New `GET /chat/sessions/{id}/context` (scope node + latest-notes +
  accumulated registry) powers the collapsible **"What the AI sees"**
  `ContextPanel` (`features/ai/`, framer-motion disclosure, EntityMention
  chips). En route: `ProviderError` now logged with its friendly reason in the
  embeddings/describe postprocess paths (§6.7 verified), `CONTEXT_VARS` gained
  `mention_manifest`/`tool_results` (§6.3), `ai.context.*` i18n keys.
  296 backend tests (new `test_chat_read_tool.py` ×8) + 217 frontend tests
  (ChatPanel context-panel/read-indicator coverage).

- 2026-08-20 — **Phase 11A: entity mentions (ADR-043, plan
  `dev/plans/15-ai-companion.md`).** New `app/ai/mentions.py`
  (`MentionRegistry` + parser; handles `[M#][N#][C#][T#]` are real ids, `Q/E`
  reserved for future contexts; out-of-range handles stay literal). The context
  resolver gains `ContextBundle.mentions()` and a structure section (scope node
  + children, cap 16) in the rendered prompt. Migration **0022**:
  `chat_messages.mentions` + `chat_sessions.mention_registry` — chat builds a
  **session-stable registry** (accumulates across turns, never renumbers; also
  offers the session's scoped material titles, cap 30, independent of per-turn
  retrieval), teaches it in the prompt, stores resolved mentions on the
  assistant message, and emits them in the `assistant_message` WS event;
  quizgen explanations and exgen context/step blocks attach `mentions` to their
  text blocks (they surface via answer feedback). Contracts: new
  `mentions_in_range` constraint — **advisory** in the chat contract (new
  `Constraint(advisory=True)` support in the engine; violations go to structlog
  as the rollout signal, never block/repair). Skill seeds teach the protocol
  (chat/quizgen/exgen; existing DBs pick it up via the injected registry
  section). Frontend: `features/ai/EntityMention.tsx` (one chip, kind-colored
  icon, routes M→library N→note C→concepts tab T→node workspace Q/E→runner) +
  `AiBadge.tsx`; BlockRenderer renders mentions **inline in markdown**
  (`mention:` protocol preserved through `urlTransform` + custom link
  component) and supports the standalone `mention` block type; ChatPanel
  bubbles render message mentions; `ai.mentions.*` i18n keys. 288 backend
  tests (new `test_mentions.py` ×11: registry parse/ranges/stability,
  advisory blocking-vs-advisory, chat e2e resolve/teach/stability/unknown/
  registry persistence, quizgen+exgen block attachment) + 215 frontend tests
  (EntityMention ×6, BlockRenderer ×2, ChatPanel chips ×1).

- 2026-08-20 — **Fixed: provider failures crashed AI routes with a 500** (user
  report: *Study here* → 500 after a provider 401). The gateway now wraps
  every provider HTTP/transport failure in a typed `ProviderError`
  (`app/ai/gateway.py`) whose message carries the model label, HTTP status +
  truncated body, and a "check the API key in Settings → Providers" hint on
  401/403; all in-request AI routes (quiz/exercise/flashcard generate, note
  actions + drawing OCR, quiz recognize, outline draft, concepts extract,
  node review/cheatsheet/draft-note) map it to **502 with that detail** — the
  UI's existing ErrorBanners surface it directly. Chat/tutor jobs record the
  same friendly message on failure. Tests: gateway wrapping (401 + transport)
  ×2, quiz-generate 502 end-to-end ×1. 277 backend tests (frontend unchanged).

- 2026-08-20 — **Fixed chat crash on subscribe + tool catalog in the chat header.**
  Bug: clicking *Ask about this node* (or any chat session subscription) crashed
  with `event is undefined` — the WS bridge's subscribe ack
  (`{"type":"subscribed","topic":…}`) carries a routable topic but **no payload**,
  so ChatPanel's handler read `.type` of undefined. Fix: `WsClient.attach` now
  drops control frames (`subscribed`/`unsubscribed`/`pong`/`error`) before topic
  routing (protects the `jobs:` handlers too — same latent crash), plus a
  defensive payload guard in ChatPanel; ws regression test added. Feature: the
  chat header gained a wrench **Tools** button opening a catalog dialog — one
  card per tool with description, example, arguments (name/type/required),
  response and scope, in two groups: chat math tools (CALC, SYMPY — new
  `CHAT_TOOL_CATALOG` in `app/ai/tools.py`, next to the implementations) and
  **MCP resource tools** (all seven, introspected live from the MCP server via
  `list_tools()` — no duplicated metadata) served by new `GET /ai/tools`.
  Frontend `features/chat/ToolsDialog.tsx` + api `listAiTools`; i18n
  `chat.tools.*`. 274 backend + 206 frontend tests.

- 2026-08-20 — **Phase 10 (10A–10D): AI task layer & context engine (ADR-042,
  plan `dev/plans/14-ai-task-layer.md`).** **10A** — new
  `services/context.py`: `ContextSpec` (course, node, scope `node|subtree|
  course`, include/exclude material ids, note ids, concept ids, one-off hint,
  retrieval query/budgets — all cross-course ids 422) resolves to a
  `ContextBundle` (material set, hybrid chunks, notes, concepts, ancestor AI
  hints, breadcrumb/objectives header) with one budgeted `render_prompt()`
  (scope/instructions/materials `[M#]`/concepts `[C#]`/notes `[N#]`/numbered
  excerpts); `services/search.py` gained **chunk-level hybrid retrieval**
  (`retrieve_chunks_hybrid` — FTS ranking RRF-fused with sqlite-vec chunk
  vectors, FTS-only fallback; fixes `retrieve_chunks` silently ignoring
  embeddings). **10B** — new `ai/runner.py` `TaskRunner.run_json` (skill
  resolve → JSON repair loop with caller validator → uniform audit row with
  model label + measured latency) + `ai/parsing.py` shared helpers; quizgen/
  exgen/flashcards migrated behavior-identical (suites unchanged), their
  duplicated `_JSON_RE`/loop/skill/audit/token/blocks-md code and
  pipeline-local system-prompt constants deleted (skill seeds are the single
  source). **10C** — migration **0021** `tree_nodes.ai_hint` (PATCH
  `/nodes/{id}`; root editable for the hint only; tree/workspace payloads +
  undo snapshot carry it); quiz/exercise/flashcards `GenerateIn` gained the
  context params; new `api/ai.py` `POST /ai/context/preview` (stats + rendered
  prompt, no LLM). **10D** — frontend `features/ai/GenerateDialog.tsx`: one
  schema-driven dialog (quiz/exercise/flashcards presets: topic, difficulty
  incl. mixed, count/steps, flashcard source incl. **from material**) + scope
  picker (this node / node+children / whole course) + material checkboxes
  (uncheck = exclude; "Add material…" = opt-in) + notes checkboxes + concept
  chips + one-time instruction field + **debounced context preview**
  (counts + expandable exact prompt); Practice tab (quiz + exercise) and the
  Cards tab generate flows all open it (old exercises
  GenerateDialog + flashcards GenerateCard retired; one-click Study
  here/palette/Home/NoteEditor actions keep defaults); `features/ai/
  AiHintCard.tsx` edits the node's AI instructions from the workspace
  overview. En route: jsdom `scrollIntoView` stub in test setup (pre-existing
  NodeTreeSidebar flake), two migration-head assertions bumped to 0021.
  273 backend + 204 frontend tests.

- 2026-08-20 — **Sidebar-navigation & tree-telemetry round (plan
  `dev/plans/13-sidebar-navigation.md`): the structure sidebar becomes a complete
  navigation surface.** **A — polish**: open/closed + per-course expansion persist
  to localStorage (stored expansion wins over auto-expand — first visit still
  auto-expands to the current node); fuzzy **Find a node…** filter (`lib/fuzzy`,
  flat scored match list with match count, chevrons hidden, ×/Esc clears);
  **keyboard navigation** (tree is focusable w/ `aria-activedescendant`, ↑/↓ move
  focus + scrollIntoView, →/← expand/step-in/collapse/step-out, Enter opens;
  focus ring distinct from current-node highlight); **drop-between reordering**
  (drag edges: top/bottom 30% of a row = before/after with a 2px primary line
  indicator, middle = into with the ring; before/after on root refused; drop
  recomputes the edge from coordinates so it can't depend on stale dragOver
  state). **B — drag materials onto nodes**: workspace Materials rows set
  `application/x-ca-material`; sidebar rows accept the MIME (ring) and drop →
  `allocateMaterial` (one-off reassignment as a gesture; picker stays the bulk
  tool). **C — study telemetry on the tree**: `GET /courses/{id}/tree` counts
  gain `studied` (node materials with study-state `studied` for the profile) and
  `cards_due` (node flashcards with no FSRS row or `due_at <= now` — new counts
  as due, mirroring analytics); sidebar rows show an SVG **progress ring**
  (studied/materials, success→primary at 100%) + a warning-tinted **due badge**
  with tooltips; flashcards left the plain count badges (the due badge covers
  them). **D — node deep-links**: `ScopeChip` (notes/practice/cards rows) and
  MaterialDetailPage assigned-to chips render as router Links into the node
  workspace (course-level chips stay static). **E — undo node delete**:
  `DELETE /nodes/{id}` returns an `undo_token`; `TreeService.delete_node`
  snapshots (attrs, sibling index, child order, material links, node concepts,
  placement PKs per table) into an in-process registry (TTL 5 min, cap 20);
  `POST /nodes/restore` recreates the node at its original sibling position,
  re-moves children back, repoints captured placements that still sit at the
  parent, then re-inserts deduped-away links/concepts; the sidebar shows an
  8-second **Undo** toast. 265 backend + 199 frontend tests.

- 2026-08-20 — **Embedded outline tree retired; the sidebar is the tree UI** (user
  decision — the root overview's recursive OutlineEditor duplicated the new
  structure sidebar). Root overview now shows a compact **Structure** card
  (`OutlineActions.tsx`: AI outline draft → review/prune → commit, inline add-node
  form; OutlineEditor.tsx + its per-row materials query/DnD/card chrome deleted,
  inner AddChildForm removed). Tree editing moved into `NodeTreeSidebar`: right-click
  context menu per row (Add child / Rename / Delete — root gets Add child only,
  delete keeps the merge-into-parent confirm), inline add/rename forms (Enter/✓
  apply, Escape/blur cancels, mousedown-guard against the blur/submit race),
  drag-to-reparent (same `application/x-ca-node` DnD, descendant-drop refused,
  drop-target ring). i18n: `courses.structureTitle/structureHint/addNode` +
  `common.apply/remove` added; dead keys removed (`addChapter`, `outlineTree`,
  `emptyTree`, `openWorkspace`, `allocateMaterial`, `workspace.childTitle/addChild`).
  Tests: OutlineEditor.test → OutlineActions.test (4), NodeTreeSidebar +5
  (context-menu add/rename, root menu shape, delete confirm, drag reparent);
  193 frontend tests. Backend untouched (263 green).

- 2026-08-20 — **Workspace structure sidebar + per-node tree counts; chapter/
  section wording retired.** Backend: `TreeService.tree()` now computes direct
  per-node counts (materials/notes/quizzes/exercises/flashcards via grouped
  `func.count()` queries) and includes them as `counts` on every node entry of
  `GET /courses/{id}/tree`. Frontend: new `features/courses/NodeTreeSidebar.tsx`
  mounted in the NodeWorkspace as a sticky left panel (hidden below md; header
  toggle with PanelLeft icons) — whole-course tree with clickable rows (root →
  course route, nodes → node route, active tab preserved), per-node chevrons,
  auto-expansion of the current node's ancestor chain, focused styling for the
  current node (`bg-primary/10`, font-medium, `aria-current="page"`,
  `aria-selected`), non-zero count badges with localized tooltips, node total in
  the header, expand-all/collapse-all (collapse keeps the root level), and
  `@tanstack/react-virtual` virtualization above 40 visible rows. Terminology:
  the outline editor's top-level add form says *Add node* / *Node title*
  placeholders everywhere (no chapter/section labels left in the courses UI;
  `courses.chapterTitle`/`sectionTitle` keys removed, `addChapter` value fixed,
  `emptyTree` reworded). New backend test (tree counts) + 6 sidebar tests;
  NodeWorkspace breadcrumb test scoped to the breadcrumb nav. 263 backend +
  189 frontend tests.

- 2026-08-20 — **Material catalog picker for node assignment** (frontend only,
  backend frozen). The inline "+ material" lists in the workspace Materials tab
  and the outline editor's node cards are replaced by a shared
  `features/courses/MaterialPickerDialog.tsx`: Library-style dialog with the
  course folder tree in a collapsible sidebar (per-folder material counts,
  link-emblem nodes, "All materials" entry incl. loose files), breadcrumb
  navigation + Up button, live fuzzy filtering (`lib/fuzzy.ts`),
  multi-select with per-row checkboxes, *select whole folder subtree* /
  *select shown* bulk toggles (already-assigned materials render locked with an
  "Assigned here" chip), selected-items chips with per-chip deselect in the
  footer, and linked sources browsable via `/sources/{id}/browse` whose
  un-ingested files offer **Ingest & select** (ingest → auto-select). One
  Assign click batches `POST /nodes/{id}/materials` for the whole selection and
  invalidates workspace/tree/materials queries. OutlineEditor drops its
  per-row materials query (the dialog owns its data); the dialog renders as a
  sibling of the draggable node row so it can't trigger DnD. Dead i18n keys
  removed (`courses.noUnallocated`, `workspace.noUnassignedMaterials`); new
  `materialPicker.*` section. 183 frontend tests (new dialog tests ×6:
  root browse+batch assign, assigned-lock, folder subtree toggle + chip
  deselect, select-shown toggle, all-materials fuzzy filter, linked source
  ingest-&-select).

- 2026-08-20 — **Fixed: note body appeared to vanish after Save** (user report;
  live-browser repro). Root cause was a feedback loop in the Tiptap editor sync:
  Save succeeded → `setDraft(null)` made the editor's `value` fall back to the
  **stale cached body** (empty for a fresh note) → the external-sync effect ran
  `setContent(stale)` → ProseMirror's programmatic setContent fired `onUpdate` →
  `onChange(stale)` resurrected the draft as `""`, shadowing the refetched
  content until reload. Two-part fix: (1) `NoteEditor.save` writes the mutation
  result into the cache (`setQueryData`) *before* clearing the draft, so the
  fallback is always the just-saved body; (2) `MarkdownEditor`'s external sync
  uses `setContent(value, { emitUpdate: false })` — programmatic syncs can never
  emit `onChange` again. Regression test locks the no-emit invariant; verified
  end-to-end with a headless-Chromium script (create → type → save → content
  persists without reload). 177 frontend tests.

- 2026-08-20 — **Housekeeping: note title editing, import side-effect fix,
  flaky test fix.** The note editor header is now an inline title input
  (PATCH on submit/blur — the API always supported it). `app/main.py` no
  longer builds the app at import time (`app = create_app()` removed) —
  importing `app.main` (tests, tooling, the MCP path) can no longer trigger
  migrations/dir creation against the real data dir; `scripts/dev.sh` uses
  `uvicorn app.main:create_app --factory`. Fixed a latent full-suite flake:
  `test_extraction_edit.py` cached per-client course ids in a dict keyed by
  `id(client)` — CPython address reuse let a fresh client inherit a dead
  course (upload 422); now a `WeakKeyDictionary`. 262 backend + 178
  frontend tests.

- 2026-08-20 — **Practice restructure (ADR-040/041 follow-up): quizzes + exercises
  live where you explore; outline virtualization** (backend frozen, 262 tests).
  Flat global Quiz/Exercises pages removed: rail items dropped (Study = Home +
  Flashcards), `/quiz` + `/exercises` beforeLoad-redirect to `/courses`
  (`/quiz/$activityId` runner + `/exercises/$exerciseId` player kept as full-page
  focus modes). Components extracted to `features/quiz/QuizRunner.tsx`,
  `features/quiz/ImportDialog.tsx`, `features/exercises/{Player,GenerateDialog,
  DrillsCard}.tsx`; back-links now go to Courses (`quiz/exercises.backToCourses`).
  Workspace **Practice tab upgraded**: quizzes + exercises over the node roll-up
  with scope chips, question counts, difficulty chips, quiz export/.qpkg/print
  rows, per-exercise similar, generate quiz (scope+count), exercise GenerateDialog,
  course-prebound quiz ImportDialog (Import button), DrillsCard taking the
  workspace course via a new `courseId` prop. Command palette: nav-quiz/exercises
  actions replaced by fuzzy `quiz:`/`exercise:` search sections (top 5 each →
  runner/player). Scores tips drill/challenge links retargeted to Courses.
  **OutlineEditor**: collapsible tree (chevron per node with children, role=tree/
  treeitem) + virtualization — flattened visible rows render plainly at ≤40 rows,
  beyond that `@tanstack/react-virtual` (new dep, dynamic measureElement,
  overscan 8, max-h 70vh) keeps the DOM small; DnD handlers unchanged per row.
  Test-env: ResizeObserver stub added to setup (reports 800×600) for jsdom.
  Dead i18n keys removed (`nav.quiz`, `nav.exercises`, `quiz.backToQuizzes`,
  `exercises.backToList`); added `backToCourses` ×2, `palette.quizResult/
  exerciseResult`, `courses.toggleNode/outlineTree`. 178 frontend tests (new:
  redirects ×2, OutlineEditor ×4 incl. >100-node virtualization; moved/rewritten:
  QuizRunner ×5, GenerateDialog ×3, DrillsCard ×2, palette search, AppShell
  no-quiz/exercises, NodeWorkspace practice ×8).

- 2026-08-20 — **Notes restructure (ADR-041, ADR-040 follow-up): notes live
  where you explore** — flat global Notes page removed (backend untouched, 262
  tests frozen). `NoteEditor` extracted to `features/notes/NoteEditor.tsx` (+ optional
  `onClose` ×-button; course▸node breadcrumb querying the shared `['tree', cid]`
  key, last crumb plain, root/missing → course crumb only). New
  `features/notes/NoteEditorDrawer.tsx`: fixed right overlay (ChatPanel border/
  shadow language, backdrop/Escape/× close, panel autofocus) driven by a `note`
  search param on both workspace routes (`tabSearch` now validates
  `{ tab?, note? }`; open via `openNote(id)` = `search: prev => ({...prev,
  note})`, close via `closeNote` = param stripped; back button works). Workspace
  NotesTab upgraded with the flat page's ported features: SearchInput (submit
  pattern), course tag-filter chips (`listNoteTags`), `useInfiniteQuery`
  load-more (limit 50, node_id roll-up kept), tag inheritance on create; create/
  draft/rows set the `note` param instead of navigating to `/notes/$id` (the
  reported bug). New standalone `/note/$noteId` route (full-page editor);
  `/notes/$noteId` → `/note/$noteId` and `/notes` → `/courses` beforeLoad
  redirects (chapter-redirect pattern). AppShell: Notes nav item removed
  (Workspace = Courses + Library). CommandPalette: nav-notes action replaced by
  a note-search section (`['notes','palette']`, limit 100, fuzzy titles, top 8
  `note: {title}` → `/note/$id`); quick-note navigates `/note/$id`. Dead i18n
  keys removed (`nav.notes`, `notes.title/newNote/empty/delete`); added
  `notes.close`, `notes.drawerLabel`, `palette.noteResult`. 170 frontend tests
  (new: NoteEditor ×5, NoteEditorDrawer/redirects ×7; rewritten: NodeWorkspace
  notes-tab ×3 with real-router drawer assertions, palette note-search, AppShell
  no-Notes).

- 2026-08-20 — **ADR-040 backend: study content requires a course (migration
  0020)**. `course_id` NOT NULL on notes/activities/exercises/flashcards;
  orphaned rows (profile-scoped) migrate into the per-profile "Unsorted"
  course, placed at its root node (root auto-created if missing — 0014 pattern
  generalized). Every create endpoint now validates: note create, quiz
  generate, caq/qpkg/inbox imports (course as required query param), exercise
  create/generate/drills, flashcard create/generate/Anki import — missing
  course → 422. Chat sessions stay course-optional by design. ~60 tests
  updated to create content inside courses; new `test_course_required.py`
  (missing-course 422s across all endpoints + the 0020 orphan migration from
  a 0019 fixture). 262 backend tests.

- 2026-08-20 — **ADR-040 frontend: course-required study content + rail redesign**
  (backend frozen, 262 tests). Every creation call now carries a course:
  `lib/api.ts` makes `course_id` required on note create, quiz/exercise/flashcard
  generate+create, drills, and the caq/qpkg/inbox/Anki imports (course as query
  param). New `useRequiredCourse()` hook + `CourseSelectField` picker
  (`components/workspace/CoursePicker.tsx`): workspace course wins → single
  existing course is the fallback → dialogs (exercise generate, flashcards
  generate/Anki, quiz import incl. inbox tab, notes new-note) show a required
  course select → one-click actions (quiz generate, Today drill/challenge,
  drills card, palette quick note) show the *open a course first* ErrorBanner
  hint instead of firing. Note editor *Make flashcards* uses the note's course.
  **Rail rewritten** (`AppShell.tsx`): course header (color dot + title +
  keyboard-accessible dropdown w/ All-courses + per-course dots, outside-click/
  Escape close; compact Create-course CTA at zero courses), *My courses*
  quick-jump (select workspace + navigate to `/courses/$id`, capped ~8 + scroll,
  workspace-course highlight independent of route), Workspace/Notes context
  strip under the header when a course is active, grouped primary nav
  (Study/Workspace/Insights + subtle Dev), Settings moved to the footer,
  focus-visible rings throughout; `switchCourse` semantics + query invalidation
  unchanged. 160 frontend tests (new: AppShell rail ×5, course-required gating
  on quiz/exercises/flashcards/notes/palette/Today; api import-URL params).

- 2026-08-19 — **Phase 9E: local read-only MCP resource server (+ flashcard scope
  chips)**. New `app/mcp_resources.py` on the official MCP SDK (2.0, added as a
  dependency): `python -m courseassistant mcp` runs a **stdio** server (launch
  modes now app|web|mcp; mode resolution lives in `__main__` — the mcp path never
  imports `app.main`, whose module-level `create_app()` runs alembic and would
  corrupt the stdio protocol; alembic/uvicorn logs are forced to stderr). Seven
  read-only tools over the same services as the API — `list_courses` (with root
  node ids), `get_node_overview` (breadcrumb/children/counts),
  `get_node_materials`, `get_node_concepts`, `get_node_exercises`,
  `get_node_quizzes`, `get_node_notes` — each taking `node_id` +
  `include_children` + optional `profile_id` (default = first profile; nodes of
  courses the profile doesn't own are invisible). No write tools by construction;
  results are dict-wrapped for unambiguous JSON content blocks. E2E tests drive
  the real subprocess via `stdio_client` (tool listing, scoped roll-up,
  include_children=false, cross-check quizzes/notes/concepts/error shape, and a
  read-only guarantee: tool names + DB row count unchanged). En route:
  `CardOut` gained `node_id` and the workspace cards tab shows scope chips
  (closes the 9B follow-up). 260 backend + 144 frontend tests.

- 2026-08-19 — **Phase 9C/9D backend: scoped retrieval + coverage APIs**.
  `retrieve_chunks` gained a `material_ids` filter (expanding bind param; empty
  list short-circuits); chat sessions bound to a non-root node narrow RAG
  retrieval to the subtree's linked materials (root-bound and unbound sessions
  keep course-wide retrieval — legacy behavior preserved; empty subtree falls
  back to course scope); quiz generate + exgen scope chunks the same way when a
  non-root `node_id` is passed. `GET /chat/sessions` gained `?node_id=` (exact
  match). Node workspace payload gained `concepts` (subtree coverage with
  `direct` flag + covering `node_ids`). New coverage management APIs:
  `POST /nodes/{id}/concepts {concept_id}` / `DELETE /nodes/{id}/concepts/
  {concept_id}` (intra-course validated, idempotent add). 3 new tests in
  `test_phase9cd_scoping.py` (coverage CRUD incl. cross-course 422, session
  node filter, scoped-chat prompt contains only subtree material).

- 2026-08-19 — **Phase 9B/9C/9D frontend: unified NodeWorkspace** (backend frozen,
  258 tests green). New `features/courses/NodeWorkspace.tsx` is the single scaffold
  for the course root and any node: `/courses/$courseId` (root, via a thin
  CourseDetailPage wrapper) and new `/courses/$courseId/n/$nodeId` both render it;
  old `/courses/$courseId/chapters/$chapterId` issues a replace-redirect to the node
  route (one release). Routable `?tab=` (Settings pattern): overview (objectives
  chips, AI review/cheat-sheet, children-as-cards with open/practice/ask quick
  actions; the 9A outline tree editor — extracted into `OutlineEditor.tsx` — embeds
  at the root; inner nodes get an add-child form) · materials (direct list with
  read-status pills + assign picker + collapsible per-child groups) · notes
  (rolled-up `listNotes({node_id})` with per-note node chips, "New note here",
  AI "Draft note") · concepts (course graph panel + per-node coverage rows with
  cover/uncover toggles and an add-coverage picker → `POST/DELETE
  /nodes/{id}/concepts`) · practice (rolled-up quizzes/exercises with node chips;
  generate quiz/exercise defaults to the current node with a this-node/whole-course
  scope picker — `GenerateDialog` exported from ExercisesPage gained the picker,
  `GenerateCard` from FlashcardsPage gained `node_id`) · cards (node-scoped flashcard
  list + generate form) · tutor (`listChatSessions(node_id)` exact-match list +
  "Ask about this node" CTA; header CTA creates a chat bound to the node and opens
  the sidebar). Header: breadcrumb (crumbs link up the tree), course accent dot,
  **Study here** (generateQuiz `{course_id, node_id, count: 8}` → runner, span-aware
  root vs node). Scope chips everywhere a `node_id` is present (flashcard rows have
  none server-side). Command palette gained node actions for the workspace course
  ("Quiz me on {node}" → scoped quiz + runner, "Open {node}" → workspace;
  depth-indented, depth ≤ 2 to avoid noise). api.ts: `listChatSessions` gained
  `node_id`, `createChatSession` gained `title`, new `addNodeConcept`/
  `removeNodeConcept`, `NodeWorkspace.concepts` typed. ChapterWorkspacePage retired
  (absorbed); its organizer features live on in the overview tab. 144 frontend tests
  (NodeWorkspace.test: root/node render, tabs, study-here scoping, child quick
  practice, coverage add/remove, tutor sessions, notes roll-up + creation, practice
  chips, missing node, legacy redirect; palette node-action test).

- 2026-08-19 — **Phase 9A backend: unified node tree shipped (ADR-039)**.
  Migration 0019: `tree_nodes` created (per course, undeletable root = course
  level, `depth ≤ 4` CHECK, materialized `path`/`sort_path`, unique partial index
  on root, composite self-FK `(parent_id, course_id) → (id, course_id)`); chapters
  + sections backfilled into the tree (sub-chapters preserved, sections as
  children); `material_links` rebuilt with `node_id` + denormalized `course_id`
  under a composite FK (intra-course placement now **DB-enforced**); activities/
  exercises/flashcards drop `section_id` for `node_id` (course-bound rows placed
  at root); notes gain `node_id` (owner_type 'section' migrated to placement;
  owner_type stays only for material/exercise_session/chat_message attachment);
  `section_concepts` → `node_concepts`; chat_sessions gain `node_id`. Old tables
  dropped — no dual source of truth; legacy-data migration test (0013→head)
  verifies tree shape + every remap. New `services/tree.py` is the single tree
  authority (create/rename/move with depth cap + cycle guard, merge-delete that
  reparents children and re-points placements with duplicate-link cleanup,
  subtree/roll-up queries via path prefix, breadcrumb, nested tree + workspace
  payloads with per-resource direct/with-children counts). APIs: node CRUD under
  `/courses/{id}/nodes` + `/nodes/{id}[/move|/workspace|/materials|/review|
  cheatsheet|/draft-note]`; `/chapters/*` + `/sections/*` endpoints removed;
  quiz/exercise/flashcard create+generate take `node_id` (course-bound creates
  place at root via `TreeService.placement_node`); quiz/exercise/flashcard/notes
  lists gained `?node_id=&include_children=` roll-up params; concepts extract/
  commit/graph use the `nodes` key; organizer operates on any node. Outline commit
  writes depth-1/2 nodes (AI still drafts 2 levels — ADR-035 as policy).
  `purge_course` deletes nodes depth-descending + node_concepts + concepts.
  En-route fix: migration ran against the real dev DB mid-development (module-level
  `create_app()` in `app/main.py` runs migrations at import); the partially-migrated
  DB was repaired and re-migrated cleanly. 255 backend tests (new
  `test_phase9a_scoping.py`: roll-up at depth, cross-course refusal, depth cap,
  merge-delete, chat binding, root immutability).

- 2026-08-19 — **Phase 9A frontend: migrated the SPA off chapters/sections onto the
  unified node APIs** (backend frozen, 255 tests). `lib/api.ts`: `SectionInfo`/
  `ChapterInfo` → recursive `NodeInfo` (`courseTree` returns the one-root nested
  list), `ChapterWorkspace` → `NodeWorkspace` (`nodeWorkspace` reads
  `GET /nodes/{id}/workspace` with children/child_materials/notes/counts/breadcrumb),
  node CRUD (`addNode`/`getNode`/`renameNode`/`moveNode`/`deleteNode`) against
  `/courses/{id}/nodes` + `/nodes/{id}[/move]`, material allocate/deallocate per
  node, organizer endpoints (`reviewNode`/`nodeCheatsheet`/`draftNodeNote`), concepts
  payload key `sections` → `nodes` (graph chips carry `node_id`/`node_title`),
  `/materials/{id}/links` chips render owner + breadcrumb + `is_course_level`,
  `QuizActivity`/`ExerciseInfo`/`ChatSession`/`NoteInfo` gained `node_id`
  (generate/list/create params typed; UI still binds at course level — node-scoped
  generation is 9B), notes create takes `node_id`. CourseDetailPage outline tab now
  renders the recursive tree (depth indent, per-node add-child/rename/delete/
  allocate, drag-to-reparent via `/nodes/{id}/move` with merge-on-delete confirm
  wording); ChapterWorkspacePage became `NodeWorkspacePage` (route path unchanged)
  rendering breadcrumb, node materials, child cards with draft-note buttons,
  child-node nav and counts. i18n keys updated (node wording; depth-1 "Chapter"/
  depth-2 "Section" labels kept). 137 frontend tests.
- 2026-08-19 — **Phase 9 redesigned around ADR-039: unified node tree (doc 12
  rewritten; no code yet).** User decision: retire chapters/sections for one
  `tree_nodes` table per course (≤4 node levels; root node = course level;
  materialized path/sort_path for indexed subtree roll-up and depth-first order).
  Placement for all study resources collapses to a single `node_id` with a
  composite FK making intra-course placement database-enforced — the polymorphic
  scope_type/scope_id of ADR-038 (never implemented) is replaced before shipping,
  and ADR-035's fixed 2-level depth becomes an outline-AI policy, not schema.
  material_links owner_type/owner_id, section_concepts, and section_id columns all
  migrate to node_id in migration 0019 (old tables dropped — no dual source of
  truth); UI becomes one NodeWorkspace route/scaffold for course + any node.
- 2026-08-19 — **Phase 9 planned & approved (ADR-038, plan doc 12; no code yet)**.
  Uniform scoping: placement (`scope_type/scope_id`, polymorphic, intra-course)
  becomes orthogonal to ownership (`course_id`) for quizzes, exercises, flashcards,
  notes (owner_type += course|chapter — also fixes the chapter-notes creation hole),
  concept coverage (section_concepts → concept_coverage at all levels), and chat
  sessions. Roll-up over the 2-level tree replaces per-level copies (full-symmetry
  FK-per-level design rejected — 21 relationships, fragments analytics/dedup).
  UI: one NodeWorkspace scaffold for course+chapter (routable tabs Materials/Notes/
  Concepts/Practice/Cards/Tutor, depth-aware "Study here" CTA, scope chips, scoped
  generation). Scoped services double as a read-only AI/MCP resource layer (MCP
  server itself = stretch slice 9E). Roadmap 05 gained Phase 9; ADR-038 recorded.

- 2026-08-19 — **Analytics concept dual-write + quiz-by-concept scoping**.
  `answer_rows` now carries `concept_id` (question's first concept tag matched
  against the answering course's `concepts` table, lowercase); the weakness
  matrix passes it through and `materialize` writes it into
  `concept_skill_stats.concept_id` (NULL when unmatched — string axis stays
  authoritative until backfilled). `POST /quiz/generate` accepts `concept_id`
  (must belong to the given course): resolves the concept name as the quiz
  topic, reusing the FOCUS TOPIC retrieval/directive machinery. 250 backend
  tests.
- 2026-08-19 — **Command palette (I5) + Tiptap notes editor (8C remainder)**.
  Palette: Ctrl/Cmd+K or the rail button opens a fuzzy-searched action list
  (reuses `lib/fuzzy.ts`) — quick actions (New note in the workspace course,
  Open tutor chat), navigation to every section, and per-course "Go to" actions
  that switch the workspace; full keyboard support (↑/↓/Enter/Esc). Editor: the
  note body is now a **Tiptap rich editor** (`@tiptap/react` + starter-kit +
  `tiptap-markdown`) with a formatting toolbar (bold/italic/strike/code,
  headings, lists, quote); storage stays canonical markdown via round-trip
  serialization, external updates (e.g. appended AI action results) reload
  content; LaTeX `$…$` remains literal text rendered in previews. 137 frontend
  tests. Note: main bundle grew to ~1.9 MB (tiptap) — acceptable locally,
  code-split later if needed.
- 2026-08-19 — Phase 8E: **AI chapter organizer** (final Phase 8 slice). New
  `services/organizer.py` on the `description` task: **Review** (`POST
  /chapters/{id}/review`) — sections + assigned material + unassigned course
  material + section concepts in, findings out (gap / ordering / orphan /
  coverage; deterministic validation clamps kinds, counts, lengths) shown as a
  findings card on the chapter workspace; **Cheat sheet** (`POST
  /chapters/{id}/cheatsheet`, refused without assigned material) — one-page
  formula/definition sheet rendered with the block renderer; **Draft notes**
  (`POST /sections/{id}/draft-note`, refused without material) — AI-drafted
  study note persisted as a real note (owner_type=section, tagged `ai-draft`,
  title suffix "AI draft") and opened in the editor. All calls audited through
  the gateway; errors surface via ErrorBanner. 248 backend + 128 frontend
  tests. **Phase 8 complete.**
- 2026-08-19 — Phase 8D: **concepts & knowledge graph (A9)**. Migration 0018
  adds `concepts` (unique per course+name), `concept_links` (prereq-of / part-of /
  related-to; unique per triple), `section_concepts` (unique per pair), and
  `concept_skill_stats.concept_id` (nullable — future analytics FK migration).
  New `concepts` AI task + `services/concepts.py`: `POST
  /courses/{id}/concepts/extract` builds the prompt from material index cards +
  outline allocations and **validates deterministically** (names lowercased ≤ 60
  chars, deduped, ≤ 60 concepts; link endpoints must be listed concepts, no
  self-links, relation whitelist; section lists filtered to real outline titles);
  `POST /concepts/commit` is append-only idempotent (existing concepts kept,
  duplicate links/section rows skipped); `GET /courses/{id}/concepts` returns the
  graph with per-concept section coverage. Course page gained a **Concepts tab**:
  graph list (aliases, section chips, outgoing/incoming relations), draft-review
  card with per-concept removal before commit. 245 backend + 126 frontend tests.
- 2026-08-19 — Phase 8C first cut: **notes tags + pagination**. Migration 0017
  adds `notes.tags` (JSON; normalized on write — trimmed, lowercased, deduped,
  max 20×60 chars). API: create/PATCH accept `tags`; `GET /notes` gained a `tag`
  filter (exact match against the JSON array) and **cursor pagination**
  (`limit` ≤ 100, `cursor` = updated_at ISO; response is now `{items,
  next_cursor}` — breaking shape change, all consumers updated); new
  `GET /notes/tags/list` per-course tag summary with counts. Frontend: Notes
  page shows tag chips per row + filter-chip bar (All / each tag), load-more on
  the cursor, search submits on Enter (SearchInput gained onSubmit); the note
  editor has an inline tags row (chips with remove ×, add-tag input); new-note
  creation inherits the active tag filter. 244 backend + 124 frontend tests.
  Tiptap upgrade remains open (markdown editor serves).
- 2026-08-19 — Phase 8B **L3: per-source scan options + error reporting
  (ADR-037)**. Migration 0016 adds `material_sources.scan_interval_sec`
  (nullable; min 15 s validated; NULL → global `CA_SOURCE_SCAN_INTERVAL_SEC`) and
  `last_scan_error` (set when a scan fails — including the manual endpoint, via
  a post-rollback error write; cleared on success). The ScanScheduler now skips
  sources whose per-source interval hasn't elapsed (due-time logic; `force`
  overrides) and `POST /sources/scan-all` force-scans everything. Browse
  responses and SourceOut carry `enabled`, `scan_interval_sec`,
  `last_scan_error`, `last_scanned_at`; the library shows a warning banner for a
  link's last scan problem. 241 backend + 122 frontend tests.
- 2026-08-19 — Phase 8B **L2: reconciliation automation (ADR-037/ADR-017)**. New
  `ScanScheduler` (background thread, startup scan after 5 s + periodic cycle,
  default every 5 min — `CA_SOURCE_SCAN_INTERVAL_SEC`, min 15 s): scans every
  enabled source, queues ingest jobs for new/pending materials, publishes WS
  `source:{id}` events on completion; a broken source (missing target, I/O
  error) is skipped without killing the cycle. **Moved/renamed files remap by
  content hash**: a vanished material whose exact content reappears elsewhere in
  the same source keeps its identity (extraction history, read-state, section
  links) — external_path/filename refreshed, status restored from `missing`;
  scan stats gained a `moved` counter. 239 backend tests.
- 2026-08-19 — Phase 8B slice 3: **chapter workspace + course tabs**. New route
  `/courses/$courseId/chapters/$chapterId` backed by `GET
  /chapters/{id}/workspace` (chapter info + course title, chapter-level assigned
  materials with per-profile read-status + progress, sections with objectives and
  per-section materials incl. rationale/auto-assign flags, sub-chapters, and
  section/material-owned notes — standalone notes excluded). The course page
  gained routable tabs (`?tab=outline|materials|notes`, mirrors Settings/Scores
  pattern): Outline keeps the drag-reorder editor, Materials shows the course's
  material grid (links into the library), Notes lists course notes; outline
  chapters gained an open-workspace button. The workspace links materials →
  library detail, notes → note editor, sub-chapters → their workspaces, and a
  "Quiz me" shortcut. 237 backend + 122 frontend tests.
- 2026-08-19 — **Fixed: Original tab downloaded instead of displaying** (user
  report). Root cause: blobs ingested from linked sources were stored with
  `mime=None` → `GET /blobs/{sha}` served `application/octet-stream`, which
  browsers force-download. Fixes: `_store_blob` now guesses the mime from the
  file name; the blob endpoint additionally back-fills at serve time for legacy
  rows (guesses from the referencing material's filename and adds
  `inline; filename="…"`); the Original tab gained a **text/markdown viewer**
  (rendered in a monospace pane) instead of a bare link — PDFs and images
  already displayed. 236 backend + 119 frontend tests.
- 2026-08-19 — **Toolbar "+" dropdown**: the Library's create button is now a "+"
  dropdown opening the same action menu as the pane right-click (New folder / New
  text·Markdown file / Upload files… / Add linked folder…), anchored under the
  button — discoverable without knowing about right-click. 118 frontend tests.
- 2026-08-19 — **Folder picker uses the Library's breadcrumb navigation**: the
  link-target picker now renders the same `Breadcrumbs` component as the Library
  (`/ ▸ home ▸ … ▸ current`, click any segment to jump) with an Up button and the
  manual path box moved to the footer; the Places sidebar and raw-path header row
  are gone. 117 frontend tests.
- 2026-08-19 — Phase 8B L1 (ADR-037): **linked sources as symlink-style folder
  nodes + file-manager context menus + folder picker**. Migration 0015 adds
  `material_folders.source_id` (unique; existing sources backfilled with link
  nodes, labels sanitized, collisions suffixed). Sources now appear in the course
  folder tree with a link emblem: **live browsing** via `GET
  /sources/{id}/browse?subdir=` (realpath containment, symlinks not followed,
  depth cap, virtual subdirectories never persisted; materials matched by
  relpath; un-ingested matching files listed with a pending flag), **explicit
  ingest** per file or "Ingest all" (`POST /sources/{id}/ingest`; per-course
  dedupe), **dangling state** (`missing_target` + Re-link via `PATCH
  /sources/{id}`), **Rescan** and **Reveal on disk** (`POST /sources/{id}/reveal`,
  xdg-open/explorer/open). **Unlink keeps materials** (moved to course root;
  source_id/external_path cleared; deleting the link node = unlink; nothing is
  ever written to a target and uploads into links are refused). Library pane
  **context menus**: empty pane (New folder / New text file / New Markdown file /
  Upload files… / Add linked folder… / New course at root; Refresh inside links),
  materials (Open / Rename inline / Delete with purge incl. FTS+vec cleanup),
  link nodes (Open / Rescan / Reveal / Rename / Unlink). New material APIs:
  `POST /materials/text` (inline txt/md creation → native ingest), `PATCH
  /materials/{id}` (rename), `DELETE /materials/{id}` (purge). **Folder picker
  dialog** for link targets: manual path entry + server-side browsing of the real
  filesystem (`GET /fs/dirs` — dirs only, hidden skipped; browsers cannot expose
  absolute paths, so the native-feeling picker runs against the local backend).
  SourcesPanel retired (its features live on the link nodes now); unfiled
  listings exclude source materials. 235 backend + 116 frontend tests.
- 2026-08-19 — Phase 8B slices 1–2: **Nemo-style library + material detail page**.
  Library is now a file-manager-style navigator: breadcrumb bar over URL search
  params (`?course=&folder=`, deep-linkable, back/forward works), grid default with
  a persisted list toggle (localStorage), folders navigate in place (Up button +
  clickable crumbs), "All courses" root shows course cards (entering one syncs the
  rail workspace selector), right-click context menu on folders (open/rename via
  inline tile edit/delete with reparent confirm), item-count status bar, and search
  results replace the pane. New route `/library/$materialId` with routable tabs
  (`?tab=`): Extraction | Original | Side-by-side (OCR QA view kept); header shows
  status/course chip, **assigned-to chips** (new `GET /api/v1/materials/{id}/links`
  returning owner titles incl. chapter + course context) and a **study-status
  control** (unread/reading/studied — first frontend for B16 read-status).
  Backend: `listMaterials` gains `unfiled` filter (course-root listing excludes
  foldered materials); ExtractionView/OriginalView extracted into shared components
  (reused by the detail page and, later, the chapter workspace). 230 backend +
  110 frontend tests.
- 2026-08-19 — **ADR-037 approved (plan only, no code yet): linked sources become
  symlink-style folder nodes.** Sources appear in the course folder tree
  (`material_folders.source_id`), navigation is live scandir (virtual
  subdirectories, nothing stored), un-ingested files get a pending badge +
  explicit ingest, dangling targets show a badge with a re-link flow, unlink
  keeps materials (moved to course root), and the app never writes to a target.
  One deliberate divergence from real symlinks: content stays blob-copied on
  ingest so originals survive target deletion. Roadmap 8B gained slices 4–6
  (L1 link nodes + browse, L2 reconciliation automation + startup/periodic
  scan, L3 robustness tail). 8B slice 1 (Nemo-style library) is in progress.
- 2026-08-19 — Phase 8A: **per-course materials & scoped assignment (ADR-036)**.
  Migration 0014: `section_materials` → **`material_links`** (owner_type
  course|chapter|section, owner_id, material_id — unique per owner+material,
  intra-course enforced in the service; data preserved, unlink ≠ delete);
  **`materials.course_id` required** (no global library) — legacy course-less
  materials, NULL-course sources and unassignable folders moved into an
  auto-created **"Unsorted"** course per profile (folders with a single-course
  subtree were assigned that course; mismatched materials lost their folder
  placement, not their course); `material_folders.course_id` (one tree per
  course, unique profile+course+path, no cross-course moves) and
  `material_sources.course_id` (sources now require a course; scans dedupe
  per course) required. Upload API takes a required `course_id` (per-course
  dedup kept — same file in two courses = two materials, one blob). New APIs:
  GET/POST/DELETE `/courses/{id}/materials[/{mid}]` and
  `/chapters/{id}/materials[/{mid}]`; `/courses/{id}/tree` carries
  chapter-level materials. **Course deletion now purges everything owned**
  (materials incl. extractions/chunks/FTS/vec rows/index cards/study states,
  folders, chapters/sections, quizzes+attempts+answers+help events+mistakes,
  exercises, flashcards+reviews, notes+drawings, chat sessions+messages,
  sources) — frontend confirm wording updated. Library page scopes by the
  workspace course (folders, materials, uploads, folder creation, linked
  sources; "All courses" mode lists everything with course chips and disables
  uploads with a hint); course-page picker only offers the course's own
  materials; zero courses → WorkspaceGate. `vectors.delete_for_extraction` is
  now a no-op when the vec table doesn't exist (purge on FTS-only installs).
  229 backend + 108 frontend tests.
- 2026-08-19 — **ADR-036 supersedes ADR-034 (user decision, pre-implementation):
  per-course material ownership, no global library.** Every material belongs to
  exactly one course; no cross-course sharing; folder trees become per-course
  (course → folders → materials) and the Library scopes by the selected course.
  Same document in two courses = two materials/extractions (accepted cost); blob
  bytes still stored once (content-addressed store unchanged). Scoped assignment
  (course/chapter/section, intra-course only) via `material_links` stays in 8A;
  legacy course-less materials migrate to an auto-created "Unsorted" course.
  Plans 01/03/05 + this file updated; no code changed (as-built still has the
  nullable course_id global library until 8A ships).
- 2026-08-19 — **Phase 8 planned & approved (plan restructure, user request; no code
  yet)**. Courses/chapters/notes draft vision reviewed against as-built: outline
  auto-creation + per-section allocation already exist; the gaps are course/chapter-
  scoped material linking, a chapter study view, notes maturity (tags/pagination/
  Tiptap), concepts graph, and AI chapter organization. Decisions: **ADR-034**
  (link-based materials — one material row per document per profile, scoped
  `material_links` at course/chapter/section, cross-course linking explicit,
  `materials.course_id` demoted to home-course metadata) and **ADR-035** (tree depth
  fixed at 2 levels). Roadmap gained Phase 8 slices 8A–8E; feature catalog gained
  A13/A14/E10; data-model plan gained the Phase 8 design section. Command palette
  (I5) deferred to polish; Tiptap moved into 8C.
- 2026-08-19 — **Routable tabs + provider-form dropdown + explicit key-keep.**
  Settings and Scores tabs are URL search params now (`/settings?tab=models`,
  `/scores?tab=history`) — deep-linkable, back/forward works (router
  `validateSearch` + navigate; tab buttons carry `aria-current`). The Add-provider
  form replaces the redundant preset-chips + type-select pair with a single
  provider dropdown (Google/OpenAI/Anthropic/Ollama/Custom-OpenAI-compatible —
  type and base URL derive from the choice, name prefills only while untouched,
  Custom requires a base URL). Edit-provider now shows an explicit "a key is
  stored — leave blank to keep it" hint (behavior was already key-preserving and
  backend-tested; the UI now says so). 104 frontend tests.
- 2026-08-19 — **Discover folded into the Add-model dialog.** The per-provider
  Discover button is gone from the Models tab (it imported the whole catalog as
  hidden disabled rows — inconsistent with the curated selected-models list).
  The dialog's new **Add all N** footer action bulk-adds every model matching the
  current fuzzy search (batches of 20, confirmation above 20; clear the search to
  import the full catalog — the old Discover use case, but visible/enabled).
  102 frontend tests.
- 2026-08-19 — **Fuzzy search + infinite scroll in the model picker.** New
  hand-rolled `lib/fuzzy.ts` (fzf-style subsequence scoring: start/separator
  boundaries, consecutive-run and exact-match bonuses, ranked + length-tie
  filtering — zero new deps) powers the Add-model dialog search (matches ids and
  capabilities, so "vision" surfaces vision models); notes search reuses the same
  markup via a new shared `SearchInput` component. The dialog list now loads
  incrementally — 30 rows, then IntersectionObserver on a sentinel loads more as
  you scroll, with a "Showing X of Y" footer; new-query resets paging. 101
  frontend tests.
- 2026-08-19 — **Models tab = curated list + robust add flow.** The tab now shows
  only *selected* (enabled) models per provider — no more checkbox wall; edit
  (pencil) keeps label/caps/enabled, delete (trash, `DELETE /models/{id}`) removes
  a model and clears its task assignments. Add-model dialog gained an explicit
  **Add manually** form (id + display name + caps chips) that works even when the
  provider can't list models, an "Add back" action for disabled models (re-adding
  now re-enables — idempotent `POST /models` applies `enabled`), and on listing
  failures (401/403) the backend message now says whether *no key is stored* or
  *the key was rejected*, with Edit-provider/Retry buttons in the dialog.
  218 backend + 85 frontend tests.
- 2026-08-19 — **Settings providers/models overhaul (modular)**. Providers: existing
  entries are editable (pencil button → shared `ProviderFormDialog` used for create
  *and* edit — rename, base URL, enabled toggle, key replacement only when a new key
  is typed; type stays fixed). Models: per-provider **Add model** button opens a
  searchable dialog over the provider's *live* catalog (new
  `GET /providers/{id}/remote-models` — fetches without persisting), add-one-by-one
  with caps shown, manual add fallback for ids not in the catalog, and already-added
  models marked; per-model **edit** dialog (label + capabilities text/vision/tools/
  embeddings + enabled — `POST /models` manual add is idempotent and revives `missing`
  models; caps validated against the vocabulary on create/update). Settings page
  split into modular components (`ProvidersTab`, `ModelsTab`, `TasksTab`, `DataTab`,
  `SkillsTab` + three dialogs). 214 backend + 83 frontend tests.
- 2026-08-19 — **Error banners link to Settings for AI-config problems**: new shared
  `ErrorBanner` replaces the plain error text on the generation surfaces (quiz
  generate, exercise generate + page errors, flashcard generate, Today drill/
  challenge, note editor actions/drawings). When the message indicates a task is
  unassigned or a provider problem, the banner shows an "Open Settings" button
  (routing to `/settings`); other errors render message-only. 80 frontend tests.
- 2026-08-19 — Phase 7 slice 8: **course workspace selector (ADR-033)**. Course
  dropdown in the nav rail ("All courses" + each course, persisted in localStorage,
  validated against the course list so stale/profile-mismatched selections fall back).
  Selecting a course scopes the study pages: Quiz/Exercises/Notes/Flashcards/Scores
  filter lists (query keys carry the course), generation binds new content
  (quiz/exercise/drill/flashcards/notes, caq + qpkg import, Anki import/export),
  rail-created chat sessions are course-bound (course-scoped RAG + skill resolution),
  and diagnostics/recommendations accept `course_id` (metrics: answer_rows,
  error_profile, due_cards_count, recommendations gained optional course scoping;
  overview/items stay profile-wide by design — Today is cross-course). Backend list
  endpoints gained optional `course_id` filters: quiz activities/attempts/mistakes,
  exercises, flashcards due. Study pages show a create-course-first gate
  (`WorkspaceGate`) only when zero courses exist; "All courses" keeps legacy unbound
  content visible. Today screen stays profile-wide but its drill/challenge buttons
  target the selected course. 209 backend + 76 frontend tests.

- 2026-08-19 — **`--force` for launch scripts**: `scripts/dev.sh` / `scripts/webapp.sh`
  now check the port before starting — if busy they print the holder's pid +
  commandline and exit with a hint (`--force`, or `CA_PORT`); `--force` TERM→KILL
  kills the holders (dev also clears the Vite port). Recovers from leaked uvicorn
  --reload/vite processes after abnormal exits; `pnpm dev --force` passthrough
  verified. dev.sh now starts uvicorn on `CA_PORT` (default 8000) explicitly.
- 2026-08-19 — **Fixed `apiFetch` infinite recursion** ("too much recursion" on every
  mutating/list call — e.g. course creation failed in the UI while the backend
  returned 201): the profile-header wrapper in `frontend/src/lib/api.ts` called
  itself instead of the global `fetch`. Regression tests added (single delegation,
  profile header, header preservation). 203 backend + 62 frontend tests.
- 2026-08-19 — **SPA deep-link fix (webapp mode)**: refreshing a client-side route
  (`/courses`, `/quiz/...`) returned `{"detail":"Not Found"}` — `StaticFiles` only
  serves `index.html` at `/`. Added `SpaStaticFiles` (`app/main.py`) which re-serves
  `index.html` on 404 for non-`api/`/`ws/` paths, so browser refresh and direct links
  work in every launch mode; unknown API paths still return a JSON 404. 203 backend
  tests.
- 2026-08-19 — **Launch modes + browser-first pivot.** New `scripts/webapp.sh` (build
  if needed → `python -m courseassistant web`: uvicorn serves the SPA on
  `CA_PORT`/8000 and opens the default browser), `scripts/dev.sh` (uvicorn --reload +
  Vite dev concurrently, `kill 0` cleanup), `scripts/app.sh` (desktop shell, build if
  needed, `--rebuild` flag on both). pnpm aliases `webapp`/`dev`/`app`; `__main__`
  dispatches modes via `resolve_mode` (unknown → error). Webapp mode verified
  end-to-end (SPA served, health green, clean shutdown). Reason: the user still sees
  a white window in the desktop shell on their machine even though the page loads and
  executes (server logs show full asset + API traffic) — developing as a local web
  app until the shell is revisited. 202 backend tests.
- 2026-08-19 — Phase 7 slice 7: **packaging (.deb + AppImage)**. `_find_spa_dist`
  now resolves the bundled SPA from `sys._MEIPASS/frontend/dist` when frozen
  (PyInstaller). Added `packaging/courseassistant.spec` (bundles `frontend/dist`
  as data, windowed, excludes test/scientific junk), `packaging/build_deb.sh`
  (PyInstaller collect → `/usr/lib/courseassistant` + launcher + .desktop + icon
  → `dpkg-deb`; built & verified a 50 MB amd64 .deb), and
  `packaging/build_appimage.sh` (AppDir + AppRun + icon + `appimagetool`).
  pyinstaller added to backend dev deps; build outputs gitignored. The app
  keeps writing user data to the standard data dir at runtime, never the install
  location. 198 backend + 59 frontend tests.
- 2026-08-19 — Phase 7 slice 6: **skills & prompt library (J5, full doc 08)**.
  Migration 0013 adds `skills`, `skill_versions` (UNIQUE skill/scope/version),
  `course_types`, and `courses.course_type_id`. Code-seeded system skills
  (tutor.hint, quiz.help_hint, chat.answer, quiz.generate, exercise.generate,
  flashcards.generate, ocr.page, notes.transcribe, notes.action, grade.freeform)
  seeded idempotently on startup; jinja2 added as a dependency. `SkillService`
  handles resolution (course → course_type → system, most specific wins),
  template rendering (server-side; malformed legacy templates fall back to raw so
  a bad edit never breaks a pipeline), versioning (save forks a new version,
  activate/restore-default, diff), and contract construction (DB-editable safe
  subset — max_words, no_answer_reveal — merged with code-only constraint kinds).
  Pipelines now resolve their skill, render the prompt, and log
  `skill_version_id` on every ai_interactions row (tutor, quiz_help, chat,
  quizgen, exgen, flashcards, notes.action) for full reproducibility. Full
  doc-08 UI: Settings → Skills tab (skill list + course-type manager + editor:
  system/user Jinja template editors with insert-variable chips, contract panel,
  scope picker with per-scope resolution badge, versions list with
  activate/restore, sandbox test-run rendering the prompt + per-constraint list,
  and export/import skill pack as JSON). Courses accept a `course_type_id`.
  198 backend + 59 frontend tests.
- 2026-08-19 — Phase 7 slice 5: **import inbox + external-AI authoring kit**
  (doc 11). The app now has a watched-by-scan import directory
  (`data/import-inbox`, created with `AUTHORING.md` + `schema.json` at its root so
  agentic tools can self-serve the format). `GET /quiz/inbox` stages and
  validates every `.caq.json`/`.json`/`.qpkg` found (same validators as quizgen;
  qpkg checksums verified); `POST /quiz/inbox/{file}/import` commits through the
  standard import path and renames the file `.imported` (or `.rejected` with an
  error report next to it). The Import dialog gained tabs: **Inbox** (staged
  files with per-file verdicts + the folder path) and **Author with AI** — a
  prompt builder (topic/count/types/difficulty → ready-to-paste prompt embedding
  the caq/v1 schema card and all validator rules; copy button). 192 backend +
  57 frontend tests.
- 2026-08-19 — Phase 7 slice 4: **cost accounting + budgets + i18n audit**.
  Migration 0012 adds `ai_interactions.task` (indexed) — the gateway now keeps a
  **cost ledger**: every real `generate`/`stream` call writes one
  `context_type="gateway"` row with task, model, estimated tokens, latency, and
  **estimated cost** (tokens × the model's $/1M rates from Settings; local models
  with no rates → cost null, never blocking). **Per-task monthly budgets**:
  `task_assignments.params.monthly_cap_usd` (PUT `/tasks/{task}/budget`, editable
  inline in Settings → Tasks); the gateway checks the month's ledger spend before
  every call and raises `BudgetExceeded` with a clear message — no API call is
  made over cap. `GET /analytics/costs` returns per-task calls/tokens/cost vs cap
  + month total; the Tasks tab shows spend per task and a *budget reached* badge.
  Frontend gained a **translation-readiness audit test** (scans all `t('key')`
  literals, resolves plurals, fails on missing keys — runs in every CI suite).
  189 backend + 57 frontend tests.
- 2026-08-19 — Phase 7 slice 3: **linked folders, profiles, qpkg, onboarding**.
  Migration 0011 adds `material_sources` (label, path, recursive, include_globs,
  course binding). Linked-folder scans are stat-first per doc 03: unchanged
  mtime+size → skip (no read); changed → content hash (same = touch, different =
  new blob + material back to pending → ingest job → new extraction version);
  vanished files mark materials `missing` and a reappearing file re-ingests;
  content is copied into the blob store so originals stay self-contained. Profile
  switcher: raw-ASGI middleware maps `X-Profile-Id` → ContextVar consumed by
  `ensure_default_profile` (BaseHTTPMiddleware silently breaks ContextVar
  propagation — pure-ASGI is required); frontend wraps every API call with the
  stored profile header; create/switch in the rail; deletion refused while a
  profile still owns content. **qpkg (caq-pkg/v1)**: per-quiz export as zip
  (manifest with per-item sha256 + quiz.json); import verifies checksums before
  the caq dry-run/commit path (tampered archives → 422 integrity error). Sample
  course onboarding endpoint + Today-screen button when the library is empty (3
  markdown lessons ingested synchronously, FTS-indexed immediately, idempotent).
  Library sidebar gained the linked-sources panel (link/scan/unlink with scan
  report). 185 backend + 56 frontend tests.
- 2026-08-19 — Phase 7 slice 2: **weak-area sessions + backup/restore + print**.
  Quiz generation accepts `topic` + `skill`: the quizgen prompt gains FOCUS TOPIC /
  SKILL FOCUS directives, retrieval scopes to the topic, and the activity title
  carries it — the Today screen's drill/challenge buttons now generate a targeted
  quiz on the weak concept (difficulty 2 band for drills, 4 for challenges) and
  navigate straight into it (H4 closed first cut). **Backup/restore (I6)**:
  `GET /backup/export` produces a `ca-backup/v1` zip — a consistent SQLite
  snapshot via the backup API (converted to rollback-journal mode so the archive
  is portable; WAL in-memory deserialize is a known sqlite3 trap), the full blob
  store, and a manifest; `POST /backup/restore` validates manifest +
  integrity_check + alembic history before swapping the database (WAL sidecar
  files removed), restores blobs, re-runs migrations, and reseeds defaults —
  round-trip tested across two app instances. Settings gained a Data tab
  (download / restore with replace-all warning). Print export (I16 first cut):
  print CSS hides chrome and a Print action on quiz rows. 181 backend + 55
  frontend tests.
- 2026-08-19 — Phase 7 slice 1: **analytics foundation + Today screen**. Migration
  0010 adds concept_skill_stats (materialized weakness matrix), daily_rollups,
  item_stats, study_goals. New `app/services/metrics.py` — the doc-10 metrics
  catalog as code: weakness matrix (concepts × skills, accuracy + time-vs-expected,
  sample-size honesty: cells under 3 answers render as low-confidence, never red),
  error-pattern profile (totals, 7-day trend), speed–accuracy quadrants
  (fluent/rushing/effortful/struggling), item analysis (p-correct, avg-time ratio,
  distractor selection rates; n≥20 with p outside [0.1, 0.95] auto-flags the
  question `review` on materialize), streak + daily history + XP/level, due-card
  counts, and the recommendations engine (due reviews first, then weakest
  concept×skill cells — conceptual weakness → read, procedural → drill — then
  strong-but-stale challenge; every recommendation carries an evidence line with
  the underlying numbers). Exam attempts are excluded from all mastery signals.
  API: GET /analytics/{overview,diagnostics,recommendations,items}, PUT /goal,
  POST /materialize. Frontend: HomePage is now the Today screen (streak, daily
  goal ring with inline goal editing, due-review count, next-best-action cards
  with one-tap actions, 90-day consistency heatmap); Scores page gained tabs —
  Diagnostics (matrix heatmap, error tags with trend, speed quadrants) and Tips
  (recommendations with evidence). 178 backend + 54 frontend tests.
- 2026-08-19 — Phase 6 slice 2: acceptance paths complete. **Anki .apkg
  import/export** (`app/pipelines/anki.py`, no anki dependency): export builds a
  minimal valid collection.anki2 (col/notes/cards/revlog schema, sha1 csum,
  zip + empty media manifest) — round-trip tested; import reads .anki21/.anki2,
  maps note fields → flashcards (cloze detection via `{{c1::}}`, deck name from
  col.decks), non-cards skipped and reported. **C18 handwriting input**:
  `POST /quiz/recognize` (notes_ocr engine, returns markdown + last-3 math
  candidates via the leak-guard extractor); quiz runner gains a write mode for
  text/numeric/equation questions — draw → recognize → "interpreted as" chips →
  student picks/edits → submit; **OCR never grades** (only confirmed LaTeX
  does); strokes + input_mode stored on the Answer envelope. **AI note actions**
  (P9): summarize/cleanup/explain/expand over note text + drawings' OCR, contract
  max_words + repair, audited as `note_action`; UI shows the result with
  append-to-note. **Chat latest-notes slot**: the 3 most recent notes (pinned
  first, course-scoped when the session is) join the prompt as explicitly
  uncited background context. "Make flashcards" button on the note editor
  closes the handwrite → deck → FSRS loop. 173 backend + 48 frontend tests.
- 2026-08-19 — Phase 6 slice 1: **notes + handwriting OCR + flashcards with FSRS**.
  Migration 0009 adds notes (title, JSON-blocks body, `search_text` column fed by
  body + drawing OCR so note search covers handwriting, owner binding
  standalone/section/material/exercise_session/chat_message, pinned),
  note_drawings (replayable strokes JSON kept as the source of truth, PNG stored
  content-addressed in the blob store, OCR result + version on the row —
  re-transcribe bumps the version), flashcards, fsrs_states (unique per card,
  due_at index), review_log. Notes API: CRUD, search, drawings with `notes_ocr`
  (math-aware vision prompt: LaTeX for handwritten math), re-OCR endpoint.
  Flashcards: generation via the `flashcards` task from three sources (note incl.
  its drawings' OCR, material extraction, mistake notebook) with deterministic
  validators (kind ∈ basic/cloze/reverse, cloze needs a `{{...}}` deletion,
  non-empty fronts/backs, duplicate fronts rejected against existing cards) and
  a repair loop; every call audited. Manual card creation held to the same
  validators. **FSRS-4.5 scheduler in pure Python** (default weights, desired
  retention 0.9, stability/difficulty/interval, learning/review/relearning
  states) — no external dependency; review endpoint applies it transactionally
  and writes review_log. Frontend: Notes page (list + search, markdown editor
  with live preview via BlockRenderer, drawing panel using the shared
  `DrawCanvas` component — pointer-event strokes, client-side PNG render, undo/
  clear), Flashcards page (generate card, due queue with reveal + Again/Hard/
  Good/Easy, card list). Chat sidebar state → Zustand store (`chat-store`) so
  any page can open chat on a bound session. 165 backend + 47 frontend tests.
- 2026-08-19 — **Phase 5 complete**: remainder items landed. New `exgen` task +
  pipeline (`app/pipelines/exgen.py`): LLM exercise generation with deterministic
  validators (every step's expected answer must parse via the equivalence chain;
  numeric values/tolerances sane) and a repair loop (max 2) — an exercise that
  still fails is rejected (422), never persisted broken. **Similar exercises
  (D7)**: `POST /exercises/{id}/similar` — isomorphic variant validators require
  same step count, changed prompts, and at least one answer non-equivalent to the
  source (proven via the chain). **Error-pattern drills (D8)**: G10 calculus error
  taxonomy seeded in code (8 patterns: chain rule, power rule, +C, u-sub bounds,
  limit/continuity, sign slips, dropped factors, notation); `GET
  /exercises/drills/patterns` lists them with occurrence counts from the mistake
  notebook; `POST /exercises/drills` generates a targeted drill. **P5b
  quiz-question help (C9b)**: migration 0008 adds `quiz_help_events` +
  `chat_sessions.context`; practice attempts get the 5-level hint ladder per
  question (levels 1–4 while the answer is open, no-skip server-enforced; level 5
  unlocks post-submit; exam attempts refused help with 422); hints run the
  tutor.hint contract incl. the leak guard, now extended with
  `expected_candidates` + `forbidden_texts` (choice questions may not quote the
  correct option); help events are listed per question and copied onto
  `answers.help_events` at submit time; "ask about this question" creates a chat
  session bound to the attempt whose answers run under the chat no-answer wrapper
  (contract + system rule) until the question is answered. Exercise session
  transcript endpoint (every answer + hint in order). Frontend: Generate
  dialog + Similar buttons + Drills card on Exercises; hint cards + full-solution
  + ask buttons in the quiz runner (practice only); chat sidebar state moved to a
  Zustand store so pages can open it on a bound session. 148 backend + 43
  frontend tests.
- 2026-08-19 — Documentation restructure (user request): `docs/` is now the complete
  tracked doc set — added `docs/README.md` (index), `architecture.md` (as-built
  system), `features.md` (catalog with ✅/— completion map), `ai.md` (providers/
  tasks/gateway/contracts/tools), `math-verification.md` (equivalence chain + leak
  guard), `data-model.md` (as-built schema incl. runtime vec tables + not-yet-built
  inventory), `import-export.md` (caq/v1 spec) — alongside the existing `usage/`
  guides and STATUS.md. `dev/` stays developer-only planning (gitignored).
  AGENTS.md "Where things are" and the ca-docs-sync skill now point at the new
  structure.
- 2026-08-19 — Documentation sync pass (ca-docs-sync): created `docs/usage/` (6 user
  guides: getting started, library, courses, quiz, exercises, chat — linked from
  README); `dev/plans/03` gained the as-built schema section (migrations 0002–0007,
  deviations: surrogate PK on study state, FTS service-layer sync, runtime vec
  tables, folders addition, not-yet-built table inventory); `dev/plans/02` module map
  refreshed to the real layout with deviation notes; `dev/plans/06` gained ADRs
  029–032 (hand-rolled gateway adapters w/ LangGraph deferred, runtime vec0 tables,
  plan-07 layer pulled into Phase 1, local embeddings deferred). Plans are
  local-only/gitignored — STATUS.md remains the tracked source of truth.
- 2026-08-19 — Phase 5 first slice: exercises & tutor with the **hint-leak guard
  (G11) live from day one**. Migration 0007 adds exercises/steps/sessions/
  step_attempts (hint_level_used + error_class per attempt, per-session
  independence score). Tutor: step answers run the equivalence chain (with
  numeric-tolerance fast path), errors classified (parse→misread,
  procedural/conceptual by skill); hint ladder 1–5 (clarify→nudge→strategy→
  partial→full) where levels never skip (server-enforced) and **every hint below
  level 5 passes `no_answer_reveal`** — the contract extracts $…$/$$…$$/bare
  numbers from hint text and proves none equivalent to the step's expected
  answer via the chain; violations trigger a repair loop (max 2). All hints
  audit to `ai_interactions`. Frontend: Exercises nav + player (MathLive input,
  stacked level-tagged hint cards, error-class chips, completion screen with
  independence %). **Chain bug fixed**: solveset stage equated any two
  expressions whose only shared root was 0 (3x vs 2x both →{0}); now applied
  only to equation-form inputs. 135 backend + 38 frontend tests.
- 2026-08-19 — Phase 4 tail: equation questions use **MathLive** (shared `MathInput`
  component, React-delegated input events — no effect-timing races); **caq/v1
  interchange** (C22/C23 first cut): `GET /quiz/activities/{id}/export` downloads
  `.caq.json`; `POST /quiz/import?dry_run=` validates pasted documents with the
  same validators as quizgen (per-question ok/problems preview in UI) then commits
  with `provenance: caq/v1` — external-AI-authored quizzes are held to identical
  standards; round-trip test (export → import → valid). Wrong single/multi answers
  now carry distractor→misconception tags (`forgot_product_rule` etc.) onto
  answers + mistakes. **Scores page** (H2b first cut): History tab (all attempts,
  score-colored, links to retake) + Mistake notebook (stem excerpt, error tags,
  source quiz). 122 backend + 36 frontend tests.
- 2026-08-19 — Phase 4 core = **v0.1 walking skeleton functionally complete**
  (upload → outline → quiz → chat RAG all work end-to-end). Migration 0006 adds
  activities/questions/attempts/answers/mistakes with the full doc-10 metadata
  taxonomy on questions (concepts/skill/bloom/difficulty/expected_time/
  misconceptions/sympy_check) and telemetry on answers (time_ms, retries,
  error_tags, help_events). New `app/math/equivalence.py` — G9 chain: LaTeX
  normalization (\frac, \sqrt, \cdot, implicit multiplication via sympy
  transformations) → symbolic simplify → seeded complex random-point sampling →
  solveset; any stage proves equivalence (typing `x^2 cos(x) + 2x sin(x)` grades
  correct against `2*x*sin(x)+x**2*cos(x)`). Grading service (6 types, multi
  partial credit, numeric tolerance abs/rel). Quizgen pipeline with deterministic
  validators (metadata required — questions enter the bank tagged or flagged
  `review`; distractors checked against the answer with the chain) + repair loop.
  Quiz API: generate (course/section scope, count, difficulty), attempts
  (practice/exam), instant-feedback answers, finish w/ score, report; mistakes
  recorded on wrong answers. Frontend: Quizzes page + runner (one question per
  screen, A–E options, type-in/equation inputs, verdict + streamed-in
  explanation UI, SymPy badge, animated summary ring with score). 117 backend +
  35 frontend tests.
- 2026-08-19 — Phase 3 completion slice: **token streaming** — `LLMGateway.stream()`
  with SSE parsers for all three provider families (openai-compatible
  `chat/completions`, anthropic `messages` content_block_delta, google
  `streamGenerateContent?alt=sse`); chat turn streams deltas over WS `chat:{id}`
  (`stream_start`/`stream_delta`/`tool_round`/`assistant_message`), final message
  persisted + audited as before. **Math tools** (`app/ai/tools.py`): `CALC` —
  regex+namespace-sandboxed numeric eval (math functions only, no builtins,
  dunder-guarded, non-finite rejected); `SYMPY <action> <expr>` — deterministic
  solve/simplify/diff/integrate/expand/factor/limit via SymPy; model emits tool
  lines, executor runs them, results injected as a system message for the next
  round (max 2), tool lines stripped from the stored answer. System prompt carries
  the tool doc. Frontend renders stream progressively (markdown+KaTeX per delta
  batch) and shows a "verifying with math tools" state on tool rounds. sympy added
  to deps. 89 backend + 33 frontend tests.
- 2026-08-19 — Phase 3 first slice: chat RAG with contracts. Migration 0005 adds
  `chat_sessions`, `chat_messages` (blocks+citations+grounded), `ai_interactions`
  (audit per call: model, estimated tokens, latency). Pipeline: POST message →
  user row + `chat_turn` job → course-scoped FTS chunk retrieval (OR-terms query
  with stopwords; vector channel joins when embeddings exist) → gateway `chat` task
  with numbered sources → deterministic contract validation (citation presence/range/
  length) with one repair round → assistant message with parsed citations (chunk,
  material, quote) + grounded flag; WS push on `chat:{id}`. Contracts engine
  (`app/ai/contracts/`) is generic (registry of validators) — foundation for quiz/
  tutor skills later. Frontend: chat sidebar toggled from the rail (sessions select,
  new chat, markdown+KaTeX answers, [n] citation chips with quote tooltips,
  not-grounded marker, thinking state). 82 backend + 31 frontend tests.
- 2026-08-19 — Phase 2 started (migration 0004): `chapters` (self-FK parent, 2-level
  max), `sections`, `section_materials` (composite PK, rationale/auto_assigned/
  confidence), `material_study_state` (unique per material×profile; B16 read-status).
  APIs: courses CRUD + `/tree`; chapters/sections add/rename/move/delete (delete
  reparents sub-chapters, cascades sections+allocations); outline `draft` (LLM via
  `outline` task over material index cards; validator drops unknown/repeated material
  ids, clamps counts/confidence) and `commit` (append-only — never overwrites; writes
  auto-assigned allocations); manual allocate/deallocate; study-state PUT + list.
  Frontend: Courses page (create/delete/list) and course page (chapter drag-reorder,
  add/rename/delete chapters & sections, per-section allocation with AI-confidence
  chips, outline review-then-commit card). 75 backend + 28 frontend tests.
- 2026-08-18 — Phase 1 QA + retrieval completion: extraction editing API
  (`PATCH /materials/{id}/extraction` → version+1, `edited_by_user`, re-chunk, FTS
  re-sync, postprocess re-embed) with UI editor + side-by-side original viewer
  (`GET /api/v1/blobs/{sha}`, inline images/PDFs); hybrid search — FTS5 BM25 +
  sqlite-vec (vec0, cosine) fused via RRF(k=60), graceful FTS-only fallback when the
  embeddings task is unassigned or dims mismatch; `embeddings` task implemented over
  the gateway (google batchEmbedContents, openai-compatible /embeddings); `description`
  task fills index cards (summary/topics/key_terms/difficulty) in a best-effort
  postprocess job (never fails ingestion); vec tables are runtime-created (need the
  sqlite-vec extension, not Alembic-migratable) with dim/model in `vec_meta`, rebuilt on
  model change. 69 backend + 25 frontend tests.
- 2026-08-18 — Plan-07 layer landed in Phase 1 (user-approved scope change) + library
  folders: `material_folders` (nested virtual directories, materialized paths,
  rename/move/delete-reparent) with upload/list folder scoping and a folder-tree UI;
  `providers`/`models`/`task_assignments` tables + Settings UI (Providers/Models/Tasks
  tabs, presets incl. Ollama, API keys → OS keyring only, masked in UI, discovery with
  capability heuristics, vision-gated `ocr` task assignment); `LLMGateway` (task→model→
  provider resolution + fallback chain, google/openai_compatible/anthropic adapters,
  httpx hand-rolled — per ADR-004's revisit clause; LangGraph adoption deferred to
  pipeline graphs); OCR is task-driven (`ocr` → any assigned vision model) — scanned
  PDFs rasterize at 150dpi → per-page OCR, images OCR'd directly; 65 backend + 23
  frontend tests. Note: OCR prompt is a code constant until the skills engine (Phase 3)
  versions it; ai_interactions audit logging still pending (Phase 3).
- 2026-08-18 — Phase 1 ingestion slice (vertical): materials upload/list/detail API with
  content-hash dedup; durable JobRunner (jobs table, claim-based worker thread, progress
  over WS `jobs:{id}` via threadsafe EventBus bridge); PyMuPDF text-PDF + native txt/md
  ingestion → versioned extraction + chunks + FTS5 (same tx) + heuristic index card;
  scanned-PDF/image paths fail fast with "OCR not configured"; FTS search endpoint with
  snippets; default profile auto-seed + migrations run on app startup; frontend Library
  page (upload w/ WS progress bar, status badges, extraction viewer via BlockRenderer).
  48 backend + 18 frontend tests green.
- 2026-08-18 — **Phase 0 accepted** (user ran the shell: window + rendering OK; health
  endpoint green; CI mirrored). Phase 1 started: core schema (profiles, courses minimal,
  material_groups, blobs, materials, extractions, chunks, material_index_cards, jobs,
  material_fts FTS5), content-addressed blob store, Alembic migration 0002. FTS sync is
  service-layer in-transaction (single-writer app) rather than doc-03's "via triggers".
- 2026-08-18 — localStorage crash in the shell fixed: pywebview's default
  `private_mode=True` runs WebKitGTK ephemeral (localStorage undefined) → shell now
  starts with `private_mode=False`; theme bootstrap + ThemeToggle guard localStorage
  access. Both suites green; dist rebuilt.
- 2026-08-18 — Shell launcher de-snaps its environment (snap VS Code terminals pollute
  `LD_LIBRARY_PATH`/`XDG_*`, which crashed WebKitNetworkProcess against core20's
  libpthread and would scope app data into `~/snap/code/...`): `sanitize_environment()`
  restores `*_VSCODE_SNAP_ORIG` originals or strips `/snap/` entries before GTK/uvicorn
  start; 6 unit tests.
- 2026-08-18 — Desktop shell now launches prerequisites-complete on Linux Mint:
  `pygobject` (linux-only marker) added to backend deps; compiled in-venv against
  `libgirepository-2.0-dev`/`libcairo2-dev`; `gi` + WebKit2 4.1 + pywebview GTK backend
  import-verified. Visual WebKitGTK spike check still pending (user).
- 2026-08-18 — Added root `README.md` with Linux prerequisites for the pywebview shell
  (`libgirepository-2.0-dev`, `libcairo2-dev` — required to build PyGObject; WebKitGTK
  typelib preinstalled on Mint) and dev/verify commands.
- 2026-08-18 — `dev/plans/` is fully gitignored again (user decision): all of `dev/` is
  local-only scratch, plans are never committed. AGENTS.md, both skills, and this file
  updated to say so; tracked doc surface is now AGENTS.md + `docs/` + `.opencode/` only.
- 2026-08-18 — Phase 0 skeleton implemented on `feat/phase-0-skeleton`: uv/pnpm
  workspaces; backend (FastAPI app factory, `/api/v1/health`, settings, keyring wrapper,
  structlog, EventBus + `/ws`, SQLAlchemy engine w/ WAL pragmas, empty Alembic baseline,
  13 tests); frontend (Vite+React+TS, Tailwind 4 semantic tokens light/dark, shadcn
  base, i18n harness w/ no-literal-string lint, block renderers, nav shell, Today
  placeholder, rendering-spike page for KaTeX/Mermaid/MathLive/canvas); CI mirrors both
  verification suites. `.gitignore` fixed to actually track `dev/plans/` and `.opencode/`
  (docs claimed tracked but the old rules ignored them).
- 2026-08-18 — Plans moved back to `dev/plans/` (tracked; rest of `dev/` gitignored via
  `dev/*` + `!dev/plans/`). References updated. Tracked docs: AGENTS.md, docs/STATUS.md,
  dev/plans/, .opencode/.
- 2026-08-18 — `dev/` is now fully gitignored scratch space (notes.txt); STATUS.md moved
  to `docs/STATUS.md` so all tracked documentation lives under `docs/`. Fixed the
  misnamed `.gitignored` → `.gitignore`.
- 2026-08-18 — Plans moved from `dev/plans/` to `dev/plans/`; all references updated
  (AGENTS.md, skills, STATUS.md). User-facing docs will live in `docs/usage/`.
- 2026-08-18 — Planning complete: docs `dev/plans/01–11` + `README.md` written and
  cross-linked; 28 ADRs recorded; opencode agent harness added (AGENTS.md, skills
  `ca-dev` / `ca-docs-sync`, this file). No code yet.

## Open issues

- **Delete-during-ingest hardening — RESOLVED (2026-08-31, plan 54-A/ADR-126)**:
  in-flight jobs are now cancelled (cooperative report checkpoints + cancel flags +
  commit-time stale re-checks) instead of failing on the FK or committing into a
  purged entity; queued jobs are marked `cancelled` at purge time. See the
  changelog entry.
- **JSXGraph uses `eval` internally (plan 34C, 2026-08-24)**: `jsxgraph`'s bundled
  JessieCode/math evaluation (`createFunction`/parser) calls `eval`/`new Function` on
  expression strings — library code, not ours, and reachable only via the `geo` block's
  construction script in the local sandboxed shell. Accepted for now (G5's approved
  library); revisit if the `geo` script source ever widens beyond app-generated content.
- **Frontend suite flake watch items + the `frontend/dist` suite dependency —
  RESOLVED (2026-08-31, plan 54-E)**: LazyNoteEditor Suspense race, folder-cascade
  sqlite contention, and the chat-turn timing flakes are fixed by waiting on
  observables (SPA-independent test client, queue-drain waits, 15 s deadlines);
  a fresh worktree now runs the backend suite without `pnpm build`.
- **Desktop shell white screen (RESOLVED 2026-08-28)**: the SPA loads and runs
  inside WebKitGTK (server logs show index/assets/health all 200; a screenshot
  harness showed the DOM renders) but the user's window shows white. localStorage
  crash already guarded (`abec8bf` + boot error surface). **Root-caused and fixed
  (see changelog): the packaged builds' white screen was missing `gi.overrides`
  in the frozen bundle — pywebview's opacity fade-in threw
  `TypeError: Must be number, not method`, leaving the webview fully
  transparent.** Fixed via `collect_submodules('gi.overrides')` + system
  typelibs/schemas in the spec; pixel-probe now shows the UI painting in the
  frozen onedir and the rebuilt `.deb`/`.AppImage` smoke-test clean. Dev-mode
  white screens (recorded 2026-08-21…27) no longer reproduce on this machine
  today and were likely the same class of failure via different import-order
  timing; `pnpm webapp` remains the browser-first fallback.
- **WebKitGTK spike: PASSED** (user-verified 2026-08-18 on Linux Mint / snap VS Code
  terminal, after env sanitization).
- **Local embeddings (resolved, 2026-08-31 · landed 2026-09-01)**: ADR-011's
  sentence-transformers/bge-m3 clause is **superseded by ADR-105 (plan 48)** — no
  in-process ML models, ever; local embeddings = any OpenAI-compatible local server
  (Ollama `/v1/embeddings`, llama.cpp, LM Studio) via the existing `embeddings` task.
  Vector search degrades to FTS-only until the user assigns an embeddings model.
  **Plan 48 landed the discovery path (2026-09-01)**: local presets + detect-local +
  wizard wiring; the embeddings path was verified live against Ollama
  (`nomic-embed-text-v2-moe` → chunk vectors → hybrid search) and embeddings calls
  now write `ai_interactions` ledger rows (they had bypassed the ledger).
- **Golden fixtures need real material (user action)**: drop ~20 scanned math pages +
  ~10 worst handwriting photos into `backend/tests/fixtures/golden/{pages,handwriting}/`
  per its README (ADR-019: real scans, not synthetic). OCR golden evals (plan 04
  thresholds) are the last open Phase-1 item once fixtures land.
- **Flaky tests under parallel workers (observed 2026-08-28, twice)**: timing
  races in the async chat/job area — `test_select_hidden_subtree_restores_later_turns`
  (`tests/test_chat_branches.py`, `wait_until` 5 s deadline) and
  `test_failed_turn_emits_turn_error_and_fails_job` (`tests/test_chat_turn_error.py`,
  job row still `running` when asserted `failed` right after the WS `turn_error`
  event). Both pass reliably in isolation and file-runs; both race a DB commit
  against a polled/asserted observable. Fix properly: poll the DB (or wait on
  the runner's completion signal) instead of asserting immediately after the
  event, and/or extend the wait deadline.
- pnpm was bootstrapped via corepack on this machine; CI uses `pnpm/action-setup@v4`.
- Playwright e2e smoke is not scaffolded yet (not part of Phase 0 CI per roadmap; comes
  with first user flows).
- Bundle split landed (plan 17 G); entry 697 kB min / 192 kB gzip, vendor chunks
  cached. **Katex dedupe done (plan 22 I, 2026-08-21):** the direct dep was
  aligned to ^0.16 so the whole tree (rehype-katex/remark-math/mermaid/
  markmap-lib) resolves one katex@0.16.47 — the boot-loaded katex chunk dropped
  ~781 → 521 kB min (~260 kB saved); rendering verified by the block suites.
