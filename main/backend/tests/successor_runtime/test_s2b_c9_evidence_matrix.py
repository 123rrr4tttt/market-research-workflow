"""Focused unit tests for the S2b C9.1 evidence-matrix capability."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.successor_runtime.assembly.base import (
    local_assembly_scope_digest,
    successor_binding,
)
from app.successor_runtime.capabilities import c9_evidence_matrix as capability
from app.successor_runtime.capabilities.c9_evidence_matrix import (
    BUSINESS_LINE_KEYS,
    NON_WORKER_TERMINAL_STATUS,
    WORKER_REQUIRED_BUSINESS_LINE_KEYS,
    BusinessLineEvidenceRecord,
    EvidenceMatrixAuthority,
    EvidenceMatrixIntegrityError,
    EvidenceMatrixLineSetError,
    EvidenceMatrixSourceError,
    EvidenceMatrixSummary,
    EvidenceRowStatus,
    EvidenceSourceRef,
    project_business_line_evidence_matrix,
)
from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    ReturnContract,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    ReturnContractBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    NodeIdentity,
    RuntimeExecutionContext,
)
from app.successor_runtime.substrate.projections import evidence_matrix as projection
from app.successor_runtime.substrate.projections.evidence_matrix import (
    C9EvidenceMatrixRouteHandler,
    project_evidence_matrix_payload,
    project_evidence_matrix_readback,
)

pytestmark = pytest.mark.unit

OBSERVED_AT = "2026-09-02T01:00:00+00:00"


def _sha256(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


_OP_DIGEST = _sha256("c9.1:operation:evidence-matrix")
_PROFILE_DIGEST = _sha256("c9.1:profile:evidence-matrix")
_DEPLOYMENT_DIGEST = _sha256("c9.1:deployment:evidence-matrix")
_AUTHORITY_REQUIREMENT_DIGEST = _sha256("c9.1:authority-requirement:read-only")
_OTHER_DIGEST = _sha256("c9.1:other-binding-content")


def _source_ref(line_key: str) -> EvidenceSourceRef:
    terminal_status = NON_WORKER_TERMINAL_STATUS.get(
        line_key,
        "readback_persisted",
    )
    source_kind = (
        "terminal_readback_event"
        if line_key in WORKER_REQUIRED_BUSINESS_LINE_KEYS
        else "endpoint_readback"
    )
    return EvidenceSourceRef(
        source_kind=source_kind,
        observed_at=OBSERVED_AT,
        status=terminal_status,
        reason_code=f"{source_kind}_ok",
        digest=_sha256(f"{line_key}:{terminal_status}"),
    )


def _record(
    line_key: str,
    *,
    status: EvidenceRowStatus = EvidenceRowStatus.PASSED,
    reason_code: str | None = None,
    decidable: bool = True,
    source: bool = True,
) -> BusinessLineEvidenceRecord:
    worker_required = line_key in WORKER_REQUIRED_BUSINESS_LINE_KEYS
    if reason_code is None:
        reason_code = (
            "terminal_readback_persisted"
            if worker_required
            else "endpoint_readback_passed"
        )
    source_refs = (_source_ref(line_key),) if source else ()
    return BusinessLineEvidenceRecord(
        line_key=line_key,
        status=status,
        reason_code=reason_code,
        requires_worker_readback=worker_required,
        persistence_decidable=decidable,
        source_refs=source_refs,
        observed_at=OBSERVED_AT,
    )


def _all_passed_records() -> tuple[BusinessLineEvidenceRecord, ...]:
    return tuple(_record(line_key) for line_key in BUSINESS_LINE_KEYS)


def _binding(
    *,
    operation_digest: str = _OP_DIGEST,
    profile_digest: str = _PROFILE_DIGEST,
    deployment_digest: str = _DEPLOYMENT_DIGEST,
) -> InterpreterBinding:
    return successor_binding(
        operation_contract_digest=operation_digest,
        interpreter_profile_digest=profile_digest,
        deployment_catalog_digest=deployment_digest,
        project_scope_digest=local_assembly_scope_digest(),
        authority_requirement_digest=_AUTHORITY_REQUIREMENT_DIGEST,
        resource_policy_epoch=1,
    )


def _handler(
    records: tuple[BusinessLineEvidenceRecord, ...],
    *,
    operation_digest: str = _OP_DIGEST,
    profile_digest: str = _PROFILE_DIGEST,
    deployment_digest: str = _DEPLOYMENT_DIGEST,
) -> C9EvidenceMatrixRouteHandler:
    binding = _binding(
        operation_digest=operation_digest,
        profile_digest=profile_digest,
        deployment_digest=deployment_digest,
    )
    return C9EvidenceMatrixRouteHandler(
        records=records,
        handler_binding_digest=binding.binding_digest,
        interpreter_profile_digest=profile_digest,
        operation_contract_digest=operation_digest,
        deployment_catalog_digest=deployment_digest,
    )


def _assignment(
    *,
    operation_digest: str = _OP_DIGEST,
    profile_digest: str = _PROFILE_DIGEST,
    deployment_digest: str = _DEPLOYMENT_DIGEST,
    binding: InterpreterBinding | None = None,
) -> RuntimeAssignment:
    exact_binding = binding or _binding(
        operation_digest=operation_digest,
        profile_digest=profile_digest,
        deployment_digest=deployment_digest,
    )
    return RuntimeAssignment(
        runtime_protocol_version="mrw.runtime.protocol.v1",
        work_item_id="work:i1-c9-1-s2b:001",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key="i1-local-c9",
        run_id="run:i1-c9-1-s2b:001",
        step_id="step:c9-1:evidence-matrix",
        step_role=CompiledStepRole.EFFECT,
        capability_id="business_lines.evidence_matrix.v1",
        operation_contract_ref=OperationContractRef(
            kind="business_lines.evidence_matrix.v1",
            contract_version="1.0.0",
            contract_digest=operation_digest,
        ),
        operation_contract_digest=operation_digest,
        return_contract_binding=ReturnContractBinding.from_contract(
            "mrw.successor.runtime.c9-1.evidence-matrix-readback.v1",
            ReturnContract(
                success_modes=("SUCCEEDED",),
                failure_modes=("FAILED",),
                admission_required=False,
                wait_modes=(),
                cancel_modes=(),
            ),
        ),
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=(f"handler-binding:sha256:{exact_binding.binding_digest}"),
        handler_binding_digest=exact_binding.binding_digest,
        handler_binding=exact_binding,
        program_digest=exact_binding.binding_digest,
        deployment_catalog_digest=deployment_digest,
        execution_epoch=1,
        incarnation="inc:i1-c9-1-s2b:001",
        input_refs=(),
        queue_eligibility_digest="0" * 64,
        resource_policy_epoch=1,
        claim_authority_epoch=1,
        claim_policy_digest="0" * 64,
        expected_step_revision=0,
        trace_id="trace:i1-c9-1-s2b:001",
    )


def _claim(
    assignment: RuntimeAssignment,
    *,
    profile_digest: str = _PROFILE_DIGEST,
) -> ClaimBinding:
    return ClaimBinding.bind(
        assignment,
        authorization_digest="0" * 64,
        lease_token="lease:i1-c9-1-s2b",
        lease_expires_at=datetime(2026, 9, 2, 2, 0, tzinfo=UTC),
        node_id="node:i1-c9-1-s2b",
        node_profile_digest="0" * 64,
        authority_digest="0" * 64,
        interpreter_profile_digest=profile_digest,
    )


def _context() -> RuntimeExecutionContext:
    return RuntimeExecutionContext(
        node=NodeIdentity(
            node_id="node:i1-c9-1-s2b",
            incarnation="node-inc:i1-c9-1-s2b",
            started_at=datetime(2026, 9, 2, 1, 0, tzinfo=UTC),
        ),
        observed_at=datetime(2026, 9, 2, 1, 0, tzinfo=UTC),
    )


def test_s2b_c9_canonical_keys_status_and_terminal_mapping() -> None:
    assert tuple(item.value for item in EvidenceRowStatus) == (
        "passed",
        "failed",
        "blocked_by_environment",
    )
    assert BUSINESS_LINE_KEYS == (
        "ingest",
        "search_discovery_index",
        "resource_source_library",
        "projects_config_workflow",
        "dashboard_admin_governance",
        "writing_knowledge_graph_agent",
        "runtime_ops",
    )
    assert WORKER_REQUIRED_BUSINESS_LINE_KEYS == (
        "ingest",
        "search_discovery_index",
        "resource_source_library",
        "writing_knowledge_graph_agent",
    )
    worker_set = set(WORKER_REQUIRED_BUSINESS_LINE_KEYS)
    assert set(BUSINESS_LINE_KEYS) - worker_set == set(NON_WORKER_TERMINAL_STATUS)
    assert NON_WORKER_TERMINAL_STATUS == {
        "projects_config_workflow": "applied",
        "dashboard_admin_governance": "available",
        "runtime_ops": "healthy",
    }


def test_s2b_c9_matrix_uses_canonical_order_and_rejects_line_set_drift() -> None:
    matrix = project_business_line_evidence_matrix(_all_passed_records())

    assert matrix.source_status is EvidenceRowStatus.PASSED
    assert [row.line_key for row in matrix.rows] == list(BUSINESS_LINE_KEYS)
    assert matrix.summary.to_plain() == {
        "total": 7,
        "passed": 7,
        "blocked": 0,
        "failed": 0,
    }

    with pytest.raises(EvidenceMatrixLineSetError):
        project_business_line_evidence_matrix(_all_passed_records()[:-1])

    with pytest.raises(EvidenceMatrixLineSetError):
        project_business_line_evidence_matrix(
            _all_passed_records() + _all_passed_records()[:1]
        )

    with pytest.raises(EvidenceMatrixLineSetError):
        _record("unexpected_business_line")

    tampered_key = list(_all_passed_records())
    object.__setattr__(tampered_key[0], "line_key", "unexpected_business_line")
    with pytest.raises(EvidenceMatrixLineSetError):
        project_business_line_evidence_matrix(tuple(tampered_key))

    with pytest.raises(EvidenceMatrixSourceError):
        project_business_line_evidence_matrix([{"line_key": "ingest"}])


def test_s2b_c9_worker_requirement_mismatch_fails_closed() -> None:
    records = list(_all_passed_records())
    object.__setattr__(records[0], "requires_worker_readback", False)
    with pytest.raises(EvidenceMatrixLineSetError):
        project_business_line_evidence_matrix(tuple(records))


def test_s2b_c9_passed_requires_decidable_worker_readback() -> None:
    full_passed = project_business_line_evidence_matrix(_all_passed_records())
    assert full_passed.source_status is EvidenceRowStatus.PASSED
    assert all(row.status is EvidenceRowStatus.PASSED for row in full_passed.rows)

    blocked = [
        _record(line_key, decidable=line_key in WORKER_REQUIRED_BUSINESS_LINE_KEYS)
        for line_key in BUSINESS_LINE_KEYS
    ]
    blocked[0] = _record("ingest", decidable=False)
    matrix = project_business_line_evidence_matrix(tuple(blocked))

    assert matrix.source_status is EvidenceRowStatus.BLOCKED_BY_ENVIRONMENT
    ingest_row = matrix.rows[0]
    assert ingest_row.status is EvidenceRowStatus.BLOCKED_BY_ENVIRONMENT
    assert ingest_row.requires_worker_readback is True
    assert "not_decidable" in ingest_row.reason_code
    assert ingest_row.row_digest != _record("ingest").row_digest
    assert matrix.summary.blocked == 1
    assert matrix.summary.passed == 6


def test_s2b_c9_failed_priority_blocked_only_and_empty_source() -> None:
    blocked = [_record(line_key) for line_key in BUSINESS_LINE_KEYS]
    blocked[3] = _record(
        "projects_config_workflow",
        status=EvidenceRowStatus.BLOCKED_BY_ENVIRONMENT,
    )
    blocked_only = project_business_line_evidence_matrix(tuple(blocked))
    assert blocked_only.source_status is EvidenceRowStatus.BLOCKED_BY_ENVIRONMENT
    assert blocked_only.summary.blocked == 1

    with_failure = [_record(line_key) for line_key in BUSINESS_LINE_KEYS]
    with_failure[4] = _record(
        "dashboard_admin_governance",
        status=EvidenceRowStatus.FAILED,
    )
    with_failure[5] = _record("writing_knowledge_graph_agent", decidable=False)
    failed = project_business_line_evidence_matrix(tuple(with_failure))
    assert failed.source_status is EvidenceRowStatus.FAILED
    assert failed.summary.failed == 1
    assert failed.summary.blocked == 1

    empty_sources = tuple(
        _record(line_key, source=False) for line_key in BUSINESS_LINE_KEYS
    )
    no_source = project_business_line_evidence_matrix(empty_sources)
    assert no_source.source_status is EvidenceRowStatus.FAILED
    assert no_source.summary.failed == 7
    assert no_source.summary.passed == 0
    assert all(
        "missing_source_evidence" in row.reason_code
        for row in no_source.rows
        if row.status is EvidenceRowStatus.FAILED
    )


def test_s2b_c9_non_worker_lines_pass_without_worker_readback() -> None:
    worker_set = set(WORKER_REQUIRED_BUSINESS_LINE_KEYS)
    non_worker = tuple(key for key in BUSINESS_LINE_KEYS if key not in worker_set)
    assert non_worker == (
        "projects_config_workflow",
        "dashboard_admin_governance",
        "runtime_ops",
    )
    records = list(_all_passed_records())
    for key in non_worker:
        assert records[BUSINESS_LINE_KEYS.index(key)].requires_worker_readback is False

    matrix = project_business_line_evidence_matrix(tuple(records))
    assert matrix.source_status is EvidenceRowStatus.PASSED
    for key in non_worker:
        row = matrix.rows[BUSINESS_LINE_KEYS.index(key)]
        assert row.status is EvidenceRowStatus.PASSED
        assert row.source_refs[0].status == NON_WORKER_TERMINAL_STATUS[key]
        assert row.source_refs[0].source_kind == "endpoint_readback"


def test_s2b_c9_authority_all_false_and_completion_claim_false() -> None:
    matrix = project_business_line_evidence_matrix(_all_passed_records())
    authority = matrix.authority.to_plain()
    for name in (
        "live_provider",
        "canonical_write",
        "cutover",
        "external_delivery",
        "authority_transfer",
        "scheduler",
        "executor",
        "legacy_db_write",
        "candidate_created",
    ):
        assert authority[name] is False
        with pytest.raises(ValueError):
            EvidenceMatrixAuthority(**{name: True})
    assert matrix.completion_claim is False
    assert authority["schema_ref"] == (
        "mrw.successor.runtime.c9-1.evidence-matrix-authority.v1"
    )

    with pytest.raises(ValueError):
        replace(matrix, completion_claim=True)


def test_s2b_c9_route_handler_binding_drift_and_success() -> None:
    records = _all_passed_records()
    handler = _handler(records)
    assignment = _assignment()
    claim = _claim(assignment)

    outcome = handler.execute(assignment, claim, _context())
    assert handler.execute_calls == 1
    assert handler.last_matrix is not None
    assert handler.last_matrix.matrix_digest == outcome.result_digest
    assert outcome.receipt_ref == "receipt:evidence-matrix:c9-1"

    drifted_handler = _handler(records)
    drifted_assignment = _assignment(operation_digest=_OTHER_DIGEST)
    drifted_claim = _claim(drifted_assignment)
    with pytest.raises(DefiniteInterpreterFailure) as exc:
        drifted_handler.execute(drifted_assignment, drifted_claim, _context())
    assert exc.value.failure_code == ("EXACT_C9_EVIDENCE_MATRIX_HANDLER_BINDING_DRIFT")
    assert drifted_handler.execute_calls == 0

    claim_drift_handler = _handler(records)
    wrong_claim = _claim(_assignment(operation_digest=_OTHER_DIGEST))
    with pytest.raises(DefiniteInterpreterFailure) as exc:
        claim_drift_handler.execute(assignment, wrong_claim, _context())
    assert exc.value.failure_code == "CLAIM_ASSIGNMENT_BINDING_DRIFT"
    assert claim_drift_handler.execute_calls == 0

    deployment_handler = _handler(records)
    deployment_assignment = _assignment(deployment_digest=_OTHER_DIGEST)
    deployment_claim = _claim(deployment_assignment)
    with pytest.raises(DefiniteInterpreterFailure) as exc:
        deployment_handler.execute(
            deployment_assignment,
            deployment_claim,
            _context(),
        )
    assert exc.value.failure_code == ("EXACT_C9_EVIDENCE_MATRIX_HANDLER_BINDING_DRIFT")
    assert deployment_handler.execute_calls == 0


def test_s2b_c9_digests_reproducible_and_tamper_rejected() -> None:
    first = project_business_line_evidence_matrix(_all_passed_records())
    second = project_business_line_evidence_matrix(_all_passed_records())

    assert first.matrix_digest == second.matrix_digest
    assert len(first.matrix_digest) == 64
    assert all(char in "0123456789abcdef" for char in first.matrix_digest)
    assert [row.row_digest for row in first.rows] == [
        row.row_digest for row in second.rows
    ]

    replaced = _record("ingest", status=EvidenceRowStatus.FAILED)
    changed = project_business_line_evidence_matrix(
        (replaced,) + _all_passed_records()[1:]
    )
    assert changed.matrix_digest != first.matrix_digest
    assert changed.rows[0].row_digest != first.rows[0].row_digest

    tampered_row = _record("ingest")
    object.__setattr__(tampered_row, "status", EvidenceRowStatus.FAILED)
    with pytest.raises(EvidenceMatrixIntegrityError):
        project_business_line_evidence_matrix(
            (tampered_row,) + _all_passed_records()[1:]
        )

    object.__setattr__(second, "source_status", EvidenceRowStatus.FAILED)
    with pytest.raises(EvidenceMatrixIntegrityError):
        second.verify_digest()


def test_s2b_c9_readback_and_payload_are_pure_plain_projections() -> None:
    records = _all_passed_records()
    rows = project_evidence_matrix_readback(records)
    assert len(rows) == len(BUSINESS_LINE_KEYS)
    for row in rows:
        for key in (
            "line_key",
            "status",
            "reason_code",
            "row_digest",
            "persistence_decidable",
            "source_refs",
        ):
            assert key in row
        assert isinstance(row["source_refs"], list)
        assert all(isinstance(item, dict) for item in row["source_refs"])

    matrix = project_business_line_evidence_matrix(records)
    payload = project_evidence_matrix_payload(matrix)
    assert payload["schema"] == capability.EVIDENCE_MATRIX_SCHEMA
    assert payload["readback_schema"] == capability.EVIDENCE_MATRIX_READBACK_SCHEMA
    assert payload["authority_schema"] == capability.EVIDENCE_MATRIX_AUTHORITY_SCHEMA
    assert payload["source_status"] == "passed"
    assert payload["completion_claim"] is False
    assert set(payload["summary"]) == {"total", "passed", "blocked", "failed"}
    assert matrix.summary.to_dict() == matrix.summary.to_plain()

    capability_source = Path(capability.__file__).read_text(encoding="utf-8")
    projection_source = Path(projection.__file__).read_text(encoding="utf-8")
    combined = (capability_source + projection_source).lower()
    for effect_import in (
        "sqlalchemy",
        "import requests",
        "import celery",
        "import redis",
        "urllib.request",
        "psycopg",
    ):
        assert effect_import not in combined

    authority = EvidenceMatrixAuthority()
    summary = EvidenceMatrixSummary(total=1, passed=1, blocked=0, failed=0)
    assert summary.to_dict() == {"total": 1, "passed": 1, "blocked": 0, "failed": 0}
    assert isinstance(authority.to_plain(), dict)
    assert isinstance(EvidenceMatrixAuthority, type)
    assert isinstance(projection.C9EvidenceMatrixRouteHandler, type)
