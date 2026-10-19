"""Per-extension documentation helpers (plan 34 wave 8 — the
``extensionDocsTree`` form, guidelines/extension-docs.md §10; health's
``app/extensions/docs.py`` is the family reference shape).

Three small pieces at study's registration/serve seam:

- :func:`validate_tree` — the registration-time gate: the vendored
  schema PLUS the wall semantics the schema cannot express (unique
  ids, each closed category once, at-most-one ``index``, every file
  resolving beside the tree) via the vendored contract's
  ``docs_tree_semantics``. An invalid tree is a self-disable reason
  exactly like an invalid manifest.
- :func:`landing_file` — the landing rule: array order is render
  order; the first item of the first category lands, unless exactly
  one item carries ``index: true``.
- :func:`strip_raw_html` — the markdown law (§10.7): extension-doc
  pages are markdown only. Raw HTML outside code fences/spans is
  neutralized to escaped text — the SAME fence-aware shape as the
  family's post-H3 posture (health's site removed ``rehypeRaw`` after
  a committed ``<script>`` rendered into executable static HTML);
  autolinks and full-line HTML comments stay (markdown, not HTML).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, cast

DOCS_POINTER = "docs/docs-tree.json"

_RAW_HTML = re.compile(r"<\s*/?[a-zA-Z!][^>\n]*>")
_AUTOLINK = re.compile(r"^<[a-zA-Z][a-zA-Z0-9+.\-]*(:|@)[^>\n]*>$")
_COMMENT_LINE = re.compile(r"^\s*<!--.*-->\s*$")
_FENCE = re.compile(r"^[\t ]*(`{3,}|~{3,})")

_DOCS_TREE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "contracts" / "docs-tree.schema.json"
)


def _docs_tree_schema() -> dict[str, Any]:
    try:
        return cast(
            dict[str, Any], json.loads(_DOCS_TREE_SCHEMA_PATH.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"docs-tree schema unavailable at {_DOCS_TREE_SCHEMA_PATH}: {exc} — "
            "registration fails closed (vendored contract set incomplete)"
        ) from exc


def validate_tree(tree: Any, docs_dir: Path) -> str | None:
    """Full registration-time validation: the vendored docs-tree schema
    (root document — the schema's anyOf picks the form) plus the wall
    semantics. Returns None when valid, else a path-precise reason."""
    from app.extensions import contract

    schema = _docs_tree_schema()
    err = contract.validate(schema, tree, schema)
    if err is not None:
        return err
    problems = contract.docs_tree_semantics(
        tree, exists=lambda ref: (docs_dir / ref).is_file()
    )
    if problems:
        return "; ".join(problems)
    return None


def load_tree(docs_dir: Path) -> dict[str, Any] | None:
    """Parse ``docs/docs-tree.json`` under ``docs_dir``; None when the
    bundle ships no tree."""
    path = docs_dir / "docs-tree.json"
    if not path.is_file():
        return None
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def landing_file(tree: dict[str, Any]) -> str | None:
    """The landing rule: the FIRST item of the FIRST category, unless
    exactly one item carries ``index: true`` (schema + semantics have
    already pinned at-most-one)."""
    landing: Any = None
    for category in tree.get("categories", []):
        for item in category.get("items", []):
            if item.get("index"):
                landing = item.get("file")
                break
        if landing is not None:
            break
    if landing is None:
        for category in tree.get("categories", []):
            for item in category.get("items", []):
                landing = item.get("file")
                break
            if landing is not None:
                break
    return str(landing) if landing is not None else None


def strip_raw_html(markdown: str) -> str:
    """The markdown law (§10.7): raw HTML outside code fences and
    inline code spans becomes escaped text — inert AND visible, the
    post-H3 shape. Autolinks (``<https://…>``, ``<user@host>``) and
    full-line HTML comments are markdown-adjacent exceptions, same as
    the website's gate."""
    out: list[str] = []
    in_fence = False
    for line in markdown.split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        segments = re.split(r"(`[^`\n]*`)", line)
        rebuilt = ""
        for i, segment in enumerate(segments):
            if i % 2 == 1:
                rebuilt += segment
                continue
            cursor = segment
            while True:
                match = _RAW_HTML.search(cursor)
                if not match:
                    rebuilt += cursor
                    break
                tag = match.group(0)
                if _AUTOLINK.match(tag.strip()) or _COMMENT_LINE.match(line):
                    rebuilt += cursor[: match.end()]
                else:
                    rebuilt += cursor[: match.start()]
                    rebuilt += tag.replace("<", "&lt;").replace(">", "&gt;")
                cursor = cursor[match.end() :]
        out.append(rebuilt)
    return "\n".join(out)
