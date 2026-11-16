"""One-shot migrate mode (ADR-0062 v7 §3, ADR-0064 §3-§4).

`docker/entrypoint.sh migrate` runs this module (`python -m app.ops.migrate`);
it is the only place server-side DDL ever happens:

1. resolve the credential tri-state (ADR-0064 §4):
   **split** (owner migrations URL) / **unsplit** (loud warning) / **broken**
   (`SA_DB_SPLIT=1` without a migrations URL → refuse to boot);
2. owner-side provisioning (split only): create/sync the app role, grants,
   `ALTER DEFAULT PRIVILEGES`, and verify-or-create the `vector` / `pg_trgm`
   extensions;
3. preflight the datastore revision (a pre-0.13 volume refuses loudly);
4. Alembic `upgrade head` **as the owner role** (through `app.local` —
   the single migration home);
5. langgraph checkpoint schema setup (DDL — owner role, never the app's);
6. re-grant (split only) and verify the stamped revision is this release's
   head.

The serving process (`serve`) holds only the app DSN:
`SA_MIGRATIONS_DATABASE_URL` must never be present there (the entrypoint
refuses that boot; the compose files never inject it).
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.engine import Connection

SPLIT_MARKER = "SA_DB_SPLIT"
MIGRATIONS_URL_VAR = "SA_MIGRATIONS_DATABASE_URL"
APP_URL_VAR = "SA_DATABASE_URL"
APP_PASSWORD_VAR = "SA_DB_APP_PASSWORD"

# Managed-DB allow-list note (ADR-0064 §3 step 2): Azure `azure_pg_admin` /
# RDS `rds_superuser` must pre-create these; a product owner on a managed
# provider cannot. Self-host: the owner creates them here.
ALLOW_LISTED_EXTENSIONS = ("vector", "pg_trgm")

_TRUTHY = {"1", "true", "yes", "on"}

UNSPLIT_WARNING = (
    "NON-SPLIT DB CONFIGURATION (ADR-0064): no %s and no %s marker — migrations "
    "run against the app URL and the runtime role is not least-privilege. "
    "This install is NOT managed-ready. Adopt the split: set %s (owner DSN) "
    "and %s=1, keep %s on the app role. The unsplit configuration keeps "
    "booting with this warning."
)

# Postgres identifier characters (roles, databases). Anything else refuses —
# DDL statements cannot bind identifiers as parameters.
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


class BrokenSplitError(RuntimeError):
    """`SA_DB_SPLIT=1` without a migrations URL — refuse to boot (no
    silent fallback: the operator asked for the split and misconfigured it)."""


class ProvisioningError(RuntimeError):
    """Owner-side provisioning could not complete (typed, per ADR-0064 §5)."""


@dataclass(frozen=True)
class MigrationPlan:
    """The resolved tri-state (ADR-0064 §4)."""

    state: str  # "split" | "unsplit"
    owner_url: str
    app_url: str | None = None
    warning: str | None = None


def split_requested(environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return env.get(SPLIT_MARKER, "").strip().lower() in _TRUTHY


def resolve_plan(environ: Mapping[str, str] | None = None) -> MigrationPlan:
    """Pure tri-state resolution (unit-tested; no connections)."""
    env = os.environ if environ is None else environ
    migrations_url = (env.get(MIGRATIONS_URL_VAR) or "").strip()
    app_url = (env.get(APP_URL_VAR) or "").strip() or None
    if split_requested(env) and not migrations_url:
        raise BrokenSplitError(
            f"{SPLIT_MARKER}=1 is set but {MIGRATIONS_URL_VAR} is missing — "
            "refusing to boot (ADR-0064 §4: no silent fallback). Set the "
            f"owner DSN in {MIGRATIONS_URL_VAR} or unset {SPLIT_MARKER}."
        )
    if migrations_url:
        warning = None
        if not split_requested(env):
            warning = (
                f"{MIGRATIONS_URL_VAR} is set without the {SPLIT_MARKER}=1 "
                "marker — add the marker so tooling can tell split from unsplit."
            )
        return MigrationPlan("split", migrations_url, app_url, warning)
    warning = UNSPLIT_WARNING % (
        MIGRATIONS_URL_VAR,
        SPLIT_MARKER,
        MIGRATIONS_URL_VAR,
        SPLIT_MARKER,
        APP_URL_VAR,
    )
    return MigrationPlan("unsplit", (env.get(APP_URL_VAR) or "").strip(), app_url, warning)


def _ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ProvisioningError(f"refusing unsafe Postgres identifier: {name!r}")
    return name


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def grant_app_dml(connection: Connection, app_user: str) -> None:
    """The app role's whole privilege set (ADR-0064 §3 steps 1 and 5):
    CONNECT, schema USAGE, DML on existing tables/sequences, and
    `ALTER DEFAULT PRIVILEGES` so every future object the owner creates is
    usable at runtime. Idempotent; safe before and after Alembic."""
    database = str(connection.exec_driver_sql("SELECT current_database()").scalar())
    user = _ident(app_user)
    connection.exec_driver_sql(f'GRANT CONNECT ON DATABASE "{_ident(database)}" TO "{user}"')
    connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO "{user}"')
    connection.exec_driver_sql(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{user}"'
    )
    connection.exec_driver_sql(
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO "{user}"'
    )
    connection.exec_driver_sql(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{user}"'
    )
    connection.exec_driver_sql(f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{user}"')


def ensure_extensions(connection: Connection) -> None:
    """Verify presence first; only a *missing* extension is attempted.

    On managed providers the product owner usually cannot `CREATE EXTENSION`
    (the provider admin does) — a failed attempt must surface as the
    allow-list note, not a raw privilege error (ADR-0064 §3 step 2).
    """
    for extension in ALLOW_LISTED_EXTENSIONS:
        row = connection.exec_driver_sql(
            "SELECT 1 FROM pg_extension WHERE extname = %s", (extension,)
        ).first()
        if row:
            continue
        print(f"==> creating extension '{extension}' (owner)")
        try:
            connection.exec_driver_sql(f"CREATE EXTENSION IF NOT EXISTS {_ident(extension)}")
        except Exception as error:
            raise ProvisioningError(
                f"extension '{extension}' is missing and this role cannot "
                f"create it ({type(error).__name__}). On a managed provider "
                "(Azure: azure_pg_admin, RDS: rds_superuser) allow-list and "
                f"pre-create it — study needs {', '.join(ALLOW_LISTED_EXTENSIONS)}."
            ) from error


def provision_owner_side(connection: Connection, app_user: str, app_password: str) -> None:
    """Create/sync the app role + grants + default privileges + extensions.

    Idempotent; runs on every migrate. The password sync makes rotation a
    re-run of migrate: the operator changes `SA_DB_PASSWORD`, migrate (owner)
    `ALTER ROLE`s the app role, and the app connects with the new secret on
    its next start (ADR-0064 §4's one-release migration path).
    """
    user = _ident(app_user)
    exists = connection.exec_driver_sql(
        "SELECT 1 FROM pg_roles WHERE rolname = %s", (app_user,)
    ).first()
    if exists:
        connection.exec_driver_sql(
            f'ALTER ROLE "{user}" WITH LOGIN PASSWORD {_literal(app_password)}'
        )
    else:
        print(f"==> creating app role '{app_user}' (DML-only)")
        connection.exec_driver_sql(
            f'CREATE ROLE "{user}" WITH LOGIN PASSWORD {_literal(app_password)}'
        )
    grant_app_dml(connection, app_user)
    ensure_extensions(connection)
    _provision_v1_tables(connection)


def _provision_v1_tables(connection: Connection) -> None:
    """Pre-create the dimension-independent v1 vector tables (ADR-0064 §3
    step 3): the write path issues `CREATE TABLE IF NOT EXISTS` for these on
    every store, which the DML-only app role cannot do once the split is
    adopted. The typed dim store (`chunk_vecs`, pgvector) stays with
    provisioning at first use — `storage.vectors.ensure_table` fails typed
    with the operator action when it is missing under the split."""
    from sqlalchemy import text

    connection.execute(
        text("CREATE TABLE IF NOT EXISTS vec_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    )
    connection.execute(
        text(
            "CREATE TABLE IF NOT EXISTS chunk_vec_ids "
            "(rowid BIGINT PRIMARY KEY, chunk_id TEXT NOT NULL UNIQUE)"
        )
    )


# --- the migrate command ---------------------------------------------------


def _preflight_datastore(owner_url: str) -> None:
    """A pre-0.13 volume cannot be upgraded (deliberate schema break)."""
    from sqlalchemy import create_engine, text

    from ..local import known_revisions

    try:
        with create_engine(owner_url).connect() as connection:
            row = connection.execute(text("SELECT version_num FROM alembic_version")).first()
    except Exception:
        return
    if row and row[0] not in known_revisions():
        raise SystemExit(
            "This PostgreSQL volume predates the 0.13 schema and cannot be upgraded.\n"
            "Recreate it with `docker compose down -v` (this deletes the volume), or\n"
            "keep running Study Assistant 0.12.1 against it. No data was changed."
        )


def _run_alembic(owner_url: str) -> None:
    """Alembic as the owner role — through `app.local.migrate_datastore`,
    keeping `app.local` the family's single migration home (C3)."""
    from ..local import migrate_datastore

    migrate_datastore(owner_url)


def _setup_checkpoints(owner_url: str) -> None:
    """langgraph's checkpoint schema is DDL — owner role, provisioned here;
    the app's checkpointer only ever opens what exists."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    async def setup() -> None:
        async with AsyncPostgresSaver.from_conn_string(owner_url.replace("+psycopg", "")) as saver:
            await saver.setup()

    asyncio.run(setup())


def _app_user() -> str:
    return os.environ.get("SA_DB_USER") or "neuronection_study_app"


def stamped_revision(owner_url: str) -> str | None:
    from sqlalchemy import create_engine, text

    try:
        with create_engine(owner_url).connect() as connection:
            row = connection.execute(text("SELECT version_num FROM alembic_version")).first()
    except Exception:
        return None
    return str(row[0]) if row else None


def main(argv: list[str] | None = None) -> int:
    try:
        plan = resolve_plan()
    except BrokenSplitError as error:
        print(f"==> REFUSING: {error}", file=sys.stderr)
        return 2
    if plan.warning:
        print(f"==> WARNING: {plan.warning}", file=sys.stderr)
    owner_url = plan.owner_url
    if not owner_url:
        print(f"==> no database URL configured ({APP_URL_VAR})", file=sys.stderr)
        return 2

    if plan.state == "split":
        app_password = (os.environ.get(APP_PASSWORD_VAR) or "").strip()
        if not app_password:
            print(
                f"==> {APP_PASSWORD_VAR} is required in split mode — the app "
                "role's distinct secret (ADR-0064)",
                file=sys.stderr,
            )
            return 2

    _preflight_datastore(owner_url)

    if plan.state == "split":
        from sqlalchemy import create_engine

        app_user = _app_user()
        with create_engine(owner_url).connect() as connection:
            provision_owner_side(connection, app_user, app_password)
            connection.commit()
        print(f"==> app role '{app_user}' bootstrapped (grants + default privileges)")

    print("==> running database migrations (owner role)")
    _run_alembic(owner_url)
    print("==> provisioning the checkpoint schema (owner role)")
    _setup_checkpoints(owner_url)

    if plan.state == "split":
        from sqlalchemy import create_engine

        from ..local import head_revision

        with create_engine(owner_url).connect() as connection:
            grant_app_dml(connection, _app_user())  # ADR-0064 step 5: re-grant
            connection.commit()
        stamped = stamped_revision(owner_url)
        head = head_revision()
        if stamped != head:
            print(
                f"==> migrations did not reach head (stamped={stamped}, head={head})",
                file=sys.stderr,
            )
            return 1
    print("==> migrate complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
