"""closed-set CHECK twins (plan 81 B, ADR-197)

Adds the database CHECK mirroring every StrEnum-backed column. Bodies are
frozen here on purpose: a migration is a historical snapshot, and the wall in
`tests/test_schema_contract.py` keeps the model CHECKs in step with
`app/core/vocab.py`.

Explicit foreign-key delete behaviour is declared on the models in this same
commit but is applied physically by the table rebuilds of the identity
migration (0073) — SQLite cannot swap an unnamed FK, and rebuilding twelve
tables twice in one round buys nothing while no database is deployed
(documented in docs/dev/data-model.md).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0072_vocab_checks"
down_revision: str | None = "0071_chat_transport"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECKS: tuple[tuple[str, str, str], ...] = (
    ("courses", "origin_allowed", "origin IN ('manual', 'genesis', 'import', 'scratch')"),
    (
        "concept_links",
        "relation_allowed",
        "relation IN ('prereq-of', 'part-of', 'related-to')",
    ),
    (
        "material_study_state",
        "status_allowed",
        "status IN ('unread', 'reading', 'studied')",
    ),
    (
        "materials",
        "kind_allowed",
        "kind IN ('pdf', 'image', 'md', 'txt', 'doc', 'docx', 'pptx', 'epub', "
        "'html', 'audio', 'video', 'link')",
    ),
    (
        "materials",
        "status_allowed",
        "status IN ('pending', 'processing', 'ready', 'failed', 'missing')",
    ),
    (
        "material_suggestions",
        "kind_allowed",
        "kind IN ('video', 'course', 'article', 'exercise', 'other')",
    ),
    (
        "material_suggestions",
        "status_allowed",
        "status IN ('suggested', 'saved', 'dismissed')",
    ),
    (
        "external_sources",
        "kind_allowed",
        "kind IN ('rss', 'youtube_channel', 'youtube_playlist', 'site_search')",
    ),
    ("questions", "flag_allowed", "flag IN ('ok', 'review', 'elo_outlier')"),
    ("attempts", "mode_allowed", "mode IN ('practice', 'exam')"),
    (
        "study_sessions",
        "kind_allowed",
        "kind IN ('focus', 'quiz', 'exercise', 'review', 'read', 'note')",
    ),
    ("study_sessions", "source_allowed", "source IN ('timer', 'auto', 'manual')"),
    (
        "plan_items",
        "kind_allowed",
        "kind IN ('study', 'practice', 'review', 'milestone')",
    ),
    ("plan_items", "origin_allowed", "origin IN ('manual', 'draft')"),
    ("item_stats", "flag_allowed", "flag IN ('ok', 'review', 'elo_outlier')"),
    (
        "chat_proposals",
        "status_allowed",
        "status IN ('proposed', 'approved', 'dismissed', 'executed', 'stale', 'conflict')",
    ),
    (
        "jobs",
        "type_allowed",
        "type IN ('ingest', 'postprocess', 'chat_turn', 'drawing_ocr', 'image_ocr', "
        "'genesis', 'url_import', 'compose')",
    ),
    (
        "jobs",
        "status_allowed",
        "status IN ('queued', 'running', 'failed', 'done', 'cancelled')",
    ),
    ("study_goals", "unit_allowed", "unit IN ('answers', 'minutes')"),
)


def _by_table() -> list[tuple[str, list[tuple[str, str]]]]:
    grouped: dict[str, list[tuple[str, str]]] = {}
    for table, name, body in CHECKS:
        grouped.setdefault(table, []).append((name, body))
    return list(grouped.items())


def upgrade() -> None:
    for table, constraints in _by_table():
        with op.batch_alter_table(table, recreate="always") as batch:
            for name, body in constraints:
                batch.create_check_constraint(name, body)


def downgrade() -> None:
    for table, constraints in reversed(_by_table()):
        with op.batch_alter_table(table, recreate="always") as batch:
            for name, _body in reversed(constraints):
                batch.drop_constraint(name, type_="check")
