"""Family web-search contract wall (ADR-0035 / plan 28).

The vendored core (app/search/providers_contract.py, dev canonical
contracts/search_providers.py — never edited here) must satisfy every
fixture in providers_contract.fixtures.json exactly: same requests out,
same normalized hits (or the same SearchError kind) in. The fixtures are
the cross-language acceptance suite — desktop's TS reference
implementation runs the same cases (plan 28 Phase 3).
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.search.providers_contract import (
    PROVIDER_TYPES,
    SearchError,
    normalize_provider_config,
    perform_search,
)

FIXTURES_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "search" / "providers_contract.fixtures.json"
)
CASES: list[dict[str, Any]] = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))["cases"]


def _transport_for(case: dict[str, Any]) -> httpx.MockTransport | None:
    if case["request"] is None:
        return None
    request_spec = case["request"]
    response_spec = case["response"]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == request_spec["method"], f"{case['id']}: method"
        actual = str(request.url)
        expected_base = request_spec["url"].rstrip("/")
        assert actual.split("?")[0] == expected_base, f"{case['id']}: url {actual}"
        for key, value in (request_spec.get("params") or {}).items():
            assert request.url.params.get(key) == value, f"{case['id']}: param {key}"
        if "auth_bearer" in request_spec:
            assert request.headers.get("Authorization") == f"Bearer {request_spec['auth_bearer']}", (
                f"{case['id']}: bearer"
            )
        for header in request_spec.get("header", "").split(";") if request_spec.get("header") else []:
            name, _, value = header.partition(":")
            assert request.headers.get(name) == value, f"{case['id']}: header {name}"
        if "body_contains" in request_spec:
            body = json.loads(request.content)
            for key, value in request_spec["body_contains"].items():
                assert body.get(key) == value, f"{case['id']}: body {key}"
        if "json" in response_spec:
            return httpx.Response(response_spec["status"], json=response_spec["json"])
        return httpx.Response(
            response_spec["status"],
            text=response_spec.get("text", ""),
            headers={"content-type": response_spec.get("content_type", "text/plain")},
        )

    return httpx.MockTransport(handler)


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_fixture(case: dict[str, Any]) -> None:
    config = case["config"]
    if "expected_error_kind" in case:
        with pytest.raises(SearchError) as excinfo:
            perform_search(
                config,
                case["query"],
                api_key=case.get("api_key", ""),
                transport=_transport_for(case),
            )
        assert excinfo.value.kind == case["expected_error_kind"], (
            f"{case['id']}: kind {excinfo.value.kind} != {case['expected_error_kind']}"
        )
        return
    hits = perform_search(
        config,
        case["query"],
        api_key=case.get("api_key", ""),
        transport=_transport_for(case),
    )
    assert hits == case["expected_hits"], case["id"]


def test_every_fixture_provider_type_is_known() -> None:
    for case in CASES:
        if "expected_error_kind" not in case:
            assert case["config"]["type"] in PROVIDER_TYPES, case["id"]


def test_normalize_clamps_and_defaults() -> None:
    normalized = normalize_provider_config(
        {"id": "sp1", "type": "tavily", "max_results": 99, "timeout_ms": 10}
    )
    assert normalized["max_results"] == 10
    assert normalized["timeout_ms"] == 500
    assert normalized["enabled"] is True
    # default base URLs apply at fetch time (effective base), not in the config
    assert normalized["base_url"] is None
