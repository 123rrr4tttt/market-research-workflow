"""Successor-native pure interpreters for the C4 agent-batch atoms.

The interpreters are deterministic implementations of the current batch plan
and retry contracts.  They perform no network, database, provider, submit or
credential work and never import legacy service packages.  All typed outputs
come from the single canonical DTO vocabulary in ``agent_batch_c4.py``.

The C4.3 submit atom is not interpreted here: durable submission remains
contract/repository scaffold only and is explicitly blocked by the shared
idempotency enum mismatch.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import (
    Annotated,
    Generic,
    Literal,
    Protocol,
    TypeAlias,
    TypeVar,
    runtime_checkable,
)

from functorial_kit import Failure

from app.successor_runtime.capabilities import batch_task as batch_task
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    sha256_hex,
)
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot
from app.successor_runtime.language.object_contracts import OperationContractRef
from app.successor_runtime.language.plan import ExecutionPlan, with_plan_digest
from app.successor_runtime.language.program import ProgramSpec
from app.successor_runtime.research.codec import is_sha256_hex
__all__ = [
    "BATCH_TASK_SUCCESSOR_PLAN_INTERPRETER_ID",
    "BATCH_TASK_SUCCESSOR_RETRY_INTERPRETER_ID",
    "BatchTaskPlanSuccessorInterpreter",
    "BatchTaskRetrySuccessorInterpreter",
    "BatchTaskSubmissionSuccessorInterpreter",
    "BatchTaskInterpreterBindingSpec",
    "InterpreterBindingView",
    "BatchPlanBindingMismatch",
    "InterpreterFailure",
    "InterpreterOutcome",
    "InterpreterSuccess",
    "PayloadView",
    "ProjectScopeView",
    "RetryBindingMismatch",
    "authority_requirement_digest",
    "build_successor_agent_batch_c4_plan_binding",
    "build_successor_agent_batch_c4_retry_binding",
    "build_successor_agent_batch_c4_submission_binding",
    "require_exact_batch_plan_binding",
    "require_exact_retry_binding",
    "successor_plan_interpreter_profile_digest",
    "successor_retry_interpreter_profile_digest",
    "successor_submission_interpreter_profile_digest",
    "validate_exact_batch_plan_binding",
    "validate_exact_retry_binding",
]


BATCH_TASK_SUCCESSOR_PLAN_INTERPRETER_ID = (
    "batch.task.build_plan.native.v2"
)
BATCH_TASK_SUCCESSOR_RETRY_INTERPRETER_ID = (
    "batch.task.reduce_retry.native.v2"
)
BATCH_TASK_SUCCESSOR_SUBMISSION_INTERPRETER_ID = (
    "batch.task.submit.native.v2"
)

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
class InterpreterBindingView(Protocol):
    @property
    def binding_digest(self) -> str: ...

    @property
    def operation_contract_digest(self) -> str: ...

    @property
    def interpreter_profile_digest(self) -> str: ...

    @property
    def deployment_catalog_digest(self) -> str: ...

    @property
    def project_scope_digest(self) -> str: ...


@dataclass(frozen=True, slots=True)
class BatchTaskInterpreterBindingSpec:
    """Capability-owned exact facts materialized by the runtime binding owner."""

    binding_kind: Literal["INTERPRETER"]
    operation_contract_digest: str
    interpreter_profile_digest: str
    deployment_catalog_digest: str
    runtime_protocol_version: str
    project_scope_digest: str
    resource_policy_epoch: int
    authority_requirement_digest: str
    binding_digest: str = ""

    def __post_init__(self) -> None:
        expected = content_digest(self, omit_fields=("binding_digest",))
        if self.binding_digest == "":
            object.__setattr__(self, "binding_digest", expected)
        elif self.binding_digest != expected:
            failure = batch_task.agent_batch_contract_failure(
                "program_binding_invalid",
                "BatchTaskInterpreterBindingSpec digest does not match content",
                site="BatchTaskInterpreterBindingSpec.__post_init__",
                public_exception="ValueError",
            )
            batch_task.raise_agent_batch_contract_failure(failure, ValueError)


@runtime_checkable
class ProjectScopeView(Protocol):
    @property
    def project_key(self) -> str: ...

    @property
    def registry_revision(self) -> int: ...

    @property
    def incarnation(self) -> str: ...

    @property
    def resolved_schema(self) -> str: ...

    @property
    def scope_digest(self) -> str: ...


PayloadView: TypeAlias = (
    batch_task.BatchPlanPayload
    | batch_task.RetryReducerInput
    | batch_task.AgentBatchSubmission
)


class BatchPlanBindingMismatch(ValueError):
    """Raised when the C4.1 Program/Plan/payload/catalog/binding drifts."""


class RetryBindingMismatch(ValueError):
    """Raised when the C4.2 Program/Plan/payload/catalog/binding drifts."""


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and is_sha256_hex(value)


def _validate_exact_binding(
    *,
    kind: str,
    operation_id: str,
    payload_type_id: str,
    result_type_id: str,
    mismatch_type: type[ValueError],
    program: ProgramSpec,
    plan: ExecutionPlan,
    contract_ref: OperationContractRef,
    payload_ref: ValueRef,
    payload: PayloadView,
    project_scope: ProjectScopeView,
    catalog: OperationContractCatalogSnapshot,
    deployment_catalog_digest: str,
    binding: InterpreterBindingView,
    expected_interpreter_profile_digest: str | None,
) -> dict[str, str] | Failure:
    """Return the exact C4 closure receipt or its canonical typed failure."""

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
            step_ref is None
            or step_ref.kind != contract_ref.kind
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
        public_message = f"{kind} binding drift: " + ", ".join(
            sorted(set(failures))
        )
        return batch_task.agent_batch_contract_failure(
            "program_binding_invalid",
            public_message,
            site="interpreter/exact_binding",
            public_exception=mismatch_type.__name__,
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
    program: ProgramSpec,
    plan: ExecutionPlan,
    contract_ref: OperationContractRef,
    payload_ref: ValueRef,
    payload: batch_task.BatchPlanPayload,
    project_scope: ProjectScopeView,
    catalog: OperationContractCatalogSnapshot,
    deployment_catalog_digest: str,
    binding: InterpreterBindingView,
    expected_interpreter_profile_digest: str | None = None,
) -> dict[str, str]:
    result = validate_exact_batch_plan_binding(
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
    if isinstance(result, Failure):
        batch_task.raise_agent_batch_contract_failure(result, BatchPlanBindingMismatch)
    return result


def validate_exact_batch_plan_binding(
    *,
    program: ProgramSpec,
    plan: ExecutionPlan,
    contract_ref: OperationContractRef,
    payload_ref: ValueRef,
    payload: batch_task.BatchPlanPayload,
    project_scope: ProjectScopeView,
    catalog: OperationContractCatalogSnapshot,
    deployment_catalog_digest: str,
    binding: InterpreterBindingView,
    expected_interpreter_profile_digest: str | None = None,
) -> dict[str, str] | Failure:
    return _validate_exact_binding(
        kind=batch_task.BATCH_PLAN_KIND,
        operation_id=batch_task.BATCH_PLAN_OPERATION_ID,
        payload_type_id=batch_task.BATCH_PLAN_PAYLOAD_TYPE.type_id,
        result_type_id=batch_task.BATCH_PLAN_RESULT_TYPE.type_id,
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
    program: ProgramSpec,
    plan: ExecutionPlan,
    contract_ref: OperationContractRef,
    payload_ref: ValueRef,
    payload: batch_task.RetryReducerInput,
    project_scope: ProjectScopeView,
    catalog: OperationContractCatalogSnapshot,
    deployment_catalog_digest: str,
    binding: InterpreterBindingView,
    expected_interpreter_profile_digest: str | None = None,
) -> dict[str, str]:
    result = validate_exact_retry_binding(
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
    if isinstance(result, Failure):
        batch_task.raise_agent_batch_contract_failure(result, RetryBindingMismatch)
    return result


def validate_exact_retry_binding(
    *,
    program: ProgramSpec,
    plan: ExecutionPlan,
    contract_ref: OperationContractRef,
    payload_ref: ValueRef,
    payload: batch_task.RetryReducerInput,
    project_scope: ProjectScopeView,
    catalog: OperationContractCatalogSnapshot,
    deployment_catalog_digest: str,
    binding: InterpreterBindingView,
    expected_interpreter_profile_digest: str | None = None,
) -> dict[str, str] | Failure:
    return _validate_exact_binding(
        kind=batch_task.RETRY_REDUCE_KIND,
        operation_id=batch_task.RETRY_REDUCE_OPERATION_ID,
        payload_type_id=batch_task.RETRY_REDUCER_PAYLOAD_TYPE.type_id,
        result_type_id=batch_task.RETRY_TRANSITION_TYPE.type_id,
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
            "schema": batch_task.BATCH_TASK_AUTHORITY_SCHEMA,
            "canonical_owner": batch_task.BATCH_TASK_OWNER,
            "authority": "read-only batch plan and retry reduction",
            "grant_scope": "project",
        }
    )


def successor_plan_interpreter_profile_digest() -> str:
    return content_digest(
        {
            "interpreter_id": BATCH_TASK_SUCCESSOR_PLAN_INTERPRETER_ID,
            "version": "1.0.0",
            "boundary": "batch task ordered plan",
        }
    )


def successor_retry_interpreter_profile_digest() -> str:
    return content_digest(
        {
            "interpreter_id": BATCH_TASK_SUCCESSOR_RETRY_INTERPRETER_ID,
            "version": "1.0.0",
            "boundary": "batch task ordered retry reducer",
        }
    )


def build_successor_agent_batch_c4_plan_binding(
    *,
    contract_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> Annotated[
    BatchTaskInterpreterBindingSpec,
    Literal[
        "kit:non-authoritative derived_as=view "
        "fact_source=contract_digest+deployment_catalog_digest+project_scope_digest"
        "+resource_policy_epoch+runtime_protocol_version"
        "+successor_plan_interpreter_profile_digest+authority_requirement_digest "
        "witness=test:test_native_plan_interpreter_binds_and_projects_exact_order"
    ],
]:
    return BatchTaskInterpreterBindingSpec(
        binding_kind="INTERPRETER",
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=successor_plan_interpreter_profile_digest(),
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=authority_requirement_digest(),
    )


def build_successor_agent_batch_c4_retry_binding(
    *,
    contract_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> Annotated[
    BatchTaskInterpreterBindingSpec,
    Literal[
        "kit:non-authoritative derived_as=view "
        "fact_source=contract_digest+deployment_catalog_digest+project_scope_digest"
        "+resource_policy_epoch+runtime_protocol_version"
        "+successor_retry_interpreter_profile_digest+authority_requirement_digest "
        "witness=test:test_native_retry_interpreter_binds_exact_attempt"
    ],
]:
    return BatchTaskInterpreterBindingSpec(
        binding_kind="INTERPRETER",
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=successor_retry_interpreter_profile_digest(),
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=authority_requirement_digest(),
    )


def build_successor_agent_batch_c4_submission_binding(
    *,
    contract_digest: str,
    deployment_catalog_digest: str,
    project_scope_digest: str,
    resource_policy_epoch: int = 1,
    runtime_protocol_version: str = "mrw.runtime.protocol.v1",
) -> Annotated[
    BatchTaskInterpreterBindingSpec,
    Literal[
        "kit:non-authoritative derived_as=view "
        "fact_source=contract_digest+deployment_catalog_digest+project_scope_digest"
        "+resource_policy_epoch+runtime_protocol_version"
        "+successor_submission_interpreter_profile_digest+authority_requirement_digest "
        "witness=test:test_submission_payload_codec_restores_nested_typed_jobs"
    ],
]:
    return BatchTaskInterpreterBindingSpec(
        binding_kind="INTERPRETER",
        operation_contract_digest=contract_digest,
        interpreter_profile_digest=successor_submission_interpreter_profile_digest(),
        deployment_catalog_digest=deployment_catalog_digest,
        runtime_protocol_version=runtime_protocol_version,
        project_scope_digest=project_scope_digest,
        resource_policy_epoch=resource_policy_epoch,
        authority_requirement_digest=authority_requirement_digest(),
    )


class BatchTaskPlanSuccessorInterpreter:
    """Bound successor interpreter for the C4.1 ordered batch plan atom."""

    interpreter_id = BATCH_TASK_SUCCESSOR_PLAN_INTERPRETER_ID

    def interpret(
        self,
        *,
        program: ProgramSpec,
        plan: ExecutionPlan,
        contract_ref: OperationContractRef,
        payload_ref: ValueRef,
        payload: batch_task.BatchPlanPayload,
        project_scope: ProjectScopeView,
        catalog: OperationContractCatalogSnapshot,
        deployment_catalog_digest: str,
        binding: InterpreterBindingView,
    ) -> InterpreterOutcome[batch_task.BatchPlanResult]:
        binding_result = validate_exact_batch_plan_binding(
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
        if isinstance(binding_result, Failure):
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message=str((binding_result.context or {})["public_message"]),
                retryable=False,
            )
        plan_result = batch_task.try_build_batch_plan(payload)
        if isinstance(plan_result, Failure):
            return InterpreterFailure(
                code="INVALID_PLAN",
                message=str((plan_result.context or {})["public_message"]),
                retryable=False,
            )
        return InterpreterSuccess(plan_result)


class BatchTaskRetrySuccessorInterpreter:
    """Bound successor interpreter for the C4.2 retry reducer atom."""

    interpreter_id = BATCH_TASK_SUCCESSOR_RETRY_INTERPRETER_ID

    def interpret(
        self,
        *,
        program: ProgramSpec,
        plan: ExecutionPlan,
        contract_ref: OperationContractRef,
        payload_ref: ValueRef,
        payload: batch_task.RetryReducerInput,
        project_scope: ProjectScopeView,
        catalog: OperationContractCatalogSnapshot,
        deployment_catalog_digest: str,
        binding: InterpreterBindingView,
    ) -> InterpreterOutcome[batch_task.RetryTransition]:
        binding_result = validate_exact_retry_binding(
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
        if isinstance(binding_result, Failure):
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message=str((binding_result.context or {})["public_message"]),
                retryable=False,
            )
        return InterpreterSuccess(batch_task.reduce_retry_action(payload))


def successor_submission_interpreter_profile_digest() -> str:
    return content_digest(
        {
            "interpreter_id": BATCH_TASK_SUCCESSOR_SUBMISSION_INTERPRETER_ID,
            "version": "1.0.0",
            "boundary": "batch task typed submission receipt derivation",
        }
    )


class BatchTaskSubmissionSuccessorInterpreter:
    """Bound successor interpreter for the C4.3 submission atom.

    The interpreter validates the exact Program/Plan/payload closure and
    derives a typed submission receipt.  Acceptance state lives in the typed
    receipt (and is persisted by the store-rehydrated handler as a project
    value), never in the generic DB idempotency enum.
    """

    interpreter_id = BATCH_TASK_SUCCESSOR_SUBMISSION_INTERPRETER_ID

    def interpret(
        self,
        *,
        program: ProgramSpec,
        plan: ExecutionPlan,
        contract_ref: OperationContractRef,
        payload_ref: ValueRef,
        payload: batch_task.AgentBatchSubmission,
        project_scope: ProjectScopeView,
        catalog: OperationContractCatalogSnapshot,
        deployment_catalog_digest: str,
        binding: InterpreterBindingView,
        run_ref: str = "run:batch-task-submission",
        created_at: str = "2030-09-01T08:00:00Z",
    ) -> InterpreterOutcome[batch_task.AgentBatchSubmissionReceipt]:
        binding_result = _validate_exact_binding(
            kind=batch_task.SUBMISSION_KIND,
            operation_id=batch_task.SUBMISSION_OPERATION_ID,
            payload_type_id=batch_task.SUBMISSION_TYPE.type_id,
            result_type_id=batch_task.SUBMISSION_RECEIPT_TYPE.type_id,
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
        if isinstance(binding_result, Failure):
            return InterpreterFailure(
                code="ASSIGNMENT_BINDING_MISMATCH",
                message=str((binding_result.context or {})["public_message"]),
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
        receipt = batch_task.AgentBatchSubmissionReceipt(
            submission_id=payload.submission_id,
            job_id=",".join(accepted),
            accepted_items=accepted,
            rejected_items=rejected,
            run_ref=run_ref,
            state="PARTIALLY_ACCEPTED" if rejected else "ACCEPTED",
            created_at=created_at,
        )
        return InterpreterSuccess(receipt)
