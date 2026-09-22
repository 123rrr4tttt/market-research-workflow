"""Focused tests for the local-Codex agent-core provider bridge and the
business-chain read-only snapshot injected into the model prompt."""

from __future__ import annotations

from typing import Any

from app.services.agent_core.business_chain_context import (
    build_business_chain_snapshot,
    business_chain_snapshot_json,
)


class _FakeSession:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def connection(self) -> Any:
        return self._connection

    def close(self) -> None:
        pass


class _FakeConnection:
    def __init__(self, counts: dict[str, int | None]) -> None:
        self._counts = counts

    def execute(self, statement: Any, params: Any | None = None) -> Any:
        sql = str(statement)
        if "to_regclass" in sql:
            table = str((params or {}).get("qualified") or "").split(".")[-1]
            return _ScalarResult(table in self._counts)
        if "WHERE state = 'ACTIVE'" in sql:
            return _ScalarResult([])
        if '"public".' not in sql:
            return _ScalarResult(None)
        return _ScalarResult(self._counts.get(_table_from_count(sql), 0) or 0)


def _table_from_count(sql: str) -> str:
    # SELECT count(*) FROM "public"."<table>"
    marker = '"public"."'
    start = sql.index(marker) + len(marker)
    return sql[start : sql.index('"', start)]


class _ScalarResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar(self) -> Any:
        return self._value

    def mappings(self) -> Any:
        return self

    def all(self) -> list[Any]:
        return []


def test_business_chain_snapshot_fails_closed_without_db_tables() -> None:
    session = _FakeSession(_FakeConnection(counts={}))
    snapshot = build_business_chain_snapshot(session_factory=lambda: session)
    assert snapshot["database"]["available"] is True
    rows = {item["table"]: item for item in snapshot["database"]["table_counts"]}
    assert rows["projects"]["available"] is False
    assert rows["project_scope_registry"]["available"] is False


def test_business_chain_snapshot_counts_active_registry() -> None:
    session = _FakeSession(
        _FakeConnection(
            counts={
                "projects": 9,
                "agent_sessions": 2409,
                "project_scope_registry": 1,
                "c7_movement_canonical_documents": 1,
            }
        )
    )
    snapshot = build_business_chain_snapshot(session_factory=lambda: session)
    rows = {item["table"]: item for item in snapshot["database"]["table_counts"]}
    assert rows["projects"]["rows"] == 9
    assert rows["project_scope_registry"]["rows"] == 1
    assert snapshot["available"] is True


def test_business_chain_snapshot_json_is_bounded_text() -> None:
    session = _FakeSession(_FakeConnection(counts={"projects": 9}))
    text = business_chain_snapshot_json(
        session_factory=lambda: session,
        project_key="demo",
        max_chars=200,
    )
    assert text.startswith("Business-chain read-only snapshot")
    assert len(text) <= 220
