"""The extension registry wall (plan 32 Phase 7): registration validates the
bundled manifests against the vendored envelope schema and THROWS on an
invalid or unhonored-capability manifest (D3/D24 — never mid-run, never
half-running), capability use is gated by declared data, and the D19 secret
law (x-secret fields never in stored config) is checked for the mcp
instances.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from app.extensions.registry import BUNDLED_IDS, ExtensionRegistry, extension_registry

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts"
MANIFEST_FIXTURES = json.loads(
    (CONTRACTS_DIR / "extension-contract.fixtures.json").read_text(encoding="utf-8")
)
MANIFEST_SCHEMA = json.loads(
    (CONTRACTS_DIR / "extension-manifest.schema.json").read_text(encoding="utf-8")
)


def _valid_manifest_copy() -> dict[str, Any]:
    """A byte-copy of study's own bundled external-sources manifest."""
    from app.extensions.registry import _base_path, dir_of

    path = _base_path() / dir_of("external-sources") / "manifest.json"
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def test_builtins_registered_at_import() -> None:
    assert set(extension_registry.get_all_manifests()) == set(BUNDLED_IDS)
    for ext_id in BUNDLED_IDS:
        manifest = extension_registry.get_manifest(ext_id)
        assert manifest is not None
        assert manifest["kind"] == "connector"
        assert manifest["apiVersion"] == "extension/v1"
        assert manifest["kindVersion"] == 1


def test_bundled_manifests_match_their_slot_dirs() -> None:
    from app.extensions.registry import _base_path, dir_of

    for ext_id in BUNDLED_IDS:
        path = _base_path() / dir_of(ext_id) / "manifest.json"
        on_disk = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        assert on_disk == extension_registry.get_manifest(ext_id), ext_id


def test_registration_throws_on_invalid_manifest() -> None:
    invalid = _valid_manifest_copy()
    del invalid["kindVersion"]  # connector refinement version is required
    with pytest.raises(ValueError, match="manifest invalid"):
        ExtensionRegistry().register_builtins(
            manifests={"external-sources": invalid, "discovery": {}, "mcp": {}}
        )


def test_registration_throws_on_unhonored_capability() -> None:
    manifest = _valid_manifest_copy()
    manifest["capabilities"] = ["ui:custom-code"]
    with pytest.raises(ValueError, match="not honored by this host profile"):
        ExtensionRegistry().register_builtins(
            manifests={"external-sources": manifest, "discovery": {}, "mcp": {}}
        )


def test_has_capability_is_declared_data_only() -> None:
    assert extension_registry.has_capability("external-sources", "sync") is True
    assert extension_registry.has_capability("external-sources", "net") is False
    assert extension_registry.has_capability("discovery", "chat-tools") is True
    assert extension_registry.has_capability("mcp", "secrets") is True
    assert extension_registry.has_capability("mcp", "net") is False
    assert extension_registry.has_capability("unknown", "net") is False


def test_discover_tool_declares_read_only_risk_class() -> None:
    manifest = extension_registry.get_manifest("discovery") or {}
    tools = {tool["id"]: tool for tool in manifest.get("tools", [])}
    assert tools["discover"]["riskClass"] == "read-only"


def test_secret_law_mcp_manifest_declares_the_sealed_slots() -> None:
    """D19: token/env are x-secret-marked in the bundled mcp manifest and
    the stored rows never carry their values (the keyring-sealed slots are
    the only home — pinned for real flows by
    test_create_remote_server_stores_secrets_in_keyring)."""
    manifest = extension_registry.get_manifest("mcp") or {}
    schema_fields = (manifest.get("configSchema") or {}).get("properties") or {}
    x_secret = {
        name
        for name, field in schema_fields.items()
        if isinstance(field, dict) and field.get("x-secret") is True
    }
    assert {"token", "env"} <= x_secret
