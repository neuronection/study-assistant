"""Shared wire-parameter fixture wall (ADR-0038) — study's side.

Loads the vendored fixture table (byte-identical across the family:
``dev/contracts/wire-params.fixtures.json`` → ``tests/fixtures/``). A row
change is a contract change — every repo must pass the same rows. Policy
rows hit the vendored ``app.ai.wire_params`` module directly; temperature
rows run through study's own factory (omit-unless-configured).
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.ai.chat_models import build_chat_model
from app.ai.types import ResolvedModel
from app.ai.wire_params import is_openai_endpoint, resolve_chat_transport, resolve_max_tokens_param

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "wire_params.fixtures.json").read_text()
)


def _temperature_model(row: Any) -> Any:
    resolved = ResolvedModel(
        provider_id=1,
        provider_type="openai_compatible",
        base_url="http://localhost:8080/v1",
        external_id=FIXTURES["temperatureModelId"],
        label="wire-fixture",
        caps=["text"],
        api_key=None,
        temperature=row["temperature"],
    )
    return build_chat_model(
        resolved,
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
        timeout=5.0,
    )


@pytest.mark.parametrize("row", FIXTURES["endpointDetection"], ids=lambda r: r["name"])
def test_endpoint_detection(row: Any) -> None:
    assert is_openai_endpoint(row["apiBase"]) is row["expected"]


@pytest.mark.parametrize("row", FIXTURES["maxTokensParam"], ids=lambda r: r["name"])
def test_max_tokens_param_resolution(row: Any) -> None:
    resolved = resolve_max_tokens_param(row["providerType"], row["apiBase"], row["override"])
    assert resolved == row["expected"]


@pytest.mark.parametrize("row", FIXTURES["chatTransport"], ids=lambda r: r["name"])
def test_chat_transport_resolution(row: Any) -> None:
    resolved = resolve_chat_transport(row["providerType"], row["apiBase"], row["override"])
    assert resolved == row["expected"]


@pytest.mark.parametrize("row", FIXTURES["temperatureOmission"], ids=lambda r: r["name"])
def test_temperature_omission(row: Any) -> None:
    model = _temperature_model(row)
    assert ("temperature" in model._default_params) is row["sent"]
