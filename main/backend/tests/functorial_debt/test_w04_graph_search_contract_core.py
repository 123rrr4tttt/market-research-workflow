"""W04 typed failure and effect-boundary witnesses."""

from __future__ import annotations

import ast
import inspect
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from functorial_kit import Failure

from app.services.graph.backfill_graph_nodes import (
    _raise_transaction_failure,
    run_graph_node_backfill,
    run_graph_node_backfill_or_raise,
    try_run_graph_node_backfill,
)
from app.services.graph.models import Graph
from app.services.search.vector_contracts import (
    build_search_evidence_hits,
    serialize_retrieval_run_record,
    try_validate_global_vector_object,
    try_validate_retrieval_run_record,
    try_validate_search_evidence_hit,
)


class _Result:
    def __init__(self, docs: list[object]) -> None:
        self.docs = docs

    def scalars(self) -> "_Result":
        return self

    def all(self) -> list[object]:
        return self.docs


class _Session:
    def __init__(self, docs: list[object]) -> None:
        self.docs = docs
        self.events: list[str] = []

    def execute(self, _query: object) -> _Result:
        self.events.append("execute")
        return _Result(self.docs)

    def rollback(self) -> None:
        self.events.append("rollback")

    def commit(self) -> None:
        self.events.append("commit")


class _FailingPort:
    def __init__(self, session: _Session, cause: RuntimeError) -> None:
        self.session = session
        self.cause = cause

    def persist_graph_nodes(self, _graph: Graph) -> object:
        self.session.events.append("persist")
        raise self.cause


def _doc(doc_id: int) -> SimpleNamespace:
    return SimpleNamespace(id=doc_id, extracted_data={"entities": []})


def test_w04_graph_backfill_failure_rolls_back_and_keeps_cause() -> None:
    invalid = Failure(family="other.failure", code="bad", message="bad", context={})
    with pytest.raises(TypeError, match="failure context"):
        _raise_transaction_failure(invalid)

    session = _Session([_doc(1)])
    cause = RuntimeError("write failed")
    port = _FailingPort(session, cause)

    with patch(
        "app.services.graph.backfill_graph_nodes.build_graph",
        return_value=Graph(nodes={}, edges=[], schema_version="v1"),
    ):
        result = try_run_graph_node_backfill(
            session,
            normalizer=lambda document: SimpleNamespace(doc_id=document.id),
            dry_run=False,
            persistence_port=port,
        )

    assert isinstance(result, Failure)
    assert result.family == "graph.backfill.failure"
    assert result.code == "transaction_failed"
    assert result.context is not None
    assert result.context["cause"] is cause
    assert session.events == ["execute", "persist", "rollback"]

    shell_session = _Session([_doc(1)])
    with patch(
        "app.services.graph.backfill_graph_nodes.build_graph",
        return_value=Graph(nodes={}, edges=[], schema_version="v1"),
    ), pytest.raises(RuntimeError, match="^write failed$") as raised:
        run_graph_node_backfill_or_raise(
            shell_session,
            normalizer=lambda document: SimpleNamespace(doc_id=document.id),
            dry_run=False,
            persistence_port=_FailingPort(shell_session, cause),
        )
    assert raised.value.__cause__ is cause


def test_w04_search_validators_are_total_typed_failures() -> None:
    global_failure = try_validate_global_vector_object({})
    assert isinstance(global_failure, Failure)
    assert global_failure.code == "global_vector_object_invalid"
    assert global_failure.context is not None
    assert global_failure.context["operation"] == "validate_global_vector_object"

    _, hits = build_search_evidence_hits(
        [{"document_id": "doc-1", "score": 0.5, "mode": "vector", "backend": "qdrant"}],
        query="market",
    )
    broken_hit = dict(hits[0])
    broken_hit["global_vector_object"] = dict(broken_hit["global_vector_object"])
    del broken_hit["global_vector_object"]["chunk_id"]
    hit_failure = try_validate_search_evidence_hit(broken_hit)
    assert isinstance(hit_failure, Failure)
    assert hit_failure.code == "evidence_hit_invalid"

    record = {
        "contract_version": "search_retrieval_run.v1",
        "run_id": "run",
        "query_group_id": "group",
        "retrieval_family": "main_search",
        "query": "market",
        "project_key": None,
        "rank_mode": "hybrid",
        "branch_records": "invalid",
    }
    run_failure = try_validate_retrieval_run_record(record)
    assert isinstance(run_failure, Failure)
    assert run_failure.code == "retrieval_run_invalid"


def test_w04_search_abi_lift_preserves_legacy_value_error_message() -> None:
    _, hits = build_search_evidence_hits(
        [{"document_id": "doc-1", "score": 0.5, "mode": "vector", "backend": "qdrant"}],
        query="market",
    )
    broken = dict(hits[0])
    del broken["backend"]
    record = {
        "contract_version": "search_retrieval_run.v1",
        "run_id": "run",
        "query_group_id": "group",
        "retrieval_family": "main_search",
        "query": "market",
        "project_key": None,
        "rank_mode": "hybrid",
        "branch_records": [],
        "retrieval_branches": [],
        "retrieval_hits": [],
        "evidence_hits": [broken],
    }
    with pytest.raises(ValueError, match="^search_retrieval_run branch_records do not match evidence hit branches$"):
        serialize_retrieval_run_record(record)


def test_w04_no_throw_variants_have_no_domain_raise() -> None:
    from app.services.graph import backfill_graph_nodes
    from app.services.search import vector_contracts

    for function in (
        backfill_graph_nodes.try_run_graph_node_backfill,
        vector_contracts.try_validate_global_vector_object,
        vector_contracts.try_validate_search_evidence_hit,
        vector_contracts.try_validate_retrieval_run_record,
    ):
        assert not any(isinstance(node, ast.Raise) for node in ast.walk(ast.parse(inspect.getsource(function))))
