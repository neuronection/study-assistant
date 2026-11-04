"""Tokenizer service (plan 52 T5a): exact, fallback, offline, cached."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.ai.tokenizers import (
    CL100K_BASE,
    FALLBACK_IDENTIFIER,
    FALLBACK_MAX_INPUT_TOKENS,
    OPENAI_EMBEDDING_MAX_INPUT_TOKENS,
    TokenizerService,
    TokenizerUnavailable,
    fallback_spec,
    hf_tokenizer_spec,
    resolve_tokenizer_spec,
)
from app.ai.tokenizers.service import CL100K_BASE_ASSET, DEFAULT_ASSET_DIR, default_cache_dir
from app.storage import tokenizer_contract as tc

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "tokenizer_tiktoken.fixtures.json"
REFERENCE = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "data"
    / "tokenizers"
    / "reference_corpus.json"
)


def _reference_samples() -> dict[str, dict]:
    payload = json.loads(REFERENCE.read_text(encoding="utf-8"))
    return {row["language"]: row for row in payload["samples"]}


def _expected_counts() -> dict[str, int]:
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    return {row["language"]: row["tokens"] for row in payload["samples"]}


def test_openai_embedding_models_resolve_cl100k_exactly():
    for model in ("text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"):
        spec = resolve_tokenizer_spec("openai_compatible", model)
        assert spec.kind is tc.TokenizerKind.TIKTOKEN
        assert spec.identifier == CL100K_BASE
        assert spec.exact is True
        assert spec.source is tc.TokenizerSource.CURATED
        assert spec.max_input_tokens == OPENAI_EMBEDDING_MAX_INPUT_TOKENS


def test_unknown_and_non_openai_models_are_labelled_fallback():
    for provider, model in (
        ("openai_compatible", "unknown-embed-9000"),
        ("openai_compatible", "text-embedding-4-unknown"),
        ("openai_compatible", "gpt-4o"),
        ("google", "gemini-embedding-2"),
        ("anthropic", "claude-embed"),
        ("mock", "mock-embed"),
        (None, None),
    ):
        spec = resolve_tokenizer_spec(provider, model)
        assert spec.kind is tc.TokenizerKind.HEURISTIC, (provider, model)
        assert spec.identifier == FALLBACK_IDENTIFIER
        assert spec.exact is False
        assert spec.source is tc.TokenizerSource.FALLBACK
        assert spec.max_input_tokens == FALLBACK_MAX_INPUT_TOKENS


def test_exact_counts_match_the_pinned_fixture_across_languages():
    service = TokenizerService()
    spec = resolve_tokenizer_spec("openai_compatible", "text-embedding-3-small")
    samples = _reference_samples()
    expected = _expected_counts()
    assert set(samples) == set(expected) == {
        "english",
        "greek",
        "german",
        "cjk",
        "code_markdown",
    }
    for language, tokens in expected.items():
        counted = service.count_or_fallback(spec, samples[language]["text"])
        assert counted.tokens == tokens, language
        assert counted.exact is True, language
        assert counted.degraded_reason is None, language


def test_heuristic_is_conservative_for_every_reference_sample():
    service = TokenizerService()
    exact = resolve_tokenizer_spec("openai_compatible", "text-embedding-3-small")
    fallback = fallback_spec()
    for language, row in _reference_samples().items():
        exact_count = service.count(exact, row["text"])
        heuristic = service.count(fallback, row["text"])
        assert heuristic >= exact_count, language
        assert heuristic == tc.heuristic_token_count(row["text"]), language
        counted = service.count_or_fallback(fallback, row["text"])
        assert counted.exact is False, language


def test_counts_are_deterministic_and_encoding_round_trips():
    service = TokenizerService()
    spec = resolve_tokenizer_spec("openai_compatible", "text-embedding-3-small")
    text = _reference_samples()["greek"]["text"]
    assert service.count(spec, text) == service.count(spec, text)
    ids = service.encode(spec, text)
    assert service.decode(spec, ids) == text
    with pytest.raises(TokenizerUnavailable):
        service.encode(fallback_spec(), text)


def test_encode_with_offsets_round_trips_every_reference_language():
    service = TokenizerService()
    spec = resolve_tokenizer_spec("openai_compatible", "text-embedding-3-small")
    for language, row in _reference_samples().items():
        text = row["text"]
        ids, offsets = service.encode_with_offsets(spec, text)
        assert ids == service.encode(spec, text), language
        assert len(offsets) == len(ids), language
        assert service.decode(spec, ids) == text, language
        previous_end = 0
        for start, end in offsets:
            assert 0 <= start <= end <= len(text), (language, start, end)
            assert start <= previous_end, f"{language}: spans must advance"
            previous_end = max(previous_end, end)
        assert offsets[0][0] == 0
        assert offsets[-1][1] == len(text)


def test_encode_with_offsets_rejects_the_heuristic():
    service = TokenizerService()
    with pytest.raises(TokenizerUnavailable):
        service.encode_with_offsets(fallback_spec(), "text")


def test_cache_is_bounded_and_keyed_by_spec_identity():
    service = TokenizerService(max_cached=1)
    first = resolve_tokenizer_spec("openai_compatible", "text-embedding-3-small")
    same_encoding_other_limit = tc.TokenizerSpec.from_dict(
        {**first.to_dict(), "max_input_tokens": 4096}
    )
    assert same_encoding_other_limit.cache_key != first.cache_key
    text = _reference_samples()["english"]["text"]
    assert service.count(first, text) == 32
    assert service.cached_count == 1
    assert service.count(same_encoding_other_limit, text) == 32
    assert service.cached_count == 1, "the LRU bound evicts the previous encoder"
    assert service.count(first, text) == 32
    assert service.cached_count == 1


def test_missing_asset_degrades_visibly_and_never_fakes_exactness(tmp_path: Path):
    service = TokenizerService(asset_dir=tmp_path)
    spec = resolve_tokenizer_spec("openai_compatible", "text-embedding-3-small")
    effective, reason = service.effective_spec(spec)
    assert reason == "asset_missing"
    assert effective.kind is tc.TokenizerKind.HEURISTIC
    assert effective.exact is False
    counted = service.count_or_fallback(spec, "Hello world")
    assert counted.exact is False
    assert counted.degraded_reason == "asset_missing"
    with pytest.raises(TokenizerUnavailable):
        service.count(spec, "Hello world")


def test_corrupt_asset_degrades_visibly(tmp_path: Path):
    payload = (DEFAULT_ASSET_DIR / CL100K_BASE_ASSET).read_bytes()
    (tmp_path / CL100K_BASE_ASSET).write_bytes(payload + b"corrupt")
    service = TokenizerService(asset_dir=tmp_path)
    spec = resolve_tokenizer_spec("openai_compatible", "text-embedding-3-small")
    _, reason = service.effective_spec(spec)
    assert reason == "asset_corrupt"
    assert service.count_or_fallback(spec, "Hello").exact is False


def test_sentencepiece_is_explicitly_unsupported():
    sparse = tc.TokenizerSpec(
        kind="sentencepiece",
        identifier="org/model",
        revision="v1",
        artifact_sha256="c" * 64,
        max_input_tokens=512,
        source="admin",
    )
    service = TokenizerService()
    with pytest.raises(TokenizerUnavailable) as error:
        service.count(sparse, "text")
    assert error.value.reason == "unsupported_tokenizer_kind"
    assert service.available(sparse) is False


def test_hf_interface_is_reserved_and_degrades_visibly():
    spec = hf_tokenizer_spec(
        identifier="org/model",
        revision="0123456789abcdef0123456789abcdef01234567",
        artifact_sha256="d" * 64,
        max_input_tokens=512,
    )
    service = TokenizerService()
    effective, reason = service.effective_spec(spec)
    assert reason == "unsupported_tokenizer_kind"
    assert effective.kind is tc.TokenizerKind.HEURISTIC
    assert service.count_or_fallback(spec, "hello world").exact is False


def test_default_cache_dir_lives_under_the_instance_data_dir(monkeypatch, tmp_path: Path):
    import app.core.config as config

    monkeypatch.setattr(
        config,
        "get_settings",
        lambda: SimpleNamespace(data_dir=tmp_path),
    )
    assert default_cache_dir() == tmp_path / "tokenizers"


def test_exact_counting_makes_no_network_call(monkeypatch):
    def forbidden(*args, **kwargs):  # pragma: no cover - the assertion is the raise
        raise AssertionError("tokenizer service attempted a network call")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    service = TokenizerService()
    spec = resolve_tokenizer_spec("openai_compatible", "text-embedding-3-small")
    assert service.count(spec, "offline " * 100) >= 100
    assert service.decode(spec, service.encode(spec, "still offline")) == "still offline"
