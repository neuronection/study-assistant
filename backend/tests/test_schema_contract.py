"""The schema-contract wall (plan 81 A; grows in B/D/E).

Every table must appear in the generated inventory, the inventory must be
byte-identical to a fresh render, every JSON column must have a declared
species, every closed set must name a real column, and every table must
declare how it is profile-scoped.
"""

import types
from pathlib import Path
from typing import get_args, get_type_hints

from sqlalchemy import JSON, CheckConstraint, Integer

from app.domain import (
    documents,
    models,  # noqa: F401
    payloads,
    schema_contract,
)
from app.domain.schema_inventory import render
from app.storage.db import Base

DOC = Path(__file__).resolve().parents[2] / "docs" / "dev" / "schema-contract.md"
INVENTORY = Path(__file__).resolve().parents[2] / "contracts" / "data-model.jsonb-inventory.txt"
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


def _json_inventory() -> dict[str, str]:
    rows: dict[str, str] = {}
    for raw in INVENTORY.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, rest = line.partition("::")
        assert rest, f"malformed JSONB inventory row: {line}"
        rows[key.strip()] = rest.strip().split()[0]
    return rows


def test_jsonb_inventory_classifies_every_json_column() -> None:
    inventory = _json_inventory()
    json_columns = {
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, JSON)
    }
    keep_open = {key for key, verdict in inventory.items() if verdict == "keep-open"}
    typed_out = {key for key, verdict in inventory.items() if verdict == "typed-out"}
    assert keep_open == json_columns, (
        "contracts/data-model.jsonb-inventory.txt is stale — missing: "
        f"{sorted(json_columns - keep_open)}, stale: {sorted(keep_open - json_columns)}"
    )
    assert not typed_out & json_columns, (
        f"typed-out rows still name live JSON columns: {sorted(typed_out & json_columns)}"
    )
    assert set(inventory.values()) <= {"keep-open", "typed-out"}
    stale_tables = {
        key.partition(".")[0]
        for key in inventory
        if key.partition(".")[0] not in Base.metadata.tables
    }
    assert not stale_tables, f"inventory names missing tables: {sorted(stale_tables)}"


def test_versioned_documents_have_their_version_sibling() -> None:
    assert set(documents.DOCUMENT_KINDS) == set(documents.VERSION_SIBLINGS)
    assert set(documents.DOCUMENT_KINDS) <= set(schema_contract.JSON_SPECIES)
    for key, sibling in documents.VERSION_SIBLINGS.items():
        table_name, _, column = key.partition(".")
        table = Base.metadata.tables[table_name]
        assert column in table.columns, f"versioned document {key} is missing"
        assert sibling in table.columns, f"{key} has no {sibling} sibling"
        column_type = table.columns[sibling].type
        assert isinstance(column_type, Integer), f"{key}.{sibling} is not an integer"
        assert table.columns[sibling].nullable is False, f"{key}.{sibling} is nullable"


def test_every_json_column_has_a_named_payload_type() -> None:
    names = payloads.PAYLOAD_TYPE_NAMES
    assert set(names) == set(schema_contract.JSON_SPECIES), (
        "PAYLOAD_TYPE_NAMES must cover exactly the JSON columns — missing: "
        f"{sorted(set(schema_contract.JSON_SPECIES) - set(names))}, stale: "
        f"{sorted(set(names) - set(schema_contract.JSON_SPECIES))}"
    )
    classes = {mapper.class_.__tablename__: mapper.class_ for mapper in Base.registry.mappers}
    for key, name in names.items():
        assert hasattr(payloads, name), f"{key} names a missing payload type {name}"
        registered = getattr(payloads, name)
        table_name, _, column = key.partition(".")
        model_class = classes[table_name]
        annotation = get_type_hints(model_class).get(column)
        assert annotation is not None, f"{key} has no model annotation"
        inner = get_args(annotation)[0]
        candidates = [inner]
        if isinstance(inner, types.UnionType):
            candidates = list(get_args(inner))
        assert any(candidate == registered for candidate in candidates), (
            f"{key} must be annotated with {name}, got {annotation}"
        )


def test_closed_sets_name_real_columns() -> None:
    for key in schema_contract.CLOSED_SETS:
        table_name, _, column_name = key.partition(".")
        table = Base.metadata.tables.get(table_name)
        assert table is not None, f"CLOSED_SETS names missing table {table_name}"
        assert column_name in table.columns, f"CLOSED_SETS names missing column {key}"
        assert table.columns[column_name].type.python_type is str, f"{key} is not a string column"


def _check_for(table_name: str, column: str) -> object:
    table = Base.metadata.tables[table_name]
    for constraint in table.constraints:
        if isinstance(constraint, CheckConstraint) and constraint.name == (
            f"ck_{table_name}_{column}_allowed"
        ):
            return constraint
    raise AssertionError(f"{table_name}.{column} has no ck_{table_name}_{column}_allowed CHECK")


def test_every_closed_set_has_its_check_twin() -> None:
    for key, enum in schema_contract.CLOSED_SETS.items():
        table_name, _, column = key.partition(".")
        constraint = _check_for(table_name, column)
        body = str(constraint.sqltext)  # type: ignore[attr-defined]
        for member in enum:
            assert f"'{member.value}'" in body, f"{key} CHECK is missing '{member.value}'"
        nullable = Base.metadata.tables[table_name].columns[column].nullable
        assert ("IS NULL" in body) is nullable, f"{key} CHECK nullability drifted"


def test_every_constraint_is_named() -> None:
    unnamed = [
        f"{table.name}.{constraint.__class__.__name__}"
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if constraint.__class__.__name__ != "PrimaryKeyConstraint" and constraint.name is None
    ]
    assert not unnamed, f"unnamed constraints: {sorted(unnamed)}"


def test_every_foreign_key_declares_its_delete_behaviour() -> None:
    missing = [
        f"{table.name}.{element.parent.name}"
        for table in Base.metadata.tables.values()
        for constraint in table.foreign_key_constraints
        for element in constraint.elements
        if constraint.ondelete is None
    ]
    assert not missing, f"foreign keys without explicit ON DELETE: {sorted(missing)}"
