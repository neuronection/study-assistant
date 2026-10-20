"""Extension registry — the host profile (family extension charter,
ADR-0040 D24/D3/D18).

Study hosts the **connector** kind at T0 (the vendored ADR-0035 trio) +
T1 (the bundled connectors under ``builtin/``) + T3 (MCP external
processes). Bundled extensions live one directory per envelope id under
``builtin/``: ``manifest.json`` — the charter envelope, validated AT
REGISTRATION against the vendored schema. A structurally invalid manifest
throws at registration (the bundled set is in-repo reviewed code — a bad
manifest is a developer error, never a half-running extension).

Capability law (D3/D18): what an extension may do is DECLARED in its
manifest ``capabilities`` and gated here — consumers ask
:meth:`ExtensionRegistry.has_capability`, and an undeclared capability is
never exercised (the probing era is over). What the host honors comes
from the study host profile in the vendored charter
(``hostProfiles.profiles[product=study-assistant].honors``) — no
hand-written vocabulary copy.

Registry keys are the envelope ``id`` (hyphenated, the charter form);
directories use the importable underscore form — health's ``domain_of``
mapping, mechanical in both directions.
"""

import json
from pathlib import Path
from typing import Any, cast

_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts" / "extension-manifest.schema.json"
_CHARTER_PATH = Path(__file__).resolve().parents[3] / "contracts" / "extension-charter.json"

BUNDLED_IDS = ("external-sources", "discovery", "mcp")

_BUNDLED_DIRS = {
    "external-sources": "external_sources",
    "discovery": "discovery",
    "mcp": "mcp",
}

_STUDY_PROFILE_PRODUCT = "study-assistant"


def dir_of(extension_id: str) -> str:
    """The importable package/slot name of an envelope id."""
    return _BUNDLED_DIRS[extension_id]


def _base_path() -> Path:
    return Path(__file__).resolve().parent / "builtin"


def _bundled_manifest_schema() -> dict[str, Any]:
    try:
        return cast(dict[str, Any], json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"extension manifest schema unavailable at {_SCHEMA_PATH}: {exc} — "
            "registration fails closed (vendored contract set incomplete)"
        ) from exc


def _charter() -> dict[str, Any]:
    try:
        return cast(dict[str, Any], json.loads(_CHARTER_PATH.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"extension charter unavailable at {_CHARTER_PATH}: {exc} — "
            "registration fails closed (vendored contract set incomplete)"
        ) from exc


def _profile() -> dict[str, Any]:
    for profile in _charter()["hostProfiles"]["profiles"]:
        if profile.get("product") == _STUDY_PROFILE_PRODUCT:
            return cast(dict[str, Any], profile)
    raise RuntimeError(
        f"no {product_label()} host profile in the vendored charter — registration fails closed"
    )


def study_honored_capabilities() -> frozenset[str]:
    """What the study host implements, from the vendored charter."""
    return frozenset(_profile().get("honors") or ())


def _docs_tree_schema() -> dict[str, Any]:
    path = _SCHEMA_PATH.parent / "docs-tree.schema.json"
    try:
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"docs-tree schema unavailable at {path}: {exc} — "
            "registration fails closed (vendored contract set incomplete)"
        ) from exc


def product_label() -> str:
    return _STUDY_PROFILE_PRODUCT


class ExtensionRegistry:
    def __init__(self) -> None:
        self._manifests: dict[str, dict[str, Any]] = {}

    def register_builtins(self, *, manifests: dict[str, dict[str, Any]] | None = None) -> None:
        """Validate + admit every bundled manifest (D24/D3: throws at
        registration). ``manifests`` overrides the on-disk set (tests)."""
        from app.extensions import contract

        schema = _bundled_manifest_schema()
        charter = _charter()
        profile = _profile()
        docs_schema = _docs_tree_schema()
        source = (
            {ext_id: self._read_manifest(ext_id) for ext_id in BUNDLED_IDS}
            if manifests is None
            else manifests
        )
        registered: dict[str, dict[str, Any]] = {}
        for ext_id, manifest in source.items():
            problems = contract.validate_registration(
                manifest,
                schema=schema,
                bundled=True,
                profile=profile,
                docs_root=_base_path() / dir_of(ext_id)
                if ext_id in _BUNDLED_DIRS
                else None,
                docs_schema=docs_schema,
                charter=charter,
            )
            if problems:
                raise ValueError(
                    f"bundled extension {ext_id!r} manifest invalid: {'; '.join(problems)}"
                )
            registered[ext_id] = manifest
        self._manifests = registered

    def _read_manifest(self, ext_id: str) -> dict[str, Any]:
        manifest_path = _base_path() / dir_of(ext_id) / "manifest.json"
        try:
            manifest = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"manifest unreadable for {ext_id!r}: {manifest_path}: {exc}"
            ) from exc
        if manifest.get("id") != ext_id:
            raise ValueError(f"manifest id {manifest.get('id')!r} does not match slot {ext_id!r}")
        return manifest

    def get_manifest(self, extension_id: str) -> dict[str, Any] | None:
        return self._manifests.get(extension_id)

    def get_all_manifests(self) -> dict[str, dict[str, Any]]:
        return dict(self._manifests)

    def has_capability(self, extension_id: str, capability: str) -> bool:
        """The declared-capability gate (D3): the ONLY answer to "can this
        extension do X?" — unknown/unregistered ids declare nothing."""
        manifest = self._manifests.get(extension_id) or {}
        return capability in (manifest.get("capabilities") or [])

    def capabilities(self, extension_id: str) -> list[str]:
        return list((self._manifests.get(extension_id) or {}).get("capabilities") or [])

    def base_dir(self, extension_id: str) -> Path:
        """Absolute path of a bundled extension's directory (docs, assets)."""
        return _base_path() / dir_of(extension_id)


def t3_perimeter_disclosure() -> str:
    """The charter's T3 perimeter consent copy — rendered VERBATIM (D22;
    paraphrasing it away is a conformance failure)."""
    charter = _charter()
    return str(charter["consent"]["t3PerimeterDisclosure"])


def host_profile_view() -> dict[str, Any]:
    """The author-visible host profile (plan 37 §6.2.4): what this host
    hosts and honors, with the sandbox posture stated as data."""
    profile = _profile()
    return {
        "product": profile.get("product"),
        "class": profile.get("class"),
        "kinds": profile.get("kinds", []),
        "tiers": profile.get("tiers", []),
        "honors": profile.get("honors", []),
        "honorsByTier": profile.get("honorsByTier", {}),
        "honorsByKind": profile.get("honorsByKind", {}),
        "surfaces": profile.get("surfaces"),
        "apiVersion": {"envelope": "extension/v1", "connectorKindVersion": 1},
        "degradeRules": _charter()["surfaces"]["degradeRules"],
        "t2Isolation": "none",
        "disclosures": ["t3PerimeterDisclosure"],
    }


extension_registry = ExtensionRegistry()
extension_registry.register_builtins()
