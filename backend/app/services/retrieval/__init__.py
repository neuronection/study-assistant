"""Retrieval-operations services (plan 51 Q3a)."""

from .legacy import LEGACY_KIND, LEGACY_SPACE_ID, load_store
from .telemetry import (
    QueryRollupRecorder,
    aggregate_rows,
    configure_recorder,
    record_query,
)

__all__ = [
    "LEGACY_KIND",
    "LEGACY_SPACE_ID",
    "QueryRollupRecorder",
    "aggregate_rows",
    "configure_recorder",
    "load_store",
    "record_query",
]
