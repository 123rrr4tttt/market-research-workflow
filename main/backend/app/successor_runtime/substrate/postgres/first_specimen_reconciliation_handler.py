"""Readback-only PostgreSQL reconciliation for the first-specimen delivery.

The handler re-opens the original durable assignment/claim graph, reconstructs
the exact ``InternalExportRequest``, and delegates only to a capability-limited
readback facade.  It has no effect execution callback and cannot redispatch the
original internal export.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, Self

from sqlalchemy import MetaData, select
from sqlalchemy.engine import Connection

from app.successor_runtime.language.object_contracts import OperationContractRef
from app.successor_runtime.research.codec import canonical_bytes, sha256_hex
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    InterpreterBinding,
    RecoveryBinding,
    RuntimeAssignment,
    canonical_digest,
    require_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import RuntimeExecutionContext
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.runtime.reconciliation import (
    AuthoritativeEffectReadback,
    EffectAttemptObservation,
    EffectReconciler,
    ReconciliationHandlerOutcome,
    ReconciliationResult,
    ReconciliationState,
)
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.blob.internal_export import (
    InternalExportOutcome,
    InternalExportRequest,
)

from .first_specimen_delivery_handler import (
    DELIVERY_OPERATION,
    FirstSpecimenDeliveryEffectStore,
    FirstSpecimenDeliveryReplay,
    InstalledFirstSpecimenDeliveryHandler,
    PostgresFirstSpecimenDeliveryReplay,
)
from .models import PUBLIC_TABLES, project_tables
from .research_ledger import one_mapping
from .runtime_journal import validate_runtime_assignment_row
from .session import ProjectScopeStale, ServerProjectScopeResolver
from .staged_artifacts import StagedArtifactRepository


class FirstSpecimenReconciliationError(RuntimeError):
    """The durable recovery graph or authoritative readback drifted."""


@dataclass(frozen=True, slots=True)
class InstalledFirstSpecimenReconciliationHandler:
    """Exact recovery realization installed on one runtime node."""

    recovery_binding: RecoveryBinding
    operation_contract_digest: str

    def __post_init__(self) -> None:
        require_digest(self.operation_contract_digest, "operation_contract_digest")
        if self.recovery_binding.interpreter_profile_digest is None:
            raise ValueError(
                "recovery installation requires original interpreter profile"
            )

    @property
    def handler_binding_digest(self) -> str:
        return self.recovery_binding.binding_digest

    @property
    def interpreter_profile_digest(self) -> str:
        profile = self.recovery_binding.interpreter_profile_digest
        assert profile is not None
        return profile


class ReconciliationUnitOfWork(Protocol):
    connection: Connection

    def __enter__(self) -> Self: ...

    def commit(self) -> None: ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...


class ReconciliationUnitOfWorkFactory(Protocol):
    def __call__(self) -> ReconciliationUnitOfWork: ...


class VerifyAdmitRecoveryPort(Protocol):
    """Exact admission recovery; it cannot invoke the original verifier."""

    def __call__(
        self,
        *,
        connection: Connection,
        scope: RuntimeScope,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        observed_at: datetime,
    ) -> ReconciliationHandlerOutcome: ...


def _load_exact_original_graph(
    connection: Connection,
    recovery: RuntimeAssignment,
    *,
    interpreter_profile_digest: str,
) -> tuple[RuntimeAssignment, ClaimBinding]:
    attempt = one_mapping(
        connection.execute(
            select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                PUBLIC_TABLES["runtime_effect_attempts"].c.project_key
                == recovery.project_key,
                PUBLIC_TABLES["runtime_effect_attempts"].c.attempt_id
                == recovery.reconciliation_attempt_id,
                PUBLIC_TABLES["runtime_effect_attempts"].c.disposition
                == "OUTCOME_UNKNOWN",
            )
        )
    )
    if attempt is None:
        raise FirstSpecimenReconciliationError(
            "recovery target is not the exact unknown attempt"
        )
    try:
        original_claim = ClaimBinding.model_validate(attempt["claim_binding_json"])
    except (TypeError, ValueError) as exc:
        raise FirstSpecimenReconciliationError(
            "original attempt ClaimBinding is malformed"
        ) from exc
    work = one_mapping(
        connection.execute(
            select(PUBLIC_TABLES["runtime_work_items"]).where(
                PUBLIC_TABLES["runtime_work_items"].c.project_key
                == recovery.project_key,
                PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                == original_claim.work_item_id,
            )
        )
    )
    if work is None:
        raise FirstSpecimenReconciliationError("original recovery work is absent")
    original = validate_runtime_assignment_row(work)
    binding = original.handler_binding
    copied_fields = (
        "project_key",
        "run_id",
        "step_id",
        "step_role",
        "capability_id",
        "operation_contract_ref",
        "operation_contract_digest",
        "return_contract_binding",
        "program_digest",
        "plan_digest",
        "deployment_catalog_digest",
        "execution_epoch",
        "incarnation",
        "input_refs",
        "input_closure_digest",
        "payload_ref",
        "payload_digest",
        "queue_eligibility_digest",
        "resource_policy_epoch",
        "claim_authority_epoch",
        "claim_policy_digest",
        "trace_id",
    )
    if (
        original.assignment_kind
        not in {AssignmentKind.INTERPRET, AssignmentKind.VERIFY_ADMIT}
        or not isinstance(binding, InterpreterBinding)
        or any(
            getattr(original, field) != getattr(recovery, field)
            for field in copied_fields
        )
        or binding.interpreter_profile_digest != interpreter_profile_digest
        or original_claim.interpreter_profile_digest != interpreter_profile_digest
        or original_claim.attempt_id != recovery.reconciliation_attempt_id
        or original_claim.assignment_digest != original.assignment_digest
        or original_claim.handler_binding_digest != original.handler_binding_digest
        or original_claim.handler_realization_digest != original.handler_binding_digest
        or attempt["assignment_digest"] != original.assignment_digest
        or attempt["handler_binding_digest"] != original.handler_binding_digest
        or attempt["handler_realization_digest"] != original.handler_binding_digest
        or attempt["claim_binding_digest"] != original_claim.binding_digest
        or attempt["authorization_digest"] != original_claim.authorization_digest
        or attempt["input_digest"] != original.input_closure_digest
        or work["assignment_digest"] != original.assignment_digest
        or work["handler_binding_digest"] != original.handler_binding_digest
        or work["interpreter_profile_digest"] != interpreter_profile_digest
        or work["state"] not in {"WAITING", "COMPLETED"}
    ):
        raise FirstSpecimenReconciliationError("original recovery graph drift")
    return original, original_claim


class InternalExportRecoveryReadback(Protocol):
    """Only the internal-export capabilities that recovery may possess."""

    interpreter_id: str
    interpreter_version: str
    provider_id: str
    provider_version: str
    operation_contract_ref: OperationContractRef

    def readback_locator(self, request: InternalExportRequest) -> str: ...

    def readback_exact(
        self, request: InternalExportRequest
    ) -> InternalExportOutcome | AuthoritativeEffectReadback: ...


@dataclass(frozen=True, slots=True)
class _OriginalDeliveryAttempt:
    assignment: RuntimeAssignment
    claim: ClaimBinding
    replay: FirstSpecimenDeliveryReplay
    observation: EffectAttemptObservation


class _ExactRequestReadbackAdapter:
    """Bridge exact request readback into the generic reconciliation contract."""

    def __init__(
        self,
        *,
        facade: InternalExportRecoveryReadback,
        request: InternalExportRequest,
        expected: EffectAttemptObservation,
    ) -> None:
        self.interpreter_id = facade.interpreter_id
        self.interpreter_version = facade.interpreter_version
        self.provider_id = facade.provider_id
        self.provider_version = facade.provider_version
        self._facade = facade
        self._request = request
        self._expected = expected
        self.receipt = None

    def readback(
        self, attempt: EffectAttemptObservation
    ) -> AuthoritativeEffectReadback:
        if attempt != self._expected:
            raise FirstSpecimenReconciliationError(
                "reconciler changed the exact original-attempt observation"
            )
        observed = self._facade.readback_exact(self._request)
        if isinstance(observed, InternalExportOutcome):
            self.receipt = observed.receipt
            return observed.readback
        if not isinstance(observed, AuthoritativeEffectReadback):
            raise FirstSpecimenReconciliationError(
                "readback facade returned no authoritative typed evidence"
            )
        return observed

    def prove_not_started(self, attempt: EffectAttemptObservation) -> object:
        raise FirstSpecimenReconciliationError(
            "first-specimen reconciliation does not materialize successor attempts"
        )


class PostgresFirstSpecimenReconciliationHandler:
    """RuntimeHandler that performs readback and candidate recovery only."""

    def __init__(
        self,
        installation: InstalledFirstSpecimenReconciliationHandler,
        uow_factory: ReconciliationUnitOfWorkFactory,
        *,
        readback: InternalExportRecoveryReadback,
        delivery_replay: PostgresFirstSpecimenDeliveryReplay | None = None,
        recover_verify_admit: VerifyAdmitRecoveryPort | None = None,
    ) -> None:
        if (
            readback.operation_contract_ref.contract_digest
            != installation.operation_contract_digest
            or readback.operation_contract_ref.kind != DELIVERY_OPERATION
        ):
            raise ValueError("recovery readback operation contract drift")
        self.installation = installation
        self.handler_binding_digest = installation.handler_binding_digest
        self.interpreter_profile_digest = installation.interpreter_profile_digest
        self.operation_contract_digest = installation.operation_contract_digest
        self._uow_factory = uow_factory
        self._readback = readback
        self._delivery_replay = delivery_replay or PostgresFirstSpecimenDeliveryReplay()
        self._reconciler = EffectReconciler()
        self._recover_verify_admit = recover_verify_admit

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> ReconciliationHandlerOutcome:
        """Observe the original attempt; never enter an effect execution path."""

        self._require_exact_recovery_assignment(assignment, claim)
        with self._uow_factory() as uow:
            original_assignment, original_claim = _load_exact_original_graph(
                uow.connection,
                assignment,
                interpreter_profile_digest=self.interpreter_profile_digest,
            )
            if original_assignment.assignment_kind is AssignmentKind.VERIFY_ADMIT:
                if self._recover_verify_admit is None:
                    raise FirstSpecimenReconciliationError(
                        "delivery VERIFY_ADMIT recovery realization is not installed"
                    )
                run = one_mapping(
                    uow.connection.execute(
                        select(PUBLIC_TABLES["runtime_runs"]).where(
                            PUBLIC_TABLES["runtime_runs"].c.project_key
                            == assignment.project_key,
                            PUBLIC_TABLES["runtime_runs"].c.run_id == assignment.run_id,
                        )
                    )
                )
                if run is None:
                    raise FirstSpecimenReconciliationError(
                        "delivery admission recovery run is absent"
                    )
                resolver = ServerProjectScopeResolver(connection=uow.connection)
                scope_ref = resolver.resolve_expected(
                    assignment.project_key,
                    int(run["project_registry_revision"]),
                    str(run["project_scope_digest"]),
                )
                if (
                    isinstance(scope_ref, ProjectScopeStale)
                    or resolver.resolve(assignment.project_key) != scope_ref
                ):
                    raise FirstSpecimenReconciliationError(
                        "delivery admission recovery project scope is stale"
                    )
                outcome = self._recover_verify_admit(
                    connection=uow.connection,
                    scope=RuntimeScope(
                        project_scope=scope_ref,
                        actor_id=claim.node_id,
                    ),
                    assignment=original_assignment,
                    claim=original_claim,
                    observed_at=context.observed_at,
                )
                uow.commit()
                return outcome
            original = self._load_original_delivery(
                uow.connection,
                assignment,
                context,
            )
            adapter = _ExactRequestReadbackAdapter(
                facade=self._readback,
                request=original.replay.request,
                expected=original.observation,
            )
            result = self._reconciler.reconcile(
                assignment=assignment,
                attempt=original.observation,
                interpreter=adapter,
            )
            if result.state is ReconciliationState.WAITING:
                return ReconciliationHandlerOutcome(result=result)
            if result.disposition is EffectDisposition.FAILED:
                return ReconciliationHandlerOutcome(result=result)
            if (
                result.state is not ReconciliationState.RESOLVED
                or result.disposition is not EffectDisposition.SUCCEEDED
                or result.readback is None
                or adapter.receipt is None
            ):
                raise FirstSpecimenReconciliationError(
                    "first-specimen readback produced an unsupported reconciliation state"
                )
            receipt = adapter.receipt
            if (
                receipt.content_digest is None
                or receipt.attempt_ref != original.claim.attempt_id
                or receipt.receipt_digest != result.readback.receipt_digest
                or receipt.provider_locator != result.readback.provider_locator
            ):
                raise FirstSpecimenReconciliationError(
                    "reconstructed delivery receipt/readback exact binding drift"
                )
            original_installation = InstalledFirstSpecimenDeliveryHandler.bind(
                handler_binding_digest=original.assignment.handler_binding_digest,
                interpreter_profile_digest=self.interpreter_profile_digest,
            )
            staged = StagedArtifactRepository(uow.connection, original.replay.scope)
            stage_id = (
                f"stage:{original.assignment.run_id}:"
                f"{original.assignment.step_id}:"
                f"epoch-{original.assignment.execution_epoch}"
            )
            existing_stage = one_mapping(
                uow.connection.execute(
                    select(PUBLIC_TABLES["runtime_staged_artifacts"]).where(
                        PUBLIC_TABLES["runtime_staged_artifacts"].c.project_key
                        == original.assignment.project_key,
                        PUBLIC_TABLES["runtime_staged_artifacts"].c.artifact_id
                        == stage_id,
                    )
                )
            )
            if existing_stage is None or existing_stage["state"] == "STAGED":
                FirstSpecimenDeliveryEffectStore._persist_receipt(
                    uow.connection,
                    original_installation,
                    original.assignment,
                    original.claim,
                    original.replay,
                    receipt,
                )
            elif (
                existing_stage["state"] != "VERIFIED"
                or existing_stage["attempt_id"] != original.claim.attempt_id
                or existing_stage["receipt_ref"] != receipt.receipt_ref
                or existing_stage["value_id"]
                != (
                    f"result:{original.assignment.run_id}:"
                    f"{original.assignment.step_id}:"
                    f"epoch-{original.assignment.execution_epoch}"
                )
            ):
                raise FirstSpecimenReconciliationError(
                    "recovered delivery candidate exact binding drift"
                )
            stage = staged.load(stage_id, for_update=True)
            if stage["state"] == "STAGED":
                staged.transition(
                    stage_id,
                    expected_revision=int(stage["revision"]),
                    expected_state="STAGED",
                    target_state="VERIFIED",
                )
            elif stage["state"] != "VERIFIED":
                raise FirstSpecimenReconciliationError(
                    "recovered delivery candidate is not verifiable"
                )
            uow.commit()
            return ReconciliationHandlerOutcome(
                result=result,
                output_digest=receipt.content_digest,
                receipt_ref=receipt.receipt_ref,
            )

    def _require_exact_recovery_assignment(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
    ) -> None:
        claim.validate_against(assignment)
        binding = assignment.handler_binding
        installed = self.installation.recovery_binding
        if (
            assignment.assignment_kind is not AssignmentKind.RECONCILE
            or not isinstance(binding, RecoveryBinding)
            or binding != installed
            or binding.binding_digest != self.handler_binding_digest
            or binding.recovery_handler_id != installed.recovery_handler_id
            or binding.recovery_handler_version != installed.recovery_handler_version
            or binding.authoritative_readback_profile_ref
            != installed.authoritative_readback_profile_ref
            or binding.interpreter_profile_digest != self.interpreter_profile_digest
            or assignment.operation_contract_digest != self.operation_contract_digest
            or assignment.operation_contract_ref
            != self._readback.operation_contract_ref
            or claim.interpreter_profile_digest != self.interpreter_profile_digest
            or assignment.reconciliation_attempt_id is None
        ):
            raise FirstSpecimenReconciliationError(
                "exact RecoveryBinding/readback/original-profile drift"
            )

    def _load_original_delivery(
        self,
        connection: Connection,
        recovery_assignment: RuntimeAssignment,
        context: RuntimeExecutionContext,
    ) -> _OriginalDeliveryAttempt:
        attempt_table = PUBLIC_TABLES["runtime_effect_attempts"]
        attempt = one_mapping(
            connection.execute(
                select(attempt_table).where(
                    attempt_table.c.project_key == recovery_assignment.project_key,
                    attempt_table.c.attempt_id
                    == recovery_assignment.reconciliation_attempt_id,
                )
            )
        )
        if attempt is None:
            raise FirstSpecimenReconciliationError(
                "original reconciliation attempt is absent"
            )
        try:
            original_claim = ClaimBinding.model_validate(attempt["claim_binding_json"])
        except (TypeError, ValueError) as exc:
            raise FirstSpecimenReconciliationError(
                "original attempt claim binding is malformed"
            ) from exc

        work_table = PUBLIC_TABLES["runtime_work_items"]
        work = one_mapping(
            connection.execute(
                select(work_table).where(
                    work_table.c.project_key == recovery_assignment.project_key,
                    work_table.c.work_item_id == original_claim.work_item_id,
                )
            )
        )
        if work is None:
            raise FirstSpecimenReconciliationError(
                "original reconciliation work item is absent"
            )
        try:
            original_assignment = validate_runtime_assignment_row(work)
        except Exception as exc:
            raise FirstSpecimenReconciliationError(
                "original assignment binding is malformed or drifted"
            ) from exc
        self._require_original_graph(
            recovery_assignment,
            attempt,
            work,
            original_assignment,
            original_claim,
        )

        original_binding = original_assignment.handler_binding
        assert isinstance(original_binding, InterpreterBinding)
        original_installation = InstalledFirstSpecimenDeliveryHandler.bind(
            handler_binding_digest=original_assignment.handler_binding_digest,
            interpreter_profile_digest=original_binding.interpreter_profile_digest,
        )
        replay = self._delivery_replay.load_exact(
            connection,
            original_installation,
            original_assignment,
            original_claim,
            context,
        )
        locator = self._readback.readback_locator(replay.request)
        if replay.request.delivery_intent.idempotency_key == "" or not locator:
            raise FirstSpecimenReconciliationError(
                "original DeliveryIntent readback identity is absent"
            )
        observation = EffectAttemptObservation(
            attempt_id=original_claim.attempt_id,
            assignment_digest=original_assignment.assignment_digest,
            handler_binding_digest=original_assignment.handler_binding_digest,
            interpreter_profile_digest=original_binding.interpreter_profile_digest,
            interpreter_id=self._readback.interpreter_id,
            interpreter_version=self._readback.interpreter_version,
            provider_id=self._readback.provider_id,
            provider_version=self._readback.provider_version,
            external_idempotency_key=(replay.request.delivery_intent.idempotency_key),
            authoritative_readback_locator=locator,
        )
        return _OriginalDeliveryAttempt(
            assignment=original_assignment,
            claim=original_claim,
            replay=replay,
            observation=observation,
        )

    def _require_original_graph(
        self,
        recovery: RuntimeAssignment,
        attempt: Mapping[str, Any],
        work: Mapping[str, Any],
        original: RuntimeAssignment,
        original_claim: ClaimBinding,
    ) -> None:
        attempt_row = attempt
        work_row = work
        binding = original.handler_binding
        copied_fields = (
            "project_key",
            "run_id",
            "step_id",
            "step_role",
            "capability_id",
            "operation_contract_ref",
            "operation_contract_digest",
            "return_contract_binding",
            "program_digest",
            "plan_digest",
            "deployment_catalog_digest",
            "execution_epoch",
            "incarnation",
            "input_refs",
            "input_closure_digest",
            "payload_ref",
            "payload_digest",
            "queue_eligibility_digest",
            "resource_policy_epoch",
            "claim_authority_epoch",
            "claim_policy_digest",
            "trace_id",
        )
        if (
            original.assignment_kind is not AssignmentKind.INTERPRET
            or not isinstance(binding, InterpreterBinding)
            or original.operation_contract_ref is None
            or original.operation_contract_ref.kind != DELIVERY_OPERATION
            or any(
                getattr(original, field) != getattr(recovery, field)
                for field in copied_fields
            )
            or binding.interpreter_profile_digest != self.interpreter_profile_digest
            or original_claim.interpreter_profile_digest
            != self.interpreter_profile_digest
            or original_claim.attempt_id != recovery.reconciliation_attempt_id
            or original_claim.assignment_digest != original.assignment_digest
            or original_claim.handler_binding_digest != original.handler_binding_digest
            or original_claim.handler_realization_digest
            != original.handler_binding_digest
            or attempt_row["attempt_id"] != original_claim.attempt_id
            or attempt_row["run_id"] != original.run_id
            or attempt_row["step_id"] != original.step_id
            or attempt_row["assignment_digest"] != original.assignment_digest
            or attempt_row["handler_binding_digest"] != original.handler_binding_digest
            or attempt_row["handler_realization_digest"]
            != original.handler_binding_digest
            or attempt_row["claim_binding_digest"] != original_claim.binding_digest
            or attempt_row["authorization_digest"]
            != original_claim.authorization_digest
            or attempt_row["input_digest"] != original.input_closure_digest
            or attempt_row["disposition"] != EffectDisposition.OUTCOME_UNKNOWN.value
            or work_row["assignment_digest"] != original.assignment_digest
            or work_row["handler_binding_digest"] != original.handler_binding_digest
            or work_row["interpreter_profile_digest"] != self.interpreter_profile_digest
            or work_row["state"] not in {"WAITING", "COMPLETED"}
        ):
            raise FirstSpecimenReconciliationError(
                "original attempt/work/assignment/claim graph drift"
            )


class PostgresFirstSpecimenLocalReconciliationHandler:
    """Read an already persisted local output without re-running its effect."""

    def __init__(
        self,
        installation: InstalledFirstSpecimenReconciliationHandler,
        uow_factory: ReconciliationUnitOfWorkFactory,
        *,
        recover_verify_admit: VerifyAdmitRecoveryPort | None = None,
    ) -> None:
        self.installation = installation
        self.handler_binding_digest = installation.handler_binding_digest
        self.interpreter_profile_digest = installation.interpreter_profile_digest
        self.operation_contract_digest = installation.operation_contract_digest
        self._uow_factory = uow_factory
        self._recover_verify_admit = recover_verify_admit

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> ReconciliationHandlerOutcome:
        self._require_exact(assignment, claim)
        with self._uow_factory() as uow:
            original, original_claim = self._load_original(uow.connection, assignment)
            run = one_mapping(
                uow.connection.execute(
                    select(PUBLIC_TABLES["runtime_runs"]).where(
                        PUBLIC_TABLES["runtime_runs"].c.project_key
                        == assignment.project_key,
                        PUBLIC_TABLES["runtime_runs"].c.run_id == assignment.run_id,
                    )
                )
            )
            if run is None:
                raise FirstSpecimenReconciliationError("local recovery run is absent")
            resolver = ServerProjectScopeResolver(connection=uow.connection)
            scope_ref = resolver.resolve_expected(
                assignment.project_key,
                int(run["project_registry_revision"]),
                str(run["project_scope_digest"]),
            )
            if (
                isinstance(scope_ref, ProjectScopeStale)
                or resolver.resolve(assignment.project_key) != scope_ref
            ):
                raise FirstSpecimenReconciliationError(
                    "local recovery project scope is stale"
                )
            scope = RuntimeScope(project_scope=scope_ref, actor_id=claim.node_id)
            if original.assignment_kind is AssignmentKind.VERIFY_ADMIT:
                if self._recover_verify_admit is None:
                    raise FirstSpecimenReconciliationError(
                        "VERIFY_ADMIT recovery realization is not installed"
                    )
                outcome = self._recover_verify_admit(
                    connection=uow.connection,
                    scope=scope,
                    assignment=original,
                    claim=original_claim,
                    observed_at=context.observed_at,
                )
                uow.commit()
                return outcome
            tables = project_tables(MetaData(), scope_ref.resolved_schema)
            runtime_value_id = (
                f"result:{original.run_id}:{original.step_id}:"
                f"epoch-{original.execution_epoch}"
            )
            runtime_value = one_mapping(
                uow.connection.execute(
                    select(PUBLIC_TABLES["runtime_values"]).where(
                        PUBLIC_TABLES["runtime_values"].c.project_key
                        == assignment.project_key,
                        PUBLIC_TABLES["runtime_values"].c.value_id == runtime_value_id,
                        PUBLIC_TABLES["runtime_values"].c.state == "AVAILABLE",
                    )
                )
            )
            if runtime_value is None:
                return self._waiting(assignment, "LOCAL_RUNTIME_VALUE_ABSENT")
            project_ref = runtime_value["project_value_ref"]
            if not isinstance(project_ref, str) or not project_ref.startswith(
                "project-value:"
            ):
                raise FirstSpecimenReconciliationError(
                    "local recovery output is not project-value owned"
                )
            project_value = one_mapping(
                uow.connection.execute(
                    select(tables.successor_values).where(
                        tables.successor_values.c.project_key == assignment.project_key,
                        tables.successor_values.c.value_id
                        == project_ref.removeprefix("project-value:"),
                        tables.successor_values.c.state == "AVAILABLE",
                    )
                )
            )
            if project_value is None:
                return self._waiting(assignment, "LOCAL_PROJECT_VALUE_ABSENT")
            exact = self._exact_bytes(project_value)
            digest = hashlib.sha256(exact).hexdigest()
            provenance = project_value["provenance_json"]
            if (
                digest != runtime_value["content_digest"]
                or digest != project_value["content_digest"]
                or len(exact) != int(runtime_value["byte_size"])
                or runtime_value["object_type"] != project_value["object_type"]
                or runtime_value["codec_id"] != project_value["codec_id"]
                or not isinstance(provenance, Mapping)
                or sha256_hex(dict(provenance)) != project_value["provenance_digest"]
            ):
                raise FirstSpecimenReconciliationError(
                    "local recovery value exact readback drift"
                )
            if (
                original.return_contract_binding is not None
                and original.return_contract_binding.admission_required
            ):
                self._verify_stage(
                    uow.connection,
                    scope,
                    original,
                    original_claim,
                    runtime_value_id,
                )
            receipt_digest = canonical_digest(
                {
                    "schema_version": "mrw.local-effect-readback-receipt.v1",
                    "attempt_id": original_claim.attempt_id,
                    "runtime_value_id": runtime_value_id,
                    "project_value_ref": project_ref,
                    "content_digest": digest,
                    "storage_digest": runtime_value["storage_digest"],
                }
            )
            readback = AuthoritativeEffectReadback(
                attempt_id=original_claim.attempt_id,
                disposition=EffectDisposition.SUCCEEDED,
                provider_locator=project_ref,
                receipt_digest=receipt_digest,
                observation_digest=canonical_digest(
                    {
                        "runtime_value_id": runtime_value_id,
                        "content_digest": digest,
                        "provenance_digest": project_value["provenance_digest"],
                    }
                ),
            )
            uow.commit()
            return ReconciliationHandlerOutcome(
                result=ReconciliationResult(
                    state=ReconciliationState.RESOLVED,
                    attempt_id=original_claim.attempt_id,
                    disposition=EffectDisposition.SUCCEEDED,
                    readback=readback,
                ),
                output_digest=digest,
            )

    def _load_original(
        self, connection: Connection, recovery: RuntimeAssignment
    ) -> tuple[RuntimeAssignment, ClaimBinding]:
        return _load_exact_original_graph(
            connection,
            recovery,
            interpreter_profile_digest=self.interpreter_profile_digest,
        )

    def _require_exact(
        self, assignment: RuntimeAssignment, claim: ClaimBinding
    ) -> None:
        claim.validate_against(assignment)
        binding = assignment.handler_binding
        if (
            assignment.assignment_kind is not AssignmentKind.RECONCILE
            or not isinstance(binding, RecoveryBinding)
            or binding != self.installation.recovery_binding
            or assignment.operation_contract_digest != self.operation_contract_digest
            or assignment.reconciliation_attempt_id is None
            or claim.interpreter_profile_digest != self.interpreter_profile_digest
        ):
            raise FirstSpecimenReconciliationError("local recovery exact binding drift")

    @staticmethod
    def _exact_bytes(row: Mapping[str, Any]) -> bytes:
        if row["content_bytes"] is not None and row["content_json"] is None:
            return bytes(row["content_bytes"])
        if row["content_json"] is not None and row["content_bytes"] is None:
            return canonical_bytes(row["content_json"])
        raise FirstSpecimenReconciliationError(
            "local recovery value lacks one exact representation"
        )

    @staticmethod
    def _verify_stage(
        connection: Connection,
        scope: RuntimeScope,
        original: RuntimeAssignment,
        original_claim: ClaimBinding,
        runtime_value_id: str,
    ) -> None:
        stage_id = (
            f"stage:{original.run_id}:{original.step_id}:"
            f"epoch-{original.execution_epoch}"
        )
        staged = StagedArtifactRepository(connection, scope)
        stage = staged.load(stage_id, for_update=True)
        if (
            stage["attempt_id"] != original_claim.attempt_id
            or stage["value_id"] != runtime_value_id
        ):
            raise FirstSpecimenReconciliationError(
                "local recovery staged candidate binding drift"
            )
        if stage["state"] == "STAGED":
            staged.transition(
                stage_id,
                expected_revision=int(stage["revision"]),
                expected_state="STAGED",
                target_state="VERIFIED",
            )
        elif stage["state"] != "VERIFIED":
            raise FirstSpecimenReconciliationError(
                "local recovery candidate is not verifiable"
            )

    @staticmethod
    def _waiting(
        assignment: RuntimeAssignment, reason: str
    ) -> ReconciliationHandlerOutcome:
        assert assignment.reconciliation_attempt_id is not None
        readback = AuthoritativeEffectReadback(
            attempt_id=assignment.reconciliation_attempt_id,
            disposition=EffectDisposition.OUTCOME_UNKNOWN,
            observation_digest=canonical_digest(
                {"attempt_id": assignment.reconciliation_attempt_id, "reason": reason}
            ),
            reason=reason,
        )
        return ReconciliationHandlerOutcome(
            result=ReconciliationResult(
                state=ReconciliationState.WAITING,
                attempt_id=assignment.reconciliation_attempt_id,
                disposition=EffectDisposition.OUTCOME_UNKNOWN,
                readback=readback,
                wait_reason=reason,
            )
        )


__all__ = [
    "FirstSpecimenReconciliationError",
    "InstalledFirstSpecimenReconciliationHandler",
    "InternalExportRecoveryReadback",
    "PostgresFirstSpecimenLocalReconciliationHandler",
    "PostgresFirstSpecimenReconciliationHandler",
    "ReconciliationUnitOfWorkFactory",
    "VerifyAdmitRecoveryPort",
    "BatchBusinessBrokerReadbackFacade",
    "BatchBusinessCancelResult",
    "BatchBusinessNonStartUnprovable",
    "BatchBusinessReadback",
    "BatchBusinessReadbackError",
    "BatchBusinessReadbackReplayData",
    "BatchBusinessReadbackReplayPort",
    "BatchBusinessReadbackRequest",
    "BatchBusinessWaitHandler",
    "BatchTaskBusinessRecoveryReadback",
    "BusinessResultPublisher",
    "InstalledBatchTaskBusinessReadbackHandler",
    "PostgresBatchBusinessReadbackReplay",
    "PostgresBusinessResultPublisher",
    "PostgresBatchTaskBusinessReadbackHandler",
]


import json
from datetime import UTC
from typing import Literal

from app.successor_runtime.capabilities.batch_business import (
    BrokerBusinessReadback,
    BusinessCancelObservation,
    BusinessTaskObservation,
    BusinessTaskState,
)
from app.successor_runtime.capabilities import batch_task
from app.successor_runtime.capabilities import batch_business
from app.successor_runtime.capabilities.checksum import canonical_json
from app.successor_runtime.runtime.recovery import NonStartProof

from .first_specimen_activation import PostgresFirstSpecimenActivationBindingAdapter
from .batch_task_submission_handler import PersistentOperationHandler
from .node_adapter import UowFactory


class BatchBusinessReadbackError(RuntimeError):
    """The durable wait graph or the business broker readback drifted."""


@dataclass(frozen=True, slots=True)
class BatchBusinessReadbackRequest:
    """Exact readback target rebuilt from the accepted dispatch ACK."""

    project_key: str
    project_scope_digest: str
    run_id: str
    step_id: str
    attempt_id: str
    assignment_digest: str
    operation_contract_ref: OperationContractRef
    handler_binding_digest: str
    dispatch_id: str
    channel: str
    lane: str
    celery_task_id: str
    ack_digest: str

    def __post_init__(self) -> None:
        for name in (
            "project_key",
            "run_id",
            "step_id",
            "attempt_id",
            "assignment_digest",
            "handler_binding_digest",
            "project_scope_digest",
            "dispatch_id",
            "celery_task_id",
            "ack_digest",
        ):
            if not getattr(self, name):
                raise ValueError(f"BatchBusinessReadbackRequest requires {name}")
        for name in (
            "project_scope_digest",
            "attempt_id",
            "assignment_digest",
            "handler_binding_digest",
            "operation_contract_ref.contract_digest",
            "ack_digest",
        ):
            value = (
                self.operation_contract_ref.contract_digest
                if name == "operation_contract_ref.contract_digest"
                else getattr(self, name)
            )
            require_digest(value, name)

    @property
    def external_idempotency_key(self) -> str:
        return self.celery_task_id

    @property
    def request_digest(self) -> str:
        return canonical_digest(
            {
                "schema_version": "mrw.batch.business-readback.request.v1",
                "project_key": self.project_key,
                "project_scope_digest": self.project_scope_digest,
                "run_id": self.run_id,
                "step_id": self.step_id,
                "attempt_id": self.attempt_id,
                "assignment_digest": self.assignment_digest,
                "operation_contract_digest": (
                    self.operation_contract_ref.contract_digest
                ),
                "handler_binding_digest": self.handler_binding_digest,
                "dispatch_id": self.dispatch_id,
                "channel": self.channel,
                "lane": self.lane,
                "celery_task_id": self.celery_task_id,
                "ack_digest": self.ack_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class BatchBusinessReadback:
    """Exact business readback outcome carrying the precise typed result."""

    readback: AuthoritativeEffectReadback
    result: batch_business.BatchBusinessResult | None = None
    business_state: str | None = None


@dataclass(frozen=True, slots=True)
class BatchBusinessCancelResult:
    """Typed broker cancellation request; terminality stays with a readback."""

    attempt_id: str
    task_id: str
    state: Literal["REVOKE_REQUESTED", "REVOKE_FAILED"]
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class BatchBusinessNonStartUnprovable:
    """A broker observation that does not authoritatively prove non-start."""

    attempt_id: str
    reason: str


class BatchTaskBusinessRecoveryReadback(Protocol):
    """Capability-limited business readback facade; it cannot redispatch."""

    interpreter_id: str
    interpreter_version: str
    provider_id: str
    provider_version: str
    operation_contract_ref: OperationContractRef

    def readback_locator(self, request: BatchBusinessReadbackRequest) -> str: ...

    def readback_exact(
        self, request: BatchBusinessReadbackRequest
    ) -> BatchBusinessReadback | AuthoritativeEffectReadback: ...

    def cancel(
        self, request: BatchBusinessReadbackRequest
    ) -> BatchBusinessCancelResult: ...

    def prove_not_started(
        self, request: BatchBusinessReadbackRequest
    ) -> NonStartProof | BatchBusinessNonStartUnprovable: ...


def _batch_unknown_readback(
    request: BatchBusinessReadbackRequest,
    reason: str,
    state_label: str,
) -> AuthoritativeEffectReadback:
    return AuthoritativeEffectReadback(
        attempt_id=request.attempt_id,
        disposition=EffectDisposition.OUTCOME_UNKNOWN,
        observation_digest=canonical_digest(
            {
                "attempt_id": request.attempt_id,
                "reason": reason,
                "business_state": state_label,
                "task_id": request.celery_task_id,
            }
        ),
        reason=reason,
    )


def _not_start_reason(state: BusinessTaskState) -> str:
    if state is BusinessTaskState.PENDING:
        return "CELERY_PENDING_IS_NOT_NON_START_EVIDENCE"
    if state is BusinessTaskState.UNKNOWN:
        return "CELERY_BROKER_STATE_UNKNOWN"
    return "BUSINESS_ALREADY_TERMINAL"


class BatchBusinessBrokerReadbackFacade:
    """Bridge one broker observer into the generic reconciliation contract."""

    interpreter_id = "successor-native.batch-business-readback"
    interpreter_version = "1.0.0"
    provider_id = "mrw.batch.celery-business"
    provider_version = "1.0.0"

    def __init__(
        self,
        *,
        operation_contract_ref: OperationContractRef,
        broker: BrokerBusinessReadback,
    ) -> None:
        self.operation_contract_ref = operation_contract_ref
        self._broker = broker

    def readback_locator(self, request: BatchBusinessReadbackRequest) -> str:
        return f"celery-task:{request.celery_task_id}"

    def readback_exact(
        self, request: BatchBusinessReadbackRequest
    ) -> BatchBusinessReadback | AuthoritativeEffectReadback:
        if request.operation_contract_ref != self.operation_contract_ref:
            raise BatchBusinessReadbackError("operation contract digest drift")
        observation = self._broker.read_task(request.celery_task_id)
        if observation.task_id != request.celery_task_id:
            raise BatchBusinessReadbackError("broker observation task id drift")
        locator = self.readback_locator(request)
        state = observation.state
        if state is BusinessTaskState.SUCCESS:
            result = batch_business.build_batch_business_result_from_ack_fields(
                task_id=request.celery_task_id,
                ack_digest=request.ack_digest,
                output=observation.result,
            )
            readback = AuthoritativeEffectReadback(
                attempt_id=request.attempt_id,
                disposition=EffectDisposition.SUCCEEDED,
                provider_locator=locator,
                receipt_digest=result.receipt_digest,
                observation_digest=canonical_digest(
                    {
                        "request_digest": request.request_digest,
                        "provider_locator": locator,
                        "receipt_digest": result.receipt_digest,
                    }
                ),
            )
            return BatchBusinessReadback(
                readback=readback,
                result=result,
                business_state=state.value,
            )
        if state in {BusinessTaskState.FAILURE, BusinessTaskState.REVOKED}:
            reason = (
                "CELERY_TASK_REVOKED"
                if state is BusinessTaskState.REVOKED
                else "CELERY_TASK_FAILURE"
            )
            failure_digest = canonical_digest(
                {
                    "attempt_id": request.attempt_id,
                    "task_id": request.celery_task_id,
                    "business_state": state.value,
                    "reason": reason,
                    "error": observation.result,
                }
            )
            return AuthoritativeEffectReadback(
                attempt_id=request.attempt_id,
                disposition=EffectDisposition.FAILED,
                failure_digest=failure_digest,
                observation_digest=canonical_digest(
                    {
                        "attempt_id": request.attempt_id,
                        "failure_digest": failure_digest,
                        "request_digest": request.request_digest,
                    }
                ),
                reason=reason,
            )
        if state is BusinessTaskState.PENDING:
            return _batch_unknown_readback(request, "CELERY_PENDING", "PENDING")
        if state is BusinessTaskState.NOT_STARTED:
            return _batch_unknown_readback(request, "CELERY_NOT_STARTED", "NOT_STARTED")
        return _batch_unknown_readback(
            request, "CELERY_BROKER_STATE_UNKNOWN", "UNKNOWN"
        )

    def cancel(
        self, request: BatchBusinessReadbackRequest
    ) -> BatchBusinessCancelResult:
        observation: BusinessCancelObservation = self._broker.cancel_task(
            request.celery_task_id
        )
        return BatchBusinessCancelResult(
            attempt_id=request.attempt_id,
            task_id=request.celery_task_id,
            state=observation.state,
            reason=observation.reason,
        )

    def prove_not_started(
        self, request: BatchBusinessReadbackRequest
    ) -> NonStartProof | BatchBusinessNonStartUnprovable:
        observation: BusinessTaskObservation = self._broker.read_task(
            request.celery_task_id
        )
        if observation.state is not BusinessTaskState.NOT_STARTED:
            return BatchBusinessNonStartUnprovable(
                request.attempt_id, _not_start_reason(observation.state)
            )
        locator = self.readback_locator(request)
        observed_at = datetime.now(UTC)
        observation_payload: dict[str, object] = {
            "attempt_id": request.attempt_id,
            "authoritative_readback_locator": locator,
            "broker_state": observation.state.value,
            "task_id": request.celery_task_id,
        }
        authoritative_observation_digest = canonical_digest(observation_payload)
        provisional = NonStartProof.model_construct(
            attempt_id=request.attempt_id,
            interpreter_id=self.interpreter_id,
            interpreter_version=self.interpreter_version,
            provider_id=self.provider_id,
            provider_version=self.provider_version,
            external_idempotency_key=request.celery_task_id,
            authoritative_readback_locator=locator,
            authoritative_observation_digest=authoritative_observation_digest,
            observed_at=observed_at,
            proof_digest="0" * 64,
        )
        proof_digest = canonical_digest(
            provisional, exclude_fields={"proof_digest"}
        )
        return NonStartProof(
            attempt_id=request.attempt_id,
            interpreter_id=self.interpreter_id,
            interpreter_version=self.interpreter_version,
            provider_id=self.provider_id,
            provider_version=self.provider_version,
            external_idempotency_key=request.celery_task_id,
            authoritative_readback_locator=locator,
            authoritative_observation_digest=authoritative_observation_digest,
            observed_at=observed_at,
            proof_digest=proof_digest,
        )


@dataclass(frozen=True, slots=True)
class InstalledBatchTaskBusinessReadbackHandler:
    """Exact business-readback realization installed on one runtime node."""

    recovery_binding: RecoveryBinding
    operation_contract_digest: str

    def __post_init__(self) -> None:
        require_digest(self.operation_contract_digest, "operation_contract_digest")
        if self.recovery_binding.interpreter_profile_digest is None:
            raise ValueError(
                "business readback recovery requires original interpreter profile"
            )

    @property
    def handler_binding_digest(self) -> str:
        return self.recovery_binding.binding_digest

    @property
    def interpreter_profile_digest(self) -> str:
        profile = self.recovery_binding.interpreter_profile_digest
        assert profile is not None
        return profile


@dataclass(frozen=True, slots=True)
class BatchBusinessReadbackReplayData:
    """What a replay must reconstruct before the readback facade is entered."""

    scope: RuntimeScope
    request: BatchBusinessReadbackRequest


class BatchBusinessReadbackReplayPort(Protocol):
    def load_exact(
        self,
        connection: Connection,
        installation: InstalledBatchTaskBusinessReadbackHandler,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> BatchBusinessReadbackReplayData: ...


class PostgresBatchBusinessReadbackReplay:
    """Rebuild the accepted ACK through the shared activation read path."""

    def load_exact(
        self,
        connection: Connection,
        installation: InstalledBatchTaskBusinessReadbackHandler,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> BatchBusinessReadbackReplayData:
        contract_ref = assignment.operation_contract_ref
        if contract_ref is None:
            raise BatchBusinessReadbackError(
                "business wait assignment lacks operation contract"
            )
        runs = PUBLIC_TABLES["runtime_runs"]
        run = one_mapping(
            connection.execute(
                select(runs).where(
                    runs.c.project_key == assignment.project_key,
                    runs.c.run_id == assignment.run_id,
                )
            )
        )
        if run is None:
            raise BatchBusinessReadbackError("business wait run is absent")
        resolver = ServerProjectScopeResolver(connection=connection)
        resolved = resolver.resolve_expected(
            assignment.project_key,
            int(run["project_registry_revision"]),
            str(run["project_scope_digest"]),
        )
        if (
            isinstance(resolved, ProjectScopeStale)
            or resolver.resolve(assignment.project_key) != resolved
        ):
            raise BatchBusinessReadbackError("business wait project scope is stale")
        scope = RuntimeScope(project_scope=resolved, actor_id=context.node.node_id)
        tables = project_tables(MetaData(), resolved.resolved_schema)
        adapter = PostgresFirstSpecimenActivationBindingAdapter()
        descriptor = adapter.load_exact(connection, assignment, scope, tables)
        input_ref = adapter.semantic_input_ref(
            connection, assignment, scope, tables, descriptor
        )
        exact = adapter.read_value_bytes(connection, scope, tables, input_ref)
        ack = self._decode_ack(exact, contract_ref)
        request = BatchBusinessReadbackRequest(
            project_key=assignment.project_key,
            project_scope_digest=resolved.scope_digest,
            run_id=assignment.run_id,
            step_id=assignment.step_id or "",
            attempt_id=claim.attempt_id,
            assignment_digest=assignment.assignment_digest,
            operation_contract_ref=contract_ref,
            handler_binding_digest=assignment.handler_binding_digest,
            dispatch_id=ack.dispatch_id,
            channel=ack.channel,
            lane=ack.lane,
            celery_task_id=ack.celery_task_id,
            ack_digest=ack.ack_digest,
        )
        return BatchBusinessReadbackReplayData(scope=scope, request=request)

    @staticmethod
    def _decode_ack(
        exact: bytes, contract_ref: OperationContractRef
    ) -> batch_task.BatchTaskSingleDispatchAck:
        try:
            codec = batch_business.build_batch_business_wait_input_codec(contract_ref)
            return codec.decode_payload(json.loads(exact.decode("utf-8")))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise BatchBusinessReadbackError(
                "business wait ACK input is malformed"
            ) from exc


class _BatchBusinessReadbackAdapter:
    """Bridge the exact request readback into the generic reconciler contract."""

    def __init__(
        self,
        *,
        facade: BatchTaskBusinessRecoveryReadback,
        request: BatchBusinessReadbackRequest,
        expected: EffectAttemptObservation,
    ) -> None:
        self.interpreter_id = facade.interpreter_id
        self.interpreter_version = facade.interpreter_version
        self.provider_id = facade.provider_id
        self.provider_version = facade.provider_version
        self._facade = facade
        self._request = request
        self._expected = expected
        self.result: batch_business.BatchBusinessResult | None = None

    def readback(
        self, attempt: EffectAttemptObservation
    ) -> AuthoritativeEffectReadback:
        if attempt != self._expected:
            raise BatchBusinessReadbackError(
                "reconciler changed the exact original-attempt observation"
            )
        observed = self._facade.readback_exact(self._request)
        if isinstance(observed, BatchBusinessReadback):
            self.result = observed.result
            return observed.readback
        return observed

    def prove_not_started(
        self, attempt: EffectAttemptObservation
    ) -> NonStartProof | BatchBusinessNonStartUnprovable:
        if attempt != self._expected:
            raise BatchBusinessReadbackError(
                "reconciler changed the exact original-attempt observation"
            )
        return self._facade.prove_not_started(self._request)


class BusinessResultPublisher(Protocol):
    """Publish the precise typed business result on a resolved success."""

    def publish(
        self,
        connection: Connection,
        assignment: RuntimeAssignment,
        scope: RuntimeScope,
        result: batch_business.BatchBusinessResult,
    ) -> str: ...


class PostgresBusinessResultPublisher:
    """Persist the typed business result through the shared activation adapter."""

    def publish(
        self,
        connection: Connection,
        assignment: RuntimeAssignment,
        scope: RuntimeScope,
        result: batch_business.BatchBusinessResult,
    ) -> str:
        contract_ref = assignment.operation_contract_ref
        if contract_ref is None:
            raise BatchBusinessReadbackError(
                "business wait assignment lacks operation contract"
            )
        tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
        adapter = PostgresFirstSpecimenActivationBindingAdapter()
        codec = batch_business.build_batch_business_wait_result_codec(
            contract_ref
        )
        content = canonical_json(codec.encode_payload(result)).encode("utf-8")
        return adapter.publish_output(
            connection, assignment, scope, tables, content=content
        )


class BatchBusinessWaitHandler(
    PersistentOperationHandler[
        batch_task.BatchTaskSingleDispatchAck, batch_business.BatchBusinessResult
    ]
):
    """INTERPRET wait kernel: reads the ACK via the shared adapter, publishes
    the precise typed business result, and never redispaches the item."""

    def __init__(
        self,
        *,
        uow_factory: UowFactory,
        binding: InterpreterBinding,
        invoke: Callable[[batch_task.BatchTaskSingleDispatchAck], batch_business.BatchBusinessResult],
    ) -> None:
        contract = batch_business.build_batch_business_wait_contract()
        super().__init__(
            uow_factory=uow_factory,
            binding=binding,
            contract=contract,
            input_codec=batch_business.build_batch_business_wait_input_codec(
                contract.ref
            ),
            output_codec=batch_business.build_batch_business_wait_result_codec(
                contract.ref
            ),
            invoke=invoke,
            validate_output=self._check_result,
        )

    @staticmethod
    def _check_result(
        ack: batch_task.BatchTaskSingleDispatchAck,
        result: batch_business.BatchBusinessResult,
    ) -> None:
        if result.task_id != ack.celery_task_id:
            raise ValueError("business wait result does not bind the dispatched task")


class PostgresBatchTaskBusinessReadbackHandler:
    """Read back one broker business result; it never redispaches the item."""

    handler_binding_digest: str
    interpreter_profile_digest: str | None

    def __init__(
        self,
        installation: InstalledBatchTaskBusinessReadbackHandler,
        uow_factory: ReconciliationUnitOfWorkFactory,
        *,
        readback: BatchTaskBusinessRecoveryReadback,
        replay: BatchBusinessReadbackReplayPort | None = None,
        publisher: BusinessResultPublisher | None = None,
    ) -> None:
        if (
            readback.operation_contract_ref.contract_digest
            != installation.operation_contract_digest
            or readback.operation_contract_ref.kind != batch_business.BUSINESS_WAIT_KIND
        ):
            raise ValueError("recovery readback operation contract drift")
        self.installation = installation
        self.handler_binding_digest = installation.handler_binding_digest
        self.interpreter_profile_digest = installation.interpreter_profile_digest
        self.operation_contract_digest = installation.operation_contract_digest
        self._uow_factory = uow_factory
        self._readback = readback
        self._replay = replay or PostgresBatchBusinessReadbackReplay()
        self._publisher = publisher or PostgresBusinessResultPublisher()
        self._reconciler = EffectReconciler()

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> ReconciliationHandlerOutcome:
        self._require_exact_recovery_assignment(assignment, claim)
        with self._uow_factory() as uow:
            original_assignment, original_claim = _load_exact_original_graph(
                uow.connection,
                assignment,
                interpreter_profile_digest=self.installation.interpreter_profile_digest,
            )
            replay = self._replay.load_exact(
                uow.connection,
                self.installation,
                original_assignment,
                original_claim,
                context,
            )
            request = replay.request
            binding = original_assignment.handler_binding
            assert isinstance(binding, InterpreterBinding)
            observation = EffectAttemptObservation(
                attempt_id=original_claim.attempt_id,
                assignment_digest=original_assignment.assignment_digest,
                handler_binding_digest=original_assignment.handler_binding_digest,
                interpreter_profile_digest=binding.interpreter_profile_digest,
                interpreter_id=self._readback.interpreter_id,
                interpreter_version=self._readback.interpreter_version,
                provider_id=self._readback.provider_id,
                provider_version=self._readback.provider_version,
                external_idempotency_key=request.external_idempotency_key,
                authoritative_readback_locator=self._readback.readback_locator(request),
            )
            adapter = _BatchBusinessReadbackAdapter(
                facade=self._readback, request=request, expected=observation
            )
            result = self._reconciler.reconcile(
                assignment=assignment, attempt=observation, interpreter=adapter
            )
            if result.state is ReconciliationState.WAITING:
                return ReconciliationHandlerOutcome(result=result)
            if result.disposition is EffectDisposition.FAILED:
                return ReconciliationHandlerOutcome(result=result)
            if (
                result.state is not ReconciliationState.RESOLVED
                or result.disposition is not EffectDisposition.SUCCEEDED
                or result.readback is None
                or adapter.result is None
            ):
                raise BatchBusinessReadbackError(
                    "batch business readback produced an unsupported reconciliation state"
                )
            business_result = adapter.result
            if business_result.receipt_digest != result.readback.receipt_digest:
                raise BatchBusinessReadbackError(
                    "reconstructed business result/readback receipt drift"
                )
            published_digest = self._publish_result(
                uow.connection, original_assignment, replay.scope, business_result
            )
            uow.commit()
            return ReconciliationHandlerOutcome(
                result=result,
                output_digest=published_digest,
                receipt_ref=f"receipt:sha256:{published_digest}",
            )

    def _publish_result(
        self,
        connection: Connection,
        original: RuntimeAssignment,
        scope: RuntimeScope,
        result: batch_business.BatchBusinessResult,
    ) -> str:
        return self._publisher.publish(connection, original, scope, result)

    def _require_exact_recovery_assignment(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
    ) -> None:
        claim.validate_against(assignment)
        binding = assignment.handler_binding
        installed = self.installation.recovery_binding
        if (
            assignment.assignment_kind is not AssignmentKind.RECONCILE
            or not isinstance(binding, RecoveryBinding)
            or binding != installed
            or binding.binding_digest != self.handler_binding_digest
            or binding.recovery_handler_id != installed.recovery_handler_id
            or binding.recovery_handler_version != installed.recovery_handler_version
            or binding.authoritative_readback_profile_ref
            != installed.authoritative_readback_profile_ref
            or binding.interpreter_profile_digest != self.interpreter_profile_digest
            or assignment.operation_contract_digest != self.operation_contract_digest
            or assignment.operation_contract_ref
            != self._readback.operation_contract_ref
            or claim.interpreter_profile_digest != self.interpreter_profile_digest
            or assignment.reconciliation_attempt_id is None
        ):
            raise BatchBusinessReadbackError(
                "exact RecoveryBinding/readback/original-profile drift"
            )
