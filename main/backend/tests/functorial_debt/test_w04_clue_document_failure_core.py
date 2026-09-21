from __future__ import annotations

import ast
from pathlib import Path

import pytest
from functorial_kit import Failure
from mrw_functorial_kit.core.w04_service_semantics import clue_chain_failures, document_query_failures

from app.services.clue_chains.graph_integration import (
    ClueChainGraphIntegrationError,
    build_graph_mutation_payload,
    clue_chain_failure as graph_clue_chain_failure,
    raise_clue_chain_legacy as raise_graph_clue_chain_legacy,
    try_build_graph_mutation_payload,
)
from app.services.clue_chains.source_library_expansion import (
    expand_source_library_hop,
    raise_clue_chain_legacy as raise_source_clue_chain_legacy,
    try_expand_source_library_hop,
)
from app.services.document_queries.contracts import (
    build_document_query,
    document_query_failure,
    raise_document_query_legacy,
    try_build_document_query,
    try_validate_document_query_result_envelope,
    validate_document_query_result_envelope,
)
from app.services.document_queries.statement_builder import build_document_query_statement, try_build_document_query_statement


REPO_ROOT = Path(__file__).resolve().parents[4]
OWNED = (
    REPO_ROOT / "main/backend/app/services/clue_chains/graph_integration.py",
    REPO_ROOT / "main/backend/app/services/clue_chains/service.py",
    REPO_ROOT / "main/backend/app/services/clue_chains/source_library_expansion.py",
    REPO_ROOT / "main/backend/app/services/document_queries/contracts.py",
    REPO_ROOT / "main/backend/app/services/document_queries/statement_builder.py",
    REPO_ROOT / "main/backend/app/services/document_queries/writing_documents.py",
)


def test_clue_graph_and_source_validation_are_typed_and_closed() -> None:
    graph = try_build_graph_mutation_payload(
        candidates=[{"candidate_id": "c1"}],
        decisions=[{"candidate_id": "c1", "decision_id": "d1", "decision": "approve"}],
        evidence_items=[],
    )
    assert isinstance(graph, Failure)
    assert clue_chain_failures.matches(graph)
    assert graph.code == "graph_projection_invalid"
    assert graph.context["public_exception"] == "ClueChainGraphIntegrationError"

    source = try_expand_source_library_hop(chain_id="c", project_key="p")
    assert isinstance(source, Failure)
    assert source.code == "input_invalid"
    assert source.context["public_message"] == "frontier_query or frontier.query is required"

    with pytest.raises(ClueChainGraphIntegrationError, match="candidate c1 missing evidence_id"):
        build_graph_mutation_payload(
            candidates=[{"candidate_id": "c1"}],
            decisions=[{"candidate_id": "c1", "decision_id": "d1", "decision": "approve"}],
            evidence_items=[],
        )
    with pytest.raises(ValueError, match="frontier_query or frontier.query is required"):
        expand_source_library_hop(chain_id="c", project_key="p")


def test_document_query_typed_validation_and_legacy_abi() -> None:
    result = try_build_document_query("", filters=({"field": "state", "op": "wat"},))
    assert isinstance(result, Failure)
    assert document_query_failures.matches(result)
    assert result.code == "filter_invalid"
    assert result.context["public_exception"] == "ValueError"
    with pytest.raises(ValueError, match="unsupported document query filter operator: wat"):
        build_document_query("", filters=({"field": "state", "op": "wat"},))

    envelope = try_validate_document_query_result_envelope({"status": "bad"})
    assert isinstance(envelope, Failure)
    assert envelope.code == "result_envelope_invalid"
    with pytest.raises(ValueError, match="document query result envelope status must be ok"):
        validate_document_query_result_envelope({"status": "bad"})

    statement = try_build_document_query_statement({"query": "", "filters": [{"field": "raw_sql", "op": "eq"}]})
    assert isinstance(statement, Failure)
    assert statement.code == "statement_invalid"
    with pytest.raises(ValueError, match="unsupported document query field"):
        build_document_query_statement({"query": "", "filters": [{"field": "raw_sql", "op": "eq"}]})


def test_graph_failure_lift_covers_programmer_defect_and_cause() -> None:
    invalid = Failure(family="other.failure", code="bad", message="bad", context={})
    with pytest.raises(TypeError, match="failure lift context"):
        raise_graph_clue_chain_legacy(invalid)

    failure = graph_clue_chain_failure("input_invalid", "graph failure", owner="test")
    with pytest.raises(ClueChainGraphIntegrationError, match="^graph failure$"):
        raise_graph_clue_chain_legacy(failure)
    cause = RuntimeError("graph cause")
    with pytest.raises(ClueChainGraphIntegrationError, match="^graph failure$") as raised:
        raise_graph_clue_chain_legacy(failure, cause=cause)
    assert raised.value.__cause__ is cause


def test_source_library_failure_lift_covers_programmer_defect_and_cause() -> None:
    invalid = Failure(family="other.failure", code="bad", message="bad", context={})
    with pytest.raises(TypeError, match="failure lift context"):
        raise_source_clue_chain_legacy(invalid)

    failure = clue_chain_failures.fail("input_invalid", "source failure", {"owner": "test", "public_exception": "ValueError", "public_message": "source failure"})
    with pytest.raises(ValueError, match="^source failure$"):
        raise_source_clue_chain_legacy(failure)
    cause = RuntimeError("source cause")
    with pytest.raises(ValueError, match="^source failure$") as raised:
        raise_source_clue_chain_legacy(failure, cause=cause)
    assert raised.value.__cause__ is cause


def test_document_query_failure_lift_covers_programmer_defect_and_cause() -> None:
    invalid = Failure(family="other.failure", code="bad", message="bad", context={})
    with pytest.raises(TypeError, match="failure lift context"):
        raise_document_query_legacy(invalid)

    failure = document_query_failure("filter_invalid", "document failure", owner="test")
    with pytest.raises(ValueError, match="^document failure$"):
        raise_document_query_legacy(failure)
    cause = RuntimeError("document cause")
    with pytest.raises(ValueError, match="^document failure$") as raised:
        raise_document_query_legacy(failure, cause=cause)
    assert raised.value.__cause__ is cause


def test_w04_owned_core_raise_sites_are_only_lifts() -> None:
    for path in OWNED:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise):
                continue
            line = source.splitlines()[node.lineno - 2] if node.lineno > 1 else ""
            assert "kit:boundary" in line, f"unmarked raise at {path}:{node.lineno}"
