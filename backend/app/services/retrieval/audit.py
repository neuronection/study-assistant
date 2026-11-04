"""App-side ``vector.*`` audit emitter (plan 51 Q3b).

Study already owns the family ``audit_events`` table through
``StudyAuditSink`` (identity-auth installation). This module is the small
retrieval-side writer for that same table — not a second ledger: it inserts
one row per action/stall/gate failure with the contract's closed
``VECTOR_AUDIT_EVENTS`` vocabulary and ids-only resources. No document,
query or prompt text ever reaches ``action``/``resource``/``outcome``.

Rows are added to the caller's session so the action and its audit row commit
(or roll back) together.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ...domain.models import AuditEvent as AuditEventRow
from ...storage.retrieval_ops import VECTOR_AUDIT_EVENTS
from .legacy import LEGACY_SPACE_ID


def build_vector_event(
    *,
    actor: str,
    action: str,
    outcome: str,
    resource: str,
) -> AuditEventRow:
    if action not in VECTOR_AUDIT_EVENTS:
        raise ValueError(f"{action!r} is not a vector audit event")
    return AuditEventRow(
        actor=actor[:200],
        action=action,
        resource=resource[:500],
        outcome=outcome[:50],
    )


def space_resource() -> str:
    return f"space:{LEGACY_SPACE_ID}"


def run_resource(run_id: str) -> str:
    return f"run:{run_id}"


def emit_vector_event(
    session: Session,
    *,
    actor: str,
    action: str,
    outcome: str,
    resource: str,
) -> AuditEventRow:
    row = build_vector_event(
        actor=actor,
        action=action,
        outcome=outcome,
        resource=resource,
    )
    session.add(row)
    return row


__all__ = [
    "build_vector_event",
    "emit_vector_event",
    "run_resource",
    "space_resource",
]
