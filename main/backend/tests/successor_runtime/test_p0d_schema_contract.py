from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES

REVISION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "versions"
    / "20260831_000002_add_successor_p0d_projections.py"
)


class _OperationRecorder:
    def __init__(self) -> None:
        self.operations: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.operations.append((name, args, kwargs))

    def add_column(self, *args: Any, **kwargs: Any) -> None:
        self._record("add_column", *args, **kwargs)

    def alter_column(self, *args: Any, **kwargs: Any) -> None:
        self._record("alter_column", *args, **kwargs)

    def create_check_constraint(self, *args: Any, **kwargs: Any) -> None:
        self._record("create_check_constraint", *args, **kwargs)

    def create_index(self, *args: Any, **kwargs: Any) -> None:
        self._record("create_index", *args, **kwargs)

    def create_table(self, *args: Any, **kwargs: Any) -> None:
        self._record("create_table", *args, **kwargs)

    def create_unique_constraint(self, *args: Any, **kwargs: Any) -> None:
        self._record("create_unique_constraint", *args, **kwargs)

    def drop_column(self, *args: Any, **kwargs: Any) -> None:
        self._record("drop_column", *args, **kwargs)

    def drop_constraint(self, *args: Any, **kwargs: Any) -> None:
        self._record("drop_constraint", *args, **kwargs)

    def drop_index(self, *args: Any, **kwargs: Any) -> None:
        self._record("drop_index", *args, **kwargs)

    def drop_table(self, *args: Any, **kwargs: Any) -> None:
        self._record("drop_table", *args, **kwargs)

    def execute(self, *args: Any, **kwargs: Any) -> None:
        self._record("execute", *args, **kwargs)

    def calls(self, name: str) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
        return [
            (args, kwargs)
            for operation, args, kwargs in self.operations
            if operation == name
        ]


def _load_revision() -> ModuleType:
    spec = importlib.util.spec_from_file_location("p0d_schema_revision", REVISION_PATH)
    assert spec and spec.loader
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    return revision


def _record(direction: str) -> _OperationRecorder:
    revision = _load_revision()
    recorder = _OperationRecorder()
    revision.op = recorder
    getattr(revision, direction)()
    return recorder


def _default_signature(column: sa.Column[Any]) -> str | None:
    if column.server_default is None:
        return None
    argument = column.server_default.arg
    if isinstance(argument, sa.sql.ClauseElement):
        return str(argument.compile(dialect=postgresql.dialect()))
    return str(argument)


def _column_signature(
    column: sa.Column[Any], *, nullable: bool | None = None
) -> tuple[str, bool, bool, str | None]:
    return (
        str(column.type.compile(dialect=postgresql.dialect())),
        column.nullable if nullable is None else nullable,
        column.primary_key,
        _default_signature(column),
    )


def _table_signature(table: sa.Table) -> tuple[str, tuple[str, ...]]:
    return (
        str(CreateTable(table).compile(dialect=postgresql.dialect())),
        tuple(
            sorted(
                str(CreateIndex(index).compile(dialect=postgresql.dialect()))
                for index in table.indexes
            )
        ),
    )


def _captured_run_projection_table(recorder: _OperationRecorder) -> sa.Table:
    calls = recorder.calls("create_table")
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == "runtime_run_projections"
    assert kwargs == {"schema": "public"}

    metadata = sa.MetaData()
    table = sa.Table(args[0], metadata, *args[1:], schema=kwargs["schema"])
    index_calls = recorder.calls("create_index")
    run_indexes = [
        (index_args, index_kwargs)
        for index_args, index_kwargs in index_calls
        if index_args[1] == "runtime_run_projections"
    ]
    assert len(run_indexes) == 1
    index_args, index_kwargs = run_indexes[0]
    assert index_kwargs == {"schema": "public"}
    sa.Index(index_args[0], *(table.c[name] for name in index_args[2]))
    return table


def test_revision_is_additive_self_contained_and_explicitly_reversible() -> None:
    tree = ast.parse(REVISION_PATH.read_text(encoding="utf-8"), str(REVISION_PATH))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_modules.update(
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    )
    assert not any(
        module == "app" or module.startswith("app.") for module in imported_modules
    )

    revision = _load_revision()
    assert revision.revision == "20260831_000002"
    assert revision.down_revision == "20260830_000001"
    assert callable(revision.upgrade)
    assert callable(revision.downgrade)


def test_upgrade_offset_columns_constraints_and_index_match_current_models() -> None:
    recorder = _record("upgrade")
    expected = PUBLIC_TABLES["runtime_projection_offsets"]

    additions = {
        args[1].name: (args[1], kwargs) for args, kwargs in recorder.calls("add_column")
    }
    expected_names = {
        "source_kind",
        "source_ref",
        "source_incarnation",
        "projection_generation",
    }
    assert set(additions) == expected_names
    for name in expected_names:
        column, kwargs = additions[name]
        assert kwargs == {"schema": "public"}
        if name == "projection_generation":
            assert column.nullable is False
            assert _column_signature(column) == _column_signature(expected.c[name])
        else:
            assert column.nullable is True
            assert _column_signature(column, nullable=False) == _column_signature(
                expected.c[name]
            )

    altered = {args[1]: kwargs for args, kwargs in recorder.calls("alter_column")}
    assert altered == {
        "source_kind": {"nullable": False, "schema": "public"},
        "source_ref": {"nullable": False, "schema": "public"},
        "source_incarnation": {"nullable": False, "schema": "public"},
    }

    unique = next(
        constraint
        for constraint in expected.constraints
        if isinstance(constraint, sa.UniqueConstraint)
        and constraint.name == "uq_projection_owner_source"
    )
    unique_calls = recorder.calls("create_unique_constraint")
    assert unique_calls == [
        (
            (
                unique.name,
                expected.name,
                [column.name for column in unique.columns],
            ),
            {"schema": "public"},
        )
    ]

    check = next(
        constraint
        for constraint in expected.constraints
        if isinstance(constraint, sa.CheckConstraint)
        and constraint.name == "ck_projection_revisions"
    )
    check_calls = recorder.calls("create_check_constraint")
    offset_checks = [call for call in check_calls if call[0][1] == expected.name]
    assert offset_checks == [
        (
            (check.name, expected.name, str(check.sqltext)),
            {"schema": "public"},
        )
    ]

    index = next(iter(expected.indexes))
    offset_indexes = [
        call for call in recorder.calls("create_index") if call[0][1] == expected.name
    ]
    assert offset_indexes == [
        (
            (index.name, expected.name, [column.name for column in index.columns]),
            {"schema": "public"},
        )
    ]

    execute_calls = recorder.calls("execute")
    assert len(execute_calls) == 1
    normalized_backfill = " ".join(str(execute_calls[0][0][0]).split())
    assert normalized_backfill == (
        "UPDATE public.runtime_projection_offsets "
        "SET source_kind = 'LEGACY_OFFSET', "
        "source_ref = 'projection-offset:' || projection_offset_id, "
        "source_incarnation = 'legacy:' || source_digest "
        "WHERE source_kind IS NULL OR source_ref IS NULL "
        "OR source_incarnation IS NULL"
    )


def test_upgrade_run_projection_table_is_schema_equivalent_to_current_models() -> None:
    recorder = _record("upgrade")
    captured = _captured_run_projection_table(recorder)
    expected = PUBLIC_TABLES["runtime_run_projections"]
    assert _table_signature(captured) == _table_signature(expected)


def test_downgrade_restores_exact_p0b_offset_contract() -> None:
    recorder = _record("downgrade")
    operation_names = [name for name, _, _ in recorder.operations]
    assert operation_names == [
        "drop_index",
        "drop_table",
        "drop_index",
        "drop_constraint",
        "create_unique_constraint",
        "create_index",
        "drop_constraint",
        "create_check_constraint",
        "drop_column",
        "drop_column",
        "drop_column",
        "drop_column",
    ]
    assert all(kwargs.get("schema") == "public" for _, _, kwargs in recorder.operations)
    assert recorder.calls("create_unique_constraint") == [
        (
            (
                "uq_projection_owner_version",
                "runtime_projection_offsets",
                ["project_key", "projector_id", "projector_version"],
            ),
            {"schema": "public"},
        )
    ]
    assert recorder.calls("create_index") == [
        (
            (
                "ix_projection_projector",
                "runtime_projection_offsets",
                ["project_key", "projector_id"],
            ),
            {"schema": "public"},
        )
    ]
    assert recorder.calls("create_check_constraint") == [
        (
            (
                "ck_projection_revisions",
                "runtime_projection_offsets",
                "source_revision >= 0 AND revision >= 0",
            ),
            {"schema": "public"},
        )
    ]
    assert [args[1] for args, _ in recorder.calls("drop_column")] == [
        "projection_generation",
        "source_incarnation",
        "source_ref",
        "source_kind",
    ]
