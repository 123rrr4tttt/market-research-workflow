from __future__ import annotations

import pytest
from functorial_kit import Failure, FailureFamily

from mrw_functorial_kit.core.w04_service_semantics import (
    clue_chain_failures,
    document_query_failures,
    graph_backfill_failures,
    search_failures,
    typed_knowledge_contract_failures,
    workflow_graph_failures,
    writing_failures,
)


EXPECTED = (
    (
        clue_chain_failures,
        "clue_chain.failure",
        (
            "input_invalid",
            "provider_result_invalid",
            "chain_not_found",
            "object_not_found",
            "chain_closed",
            "graph_projection_invalid",
        ),
    ),
    (
        document_query_failures,
        "document_query.failure",
        (
            "filter_invalid",
            "sort_invalid",
            "statement_invalid",
            "result_envelope_invalid",
            "document_not_found",
        ),
    ),
    (graph_backfill_failures, "graph.backfill.failure", ("transaction_failed",)),
    (
        search_failures,
        "search.failure",
        (
            "backend_unavailable",
            "embedding_failed",
            "vector_search_failed",
            "global_vector_object_invalid",
            "evidence_hit_invalid",
            "retrieval_run_invalid",
        ),
    ),
    (
        typed_knowledge_contract_failures,
        "typed_knowledge.contract_failure",
        (
            "object_contract_invalid",
            "relationship_contract_invalid",
            "downstream_contract_invalid",
            "writing_handoff_contract_invalid",
            "writing_context_contract_invalid",
            "governance_transition_invalid",
        ),
    ),
    (
        workflow_graph_failures,
        "workflow_graph.failure",
        (
            "contract_invalid",
            "integrity_invalid",
            "object_not_found",
            "revision_conflict",
            "executor_not_registered",
            "required_input_missing",
            "store_unavailable",
        ),
    ),
    (
        writing_failures,
        "writing.failure",
        (
            "document_not_found",
            "version_conflict",
            "card_not_found",
            "action_not_found",
            "action_execution_failed",
        ),
    ),
)


@pytest.mark.parametrize(("family", "name", "codes"), EXPECTED)
def test_INVARIANT__w04_failure_family_codes_are_exact(
    family: FailureFamily,
    name: str,
    codes: tuple[str, ...],
) -> None:
    assert family.name == name
    assert family.codes == codes


@pytest.mark.parametrize(("family", "_name", "_codes"), EXPECTED)
def test_INVARIANT__w04_failure_family_rejects_unknown_codes(
    family: FailureFamily,
    _name: str,
    _codes: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError, match="unknown code 'w04_not_registered'"):
        family.fail("w04_not_registered", "closed family rejection")


@pytest.mark.parametrize(("family", "_name", "_codes"), EXPECTED)
def test_FAILURE_PRESERVED__w04_fail_returns_kit_failure_structure(
    family: FailureFamily,
    _name: str,
    _codes: tuple[str, ...],
) -> None:
    code = family.codes[0]
    failure = family.fail(code, "specific diagnostic", {"source": "test"})

    assert type(failure) is Failure
    assert (failure.family, failure.code, failure.message) == (
        family.name,
        code,
        "specific diagnostic",
    )
    assert failure.context == {"source": "test"}
    assert family.matches(failure)
