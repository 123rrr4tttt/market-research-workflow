from __future__ import annotations

import ast
from pathlib import Path

import pytest
from functorial_kit import Failure
from mrw_functorial_kit.core.service_failure_semantics import clue_chain_failures, material_query_failures

from app.services.clue_chains.source_library_expansion import (
    expand_source_library_hop,
    raise_clue_chain_legacy as raise_source_clue_chain_legacy,
    try_expand_source_library_hop,
)
from app.services.document_queries.contracts import (
    build_material_query,
    material_query_failure,
    raise_material_query_legacy,
    try_build_material_query,
    try_validate_material_query_result_envelope,
    validate_material_query_result_envelope,
)
from app.services.document_queries.statement_builder import build_material_query_statement, try_build_material_query_statement


REPO_ROOT = Path(__file__).resolve().parents[4]
OWNED = (
    REPO_ROOT / "main/backend/app/services/clue_chains/service.py",
    REPO_ROOT / "main/backend/app/services/clue_chains/source_library_expansion.py",
    REPO_ROOT / "main/backend/app/services/document_queries/contracts.py",
    REPO_ROOT / "main/backend/app/services/document_queries/statement_builder.py",
    REPO_ROOT / "main/backend/app/services/document_queries/writing_documents.py",
)


def test_clue_source_validation_is_typed_and_closed() -> None:
    source = try_expand_source_library_hop(chain_id="c", project_key="p")
    assert isinstance(source, Failure)
    assert source.code == "input_invalid"
    assert source.context["public_message"] == "frontier_query or frontier.query is required"

    with pytest.raises(ValueError, match="frontier_query or frontier.query is required"):
        expand_source_library_hop(chain_id="c", project_key="p")


def test_material_query_typed_validation_and_legacy_abi() -> None:
    result = try_build_material_query("", filters=({"field": "state", "op": "wat"},))
    assert isinstance(result, Failure)
    assert material_query_failures.matches(result)
    assert result.code == "filter_invalid"
    assert result.context["public_exception"] == "ValueError"
    with pytest.raises(ValueError, match="unsupported material query filter operator: wat"):
        build_material_query("", filters=({"field": "state", "op": "wat"},))

    envelope = try_validate_material_query_result_envelope({"status": "bad"})
    assert isinstance(envelope, Failure)
    assert envelope.code == "result_envelope_invalid"
    with pytest.raises(ValueError, match="material query result envelope status must be ok"):
        validate_material_query_result_envelope({"status": "bad"})

    invalid_field_query = {
        "query": "",
        "filters": [{"field": "raw_sql", "op": "eq"}],
        "limit": 20,
        "offset": 0,
    }
    statement = try_build_material_query_statement(invalid_field_query)
    assert isinstance(statement, Failure)
    assert statement.code == "statement_invalid"
    with pytest.raises(ValueError, match="unsupported material query field"):
        build_material_query_statement(invalid_field_query)


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


def test_material_query_failure_lift_covers_programmer_defect_and_cause() -> None:
    invalid = Failure(family="other.failure", code="bad", message="bad", context={})
    with pytest.raises(TypeError, match="failure lift context"):
        raise_material_query_legacy(invalid)

    failure = material_query_failure("filter_invalid", "material failure", owner="test")
    with pytest.raises(ValueError, match="^material failure$"):
        raise_material_query_legacy(failure)
    cause = RuntimeError("material cause")
    with pytest.raises(ValueError, match="^material failure$") as raised:
        raise_material_query_legacy(failure, cause=cause)
    assert raised.value.__cause__ is cause


def test_owned_core_raise_sites_are_only_lifts() -> None:
    for path in OWNED:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise):
                continue
            line = source.splitlines()[node.lineno - 2] if node.lineno > 1 else ""
            assert "kit:boundary" in line, f"unmarked raise at {path}:{node.lineno}"
