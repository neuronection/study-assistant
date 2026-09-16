# Feature catalog (as built)

P0/P1/P2 refer to the product plan (vision tiers). "—" means not started; see
`STATUS.md` for phase placement of the gaps.

## Ingestion & library

- ✅ Upload PDFs (text layer via PyMuPDF; scanned via OCR task), images, Markdown,
  plain text; content-hash dedup **per course** (re-upload to the same course =
  cache hit; the same file in two courses = two materials, one blob on disk) —
  B1/B2/B3/B8; **every material belongs to exactly one course (no global library,
  ADR-036; uploads require a course)** — Phase 8A; **uploads accept `node_id`**
  (assignment ride-along in the same request, dedupe hits still assigned — plan 75-A)
- ✅ Versioned extractions; originals kept forever in the content-addressed blob
  store; `GET /api/v1/blobs/{sha}` serves them — B4
- ✅ Side-by-side original ⇄ extraction QA editor (**rich Tiptap editor since
  plan 26 — tables, links and LaTeX math round-trip byte-identically behind the
  plan-23 fidelity guards; ADR-060 supersedes the old textarea**); saving
  creates a new version, re-chunks, re-syncs search, re-embeds — B7
- ✅ **Text-file viewer vocabulary (2026-09-05)**: text/Markdown materials open
  with **Formatted / Raw text / Description** tabs instead of
  Extraction/Original/Side-by-side (redundant for authored files) — Formatted
  is the rendered extraction, Raw text shows the markdown source, Description
  shows the material's **description** (new nullable `materials.description`,
  set at creation or via `PATCH /materials/{id}`). Edit mode splits into
  **Content / Description** tabs (Save persists both), and the new text/Markdown
  file dialog has the same tab pair
- ✅ **Save as material** (plan 26, ADR-061): one explicit verb turns the
  QA-edited extraction into a standalone md material (provenance `derived`,
  own blob, standard ingest); it also lands where the original lives — the
  source's node assignments are copied and, when derived from a node
  workspace, the opened node is linked too (merged, no duplicates);
  content-hash dedup applies — an identical existing material is returned
  instead (`deduped`, left untouched); the original is never modified.
  **Filesystem-style naming (plan 57): the derived material is named after
  its source (`report.pdf` → `report.md`) — the source's own title doesn't
  collide; any *other* material with the same name in the target folder does,
  and gets a zero-padded counter (`report_01.md`, `report_02.md`).**
  **Batch verb (plan 57): right-click one/many selected files in the Library
  or a node's Materials tab → Save as material / Save N as materials — one
  `POST /materials/derive` request, per-source outcomes (`created` / `deduped`
  / `skipped: no extraction`), sources without an extraction never block the
  batch; listings carry `has_extraction` so the menu item gates precisely.**
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
  upload / add linked folder / new course), materials (open / linked
  locations / cut / copy / assign-to-node / rename / delete with purge),
  folders (open / cut / paste-into / linked locations / rename / delete),
  links (open / rescan / reveal / rename / unlink); inline rename on tiles
- ✅ **In-tab folder browsing (plan 76, ADRs 181–183, 2026-09-15)**: the course
  Materials tab drills into folders in place via `?tab=materials&folder=<id>`
  (back/forward + deep links), showing the folder's **full contents** —
  subfolders + materials from the standard library endpoints (shared
  `MaterialBrowser` component with the Library), breadcrumbs with a Materials
  root crumb, honest stale-id fallback, drawer opening for folder materials,
  and Open / Open-in-library / Assign-to-node menus; linked-source folders
  browse over `browseSource` with subdirectory state, one-click ingest of
  pending files, and an "Open in library" crumb-row button in every browse mode
- ✅ **Needs placement (plan 75-C, 2026-09-15)**: `GET
  /courses/{id}/materials/unassigned` lists ready course materials visible at
  no node (direct link absent **and** not a member of any linked folder; cap
  40) — the course Materials tab shows a collapsible "Needs placement" strip
  and the Library course view lists them, each with an Assign… action reusing
  the node picker; the unassigned helper (plan 70-B amend: via-folder counts
  as placed) is the shared compose wiring per plan 70-B's coordination note
- ✅ **Placement suggestions (plan 75-D, ADR-179, 2026-09-15)**: deterministic
  suggest-for-all in the needs-placement panel — `POST
  /courses/{id}/placement-suggestions` ranks candidate nodes by token
  overlap (material title + index-card topics/key-terms vs node
  titles/summaries/objectives/concepts; Jaccard + containment bonus, ≤3
  candidates each), renders evidence chips (`matched_on` tokens as tooltip)
  and places only on click — no LLM, works offline
- ✅ **Placement references (plan 71, ADR-159)**: library items show a small
  `Link2`+count badge when placed in the course tree (materials: direct
  `material_links` only; folders: the folder's own `material_folder_links`) —
  counts ride the list responses (`MaterialOut.link_count`,
  `FolderOut.node_link_count`, one grouped query each); right-click
  **Linked locations** (single selection) opens a read-only dialog listing
  each placement with breadcrumb, Auto/via-folder chips and rationale,
  deduped by node (direct wins), rows navigating to the node workspace;
  folders expose `GET /folders/{id}/links` (mirrors the material endpoint;
  the whole-subtree view stays in `delete-info`)
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

- ✅ **Material tags & ⭐ favorites (plan 67-D, ADR-149, migration 0057)**:
  tag chips (add/remove inline) and a star toggle on the material header; the
  Library gains a starred-only filter, tag filter chips and **Star/Unstar in
  the material context menu** (single + multi-select); both fields round-trip
  in course bundles
- ✅ **Import from URL (plan 67-E, ADR-150)**: paste a page URL (Library
  "New…" menu or command palette) → it is fetched, converted to markdown with
  a provenance header, and lands as a standard searchable/READ-able material
  in the chosen course — with optional node assignment and an honest error
  when the page is unreachable

## Courses & structure

- ✅ **Folder→node mirroring (plan 75-B, 2026-09-15)**: a library folder tree
  becomes a node subtree — `POST /nodes/{id}/mirror-folder` reuses
  title-matched child nodes (case-insensitive, idempotent reruns) or creates
  them, folder-links each mirrored folder (its files attach implicitly,
  including files added later), caps at node depth 4 and reports deeper
  levels as `skipped_folders`; NodeWorkspace materials-tab folder menu
  "Mirror folder structure into nodes" shows created/reused + skipped counts
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
- ✅ **Scratchpad + Promote-to-course (plan 52-A, ADR-134, 2026-09-06)**: a
  per-profile hidden `origin=scratch` course (0053) is the home for
  exploration — notes, files, chat uploads and tutor chats work in it, hidden
  from the Courses page/rail until it has content (Home "Explore a topic"
  card), and excluded from exam forecasts and profile-wide recommendations
  (streaks still count). Right-clicking a scratch node offers **Promote to
  course…**: the subtree (nodes, notes, files, chat bindings) moves into a new
  real course, scratch-exclusive content moves with it, concept coverage is
  honestly dropped
- ✅ **Course genesis (plan 52-B, ADR-135, 2026-09-06)**: Home **Generate a
  course from a topic** → three-step dialog (topic+level → editable 2-level
  outline → generation options). `POST /courses/genesis/draft` drafts via the
  `outline` task with deterministic validators; `POST /courses/genesis` creates
  the course (`origin=genesis`, node `ai_hint` = objectives), enforces the
  genesis task budget (`genesis_task_cap` profile preference, default 60) and
  enqueues one cancellable **`genesis` job** that generates per chapter:
  `lesson` compose + 5-question quiz + 10 flashcards, per-task failure
  isolation (a failed task never blocks the rest)
- ✅ **`lesson` compose kind (plan 52-C, ADR-135)**: expository lesson
  (definitions → explanation → worked example → pitfalls) teaching from model
  knowledge when the node has no material; one-live-artifact per node,
  revision-aware regeneration that keeps the user's edits; also selectable in
  the compose builder like any other kind
- ✅ **Compose coverage honesty (plan 70-A, ADR-157, 2026-09-16)**: AI-composed
  documents now report how much of the scope's material they actually drew on —
  deterministic coverage accounting over the retrieval manifest (≥ 8 materials
  with < 50 % covered triggers one diversified second retrieval round before
  giving up), recorded in the material's provenance; the GenerateDialog result
  names the shortfall ("Built from 8 of 14 materials — 6 weren't retrieved.")
  and shows a review warning when coverage stays thin (`needs_review` — also
  finally surfaced for formula sheets); regenerating with better coverage
  clears the flag
- ✅ **Compose orphan-material awareness (plan 70-B, 2026-09-16)**: the compose
  builder (node/subtree scope) lists unplaced course materials ("N materials
  in this course are not placed at any topic yet.") with an opt-in checkbox to
  also draw on them (`include_unassigned`, default off) and a link to the
  course Materials tab for placing them; the coverage note includes them when
  checked
- ✅ **Validated practice sets (plan 70-C, ADR-158, 2026-09-16)**: composed
  practice sets are now authored as structured items and **every answer is
  checked server-side before saving** (SymPy equivalence for equations,
  distractors can't duplicate the answer, numeric values must parse — the
  quizgen validation machinery, extracted and shared); broken generations are
  repaired or refused (422), never saved with a provably wrong key. The
  document reads exactly as before (problems + answers section), and the
  structured items are stored in the material's provenance for future
  interactive practice
- ✅ **Custom MCP connectors (plan 73-G, ADR-170, 2026-09-16)**: bring your
  own source. Register an external MCP server (stdio) in **Settings →
  Integrations**, refresh to list its tools, and assign each tool a
  contract: **Discovery** tools appear as providers in the Discover dialog
  and behind chat DISCOVER; **Parser** tools (keyed by a URL pattern like
  `coursera.org/learn/*`) work inside Import & parse like any built-in
  parser. Servers launch on demand with per-call timeouts, stay disabled
  until you explicitly enable tools, every invocation is audited, all
  external output is validated app-side (invalid rows dropped, contract
  violations fail honestly), and per-server errors show right on the card
  — never a silent empty result
- ✅ **Chat discovery & attach proposals (plan 73-F, ADR-167/170,
  2026-09-16)**: ask the chatbot to "find me a video on integration by parts"
  — the new **DISCOVER** tool searches across web, YouTube and site presets
  (with per-result provider badges) and can even be invoked as
  **`DISCOVER here`** to search for the current chapter/topic without typing
  a query (built deterministically from the node's title, summary, hint and
  concepts; falls back to the course, and is honestly refused when there is
  no course context). Results appear as citation chips — never saved or
  imported on their own. When the model finds something worth keeping it can
  propose **attach_link** {url, title, node}: approving creates a real link
  reference at the chosen topic (deduped on the normalized URL), previewed on
  the proposal card — approval is the only path from chat to material
- ✅ **External web sources (plan 73-E, ADR-167/170, 2026-09-16)**: standing
  web sources that surface new material on their own — **RSS/Atom feeds**
  (feedparser over httpx with etag/last-modified resume), **YouTube channels
  and playlists** (yt-dlp flat extract, no downloads) and **site-filtered
  searches** (the slice-C search provider with a `site:` filter) — scanned on
  a schedule (per source, 15-minute politeness floor, 6 h default) by a
  deterministic scheduler: every new item lands as a **suggestion** in the
  Discover dialog (never a material, never auto-imported, zero LLM calls);
  a URL already saved or dismissed is never re-surfaced. Per-source enable
  toggle, manual **Scan now**, honest error badges (a dead feed shows its
  last error), overlap guard so slow scans never stack, and untrusted
  feed/yt-dlp metadata is HTML-stripped and http(s)-validated before
  storage. Settings → Integrations (the former MCP tab) hosts the
  **Web sources** card with add/edit dialog (kind, URL, label, course,
  interval, per-kind options); sources are course-owned config that rides
  `ca-course/v2` bundles with fresh cursors on import
- ✅ **Suggestions: keep track + Discover UI (plan 73-D, 2026-09-16)**: found
  material no longer vanishes. Every discovery result row is annotated with its
  tracking state ("Saved" / "Dismissed"), and the new **Discover dialog** (in
  the create menu of the course Materials tab and the Library) searches across
  the enabled providers with per-row verbs — **Open** external, **Attach as
  link** (slice A, placed at the current node), **Import & parse** (slice B job
  with live polling), **Save for later**, **Dismiss** — plus a **Saved &
  dismissed** section listing every tracked suggestion with status chips,
  restore, re-pointable attach, open-material shortcuts and **Forget**.
  Suggestions are one row per normalized URL per profile
  (`material_suggestions`, migration 0062): attaching or importing links the
  row to its material, deleting that material reverts the row to `suggested`,
  deleting the course removes its rows (scratchpad rows survive), and Settings
  → Providers gains the **Discovery** card (web / YouTube toggles + site
  presets with kind and enable flags, honestly gated on a configured search
  provider)
- ✅ **Discovery provider registry (plan 73-C, ADR-166, 2026-09-16)**: one
  normalized search across pluggable providers — Web (the existing Tavily/
  SearXNG integration), **YouTube** (yt-dlp flat search, typed `video` with
  duration/channel), and site-filtered presets (**Khan Academy** ships
  built-in; no first-party Coursera/Udemy — a user may add their own site or
  an MCP connector later). `POST /discovery/search` returns normalized rows
  (kind from a closed vocabulary: video/course/article/exercise/other) with
  per-provider errors surfaced honestly — partial results render, silence
  doesn't; nothing is ever persisted by a search
- ✅ **Parser registry & YouTube transcripts (plan 73-B, ADR-165, 2026-09-16)**:
  the "Import & parse" verb on link references is now real — an ordered
  parser registry (YouTube → direct file → HTML) runs as a cancellable
  background job: YouTube URLs gain a **searchable, timestamped transcript**
  (`[mm:ss]` anchors, manual captions preferred over auto-generated, the
  material's language first) plus channel/duration metadata; direct file URLs
  (`.pdf`, `.md`, `.docx`, `.mp3`, …) download into the standard upload path
  and land like any upload; plain pages parse via the same HTML conversion as
  the URL importer. No captions? The reference card says so honestly and
  offers **Transcribe audio instead** (yt-dlp audio download into the
  existing transcription pipeline). Re-parsing creates a new version —
  restorable from history. Extractor breakage (a known YouTube reality) fails
  loudly with a "try updating yt-dlp" hint, never a silent empty transcript
- ✅ **Async compose with progress and cancel (plan 70-D, ADR-156,
  2026-09-16)**: the compose builder no longer blocks for the whole generation —
  it submits a cancellable compose job and shows live progress with a cancel
  button; the dialog polls the new single-job status endpoint and lands on the
  same result view (coverage note, review warning, open document). Large
  documents can no longer hold the UI for minutes; the sync endpoint remains
  for chat approvals
- ✅ **Link materials — attach a URL as a reference (plan 73-A, ADR-164/171,
  2026-09-16)**: a new `link` material kind keeps a web resource as a real,
  first-class material — placeable, taggable, ⭐, searchable metadata — with
  zero ingest. The URL-import dialog gains an **Attach as reference** mode
  (default) beside **Import & parse**, the node workspace create menu gains
  "Import from URL" (placing at the current node), and link materials render
  a compact reference card (title, domain, open-external, "Import & parse")
  instead of extraction views. Per-course dedupe is database-enforced on a
  normalized URL (`youtu.be/x` ≡ `youtube.com/watch?v=x`, tracking params
  stripped) — re-attaching the same link surfaces the existing material
- ✅ **Web research tools (plan 52-D, ADR-136)**: a configurable web search
  provider (Settings → Providers → Web search; Tavily-compatible or SearXNG,
  API key in the keyring) unlocks the tutor's **SEARCH** (2/turn) and **FETCH**
  (1/turn) tools — results render as source-domain chips, retrieved content is
  never stored, and an advisory contract nudges citation when search was used.
  Genesis gains a **Ground the outline in web sources** toggle; grounded
  courses carry a "Drafted with sources:" footer
- ✅ **Quiz-me chat mode (plan 53-C, ADR-121)**: a per-session **Quiz-me**
  toggle swaps the tutor into assessing mode — it asks one question at a time
  via the `QUIZ` tool (choices or free text/math) and the **server grades
  deterministically** (choice match / math equivalence chain / accepted text
  variants); the expected answer never enters any model-visible payload, the
  card shows the verdict + expected answer, and the tutor follows up. Graded
  verdicts **credit the daily answer count** (plan 53 round 2, 0056
  `quizme_answers` — counted beside quiz answers in streaks/goals/XP; no
  synthetic Answer row)
- ✅ **Study planner (plan 53-A, ADR-118, 2026-09-06)**: a root-only
  **Planner** tab per course + a **This week's plan** strip on Home (next 7
  days across courses). `plan_items` (0054) are user-owned rows
  (study/practice/review/milestone, due dates, check-off); **Generate plan**
  deterministically paces the course's untouched nodes across the days before
  the exam date (spacing arithmetic, no scheduler), adds weak-concept practice
  items from the diagnostics cells and weekly review milestones — all as
  **draft suggestions** the user keeps or discards individually; re-generate
  never touches done or manual items. Items drag between days (or +1-day
  button), feed streaks honestly, and join the Home surface
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
- ✅ **Table / matrix completion (C19, plan 51-F)**: the `table_fill` question
  type answers a grid cell by cell — headers + row labels, pre-filled `"locked"`
  cells shown read-only, fillable cells typed per their declared kind
  (text = normalized match + accept list, numeric = tolerance, equation =
  SymPy equivalence). Grading is per-cell deterministic with partial credit =
  fraction of correct cells; generators propose tables (validators: alignment,
  kinds, parseable values, ≥1 fillable cell; repair loop) and `caq/v1`
  round-trips them; the filled grid replays in the attempt report
- ✅ **Composite questions with follow-through credit (C16, plan 51-E)**: the
  `composite` type is one multi-part problem (2–4 ordered parts, each
  text/numeric/equation). Each part grades deterministically; when a part
  declares a `follow_through` relation (a SymPy expression over the prior
  parts' answers, symbols `a`/`b`/`c`), a later part answered correctly **from
  your earlier answer** earns credit flagged *follow-through* even when the
  earlier part was wrong. Validators prove at generation time that the relation
  is parseable, only references prior parts, reproduces the declared value from
  the declared answers, and still evaluates from a perturbed answer (repair
  loop); `caq/v1` round-trips the parts; the per-part feedback
  ("(a): incorrect, (b): correct (follow-through)") renders in the runner and
  the response rides the attempt report
- ✅ **Graph-reading answers (C5, plan 51-G)**: the `graph_read` type renders a
  **server-computed curve** in the stem (deterministic SymPy evaluation over a
  domain — never model-authored numbers) and asks the student to read it:
  *read-a-value* (numeric answer with tolerance, e.g. "What is f(2)?") or
  *click-a-point* (click the chart, graded by nearest data point — plotly click
  events). The model authors only the expression, domain and target x; the
  expected value/tolerance/data-point index are **computed by the backend** and
  validators prove any declared value matches the computed data. The chart
  rides the stem as a standard `chart` block; the response (reading or clicked
  point) replays via the attempt report
- ✅ **Code-execution questions (C14, plan 51-D, ADR-115)**: the `code` type
  runs the student's Python **in Pyodide (CPython → WASM) inside the
  webview** — no server-side execution path exists at all, identical in desktop
  and web modes, offline-capable (the runtime is bundled as a lazy chunk).
  Visible test cases (call expression → expected JSON value / stdout); the
  runner executes the code once, evaluates each call with stdout capture, and
  compares in-page (number tolerance, string normalization); the submitted
  per-case payload is **re-verified by the backend** against the stored tests
  (partial credit = passing cases). Generators may propose code questions
  (validators: 1–10 tests, call + expected per test, reference solution
  required; the reference solution stays server-side and is never exported to
  `caq`). Known limits: Pyodide stdlib + bundled packages only; no hard
  execution timeout without cross-origin isolation (infinite loops freeze the
  tab — documented)
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
- ✅ **Split-view study mode (plan 22 G; per-pane close plan 62-A; shared
  header plan 62-B)**: `SplitStudyPane` overlay — material (MaterialDetailBody
  tabs) left, `NoteEditor` right (rides autosave), both panes headed by one
  shared `StudyPaneHeader` band (title + meta chips + tabs + verbs + overflow +
  close; the note side hosts tag chips and the autosave "Save now" chip, the
  pane title band and duplicate "Study — {title}" header are retired), drag
  divider persisted per course
  (30–70 %, `ca-study-split:{course}`), ≥lg only (drawer fallback below);
  URL-addressable `?material=<id>&study=<noteId|new>` on both workspace routes;
  **per-pane close** — the note header ✕ drops only `study` (the material
  drawer remains; `onRequestClose` flushes a dirty autosave first), pane ✕/Esc
  closes everything (ADR-139); **visible divider** with grip dots, arrow-key
  resize (±5, persisted) and double-click 50/50 reset (plan 62-C); **empty-note
  quick-start strip** (quote bridge / math+mermaid syntax, dismissed on first
  content, plan 62-D); **Take
  notes** in the material drawer/page header;
  **header declutter (plan 62-E/F)** — all materials switch views via a compact
  "Switch view" dropdown (Formatted/Raw text for text files;
  Extraction/Original/Side-by-side for scans), Description renders in an ⓘ
  header popover (only when set), and one ⋯ More-material-actions overflow
  holds Export .md / Print / Save as material / History (hidden without an
  extraction; mindmaps skip History) while the extraction toolbar keeps only
  version meta + read-aloud + edit
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
- ✅ **Adaptive difficulty via item-level Elo (C11, plan 51-H)**: every graded
  practice answer updates a deterministic Elo pair — the question's rating
  (seeded from its declared difficulty, `item_stats.rating`) and the student's
  rating for each concept×skill cell it touches (`concept_skill_ratings`); K
  declines from 32 to 8 with attempt count, exam attempts are excluded
  server-side. Consumers: focused quiz generation targets the student's cell
  rating (concept/skill focus without an explicit difficulty derives the
  target difficulty from the rating), and item analysis flags
  `elo_outlier` questions whose live rating drifts ≥200 points from their
  declared-difficulty seed after ≥10 attempts — too-hard/too-easy detection
  for the bank. Low-attempt questions keep wide uncertainty (no flag, and
  targeting falls back to the requested difficulty)
- ✅ Quiz time limits (C10 completion, plan 49-C): `activities.time_limit_sec` +
  server-computed `attempts.deadline_at`; generate picker (none/30/60/90/120/custom)
  and a Practice-tab ⋯ Time limit editor; countdown chip in the runner
  (server-offset corrected), auto-submit at the deadline mark with an honest
  summary, post-deadline answers rejected `attempt_closed`, lazy sweep on read.
  Cloze/match/order (C3) and essay rubrics (C17) remain open (item analysis
  C15 shipped as first cut, see analytics)

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

- ✅ **Chat as a working actor (plan 66, ADR-144…147)**: the tutor proposes and
  the student clicks — **14 approval-gated proposal actions** (up to three per
  reply), including **edit/append for notes and materials reviewed as a diff**
  (formatted `MarkdownDiffView` review with a Raw source toggle, server-captured
  staleness snapshots — the model never authors diffs), **a visible target row**
  (kind + file/note name + course-tree breadcrumb on every create/edit/append
  card), **context-aware generation** (material/note ids,
  instructions, question types — unoffered ids trigger a repair round),
  flashcard/material/concept creation, organize moves/tags/exam-date and
  planner proposals. New read tools: **`FIND`** (course-scoped hybrid search
  whose hits become READ-able handles) and insight resources
  `NODE_CONCEPTS`/`NODE_FLASHCARDS`/`MISTAKES`/`PLAN`/`DUE` — the tutor can
  now see error patterns, plan items, due cards and readiness
- ✅ **Chat surface on the shared library core (plan 60, family plan 11 /
  ADR-0009)**: the sidebar and full-page chat are assembled from
  `@neuronection/assistant-ui` chat modules — `ChatPanel` (page/sidebar
  hosts), `ChatTranscript` (log semantics, stick-to-bottom + jump pill,
  turn-completion announcements), `ChatMessage` + `MessageVariantSwitcher`
  (bubbles, copy/edit/regenerate actions, `‹n/N›` variants), `MarkdownSurface`
  (math/KaTeX, tables, mermaid, copyable code; mention links via the `a`
  override), `ChatReasoning` (collapsible thinking, preference persisted),
  `ChatComposer` (IME-safe submit — composition never sends), `ChatBranchTree`
  (commit-graph rail) and `ChatSessionList` (fuzzy search, date groups).
  App-side remain the WS→family-event adapter (`chatTransport.ts`, run-id
  gated), widget/plotly/geo block renderers, TraceTimeline, tool cards with
  calculator views, attach/equation/draw/screenshot dialogs and the .md export
  — zero backend changes
- ✅ **Reading-view header cleanup (2026-09-07, UI modernization)**: the
  material page's top action row now holds **Ask AI / Take notes / Export .md /
  reading status** together — Ask AI moved up out of the extraction toolbar —
  and the **unread / reading / studied** pill trio became a **compact
  reading-status dropdown** (status dot + label + check-marked menu). The
  extraction toolbar slims to **read-aloud ▶, Edit (pencil) and a ⋯ More
  actions menu** holding the less-frequent verbs (**Print, Save as material,
  History**) — and the plain reading view regained its **Print** action (the
  print preview previously lived only on mindmap materials). Menu
  primitives come from the family library via the `popover-menu` shim
  (`Menu`/`MenuCheckboxItem` compound joins `PopoverMenu`)
- ✅ **Ask AI from the reading view (plan 61, ADR-137/138)**: the material
  reading header gains an **Ask AI** popover (attached-material chip, suggested
  question chips — explain / summarize / key terms / worked example / quiz me —
  and free text; chips fill the input, **one explicit Ask click sends**), and
  selecting a passage shows a floating toolbar with **Ask AI about this**
  (selection quoted as a capped blockquote above your question) plus
  quote-into-note in split view. Every ask opens the sidepanel chat pinned to
  **one session per material** (lazily created, titled after the material,
  scoped to its node) with the material attached — grounding rides message
  attachments + the READ tool, never pasted ids; the quiz-me chip flips the
  session into quiz-me mode first. The sidepanel and the drawer
  **coexist**: the FocusShell overlay (material drawer, quiz/exercise runners)
  yields — panel and backdrop inset by the live chat width, maximize yields to
  the remaining space — and the chat entrance/resize are 200 ms
  reduced-motion-safe animations
- ✅ **First-ask visibility fix (2026-09-07 follow-up)**: a pendingSend queued
  before the sidepanel mounts (the Ask AI / selection-ask path) is consumed on
  mount with a session adoption, so the provider's mount reset no longer wipes
  the in-flight turn — the thinking card, streamed reply and turn-final
  refetch now render from the very first ask (previously the request and the
  response only appeared after the next manual send). Browser-locked by e2e
  `05-ask` S6/S7 (paced mock provider, real-LLM turn length; S7 covers asking
  while the sidepanel is already open on another session), and the send path
  waits for the provider to catch up with the store's pinned ask session
  before sending
- ✅ **Multi-material Ask AI from the library (2026-09-07, plan-61 follow-up)**:
  selecting one or more materials and right-clicking offers **Ask AI about N
  materials…** — a dialog with the selection as attachment chips, the five
  predefined question chips (multi-aware phrasings) and free text; one
  course-scoped session per selection tuple (reused on re-ask), every material
  attached as READ-grounded context (capped at 10, matching the backend), and
  the quiz-me chip switches the session into quiz-me mode before sending.
  Locked by e2e `05-ask` S8 + dialog/util/store vitest suites
- ✅ **Full-page chat fixes (2026-09-07 live-testing follow-up)**: the first
  send on the full-page tutor no longer loses the live turn — `/chat` became a
  layout route (index + `$chatId` children) so creating a session and
  navigating to `/chat/$chatId` no longer remounts the surface and orphans the
  in-flight stream (the thinking card, streamed text and stop button now
  render from send to finalize); `useActiveChatSession` bridges the
  just-created session from the chat store while the sessions refetch is in
  flight, and the AppShell effect that closes the sidepanel on `/chat` only
  fires when the sidepanel is actually open (it used to wipe the pinned
  session mid-bridge). A new e2e spec (02-chat S5) and a ChatPage streaming
  integration test lock the behavior. Styling rides the library: the `page`
  variant is now a full-bleed shell with a centered conversation column and
  assistant bubbles are muted/borderless (assistant-ui 0.26.0), and the app
  bridges its palette onto the `--as-*` tokens in the new
  `frontend/src/theme.css` — chat (and every library surface) now follows the
  app's dark theme
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
- ✅ **Attach menu (+)**: reference courses, materials, notes, quizzes,
  exercises, **course-tree nodes** (plan 72-F — flattened tree with
  summary/breadcrumb meta; picks send `kind:'node'` attachments the tutor can
  READ and target) and **file upload** through the chat (saved to the
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

- ✅ **Skeleton loading + keyboard help (plan 77-A, ADR-184)**: spinner-only
  loading is gone from the high-traffic surfaces — the Library pane (grid/list
  shaped, per mode), course Materials-tab browse, the NodeWorkspace gate,
  Review's card, the chat session list and Home's stat cards/strips render
  layout-matched shimmer skeletons (`MaterialBrowserSkeleton` shared by both
  browse surfaces) instead of popping in; inline verbs keep their spinners.
  Primitives are the family library's `skeleton` module (`aria-hidden`
  decorations, CSS-only sweep via `--as-*` tokens, static under
  `prefers-reduced-motion`), consumed through the `ui/skeleton` shim; loading
  regions carry `aria-busy`. A **`?` keyboard-shortcuts overlay**
  (`components/layout/ShortcutsDialog.tsx` over the honest
  `lib/shortcuts.ts` inventory — palette, capture, review 1–4/space, library
  cut/copy/paste/delete, Esc, split-divider arrows) opens from a rail button
  under the palette entry and never fires while typing (input/textarea/
  contenteditable guard)
- ✅ **Capture shell (plan 67-A/B/C, ADR-148)**: the **command palette**
  (`Ctrl/Cmd+K` — navigation, creates, jumps to any note/quiz/exercise,
  `?`-prefixed full-text search, ranked by the library fuzzy module) gains
  quick-capture, snap-a-region-into-note and import-from-URL actions, and
  **`Ctrl/Cmd+Shift+K` opens a quick-capture sheet** that saves a markdown
  note to the scratchpad with an undo toast; Home shows recent captures.
  Shared motion presets (`lib/motion.ts`) animate the surfaces and collapse
  under reduced motion
- ✅ Desktop shell (`python -m studyassistant`), WebKitGTK validated; browser dev
  mode — I1
- ✅ Providers/models/tasks Settings with keyring keys, discovery, vision gating,
  presets incl. Ollama, and per-capability **default models** with per-task override
  (inherit-or-custom) — I3/I7 (wizard polish pending); **per-course task-model
  overrides** via the workspace root's Settings tab → Tasks subtab (course title +
  description in the General subtab) — ADR-091
- ✅ Light/dark/system theme; **UI languages en/el/de** — Settings → General switcher,
  instant apply, locale-aware date/number formatting, completeness-gated picker
  (`docs/usage/language.md`) — I4/I8 (plan 69)
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
- ✅ **Extraction modes (plan 74 A, ADR-172)**: re-ingest now accepts an
  extraction **mode** — `POST /materials/{id}/reingest` body
  `{"mode": "auto" | "text" | "ocr"}` (`ReingestOptionsIn`): `text` = use the
  PDF's own text layer even when thin (extractor `pymupdf:forced`), `ocr` =
  force the vision model over every rasterized page (extractor `ocr:forced`),
  `auto` = the smart per-page choice. Applicability is
  server-computed and exposed per material (`MaterialOut.reextract_modes`,
  computed from kind: pdf gets all three, images get auto/ocr, everything
  else auto only) — non-applicable modes are refused with a 422 naming the
  allowed ones. Cancel-safe: OCR loops check the cancel flag between pages, so
  a long forced-OCR run aborts mid-flight instead of after completion.
- ✅ **Per-page hybrid auto extraction (plan 74 B, ADR-173/175)**: `auto` no
  longer trusts a text layer on a whole-document average (the old
  50-chars/page rule). Each page is scored deterministically (`pdf_pages.py`)
  — thin text (below the page floor), garbled glyph pages (`(cid:NNN)`
  markers, U+FFFD replacement chars over 1% of the page), and
  figure-dominated pages (image covering ≥ half the page with little text)
  are routed to the vision model; healthy pages keep their extracted text;
  results are spliced in page order. Mixed documents extract as `hybrid`
  (visible in version meta), all-text as `pymupdf`, all-OCR as `ocr`. If no
  vision model is assigned, `auto` degrades to plain text **only when the
  document has a text spine** (extractor `pymupdf:degraded`, honestly
  labeled); a fully-scanned document without a provider still fails with the
  honest "OCR task unassigned" message. Huffman-garbage sub-layers
  (≥50 chars/page of `(cid:…)` runs) that the old heuristic trusted now
  correctly re-OCR.
- ✅ **OCR prompt governance + page context (plan 74 C, ADR-176)**: page-OCR
  runs through the seeded **`ocr.page` skill** — the gateway resolves the
  active skill version once per ingest job and threads it as the system
  prompt (byte-identical to the previous hardcoded constant; falling back to
  that constant when the skill row is missing). Editing the skill in
  Settings → Skills immediately changes page OCR (it is a normal versioned
  skill now — the duplicate constant in `gateway_ocr.py` is gone, one source).
  The document title rides along as page context
  (`Transcribe this page. Document: {title}`) so short pages (captions,
  formulas alone on a page) are transcribed with framing. Handwriting/
  drawing OCR keeps its own `notes.transcribe` skill and path.
- ✅ **Viewer block copy actions + math-viewer fidelity (plan 63, ADR-140/141)**:
- ✅ **AI block fixer (plan 64, ADR-142)**: broken mermaid/math blocks in the
  editor show a ✨ **Fix with AI** affordance (on the failed block and inside both
  edit dialogs). A tier-0 deterministic repairer fixes known extractor mermaid
  sins instantly (quoting unquoted labels with parens/colons — validated by
  `mermaid.parse` before proposing); harder breakages go to the model as
  `fix_mermaid`/`fix_math` transform presets with the renderer's parse error
  attached, and a free-form **Ask AI** box lets the user steer or re-run the fix
  with their own instruction (combined with the repair directive in the prompt).
  Every proposal is reviewed as a diff and gated by the real renderer —
  Apply stays disabled until the fixed source parses; nothing is applied without
  the user's click
- ✅ **Selection-aware AI helper (plan 65, ADR-143)**: the ✨ helper captures
  **any selection shape** — plain text, a single diagram/formula node, or mixed
  text+blocks spans — by serializing the selection *slice* to markdown
  (tiptap-markdown serializer over `doc.cut(from, to)`, so node selections and
  atom blocks are included naturally). The idle popover shows a compact
  **selection summary chip** (collapsed by default, expandable to a ≤280-char
  preview + line count; per-kind counts: diagrams · formulas · code blocks ·
  tables · images · paragraphs), and the scope pill upgrades to
  "Selection — diagram" / "Selection — mixed (N blocks)". A **Try to fix** entry
  appears when the selection contains math/mermaid: it self-diagnoses via the
  renderer gate, runs the plan-64 tier-0 repair + `fix_*` preset flow in the
  popover (no dialog round-trip), and its result lands in the same review diff.
  Single math/mermaid-node selections are **gated like plan-64 fixes**: if the
  result still contains the same block kind it must parse before Apply
  (failure shows the renderer error and an explicit "Insert as markdown
  anyway" escape hatch); cross-kind results apply as explicitly-labeled
  markdown ("Applies as markdown"). Apply replaces the captured range in one
  undo step via the existing markdown replace path — every transform (not only
  fixes) reviews as a diff.
  every rendered-block surface (`BlockRenderer` — chat transcript, reading view,
  note history, quiz stems/explanations, flashcard review, exercise hints, cheat
  sheets) gains a hover/focus-revealed ⋯ **Copy options** menu composed app-side on
  the family library's `ActionMenu` — per block type: math → Copy LaTeX / Copy as
  Markdown (`$…$` or `$$…$$`), code → Copy as fenced block (the existing direct copy
  button stays), text → Copy markdown, diagram → mermaid source, chart → figure
  JSON, table → GFM markdown table, geo → JSXGraph script. Suppressed where a menu
  would misfire or print: inside clickable answer rows (quiz choices, math-trainer
  chips, error-spot lines, matching/ordering labels) and on the flashcard print
  sheet (`actions={false}`). Promotion-shaped for the library (presentational,
  labels via i18next at call sites) under the two-app rule. **Fidelity:** display
  math the extractor stored with `$$` sharing lines with content (broken in any
  remark renderer) is canonicalized viewer-side before parsing
  (`normalizeMathFences` — the editor's own text-level scanning rules), so
  multi-line `$$…$$` renders display like the editor and single-line `$$…$$` alone
  on a line renders display-style; stored markdown is never rewritten. **Mermaid:**
  diagram renders are serialized (a module-level queue — concurrent renders, e.g.
  many flowcharts mounting at once under StrictMode, previously cascaded failures
  via a global temp-DOM sweep when one diagram failed) and failures clean up only
  their own temp container, so one invalid diagram can no longer break the others;
  genuinely invalid mermaid shows its raw source in both editor and reader
- — Onboarding wizard (I9 polish)

## Progress & analytics (Phase 7 — in progress)

- ✅ Today screen: streak, daily goal ring (editable goal), due-review count,
  next-best-action cards (review/drill/read/challenge) with evidence lines and
  one-tap actions, 90-day consistency heatmap — H10/H11/I21 first cut
- ✅ Study time tracking: `study_sessions` rows auto-opened by focus surfaces
  (quiz runner, exercise player, note editor, material reading drawer) with a
  one-minute heartbeat and a server-side resume window so remounts fold into one
  row; Study-time card (today/this week) on Home; heatmap colors fold in study
  time — H3 study-time promise (plan 49-A)
- ✅ Focus timer (I18): floating AppShell pill — 25/5, 50/10 or custom presets,
  pause/resume/give-up, break offer on completion; focus blocks log
  `study_sessions` rows (`source=timer`) with the active route's course/node
  context
- ✅ Minutes-or-questions goals (H10): daily goal gains a unit
  (answers | minutes); streak counts any qualifying day — ≥1 answer/card review
  or ≥5 minutes of tracked study time
- ✅ Review nudges: Home strip (due cards + overdue tasks → /review, hidden at
  zero) and opt-in browser notifications (Settings → General; ≤1 summary per
  30 min while the app is open; feature-detected with honest fallbacks) —
  plan 68-C
- ✅ Planner week view + ICS: List⇄Week toggle (Mon–Sun grid, today highlight,
  drag-between-days, overdue/done styling) and a server-rendered
  `GET /courses/{id}/plan.ics` calendar export with stable UIDs (re-import
  updates, never duplicates) incl. the exam date as an all-day event — plan 68-B
- ✅ Notification center: 🔔 bell in the sidebar footer over a computed
  `GET /notifications` aggregate — due-card count, today/overdue plan rows,
  exam countdowns; grouped popover deep-links to the review queue / planner;
  count-dot clears via a localStorage seen-marker (nothing persisted
  server-side) — plan 68-A
- ✅ Global Review queue: cross-course due API (`GET /review/due`, grouped by
  course) behind a first-class `/review` page — rail entry with a live due-count
  badge, per-card course chips, keyboard 1–4 rating, progress bar, and honest
  all-clear state; the per-course Practice cards segment embeds the same
  course-agnostic `ReviewQueue` (one review implementation, two scopes) — H3
  dashboard promise (plan 49-B)
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
- ✅ Print export via print CSS (quiz list) — superseded by the **print/PDF
  engine (plan 53-F, ADR-120)**: dedicated print surfaces with a shared
  `PrintDoc` shell + print stylesheet (KaTeX renders natively; no headless
  renderer) — quiz **exam paper** and **answer key** (`?print=paper|key` from
  the quiz row menu, server-authoritative `GET /quiz/activities/{id}/answer-key`),
  **flashcard cut-out sheets** (front/back fold cards over the due set), a
  **Print** action on the extraction reading view (KaTeX/Mermaid render via
  `MarkdownSurface`), and a **Planner week sheet**. `?autoprint=1`-style
  surfaces open the dialog automatically; in the desktop shell `window.print()`
  opens the GTK print dialog (export-to-PDF included), and the documented
  fallback is printing from webapp mode. See `docs/usage/printing.md`
- ✅ **Read-aloud TTS (plan 53-E, ADR-119)**: ▶ buttons on the extraction
  reading view, the note editor, chat assistant messages, and lessons
  (ai-composed materials) — zero-config **browser `speechSynthesis` first**
  (gated on actual voice availability after the `voiceschanged` settle, so
  voiceless WebKitGTK hides the buttons honestly) with the provider `tts`
  task as the natural-voice option when assigned; playback bar with stop +
  speed; math is read via a deterministic LaTeX strip-and-speak helper (no
  model round-trip); provider audio is ephemeral and ledgered per char count
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
  E3/E6 (first cut; menu + edit + toggle in plan 23 B; delete in the drawing menu 2026-08-22);
  **re-OCR shows an old-vs-new transcript diff (2026-09-05)**: the previous
  transcript is captured at re-run, and when the new text arrives the inline
  transcript renders a side-by-side `TextDiffView` (`-`/`+` lines, auto-open,
  "changed" badge, Show-plain dismiss) instead of silently replacing the text
- ✅ Note search including OCR'd handwriting — E8 (first cut via search_text)
- ✅ **Snap a screen region into a note (plan 67 C)**: a 📸 note-editor toolbar
  button and a "Snap a region into note" palette action open the region-crop
  engine (extracted from the chat composer) — pick a window/screen, drag a
  rectangle, review the capture in a preview popover (Insert/Cancel), and
  Insert stores it as a strokeless snapshot drawing (OCR honestly skipped) and
  drops the `ca-drawing://N` ref at the cursor with an Undo toast; with no
  note editor open the shot lands in a new note in the current course, else
  the scratchpad
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
  **transform presets are always enabled: with no selection they run on the
  whole note** (the popover header + a scope pill — Selection / Whole note —
  state what will be transformed, and the review view offers **Replace note**
  via a whole-document replace), and the Context chip falls back to the whole
  note when nothing is selected;   **the review view is a tabbed comparison**
  (2026-09-05): **Diff** (default for transforms — a gitlens-style side-by-side
  `TextDiffView` with `-`/`+` gutters, `+N −M` stats, expandable
  "unchanged lines" folds that highlight each changed block, **word-level
  intra-line highlighting** (exact changed words marked inside changed lines),
  **source line numbers**, **prev/next change navigation** with a change
  counter, fold re-collapse, and **virtualized rendering** for long diffs),
  **Formatted**
  (markdown preview) and **Raw** (editable plain text); with a selection and a
  wide panel, a compact scrollable **Original pane** sits left of the result
  for the Formatted/Raw views; streaming output is coalesced (50 ms) so token
  floods never block the UI; math, diagrams, tables and drawing refs survive
  insertion byte-faithfully; the
  popover is a **movable, resizable floating window** (grip bar to move, edge/
  corner handles to resize) that stays inside the app window so its buttons are
  never clipped
- ✅ **Dictation in the rich editor (plan 42/ADR-097)**: a 🎤 toolbar button
  (everywhere the shared editor appears — notes, extraction QA editor, new
  text/markdown file dialog) records a voice clip (timer + live level meter,
  Cancel to discard), transcribes it through the `transcribe` speech-to-text
  task, and inserts the text at the cursor
- — Pin-to-notes (F7)
