from __future__ import annotations

from pathlib import Path
from typing import Any
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.unit

from app.services.projects import global_stats  # noqa: E402


class _FakeExecution:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeScalarExecution:
    def __init__(self, rows: list[tuple[Any, ...]]):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeConnection:
    def __init__(self, project_rows: list[tuple[str, str]], count_rows: list[dict[str, Any]] | RuntimeError):
        self.project_rows = project_rows
        self.count_rows = count_rows
        self.statements: list[str] = []
        self.opened = 0

    def execute(self, statement: Any, params: dict[str, Any] | None = None):
        sql = str(statement)
        self.statements.append(sql)
        if "FROM public.projects" in sql:
            return _FakeScalarExecution(self.project_rows)
        if isinstance(self.count_rows, RuntimeError):
            raise self.count_rows
        return _FakeExecution(self.count_rows)

    def begin(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return False


class _FakeEngine:
    def __init__(self, connection: _FakeConnection):
        self._connection = connection
        self.opened = 0

    def connect(self):
        self.opened += 1
        self._connection.opened += 1
        return self._connection


def _run(project_rows: list[tuple[str, str]], count_rows: list[dict[str, Any]] | RuntimeError):
    connection = _FakeConnection(project_rows, count_rows)
    engine = _FakeEngine(connection)
    with patch_object(engine):
        return query_global_canonical_stats(), connection


def patch_object(engine: _FakeEngine):
    from unittest.mock import patch

    return patch.object(global_stats, "engine", engine)


def query_global_canonical_stats():
    return global_stats.query_global_canonical_stats()


def test_no_enabled_projects_returns_three_zero_counts_without_tenant_query() -> None:
    result, connection = _run([], [])

    assert result == {"documents_total": 0, "metrics_total": 0, "prices_total": 0}
    assert len(connection.statements) == 2
    assert "REPEATABLE READ READ ONLY" in connection.statements[0]
    assert "WHERE enabled = true" in connection.statements[1]
    assert all("UNION ALL" not in statement for statement in connection.statements)


def test_enabled_projects_aggregate_canonical_counts_across_one_snapshot() -> None:
    count_rows = [
        {"object_name": "documents", "total": 3},
        {"object_name": "documents", "total": 4},
        {"object_name": "market_metric_points", "total": 5},
        {"object_name": "price_observations", "total": 2},
    ]
    result, connection = _run(
        [("alpha", "project_alpha"), ("beta", "project_beta")],
        count_rows,
    )

    assert result == {"documents_total": 7, "metrics_total": 5, "prices_total": 2}
    assert connection.opened == 1
    assert "REPEATABLE READ READ ONLY" in connection.statements[0]
    assert "WHERE enabled = true" in connection.statements[1]
    assert "UNION ALL" in connection.statements[2]


@pytest.mark.parametrize("stored_schema", ["public", "aggregator", "unexpected_schema", "bad-schema"])
def test_invalid_stored_schema_fails_closed(stored_schema: str) -> None:
    with pytest.raises(ValueError, match="invalid stored schema"):
        _run([("alpha", stored_schema)], [])


def test_missing_tenant_table_fails_closed_instead_of_reporting_zero() -> None:
    with pytest.raises(RuntimeError, match="relation does not exist"):
        _run([("alpha", "project_alpha")], RuntimeError("relation does not exist"))
