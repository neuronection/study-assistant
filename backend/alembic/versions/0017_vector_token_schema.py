"""Plan 52 T5b1 — token-aware space identity and token offsets (schema only).

Adds the pinned tokenizer/chunk scalars to ``vector_spaces`` (all NULL on a
legacy v1 row, the complete set on a token-aware v2 row) and the token offsets
to ``vector_records`` (NULL on legacy character chunks). No application path
writes these columns yet: T5b2 owns token-aware writes and the v2 cutover.
The stored ``space_key`` from 0016 is never rewritten here; only a future
token-aware space computes the v2 pre-image.

The CHECK set is the database half of the contract: a half-configured space,
a heuristic that claims exactness, an HF tokenizer without a pinned revision
or checksum, a chunk budget that cannot fit the model input, a v2 row that
keeps ``chunker_version='1'``, and inconsistent token offsets are all refused.
``vector_records.token_count`` must equal ``token_end - token_start`` when the
token fields are present; legacy records keep all three NULL.

Downgrade drops the columns and their checks but keeps the stored
``space_key``: a v2 key remains a v2 key even if the columns that explain it
are removed, so a downgrade cannot silently make an old space look live.

Revision ID: 0017_vector_token_schema
Revises: 0016_vector_space_stored_key
Create Date: 2026-11-05
"""

import sqlalchemy as sa

from alembic import op

revision = "0017_vector_token_schema"
down_revision = "0016_vector_space_stored_key"
branch_labels = None
depends_on = None

_TOKENIZER_GROUP_CHECK = (
    "(tokenizer_kind IS NULL AND tokenizer_identifier IS NULL "
    "AND tokenizer_revision IS NULL AND tokenizer_artifact_sha256 IS NULL "
    "AND tokenizer_exact IS NULL AND max_input_tokens IS NULL "
    "AND chunk_max_tokens IS NULL AND chunk_overlap_tokens IS NULL "
    "AND chunk_max_chars IS NULL) OR "
    "(tokenizer_kind IS NOT NULL AND tokenizer_identifier IS NOT NULL "
    "AND tokenizer_exact IS NOT NULL AND max_input_tokens IS NOT NULL "
    "AND chunk_max_tokens IS NOT NULL AND chunk_overlap_tokens IS NOT NULL "
    "AND chunk_max_chars IS NOT NULL)"
)
_TOKENIZER_KIND_CHECK = (
    "tokenizer_kind IS NULL OR "
    "tokenizer_kind IN ('tiktoken', 'hf_tokenizers', 'sentencepiece', 'heuristic')"
)
_TOKENIZER_EXACT_CHECK = (
    "tokenizer_kind IS NULL OR "
    "(tokenizer_kind = 'heuristic' AND tokenizer_exact = false) OR "
    "(tokenizer_kind <> 'heuristic' AND tokenizer_exact = true)"
)
_TOKENIZER_PROVENANCE_CHECK = (
    "tokenizer_kind IS NULL OR "
    "(tokenizer_kind = 'heuristic' AND tokenizer_revision IS NULL "
    "AND tokenizer_artifact_sha256 IS NULL) OR "
    "(tokenizer_kind IN ('hf_tokenizers', 'sentencepiece') "
    "AND tokenizer_revision IS NOT NULL AND tokenizer_artifact_sha256 IS NOT NULL) OR "
    "(tokenizer_kind = 'tiktoken' AND tokenizer_artifact_sha256 IS NOT NULL)"
)
_TOKENIZER_BOUNDS_CHECK = (
    "tokenizer_kind IS NULL OR "
    "(max_input_tokens > 0 AND chunk_max_tokens >= 32 "
    "AND chunk_overlap_tokens >= 0 AND chunk_overlap_tokens * 2 < chunk_max_tokens "
    "AND chunk_max_chars > 0 AND chunk_max_tokens <= max_input_tokens)"
)
_TOKENIZER_CHUNKER_VERSION_CHECK = "tokenizer_kind IS NULL OR chunker_version = '2'"

_TOKEN_FIELDS_CONSISTENT = (
    "(token_count IS NULL AND token_start IS NULL AND token_end IS NULL) OR "
    "(token_count IS NOT NULL AND token_start IS NOT NULL AND token_end IS NOT NULL "
    "AND token_count = token_end - token_start)"
)

_SPACE_CHECKS = (
    ("tokenizer_group_all_or_none", _TOKENIZER_GROUP_CHECK),
    ("tokenizer_kind_allowed", _TOKENIZER_KIND_CHECK),
    ("tokenizer_exact_matches_kind", _TOKENIZER_EXACT_CHECK),
    ("tokenizer_provenance_by_kind", _TOKENIZER_PROVENANCE_CHECK),
    ("tokenizer_chunk_bounds", _TOKENIZER_BOUNDS_CHECK),
    ("tokenizer_requires_chunker_v2", _TOKENIZER_CHUNKER_VERSION_CHECK),
)

_RECORD_CHECKS = (
    ("token_count_non_negative", "token_count IS NULL OR token_count >= 0"),
    ("token_start_non_negative", "token_start IS NULL OR token_start >= 0"),
    ("token_end_non_negative", "token_end IS NULL OR token_end >= 0"),
    ("token_range_ordered", "token_start IS NULL OR token_end IS NULL OR token_end >= token_start"),
    ("token_fields_consistent", _TOKEN_FIELDS_CONSISTENT),
)


def upgrade() -> None:
    with op.batch_alter_table("vector_spaces") as batch:
        batch.add_column(sa.Column("tokenizer_kind", sa.String(length=30), nullable=True))
        batch.add_column(sa.Column("tokenizer_identifier", sa.String(length=200), nullable=True))
        batch.add_column(sa.Column("tokenizer_revision", sa.String(length=120), nullable=True))
        batch.add_column(
            sa.Column("tokenizer_artifact_sha256", sa.String(length=64), nullable=True)
        )
        batch.add_column(sa.Column("tokenizer_exact", sa.Boolean(), nullable=True))
        batch.add_column(sa.Column("max_input_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("chunk_max_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("chunk_overlap_tokens", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("chunk_max_chars", sa.Integer(), nullable=True))
        for name, condition in _SPACE_CHECKS:
            batch.create_check_constraint(name, condition)

    with op.batch_alter_table("vector_records") as batch:
        batch.add_column(sa.Column("token_count", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("token_start", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("token_end", sa.Integer(), nullable=True))
        for name, condition in _RECORD_CHECKS:
            batch.create_check_constraint(name, condition)


def downgrade() -> None:
    with op.batch_alter_table("vector_records") as batch:
        for name, _condition in reversed(_RECORD_CHECKS):
            batch.drop_constraint(name, type_="check")
        batch.drop_column("token_end")
        batch.drop_column("token_start")
        batch.drop_column("token_count")

    with op.batch_alter_table("vector_spaces") as batch:
        for name, _condition in reversed(_SPACE_CHECKS):
            batch.drop_constraint(name, type_="check")
        batch.drop_column("chunk_max_chars")
        batch.drop_column("chunk_overlap_tokens")
        batch.drop_column("chunk_max_tokens")
        batch.drop_column("max_input_tokens")
        batch.drop_column("tokenizer_exact")
        batch.drop_column("tokenizer_artifact_sha256")
        batch.drop_column("tokenizer_revision")
        batch.drop_column("tokenizer_identifier")
        batch.drop_column("tokenizer_kind")
