from __future__ import annotations

import ast
import json
from pathlib import Path


_EXACT_KEYS = (
    "derived-marked|main/backend/scripts/check_graph_editing_audit_durability.py|build_gate_snapshot returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_graph_rollout_readback_gate.py|build_gate_snapshot returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_graph_typed_writing_consumer_status_boundary.py|build_check returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_graph_visual_data_smoke_gate.py|build_gate_snapshot returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_policy_state_document_query_boundary.py|build_check returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_prompt_time_density_consumer_boundary.py|build_check returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_source_library_ingest_external_project_contract.py|build_contract returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_source_library_public_replay_a5_gate.py|build_check returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_source_library_relevance_review_queue.py|build_check returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_source_library_review_closure_batch.py|build_check returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_source_library_review_closure_batch.py|build_expected_artifact returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_source_library_review_closure_batch2.py|build_check returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_source_library_review_closure_batch2.py|build_expected_artifact returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_source_library_review_closure_batch3.py|build_check returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_source_library_review_closure_batch3.py|build_expected_artifact returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_source_library_review_closure_batch4.py|build_check returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_source_library_review_closure_batch4.py|build_expected_artifact returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_source_library_search_governance.py|build_check returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_source_library_taxonomy_review_readiness.py|build_check returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_source_library_three_lane_live_closure.py|build_contract returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_structured_consumer_query_extraction.py|build_check returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_structured_sql_helper_migration.py|build_check returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_successor_c7_semantic_movements.py|build_documents returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_time_density_current_state.py|build_current_state returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_time_density_decision_log_contract.py|build_contract returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_time_density_runtime_support.py|build_policy_decision_trace returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_time_density_runtime_support.py|build_time_density_decision_log_features returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_time_density_runtime_support.py|build_time_density_live_gap_markers returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_time_density_runtime_support.py|build_time_semantics returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_time_semantics_ope_contract.py|build_contract returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_time_semantics_release_gate.py|build_check returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_time_semantics_sample_provenance_readback.py|build_check returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_typed_writing_live_boundary.py|build_inventory returns an unmarked derived value",
    "derived-marked|main/backend/scripts/check_wave27_structured_consumer_closure.py|build_check returns an unmarked derived value",
)
_VIEW_FUNCTIONS = {
    "build_expected_artifact",
    "build_time_density_decision_log_features",
    "build_time_semantics",
}
_REPO_ROOT = Path(__file__).resolve().parents[4]
_WITNESS = "test:test_c13_cli_graph_workflow_metadata_preserves_abi"


def _metadata_for(key: str) -> str:
    _gate, relative_path, tail = key.split("|", 2)
    function = tail.split(" ", 1)[0]
    source = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == function
    )
    assert isinstance(node.returns, ast.Subscript)
    assert ast.unparse(node.returns.value) == "Annotated"
    annotation = ast.literal_eval(node.returns.slice.elts[1])
    assert isinstance(annotation, str)
    return annotation


def test_c13_cli_graph_workflow_metadata_preserves_abi() -> None:
    assert len(_EXACT_KEYS) == len(set(_EXACT_KEYS)) == 34

    for key in _EXACT_KEYS:
        metadata = _metadata_for(key)
        expected_view = key.split("|", 2)[2].split(" ", 1)[0] in _VIEW_FUNCTIONS
        expected_derived = "view" if expected_view else "generated_evidence"

        assert metadata.startswith("kit:non-authoritative ")
        assert f"derived_as={expected_derived} " in metadata
        assert "fact_source=" in metadata
        assert f"witness={_WITNESS}" in metadata


def test_c13_frozen_denominator_is_preserved_after_live_baseline_reduction() -> None:
    frozen_path = (
        _REPO_ROOT
        / "docs/governance/functorial-debt-zero-baseline.starting-baseline.v1.json"
    )
    live_path = _REPO_ROOT / "arch-baseline.json"
    frozen = set(json.loads(frozen_path.read_text(encoding="utf-8")))
    live = set(json.loads(live_path.read_text(encoding="utf-8")))

    assert set(_EXACT_KEYS) <= frozen
    assert set(_EXACT_KEYS).isdisjoint(live)
