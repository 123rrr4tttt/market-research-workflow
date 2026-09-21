"""Focused W04 authority metadata and unresolved raise-inventory witness."""

from __future__ import annotations

import ast
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
WITNESS = "test:test_w04_authority_metadata"


def _metadata(annotation: ast.expr) -> str:
    assert isinstance(annotation, ast.Subscript)
    assert isinstance(annotation.value, ast.Name)
    assert annotation.value.id == "Annotated"
    value = annotation.slice
    if isinstance(value, ast.Tuple):
        assert len(value.elts) == 2
        value = value.elts[1]
    assert isinstance(value, ast.Constant)
    assert isinstance(value.value, str)
    return value.value


def _function(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    matches = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    assert len(matches) == 1, f"{path}:{name} expected exactly one top-level function"
    return matches[0]


def _assert_authority(
    path: Path,
    name: str,
    *,
    tag: str,
    fields: dict[str, str],
) -> None:
    node = _function(path, name)
    assert node.returns is not None
    tokens = _metadata(node.returns).split()
    assert tokens[0] == tag
    parsed: dict[str, str] = {}
    for token in tokens[1:]:
        key, value = token.split("=", 1)
        parsed[key] = value
    assert parsed == fields
    assert parsed["witness"] == WITNESS

    body_source = "\n".join(ast.get_source_segment(path.read_text(encoding="utf-8"), child) or "" for child in node.body)
    assert "kit:" not in body_source


def test_w04_authority_metadata() -> None:
    packet = json.loads(
        (REPO_ROOT / "docs/governance/functorial-debt-zero-baseline-packets.v1.json").read_text(
            encoding="utf-8"
        )
    )
    w04 = next(packet_item for packet_item in packet["packets"] if packet_item["id"] == "W04")
    derived_keys = {key for key in w04["expected_removed_keys"] if key.startswith("derived-marked|")}
    assert len(derived_keys) == 52

    expected_targets: set[tuple[str, str]] = set()
    for key in derived_keys:
        gate, relative_path, message = key.split("|", 2)
        assert gate == "derived-marked"
        function_name = message.removesuffix(" returns an unmarked derived value")
        expected_targets.add((relative_path, function_name))

    classifications: dict[tuple[str, str], tuple[str, dict[str, str]]] = {
        ("main/backend/app/services/clue_chains/external_search_expansion.py", "build_external_search_provider"): (
            "kit:prepared-command",
            {"effect_boundary": "external_search_provider"},
        ),
        ("main/backend/app/services/clue_chains/graph_integration.py", "build_graph_submit_bridge_envelope"): (
            "kit:prepared-command",
            {"effect_boundary": "clue_chain_graph_submit"},
        ),
        ("main/backend/app/services/clue_chains/graph_integration.py", "build_graph_handoff_payload"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "graph_mutation+evidence_pack"},
        ),
        ("main/backend/app/services/clue_chains/graph_integration.py", "build_graph_evidence_pack"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "graph_mutation_payload"},
        ),
        ("main/backend/app/services/clue_chains/graph_integration.py", "build_graph_mutation_payload"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "decisions+candidates+evidence"},
        ),
        ("main/backend/app/services/clue_chains/store.py", "build_clue_chain_store"): (
            "kit:prepared-command",
            {"effect_boundary": "ingest_config_clue_chain_store"},
        ),
        ("main/backend/app/services/document_queries/contracts.py", "build_document_query_result_item"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "repository_row+source_type+rank"},
        ),
        ("main/backend/app/services/document_queries/contracts.py", "build_document_query_result_envelope"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "document_query+rows+source+meta"},
        ),
        ("main/backend/app/services/document_queries/search_endpoint.py", "build_search_endpoint_document_query"): (
            "kit:prepared-command",
            {"effect_boundary": "app.services.document_queries.statement_builder"},
        ),
        ("main/backend/app/services/document_queries/statement_builder.py", "build_document_query_statement"): (
            "kit:prepared-command",
            {"effect_boundary": "document_query_statement"},
        ),
        ("main/backend/app/services/document_views/policy_view.py", "build_policy_summary"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "policy_document_extractors"},
        ),
        ("main/backend/app/services/document_views/policy_view.py", "build_policy_detail"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "policy_summary+document_detail_extractors"},
        ),
        ("main/backend/app/services/document_views/social_view.py", "build_social_data_item"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "social_document_extracted_data"},
        ),
        ("main/backend/app/services/document_views/writing_card_view.py", "build_keyword_card"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "keyword_card_inputs+system_clock"},
        ),
        ("main/backend/app/services/document_views/writing_card_view.py", "build_keyword_card_from_hybrid_row"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "hybrid_search_row"},
        ),
        ("main/backend/app/services/document_views/writing_card_view.py", "build_keyword_card_from_source_row"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "source_row"},
        ),
        ("main/backend/app/services/document_views/writing_card_view.py", "build_keyword_card_from_material_item"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "material_item"},
        ),
        ("main/backend/app/services/document_views/writing_card_view.py", "build_keyword_card_from_graph_node"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "graph_node+graph_context"},
        ),
        ("main/backend/app/services/document_views/writing_card_view.py", "build_keyword_card_from_typed_knowledge_handoff"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "validated_writing_knowledge_handoff"},
        ),
        ("main/backend/app/services/document_views/writing_view.py", "build_writing_conflict_details"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "writing_document_row+expected_version"},
        ),
        ("main/backend/app/services/graph/builder.py", "build_graph"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "normalized_social_posts+graph_parameters"},
        ),
        ("main/backend/app/services/graph/builder.py", "build_topic_subgraph"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "source_graph+topic_label+time_window"},
        ),
        ("main/backend/app/services/graph/builder.py", "build_market_graph"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "normalized_market_data"},
        ),
        ("main/backend/app/services/graph/builder.py", "build_policy_graph"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "normalized_policy_data"},
        ),
        ("main/backend/app/services/graph/persistence/graph_live_smoke_readiness.py", "build_graph_live_smoke_readiness"): (
            "kit:non-authoritative",
            {"derived_as": "generated_evidence", "fact_source": "dry_run+readiness+database+smoke_evidence_inputs"},
        ),
        ("main/backend/app/services/graph/persistence/graph_node_live_db_rollout_gate.py", "build_graph_node_live_db_rollout_gate"): (
            "kit:non-authoritative",
            {"derived_as": "generated_evidence", "fact_source": "dry_run+readiness+database+live_db_evidence_inputs"},
        ),
        ("main/backend/app/services/graph/persistence/graph_node_rollout_manifest.py", "build_graph_node_rollout_manifest"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "gate+readiness+manifest_inputs"},
        ),
        ("main/backend/app/services/graph/persistence/graph_projection_contract.py", "build_graph_projection_rollout_readiness"): (
            "kit:non-authoritative",
            {"derived_as": "preflight", "fact_source": "rollout_mode+limit+precondition_inputs"},
        ),
        ("main/backend/app/services/graph/persistence/graph_projection_contract.py", "build_graph_projection_dry_run"): (
            "kit:non-authoritative",
            {"derived_as": "simulation", "fact_source": "in_memory_graph+schema_version"},
        ),
        ("main/backend/app/services/search/vector_contracts.py", "build_query_group_id"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "search_query_parameters"},
        ),
        ("main/backend/app/services/search/vector_contracts.py", "build_global_vector_object"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "search_row+projection_parameters"},
        ),
        ("main/backend/app/services/search/vector_contracts.py", "build_search_evidence_hit"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "search_row+query_group+rank_parameters"},
        ),
        ("main/backend/app/services/search/vector_contracts.py", "build_search_evidence_hits"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "search_rows+query_parameters"},
        ),
        ("main/backend/app/services/search/vector_contracts.py", "build_retrieval_run_record"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "query+evidence_hits+rank_parameters"},
        ),
        ("main/backend/app/services/search/vector_contracts.py", "build_agent_matrix_evidence_hits"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "agent_matrix_candidates+query_parameters"},
        ),
        ("main/backend/app/services/typed_knowledge/contracts.py", "build_downstream_contract_draft"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "validated_knowledge_item"},
        ),
        ("main/backend/app/services/typed_knowledge/contracts.py", "build_writing_knowledge_handoff"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "validated_downstream_contract+selection_inputs"},
        ),
        ("main/backend/app/services/typed_knowledge/contracts.py", "build_writing_knowledge_context_envelope"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "validated_writing_handoffs"},
        ),
        ("main/backend/app/services/typed_knowledge/persistence_boundary.py", "build_writing_handoff_ref"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "validated_writing_knowledge_handoff"},
        ),
        ("main/backend/app/services/typed_knowledge/persistence_boundary.py", "build_identity_ref"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "project_key+object_type+object_key"},
        ),
        ("main/backend/app/services/typed_knowledge/persistence_boundary.py", "build_sample_boundary_envelope"): (
            "kit:non-authoritative",
            {"derived_as": "generated_evidence", "fact_source": "typed_knowledge_fixture_inputs"},
        ),
        ("main/backend/app/services/typed_knowledge/persistence_boundary.py", "build_live_db_boundary_envelope"): (
            "kit:authoritative-write",
            {"canonical_writer": "SqlAlchemyTypedKnowledgeRepository"},
        ),
        ("main/backend/app/services/typed_knowledge/persistence_boundary.py", "build_live_writing_context_from_repository"): (
            "kit:canonical-read",
            {"canonical_owner": "SqlAlchemyTypedKnowledgeRepository"},
        ),
        ("main/backend/app/services/typed_knowledge/persistence_boundary.py", "build_public_api_route_contract_envelope"): (
            "kit:non-authoritative",
            {"derived_as": "generated_evidence", "fact_source": "boundary_envelope+live_db_flag"},
        ),
        ("main/backend/app/services/typed_knowledge/persistence_boundary.py", "build_persisted_card_request_response_readback"): (
            "kit:non-authoritative",
            {"derived_as": "generated_evidence", "fact_source": "boundary_envelope+live_db_flag"},
        ),
        ("main/backend/app/services/workflow_graph/contracts.py", "build_workflow_graph_integrity_report"): (
            "kit:non-authoritative",
            {"derived_as": "preflight", "fact_source": "node_ids+edges+topo_order"},
        ),
        ("main/backend/app/services/workflow_graph/governance_contract.py", "build_graph_edit_audit_record"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "graph_edit_governance_inputs"},
        ),
        ("main/backend/app/services/workflow_graph/governance_contract.py", "build_graph_rollback_contract"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "graph_rollback_governance_inputs"},
        ),
        ("main/backend/app/services/workflow_graph/governance_contract.py", "build_handoff_audit_record"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "handoff_audit_inputs"},
        ),
        ("main/backend/app/services/workflow_graph/store.py", "build_run_store"): (
            "kit:prepared-command",
            {"effect_boundary": "workflow_graph_run_store"},
        ),
        ("main/backend/app/services/workflow_graph/store.py", "build_compiled_graph_store"): (
            "kit:prepared-command",
            {"effect_boundary": "workflow_graph_compiled_store"},
        ),
        ("main/backend/app/services/writing/primary_loop_service.py", "build_wave_a_baseline_matrix"): (
            "kit:non-authoritative",
            {"derived_as": "view", "fact_source": "writing_baseline_capability_constants"},
        ),
    }

    assert set(classifications) == expected_targets
    for (relative_path, function_name), (tag, fields) in sorted(classifications.items()):
        _assert_authority(
            REPO_ROOT / relative_path,
            function_name,
            tag=tag,
            fields={**fields, "witness": WITNESS},
        )
