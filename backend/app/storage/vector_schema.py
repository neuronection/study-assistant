"""Physical vector-index naming and the Alembic autogenerate exemption.

Plan 50 P3a / plan 51 Q3c2a. The provisioned ``vec_<8hex>`` tables are
extension-managed objects: ``vector_provisioning`` owns their DDL, not the
ORM metadata. Alembic autogenerate therefore ignores them, or a live/dev
database would emit a ``RemoveTable`` on every comparison.

Study's space ids are strings (the legacy ``content`` space keeps
``legacy-chunk-vecs``), so the physical name is derived deterministically:
a UUID uses its first eight hex characters, any other id uses the first four
bytes of a BLAKE2b digest. Both forms are eight lowercase hex characters,
which is also the security boundary for the dynamic SQL the backends issue —
only ``vec_`` + eight lowercase hex is accepted, so a table name can never
carry an injected predicate.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any

INDEX_TABLE_RE = re.compile(r"^vec_[0-9a-f]{8}$")
_VECTOR_INDEX_RE = re.compile(r"^ix_vec_[0-9a-f]{8}_hnsw$")


def index_table_name(space_id: str | uuid.UUID) -> str:
    """Derive the physical index table name from a study space id."""
    try:
        return f"vec_{uuid.UUID(str(space_id)).hex[:8]}"
    except (TypeError, ValueError):
        digest = hashlib.blake2b(str(space_id).encode("utf-8"), digest_size=4).hexdigest()
        return f"vec_{digest}"


def validate_index_table(name: str) -> str:
    """Refuse anything that is not exactly ``vec_<8 lowercase hex>``."""
    if not isinstance(name, str) or INDEX_TABLE_RE.fullmatch(name) is None:
        raise ValueError(f"invalid vector index table name: {name!r}")
    return name


def is_extension_managed_table(name: str | None) -> bool:
    """True for the provisioned physical index tables."""
    return bool(name) and INDEX_TABLE_RE.fullmatch(str(name)) is not None


def include_object(
    _object: Any,
    name: str | None,
    type_: str,
    _reflected: bool,
    _compare_to: Any,
) -> bool:
    """Alembic ``include_object`` hook: hide extension-managed vector objects."""
    if type_ == "table":
        return not is_extension_managed_table(name)
    if type_ == "index":
        return not (name is not None and _VECTOR_INDEX_RE.fullmatch(name) is not None)
    return True


__all__ = [
    "INDEX_TABLE_RE",
    "include_object",
    "index_table_name",
    "is_extension_managed_table",
    "validate_index_table",
]
