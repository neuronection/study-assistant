"""Vector-space lifecycle over the Q3c2a backend (plan 51 Q3c2b1).

A space is a versioned embedding configuration. Changing model, dimension or
prefixes is never an in-place rewrite: build a ``building`` space beside the
active one, backfill it through the ordinary index writer, pass the physical
and coverage gates, then flip the one active pointer and retire the previous
row. Readers follow the active row, so the cutover has no downtime.

The lifecycle service writes DDL through :mod:`storage.vector_provisioning`
(the only seam allowed to create/drop a vector table). Activation is
coverage-gated here; the golden-query quality gate is deliberately **not**
part of this slice (Q3c2b2) and every activation reports
``quality="not_sampled"`` rather than a fake pass.

``chunk_vecs`` is not dropped on activation. It is the compatibility store
until the retired legacy space is explicitly dropped (the cutover/retirement
step), or until a new active space makes it read-dead.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ...domain.models import (
    RetrievalCoverageSnapshot,
    VectorDocument,
    VectorRecord,
    VectorSpace,
)
from ...storage.retrieval_ops import COVERAGE_GATE, SPACE_DROP_GRACE_DAYS, GateStatus
from ...storage.vector_contract import METRICS
from ...storage.vector_provisioning import (
    SpaceProvision,
    VectorProvisioningError,
    drop_space_index,
    provision_space,
    space_status,
)
from ...storage.vector_provisioning import (
    SpaceStatus as PhysicalStatus,
)
from ...storage.vector_store import (
    ContentSpace,
    StudyVectorStore,
    content_space_for,
)

SPACE_DROP_GRACE = timedelta(days=SPACE_DROP_GRACE_DAYS)
LEGACY_KIND = "chunk"


class SpaceLifecycleError(RuntimeError):
    """A lifecycle transition was refused."""


class SpaceNotFound(SpaceLifecycleError):
    """No persisted space matches the reference."""


class SpaceStateError(SpaceLifecycleError):
    """The space is in a state that does not allow the requested transition."""


class SpaceCoverageError(SpaceLifecycleError):
    """The building space is not covered well enough to activate."""


@dataclass(frozen=True)
class SpaceBuildResult:
    space_id: str
    name: str
    status: str
    space_key: str
    provider: str
    model: str
    dim: int
    backend: str
    index_table: str | None
    created: bool
    provision_detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "space_id": self.space_id,
            "name": self.name,
            "status": self.status,
            "space_key": self.space_key,
            "provider": self.provider,
            "model": self.model,
            "dim": self.dim,
            "backend": self.backend,
            "index_table": self.index_table,
            "created": self.created,
            "provision_detail": self.provision_detail,
        }


@dataclass(frozen=True)
class ActivationGate:
    """The evidence activation required and the coverage it measured."""

    space_id: str
    coverage_gate: float
    coverage: dict[str, float]
    coverage_status: GateStatus
    quality: str = "not_sampled"
    snapshots: dict[str, dict[str, Any]] | None = None
    allowed: bool = True
    reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "space_id": self.space_id,
            "coverage_gate": self.coverage_gate,
            "coverage": dict(self.coverage),
            "coverage_status": self.coverage_status.value,
            "quality": self.quality,
            "snapshots": self.snapshots or {},
            "allowed": self.allowed,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class ActivationResult:
    space_id: str
    name: str
    space_key: str
    previous_space_id: str | None = None
    previous_space_name: str | None = None
    previous_space_key: str | None = None
    already_active: bool = False
    gate: ActivationGate | None = None
    legacy_compat_retained: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "space_id": self.space_id,
            "name": self.name,
            "space_key": self.space_key,
            "previous_space_id": self.previous_space_id,
            "previous_space_name": self.previous_space_name,
            "previous_space_key": self.previous_space_key,
            "already_active": self.already_active,
            "gate": self.gate.as_dict() if self.gate is not None else None,
            "legacy_compat_retained": self.legacy_compat_retained,
        }


@dataclass(frozen=True)
class SpaceDropResult:
    space_id: str
    name: str
    dropped: bool
    index_table: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "space_id": self.space_id,
            "name": self.name,
            "dropped": self.dropped,
            "index_table": self.index_table,
        }


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _space_key(row: VectorSpace) -> str:
    from ...storage.vector_contract import space_key

    return space_key(
        row.provider,
        row.model,
        row.dim,
        bool(row.normalize),
        row.query_prefix,
        row.document_prefix,
        str(row.chunker_version),
        str(row.composer_version),
    )


def resolve_space(session: Session, ref: str) -> VectorSpace:
    """Resolve an id first, then a name (newest row wins)."""
    row = session.get(VectorSpace, str(ref))
    if row is not None:
        return row
    row = session.scalars(
        select(VectorSpace)
        .where(VectorSpace.name == str(ref))
        .order_by(VectorSpace.created_at.desc(), VectorSpace.id)
    ).first()
    if row is None:
        raise SpaceNotFound(f"no vector space {ref!r}")
    return row


def active_space_row(session: Session) -> VectorSpace | None:
    rows = list(
        session.scalars(
            select(VectorSpace)
            .where(VectorSpace.status == "active")
            .order_by(VectorSpace.updated_at.desc(), VectorSpace.id)
        )
    )
    return rows[0] if rows else None


def building_spaces(session: Session) -> list[VectorSpace]:
    return list(
        session.scalars(
            select(VectorSpace)
            .where(VectorSpace.status == "building")
            .order_by(VectorSpace.created_at, VectorSpace.id)
        )
    )


def latest_coverage(
    session: Session, space_id: str, *, kind: str = LEGACY_KIND
) -> RetrievalCoverageSnapshot | None:
    return session.scalars(
        select(RetrievalCoverageSnapshot)
        .where(
            RetrievalCoverageSnapshot.space_id == space_id,
            RetrievalCoverageSnapshot.kind == kind,
        )
        .order_by(RetrievalCoverageSnapshot.as_of.desc())
        .limit(1)
    ).first()


def coverage_fraction(snapshot: RetrievalCoverageSnapshot) -> float | None:
    total = int(snapshot.total or 0)
    if total <= 0:
        return None
    return int(snapshot.embedded or 0) / total


def write_coverage_snapshot(
    session: Session,
    *,
    space_id: str,
    total: int,
    embedded: int,
    missing: int,
    failed: int = 0,
    stale: int = 0,
    kind: str = LEGACY_KIND,
) -> RetrievalCoverageSnapshot:
    moment = _now()
    row = RetrievalCoverageSnapshot(
        space_id=space_id,
        kind=kind,
        as_of=moment,
        total=max(total, 0),
        missing=max(missing, 0),
        stale=max(stale, 0),
        failed=max(failed, 0),
        embedded=max(embedded, 0),
        created_at=moment,
        updated_at=moment,
    )
    session.add(row)
    session.flush()
    return row


def space_health(
    session: Session, space_id: str
) -> tuple[PhysicalStatus, str | None]:
    """Physical status plus the honest issuance of the addressed space."""
    physical = space_status(session, space_id)
    return physical, physical.detail


def legacy_compat_present(session: Session) -> bool:
    from ...storage import vectors

    return vectors.table_exists(session)


def build_space(
    session: Session,
    *,
    name: str,
    provider: str,
    model: str,
    dim: int,
    metric: str = METRICS[0],
    normalize: bool = True,
    query_prefix: str | None = None,
    document_prefix: str | None = None,
    chunker_version: str = "1",
    composer_version: str = "1",
) -> tuple[SpaceBuildResult, bool]:
    """Create a ``building`` space and provision its physical index.

    Returns ``(result, model_changed)``. A matching building space is reused
    idempotently; a different building space with the same name is refused
    until the first one is retired/dropped.
    """
    if not name or len(name) > 40:
        raise ValueError("space name must be 1-40 characters")
    if not provider or not model:
        raise ValueError("provider and model are required")
    if int(dim) < 1:
        raise ValueError("dim must be positive")
    if metric not in METRICS:
        raise ValueError(f"unsupported metric {metric!r}; expected one of {METRICS}")
    normalized_name = str(name).strip()
    for existing in building_spaces(session):
        if existing.name != normalized_name:
            continue
        same = (
            existing.provider == provider
            and existing.model == model
            and int(existing.dim) == int(dim)
            and bool(existing.normalize) == bool(normalize)
            and existing.query_prefix == query_prefix
            and existing.document_prefix == document_prefix
        )
        if same:
            provision = provision_space(session, existing)
            return (
                _build_result(existing, provision, created=False),
                _model_changed(session, existing),
            )
        raise SpaceStateError(
            f"building space {normalized_name!r} already exists with a different "
            "configuration; retire or drop it before building another"
        )
    row = VectorSpace(
        id=str(uuid.uuid4()),
        name=normalized_name,
        provider=str(provider),
        model=str(model),
        dim=int(dim),
        metric=metric,
        normalize=bool(normalize),
        query_prefix=query_prefix,
        document_prefix=document_prefix,
        chunker_version=str(chunker_version),
        composer_version=str(composer_version),
        index_table=None,
        status="building",
        created_at=_now(),
        updated_at=_now(),
    )
    session.add(row)
    session.flush()
    try:
        provision = provision_space(session, row)
    except VectorProvisioningError:
        session.rollback()
        raise
    return (_build_result(row, provision, created=True), _model_changed(session, row))


def _build_result(
    row: VectorSpace, provision: SpaceProvision, *, created: bool
) -> SpaceBuildResult:
    return SpaceBuildResult(
        space_id=str(row.id),
        name=str(row.name),
        status=str(row.status),
        space_key=_space_key(row),
        provider=str(row.provider),
        model=str(row.model),
        dim=int(row.dim),
        backend=provision.backend,
        index_table=provision.index_table,
        created=created,
        provision_detail=provision.detail,
    )


def _model_changed(session: Session, row: VectorSpace) -> bool:
    active = active_space_row(session)
    return active is not None and active.id != row.id and _space_key(active) != _space_key(row)


def _assert_physical(session: Session, row: VectorSpace) -> PhysicalStatus:
    from ...storage.vector_backends import choose_backend

    physical = space_status(session, row)
    if row.index_table is not None and choose_backend(session).name == "linear":
        raise SpaceStateError(
            f"space {row.name!r} has a provisioned index {row.index_table!r}, but "
            "the vector extension/driver is unavailable; activation refused"
        )
    if row.index_table is None:
        if physical.backend != "linear":
            raise SpaceStateError(
                f"space {row.name!r} declares no index table but reports "
                f"{physical.backend!r}"
            )
        return physical
    if not physical.table_exists:
        raise SpaceStateError(
            f"space {row.name!r} has no physical index {row.index_table!r}; provision it first"
        )
    if physical.table_dim is not None and physical.table_dim != row.dim:
        raise SpaceStateError(
            f"index {row.index_table!r} is dim {physical.table_dim}, "
            f"space {row.name!r} needs {row.dim}"
        )
    if not physical.index_present:
        raise SpaceStateError(
            f"index {row.index_table!r} is missing its ANN index; rebuild it before activation"
        )
    return physical


def _assert_coverage(
    session: Session,
    row: VectorSpace,
    *,
    coverage_gate: float,
) -> ActivationGate:
    snapshot = latest_coverage(session, str(row.id))
    if snapshot is None:
        raise SpaceCoverageError(
            f"space {row.name!r} has no coverage snapshot; backfill it first"
        )
    fraction = coverage_fraction(snapshot)
    if fraction is None:
        raise SpaceCoverageError(
            f"space {row.name!r} has no embeddable chunks; coverage is unknown"
        )
    status = GateStatus.PASS if fraction >= coverage_gate else GateStatus.FAIL
    snapshots = {
        LEGACY_KIND: {
            "as_of": snapshot.as_of.isoformat() if snapshot.as_of else None,
            "total": snapshot.total,
            "embedded": snapshot.embedded,
            "missing": snapshot.missing,
            "stale": snapshot.stale,
            "failed": snapshot.failed,
        }
    }
    if status is GateStatus.FAIL:
        raise SpaceCoverageError(
            f"space {row.name!r} is below the coverage gate {coverage_gate:.4f}: "
            f"{LEGACY_KIND}={fraction:.4f}"
        )
    return ActivationGate(
        space_id=str(row.id),
        coverage_gate=float(coverage_gate),
        coverage={LEGACY_KIND: fraction},
        coverage_status=status,
        snapshots=snapshots,
        allowed=True,
    )


def activate_space(
    session: Session,
    space_id: str,
    *,
    coverage_gate: float = COVERAGE_GATE,
) -> ActivationResult:
    """Flip one active pointer atomically; retire every previous active row."""
    if not 0.0 <= float(coverage_gate) <= 1.0:
        raise ValueError("coverage_gate must be between 0 and 1")
    row = resolve_space(session, space_id)
    if row.status == "retired":
        raise SpaceStateError(f"space {row.name!r} is retired and cannot be activated")
    if row.status == "active":
        return ActivationResult(
            space_id=str(row.id),
            name=str(row.name),
            space_key=_space_key(row),
            already_active=True,
            legacy_compat_retained=legacy_compat_present(session),
        )
    physical = _assert_physical(session, row)
    gate = _assert_coverage(session, row, coverage_gate=float(coverage_gate))
    now = _now()
    statement = select(VectorSpace).where(VectorSpace.status == "active")
    if session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    previous = [candidate for candidate in session.scalars(statement) if candidate.id != row.id]
    previous_keys = [_space_key(candidate) for candidate in previous]
    previous_ids = [str(candidate.id) for candidate in previous]
    previous_names = [str(candidate.name) for candidate in previous]
    for candidate in previous:
        candidate.status = "retired"
        candidate.retired_at = now
        candidate.updated_at = now
    if previous:
        session.flush()
    row.status = "active"
    row.activated_at = now
    row.retired_at = None
    row.updated_at = now
    session.flush()
    del physical
    return ActivationResult(
        space_id=str(row.id),
        name=str(row.name),
        space_key=_space_key(row),
        previous_space_id=previous_ids[0] if previous_ids else None,
        previous_space_name=previous_names[0] if previous_names else None,
        previous_space_key=previous_keys[0] if previous_keys else None,
        gate=gate,
        legacy_compat_retained=legacy_compat_present(session),
    )


def retire_space(session: Session, space_id: str) -> dict[str, Any]:
    row = resolve_space(session, space_id)
    if row.status == "active":
        raise SpaceStateError(
            f"space {row.name!r} is active; activate its replacement instead of retiring it"
        )
    if row.status == "building":
        row.status = "retired"
        row.retired_at = _now()
        row.updated_at = _now()
        session.flush()
    return {
        "space_id": str(row.id),
        "name": str(row.name),
        "status": str(row.status),
        "index_table": row.index_table,
        "retired_at": row.retired_at.isoformat() if row.retired_at else None,
    }


def drop_space(
    session: Session,
    space_id: str,
    *,
    confirm: str,
    force: bool = False,
    grace: timedelta = SPACE_DROP_GRACE,
) -> SpaceDropResult:
    """Drop a retired space's physical table and metadata.

    The active space can never be dropped; a building space must be retired
    first. Without ``force`` the space must have been retired for the grace
    period. ``force`` still requires the typed space name in ``confirm``.
    """
    row = resolve_space(session, space_id)
    if row.status == "active":
        raise SpaceStateError("the active space cannot be dropped; activate a replacement")
    if row.status == "building":
        raise SpaceStateError(f"space {row.name!r} is still building; retire it before drop")
    if row.status != "retired":
        raise SpaceStateError(f"space {row.name!r} is {row.status!r}; only retired spaces drop")
    if not confirm or confirm != row.name:
        raise SpaceStateError(
            f"drop requires the typed space name {row.name!r} in confirm"
        )
    now = _now()
    if force:
        pass
    else:
        retired_at = _as_utc(row.retired_at)
        if retired_at is None:
            raise SpaceStateError(
                f"space {row.name!r} has no retirement timestamp; use force with confirmation"
            )
        age = now - retired_at
        if age < grace:
            remaining = grace - age
            raise SpaceStateError(
                f"space {row.name!r} is within its {grace.days}-day grace period "
                f"({remaining.days}d {remaining.seconds // 3600}h left); "
                "use force with confirmation to drop now"
            )
    dropped_id = str(row.id)
    dropped_name = str(row.name)
    table = drop_space_index(session, row)
    session.execute(delete(VectorRecord).where(VectorRecord.space_id == row.id))
    session.execute(delete(VectorDocument).where(VectorDocument.space_id == row.id))
    session.execute(delete(VectorSpace).where(VectorSpace.id == row.id))
    session.flush()
    return SpaceDropResult(
        space_id=dropped_id,
        name=dropped_name,
        dropped=True,
        index_table=table,
    )


def space_status_dto(
    session: Session, row: VectorSpace
) -> tuple[ContentSpace | None, PhysicalStatus]:
    space = StudyVectorStore(session, space_id=str(row.id)).content_space()
    return space, space_status(session, row)


def active_space_id(session: Session) -> str | None:
    space = content_space_for(session)
    return space.space_id if space is not None else None


__all__ = [
    "LEGACY_KIND",
    "SPACE_DROP_GRACE",
    "ActivationGate",
    "ActivationResult",
    "SpaceBuildResult",
    "SpaceCoverageError",
    "SpaceDropResult",
    "SpaceLifecycleError",
    "SpaceNotFound",
    "SpaceStateError",
    "activate_space",
    "active_space_id",
    "active_space_row",
    "build_space",
    "building_spaces",
    "coverage_fraction",
    "drop_space",
    "latest_coverage",
    "legacy_compat_present",
    "resolve_space",
    "retire_space",
    "space_health",
    "space_status_dto",
    "write_coverage_snapshot",
]
