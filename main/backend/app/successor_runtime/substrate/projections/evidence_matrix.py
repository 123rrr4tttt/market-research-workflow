"""Read-only C9.1 evidence-matrix readback projection and route handler.

The projection consumes the pure C9.1 capability records and emits plain
readback rows plus a JSON-ready matrix payload.  It performs no database,
scheduler, executor, provider, credential or canonical-write effect.  The
route handler is an exact binding guard in front of the same pure projection;
its ``execute`` only counts a successful projection and never mutates any
store.
"""

from __future__ import annotations

from typing import Any

from app.successor_runtime.capabilities.c9_evidence_matrix import (
    EVIDENCE_MATRIX_READBACK_SCHEMA,
    EVIDENCE_MATRIX_SCHEMA,
    BusinessLineEvidenceMatrix,
    BusinessLineEvidenceRecord,
    project_business_line_evidence_matrix,
)
from app.successor_runtime.runtime.assignments import RuntimeAssignment, require_digest
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    InterpreterOutcome,
    RuntimeExecutionContext,
    RuntimeHandler,
)

__all__ = [
    "C9EvidenceMatrixRouteHandler",
    "EvidenceMatrixProjectionError",
    "project_evidence_matrix_payload",
    "project_evidence_matrix_readback",
]


class EvidenceMatrixProjectionError(ValueError):
    """C9.1 evidence-matrix rows cannot form a trustworthy projection."""


def project_evidence_matrix_readback(
    records: Any,
) -> tuple[dict[str, Any], ...]:
    """Project typed records into plain readback rows without any store call."""

    matrix = project_business_line_evidence_matrix(records)
    return tuple(row.to_plain() for row in matrix.rows)


def project_evidence_matrix_payload(
    matrix: BusinessLineEvidenceMatrix,
) -> dict[str, Any]:
    """Render one immutable matrix as a JSON-ready readback payload."""

    if not isinstance(matrix, BusinessLineEvidenceMatrix):
        raise EvidenceMatrixProjectionError(
            "C9.1 evidence-matrix payload requires a typed matrix"
        )
    matrix.verify_digest()
    return {
        "schema": EVIDENCE_MATRIX_SCHEMA,
        "readback_schema": EVIDENCE_MATRIX_READBACK_SCHEMA,
        "authority_schema": matrix.authority.schema_ref,
        **matrix.to_plain(),
    }


def _require_exact_route_binding(
    *,
    assignment: RuntimeAssignment,
    claim: ClaimBinding,
    handler_binding_digest: str,
    interpreter_profile_digest: str,
    operation_contract_digest: str,
    deployment_catalog_digest: str,
) -> None:
    if claim.assignment_digest != assignment.assignment_digest:
        raise DefiniteInterpreterFailure("CLAIM_ASSIGNMENT_BINDING_DRIFT")
    if claim.handler_binding_digest != assignment.handler_binding_digest:
        raise DefiniteInterpreterFailure("CLAIM_ASSIGNMENT_BINDING_DRIFT")
    if (
        assignment.handler_binding_digest != handler_binding_digest
        or assignment.operation_contract_digest != operation_contract_digest
        or assignment.deployment_catalog_digest != deployment_catalog_digest
        or getattr(assignment.handler_binding, "interpreter_profile_digest", None)
        != interpreter_profile_digest
    ):
        raise DefiniteInterpreterFailure(
            "EXACT_C9_EVIDENCE_MATRIX_HANDLER_BINDING_DRIFT"
        )


class C9EvidenceMatrixRouteHandler(RuntimeHandler):
    """Exact runtime route over the read-only C9.1 evidence matrix."""

    handler_binding_digest: str
    interpreter_profile_digest: str

    def __init__(
        self,
        *,
        records: tuple[BusinessLineEvidenceRecord, ...],
        handler_binding_digest: str,
        interpreter_profile_digest: str,
        operation_contract_digest: str,
        deployment_catalog_digest: str,
    ) -> None:
        require_digest(
            handler_binding_digest,
            "C9 evidence matrix handler binding digest",
        )
        require_digest(
            interpreter_profile_digest,
            "C9 evidence matrix interpreter profile digest",
        )
        require_digest(
            operation_contract_digest,
            "C9 evidence matrix operation contract digest",
        )
        require_digest(
            deployment_catalog_digest,
            "C9 evidence matrix deployment catalog digest",
        )
        typed_records = tuple(records)
        if any(
            not isinstance(record, BusinessLineEvidenceRecord)
            for record in typed_records
        ):
            raise TypeError("C9 evidence matrix records must be typed")
        self.records = typed_records
        self.handler_binding_digest = handler_binding_digest
        self.interpreter_profile_digest = interpreter_profile_digest
        self.operation_contract_digest = operation_contract_digest
        self.deployment_catalog_digest = deployment_catalog_digest
        self.execute_calls = 0
        self.last_matrix: BusinessLineEvidenceMatrix | None = None

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        del context  # projection is deterministic and effect-free
        _require_exact_route_binding(
            assignment=assignment,
            claim=claim,
            handler_binding_digest=self.handler_binding_digest,
            interpreter_profile_digest=self.interpreter_profile_digest,
            operation_contract_digest=self.operation_contract_digest,
            deployment_catalog_digest=self.deployment_catalog_digest,
        )
        matrix = project_business_line_evidence_matrix(self.records)
        self.last_matrix = matrix
        self.execute_calls += 1
        return InterpreterOutcome.succeeded(
            matrix.matrix_digest,
            receipt_ref="receipt:evidence-matrix:c9-1",
        )
