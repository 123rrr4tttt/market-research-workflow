"""Production caller for the human-approved first-specimen DeliveryGate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import MetaData, select
from sqlalchemy.engine import Engine

from app.successor_runtime.capabilities.first_specimen_delivery_gate import (
    DeliveryAssignmentParameters,
    DeliveryGate,
    DeliveryGateCommand,
    DeliveryGateReceipt,
    DeliveryIntentTemplate,
)
from app.successor_runtime.language.object_contracts import (
    build_first_specimen_return_contract_registry,
)
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.runtime.assignments import (
    ReturnContractBinding,
    canonical_digest,
)
from app.successor_runtime.runtime.ports import RuntimeScope

from .approvals import PostgresDeliveryApprovalPort
from .authority_provider import PostgresAuthorityProvider
from .delivery_runtime import (
    PostgresDeliveryRuntimePort,
    build_delivery_runtime_assignment,
)
from .first_specimen_activation import FirstSpecimenActivationCatalog
from .models import PUBLIC_TABLES, project_tables
from .plans import PlanRepository
from .research_ledger import ResearchLedgerRepository, one_mapping
from .runtime_journal import ExactBindingConflict
from .unit_of_work import RuntimeUnitOfWork
from .values import ValueRepository


@dataclass(frozen=True, slots=True)
class FirstSpecimenDeliveryGateRequest:
    scope: RuntimeScope
    run_id: str
    artifact_id: str
    artifact_revision: int
    artifact_incarnation: str
    template: DeliveryIntentTemplate
    value_incarnation: str
    intent_incarnation: str
    now: datetime
    trace_id: str
    deadline_at: datetime | None = None

    def __post_init__(self) -> None:
        if (
            not self.run_id
            or not self.artifact_id
            or self.artifact_revision < 1
            or not self.artifact_incarnation
            or not self.trace_id
        ):
            raise ValueError(
                "delivery gate request requires exact run/artifact/trace identity"
            )
        if self.now.tzinfo is None:
            raise ValueError("delivery gate request time must be timezone-aware")


class PostgresFirstSpecimenDeliveryGate:
    """Derive exact delivery assignment parameters from persisted Run/Plan facts."""

    def __init__(
        self,
        *,
        engine: Engine,
        activation_catalog: FirstSpecimenActivationCatalog,
    ) -> None:
        self.engine = engine
        self.catalog = activation_catalog

    def admit(self, request: FirstSpecimenDeliveryGateRequest) -> DeliveryGateReceipt:
        scope = request.scope
        tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
        gate = DeliveryGate(
            uow_factory=lambda: RuntimeUnitOfWork(engine=self.engine),
            value_port=lambda uow: ValueRepository(uow.connection, tables),
            ledger_port=lambda uow: ResearchLedgerRepository(uow.connection, tables),
            approval_port=lambda uow: PostgresDeliveryApprovalPort(
                uow.connection, scope
            ),
            authority_port=lambda uow: PostgresAuthorityProvider(uow.connection, scope),
            runtime_port=lambda uow: PostgresDeliveryRuntimePort(uow.connection, scope),
            assignment_factory=build_delivery_runtime_assignment,
        )
        artifact, parameters = self._load_exact_request(request)
        return gate.admit(
            DeliveryGateCommand(
                scope=scope,
                template=request.template,
                artifact=artifact,
                artifact_expected_revision=request.artifact_revision,
                artifact_expected_incarnation=request.artifact_incarnation,
                assignment=parameters,
                value_incarnation=request.value_incarnation,
                intent_incarnation=request.intent_incarnation,
                now=request.now,
            )
        )

    def _load_exact_request(
        self, request: FirstSpecimenDeliveryGateRequest
    ) -> tuple[ResearchObjectRef, DeliveryAssignmentParameters]:
        scope = request.scope
        tables = project_tables(MetaData(), scope.project_scope.resolved_schema)
        with self.engine.connect() as connection:
            run = one_mapping(
                connection.execute(
                    select(PUBLIC_TABLES["runtime_runs"]).where(
                        PUBLIC_TABLES["runtime_runs"].c.project_key
                        == scope.project_scope.project_key,
                        PUBLIC_TABLES["runtime_runs"].c.run_id == request.run_id,
                        PUBLIC_TABLES["runtime_runs"].c.project_registry_revision
                        == scope.project_scope.project_registry_revision,
                        PUBLIC_TABLES["runtime_runs"].c.project_scope_digest
                        == scope.project_scope.scope_digest,
                        PUBLIC_TABLES["runtime_runs"].c.resolved_schema
                        == scope.project_scope.resolved_schema,
                    )
                )
            )
            if (
                run is None
                or run["plan_digest"] is None
                or run["qualification_digest"] is None
            ):
                raise ExactBindingConflict("delivery gate requires exact qualified run")
            plan = PlanRepository(connection, tables).get(
                scope, str(run["plan_digest"])
            )
            matches = tuple(
                step
                for step in plan.ordered_steps
                if step.step_kind == "EFFECT"
                and step.operation_contract_ref is not None
                and step.operation_contract_ref.kind == "delivery.internal_export.v1"
            )
            if len(matches) != 1:
                raise ExactBindingConflict("Plan lacks one exact delivery effect step")
            step = matches[0]
            assert step.operation_contract_ref is not None
            if step.return_contract_ref is None:
                raise ExactBindingConflict("delivery step lacks named ReturnContract")
            entry = self.catalog.entry_for(step.operation_contract_ref.contract_digest)
            if not entry.external_gate_required:
                raise ExactBindingConflict(
                    "delivery effect is not bound to external gate"
                )
            step_row = one_mapping(
                connection.execute(
                    select(PUBLIC_TABLES["runtime_steps"]).where(
                        PUBLIC_TABLES["runtime_steps"].c.project_key
                        == scope.project_scope.project_key,
                        PUBLIC_TABLES["runtime_steps"].c.run_id == request.run_id,
                        PUBLIC_TABLES["runtime_steps"].c.step_id == step.step_id,
                    )
                )
            )
            if step_row is None or step_row["state"] != "PENDING":
                raise ExactBindingConflict(
                    "delivery effect is not awaiting its human gate"
                )
            artifact = ResearchLedgerRepository(connection, tables).get_object(
                scope,
                request.artifact_id,
                expected_revision=request.artifact_revision,
                expected_incarnation=request.artifact_incarnation,
            )
            work_digest = canonical_digest(
                {
                    "schema_version": "mrw.first-specimen.delivery-gate-work.v1",
                    "run_id": request.run_id,
                    "step_id": step.step_id,
                    "artifact_id": artifact.object_id,
                    "artifact_revision": artifact.revision,
                    "artifact_digest": artifact.content_digest,
                }
            )
            eligibility = entry.queue_eligibility
            parameters = DeliveryAssignmentParameters(
                runtime_protocol_version=entry.interpreter_binding.runtime_protocol_version,
                work_item_id=f"work:delivery:{work_digest}",
                run_id=request.run_id,
                step_id=step.step_id,
                capability_id=eligibility.capability_id,
                operation_contract_ref=step.operation_contract_ref,
                return_contract_binding=ReturnContractBinding.from_contract(
                    step.return_contract_ref,
                    build_first_specimen_return_contract_registry().resolve_required(
                        step.return_contract_ref
                    ),
                ),
                handler_binding=entry.interpreter_binding,
                recovery_binding=entry.recovery_binding,
                program_digest=str(run["program_digest"]),
                plan_digest=plan.plan_digest,
                deployment_catalog_digest=entry.interpreter_binding.deployment_catalog_digest,
                execution_epoch=int(run["execution_epoch"]),
                incarnation=str(run["incarnation"]),
                queue_eligibility_digest=eligibility.eligibility_digest,
                qualification_digest=str(run["qualification_digest"]),
                required_node_profile_selector=entry.required_node_profile_selector,
                resource_policy_digest=entry.resource_policy_digest,
                fairness_key=entry.fairness_key,
                resource_class=eligibility.resource_class.value,
                resource_units=eligibility.units,
                concurrency_key=eligibility.concurrency_key
                or eligibility.capability_id,
                resource_policy_epoch=eligibility.policy_epoch,
                expected_step_revision=int(step_row["revision"]),
                trace_id=request.trace_id,
                deadline_at=request.deadline_at,
            )
            return artifact, parameters


__all__ = [
    "FirstSpecimenDeliveryGateRequest",
    "PostgresFirstSpecimenDeliveryGate",
]
