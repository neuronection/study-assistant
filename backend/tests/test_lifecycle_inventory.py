"""Lifecycle inventory wall (plan 81 E, ADR-201; constitution §7).

`contracts/data-model.lifecycle.txt` is the policy: one class per mapped
table (`record | operational | transient`). This wall proves the file covers
exactly the model tables, that `deleted_items` is the single tombstone
surface, and that no other table smuggled in soft-delete semantics.
"""

from pathlib import Path

from app.domain import models  # noqa: F401
from app.storage.db import Base

INVENTORY = Path(__file__).resolve().parents[2] / "contracts" / "data-model.lifecycle.txt"
CLASSES = {"record", "operational", "transient"}


def _rows() -> dict[str, str]:
    rows: dict[str, str] = {}
    for raw in INVENTORY.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        table, separator, rest = line.partition("::")
        assert separator, f"malformed lifecycle row: {line}"
        rows[table.strip()] = rest.strip().split()[0] if rest.strip() else ""
    return rows


def test_every_mapped_table_is_classified() -> None:
    rows = _rows()
    missing = sorted(set(Base.metadata.tables) - set(rows))
    assert not missing, f"tables without a lifecycle class: {missing}"
    stale = sorted(set(rows) - set(Base.metadata.tables))
    assert not stale, f"lifecycle inventory names missing tables: {stale}"
    assert set(rows.values()) <= CLASSES, f"unknown lifecycle class: {set(rows.values()) - CLASSES}"


def test_deleted_items_is_the_single_tombstone_surface() -> None:
    rows = _rows()
    assert rows.get("deleted_items") == "operational"

    soft_delete = sorted(
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if column.name == "is_deleted" or column.name == "deleted_at"
    )
    assert soft_delete == ["deleted_items.deleted_at"], (
        "deleted_items is the only tombstone; soft-delete columns found: "
        f"{[item for item in soft_delete if item != 'deleted_items.deleted_at']}"
    )


def test_lifecycle_classes_have_expected_anchors() -> None:
    rows = _rows()
    assert rows["jobs"] == "transient"
    assert rows["auth_sessions"] == "transient"
    assert rows["chat_quiz_pendings"] == "transient"
    assert rows["audit_events"] == "operational"
    assert rows["ai_interactions"] == "operational"
    assert rows["courses"] == "record"
    assert rows["materials"] == "record"


def test_no_orphan_tables_in_the_inventory() -> None:
    rows = _rows()
    assert len(rows) == len(set(rows)) == len(Base.metadata.tables)
