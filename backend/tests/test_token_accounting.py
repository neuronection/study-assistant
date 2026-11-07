"""The study token-accounting seam (plan 52 T5a).

Proves the seam resolves the effective embedding tokenizer, keeps the
exact/approximate label visible, and that the old character-divisor estimate
is gone from production accounting.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai.tokenizers import (
    CL100K_BASE,
    FALLBACK_IDENTIFIER,
    accounting_for,
    count_embedding_tokens,
    count_tokens,
    default_accounting,
    embedding_accounting,
)
from app.domain.models import AiModel, DefaultTaskAssignment, Provider, TaskAssignment
from app.storage.tokenizer_contract import TokenizerKind

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
REFERENCE = APP / "data" / "tokenizers" / "reference_corpus.json"


def _provider_model(session: Session, provider_type: str, model_id: str) -> AiModel:
    provider = Provider(
        name=f"p-{provider_type}",
        type=provider_type,
        base_url="http://x/v1",
        keyring_ref="provider:test",
    )
    session.add(provider)
    session.flush()
    model = AiModel(
        provider_id=provider.id,
        external_id=model_id,
        label=model_id,
        caps=["embeddings"],
        enabled=True,
    )
    session.add(model)
    session.flush()
    return model


def _english_text() -> str:
    payload = json.loads(REFERENCE.read_text(encoding="utf-8"))
    return next(row["text"] for row in payload["samples"] if row["language"] == "english")


def test_curated_openai_embedding_resolves_exact_cl100k(db_session: Session):
    model = _provider_model(db_session, "openai_compatible", "text-embedding-3-small")
    db_session.merge(TaskAssignment(task="embeddings", model_id=model.id))
    db_session.commit()

    accounting = embedding_accounting(db_session)
    assert accounting.spec.kind is TokenizerKind.TIKTOKEN
    assert accounting.spec.identifier == CL100K_BASE
    assert accounting.exact is True
    assert accounting.degraded_reason is None

    counted = count_embedding_tokens(db_session, _english_text())
    assert counted.tokens == 32
    assert counted.exact is True


def test_unknown_and_non_openai_embeddings_are_labelled_fallback(db_session: Session):
    for provider_type, model_id in (
        ("openai_compatible", "no-such-embedding-model"),
        ("google", "gemini-embedding-2"),
        ("anthropic", "some-embedding"),
    ):
        model = _provider_model(db_session, provider_type, model_id)
        db_session.merge(TaskAssignment(task="embeddings", model_id=model.id))
        db_session.commit()

        accounting = embedding_accounting(db_session)
        assert accounting.spec.kind is TokenizerKind.HEURISTIC, provider_type
        assert accounting.spec.identifier == FALLBACK_IDENTIFIER, provider_type
        assert accounting.exact is False, provider_type
        counted = count_embedding_tokens(db_session, _english_text())
        assert counted.exact is False, provider_type


def test_unassigned_embedding_task_is_labelled_fallback(db_session: Session):
    accounting = embedding_accounting(db_session)
    assert accounting.exact is False
    assert accounting.spec.kind is TokenizerKind.HEURISTIC
    assert default_accounting().exact is False


def test_default_task_assignment_resolves_the_embedding_model(db_session: Session):
    model = _provider_model(db_session, "openai_compatible", "text-embedding-3-large")
    db_session.add(
        DefaultTaskAssignment(requires="embeddings", model_id=model.id, fallback_model_id=None)
    )
    db_session.commit()

    accounting = embedding_accounting(db_session)
    assert accounting.spec.kind is TokenizerKind.TIKTOKEN
    assert accounting.exact is True


def test_accounting_metadata_is_counts_only_never_text(db_session: Session):
    text = _english_text()
    accounting = accounting_for("openai_compatible", "text-embedding-3-small")
    metadata = accounting.metadata()
    assert metadata["tokenizer_exact"] is True
    assert metadata["tokenizer_kind"] == "tiktoken"
    assert text not in json.dumps(metadata)

    fallback = accounting_for("google", "gemini-embedding-2")
    fallback_metadata = fallback.metadata()
    assert fallback_metadata["tokenizer_exact"] is False
    assert fallback_metadata["tokenizer_kind"] == "heuristic"
    assert text not in json.dumps(fallback_metadata)


def test_count_tokens_uses_the_given_accounting():
    exact = accounting_for("openai_compatible", "text-embedding-3-small")
    fallback = accounting_for("google", "gemini-embedding-2")
    text = _english_text()
    exact_count = count_tokens(text, exact)
    fallback_count = count_tokens(text, fallback)
    assert exact_count.exact is True
    assert fallback_count.exact is False
    assert fallback_count.tokens >= exact_count.tokens


def test_no_character_divisor_token_estimate_remains_in_production_code():
    pattern = re.compile(r"len\s*\([^\n)]*\)\s*//\s*4\b")
    offenders = [
        str(path.relative_to(BACKEND))
        for path in APP.rglob("*.py")
        if "tokenizers" not in path.parts and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"character-divisor token estimates remain: {offenders}"


def test_production_accounting_never_imports_a_network_tokenizer_loader():
    import ast

    offenders: list[str] = []
    for path in (APP / "ai" / "tokenizers").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {
                "get_encoding",
                "from_pretrained",
            }:
                offenders.append(f"{path.name}: .{node.attr}()")
            if isinstance(node, ast.Import) and any(
                alias.name.startswith("tiktoken_ext") for alias in node.names
            ):
                offenders.append(f"{path.name}: import tiktoken_ext")
            if isinstance(node, ast.ImportFrom) and str(node.module).startswith("tiktoken_ext"):
                offenders.append(f"{path.name}: from tiktoken_ext")
    assert offenders == []
