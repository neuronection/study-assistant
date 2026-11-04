"""Tokenizer service and accounting seam (plan 52 T5a).

Exact bundled ``tiktoken`` for the curated OpenAI embedding models, a
labelled conservative fallback for everything else, and the single
accounting seam that resolves the effective tokenizer for the assigned
embedding model. Token-aware chunk writes and the v2 space identity remain
plan 52 T5b/T5c.
"""

from app.ai.tokenizers.accounting import (
    EMBEDDINGS_TASK,
    TokenAccounting,
    accounting_for,
    count_embedding_tokens,
    count_tokens,
    default_accounting,
    embedding_accounting,
    embedding_token_count,
    token_count,
)
from app.ai.tokenizers.registry import (
    CURATED_OPENAI_EMBEDDING_MODELS,
    curated_embedding_model,
    resolve_tokenizer_spec,
)
from app.ai.tokenizers.service import (
    CL100K_BASE,
    FALLBACK_IDENTIFIER,
    FALLBACK_MAX_INPUT_TOKENS,
    HF_CACHE_SUBDIR,
    HF_TOKENIZER_FILENAME,
    MAX_TOKENIZER_JSON_BYTES,
    OPENAI_EMBEDDING_MAX_INPUT_TOKENS,
    TokenCount,
    TokenizerService,
    TokenizerUnavailable,
    default_cache_dir,
    fallback_spec,
    get_tokenizer_service,
    hf_tokenizer_spec,
    provider_class,
    tiktoken_spec,
)

__all__ = [
    "CL100K_BASE",
    "CURATED_OPENAI_EMBEDDING_MODELS",
    "EMBEDDINGS_TASK",
    "FALLBACK_IDENTIFIER",
    "FALLBACK_MAX_INPUT_TOKENS",
    "HF_CACHE_SUBDIR",
    "HF_TOKENIZER_FILENAME",
    "MAX_TOKENIZER_JSON_BYTES",
    "OPENAI_EMBEDDING_MAX_INPUT_TOKENS",
    "TokenAccounting",
    "TokenCount",
    "TokenizerService",
    "TokenizerUnavailable",
    "accounting_for",
    "count_embedding_tokens",
    "count_tokens",
    "curated_embedding_model",
    "default_accounting",
    "default_cache_dir",
    "embedding_accounting",
    "embedding_token_count",
    "fallback_spec",
    "get_tokenizer_service",
    "hf_tokenizer_spec",
    "provider_class",
    "resolve_tokenizer_spec",
    "tiktoken_spec",
    "token_count",
]
