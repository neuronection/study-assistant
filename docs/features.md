# Feature catalog (as built)

P0/P1/P2 refer to the product plan (vision tiers). "—" means not started; see
`STATUS.md` for phase placement of the gaps.

## Ingestion & library

- ✅ Upload PDFs (text layer via PyMuPDF; scanned via OCR task), images, Markdown,
  plain text; content-hash dedup **per course** (re-upload to the same course =
  cache hit; the same file in two courses = two materials, one blob on disk) —
  B1/B2/B3/B8; **every material belongs to exactly one course (no global library,
  ADR-036; uploads require a course)** — Phase 8A
- ✅ Versioned extractions; originals kept forever in the content-addressed blob
  store; `GET /api/v1/blobs/{sha}` serves them — B4
- ✅ Side-by-side original ⇄ extraction QA editor (**rich Tiptap editor since
  plan 26 — tables, links and LaTeX math round-trip byte-identically behind the
  plan-23 fidelity guards; ADR-060 supersedes the old textarea**); saving
  creates a new version, re-chunks, re-syncs search, re-embeds — B7
- ✅ **Save as material** (plan 26, ADR-061): one explicit verb turns the
  QA-edited extraction into a standalone md material (provenance `derived`,
  own blob, standard ingest); it also lands where the original lives — the
  source's node assignments are copied and, when derived from a node
  workspace, the opened node is linked too (merged, no duplicates);
  content-hash dedup applies — an identical existing material is returned
  instead (`deduped`, left untouched); the original is never modified.
  **Drawings come along (plan 29, ADR-064): the derived material copies the
  source's drawings and remaps `ca-drawing://` ids so it is self-contained.**
- ✅ **Material drawings (plan 29, ADR-064)**: text/markdown materials own
  drawings exactly like notes — `material_drawings` + `ca-drawing://` refs in
  the extraction markdown. The extraction QA editor gets the **pen button**
  (shared `DrawingAdapter`), drawings render inline in the reading view, OCR
  joins search + AI context, and **Export .md** downloads the material with
  drawings embedded as base64 images (self-contained single file); strokes stay
  editable while the file lives in the app. The **new text/markdown file dialog
  has the pen too** — drawings buffer in memory (placeholder refs, data-URI
  previews) and are committed with the create (create material → POST drawings →
  remap refs → save extraction); nothing is created until the user clicks Create.
  **The dialog stays open after Create**: Save writes again without closing (new
  drawings committed by the next Save), Done closes it (2026-08-22).
- ✅ **Infinite drawing canvas (plan 43, ADR-098)**: the handwriting canvas is
  unbounded — **scroll zooms toward the cursor**, **middle-drag / Space-drag /
  hand tool pans**, and a floating bottom bar has zoom −/%, +, **Fit drawing**
  and **1:1** (actual size); the canvas dialog (note editor + chat drawing)
  toggles **fullscreen**. Saves are **cropped to the strokes' bounding box +
  small padding** and store the exported region as `view` metadata
  (`note_drawings`/`material_drawings`, 0046), so **re-editing restores the
  exact 100% scale** and notes render drawings at natural size instead of
  stretching them.
- ✅ Virtual folders — **one folder tree per course** (nested, rename/move/delete-
  reparent within the course); Library page scopes by the selected workspace course
  and shows course chips in "All courses" mode — Phase 8A
- ✅ LLM index cards (summary, topics, key terms, difficulty, reading time) — B5
- ✅ Hybrid search: FTS5 BM25 + sqlite-vec cosine fused with RRF; FTS-only fallback
  when embeddings unassigned — B6; **typo-tolerant fuzzy tier** (trigram index +
  per-token verification; `services/search/` engine shared by library search, command
  palette, notes search and AI/RAG retrieval) + optional `course_id` scoping
- ✅ Job queue with progress streamed over WebSocket — B8
- ✅ Linked material folders (B15) as **symlink-style folder nodes** (ADR-037,
  L1): stat-first scans → new extraction versions, missing-file handling, content
  copied into the blob store; a source appears in the course tree with live
  browsing (virtual subdirectories), pending badge + explicit per-file/all
  ingest, dangling-target detection with re-link, rescan + reveal-on-disk,
  unlink keeps materials — never writes to a target
- ✅ File-manager context menus: pane (paste / new folder / new text·md file /
  upload / add linked folder / new course), materials (open / cut / copy /
  assign-to-node / rename / delete with purge), folders (open / cut / paste-into /
  rename / delete), links (open / rescan / reveal / rename / unlink); inline
  rename on tiles
- ✅ **File-browser interaction grammar (plan 24, ADR-056/057 + ADR-059)**:
  click / Ctrl-toggle / Shift-range / rubber-band marquee selection in the
  library; **single click selects, double-click (or Enter) opens** everywhere
  the grammar applies (library pane, workspace tabs);
  cut/copy/paste + Ctrl+X/C/V/Delete/Esc; drag-to-folder **move** with a
  multi-id payload (`application/x-ca-item`); **duplicate material** (copy
  shares the blob, deep-copies the latest extraction + chunks + FTS + index
  card, re-queues embeddings, fresh study state, no node links, "… (copy)"
  title); **assign-to-node** dialog for material selections; the workspace tabs
  (Materials/Notes/Practice) get the same selection with **placement verbs** —
  bulk unassign/assign, bulk delete (trash-undo where snapshots exist) and
  **move-to-node** for notes/quizzes/exercises
- ✅ Inline text/Markdown file creation (`POST /materials/text`) through the
  normal ingest pipeline
- ✅ Native-style folder picker for link targets (manual path + server-side real
  filesystem browsing via `GET /fs/dirs`)
- ✅ **Interactive mindmaps** (plan 16/17): `mindmap`-kind extractions render as a
  pan/zoom `markmap` canvas (`MindmapCanvas`) instead of plain markdown; branches
  are selectable with a per-node action menu (ask / quiz / exercises /
  flashcards / study guide / write note / add-as-section / add child / edit /
  delete); the whole-map toolbar offers AI edit, **add root node**, **quiz/ask
  about the whole map**, and **History** — the extraction version list with a
  readonly preview and one-click **restore** (restore = new version, so it is
  itself undoable); the AI-edit preview shows the real interactive map
- ✅ **Unified material display (plan 17 A)**: one `MaterialRow`/`MaterialTile`/
  `MaterialList` family in `components/materials/` renders materials everywhere
  (library grid + list, workspace rows with drag/unassign, picker with
  assigned-lock and selection states, generate dialog) — status pill, read-state
  + progress, AI badge, rationale tooltip in one place
- ✅ **DOCX/PPTX/EPUB/HTML ingest (B10, plan 47)**: office/web documents convert
  to markdown extractions at ingest (headings/tables/links/images; slide +
  speaker-note fidelity for decks; spine order for EPUBs), embedded images get
  their own `material_images` rows with async `image_ocr` transcription joining
  search/AI context, and unsupported types are refused at upload (422) — plan
  47-A; audio/video (B13) lands with plan 47-D
- ✅ **Lecture audio/video ingest (B13, plan 47-D)**: `.mp3/.m4a/.wav/.ogg/.opus/.mpga`
  and `.webm/.mp4/.mpeg` recordings transcribe through the provider **transcribe**
  task into normal markdown materials (searchable, quotable, quiz-generatable)
  with a metadata header and `transcribed` provenance; duration/bitrate are read
  at upload (mutagen) and oversized recordings warn before the provider sees the
  bytes; re-ingest re-transcribes into a new version
- — Perceptual-hash image dedup (B9), preprocessing (B11),
  version diffing (B12), watched import inbox

## Courses & structure

- ✅ Course workspace selector in the nav rail (**2026-08-26 consolidation**): one
  **course hub** under a logo header (gradient mark + wordmark, links home) — a
  popover switcher ("Select a course" placeholder when nothing is picked; rows with
  color-letter tile, subject + material count; fuzzy search box when >5 courses;
  All-courses row inside the listbox; Courses footer link) whose entries set the
  current course **and open its workspace**, plus a 2×2 shortcut grid (**Workspace /
  Materials / Notes / Practice**, `?tab=` deep links with active state) when a course
  is active, and a compact Create-course CTA when none exist; the flat nav below is
  Home · Courses · Tutor · Library · Scores — scoping Flashcards/Scores lists +
  generation + chat sessions + diagnostics/recommendations; study pages show a
  create-course-first gate when no course exists — ADR-033
- ✅ **Course-required study content (ADR-040)**: every creation endpoint
  (notes, quiz/exercise/flashcard generate + create, drills, caq/qpkg/inbox
  imports, Anki import) requires a course — the frontend sends the workspace
  course, falls back to the single existing course, shows a required course
  picker in create/import dialogs, or an *open a course first* hint on one-click
  actions; legacy unbound content was migrated into a per-profile "Unsorted"
  course server-side
- ✅ Course CRUD; **unified node tree (9A)** — one `tree_nodes` tree per course
  (undeletable root = course level, ≤4 levels, merge-delete); reorder/move with
  reparenting — A1 (soft-delete/undo still missing); **deleting a course purges
  everything in it** (materials + extractions, folders, the node tree, notes,
  quizzes, exercises, flashcards, chat sessions, search index entries) — Phase 8A
- ✅ **Scoped material assignment (A13)**: a material can be assigned at course,
  any node of its own course (`material_links` on `node_id`; cross-course
  placement refused at the DB level); unlink ≠ delete; the tree carries node-level
  materials too — Phase 8A
- ✅ **Folder assignment (plan 25 / ADR-058)**: a library folder (virtual or
  linked-source) can be assigned to a node like a material — membership is
  resolved at read time (new files join automatically), flows into workspace/
  tree/AI context/organizer, unassign/delete guards keep it honest. Picker
  folder toggles, workspace badge + Assigned-folders strip, library
  *Assign folder to node…*, via-folder chips on material detail (2026-08-22)
- ✅ AI outline: draft from material index cards → review/edit → commit; allocations
  with rationale + confidence; manual assign/unassign via the catalog picker — A6/A7
- ✅ Read-status per profile (unread/reading/studied + progress) — B16
- ✅ **Unified NodeWorkspace (9B/9C/9D)**: one scaffold for the course root
  (`/courses/{id}`) and every node (`/courses/{id}/n/{nodeId}`, old `/chapters/`
  URLs redirect) — routable tabs Overview · Materials · Notes · Concepts · Practice ·
  Tutor · Settings (root only), underline-style with icons and live content counts (plus a due-cards badge on
  Practice); flashcards live in Practice's **Flashcards segment** (`?tab=cards`
  deep-links there); breadcrumb + course accent; depth-aware **Study here** (opens the
  **study launcher** — quiz, exercises, flashcards, study guide, summary sheet,
  practice set, error recap, mindmap, or write-a-note, each pre-scoped to the node)
  and **Ask about this node** (chat bound to the
  node, opened in the side panel); children as cards with quick actions; generation defaults to the current
  node with a this-node/whole-course picker; per-node concept coverage management;
  node-scoped tutor sessions; scope chips on placed rows; palette node actions;
  **structure sidebar** (collapsible whole-course tree with per-node content
  counts + study telemetry — progress ring for studied materials, due-card badge —
  current-node focus, auto-expand to the current node, expand/collapse all,
  virtualized above 40 visible rows, hidden below md + header toggle; persisted
  open/expanded state; fuzzy node filter; keyboard navigation; tree editing:
  right-click Add child/Rename/Delete with **undo toast** (snapshot restore),
  inline forms, **panel-wide right-click (non-row areas incl. chrome)
  targets the active node**,
  drag-to-reparent **with before/after/into drop edges**; the
  workspace **Overview action bar** hosts node creation on every node
  (**2026-08-23**: the root Structure card and the inner Subsections "Add child"
  button are retired — inner nodes get **Add child**, the root gets **AI outline +
  Add node**, inline title form below the bar; **2026-09-01**: a brand-new course
  root shows a three-step getting-started card instead of the action bar); material
  rows drag onto sidebar nodes to assign; **Study…** in the row's context menu
  opens the entity action menu scoped to that node — ask / quiz / exercises /
  flashcards / study guide / write note, with generation prefilled to the node
  and chat sessions bound to it); node **scope chips and
  assigned-to chips deep-link** into the node workspace; the
  embedded outline tree is retired — the root overview keeps a compact Structure
  card (AI outline + add node); material
  assignment via a **catalog picker** (folder-tree browsing, fuzzy filter,
  multi-select incl. whole-subfolder/linked-source ingest-and-select, batch assign)
  ("Quiz me on X", "Open X")
- ✅ **Practice lives where you explore (ADR-040/041 follow-up)**: no flat global
  Quiz/Exercises pages — the workspace **Practice tab** is the home for both
  (rolled-up node lists with scope chips, question counts, difficulty chips,
  quiz export/.qpkg/print rows, per-exercise *similar*, generate quiz/exercise
  with the this-node/whole-course picker, course-prebound quiz import dialog,
  error-pattern drills bound to the workspace course); full-page runner
  (`/quiz/{id}`) and player (`/exercises/{id}`) remain focus modes; `/quiz` +
  `/exercises` list URLs redirect to Courses; the command palette fuzzy-searches
  quiz/exercise titles straight into the runner/player
- ✅ **Outline tree: collapse + virtualization**: per-node chevron collapse on
  nodes with children; visible rows flatten depth-first and render plainly up to
  40 rows, above that `@tanstack/react-virtual` windows them (dynamic row
  measurement, DnD intact)
- ✅ **Notes live where you explore (ADR-040 follow-up)**: no flat global Notes
  page — the workspace Notes tab is the notes surface (search incl. OCR'd
  handwriting, tag filter chips, cursor pagination, node roll-up), note rows and
  create/draft actions open a **drawer editor over the workspace**
  (`?note=<id>` search param — back/X/backdrop close it) with a course▸node
  breadcrumb; a standalone full-page editor lives at `/note/{id}` (old `/notes/…`
  URLs redirect; `/notes` → Courses); the command palette fuzzy-searches note
  titles (`note: …` results) and its quick-note action opens the full-page editor
- ✅ **Concepts & knowledge graph (A9, Phase 8D)**: AI concept extraction from
  material index cards + outline → review → commit (validated); course Concepts
  tab with aliases, per-node coverage chips and relations; **per-node coverage
  management (9C)** — cover/uncover concepts at any node from its workspace
- ✅ **AI node organizer (A10 first cut, Phase 8E, node-based since 9A; reworked
  plan 22 J, ADR-051; plan 33, ADR-070)**: node Review with honest findings (gaps,
  ordering, orphaned material, missing coverage) — **persisted as dated `node_review`
  materials** (same-day reruns update that day's report; the Overview tab shows
  a clickable review history); one-page **cheat sheets persisted as materials**
  (AI badge, editable via extraction edit, node-linked) — the Overview **cheat-sheet
  button is a menu**: no sheet → *Generate cheat sheet…*, sheet exists → *Open
  existing* / *Regenerate cheat sheet…*, both opening the **compose builder
  pre-locked to cheat sheet** (materials/notes/concepts/instructions context
  controls, result previewed inline); AI-drafted node notes
  (tagged `ai-draft`, editable) with **find-existing dedup** (no duplicate per
  click). Organizer artifacts ride the **one-live-artifact rule**: cheat sheet
  regenerate = new extraction version on the same material with the current
  content (incl. manual edits) as revision context — generated via the compose
  pipeline (`POST /materials/compose kind=cheat_sheet`); the same rule guards the
  GenerateDialog compose kinds — an existing artifact at the placement node
  shows a banner (Open existing / Regenerate) and silent duplicates are
  refused with 409; `node_review` is excluded from AI retrieval (meta-content
  must not leak into quiz/tutor context) while cheat sheets participate
- ✅ **AI task layer & context engine (Phase 10)**: one uniform **generate dialog**
  for quiz/exercise/flashcards/practice — task parameters, scope picker (this node /
  node + children / whole course), **material context as removable chips**
  (in-scope materials included by default; *Add material…* / *Exclude from
  context…* open the library picker), **notes attached via a searchable note
  picker** (no checkbox lists — long lists never render), focus-concept selection,
  a one-time instruction field, and a live **context preview** ("exactly what will
  be sent" — no LLM call). Per-node
  **AI instructions** (`ai_hint`, editable in the workspace overview, root =
  course-level) are inherited down the tree into every AI task. Backend:
  ContextResolver (hybrid chunk retrieval, manifest, budgets) + TaskRunner
  (uniform skill resolution / repair loop / audit) — see ai.md
- — Course metadata beyond title/subject (A2), material groups (A4), favorites
  (A5)

## Quizzes

- ✅ Types: single, multi (partial credit), true/false, type-in text, numeric
  (tolerance), equation (MathLive input), **numberline (plan 51-A, ADR-112)** —
  C1/C2/C6 (block-format stems render markdown+math)
- ✅ **Number-line answers (C21, plan 51-A)**: the `numberline` question type and
  exercise-step kind answer by clicking/dragging on an interactive number line —
  place points, shade one or more intervals (open/closed endpoints toggled per
  end, draggable), replayed exactly after grading and carried in the attempt
  report for review. Grading is deterministic region math (`math/regions.py`):
  point tolerance, interval containment, boundary-kind strictness, Dice-style
  partial credit for partial shading (see math-verification.md). Generators may
  propose numberline questions (validators enforce the payload schema + domain
  bounds; repair loop); `caq/v1` round-trips them
- ✅ Generation: count/difficulty controls, course/node scope; deterministic
  validators enforce the full metadata taxonomy (concepts, skill, bloom, difficulty,
  expected time, misconceptions) — questions enter the bank tagged or flagged
  `review` — C7/C12/H4b
- ✅ Deterministic grading via the equivalence chain; distractors ≠ answer checked at
  generation — C8/G9
- ✅ Instant feedback with explanation; misconception tags land on wrong answers and
  the mistake notebook — C9/C13 (partial)
- ✅ Attempts (practice/exam modes server-side), finish, score, report — H2 (partial)
- ✅ Practice-mode per-question help (P5b): hint ladder levels 1–4 while the answer
  is open, level 5 (full solution) after submit; no-skip enforced; exam attempts
  refused help server-side; "ask about this question" opens a chat session bound to
  the attempt that runs under the no-answer-reveal wrapper until the question is
  answered; help events land on the answer transcript — C9b
- ✅ `caq/v1` export/import with dry-run validation preview — C22/C23 (single-file
  tier)
- ✅ `qpkg` package export/import: zip with sha256 manifest, integrity-checked,
  same validators — C22/C23 tier 2 (assets/ split form pending)
- ✅ **Course bundles (`ca-course/v1`, plan 22 F, ADR-050)**: `GET /courses/{id}/export`
  → zip (manifest + course.json + tree + concepts/links/coverage + materials w/
  latest extraction + index cards + node links + notes w/ drawings + quizzes +
  exercises incl. `card_*` kinds + course-scope skill overrides + content-addressed
  blobs); **never exports personal data** (attempts/answers/mistakes, analytics,
  chats, scheduling, read-status). `POST /courses/import` with `dry_run`
  validation preview (counts + warnings) then import-as-copy with full id
  remapping (tree paths rebuilt via TreeService, concept/question refs remapped,
  extractions written directly with chunks + FTS rebuild, no re-OCR; title
  collision → " (imported)"); Courses page: per-card **Export** link +
  **Import course** with confirm dialog → navigates to the new workspace;
  each course card also shows its **description** when one is set
- ✅ Single-artifact export (plan 22 F2): note **Print** (standalone page w/
  `?print=1` auto-print; global print CSS hides chrome) and **Export .md**
  (self-contained download — `ca-drawing://N` refs inlined as base64 data URIs)
- ✅ **Split-view study mode (plan 22 G)**: `SplitStudyPane` overlay — material
  (MaterialDetailBody tabs) left, `NoteEditor` right (rides autosave), drag
  divider persisted per course (30–70 %, `ca-study-split:{course}`), ≥lg only
  (drawer fallback below); URL-addressable `?material=<id>&study=<noteId|new>`
  on both workspace routes; **Take notes** in the material drawer/page header
  creates a note on the material's node; **Study alongside** on a note drawer
  picks a material (catalog picker, select mode) for the reverse direction;
  the **material/notes drawers expand to full width** (FocusShell toggle,
  persisted `ca-focus-fullscreen`);
  **selection → Quote-into-note bridge** (floating affordance on text
  selection in the reader → blockquote + `ca-material://` source link inserted
  at the tiptap cursor via `insertQuote` API)- ✅ Import inbox: watched-by-scan directory; files staged + validated, committed
  files renamed `.imported`, invalid → `.rejected` + error report; AUTHORING.md +
  schema.json written for agent self-service — doc 11
- ✅ "Author with AI" prompt builder: topic/count/types/difficulty → copyable
  prompt embedding the schema and every validator rule — doc 11 authoring kit
- ✅ Score page: History tab + mistake notebook — H2b first cut
- — Cloze/match/order (C3), composite follow-through (C16), essay rubrics (C17),
  table fill (C19), practice/exam UI differences (C10),
  adaptive difficulty (C11), item analysis (C15)

## Exercises & tutor

- ✅ LLM exercise generation (`exgen` task): topic/difficulty/step-count in, a
  validated multi-step exercise out — every expected answer parses via the
  equivalence chain or the draft is rejected — D1/D5
- ✅ Similar-exercise generator: isomorphic variants on demand (same step
  structure, answers proven non-equivalent to the source) — D7
- ✅ Error-pattern drills generalized (plan 28, ADR-063): patterns are DB-backed
  and course-type-scoped (`error_patterns`; G10 calculus taxonomy seeds under
  `math`), counts are scoped to the open course, `sign_slip`/`dropped_factor` are
  detected deterministically by the equivalence chain at grade time, and the AI
  proposes new patterns from recent wrong answers via approve/dismiss HITL cards
  (`pattern.discover`) — D8/G10
- ✅ **Error-spotting exercises, deterministic-first (C20, plan 51-C, ADR-114)**:
  drills are now proven `error_spot` exercises — the generator returns both the
  flawed and the fully-correct solution with per-line math answers, and
  validators prove via the equivalence chain that exactly one line is wrong
  (flawed ≢ correct at the flaw, every other line equivalent, both versions'
  answers parse) before anything is banked; when the pattern has a code detector
  (`sign_slip`/`dropped_factor`) the flawed answer must additionally carry
  exactly the detector's signature (negation / a seeded factor multiple) —
  ADR-114's deterministic-first seeding. Grading is deterministic: picking the
  flawed line is exact; drills require typing the corrected line's answer,
  graded by the equivalence chain against the true line (right pick + wrong/missing
  fix = incorrect with precise feedback; legacy pick-only responses still grade).
  The DrillsCard shows a per-pattern **spotted** count (correct picks on drills,
  tracked separately from your own mistakes); every error_spot generation —
  generic or drill — carries the same proof. Lines input gains the correction
  field (`requires_fix` on the step input) — C20
- ✅ Multi-step exercises with expected answers per step; session transcript
  endpoint (every answer + hint visible in order) — D1/D5/D10
- ✅ 5-level hint ladder (clarify → nudge → strategy → partial → full); levels never
  skip (server-enforced) — D2
- ✅ Hint-leak guard: deterministic answer-equivalence check on every hint below
  level 5, with repair loop — G11/D10 (audit trail kept)
- ✅ Socratic mode toggle (guiding questions) — D3
- ✅ Error classification per step (misread / procedural / conceptual) — D8 (taxonomy
  seed)
- ✅ Independence score per session — D4/D10
- ✅ Interactive widget blocks in exercises (plan 34, ADR-072/075): a generated
  step's prompt can carry a chart (Plotly), interactive geometry (JSXGraph), a
  checklist, slider, choice, equation input or numberline; the player renders them
  and submits their state, which lands on the step attempt — G3/G5/C5/C6 (partial)
- — Multiple solution paths (D9)

## Tutor chat

- ✅ Sidebar chat with saved sessions; token streaming over WS with live math
  rendering, animated thinking dots, auto-growing
  composer with starter prompts — F1
- ✅ **Tool-call cards (plan 34)**: every tool the tutor runs (`CALC`/`SYMPY`/`READ`/`STATE`/`PLOT`)
  appears as a collapsible card naming the tool and its argument — click to inspect the
  full argument and (for math) the exact result; persisted on the message so history
  shows it too — F4
- ✅ **Response trace & per-tool timing (plan 35)**: every answer shows how long the turn
  took, how many tools ran, and the model; expand a timeline of thinking/computing/reading/
  plotting/repairing phases and each tool call with its own duration, token counts, and
  (when the model exposes it) its reasoning — while streaming, a live status line shows the
  current phase and an elapsed timer; long math-heavy answers stream smoothly (no UI freeze)
- ✅ **Live thinking process (reasoning stream)**: when the model reasons out loud
  (OpenAI o-series `reasoning_content`, Claude extended thinking, Gemini `thought`), the inner
  stream appears in a collapsible **Thinking** bubble as it's generated — toggle it with the
  chevron (your choice is remembered), and it stays inspectable in the answer's trace
- ✅ **Browse your data in chat (plan 36)**: the tutor can list your courses and browse a
  node's quizzes, exercises and notes (`COURSES` / `NODE_OVERVIEW` / `NODE_QUIZZES` /
  `NODE_EXERCISES` / `NODE_NOTES`), read-only — the same tools external agents get via the
  MCP server (documented under Settings → MCP server)
- ✅ **Attach menu (+)**: reference courses, materials, notes, quizzes and
  exercises (fuzzy search) plus **file upload** through the chat (saved to the
  course library's *Chat uploads* folder and ingested); attachments become
  mention handles the tutor can READ — incl. full quiz/exercise content.
  Uploads are filed per conversation (`Chat uploads/<session> (#id)`, renamed
  with the session; drawings/screenshots enumerated per folder — uploading
  creates the chat if it doesn't exist yet). Quick actions above the tabs:
  equation editor, drawing canvas, screenshot crop (plan 40C); course-less
  chats resolve a fallback upload target — the **Unsorted** course, else the
  single active course (ADR-094 amendment) — and hide uploads/drawing/screenshot
  only when no course exists
- ✅ RAG over course-scoped material with `[n]` citations resolving to
  material/quote; "not from your material" marker on uncited answers — F3
  (hallucination guard first cut)
- ✅ Math tools (CALC + SYMPY) with verified results fed back — F4
- ✅ **Plot tool + interactive widgets (plan 34F)**: `PLOT` renders a deterministic
  chart in the chat (SymPy-sampled, not model-authored), and the tutor can hand the
  student a checklist/slider/choice/numberline (` ```widget ` fences) whose state is
  read back on the next turn via the `STATE` tool — G3/F4 (plot) + generative UI
- ✅ Full audit to `ai_interactions` — audit-all-AI principle
- ✅ **Dictation (plan 42/ADR-097)**: a 🎤 button in the composer records your
  voice (pulsing red strip with timer + live level meter; Cancel to discard),
  transcribes it through the speech-to-text model assigned to the `transcribe`
  task, and drops the text into the draft at the caret
- — Auto-context slots beyond course scope (F2 partial), modes (F5), region ask
  (F6), pin-to-notes (F7)

## Platform & engineering

- ✅ Desktop shell (`python -m studyassistant`), WebKitGTK validated; browser dev
  mode — I1
- ✅ Providers/models/tasks Settings with keyring keys, discovery, vision gating,
  presets incl. Ollama, and per-capability **default models** with per-task override
  (inherit-or-custom) — I3/I7 (wizard polish pending); **per-course task-model
  overrides** via the workspace root's Settings tab → Tasks subtab (course title +
  description in the General subtab) — ADR-091
- ✅ Light/dark/system theme; i18n harness with no-hardcoded-strings lint — I4/I8
- ✅ CI mirroring the full verification suites (ruff, mypy strict, pytest; eslint,
  tsc, vitest, build + migrations) — I13
- ✅ Translation-readiness audit: test scans all `t()` literals against the
  catalog (plural-aware) — I8
- ✅ Backup/restore (see Progress & analytics) — I6
- ✅ Onboarding: one-tap sample course with real, searchable material — I9 first cut
- ✅ Profiles in the schema from day 1 + switcher UI (create/switch in the rail;
  per-profile data via header scoping; delete-with-content refused) — A12
- ✅ English UI, all strings keyed — I8
- ✅ Skills & prompt library (doc 08): code-seeded system skills, editable in a
  full editor (Jinja templates, contract panel, scope picker, versions +
  activate/restore, sandbox test-run, export/import pack); resolved
  system→course-type→course; every ai_interactions row logs its skill_version
  for reproducibility — J5
- ✅ Packaging: PyInstaller bundle bundling the SPA, Debian `.deb` build and
  AppImage AppDir build — I23
- ✅ Command palette (I5 + plan 22 I1): Ctrl+K fuzzy-searches titles (notes,
  quizzes, exercises, courses, node actions) **plus a `?`-prefixed
  content mode** hitting the hybrid search API — snippet results deep-link to
  the material page
- ✅ **Job retry + task-activity rail button (2026-08-27)**: `GET /jobs` (+`/summary`,
  status/type filters) lists recent jobs with labels, errors and material ids;
  `POST /jobs/{id}/retry` and `POST /jobs/retry-failed` requeue failed jobs (only
  types with a registered handler; chat turns excluded). The rail's activity button
  shows a red failure badge, opens a panel with failed/active/done sections,
  per-item ⭯ retry, a **Retry all N** bulk action, live 2s polling while open —
  plus a full **`/jobs` page** (View all tasks): URL-persisted status tabs with
  counts (`?status=`), a type filter from `GET /jobs/types`, Completed/Started/
  Created sorting with direction toggle, status·stage chips showing where a job
  stopped, click-to-expand full errors and deep links to the failed material —
  see *Task activity* usage page. Library context menus gain **Re-ingest …
  (OCR again)** (single/multi, `POST /materials/{id}/reingest`) and **Retry failed
  AI tasks for this file** when that material has failed retriable jobs.
- — Onboarding wizard (I9 polish)

## Progress & analytics (Phase 7 — in progress)

- ✅ Today screen: streak, daily goal ring (editable goal), due-review count,
  next-best-action cards (review/drill/read/challenge) with evidence lines and
  one-tap actions, 90-day consistency heatmap — H10/H11/I21 first cut
- ✅ Diagnostics: concepts×skills weakness matrix (sample-size aware), error-pattern
  profile with 7-day trend, speed–accuracy quadrants — doc 10 §3.3
- ✅ Recommendations v1 with evidence lines (read/drill/review/challenge),
  exam attempts excluded from mastery signals — doc 10 §3.5/§5
- ✅ Item analysis: p-correct, avg-time ratio, distractor selection; n≥20 outliers
  auto-flag questions `review` — C15 first cut
- ✅ XP/level accrual (calm: numbers only, no dark patterns)
- ✅ Weak-area sessions: one tap on a drill/challenge recommendation generates a
  topic+skill-focused quiz (difficulty banded) and opens it — H4
- ✅ Backup/restore: full-archive zip (consistent DB snapshot + all originals +
  manifest), validated restore with migration replay — I6
- ✅ Automatic backups (plan 22 C): scheduler (startup run + every N hours,
  default 24), daily/weekly retention (14+8 default), post-write archive
  validation (integrity-checked before counted), **optional sync-folder copy**
  for off-machine redundancy, **boot integrity check with automatic recovery**
  from the newest valid backup (corrupt file quarantined, event surfaced in
  Settings → Data), Settings → Data card (toggle, interval, retention, sync
  picker, Back up now, list with restore-by-name/delete; runtime overrides in
  `backup-settings.json`, env defaults `SA_AUTO_BACKUP` etc.) — ADR-047
- ✅ Trash (plan 22 D, ADR-048): deleting a note/quiz/exercise/chat snapshots
  the full subtree (children, drawings w/ embedded PNGs, review history,
  attempts) into `deleted_items` (7-day TTL, purged at boot + on demand) —
  **Undo strip** on every trashed delete, Trash card in Settings → Data with
  restore (original ids, id-collision-safe remap) and delete-forever; course
  deletion refuses to run without `confirmed_backup` — the guarded path
  creates a fresh full backup before purging
- ✅ Print export via print CSS (quiz list) — I16 first cut
- ✅ **Exam planner v1 (plan 22 H1, migration 0029)**: per-course `exam_date`
  (course settings popover on the root; PATCH clears with null); `GET
  /analytics/exams` — courses with an exam ≤30 days out get countdown,
  engagement coverage (nodes with studied material, notes, quizzes or
  exercises / total), **pace line** (remaining ÷ days, off-track when >1.5
  nodes/day) and the first untouched node; **exam card on Today** with
  coverage bar, red when off track, one-tap jump into the most-behind node
- ✅ **Course formula sheet (plan 22 H2)**: `formula_sheet` compose kind —
  **deterministic collector** first (math spans from course notes incl.
  drawing OCR + latest material extractions, whitespace-normalized dedupe,
  trivial arithmetic dropped, grouped by source node, cap 40/node; 422 when
  the course has no formulas yet), LLM only organizes/titles/hints; output
  validated by **stripping every formula not in the collected set**
  (no invented formulas, guaranteed) with a `needs_review` provenance flag
  when >20 % was stripped; launched from the study launcher at the course
  root
- — Mastery rings/tree (I19/I20), confidence calibration (P2), exam coverage,
  cost dashboard (H7), CSV export (H9)

## Notes, handwriting, flashcards (Phase 6 — in progress)

- ✅ Notes: markdown+LaTeX notes (Tiptap rich editor) with live preview, pinned,
  attachable to courses; editing happens
  in-context (workspace drawer / standalone `/note/{id}` page) — see Courses &
  structure
- ✅ Crash-safe editing (plan 22 A): debounced autosave (1.5 s idle / 10 s max
  latency, 5 s retry on failure) with a truthful Unsaved/Saving…/Saved indicator;
  localStorage draft mirror + restore banner recovers text lost to a crash;
  closing/navigating away flushes pending edits; stale-write guard — a PATCH with
  `base_updated_at` older than the stored note returns 409 and the editor offers
  *reload theirs / keep mine*
- ✅ Note version history (plan 22 B, migration 0027): every body change snapshots
  the pre-write state **server-side, coalesced** (≥10 min apart unless
  `force_version`) — cap 50/note, causes *autosave / manual / restore*;
  History dialog with rendered preview, one-click Restore (itself undoable) and
  Save-version-now; versions cascade with the note
- ✅ Canvas v2 + **inline drawing blocks** (plan 22 E, ADR-049): DrawCanvas with
  pen/eraser (stroke-hit erase), 4 inks, 3 widths, undo/redo, guarded clear,
  pressure-sensitive widths, variable height (grows with content, DPR-aware);
  drawings embed **inside the note body** as `![drawing](ca-drawing://N)` —
  a tiptap image NodeView renders the PNG + collapsible OCR text with a
  per-drawing ⋯ menu (edit / run OCR again / copy OCR text); the canvas footer
  is [OCR toggle · default on] + Save-drawing, which inserts at the cursor;
  referenced drawings render only inline, cards below the editor are the
  fallback for unreferenced ones; body
  blocks gain `{"type":"drawing"}` (parsed/validated server-side, 422 on unknown
  ids); BlockRenderer `drawing` case (resolver prop); ContextResolver renders
  drawing OCR **in position** (fenced), unreferenced drawings appended
- ✅ Uniform entity actions on list rows: grid/list toggle, kebab + right-click
  Rename/Delete (shared `EntityItems` component with quizzes, exercises, chats
  and materials)
- ✅ Handwriting → markdown: draw on the canvas → subject-agnostic OCR (`notes_ocr`
  vision task, LaTeX for any math present) → editable markdown; strokes kept forever
  as the source of truth, OCR re-runnable with version counter —
  E3/E6 (first cut; menu + edit + toggle in plan 23 B; delete in the drawing menu 2026-08-22)
- ✅ Note search including OCR'd handwriting — E8 (first cut via search_text)
- ✅ Flashcards: basic/cloze/reverse; AI generation from notes / material /
  mistake notebook with validators + duplicate rejection; manual cards held to
  the same rules — E7 (generation half). **Storage is exercise-kinded since
  ADR-045**: cards are `card_*`-kind exercises (front = step prompt, back in
  `expected`), FSRS/review rows point at the exercise — one practice model
  under the hood; the flashcards UI/API surface is unchanged
- ✅ FSRS spaced repetition (FSRS-4.5, pure Python): due queue, Again/Hard/Good/
  Easy scheduling, full review log — E7 (scheduling half)
- ✅ Anki import (.apkg → cards, cloze detected, round-trip) and export
  (.apkg built from scratch, opens in Anki) — E7
- ✅ Handwriting input on quiz answers (C18): type ⇄ write toggle,
  "interpreted as" confirmation chips, strokes stored on the answer, graded by
  the equivalence chain — OCR proposes, the student confirms
- ✅ AI note actions: summarize / clean up / explain / expand (contract-bound,
  audited) — E5
- ✅ Chat auto-context: latest notes (incl. OCR'd handwriting) as background
  context — F2 (notes slot active)
- ✅ Rich-editor upgrade beyond notes (plan 26): extraction QA editing uses
  the shared Tiptap `MarkdownEditor` (tables/links/math guarded, ADR-060);
  the notes link-parse fix landed with it
- ✅ **Inline AI helper in the rich editor (plan 31, ADR-068)**: a ✨ toolbar
  button (in notes, the extraction QA editor and the new text/markdown file
  dialog) opens a popover with transform presets (explain / answer / compact /
  expand / rewrite / simplify / grammar / structure / bullets / format-as-
  markdown / translate), a free-form prompt box, a Context chip (selection +
  surrounding text) and a Course-material chip (grounds the prompt in the
  course), a streamed live preview with Stop, and human-gated insertion
  (replace selection / insert at cursor / insert below / regenerate / discard) —
  math, diagrams, tables and drawing refs survive insertion byte-faithfully; the
  popover is a **movable, resizable floating window** (grip bar to move, edge/
  corner handles to resize) that stays inside the app window so its buttons are
  never clipped
- ✅ **Dictation in the rich editor (plan 42/ADR-097)**: a 🎤 toolbar button
  (everywhere the shared editor appears — notes, extraction QA editor, new
  text/markdown file dialog) records a voice clip (timer + live level meter,
  Cancel to discard), transcribes it through the `transcribe` speech-to-text
  task, and inserts the text at the cursor
- — Pin-to-notes (F7)
