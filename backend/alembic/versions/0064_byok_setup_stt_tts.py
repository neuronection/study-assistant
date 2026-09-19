import json
from collections.abc import Mapping, Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0064_byok_setup_stt_tts"
down_revision: str | None = "0063_external_sources"
branch_labels = None
depends_on = None

_CAPS_TO_STT_TTS: Mapping[str, Sequence[str]] = {
    "audio": ("stt", "tts"),
    "speech": ("tts",),
}
_CAPS_TO_LEGACY: Mapping[str, Sequence[str]] = {
    "stt": ("audio",),
    "tts": ("speech",),
}
_REQUIRES_RENAMES = (("audio", "stt"), ("speech", "tts"))


def _load_caps(raw: object) -> list[str] | None:
    if isinstance(raw, list):
        return [cap for cap in raw if isinstance(cap, str)]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except ValueError:
            return None
        if isinstance(parsed, list):
            return [cap for cap in parsed if isinstance(cap, str)]
        return None
    return None


def _rewrite_caps(mapping: Mapping[str, Sequence[str]]) -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, caps FROM models")).fetchall()
    for row_id, raw_caps in rows:
        caps = _load_caps(raw_caps)
        if caps is None:
            continue
        updated: list[str] = []
        for cap in caps:
            updated.extend(mapping.get(cap, (cap,)))
        deduped: list[str] = []
        for cap in updated:
            if cap not in deduped:
                deduped.append(cap)
        if deduped != caps:
            bind.execute(
                sa.text("UPDATE models SET caps = :caps WHERE id = :id"),
                {"caps": json.dumps(deduped), "id": row_id},
            )


def _rename_requires(table: str, reverse: bool = False) -> None:
    bind = op.get_bind()
    for old, new in _REQUIRES_RENAMES:
        source, target = (new, old) if reverse else (old, new)
        bind.execute(
            sa.text(f"UPDATE {table} SET requires = :target WHERE requires = :source"),
            {"target": target, "source": source},
        )


def upgrade() -> None:
    op.add_column(
        "providers",
        sa.Column("preset_key", sa.String(length=40), nullable=True),
    )
    _rewrite_caps(_CAPS_TO_STT_TTS)
    _rename_requires("default_task_assignments")
    _rename_requires("course_default_task_assignments")


def downgrade() -> None:
    _rename_requires("course_default_task_assignments", reverse=True)
    _rename_requires("default_task_assignments", reverse=True)
    _rewrite_caps(_CAPS_TO_LEGACY)
    op.drop_column("providers", "preset_key")
