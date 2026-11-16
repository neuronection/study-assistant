"""Profile-bound device credentials for external capture.

Format, digest and constant-time comparison are family code
(``nx_auth.opaque``, plan 60 D3): a brandless ``token_urlsafe(32)`` whose
only persisted form is the SHA-256 digest. Study keeps the row, the scope
enum and the revocation policy; the lookup stays digest-only (no prefix
column, no schema change).
"""

from nx_auth.opaque import mint, parse, verify
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.vocab import CaptureScope
from ...domain.models import CaptureToken, utcnow


def issue(
    session: Session,
    *,
    profile_id: str,
    label: str,
    scope: CaptureScope = CaptureScope.STAGE,
) -> tuple[str, CaptureToken]:
    token, _prefix, token_hash = mint(brand=None)
    row = CaptureToken(
        profile_id=profile_id,
        label=label.strip() or "device",
        token_hash=token_hash,
        scope=scope.value,
    )
    session.add(row)
    session.flush()
    return token, row


def authenticate(
    session: Session,
    *,
    token: str,
    scope: CaptureScope,
) -> CaptureToken | None:
    parsed = parse(token, brand=None)
    if parsed is None:
        return None
    _prefix, presented_hash = parsed
    row = session.scalar(
        select(CaptureToken).where(
            CaptureToken.token_hash == presented_hash,
            CaptureToken.scope == scope.value,
            CaptureToken.revoked_at.is_(None),
        )
    )
    if row is None or not verify(row.token_hash, presented_hash):
        return None
    row.last_used_at = utcnow()
    session.flush()
    return row


def revoke(session: Session, *, token_id: str, profile_id: str) -> bool:
    row = session.get(CaptureToken, token_id)
    if row is None or row.profile_id != profile_id or row.revoked_at is not None:
        return False
    row.revoked_at = utcnow()
    session.flush()
    return True


def list_tokens(session: Session, *, profile_id: str) -> list[CaptureToken]:
    return list(
        session.scalars(
            select(CaptureToken)
            .where(CaptureToken.profile_id == profile_id)
            .order_by(CaptureToken.created_at.desc())
        )
    )
