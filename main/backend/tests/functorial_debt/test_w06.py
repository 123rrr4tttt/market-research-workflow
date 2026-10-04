"""Focused authority metadata and ABI witnesses for packet W06."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import get_args, get_type_hints

from functorial_kit import scan_project, violation_key


REPO_ROOT = Path(__file__).resolve().parents[4]
PACKET_PATH = (
    REPO_ROOT
    / "docs"
    / "governance"
    / "functorial-debt-zero-baseline-packets.v1.json"
)
WITNESS = "test:test_w06_successor_authority_metadata"
SOURCE_TOTAL_CORE_WITNESS = "test:test_w06_c2_total_core_failure_lifts"
CURRENT_NATIVE_WITNESS = (
    "test:test_w08a_remaining_assembly_bindings_are_prepared_commands"
)
NATIVE_WITNESS_BY_ROW = {
    (
        "main/backend/app/successor_runtime/capabilities/knowledge_program.py",
        "build_knowledge_bundle",
    ): CURRENT_NATIVE_WITNESS,
}

# Frozen packet identities stay intact; only current source observations are transported.
_CURRENT_SOURCE_FILES = {'main/backend/app/successor_runtime/capabilities/c1_legacy_dsl.py': 'main/backend/app/successor_runtime/capabilities/workflow_legacy_dsl.py',
 'main/backend/app/successor_runtime/capabilities/c8_graph.py': 'main/backend/app/successor_runtime/capabilities/knowledge_graph_projection.py',
 'main/backend/app/successor_runtime/capabilities/c8_program.py': 'main/backend/app/successor_runtime/capabilities/knowledge_program.py',
 'main/backend/app/successor_runtime/capabilities/c8_report.py': 'main/backend/app/successor_runtime/capabilities/knowledge_report.py',
 'main/backend/app/successor_runtime/capabilities/c8_report_export.py': 'main/backend/app/successor_runtime/capabilities/knowledge_report_export.py',
 'main/backend/app/successor_runtime/capabilities/ingest_c7_common.py': 'main/backend/app/successor_runtime/capabilities/material_ingest_common.py',
 'main/backend/app/successor_runtime/capabilities/ingest_c7_program.py': 'main/backend/app/successor_runtime/capabilities/material_ingest_program.py',
 'main/backend/app/successor_runtime/capabilities/source_library_c2_1.py': 'main/backend/app/successor_runtime/capabilities/source_resolution.py',
 'main/backend/app/successor_runtime/capabilities/source_library_c2_1_program.py': 'main/backend/app/successor_runtime/capabilities/source_resolution_program.py',
 'main/backend/app/successor_runtime/capabilities/source_library_c2_2.py': 'main/backend/app/successor_runtime/capabilities/source_planning.py',
 'main/backend/app/successor_runtime/capabilities/source_library_c2_2_interpreters.py': 'main/backend/app/successor_runtime/capabilities/source_planning_interpreters.py',
 'main/backend/app/successor_runtime/capabilities/source_library_c2_2_program.py': 'main/backend/app/successor_runtime/capabilities/source_planning_program.py',
 'main/backend/app/successor_runtime/capabilities/source_library_c2_3.py': 'main/backend/app/successor_runtime/capabilities/source_provider_acquisition.py',
 'main/backend/app/successor_runtime/capabilities/source_library_c2_3_live_provider.py': 'main/backend/app/successor_runtime/capabilities/source_provider_worker.py',
 'main/backend/app/successor_runtime/capabilities/source_library_c2_3_test_interpreters.py': 'main/backend/app/successor_runtime/capabilities/source_provider_test_interpreters.py',
 'main/backend/app/successor_runtime/capabilities/source_library_c2_4_projection.py': 'main/backend/app/successor_runtime/capabilities/source_terminal_projection.py',
 'main/backend/app/successor_runtime/capabilities/c1_slice_acceptance.py': 'main/backend/app/successor_runtime/capabilities/workflow_slice_acceptance.py',
 'main/backend/app/successor_runtime/capabilities/c8_common.py': 'main/backend/app/successor_runtime/capabilities/knowledge_common.py',
 'main/backend/app/successor_runtime/capabilities/c8_consumer.py': 'main/backend/app/successor_runtime/capabilities/knowledge_consumer.py',
 'main/backend/app/successor_runtime/capabilities/c8_report_export_audit_evidence_surface.py': 'main/backend/app/successor_runtime/capabilities/knowledge_report_export_audit_evidence_surface.py',
 'main/backend/app/successor_runtime/capabilities/c8_report_export_token_state.py': 'main/backend/app/successor_runtime/capabilities/knowledge_report_export_token_state.py',
 'main/backend/app/successor_runtime/capabilities/c8_report_quality_trend_evidence_surface.py': 'main/backend/app/successor_runtime/capabilities/knowledge_report_quality_trend_evidence_surface.py',
 'main/backend/app/successor_runtime/capabilities/c8_test_interpreter.py': 'main/backend/app/successor_runtime/capabilities/knowledge_test_interpreter.py',
 'main/backend/app/successor_runtime/capabilities/c8_typed_knowledge.py': 'main/backend/app/successor_runtime/capabilities/typed_knowledge.py',
 'main/backend/app/successor_runtime/capabilities/c8_writing.py': 'main/backend/app/successor_runtime/capabilities/knowledge_writing.py',
 'main/backend/app/successor_runtime/capabilities/c9_2_search_retrieval_panel.py': 'main/backend/app/successor_runtime/capabilities/search_retrieval_panel.py',
 'main/backend/app/successor_runtime/capabilities/c9_evidence_matrix.py': 'main/backend/app/successor_runtime/capabilities/projection_evidence_matrix.py',
 'main/backend/app/successor_runtime/capabilities/ingest_c7_registry.py': 'main/backend/app/successor_runtime/capabilities/material_ingest_registry.py',
 'main/backend/app/successor_runtime/capabilities/source_library_c2_1_interpreters.py': 'main/backend/app/successor_runtime/capabilities/source_resolution_interpreters.py',
 'main/backend/app/successor_runtime/capabilities/source_library_c2_3_guard_runtime.py': 'main/backend/app/successor_runtime/capabilities/source_provider_guard.py',
 'main/backend/app/successor_runtime/capabilities/source_library_c2_shared.py': 'main/backend/app/successor_runtime/capabilities/source_contracts.py'}
_CURRENT_SOURCE_FUNCTIONS = {'build_c1_catalog': 'build_workflow_catalog',
 'build_c1_contract': 'build_workflow_contract',
 'build_c1_operation_contracts': 'build_workflow_operation_contracts',
 'build_c1_registry': 'build_workflow_registry',
 'build_c8_bridge_bundle': 'build_knowledge_bridge_bundle',
 'build_c8_bundle': 'build_knowledge_bundle',
 'build_c8_catalog': 'build_knowledge_catalog',
 'build_c8_delivery_bridge_bundle': 'build_knowledge_delivery_bridge_bundle',
 'build_c8_delivery_bridge_program': 'build_knowledge_delivery_bridge_program',
 'build_c8_program': 'build_knowledge_program',
 'build_c8_registry': 'build_knowledge_registry',
 'build_c8_report_bridge_program': 'build_knowledge_report_bridge_program',
 'build_ingest_c7_bundle': 'build_material_ingest_bundle',
 'build_ingest_c7_catalog': 'build_material_ingest_catalog',
 'build_ingest_c7_registry': 'build_material_ingest_registry',
 'build_ingest_c7_1_program': 'build_material_stage_candidate_program',
 'build_source_library_c2_1_bundle': 'build_source_resolution_bundle',
 'build_source_library_c2_1_catalog': 'build_source_resolution_catalog',
 'build_source_library_c2_1_registry': 'build_source_resolution_registry',
 'build_source_library_c2_1_program': 'build_source_resolution_program',
 'build_source_library_c2_2_bundle': 'build_source_planning_bundle',
 'build_source_library_c2_2_catalog': 'build_source_planning_catalog',
 'build_source_library_c2_2_registry': 'build_source_planning_registry',
 'build_c2_1_to_c2_2_materialization': 'build_resolution_to_planning_materialization',
 'build_source_library_c2_2_program': 'build_source_planning_program',
 'build_source_library_c2_3_bundle': 'build_source_provider_acquisition_bundle',
 'build_source_library_c2_3_catalog': 'build_source_provider_acquisition_catalog',
 'build_source_library_c2_3_registry': 'build_source_provider_acquisition_registry',
 'build_source_library_c2_4_profiles': 'build_source_terminal_projection_profiles'}


def _w06_derived_rows() -> list[dict[str, object]]:
    packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    packet_w06 = next(item for item in packet["packets"] if item["id"] == "W06")
    return [
        row
        for row in packet_w06["input_rows"]
        if row["gate"] == "derived-marked"
    ]


def _function_return(path: Path, function_name: str) -> ast.Subscript:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    )
    assert isinstance(function.returns, ast.Subscript)
    assert ast.unparse(function.returns.value) == "Annotated"
    assert isinstance(function.returns.slice, ast.Tuple)
    assert len(function.returns.slice.elts) == 2
    return function.returns


def test_w06_successor_authority_metadata() -> None:
    rows = _w06_derived_rows()
    assert len(rows) == 54
    seen: set[tuple[str, str]] = set()

    for row in rows:
        historical_name = str(row["message"]).split()[0]
        function_name = _CURRENT_SOURCE_FUNCTIONS.get(historical_name, historical_name)
        relative_path = _CURRENT_SOURCE_FILES.get(str(row["file"]), str(row["file"]))
        path = REPO_ROOT / relative_path
        annotation = _function_return(path, function_name)
        literal_node = annotation.slice.elts[1]
        assert isinstance(literal_node, ast.Subscript)
        metadata = ast.literal_eval(literal_node.slice)
        assert isinstance(metadata, str)

        if function_name == "build_serper_live_gateway":
            assert metadata.startswith(
                "kit:prepared-command effect_boundary=source_library.serper.live_provider"
            )
        elif (relative_path, function_name) in NATIVE_WITNESS_BY_ROW:
            assert metadata.startswith(
                "kit:non-authoritative derived_as=view fact_source=native_C8_definitions "
            )
        else:
            assert metadata.startswith("kit:non-authoritative derived_as=")
            assert " fact_source=" in metadata

        expected_witness = NATIVE_WITNESS_BY_ROW.get((relative_path, function_name), WITNESS)
        assert metadata.endswith(expected_witness)
        seen.add((relative_path, function_name))

    assert len(seen) == len(rows) == 54


def test_w06_metadata_preserves_c1_runtime_abi() -> None:
    from app.successor_runtime.capabilities.workflow_legacy_dsl import (
        build_workflow_catalog,
        build_workflow_contract,
        build_workflow_operation_contracts,
        build_workflow_registry,
    )

    contracts = build_workflow_operation_contracts()
    assert [contract.ref.kind for contract in contracts] == [
        "workflow.vector_search.v1",
        "workflow.llm_call.v1",
        "workflow.join.v1",
    ]
    assert build_workflow_contract("workflow.vector_search.v1") == contracts[0]
    catalog = build_workflow_catalog(contracts)
    registry = build_workflow_registry(contracts)
    assert catalog.entries == tuple(
        (
            contract.ref.kind,
            contract.ref.contract_version,
            contract.ref.contract_digest,
            contract.owner_capability_id,
        )
        for contract in contracts
    )
    assert (registry.catalog, registry.contracts) == (catalog, contracts)

    hints = get_type_hints(build_workflow_contract, include_extras=True)
    return_metadata = get_args(hints["return"].__metadata__[0])[0]
    assert return_metadata.startswith("kit:non-authoritative derived_as=view ")
    assert "fact_source=WORKFLOW_CONTRACT_KINDS+_make_contract" in return_metadata
    assert WITNESS in return_metadata


def test_w06_live_gateway_is_prepared_not_executed() -> None:
    from app.successor_runtime.capabilities.source_provider_worker import (
        build_serper_live_gateway,
    )

    assert build_serper_live_gateway(api_key_provider=lambda: None) is None

    captured: list[str] = []

    def provider() -> str:
        captured.append("resolve")
        return "test-key"

    gateway = build_serper_live_gateway(api_key_provider=provider)
    assert gateway is not None
    assert captured == ["resolve"]
    return_metadata = get_type_hints(build_serper_live_gateway, include_extras=True)[
        "return"
    ]
    assert get_args(return_metadata.__metadata__[0])[0] == (
        "kit:prepared-command effect_boundary=source_library.serper.live_provider "
        f"witness={WITNESS}"
    )


def test_w06_c2_total_core_failure_lifts() -> None:
    """The complete W06 no-throw packet is closed after the C7 rebind."""

    packet = json.loads(PACKET_PATH.read_text(encoding="utf-8"))
    packet_w06 = next(item for item in packet["packets"] if item["id"] == "W06")
    expected = {
        f"{row['gate']}|{_CURRENT_SOURCE_FILES.get(row['file'], row['file'])}|{row['message']}"
        for row in packet_w06["input_rows"]
        if row["gate"] == "no-throw-in-core"
    }
    actual = {violation_key(violation) for violation in scan_project(REPO_ROOT).violations}

    assert len(expected) == 44
    assert expected.isdisjoint(actual)


def test_w06_c9_total_core_failure_lifts() -> None:
    from app.successor_runtime.capabilities.source_library_worker_readback import (
        SourceLibraryWorkerObservation,
    )

    try:
        SourceLibraryWorkerObservation(
            item_key="item-1",
            plan_mode="invalid",  # type: ignore[arg-type]
            phase="planned",
            guard_decision="missing",
            observed_at="2026-09-05T00:00:00Z",
        )
    except ValueError as error:
        assert "unknown plan_mode" in str(error)
    else:
        raise AssertionError("worker readback must lift its typed C9 failure")
