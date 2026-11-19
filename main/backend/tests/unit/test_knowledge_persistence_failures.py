from __future__ import annotations

import ast
from pathlib import Path

import pytest
from functorial_kit import Failure

from app.services.typed_knowledge import persistence_boundary as boundary


REPO_ROOT = Path(__file__).resolve().parents[4]


def test_persistence_shell_failure_preserves_registered_code_and_context() -> None:
    failure = boundary.try_validate_persistence_boundary_record(
        boundary.PersistenceBoundaryRecord(
            contract_version="wrong",
            object_type=boundary.OBJECT_TYPE_KNOWLEDGE_ITEM,
            object_key="ki:1",
            project_key="demo_proj",
            identity_ref="demo_proj:knowledge_item:ki:1",
            visibility_scope="internal_only",
            lifecycle_state=boundary.LIFECYCLE_STATE_PROPOSED,
            governance={"review_state": "draft_candidate"},
        )
    )
    assert isinstance(failure, Failure)
    assert failure.family == "typed_knowledge.persistence_boundary_failure"
    assert failure.code == boundary.TYPED_KNOWLEDGE_PERSISTENCE_BOUNDARY_FAILURE
    assert failure.message == "persistence_boundary_contract_version_mismatch"
    assert failure.context["owner"] == "typed_knowledge.persistence_boundary.record"


def test_persistence_shell_legacy_error_keeps_stable_failure_code() -> None:
    with pytest.raises(boundary.TypedKnowledgePersistenceBoundaryError, match="persistence_boundary_contract_version_mismatch") as raised:
        boundary.validate_persistence_boundary_record(
            boundary.PersistenceBoundaryRecord(
                contract_version="wrong",
                object_type=boundary.OBJECT_TYPE_KNOWLEDGE_ITEM,
                object_key="ki:1",
                project_key="demo_proj",
                identity_ref="demo_proj:knowledge_item:ki:1",
                visibility_scope="internal_only",
                lifecycle_state=boundary.LIFECYCLE_STATE_PROPOSED,
                governance={"review_state": "draft_candidate"},
            )
        )
    assert raised.value.failure_code == boundary.TYPED_KNOWLEDGE_PERSISTENCE_BOUNDARY_FAILURE


def test_typed_knowledge_persistence_failure_lift_rejects_invalid_context() -> None:
    failure = boundary.typed_knowledge_persistence_failure("bad")
    failure.context.pop("public_exception", None)
    with pytest.raises(TypeError, match="failure lift context"):
        boundary.raise_typed_knowledge_persistence_legacy(failure)


def test_typed_knowledge_persistence_failure_lift_preserves_cause() -> None:
    failure = boundary.typed_knowledge_persistence_failure("bad")
    cause = RuntimeError("cause")
    with pytest.raises(boundary.TypedKnowledgePersistenceBoundaryError, match="bad") as raised:
        boundary.raise_typed_knowledge_persistence_legacy(failure, cause=cause)
    assert raised.value.__cause__ is cause


def test_persistence_envelope_authority_and_live_db_claims_remain_guarded() -> None:
    envelope = boundary.build_sample_boundary_envelope()
    assert envelope["meta"]["readiness"]["live_db_persistence"] is False
    assert "live_db_persistence_not_implemented" in envelope["meta"]["remaining_live_gaps"]
    boundary.validate_persistence_api_envelope(envelope)


def test_persistence_core_raise_sites_are_only_centralized_lift() -> None:
    path = REPO_ROOT / "main/backend/app/services/typed_knowledge/persistence_boundary.py"
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
    assert set(enclosing_names) == {"raise_typed_knowledge_persistence_legacy"}
