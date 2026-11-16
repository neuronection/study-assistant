"""Shared helpers for env-gated object-storage smoke tests.

The smoke modules are skipped without credentials, so these helpers stay
dependency-free (the SDKs are imported by the contract adapters only after a
test has confirmed its env is present).
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from app.ai.gateway import LLMGateway, Message, ResolvedModel


def env_values(prefix: str) -> dict[str, str]:
    """Environment entries whose names start with ``<prefix>_``."""
    marker = f"{prefix}_"
    return {name: value for name, value in os.environ.items() if name.startswith(marker)}


def run_prefix(base: str | None, default: str) -> str:
    """A unique, slash-terminated key prefix for one smoke run."""
    stem = (base or default).strip("/") or default
    return f"{stem}/{uuid.uuid4().hex}/"


class SmokeGateway(LLMGateway):
    """A deterministic text/vision gateway for the round-trip smoke."""

    def __init__(self) -> None:
        super().__init__(session_factory=None)

    def resolve(self, task: str, course_id: str | None = None) -> ResolvedModel:
        return ResolvedModel(
            provider_id="1",
            provider_type="openai_compatible",
            base_url="http://localhost/v1",
            external_id="smoke",
            label="smoke",
            caps=["text", "vision"],
            api_key=None,
        )

    def generate(
        self,
        task: str,
        messages: list[Message],
        model: Any = None,
        course_id: str | None = None,
    ) -> str:
        return "ok"


class NoAI:
    """No-op embedder/describer so the smoke never calls a model provider."""

    def embed(self, texts: list[str]) -> tuple[str, list[list[float]]] | None:
        return None

    def describe(
        self, title: str, markdown: str, course_id: str | None = None
    ) -> dict[str, Any] | None:
        return None
