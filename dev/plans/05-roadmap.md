# 05 — Roadmap

Phases are vertical slices — each ends with something usable. Durations are deliberately
**not** calendar commitments (solo, part-time development; Phases 4–6 in particular ran
optimistic in early drafts). Treat phases as strict ordering, not dates.

**Milestone v0.1 (walking skeleton)** = end of Phase 4: ingest → outline → basic quiz →
chat RAG. It may not slip; P0 items outside it may slip one phase.

## Phase 0 — Skeleton & fixtures

Repo (uv/pnpm workspaces), FastAPI + SQLAlchemy + Alembic + settings + keyring, Vite React
TS + Tailwind + shadcn, **design tokens & base components per doc 09** (semantic palette,
light/dark, block-renderer skeleton), framer-motion, **i18n harness (react-i18next + `en`
catalog, no hardcoded strings allowed by lint)**, pywebview shell launching built SPA, WS
plumbing, CI (ruff, mypy, pytest, eslint, vitest), basic navigation shell.
**Also: collect eval fixtures now** — ~20 of your real scanned math pages + ~10 worst
handwriting photos (feeds the golden sets in plan 04; synthetic samples won't reproduce
real failure modes).

**Accept:** `python -m courseassistant` opens a window showing a React page served by the
Python backend; `GET /api/v1/health` green in CI; **WebKitGTK renders KaTeX + Mermaid +
MathLive + canvas correctly** (go/no-go for pywebview); fixture set committed under
`tests/fixtures/golden/`.

## Phase 1 — Ingestion core

Profiles schema (profile_id scoping on all user-content tables), blob store, materials +
groups, upload UI with job queue/progress, P1 ingestion graph:
PDF-text, PDF-OCR, images → OCR provider extractions (markdown/LaTeX/Mermaid/tables),
extraction viewer with side-by-side QA editing, index cards, chunk+embed+FTS.

**Accept:** drop a scanned 30-page math PDF and 10 whiteboard photos → searchable
extractions with equations & diagrams rendered; edit an extraction → search reflects it;
re-upload same file → cache hit, no extra cost; golden OCR fixtures pass thresholds.

## Phase 2 — Courses, structure, search

Course/chapter tree CRUD + DnD, hybrid search UI (results → material + page jump), P3
outline & allocation graph with review/commit flow, section views, read-status on
materials (B16 first cut).

**Accept:** from 20 mixed materials → AI outline drafted, edited, committed; each section
shows allocated materials with rationale.

## Phase 3 — Chatbot & retrieval validation *(moved before quiz engine by design)*

P7 chat RAG graph in the sidebar: sessions, streaming over WS, hybrid retrieval
course-scoped, SymPy/calc tools, citations resolving to material page/region. Cheapest
pipeline first — it hardens the retrieval layer on real material before quizgen and the
tutor (much harder to debug) are built on top of it. Auto-context starts with current
section + materials; mistake/notes context slots activate as those features land
(Phases 4/6).

**Accept:** chat answers cite materials with click-through to source page/region; claims
not grounded in material get the "not from your material" marker; usage logged per call.
Contracts engine + equivalence chain active in code from this phase (chat.answer,
no-math yet) — the same validators later guard quiz & tutor skills.

## Phase 4 — Quiz engine (→ **v0.1 complete**)

First cut: single choice, multi-select, true/false, type-in text + attempts + immediate
feedback → **v0.1 walking skeleton done**. Then: C2 math types (MathLive equation input,
numeric with units & tolerance), block rendering in stems, P4 quizgen with deterministic
validators + question bank (flag/regenerate), SymPy equivalence **chain (G9: simplify +
numeric sampling + solveset)** checking, mistake capture, quiz session report,
**help events (D10) audited on every answer**. P1 type wave starts here: cloze, match,
order, C16 composite (with follow-through), C17 essay/proof rubric path, C19 table_fill.

**Accept:** generated math quiz: ≥95% validator-pass rate; typed `2x` vs expected `x*2`
graded correct via SymPy; wrong answers get explanations; mistakes land in notebook;
v0.1 demo runs end-to-end (upload → outline → quiz → ask-the-tutor).
P1 type wave continues: C16 composite (follow-through credit), C17 essay/proof rubric
grading, C19 table completion. Quiz UX per doc 09: one-question-per-screen flow, instant
deterministic verdicts with streamed explanations, variety engine (H12), session summary
screen with mastery delta. **Question metadata + answer telemetry enforced from the first
generated question (H4b, doc 10 — tagged or not in the bank); score-page History tab +
basic overview ship with the first quizzes.** **caq/v1 single-file import (paste/upload)
with contract validation & preview + `.caq.json` export (doc 11, C22/C23) — validators
already exist, so external-AI-authored quizzes land here.**

## Phase 5 — Exercises & tutor

Exercise/session model, step inputs, P5 tutor graph (hint ladder, Socratic toggle, full
audit trail + independence score), **hint-leak guard G11 live from day one of the tutor**,
worked solutions, similar-exercise generator (D7), error-pattern drills (D8, seeded with
the calculus error taxonomy G10), **P5b quiz-question help** (C9b: practice-mode hint
ladder + "ask about this question" into chat, exam-mode refusal, chat no-answer wrapper).

**Accept:** multi-step calculus exercise; hint ladder walks from nudge to full solution
without skipping; every help event visible in the attempt transcript; isomorphic variant
generated on demand.

## Phase 6 — Notes, handwriting & flashcards

Tiptap notes (LaTeX/Mermaid/tables) attached everywhere, drawing canvas + P2 notes-OCR
(strokes kept), **C18 handwriting input mode on equation/numeric/text questions**
(type ⇄ write toggle, "interpreted as" chip, strokes stored on the answer — canvas
component shared with notes), flashcards P8 + FSRS scheduling + **Anki import/export**,
AI note actions, chat "latest notes" context slot activated.

**Accept:** handwrite a derivation → OCR to LaTeX blocks → "make flashcards" → FSRS queue;
import an existing .apkg deck into a course; **handwrite a quiz answer, confirm the
interpreted LaTeX, graded by the equivalence chain** (misread correction flow exercised).

## Phase 7 — Progress, polish, packaging

Mastery estimates + dashboard (streaks, heatmap, cost), weak-area sessions, study planner,
**Score page completion (doc 10): diagnostics — concepts×skills weakness matrix,
error-pattern profile, speed–accuracy; item analysis feeding bank flags; recommendations
v1 with evidence lines (read/drill/review/challenge) wired into Today & weak-area
sessions**, rollup materialization jobs,
**Today screen + daily goals + streaks + next-best-action (H10/H11/I21)**, **mastery
visualizations & milestone celebrations (I19/I20)**, backup/restore, onboarding + sample
course, settings (provider/model/task tabs, budgets,
**Ollama preset**), **profile switcher UI**, **linked material folders** (B15: source
registration, periodic mtime-first scanning, change detection → re-ingest versions,
missing-file handling), **PDF/print export** (I16), **Skills & prompt library UI** (doc 08: editor, test-run
sandbox, course types & overrides, versioning — contracts already code-enforced since
Phase 3), translation-readiness audit (missing keys check), **qpkg package import/export
with assets, watched import inbox directory + external-AI authoring kit (prompt builder,
schema card, agent-readable `schema.json`) — Anki import consolidated into the same
staged-import pipeline (doc 11)**, PyInstaller packaging.

**Accept:** v1.0 installable desktop app; full course lifecycle demo (upload → learn →
review → print) runs offline except OCR/LLM calls; Ollama chat mode functional; linked
folder update flows through to a new extraction version without manual re-upload.

*Remainder note (2026-08-19): command palette (I5) deferred to polish/backlog; Tiptap
notes upgrade moved into Phase 8C; golden OCR evals remain blocked on user fixtures;
section deep-link from search lands with the 8B routes.*

## Phase 8 — Course workspace & knowledge organization

User-approved restructure (2026-08-19; ADR-035/036 — 036 supersedes 034 same day).
Goal: the course stops being an outline editor and becomes the study surface —
materials owned per course and assigned at any scope within it, a per-chapter
workspace, notes as real study objects, and AI as the organizer. Slices are vertical
and shippable in order.

### 8A — Per-course materials & scoped assignment (backend) — **DONE (2026-08-19)**

Shipped as migration 0014 + services/APIs + Library scoping (see STATUS.md
changelog 2026-08-19 / ADR-036). Acceptance verified: upload requires a course;
assignment works at all three scopes intra-course; per-course folder trees;
"Unsorted" migration (incl. a dedicated legacy-data migration test); course
deletion purges the full tree. Library UI scoped; course-page picker scoped.

- `materials.course_id` becomes required (owner). Migration moves existing course-less
  materials + global folders into an auto-created "Unsorted" course (quick-assign UI;
  deletable once empty). New uploads require a course.
- Migrate `section_materials` → `material_links(owner_type: course|chapter|section,
  owner_id, material_id, rationale, auto_assigned, confidence)` — strictly
  intra-course; course-level and chapter-level assignment are new; sections keep
  working unchanged through the new table.
- `material_folders` gain `course_id` — per-course folder trees (course → folders →
  materials); the Library page scopes by the selected workspace course (ADR-033),
  "All courses" groups by course.
- Dedup stays per-course (today's behavior): same file re-uploaded to a course is a
  cache hit; the same file in two courses is two materials, one blob on disk.
- Delete semantics simplify: deleting a course offers to delete its materials (+
  folder tree); unlink ≠ delete stays.

**Accept:** upload requires a course; a material can be assigned at course, chapter,
and section scope of *its own* course; Library shows one folder tree per course;
legacy unassigned content lands in "Unsorted" and is assignable; course deletion
cleans up its tree.

### 8B — Course workspace UI (frontend) — **COMPLETE (2026-08-19)**

Slices 1–2 **DONE** — Nemo-style navigator (breadcrumbs over
`?course=&folder=`, grid default + persisted toggle, course-cards root, folder
context menu, status bar) + material detail page (`/library/$materialId`,
routable tabs, assigned-to chips via `GET /materials/{id}/links`, study-status
control; `unfiled` filter on listMaterials). SourcesPanel retained until L1.
Slice 3 **DONE** — course tabs (`?tab=outline|materials|notes`), chapter
workspace routes + `GET /chapters/{id}/workspace` (read-status pills, sections,
sub-chapters, notes sidebar, Quiz-me shortcut), open-workspace buttons in the
outline, materials grid → library links.

User decision (2026-08-19): the Library becomes a file-manager-style navigator
(modeled on Nemo/Cinnamon) and gains a dedicated material detail page.

- **Slice 1 (library)**: breadcrumb navigation (All courses ▸ course ▸ folders,
  URL-encoded `?course=&folder=`, deep-linkable), grid default + list toggle
  (localStorage), folders navigate in-pane, "All courses" root shows course cards,
  right-click context menu (open/rename/delete), toolbar (up, new folder, upload,
  search; search results replace the pane), item-count status bar, slim Places
  sidebar (course roots + linked sources). Backend support: `GET
  /materials/{id}/links` (owner titles for assignment chips) + `unfiled` filter
  for course-root listings.
- **Slice 2 (material detail)**: `/library/$materialId` — header (status, course
  chip, assigned-to chips, study-state), tabs Extraction | Original | Side-by-side
  (`?tab=`, routable). ExtractionView/OriginalView extracted into shared
  components.
- **Slice 3 (chapter workspace)**: `/courses/$id` tabs Outline/Materials/Notes;
  chapter routes with assigned materials, notes, scoped generate actions; reuses
  MaterialGrid/List/Picker from slice 1. Search deep-links into chapter views.

**Accept:** open a course → see every assigned document with scope badges; open a
chapter → materials + notes + sections in one workspace; assign a course doc at course
level in two clicks; no component duplicated between scopes.

### 8B slices 4–6 — Linked sources as symlink-style nodes (ADR-037, user 2026-08-19)

Model: five symlink laws — link is a tree node; navigation live via scandir (structure
never stored); content stays blob-copied (divergence); dangling honest; never write to
target. Explicit ingest for un-ingested files; unlink keeps materials (course root).

- **L1 (slice 4) — link nodes + live browse** — **DONE (2026-08-19)**: migration
  0015, browse/ingest/relink/reveal APIs, pane + item context menus, text-file
  creation, material rename/delete, server-side folder picker (`GET /fs/dirs`),
  SourcesPanel retired. See STATUS.md changelog.
- **L2 (slice 5) — reconciliation automation** — **DONE (2026-08-19)**:
  `ScanScheduler` (startup + periodic scan, `CA_SOURCE_SCAN_INTERVAL_SEC`,
  WS `source:{id}` events, per-source error isolation) + moved/renamed remap by
  content hash (`moved` stat; identity preserved).
- **L3 (slice 6) — robustness tail** — **DONE (2026-08-19)**: per-source
  `scan_interval_sec` (min 15 s, migration 0016), `last_scan_error`
  recording/surfacing, scheduler due-time logic, `POST /sources/scan-all`.

**Accept (L1):** link navigates like a folder showing the target's live contents;
new file visible immediately with pending badge → explicit ingest; target deleted →
dangling badge, materials still readable; unlink leaves materials at course root;
nothing ever written to the target.

### 8C — Notes as study objects

**DONE (2026-08-19)**: tags + cursor pagination + chapter notes index (8B-3) +
Tiptap rich editor with markdown round-trip (8C complete).

- Tiptap rich editing upgrade (absorbed from Phase 7 remainder): blocks stay canonical;
  LaTeX/Mermaid/tables first-class in the editor.
- Notes tags (json) + tag filter chips; paginated notes API (cursor on updated_at);
  per-chapter notes index/tree in the chapter workspace (derived from owner bindings).
- Note → material links surfaced in the workspace (owner_type=material already exists).

**Accept:** tag + filter a 150-note course without hitting the 100-row limit; chapter
workspace shows an organized notes index; edit a note with live LaTeX rendering.

### 8D — Concepts & knowledge graph (A9) — **DONE (2026-08-19)**

Migration 0018; concepts AI task; extract→review→commit with deterministic
validators; Concepts tab (graph list + draft review); concept_skill_stats
gained concept_id. Analytics dual-write + quiz-scope-by-concept remain future
work (concepts now real but question tags still carry the diagnostic axis).

- Build `concepts` / `concept_links` / `section_concepts` (planned in 03 since day one,
  never built); AI extraction pipeline (`concept` task) over linked material per chapter
  with deterministic validators (dedup against aliases, concept-count clamps).
- Interactive concept map view (concept relations + section coverage); concepts replace
  free-text tags as the analytics key over time (concept_skill_stats gains concept_id,
  dual-write transition).
- Quiz/exercise generation can scope by concept.

**Accept:** a course's material yields a browsable concept map; weakness matrix rows
link to concepts; regenerate quiz scoped to one concept.

### 8E — AI chapter organizer — **DONE (2026-08-19; Phase 8 complete)**

- "Review this chapter" action: coverage vs chapter/section titles, ordering suggestions,
  unlinked-material hints (gap analysis A10 first cut).
- Chapter cheat sheets (G6): auto-generated formula/summary sheet per chapter, printable
  (rides I16 print CSS).
- "Draft missing notes" per section from linked material (notes.action skill reuse,
  clearly AI-provenance-tagged, editable).
- All through the skills/contracts engine: audited, budgeted, repair loop — no new AI
  plumbing.

**Accept:** one click produces an honest chapter review (what's covered, what isn't);
cheat sheet exports to print; drafted notes are visibly AI-made and editable.

## Phase 9 — Unified node tree & uniform scoping (ADR-039, doc 12)

User decision (2026-08-19): chapters/sections collapse into **one `tree_nodes` table
per course** (≤4 node levels below the course = 5 layers; every course has an
undeletable root node = course level). All placement — quizzes, exercises, flashcards,
notes, material links, concept coverage, chat binding — becomes a single `node_id`
column with a composite FK that makes intra-course placement **database-enforced**
(replaces ADR-038's polymorphic scope before it shipped; supersedes ADR-035's 2-level
clause — outline AI still drafts 2 levels by policy). Ownership stays `course_id`
(ADR-036); concepts stay one course graph with per-node coverage. Materialized
`path`/`sort_path` give indexed subtree roll-up + depth-first ordering. Full design:
`12-uniform-scoping.md`.

- **9A** — **DONE (2026-08-19)**: migration 0019 + `services/tree.py` + node APIs +
  scoped params on every resource list/create + organizer/concepts/outline rewired +
  frontend migrated to the node APIs (recursive outline tree, NodeWorkspacePage,
  node-based concepts/organizer/links chips). 255 backend + 137 frontend tests;
  legacy-data migration test covers chapters/sections → nodes incl. sub-chapters.
  Node-scoped generation UI + route rename deferred to 9B.
- **9B** — **DONE (2026-08-19)**: unified **NodeWorkspace** — `/courses/$cid` (root)
  + `/courses/$cid/n/$nid` share one component; routable tabs
  Overview/Materials/Notes/Concepts/Practice/Cards/Tutor; breadcrumb + course
  accent; depth-aware Study-here; children-as-cards; scope chips; generate flows
  default to the node with a this-node/whole-course picker; palette node actions
  (depth ≤ 2); `/chapters/$nid` replace-redirects. Outline editor = the 9A recursive
  tree (DnD intact) embedded at root overview — **not** virtualized (TanStack
  Virtual deferred; personal scale doesn't need it). 144 frontend tests.
- **9C** — **DONE (2026-08-19, workspace-slice)**: per-node coverage management
  (cover/uncover toggles + add-coverage picker over the course graph) in the
  Concepts tab. Weakness-matrix/drill deep-links into workspaces still open.
- **9D** — **DONE (2026-08-19, workspace-slice)**: `listChatSessions?node_id=`,
  "Ask about this node" (header + tutor tab), node-bound session list in the Tutor
  tab (exact-node). Today recommendations → scoped sessions still open.
- **9E** — **DONE (2026-08-19)**: local read-only MCP server (official SDK 2.0,
  stdio via `python -m courseassistant mcp`); seven read-only node-scoped tools;
  e2e subprocess tests; mcp launch path never imports app.main (stdio purity).

**Accept (phase):** a student can place, generate, study, and ask about every
resource type at any hierarchy depth — one mechanism, one UI scaffold, one query
primitive, DB-enforced integrity.

## Phase 10 — AI task layer & context engine (ADR-042, doc 14)

User decision (2026-08-20): one uniform way to invoke AI generation tasks with
explicit, inspectable context — materials opt-in/out, context notes, concepts,
per-node AI hints — via a shared context resolver and task runner.

- **10A** — **DONE (2026-08-20)**: `services/context.py` (ContextSpec →
  ContextBundle; chunk-level hybrid retrieval fixing the embeddings-ignored
  gap; manifest + budgeted render) + `ai/parsing.py` shared helpers.
- **10B** — **DONE (2026-08-20)**: `ai/runner.py` TaskRunner; quizgen/exgen/
  flashcards migrated behavior-identical; duplicated loop/audit/prompt code
  deleted.
- **10C** — **DONE (2026-08-20)**: migration 0021 `tree_nodes.ai_hint`;
  context params on the generate endpoints; `POST /ai/context/preview`.
- **10D** — **DONE (2026-08-20)**: uniform `features/ai/GenerateDialog.tsx`
  (params + scope + opt-in/out + notes/concepts + hint + live preview) wired
  into Practice/Cards/Flashcards; `AiHintCard` in the workspace overview.
- **10E** — **DEFERRED**: chat context via the resolver + `read_item`
  on-demand tool; MCP resource server shares the resolver.

**Accept (phase):** every AI generation call goes through one context pipeline
the user can inspect and shape before it fires — no hidden context, no
per-pipeline prompt assembly.

## Phase 11 — AI-native companion: references, HITL cards, AI-composed material (ADR-043, doc 15)

User decision (2026-08-20): the AI references existing items with clickable entity
cards, proposes human-approved actions (HITL), and composes real indexed study
material — one protocol on the Phase-10 task layer. Mentions `[M#][N#][C#][T#]`
taught + parsed; chat goes manifest-first with a `READ` tool (10E lands here);
`chat_proposals` whitelist (create_note / assign_material / cover_concept /
set_node_ai_hint / generate-*=prefilled dialog / compose_material); new
`material.compose` task → real `.md` material through the standard ingest pipeline,
AI-badged and auto-assigned to the scope node. Plan: `15-ai-companion.md`.
**11A done (2026-08-20)** — registry/parser, migration 0022, session-stable chat
handles, explanation/step block mentions, advisory `mentions_in_range`,
`EntityMention`/`AiBadge` + inline BlockRenderer chips. **11B done (2026-08-20)** —
chat on ContextResolver (hybrid retrieval, manifest-first w/ summaries), READ tool
(own 3/turn budget, 4k chars, model-only), reads recorded (0023), tool doc from the
catalog (single source), context panel endpoint + UI. **11C1 done (2026-08-20)** —
proposal protocol + create_note whitelist + blocking proposal_valid contract,
migration 0024 chat_proposals, click-gated approve/dismiss + audit, ProposalCard UI.
**11C2 done (2026-08-20)** — assign/cover/hint actions with execute-time
revalidation (stale cards), generate-*=prefilled-dialog, dismissal feedback.
**11D done (2026-08-20)** — material_compose task + run_text runner variant +
compose pipeline (validators, self-exclusion, provenance 0025, auto-assign +
ingest), POST /materials/compose, GenerateDialog compose preset, chat proposal,
AiBadge. **11E done (2026-08-20)** — notes_ocr via SkillService, exercise session summary
note, Today ask-tutor, Tasks unassigned nudge; skills sandbox covers protocol by
construction. **Phase 11 complete.**

## Post-1.0 backlog (P2)

**Planned rounds (audit 2026-08-31, user-approved):**

- **Plan 47** — ingestion breadth: DOCX/PPTX/EPUB/HTML converters (B10) + lecture
  audio/video ingestion via the `transcribe` task (B13); unsupported uploads now 422
  at the door (ADR-103/104).
- **Plan 48** — local-first AI engines: llama.cpp / LM Studio presets, local-engine
  detection in onboarding, embeddings via OpenAI-compatible local servers; ADR-105
  supersedes ADR-011's sentence-transformers clause (no in-process ML models, ever).
- **Plan 49** — study experience: cross-course Review queue, `study_sessions` +
  focus timer (I18/H3/H10), server-enforced exam timing (C10) (ADR-106…108).
- **Plan 50** — `ca-course/v2` bundles (flashcards/FSRS, exam_date, import
  re-embeds), skill packs (J7), Playwright e2e smoke, OSS readiness (ADR-109…111).
- **Plan 51** — AI-native answer types: C21 number-line answers, G7 graph-sketch
  grading (keypoints v1), C20 error-spotting, C14 code-exec via Pyodide, **widened
  same day** with C16 composite (follow-through credit), C19 table-fill, C4/C5
  visual answers, C11 item-level Elo (ADR-112…125).
- **Plan 52** — topic explorer & course genesis: Scratchpad + promote-to-course
  (ADR-040 exception), topic → AI-scaffolded courses (lesson compose kind, seeded
  practice, budget gates), SEARCH/FETCH chat research tools with optional web
  grounding (ADR-116/117).
- **Plan 53** — planner & expression: study planner (H5) + exam-readiness forecast
  (H6), Quiz-me mode with server-side deterministic grading (F5), teach-back, TTS
  read-aloud (I14), print/PDF template engine (I16) (ADR-118…121).
- **Plan 54** — consolidation & hardening (**runs first**): cancel-on-purge +
  `cancelled` job status + commit-time stale checks (the deferred
  delete-during-ingest fix), mechanical splits of `lib/api.ts` / `domain/models.py`
  / `services/` behind stable import paths, flake-class hygiene (ADR-126/127).
- **Plan 55** — code quality & typed contracts (**after 54, before features**):
  StrEnum vocabularies over string matching (ADR-128), OpenAPI-generated frontend
  types + CI drift guard (ADR-129), typed service/API boundaries (ADR-130), shared
  constants, assistant-ui adoption round 2. No-comments rule reaffirmed.

Still unpulled backlog: local OCR adapter (superseded in practice by plan 48's
"local engines via openai_compatible" — a PaddleOCR adapter is only worth it if
vision-model OCR quality proves insufficient), Tauri shell migration (ADR-099
reaffirmed pywebview for v1.x), plugins (I11), snap-region-into-notes (E4) and the
PDF annotation layer (E9), material tags/favorites (A5 remainder), quick-capture
hotkey (I17), additional UI languages (Greek… — i18n plumbing ready, 1,700+ keys
per locale), collaboration/cloud, URL→material web importer,
constraint-solver scheduling/ICS/notifications, server-side PDF rendering,
graph-sketch freehand-curve recognition (plan 51 v2).

**Post-1.0 units shipped since this list was written:** plan 29 (2026-08-22,
ADR-064) — text/markdown materials own drawings (`material_drawings`, `ca-drawing://`
refs, editable in-app) + material **Export .md** with drawings embedded as images
(doc `29-material-drawings-and-md-export.md`).
