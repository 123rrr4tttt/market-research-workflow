"""S2b cell-extension wiring tests for ALL-SM-001/002/009.

Each family assembly builder installs its typed successor route only when the
caller supplies the corresponding deterministic closure.  These tests prove
the C7.2 ingest-registry handler, C9.1 evidence-matrix route and C8.3
export/token-state handler are really carried by the family assemblies and by
the serial successor composition root without granting authority.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine

from app.successor_runtime.assembly.base import (
    C7AssemblyOptions,
    C8AssemblyOptions,
    C9AssemblyOptions,
    FamilyAssemblyOptions,
    local_assembly_scope_digest,
)
from app.successor_runtime.assembly.c7_assembly import build_c7_assembly
from app.successor_runtime.assembly.c8_assembly import build_c8_assembly
from app.successor_runtime.assembly.c9_assembly import build_c9_assembly
from app.successor_runtime.assembly.successor_assembly import assemble_successor_runtime
from app.successor_runtime.capabilities.c8_report_export_token_state import (
    ClaimExportTokenCommand,
    LocalSuccessorReportExportTokenStore,
)
from app.successor_runtime.capabilities.c9_evidence_matrix import (
    BUSINESS_LINE_KEYS,
    WORKER_REQUIRED_BUSINESS_LINE_KEYS,
    BusinessLineEvidenceRecord,
    EvidenceRowStatus,
    EvidenceSourceRef,
)
from app.successor_runtime.capabilities.ingest_c7_registry import (
    IngestRegistryReserveCommand,
    LocalSuccessorIngestRegistryStore,
    derive_registry_identity,
)
from app.successor_runtime.substrate.postgres.c8_export_token_state_handler import (
    C8_3ExportTokenStateRuntimeHandler,
)
from app.successor_runtime.substrate.postgres.ingest_c7_registry_handler import (
    C7IngestRegistryRuntimeHandler,
)
from app.successor_runtime.substrate.projections.evidence_matrix import (
    C9EvidenceMatrixRouteHandler,
)

pytestmark = pytest.mark.unit

_PROJECT_KEY = "s2b-local"
_OBSERVED_AT = "2026-09-02T16:00:00+00:00"


def _c7_options() -> C7AssemblyOptions:
    identity = derive_registry_identity(
        project_key=_PROJECT_KEY,
        trigger_type="ingest.url.single",
        idempotency_key="idem:s2b-cell-extension:001",
        request_payload={"url": "https://example.com/article", "kind": "url"},
    )
    return C7AssemblyOptions(
        registry_store=LocalSuccessorIngestRegistryStore(),
        registry_command=IngestRegistryReserveCommand(
            identity=identity,
            subject_payload={"url": "https://example.com/article"},
            request_payload={"url": "https://example.com/article", "kind": "url"},
        ),
    )


def _c8_options() -> C8AssemblyOptions:
    return C8AssemblyOptions(
        export_token_store=LocalSuccessorReportExportTokenStore(),
        export_token_command=ClaimExportTokenCommand(
            artifact_id="artifact:s2b-cell-extension:001",
            actor_digest="actor:sha256:0011223344556677",
            project_key=_PROJECT_KEY,
            trace_id="trace:s2b-cell-extension:001",
            request_id="req:s2b-cell-extension:001",
        ),
    )


def _evidence_records() -> tuple[BusinessLineEvidenceRecord, ...]:
    records: list[BusinessLineEvidenceRecord] = []
    for index, line_key in enumerate(BUSINESS_LINE_KEYS, start=1):
        worker_required = line_key in WORKER_REQUIRED_BUSINESS_LINE_KEYS
        records.append(
            BusinessLineEvidenceRecord(
                line_key=line_key,
                status=EvidenceRowStatus.PASSED,
                reason_code="successor_line_event_readback_passed",
                requires_worker_readback=worker_required,
                persistence_decidable=worker_required,
                source_refs=(
                    EvidenceSourceRef(
                        source_kind="line_event_readback",
                        observed_at=_OBSERVED_AT,
                        status="passed",
                        reason_code="terminal_readback_observed",
                    ),
                ),
                observed_at=_OBSERVED_AT,
            )
        )
    return tuple(records)


def _c9_options() -> C9AssemblyOptions:
    return C9AssemblyOptions(evidence_records=_evidence_records())


def test_s2b_c7_2_ingest_registry_handler_wired_in_c7_assembly() -> None:
    assembly = build_c7_assembly(
        options=_c7_options(),
        project_scope_digest=local_assembly_scope_digest(),
    )

    registry_handlers = [
        handler
        for handler in assembly.handlers
        if isinstance(handler, C7IngestRegistryRuntimeHandler)
    ]
    assert len(registry_handlers) == 1
    assert assembly.cell("C7.2").status == "INSTALLED"
    assert "ingest-submission registry typed route handler installed" in (
        assembly.cell("C7.2").note
    )
    assert registry_handlers[0].execute_calls == 0


def test_s2b_c8_3_export_token_state_handler_wired_in_c8_assembly() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    assembly = build_c8_assembly(
        engine=engine,
        project_scope_digest=local_assembly_scope_digest(),
        options=_c8_options(),
    )

    export_handlers = [
        handler
        for handler in assembly.handlers
        if isinstance(handler, C8_3ExportTokenStateRuntimeHandler)
    ]
    assert len(export_handlers) == 1
    assert assembly.cell("C8.3").status == "INSTALLED"
    assert "report-export/token-state successor route installed" in (
        assembly.cell("C8.3").note
    )
    assert export_handlers[0].execute_calls == 0


def test_s2b_c9_evidence_matrix_route_wired_in_c9_assembly() -> None:
    assembly = build_c9_assembly(options=_c9_options())

    matrix_handlers = [
        handler
        for handler in assembly.handlers
        if isinstance(handler, C9EvidenceMatrixRouteHandler)
    ]
    assert len(matrix_handlers) == 1
    assert "evidence-matrix read-only route handler carried by the family" in (
        assembly.cell("C9.3").note
    )
    assert matrix_handlers[0].execute_calls == 0


def test_s2b_successor_assembly_carries_all_three_cell_extension_handlers() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    assembly = assemble_successor_runtime(
        engine=engine,
        options=FamilyAssemblyOptions(
            c7=_c7_options(),
            c8=_c8_options(),
            c9=_c9_options(),
        ),
    )

    handler_types = {
        C7IngestRegistryRuntimeHandler: "C7.2",
        C8_3ExportTokenStateRuntimeHandler: "C8.3",
        C9EvidenceMatrixRouteHandler: "C9.3",
    }
    for handler_type, cell_id in handler_types.items():
        matches = [
            handler
            for handler in assembly.handlers
            if isinstance(handler, handler_type)
        ]
        assert len(matches) == 1, cell_id
        assert assembly.by_cell(cell_id).status in (
            "INSTALLED",
            "PROJECTOR_WIRING_DECLARED",
        )


def test_s2b_assembly_requires_pairwise_store_and_command() -> None:
    scope = local_assembly_scope_digest()
    with pytest.raises(ValueError, match="registry_store"):
        build_c7_assembly(
            options=C7AssemblyOptions(
                registry_store=LocalSuccessorIngestRegistryStore()
            ),
            project_scope_digest=scope,
        )
    with pytest.raises(ValueError, match="export_token_store"):
        build_c8_assembly(
            engine=create_engine("sqlite+pysqlite:///:memory:", future=True),
            project_scope_digest=scope,
            options=C8AssemblyOptions(
                export_token_command=ClaimExportTokenCommand(
                    artifact_id="artifact:s2b-cell-extension:002",
                    actor_digest="actor:sha256:0011223344556677",
                )
            ),
        )


def test_s2b_cell_extension_handlers_keep_authority_false_until_execute() -> None:
    scope = local_assembly_scope_digest()
    c7_assembly = build_c7_assembly(options=_c7_options(), project_scope_digest=scope)
    c7_handler = next(
        handler
        for handler in c7_assembly.handlers
        if isinstance(handler, C7IngestRegistryRuntimeHandler)
    )
    assert c7_handler.command.authority is None

    c8_assembly = build_c8_assembly(
        engine=create_engine("sqlite+pysqlite:///:memory:", future=True),
        project_scope_digest=scope,
        options=_c8_options(),
    )
    c8_handler = next(
        handler
        for handler in c8_assembly.handlers
        if isinstance(handler, C8_3ExportTokenStateRuntimeHandler)
    )
    assert all(
        not value
        for value in c8_handler.command.authority.to_plain().values()
        if isinstance(value, bool)
    )

    c9_assembly = build_c9_assembly(options=_c9_options())
    c9_handler = next(
        handler
        for handler in c9_assembly.handlers
        if isinstance(handler, C9EvidenceMatrixRouteHandler)
    )
    assert c9_handler.execute_calls == 0
