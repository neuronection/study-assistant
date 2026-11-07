"""Generate the schema inventory half of `docs/dev/schema-contract.md`.

`--check` fails when the checked-in block differs from a fresh render (the CI
drift guard); `--write` updates the doc.

Run from `backend/` (the same way `export-openapi.py` is run):

    uv run python ../scripts/schema_inventory.py --check
"""

import sys
from pathlib import Path

from app.domain import models  # noqa: F401  (registers every table)
from app.domain.schema_inventory import render

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "dev" / "schema-contract.md"
START = "<!-- schema-inventory:start -->"
END = "<!-- schema-inventory:end -->"


def splice(document: str, block: str) -> str:
    start = document.index(START) + len(START)
    end = document.index(END)
    return document[:start] + "\n" + block + "\n" + document[end:]


def main(argv: list[str]) -> int:
    block = render()
    if "--check" in argv:
        document = DOC.read_text()
        if splice(document, block) != document:
            print(f"{DOC.relative_to(ROOT)} is stale — run scripts/schema_inventory.py --write")
            return 1
        print("schema inventory is up to date")
        return 0
    DOC.write_text(splice(DOC.read_text(), block))
    print(f"wrote {DOC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
