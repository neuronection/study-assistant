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

## Revision scheme

- Files live in `backend/alembic/versions/` named `00NN_slug.py`, where
  **`NN` is the current head number + 1** (after `0029_course_exam_date` comes
  `0030_…`).
- `revision = "00NN_slug"` and `down_revision` is the previous head's id
  string. The chain is **linear** — no branches, no merge revisions.

## Model-first changes

`backend/app/domain/models/` is the single source of truth, a package split by
area (`core.py`, `content.py`, `study.py`, `chat.py`, `ops.py`) re-exported by
its `__init__`. Add or edit the column in the domain file that fits, then
generate the migration. Services and routers import models from
`..domain.models`; mypy strict catches anything missed.

## Required downgrade

Every migration implements `downgrade()`. New tables are dropped; new columns
are dropped; data migrations reverse best-effort. Downgrades are tested.

## Closed sets are database contracts

A `StrEnum` in `backend/app/core/vocab.py` used as a column value has a CHECK
twin on the model (`schema_contract.vocab_check("<column>", Enum)`) and a row
in `schema_contract.CLOSED_SETS`. Adding a member means changing the enum, the
CHECK, and adding a migration **in the same commit** — otherwise inserts of the
new value fail at runtime while the Python code happily produces them
(family-migration §5b). The metadata `naming_convention` renders
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
column), the test seeds the **old shape** on a lower revision, upgrades, and
asserts the transform. A worked pattern is
`tests/test_phase8a_materials.py::test_migration_moves_legacy_data_to_unsorted`,
and the recent BYOK vocabulary rewrite is covered by
`tests/test_byok_migration.py` (legacy shape → upgrade → downgrade round-trip).

## Bump the head-assertion test

The literal head revision string is asserted in one file — bump it on every
new revision or the suite goes red:

- `backend/tests/test_profile_identity_migration.py`
  (`test_migration_head_is_latest`)

More files run migrations but pin **mid-chain** revisions (fixed shape
assertions — touch only when that revision's shape or the chain changes;
they become baseline round-trips if the chain is ever squashed):

- `backend/tests/test_course_required.py` (`0019_tree_nodes`, `0065_identity_core`)
- `backend/tests/test_phase8a_materials.py` (`0013_skills`)
- `backend/tests/test_byok_migration.py`, `tests/test_chat_branches_migration.py`,
  `tests/test_search_fuzzy.py`, `tests/test_exercise_kinds_migration.py`

## SQLite pitfalls

These have all caused real bugs; check for them when writing a migration:

- **Stale migrated template.** `tests/conftest.py` caches a migrated template
  database at `/tmp/pytest-of-<user>/migrated_template.db` and rebuilds it only
  when missing, so a non-xdist run can silently test an old schema after you add
  a migration (`no such table: <new_table>`). Delete
  `migrated_template.db*` after adding a revision.
- **SQLAlchemy JSON in-place edits vanish.** Mutating a dict/list loaded from a
  JSON column and reassigning an equal value is a no-op. Call
  `flag_modified(obj, "col")` after in-place edits, or assign a genuinely new
  structure.
- **SQLite stores datetimes naive** while in-memory ORM copies are tz-aware.
  Normalize both sides of any comparison against a client-supplied timestamp
  (`_utc_naive` in `app/api/notes.py` is the pattern).
- **SQLite FKs are unnamed**, so `batch_alter_table` cannot swap them. Rebuild
  the table with raw DDL (`CREATE TABLE …_new`, copy, drop, rename) — migration
  `0026` is the worked example.
- **Partial indexes** need `sqlite_where=text("col = 1")` (see the `tree_nodes`
  root index). Composite placement FKs follow the `(node_id, course_id)`
  `ForeignKeyConstraint` pattern.
- **JSON columns** store arbitrary lists/dicts; guard with `isinstance(x, dict)`
  before `.get()`.

## Empty-database rule

A fresh database must reach the same schema as an upgraded one. Because the app
migrates on startup, tests build from a migrated template; if you add a
revision, verify both a fresh migration and an upgrade from the previous head.

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
