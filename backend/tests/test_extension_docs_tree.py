"""The extension-SDK doc-set tree wall (plan 34 wave 5): study's
chaptered set at ``docs/dev/sdk/`` validates against the vendored
docs-tree contract and passes the same semantic checks dev's wall 14
enforces — unique node ids, every referenced file present beside the
tree, declared chapters with matching node ids — plus the contract's own
fixture suite (valid accepted, invalid rejected) through the vendored
validator, audience routing (user nodes under ``docs/user/``, dev nodes
under the set's directory), and the T3 perimeter disclosure rendered
verbatim (byte-exact) in the set's security chapter and its user page.

The product-level ``docs/docs-tree.json`` (guidelines/docs.md
audiences form) is deliberately NOT this contract's scope; a file named
``docs-tree.json`` is governed by its scope.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.extensions import contract

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "contracts"
SDK_TREE = REPO_ROOT / "docs" / "dev" / "sdk" / "docs-tree.json"
SECURITY_PAGE = REPO_ROOT / "docs" / "dev" / "sdk" / "security-and-gotchas.md"
CONNECTOR_USER_PAGE = REPO_ROOT / "docs" / "user" / "add-an-mcp-connector.md"
CHARTER = json.loads((CONTRACTS_DIR / "extension-charter.json").read_text(encoding="utf-8"))

DOCS_TREE_SCHEMA = json.loads((CONTRACTS_DIR / "docs-tree.schema.json").read_text(encoding="utf-8"))
DOCS_TREE_FIXTURES = json.loads(
    (CONTRACTS_DIR / "docs-tree.fixtures.json").read_text(encoding="utf-8")
)

EXPECTED_CHAPTERS = (
    "overview",
    "quickstart",
    "core-concepts",
    "installation-and-modes",
    "authoring-and-configuration",
    "examples-and-use-cases",
    "security-and-gotchas",
    "reference",
    "versioning-and-migration",
    "troubleshooting-and-faq",
)


def _walk_nodes(doc: dict[str, Any]) -> list[dict[str, Any]]:
    stack = list(doc.get("roots", []))
    nodes: list[dict[str, Any]] = []
    while stack:
        node = stack.pop(0)
        nodes.append(node)
        stack.extend(node.get("children", []))
    return nodes


# ------------------------------------------------- the vendored fixture wall


@pytest.mark.parametrize("case", DOCS_TREE_FIXTURES.get("valid", []), ids=lambda case: case["name"])
def test_docs_tree_fixtures_accept(case: dict[str, Any]) -> None:
    assert contract.validate(DOCS_TREE_SCHEMA, case["doc"], DOCS_TREE_SCHEMA) is None


@pytest.mark.parametrize(
    "case", DOCS_TREE_FIXTURES.get("invalid", []), ids=lambda case: case["name"]
)
def test_docs_tree_fixtures_reject(case: dict[str, Any]) -> None:
    """Mirrors dev wall 14's fixture runner: an invalid case is rejected
    by the schema OR by the wall semantics (unique ids, at-most-one
    index, category slugs once — the checks JSON Schema cannot express;
    the vendored contract module carries them)."""
    err = contract.validate(DOCS_TREE_SCHEMA, case["doc"], DOCS_TREE_SCHEMA)
    sem = contract.docs_tree_semantics(case["doc"])
    assert err is not None or sem, f"invalid case {case['name']} was accepted"


# -------------------------------------------------------- study's real tree


def test_sdk_docs_tree_validates_against_the_contract() -> None:
    doc = json.loads(SDK_TREE.read_text(encoding="utf-8"))
    err = contract.validate(DOCS_TREE_SCHEMA, doc, DOCS_TREE_SCHEMA)
    assert err is None, err


def test_sdk_docs_tree_declares_exactly_the_ten_chapters() -> None:
    doc = json.loads(SDK_TREE.read_text(encoding="utf-8"))
    assert tuple(doc["chapters"]) == EXPECTED_CHAPTERS


def test_sdk_docs_tree_unique_ids_files_exist_and_chapters_match_nodes() -> None:
    doc = json.loads(SDK_TREE.read_text(encoding="utf-8"))
    nodes = _walk_nodes(doc)
    ids = [node["id"] for node in nodes]

    dupes = sorted({node_id for node_id in ids if ids.count(node_id) > 1})
    assert not dupes, f"duplicate node ids {dupes}"

    for chapter in doc.get("chapters", []):
        assert chapter in ids, f"declared chapter {chapter!r} has no matching node id"

    for node in nodes:
        file_ref = node.get("file")
        if not file_ref:
            continue
        path = (SDK_TREE.parent / file_ref).resolve()
        assert path.is_file(), f"node {node['id']!r} references missing file {file_ref!r}"
        assert REPO_ROOT in path.parents, f"node {node['id']!r} escapes the repo: {file_ref!r}"


def test_sdk_docs_tree_audience_routing_matches_file_locations() -> None:
    """The audience tag is where the page lives: user nodes under
    docs/user/, dev nodes under the set's own directory."""
    doc = json.loads(SDK_TREE.read_text(encoding="utf-8"))
    for node in _walk_nodes(doc):
        file_ref = node.get("file")
        if not file_ref:
            continue
        resolved = (SDK_TREE.parent / file_ref).resolve()
        if node["audience"] == "user":
            assert resolved.parent == (REPO_ROOT / "docs" / "user").resolve(), (
                f"user node {node['id']!r} must live under docs/user/: {file_ref}"
            )
        else:
            assert resolved.parent == SDK_TREE.parent.resolve(), (
                f"dev node {node['id']!r} must live under docs/dev/sdk/: {file_ref}"
            )


def test_every_set_page_is_listed_in_the_product_tree_exactly_once() -> None:
    """Set pages that live under the product docs/ tree are listed in BOTH
    trees (guidelines/extension-docs.md §4): once for site nav, once for
    chapter conformance."""
    product_tree = json.loads((REPO_ROOT / "docs" / "docs-tree.json").read_text(encoding="utf-8"))
    product_files = [
        item["file"]
        for audience in product_tree["audiences"]
        for category in audience["categories"]
        for item in category["items"]
    ]
    set_doc = json.loads(SDK_TREE.read_text(encoding="utf-8"))
    for node in _walk_nodes(set_doc):
        file_ref = node.get("file")
        if not file_ref:
            continue
        product_ref = str((SDK_TREE.parent / file_ref).resolve().relative_to(REPO_ROOT / "docs"))
        count = product_files.count(product_ref)
        assert count == 1, f"{product_ref} listed {count} times in docs/docs-tree.json (want 1)"


# ----------------------------------------------------- the doc-check walls


def _t3_disclosure() -> str:
    return str(CHARTER["consent"]["t3PerimeterDisclosure"])


@pytest.mark.parametrize(
    "page", [SECURITY_PAGE, CONNECTOR_USER_PAGE], ids=["security-chapter", "connector-user-page"]
)
def test_t3_perimeter_disclosure_is_verbatim(page: Path) -> None:
    """The charter consent copy is data, not copy: it must appear
    byte-exact (single blockquote line) in the security chapter and the
    connector user page — the same wall the settings card obeys."""
    text = page.read_text(encoding="utf-8")
    disclosure = _t3_disclosure()
    assert f"> {disclosure}" in text, (
        f"{page.name} must embed the T3 perimeter disclosure verbatim as a blockquote"
    )


def test_set_internal_links_resolve() -> None:
    link_re = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)\s]*)?\)")
    for md in sorted(SDK_TREE.parent.glob("*.md")):
        text = md.read_text(encoding="utf-8")
        for ref in link_re.findall(text):
            target = (md.parent / ref).resolve()
            assert target.is_file(), f"{md.name} links to missing {ref}"
            assert REPO_ROOT in target.parents, f"{md.name} escapes the repo: {ref}"
