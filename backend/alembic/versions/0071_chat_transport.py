"""Model rows gain the chat_transport seam (ADR-0039).

Nullable ``models.chat_transport`` (``'responses'`` | ``'completions'``;
NULL/anything else = auto = chat completions) — the per-model OpenAI API
surface knob. The gpt-6 family rejects function tools combined with
``reasoning_effort`` on chat completions; a row serving tool tasks with
reasoning opts into ``responses`` (honored only when the base URL rides
OpenAI's own API, and always constructed store-less).

No data migration: NULL means auto, which is every existing row's
current behavior.
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0071_chat_transport"
down_revision: str | None = "0070_single_slot_capability_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("models", sa.Column("chat_transport", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("models", "chat_transport")
