# Data model (as built)

SQLite, WAL mode, foreign keys on, busy-timeout 5 s. Managed by Alembic —
the `0001_baseline` squash (plan 81 F, ADR-196) plus `0002_vocab_sweep`
(plan 82 C); the app runs migrations on startup. All user-content tables are `profile_id`-scoped
(no-auth profiles; a default profile is seeded on first run).

The **contract** layer — per-table identity, closed sets and their CHECK twins,
foreign keys and delete behaviour, JSON species, profile-scope derivation path —
is generated from the models into
[schema-contract.md](schema-contract.md) (`scripts/schema_inventory.py --check`
is a CI gate). This page is the prose narrative; that page is the guarantee.

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

## Identity (ADR-198; folded into `0001_baseline`)

Every user-data entity is keyed by a UUID string — `Uuid(as_uuid=False)`, the
same convention `users`/`profiles` carry from the family identity schema. On
SQLite that is `CHAR(32)` hex; on PostgreSQL it is the native `uuid` type (the
dialect twin). Integer surrogate keys are retired; natural keys are unchanged
(`blobs.sha256`, the task-assignment tables' composite keys,
`instance_settings.key`).

- **Why:** course bundles, import/export and any future sync/sharing/merge need
  identity that survives a re-home. A bundle import honours the incoming ids and
  remaps only on collision (`course_bundle._import_id`), so export → wipe →
  import preserves every reference.
- **Ordering:** UUID order is *not* insertion order. Any list that used to mean
  "oldest/newest first" orders by `created_at, id` (or the row's own timestamp:
  `attempts.started_at`, `review_log.reviewed_at`, `deleted_items.deleted_at`);
  `question` order inside a quiz is `questions.created_at, id`. The discovery
  suggestion cursor is the opaque `"<created_at iso>|<id>"` keyset pair.
- **Polymorphic refs** (`notes.owner_id`, `chat_messages.parent_id`,
  `skill_versions.scope_ref`, `ai_interactions.context_id`, JSON id arrays) are
  UUID strings with no FK — the same shapes as before, wider type only.
- **Vectors:** `chunk_vecs.rowid` stays a 63-bit integer (vec0/pgvector need
  it); `storage/vectors.py` derives it from the chunk id and keeps the reverse
  mapping in `chunk_vec_ids`.

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
- **profiles** (family-normative, identity-auth §5 — 0066): id (app
  generated UUID), **user_id** (NOT NULL, FK users ON DELETE CASCADE —
  1:N per user), name, **is_default** (exactly one per user), color,
  **preferences JSON?** (0039 — user preferences, e.g.
  `use_embeddings`), **last_used_at?** (§6 last-used profile), created_at,
  updated_at. `preferences` keeps its pass-through JSON (extension-owned `mcp` /
  `search_providers` sections) behind the `ProfilePreferences` TypedDict and the
  pydantic validation at the preferences API edge (ADR-200). Every `profile_id`
  column is a UUID with ON DELETE CASCADE;
  user creation auto-provisions Default in the same transaction and
  deleting the last profile re-provisions it.
- **providers**: id, name, type (google | openai_compatible | anthropic), base_url,
  keyring_ref (`provider:{id}`), **preset_key?** (String 40, 0064 — the §15 stamp
  for preset setup rows; NULL = manually added), enabled, status JSON (last
  test: ok/error/count)
- **models**: id, provider_id, external_id, label, caps JSON (text/vision/tools/
  embeddings/stt/tts/decision — vocabulary per family §15 + plan 26 after
  0064; `decision` is explicit-only, never inferred), **decision_transport?**
  (0069 — the transport seam, `systemone` today), ctx_tokens,
  cost_in/out, **reasoning_effort?** (0038 — per-model reasoning
  control: OpenAI `none/low/medium/high` (set `none` to enable function tools on reasoning
  models), Anthropic `minimal/low/medium/high`), enabled, missing — unique (provider, external_id)
- **task_assignments**: task (PK: ocr, notes_ocr, description, outline, concepts,
  quizgen, exgen, tutor, grade, chat, flashcards, embeddings), model_id,
  fallback_model_id, params
- **default_task_assignments** (0041): requires (PK: text | vision |
  embeddings | stt | tts | decision:tool-dispatch | decision:boolean-gate |
  decision:choice | decision:score — the four `decision:*` slots seeded by
  0069, plan 26),
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
  remap by content hash. **`preset`** (0006, plan 85 D, ADR-213;
  `folder|vault`, CHECK twin) selects the scan meaning: `folder` ingests files
  as materials and gets a library folder node, `vault` ingests `.md` files as
  **notes** with `[[wikilink]]` edges and has no folder node
- **material_suggestions** (0062, plan 73-D): id, profile_id, course_id?
  (nullable — scratchpad-level discovery is allowed; suggestions are pointers,
  not study content), node_id? (composite `(node_id, course_id)` FK discipline
  when set — node deletion re-points to the parent like other placements),
  provider, url (raw, display) + url_norm (`normalize_url` identity key,
  ADR-171; **unique per (profile_id, url_norm)** — one row per identity,
  re-discovery upserts), title, snippet?, kind (DiscoveryKind), meta JSON,
  status (`suggested|saved|dismissed` StrEnum), material_id? (set when
  attached/imported — deleting the material reverts the row to `suggested`),
  timestamps. Course purge deletes the course's rows; scratchpad rows survive.
  **Suggestions do not ride `sa-course/v2`** — they are profile-scoped tracking
  history, not study content.
- **external_sources** (0063, plan 73-E): id, profile_id, course_id (required —
  a source feeds one course's suggestion stream), kind
  (`rss|youtube_channel|youtube_playlist|site_search` StrEnum), url
  (String 2048), label?, options JSON (per-kind: `max_items`, `query`+`site`
  for site_search), enabled, scan_interval_sec? (per-source override, min
  15 min; NULL → 6 h default), last_scan_error?, last_scanned_at?,
  cursor JSON (per-kind resume marker: RSS etag/last-modified + seen-entry ids;
  YouTube seen-video ids — both capped at 1000), created_at. Course purge
  cascades; **rides `sa-course/v2`** (kind/url/label/options/enabled/interval
  exported, import re-creates rows with fresh cursors).
- **blobs**: sha256 PK, rel_path, size, mime — content-addressed originals
- **materials**: id, profile_id, course_id (**required** — every material is owned
  by exactly one course; no global library, ADR-036), folder_id?, kind
  (pdf/image/md/txt/doc), title, blob_sha, filename, mime, pages, language, status
  (pending/processing/ready/failed), content_hash, phash?, source/external fields
  (for future linked folders) — index (course_id, status); upload dedup is
  per (profile, course, content_hash)
- **materials** — AV metadata (0049, ADR-104): `duration_sec` (float, from
  mutagen at upload), `bitrate_kbps` (int) — nullable, only set for
  audio/video kinds; feeds the transcript metadata header and the pre-flight
  transcription size warning
- **materials** — description (0052): `description` nullable text — a short
  user-written summary of the file, set at text-file creation or via the
  material PATCH (whitespace-only normalizes to NULL); shown on the material
  page's Description tab
- **materials** — citation metadata (0004, plan 85 B, ADR-212): `citation_title`
  (500), `citation_authors` JSON (`AuthorList` — ordered `{name, affiliation?}`
  rows, keep-open), `citation_year`, `citation_doi` (255), `citation_container`
  (300) and `citation_kind` (`CitationKind` CHECK twin, nullable — ordinary
  materials have no citation). DOI-first dedupe in the import path; BibTeX
  export serializes the same columns and `citation_text` renders one
  deterministic style (`Author (Year) — Title`)
- **extractions**: id, material_id, version (append-only; latest = current),
  extractor (pymupdf | ocr | native | manual), model, blocks JSON
  (+ `blocks_schema_version`, ADR-200), markdown, confidence, tokens/cost,
  reviewed, edited_by_user
- **chunks**: id, extraction_id, ordinal, text, token_count
- **material_images** (0048, ADR-103): id, material_id (FK, cascade), position
  (document order), blob_sha (FK→blobs, content-addressed), mime, ocr_version,
  ocr_markdown, ocr_job_id, created_at — embedded images extracted from
  converted office/web materials (plan 47); referenced from the extraction
  markdown via `sa-image://{id}`, transcribed asynchronously by the
  `image_ocr` job (plan-46 async pattern), OCR text joins FTS/AI context like
  drawing OCR
- **material_drawings** (0032, ADR-064): id, material_id (FK, cascade), strokes
  JSON (+ `strokes_schema_version`, ADR-200; replayable vector strokes — the
  source of truth), png_sha (FK→blobs, content-addressed PNG render),
  **view_x/view_y/view_width/view_height** (0046/0074 — the exported region as
  typed columns, mirrors `note_drawings`), ocr_version, ocr_blocks JSON
  (+ `ocr_blocks_schema_version`), ocr_markdown,
  ocr_job_id (0047, ADR-102, mirrors `note_drawings.ocr_job_id`),
  created_at — mirrors `note_drawings`; drawings are referenced from the
  extraction markdown via `![drawing](sa-drawing://{id})`, and their OCR joins the
  material FTS + AI chunk context
- **material_index_cards**: material_id PK, summary, topics, key_terms,
  reading_minutes, difficulty
- **material_study_state**: id, material_id + profile_id unique, status
  (unread/reading/studied), progress, last_opened_at

### Courses & node tree
- **courses**: id, profile_id, title, description, subject, level, goals, tags,
  color, **exam_date?** (Date, 0029 — exam planner; cleared via explicit null
  PATCH), archived_at, **origin** (0053: `manual | genesis | import | scratch`
  — scratch = the per-profile hidden Scratchpad), **hidden** (0053)
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
  input_modes, tags (concept names meanwhile), provenance (generator | saq/v1),
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
  (+ `body_schema_version`, ADR-200; text blocks +
  `{"type":"drawing","drawing_id"}` inline blocks, plan 22 E — serialized as
  `![drawing](sa-drawing://N)` markdown; unknown ids rejected 422; every write
  is validated by `app/domain/documents.py`), search_text (title + body +
  drawings' OCR markdown — powers note search incl. handwriting), tags JSON,
  pinned, timestamps; **vault provenance** (0006, plan 85 D, ADR-213):
  `source_id?` → `material_sources` (`SET NULL` — unlinking keeps the note),
  `external_path`, `file_mtime`, `file_size`, `content_hash` mirror the
  linked-folder scanner so rescans version an edited `.md` file
- **note_links** (0006, plan 85 D, ADR-213): id, profile_id, course_id,
  `from_note_id` → notes (CASCADE), `to_note_id?` → notes (CASCADE, NULL for a
  broken wikilink), `target` (the link text), created_at; unique
  `(from_note_id, target)`, indexed by target for backlinks. Populated by the
  vault scanner from `[[wikilinks]]`; never written by the editor.
- **note_drawings**: id, note_id, strokes JSON (+ `strokes_schema_version`,
  ADR-200; replayable vector strokes — the source of truth), png_sha → blobs
  (content-addressed render), **view_x/view_y/view_width/view_height** (0046,
  ADR-098; typed columns since 0074 — the exported region in stroke
  coordinates, 1 PNG px = 1 logical px; lets re-editing restore 100% scale),
  ocr_version, ocr_blocks JSON (+ `ocr_blocks_schema_version`)/ocr_markdown
  (notes_ocr result, re-runnable), ocr_job_id (0047, ADR-102 — the in-flight
  background `drawing_ocr` job, or null; serialized only while that job is
  queued/running)
- **note_versions**: id, note_id (FK CASCADE), profile_id, title, tags, body
  JSON (+ `body_schema_version`), cause (autosave-coalesced | manual |
  restore), created_at — pre-write
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
  retrieval narrows to the subtree), title, context JSON (typed
  `ChatSessionContext`: quiz-attempt / exercise binding, pending answer,
  reported proposal ids), mention_registry JSON (typed `MentionRegistryList`),
  **use_embeddings?** (0039 — per-chat query-embedding override; null = follow
  the profile preference), **active_root_id?** (0044 — which root-level message
  starts the visible branch path), **quizme**, created_at. The one pending
  quiz card lives in `chat_quiz_pendings` (0074, ADR-200), not in a JSON column.
- **chat_quiz_pendings**: session_id PK (FK chat_sessions ON DELETE CASCADE),
  question, choices JSON (list[str]), expected_index?, expected_latex?,
  expected_text?, accept JSON (list[str]), awaiting_answer, verdict
  (correct | incorrect), verdict_detail, student_answer, created_at — at most
  one row per session; the expected-answer fields never leave the server (the
  session API exposes the public state only)
- **chat_proposals**: id, message_id (FK CASCADE), action, payload JSON (the
  per-action instruction document behind `payload_schema_version`, validated by
  the action's pydantic model at every write), **target_kind** (note | material
  | concept | link), **target_name**, **target_node_id?** (FK tree_nodes ON
  DELETE SET NULL), **target_node_path JSON?** (display breadcrumb),
  **original_md?** (server-captured content snapshot for edit/append cards),
  result JSON (polymorphic outcome document behind `result_schema_version`),
  status (proposed | approved | dismissed | executed | stale | conflict),
  created_at, executed_at
- **chat_proposal_anchors**: proposal_id + position PK (FK CASCADE), op (replace
  | append | prepend), find_text?, text — ordered anchored text edits
  (0074, ADR-200); the API recomposes them into `payload.text_edits`
- **chat_messages**: id, session_id, role, blocks JSON (+
  `blocks_schema_version`, ADR-200), citations JSON
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
  provider cache-read tokens, cost discounted at 0.1×), cost_usd?, latency_ms,
  **metadata JSON** + **metadata_schema_version** (0015 — caller-supplied
  `space_id`/`kind`/`view`/`chunk_index` embedding tags only, never text) —
  every model call lands here; `context_type="gateway"` rows are the cost ledger
  (one per real API call, with real provider usage numbers since 37A)
- **notification_kinds**: key (the closed `NotificationKind` vocabulary),
  title, description, severity, admin_only, default_enabled, created_at —
  boot-seeded config; unknown kinds notify nobody
- **notifications**: id, kind (FK CASCADE), severity, title, body, payload JSON
  (ids/counts/scores/reasons only), source_ref JSON?, recipients JSON (admin
  user ids), dedup_key? (partial unique), dedup_expires_at?, created_at —
  deduped, recoverable alert events; the bell reads active keys, history stays
- **jobs**: id, type (ingest/postprocess/chat_turn/drawing_ocr), payload, status
  (queued/running/done/failed/cancelled), progress, stage, error, result
  (bounded `VECTOR_*` run result), idempotency_key/lock_key/heartbeat_at/
  cancel_requested (0011 retrieval action runtime), timestamps

## Derived structures (not in Alembic)

- **material_fts** — FTS5 virtual table (title, markdown, description, topics,
  material_id UNINDEXED), synced service-layer in the same transaction as extraction
  writes
- **material_fts_trigram** (0045) — same columns, `tokenize='trigram'`; index-backed
  candidate generation for the typo-tolerant fuzzy search tier (candidates verified
  per-token in Python before ranking); synced alongside `material_fts` and backfilled
  from it by 0045
- **chunk_vecs** — sqlite-vec vec0 table (chunk_embedding float[dim], cosine)
  on SQLite / pgvector + HNSW on PostgreSQL, created at runtime with the vector
  extension; **vec_meta** stores dim + model; **chunk_vec_ids** keeps the
  rowid→chunk UUID reverse map. A model/dimension change is **not** applied in
  place (0012, plan 50 P3a): `storage/vectors.ensure_table` raises
  `VectorSpaceChangeRequired` and the old table stays readable until an
  explicit new-space/cutover handoff runs. Since 0013 (plan 51 Q3c2a) the
  `content` space is dual-written to its provisioned `vec_dfbcce9b` backend
  and `chunk_vecs` remains the compatibility fallback.
- **vector_spaces / vector_documents / vector_records** (0012/0013/0014,
  plan 50 P3a + plan 51 Q3c2b1) — the portable metadata mapping. The legacy
  `content` space keeps the synthetic id `legacy-chunk-vecs`; 0013 updates its
  `index_table` to `vec_dfbcce9b`, and Q3c2b1 adds real `building`/`active`/
  `retired` spaces beside it. A document is a material (`kind='material'`,
  `source_id` = material UUID); a record is a chunk's `body` view carrying
  the family content hash, the study ``rowid`` (sqlite-vec map) and a
  space-local `chunk_id` handle (0014). The record id is deterministic per
  `(space, chunk)`, so two spaces can coexist without sharing the global
  primary key. The metadata is derived/operational, hard-deleted with its
  document, and never a second copy of text. `storage/vector_store.py` is the
  only read/write seam; physical DDL lives in
  `storage/vector_provisioning.py` and the dialect SQL in
  `storage/vector_backends.py`. Since 0016 every space carries the non-null
  `space_key` stamped once at creation/cutover (the frozen v1 pre-image for
  legacy rows); remap/status reads use that stored value and never recompute
  it. 0017 adds the nullable tokenizer/chunk identity and token-offset columns
  that plan 52 T5b2 will write; existing rows stay NULL and character chunking
  is unchanged.
- **tree_nodes.path / sort_path** — materialized from parent_id + order_idx;
  rebuilt by the migration and maintained by `services/tree.py` (rebuildable at
  any time)

## Not yet built (planned)

staged_imports (qpkg tier), settings, mastery_estimates (mastery signals are
computed in `services/platform/metrics.py` meanwhile). `study_sessions` is built —
see the 0059 note below. Phase 9B+ (UI work) adds no schema.

## Migration notes

- **0017_vector_token_schema (plan 52 T5b1)**: adds the nullable tokenizer
  (`kind`/`identifier`/`revision`/`artifact_sha256`/`exact`/`max_input_tokens`)
  and chunk (`max_tokens`/`overlap_tokens`/`max_chars`) scalars to
  `vector_spaces`, and nullable `token_count`/`token_start`/`token_end` to
  `vector_records`. All existing rows stay NULL. CHECKs enforce
  all-or-none, kind/exact/provenance, chunk bounds,
  `chunker_version='2'` when a tokenizer is present, and ordered/consistent
  token offsets. Downgrade drops these columns/checks but keeps `space_key`.
  No write path uses them yet (T5b2).
- **0016_vector_space_stored_key (plan 52 T5b1)**: adds non-null
  `vector_spaces.space_key` (`String(64)`) and stamps every existing row once
  with the frozen v1 eight-field pre-image before enforcing NOT NULL. The
  stored value is the remap/cutover identity; consumers never recompute it.
  Downgrade drops the column.
- **0015_retrieval_alerts (plan 51 Q3c3a)**: adds
  `ai_interactions.metadata` (JSON, non-null, `{}`) and
  `metadata_schema_version` (smallint, non-null, `1`) — caller-supplied
  `space_id`/`kind`/`view`/`chunk_index` embedding tags, never text — plus
  the boot-seeded `notification_kinds` registry and deduped `notifications`
  event rows with admin recipient ids and a partial unique dedup key.
  Downgrade drops both notification tables and the two ledger columns.
- **0014_vector_record_chunk_id (plan 51 Q3c2b1)**: adds
  `vector_records.chunk_id` (nullable `String(80)`), its index and the
  unique `(space_id, chunk_id)` constraint, then backfills `chunk_id = id`
  for the legacy `legacy-chunk-vecs` space. A building space coexists with
  the active one, so the global record primary key can no longer be the
  chunk id; `chunk_id` is the search hydration handle. Downgrade drops the
  column/constraint/index; record rows stay.
- **0012_vector_spaces (plan 50 P3a, ADR-0051 companion)**: adds
  `vector_spaces` (one `active` space per name; `index_table` allows the
  legacy `chunk_vecs`, NULL for linear, or a future `vec_<8hex>`),
  `vector_documents` (material source handle + `profile_id`; unique per
  space/kind/source) and `vector_records` (a chunk `body` record with
  `content_hash`, optional `rowid` reverse map, unique
  `(document, view, chunk_index)`). The one `content` space is backfilled
  from `vec_meta`; documents/records are backfilled from
  `chunk_vec_ids` + chunks/materials. Existing `chunk_vecs` rows are never
  dropped or rewritten; content hashes left empty by the SQL backfill are
  filled idempotently by `StudyVectorStore.backfill_metadata`. No coverage
  snapshot is written. Downgrade drops only the three metadata tables.
- **0011_retrieval_run_actions (plan 51 Q3b)**: `jobs` gains
  `idempotency_key` (nullable, 8–120 chars), `lock_key`, `heartbeat_at`
  and `cancel_requested` (boolean, default false). Two partial unique
  indexes cover only `status IN ('queued','running')`:
  `uq_jobs_idempotency_active (type, idempotency_key)` and
  `uq_jobs_lock_key_active (lock_key)`. Terminal rows release both slots,
  so retry/cancel/reaping never deadlock; the service additionally replays
  terminal rows inside the contract's 24 h key window. Downgrade drops
  both indexes and the four columns (batch mode on SQLite), leaving run
  history intact.
- **0010_retrieval_ops (plan 51 Q3a, ADR-0051 companion)**: the `jobs.type`
  CHECK widens with the three family `VECTOR_*` names and `jobs.result`
  (JSON, nullable) carries the bounded run-result document. New
  `retrieval_query_rollups` (dimensions `space_id/kind/view/degraded_reason/
  bucket_start/bucket_width`; count/zero/candidates measures + a versioned
  latency histogram; 30-day operational TTL) and
  `retrieval_coverage_snapshots` (one row per space/kind/as_of; nullable ANN
  recall; 90-day TTL). Both key a string `space_id`; the `content` space's
  id is that same string, and Q3c owns the lifecycle/cutover that changes
  it. Downgrade drops the tables and the
  result column and restores the old type CHECK; it fails loudly if a
  `VECTOR_*` job row still exists rather than rewriting run history.
- **0008_quiz_question_kinds (plan 87 B, ADR-217)**: the `questions.type`
  CHECK twin widens with the exercise-engine kinds (`matching`, `ordering`,
  `cloze`, `essay`); answer payloads reuse the existing JSON column (no new
  typed columns). SQLite rebuilds the table through batch mode; downgrade
  restores the 11-member CHECK and fails loudly if a new-kind row still
  exists.
- **0007_source_providers (plan 86 A/B/E, ADR-214/215/216)**:
  `external_sources` gains the open, registry-validated `provider` string
  (default `rss`), the `auth_kind` CHECK twin (`token|oauth2|none`), the
  nullable keyring-slot pointer `account_ref`, and `consecutive_failures`
  for the family `degraded|failing` status; the `kind` CHECK widens with the
  adapter-shaped members (`webdav_folder`, `cloud_folder`,
  `zotero_collection`, `anki_deck`). Existing rows are backfilled to their
  catalog provider. `exercises` gains nullable `external_uid` (the remote
  SRS card key), and `external_review_events` stores the union-merged
  localhost review log keyed by `(source_id, remote_card_id, reviewed_at)`.
  SQLite rebuilds both altered tables through batch mode; downgrade drops
  the columns/table and restores the four-member `kind` CHECK (fails loudly
  if adapter-kind rows still exist).
- **0006_vault_notes (plan 85 D, ADR-213)**: `material_sources` gains
  `preset` (`folder|vault`, CHECK twin, default `folder`); `notes` gains the
  linked-file provenance (`source_id` → `material_sources` `SET NULL`,
  `external_path`, `file_mtime`, `file_size`, `content_hash`); new
  `note_links` table (outbound wikilink edges with a nullable resolved
  target). SQLite rebuilds `material_sources`/`notes` through batch mode;
  downgrade drops the table, the columns and the CHECK.
- **0005_plan_item_external_uid (plan 85 C, ADR-213)**: `plan_items` gains the
  nullable `external_uid` column and the partial unique index
  `uq_plan_items_course_external_uid` (`WHERE external_uid IS NOT NULL`).
  Downgrade drops the index and the column.
- **0004_citation_metadata (plan 85 B, ADR-212)**: `materials` gains the
  nullable citation columns (`citation_title`, `citation_authors` JSON,
  `citation_year`, `citation_doi`, `citation_container`, `citation_kind`) and
  the `CitationKind` CHECK twin (`citation_kind IS NULL OR …`). SQLite rebuilds
  the table through `batch_alter_table(recreate="always")`; downgrade drops the
  CHECK and the six columns, restoring the previous shape.
- **0003_discovery_kinds (plan 85 A, ADR-211)**: `material_suggestions.kind`
  widens to the scholarly `DiscoveryKind` members (`paper`, `dataset`,
  `reference`). The CHECK swaps through a batch rebuild; downgrade restores the
  four-member vocabulary and fails loudly if a scholarly-kind row still exists.
- **0002_vocab_sweep (plan 82 C, ADR-204)**: `questions.type` and
  `exercises.kind` gain their CHECK twins now that the vocabularies are
  StrEnums (`QuestionType`, `ExerciseKind`; `exercises.kind` also carries the
  `FlashcardKind` card kinds — cards are exercise rows). SQLite cannot add a
  CHECK in place, so both land through `batch_alter_table(recreate="always")`;
  a row holding an unknown value fails the copy loudly. Downgrade drops both
  and recreates the previous shape.
- **0001_baseline (plan 81 F, ADR-196)**: the chain squashed. The former
  `0001`–`0075` history is deleted and `0001_baseline` is regenerated from
  the post-A–E models (65 tables, all named constraints/CHECK twins, UUID
  identity, payload law, scope/lifecycle law). `alembic upgrade head` on an
  empty database builds the entire schema in this one revision — including
  the SQLite FTS5 virtual tables / PostgreSQL tsvector+pg_trgm twins and the
  four seeded `decision:*` `default_task_assignments` rows — and
  `alembic downgrade base` drops it cleanly (a baseline-squash downgrade,
  the family migration rules (§3)). **Pre-baseline databases are rebuilt, not migrated**:
  delete the SQLite file and reseed demo data (`scripts/seed-demo.py`); no
  data-migration path exists by design. Every revision-pinned test was
  reworked to baseline round-trips/shape tests and all head assertions read
  the single `tests/migration_head.py::HEAD_REVISION` constant; the test
  template cache is keyed on a schema hash so a stale
  `migrated_template.db` cannot survive a schema change. Forward policy
  (model-first, one migration per change, batched per round, no compat
  columns/aliases/deprecation windows) is recorded in
  [migrations.md](migrations.md).

- **0075 (plan 81 E, ADR-201)**: scope & lifecycle law. `material_groups` and
  `materials.group_id` are **deleted** — the table shipped as a P0 plan row
  (01 A4) with no CRUD/UI; grouping is served by node placement
  (`material_links`) + material folders, and a future group feature arrives
  with its own plan. `skill_versions.scope_ref` is retyped `Integer` →
  `Uuid(as_uuid=False)` (its values are `courses.id`/`course_types.id`; C
  retyped every reader but missed the column, which would reject UUID text on
  PostgreSQL). Nullable-unique law: `skill_versions` gains a partial unique
  index `(skill_id, scope_type, version) WHERE scope_ref IS NULL`, the SQLite
  equivalent of PG `UNIQUE NULLS NOT DISTINCT`, so global-scope versions cannot
  duplicate. Lifecycle classes are declared per table in
  `contracts/data-model.lifecycle.txt` (`record | operational | transient`,
  D6-gated); `deleted_items` is the single tombstone (`operational`), no table
  carries other soft-delete columns, and hard delete is purge-only/cascade-
  complete (`tests/test_purge_cascade.py`). The revision is guarded for the
  0073 rebuild interaction (a fresh chain already lands the new shape) and its
  `downgrade()` restores the empty `material_groups` shape, `materials.group_id`
  + FK/index, and the integer `scope_ref` shape (round-trip in
  `tests/test_scope_lifecycle_migration.py`). `PROFILE_SCOPE` documents every
  table's scope path or non-user class; cross-profile reads are proven closed
  by `tests/test_profile_isolation.py`.

- **0074 (plan 81 D, ADR-200)**: payload contract law. Known-shape state
  leaves JSON: `chat_proposals` gains `target_kind`/`target_name`/
  `target_node_id`/`target_node_path`/`original_md` columns and the ordered
  `chat_proposal_anchors` table for anchored edits (the per-action instruction
  document stays JSON as `payload` with `payload_schema_version`; the outcome
  map stays JSON with `result_schema_version`); `chat_sessions.quiz_pending`
  becomes the one-row `chat_quiz_pendings` table; drawing `view` JSON becomes
  `view_x`/`view_y`/`view_width`/`view_height`. Canonical content documents
  keep their JSON shape and gain a version sibling validated at the write
  boundary — `notes.body`/`note_versions.body` (`body_schema_version`),
  `chat_messages.blocks`/`extractions.blocks` (`blocks_schema_version`),
  drawing `strokes`/`ocr_blocks` (`strokes_schema_version`/
  `ocr_blocks_schema_version`). Data moves run in Python before the old columns
  drop; `downgrade()` restores the columns and their documents (round-trip in
  `tests/test_payload_law_migration.py`). New closed sets: `target_kind`,
  anchor `op`, quiz `verdict` (CHECK twins). The empty-autogenerate model⇄DB
  drift gate is `tests/test_model_db_drift.py`; the JSONB verdict inventory is
  `contracts/data-model.jsonb-inventory.txt`. Note the chain interaction: 0073
  rebuilds the identity domain from current model metadata, so a fresh upgrade
  already lands the 0074 shape and the revision guards every add/create/drop
  (the data moves only run on a database that still carries the old columns);
  0068's text rewrite likewise skips columns the current model no longer has.

- **0073 (plan 81 C, ADR-198)**: UUID identity for every user-data entity.
  Every surrogate integer primary key becomes `Uuid(as_uuid=False)` — the
  convention `users`/`profiles` already used (CHAR(32) hex on SQLite, native
  `uuid` on PostgreSQL) — and every FK that pointed at one follows, including
  the polymorphic loose references (`notes.owner_id`, `chat_messages.parent_id`/
  `active_child_id`, `chat_sessions.active_root_id`, `skill_versions.scope_ref`,
  `ai_interactions.context_id`/`skill_version_id`, `questions.concept_ids`,
  `source_refs`, `*_drawings.ocr_job_id`, `materials.source_id`,
  `concept_skill_stats.concept_id`). Natural/composite keys are unchanged
  (`blobs.sha256`, `users`/`profiles` identity, the task-assignment tables).
  **The revision is destructive**: SQLite cannot convert an `INTEGER` primary
  key into the UUID storage shape in place, so the whole identity domain is
  dropped and rebuilt child-first from the model metadata (the 0066 pattern) —
  no rows are carried over (dev databases are rebuilt, ADR-196). `users`,
  `profiles`, `auth_sessions`, `audit_events` and `blobs` survive. The
  PostgreSQL FTS twins are rebuilt with `material_id TEXT`; FTS rows and the
  vec tables are cleared (reindex after upgrading). `downgrade()` restores the
  empty integer shape by rebuilding the same domain with identity columns
  typed back to `Integer` (shape only, no data). Consequence for callers:
  id order is no longer insertion order — list endpoints order by
  `created_at, id` and the suggestion cursor is `"<created_at>|<id>"`
  (`tests/test_uuid_identity_migration.py`, `tests/test_course_bundle.py`).

- **0072 (plan 81 B, ADR-197)**: DB-enforced closed sets. Nineteen
  StrEnum-backed columns (`courses.origin`, `materials.kind/status`,
  `jobs.type/status`, `chat_proposals.status`, `plan_items.kind/origin`,
  `study_sessions.kind/source`, `questions.flag`, `item_stats.flag`,
  `attempts.mode`, `material_study_state.status`,
  `material_suggestions.kind/status`, `external_sources.kind`,
  `concept_links.relation`, `study_goals.unit`) gain `CHECK` twins (`ck_<table>_<column>_allowed`) mirroring their StrEnum
  member lists; `Base.metadata` gains an `ix_/uq_/ck_/fk_/pk_` naming
  convention so every future constraint is named (short-name drops per
  the family migration rules (§5b)). `JobType.COMPOSE` was missing from the enum while the
  job registry already ran it — widened in the same commit so the new
  `jobs.type` CHECK cannot reject a real job. Explicit `ON DELETE` is declared
  on the FKs that silently relied on NO ACTION (`SET NULL` for catalogue/model
  references, `CASCADE` for provider→models and skill→versions, `RESTRICT` for
  the immortal blob store); SQLite cannot swap an unnamed FK, so the physical
  rewrite rides the 0073 table rebuilds (no deployed database exists).
  Downgrade drops every CHECK and is round-trip tested, including row
  preservation across the batch rebuilds
  (`tests/test_vocab_checks_migration.py`).

- **0069 (plan 26 Phase 3, ADR-0032)**: decision models — `models` gains
  nullable `decision_transport` (VARCHAR(20), the transport seam,
  `systemone` today), and the four `decision:*` slot rows are seeded into
  `default_task_assignments` (insert-if-absent; boot seeding is
  idempotent too). Downgrade drops the column and deletes the four slot
  rows; round-trip + idempotence pinned in
  `tests/test_decision_transport_migration.py`. No data migration (study
  had no legacy decision code — greenfield per §13.8).

- **S3 Postgres twins (2026-09-24, no revision numbers):** the
  existing migrations were made dialect-aware in place (no backwards
  compatibility — greenfield doctrine): `0002`/`0045` create
  tsvector+GIN / pg_trgm tables on PostgreSQL instead of fts5 virtual
  tables (`tsv`/`search_text` are generated columns, so app-side
  DELETE+INSERT sync stays shared), `0026`'s hand DDL swaps
  `DATETIME`→`TIMESTAMP`, `0019`/`0020` use bare `is_root`/`TRUE`
  booleans, `0053`/`0057`/`0061` carry `postgresql_where` twins,
  `0001` widens `alembic_version` to VARCHAR(64) on PG (long revision
  ids overflow Alembic's default), `0066` renders portable boolean
  defaults. Vector index: `chunk_vecs` is a vec0 virtual table on
  SQLite and `chunk_vecs(rowid BIGINT PK, chunk_embedding vector(N))`
  + HNSW cosine on PostgreSQL (drop+recreate on dim change, `vec_meta`
  shared). SQLite files: `<data_dir>/study.sqlite3` +
  `checkpoints.sqlite3` (was `app.db`/`checkpoints.db`).

- **0066 (family plan 16 S2b, ADR-0013)**: profiles identity rework —
  the whole profile domain is rebuilt from the model metadata:
  `profiles` gains `user_id` (NOT NULL, FK users, CASCADE), `is_default`,
  `updated_at`, `last_used_at`, UUID ids; every `profile_id` column
  becomes UUID with ON DELETE CASCADE. **Destructive and irreversible**
  (no backwards compatibility — user directive 2026-09-24): no rows are
  carried over, derived fts5/vec0 virtual tables are cleared, and
  `downgrade()` raises NotImplementedError. Recreate dev databases and
  reindex search/vectors after upgrading. Legacy-chain data tests stop at
  `0065_identity_core`; `tests/test_profile_identity_migration.py` pinned
  the head + schema shape (superseded by `0001_baseline` — those shape
  assertions now live in `tests/test_baseline_migration.py`).

- **0065 (family plan 16 S2, ADR-0013)**: identity core — `users`,
  `auth_sessions`, `instance_settings`, `audit_events` (family-normative
  shapes; uuid ids — native `uuid` on PostgreSQL, CHAR(32) hex on
  SQLite). Fresh-schema only: recreate pre-0065 dev databases
  (greenfield posture). The `profiles` rework (UUID ids +
  `user_id NOT NULL`) landed in 0066 (see above).

- **0064 (plan 79)**: BYOK setup + `stt`/`tts` capability split — adds
  nullable `providers.preset_key` (String 40; §15 stamp, NULL = manual
  row); rewrites `models.caps` JSON lists (`audio` expands to
  `['stt','tts']` per the frozen §15 contract, `speech` → `tts`);
  renames `default_task_assignments.requires` and
  `course_default_task_assignments.requires` rows (`audio` → `stt`,
  `speech` → `tts`). Downgrade restores old vocabulary best-effort
  (`stt` → `audio`, `tts` → `speech`; audio rows expanded during upgrade
  keep the extra `speech` entry) and drops `preset_key`. Tests:
  `tests/test_byok_migration.py` (legacy shape → upgrade → downgrade
  round-trip).
- **0063 (plan 73-E)**: `external_sources` table — profile FK indexed, course
  FK indexed (required), kind/url/label/options/enabled/scan_interval_sec/
  last_scan_error/last_scanned_at/cursor JSON/created_at. No data migration
  (new table). Downgrade drops the table.
- **0062 (plan 73-D)**: `material_suggestions` table — profile FK indexed,
  nullable course FK indexed, nullable `node_id` with the composite
  `(node_id, course_id)` FK to the node tree, provider/url/url_norm/title/
  snippet/kind/meta/status/material_id/created_at/updated_at, plus unique
  `uq_material_suggestions_profile_url` on `(profile_id, url_norm)`. No data
  migration (new table). Downgrade drops the table.
- **0061 (plan 73-A, ADR-164/171)**: `materials.source_url` (nullable string
  2048, the raw URL preserved for display) and `materials.source_url_norm`
  (nullable string 2048, the `normalize_url` identity key) plus two partial
  indexes: `ix_materials_source_url` (`WHERE source_url IS NOT NULL`) and
  unique `uq_materials_course_source_url_norm` on
  `(course_id, source_url_norm) WHERE kind = 'link' AND source_url_norm IS
  NOT NULL` — database-enforced per-course link dedupe. Downgrade drops both
  indexes and columns.
- **0060 (plan 49-C, ADR-108)**: `activities.time_limit_sec` (nullable int) and
  `attempts.deadline_at` (nullable timestamp, server-computed at attempt start
  from the quiz's limit) — server-enforced quiz timing. Downgrade drops both
  columns.
- **0059 (plan 49-A, ADR-106)**: `study_sessions` table (profile FK indexed,
  nullable course FK, nullable `node_id`, `kind` focus|quiz|exercise|review|
  read|note, `source` timer|auto|manual, nullable `entity_ref` for resume
  matching, `started_at`/`ended_at`/`last_beat`, `duration_sec`; index on
  (`profile_id`, `started_at`)) — the single source of truth for *time*
  analytics. Also `daily_rollups.study_seconds` (server_default 0) and
  `study_goals` gains `unit` (answers|minutes, default answers) and
  `minutes_per_day` (default 30). Downgrade drops the columns and the table.
- **0058 (plan 75-E, ADR-180)**: `material_sources.mirror_subdirs` boolean
  (server_default false) — opt-in linked-source subdirectory mirroring; when
  on, scan mirrors the source's subdirectory tree into the linked folder's
  children (title-match reuse, plain-library child folders with `source_id`
  NULL) and tags new materials with their folder (`materials.folder_id`);
  root linked-folder membership stays flat ("whole source") while mirrored
  child folders scope membership by the ordinary path-subtree walk — no
  change to `folder_member_ids` needed (review finding: the expected
  source-folder flatness bug does not apply to child folders). Downgrade
  drops the column (mirrored folders and assignments remain user data).
- **0057 (plan 67-D, ADR-149)**: `materials.tags` JSON (list[str], notes-style
  normalized via the shared `normalize_tags`) + `materials.starred` boolean
  (server_default false) + partial index `ix_materials_starred` where
  `starred = 1`; both round-trip in `sa-course/v2` bundles; list endpoint
  filters `tag=` / `starred=`.
- **0056 (plan 53 round 2, Quiz-me daily credit)**: new `quizme_answers` table
  (id, profile_id FK, session_id FK, correct bool, created_at) — one row per
  graded quiz-me answer so `daily_history` can fold verdicts into the daily
  answer/correct counts beside `Answer` rows (no synthetic Answer row — there
  is no Question to reference). Downgrade drops the table.
- **0055 (plan 53-C, Quiz-me)**: `chat_sessions.quizme` (bool, default off) +
  `chat_sessions.quiz_pending` (JSON — the pending quiz: question, choices,
  expected answer material **never exposed to the model**, verdict after
  grading). Downgrade drops both columns.
- **0054 (plan 53-A, planner)**: new `plan_items` table — per-course planner
  rows (profile_id, course_id, node_id nullable via the placement composite
  FK `(node_id, course_id)` — items follow node merge-delete and
  promote-to-course automatically), `title`, `detail?` (evidence line),
  `kind` (`study|practice|review|milestone`, `PlanItemKind` StrEnum),
  `due_date`, `done_at?`, `origin` (`manual|draft`), `sort_key`; indexes on
  (course_id, due_date) and (profile_id, due_date). Draft items are
  regenerable suggestions; re-generating deletes only future undone drafts.
  Course purge removes items. Downgrade drops the table.
- **plan_items** — calendar provenance (0005, plan 85 C, ADR-213):
  `external_uid` (nullable, ≤200) is the source ICS occurrence UID; a partial
  unique index on `(course_id, external_uid) WHERE external_uid IS NOT NULL`
  makes a re-import update rows instead of duplicating the week, while
  hand-made items (NULL) stay NULL-distinct (family data-model §9)
- **0053 (plan 52-A, Scratchpad)**: `courses.origin`
  (`manual | genesis | import | scratch`, default `manual`, `CourseOrigin`
  StrEnum) + `courses.hidden` (bool, default false) — the per-profile
  Scratchpad is a hidden `origin=scratch` course (unique per profile via the
  partial index `uq_courses_profile_scratch`), seeded lazily by
  `ensure_scratch_course`; hidden courses are excluded from `GET /courses`
  unless `include_hidden=true` and from exam forecasts / profile-wide
  recommendations (streaks still count). Downgrade drops the column and the
  index.
- **0052 (text editor UX)**: `materials.description` nullable text — a
  per-material description written from the text-file dialog (create) and the
  material page's edit mode (`PATCH /materials/{id}`); whitespace-only
  normalizes to NULL. Downgrade drops the column.
- **0051 (plan 51, ADR-125)**: item-level Elo — `item_stats.rating` +
  `item_stats.rating_count` (nullable; seeded lazily from the question's
  difficulty) and the new `concept_skill_ratings` table
  (profile_id/concept/skill unique, `rating`/`rating_count`) for the student's
  per-cell rating — kept separate from `concept_skill_stats` because
  materialize deletes-and-rebuilds that table. Downgrade drops both.
- **0049 (plan 47, ADR-104)**: `materials.duration_sec` + `materials.bitrate_kbps`
  nullable columns — read with mutagen at upload for audio/video materials
  (no ffmpeg, containers pass through to the provider). Downgrade drops both.
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
