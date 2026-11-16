"""The vendored source grammar (plan 60 D4) imports and answers.

The module is vendored byte-identically from the family contract
(``dev/contracts/extension_sources.py`` via
``scripts/sync-extension-contract.sh``) and is not consumed by study yet —
this keeps it importable, stdlib-clean and pinned to the family caps so the
first adopter inherits a working module, not a stale copy.
"""

from __future__ import annotations

import pytest

from app.extensions import extension_sources


def test_source_grammar_imports_with_the_frozen_api() -> None:
    assert extension_sources.MAX_ARCHIVE_ENTRIES == 512
    assert extension_sources.MAX_REF_LENGTH == 200
    assert extension_sources.MAX_SUBPATH_LENGTH == 255
    assert extension_sources.MAX_URL_LENGTH == 512
    assert issubclass(extension_sources.SourceRefError, ValueError)


def test_source_grammar_answers_every_seam() -> None:
    url = "https://git.example.com/ext/greenhouse-jobs"
    assert extension_sources.parse_url(url) == url
    assert extension_sources.parse_source_ref("main").value == "main"
    assert extension_sources.parse_source_ref("a" * 40).is_commit_pin
    assert extension_sources.parse_subpath("packs/core") == "packs/core"
    assert extension_sources.parse_commit_sha("a" * 64) == "a" * 64
    assert extension_sources.validate_archive_entry("items/x.json") == "items/x.json"


def test_source_grammar_refuses_a_forbidden_entry_with_its_code() -> None:
    with pytest.raises(extension_sources.SourceRefError) as excinfo:
        extension_sources.validate_archive_entry("items/x.txt")
    assert excinfo.value.code == "ARCHIVE_ENTRY_FORBIDDEN"
