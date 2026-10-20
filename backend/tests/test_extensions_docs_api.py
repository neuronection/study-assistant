"""The per-extension documentation surface (plan 34 wave 8 — the
``extensionDocsTree`` form): registration-time validation of the
manifest ``docs`` binding, the GET documentation endpoint (tree +
markdown, landing rule, traversal-safe, raw HTML neutralized), and the
T3 perimeter disclosure rendered verbatim in the bundled mcp
connector's docs — the charter copy is data, not prose.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.extensions import docs as ext_docs
from app.extensions.registry import BUNDLED_IDS, ExtensionRegistry, extension_registry

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts"
BUILTIN_ROOT = Path(__file__).resolve().parents[1] / "app" / "extensions" / "builtin"
CHARTER = cast(
    dict[str, Any],
    json.loads((CONTRACTS_DIR / "extension-charter.json").read_text(encoding="utf-8")),
)


# --------------------------------------------------- the docs binding gate


def _manifest_copy(ext_id: str) -> dict[str, Any]:
    path = BUILTIN_ROOT / "external_sources" / "manifest.json"
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _registry_with_tmp_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tree: dict[str, Any] | None,
) -> ExtensionRegistry:
    """A registry whose on-disk bundle root is ``tmp_path`` — one
    external-sources bundle with (optionally) a docs tree beside the
    manifest slot, so a broken docs promise is testable without touching
    the real builtin tree."""
    slot = tmp_path / "external_sources"
    docs_dir = slot / "docs"
    docs_dir.mkdir(parents=True)
    if tree is not None:
        (docs_dir / "docs-tree.json").write_text(json.dumps(tree), encoding="utf-8")
    monkeypatch.setattr("app.extensions.registry._base_path", lambda: tmp_path)
    return ExtensionRegistry()


def test_every_bundled_extension_carries_a_valid_docs_tree() -> None:
    pointed = 0
    for ext_id in BUNDLED_IDS:
        manifest = extension_registry.get_manifest(ext_id)
        assert manifest is not None
        pointer = manifest.get("docs")
        if pointer is None:
            continue
        pointed += 1
        assert pointer == ext_docs.DOCS_POINTER
        docs_dir = extension_registry.base_dir(ext_id) / "docs"
        tree = ext_docs.load_tree(docs_dir)
        assert tree is not None, f"{ext_id}: pointer without a tree"
        assert ext_docs.validate_tree(tree, docs_dir) is None, f"{ext_id}: invalid tree"
        assert ext_docs.landing_file(tree) is not None, f"{ext_id}: no landing page"
    assert pointed == len(BUNDLED_IDS), (
        "all three bundled connectors document themselves (plan 34 wave 8)"
    )


def test_docs_pointer_without_tree_throws_at_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest_copy("external-sources")
    registry = _registry_with_tmp_bundle(tmp_path, monkeypatch, tree=None)
    with pytest.raises(ValueError, match="tree is unreadable"):
        registry.register_builtins(
            manifests={"external-sources": manifest, "discovery": {}, "mcp": {}}
        )


def test_docs_pointer_with_invalid_tree_throws_at_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest_copy("external-sources")
    docs_dir = BUILTIN_ROOT / "external_sources" / "docs"
    tree = json.loads((docs_dir / "docs-tree.json").read_text(encoding="utf-8"))
    tree["categories"][0]["category"] = "getting-started"
    registry = _registry_with_tmp_bundle(tmp_path, monkeypatch, tree=tree)
    with pytest.raises(ValueError, match="\\$\\.docs:"):
        registry.register_builtins(
            manifests={"external-sources": manifest, "discovery": {}, "mcp": {}}
        )


def test_docs_pointer_with_wrong_value_throws_at_registration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _manifest_copy("external-sources")
    manifest["docs"] = "docs/other-tree.json"
    registry = _registry_with_tmp_bundle(tmp_path, monkeypatch, tree=None)
    with pytest.raises(ValueError, match="manifest invalid"):
        registry.register_builtins(
            manifests={"external-sources": manifest, "discovery": {}, "mcp": {}}
        )


def test_manifest_without_pointer_registers_without_a_tree() -> None:
    """Honest absence (§10.3): no pointer ⇒ no docs promise — the bundle
    registers fine (the other bundles' pointers still resolve)."""
    manifests = {
        ext_id: json.loads(
            (extension_registry.base_dir(ext_id) / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        for ext_id in BUNDLED_IDS
    }
    del manifests["external-sources"]["docs"]
    registry = ExtensionRegistry()
    registry.register_builtins(manifests=manifests)
    assert "docs" not in (registry.get_manifest("external-sources") or {})


def test_docs_tree_semantics_reject_duplicate_index_and_escape() -> None:
    docs_dir = BUILTIN_ROOT / "external_sources" / "docs"
    tree = json.loads((docs_dir / "docs-tree.json").read_text(encoding="utf-8"))

    duplicated = json.loads(json.dumps(tree))
    duplicated["categories"][0]["items"][0]["index"] = True
    duplicated["categories"][1]["items"][0]["index"] = True
    problems = ext_docs.validate_tree(duplicated, docs_dir)
    assert problems is not None and "index" in problems

    escaping = json.loads(json.dumps(tree))
    escaping["categories"][0]["items"][0]["file"] = "../manifest.json"
    problems = ext_docs.validate_tree(escaping, docs_dir)
    assert problems is not None, (
        "an escaping file ref must be rejected (the schema's file pattern "
        "pins it shut; semantics catch whatever the pattern cannot)"
    )


def test_docs_tree_files_resolve_beside_the_tree() -> None:
    for ext_id in BUNDLED_IDS:
        docs_dir = extension_registry.base_dir(ext_id) / "docs"
        tree = json.loads((docs_dir / "docs-tree.json").read_text(encoding="utf-8"))
        problems = ext_docs.validate_tree(tree, docs_dir)
        assert problems is None, f"{ext_id}: {problems}"


# ------------------------------------------------------- the landing rule


def test_landing_rule_prefers_the_index_flag() -> None:
    tree = {
        "version": 1,
        "categories": [
            {
                "category": "overview",
                "items": [{"id": "a", "file": "a.md"}],
            },
            {
                "category": "usage",
                "items": [{"id": "b", "file": "b.md", "index": True}],
            },
        ],
    }
    assert ext_docs.landing_file(tree) == "b.md"


def test_landing_rule_defaults_to_the_first_item() -> None:
    tree = {
        "version": 1,
        "categories": [
            {
                "category": "overview",
                "items": [{"id": "a", "file": "a.md"}, {"id": "b", "file": "b.md"}],
            }
        ],
    }
    assert ext_docs.landing_file(tree) == "a.md"


# ------------------------------------------------------------ the markdown law


def test_strip_raw_html_neutralizes_tags_but_spares_fences_and_autolinks() -> None:
    page = (
        "# Title\n\n"
        "<script>alert(1)</script>\n\n"
        "```\n<div>inside a fence stays</div>\n```\n\n"
        "See <https://example.org> and `<b>inline code</b>`.\n"
    )
    out = ext_docs.strip_raw_html(page)
    assert "<script>" not in out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out
    assert "<div>inside a fence stays</div>" in out
    assert "<https://example.org>" in out
    assert "<b>inline code</b>" in out


def test_strip_raw_html_spares_full_line_comments() -> None:
    assert ext_docs.strip_raw_html("<!-- sync-marker -->\n") == "<!-- sync-marker -->\n"


# ---------------------------------------------------------------- the endpoint


def test_documentation_opens_on_the_landing_page(client: TestClient) -> None:
    with client:
        body = client.get("/api/v1/extensions/mcp/documentation").json()
    assert body["tree"]["version"] == 1
    assert body["markdown"].startswith("# Overview")
    landing = ext_docs.landing_file(body["tree"])
    assert landing is not None
    page = (
        BUILTIN_ROOT / "mcp" / "docs" / landing
    ).read_text(encoding="utf-8")
    assert body["markdown"] == ext_docs.strip_raw_html(page)


def test_documentation_serves_requested_pages(client: TestClient) -> None:
    with client:
        body = client.get(
            "/api/v1/extensions/mcp/documentation", params={"file": "security.md"}
        ).json()
    assert "The perimeter, stated plainly" in body["markdown"]


def test_documentation_traversal_is_pinned_to_the_docs_dir(client: TestClient) -> None:
    with client:
        body = client.get(
            "/api/v1/extensions/mcp/documentation",
            params={"file": "../../../contracts/extension-charter.json"},
        ).json()
    assert "Could not find file" in body["markdown"]
    assert "t3PerimeterDisclosure" not in body["markdown"]
    assert "hostProfiles" not in body["markdown"]


def test_documentation_404_for_unknown_extensions(client: TestClient) -> None:
    with client:
        response = client.get("/api/v1/extensions/no-such/documentation")
    assert response.status_code == 404


def test_documentation_honest_absence_without_a_pointer(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifests = {
        ext_id: json.loads(
            (extension_registry.base_dir(ext_id) / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        for ext_id in BUNDLED_IDS
    }
    del manifests["external-sources"]["docs"]
    registry = ExtensionRegistry()
    registry.register_builtins(manifests=manifests)
    monkeypatch.setattr(extension_registry, "_manifests", registry._manifests)
    monkeypatch.setattr(
        extension_registry,
        "base_dir",
        lambda ext_id: tmp_path / ext_id.replace("-", "_"),
    )
    with client:
        body = client.get("/api/v1/extensions/external-sources/documentation").json()
    assert body["tree"] is None
    assert "No documentation provided" in body["markdown"]


# --------------------------------------------------- the T3 disclosure verbatim


def test_mcp_docs_render_the_t3_perimeter_disclosure_verbatim() -> None:
    page = (BUILTIN_ROOT / "mcp" / "docs" / "security.md").read_text(encoding="utf-8")
    disclosure = str(CHARTER["consent"]["t3PerimeterDisclosure"])
    assert f"> {disclosure}" in page, (
        "the mcp connector's security page must embed the T3 perimeter "
        "disclosure verbatim as a blockquote (charter copy is data, not prose)"
    )
    assert page.count(disclosure) == 1
