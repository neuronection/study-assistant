"""The one study token-accounting seam (plan 52 T5a).

Everything that used to estimate tokens with ``len(text) // 4`` resolves its
count here. The seam resolves **one** local tokenizer for the assigned
embedding model through :mod:`app.ai.tokenizers.registry`:

* a curated OpenAI embedding model counts with the bundled, checksum-verified
  ``cl100k_base`` (``exact=True`` for that tokenizer);
* every other model, an unassigned task, or a missing/corrupt asset counts
  with the conservative UTF-8/codepoint heuristic (``exact=False``, and the
  degraded reason stays visible).

The provider does not currently return embedding usage, so this local count
is the interim accounting source. It is **not** a provider-billed token
count: the returned :class:`TokenCount` keeps the exact/approximate label so
callers never present the heuristic as exact.

No writes, no raw text in any identity or log line, no network.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.ai.tokenizers.registry import resolve_tokenizer_spec
from app.ai.tokenizers.service import (
    TokenCount,
    TokenizerService,
    get_tokenizer_service,
)
from app.storage.tokenizer_contract import TokenizerKind, TokenizerSpec

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

EMBEDDINGS_TASK = "embeddings"


@dataclass(frozen=True)
class TokenAccounting:
    """The effective tokenizer plus the service that produced a count."""

    spec: TokenizerSpec
    service: TokenizerService
    degraded_reason: str | None = None

    @property
    def exact(self) -> bool:
        """A heuristic count is never exact; a degraded exact spec is not either."""
        return self.spec.kind is not TokenizerKind.HEURISTIC

    def count(self, text: str) -> TokenCount:
        """Count ``text`` and keep the tokenizer/exactness evidence."""
        return self.service.count_or_fallback(self.spec, text)

    def metadata(self) -> dict[str, Any]:
        """JSON-safe tokenizer evidence for internal traces; never raw text."""
        return {
            "tokenizer": self.spec.identity,
            "tokenizer_kind": self.spec.kind.value,
            "tokenizer_source": self.spec.source.value,
            "tokenizer_exact": self.exact,
            "tokenizer_degraded_reason": self.degraded_reason,
        }


def accounting_for(provider_type: str | None, model: str | None) -> TokenAccounting:
    """Resolve the effective tokenizer for one embedding provider/model pair."""
    service = get_tokenizer_service()
    spec = resolve_tokenizer_spec(provider_type, model)
    effective, degraded_reason = service.effective_spec(spec)
    return TokenAccounting(
        spec=effective,
        service=service,
        degraded_reason=degraded_reason,
    )


def default_accounting() -> TokenAccounting:
    """The labelled conservative fallback (no model resolution available)."""
    return accounting_for(None, None)


def _assignment_model(session: Session, task: str) -> tuple[str | None, str | None]:
    """Resolve ``(provider_type, external_id)`` for an assigned task."""
    from sqlalchemy import select

    from app.domain.models import (
        AiModel,
        DefaultTaskAssignment,
        Provider,
        TaskAssignment,
    )

    assignment = session.get(TaskAssignment, task)
    model_id = assignment.model_id if assignment is not None else None
    if model_id is None:
        result = session.execute(
            select(DefaultTaskAssignment.model_id).where(
                DefaultTaskAssignment.requires == task
            )
        ).first()
        model_id = result[0] if result is not None else None
    if model_id is None:
        return None, None
    model = session.get(AiModel, model_id)
    if model is None:
        return None, None
    provider = session.get(Provider, model.provider_id)
    return (provider.type if provider is not None else None), model.external_id


def embedding_accounting(session: Session | None) -> TokenAccounting:
    """The effective tokenizer for the current embeddings assignment."""
    if session is None:
        return default_accounting()
    provider_type, model = _assignment_model(session, EMBEDDINGS_TASK)
    return accounting_for(provider_type, model)


def count_tokens(text: str, accounting: TokenAccounting | None = None) -> TokenCount:
    """Count with ``accounting`` (or the labelled fallback when omitted)."""
    return (accounting or default_accounting()).count(text)


def token_count(text: str, accounting: TokenAccounting | None = None) -> int:
    """Integer convenience wrapper that never claims an exact heuristic."""
    return count_tokens(text, accounting).tokens


def count_embedding_tokens(session: Session | None, text: str) -> TokenCount:
    """Count text with the effective embedding tokenizer for ``session``."""
    return embedding_accounting(session).count(text)


def embedding_token_count(session: Session | None, text: str) -> int:
    """Integer convenience for existing chunk/context writes."""
    return count_embedding_tokens(session, text).tokens


__all__ = [
    "EMBEDDINGS_TASK",
    "TokenAccounting",
    "accounting_for",
    "count_embedding_tokens",
    "count_tokens",
    "default_accounting",
    "embedding_accounting",
    "embedding_token_count",
    "token_count",
]
