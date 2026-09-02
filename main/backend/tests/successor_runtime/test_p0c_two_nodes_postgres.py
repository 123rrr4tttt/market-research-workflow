"""Two isomorphic RuntimeNodes over the real PostgreSQL claim/lifecycle path."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest
import sqlalchemy as sa

from app.successor_runtime.capabilities import (
    build_first_specimen_bundle,
    build_first_specimen_catalog,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.first_specimen import CanonicalReadInput
from app.successor_runtime.capabilities.first_specimen_interpreters import (
    CapturedDocumentValue,
    FirstSpecimenInterpreters,
    InterpreterSuccess,
)
from app.successor_runtime.language.catalog import OperationContractRegistry
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.research.artifacts import ResearchArtifact
from app.successor_runtime.research.codec import canonical_bytes, dataclass_to_json
from app.successor_runtime.research.object_types import RESEARCH_ARTIFACT_TYPE
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    QualificationBinding,
    RecoveryBinding,
    ReturnContractBinding,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.authority_grants import (
    AuthorityOperationScope,
    AuthorityResourceCeiling,
    AuthorityResourceLimit,
)
from app.successor_runtime.runtime.node import (
    ClaimRunState,
    DeploymentBinding,
    InterpreterOutcome,
    NodeIdentity,
    RuntimeExecutionContext,
    RuntimeNode,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
)
from app.successor_runtime.runtime.ports import (
    RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
    ControlPlaneScope,
)
from app.successor_runtime.runtime.qualification import (
    QualifiedPlan,
    StepAuthorizationBinding,
)
from app.successor_runtime.runtime.resources import QueueEligibility, ResourceClass
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.postgres.authority import (
    AuthorityGrant,
    AuthorityGrantRepository,
)
from app.successor_runtime.substrate.postgres.authority_provider import (
    PostgresAuthorityProvider,
)
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.node_adapter import (
    PostgresRuntimeNodeAdapter,
    runtime_uow_factory,
)
from app.successor_runtime.substrate.postgres.nodes import (
    DeploymentCatalog,
    DeploymentCatalogRepository,
    RuntimeNodeRepository,
)
from app.successor_runtime.substrate.postgres.plans import PlanRepository
from app.successor_runtime.substrate.postgres.qualification_store import (
    QualificationStoreRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactQualificationBinding,
    RuntimeJournalRepository,
)
from app.successor_runtime.substrate.postgres.runtime_lifecycle import (
    ActivateQualification,
    AssignmentEnvelope,
    AttachPlan,
    RuntimeLifecycleRepository,
    _assignment_values,
)
from app.successor_runtime.substrate.postgres.runtime_values import (
    RuntimeValueBinding,
    RuntimeValueRepository,
)
from app.successor_runtime.substrate.postgres.staged_artifacts import (
    StagedArtifactBinding,
    StagedArtifactRepository,
)
from app.successor_runtime.substrate.postgres.values import ValueRepository
from app.successor_runtime.substrate.postgres.work_items import (
    WorkItemClaimRepository,
)

from .p0c_postgres_fixture import (
    CLAIM_POLICY_DIGEST,
    DEPLOYMENT_CATALOG_DIGEST,
    NOW,
    PROJECT_INCARNATION,
    PROJECT_KEY,
    PROJECT_REGISTRY_REVISION,
    PROJECT_SCOPE_DIGEST,
    RESOURCE_POLICY_DIGEST,
    LiveP0CDatabase,
    live_p0c_database,
    p0c_database,
    submission_command,
)

pytestmark = pytest.mark.integration

NODE_PROFILE_DIGEST = hashlib.sha256(b"p0c-isomorphic-node-profile").hexdigest()
SECURITY_PROFILE_DIGEST = hashlib.sha256(b"p0c-security-profile").hexdigest()
RESOURCE_PROFILE_DIGEST = hashlib.sha256(b"p0c-resource-profile").hexdigest()
AUTHORITY_REQUIREMENT_DIGEST = hashlib.sha256(b"p0c-authority-requirement").hexdigest()
CAPABILITY_ID = "material.first_specimen.v1"
AUTHORITY_EPOCH = 7
RESOURCE_POLICY_EPOCH = 8


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class _PreparedNodeSpecimen:
    assignments: tuple[RuntimeAssignment, RuntimeAssignment]
    handler: "_MaterialReadHandler"
    interpreter_profile_digest: str


class _MaterialReadHandler:
    def __init__(
        self,
        *,
        handler_binding_digest: str,
        interpreter_profile_digest: str,
        payloads: dict[str, tuple[CanonicalReadInput, CapturedDocumentValue, Any]],
    ) -> None:
        self.handler_binding_digest = handler_binding_digest
        self.interpreter_profile_digest = interpreter_profile_digest
        self.payloads = payloads
        self.executions: list[tuple[str, str, str]] = []
        self.interpreters = FirstSpecimenInterpreters()

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: object,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        assert getattr(claim, "assignment_digest") == assignment.assignment_digest
        payload, captured, expected = self.payloads[assignment.step_id or ""]
        result = self.interpreters.read_canonical_ref(payload, captured)
        assert isinstance(result, InterpreterSuccess)
        assert result.value == expected
        assert result.value.content_digest is not None
        self.executions.append(
            (
                context.node.node_id,
                assignment.step_id or "",
                getattr(claim, "attempt_id"),
            )
        )
        return InterpreterOutcome.succeeded(result.value.content_digest)


class _ExactResolver:
    def __init__(self, handler: _MaterialReadHandler) -> None:
        self.handler = handler

    def resolve_exact(
        self,
        *,
        assignment: RuntimeAssignment,
        handler_binding_digest: str,
    ) -> _MaterialReadHandler:
        assert handler_binding_digest == assignment.handler_binding_digest
        assert handler_binding_digest == self.handler.handler_binding_digest
        return self.handler


class _DatabaseGuard:
    def __init__(self, database: LiveP0CDatabase) -> None:
        self.database = database

    def require_not_cancelled(self, *, claim: object, observed_at: object) -> None:
        del observed_at
        assignment = getattr(claim, "assignment")
        with self.database.engine.connect() as connection:
            cancelled = connection.scalar(
                sa.select(sa.text("cancellation_requested"))
                .select_from(sa.text("public.runtime_runs"))
                .where(sa.text("project_key=:project_key AND run_id=:run_id"))
                .params(project_key=assignment.project_key, run_id=assignment.run_id)
            )
        if cancelled:
            raise RuntimeError("run cancellation is current")

    def require_current_authority(
        self,
        *,
        claim: object,
        expected_authority_digest: str,
        expected_authority_epoch: int,
        observed_at: object,
    ) -> None:
        assignment = getattr(claim, "assignment")
        with self.database.engine.connect() as connection:
            row = (
                connection.execute(
                    sa.text(
                        "SELECT a.authorization_digest, a.expires_at, "
                        "c.authority_epoch, c.successor_claim_enabled, "
                        "c.legacy_claim_enabled "
                        "FROM public.runtime_step_authorizations a "
                        "JOIN public.runtime_capability_authority c "
                        "ON c.project_key=a.project_key "
                        "AND c.capability_id=a.capability_id "
                        "WHERE a.project_key=:project_key AND a.run_id=:run_id "
                        "AND a.step_id=:step_id"
                    ),
                    {
                        "project_key": assignment.project_key,
                        "run_id": assignment.run_id,
                        "step_id": assignment.step_id,
                    },
                )
                .mappings()
                .one()
            )
        if (
            row["authorization_digest"] != expected_authority_digest
            or int(row["authority_epoch"]) != expected_authority_epoch
            or not row["successor_claim_enabled"]
            or row["legacy_claim_enabled"]
            or row["expires_at"] <= observed_at
        ):
            raise RuntimeError("current authority drift")


class _TickClock:
    def __init__(self, start: Any) -> None:
        self.current = start

    def now(self) -> Any:
        observed = self.current
        self.current = observed + timedelta(milliseconds=10)
        return observed


def _payload(cls: type, **values: object) -> Any:
    return cls(**values, payload_digest=content_digest(values))


def _prepare_execution(database: LiveP0CDatabase) -> _PreparedNodeSpecimen:
    command = submission_command()
    submitted = database.submission_service().submit(command)
    bundle = build_first_specimen_bundle()
    catalog = build_first_specimen_catalog(bundle.operations)
    registry = OperationContractRegistry(catalog, bundle.operations)
    plan = compile_program(
        submitted.program,
        catalog,
        operation_contracts=registry,
        transform_registry=command.registries.transforms,
        merge_registry=command.registries.merges,
        discriminator_registry=command.registries.discriminators,
    )
    capture_by_label = {
        "material.read.source.a": submitted.captures[0],
        "material.read.source.b": submitted.captures[1],
    }
    contracts = {operation.ref.kind: operation for operation in bundle.operations}
    bindings: dict[str, InterpreterBinding] = {}
    for kind, contract in contracts.items():
        profile = contract.interpreter_compatibility_ref
        bindings[kind] = InterpreterBinding.from_content(
            operation_contract_digest=contract.ref.contract_digest,
            interpreter_profile_digest=profile.profile_digest,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            runtime_protocol_version="1",
            project_scope_digest=PROJECT_SCOPE_DIGEST,
            resource_policy_epoch=RESOURCE_POLICY_EPOCH,
            authority_requirement_digest=AUTHORITY_REQUIREMENT_DIGEST,
        )

    authorizable = tuple(
        step
        for step in plan.ordered_steps
        if step.step_kind in {"EFFECT", "ADMISSION"}
        and step.operation_contract_ref is not None
    )
    eligibility_by_step: dict[str, QueueEligibility] = {}
    for step in authorizable:
        assert step.operation_contract_ref is not None
        contract = contracts[step.operation_contract_ref.kind]
        eligibility = QueueEligibility(
            project_key=PROJECT_KEY,
            capability_id=contract.owner_capability_id,
            resource_class=ResourceClass.CPU_LIGHT,
            units=1,
            policy_epoch=RESOURCE_POLICY_EPOCH,
            policy_digest=RESOURCE_POLICY_DIGEST,
            concurrency_key=f"p0c:{step.step_id}",
        )
        eligibility_by_step[step.step_id] = eligibility

    with database.engine.begin() as connection:
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_capability_authority"]).values(
                project_key=PROJECT_KEY,
                capability_id=CAPABILITY_ID,
                mode="canary",
                authority_epoch=AUTHORITY_EPOCH,
                successor_claim_enabled=True,
                legacy_claim_enabled=False,
                allowlist_digest=_digest("p0c-allowlist"),
                config_digest=_digest("p0c-capability-config"),
                effective_at=NOW,
                updated_by=database.scope.actor_id,
                approval_ref="approval:p0c-canary",
                rollback_target_ref="canonical:legacy-document-read-only",
                revision=0,
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_resource_policies"]).values(
                resource_policy_id="policy:p0c-material",
                project_key=PROJECT_KEY,
                capability_id=CAPABILITY_ID,
                resource_class="CPU_LIGHT",
                concurrency_limit=2,
                max_project_active=2,
                max_capability_active=2,
                max_resource_active=2,
                units_ceiling=2,
                provider_limit=None,
                policy_epoch=RESOURCE_POLICY_EPOCH,
                policy_digest=RESOURCE_POLICY_DIGEST,
                revision=0,
            )
        )
        AuthorityGrantRepository(connection, database.scope).create(
            AuthorityGrant(
                grant_id="grant:p0c-material",
                actor_id=database.scope.actor_id,
                capability_id=CAPABILITY_ID,
                operation_scope_json=AuthorityOperationScope.from_content(
                    operation_kinds=("material.read_canonical_ref.v1",),
                    project_scope_digest=PROJECT_SCOPE_DIGEST,
                ),
                resource_ceiling_json=AuthorityResourceCeiling.from_content(
                    limits=(
                        AuthorityResourceLimit(
                            resource_class=ResourceClass.CPU_LIGHT.value,
                            units=2,
                        ),
                    ),
                    max_active=2,
                ),
                credential_ref=None,
                grant_epoch=1,
                expires_at=NOW + timedelta(days=1),
            )
        )
        authority_context = PostgresAuthorityProvider(
            connection,
            database.scope,
        ).current_context(
            database.scope.actor_id,
            capability_id=CAPABILITY_ID,
            canonical_base_revision=0,
            canonical_incarnation=PROJECT_INCARNATION,
            now=NOW,
        )

    authorizations: list[StepAuthorizationBinding] = []
    for step in authorizable:
        assert step.operation_contract_ref is not None
        contract = contracts[step.operation_contract_ref.kind]
        eligibility = eligibility_by_step[step.step_id]
        authorizations.append(
            StepAuthorizationBinding.from_content(
                run_id=command.run_id,
                step_id=step.step_id,
                operation_kind=step.operation_contract_ref.kind,
                operation_contract_digest=step.operation_contract_ref.contract_digest,
                capability_id=contract.owner_capability_id,
                claim_owner="successor",
                claim_authority_epoch=AUTHORITY_EPOCH,
                claim_policy_digest=CLAIM_POLICY_DIGEST,
                payload_digest=_digest(f"payload:{step.step_id}"),
                actor_id=database.scope.actor_id,
                project_key=PROJECT_KEY,
                project_registry_revision=PROJECT_REGISTRY_REVISION,
                project_scope_digest=PROJECT_SCOPE_DIGEST,
                interpreter_binding_digest=bindings[
                    step.operation_contract_ref.kind
                ].binding_digest,
                deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                authority_source_bindings=authority_context.authority_source_bindings,
                grants_digest=authority_context.grants_digest,
                approval_refs=(),
                resource_ceiling_digest=authority_context.resource_ceiling_digest,
                resource_policy_epoch=RESOURCE_POLICY_EPOCH,
                queue_eligibility_digest=eligibility.eligibility_digest,
                grant_epoch=1,
                expires_at=authority_context.expires_at,
                canonical_base_revision=0,
                canonical_incarnation=PROJECT_INCARNATION,
            )
        )
    qualified = QualifiedPlan.from_content(
        plan_digest=plan.plan_digest,
        authority_context_digest=authority_context.context_digest,
        step_bindings=tuple(authorizations),
    )
    exact_qualification = ExactQualificationBinding.from_content(
        qualification_id="qualification:p0c:execution-plan",
        project_key=PROJECT_KEY,
        run_id=command.run_id,
        plan_id=plan.plan_id,
        plan_digest=plan.plan_digest,
        authority_context=authority_context,
        authority_context_digest=authority_context.context_digest,
        qualified_plan=qualified,
        decision="QUALIFIED",
    )

    qualification_handler = QualificationBinding.from_content(
        authority_reader_id="p0c-authority-reader",
        authority_reader_version="1.0.0",
        authority_reader_digest=_digest("p0c-authority-reader"),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
    )
    qualify_assignment = RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id=f"{command.run_id}:qualify",
        assignment_kind=AssignmentKind.QUALIFY,
        project_key=PROJECT_KEY,
        run_id=command.run_id,
        capability_id="mrw.first-specimen.qualify",
        handler_binding_kind=HandlerBindingKind.QUALIFICATION,
        handler_binding_ref=(
            f"handler-binding:sha256:{qualification_handler.binding_digest}"
        ),
        handler_binding_digest=qualification_handler.binding_digest,
        handler_binding=qualification_handler,
        program_digest=submitted.program.program_digest,
        plan_digest=plan.plan_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        execution_epoch=0,
        incarnation=command.run_incarnation,
        queue_eligibility_digest=_digest("p0c-qualify-eligibility"),
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        claim_authority_epoch=AUTHORITY_EPOCH,
        claim_policy_digest=CLAIM_POLICY_DIGEST,
        trace_id="trace:p0c:qualify",
    )

    step_input_digest: dict[str, str] = {}
    for step in authorizable:
        capture = capture_by_label.get(step.operation_id or "")
        step_input_digest[step.step_id] = (
            canonical_digest((capture.snapshot_value_ref.storage_ref,))
            if capture is not None
            else _digest(f"input:{step.step_id}")
        )

    with database.engine.begin() as connection:
        RuntimeJournalRepository(connection, database.scope).append_transition(
            run_id=command.run_id,
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(
                {
                    "event_type": "CompileSucceeded",
                    "schema_version": "mrw.runtime.event.compile-succeeded.v1",
                    "event_metadata_json": {"plan_digest": plan.plan_digest},
                    "authority_digest": command.submission_authority_digest,
                },
            ),
        )
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_work_items"])
            .where(
                PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                == submitted.compile_assignment.work_item_id
            )
            .values(state="COMPLETED", revision=1)
        )
        PlanRepository(connection, database.project_tables).put_exact(
            database.scope,
            plan,
            plan.plan_digest,
            operation_catalog_id=catalog.catalog_id,
            catalog_version=catalog.catalog_version,
            catalog_digest=catalog.catalog_digest,
        )
        lifecycle = RuntimeLifecycleRepository(connection, database.scope)
        lifecycle.attach_plan(
            AttachPlan(
                run_id=command.run_id,
                expected_run_revision=1,
                plan_id=plan.plan_id,
                plan_digest=plan.plan_digest,
                program_id=plan.program_id,
                program_digest=plan.program_digest,
                project_storage_ref=f"project-value:plan:{plan.plan_id}",
                compiler_id=plan.compiler_id,
                compiler_version=plan.compiler_version,
                operation_catalog_id=catalog.catalog_id,
                catalog_version=catalog.catalog_version,
                catalog_digest=catalog.catalog_digest,
                effect_closure_digest=plan.effect_closure_digest,
                authority_closure_digest=plan.authority_closure_digest,
                resource_closure_digest=plan.resource_closure_digest,
                qualify_work=AssignmentEnvelope(
                    assignment=qualify_assignment,
                    required_node_profile_selector=NODE_PROFILE_DIGEST,
                    authority_digest=authority_context.context_digest,
                    resource_policy_digest=RESOURCE_POLICY_DIGEST,
                    fairness_key=PROJECT_KEY,
                ),
                due_at=NOW,
            )
        )
        for step in authorizable:
            assert step.operation_contract_ref is not None
            eligibility = eligibility_by_step[step.step_id]
            contract = contracts[step.operation_contract_ref.kind]
            connection.execute(
                sa.insert(PUBLIC_TABLES["runtime_steps"]).values(
                    project_key=PROJECT_KEY,
                    run_id=command.run_id,
                    step_id=step.step_id,
                    operation_id=step.operation_id,
                    operation_kind=step.operation_contract_ref.kind,
                    operation_version=step.operation_contract_ref.contract_version,
                    state="READY",
                    revision=0,
                    execution_epoch=0,
                    input_digest=step_input_digest[step.step_id],
                    effect_class="LOCAL_SUCCESSOR_NATIVE",
                    resource_class=eligibility.resource_class.value,
                    concurrency_key=eligibility.concurrency_key,
                    capability_id=contract.owner_capability_id,
                    claim_owner="successor",
                    claim_authority_epoch=AUTHORITY_EPOCH,
                    claim_policy_digest=CLAIM_POLICY_DIGEST,
                    attempt_count=0,
                    max_attempts=2,
                )
            )
        QualificationStoreRepository(connection, database.scope).persist(
            exact_qualification
        )
        lifecycle.activate_qualification(
            ActivateQualification(
                run_id=command.run_id,
                expected_run_revision=2,
                binding=exact_qualification,
            )
        )
        connection.execute(
            sa.text(
                "UPDATE public.runtime_work_items SET state='COMPLETED', "
                "revision=1 WHERE work_item_id=:work_item_id"
            ),
            {"work_item_id": qualify_assignment.work_item_id},
        )

        DeploymentCatalogRepository(connection).put_exact(
            DeploymentCatalog(
                catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                catalog_version="1.0.0",
                catalog_ref="artifact:p0c-deployment-catalog",
                node_profile_digest=NODE_PROFILE_DIGEST,
                security_profile_digest=SECURITY_PROFILE_DIGEST,
                resource_profile_digest=RESOURCE_PROFILE_DIGEST,
            )
        )
        nodes = RuntimeNodeRepository(connection)
        for node_id in ("p0c-node-a", "p0c-node-b"):
            nodes.register(
                node_id=node_id,
                node_profile_digest=NODE_PROFILE_DIGEST,
                deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                runtime_protocol_version="1",
                started_at=NOW - timedelta(minutes=1),
            )
        reads = tuple(
            step
            for step in plan.ordered_steps
            if step.operation_id in {"material.read.source.a", "material.read.source.b"}
        )
        assignments: list[RuntimeAssignment] = []
        payloads: dict[str, tuple[CanonicalReadInput, CapturedDocumentValue, Any]] = {}
        authorization_by_step = {item.step_id: item for item in authorizations}
        read_binding = bindings["material.read_canonical_ref.v1"]
        recovery = RecoveryBinding.from_content(
            recovery_handler_id="p0c-material-readback",
            recovery_handler_version="1.0.0",
            interpreter_profile_digest=read_binding.interpreter_profile_digest,
            authoritative_readback_profile_ref="captured-material-runtime-input",
        )
        for step in reads:
            assert step.operation_contract_ref is not None
            assert step.return_contract_ref is not None
            capture = capture_by_label[step.operation_id or ""]
            input_refs = (capture.snapshot_value_ref.storage_ref,)
            input_digest = step_input_digest[step.step_id]
            eligibility = eligibility_by_step[step.step_id]
            assignment = RuntimeAssignment(
                runtime_protocol_version="1",
                work_item_id=f"work:{step.step_id}",
                assignment_kind=AssignmentKind.INTERPRET,
                project_key=PROJECT_KEY,
                run_id=command.run_id,
                step_id=step.step_id,
                step_role=CompiledStepRole.EFFECT,
                capability_id=CAPABILITY_ID,
                operation_contract_ref=step.operation_contract_ref,
                operation_contract_digest=step.operation_contract_ref.contract_digest,
                return_contract_binding=ReturnContractBinding.from_contract(
                    step.return_contract_ref, step.return_contract
                ),
                handler_binding_kind=HandlerBindingKind.INTERPRETER,
                handler_binding_ref=(
                    f"handler-binding:sha256:{read_binding.binding_digest}"
                ),
                handler_binding_digest=read_binding.binding_digest,
                handler_binding=read_binding,
                program_digest=plan.program_digest,
                plan_digest=plan.plan_digest,
                deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                execution_epoch=0,
                incarnation=command.run_incarnation,
                input_refs=input_refs,
                input_closure_digest=input_digest,
                queue_eligibility_digest=eligibility.eligibility_digest,
                resource_policy_epoch=RESOURCE_POLICY_EPOCH,
                claim_authority_epoch=AUTHORITY_EPOCH,
                claim_policy_digest=CLAIM_POLICY_DIGEST,
                expected_step_revision=0,
                trace_id=f"trace:{step.step_id}",
            )
            assignments.append(assignment)
            envelope = AssignmentEnvelope(
                assignment=assignment,
                required_node_profile_selector=NODE_PROFILE_DIGEST,
                authority_digest=authorization_by_step[step.step_id].binding_digest,
                resource_policy_digest=RESOURCE_POLICY_DIGEST,
                fairness_key=PROJECT_KEY,
                qualification_digest=qualified.qualification_digest,
                resource_class=eligibility.resource_class.value,
                resource_units=eligibility.units,
                concurrency_key=eligibility.concurrency_key,
                recovery_binding=recovery,
                authoritative_readback_profile_ref=(
                    recovery.authoritative_readback_profile_ref
                ),
            )
            connection.execute(
                sa.insert(PUBLIC_TABLES["runtime_work_items"]).values(
                    **_assignment_values(envelope, due_at=NOW)
                )
            )
            payloads[step.step_id] = (
                _payload(
                    CanonicalReadInput,
                    source_ref=capture.source_ref.source_ref_id,
                    locator=capture.source_ref.locator,
                    owner_id=capture.source_ref.owner_id,
                    observed_at=capture.source_ref.observed_at.isoformat(),
                ),
                CapturedDocumentValue(
                    exact_bytes=capture.observation.exact_bytes,
                    snapshot=capture.snapshot,
                    exact_bytes_digest=capture.snapshot_value_ref.content_digest,
                ),
                capture.material,
            )

    handler = _MaterialReadHandler(
        handler_binding_digest=bindings[
            "material.read_canonical_ref.v1"
        ].binding_digest,
        interpreter_profile_digest=bindings[
            "material.read_canonical_ref.v1"
        ].interpreter_profile_digest,
        payloads=payloads,
    )
    return _PreparedNodeSpecimen(
        assignments=(assignments[0], assignments[1]),
        handler=handler,
        interpreter_profile_digest=handler.interpreter_profile_digest,
    )


def _node(
    database: LiveP0CDatabase,
    prepared: _PreparedNodeSpecimen,
    node_id: str,
) -> RuntimeNode:
    adapter = PostgresRuntimeNodeAdapter(runtime_uow_factory(database.engine))
    return RuntimeNode(
        identity=NodeIdentity(
            node_id=node_id,
            incarnation=f"{node_id}:incarnation:1",
            started_at=NOW - timedelta(minutes=1),
        ),
        profile=RuntimeNodeProfile(
            profile_digest=NODE_PROFILE_DIGEST,
            supported_assignment_kinds=frozenset({AssignmentKind.INTERPRET}),
            interpreter_profile_digests=frozenset(
                {prepared.interpreter_profile_digest}
            ),
        ),
        deployment=DeploymentBinding(
            catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            node_profile_digest=NODE_PROFILE_DIGEST,
            runtime_protocol_version="1",
        ),
        protocol=RuntimeNodeProtocol(version="1", claim_batch_size=1),
        control_scope=ControlPlaneScope(
            system_actor_id=node_id,
            permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
            authority_epoch=AUTHORITY_EPOCH,
        ),
        claims=adapter,
        interpreters=_ExactResolver(prepared.handler),
        outcomes=adapter,
        cancellation=_DatabaseGuard(database),
        clock=_TickClock(NOW),
    )


def _direct_claim_context(
    prepared: _PreparedNodeSpecimen, node_id: str
) -> dict[str, Any]:
    return {
        "control_scope": ControlPlaneScope(
            system_actor_id=node_id,
            permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
            authority_epoch=AUTHORITY_EPOCH,
        ),
        "node": NodeIdentity(
            node_id=node_id,
            incarnation=f"{node_id}:incarnation:1",
            started_at=NOW - timedelta(minutes=1),
        ),
        "profile": RuntimeNodeProfile(
            profile_digest=NODE_PROFILE_DIGEST,
            supported_assignment_kinds=frozenset({AssignmentKind.INTERPRET}),
            interpreter_profile_digests=frozenset(
                {prepared.interpreter_profile_digest}
            ),
        ),
        "deployment": DeploymentBinding(
            catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            node_profile_digest=NODE_PROFILE_DIGEST,
            runtime_protocol_version="1",
        ),
        "protocol": RuntimeNodeProtocol(version="1", claim_batch_size=1),
        "limit": 1,
        "observed_at": NOW,
    }


def test_a01_cw04_two_isomorphic_nodes_each_execute_one_exact_assignment(
    p0c_database: LiveP0CDatabase,
) -> None:
    prepared = _prepare_execution(p0c_database)
    node_a = _node(p0c_database, prepared, "p0c-node-a")
    node_b = _node(p0c_database, prepared, "p0c-node-b")

    first = node_a.run_once()
    second = node_b.run_once()

    assert type(node_a) is type(node_b) is RuntimeNode
    assert node_a.profile == node_b.profile
    assert node_a.deployment == node_b.deployment
    assert first.claimed == second.claimed == 1
    assert [item.state for item in first.results + second.results] == [
        ClaimRunState.COMMITTED,
        ClaimRunState.COMMITTED,
    ]
    assert [item.disposition for item in first.results + second.results] == [
        EffectDisposition.SUCCEEDED,
        EffectDisposition.SUCCEEDED,
    ]
    assert {node_id for node_id, _, _ in prepared.handler.executions} == {
        "p0c-node-a",
        "p0c-node-b",
    }
    assert {step_id for _, step_id, _ in prepared.handler.executions} == {
        assignment.step_id for assignment in prepared.assignments
    }
    assert len({attempt for _, _, attempt in prepared.handler.executions}) == 2

    with p0c_database.engine.connect() as connection:
        work = (
            connection.execute(
                sa.text(
                    "SELECT work_item_id, state, claim_attempt_id, "
                    "assignment_digest, handler_binding_digest "
                    "FROM public.runtime_work_items WHERE assignment_kind='INTERPRET' "
                    "ORDER BY work_item_id"
                )
            )
            .mappings()
            .all()
        )
        attempts = (
            connection.execute(
                sa.text(
                    "SELECT attempt_id, assignment_digest, handler_binding_digest, "
                    "handler_realization_digest, disposition "
                    "FROM public.runtime_effect_attempts ORDER BY attempt_id"
                )
            )
            .mappings()
            .all()
        )
        reservations = (
            connection.execute(
                sa.text(
                    "SELECT state FROM public.runtime_resource_reservations "
                    "ORDER BY reservation_id"
                )
            )
            .scalars()
            .all()
        )
    assert [row["state"] for row in work] == ["COMPLETED", "COMPLETED"]
    assert [row["disposition"] for row in attempts] == ["SUCCEEDED", "SUCCEEDED"]
    assert all(
        row["assignment_digest"]
        == next(
            item["assignment_digest"]
            for item in work
            if item["claim_attempt_id"] == row["attempt_id"]
        )
        and row["handler_binding_digest"] == row["handler_realization_digest"]
        for row in attempts
    )
    assert reservations == ["RELEASED", "RELEASED"]


def test_backlog_survives_engine_restart_and_stale_node_cannot_claim(
    p0c_database: LiveP0CDatabase,
) -> None:
    prepared = _prepare_execution(p0c_database)
    with p0c_database.engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE public.runtime_nodes SET state='OFFLINE' "
                "WHERE node_id='p0c-node-a'"
            )
        )
    p0c_database.engine.dispose()

    stale = _node(p0c_database, prepared, "p0c-node-a")
    with pytest.raises(Exception, match="node profile/deployment binding mismatch"):
        stale.run_once()

    live = _node(p0c_database, prepared, "p0c-node-b")
    first = live.run_once()
    second = live.run_once()
    assert first.claimed == second.claimed == 1
    assert all(result.committed for result in first.results + second.results)
    with p0c_database.engine.connect() as connection:
        remaining = connection.scalar(
            sa.text(
                "SELECT count(*) FROM public.runtime_work_items "
                "WHERE assignment_kind='INTERPRET' AND state='READY'"
            )
        )
    assert remaining == 0


def test_cw04_two_connections_cannot_hold_one_valid_lease_and_attempt(
    p0c_database: LiveP0CDatabase,
) -> None:
    prepared = _prepare_execution(p0c_database)
    # Leave exactly one INTERPRET item claimable so the two independent
    # adapters contend for the same locked row.
    disabled = prepared.assignments[1].work_item_id
    with p0c_database.engine.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_work_items"])
            .where(PUBLIC_TABLES["runtime_work_items"].c.work_item_id == disabled)
            .values(state="COMPLETED")
        )

    def claim(node_id: str) -> tuple[Any, ...]:
        adapter = PostgresRuntimeNodeAdapter(runtime_uow_factory(p0c_database.engine))
        return adapter.claim_due(**_direct_claim_context(prepared, node_id))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, ("p0c-node-a", "p0c-node-b")))
    assert sorted(len(result) for result in results) == [0, 1]
    winner = next(result[0] for result in results if result)
    assert winner.effect_disposition is EffectDisposition.NOT_STARTED

    with p0c_database.engine.connect() as connection:
        claimed = (
            connection.execute(
                sa.text(
                    "SELECT work_item_id, lease_owner, lease_token, claim_attempt_id, "
                    "claim_binding_digest FROM public.runtime_work_items "
                    "WHERE state='CLAIMED'"
                )
            )
            .mappings()
            .all()
        )
        attempts = (
            connection.execute(
                sa.text(
                    "SELECT attempt_id, assignment_digest, handler_binding_digest, "
                    "handler_realization_digest, disposition "
                    "FROM public.runtime_effect_attempts"
                )
            )
            .mappings()
            .all()
        )
        reservations = (
            connection.execute(
                sa.text(
                    "SELECT attempt_id, lease_token, state "
                    "FROM public.runtime_resource_reservations"
                )
            )
            .mappings()
            .all()
        )
    assert len(claimed) == len(attempts) == len(reservations) == 1
    assert claimed[0]["claim_attempt_id"] == attempts[0]["attempt_id"]
    assert reservations[0]["attempt_id"] == attempts[0]["attempt_id"]
    assert claimed[0]["lease_token"] == reservations[0]["lease_token"]
    assert (
        attempts[0]["handler_binding_digest"]
        == attempts[0]["handler_realization_digest"]
    )


def test_cw05_expired_pre_effect_lease_becomes_unknown_and_never_redispatches(
    p0c_database: LiveP0CDatabase,
) -> None:
    prepared = _prepare_execution(p0c_database)
    with p0c_database.engine.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_work_items"])
            .where(
                PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                == prepared.assignments[1].work_item_id
            )
            .values(state="COMPLETED")
        )
    adapter = PostgresRuntimeNodeAdapter(runtime_uow_factory(p0c_database.engine))
    claimed = adapter.claim_due(**_direct_claim_context(prepared, "p0c-node-a"))
    assert len(claimed) == 1
    attempt_id = claimed[0].claim_binding.attempt_id

    expired_at = NOW + timedelta(minutes=2)
    reaper = ControlPlaneScope(
        system_actor_id="p0c-reaper",
        permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
        authority_epoch=AUTHORITY_EPOCH,
    )
    with p0c_database.engine.begin() as connection:
        reaped = WorkItemClaimRepository(connection).reap_expired(
            reaper, now=expired_at
        )
    assert reaped == (claimed[0].assignment.work_item_id,)

    loser = PostgresRuntimeNodeAdapter(runtime_uow_factory(p0c_database.engine))
    assert loser.claim_due(**_direct_claim_context(prepared, "p0c-node-b")) == ()
    with p0c_database.engine.connect() as connection:
        original = (
            connection.execute(
                sa.text(
                    "SELECT state, wait_reason FROM public.runtime_work_items "
                    "WHERE work_item_id=:work_item_id"
                ),
                {"work_item_id": claimed[0].assignment.work_item_id},
            )
            .mappings()
            .one()
        )
        attempt = (
            connection.execute(
                sa.text(
                    "SELECT disposition FROM public.runtime_effect_attempts "
                    "WHERE attempt_id=:attempt_id"
                ),
                {"attempt_id": attempt_id},
            )
            .mappings()
            .one()
        )
        recovery = (
            connection.execute(
                sa.text(
                    "SELECT state, reconciliation_attempt_id "
                    "FROM public.runtime_work_items "
                    "WHERE assignment_kind='RECONCILE' AND state='READY'"
                )
            )
            .mappings()
            .one()
        )
    assert original == {"state": "WAITING", "wait_reason": "BACKOFF"}
    assert attempt["disposition"] == "OUTCOME_UNKNOWN"
    assert recovery["reconciliation_attempt_id"] == attempt_id


def test_a08_cw08_staged_artifact_reopens_exactly_without_upstream_reexecution(
    p0c_database: LiveP0CDatabase,
) -> None:
    prepared = _prepare_execution(p0c_database)
    node_a = _node(p0c_database, prepared, "p0c-node-a")
    node_b = _node(p0c_database, prepared, "p0c-node-b")
    assert node_a.run_once().results[0].committed
    assert node_b.run_once().results[0].committed
    assert len(prepared.handler.executions) == 2

    materials = tuple(
        payload[2] for _step_id, payload in sorted(prepared.handler.payloads.items())
    )
    markdown = (
        "# Staged P0-C artifact\n\n"
        + "\n".join(f"- `{item.material_ref_id}`" for item in materials)
        + "\n"
    ).encode("utf-8")
    artifact = ResearchArtifact(
        artifact_id="artifact:p0c:cw08",
        content_ref=f"sha256:{hashlib.sha256(markdown).hexdigest()}",
        content_digest=None,
        claim_closure=("claim:p0c:cw08",),
        evidence_relation_closure=("qualification:p0c:cw08",),
        citation_closure=tuple(item.material_ref_id for item in materials),
        format="markdown",
        revision=1,
        lifecycle_state="DRAFT",
    )
    assert artifact.content_digest is not None
    exact = canonical_bytes(dataclass_to_json(artifact, ("content_digest",)))
    assert hashlib.sha256(exact).hexdigest() == artifact.content_digest
    incarnation = "artifact-inc:p0c:cw08"
    project_ref = f"project-value:{artifact.artifact_id}"
    runtime_binding = RuntimeValueBinding(
        value_id=artifact.artifact_id,
        object_type=RESEARCH_ARTIFACT_TYPE.type_id,
        codec_id=RESEARCH_ARTIFACT_TYPE.codec_id,
        content_digest=artifact.content_digest,
        byte_size=len(exact),
        project_value_ref=project_ref,
        storage_digest=_digest(project_ref),
    )
    step_id = prepared.assignments[0].step_id
    assert step_id is not None
    stage = StagedArtifactBinding(
        artifact_id=artifact.artifact_id,
        run_id=prepared.assignments[0].run_id,
        step_id=step_id,
        value_id=artifact.artifact_id,
        qualifier_ref="qualifier:p0c:cw08:pending-verification",
        loss_profile_ref="loss:none",
    )
    with p0c_database.engine.begin() as connection:
        ValueRepository(connection, p0c_database.project_tables).put_exact(
            p0c_database.scope,
            value_id=artifact.artifact_id,
            object_type=RESEARCH_ARTIFACT_TYPE.type_id,
            codec_id=RESEARCH_ARTIFACT_TYPE.codec_id,
            content=exact,
            expected_digest=artifact.content_digest,
            provenance_digest=_digest("artifact:p0c:cw08:provenance"),
            expected_revision=0,
            expected_incarnation=incarnation,
            provenance={"crash_fixture": "CW08"},
        )
        RuntimeValueRepository(connection, p0c_database.scope).put_exact(
            runtime_binding
        )
        staged = StagedArtifactRepository(connection, p0c_database.scope).stage(stage)
        assert staged["state"] == "STAGED"

    p0c_database.engine.dispose()
    with p0c_database.engine.connect() as connection:
        reopened = StagedArtifactRepository(connection, p0c_database.scope).load(
            artifact.artifact_id
        )
        readback = ValueRepository(connection, p0c_database.project_tables).get_exact(
            p0c_database.scope,
            artifact.artifact_id,
            expected_revision=1,
            expected_incarnation=incarnation,
            expected_digest=artifact.content_digest,
        )
    assert reopened["state"] == "STAGED"
    assert reopened["value_id"] == artifact.artifact_id
    assert readback == exact
    assert len(prepared.handler.executions) == 2
