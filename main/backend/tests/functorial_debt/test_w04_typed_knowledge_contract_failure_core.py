from __future__ import annotations

import ast
from pathlib import Path

import pytest
from functorial_kit import Failure

from app.services.typed_knowledge import contracts


REPO_ROOT = Path(__file__).resolve().parents[4]


def test_typed_knowledge_validator_returns_closed_failure_with_context() -> None:
    failure = contracts.try_validate_knowledge_item(
        contracts.KnowledgeItem(
            key="ki:bad",
            project_key="demo_proj",
            canonical_statement="statement",
            primary_type_node_key="type:policy",
            evidence_refs=(),
        )
    )

    assert isinstance(failure, Failure)
    assert (failure.family, failure.code, failure.message) == (
        "typed_knowledge.contract_failure",
        "object_contract_invalid",
        "knowledge_item_missing_provenance",
    )
    assert failure.context == {
        "owner": "typed_knowledge.contracts.knowledge_item",
        "public_exception": "TypedKnowledgeContractError",
        "public_message": "knowledge_item_missing_provenance",
        "field": "evidence_refs",
    }


def test_typed_knowledge_legacy_contract_abi_is_preserved() -> None:
    with pytest.raises(contracts.TypedKnowledgeContractError, match="knowledge_item_missing_provenance"):
        contracts.validate_knowledge_item(
            contracts.KnowledgeItem(
                key="ki:bad",
                project_key="demo_proj",
                canonical_statement="statement",
                primary_type_node_key="type:policy",
                evidence_refs=(),
            )
        )


def test_typed_knowledge_failure_lift_rejects_invalid_context() -> None:
    failure = contracts.typed_knowledge_failure(
        "object_contract_invalid",
        "bad",
        owner="typed_knowledge.test",
    )
    failure.context.pop("public_exception", None)
    with pytest.raises(TypeError, match="failure lift context"):
        contracts.raise_typed_knowledge_legacy(failure)


def test_typed_knowledge_failure_lift_preserves_cause() -> None:
    failure = contracts.typed_knowledge_failure(
        "object_contract_invalid",
        "bad",
        owner="typed_knowledge.test",
    )
    cause = RuntimeError("cause")
    with pytest.raises(contracts.TypedKnowledgeContractError, match="bad") as raised:
        contracts.raise_typed_knowledge_legacy(failure, cause=cause)
    assert raised.value.__cause__ is cause


def test_typed_knowledge_governance_core_returns_typed_failure() -> None:
    result = contracts.try_apply_review_state_transition(
        current_state=contracts.REVIEW_STATE_DRAFT_CANDIDATE,
        target_state=contracts.REVIEW_STATE_HUMAN_CONFIRMED,
        actor=contracts.ACTOR_AUTOMATION,
    )
    assert isinstance(result, Failure)
    assert result.code == "governance_transition_invalid"
    assert result.message == "governance_transition_requires_human"


def test_contract_core_raise_sites_are_only_centralized_lift() -> None:
    path = REPO_ROOT / "main/backend/app/services/typed_knowledge/contracts.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    raises = [node for node in ast.walk(tree) if isinstance(node, ast.Raise)]
    parent: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[child] = node
    enclosing_names: list[str] = []
    for node in raises:
        current = parent.get(node)
        while current is not None and not isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            current = parent.get(current)
        assert isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef))
        enclosing_names.append(current.name)
    assert set(enclosing_names) == {"raise_typed_knowledge_legacy"}
