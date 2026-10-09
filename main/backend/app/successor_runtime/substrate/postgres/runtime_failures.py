"""Exact project-scoped bodies for deterministic runtime failures.

The public runtime journal may retain only the returned ``failure_ref`` and
``failure_digest``.  The typed failure body itself is an immutable project
value written through the caller's transaction.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, NotRequired, TypeGuard, TypedDict

from functorial_kit import Failure
from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.successor_runtime.capabilities.checksum import CanonicalJsonObject, CanonicalJsonValue
from app.successor_runtime.research.codec import canonical_bytes, runtime_value, sha256_hex
from app.successor_runtime.runtime.assignments import (
    RuntimeAssignment,
    require_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.ports import RuntimeScope

from .research_ledger import ExactContentConflict, project_table
from .values import ValueRepository

FAILURE_SCHEMA = "mrw.runtime.failure.v1"
FAILURE_OBJECT_TYPE = "RuntimeFailure.v1"
DOMAIN_FAILURE_SCHEMA = "mrw.runtime.failure.v2"
DOMAIN_FAILURE_OBJECT_TYPE = "RuntimeFailure.v2"
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
    domain_failure: Failure | None = None


class DomainFailureBody(TypedDict):
    family: str
    code: str
    message: str
    context: CanonicalJsonObject | None


class RuntimeFailureBody(TypedDict):
    schema_version: str
    project_key: str
    project_registry_revision: int
    project_scope_incarnation: str
    project_scope_digest: str
    run_id: str
    step_id: str | None
    work_item_id: str
    assignment_kind: str
    assignment_digest: str
    handler_binding_digest: str
    execution_epoch: int
    assignment_incarnation: str
    attempt_id: str
    claim_binding_digest: str
    authority_digest: str
    claim_authority_epoch: int
    failure_code: str
    domain_failure: NotRequired[DomainFailureBody]


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _is_string_object_dict(
    value: object,
) -> TypeGuard[dict[str, object]]:
    if not _is_object_dict(value):
        return False
    return all(isinstance(key, str) for key in value)


def _checked_json(value: object) -> CanonicalJsonValue:
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if _is_object_list(value):
        return [_checked_json(item) for item in value]
    if _is_string_object_dict(value):
        return {key: _checked_json(item) for key, item in value.items()}
    raise TypeError("domain Failure context must use JSON-native values")


def _domain_failure_body(failure: Failure, failure_code: str) -> DomainFailureBody:
    if not isinstance(runtime_value(failure), Failure):
        raise TypeError("domain_failure must be Failure")
    if any(
        not isinstance(runtime_value(value), str)
        for value in (failure.family, failure.code, failure.message)
    ):
        raise TypeError("domain Failure family/code/message must be strings")
    if failure.code != failure_code or not failure.family:
        raise ValueError("domain Failure code/family differs from its failure declaration")
    context = _checked_json(runtime_value(failure.context))
    if context is not None and not isinstance(context, dict):
        raise TypeError("domain Failure context must be a JSON object or null")
    body: DomainFailureBody = {
        "family": failure.family, "code": failure.code, "message": failure.message, "context": context,
    }
    json.dumps(body, allow_nan=False)
    return body


def _require_failure_code(failure_code: str) -> str:
    if not isinstance(runtime_value(failure_code), str):
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
    if not isinstance(runtime_value(scope), RuntimeScope):
        raise TypeError("scope must be RuntimeScope")
    if not isinstance(runtime_value(assignment), RuntimeAssignment):
        raise TypeError("assignment must be RuntimeAssignment")
    if not isinstance(runtime_value(claim), ClaimBinding):
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
    domain_failure: Failure | None = None,
) -> RuntimeFailureBody:
    body: RuntimeFailureBody = {
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
    if domain_failure is not None:
        body["schema_version"] = DOMAIN_FAILURE_SCHEMA
        body["domain_failure"] = _domain_failure_body(domain_failure, failure_code)
    return body


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
        domain_failure: Failure | None = None,
    ) -> RuntimeFailureRecord:
        assignment, claim = _validate_exact_bindings(scope, assignment, claim)
        body = _failure_body(scope, assignment, claim, failure_code, domain_failure)
        exact = canonical_bytes(body)
        failure_digest = hashlib.sha256(exact).hexdigest()
        provenance = _failure_provenance(scope, assignment, claim)
        stored = ValueRepository(self.connection, self.tables).put_exact(
            scope,
            value_id=_failure_value_id(claim),
            object_type=FAILURE_OBJECT_TYPE if domain_failure is None else DOMAIN_FAILURE_OBJECT_TYPE,
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
            decoded = runtime_value(json.loads(exact.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeFailureBindingError(
                "runtime failure body is not canonical JSON"
            ) from exc
        if not _is_string_object_dict(decoded) or canonical_bytes(decoded) != exact:
            raise RuntimeFailureBindingError(
                "runtime failure body is not canonical JSON"
            )
        failure_code = decoded.get("failure_code")
        if not isinstance(failure_code, str):
            raise RuntimeFailureBindingError(
                "runtime failure body has no typed failure_code"
            )
        domain_failure = None
        if decoded.get("schema_version") == DOMAIN_FAILURE_SCHEMA:
            domain = decoded.get("domain_failure")
            if not _is_string_object_dict(domain) or set(domain) != {"family", "code", "message", "context"}:
                raise RuntimeFailureBindingError("runtime domain Failure body is malformed")
            family = domain["family"]
            code = domain["code"]
            message = domain["message"]
            context = _checked_json(domain["context"])
            if (
                not isinstance(family, str)
                or not isinstance(code, str)
                or not isinstance(message, str)
                or (context is not None and not isinstance(context, dict))
            ):
                raise RuntimeFailureBindingError("runtime domain Failure body is malformed")
            domain_failure = Failure(
                family=family,
                code=code,
                message=message,
                context=context,
            )
        try:
            expected = canonical_bytes(_failure_body(scope, assignment, claim, failure_code, domain_failure))
        except (TypeError, ValueError) as exc:
            raise RuntimeFailureBindingError("runtime domain Failure body is invalid") from exc
        if exact != expected or hashlib.sha256(exact).hexdigest() != failure_digest:
            raise RuntimeFailureBindingError(
                "runtime failure body differs from exact assignment/claim binding"
            )
        values = project_table(self.tables, "successor_values")
        identity = self.connection.execute(select(values).where(
            values.c.project_key == scope.project_scope.project_key,
            values.c.value_id == _failure_value_id(claim),
        )).mappings().one()
        if (identity["object_type"] != (FAILURE_OBJECT_TYPE if domain_failure is None else DOMAIN_FAILURE_OBJECT_TYPE)
                or identity["codec_id"] != FAILURE_CODEC_ID or identity["state"] != "FAILED"):
            raise RuntimeFailureBindingError("runtime failure value object identity drift")
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
            domain_failure=domain_failure,
        )


__all__ = [
    "FAILURE_CODEC_ID",
    "FAILURE_OBJECT_TYPE",
    "FAILURE_SCHEMA",
    "DOMAIN_FAILURE_SCHEMA",
    "DOMAIN_FAILURE_OBJECT_TYPE",
    "RuntimeFailureBindingError",
    "RuntimeFailureRecord",
    "RuntimeFailureRepository",
]
