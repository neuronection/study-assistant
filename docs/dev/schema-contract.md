# Schema contract

What the database guarantees, in one place. Two halves:

- **The law** (below) — identity, closed sets, time, payload, scope and lifecycle rules. Written by hand.
- **The inventory** (bottom) — generated from `backend/app/domain/models/` by
  `scripts/schema_inventory.py`, so it cannot drift from the models.

Regenerate after any model change:

```bash
cd backend && uv run python ../scripts/schema_inventory.py --write
```

CI runs the same script with `--check`; a stale inventory is a red gate. The
hand-written facts the metadata cannot express (closed sets and their StrEnum
home, JSON species, profile scope paths) live in
`backend/app/domain/schema_contract.py`, and `tests/test_schema_contract.py`
proves every entry names a real table/column and that nothing is unclassified.

**Enforcement status (plan 81):** A — inventory generated and drift-guarded.
B — named constraints + CHECK twins: enforced and wall-tested. C — UUID
identity: landed (folded into `0001_baseline`). D — payload law: landed — typed
state out of JSON, versioned content documents, TypedDict registry, JSONB
verdict inventory, and the model⇄DB drift gate. E — dead schema + scope &
lifecycle law: landed — `material_groups`/`materials.group_id` removed,
`skill_versions.scope_ref` typed as UUID, lifecycle inventory + single-tombstone
rule, nullable-unique law. F — the chain is one squashed `0001_baseline`
regenerated from these models (ADR-196); this document describes that
baseline, and the pre-squash revision numbers below are history.

## Identity law (ADR-198)

- `users`, `profiles` and **every user-data entity** use a UUID primary key
  (`Uuid(as_uuid=False)`: canonical dashed strings in Python, `CHAR(32)` hex on
  SQLite, native `uuid` on PostgreSQL).
- Rows keyed by nature keep their natural key: `blobs.sha256`,
  `task_assignments.task`, `default_task_assignments.requires`,
  `study_goals.profile_id`, `material_index_cards.material_id`, and the
  `(course_id, task)` assignment tables.
- Catalogue/config tables (`course_types`, `error_patterns`, `skills`,
  `skill_versions`, `providers`, `models`) are **not** user content and are not
  exported in course bundles; their surrogate keys are UUIDs too (ADR-198
  retyped them), while the rows are seeded config. Every FK that points at a
  UUID entity is UUID-typed.
- Polymorphic references (`notes.owner_id`, `chat_messages.parent_id`,
  `ai_interactions.context_id`, `skill_versions.scope_ref`) are UUID strings
  too, because their targets are UUID rows. `skill_versions.scope_ref` was the
  one column the identity cut missed (typed `Integer` while its values are
  `courses.id`/`course_types.id`); 0075 retypes it.

## Closed sets (ADR-197)

A column whose values come from a `StrEnum` in `backend/app/core/vocab.py` is a
closed set and carries a database `CHECK` mirroring the enum members
(`ck_<table>_<column>_allowed`, short name `"<column>_allowed"` for
`op.drop_constraint`). The enum and its CHECK land in the **same commit** —
widening a vocabulary without widening the CHECK makes inserts fail at runtime
(family-migration §5b).

Adding a new closed-set column means: StrEnum member → `schema_contract.CLOSED_SETS`
entry → `CheckConstraint` on the model → migration → inventory regeneration.

## Temporal & attribution law (ADR-199)

- One clock: `app.domain.models.core.utcnow` (`datetime.now(UTC)`). Never
  `datetime.utcnow()`, never a DB-side `now()` default — a second clock source
  forks truth in a single-writer local-first app.
- Every row carries `created_at` (`DateTime(timezone=True)`). Mutable documents
  add `updated_at` (`onupdate=utcnow`). Usage surfaces add
  `last_used_at`/`last_opened_at` (nullable, touched at use).
- **SQLite stores naive datetimes**; anything compared against a
  client-supplied value is normalized on both sides (`_utc_naive` in
  `app/api/notes.py` is the pattern). Never compare an aware in-memory value to
  a stored one directly.

## Payload law (ADR-200)

JSON columns have exactly one of three species, recorded per column in
`schema_contract.JSON_SPECIES`:

- **document** — the canonical block/stroke content format (`body`, `blocks`,
  `strokes`, `stem`, `options`, `prompt`, `response`, `feedback`,
  `ocr_blocks`, citations): legitimately open-shaped, stays JSON.
- **state** — known-shape application state. Queryable state becomes typed
  columns/tables; the remainder is typed by a `TypedDict`/pydantic model at the
  write boundary and validated at the API edge.
- **list** — a typed JSON array of scalars or ids (`tags`, `goals`,
  `objectives`, `concept_ids`).

The law in practice (0074, ADR-200):

- Every JSON column has a **named payload type** in
  `backend/app/domain/payloads.py` (`PAYLOAD_TYPE_NAMES`); the schema wall
  proves the registry covers exactly the JSON columns and that each model
  annotation names its registered type.
- The canonical content documents (`notes.body`, `note_versions.body`,
  `chat_messages.blocks`, `extractions.blocks`, drawing `strokes`/`ocr_blocks`)
  carry a `<column>_schema_version` sibling; every ORM write is validated by
  `backend/app/domain/documents.py` (`DocumentShapeError` is the typed error).
- Known-shape state that the app queries is typed out: proposal target/snapshot
  columns + `chat_proposal_anchors`, `chat_sessions.quiz_pending` →
  `chat_quiz_pendings`, drawing `view` → `view_x`/`view_y`/`view_width`/
  `view_height`. The per-action proposal instruction document and the
  polymorphic proposal outcome map stay JSON behind their schema versions and
  are validated by `backend/app/domain/proposal_contract.py`.
- Classification is declared per column in
  `contracts/data-model.jsonb-inventory.txt` (`keep-open | typed-out`); typed-out
  rows record where the state went. The wall rejects a stale keep-open row and
  a typed-out row that still names a live JSON column.
- In-place edits of a JSON value need `flag_modified(obj, "column")` — assigning
  an equal-valued structure is not a change and silently does not persist.

## Scope & lifecycle law (ADR-201)

- **Every mapped table has one lifecycle class** in
  `contracts/data-model.lifecycle.txt` (`record | operational | transient`),
  gate-checked by D6 and by `tests/test_lifecycle_inventory.py`:
  `record` is retained with the subject and erased only with it;
  `operational` has bounded retention (telemetry, logs, blobs, trash);
  `transient` is prunable at any time (auth sessions, pending quiz state, jobs).
- **`deleted_items` is the only tombstone surface** (`operational`). Deletion
  of a user-visible entity snapshots it there (plan 77-F: row-only restore on
  the immortal blob store) and then hard-deletes; no other table carries
  `deleted_at` or `is_deleted`, and no query filters soft-deleted rows.
- Every user-data table is profile-scoped either by its own `profile_id` or by a
  documented derivation path through its parent (see the Profile scope column;
  the registry is `schema_contract.PROFILE_SCOPE`). Tables that are not user
  data declare why: `catalogue`, `instance`, `identity`, or `operational`
  (for example `ai_interactions` is instance AI telemetry, `jobs` is queue
  state; neither holds a user-content record). A new table without an entry is
  a contract violation.
- Hard delete is purge-only and cascade-complete: deleting a course leaves no
  rows outside `blobs` and `deleted_items` snapshots. The sweep test
  (`tests/test_purge_cascade.py`) seeds one row in every course-scoped table,
  purges, and asserts every table returns to its baseline.
- **Nullable-unique law (constitution §9).** Business-law uniqueness lives in
  the DB. Where a nullable column is part of the key, plain `UNIQUE` lets
  duplicate NULL keyed rows through on SQLite and PostgreSQL, so a partial
  `… WHERE scope_ref IS NULL` index supplies the SQLite equivalent of
  PostgreSQL's `UNIQUE NULLS NOT DISTINCT` (`skill_versions` global scope).
  Remaining nullable keys are intentionally NULL-distinct and documented here:
  `users(oidc_issuer, oidc_subject)` (local users have neither),
  `material_folders.source_id` (local folders have none), and
  `materials(course_id, source_url_norm)` (its partial index already excludes
  NULL).

## Trash TTL

`deleted_items.purge_after` is the restore deadline (7 days); the pruning job
hard-deletes expired snapshots.

## Inventory

<!-- schema-inventory:start -->
<!-- generated by scripts/schema_inventory.py — do not edit by hand (71 tables) -->

| Table | Identity | Profile scope | Foreign keys | Closed sets (CHECK) | JSON columns (species) | Indexes & checks |
|---|---|---|---|---|---|---|
| `activities` | `id` CHAR(32) | profile_id | `course_id`→`courses.id` ON DELETE CASCADE (fk_activities_course_id)<br>`course_id`→`tree_nodes.course_id`, `node_id`→`tree_nodes.id` ON DELETE CASCADE (fk_activities_node_id_course_id)<br>`profile_id`→`profiles.id` ON DELETE CASCADE (fk_activities_profile_id) | — | `config` (state)<br>`generated_from` (state) | `ix_activities_course_id`(course_id)<br>`ix_activities_profile_id`(profile_id) |
| `ai_interactions` | `id` CHAR(32) | operational (instance AI telemetry, no user-content record) | — | — | — | `ix_ai_interactions_context`(context_type, context_id)<br>`ix_ai_interactions_task`(task) |
| `answers` | `id` CHAR(32) | attempt_id → attempts → activities.profile_id | `attempt_id`→`attempts.id` ON DELETE CASCADE (fk_answers_attempt_id)<br>`question_id`→`questions.id` ON DELETE CASCADE (fk_answers_question_id) | — | `error_tags` (list)<br>`feedback` (document)<br>`help_events` (document)<br>`response` (document) | `ix_answers_attempt_id`(attempt_id)<br>`ix_answers_question_id`(question_id) |
| `attempts` | `id` CHAR(32) | activity_id → activities.profile_id | `activity_id`→`activities.id` ON DELETE CASCADE (fk_attempts_activity_id) | `mode` → AttemptMode | `meta` (state) | `ix_attempts_activity_id`(activity_id)<br>CHECKs: `ck_attempts_mode_allowed`: mode IN ('practice', 'exam') |
| `audit_events` | `id` CHAR(32) | identity | — | — | — | `ix_audit_events_action`(action)<br>`ix_audit_events_created_at`(created_at)<br>`ix_audit_events_tenant_id`(tenant_id) |
| `auth_sessions` | `id` CHAR(32) | identity | `user_id`→`users.id` ON DELETE CASCADE (fk_auth_sessions_user_id) | — | — | `ix_auth_sessions_user_id`(user_id) |
| `blobs` | `sha256` VARCHAR(64) | global content-addressed store | — | — | — | — |
| `calendar_event_links` | `id` CHAR(32) | link_id → calendar_links → courses.profile_id | `link_id`→`calendar_links.id` ON DELETE CASCADE (fk_calendar_event_links_link_id) | — | — | `ix_calendar_event_links_link_id`(link_id)<br>`ix_calendar_event_links_local`(link_id, local_id)<br>`uq_calendar_event_links_link_uid`(link_id, uid) [unique] |
| `calendar_links` | `id` CHAR(32) | course_id → courses.profile_id | `course_id`→`courses.id` ON DELETE CASCADE (fk_calendar_links_course_id)<br>`profile_id`→`profiles.id` ON DELETE CASCADE (fk_calendar_links_profile_id) | — | `options` (state)<br>`scopes` (list) | `ix_calendar_links_course_id`(course_id)<br>`ix_calendar_links_profile`(profile_id)<br>`ix_calendar_links_profile_id`(profile_id)<br>`uq_calendar_links_course_calendar`(course_id, provider, calendar_id) [unique]<br>CHECKs: `ck_calendar_links_direction_allowed`: direction IN ('push', 'pull', 'two-way')<br>`ck_calendar_links_status_allowed`: status IN ('ok', 'degraded', 'failing', 'stale', 'needs-auth', 'needs-secret') |
| `chat_messages` | `id` CHAR(32) | session_id → chat_sessions.profile_id | `session_id`→`chat_sessions.id` ON DELETE CASCADE (fk_chat_messages_session_id) | — | `blocks` (document)<br>`citations` (document)<br>`mentions` (state)<br>`reads` (state)<br>`state` (state)<br>`tool_calls` (state)<br>`trace` (state)<br>`warnings` (list) | `ix_chat_messages_parent_id`(parent_id)<br>`ix_chat_messages_session_id`(session_id) |
| `chat_proposal_anchors` | `position` INTEGER, `proposal_id` CHAR(32) | proposal_id → chat_proposals → chat_messages → chat_sessions.profile_id | `proposal_id`→`chat_proposals.id` ON DELETE CASCADE (fk_chat_proposal_anchors_proposal_id) | `op` → ProposalAnchorOp | — | `ix_chat_proposal_anchors_proposal`(proposal_id, position)<br>CHECKs: `ck_chat_proposal_anchors_op_allowed`: op IN ('replace', 'append', 'prepend') |
| `chat_proposals` | `id` CHAR(32) | message_id → chat_messages → chat_sessions.profile_id | `message_id`→`chat_messages.id` ON DELETE CASCADE (fk_chat_proposals_message_id)<br>`target_node_id`→`tree_nodes.id` ON DELETE SET NULL (fk_chat_proposals_target_node_id) | `status` → ChatProposalStatus<br>`target_kind` → ProposalTargetKind | `payload` (state)<br>`result` (state)<br>`target_node_path` (list) | `ix_chat_proposals_message_id`(message_id)<br>CHECKs: `ck_chat_proposals_status_allowed`: status IN ('proposed', 'approved', 'dismissed', 'executed', 'stale', 'conflict')<br>`ck_chat_proposals_target_kind_allowed`: target_kind IS NULL OR target_kind IN ('note', 'material', 'concept', 'link') |
| `chat_quiz_pendings` | `session_id` CHAR(32) | session_id → chat_sessions.profile_id | `session_id`→`chat_sessions.id` ON DELETE CASCADE (fk_chat_quiz_pendings_session_id) | `verdict` → QuizVerdict | `accept` (list)<br>`choices` (list) | CHECKs: `ck_chat_quiz_pendings_verdict_allowed`: verdict IS NULL OR verdict IN ('correct', 'incorrect') |
| `chat_sessions` | `id` CHAR(32) | profile_id | `course_id`→`courses.id` ON DELETE CASCADE (fk_chat_sessions_course_id)<br>`course_id`→`tree_nodes.course_id`, `node_id`→`tree_nodes.id` ON DELETE CASCADE (fk_chat_sessions_node_id_course_id)<br>`profile_id`→`profiles.id` ON DELETE CASCADE (fk_chat_sessions_profile_id) | — | `context` (state)<br>`mention_registry` (state) | `ix_chat_sessions_course_id`(course_id)<br>`ix_chat_sessions_profile_id`(profile_id)<br>`ix_chat_sessions_public_id`(public_id) [unique] |
| `chunks` | `id` CHAR(32) | extraction_id → extractions → materials.profile_id | `extraction_id`→`extractions.id` ON DELETE CASCADE (fk_chunks_extraction_id) | — | — | `ix_chunks_extraction_id`(extraction_id) |
| `concept_links` | `id` CHAR(32) | course_id → courses.profile_id | `course_id`→`courses.id` ON DELETE CASCADE (fk_concept_links_course_id)<br>`from_concept_id`→`concepts.id` ON DELETE CASCADE (fk_concept_links_from_concept_id)<br>`to_concept_id`→`concepts.id` ON DELETE CASCADE (fk_concept_links_to_concept_id) | `relation` → ConceptRelation | — | `ix_concept_links_course_id`(course_id)<br>`uq_concept_links_triple`(from_concept_id, to_concept_id, relation) [unique]<br>CHECKs: `ck_concept_links_relation_allowed`: relation IN ('prereq-of', 'part-of', 'related-to') |
| `concept_skill_ratings` | `id` CHAR(32) | profile_id | `profile_id`→`profiles.id` ON DELETE CASCADE (fk_concept_skill_ratings_profile_id) | — | — | `uq_concept_skill_ratings`(profile_id, concept, skill) [unique] |
| `concept_skill_stats` | `id` CHAR(32) | profile_id | `profile_id`→`profiles.id` ON DELETE CASCADE (fk_concept_skill_stats_profile_id) | — | — | `uq_concept_skill_stats`(profile_id, concept, skill) [unique] |
| `concepts` | `id` CHAR(32) | course_id → courses.profile_id | `course_id`→`courses.id` ON DELETE CASCADE (fk_concepts_course_id) | — | `aliases` (list) | `ix_concepts_course_id`(course_id)<br>`uq_concepts_course_name`(course_id, name) [unique] |
| `course_default_task_assignments` | `course_id` CHAR(32), `requires` VARCHAR(40) | instance | `course_id`→`courses.id` ON DELETE CASCADE (fk_course_default_task_assignments_course_id)<br>`model_id`→`models.id` ON DELETE SET NULL (fk_course_default_task_assignments_model_id) | — | — | — |
| `course_task_assignments` | `course_id` CHAR(32), `task` VARCHAR(40) | course_id → courses.profile_id | `course_id`→`courses.id` ON DELETE CASCADE (fk_course_task_assignments_course_id)<br>`fallback_model_id`→`models.id` ON DELETE SET NULL (fk_course_task_assignments_fallback_model_id)<br>`model_id`→`models.id` ON DELETE SET NULL (fk_course_task_assignments_model_id) | — | — | — |
| `course_types` | `id` CHAR(32) | catalogue | — | — | — | `uq_course_types_key`(key) [unique] |
| `courses` | `id` CHAR(32) | profile_id | `course_type_id`→`course_types.id` ON DELETE SET NULL (fk_courses_course_type_id)<br>`profile_id`→`profiles.id` ON DELETE CASCADE (fk_courses_profile_id) | `origin` → CourseOrigin | `goals` (list)<br>`tags` (list) | `ix_courses_profile_id`(profile_id)<br>`uq_courses_profile_scratch`(profile_id) [unique, partial]<br>CHECKs: `ck_courses_origin_allowed`: origin IN ('manual', 'genesis', 'import', 'scratch') |
| `daily_rollups` | `id` CHAR(32) | profile_id | `profile_id`→`profiles.id` ON DELETE CASCADE (fk_daily_rollups_profile_id) | — | — | `uq_daily_rollups`(profile_id, day) [unique] |
| `default_task_assignments` | `requires` VARCHAR(40) | instance | `fallback_model_id`→`models.id` ON DELETE SET NULL (fk_default_task_assignments_fallback_model_id)<br>`model_id`→`models.id` ON DELETE SET NULL (fk_default_task_assignments_model_id) | — | — | — |
| `deleted_items` | `id` CHAR(32) | profile_id | `profile_id`→`profiles.id` ON DELETE CASCADE (fk_deleted_items_profile_id) | — | `payload` (state) | `ix_deleted_items_profile_id`(profile_id) |
| `error_patterns` | `id` CHAR(32) | catalogue | `course_type_id`→`course_types.id` ON DELETE SET NULL (fk_error_patterns_course_type_id) | — | `detection` (state) | `ix_error_patterns_course_type`(course_type_id)<br>`uq_error_patterns_key`(key) [unique] |
| `exercise_sessions` | `id` CHAR(32) | exercise_id → exercises.profile_id | `exercise_id`→`exercises.id` ON DELETE CASCADE (fk_exercise_sessions_exercise_id) | — | — | `ix_exercise_sessions_exercise_id`(exercise_id) |
| `exercise_steps` | `id` CHAR(32) | exercise_id → exercises.profile_id | `exercise_id`→`exercises.id` ON DELETE CASCADE (fk_exercise_steps_exercise_id) | — | `expected` (document)<br>`hints_pregenerated` (document)<br>`prompt` (document)<br>`rubric` (state) | `ix_exercise_steps_exercise_id`(exercise_id) |
| `exercises` | `id` CHAR(32) | profile_id | `course_id`→`courses.id` ON DELETE CASCADE (fk_exercises_course_id)<br>`course_id`→`tree_nodes.course_id`, `node_id`→`tree_nodes.id` ON DELETE CASCADE (fk_exercises_node_id_course_id)<br>`profile_id`→`profiles.id` ON DELETE CASCADE (fk_exercises_profile_id) | `kind` → ExerciseKind | `context` (document)<br>`created_from` (state) | `ix_exercises_course_id`(course_id)<br>`ix_exercises_external_uid`(external_uid)<br>`ix_exercises_profile_id`(profile_id)<br>CHECKs: `ck_exercises_kind_allowed`: kind IN ('multi_step', 'card_basic', 'card_reverse', 'card_cloze', 'matching', 'ordering', 'categorize', 'fill_blank', 'explain', 'error_spot', 'correct_solution') |
| `external_review_events` | `id` CHAR(32) | source_id → external_sources.profile_id | `source_id`→`external_sources.id` ON DELETE CASCADE (fk_external_review_events_source_id) | — | — | `ix_external_review_events_remote_card`(remote_card_id)<br>`ix_external_review_events_source_id`(source_id)<br>`uq_external_review_events_source_card_time`(source_id, remote_card_id, reviewed_at) [unique] |
| `external_sources` | `id` CHAR(32) | profile_id | `course_id`→`courses.id` ON DELETE CASCADE (fk_external_sources_course_id)<br>`profile_id`→`profiles.id` ON DELETE CASCADE (fk_external_sources_profile_id) | `auth_kind` → AuthKind<br>`kind` → ExternalSourceKind | `cursor` (state)<br>`options` (state) | `ix_external_sources_course_id`(course_id)<br>`ix_external_sources_profile_id`(profile_id)<br>CHECKs: `ck_external_sources_auth_kind_allowed`: auth_kind IN ('token', 'oauth2', 'none')<br>`ck_external_sources_kind_allowed`: kind IN ('rss', 'youtube_channel', 'youtube_playlist', 'site_search', 'webdav_folder', 'cloud_folder', 'zotero_collection', 'anki_deck') |
| `extractions` | `id` CHAR(32) | material_id → materials.profile_id | `material_id`→`materials.id` ON DELETE CASCADE (fk_extractions_material_id) | — | `blocks` (document)<br>`confidence` (state) | `ix_extractions_material_id`(material_id) |
| `fsrs_states` | `id` CHAR(32) | card_id → exercises.profile_id | `card_id`→`exercises.id` ON DELETE CASCADE (fk_fsrs_states_card_id) | — | — | `ix_fsrs_states_card_id`(card_id) [unique] |
| `instance_settings` | `key` VARCHAR(100) | identity | — | — | — | — |
| `item_stats` | `id` CHAR(32) | question_id → questions → activities.profile_id | `question_id`→`questions.id` ON DELETE CASCADE (fk_item_stats_question_id) | `flag` → ItemFlag | `distractor_selection` (state) | `uq_item_stats`(question_id) [unique]<br>CHECKs: `ck_item_stats_flag_allowed`: flag IN ('ok', 'review', 'elo_outlier') |
| `jobs` | `id` CHAR(32) | operational (queue state; instance-level by design, no user-content record) | — | `status` → JobStatus<br>`type` → JobType | `payload` (state)<br>`result` (state) | `uq_jobs_idempotency_active`(type, idempotency_key) [unique, partial]<br>`uq_jobs_lock_key_active`(lock_key) [unique, partial]<br>CHECKs: `ck_jobs_status_allowed`: status IN ('queued', 'running', 'failed', 'done', 'cancelled')<br>`ck_jobs_type_allowed`: type IN ('ingest', 'postprocess', 'chat_turn', 'drawing_ocr', 'image_ocr', 'genesis', 'url_import', 'compose', 'VECTOR_REINDEX', 'VECTOR_MAINTENANCE', 'VECTOR_CUTOVER') |
| `material_drawings` | `id` CHAR(32) | material_id → materials.profile_id | `material_id`→`materials.id` ON DELETE CASCADE (fk_material_drawings_material_id)<br>`png_sha`→`blobs.sha256` ON DELETE RESTRICT (fk_material_drawings_png_sha) | — | `ocr_blocks` (document)<br>`strokes` (document) | `ix_material_drawings_material_id`(material_id) |
| `material_folder_links` | `id` CHAR(32) | course_id → courses.profile_id | `course_id`→`courses.id` ON DELETE CASCADE (fk_material_folder_links_course_id)<br>`course_id`→`tree_nodes.course_id`, `node_id`→`tree_nodes.id` ON DELETE CASCADE (fk_material_folder_links_node_id_course_id)<br>`folder_id`→`material_folders.id` ON DELETE CASCADE (fk_material_folder_links_folder_id) | — | — | `ix_material_folder_links_course_id`(course_id)<br>`ix_material_folder_links_folder_id`(folder_id)<br>`ix_material_folder_links_node`(node_id)<br>`uq_material_folder_links_node`(node_id, folder_id) [unique] |
| `material_folders` | `id` CHAR(32) | profile_id | `course_id`→`courses.id` ON DELETE CASCADE (fk_material_folders_course_id)<br>`parent_id`→`material_folders.id` ON DELETE CASCADE (fk_material_folders_parent_id)<br>`profile_id`→`profiles.id` ON DELETE CASCADE (fk_material_folders_profile_id)<br>`source_id`→`material_sources.id` ON DELETE CASCADE (fk_material_folders_source_id) | — | — | `ix_material_folders_course_id`(course_id)<br>`ix_material_folders_parent_id`(parent_id)<br>`ix_material_folders_profile_id`(profile_id)<br>`uq_material_folders_profile_course_path`(profile_id, course_id, path) [unique]<br>`uq_material_folders_source_id`(source_id) [unique] |
| `material_images` | `id` CHAR(32) | material_id → materials.profile_id | `blob_sha`→`blobs.sha256` ON DELETE RESTRICT (fk_material_images_blob_sha)<br>`material_id`→`materials.id` ON DELETE CASCADE (fk_material_images_material_id) | — | — | `ix_material_images_material_id`(material_id) |
| `material_index_cards` | `material_id` CHAR(32) | material_id → materials.profile_id | `material_id`→`materials.id` ON DELETE CASCADE (fk_material_index_cards_material_id) | — | `key_terms` (list)<br>`topics` (list) | — |
| `material_links` | `id` CHAR(32) | course_id → courses.profile_id | `course_id`→`courses.id` ON DELETE CASCADE (fk_material_links_course_id)<br>`course_id`→`tree_nodes.course_id`, `node_id`→`tree_nodes.id` ON DELETE CASCADE (fk_material_links_node_id_course_id)<br>`extraction_id`→`extractions.id` ON DELETE CASCADE (fk_material_links_extraction_id)<br>`material_id`→`materials.id` ON DELETE CASCADE (fk_material_links_material_id) | — | — | `ix_material_links_course_id`(course_id)<br>`ix_material_links_material_id`(material_id)<br>`ix_material_links_node`(node_id)<br>`uq_material_links_node`(node_id, material_id) [unique] |
| `material_sources` | `id` CHAR(32) | profile_id | `course_id`→`courses.id` ON DELETE CASCADE (fk_material_sources_course_id)<br>`profile_id`→`profiles.id` ON DELETE CASCADE (fk_material_sources_profile_id) | `preset` → SourcePreset | `include_globs` (list) | `ix_material_sources_profile_id`(profile_id)<br>CHECKs: `ck_material_sources_preset_allowed`: preset IN ('folder', 'vault') |
| `material_study_state` | `id` CHAR(32) | profile_id | `material_id`→`materials.id` ON DELETE CASCADE (fk_material_study_state_material_id)<br>`profile_id`→`profiles.id` ON DELETE CASCADE (fk_material_study_state_profile_id) | `status` → StudyStatus | — | `ix_material_study_state_material_id`(material_id)<br>`ix_material_study_state_profile_id`(profile_id)<br>`uq_material_study_state`(material_id, profile_id) [unique]<br>CHECKs: `ck_material_study_state_status_allowed`: status IN ('unread', 'reading', 'studied') |
| `material_suggestions` | `id` CHAR(32) | profile_id | `course_id`→`courses.id` ON DELETE CASCADE (fk_material_suggestions_course_id)<br>`course_id`→`tree_nodes.course_id`, `node_id`→`tree_nodes.id` ON DELETE CASCADE (fk_material_suggestions_node_id_course_id)<br>`material_id`→`materials.id` ON DELETE CASCADE (fk_material_suggestions_material_id)<br>`profile_id`→`profiles.id` ON DELETE CASCADE (fk_material_suggestions_profile_id) | `kind` → DiscoveryKind<br>`status` → SuggestionStatus | `meta` (state) | `ix_material_suggestions_course_id`(course_id)<br>`ix_material_suggestions_profile_id`(profile_id)<br>`uq_material_suggestions_profile_url`(profile_id, url_norm) [unique]<br>CHECKs: `ck_material_suggestions_kind_allowed`: kind IN ('video', 'course', 'article', 'exercise', 'paper', 'dataset', 'reference', 'other')<br>`ck_material_suggestions_status_allowed`: status IN ('suggested', 'saved', 'dismissed') |
| `materials` | `id` CHAR(32) | profile_id | `blob_sha`→`blobs.sha256` ON DELETE RESTRICT (fk_materials_blob_sha)<br>`course_id`→`courses.id` ON DELETE CASCADE (fk_materials_course_id)<br>`folder_id`→`material_folders.id` ON DELETE CASCADE (fk_materials_folder_id)<br>`profile_id`→`profiles.id` ON DELETE CASCADE (fk_materials_profile_id) | `citation_kind` → CitationKind<br>`kind` → MaterialKind<br>`status` → MaterialStatus | `citation_authors` (list)<br>`provenance` (state)<br>`tags` (list) | `ix_materials_content_hash`(content_hash)<br>`ix_materials_course_id`(course_id)<br>`ix_materials_course_status`(course_id, status)<br>`ix_materials_folder_id`(folder_id)<br>`ix_materials_profile_id`(profile_id)<br>`ix_materials_source_url`(source_url) [partial]<br>`ix_materials_starred`(starred) [partial]<br>`uq_materials_course_source_url_norm`(course_id, source_url_norm) [unique, partial]<br>CHECKs: `ck_materials_citation_kind_allowed`: citation_kind IS NULL OR citation_kind IN ('article', 'book', 'chapter', 'conference', 'preprint', 'thesis', 'report', 'dataset', 'other')<br>`ck_materials_kind_allowed`: kind IN ('pdf', 'image', 'md', 'txt', 'doc', 'docx', 'pptx', 'epub', 'html', 'audio', 'video', 'link')<br>`ck_materials_status_allowed`: status IN ('pending', 'processing', 'ready', 'failed', 'missing') |
| `mistakes` | `id` CHAR(32) | profile_id | `profile_id`→`profiles.id` ON DELETE CASCADE (fk_mistakes_profile_id)<br>`question_id`→`questions.id` ON DELETE CASCADE (fk_mistakes_question_id) | — | `concept_ids` (list)<br>`error_tags` (list) | `ix_mistakes_profile_id`(profile_id)<br>`ix_mistakes_question_id`(question_id) |
| `models` | `id` CHAR(32) | instance | `provider_id`→`providers.id` ON DELETE CASCADE (fk_models_provider_id) | — | `caps` (list) | `ix_models_provider_id`(provider_id)<br>`uq_models_provider_external`(provider_id, external_id) [unique] |
| `node_concepts` | `id` CHAR(32) | node_id → tree_nodes → courses.profile_id | `concept_id`→`concepts.id` ON DELETE CASCADE (fk_node_concepts_concept_id)<br>`node_id`→`tree_nodes.id` ON DELETE CASCADE (fk_node_concepts_node_id) | — | — | `ix_node_concepts_node_id`(node_id)<br>`uq_node_concepts`(node_id, concept_id) [unique] |
| `note_drawings` | `id` CHAR(32) | note_id → notes.profile_id | `note_id`→`notes.id` ON DELETE CASCADE (fk_note_drawings_note_id)<br>`png_sha`→`blobs.sha256` ON DELETE RESTRICT (fk_note_drawings_png_sha) | — | `ocr_blocks` (document)<br>`strokes` (document) | `ix_note_drawings_note_id`(note_id) |
| `note_links` | `id` CHAR(32) | from_note_id → notes.profile_id | `course_id`→`courses.id` ON DELETE CASCADE (fk_note_links_course_id)<br>`from_note_id`→`notes.id` ON DELETE CASCADE (fk_note_links_from_note_id)<br>`profile_id`→`profiles.id` ON DELETE CASCADE (fk_note_links_profile_id)<br>`to_note_id`→`notes.id` ON DELETE CASCADE (fk_note_links_to_note_id) | — | — | `ix_note_links_profile_id`(profile_id)<br>`ix_note_links_to_note`(to_note_id)<br>`uq_note_links_from_target`(from_note_id, target) [unique] |
| `note_versions` | `id` CHAR(32) | profile_id | `note_id`→`notes.id` ON DELETE CASCADE (fk_note_versions_note_id)<br>`profile_id`→`profiles.id` ON DELETE CASCADE (fk_note_versions_profile_id) | — | `body` (document)<br>`tags` (list) | `ix_note_versions_note`(note_id, id)<br>`ix_note_versions_note_id`(note_id)<br>`ix_note_versions_profile_id`(profile_id) |
| `notes` | `id` CHAR(32) | profile_id | `course_id`→`courses.id` ON DELETE CASCADE (fk_notes_course_id)<br>`course_id`→`tree_nodes.course_id`, `node_id`→`tree_nodes.id` ON DELETE CASCADE (fk_notes_node_id_course_id)<br>`profile_id`→`profiles.id` ON DELETE CASCADE (fk_notes_profile_id)<br>`source_id`→`material_sources.id` ON DELETE SET NULL (fk_notes_source_id) | — | `body` (document)<br>`tags` (list) | `ix_notes_content_hash`(content_hash)<br>`ix_notes_node_id`(node_id)<br>`ix_notes_owner`(owner_type, owner_id)<br>`ix_notes_profile_id`(profile_id)<br>`ix_notes_source_id`(source_id) |
| `plan_items` | `id` CHAR(32) | profile_id | `course_id`→`courses.id` ON DELETE CASCADE (fk_plan_items_course_id)<br>`course_id`→`tree_nodes.course_id`, `node_id`→`tree_nodes.id` ON DELETE CASCADE (fk_plan_items_node_id_course_id)<br>`profile_id`→`profiles.id` ON DELETE CASCADE (fk_plan_items_profile_id) | `kind` → PlanItemKind<br>`origin` → PlanItemOrigin | — | `ix_plan_items_course_due`(course_id, due_date)<br>`ix_plan_items_course_id`(course_id)<br>`ix_plan_items_profile_due`(profile_id, due_date)<br>`ix_plan_items_profile_id`(profile_id)<br>`uq_plan_items_course_external_uid`(course_id, external_uid) [unique, partial]<br>CHECKs: `ck_plan_items_kind_allowed`: kind IN ('study', 'practice', 'review', 'milestone', 'exam', 'deadline')<br>`ck_plan_items_origin_allowed`: origin IN ('manual', 'draft', 'calendar') |
| `profiles` | `id` CHAR(32) | own row | `user_id`→`users.id` ON DELETE CASCADE (fk_profiles_user_id) | — | `preferences` (state) | `ix_profiles_user_id`(user_id) |
| `providers` | `id` CHAR(32) | instance | — | — | `status` (state) | — |
| `questions` | `id` CHAR(32) | activity_id → activities.profile_id | `activity_id`→`activities.id` ON DELETE CASCADE (fk_questions_activity_id)<br>`parent_id`→`questions.id` ON DELETE CASCADE (fk_questions_parent_id) | `flag` → ItemFlag<br>`type` → QuestionType | `answer` (document)<br>`concept_ids` (list)<br>`distractor_misconceptions` (state)<br>`explanation` (document)<br>`input_modes` (list)<br>`options` (document)<br>`provenance` (state)<br>`source_refs` (list)<br>`stats` (state)<br>`stem` (document)<br>`sympy_check` (state)<br>`tags` (list) | `ix_questions_activity_id`(activity_id)<br>CHECKs: `ck_questions_flag_allowed`: flag IN ('ok', 'review', 'elo_outlier')<br>`ck_questions_type_allowed`: type IN ('single', 'multi', 'truefalse', 'text', 'numeric', 'equation', 'numberline', 'table_fill', 'composite', 'graph_read', 'code', 'matching', 'ordering', 'cloze', 'essay') |
| `quiz_help_events` | `id` CHAR(32) | attempt_id → attempts → activities.profile_id | `attempt_id`→`attempts.id` ON DELETE CASCADE (fk_quiz_help_events_attempt_id)<br>`question_id`→`questions.id` ON DELETE CASCADE (fk_quiz_help_events_question_id) | — | — | `ix_quiz_help_events_attempt_question`(attempt_id, question_id) |
| `quizme_answers` | `id` CHAR(32) | profile_id | `profile_id`→`profiles.id` ON DELETE CASCADE (fk_quizme_answers_profile_id)<br>`session_id`→`chat_sessions.id` ON DELETE CASCADE (fk_quizme_answers_session_id) | — | — | `ix_quizme_answers_profile_id`(profile_id)<br>`ix_quizme_answers_session_id`(session_id) |
| `retrieval_coverage_snapshots` | `id` CHAR(32) | operational (instance vector coverage aggregate, no user-content record) | — | — | — | `ix_retrieval_coverage_snapshots_space_kind`(space_id, kind, as_of)<br>CHECKs: `ck_retrieval_coverage_snapshots_ann_recall_k_positive`: ann_recall_k IS NULL OR ann_recall_k > 0<br>`ck_retrieval_coverage_snapshots_ann_recall_range`: ann_recall IS NULL OR (ann_recall >= 0 AND ann_recall <= 1)<br>`ck_retrieval_coverage_snapshots_coverage_counts_non_negative`: total >= 0 AND missing >= 0 AND stale >= 0 AND failed >= 0 AND embedded >= 0<br>`ck_retrieval_coverage_snapshots_probe_size_non_negative`: probe_size IS NULL OR probe_size >= 0 |
| `retrieval_query_rollups` | `id` CHAR(32) | operational (instance query-health aggregate, no user-content record) | — | `degraded_reason` → DegradedReason | `latency_histogram` (state) | `ix_retrieval_query_rollups_space_bucket`(space_id, bucket_start)<br>`uq_retrieval_query_rollups_dims`(space_id, kind, bucket_start, bucket_width) [unique]<br>CHECKs: `ck_retrieval_query_rollups_bucket_width_positive`: bucket_width > 0<br>`ck_retrieval_query_rollups_candidates_sum_non_negative`: candidates_sum >= 0<br>`ck_retrieval_query_rollups_count_non_negative`: count >= 0<br>`ck_retrieval_query_rollups_degraded_reason_allowed`: degraded_reason IS NULL OR degraded_reason IN ('provider_unassigned', 'embed_failed', 'index_missing', 'space_mismatch', 'over_cap')<br>`ck_retrieval_query_rollups_zero_results_range`: zero_results >= 0 AND zero_results <= count |
| `review_log` | `id` CHAR(32) | card_id → exercises.profile_id | `card_id`→`exercises.id` ON DELETE CASCADE (fk_review_log_card_id) | — | — | `ix_review_log_card_id`(card_id) |
| `skill_versions` | `id` CHAR(32) | catalogue; course/course_type overrides via scope_ref → courses.id/course_types.id | `skill_id`→`skills.id` ON DELETE CASCADE (fk_skill_versions_skill_id) | — | `contract` (state)<br>`params` (state) | `uq_skill_versions`(skill_id, scope_type, scope_ref, version) [unique]<br>`uq_skill_versions_global`(skill_id, scope_type, version) [unique, partial] |
| `skills` | `id` CHAR(32) | catalogue | — | — | — | `uq_skills_key`(key) [unique] |
| `step_attempts` | `id` CHAR(32) | session_id → exercise_sessions → exercises.profile_id | `session_id`→`exercise_sessions.id` ON DELETE CASCADE (fk_step_attempts_session_id) | — | `feedback` (document)<br>`response` (document)<br>`state` (state) | `ix_step_attempts_session_id`(session_id) |
| `study_goals` | `profile_id` CHAR(32) | profile_id | `profile_id`→`profiles.id` ON DELETE CASCADE (fk_study_goals_profile_id) | `unit` → GoalUnit | — | CHECKs: `ck_study_goals_unit_allowed`: unit IN ('answers', 'minutes') |
| `study_sessions` | `id` CHAR(32) | profile_id | `course_id`→`courses.id` ON DELETE CASCADE (fk_study_sessions_course_id)<br>`profile_id`→`profiles.id` ON DELETE CASCADE (fk_study_sessions_profile_id) | `kind` → StudySessionKind<br>`source` → StudySessionSource | — | `ix_study_sessions_course_id`(course_id)<br>`ix_study_sessions_profile_id`(profile_id)<br>`ix_study_sessions_profile_started`(profile_id, started_at)<br>CHECKs: `ck_study_sessions_kind_allowed`: kind IN ('focus', 'quiz', 'exercise', 'review', 'read', 'note')<br>`ck_study_sessions_source_allowed`: source IN ('timer', 'auto', 'manual') |
| `task_assignments` | `task` VARCHAR(40) | instance | `fallback_model_id`→`models.id` ON DELETE SET NULL (fk_task_assignments_fallback_model_id)<br>`model_id`→`models.id` ON DELETE SET NULL (fk_task_assignments_model_id) | — | `params` (state) | — |
| `tree_nodes` | `id` CHAR(32) | course_id → courses.profile_id | `course_id`→`courses.id` ON DELETE CASCADE (fk_tree_nodes_course_id)<br>`course_id`→`tree_nodes.course_id`, `parent_id`→`tree_nodes.id` ON DELETE CASCADE (fk_tree_nodes_parent_id_course_id) | — | `objectives` (list) | `ix_tree_nodes_course_id`(course_id)<br>`ix_tree_nodes_course_parent`(course_id, parent_id)<br>`uq_tree_nodes_path`(path) [unique]<br>`uq_tree_nodes_root`(course_id) [unique, partial]<br>CHECKs: `ck_tree_nodes_depth`: depth >= 0 AND depth <= 4 |
| `users` | `id` CHAR(32) | identity | — | — | — | `ix_users_email`(email) [unique] |
<!-- schema-inventory:end -->
