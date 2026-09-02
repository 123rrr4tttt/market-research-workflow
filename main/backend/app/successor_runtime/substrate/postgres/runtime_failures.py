"""Exact project-scoped bodies for deterministic runtime failures.

The public runtime journal may retain only the returned ``failure_ref`` and
``failure_digest``.  The typed failure body itself is an immutable project
value written through the caller's transaction.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.engine import Connection

from app.successor_runtime.research.codec import canonical_bytes, sha256_hex
from app.successor_runtime.runtime.assignments import (
    RuntimeAssignment,
    require_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.ports import RuntimeScope

from .research_ledger import ExactContentConflict
from .values import ValueRepository

FAILURE_SCHEMA = "mrw.runtime.failure.v1"
FAILURE_OBJECT_TYPE = "RuntimeFailure.v1"
FAILURE_CODEC_ID = "mrw.canonical-json.v1"
FAILURE_PROVENANCE_SCHEMA = "mrw.runtime.failure-provenance.v1"
_FAILURE_REF_PREFIX = "project-value:runtime-failure:"


class RuntimeFailureBindingError(ExactContentConflict):
    """The stored failure is not the exact assignment/claim-bound record."""


@dataclass(frozen=True, slots=True)
class RuntimeFailureRecord:
    failure_ref: str
    failure_digest: str
    failure_code: str
    attempt_id: str
    assignment_digest: str
    claim_binding_digest: str
    value_revision: int
    value_incarnation: str
    byte_size: int


def _require_failure_code(failure_code: str) -> str:
    if not isinstance(failure_code, str):
        raise TypeError("failure_code must be a typed string")
    if (
        not failure_code
        or failure_code != failure_code.strip()
        or len(failure_code) > 512
        or any(
            ord(character) < 0x20 or ord(character) == 0x7F
            for character in failure_code
        )
    ):
        raise ValueError(
            "failure_code must be a non-empty canonical string of at most 512 characters"
        )
    return failure_code


def _validate_exact_bindings(
    scope: RuntimeScope,
    assignment: RuntimeAssignment,
    claim: ClaimBinding,
) -> tuple[RuntimeAssignment, ClaimBinding]:
    if not isinstance(scope, RuntimeScope):
        raise TypeError("scope must be RuntimeScope")
    if not isinstance(assignment, RuntimeAssignment):
        raise TypeError("assignment must be RuntimeAssignment")
    if not isinstance(claim, ClaimBinding):
        raise TypeError("claim must be ClaimBinding")

    # Re-validation closes model_copy/model_construct bypasses before any
    # project write.  It also rechecks the handler and assignment root union.
    exact_assignment = RuntimeAssignment.model_validate(
        assignment.model_dump(mode="json", exclude_none=False)
    )
    exact_claim = ClaimBinding.model_validate(
        claim.model_dump(mode="json", exclude_none=False)
    )
    exact_claim.validate_against(exact_assignment)
    if scope.project_scope.project_key != exact_assignment.project_key:
        raise RuntimeFailureBindingError(
            "runtime failure scope differs from exact assignment project"
        )
    return exact_assignment, exact_claim


def _failure_value_id(claim: ClaimBinding) -> str:
    return f"runtime-failure:{claim.attempt_id}"


def _failure_ref(claim: ClaimBinding) -> str:
    return f"{_FAILURE_REF_PREFIX}{claim.attempt_id}"


def _failure_incarnation(
    scope: RuntimeScope,
    assignment: RuntimeAssignment,
    claim: ClaimBinding,
) -> str:
    digest = sha256_hex(
        {
            "contract": "RuntimeFailureIncarnation.v1",
            "project_scope_digest": scope.project_scope.scope_digest,
            "project_scope_incarnation": scope.project_scope.incarnation,
            "assignment_digest": assignment.assignment_digest,
            "assignment_incarnation": assignment.incarnation,
            "attempt_id": claim.attempt_id,
            "claim_binding_digest": claim.binding_digest,
        }
    )
    return f"runtime-failure:{digest}"


def _failure_body(
    scope: RuntimeScope,
    assignment: RuntimeAssignment,
    claim: ClaimBinding,
    failure_code: str,
) -> dict[str, Any]:
    return {
        "schema_version": FAILURE_SCHEMA,
        "project_key": scope.project_scope.project_key,
        "project_registry_revision": scope.project_scope.project_registry_revision,
        "project_scope_incarnation": scope.project_scope.incarnation,
        "project_scope_digest": scope.project_scope.scope_digest,
        "run_id": assignment.run_id,
        "step_id": assignment.step_id,
        "work_item_id": assignment.work_item_id,
        "assignment_kind": assignment.assignment_kind.value,
        "assignment_digest": assignment.assignment_digest,
        "handler_binding_digest": assignment.handler_binding_digest,
        "execution_epoch": assignment.execution_epoch,
        "assignment_incarnation": assignment.incarnation,
        "attempt_id": claim.attempt_id,
        "claim_binding_digest": claim.binding_digest,
        "authority_digest": claim.authority_digest,
        "claim_authority_epoch": claim.claim_authority_epoch,
        "failure_code": _require_failure_code(failure_code),
    }


def _failure_provenance(
    scope: RuntimeScope,
    assignment: RuntimeAssignment,
    claim: ClaimBinding,
) -> dict[str, Any]:
    return {
        "schema_version": FAILURE_PROVENANCE_SCHEMA,
        "project_scope_digest": scope.project_scope.scope_digest,
        "assignment_digest": assignment.assignment_digest,
        "handler_binding_digest": assignment.handler_binding_digest,
        "attempt_id": claim.attempt_id,
        "claim_binding_digest": claim.binding_digest,
    }


class RuntimeFailureRepository:
    """Absent-or-exact failure body store enlisted in a caller-owned UoW."""

    def __init__(self, connection: Connection, tables: Any) -> None:
        self.connection = connection
        self.tables = tables

    def put_exact(
        self,
        scope: RuntimeScope,
        *,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        failure_code: str,
    ) -> RuntimeFailureRecord:
        assignment, claim = _validate_exact_bindings(scope, assignment, claim)
        body = _failure_body(scope, assignment, claim, failure_code)
        exact = canonical_bytes(body)
        failure_digest = hashlib.sha256(exact).hexdigest()
        provenance = _failure_provenance(scope, assignment, claim)
        stored = ValueRepository(self.connection, self.tables).put_exact(
            scope,
            value_id=_failure_value_id(claim),
            object_type=FAILURE_OBJECT_TYPE,
            codec_id=FAILURE_CODEC_ID,
            content=exact,
            expected_digest=failure_digest,
            provenance_digest=sha256_hex(provenance),
            expected_revision=0,
            expected_incarnation=_failure_incarnation(scope, assignment, claim),
            source_ref=f"runtime-attempt:{claim.attempt_id}",
            provenance=provenance,
            state="FAILED",
        )
        if stored.revision != 1:
            raise RuntimeFailureBindingError(
                "immutable runtime failure has a non-creation revision"
            )
        return self.verify_exact(
            scope,
            assignment=assignment,
            claim=claim,
            failure_ref=_failure_ref(claim),
            failure_digest=failure_digest,
        )

    def verify_exact(
        self,
        scope: RuntimeScope,
        *,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        failure_ref: str,
        failure_digest: str,
    ) -> RuntimeFailureRecord:
        assignment, claim = _validate_exact_bindings(scope, assignment, claim)
        require_digest(failure_digest, "failure_digest")
        expected_ref = _failure_ref(claim)
        if failure_ref != expected_ref:
            raise RuntimeFailureBindingError(
                "failure_ref does not bind the exact runtime attempt"
            )
        incarnation = _failure_incarnation(scope, assignment, claim)
        exact = ValueRepository(self.connection, self.tables).get_exact(
            scope,
            _failure_value_id(claim),
            expected_revision=1,
            expected_incarnation=incarnation,
            expected_digest=failure_digest,
        )
        try:
            decoded = json.loads(exact.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeFailureBindingError(
                "runtime failure body is not canonical JSON"
            ) from exc
        if not isinstance(decoded, dict) or canonical_bytes(decoded) != exact:
            raise RuntimeFailureBindingError(
                "runtime failure body is not canonical JSON"
            )
        failure_code = decoded.get("failure_code")
        if not isinstance(failure_code, str):
            raise RuntimeFailureBindingError(
                "runtime failure body has no typed failure_code"
            )
        expected = canonical_bytes(
            _failure_body(scope, assignment, claim, failure_code)
        )
        if exact != expected or hashlib.sha256(exact).hexdigest() != failure_digest:
            raise RuntimeFailureBindingError(
                "runtime failure body differs from exact assignment/claim binding"
            )
        return RuntimeFailureRecord(
            failure_ref=expected_ref,
            failure_digest=failure_digest,
            failure_code=failure_code,
            attempt_id=claim.attempt_id,
            assignment_digest=assignment.assignment_digest,
            claim_binding_digest=claim.binding_digest,
            value_revision=1,
            value_incarnation=incarnation,
            byte_size=len(exact),
        )


__all__ = [
    "FAILURE_CODEC_ID",
    "FAILURE_OBJECT_TYPE",
    "FAILURE_SCHEMA",
    "RuntimeFailureBindingError",
    "RuntimeFailureRecord",
    "RuntimeFailureRepository",
]
