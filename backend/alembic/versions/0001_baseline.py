"""baseline — the single squashed schema (plan 81 F, ADR-196)

One revision holds the whole schema: the former `0001`-`0075` chain is
squashed and regenerated from the post-A-E models (plan 81 A-E).
`alembic upgrade head` on an empty database builds everything here.

**Destructive by design** (the family-migration §3 baseline-squash
sanction, ADR-196): no database is deployed yet and pre-baseline
databases are **rebuilt**, not migrated (`scripts/seed-demo.py` reseeds
demo data). `downgrade()` restores the empty schema — it drops every
table — rather than a previous chain shape.

Runtime-managed derived objects are created by raw DDL in this revision:
the SQLite FTS5 virtual tables and the PostgreSQL generated-`tsvector`
twins with their indexes. The sqlite-vec/pgvector tables stay
runtime-created (`app/storage/vectors.py`); the four `decision:*`
`default_task_assignments` slots are seeded here because the app expects
them at boot (0069's behaviour, folded into the baseline).

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DECISION_SLOTS = (
    "decision:tool-dispatch",
    "decision:boolean-gate",
    "decision:choice",
    "decision:score",
)

_RUNTIME_TABLES = (
    "material_fts_trigram",
    "material_fts",
    "chunk_vecs",
    "chunk_vec_ids",
    "vec_meta",
)


def _create_derived_search_objects() -> None:
    if op.get_bind().dialect.name == "postgresql":
        # ADR-0022 S3 twin: PG has no fts5 — generated tsvector + GIN.
        op.execute(
            "CREATE TABLE material_fts ("
            "material_id TEXT, "
            "title TEXT, "
            "markdown TEXT, "
            "description TEXT, "
            "topics TEXT, "
            "tsv tsvector GENERATED ALWAYS AS ("
            "  to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(markdown,'') || ' '"
            "    || coalesce(description,'') || ' ' || coalesce(topics,''))"
            ") STORED)"
        )
        op.execute("CREATE INDEX ix_material_fts_tsv ON material_fts USING gin (tsv)")
        op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        op.execute(
            "CREATE TABLE material_fts_trigram ("
            "material_id TEXT, "
            "title TEXT, markdown TEXT, description TEXT, topics TEXT, "
            "search_text TEXT GENERATED ALWAYS AS "
            "(coalesce(title,'') || ' ' || coalesce(markdown,'')) STORED)"
        )
        op.execute(
            "CREATE INDEX ix_material_fts_trigram_search_text "
            "ON material_fts_trigram USING gin (search_text gin_trgm_ops)"
        )
    else:
        op.execute(
            "CREATE VIRTUAL TABLE material_fts USING fts5("
            "title, markdown, description, topics, material_id UNINDEXED)"
        )
        op.execute(
            "CREATE VIRTUAL TABLE material_fts_trigram USING fts5("
            "title, markdown, description, topics, material_id UNINDEXED, "
            "tokenize='trigram')"
        )


def _seed_decision_slots() -> None:
    bind = op.get_bind()
    for slot in _DECISION_SLOTS:
        bind.execute(
            sa.text(
                "INSERT INTO default_task_assignments (requires, model_id, fallback_model_id) "
                "SELECT :slot, NULL, NULL WHERE NOT EXISTS ("
                "SELECT 1 FROM default_task_assignments WHERE requires = :slot)"
            ),
            {"slot": slot},
        )


def upgrade() -> None:
    op.create_table(
        "ai_interactions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("context_type", sa.String(length=30), nullable=False),
        sa.Column("context_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("direction", sa.Text(), nullable=True),
        sa.Column("task", sa.String(length=40), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("skill_version_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_interactions")),
    )
    with op.batch_alter_table("ai_interactions", schema=None) as batch_op:
        batch_op.create_index(
            "ix_ai_interactions_context", ["context_type", "context_id"], unique=False
        )
        batch_op.create_index("ix_ai_interactions_task", ["task"], unique=False)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("actor", sa.String(length=200), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("resource", sa.String(length=500), nullable=False),
        sa.Column("tenant_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("outcome", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_audit_events_action"), ["action"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_audit_events_created_at"), ["created_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_audit_events_tenant_id"), ["tenant_id"], unique=False)

    op.create_table(
        "blobs",
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("rel_path", sa.String(length=500), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("mime", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("sha256", name=op.f("pk_blobs")),
    )
    op.create_table(
        "course_types",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_course_types")),
    )
    with op.batch_alter_table("course_types", schema=None) as batch_op:
        batch_op.create_index("uq_course_types_key", ["key"], unique=True)

    op.create_table(
        "instance_settings",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_instance_settings")),
    )
    op.create_table(
        "jobs",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=120), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'failed', 'done', 'cancelled')",
            name=op.f("ck_jobs_status_allowed"),
        ),
        sa.CheckConstraint(
            "type IN ('ingest', 'postprocess', 'chat_turn', 'drawing_ocr', 'image_ocr', "
            "'genesis', 'url_import', 'compose')",
            name=op.f("ck_jobs_type_allowed"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
    )
    op.create_table(
        "providers",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("base_url", sa.String(length=300), nullable=False),
        sa.Column("keyring_ref", sa.String(length=200), nullable=False),
        sa.Column("preset_key", sa.String(length=40), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("is_local", sa.Boolean(), nullable=True),
        sa.Column("country", sa.String(length=80), nullable=True),
        sa.Column("status", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_providers")),
    )
    op.create_table(
        "skills",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("task", sa.String(length=40), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skills")),
    )
    with op.batch_alter_table("skills", schema=None) as batch_op:
        batch_op.create_index("uq_skills_key", ["key"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("token_version", sa.Integer(), nullable=False),
        sa.Column("oidc_issuer", sa.String(length=500), nullable=True),
        sa.Column("oidc_subject", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint(
            "oidc_issuer", "oidc_subject", name=op.f("uq_users_oidc_issuer_oidc_subject")
        ),
    )
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_users_email"), ["email"], unique=True)

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("refresh_jti_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("client_label", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_auth_sessions_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
    )
    with op.batch_alter_table("auth_sessions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_auth_sessions_user_id"), ["user_id"], unique=False)

    op.create_table(
        "error_patterns",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("course_type_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("example", sa.Text(), nullable=True),
        sa.Column("detection", sa.JSON(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("order_idx", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_type_id"],
            ["course_types.id"],
            name=op.f("fk_error_patterns_course_type_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_error_patterns")),
    )
    with op.batch_alter_table("error_patterns", schema=None) as batch_op:
        batch_op.create_index("ix_error_patterns_course_type", ["course_type_id"], unique=False)
        batch_op.create_index("uq_error_patterns_key", ["key"], unique=True)

    op.create_table(
        "models",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("provider_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("caps", sa.JSON(), nullable=False),
        sa.Column("decision_transport", sa.String(length=20), nullable=True),
        sa.Column("ctx_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_in", sa.Float(), nullable=True),
        sa.Column("cost_out", sa.Float(), nullable=True),
        sa.Column("reasoning_effort", sa.String(length=20), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("chat_transport", sa.String(length=20), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("missing", sa.Boolean(), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["providers.id"],
            name=op.f("fk_models_provider_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_models")),
    )
    with op.batch_alter_table("models", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_models_provider_id"), ["provider_id"], unique=False)
        batch_op.create_index(
            "uq_models_provider_external", ["provider_id", "external_id"], unique=True
        )

    op.create_table(
        "profiles",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.Column("preferences", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_profiles_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profiles")),
    )
    with op.batch_alter_table("profiles", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_profiles_user_id"), ["user_id"], unique=False)

    op.create_table(
        "skill_versions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("skill_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_ref", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("system_template", sa.Text(), nullable=False),
        sa.Column("user_template", sa.Text(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.Column("contract", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["skill_id"], ["skills.id"], name=op.f("fk_skill_versions_skill_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skill_versions")),
    )
    with op.batch_alter_table("skill_versions", schema=None) as batch_op:
        batch_op.create_index(
            "uq_skill_versions", ["skill_id", "scope_type", "scope_ref", "version"], unique=True
        )
        batch_op.create_index(
            "uq_skill_versions_global",
            ["skill_id", "scope_type", "version"],
            unique=True,
            sqlite_where=sa.text("scope_ref IS NULL"),
            postgresql_where=sa.text("scope_ref IS NULL"),
        )

    op.create_table(
        "concept_skill_ratings",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("concept", sa.String(length=200), nullable=False),
        sa.Column("skill", sa.String(length=20), nullable=False),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("rating_count", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_concept_skill_ratings_profile_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_concept_skill_ratings")),
    )
    with op.batch_alter_table("concept_skill_ratings", schema=None) as batch_op:
        batch_op.create_index(
            "uq_concept_skill_ratings", ["profile_id", "concept", "skill"], unique=True
        )

    op.create_table(
        "concept_skill_stats",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("concept", sa.String(length=200), nullable=False),
        sa.Column("concept_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("skill", sa.String(length=20), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=False),
        sa.Column("avg_time_ratio", sa.Float(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weakness_score", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_concept_skill_stats_profile_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_concept_skill_stats")),
    )
    with op.batch_alter_table("concept_skill_stats", schema=None) as batch_op:
        batch_op.create_index(
            "uq_concept_skill_stats", ["profile_id", "concept", "skill"], unique=True
        )

    op.create_table(
        "courses",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("subject", sa.String(length=120), nullable=True),
        sa.Column("level", sa.String(length=120), nullable=True),
        sa.Column("goals", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.Column("exam_date", sa.Date(), nullable=True),
        sa.Column("course_type_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("origin", sa.String(length=20), server_default="manual", nullable=False),
        sa.Column("hidden", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "origin IN ('manual', 'genesis', 'import', 'scratch')",
            name=op.f("ck_courses_origin_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["course_type_id"],
            ["course_types.id"],
            name=op.f("fk_courses_course_type_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["profiles.id"], name=op.f("fk_courses_profile_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_courses")),
    )
    with op.batch_alter_table("courses", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_courses_profile_id"), ["profile_id"], unique=False)
        batch_op.create_index(
            "uq_courses_profile_scratch",
            ["profile_id"],
            unique=True,
            sqlite_where=sa.text("origin = 'scratch'"),
            postgresql_where=sa.text("origin = 'scratch'"),
        )

    op.create_table(
        "daily_rollups",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("day", sa.String(length=10), nullable=False),
        sa.Column("answers_n", sa.Integer(), nullable=False),
        sa.Column("correct_n", sa.Integer(), nullable=False),
        sa.Column("cards_reviewed", sa.Integer(), nullable=False),
        sa.Column("minutes", sa.Float(), nullable=False),
        sa.Column("study_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("xp", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_daily_rollups_profile_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_daily_rollups")),
    )
    with op.batch_alter_table("daily_rollups", schema=None) as batch_op:
        batch_op.create_index("uq_daily_rollups", ["profile_id", "day"], unique=True)

    op.create_table(
        "default_task_assignments",
        sa.Column("requires", sa.String(length=40), nullable=False),
        sa.Column("model_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("fallback_model_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.ForeignKeyConstraint(
            ["fallback_model_id"],
            ["models.id"],
            name=op.f("fk_default_task_assignments_fallback_model_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["models.id"],
            name=op.f("fk_default_task_assignments_model_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("requires", name=op.f("pk_default_task_assignments")),
    )
    op.create_table(
        "deleted_items",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("entity_type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_deleted_items_profile_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deleted_items")),
    )
    with op.batch_alter_table("deleted_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_deleted_items_profile_id"), ["profile_id"], unique=False
        )

    op.create_table(
        "study_goals",
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("answers_per_day", sa.Integer(), nullable=False),
        sa.Column("unit", sa.String(length=10), server_default="answers", nullable=False),
        sa.Column("minutes_per_day", sa.Integer(), server_default="30", nullable=False),
        sa.CheckConstraint(
            "unit IN ('answers', 'minutes')", name=op.f("ck_study_goals_unit_allowed")
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_study_goals_profile_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("profile_id", name=op.f("pk_study_goals")),
    )
    op.create_table(
        "task_assignments",
        sa.Column("task", sa.String(length=40), nullable=False),
        sa.Column("model_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("fallback_model_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("params", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["fallback_model_id"],
            ["models.id"],
            name=op.f("fk_task_assignments_fallback_model_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["models.id"],
            name=op.f("fk_task_assignments_model_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("task", name=op.f("pk_task_assignments")),
    )
    op.create_table(
        "concepts",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_concepts_course_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_concepts")),
    )
    with op.batch_alter_table("concepts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_concepts_course_id"), ["course_id"], unique=False)
        batch_op.create_index("uq_concepts_course_name", ["course_id", "name"], unique=True)

    op.create_table(
        "course_default_task_assignments",
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("requires", sa.String(length=40), nullable=False),
        sa.Column("model_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_default_task_assignments_course_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["models.id"],
            name=op.f("fk_course_default_task_assignments_model_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint(
            "course_id", "requires", name=op.f("pk_course_default_task_assignments")
        ),
    )
    op.create_table(
        "course_task_assignments",
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("task", sa.String(length=40), nullable=False),
        sa.Column("model_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("fallback_model_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_course_task_assignments_course_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["fallback_model_id"],
            ["models.id"],
            name=op.f("fk_course_task_assignments_fallback_model_id"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["models.id"],
            name=op.f("fk_course_task_assignments_model_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("course_id", "task", name=op.f("pk_course_task_assignments")),
    )
    op.create_table(
        "external_sources",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=True),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("scan_interval_sec", sa.Integer(), nullable=True),
        sa.Column("last_scan_error", sa.Text(), nullable=True),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cursor", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('rss', 'youtube_channel', 'youtube_playlist', 'site_search')",
            name=op.f("ck_external_sources_kind_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_external_sources_course_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_external_sources_profile_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_sources")),
    )
    with op.batch_alter_table("external_sources", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_external_sources_course_id"), ["course_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_external_sources_profile_id"), ["profile_id"], unique=False
        )

    op.create_table(
        "material_sources",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("recursive", sa.Boolean(), nullable=False),
        sa.Column("include_globs", sa.JSON(), nullable=True),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("mirror_subdirs", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("scan_interval_sec", sa.Integer(), nullable=True),
        sa.Column("last_scan_error", sa.Text(), nullable=True),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_material_sources_course_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_material_sources_profile_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_sources")),
    )
    with op.batch_alter_table("material_sources", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_material_sources_profile_id"), ["profile_id"], unique=False
        )

    op.create_table(
        "study_sessions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("node_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=10), nullable=False),
        sa.Column("entity_ref", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_beat", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_sec", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "kind IN ('focus', 'quiz', 'exercise', 'review', 'read', 'note')",
            name=op.f("ck_study_sessions_kind_allowed"),
        ),
        sa.CheckConstraint(
            "source IN ('timer', 'auto', 'manual')", name=op.f("ck_study_sessions_source_allowed")
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_study_sessions_course_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_study_sessions_profile_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_study_sessions")),
    )
    with op.batch_alter_table("study_sessions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_study_sessions_course_id"), ["course_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_study_sessions_profile_id"), ["profile_id"], unique=False
        )
        batch_op.create_index(
            "ix_study_sessions_profile_started", ["profile_id", "started_at"], unique=False
        )

    op.create_table(
        "tree_nodes",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("parent_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("objectives", sa.JSON(), nullable=True),
        sa.Column("ai_hint", sa.Text(), nullable=True),
        sa.Column("order_idx", sa.Integer(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("sort_path", sa.String(length=1000), nullable=False),
        sa.Column("is_root", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("depth >= 0 AND depth <= 4", name=op.f("ck_tree_nodes_depth")),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_tree_nodes_course_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["parent_id", "course_id"],
            ["tree_nodes.id", "tree_nodes.course_id"],
            name=op.f("fk_tree_nodes_parent_id_course_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tree_nodes")),
        sa.UniqueConstraint("id", "course_id", name="uq_tree_nodes_id_course"),
    )
    with op.batch_alter_table("tree_nodes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_tree_nodes_course_id"), ["course_id"], unique=False)
        batch_op.create_index(
            "ix_tree_nodes_course_parent", ["course_id", "parent_id"], unique=False
        )
        batch_op.create_index("uq_tree_nodes_path", ["path"], unique=True)
        batch_op.create_index(
            "uq_tree_nodes_root",
            ["course_id"],
            unique=True,
            sqlite_where=sa.text("is_root = 1"),
            postgresql_where=sa.text("is_root"),
        )

    op.create_table(
        "activities",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("node_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("time_limit_sec", sa.Integer(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("generated_from", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_activities_course_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["node_id", "course_id"],
            ["tree_nodes.id", "tree_nodes.course_id"],
            name=op.f("fk_activities_node_id_course_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_activities_profile_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_activities")),
    )
    with op.batch_alter_table("activities", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_activities_course_id"), ["course_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_activities_profile_id"), ["profile_id"], unique=False)

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("node_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("use_embeddings", sa.Boolean(), nullable=True),
        sa.Column("public_id", sa.String(length=36), nullable=False),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("mention_registry", sa.JSON(), nullable=True),
        sa.Column("active_root_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("quizme", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_chat_sessions_course_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["node_id", "course_id"],
            ["tree_nodes.id", "tree_nodes.course_id"],
            name=op.f("fk_chat_sessions_node_id_course_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_chat_sessions_profile_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_sessions")),
    )
    with op.batch_alter_table("chat_sessions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_chat_sessions_course_id"), ["course_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_chat_sessions_profile_id"), ["profile_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_chat_sessions_public_id"), ["public_id"], unique=True)

    op.create_table(
        "concept_links",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("from_concept_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("to_concept_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("relation", sa.String(length=30), nullable=False),
        sa.CheckConstraint(
            "relation IN ('prereq-of', 'part-of', 'related-to')",
            name=op.f("ck_concept_links_relation_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_concept_links_course_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["from_concept_id"],
            ["concepts.id"],
            name=op.f("fk_concept_links_from_concept_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["to_concept_id"],
            ["concepts.id"],
            name=op.f("fk_concept_links_to_concept_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_concept_links")),
    )
    with op.batch_alter_table("concept_links", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_concept_links_course_id"), ["course_id"], unique=False)
        batch_op.create_index(
            "uq_concept_links_triple", ["from_concept_id", "to_concept_id", "relation"], unique=True
        )

    op.create_table(
        "exercises",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("node_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("deck_ref", sa.String(length=200), nullable=True),
        sa.Column("context", sa.JSON(), nullable=True),
        sa.Column("difficulty", sa.Float(), nullable=True),
        sa.Column("created_from", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_exercises_course_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["node_id", "course_id"],
            ["tree_nodes.id", "tree_nodes.course_id"],
            name=op.f("fk_exercises_node_id_course_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_exercises_profile_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exercises")),
    )
    with op.batch_alter_table("exercises", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_exercises_course_id"), ["course_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_exercises_profile_id"), ["profile_id"], unique=False)

    op.create_table(
        "material_folders",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("parent_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("path", sa.String(length=1000), nullable=False),
        sa.Column("source_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_material_folders_course_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["material_folders.id"],
            name=op.f("fk_material_folders_parent_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_material_folders_profile_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["material_sources.id"],
            name=op.f("fk_material_folders_source_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_folders")),
    )
    with op.batch_alter_table("material_folders", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_material_folders_course_id"), ["course_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_material_folders_parent_id"), ["parent_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_material_folders_profile_id"), ["profile_id"], unique=False
        )
        batch_op.create_index(
            "uq_material_folders_profile_course_path",
            ["profile_id", "course_id", "path"],
            unique=True,
        )
        batch_op.create_index("uq_material_folders_source_id", ["source_id"], unique=True)

    op.create_table(
        "node_concepts",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("node_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("concept_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["concept_id"],
            ["concepts.id"],
            name=op.f("fk_node_concepts_concept_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["node_id"],
            ["tree_nodes.id"],
            name=op.f("fk_node_concepts_node_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_node_concepts")),
    )
    with op.batch_alter_table("node_concepts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_node_concepts_node_id"), ["node_id"], unique=False)
        batch_op.create_index("uq_node_concepts", ["node_id", "concept_id"], unique=True)

    op.create_table(
        "notes",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("node_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("owner_type", sa.String(length=30), nullable=False),
        sa.Column("owner_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("body_schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_notes_course_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["node_id", "course_id"],
            ["tree_nodes.id", "tree_nodes.course_id"],
            name=op.f("fk_notes_node_id_course_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["profiles.id"], name=op.f("fk_notes_profile_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notes")),
    )
    with op.batch_alter_table("notes", schema=None) as batch_op:
        batch_op.create_index("ix_notes_node_id", ["node_id"], unique=False)
        batch_op.create_index("ix_notes_owner", ["owner_type", "owner_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_notes_profile_id"), ["profile_id"], unique=False)

    op.create_table(
        "plan_items",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("node_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("detail", sa.String(length=500), nullable=True),
        sa.Column("kind", sa.String(length=20), server_default="study", nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("origin", sa.String(length=20), server_default="manual", nullable=False),
        sa.Column("sort_key", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('study', 'practice', 'review', 'milestone')",
            name=op.f("ck_plan_items_kind_allowed"),
        ),
        sa.CheckConstraint(
            "origin IN ('manual', 'draft')", name=op.f("ck_plan_items_origin_allowed")
        ),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_plan_items_course_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["node_id", "course_id"],
            ["tree_nodes.id", "tree_nodes.course_id"],
            name=op.f("fk_plan_items_node_id_course_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_plan_items_profile_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plan_items")),
    )
    with op.batch_alter_table("plan_items", schema=None) as batch_op:
        batch_op.create_index("ix_plan_items_course_due", ["course_id", "due_date"], unique=False)
        batch_op.create_index(batch_op.f("ix_plan_items_course_id"), ["course_id"], unique=False)
        batch_op.create_index("ix_plan_items_profile_due", ["profile_id", "due_date"], unique=False)
        batch_op.create_index(batch_op.f("ix_plan_items_profile_id"), ["profile_id"], unique=False)

    op.create_table(
        "attempts",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("activity_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.CheckConstraint("mode IN ('practice', 'exam')", name=op.f("ck_attempts_mode_allowed")),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["activities.id"],
            name=op.f("fk_attempts_activity_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attempts")),
    )
    with op.batch_alter_table("attempts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_attempts_activity_id"), ["activity_id"], unique=False)

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("parent_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("active_child_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("blocks", sa.JSON(), nullable=False),
        sa.Column(
            "blocks_schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("citations", sa.JSON(), nullable=True),
        sa.Column("mentions", sa.JSON(), nullable=True),
        sa.Column("reads", sa.JSON(), nullable=True),
        sa.Column("tool_calls", sa.JSON(), nullable=True),
        sa.Column("grounded", sa.Boolean(), nullable=True),
        sa.Column("state", sa.JSON(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=True),
        sa.Column("trace", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["chat_sessions.id"],
            name=op.f("fk_chat_messages_session_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_messages")),
    )
    with op.batch_alter_table("chat_messages", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_chat_messages_parent_id"), ["parent_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_chat_messages_session_id"), ["session_id"], unique=False
        )

    op.create_table(
        "chat_quiz_pendings",
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("choices", sa.JSON(), nullable=True),
        sa.Column("expected_index", sa.Integer(), nullable=True),
        sa.Column("expected_latex", sa.String(length=500), nullable=True),
        sa.Column("expected_text", sa.String(length=500), nullable=True),
        sa.Column("accept", sa.JSON(), nullable=True),
        sa.Column("awaiting_answer", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("verdict", sa.String(length=20), nullable=True),
        sa.Column("verdict_detail", sa.String(length=500), nullable=True),
        sa.Column("student_answer", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "verdict IS NULL OR verdict IN ('correct', 'incorrect')",
            name=op.f("ck_chat_quiz_pendings_verdict_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["chat_sessions.id"],
            name=op.f("fk_chat_quiz_pendings_session_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_chat_quiz_pendings")),
    )
    op.create_table(
        "exercise_sessions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("exercise_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("current_step_idx", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("socratic", sa.Boolean(), nullable=False),
        sa.Column("independence_score", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.id"],
            name=op.f("fk_exercise_sessions_exercise_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exercise_sessions")),
    )
    with op.batch_alter_table("exercise_sessions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_exercise_sessions_exercise_id"), ["exercise_id"], unique=False
        )

    op.create_table(
        "exercise_steps",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("exercise_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("order_idx", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.JSON(), nullable=False),
        sa.Column("expected", sa.JSON(), nullable=True),
        sa.Column("hints_pregenerated", sa.JSON(), nullable=True),
        sa.Column("rubric", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["exercise_id"],
            ["exercises.id"],
            name=op.f("fk_exercise_steps_exercise_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exercise_steps")),
    )
    with op.batch_alter_table("exercise_steps", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_exercise_steps_exercise_id"), ["exercise_id"], unique=False
        )

    op.create_table(
        "fsrs_states",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("card_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("stability", sa.Float(), nullable=True),
        sa.Column("difficulty", sa.Float(), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("lapses", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["card_id"], ["exercises.id"], name=op.f("fk_fsrs_states_card_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fsrs_states")),
    )
    with op.batch_alter_table("fsrs_states", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_fsrs_states_card_id"), ["card_id"], unique=True)

    op.create_table(
        "material_folder_links",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("node_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("folder_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("auto_assigned", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_material_folder_links_course_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["folder_id"],
            ["material_folders.id"],
            name=op.f("fk_material_folder_links_folder_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["node_id", "course_id"],
            ["tree_nodes.id", "tree_nodes.course_id"],
            name=op.f("fk_material_folder_links_node_id_course_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_folder_links")),
    )
    with op.batch_alter_table("material_folder_links", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_material_folder_links_course_id"), ["course_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_material_folder_links_folder_id"), ["folder_id"], unique=False
        )
        batch_op.create_index("ix_material_folder_links_node", ["node_id"], unique=False)
        batch_op.create_index(
            "uq_material_folder_links_node", ["node_id", "folder_id"], unique=True
        )

    op.create_table(
        "materials",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("folder_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("blob_sha", sa.String(length=64), nullable=True),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("mime", sa.String(length=120), nullable=True),
        sa.Column("pages", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("phash", sa.String(length=24), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("starred", sa.Boolean(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("source_url_norm", sa.String(length=2048), nullable=True),
        sa.Column("source_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("external_path", sa.String(length=1000), nullable=True),
        sa.Column("file_mtime", sa.Float(), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("bitrate_kbps", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('pdf', 'image', 'md', 'txt', 'doc', 'docx', 'pptx', 'epub', "
            "'html', 'audio', 'video', 'link')",
            name=op.f("ck_materials_kind_allowed"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'failed', 'missing')",
            name=op.f("ck_materials_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["blob_sha"], ["blobs.sha256"], name=op.f("fk_materials_blob_sha"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["course_id"], ["courses.id"], name=op.f("fk_materials_course_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["folder_id"],
            ["material_folders.id"],
            name=op.f("fk_materials_folder_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_materials_profile_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_materials")),
    )
    with op.batch_alter_table("materials", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_materials_content_hash"), ["content_hash"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_materials_course_id"), ["course_id"], unique=False)
        batch_op.create_index("ix_materials_course_status", ["course_id", "status"], unique=False)
        batch_op.create_index(batch_op.f("ix_materials_folder_id"), ["folder_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_materials_profile_id"), ["profile_id"], unique=False)
        batch_op.create_index(
            "ix_materials_source_url",
            ["source_url"],
            unique=False,
            sqlite_where=sa.text("source_url IS NOT NULL"),
            postgresql_where=sa.text("source_url IS NOT NULL"),
        )
        batch_op.create_index(
            "ix_materials_starred",
            ["starred"],
            unique=False,
            sqlite_where=sa.text("starred = 1"),
            postgresql_where=sa.text("starred"),
        )
        batch_op.create_index(
            "uq_materials_course_source_url_norm",
            ["course_id", "source_url_norm"],
            unique=True,
            sqlite_where=sa.text("kind = 'link' AND source_url_norm IS NOT NULL"),
            postgresql_where=sa.text("kind = 'link' AND source_url_norm IS NOT NULL"),
        )

    op.create_table(
        "note_drawings",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("note_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("strokes", sa.JSON(), nullable=False),
        sa.Column(
            "strokes_schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("png_sha", sa.String(length=64), nullable=True),
        sa.Column("view_x", sa.Float(), nullable=True),
        sa.Column("view_y", sa.Float(), nullable=True),
        sa.Column("view_width", sa.Float(), nullable=True),
        sa.Column("view_height", sa.Float(), nullable=True),
        sa.Column("ocr_version", sa.Integer(), nullable=False),
        sa.Column("ocr_blocks", sa.JSON(), nullable=True),
        sa.Column(
            "ocr_blocks_schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("ocr_markdown", sa.Text(), nullable=True),
        sa.Column("ocr_job_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["note_id"], ["notes.id"], name=op.f("fk_note_drawings_note_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["png_sha"],
            ["blobs.sha256"],
            name=op.f("fk_note_drawings_png_sha"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_note_drawings")),
    )
    with op.batch_alter_table("note_drawings", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_note_drawings_note_id"), ["note_id"], unique=False)

    op.create_table(
        "note_versions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("note_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.Column("body_schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("cause", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["note_id"], ["notes.id"], name=op.f("fk_note_versions_note_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_note_versions_profile_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_note_versions")),
    )
    with op.batch_alter_table("note_versions", schema=None) as batch_op:
        batch_op.create_index("ix_note_versions_note", ["note_id", "id"], unique=False)
        batch_op.create_index(batch_op.f("ix_note_versions_note_id"), ["note_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_note_versions_profile_id"), ["profile_id"], unique=False
        )

    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("activity_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("parent_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("stem", sa.JSON(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("answer", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.JSON(), nullable=True),
        sa.Column("difficulty", sa.Float(), nullable=True),
        sa.Column("bloom", sa.String(length=20), nullable=True),
        sa.Column("skill", sa.String(length=20), nullable=True),
        sa.Column("concept_ids", sa.JSON(), nullable=True),
        sa.Column("expected_time_sec", sa.Integer(), nullable=True),
        sa.Column("curriculum_code", sa.String(length=120), nullable=True),
        sa.Column("source_refs", sa.JSON(), nullable=True),
        sa.Column("distractor_misconceptions", sa.JSON(), nullable=True),
        sa.Column("sympy_check", sa.JSON(), nullable=True),
        sa.Column("input_modes", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("provenance", sa.JSON(), nullable=True),
        sa.Column("flag", sa.String(length=10), nullable=False),
        sa.Column("stats", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "flag IN ('ok', 'review', 'elo_outlier')", name=op.f("ck_questions_flag_allowed")
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["activities.id"],
            name=op.f("fk_questions_activity_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["questions.id"], name=op.f("fk_questions_parent_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_questions")),
    )
    with op.batch_alter_table("questions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_questions_activity_id"), ["activity_id"], unique=False)

    op.create_table(
        "quizme_answers",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_quizme_answers_profile_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["chat_sessions.id"],
            name=op.f("fk_quizme_answers_session_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quizme_answers")),
    )
    with op.batch_alter_table("quizme_answers", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_quizme_answers_profile_id"), ["profile_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_quizme_answers_session_id"), ["session_id"], unique=False
        )

    op.create_table(
        "review_log",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("card_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("interval_days", sa.Float(), nullable=False),
        sa.Column("elapsed_days", sa.Float(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["card_id"], ["exercises.id"], name=op.f("fk_review_log_card_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_log")),
    )
    with op.batch_alter_table("review_log", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_review_log_card_id"), ["card_id"], unique=False)

    op.create_table(
        "answers",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("attempt_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("question_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("response", sa.JSON(), nullable=True),
        sa.Column("input_mode", sa.String(length=10), nullable=True),
        sa.Column("correct", sa.Boolean(), nullable=True),
        sa.Column("partial_credit", sa.Float(), nullable=True),
        sa.Column("feedback", sa.JSON(), nullable=True),
        sa.Column("graded_by", sa.String(length=10), nullable=True),
        sa.Column("time_ms", sa.Integer(), nullable=True),
        sa.Column("retries", sa.Integer(), nullable=False),
        sa.Column("error_tags", sa.JSON(), nullable=True),
        sa.Column("help_events", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"], ["attempts.id"], name=op.f("fk_answers_attempt_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_answers_question_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_answers")),
    )
    with op.batch_alter_table("answers", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_answers_attempt_id"), ["attempt_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_answers_question_id"), ["question_id"], unique=False)

    op.create_table(
        "chat_proposals",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("message_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("target_kind", sa.String(length=20), nullable=True),
        sa.Column("target_name", sa.String(length=300), nullable=True),
        sa.Column("target_node_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("target_node_path", sa.JSON(), nullable=True),
        sa.Column("original_md", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "payload_schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column(
            "result_schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('proposed', 'approved', 'dismissed', 'executed', 'stale', 'conflict')",
            name=op.f("ck_chat_proposals_status_allowed"),
        ),
        sa.CheckConstraint(
            "target_kind IS NULL OR target_kind IN ('note', 'material', 'concept', 'link')",
            name=op.f("ck_chat_proposals_target_kind_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["chat_messages.id"],
            name=op.f("fk_chat_proposals_message_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id"],
            ["tree_nodes.id"],
            name=op.f("fk_chat_proposals_target_node_id"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_proposals")),
    )
    with op.batch_alter_table("chat_proposals", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_chat_proposals_message_id"), ["message_id"], unique=False
        )

    op.create_table(
        "extractions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("material_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("extractor", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=True),
        sa.Column("blocks", sa.JSON(), nullable=False),
        sa.Column(
            "blocks_schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("confidence", sa.JSON(), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("token_in", sa.Integer(), nullable=True),
        sa.Column("token_out", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Float(), nullable=True),
        sa.Column("reviewed", sa.Boolean(), nullable=False),
        sa.Column("edited_by_user", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["materials.id"],
            name=op.f("fk_extractions_material_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extractions")),
    )
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_extractions_material_id"), ["material_id"], unique=False
        )

    op.create_table(
        "item_stats",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("question_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("n_attempts", sa.Integer(), nullable=False),
        sa.Column("p_correct", sa.Float(), nullable=False),
        sa.Column("avg_time_ms", sa.Float(), nullable=True),
        sa.Column("avg_time_ratio", sa.Float(), nullable=True),
        sa.Column("distractor_selection", sa.JSON(), nullable=True),
        sa.Column("flag", sa.String(length=10), nullable=False),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("rating_count", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "flag IN ('ok', 'review', 'elo_outlier')", name=op.f("ck_item_stats_flag_allowed")
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_item_stats_question_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_item_stats")),
    )
    with op.batch_alter_table("item_stats", schema=None) as batch_op:
        batch_op.create_index("uq_item_stats", ["question_id"], unique=True)

    op.create_table(
        "material_drawings",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("material_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("strokes", sa.JSON(), nullable=False),
        sa.Column(
            "strokes_schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("png_sha", sa.String(length=64), nullable=True),
        sa.Column("view_x", sa.Float(), nullable=True),
        sa.Column("view_y", sa.Float(), nullable=True),
        sa.Column("view_width", sa.Float(), nullable=True),
        sa.Column("view_height", sa.Float(), nullable=True),
        sa.Column("ocr_version", sa.Integer(), nullable=False),
        sa.Column("ocr_blocks", sa.JSON(), nullable=True),
        sa.Column(
            "ocr_blocks_schema_version", sa.Integer(), server_default=sa.text("1"), nullable=False
        ),
        sa.Column("ocr_markdown", sa.Text(), nullable=True),
        sa.Column("ocr_job_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["materials.id"],
            name=op.f("fk_material_drawings_material_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["png_sha"],
            ["blobs.sha256"],
            name=op.f("fk_material_drawings_png_sha"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_drawings")),
    )
    with op.batch_alter_table("material_drawings", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_material_drawings_material_id"), ["material_id"], unique=False
        )

    op.create_table(
        "material_images",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("material_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("blob_sha", sa.String(length=64), nullable=True),
        sa.Column("mime", sa.String(length=120), nullable=True),
        sa.Column("ocr_version", sa.Integer(), nullable=False),
        sa.Column("ocr_markdown", sa.Text(), nullable=True),
        sa.Column("ocr_job_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["blob_sha"],
            ["blobs.sha256"],
            name=op.f("fk_material_images_blob_sha"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["materials.id"],
            name=op.f("fk_material_images_material_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_images")),
    )
    with op.batch_alter_table("material_images", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_material_images_material_id"), ["material_id"], unique=False
        )

    op.create_table(
        "material_index_cards",
        sa.Column("material_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("topics", sa.JSON(), nullable=True),
        sa.Column("key_terms", sa.JSON(), nullable=True),
        sa.Column("reading_minutes", sa.Integer(), nullable=True),
        sa.Column("difficulty", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["materials.id"],
            name=op.f("fk_material_index_cards_material_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("material_id", name=op.f("pk_material_index_cards")),
    )
    op.create_table(
        "material_study_state",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("material_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress", sa.Float(), nullable=False),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('unread', 'reading', 'studied')",
            name=op.f("ck_material_study_state_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["materials.id"],
            name=op.f("fk_material_study_state_material_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_material_study_state_profile_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_study_state")),
    )
    with op.batch_alter_table("material_study_state", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_material_study_state_material_id"), ["material_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_material_study_state_profile_id"), ["profile_id"], unique=False
        )
        batch_op.create_index("uq_material_study_state", ["material_id", "profile_id"], unique=True)

    op.create_table(
        "material_suggestions",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("node_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("url_norm", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("material_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('video', 'course', 'article', 'exercise', 'other')",
            name=op.f("ck_material_suggestions_kind_allowed"),
        ),
        sa.CheckConstraint(
            "status IN ('suggested', 'saved', 'dismissed')",
            name=op.f("ck_material_suggestions_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_material_suggestions_course_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["materials.id"],
            name=op.f("fk_material_suggestions_material_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["node_id", "course_id"],
            ["tree_nodes.id", "tree_nodes.course_id"],
            name=op.f("fk_material_suggestions_node_id_course_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["profiles.id"],
            name=op.f("fk_material_suggestions_profile_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_suggestions")),
    )
    with op.batch_alter_table("material_suggestions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_material_suggestions_course_id"), ["course_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_material_suggestions_profile_id"), ["profile_id"], unique=False
        )
        batch_op.create_index(
            "uq_material_suggestions_profile_url", ["profile_id", "url_norm"], unique=True
        )

    op.create_table(
        "mistakes",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("profile_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("question_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("concept_ids", sa.JSON(), nullable=True),
        sa.Column("error_tags", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["profiles.id"], name=op.f("fk_mistakes_profile_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_mistakes_question_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mistakes")),
    )
    with op.batch_alter_table("mistakes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_mistakes_profile_id"), ["profile_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_mistakes_question_id"), ["question_id"], unique=False)

    op.create_table(
        "quiz_help_events",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("attempt_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("question_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("violations", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["attempt_id"],
            ["attempts.id"],
            name=op.f("fk_quiz_help_events_attempt_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["questions.id"],
            name=op.f("fk_quiz_help_events_question_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quiz_help_events")),
    )
    with op.batch_alter_table("quiz_help_events", schema=None) as batch_op:
        batch_op.create_index(
            "ix_quiz_help_events_attempt_question", ["attempt_id", "question_id"], unique=False
        )

    op.create_table(
        "step_attempts",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("session_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("step_idx", sa.Integer(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=True),
        sa.Column("correct", sa.Boolean(), nullable=True),
        sa.Column("hint_level_used", sa.Integer(), nullable=True),
        sa.Column("error_class", sa.String(length=30), nullable=True),
        sa.Column("feedback", sa.JSON(), nullable=True),
        sa.Column("state", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["exercise_sessions.id"],
            name=op.f("fk_step_attempts_session_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_step_attempts")),
    )
    with op.batch_alter_table("step_attempts", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_step_attempts_session_id"), ["session_id"], unique=False
        )

    op.create_table(
        "chat_proposal_anchors",
        sa.Column("proposal_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("op", sa.String(length=10), nullable=False),
        sa.Column("find_text", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "op IN ('replace', 'append', 'prepend')",
            name=op.f("ck_chat_proposal_anchors_op_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["proposal_id"],
            ["chat_proposals.id"],
            name=op.f("fk_chat_proposal_anchors_proposal_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("proposal_id", "position", name=op.f("pk_chat_proposal_anchors")),
    )
    with op.batch_alter_table("chat_proposal_anchors", schema=None) as batch_op:
        batch_op.create_index(
            "ix_chat_proposal_anchors_proposal", ["proposal_id", "position"], unique=False
        )

    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("extraction_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["extraction_id"],
            ["extractions.id"],
            name=op.f("fk_chunks_extraction_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
    )
    with op.batch_alter_table("chunks", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_chunks_extraction_id"), ["extraction_id"], unique=False
        )

    op.create_table(
        "material_links",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("course_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("node_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("material_id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("extraction_id", sa.Uuid(as_uuid=False), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("auto_assigned", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.id"],
            name=op.f("fk_material_links_course_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_id"],
            ["extractions.id"],
            name=op.f("fk_material_links_extraction_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["material_id"],
            ["materials.id"],
            name=op.f("fk_material_links_material_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["node_id", "course_id"],
            ["tree_nodes.id", "tree_nodes.course_id"],
            name=op.f("fk_material_links_node_id_course_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_material_links")),
    )
    with op.batch_alter_table("material_links", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_material_links_course_id"), ["course_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_material_links_material_id"), ["material_id"], unique=False
        )
        batch_op.create_index("ix_material_links_node", ["node_id"], unique=False)
        batch_op.create_index("uq_material_links_node", ["node_id", "material_id"], unique=True)

    _create_derived_search_objects()
    _seed_decision_slots()


def downgrade() -> None:
    for name in _RUNTIME_TABLES:
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{name}"'))
    with op.batch_alter_table("material_links", schema=None) as batch_op:
        batch_op.drop_index("uq_material_links_node")
        batch_op.drop_index("ix_material_links_node")
        batch_op.drop_index(batch_op.f("ix_material_links_material_id"))
        batch_op.drop_index(batch_op.f("ix_material_links_course_id"))

    op.drop_table("material_links")
    with op.batch_alter_table("chunks", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chunks_extraction_id"))

    op.drop_table("chunks")
    with op.batch_alter_table("chat_proposal_anchors", schema=None) as batch_op:
        batch_op.drop_index("ix_chat_proposal_anchors_proposal")

    op.drop_table("chat_proposal_anchors")
    with op.batch_alter_table("step_attempts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_step_attempts_session_id"))

    op.drop_table("step_attempts")
    with op.batch_alter_table("quiz_help_events", schema=None) as batch_op:
        batch_op.drop_index("ix_quiz_help_events_attempt_question")

    op.drop_table("quiz_help_events")
    with op.batch_alter_table("mistakes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_mistakes_question_id"))
        batch_op.drop_index(batch_op.f("ix_mistakes_profile_id"))

    op.drop_table("mistakes")
    with op.batch_alter_table("material_suggestions", schema=None) as batch_op:
        batch_op.drop_index("uq_material_suggestions_profile_url")
        batch_op.drop_index(batch_op.f("ix_material_suggestions_profile_id"))
        batch_op.drop_index(batch_op.f("ix_material_suggestions_course_id"))

    op.drop_table("material_suggestions")
    with op.batch_alter_table("material_study_state", schema=None) as batch_op:
        batch_op.drop_index("uq_material_study_state")
        batch_op.drop_index(batch_op.f("ix_material_study_state_profile_id"))
        batch_op.drop_index(batch_op.f("ix_material_study_state_material_id"))

    op.drop_table("material_study_state")
    op.drop_table("material_index_cards")
    with op.batch_alter_table("material_images", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_material_images_material_id"))

    op.drop_table("material_images")
    with op.batch_alter_table("material_drawings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_material_drawings_material_id"))

    op.drop_table("material_drawings")
    with op.batch_alter_table("item_stats", schema=None) as batch_op:
        batch_op.drop_index("uq_item_stats")

    op.drop_table("item_stats")
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_extractions_material_id"))

    op.drop_table("extractions")
    with op.batch_alter_table("chat_proposals", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chat_proposals_message_id"))

    op.drop_table("chat_proposals")
    with op.batch_alter_table("answers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_answers_question_id"))
        batch_op.drop_index(batch_op.f("ix_answers_attempt_id"))

    op.drop_table("answers")
    with op.batch_alter_table("review_log", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_review_log_card_id"))

    op.drop_table("review_log")
    with op.batch_alter_table("quizme_answers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_quizme_answers_session_id"))
        batch_op.drop_index(batch_op.f("ix_quizme_answers_profile_id"))

    op.drop_table("quizme_answers")
    with op.batch_alter_table("questions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_questions_activity_id"))

    op.drop_table("questions")
    with op.batch_alter_table("note_versions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_note_versions_profile_id"))
        batch_op.drop_index(batch_op.f("ix_note_versions_note_id"))
        batch_op.drop_index("ix_note_versions_note")

    op.drop_table("note_versions")
    with op.batch_alter_table("note_drawings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_note_drawings_note_id"))

    op.drop_table("note_drawings")
    with op.batch_alter_table("materials", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_materials_course_source_url_norm",
            sqlite_where=sa.text("kind = 'link' AND source_url_norm IS NOT NULL"),
            postgresql_where=sa.text("kind = 'link' AND source_url_norm IS NOT NULL"),
        )
        batch_op.drop_index(
            "ix_materials_starred",
            sqlite_where=sa.text("starred = 1"),
            postgresql_where=sa.text("starred"),
        )
        batch_op.drop_index(
            "ix_materials_source_url",
            sqlite_where=sa.text("source_url IS NOT NULL"),
            postgresql_where=sa.text("source_url IS NOT NULL"),
        )
        batch_op.drop_index(batch_op.f("ix_materials_profile_id"))
        batch_op.drop_index(batch_op.f("ix_materials_folder_id"))
        batch_op.drop_index("ix_materials_course_status")
        batch_op.drop_index(batch_op.f("ix_materials_course_id"))
        batch_op.drop_index(batch_op.f("ix_materials_content_hash"))

    op.drop_table("materials")
    with op.batch_alter_table("material_folder_links", schema=None) as batch_op:
        batch_op.drop_index("uq_material_folder_links_node")
        batch_op.drop_index("ix_material_folder_links_node")
        batch_op.drop_index(batch_op.f("ix_material_folder_links_folder_id"))
        batch_op.drop_index(batch_op.f("ix_material_folder_links_course_id"))

    op.drop_table("material_folder_links")
    with op.batch_alter_table("fsrs_states", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_fsrs_states_card_id"))

    op.drop_table("fsrs_states")
    with op.batch_alter_table("exercise_steps", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_exercise_steps_exercise_id"))

    op.drop_table("exercise_steps")
    with op.batch_alter_table("exercise_sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_exercise_sessions_exercise_id"))

    op.drop_table("exercise_sessions")
    op.drop_table("chat_quiz_pendings")
    with op.batch_alter_table("chat_messages", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chat_messages_session_id"))
        batch_op.drop_index(batch_op.f("ix_chat_messages_parent_id"))

    op.drop_table("chat_messages")
    with op.batch_alter_table("attempts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_attempts_activity_id"))

    op.drop_table("attempts")
    with op.batch_alter_table("plan_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_plan_items_profile_id"))
        batch_op.drop_index("ix_plan_items_profile_due")
        batch_op.drop_index(batch_op.f("ix_plan_items_course_id"))
        batch_op.drop_index("ix_plan_items_course_due")

    op.drop_table("plan_items")
    with op.batch_alter_table("notes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_notes_profile_id"))
        batch_op.drop_index("ix_notes_owner")
        batch_op.drop_index("ix_notes_node_id")

    op.drop_table("notes")
    with op.batch_alter_table("node_concepts", schema=None) as batch_op:
        batch_op.drop_index("uq_node_concepts")
        batch_op.drop_index(batch_op.f("ix_node_concepts_node_id"))

    op.drop_table("node_concepts")
    with op.batch_alter_table("material_folders", schema=None) as batch_op:
        batch_op.drop_index("uq_material_folders_source_id")
        batch_op.drop_index("uq_material_folders_profile_course_path")
        batch_op.drop_index(batch_op.f("ix_material_folders_profile_id"))
        batch_op.drop_index(batch_op.f("ix_material_folders_parent_id"))
        batch_op.drop_index(batch_op.f("ix_material_folders_course_id"))

    op.drop_table("material_folders")
    with op.batch_alter_table("exercises", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_exercises_profile_id"))
        batch_op.drop_index(batch_op.f("ix_exercises_course_id"))

    op.drop_table("exercises")
    with op.batch_alter_table("concept_links", schema=None) as batch_op:
        batch_op.drop_index("uq_concept_links_triple")
        batch_op.drop_index(batch_op.f("ix_concept_links_course_id"))

    op.drop_table("concept_links")
    with op.batch_alter_table("chat_sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chat_sessions_public_id"))
        batch_op.drop_index(batch_op.f("ix_chat_sessions_profile_id"))
        batch_op.drop_index(batch_op.f("ix_chat_sessions_course_id"))

    op.drop_table("chat_sessions")
    with op.batch_alter_table("activities", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_activities_profile_id"))
        batch_op.drop_index(batch_op.f("ix_activities_course_id"))

    op.drop_table("activities")
    with op.batch_alter_table("tree_nodes", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_tree_nodes_root",
            sqlite_where=sa.text("is_root = 1"),
            postgresql_where=sa.text("is_root"),
        )
        batch_op.drop_index("uq_tree_nodes_path")
        batch_op.drop_index("ix_tree_nodes_course_parent")
        batch_op.drop_index(batch_op.f("ix_tree_nodes_course_id"))

    op.drop_table("tree_nodes")
    with op.batch_alter_table("study_sessions", schema=None) as batch_op:
        batch_op.drop_index("ix_study_sessions_profile_started")
        batch_op.drop_index(batch_op.f("ix_study_sessions_profile_id"))
        batch_op.drop_index(batch_op.f("ix_study_sessions_course_id"))

    op.drop_table("study_sessions")
    with op.batch_alter_table("material_sources", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_material_sources_profile_id"))

    op.drop_table("material_sources")
    with op.batch_alter_table("external_sources", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_external_sources_profile_id"))
        batch_op.drop_index(batch_op.f("ix_external_sources_course_id"))

    op.drop_table("external_sources")
    op.drop_table("course_task_assignments")
    op.drop_table("course_default_task_assignments")
    with op.batch_alter_table("concepts", schema=None) as batch_op:
        batch_op.drop_index("uq_concepts_course_name")
        batch_op.drop_index(batch_op.f("ix_concepts_course_id"))

    op.drop_table("concepts")
    op.drop_table("task_assignments")
    op.drop_table("study_goals")
    with op.batch_alter_table("deleted_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_deleted_items_profile_id"))

    op.drop_table("deleted_items")
    op.drop_table("default_task_assignments")
    with op.batch_alter_table("daily_rollups", schema=None) as batch_op:
        batch_op.drop_index("uq_daily_rollups")

    op.drop_table("daily_rollups")
    with op.batch_alter_table("courses", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_courses_profile_scratch",
            sqlite_where=sa.text("origin = 'scratch'"),
            postgresql_where=sa.text("origin = 'scratch'"),
        )
        batch_op.drop_index(batch_op.f("ix_courses_profile_id"))

    op.drop_table("courses")
    with op.batch_alter_table("concept_skill_stats", schema=None) as batch_op:
        batch_op.drop_index("uq_concept_skill_stats")

    op.drop_table("concept_skill_stats")
    with op.batch_alter_table("concept_skill_ratings", schema=None) as batch_op:
        batch_op.drop_index("uq_concept_skill_ratings")

    op.drop_table("concept_skill_ratings")
    with op.batch_alter_table("skill_versions", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_skill_versions_global",
            sqlite_where=sa.text("scope_ref IS NULL"),
            postgresql_where=sa.text("scope_ref IS NULL"),
        )
        batch_op.drop_index("uq_skill_versions")

    op.drop_table("skill_versions")
    with op.batch_alter_table("profiles", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_profiles_user_id"))

    op.drop_table("profiles")
    with op.batch_alter_table("models", schema=None) as batch_op:
        batch_op.drop_index("uq_models_provider_external")
        batch_op.drop_index(batch_op.f("ix_models_provider_id"))

    op.drop_table("models")
    with op.batch_alter_table("error_patterns", schema=None) as batch_op:
        batch_op.drop_index("uq_error_patterns_key")
        batch_op.drop_index("ix_error_patterns_course_type")

    op.drop_table("error_patterns")
    with op.batch_alter_table("auth_sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_auth_sessions_user_id"))

    op.drop_table("auth_sessions")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_email"))

    op.drop_table("users")
    with op.batch_alter_table("skills", schema=None) as batch_op:
        batch_op.drop_index("uq_skills_key")

    op.drop_table("skills")
    op.drop_table("providers")
    op.drop_table("jobs")
    op.drop_table("instance_settings")
    with op.batch_alter_table("course_types", schema=None) as batch_op:
        batch_op.drop_index("uq_course_types_key")

    op.drop_table("course_types")
    op.drop_table("blobs")
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_events_tenant_id"))
        batch_op.drop_index(batch_op.f("ix_audit_events_created_at"))
        batch_op.drop_index(batch_op.f("ix_audit_events_action"))

    op.drop_table("audit_events")
    with op.batch_alter_table("ai_interactions", schema=None) as batch_op:
        batch_op.drop_index("ix_ai_interactions_task")
        batch_op.drop_index("ix_ai_interactions_context")

    op.drop_table("ai_interactions")
