"""C1-M001/C1-M002 legacy DSL -> typed Program parity fixtures.

movement binding: C1-M001 | evidence ref: evidence:c1:m001:legacy-dsl-parity
movement binding: C1-M002 | evidence ref: evidence:c1:m002:digest-counterexamples

The suite binds the legacy graph DSL parse/validate/compile surface to the
successor Program/Plan digest surface and asserts typed counterexamples for
node-kind, node-config and ordered-composition changes.
"""

from __future__ import annotations

import inspect

import pytest

from app.successor_runtime.capabilities import workflow_legacy_dsl as workflow


def _node(
    node_id: str,
    node_type: str = "vector_search",
    config: dict | None = None,
) -> dict:
    return {
        "node_id": node_id,
        "node_type": node_type,
        "config": config if config is not None else {},
    }


def _payload(
    nodes: list,
    edges: list | None = None,
    *,
    version: str = "1.0",
    options: dict | None = None,
) -> dict:
    normalized_edges: list = []
    for edge in edges if edges is not None else []:
        if isinstance(edge, tuple) and len(edge) == 2:
            normalized_edges.append({"from": edge[0], "to": edge[1]})
        else:
            normalized_edges.append(edge)
    return {
        "version": version,
        "options": options if options is not None else {},
        "nodes": nodes,
        "edges": normalized_edges,
    }


def _plain(value):
    if (
        isinstance(value, tuple)
        and value
        and all(
            isinstance(item, tuple) and len(item) == 2 and isinstance(item[0], str)
            for item in value
        )
    ):
        return {item[0]: _plain(item[1]) for item in value}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


def test_valid_legacy_dsl_parse_and_compile_is_deterministic() -> None:
    """movement binding: C1-M001 | evidence ref: evidence:c1:m001:legacy-dsl-parity"""
    payload = _payload(
        nodes=[
            _node("retrieve", "vector_search", {"top_k": 5}),
            _node("draft", "llm_call", {"model": "mrw-local"}),
            _node("combine", "join", {"field": "values"}),
        ],
        edges=[("retrieve", "combine"), ("draft", "combine")],
    )
    first = workflow.parse_and_validate_workflow_dsl(payload)
    second = workflow.parse_and_validate_workflow_dsl(payload)

    assert first.ok and second.ok
    assert first.program_digest == second.program_digest
    assert first.plan_digest == second.plan_digest
    assert first.catalog_digest == second.catalog_digest
    assert first.program_digest == first.program.program_digest
    assert first.plan_digest == first.plan.plan_digest


def test_duplicate_node_id_is_rejected_with_typed_code() -> None:
    """movement binding: C1-M001 | evidence ref: evidence:c1:m001:legacy-dsl-parity"""
    receipt = workflow.parse_and_validate_workflow_dsl(
        _payload([_node("a"), _node("a", "llm_call")])
    )

    assert not receipt.ok
    assert receipt.failure is not None
    assert receipt.failure.code == workflow.WORKFLOW_DSL_DUPLICATE_NODE_ID


def test_unsupported_node_type_is_rejected_with_typed_code() -> None:
    """movement binding: C1-M001 | evidence ref: evidence:c1:m001:legacy-dsl-parity"""
    receipt = workflow.parse_and_validate_workflow_dsl(
        _payload([_node("a"), _node("b", "web_search")])
    )

    assert not receipt.ok
    assert receipt.failure is not None
    assert receipt.failure.code == workflow.WORKFLOW_DSL_UNSUPPORTED_NODE_TYPE


def test_edge_referencing_missing_node_is_rejected_with_typed_code() -> None:
    """movement binding: C1-M001 | evidence ref: evidence:c1:m001:legacy-dsl-parity"""
    receipt = workflow.parse_and_validate_workflow_dsl(
        _payload([_node("a")], edges=[("a", "missing")])
    )

    assert not receipt.ok
    assert receipt.failure is not None
    assert receipt.failure.code == workflow.WORKFLOW_DSL_MISSING_ENDPOINT


def test_cycle_is_rejected_with_typed_code() -> None:
    """movement binding: C1-M001 | evidence ref: evidence:c1:m001:legacy-dsl-parity"""
    receipt = workflow.parse_and_validate_workflow_dsl(
        _payload(
            [_node("a"), _node("b")],
            edges=[("a", "b"), ("b", "a")],
        )
    )

    assert not receipt.ok
    assert receipt.failure is not None
    assert receipt.failure.code == workflow.WORKFLOW_DSL_CYCLE


@pytest.mark.parametrize(
    "payload",
    (
        {
            "version": "1.0",
            "options": {},
            "nodes": {"a": {"node_type": "vector_search"}},
            "edges": [],
        },
        _payload(["not-a-node-mapping"]),
        _payload([_node("a")], version=""),
    ),
    ids=("nodes-not-list", "node-not-mapping", "empty-version"),
)
def test_malformed_payload_is_rejected_with_typed_code(payload: dict) -> None:
    """movement binding: C1-M001 | evidence ref: evidence:c1:m001:legacy-dsl-parity"""
    receipt = workflow.parse_and_validate_workflow_dsl(payload)

    assert not receipt.ok
    assert receipt.failure is not None
    assert receipt.failure.code == workflow.WORKFLOW_DSL_MALFORMED_PAYLOAD


def test_node_kind_change_alters_plan_digest() -> None:
    """movement binding: C1-M002 | evidence ref: evidence:c1:m002:digest-counterexamples"""
    base = workflow.parse_and_validate_workflow_dsl(
        _payload(
            [_node("a", "vector_search", {"top_k": 3}), _node("b", "llm_call")],
            edges=[("a", "b")],
        )
    )
    changed = workflow.parse_and_validate_workflow_dsl(
        _payload(
            [_node("a", "llm_call", {"top_k": 3}), _node("b", "llm_call")],
            edges=[("a", "b")],
        )
    )

    assert base.ok and changed.ok
    assert changed.program_digest != base.program_digest
    assert changed.plan_digest != base.plan_digest


def test_node_config_change_alters_program_and_plan_digests() -> None:
    """movement binding: C1-M002 | evidence ref: evidence:c1:m002:digest-counterexamples"""
    base = workflow.parse_and_validate_workflow_dsl(
        _payload([_node("a", "vector_search", {"top_k": 3})])
    )
    changed = workflow.parse_and_validate_workflow_dsl(
        _payload([_node("a", "vector_search", {"top_k": 9})])
    )

    assert base.ok and changed.ok
    assert base.program.metadata != changed.program.metadata
    assert _plain(base.program.metadata)["nodes"][0]["config"] == {"top_k": 3}
    assert _plain(changed.program.metadata)["nodes"][0]["config"] == {"top_k": 9}
    assert changed.program_digest != base.program_digest
    assert changed.plan_digest != base.plan_digest


def test_swapped_node_order_alters_plan_digest_ordered_not_commutative() -> None:
    """movement binding: C1-M002 | evidence ref: evidence:c1:m002:digest-counterexamples"""
    forward = workflow.parse_and_validate_workflow_dsl(
        _payload([_node("a", "vector_search"), _node("b", "llm_call")])
    )
    swapped = workflow.parse_and_validate_workflow_dsl(
        _payload([_node("b", "llm_call"), _node("a", "vector_search")])
    )

    assert forward.ok and swapped.ok
    assert forward.topo_order == ("a", "b")
    assert swapped.topo_order == ("b", "a")
    assert swapped.program_digest != forward.program_digest
    assert swapped.plan_digest != forward.plan_digest


def test_missing_catalog_contract_surfaces_typed_compile_failure() -> None:
    """movement binding: C1-M002 | evidence ref: evidence:c1:m002:digest-counterexamples"""
    contracts = (
        workflow.build_workflow_contract("workflow.vector_search.v1"),
        workflow.build_workflow_contract("workflow.llm_call.v1"),
    )
    catalog = workflow.build_workflow_catalog(contracts)
    registry = workflow.build_workflow_registry(contracts)
    receipt = workflow.parse_and_validate_workflow_dsl(
        _payload([_node("a", "join", {"field": "values"})]),
        catalog=catalog,
        operation_contracts=registry,
    )

    assert not receipt.ok
    assert receipt.failure is not None
    assert receipt.failure.code == workflow.WORKFLOW_DSL_COMPILE_FAILURE
    assert receipt.failure.nested_code == "UNKNOWN_OPERATION_CONTRACT"


def test_receipt_counts_effect_provider_and_store_as_zero() -> None:
    """movement binding: C1-M001 | evidence ref: evidence:c1:m001:legacy-dsl-parity"""
    ok = workflow.parse_and_validate_workflow_dsl(
        _payload([_node("a", "vector_search"), _node("b", "llm_call")])
    )
    rejected = workflow.parse_and_validate_workflow_dsl(
        _payload([_node("a"), _node("a", "llm_call")])
    )

    for receipt in (ok, rejected):
        assert receipt.provider_calls == 0
        assert receipt.store_writes == 0
        assert receipt.canonical_effect_calls == 0


def test_allowed_node_types_map_to_exact_ordered_operation_kinds() -> None:
    """movement binding: C1-M001 | evidence ref: evidence:c1:m001:legacy-dsl-parity"""
    receipt = workflow.parse_and_validate_workflow_dsl(
        _payload(
            [
                _node("retrieve", "vector_search", {"top_k": 5}),
                _node("draft", "llm_call", {"model": "mrw-local"}),
                _node("combine", "join", {"field": "values"}),
            ],
            edges=[("retrieve", "draft"), ("draft", "combine")],
        )
    )

    assert receipt.ok
    assert workflow.WORKFLOW_ALLOWED_NODE_TYPES == {"vector_search", "llm_call", "join"}
    assert tuple(
        step.operation_contract_ref.kind for step in receipt.plan.ordered_steps
    ) == (
        "workflow.vector_search.v1",
        "workflow.llm_call.v1",
        "workflow.join.v1",
    )
    assert tuple(
        node["contract_kind"] for node in _plain(receipt.program.metadata)["nodes"]
    ) == (
        "workflow.vector_search.v1",
        "workflow.llm_call.v1",
        "workflow.join.v1",
    )


def test_facade_source_has_no_legacy_database_or_provider_imports() -> None:
    """movement binding: C1-M001 | evidence ref: evidence:c1:m001:legacy-dsl-parity"""
    source = inspect.getsource(workflow)
    forbidden_imports = (
        "app.services.workflow_graph",
        "sqlalchemy",
        "openai",
        "app.models",
        "app.successor_runtime.substrate",
    )

    assert all(item not in source for item in forbidden_imports)
