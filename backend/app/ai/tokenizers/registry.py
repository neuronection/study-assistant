"""Embedding-model tokenizer mapping for study accounting (plan 52 T5a).

One rule: a model name alone never selects a tokenizer. The mapping is keyed
by ``(provider_class, model)`` and only the curated OpenAI embedding models
resolve to the bundled exact ``cl100k_base`` encoding. Everything else -
Google embeddings, an OpenAI chat model, an unknown Ollama model, an
unassigned task - resolves to the conservative heuristic, visibly
``exact=False``.

Plan 52 T5a deliberately ships no model-profile table and no chunk defaults:
the write path stays character-chunked until T5b, and the v2 space identity
belongs to T5c. The later waves extend this module instead of guessing a
tokenizer from a substring.
"""

from __future__ import annotations

from app.ai.tokenizers.service import (
    CL100K_BASE,
    FALLBACK_MAX_INPUT_TOKENS,
    OPENAI_EMBEDDING_MAX_INPUT_TOKENS,
    fallback_spec,
    provider_class,
    tiktoken_spec,
)
from app.storage.tokenizer_contract import TokenizerSource, TokenizerSpec

# ``o200k_base`` is a chat encoding and stays out; these are the embedding
# models OpenAI documents as cl100k_base users.
CURATED_OPENAI_EMBEDDING_MODELS = (
    "text-embedding-3-small",
    "text-embedding-3-large",
    "text-embedding-ada-002",
)

_CURATED_OPENAI_KEYS = {
    ("openai", model) for model in CURATED_OPENAI_EMBEDDING_MODELS
}


def curated_embedding_model(provider_type: str | None, model: str | None) -> bool:
    """Whether the pair resolves to the bundled exact embedding tokenizer."""
    return (
        provider_class(provider_type),
        str(model or "").strip(),
    ) in _CURATED_OPENAI_KEYS


def resolve_tokenizer_spec(
    provider_type: str | None, model: str | None
) -> TokenizerSpec:
    """Resolve the effective local tokenizer for an embedding model.

    Curated OpenAI embedding rows use ``cl100k_base`` exactly; every other
    pair is the labelled conservative fallback. No vendor/model substring is
    ever inspected.
    """
    if curated_embedding_model(provider_type, model):
        return tiktoken_spec(
            CL100K_BASE,
            max_input_tokens=OPENAI_EMBEDDING_MAX_INPUT_TOKENS,
            source=TokenizerSource.CURATED,
        )
    return fallback_spec(FALLBACK_MAX_INPUT_TOKENS)


__all__ = [
    "CURATED_OPENAI_EMBEDDING_MODELS",
    "curated_embedding_model",
    "resolve_tokenizer_spec",
]
