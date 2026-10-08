"""Focused authority metadata and ABI witnesses for packet W06."""

from __future__ import annotations

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
# Frozen packet identities stay intact; only current source observations are transported.
_CURRENT_SOURCE_FILES = {'main/backend/app/successor_runtime/capabilities/c8_graph.py': 'main/backend/app/successor_runtime/capabilities/knowledge_graph_projection.py',
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
