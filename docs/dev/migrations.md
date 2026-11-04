# Migrations

Study Assistant's schema is SQLAlchemy 2 models managed by Alembic on a single
linear revision chain. **Migrations are an entrypoint/ops responsibility
(ADR-0028, plan 20 Phase 4) — `create_app` never runs them**: the desktop
entrypoint (`app/local.py:run_migrations`, via `python -m studyassistant`),
the docker one-shot `migrate` service (`entrypoint.sh migrate`, owner role),
`scripts/run-dev.sh`, and the test fixtures each apply
`alembic upgrade head` explicitly. Every migration must have a tested
downgrade. This page is the working discipline; the tables themselves are
documented in [data-model.md](data-model.md), whose "Migration notes" section
records each revision.

## Forward policy (ADR-196, plan 81 F)

The schema is **one squashed baseline plus forward-only history** from here:

- **Model-first, always.** Edit `backend/app/domain/models/`, then write the
  revision to match. The model⇄DB drift gate (`tests/test_model_db_drift.py`)
  fails any database shape the models do not declare. The first forward
  revision after the baseline is `0002_vocab_sweep` (plan 82 C): the model
  gained `questions.type` / `exercises.kind` CHECK twins and the revision
  adds them, on SQLite through `batch_alter_table(recreate="always")`.
- **One migration per change, batched per round.** A feature round lands its
  schema changes in one revision per logical change (not one per day, not a
  grab-bag). Parallel worktrees renumber onto the new head before committing.
- **No compatibility layers — ever.** No `*_legacy` columns, no defaulted
  copy columns, no renamed-forward views, no deprecation windows, no
  back-fill-then-remove two-step when the old shape can simply be dropped.
  There are no deployed databases to protect and no second writer to keep
  alive (the no-legacy doctrine; constitution §8). If a type/shape cut cannot
  be done in place, **squash from the models** (the baseline pattern) and
  rebuild dev databases.
- **Shape changes land with the feature that needs them.** No speculative
  columns or tables "for later" (then they are dead schema — see E).
- **The schema-lint wall is the floor, not the goal.** Every constraint is
  named, every closed-set column has its CHECK twin in the same commit that
  changes the enum, every FK names its `ON DELETE`, every JSON/lifecycle
  table is inventoried, and the model⇄DB plus inventory drift gates stay
  green. A migration that bypasses the wall is not done.
- **Downgrade is still required** — except for a declared destructive
  baseline squash (below).

## Revision scheme

The chain starts at the squashed **`0001_baseline`** (plan 81 F). New
revisions are files in `backend/alembic/versions/` named `00NN_slug.py`,
where **`NN` is the current head number + 1** (after `0001_baseline` comes
`0002_…`). `revision = "00NN_slug"` and `down_revision` is the previous
head's id string. The chain is **linear** — no branches, no merge revisions.

## Model-first changes

`backend/app/domain/models/` is the single source of truth, a package split by
area (`core.py`, `content.py`, `study.py`, `chat.py`, `ops.py`) re-exported by
its `__init__`. Add or edit the column in the domain file that fits, then
generate the migration (`alembic revision --autogenerate`, then review every
line) or write it by hand to match. `0001_baseline` was generated this way
from the post-A–E models: it is not edited to carry new work — new revisions
chain onto it.

## Required downgrade

Every migration implements `downgrade()`. New tables are dropped; new columns
are dropped; data migrations reverse best-effort. Downgrades are tested.

**One sanctioned exception — a declared destructive baseline squash**
(the family migration rules, §3). `0001_baseline`'s `downgrade()` restores an *empty*
schema (it drops every table) instead of a previous chain shape; the header,
[data-model.md](data-model.md) and ADR-196 declare it. Every revision after
the baseline stays under the normal rule.

## Closed sets are database contracts

A `StrEnum` in `backend/app/core/vocab.py` used as a column value has a CHECK
twin on the model (`schema_contract.vocab_check("<column>", Enum)`) and a row
in `schema_contract.CLOSED_SETS`. Adding a member means changing the enum, the
CHECK, and adding a migration **in the same commit** — otherwise inserts of the
new value fail at runtime while the Python code happily produces them
(the family migration rules, §5b). The metadata `naming_convention` renders
`ck_<table>_<column>_allowed`; `op.drop_constraint` takes the short
`"<column>_allowed"` form.

## Named constraints

`Base.metadata` carries an `ix_/uq_/ck_/fk_/pk_` naming convention, so every
constraint created from the models is named and can be dropped by name. When
writing a migration by hand against an *older* database, remember constraints
created before the convention are still unnamed on SQLite — that is why FK
swaps rebuild the table (below).

## Data migrations

When a revision transforms existing rows (rewrites a vocabulary, backfills a
column), the test seeds the **previous revision's shape**, upgrades, and
asserts the transform. From `0002` onward that is the normal pattern. Against
`0001_baseline` there is no lower revision, so the pre-squash legacy-data
tests were reworked into baseline shape/round-trip tests (for example
`tests/test_phase8a_materials.py::test_baseline_has_no_legacy_chapter_schema`
and `tests/test_byok_migration.py::test_baseline_byok_shape_round_trip`); the
data transforms themselves (orphan backfills, vocabulary rewrites) no longer
exist because the baseline only ever creates the final shape.

## Head assertion

The head revision is pinned in **one** place — bump it when a new revision
lands:

- `backend/tests/migration_head.py::HEAD_REVISION` (the constant)
- asserted by `backend/tests/test_baseline_migration.py::test_migration_head_is_latest`

Do not add literal revision ids to tests. Revision-pinned tests were reworked
to import the constant and exercise baseline round-trips/downgrades
(`test_scope_lifecycle_migration`, `test_payload_law_migration`,
`test_vocab_checks_migration`, `test_uuid_identity_migration`, …). Tests that
derive the head from the script directory (`test_migrations_postgres`) need no
edit on a new revision.

## SQLite pitfalls

These have all caused real bugs; check for them when writing a migration:

- **Migrated template cache is schema-hash keyed.** `tests/conftest.py` names
  the cached migrated template `migrated_template_<schema-hash>.db`, where the
  hash covers `alembic/versions/*.py`, the model package, `core/vocab.py`,
  `schema_contract.py` and `storage/db.py`. A schema change therefore builds a
  new template automatically — the old "delete
  `/tmp/pytest-of-<user>/migrated_template.db*`" ritual is gone. If you ever
  see a `no such table` after a model edit that is not a revision, the hash
  inputs are incomplete; fix the fingerprint, do not delete files by hand.
- **SQLAlchemy JSON in-place edits vanish.** Mutating a dict/list loaded from a
  JSON column and reassigning an equal value is a no-op. Call
  `flag_modified(obj, "col")` after in-place edits, or assign a genuinely new
  structure.
- **SQLite stores datetimes naive** while in-memory ORM copies are tz-aware.
  Normalize both sides of any comparison against a client-supplied timestamp
  (`_utc_naive` in `app/api/notes.py` is the pattern).
- **SQLite FKs are unnamed on pre-convention databases**, so
  `batch_alter_table` cannot swap them there. The baseline creates every FK
  named; for a database rebuilt from the baseline, `batch_alter_table` works.
  Migration `0026` (history, now folded into the baseline) is the raw-DDL
  worked example if a legacy path ever needs it.
- **Partial indexes** need `sqlite_where=text("col = 1")` (see the `tree_nodes`
  root index). Composite placement FKs follow the `(node_id, course_id)`
  `ForeignKeyConstraint` pattern.
- **JSON columns** store arbitrary lists/dicts; guard with `isinstance(x, dict)`
  before `.get()`.

## Empty-database rule

`alembic upgrade head` on an empty database builds the entire schema in
`0001_baseline` (tables, constraints, indexes, FTS/tsvector twins, seeded
decision slots) and `alembic downgrade base` drops it cleanly — both are
proven by `tests/test_baseline_migration.py` and the model⇄DB drift gate. Any
new revision must keep the fresh-DB path green (CI and app startup both run
it): verify against a fresh database, not only an upgraded one.

**Pre-baseline databases are rebuilt, not migrated.** No data-migration
tooling exists for the deleted chain (ADR-196, non-goal): delete the SQLite
file and reseed (`scripts/seed-demo.py`), or re-provision the PostgreSQL
database.

## PostgreSQL chain (plan 51 Q3c1)

The chain is green from `0001_baseline` to
`0017_vector_token_schema` on PostgreSQL 16 + pgvector. `tests/test_migrations_postgres.py` creates a
scratch database, upgrades the whole chain and asserts the result whenever
`SA_TEST_DATABASE_URL` points at a disposable server; it skips only when the
variable is unset (the SQLite suite always runs). The repaired pre-0012
history is dialect-portable without changing any final schema shape:

- **Boolean server defaults** — the baseline shipped
  `server_default=text("0")` (and bare `"0"`) on `courses.hidden`,
  `material_sources.mirror_subdirs`, `chat_sessions.quizme`,
  `chat_quiz_pendings.awaiting_answer` and `materials.starred`;
  `0009_calendar_links` shipped `text("1")` on `calendar_links.enabled`.
  PostgreSQL rejects `BOOLEAN DEFAULT 0` at `CREATE TABLE`, so a fresh
  upgrade failed on `courses`. They now use SQLAlchemy `sa.false()` /
  `sa.true()` (rendered as `0`/`1` on SQLite, `false`/`true` on PostgreSQL).
  The model declarations use the matching `false()` / `true()`.
- **Decision-slot seed** — `0001_baseline` reused one bind parameter in an
  `INSERT … SELECT` target and its `WHERE NOT EXISTS` predicate; PostgreSQL
  deduced `text` vs `character varying` and rejected the statement with
  `AmbiguousParameter`. Both occurrences cast to `VARCHAR(40)`.
- **`batch_alter_table(recreate="always")`** — 0002/0003/0004/0006/0007/
  0008/0009/0010/0011 force-recreated tables on every dialect. On PostgreSQL
  that copy drops the primary key while dependent foreign keys still
  reference it (`DependentObjectsStillExist`). Each revision now uses a local
  `_recreate_mode()`: `"always"` on SQLite (which needs the copy), `"auto"`
  on PostgreSQL (alter in place). The SQLite path and every final schema are
  unchanged.

`tests/test_migrations_postgres.py` pins the repaired defaults, the seeded
decision slots, and a full 0011→0012 round-trip over a real legacy store
(`vec_meta` + `chunk_vecs` + `chunk_vec_ids`): the `content` space row,
document/record backfill shape, rowid parity, content hashes, absence of a
fabricated coverage snapshot, model/dim agreement with `vec_meta`, the Q3b
partial indexes, and a downgrade/upgrade that leaves `chunk_vecs` intact.

## Vector-space provisioning (plan 51 Q3c2a)

`0013_vector_space_provisioning` performs the one-time physical move from the
legacy `chunk_vecs` store to the provisioned `vec_<8hex>` table:

- PostgreSQL creates the `vector` extension when available, then
  `vec_<8hex> (record_id UUID PRIMARY KEY REFERENCES vector_records(id) ON
  DELETE CASCADE, embedding vector(dim) NOT NULL)` plus
  `ix_<table>_hnsw USING hnsw (embedding vector_cosine_ops)`. HNSW supports
  at most 2,000 dimensions; a larger space is left on the legacy store.
- SQLite loads `sqlite-vec` defensively and creates
  `vec_<8hex> USING vec0(record_rowid INTEGER PRIMARY KEY, embedding
  float[dim] distance_metric=cosine)`. `vector_records.rowid` is the rowid
  map; no second mapping table exists.
- The copy is `chunk_vecs ⨝ chunk_vec_ids ⨝ vector_records`, keyed by record
  identity. The new table's row count is verified before
  `vector_spaces.index_table` is updated, all inside the migration
  transaction; a failed copy leaves both the pointer and the legacy tables
  untouched.
- `chunk_vecs` / `chunk_vec_ids` are never dropped or rewritten. Downgrade
  drops the provisioned table(s) and resets `index_table = 'chunk_vecs'`.

The naming rule is frozen in the migration (a migration must not import
application code) and shares its shape with
`storage/vector_schema.index_table_name`: eight lowercase hex characters
derived from the space id (`vec_dfbcce9b` for `legacy-chunk-vecs`). The
migration tests pin both the table name and the copied rows.

## Retrieval alerts and generation tags (plan 51 Q3c3a)

`0015_retrieval_alerts` adds the ledger's `metadata`/`metadata_schema_version`
columns and the two notification-funnel tables. The `metadata` column is
non-null with a `{}` server default; the notification dedup key is a partial
unique index over `dedup_key IS NOT NULL`. Both the SQLite round-trip
(`tests/test_retrieval_ops_migration.py`) and the PostgreSQL chain
(`tests/test_migrations_postgres.py`) pin the columns, tables, foreign key and
partial index, including downgrade/upgrade. A revision id longer than 32
characters would overflow Alembic's `alembic_version.version_num` on
PostgreSQL; the short `0015_retrieval_alerts` id is deliberate.

## Stored space key + token schema (plan 52 T5b1)

`0016_vector_space_stored_key` adds `vector_spaces.space_key` and stamps every
populated row once with the frozen v1 pre-image (the hash is inlined in the
migration, as Career's `0095` does), then enforces NOT NULL. SQLite uses
`batch_alter_table`; PostgreSQL alters the column in place. `0017_vector_token_schema`
adds the nullable tokenizer/chunk columns to `vector_spaces` and the nullable
token offsets to `vector_records`, with all-or-none/kind/provenance/bounds/
`chunker_version='2'` and ordered/consistent-token CHECKs. Both migrations are
covered by populated SQLite round-trips
(`tests/test_vector_space_token_migration.py`) and the PostgreSQL chain
(`tests/test_migrations_postgres.py`), including the deliberate downgrade
asymmetry: 0017 drops its token columns but keeps the stored `space_key`.
Revision ids stay under 32 characters.

## Vector record chunk identity (plan 51 Q3c2b1)

`0014_vector_record_chunk_id` adds
`vector_records.chunk_id` (nullable `String(80)`), an index and the unique
`(space_id, chunk_id)` constraint, then backfills `chunk_id = id` for the
legacy `legacy-chunk-vecs` space. The global record primary key can no longer
be the chunk id once a building space coexists with the active one; `chunk_id`
is the space-local hydration handle the search path uses, while the record id
is the deterministic `uuid5(space, chunk)` and `rowid` is the sqlite-vec rule
over it. Downgrade drops the constraint/index/column; record rows are kept.
The migration is part of the same single linear chain and is covered by the
SQLite and PostgreSQL round-trip tests.

## Concurrent sessions (worktree renumbering)

When two branches each add a revision, the later branch is renumbered onto the
single chain before merge: bump its `NN`, repoint its `down_revision` to the
other branch's id, and update the head-assertion tests. Merge back
fast-forward-only (see [development.md](development.md)).

## Docs in the same commit

Add a `- **00NN (plan/ADR ref)**: what changed` entry to the "Migration notes"
section of [data-model.md](data-model.md), and update `docs/STATUS.md`. The
plan's as-built section lives in the internal planning record (family dev
`projects/study-assistant/plans/`) and never ships.

## Verify

```bash
cd backend && ruff check . && mypy . && pytest
```

Red means fix it before committing — a migration that breaks the head-assertion
tests or the round-trip test is not done.
