"""Successor-native pure interpreters for the C4 agent-batch atoms.

The interpreters are deterministic rewrites of the legacy agent-batch plan and
retry helpers.  They perform no network, database, provider, submit or
credential work and never import legacy service packages.  The legacy path is
exercised only by the sibling ``successor_migration.legacy_agent_batch``
adapter.  All typed outputs come from the single canonical DTO vocabulary in
``agent_batch_c4.py``.

The C4.3 submit atom is not interpreted here: durable submission remains
contract/repository scaffold only and is explicitly blocked by the shared
idempotency enum mismatch.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import (
    Any,
    Generic,
    Literal,
    Protocol,
    TypeAlias,
    TypeVar,
    runtime_checkable,
)

from app.successor_runtime.capabilities import agent_batch_c4 as c4
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    sha256_hex,
)
from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot
from app.successor_runtime.language.object_contracts import OperationContractRef
from app.successor_runtime.language.plan import with_plan_digest
from app.successor_runtime.research.codec import is_sha256_hex

__all__ = [
    "AGENT_BATCH_C4_LEGACY_PLAN_INTERPRETER_ID",
    "AGENT_BATCH_C4_LEGACY_RETRY_INTERPRETER_ID",
    "AGENT_BATCH_C4_SUCCESSOR_PLAN_INTERPRETER_ID",
    "AGENT_BATCH_C4_SUCCESSOR_RETRY_INTERPRETER_ID",
    "AgentBatchC4PlanSuccessorInterpreter",
    "AgentBatchC4RetrySuccessorInterpreter",
    "AgentBatchC4SubmissionSuccessorInterpreter",
    "BatchPlanBindingMismatch",
    "InterpreterFailure",
    "InterpreterOutcome",
    "InterpreterSuccess",
    "PayloadView",
    "ProjectScopeView",
    "RetryBindingMismatch",
    "authority_requirement_digest",
    "legacy_plan_interpreter_profile_digest",
    "legacy_retry_interpreter_profile_digest",
    "require_exact_batch_plan_binding",
    "require_exact_retry_binding",
    "successor_plan_interpreter_profile_digest",
    "successor_retry_interpreter_profile_digest",
    "successor_submission_interpreter_profile_digest",
]


AGENT_BATCH_C4_SUCCESSOR_PLAN_INTERPRETER_ID = (
    "successor.agent_batch.batch_plan.pure.v1"
)
AGENT_BATCH_C4_LEGACY_PLAN_INTERPRETER_ID = "legacy.agent_batch.nl_command.plan.v1"
AGENT_BATCH_C4_SUCCESSOR_RETRY_INTERPRETER_ID = (
    "successor.agent_batch.retry_action.reducer.v1"
)
AGENT_BATCH_C4_SUCCESSOR_SUBMISSION_INTERPRETER_ID = (
    "successor.agent_batch.submission.typed.v1"
)
AGENT_BATCH_C4_LEGACY_RETRY_INTERPRETER_ID = "legacy.agent_batch.retry_loop.v1"

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class InterpreterSuccess(Generic[T]):
    value: T
    disposition: Literal["SUCCEEDED"] = "SUCCEEDED"


@dataclass(frozen=True, slots=True)
class InterpreterFailure:
    code: str
    message: str
    retryable: bool = False
    disposition: Literal["FAILED"] = "FAILED"


InterpreterOutcome: TypeAlias = InterpreterSuccess[T] | InterpreterFailure


@runtime_checkable
class ProjectScopeView(Protocol):
    project_key: str
    registry_revision: int
    incarnation: str
    scope_digest: str


@runtime_checkable
class PayloadView(Protocol):
    schema_version: str
    operation_kind: str
    project_key: str
    registry_revision: int
    resolved_schema: str
    scope_incarnation: str
    scope_digest: str
    payload_digest: str


class BatchPlanBindingMismatch(ValueError):
    """Raised when the C4.1 Program/Plan/payload/catalog/binding drifts."""


class RetryBindingMismatch(ValueError):
    """Raised when the C4.2 Program/Plan/payload/catalog/binding drifts."""


def _is_hex64(value: Any) -> bool:
    return isinstance(value, str) and is_sha256_hex(value)


def _require_exact_binding(
    *,
    kind: str,
    operation_id: str,
    payload_type_id: str,
    result_type_id: str,
    mismatch_type: type[ValueError],
    program: Any,
    plan: Any,
    contract_ref: OperationContractRef,
    payload_ref: Any,
    payload: PayloadView,
    project_scope: ProjectScopeView,
    catalog: OperationContractCatalogSnapshot,
    deployment_catalog_digest: str,
    binding: Any,
    expected_interpreter_profile_digest: str | None,
) -> dict[str, str]:
    """Fail closed unless the complete C4 Program/Plan closure is exact."""

    failures: list[str] = []
    if payload.operation_kind != kind:
        failures.append("payload operation_kind")
    if program.project_key != project_scope.project_key:
        failures.append("program/project key")
    if program.project_registry_revision != project_scope.registry_revision:
        failures.append("program/registry revision")
    if program.project_scope_digest != project_scope.scope_digest:
        failures.append("program/scope digest")
    if payload.project_key != project_scope.project_key:
        failures.append("payload/scope project key")
    if payload.registry_revision != project_scope.registry_revision:
        failures.append("payload/scope registry revision")
    if payload.scope_digest != project_scope.scope_digest:
        failures.append("payload/scope digest")

    program_metadata = dict(program.metadata)
    if program_metadata.get("resolved_schema") != project_scope.resolved_schema:
        failures.append("program metadata/resolved schema")
    if program_metadata.get("project_scope_incarnation") != project_scope.incarnation:
        failures.append("program metadata/scope incarnation")
    if program_metadata.get("payload_content_digest") != payload_ref.content_digest:
        failures.append("program metadata/payload content digest")
    if program.program_digest != program.digest():
        failures.append("program digest")
    if plan.program_id != program.program_id:
        failures.append("plan/program id")
    if plan.program_digest != program.program_digest:
        failures.append("plan/program digest")
    if not _is_hex64(plan.plan_digest):
        failures.append("plan digest")
    if with_plan_digest(plan).plan_digest != plan.plan_digest:
        failures.append("plan digest forged")
    if getattr(plan.input_type, "type_id", None) != payload_type_id:
        failures.append("plan input type")
    if getattr(plan.output_type, "type_id", None) != result_type_id:
        failures.append("plan output type")

    effect_steps = tuple(
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    )
    if len(effect_steps) != 1:
        failures.append("plan effect steps")
    else:
        step_ref = effect_steps[0].operation_contract_ref
        if (
            step_ref.kind != contract_ref.kind
            or step_ref.contract_version != contract_ref.contract_version
            or step_ref.contract_digest != contract_ref.contract_digest
        ):
            failures.append("plan/contract ref")
    if any(step.step_kind == "ADMISSION" for step in plan.ordered_steps):
        failures.append("plan admission step")

    if contract_ref.kind != kind:
        failures.append("contract kind")
    if not _is_hex64(contract_ref.contract_digest):
        failures.append("contract digest")
    catalog_ref = catalog.lookup(contract_ref)
    if (
        catalog_ref is None
        or catalog_ref.contract_digest != contract_ref.contract_digest
    ):
        failures.append("catalog/contract ref")

    plain = dataclasses.asdict(payload)
    expected_content_digest = sha256_hex(canonical_json(plain).encode("utf-8"))
    if payload_ref.content_digest != expected_content_digest:
        failures.append("payload ref content digest")
    if payload_ref.project_key != project_scope.project_key:
        failures.append("payload ref project key")
    if getattr(payload_ref.object_type, "type_id", None) != payload_type_id:
        failures.append("payload ref object type")
    if not _is_hex64(payload_ref.provenance_digest):
        failures.append("payload ref provenance digest")

    if not _is_hex64(binding.binding_digest):
        failures.append("binding digest")
    if (
        getattr(binding, "operation_contract_digest", None)
        != contract_ref.contract_digest
    ):
        failures.append("binding/contract digest")
    if getattr(binding, "project_scope_digest", None) != project_scope.scope_digest:
        failures.append("binding/scope digest")
    if not _is_hex64(deployment_catalog_digest):
        failures.append("deployment catalog digest")
    if getattr(binding, "deployment_catalog_digest", None) != deployment_catalog_digest:
        failures.append("binding/deployment catalog digest")
    if (
        expected_interpreter_profile_digest is not None
        and getattr(binding, "interpreter_profile_digest", None)
        != expected_interpreter_profile_digest
    ):
        failures.append("binding/interpreter profile")

    if failures:
        raise mismatch_type(
            f"{kind} binding drift: " + ", ".join(sorted(set(failures)))
        )
    return {
        "program_digest": program.program_digest,
        "plan_digest": plan.plan_digest,
        "contract_digest": contract_ref.contract_digest,
        "payload_content_digest": payload_ref.content_digest,
        "binding_digest": binding.binding_digest,
    }


def require_exact_batch_plan_binding(
    *,
    program: Any,
    plan: Any,
    contract_ref: OperationContractRef,
    payload_ref: Any,
    payload: PayloadView,
    project_scope: ProjectScopeView,
    catalog: OperationContractCatalogSnapshot,
    deployment_catalog_digest: str,
    binding: Any,
    expected_interpreter_profile_digest: str | None = None,
) -> dict[str, str]:
    return _require_exact_binding(
        kind=c4.BATCH_PLAN_KIND,
        operation_id=c4.BATCH_PLAN_OPERATION_ID,
        payload_type_id=c4.BATCH_PLAN_PAYLOAD_TYPE.type_id,
        result_type_id=c4.BATCH_PLAN_RESULT_TYPE.type_id,
        mismatch_type=BatchPlanBindingMismatch,
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=project_scope,
        catalog=catalog,
        deployment_catalog_digest=deployment_catalog_digest,
        binding=binding,
        expected_interpreter_profile_digest=expected_interpreter_profile_digest,
    )


def require_exact_retry_binding(
    *,
    program: Any,
    plan: Any,
    contract_ref: OperationContractRef,
    payload_ref: Any,
    payload: PayloadView,
    project_scope: ProjectScopeView,
    catalog: OperationContractCatalogSnapshot,
    deployment_catalog_digest: str,
    binding: Any,
    expected_interpreter_profile_digest: str | None = None,
) -> dict[str, str]:
    return _require_exact_binding(
        kind=c4.RETRY_REDUCE_KIND,
        operation_id=c4.RETRY_REDUCE_OPERATION_ID,
        payload_type_id=c4.RETRY_REDUCER_PAYLOAD_TYPE.type_id,
        result_type_id=c4.RETRY_TRANSITION_TYPE.type_id,
        mismatch_type=RetryBindingMismatch,
        program=program,
        plan=plan,
        contract_ref=contract_ref,
        payload_ref=payload_ref,
        payload=payload,
        project_scope=project_scope,
        catalog=catalog,
        deployment_catalog_digest=deployment_catalog_digest,
        binding=binding,
        expected_interpreter_profile_digest=expected_interpreter_profile_digest,
    )


def authority_requirement_digest() -> str:
    return content_digest(
        {
            "schema": "mrw.successor.agent-batch.c4.authority.v1",
            "canonical_owner": c4.AGENT_BATCH_C4_OWNER,
            "authority": "read-only batch plan and retry reduction",
            "grant_scope": "project",
        }
    )


def successor_plan_interpreter_profile_digest() -> str:
    return content_digest(
        {
            "interpreter_id": AGENT_BATCH_C4_SUCCESSOR_PLAN_INTERPRETER_ID,
            "version": "1.0.0",
            "boundary": "successor-native pure C4.1 ordered batch plan",
        }
    )


def legacy_plan_interpreter_profile_digest() -> str:
    return content_digest(
        {
            "interpreter_id": AGENT_BATCH_C4_LEGACY_PLAN_INTERPRETER_ID,
            "version": "1.0.0",
            "donor": "agent_loop.run_agent_batch_nl_command_loop plan slice",
        }
    )


def successor_retry_interpreter_profile_digest() -> str:
    return content_digest(
        {
            "interpreter_id": AGENT_BATCH_C4_SUCCESSOR_RETRY_INTERPRETER_ID,
            "version": "1.0.0",
            "boundary": "successor-native pure C4.2 retry reducer",
        }
    )


def legacy_retry_interpreter_profile_digest() -> str:
    return content_digest(
        {
            "interpreter_id": AGENT_BATCH_C4_LEGACY_RETRY_INTERPRETER_ID,
            "version": "1.0.0",
            "donor": "agent_loop._build_search_retry_state reducer slice",
        }
    )


class AgentBatchC4PlanSuccessorInterpreter:
    """Bound successor interpreter for the C4.1 ordered batch plan atom."""

    interpreter_id = AGENT_BATCH_C4_SUCCESSOR_PLAN_INTERPRETER_ID

    def interpret(
        self,
        *,
        program: Any,
        plan: Any,
        contract_ref: OperationContractRef,
        payload_ref: Any,
        payload: c4.BatchPlanPayload,
        project_scope: ProjectScopeView,
        catalog: OperationContractCatalogSnapshot,
        deployment_catalog_digest: str,
        binding: Any,
    ) -> InterpreterOutcome[c4.BatchPlanResult]:
        try:
            require_exact_batch_plan_binding(
                program=program,
                plan=plan,
                contract_ref=contract_ref,
                payload_ref=payload_ref,
                payload=payload,
                project_scope=project_scope,
                catalog=catalog,
                deployment_catalog_digest=deployment_catalog_digest,
                binding=binding,
                expected_interpreter_profile_digest=(
                    successor_plan_interpreter_profile_digest()
                ),
            )
        except BatchPlanBindingMismatch as exc:
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message=str(exc),
                retryable=False,
            )
        try:
            return InterpreterSuccess(c4.build_batch_plan(payload))
        except ValueError as exc:
            return InterpreterFailure(
                code="INVALID_PLAN",
                message=str(exc),
                retryable=False,
            )


class AgentBatchC4RetrySuccessorInterpreter:
    """Bound successor interpreter for the C4.2 retry reducer atom."""

    interpreter_id = AGENT_BATCH_C4_SUCCESSOR_RETRY_INTERPRETER_ID

    def interpret(
        self,
        *,
        program: Any,
        plan: Any,
        contract_ref: OperationContractRef,
        payload_ref: Any,
        payload: c4.RetryReducerInput,
        project_scope: ProjectScopeView,
        catalog: OperationContractCatalogSnapshot,
        deployment_catalog_digest: str,
        binding: Any,
    ) -> InterpreterOutcome[c4.RetryTransition]:
        try:
            require_exact_retry_binding(
                program=program,
                plan=plan,
                contract_ref=contract_ref,
                payload_ref=payload_ref,
                payload=payload,
                project_scope=project_scope,
                catalog=catalog,
                deployment_catalog_digest=deployment_catalog_digest,
                binding=binding,
                expected_interpreter_profile_digest=(
                    successor_retry_interpreter_profile_digest()
                ),
            )
        except RetryBindingMismatch as exc:
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message=str(exc),
                retryable=False,
            )
        try:
            return InterpreterSuccess(c4.reduce_retry_action(payload))
        except ValueError as exc:
            return InterpreterFailure(
                code="RETRY_ACTION_INVALID",
                message=str(exc),
                retryable=False,
            )


def successor_submission_interpreter_profile_digest() -> str:
    return content_digest(
        {
            "interpreter_id": AGENT_BATCH_C4_SUCCESSOR_SUBMISSION_INTERPRETER_ID,
            "version": "1.0.0",
            "boundary": "successor-native typed C4.3 submission receipt derivation",
        }
    )


class AgentBatchC4SubmissionSuccessorInterpreter:
    """Bound successor interpreter for the C4.3 submission atom.

    The interpreter validates the exact Program/Plan/payload closure and
    derives a typed submission receipt.  Acceptance state lives in the typed
    receipt (and is persisted by the store-rehydrated handler as a project
    value), never in the generic DB idempotency enum.
    """

    interpreter_id = AGENT_BATCH_C4_SUCCESSOR_SUBMISSION_INTERPRETER_ID

    def interpret(
        self,
        *,
        program: Any,
        plan: Any,
        contract_ref: OperationContractRef,
        payload_ref: Any,
        payload: c4.AgentBatchSubmission,
        project_scope: ProjectScopeView,
        catalog: OperationContractCatalogSnapshot,
        deployment_catalog_digest: str,
        binding: Any,
        run_ref: str = "run:p3-c4-submission",
        created_at: str = "2030-09-01T08:00:00Z",
    ) -> InterpreterOutcome[c4.AgentBatchSubmissionReceipt]:
        try:
            _require_exact_binding(
                kind=c4.SUBMISSION_KIND,
                operation_id=c4.SUBMISSION_OPERATION_ID,
                payload_type_id=c4.SUBMISSION_TYPE.type_id,
                result_type_id=c4.SUBMISSION_RECEIPT_TYPE.type_id,
                mismatch_type=BatchPlanBindingMismatch,
                program=program,
                plan=plan,
                contract_ref=contract_ref,
                payload_ref=payload_ref,
                payload=payload,
                project_scope=project_scope,
                catalog=catalog,
                deployment_catalog_digest=deployment_catalog_digest,
                binding=binding,
                expected_interpreter_profile_digest=(
                    successor_submission_interpreter_profile_digest()
                ),
            )
        except BatchPlanBindingMismatch as exc:
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message=str(exc),
                retryable=False,
            )
        accepted = tuple(
            job.job_id
            for job in payload.jobs
            if job.channel in {"search.market", "source_library"}
        )
        rejected = tuple(
            (job.job_id, "unsupported_channel")
            for job in payload.jobs
            if job.channel not in {"search.market", "source_library"}
        )
        if not accepted:
            return InterpreterFailure(
                code="SUBMISSION_REJECTED",
                message="no accepted submission items",
                retryable=False,
            )
        receipt = c4.AgentBatchSubmissionReceipt(
            submission_id=payload.submission_id,
            job_id=",".join(accepted),
            accepted_items=accepted,
            rejected_items=rejected,
            run_ref=run_ref,
            state="PARTIALLY_ACCEPTED" if rejected else "ACCEPTED",
            created_at=created_at,
        )
        return InterpreterSuccess(receipt)
