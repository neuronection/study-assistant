"""The schema-contract wall (plan 81 A; grows in B/D/E).

Every table must appear in the generated inventory, the inventory must be
byte-identical to a fresh render, every JSON column must have a declared
species, every closed set must name a real column, and every table must
declare how it is profile-scoped.
"""

from pathlib import Path

from sqlalchemy import JSON

from app.domain import (
    models,  # noqa: F401
    schema_contract,
)
from app.domain.schema_inventory import render
from app.storage.db import Base

DOC = Path(__file__).resolve().parents[2] / "docs" / "dev" / "schema-contract.md"
START = "<!-- schema-inventory:start -->"
END = "<!-- schema-inventory:end -->"


def _splice(document: str, block: str) -> str:
    start = document.index(START) + len(START)
    end = document.index(END)
    return document[:start] + "\n" + block + "\n" + document[end:]


def test_inventory_is_current() -> None:
    document = DOC.read_text()
    assert _splice(document, render()) == document, (
        "docs/dev/schema-contract.md is stale — run "
        "`cd backend && uv run python ../scripts/schema_inventory.py --write`"
    )


def test_every_model_table_is_listed() -> None:
    document = DOC.read_text()
    for table in Base.metadata.tables:
        assert f"| `{table}` |" in document, f"{table} is missing from the inventory"


def test_every_table_declares_its_profile_scope() -> None:
    missing = sorted(set(Base.metadata.tables) - set(schema_contract.PROFILE_SCOPE))
    assert not missing, f"tables without a PROFILE_SCOPE entry: {missing}"
    stale = sorted(set(schema_contract.PROFILE_SCOPE) - set(Base.metadata.tables))
    assert not stale, f"PROFILE_SCOPE names missing tables: {stale}"


def test_every_json_column_has_a_species() -> None:
    json_columns = {
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, JSON)
    }
    unclassified = sorted(json_columns - set(schema_contract.JSON_SPECIES))
    assert not unclassified, f"JSON columns without a declared species: {unclassified}"
    stale = sorted(set(schema_contract.JSON_SPECIES) - json_columns)
    assert not stale, f"JSON_SPECIES names columns that are not JSON: {stale}"
    assert set(schema_contract.JSON_SPECIES.values()) <= {
        schema_contract.DOCUMENT,
        schema_contract.STATE,
        schema_contract.LIST,
    }


def test_closed_sets_name_real_columns() -> None:
    for key in schema_contract.CLOSED_SETS:
        table_name, _, column_name = key.partition(".")
        table = Base.metadata.tables.get(table_name)
        assert table is not None, f"CLOSED_SETS names missing table {table_name}"
        assert column_name in table.columns, f"CLOSED_SETS names missing column {key}"
        assert table.columns[column_name].type.python_type is str, f"{key} is not a string column"
