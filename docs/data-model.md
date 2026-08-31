# Data model (as built)

SQLite, WAL mode, foreign keys on, busy-timeout 5 s. Managed by Alembic migrations
`0001`–`0019`; the app runs migrations on startup. All user-content tables are
`profile_id`-scoped (no-auth profiles; a default profile is seeded on first run).

## Entity map

```
profiles ─┬─ courses ─── tree_nodes (self-FK parent, ≤4 levels, root = course level)
            │      └─ material_links (node_id) ── materials
            ├─ material_folders (self-FK; one tree per course)
            ├─ materials ─── extractions (versioned, append-only) ─── chunks
            │      └─ material_index_cards · material_study_state (per profile)
            ├─ concepts ─┬─ concept_links ── node_concepts (coverage per node)
            │            └─ (per-course graph; nodes cover concepts)
            ├─ chat_sessions (node binding) ─── chat_messages (citations JSON, grounded flag)
            ├─ activities (quiz, node placement) ─┬─ questions (metadata taxonomy, sympy_check)
            │                                     ├─ attempts ─── answers (telemetry, error tags)
            │                                     └─ mistakes (mistake notebook)
            └─ exercises (node placement) ─┬─ exercise_steps (expected answer spec)
                                          └─ exercise_sessions ─── step_attempts (hint level,
                                                                   error class, independence)
providers ─── models ─── task_assignments        (machine-global, not per profile)
              models ─── default_task_assignments (per-capability defaults, ADR-088)
              models ─── course_task_assignments  (per-course task model overrides, ADR-091)
              models ─── course_default_task_assignments (per-course capability defaults, ADR-092)
jobs · ai_interactions                          (durable queue · AI audit log)
```

## Scoping model (ADR-039, migration 0019)

Every course has exactly one **root node** (`is_root`, depth 0) — the course level
is a node. Nodes nest to **depth 4** (5 layers incl. root). Placement for all study
resources is a single `node_id` column paired with the owning row's `course_id`
under a **composite FK `(node_id, course_id) → tree_nodes(id, course_id)`** —
cross-course placement is impossible at the database level. `node_id` NULL ⇔
unbound ("All courses" content, ADR-033). Ownership/purge stays `course_id`
(ADR-036). Roll-up queries use the materialized `path` prefix (`/root/…/node/`);
depth-first ordering uses `sort_path`; both are derived data rebuildable from
`parent_id` + `order_idx`.

## Table reference

### Profiles & machine config
- **profiles**: id, name, color, **preferences JSON?** (0039 — user preferences, e.g.
  `use_embeddings`), created_at
- **providers**: id, name, type (google | openai_compatible | anthropic), base_url,
  keyring_ref (`provider:{id}`), enabled, status JSON (last test: ok/error/count)
- **models**: id, provider_id, external_id, label, caps JSON (text/vision/tools/
  embeddings), ctx_tokens, cost_in/out, **reasoning_effort?** (0038 — per-model reasoning
  control: OpenAI `none/low/medium/high` (set `none` to enable function tools on reasoning
  models), Anthropic `minimal/low/medium/high`), enabled, missing — unique (provider, external_id)
- **task_assignments**: task (PK: ocr, notes_ocr, description, outline, concepts,
  quizgen, exgen, tutor, grade, chat, flashcards, embeddings), model_id,
  fallback_model_id, params
- **default_task_assignments** (0041): requires (PK: text | vision | embeddings),
  model_id, fallback_model_id — per-capability default models; a task's unset
  model/fallback inherits its capability's default (ADR-088)
- **course_task_assignments** (0042): course_id+task (composite PK), model_id,
  fallback_model_id — optional **per-course overrides** of a task's model and/or
  fallback; NULL slots fall through to the global chain (task assignment →
  capability default). Cleared on course purge; unassigned when their model is
  deleted (ADR-091)
- **course_default_task_assignments** (0043): course_id+requires (composite PK:
  text | vision | embeddings), model_id, fallback_model_id — per-course
  **capability defaults**; a task resolves per-slot through global default →
  global task → course default → course task (ADR-092). Purged with the course;
  model deletion nulls refs

### Library
- **material_folders**: id, profile_id, course_id (one folder tree per course,
  unique per profile+course+path), parent_id, name, path (materialized),
  source_id? (unique → material_sources: a linked source is a **symlink-style
  folder node** in its course's tree, ADR-037 — live browse via the source's
  target, virtual subdirectories never persisted; deleting the node = unlink)
- **material_sources**: id, profile_id, label, path, recursive, include_globs,
  course_id (required — scanned files land in that course), enabled,
  scan_interval_sec? (per-source override, min 15 s; NULL → global default),
  last_scan_error?, last_scanned_at — linked folders (B15/ADR-037); scans are
  stat-first, changed files re-ingest as new extraction versions, moved files
  remap by content hash
- **blobs**: sha256 PK, rel_path, size, mime — content-addressed originals
- **materials**: id, profile_id, course_id (**required** — every material is owned
  by exactly one course; no global library, ADR-036), group_id?, folder_id?, kind
  (pdf/image/md/txt/doc), title, blob_sha, filename, mime, pages, language, status
  (pending/processing/ready/failed), content_hash, phash?, source/external fields
  (for future linked folders) — index (course_id, status); upload dedup is
  per (profile, course, content_hash)
- **extractions**: id, material_id, version (append-only; latest = current),
  extractor (pymupdf | ocr | native | manual), model, blocks JSON, markdown,
  confidence, tokens/cost, reviewed, edited_by_user
- **chunks**: id, extraction_id, ordinal, text, token_count
- **material_images** (0048, ADR-103): id, material_id (FK, cascade), position
  (document order), blob_sha (FK→blobs, content-addressed), mime, ocr_version,
  ocr_markdown, ocr_job_id, created_at — embedded images extracted from
  converted office/web materials (plan 47); referenced from the extraction
  markdown via `ca-image://{id}`, transcribed asynchronously by the
  `image_ocr` job (plan-46 async pattern), OCR text joins FTS/AI context like
  drawing OCR
- **material_drawings** (0032, ADR-064): id, material_id (FK, cascade), strokes
  JSON (replayable vector strokes — the source of truth), png_sha (FK→blobs,
  content-addressed PNG render), view JSON (0046, ADR-098 — exported region,
  mirrors `note_drawings.view`), ocr_version, ocr_blocks JSON, ocr_markdown,
  ocr_job_id (0047, ADR-102, mirrors `note_drawings.ocr_job_id`),
  created_at — mirrors `note_drawings`; drawings are referenced from the
  extraction markdown via `![drawing](ca-drawing://{id})`, and their OCR joins the
  material FTS + AI chunk context
- **material_index_cards**: material_id PK, summary, topics, key_terms,
  reading_minutes, difficulty
- **material_study_state**: id, material_id + profile_id unique, status
  (unread/reading/studied), progress, last_opened_at

### Courses & node tree
- **courses**: id, profile_id, title, description, subject, level, goals, tags,
  color, **exam_date?** (Date, 0029 — exam planner; cleared via explicit null
  PATCH), archived_at
- **tree_nodes**: id, course_id (FK), parent_id (composite FK `(parent_id,
  course_id)` → self — intra-course parenting DB-enforced), title, summary?,
  objectives JSON, ai_hint? (0021 — instructions injected into every AI task in
  the subtree; the root's hint acts as course-level guidance), order_idx
  (gap-numbered ×1000), depth (0–4 CHECK), path
  (`/{root}/…/{id}/` — unique; subtree = prefix scan), sort_path (zero-padded
  order chain — depth-first sort), is_root (exactly one per course, partial
  unique index), created_at. Root is undeletable; delete = **merge** (children +
  placements move to the deleted node's parent, duplicate material links cleaned)
- **material_links**: id, course_id (denormalized owner), node_id (composite FK
  with course_id → tree_nodes — **intra-course placement DB-enforced**),
  material_id, extraction_id?, rationale, auto_assigned, confidence, created_at —
  unique (node_id, material_id); unlink ≠ delete. Course-level assignment =
  the root node
- **material_folder_links** (0030, ADR-058): id, course_id, node_id (composite FK
  like material_links), folder_id → material_folders, rationale, auto_assigned,
  confidence, created_at — unique (node_id, folder_id). A node's effective
  materials = direct links ∪ **members of assigned folders, resolved at read
  time** (virtual folders by subtree path prefix; linked-source folders by
  `materials.source_id`); never materialized, so later uploads/scans join
  automatically. Unassigning a folder-derived material is refused (move the file
  out or unassign the folder); deleting/unlinking a folder with active links is
  refused; direct links win on overlap; node merge-delete/restore and course
  export/import treat them as placements
- **concepts**: id, course_id, name (unique per course), description?, aliases
  JSON — one knowledge graph per course (8D); **concept_links**: from/to concept +
  relation (prereq-of | part-of | related-to), unique per triple; **node_concepts**:
  node+concept unique, weight? — coverage at any depth

### Quiz
- **activities**: id, profile_id, course_id (required, ADR-040), node_id? (placement; root ⇔ course
  level; NULL ⇔ unbound), type (quiz), title, config, generated_from, created_at
- **questions**: id, activity_id, parent_id?, type (single/multi/truefalse/text/
  numeric/equation), stem blocks, options blocks, answer JSON (per type), explanation
  blocks + full taxonomy: difficulty, bloom, skill (conceptual/procedural/applied/
  notation), concept_ids, expected_time_sec, curriculum_code, source_refs,
  distractor_misconceptions (option → error tag), sympy_check (expected expr),
  input_modes, tags (concept names meanwhile), provenance (generator | caq/v1),
  flag (ok/review), stats
- **attempts**: id, activity_id, mode (practice/exam), started/finished, score
  (partial-credit weighted), meta
- **answers**: id, attempt_id, question_id, response JSON, input_mode, correct,
  partial_credit, feedback blocks, graded_by (deterministic | symPy | config),
  time_ms, retries, error_tags, help_events (hint refs filled at answer time)
- **quiz_help_events**: id, attempt_id, question_id, level (1–5), markdown,
  violations? — the P5b hint-ladder transcript; gates no-skip + level-5 reveal
- **mistakes**: id, profile_id, question_id, error_tags, created_at, resolved_at?

### Exercises & tutor
- **exercises**: id, profile_id, course_id (required, ADR-040), node_id? (placement), title, **kind**
  (default `multi_step`; `card_basic`/`card_reverse`/`card_cloze` = flashcards, ADR-045 — one
  exercise per card, `deck_ref?` groups a deck), context
  blocks, difficulty, created_from (`manual` | `generator: exgen` | `source:
  similar, from_exercise_id` | `source: drill, pattern` | cards: `{source, source_ref}`)
- **exercise_steps**: id, exercise_id, order_idx, prompt blocks, expected
  (kind math|numeric, value, tolerance?), hints_pregenerated?, rubric? — card steps:
  order_idx 0, prompt = front, `expected = {kind: card_*, back: blocks}`;
  structural steps (B2): single step, `expected = {kind: matching|ordering|
  categorize|fill_blank, pairs|items|categories+items|prompt_md+answers}` —
  graders + public widget specs in `services/exercise_structs.py`
- **exercise_sessions**: id, exercise_id, current_step_idx, status, socratic,
  independence_score, started/finished
- **step_attempts**: id, session_id, step_idx, response, correct, hint_level_used,
  error_class (misread/procedural/conceptual), feedback, **state JSON** (per-widget
  state document keyed by widget id, plan 34D)

### Error patterns (drills, ADR-063)
- **error_patterns**: id, **key** (unique stable slug), course_type_id? (FK→course_types,
  null = global), name, description, example?, detection? (optional deterministic
  detector spec, e.g. `{type: negated}` for sign_slip, `{type: factor, factors}`),
  is_system (seeded vs AI/user-discovered), is_active, order_idx, created_at.
  Code-seeded idempotently via `seed_error_patterns` (ADR-020 pattern; G10 calculus
  taxonomy under `math`). Drill resolution = active patterns where `course_type_id`
  matches the course's type or is null; counts are course-scoped via
  `Mistake→Question→Activity.course_id`. `exercises.created_from` provenance is by
  pattern **key** (string), not id — no FK back.

### Notes, handwriting, flashcards
- **notes**: id, profile_id, course_id (required, ADR-040), **node_id?** (placement — any depth; root
  ⇔ course level), owner_type (standalone/material/exercise_session/chat_message)
  + owner_id? (**attachment** to non-node things only), title, body JSON blocks
  (text blocks + `{"type":"drawing","drawing_id"}` inline blocks, plan 22 E —
  serialized as `![drawing](ca-drawing://N)` markdown; unknown ids rejected 422),
  search_text (title + body + drawings' OCR markdown — powers note search incl.
  handwriting), tags JSON, pinned, timestamps
- **note_drawings**: id, note_id, strokes JSON (replayable vector strokes — the
  source of truth), png_sha → blobs (content-addressed render), view JSON
  (0046, ADR-098 — the exported region `{x, y, width, height}` in stroke
  coordinates, 1 PNG px = 1 logical px; lets re-editing restore 100% scale),
  ocr_version, ocr_blocks/ocr_markdown (notes_ocr result, re-runnable),
  ocr_job_id (0047, ADR-102 — the in-flight background `drawing_ocr` job, or
  null; serialized only while that job is queued/running)
- **note_versions**: id, note_id (FK CASCADE), profile_id, title, tags, body
  JSON, cause (autosave-coalesced | manual | restore), created_at — pre-write
  snapshots taken coalesced (≥10 min apart or `force_version`; plan 22 B),
  capped 50/note; restore writes the old body and force-snapshots (undoable)
- **deleted_items**: id, profile_id, entity_type (note | quiz | exercise |
  chat), title, payload JSON (full subtree snapshot — children, drawings w/
  embedded PNG base64, review history), deleted_at, purge_after (7-day TTL,
  purged at boot + on listing; plan 22 D). Restore re-inserts with original ids
  (collisions re-inserted with fresh ids + FK remap); no soft-delete columns
- **flashcards**: *folded into exercises as `card_*` kinds (ADR-045, migration 0026
  dropped the table — front/back live on the step, FSRS/review rows re-pointed to
  exercises.id; the `/flashcards` REST surface is unchanged)*
- **fsrs_states**: id, card_id (unique → exercises.id for card kinds), state
  (new/learning/review/relearning),
  stability, difficulty, reps, lapses, due_at (indexed — review queue),
  last_review_at
- **review_log**: id, card_id (→ exercises.id), rating (1–4), interval_days, elapsed_days,
  reviewed_at

### Analytics (Phase 7)
- **concept_skill_stats**: id, profile_id, concept (tag string — the string axis),
  concept_id? (nullable FK-free dual-write to `concepts`), skill, n, accuracy,
  avg_time_ratio, last_seen_at, weakness_score — unique (profile, concept, skill);
  materialized by `/analytics/materialize`
- **daily_rollups**: id, profile_id, day (YYYY-MM-DD, unique per profile),
  answers_n, correct_n, cards_reviewed, minutes, xp
- **item_stats**: id, question_id (unique), n_attempts, p_correct, avg_time_ms,
  avg_time_ratio, distractor_selection JSON, flag — extreme p-correct at n≥20
  flags the question `review`
- **study_goals**: profile_id PK, answers_per_day (default 20)

### Skills & prompt library (Phase 7, doc 08)
- **course_types**: id, key (unique), name, description — seeded
  (math/science/language/programming/generic), user-extensible; `courses.course_type_id`
- **skills**: id, task, key (unique, e.g. `tutor.hint`), name, description, is_system —
  seeded idempotently from code
- **skill_versions**: id, skill_id, scope_type (system/course_type/course),
  scope_ref, version, system_template, user_template (Jinja2), params JSON,
  contract JSON, is_active, created_at — UNIQUE(skill, scope, version);
  every `ai_interactions.skill_version_id` references one

### Chat & audit
- **chat_sessions**: id, profile_id, course_id?, **node_id?** (scope binding —
  retrieval narrows to the subtree), title, context JSON (quiz-attempt binding
  for P5b "ask about this question"), **use_embeddings?** (0039 — per-chat query-
  embedding override; null = follow the profile preference), **active_root_id?**
  (0044 — which root-level message starts the visible branch path), created_at
- **chat_messages**: id, session_id, role, blocks, citations JSON
  ([{index, chunk_id, material_id, title, quote}]), grounded bool?,
  **state JSON** (per-widget state document keyed by widget id, plan 34D),
  **tool_calls JSON** ([{name, argument, phase, result?, title?}] — the tools the
  tutor invoked that turn, shown as collapsible cards; READ/STATE results are
  never stored, only a `read N chars` summary for READ), **warnings JSON?** (0040 —
  persisted turn-level warnings, e.g. "semantic search unavailable", rendered as a
  notice under the message), **parent_id?** (0044 — branch tree parent; NULL =
  root-level variant), **active_child_id?** (0044 — which child continues the
  visible path; the linear conversation is the root→tip walk over these pointers)
- **ai_interactions**: id, context_type (chat/tutor/quiz_help/exgen/flashcards/
  note_action/**gateway**/…), context_id, direction, **task** (set on gateway
  ledger rows), model, input/output tokens, **cached_input_tokens?** (0037 —
  provider cache-read tokens, cost discounted at 0.1×), cost_usd?, latency_ms —
  every model call lands here; `context_type="gateway"` rows are the cost ledger
  (one per real API call, with real provider usage numbers since 37A)
- **jobs**: id, type (ingest/postprocess/chat_turn/drawing_ocr), payload, status
  (queued/running/done/failed/cancelled), progress, stage, error, timestamps

## Derived structures (not in Alembic)

- **material_fts** — FTS5 virtual table (title, markdown, description, topics,
  material_id UNINDEXED), synced service-layer in the same transaction as extraction
  writes
- **material_fts_trigram** (0045) — same columns, `tokenize='trigram'`; index-backed
  candidate generation for the typo-tolerant fuzzy search tier (candidates verified
  per-token in Python before ranking); synced alongside `material_fts` and backfilled
  from it by 0045
- **chunk_vecs** — sqlite-vec vec0 table (chunk_embedding float[dim], cosine),
  created at runtime with the sqlite-vec extension; **vec_meta** stores dim + model;
  changing embedding model drops and rebuilds the table automatically
- **tree_nodes.path / sort_path** — materialized from parent_id + order_idx;
  rebuilt by the migration and maintained by `services/tree.py` (rebuildable at
  any time)

## Not yet built (planned)

staged_imports (qpkg tier), settings, study_sessions, mastery_estimates (mastery
signals computed in metrics.py meanwhile). Phase 9B+ (UI work) adds no schema.

## Migration notes

- **0048 (plan 47, ADR-103)**: new `material_images` table — extracted embedded
  images of converted office/web materials (docx/pptx/epub/html), one row per
  image with a content-addressed blob, document position, and async `image_ocr`
  state (`ocr_version`/`ocr_markdown`/`ocr_job_id`, plan-46 pattern). Downgrade
  drops the table.
- **0047 (plan 46, ADR-102)**: `ocr_job_id` nullable Integer column added to
  `note_drawings` and `material_drawings` — pointer to the in-flight background
  `drawing_ocr` job (create/update/re-OCR save first and return; the job fills
  the OCR fields and clears the pointer). Downgrade drops both columns.
- **0045 (fuzzy search)**: `material_fts_trigram` — trigram-tokenized FTS5 mirror of
  `material_fts` for typo-tolerant search; backfilled from existing rows on upgrade,
  dropped on downgrade. Synced service-layer together with `material_fts` (no shape
  change to tracked tables).
- **0044 (plan 40, ADR-093)**: chat branching — `chat_messages.parent_id` +
  `active_child_id`, `chat_sessions.active_root_id`; data migration chains each
  session's existing messages by id (identical linear view afterwards).
- **0031 (plan 28, ADR-063)**: `error_patterns` — course-type-scoped error-pattern
  taxonomies (new table; rows seeded idempotently from code at startup, G10 calculus
  taxonomy under `math`).
- **0030 (plan 25 A, ADR-058)**: `material_folder_links` — folder assignment to
  nodes (new table, no data migration).
- **0029 (plan 22 H)**: `courses.exam_date` (nullable Date) — exam planner.
- **0028 (plan 22 D, ADR-048)**: `deleted_items` — snapshot trash; destructive
  deletes of notes/quizzes/exercises/chats snapshot the subtree first (deletes
  return `{deleted_item_id}` 200, no longer 204); course deletion requires
  `confirmed_backup` and creates a fresh backup before purging.
- **0027 (plan 22 B, ADR-046)**: `note_versions` — coalesced pre-write snapshots
  (PATCH notes may carry `force_version`; history/restore endpoints added).
- **0020 (ADR-040)**: `course_id` NOT NULL on notes/activities/exercises/
  flashcards; course-less rows moved into the per-profile "Unsorted" course at
  its root node (auto-created if missing). Creation endpoints require a course.
- **0019 (Phase 9A, ADR-039)**: chapters/sections collapse into `tree_nodes`
  (chapters → depth 1–2 preserving nesting; sections → children of their chapter's
  node; every course gains a root). `material_links.owner_type/owner_id` → `node_id`
  + `course_id` under the composite FK; activities/exercises/flashcards
  `section_id` → `node_id` (course-bound rows placed at root); notes: owner_type
  'section' → `node_id` placement; `section_concepts` → `node_concepts`;
  chat_sessions gain `node_id`. Old tables/columns dropped — no dual source of
  truth. Downgrade intentionally unsupported (structural rewrite).
- **0014 (Phase 8A, ADR-036)**: `section_materials` → `material_links` (data
  preserved, owner_type='section'); `materials.course_id` and
  `material_folders.course_id`/`material_sources.course_id` became required.
  Course-less materials/sources and unassignable folders migrated into an
  auto-created "Unsorted" course per profile (a normal course — quick-assign from
  there, delete once empty). Folders whose subtree held materials of exactly one
  course were assigned that course; materials whose folder landed elsewhere kept
  their course and lost the folder placement.
