"""Closed-set CHECK twins behave at the database boundary (plan 81 B).

Every StrEnum-backed column must reject a value the vocabulary forbids and
accept each real member on a raw SQL path (no ORM validation involved).
"""

from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Column, Engine, create_engine, event, insert
from sqlalchemy.exc import IntegrityError

from app.domain import (
    models,  # noqa: F401
    schema_contract,
)
from app.storage.db import Base


@pytest.fixture(scope="module")
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _disable_foreign_keys(dbapi_connection: Any, _record: object) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=OFF")

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def _placeholder(column: Column[Any]) -> Any:
    python_type = column.type.python_type
    if python_type is bool:
        return False
    if python_type is int:
        return 1
    if python_type is float:
        return 0.0
    if python_type is datetime:
        return datetime.now(UTC)
    if python_type is date:
        return date(2026, 1, 1)
    if python_type is str:
        return uuid4().hex if column.type.__class__.__name__ == "Uuid" else "probe"
    return []


def _row_values(table_name: str, column: str, value: str) -> dict[str, Any]:
    table = Base.metadata.tables[table_name]
    values: dict[str, Any] = {}
    for table_column in table.columns:
        if table_column.primary_key and table_column.autoincrement is True:
            continue
        if table_column.name == column:
            values[column] = value
            continue
        if not table_column.nullable and table_column.default is None:
            enum = schema_contract.CLOSED_SETS.get(f"{table_name}.{table_column.name}")
            if enum is not None:
                values[table_column.name] = next(iter(enum)).value
            else:
                values[table_column.name] = _placeholder(table_column)
    return values


CASES = [
    (key, member.value)
    for key, enum in sorted(schema_contract.CLOSED_SETS.items())
    for member in enum
]


@pytest.mark.parametrize(("key", "value"), CASES)
def test_check_accepts_every_vocabulary_member(engine: Engine, key: str, value: str) -> None:
    table_name, _, column = key.partition(".")
    with engine.connect() as connection:
        transaction = connection.begin()
        table = Base.metadata.tables[table_name]
        connection.execute(insert(table).values(**_row_values(table_name, column, value)))
        transaction.rollback()


@pytest.mark.parametrize("key", sorted(schema_contract.CLOSED_SETS))
def test_check_rejects_unknown_value(engine: Engine, key: str) -> None:
    table_name, _, column = key.partition(".")
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            insert(Base.metadata.tables[table_name]).values(
                **_row_values(table_name, column, "not-a-member")
            )
        )
