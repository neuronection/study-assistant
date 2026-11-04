"""Token-aware chunking, overlap, offsets and the max_chars ceiling (T5b2)."""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path

import pytest

from app.ai.tokenizers import fallback_spec, resolve_tokenizer_spec
from app.ai.tokenizers.service import TokenizerService
from app.pipelines.chunking import (
    InputTooLong,
    TokenWindow,
    chunk_markdown,
    chunk_tokens,
)
from app.storage.tokenizer_contract import (
    ChunkConfig,
    TokenizerKind,
    TokenizerSpec,
)

REFERENCE = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "data"
    / "tokenizers"
    / "reference_corpus.json"
)
LANGUAGES = ("english", "greek", "german", "cjk", "code_markdown")


def _samples() -> dict[str, str]:
    payload = json.loads(REFERENCE.read_text(encoding="utf-8"))
    return {row["language"]: row["text"] for row in payload["samples"]}


def _exact_spec() -> TokenizerSpec:
    return resolve_tokenizer_spec("openai_compatible", "text-embedding-3-small")


def _config(**overrides: int) -> ChunkConfig:
    values = {"max_chunk_tokens": 64, "overlap_tokens": 8, "max_chars": 400}
    values.update(overrides)
    return ChunkConfig(**values)


def _service() -> TokenizerService:
    return TokenizerService()


@pytest.mark.parametrize("language", LANGUAGES)
def test_token_windows_round_trip_offsets_and_cover_every_language(
    language: str,
) -> None:
    text = _samples()[language]
    service = _service()
    spec = _exact_spec()
    windows = chunk_tokens(
        text, tokenizer=spec, chunk=_config(), service=service
    )
    assert windows
    ids, _spans = service.encode_with_offsets(spec, text)
    assert len(ids) > 0
    previous_end = 0
    for window in windows:
        assert isinstance(window, TokenWindow)
        assert text[window.char_start : window.char_end] == window.text
        assert 0 <= window.token_start < window.token_end <= len(ids)
        assert window.token_count == window.token_end - window.token_start
        assert window.token_count <= 64
        assert len(window.text) <= 400
        assert window.char_start >= previous_end or window.token_start > 0
        previous_end = max(previous_end, window.char_end)
        assert window.token_start < len(ids)
    assert windows[-1].char_end == len(text.rstrip())
    if len(ids) > 64:
        assert windows[1].token_start < windows[0].token_end


def test_overlap_is_in_tokens_and_progresses() -> None:
    text = "alpha beta gamma delta " * 200
    service = _service()
    windows = chunk_tokens(
        text,
        tokenizer=_exact_spec(),
        chunk=_config(max_chunk_tokens=48, overlap_tokens=12),
        service=service,
    )
    assert len(windows) > 1
    for previous, current in pairwise(windows):
        assert current.token_start < previous.token_end
        assert current.token_start > previous.token_start
        assert previous.token_end - current.token_start == 12


def test_max_chars_ceiling_narrows_windows_without_truncating() -> None:
    text = "Lorem ipsum dolor sit amet. " * 60
    windows = chunk_tokens(
        text,
        tokenizer=_exact_spec(),
        chunk=_config(max_chunk_tokens=64, overlap_tokens=8, max_chars=120),
        service=_service(),
    )
    assert windows
    assert all(len(window.text) <= 120 for window in windows)
    assert windows[-1].char_end == len(text.rstrip())


def test_a_single_window_that_cannot_fit_raises_input_too_long() -> None:
    text = "hello world"
    with pytest.raises(InputTooLong) as error:
        chunk_tokens(
            text,
            tokenizer=_exact_spec(),
            chunk=_config(max_chunk_tokens=32, overlap_tokens=4, max_chars=2),
            service=_service(),
        )
    assert error.value.reason == "input_too_long"


def test_prefix_budget_exhaustion_raises_input_too_long() -> None:
    spec = TokenizerSpec(
        kind=TokenizerKind.TIKTOKEN,
        identifier="cl100k_base",
        artifact_sha256=(
            "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
        ),
        max_input_tokens=16,
        source="admin",
    )
    with pytest.raises(InputTooLong):
        chunk_tokens(
            "hello world",
            tokenizer=spec,
            chunk=_config(max_chunk_tokens=32),
            service=_service(),
            document_prefix="passage: ",
        )


def test_heuristic_windows_are_labelled_and_still_bounded() -> None:
    text = _samples()["cjk"]
    windows = chunk_tokens(
        text,
        tokenizer=fallback_spec(),
        chunk=_config(max_chunk_tokens=64, overlap_tokens=8, max_chars=400),
    )
    assert windows
    assert windows[-1].char_end == len(text.rstrip())
    for window in windows:
        assert window.token_count == window.token_end - window.token_start
        assert window.token_count <= 64
        assert len(window.text) <= 400


def test_v1_chunk_markdown_is_unchanged() -> None:
    text = "\n\n".join(["one " * 200, "two " * 200])
    assert chunk_markdown(text, max_chars=350) == chunk_markdown(
        text, max_chars=350
    )
    assert all(len(chunk) <= 350 for chunk in chunk_markdown(text, max_chars=350))
