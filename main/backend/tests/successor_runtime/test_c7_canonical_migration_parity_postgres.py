"""Schema parity guard between migration and the inline C7 canonical table.

The runtime table definition in ``ingest_c7_movement_admission`` and the
production Alembic revision ``20260903_000003`` must never drift.  This guard
compares name, SQL type, nullability and primary-key role column by column.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from app.successor_runtime.substrate.postgres.ingest_c7_movement_admission import (
    C7_MOVEMENT_CANONICAL_DOCUMENTS,
)

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "20260903_000003_add_c7_canonical_documents.py"
)


def _load_migration() -> Any:
    spec = importlib.util.spec_from_file_location(
        "_20260903_000003_c7_canonical_migration", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _column_identity(column: Any) -> tuple[str, str, bool, bool]:
    return (
        str(column.name),
        str(column.type),
        bool(column.nullable),
        bool(column.primary_key),
    )


def test_migration_column_parity_with_runtime_table() -> None:
    migration = _load_migration()
    migration_columns = [_column_identity(c) for c in migration._column_spec()]
    runtime_columns = [_column_identity(c) for c in C7_MOVEMENT_CANONICAL_DOCUMENTS.columns]
    assert migration_columns == runtime_columns
