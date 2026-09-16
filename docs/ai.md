# AI layer

Nothing is hardcoded to a vendor. Providers, models, and per-task assignment are
user-configured in **Settings**; Gemini is just one example. **Everything can run
fully local** — llama.cpp, LM Studio, Ollama and whisper-class servers are
presets, the wizard auto-detects running local engines, and API keys are optional
for local engines (ADR-105: no in-process ML models, ever). See
`docs/usage/local-ai.md`.

## Concepts

| Concept | Where | Notes |
|---|---|---|
| **Provider** | Settings → Providers | An account/endpoint: `google`, `openai_compatible` (covers OpenAI, Ollama, LM Studio, vLLM, OpenRouter, Groq…), or `anthropic`. Local presets: Ollama (`localhost:11434/v1`), llama.cpp (`localhost:8080/v1`), LM Studio (`localhost:1234/v1`) — all keyless; `GET /providers/detect-local` probes these ports (shape-validated, localhost-only) for the wizard/settings detection. API key → OS keyring only. |
| **Model** | Settings → Models | Auto-discovered from the provider (`/models` endpoints); capability heuristics (text/vision/tools/embeddings/audio/speech) pre-fill, always user-overridable; vanished models flagged `missing` so assignments aren't destroyed. `audio` is inferred for Whisper-class ids (`whisper`, `transcribe`) and every `gemini` model (audio input on `generateContent`); `speech` is inferred for TTS-class ids (`tts`, e.g. `tts-1`, `gpt-4o-mini-tts`, Gemini TTS previews). |
| **Task** | Settings → Tasks | Fixed registry (`app/ai/tasks.py`): `ocr`*, `notes_ocr`*, `description`, `outline`, `concepts`, `quizgen`, `exgen`, `tutor`, `grade`, `chat`, `flashcards`, `embeddings`, `transcribe`**, `tts`†. * = hard-requires a vision-capable model, ** = hard-requires a speech-to-text (audio) model, † = hard-requires a text-to-speech (speech) model (all enforced at assignment time, UI and API). Each task: assigned model + optional fallback, or **"(Inherit default)"** — a per-capability **default model** (`text`/`vision`/`embeddings`/`audio`/`speech`, `default_task_assignments`) supplies any task without a custom model (ADR-088); a custom model on a task is an override that shadows the default. |

### Per-course overrides (ADR-091/092)

Every generation call carries an optional `course_id` into the gateway. Model
resolution is a four-level per-slot chain (lowest → highest priority):

1. **global capability default** (`default_task_assignments`, ADR-088)
2. **global task assignment** (`task_assignments`)
3. **per-course capability default** (`course_default_task_assignments`, 0043) — set in the workspace root Settings tab's *Default models* card
4. **per-course task override** (`course_task_assignments`) — the Tasks list below it

Each slot (model / fallback) is resolved independently; an unset level never
blocks a lower one except by a higher level setting that slot. Threading covers
all course-scoped generators — quiz/exercise/flashcard generation, compose,
chat, tutor hints, rubric grading, drills, pattern discovery, outline,
organizer, concepts, note drafting/actions and material index cards — while
embeddings stay global (search infrastructure). Course deletion purges both
tables; deleting a model nulls it out of every row.

## Context engine (`app/services/context.py` — Phase 10A)

One resolver assembles **what any AI task sees**. A `ContextSpec`
(`course_id`, `node_id`, `scope: node|subtree|course`, `include/exclude_material_ids`,
`note_ids`, `concept_ids`, `hint`, retrieval query + budgets) resolves to a
`ContextBundle`:

- **Scope → material set**: direct links (node), subtree roll-up (subtree — the
  default; the course root degrades to unfiltered course scope), or whole course;
  include/exclude applied on top, all validated intra-course (422 otherwise).
- **Retrieval**: chunk-level **hybrid** search — FTS ranking RRF-fused with
  sqlite-vec chunk vectors when a query embedding exists (graceful FTS-only
  fallback). This fixed the pre-Phase-10 gap where chunk retrieval ignored
  embeddings entirely.
- **Manifest + prompt render**: numbered sections (study scope + objectives,
  AI instructions, materials with index-card summaries `[M#]`, focus concepts
  `[C#]`, attached notes `[N#]`, **structure in scope** — parent/siblings/
  current/children as `[T#] title (relation) — summary`, plan 72-E, cap 24 —
  and numbered source excerpts) with per-section budgets — one implementation
  shared by quizgen/exgen/flashcards.
- **AI hints**: `tree_nodes.ai_hint` (root = course-level guidance) is inherited
  from every ancestor of the scope node (most-specific last) plus the one-off
  `hint` from the request. Edited in the workspace overview.

`POST /ai/context/preview` returns the same bundle's stats + rendered prompt (no
LLM call) — this powers the generate dialog's "exactly what will be sent"
preview. Chat keeps its own context assembly for now (deferred slice 10E).

## Entity mentions (Phase 11A)

The manifest handles are a **two-way protocol**: the model may *use* the handles
in its output and the app resolves + renders them as clickable cards.

- **Registry** (`app/ai/mentions.py`): per-call from the bundle
  (`ContextBundle.mentions()` — materials `[M#]`, notes `[N#]`, concepts `[C#]`,
  scope node + children `[T#]`; `Q#`/`E#` reserved for quiz/exercise contexts).
  Handles are real ids, so they are stable. **Chat accumulates the registry over
  the session** (`chat_sessions.mention_registry`): a handle assigned once never
  changes meaning between turns; chat also offers the session's scoped material
  titles (cap 30) regardless of per-turn retrieval.
- **Parsing**: regex over model output; only registered handles resolve (stored
  on `chat_messages.mentions`; unknown/out-of-course handles stay literal text —
  never an error). Quiz explanations and exercise step/context blocks carry
  `mentions` on their text blocks; they surface in answer feedback and render as
  cards.
- **User attachments (composer "+")**: `POST /chat/sessions/{id}/messages`
  accepts `attachments: [{kind, id}]` (`material|note|quiz|exercise|node|course`,
  ≤10). The service resolves each to a registry entry (title + summary: index
  card for materials, note excerpt, question/step counts for quiz/exercises,
  description for courses — `course` maps to its root node as a `[T#]` ref),
  merges them into the **session registry** before the turn, and stores them on
  the user message (rendered as chips). The model-visible user turn gains an
  explicit "The student attached these items" line with the handles. Chat file
  uploads ride the normal material pipeline (upload → *Chat uploads* folder →
  ingest), so an uploaded file becomes a READable `[M#]` once processed.
- **Contract**: `mentions_in_range` is **advisory** in the chat contract —
  violations never block or repair, but are logged (`mentions_advisory` via
  structlog) as the rollout signal for tightening it later.
- **Frontend**: one `EntityMention` chip component (`features/ai/`) used
  everywhere — chat bubbles, block rendering (inline in markdown via
  `mention:`-protocol links + the standalone `mention` block type). Routing:
  M → library, N → note page, C → workspace concepts tab, T → node workspace,
  Q/E → runner/player.

## Chat on-demand context (Phase 11B)

Chat is now **manifest-first** and shares the Phase-10 context pipeline:

- Course-bound sessions build a `ContextSpec` (subtree scope at the session
  node, the user message as retrieval query) and resolve it through
  `ContextResolver` — so chat retrieval is the same **hybrid** FTS ⊕ sqlite-vec
  fusion as every other task (the FTS-only gap is closed), scoped to the
  session's subtree materials. 4–6 chunks still seed the prompt for grounding
  and citations. Unbound sessions call the hybrid retrieval directly.
- The prompt carries the **referenceable-items manifest** (registry with
  index-card summaries) *before* the sources: materials, notes, the scope node.
- **Course-structure block (plan 72-B)**: the prompt opens with the tree
  neighborhood of the attached node — a `Location:` breadcrumb, the parent
  node, siblings and children as `[T<id>] title — summary` entries (≤8 per
  group, summaries capped at 80 chars; course-level sessions list the root's
  chapters instead). All rendered nodes are **registered as `T#` handles**,
  so the model can READ neighbors and target them (tools, proposals) —
  placement questions ("would this fit better in a sibling?") are answerable
  without extra context.
- **`READ <handle>` tool**: deterministic fetch of an offered item's content
  (latest material extraction markdown / note body incl. drawing OCR / concept
  description / node summary+objectives **plus registered children and
  placed-material handles (plan 72-C)** / **quiz** title + questions with
  options and correct answers / **exercise** title + steps with expected
  answers), char-budgeted at 4k. READ has its own budget (**3 per turn**)
  separate from the 2 math-tool rounds; unknown or out-of-scope handles return
  an error line to the model instead of content. Materials that are still
  ingesting return a "still being processed" note (not recorded as a read).
  READ results are model-only — tool logs are never part of the stored answer;
  what was read is recorded per message (`chat_messages.reads`, migration
  0023) and shown as read indicators in the UI. `tool_round` stream events
  carry a `phase` (`read`/`math`/`mixed`) so the UI can say what is happening.
- **`STATE <widget_id>` tool**: deterministic read of an interactive widget's
  state the tutor showed earlier in the conversation (checklist/slider/choice/
  numberline/…), returned as JSON, model-only (never stored in the answer).
  State is written by `PATCH /chat/messages/{id}/state` (RFC-6902 JSON-Patch,
  the plan-34D `apply_patch` reducer) into `chat_messages.state`; STATE has its
  own 3-per-turn budget and an unknown-widget error line.
- **Tool doc single source**: the chat system prompt's tool documentation is
  generated from `CHAT_TOOL_CATALOG` (`build_tool_doc`), which also feeds
  `GET /ai/tools` — the prompt and the Tools dialog cannot drift.
- **Context panel** (`GET /chat/sessions/{id}/context`): session scope node,
  auto-context (latest-notes slot), and the accumulated mention registry —
  rendered as the collapsible "What the AI sees" panel in the chat sidebar.

## HITL proposals (Phase 11C)

The model may end a chat turn with **up to three** fenced action proposals
(plan 66 raised the cap from one; each is an independent row and card):

    ```proposal
    {"action": "create_note", "title": …, "body_md": …, "node_id": int|null}
    ```

- **Whitelist + validation** (`app/ai/proposals.py`): one pydantic schema per
  action, registered in `PROPOSAL_ACTIONS` (payload model + prompt grammar line
  + flags) — the system-prompt grammar is assembled from the registry, and a
  completeness test locks every action to an executor (`services/platform/
  proposal_actions.py` `EXECUTORS`) or an `api_executed` marker. The
  `proposal_valid` contract also checks `node_id` payloads against the
  session course's tree at proposal creation (plan 72-D; `prep.context`
  carries `course_node_ids`) — an invented node id triggers a repair round
  instead of an approve-time stale surprise. 11C2 adds
  `assign_material` {material_id, node_id}, `cover_concept`
  {concept_id, node_id}, `set_node_ai_hint` {node_id, hint}, `generate_quiz`
  {topic?, count, difficulty?, node_id?}, `generate_exercise`
  {topic?, steps, difficulty?, node_id?}. Plan 66 adds the content-edit
  actions `edit_note` {note_id, new_body_md, reason?} and `append_note`
  {note_id, markdown, heading?}: at proposal creation the server captures the
  target note's current markdown into the payload (`original_md`, via
  `capture_proposal_snapshot` — the model never supplies originals), the card
  renders the change as a formatted diff review (see below), and approve-time
  execution
  refuses when the note's current body no longer matches the snapshot
  (status `stale`). Edits/ appends go through `services/content/notes.py`
  `save_note_body` — the same versioned path the notes PATCH endpoint uses
  (`NoteVersion` rows, cause `ai-edit`). Plan 66 slice C extends the same
  pattern to materials: `edit_material` {material_id, new_markdown, reason?}
  and `append_material` {material_id, markdown, heading?} snapshot the latest
  extraction's markdown, execute through `MaterialsService.edit_extraction`
  (new extraction version + rechunk + FTS), enqueue a `postprocess` job, and
  the approve endpoint wakes the job runner. Slice D makes generation
  proposals context-aware: `generate_quiz`/`generate_exercise` payloads gain
  `material_ids`/`note_ids` (≤10 each), `instructions`, and quiz-only
  `question_types` (validated against the `QUESTION_TYPES` vocabulary, now
  single-sourced in `core/vocab.py`) + `shuffle`; the `proposal_valid`
  contract additionally cross-checks those id lists against the turn's
  offered mention refs (`validate_proposal_context` — unoffered ids trigger a
  repair round), and approve hands the full payload to the generator dialog
  which pre-seeds context materials, notes, instructions and quiz options.
  Slice E adds `generate_flashcards` {material_id?|note_id?, count} (open-dialog
  dispatch like the other generate actions; the card passes the source into the
  flashcards dialog), plus the create actions `create_material` {title,
  body_md, node_id?} — executed through `MaterialsService.create_text` +
  standard ingest + AI-proposal node link, previewed as markdown on the card —
  and `create_concept` {name, description?, node_id?} — idempotent
  concept-create + optional node coverage link. Slice F adds the `FIND` tool:
  course-scoped local search over materials (hybrid FTS/vector via
  `services/search/materials.hybrid_search`) and notes (`search_text` match),
  returning up to 10 titled handles that are registered into the mention
  registry so `READ` can fetch them — "find my notes on X, then READ" works in
  one turn. Budget 2/turn; wired into both engines and the degraded prompt
  grammar. Slice G extends the read tools: `NODE_CONCEPTS` (promoted from
  MCP-only), `NODE_FLASHCARDS` (counts + due fronts, never backs), and three
  course-scoped tools — `MISTAKES` (recent wrong answers + top error tags +
  active discovered patterns), `PLAN` (exam date, open plan items, overdue
  count, readiness via the shared `exam_status` reader with its honest
  not-enough-data state) and `DUE` (due-card overview). Resource tools gained
  a `course` argument kind resolved from the chat session; the MCP server
  exposes the same five additions. Plan 72-C adds **`NODE_MATERIALS`** to the
  chat toolset (materials placed at a node, direct links only in chat; the
  MCP server tool keeps the children variant) — results register `M#`
  handles so a follow-up `READ` opens the material. Slices H+I close the organize/planner
  gaps: `move_to_node` {kind: note|quiz|exercise|material, id, node_id}
  reuses the placement-node moves, `tag_note` {note_id, add[]} normalizes and
  merges tags, `set_exam_date` {exam_date} writes the course exam date,
  `generate_plan` executes the deterministic planner (refuses honestly when
  no exam date exists yet), and `add_plan_items` {items: [{title, due_date |
  days_ahead, kind}]} inserts manual plan items with kinds from the
  `PLAN_ITEM_KINDS` vocabulary. Payloads stay JSON-serializable
  (`model_dump_json` round-trip) so dates persist as ISO strings.
  At creation the server also enriches every diff/create payload with display
  info (`resolve_proposal_target` in `proposal_actions.py`):
  `target_kind` (note|material|concept), `target_name` (note title / material
  title / title-name), and — when the payload carries a course
  `node_id` — `target_node_id` + `target_node_path` (course-rooted title
  breadcrumb). The card renders this as a target row under the header so the
  user always sees **which file and which section** a proposal touches, and an
  executed material proposal links to `/library/$materialId` (result
  `material_id`). Diff reviews (`edit/append_note`, `edit/append_material`)
  render **formatted by default**: the library `MarkdownDiffView`
  (`markdown-diff-view` shim) compares markdown blocks and renders each through
  the chat-markdown surface, so math/headings/tables read as they will after
  approval; a Raw toggle switches to the source-precise `TextDiffView`.
  The `proposal_valid` contract
  constraint (blocking, course-bound chats only) checks fence count (≤3),
  JSON, action whitelist, and payload shape — violations trigger the normal
  repair loop; anything still invalid after repair is stripped from the stored
  message. Proposal blocks are removed from the stored markdown; the card is
  the UI.
- **Storage** (`chat_proposals`, migration 0024): message, action, payload,
  status `proposed|approved|dismissed|executed|stale`, result, timestamps.
  Surfaced on the messages API and the `assistant_message` WS event.
- **Execution is click-gated**: `POST /chat/proposals/{id}/approve` is the only
  path that executes — `create_note` places a real note through the same
  placement rules as the notes API (`TreeService.placement_node`), tagged
  `ai-proposal`, audited to `ai_interactions` (`context_type=proposal`).
  `assign_material`/`cover_concept`/`set_node_ai_hint` run through
  `services/proposal_actions.py` with **execute-time revalidation**: targets
  are re-checked against current state at click time; already-satisfied actions
  complete as `executed` with a no-op note; invalid targets (node deleted,
  cross-course id) mark the card **`stale`** with the reason — never a silent
  failure. `generate_quiz`/`generate_exercise` never auto-run: approve marks
  the card `approved` and returns `open_dialog` params; the UI opens the
  GenerateDialog **prefilled** — the Generate click inside the dialog is the
  real approval. Approve on a non-`proposed` card is a 409; execution never
  happens without the click. `POST /chat/proposals/{id}/dismiss` records
  dismissal; after **2 dismissals** in a session the system prompt gains a
  "the user dismissed earlier proposals" note (more conservative proposals).
- **Frontend**: `ProposalCard` (`features/ai/`) — status badge (incl. stale +
  its explanation), expandable payload preview, Approve/Dismiss with pending
  state, deep-link to the created note, "Open generator" for approved
  generate-* cards (mounts the shared GenerateDialog prefilled).

## AI-composed material (`material.compose` — Phase 11D)

New `material_compose` task (text-capable; seeded TaskAssignment + skill
`material.compose`). The AI writes **real study documents** — indexed,
searchable, citable, assignable, printable — not throwaway artifacts.

- **Pipeline** (`app/pipelines/compose.py` on `TaskRunner.run_text` — new
  markdown variant of the uniform runner with the same repair loop + audit):
  brief (kind, title, instructions, optional extra material) + a
  `ContextBundle` → markdown draft → deterministic validators (length
  400–60k chars, mention handles in range) → repair loop (2 rounds) →
  `MaterialsService.create_text` (`.md` material) → **standard ingest
  pipeline** (chunks/FTS/embeddings/index card — the material is queued like
  any upload) → auto-assign to the scope node with an "AI-composed" rationale.
- **Self-exclusion by construction**: `ContextSpec.exclude_ai_composed` —
  compositions resolve context with `provenance IS NULL` materials only, so a
  composition never grounds on a prior composition (compounding-hallucination
  guard). Chat retrieval keeps composed materials: they are your study docs.
- **Provenance** (`materials.provenance` JSON, migration 0025):
  `{source: "ai-composed", kind, model}` plus optional `coverage` and
  `needs_review` (plan 70-A, below) — surfaced on material payloads and
  rendered as the `AiBadge` in the library grid and workspace material rows.
  (Not-AI provenance sources exist too: `{source: "derived",
  from_material_id, from_version}` marks a user-triggered "Save as material"
  extraction copy — plan 26 — which carries no AI badge.)
- **Math lint is advisory + sampled**: up to 5 LaTeX spans per document are
  parse-checked (`parse_math`); failures are logged, never blocking.
- **Coverage accounting + `needs_review` gate (plan 70-A, ADR-157)**:
  retrieval coverage is measured deterministically — `ContextBundle.coverage`
  reports `{total, covered, missing_ids}` over the manifest's candidate
  materials (covered = ≥1 retrieved chunk carries the material's id; zero LLM
  involvement). When a scope holds **≥ 8 candidate materials** and the first
  round covers **< 50 %**, the resolver runs one **diversified second round**
  (query = node title + the node's concept names + first objectives; deduped
  by chunk id; total capped at `max_chunks × 2`) before giving up. Compose
  records the post-round coverage in `provenance.coverage` and the context
  audit stats, and sets `provenance["needs_review"] = true` when coverage is
  still < 50 % at ≥ 8 materials — the flag `formula_sheet` already used, now
  surfaced **generally**: the GenerateDialog result state names the shortfall
  ("Built from 8 of 14 materials — 6 weren't retrieved.") and shows a review
  warning whenever `needs_review` is set (finally giving formula_sheet's
  dormant flag a UI consumer). Regenerating with recovered coverage clears
  the stale flag; never LLM self-assessment (ADR-157).
- **Orphan-material awareness (plan 70-B)**: `ContextSpec.include_unassigned`
  (default off) merges course materials with **no placement anywhere** — the
  plan-75-C definition (`services/knowledge/placement.unassigned_materials`:
  ready material visible at no node by direct link and not a folder member) —
  into the node/subtree candidate set; course scope already includes
  everything and ignores the flag. `POST /materials/compose` accepts
  `include_unassigned`; the GenerateDialog's compose task queries
  `GET /courses/{id}/materials/unassigned` at node/subtree scope and shows an
  opt-in notice (checkbox off by default) with a link to the course Materials
  tab for placing them properly. Chat's `compose_material` proposal is
  untouched.
- **Kinds**: study guide, summary sheet, practice set, error recap, mindmap
  (a markdown outline rendered as an interactive, collapsible mindmap via
  `markmap` in `MindmapViewer`). Mindmap branches are selectable and open an
  `EntityActionMenu` (generate/ask/note/course-section/CRUD) — the selected node's
  label becomes the generation `topic` and an LLM hint carries the whole mindmap
  (capped) plus the selected node through `context_hint`. Every AI (or manual)
  mindmap edit saves a new extraction version — restorable from the viewer's
  History dialog (restore = one more version, never destructive).
- **`formula_sheet` (plan 22 H)**: deterministic collector first — math spans
  from course notes (incl. drawing OCR) and latest material extractions,
  whitespace-normalized dedupe, trivial arithmetic dropped, grouped by source
  node (cap 40/node); 422 when the course has no formulas yet. The LLM only
  organizes/titles/hints with copy-exactly rules; the output is then **stripped
  of any formula not in the collected set** (no invented formulas, guaranteed)
  and flagged `needs_review` in provenance when >20 % was stripped. Root
  study-launcher entry; one live sheet per course root (below).
- **`practice_set` through deterministic validators (plan 70-C, ADR-158)**:
  composing a practice set no longer trusts freeform markdown. The model
  authors **structured JSON items** (`stem_md`, `answer_kind`, `answer`,
  `choices?`, `solution_steps?`) restricted to the server-verifiable kinds
  (`single`, `multi`, `truefalse`, `numeric`, `equation` — client-executed
  kinds like `code` stay out), through `run_json` with the
  `PracticeSetOut` schema, the `material.compose_practice` skill (seeded;
  skills-version edits apply) and the same 2-round repair loop with validator
  feedback (exhaustion → `ComposeError` → 422). Validation is deterministic:
  the quizgen-derived answer-validation chain
  (`services/study/answer_validation.py` — shape/sanity per kind, distractor ≠
  answer via the SymPy equivalence chain, extracted mechanically so quizgen's
  golden-set contract is unchanged), plus stems non-empty, 1–30 items, and
  SymPy parseability for equation answers. Validated items render to the same
  markdown contract as before (numbered problems, **Answers** section at the
  end — the reader/ingest path is unchanged) and the structured items +
  per-item checks ride `provenance["practice_items"]` (free for future
  interactive practice; still no migration).
- **`cheat_sheet` / `node_review` (plan 22 J, ADR-051 — organizer artifacts)**:
  the Phase 8E organizer outputs persist as real materials with provenance
  kinds `cheat_sheet` / `node_review`. Cheat sheets follow the **one-live-artifact
  rule**; review reports are **dated** ("… — Review YYYY-MM-DD", same-day rerun
  updates that day's report — the trend is the value). `node_review` is
  **excluded from AI retrieval** (`RETRIEVAL_EXCLUDED_KINDS` — filtered from the
  materials manifest and chunk candidates in every scope branch) so meta-content
  ("no material covers X") never leaks into quiz/tutor context; cheat sheets
  participate normally.
- **`lesson` (plan 52-C, ADR-135 — course genesis)**: an **expository lesson**
  on the node's topic — definitions → explanation → worked example → common
  pitfalls, no fabricated citations. Unlike the revision kinds above, a
  lesson's **source is model knowledge**: the ContextSpec rides with whatever
  material the node already has (none at genesis time) and the prompt says so
  explicitly; retrieval posture is unchanged (`RETRIEVAL_EXCLUDED_KINDS`
  untouched — lessons are study content, quotable by the tutor). The
  one-live-artifact rule applies per (node, `lesson`); regenerating revises the
  user's edits via the `{existing}` revision slot. Genesis (plan 52-B) generates
  one lesson per depth-1 node through this kind.
- **One live artifact per (node, kind)**: `POST /materials/compose` looks for a
  material of the same kind at the placement node — found without `regenerate` →
  **409** (no silent duplicates); with `regenerate: true` → the output is saved
  as a **new extraction version on the same material** (restore history free)
  and the existing markdown — including the user's manual edits — is injected
  into the prompt as *revision context* ("revise, keep their valid additions").
  The GenerateDialog surfaces the existing artifact as a banner (Open existing /
  Regenerate). Same-node regenerate + one-live rule also governs the cheatsheet
  endpoint; `GET /nodes/{id}/artifacts` exposes the live sheet, review history
  and (with `?kind=`) any kind.
- **Entry points**: workspace overview "Compose study material" (GenerateDialog
  `compose` preset — kind selector, title, instructions, scope picker, context
  preview), the study launcher's kind grid, and the chat `compose_material`
  proposal (approve composes synchronously with the session's scope). A related
  deterministic sibling — the exercise-completion **session summary note** — lives
  on the exercise session endpoint (11E), not the LLM compose path.

**Rubric-graded exercise steps (plan 18 B3)**: free-form kinds (`explain`,
`error_spot`, `correct_solution`) run deterministic checks first (line picks,
exact fixes) and only fall through to the `grade.freeform` skill — verdict
(correct/partial/incorrect) + score + per-row rationale, validated and
audited like every task; the rationale is stored as step feedback and the
stage line is marked AI-graded.

`notes_ocr` (handwriting OCR) now also resolves through
`SkillService` (`notes.transcribe`) rather than a hardcoded prompt (11E).
The seed prompt is **extraction-only and subject-agnostic**: output exactly the text
written in the image (LaTeX for any math that is present, plain text otherwise, in
reading order), never describe the image, empty output when nothing is legible.
The page-OCR prompt (`ocr.page` / `ocr` task) uses the same conditional rule
("if the page contains mathematics, render it as LaTeX") — neither prompt assumes
the content is math. **(plan 74 C, ADR-176)** the OCR engine now *resolves*
this seeded skill — `SkillService.resolve("ocr.page")` once per ingest job,
threaded into `GatewayOcr` as the system prompt (same hardcoded text as the
seed as fallback; always win when a version is active), and the document
title is threaded as page `context` (`Transcribe this page. Document: {title}`).
Editing `ocr.page` in Settings changes page OCR; the notes/drawing paths
(`notes.transcribe`) are unchanged.

**OCR payload efficiency (plan 46, ADR-102)**: every image sent to a vision task
passes through `app/ocr/imaging.prepare_ocr_image` at the engine boundary — the
long edge is capped (profile preference `ocr_image_max_edge`: Off / 1024 /
**1568 default** / 2048 px, edited in Settings → Search & OCR) with a LANCZOS
downscale, then the image is re-encoded as flattened-RGB **WebP q85** (JPEG
fallback). It applies uniformly to drawings, quiz-answer recognition, uploaded
images and rasterized PDF pages; stored blobs keep their original quality, and a
decode/encode failure passes the original bytes through.

**Drawing OCR is a background job**: `POST/PUT …/drawings` and `…/reocr` save the
drawing, enqueue a `drawing_ocr` job and return immediately (no more blocking on
the vision model, no more 502s — failures are retriable jobs in the activity
rail). The handler transcribes from the stored PNG, bumps `ocr_version`, refreshes
note search text / material FTS and clears `ocr_job_id`; the UI shows a
"Transcribing…" placeholder and picks the transcript up over the `jobs:{id}` WS
topic. `ocr_job_id` is serialized only while its job is queued/running, so a
crashed backend can never leave a stuck pending state, and re-OCR returns 409
while a job is live.

**Material drawings (plan 29, ADR-064)**: text/markdown materials carry drawings
(`material_drawings`) referenced from the extraction markdown with
`![drawing](ca-drawing://{id})`. Their OCR text joins the material's FTS and is
appended to the **chunk source** in `edit_extraction`/ingest, so hybrid retrieval
(and therefore quiz/exercise/chat generation context) can quote handwriting in
materials exactly as it does for notes. The same `notes_ocr` engine transcribes
material-drawing PNGs through the material drawing endpoints.

## Course genesis (plan 52-B, ADR-135)

Topic → studyable course, scaffold-then-generate (never a one-shot blob):

1. **Draft** — `POST /courses/genesis/draft` (`{topic, level?, ground?}`, level ∈
   `school | university-intro | university-advanced`) runs the existing
   `outline` task (per-course/task model resolution) with the
   `course.genesis` system prompt and deterministic validators (shape, ≤2
   levels, ≤30 chapters × ≤15 sections, 1–3 one-line objectives per section,
   title/subject/goals normalization). No DB writes — the draft goes back to
   the dialog for review. With `ground: true` **and** a configured web search
   provider, three deterministic SEARCH queries (`<topic> overview / key
   concepts / curriculum`) feed titled excerpts into the outline prompt and the
   source URLs return on the draft; commit appends a
   "Drafted with sources: …" footer to the course description. Search
   failures degrade silently to an ungrounded draft.
2. **Review** — the `GenesisDialog` (step 2) lets the user edit course title
   and every chapter/section title before anything is created.
3. **Commit** — `POST /courses/genesis` (`{draft, lessons, quizzes,
   flashcards}`) creates the course (`origin=genesis`), a node per chapter and
   section (each node's `ai_hint` carries its objective — feeding every later
   AI task in the subtree), then estimates the task count =
   chapters × selected options and enforces the **budget cap** (profile
   preference `genesis_task_cap`, default 60; 422 over cap). Any selection
   enqueues one cancellable **`genesis` job** (`GenesisPayload`).
4. **Generate** — the `genesis` handler walks depth-1 nodes: `lesson` compose
   (model-knowledge teaching, ADR-135), a 5-question node-scoped quiz and 10
   flashcards (grounded in the lesson markdown when lessons ran). Progress is
   reported per task; **a failed task never blocks the others** (per-task
   try/except with rollback + failed-activity cleanup — all-failed fails the
   job, partial failure completes with the failures in the report stage line).

Everything genesis produces is normal, editable, provenance-tagged app content
(`ai-composed` lessons, ordinary quizzes/flashcards); the workspace keeps
prompting the user to add their own material.

## Task runner (`app/ai/runner.py` — Phase 10B)

Uniform invocation for structured generation tasks: `run_json(task, prompt,
validate, …)` and `run_text(…)` resolve the skill (course → course_type → system,
seeded fallback), run the repair loop with the caller's deterministic validator,
and write one app-level audit row (model label, `skill_version_id`, token
estimates, measured latency). Plan 31 added `stream_text(…)` — the same
repair-loop/audit semantics as a streaming generator that yields `delta`/`repair`
events and carries only the *last* round's text (plus an optional `stop()`
callable the consumer checks between chunks for cancellation).
Quizgen/exgen/flashcards run through it; their duplicated JSON
extraction / loop / audit / prompt-constant code is gone
(`app/ai/parsing.py` holds the shared extract/fence/blocks→markdown/token
helpers). Skill seeding is self-healing: when a seeded system template changes in code,
an **unmodified v1** in an existing DB is refreshed in place on startup/restore
(user-forked versions are never overwritten).

The seeded skill prompts are the single source — the pipeline-local
copies were deleted.

## Gateway (`app/ai/gateway.py`)

One entrypoint for all model calls. Resolves task → model → provider at call time
(edits apply instantly, no restart), reads the key from the keyring per call, and
speaks the provider families through **LangChain chat models** (plan 37A / ADR-081 —
`app/ai/chat_models.py`), behind an unchanged `LLMGateway` surface:

- **google** — `ChatGoogleGenerativeAI` (`generateContent` / `streamGenerateContent?alt=sse`)
- **openai_compatible** — `ChatOpenAI` (`chat/completions` + SSE streaming; also covers
  Ollama's `openai_compatible` preset and `embeddings`)
- **anthropic** — `ChatAnthropic` (`messages` with system + content blocks, SSE streaming)

Messages are typed (`system`/`user`/`assistant` with text or image parts); the gateway
maps them to LangChain message types per provider. Provider HTTP/transport failures are
wrapped in a typed `ProviderError` (status + body snippet + "check the API key in
Settings → Providers" hint on 401/403) and mapped to **502** by every in-request AI
route (quiz/exercise/flashcard generate, note actions, OCR, outline/concepts/organizer)
— never a raw 500. Transient failures (status ≥500/429 or an `httpx` cause) are
**retried** (2 attempts, exponential backoff; streams retry only before the first
chunk), and the task's `fallback_model_id` is tried next when the primary fails — the
`ai_interactions` ledger and chat trace are attributed to the model that actually
answered. **Resolution order (ADR-088):** a task's explicit `model_id`/`fallback_model_id`
win; any unset slot falls back to its capability's **default** (`default_task_assignments`
keyed by `requires`), so "inherit default" tasks resolve to the default and partial
overrides keep the default fallback. Token counts come from the provider's real
`usage_metadata` (the `len//4`
estimate is kept only for the offline/mock path). **Native tool calling (37B/ADR-082):** a
`tools`-capable model gets the chat tool schemas bound via `.bind_tools()` — schemas generated
from the same catalogs as the prompt — and the stream surfaces each complete structured call as
a `tool_call` event; the chat service runs the same deterministic tool implementations and
feeds results back as real `ToolMessage`s. Text-only/local models keep the prompt-line grammar
(`TOOL_LINE_RE`) unchanged. If a `tools`-capped model's endpoint rejects the bound-tools
payload, the turn **auto-degrades to the prompt grammar for that model** (remembered in-memory
per provider+model; the Settings `tools` override is the durable fix). A provider failure
before the first streamed chunk surfaces as a `turn_error` (frontend banner), never an empty
message. Models carry an optional **`reasoning_effort`** setting (Settings → Providers → edit
model) passed to `ChatOpenAI`/`ChatAnthropic`/`ChatGoogleGenerativeAI` — set `none` on OpenAI
reasoning models that reject `tools` to re-enable native function calling, or
`low/medium/high` (Anthropic: `max/xhigh/high/medium/low`; Google: `minimal/low/medium/high`)
to tune reasoning depth. Values are **filtered to the provider's accepted vocabulary** (38A):
an out-of-set value (e.g. Anthropic's `max` stored on a Gemini model) is dropped to the
provider default instead of failing model construction. **Structured generation (37C/ADR-083):** `generate_structured`
wraps `.with_structured_output()` (cap-gated on `tools`) as a fast path for the JSON-generating
tasks (quizgen/exgen/flashcards/rubric/pattern.discover) — permissive Pydantic schemas guide
shape, the deterministic validators still gate content, and any schema-unsupported error
degrades to the plain generate path. Since plan 38 it calls `.with_structured_output(include_raw=True)`
so the ledger bills **real `usage_metadata` tokens** (not `len//4` estimates) for structured
tasks, and it **pre-gates the fast path on the model profile**
(`model.profile["structured_output"]`): a profile that confidently says "unsupported" skips
the round trip and falls through to the next model, while unknown-profile endpoints keep the
error-based degrade as the safety net (38B/38C, ADR-086/087). **Prompt caching (37D/ADR-084):** the chat turn's
first system block (the invariant prefix) gets an Anthropic `cache_control` ephemeral hint and
OpenAI's automatic prefix caching is accounted via `input_token_details.cache_read`; the
`ai_interactions` ledger records `cached_input_tokens` (migration 0037) and discounts cached
input at 0.1×. **Query embeddings can be disabled** (Settings → Search global preference +
per-chat ✦ toggle in the chat header, migration 0039): when off, chat retrieval is FTS keyword
search only and the live query-embedding call is skipped (query text stays local). The suite
runs with sockets blocked (a conftest guard) so no test can touch the network.

## Chat-turn graph engine (`app/ai/graphs/` — family AI-alignment Phase 5)

The chat turn runs as **one engine**: the LangGraph chat-turn graph
(`app/ai/graphs/chat_turn.py`, ADR-0008 / family plan 10 Phase 5). The
former legacy loop and the `SA_CHAT_ENGINE` flag were removed in plan 72-A
(user decision: no legacy items); the graph engine is checkpointed:

    retrieve → contract_guard → agent_round ⇄ (tool rounds) → validate_repair → finalize

A custom StateGraph (not `create_agent`): the turn interleaves **two tool modes**
(native `.bind_tools()` plus the degraded prompt-line grammar, remembered
in-memory per model), per-kind budgets (math 2 / READ 3 / STATE 3 / resource 5
per turn), and the deterministic contract repair loop — none of which agent
middleware can host. Single-call tasks stay on `TaskRunner` by design.

- **Shared helpers, one home**: context assembly, contract selection, and
  persistence live in `ChatService.prepare_turn_context` /
  `prepare_turn_contract` / `finalize_turn`, called by the graph nodes —
  the external contract (WS events, proposal cards, message rows,
  `ai_interactions` ledger) is stable and pinned by the chat API/e2e tests.
- **Nodes call the gateway only** for model I/O; retrieval, deterministic
  tools, contracts, and persistence are plain code called from nodes. Node
  bodies run via `asyncio.to_thread` (LangGraph node timeouts require async
  nodes; the thread hop also preserves the callback context that feeds
  token streaming).
- **Streaming**: the adapter (`graphs/chat_turn_adapter.py`) consumes the raw
  stable streaming API `astream(stream_mode=["updates", "messages"])` on the
  app's event loop (integrator ruling 2026-09-04 — `astream_events(version=
  "v3")` is still beta on the pinned langgraph; swapping it in later is a
  one-file change confined to the adapter): `messages` tuples
  (`AIMessageChunk`, metadata) map onto throttled `stream_delta` WS events
   (tool lines filtered at round boundaries), text and reasoning in
   exact arrival order; `updates` flush the pending line at round boundaries
   and carry the `finalize` node's persisted event payload (emitted after the
   stream ends so deltas always precede it on the wire) plus the reserved
   `__interrupt__` mapping point for `interrupt()`-based proposals (today's
   proposals remain the fence protocol — external contract frozen).
   `stream_start`/`phase`/`tool_call` carry turn-semantic payloads with no
   LangGraph projection, so nodes emit them through the same `Emitter` the
   job handler wires. `thread_id` = chat session id.
- **Checkpointer** (dual-mode): dialect-picked in `graphs/checkpointer.py` —
  `AsyncSqliteSaver` on `data_dir/checkpoints.db` (desktop) or
  `AsyncPostgresSaver` (server mode, URI required). It is opened once in the
  app lifespan (never per request), `setup()` runs at boot, and boot-time
  pruning deletes threads whose latest checkpoint is older than
  `SA_CHECKPOINT_TTL_DAYS` (default 14) — checkpoints grow unboundedly
  otherwise. Checkpoint state is resumable runtime state only; chat messages
  stay in `app.db`.
- **Fault tolerance**: `set_node_defaults` layers a per-node hang-guard timeout
  and a retry policy that only retries raw transport leaks (`httpx.HTTPError`)
  over the gateway's own retries — `ProviderError` (already retried with
  fallback inside the gateway) is never double-retried. Failures bubble to the
  job handler, which emits `turn_error`.

## Family event vocabulary (Phase 6.2)

Chat turns emit the **family event vocabulary** additively alongside the
turn-semantic WS event names, on the same `chat:{session_id}` topic — one pure
mapper (`app/agui/family.py`), applied to every turn event: `stream_start` →
`flow_started` (flow `chat`, run_id, canonical
steps thinking/tools/answer) · `phase` → `node_started` · `tool_call` →
`node_finished` (`tool:{phase}` id, outcome + result detail) ·
`stream_delta` → `delta` (`kind: reasoning` when reasoning) ·
`assistant_message` → `flow_finished` (result ref = message id) ·
`turn_error` → `flow_failed` (retryable false). `stream_interrupted` has no
family equivalent and maps to nothing. Event names are the closed
`FlowEvent` StrEnum (`core/vocab.py`). The turn-semantic names stay the chat
panel's contract (its handler ignores unknown types); the family stream feeds
`FlowStatusCard` surfaces — adopted first in the shared editor's AI helper
(Phase 6.3), with `TraceTimeline` unchanged for the rich chat view.

## Features built on the gateway

| Feature | Task | Flow |
|---|---|---|
| **OCR** | `ocr` | Scanned PDFs rasterized (150 dpi) per page, images directly → markdown with LaTeX/tables/Mermaid; every image is first preprocessed (long-edge cap + WebP q85 re-encode, `ocr_image_max_edge` preference — ADR-102); failures mark the material `failed` with a clear message |
| **Index cards** | `description` | Post-ingest job fills summary/topics/key terms/difficulty; best-effort — never fails ingestion |
| **Embeddings** | `embeddings` | Chunks embedded (batches of 32) into sqlite-vec; hybrid search fuses BM25 + cosine via RRF(k=60); FTS-only fallback when unassigned |
| **Outline** | `outline` | Drafts a 2-level outline (policy, ADR-039) committed as depth-1/2 tree nodes + material allocation from index cards; server-side validation (ids exist/unique, counts clamped); **draft → review → commit** — never commits blindly |
| **Chat RAG** | `chat` | Course-scoped chunk retrieval → numbered sources → streamed answer with `[n]` citations; contract-validated with a repair loop. Sessions bound to an open quiz attempt ("ask about this question") run under the `no_answer_reveal` wrapper until that question is answered |
| **Quizgen** | `quizgen` | Blueprint → JSON questions → deterministic validators (metadata completeness, answer sanity, distractors ≠ answer via the equivalence chain; numberline answers validated as region payloads — domain bounds, interval ordering, at least one marker; table_fill grids validated per cell — alignment, kinds, parseable values, ≥1 fillable cell; composite parts validated per type with follow-through relations proven to parse, reference only prior parts, reproduce the declared value and survive a perturbed substitution; graph_read drafts validated as parseable expressions finite over the plotted domain with the expected reading **computed by the backend**, never the model;     code questions validated for 1–10 runnable test cases with a stored reference solution — executed only in the student's browser, never on the server) → repair loop (max 2). Context via the Phase-10 resolver (scope/material opt-in-out/notes/concepts/hints). **Difficulty targeting (51-H/ADR-125)**: when a concept/skill focus is set without an explicit difficulty, the generation target derives from the student's Elo rating for that cell (`rating → difficulty`), so focused practice adapts without config. The `numberline` (51-A/ADR-112), `table_fill` (51-F/ADR-123), `composite` (51-E/ADR-122), `graph_read` (51-G/ADR-124) and `code` (51-D/ADR-115) types let the model author richer answer surfaces whose grading and expected values are deterministic — the model authors the stimulus, never grades |
| **Exgen** | `exgen` | Multi-step exercise generation: JSON draft → validators (every expected answer parses via the chain, numeric tolerances sane, `expected_kind: numberline` answers validated as region payloads) → repair loop; refuses to persist an invalid exercise. Same pipeline powers **similar exercises** (isomorphic variant: same step structure, answers proven non-equivalent to the source), **error-pattern drills** (patterns resolve from the course type's `error_patterns` taxonomy (plan 28/ADR-063); since plan 51-C/ADR-114 drills are **error-spotting exercises**: both solution versions are returned and the chain proves exactly one line wrong — with detector-seeded flaws additionally matching `sign_slip`/`dropped_factor` transformations — before banking), and generated **error_spot** exercises under the same flaw-proof validators. Context via the resolver |
| **Pattern discovery** | `description` | Plan 28: `POST /exercises/drills/propose` digests the course's 30 most recent wrong answers + existing patterns → `pattern.discover` skill (contract-validated `{key, name, description, example}` proposals, max 5) → approve/dismiss HITL cards; approved rows become `error_patterns` (`source=discovered`). Detection of `sign_slip`/`dropped_factor` is deterministic (equivalence chain at grade time, no LLM) |
| **Tutor** | `tutor` | 5-level hint ladder under the leak-guard contract; audited per hint. P5b reuses the same machinery per quiz question (practice attempts only; exam mode refuses help server-side) |
| **Notes OCR** | `notes_ocr`* | Handwritten work (drawing canvas PNG) → extracts only the written text (LaTeX for any math present; plain text otherwise); no image descriptions. Strokes stay the source of truth, OCR is re-runnable per drawing with a version counter and can be skipped per save (toggle). **Runs as a background `drawing_ocr` job** (ADR-102): saving a drawing returns immediately, the transcript appears when the job finishes; failures are retriable activity-rail jobs. Also powers quiz-answer recognition (C18): `/quiz/recognize` returns candidates — the student confirms, only confirmed LaTeX is graded |
| **Flashcards** | `flashcards` | basic/cloze/reverse cards from notes (incl. OCR'd handwriting), material extractions, or the mistake notebook; validators (cloze deletion present, non-empty sides, duplicate fronts rejected) + repair loop; audited. Receives AI hints/notes as extra context (Phase 10) |
| **Note actions** | `description` | P9: summarize/cleanup/explain/expand a note (text + drawings' OCR) under a max-words contract; audited as `note_action` |
| **Note compose** | `description` | Post-1.0 (ADR-044): `POST /notes/compose` resolves the `ContextResolver` scope and writes a self-contained note via the `notes.compose` skill (max-words contract) — placed at the node, opened in the drawer; audited as `note_compose` |
| **Inline editor AI** | `editor_transform` | Plan 31 (ADR-068): the shared rich editor's ✨ `AiHelperPopover` calls `POST /ai/editor/transform` (transform presets explain/answer/compact/expand/rewrite/simplify/grammar/structure/bullets/markdown/translate or a free-form prompt; **Context** = selection + bounded surrounding doc text; **Course material** = optional grounding via the ContextResolver, node/course scope) → a job streams `editor_delta` on `ai-editor:{job_id}` (WS) with repair re-streams, cancel and a poll fallback. Contracts enforced by `TaskRunner`'s repair loop: no-preamble, ≤8k chars, compact ≤ input, answer needs a sentence, markdown fence/math balance. Audited as `editor_transform`. Results are transient — the user inserts them explicitly (replace selection / at cursor / insert below) |
| **AI block fixer** | `editor_transform` | Plan 64 (ADR-142): broken mermaid/math blocks in the editor get a ✨ **Fix with AI** affordance (failed-block fallback + both edit dialogs) backed by two new transform presets, `fix_mermaid`/`fix_math`, plus an additive `diagnostic` request field carrying the renderer's parse error into the prompt. Tier-0 is a deterministic repairer (`lib/mermaidRepair.ts` — quotes unquoted node labels containing parens/colons, the known extractor sin) that runs before the model and shows as an instant "Fixed without AI" proposal. The deterministic gate lives client-side: `mermaid.parse` / KaTeX `throwOnError` must accept the proposal or Apply stays disabled. A free-form ask box rides the same instruction channel — fix presets always keep their repair directive and append the user's request (`Additional user request: …`). Proposals review as a diff (`TextDiffView`) inside the block's own dialog; Apply writes the node attribute — nothing reaches the document without explicit user action. Repair-round streaming now resets the buffer on `editor_repair` (previously concatenated the failed attempt) |
| **Dictation (STT)** | `transcribe` | Plan 42 (ADR-097): the shared editor's 🎤 toolbar button and the chat composer's mic record a clip in the browser (`MediaRecorder`, webm/opus → ogg → mp4 fallback), then `POST /ai/transcribe` (multipart, ≤25 MB, optional ISO `language`) → `{text, model}`, inserted at the cursor/draft caret. Provider-native: `openai_compatible` → `POST {base}/audio/transcriptions` (Whisper-class, incl. local whisper.cpp/faster-whisper servers); `google` → `generateContent` inline audio guided by the `transcribe.audio` seed skill (verbatim transcript, dictated math as LaTeX); `anthropic` → unsupported. Sync endpoint (short clips; blocking call off the event loop), errors mapped 409 unassigned / 429 budget / 502 provider. Audio is **ephemeral** — never persisted, only the `ai_interactions` ledger row remains (prompt field carries `[audio N bytes mime]`). A live meter/timer/cancel strip shows recording state; same UI in the editor toolbar and the chat composer |
| **Read-aloud (TTS)** | `tts` | Plan 53-E (ADR-119): `POST /ai/speak` `{text ≤10k chars, voice?}` → ephemeral audio bytes (`audio/mpeg` / `audio/wav`) with the model label in `X-Speech-Model`. Provider-native: `openai_compatible` → `POST {base}/audio/speech` (mp3); `google` → `generateContent` with `responseModalities: ["AUDIO"]` + prebuilt voice (raw L16/PCM is wrapped in a WAV header server-side); `anthropic` → unsupported. Errors mapped 409 unassigned / 429 budget / 502 provider; audio is **never persisted** — only the `ai_interactions` ledger row (prompt field `[tts N chars]`). The frontend's zero-config fallback is the browser's `speechSynthesis` behind a **voice-availability gate** (`getVoices()` after the `voiceschanged` settle — API presence alone is not enough on WebKitGTK); the provider task is the quality option, resolved through the normal chain (task assignment → speech-capability default → course overrides) |

## Skills & prompt library (`app/services/skills.py` + `app/ai/skills/`)

Behavior is organized as **skills** (task → named behavior = Jinja templates +
contract), seeded from code and stored in `skills` / `skill_versions`
(DB is the live runtime source; code is the reset point). Resolution:
**course → course_type → system** (most specific wins). Templates render
server-side only. Every `ai_interactions` row logs `skill_version_id`, so any
prompt + contract + model + result is reproducible. The same contract validators
run in pipelines and the sandbox UI. See [usage/skills.md](usage/skills.md).

## Contracts engine (`app/ai/contracts/`)

Machine-checkable constraints on AI output, deterministic where required:

| Constraint | Enforces |
|---|---|
| `citation_if_context` | Retrieved material present → answer must carry `[n]` citations |
| `citations_in_range` | Citation indices must reference provided sources |
| `max_words` / `max_blocks` | Length budgets (hint budgets scale with ladder level) |
| `no_answer_reveal` | **Hint-leak guard** — see [math-verification.md](math-verification.md); also accepts `expected_candidates` and `forbidden_texts` (choice questions: the correct option may not be quoted verbatim) |

Violations trigger a repair loop (the violations are fed back to the model, max 2
rounds for quizgen/tutor, 1 for chat); unresolved quiz questions are flagged
`review` instead of entering play silently. Every AI call is logged to
`ai_interactions` (model, estimated tokens, latency, direction).

## Tools (chat math verification)

The chat system prompt teaches single-line tools the model may emit:

- `CALC <expr>` — sandboxed numeric evaluation (math-function namespace, empty
  builtins, dunder guard, non-finite rejected)
- `SYMPY <action> <expr>` — deterministic `solve | simplify | diff | integrate |
  expand | factor | limit` via SymPy (`x` as default variable)
- `STATE <widget_id>` — deterministic read of an interactive widget's state the
  tutor showed earlier (plan 34D), returned as JSON, model-only, 3-per-turn budget
- `PLOT <expr>` — deterministic plot of a function of x (plan 34F): SymPy
  `lambdify` sampling over [-10, 10] returns a compact plotly scatter JSON the
  model wraps in a ` ```chart ` fence to render an interactive chart.
- `SEARCH <query>` — web search over the configured provider (plan 52-D,
  ADR-136): Tavily-compatible `POST {base}/search` or SearXNG JSON API behind
  one adapter (`app/search/provider.py`, flavor preference + keyring key,
  Settings → Providers → Web search). Up to 5 titled results with URLs;
  2-per-turn budget. Unconfigured → an honest error line the model can relay.
- `FETCH <url>` — fetch a page as readable markdown via the plan-47 html
  converter (≤4000 chars, direct fetch not crawler, robots-unaware by design);
  1-per-turn budget.
- `QUIZ {...}` — quiz-me mode only (plan 53-C, **ADR-121**): the model passes
  the question + either `choices`+`expected_index` or
  `expected_latex`/`expected_text` (+ pre-authorized `accept` synonyms). The
  server stores the question as the session's pending quiz, renders an
  interactive card, and grades the student's answer **deterministically**
  (exact choice match / the math equivalence chain / normalized text + accept
  variants). The tool result and every prompt payload carry **no expected
  answer** — the model can't leak what it never sees. 2-per-turn budget.

SEARCH/FETCH excerpts are **model-only and never persisted** beyond the
message's `tool_calls` summary line (READ-tool precedent); the retrieved URLs
feed the **advisory** `sources_cited_when_search_used` contract — when a turn
used them but the answer cites none of the sources (URL or registrable domain),
the violation is logged (`validation.advisories`), never blocking. The frontend
renders SEARCH results as citation chips (source domains) on the tool card.

Tool lines are extracted, executed, results injected as a system message for the next
round (max 2 rounds), and stripped from the stored answer. Chat answers may also carry
fenced ` ```chart ` (plotly figure) and ` ```widget ` (`{widget,id,props}`) blocks —
`parse_answer_blocks` splits them into `chat_messages.blocks` so the frontend renders
charts and interactive widgets inline. The widget grammar (names + props) is
**single-sourced** in `app/ai/widgets.py` (`WIDGET_SPECS` → `build_widget_doc`); it is
injected into the chat system prompt (`CHAT_WIDGET_DOC`) and the exgen prompt
(`EXGEN_WIDGET_DOC`), so the model always knows every widget and its props and the
prompt cannot drift from the validator.

`GET /ai/tools` serves the machine-readable catalog of these chat tools
(`CHAT_TOOL_CATALOG` in `app/ai/tools.py`) and the MCP resource tools
(introspected live from the MCP server's registry — name, description, JSON-schema
arguments, scope). The chat panel's wrench button renders it as tool cards.

## MCP resource server (`python -m studyassistant mcp`)

Read-only **stdio** server (ADR-042 10E closed) exposing eight node-scoped tools
over the same services as the REST API: `list_courses`,
`get_node_overview/materials/concepts/exercises/quizzes/notes` (cheap
structured listings) and **`get_node_context`** — the deep one:
`get_node_context(node_id, scope='subtree', query?, max_chunks=12)` runs the
same `ContextResolver` the in-app AI uses (FTS-only — no embeddings dependency;
`query` triggers hybrid retrieval, capped at 500 chars) and returns the exact
budgeted manifest `POST /ai/context/preview` renders (materials with index-card
summaries, notes, concepts, ancestor hints, numbered excerpts), so external
agents see the same inspectable context as the app. Errors are surfaced as
resource errors (unknown node/scope, bad query length); no write tools exist by
construction.
