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
  fails any database shape the models do not declare.
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
(family-migration §3). `0001_baseline`'s `downgrade()` restores an *empty*
schema (it drops every table) instead of a previous chain shape; the header,
[data-model.md](data-model.md) and ADR-196 declare it. Every revision after
the baseline stays under the normal rule.

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
  hash covers `alembic/versions/*.py`, the model package,
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
