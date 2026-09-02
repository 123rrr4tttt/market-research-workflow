"""Real PostgreSQL composition-root proof for the complete first specimen.

The test owns only compile/qualification/deployment bootstrap facts.  Runtime
work is created by ``PostgresFirstSpecimenAssembly.activate_initial`` and all
effects are executed by two ordinary production ``RuntimeNode`` instances.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.successor_runtime.capabilities import (
    build_first_specimen_bundle,
    build_first_specimen_catalog,
)
from app.successor_runtime.capabilities.first_specimen_submission import (
    SubmissionCommand,
)
from app.successor_runtime.language.catalog import OperationContractRegistry
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.language.program import (
    Atom,
    Decide,
    MapOutput,
    ProgramNode,
    Then,
    TraverseOrdered,
    ZipOrdered,
)
from app.successor_runtime.research.artifacts import artifact_identity_ref
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    InterpreterBinding,
    QualificationBinding,
    RecoveryBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.authority_grants import (
    AuthorityOperationScope,
    AuthorityResourceCeiling,
    AuthorityResourceLimit,
)
from app.successor_runtime.runtime.node import (
    DeploymentBinding,
    InterpreterOutcome,
    NodeIdentity,
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
from app.successor_runtime.substrate.blob.internal_export import (
    InternalExportInterpreter,
    InternalExportReadbackUnavailable,
)
from app.successor_runtime.substrate.blob.store import BlobNotFound, ProjectBlobStore
from app.successor_runtime.substrate.postgres.approvals import (
    ApprovalBinding,
    ApprovalRepository,
)
from app.successor_runtime.substrate.postgres.authority import (
    AuthorityGrant,
    AuthorityGrantRepository,
)
from app.successor_runtime.substrate.postgres.authority_provider import (
    PostgresAuthorityProvider,
)
from app.successor_runtime.substrate.postgres.first_specimen_activation import (
    ActivationCatalogEntry,
    FirstSpecimenActivationCatalog,
    PostgresFirstSpecimenActivationBindingAdapter,
    persist_qualification_step_shells,
)
from app.successor_runtime.substrate.postgres.first_specimen_assembly import (
    FirstSpecimenOperationHandler,
    build_postgres_first_specimen_assembly,
)
from app.successor_runtime.substrate.postgres.first_specimen_delivery_gate import (
    FirstSpecimenDeliveryGateRequest,
)
from app.successor_runtime.substrate.postgres.first_specimen_handlers import (
    InstalledFirstSpecimenEffectHandler,
    PostgresFirstSpecimenEffectReplay,
)
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.nodes import (
    DeploymentCatalog,
    DeploymentCatalogRepository,
    RuntimeNodeRepository,
)
from app.successor_runtime.substrate.postgres.plans import PlanRepository
from app.successor_runtime.substrate.postgres.qualification_store import (
    QualificationStoreRepository,
)
from app.successor_runtime.substrate.postgres.research_ledger import (
    ResearchLedgerRepository,
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
)
from app.successor_runtime.substrate.postgres.work_items import WorkItemClaimRepository

from .p0c_postgres_fixture import (
    CLAIM_POLICY_DIGEST,
    DELIVERY_AUTHORITY_DIGEST,
    DEPLOYMENT_CATALOG_DIGEST,
    LEGACY_DOCUMENTS,
    NOW,
    PROJECT_KEY,
    PROJECT_REGISTRY_REVISION,
    PROJECT_SCOPE_DIGEST,
    RESOURCE_POLICY_DIGEST,
    SEED_CONTENT_BYTES,
    SEED_CONTENT_SHA256,
    LiveP0CDatabase,
    submission_command,
)

pytestmark = pytest.mark.integration
pytest_plugins = ("tests.successor_runtime.p0c_postgres_fixture",)

NODE_PROFILE_DIGEST = hashlib.sha256(b"p0c-full-chain-node-profile").hexdigest()
SECURITY_PROFILE_DIGEST = hashlib.sha256(b"p0c-full-chain-security").hexdigest()
RESOURCE_PROFILE_DIGEST = hashlib.sha256(b"p0c-full-chain-resource").hexdigest()
AUTHORITY_EPOCH = 7
RESOURCE_POLICY_EPOCH = 8


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _atoms(node: ProgramNode) -> tuple[Atom, ...]:
    found: list[Atom] = []

    def visit(current: ProgramNode) -> None:
        if isinstance(current, Atom):
            found.append(current)
        elif isinstance(current, Then):
            visit(current.first)
            visit(current.second)
        elif isinstance(current, MapOutput):
            visit(current.source)
        elif isinstance(current, ZipOrdered):
            visit(current.left)
            visit(current.right)
        elif isinstance(current, TraverseOrdered):
            visit(current.element_program)
        elif isinstance(current, Decide):
            for branch in current.branches:
                visit(branch.program)

    visit(node)
    return tuple(found)


def _activation_catalog(command: SubmissionCommand) -> FirstSpecimenActivationCatalog:
    bundle = build_first_specimen_bundle()
    entries: list[ActivationCatalogEntry] = []
    for operation in bundle.operations:
        profile = operation.interpreter_compatibility_ref.profile_digest
        authority_requirement = (
            DELIVERY_AUTHORITY_DIGEST
            if operation.ref.kind == "delivery.internal_export.v1"
            else _digest(f"authority:{operation.ref.kind}")
        )
        binding = InterpreterBinding.from_content(
            operation_contract_digest=operation.ref.contract_digest,
            interpreter_profile_digest=profile,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            runtime_protocol_version="1",
            project_scope_digest=PROJECT_SCOPE_DIGEST,
            resource_policy_epoch=RESOURCE_POLICY_EPOCH,
            authority_requirement_digest=authority_requirement,
        )
        recovery = RecoveryBinding.from_content(
            recovery_handler_id=f"readback:{operation.ref.kind}",
            recovery_handler_version="1.0.0",
            interpreter_profile_digest=profile,
            authoritative_readback_profile_ref=f"project-readback:{operation.ref.kind}",
        )
        eligibility = QueueEligibility(
            project_key=PROJECT_KEY,
            capability_id=operation.owner_capability_id,
            resource_class=ResourceClass.CPU_LIGHT,
            units=1,
            policy_epoch=RESOURCE_POLICY_EPOCH,
            policy_digest=RESOURCE_POLICY_DIGEST,
            concurrency_key=f"{PROJECT_KEY}:{operation.ref.kind}",
        )
        entries.append(
            ActivationCatalogEntry(
                operation_contract_digest=operation.ref.contract_digest,
                interpreter_binding=binding,
                recovery_binding=recovery,
                queue_eligibility=eligibility,
                required_node_profile_selector=NODE_PROFILE_DIGEST,
                resource_policy_digest=RESOURCE_POLICY_DIGEST,
                fairness_key=PROJECT_KEY,
                effect_class="LOCAL_SUCCESSOR_NATIVE",
                max_attempts=2,
                external_gate_required=(
                    operation.ref.kind == "delivery.internal_export.v1"
                ),
            )
        )
    registries = command.registries
    return FirstSpecimenActivationCatalog(
        entries=tuple(entries),
        transform_registry=registries.transforms,
        merge_registry=registries.merges,
        discriminator_registry=registries.discriminators,
    )


def _install_control_facts(
    connection: sa.Connection,
    database: LiveP0CDatabase,
    catalog: FirstSpecimenActivationCatalog,
) -> None:
    DeploymentCatalogRepository(connection).put_exact(
        DeploymentCatalog(
            catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            catalog_version="1.0.0",
            catalog_ref="artifact:p0c-full-chain-deployment",
            node_profile_digest=NODE_PROFILE_DIGEST,
            security_profile_digest=SECURITY_PROFILE_DIGEST,
            resource_profile_digest=RESOURCE_PROFILE_DIGEST,
        )
    )
    nodes = RuntimeNodeRepository(connection)
    for node_id in ("p0c-full-node-a", "p0c-full-node-b"):
        nodes.register(
            node_id=node_id,
            node_profile_digest=NODE_PROFILE_DIGEST,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            runtime_protocol_version="1",
            started_at=NOW - timedelta(minutes=1),
        )

    capabilities = sorted(
        {entry.queue_eligibility.capability_id for entry in catalog.entries}
    )
    for capability_id in capabilities:
        operation_kinds = tuple(
            operation.ref.kind
            for operation in build_first_specimen_bundle().operations
            if operation.owner_capability_id == capability_id
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_capability_authority"]).values(
                project_key=PROJECT_KEY,
                capability_id=capability_id,
                mode="canary",
                authority_epoch=AUTHORITY_EPOCH,
                successor_claim_enabled=True,
                legacy_claim_enabled=False,
                allowlist_digest=_digest(f"allowlist:{capability_id}"),
                config_digest=(
                    DELIVERY_AUTHORITY_DIGEST
                    if capability_id == "delivery.first_specimen.v1"
                    else _digest(f"config:{capability_id}")
                ),
                effective_at=NOW,
                updated_by=database.scope.actor_id,
                approval_ref="approval:p0c-full-chain-canary",
                rollback_target_ref="canonical:legacy-read-only",
                revision=0,
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_resource_policies"]).values(
                resource_policy_id=f"policy:{capability_id}",
                project_key=PROJECT_KEY,
                capability_id=capability_id,
                resource_class=ResourceClass.CPU_LIGHT.value,
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
                grant_id=f"grant:p0c-full-chain:{capability_id}",
                actor_id=database.scope.actor_id,
                capability_id=capability_id,
                operation_scope_json=AuthorityOperationScope.from_content(
                    operation_kinds=operation_kinds,
                    project_scope_digest=database.scope.project_scope.scope_digest,
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


def _bootstrap(
    database: LiveP0CDatabase,
):
    command = submission_command(suffix="full-chain")
    submitted = database.submission_service().submit(command)
    bundle = build_first_specimen_bundle()
    operation_catalog = build_first_specimen_catalog(bundle.operations)
    registry = OperationContractRegistry(operation_catalog, bundle.operations)
    plan = compile_program(
        submitted.program,
        operation_catalog,
        operation_contracts=registry,
        transform_registry=command.registries.transforms,
        merge_registry=command.registries.merges,
        discriminator_registry=command.registries.discriminators,
    )
    activation_catalog = _activation_catalog(command)
    entry_by_digest = {
        entry.operation_contract_digest: entry for entry in activation_catalog.entries
    }
    atoms = {
        atom.operation.operation_id: atom for atom in _atoms(submitted.program.root)
    }

    with database.engine.begin() as connection:
        _install_control_facts(connection, database, activation_catalog)
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
            operation_catalog_id=operation_catalog.catalog_id,
            catalog_version=operation_catalog.catalog_version,
            catalog_digest=operation_catalog.catalog_digest,
        )

        steps = tuple(
            step
            for step in plan.ordered_steps
            if step.step_kind in {"EFFECT", "ADMISSION"}
            and step.operation_contract_ref is not None
        )
        contexts = {}
        authorizations = []
        for step in steps:
            assert step.operation_contract_ref is not None
            entry = entry_by_digest[step.operation_contract_ref.contract_digest]
            context = contexts.setdefault(
                entry.queue_eligibility.capability_id,
                PostgresAuthorityProvider(connection, database.scope).current_context(
                    database.scope.actor_id,
                    capability_id=entry.queue_eligibility.capability_id,
                    canonical_base_revision=0,
                    canonical_incarnation=f"canonical:{step.step_id}:incarnation:1",
                    now=NOW,
                ),
            )
            atom = atoms[step.operation_id or ""]
            canonical_incarnation = (
                "inc-1"
                if step.operation_contract_ref.kind == "evidence.qualify.v1"
                else (
                    f"canonical:{command.run_id}:"
                    "artifact.compose_markdown.v1:incarnation:1"
                )
                if step.operation_contract_ref.kind == "delivery.internal_export.v1"
                and step.step_kind == "EFFECT"
                else "delivery-receipt-inc-1"
                if step.operation_contract_ref.kind == "delivery.internal_export.v1"
                else f"canonical:{command.run_id}:{step.operation_contract_ref.kind}:incarnation:1"
            )
            authorizations.append(
                StepAuthorizationBinding.from_content(
                    run_id=command.run_id,
                    step_id=step.step_id,
                    operation_kind=step.operation_contract_ref.kind,
                    operation_contract_digest=step.operation_contract_ref.contract_digest,
                    capability_id=entry.queue_eligibility.capability_id,
                    claim_owner="successor",
                    claim_authority_epoch=AUTHORITY_EPOCH,
                    claim_policy_digest=CLAIM_POLICY_DIGEST,
                    payload_digest=atom.operation.payload_ref.content_digest,
                    actor_id=database.scope.actor_id,
                    project_key=PROJECT_KEY,
                    project_registry_revision=PROJECT_REGISTRY_REVISION,
                    project_scope_digest=PROJECT_SCOPE_DIGEST,
                    interpreter_binding_digest=entry.interpreter_binding.binding_digest,
                    deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                    authority_source_bindings=context.authority_source_bindings,
                    grants_digest=context.grants_digest,
                    resource_ceiling_digest=context.resource_ceiling_digest,
                    resource_policy_epoch=RESOURCE_POLICY_EPOCH,
                    queue_eligibility_digest=entry.queue_eligibility.eligibility_digest,
                    grant_epoch=context.grant_epoch,
                    expires_at=context.expires_at,
                    approval_refs=(
                        (command.delivery_template.approval_ref,)
                        if step.operation_contract_ref.kind
                        == "delivery.internal_export.v1"
                        else ()
                    ),
                    canonical_base_revision=(
                        1
                        if step.operation_contract_ref.kind
                        == "delivery.internal_export.v1"
                        and step.step_kind == "EFFECT"
                        else 0
                    ),
                    canonical_incarnation=canonical_incarnation,
                )
            )

        qualification_context = next(iter(contexts.values()))
        qualified = QualifiedPlan.from_content(
            plan_digest=plan.plan_digest,
            authority_context_digest=qualification_context.context_digest,
            step_bindings=tuple(authorizations),
        )
        exact = ExactQualificationBinding.from_content(
            qualification_id="qualification:p0c:full-chain",
            project_key=PROJECT_KEY,
            run_id=command.run_id,
            plan_id=plan.plan_id,
            plan_digest=plan.plan_digest,
            authority_context=qualification_context,
            authority_context_digest=qualification_context.context_digest,
            qualified_plan=qualified,
            decision="QUALIFIED",
        )
        qualification_handler = QualificationBinding.from_content(
            authority_reader_id="p0c-full-chain-authority-reader",
            authority_reader_version="1.0.0",
            authority_reader_digest=_digest("p0c-full-chain-authority-reader"),
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
            handler_binding_kind="QUALIFICATION",
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
            queue_eligibility_digest=_digest("p0c-full-chain-qualify-eligibility"),
            resource_policy_epoch=RESOURCE_POLICY_EPOCH,
            claim_authority_epoch=AUTHORITY_EPOCH,
            claim_policy_digest=CLAIM_POLICY_DIGEST,
            trace_id="trace:p0c:full-chain:qualify",
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
                operation_catalog_id=operation_catalog.catalog_id,
                catalog_version=operation_catalog.catalog_version,
                catalog_digest=operation_catalog.catalog_digest,
                effect_closure_digest=plan.effect_closure_digest,
                authority_closure_digest=plan.authority_closure_digest,
                resource_closure_digest=plan.resource_closure_digest,
                qualify_work=AssignmentEnvelope(
                    assignment=qualify_assignment,
                    required_node_profile_selector=NODE_PROFILE_DIGEST,
                    authority_digest=qualification_context.context_digest,
                    resource_policy_digest=RESOURCE_POLICY_DIGEST,
                    fairness_key=PROJECT_KEY,
                ),
                due_at=NOW,
            )
        )
        persist_qualification_step_shells(
            connection,
            database.scope,
            run_id=command.run_id,
            plan=plan,
            catalog=activation_catalog,
            authorizations=exact.qualified_plan.step_bindings,
            observed_at=NOW,
        )
        QualificationStoreRepository(connection, database.scope).persist(exact)
        lifecycle.activate_qualification(
            ActivateQualification(
                run_id=command.run_id,
                expected_run_revision=2,
                binding=exact,
            )
        )
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_work_items"])
            .where(
                PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                == qualify_assignment.work_item_id
            )
            .values(state="COMPLETED", revision=1)
        )
    return command, submitted, plan, activation_catalog


class _Clock:
    def __init__(self) -> None:
        self.current = NOW + timedelta(hours=1)

    def now(self):
        result = self.current
        self.current += timedelta(milliseconds=10)
        return result


class _CountingProjectBlobStore(ProjectBlobStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.store_calls = 0

    def store(self, scope: object, data: bytes):  # type: ignore[override]
        self.store_calls += 1
        return super().store(scope, data)  # type: ignore[arg-type]


class _CrashAfterExportInterpreter(InternalExportInterpreter):
    def execute(self, step: object, context: object):  # type: ignore[override]
        super().execute(step, context)
        raise InternalExportReadbackUnavailable(
            "injected crash after internal export before candidate commit"
        )


class _TransientReadbackBlobStore(_CountingProjectBlobStore):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.readback_calls = 0

    def readback(self, scope: object, digest: str):  # type: ignore[override]
        self.readback_calls += 1
        if self.readback_calls == 3:
            raise BlobNotFound("injected temporary authoritative readback outage")
        return super().readback(scope, digest)  # type: ignore[arg-type]


class _OutcomeUnknownAfterLocalEffect:
    def __init__(self, delegate: object) -> None:
        self.delegate = delegate
        self.handler_binding_digest = delegate.handler_binding_digest
        self.interpreter_profile_digest = delegate.interpreter_profile_digest
        self.operation_contract_digest = delegate.operation_contract_digest
        self.calls = 0

    def execute(self, assignment: object, claim: object, context: object):
        self.calls += 1
        outcome = self.delegate.execute(assignment, claim, context)
        assert outcome.disposition is EffectDisposition.SUCCEEDED
        return InterpreterOutcome.outcome_unknown(
            "injected crash after local candidate persistence"
        )


class _CrashAfterRecoveryHandler:
    def __init__(self, delegate: object) -> None:
        self.delegate = delegate
        self.handler_binding_digest = delegate.handler_binding_digest
        self.interpreter_profile_digest = delegate.interpreter_profile_digest
        self.operation_contract_digest = delegate.operation_contract_digest
        self.calls = 0

    def execute(self, assignment: object, claim: object, context: object):
        self.calls += 1
        outcome = self.delegate.execute(assignment, claim, context)
        if self.calls == 1:
            raise RuntimeError(
                "injected crash after admission recovery before runtime adoption"
            )
        return outcome


class _DeterministicFailureHandler:
    def __init__(self, delegate: object) -> None:
        self.handler_binding_digest = delegate.handler_binding_digest
        self.interpreter_profile_digest = delegate.interpreter_profile_digest
        self.operation_contract_digest = delegate.operation_contract_digest
        self.calls = 0

    def execute(self, _assignment: object, _claim: object, _context: object):
        self.calls += 1
        return InterpreterOutcome.failed("INJECTED_DETERMINISTIC_FAILURE")


class _RevokeAuthorityAfterLocalEffect:
    def __init__(self, delegate: object, engine: object, capability_id: str) -> None:
        self.delegate = delegate
        self.engine = engine
        self.capability_id = capability_id
        self.handler_binding_digest = delegate.handler_binding_digest
        self.interpreter_profile_digest = delegate.interpreter_profile_digest
        self.operation_contract_digest = delegate.operation_contract_digest
        self.calls = 0

    def execute(self, assignment: object, claim: object, context: object):
        self.calls += 1
        outcome = self.delegate.execute(assignment, claim, context)
        with self.engine.begin() as connection:
            connection.execute(
                sa.update(PUBLIC_TABLES["runtime_authority_grants"])
                .where(
                    PUBLIC_TABLES["runtime_authority_grants"].c.project_key
                    == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_authority_grants"].c.capability_id
                    == self.capability_id,
                    PUBLIC_TABLES["runtime_authority_grants"].c.revoked_at.is_(None),
                )
                .values(revoked_at=context.observed_at)
            )
        return outcome


def run_full_chain_first_specimen(
    p0c_database: LiveP0CDatabase,
    tmp_path: Path,
    delivery_mode: str,
):
    """Execute the production full chain and return its exact submission command."""
    command, _submitted, plan, catalog = _bootstrap(p0c_database)
    delivery = build_first_specimen_bundle().operation_by_kind(
        "delivery.internal_export.v1"
    )
    crash_delivery = delivery_mode in {
        "delivery-crash",
        "delivery-crash-wait-retry",
        "delivery-reconcile-lease-expiry",
    }
    blob_store = (
        _TransientReadbackBlobStore(tmp_path / "internal-export")
        if delivery_mode == "delivery-crash-wait-retry"
        else _CountingProjectBlobStore(tmp_path / "internal-export")
    )
    delivery_interpreter = (
        _CrashAfterExportInterpreter(
            operation_contract_ref=delivery.ref,
            blob_store=blob_store,
        )
        if crash_delivery
        else InternalExportInterpreter(
            operation_contract_ref=delivery.ref,
            blob_store=blob_store,
        )
    )
    assembly = build_postgres_first_specimen_assembly(
        engine=p0c_database.engine,
        activation_catalog=catalog,
        delivery_interpreter=delivery_interpreter,
    )
    authority_revocation_handler = None
    if delivery_mode == "artifact-authority-revoked":
        artifact_operation = build_first_specimen_bundle().operation_by_kind(
            "artifact.compose_markdown.v1"
        )
        rewritten_authority = []
        for handler in assembly.handlers:
            if (
                handler.operation_contract_digest
                == artifact_operation.ref.contract_digest
            ):
                authority_revocation_handler = _RevokeAuthorityAfterLocalEffect(
                    handler.effect,
                    p0c_database.engine,
                    "artifact.first_specimen.v1",
                )
                rewritten_authority.append(
                    FirstSpecimenOperationHandler(
                        effect=authority_revocation_handler,
                        verify_admit=handler.verify_admit,
                        operation_contract_digest=handler.operation_contract_digest,
                    )
                )
            else:
                rewritten_authority.append(handler)
        assembly = replace(assembly, handlers=tuple(rewritten_authority))
    deterministic_failure_handler = None
    if delivery_mode == "artifact-effect-failed":
        artifact_operation = build_first_specimen_bundle().operation_by_kind(
            "artifact.compose_markdown.v1"
        )
        rewritten_failure = []
        for handler in assembly.handlers:
            if (
                handler.operation_contract_digest
                == artifact_operation.ref.contract_digest
            ):
                deterministic_failure_handler = _DeterministicFailureHandler(
                    handler.effect
                )
                rewritten_failure.append(
                    FirstSpecimenOperationHandler(
                        effect=deterministic_failure_handler,
                        verify_admit=handler.verify_admit,
                        operation_contract_digest=handler.operation_contract_digest,
                    )
                )
            else:
                rewritten_failure.append(handler)
        assembly = replace(assembly, handlers=tuple(rewritten_failure))
    local_crash_handler = None
    admission_crash = delivery_mode in {
        "evidence-admission-crash",
        "claim-admission-crash",
        "admission-crash",
        "admission-recovery-adoption-crash",
        "delivery-admission-crash",
    }
    if delivery_mode == "artifact-crash" or admission_crash:
        crash_kind = {
            "evidence-admission-crash": "evidence.qualify.v1",
            "claim-admission-crash": "claim.form_or_open_gap.v1",
            "delivery-admission-crash": "delivery.internal_export.v1",
        }.get(delivery_mode, "artifact.compose_markdown.v1")
        crash_operation = build_first_specimen_bundle().operation_by_kind(crash_kind)
        rewritten = []
        for handler in assembly.handlers:
            if handler.operation_contract_digest == crash_operation.ref.contract_digest:
                wrapped = (
                    handler.effect
                    if delivery_mode == "artifact-crash"
                    else handler.verify_admit
                )
                assert wrapped is not None
                local_crash_handler = _OutcomeUnknownAfterLocalEffect(wrapped)
                rewritten.append(
                    FirstSpecimenOperationHandler(
                        effect=(
                            local_crash_handler
                            if delivery_mode == "artifact-crash"
                            else handler.effect
                        ),
                        verify_admit=(
                            local_crash_handler
                            if admission_crash
                            else handler.verify_admit
                        ),
                        operation_contract_digest=handler.operation_contract_digest,
                    )
                )
            else:
                rewritten.append(handler)
        assembly = replace(assembly, handlers=tuple(rewritten))
    recovery_crash_handler = None
    if delivery_mode == "admission-recovery-adoption-crash":
        rewritten_recovery = []
        for handler in assembly.recovery_handlers:
            if handler.operation_contract_digest == crash_operation.ref.contract_digest:
                recovery_crash_handler = _CrashAfterRecoveryHandler(handler)
                rewritten_recovery.append(recovery_crash_handler)
            else:
                rewritten_recovery.append(handler)
        assembly = replace(assembly, recovery_handlers=tuple(rewritten_recovery))

    receipt = assembly.activate_initial(
        scope=p0c_database.scope,
        run_id=command.run_id,
        observed_at=NOW + timedelta(hours=1),
    )
    assert receipt.activated_step_ids
    with p0c_database.engine.connect() as connection:
        assert connection.scalar(
            sa.select(sa.func.count())
            .select_from(PUBLIC_TABLES["runtime_work_items"])
            .where(PUBLIC_TABLES["runtime_work_items"].c.assignment_kind == "INTERPRET")
        ) == len(receipt.work_item_ids)
        first_work = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_work_items"]).where(
                    PUBLIC_TABLES["runtime_work_items"].c.assignment_kind == "INTERPRET"
                )
            )
            .mappings()
            .one()
        )
        first_assignment = RuntimeAssignment.model_validate(
            first_work["assignment_binding_json"]
        )
        first_entry = catalog.entry_for(
            first_assignment.operation_contract_digest or ""
        )
        replay_probe = PostgresFirstSpecimenEffectReplay(
            PostgresFirstSpecimenActivationBindingAdapter()
        )
        probe_scope, probe_tables = replay_probe.resolve_scope(
            connection,
            first_assignment,
            actor_id="p0c-full-node-probe",
        )
        replay_probe.load_exact(
            connection,
            InstalledFirstSpecimenEffectHandler.bind(
                operation_kind=first_assignment.operation_contract_ref.kind,
                handler_binding_digest=first_assignment.handler_binding_digest,
                interpreter_profile_digest=(
                    first_entry.interpreter_binding.interpreter_profile_digest
                ),
            ),
            first_assignment,
            probe_scope,
            probe_tables,
        )

    profile_digests = frozenset(
        entry.interpreter_binding.interpreter_profile_digest
        for entry in catalog.entries
    )
    nodes = []
    shared_clock = _Clock()
    for node_id in ("p0c-full-node-a", "p0c-full-node-b"):
        nodes.append(
            assembly.compose_node(
                identity=NodeIdentity(
                    node_id=node_id,
                    incarnation=f"{node_id}:incarnation:1",
                    started_at=NOW - timedelta(minutes=1),
                ),
                profile=RuntimeNodeProfile(
                    profile_digest=NODE_PROFILE_DIGEST,
                    supported_assignment_kinds=frozenset(
                        {
                            AssignmentKind.INTERPRET,
                            AssignmentKind.VERIFY_ADMIT,
                            AssignmentKind.RECONCILE,
                        }
                    ),
                    interpreter_profile_digests=profile_digests,
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
                clock=shared_clock,
            )
        )

    reports = []
    idle = 0
    unknown_local_results = 0
    deterministic_failure_results = 0
    authority_rejection_results = 0
    for turn in range(80):
        report = nodes[turn % 2].run_once()
        reports.append(report)
        if report.claimed:
            idle = 0
            if not report.results[0].committed:
                with p0c_database.engine.connect() as connection:
                    failed_work = (
                        connection.execute(
                            sa.select(PUBLIC_TABLES["runtime_work_items"]).where(
                                PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                                == report.results[0].work_item_id
                            )
                        )
                        .mappings()
                        .one()
                    )
                if (
                    delivery_mode == "artifact-authority-revoked"
                    and report.results[0].failure_code is not None
                    and (
                        "AUTHORITY" in report.results[0].failure_code
                        or "GRANT" in report.results[0].failure_code
                    )
                ):
                    authority_rejection_results += 1
                    break
                if (
                    delivery_mode == "admission-recovery-adoption-crash"
                    and failed_work["assignment_kind"] == "RECONCILE"
                    and recovery_crash_handler is not None
                    and recovery_crash_handler.calls == 1
                ):
                    expired_at = failed_work["lease_expires_at"] + timedelta(seconds=1)
                    with p0c_database.engine.begin() as connection:
                        reaped = WorkItemClaimRepository(connection).reap_expired(
                            ControlPlaneScope(
                                system_actor_id="p0c-full-reaper",
                                permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
                                authority_epoch=AUTHORITY_EPOCH,
                            ),
                            now=expired_at,
                        )
                    assert reaped == (failed_work["work_item_id"],)
                    shared_clock.current = expired_at + timedelta(seconds=1)
                    continue
                pytest.fail(
                    f"{failed_work['assignment_kind']}:"
                    f"{failed_work['operation_contract_digest']}:"
                    f"work={failed_work['state']}@{failed_work['revision']}:"
                    f"claim={report.results[0].state.value}:"
                    f"disposition={report.results[0].disposition.value}:"
                    f"{report.results[0].failure_code}"
                )
            if (
                delivery_mode
                in {
                    "artifact-crash",
                    "evidence-admission-crash",
                    "claim-admission-crash",
                    "admission-crash",
                    "admission-recovery-adoption-crash",
                }
                and report.results[0].disposition.value == "OUTCOME_UNKNOWN"
            ):
                unknown_local_results += 1
                continue
            if (
                delivery_mode == "artifact-effect-failed"
                and report.results[0].disposition.value == "FAILED"
            ):
                deterministic_failure_results += 1
                break
            assert report.results[0].disposition.value == "SUCCEEDED", report
        else:
            idle += 1
            if idle >= 4:
                break
    assert {report.node_id for report in reports if report.claimed} == {
        "p0c-full-node-a",
        "p0c-full-node-b",
    }
    assert any(report.claimed for report in reports)
    if delivery_mode == "artifact-authority-revoked":
        assert authority_rejection_results == 1
        assert authority_revocation_handler is not None
        assert authority_revocation_handler.calls == 1
        with p0c_database.engine.connect() as connection:
            artifact_step = (
                connection.execute(
                    sa.select(PUBLIC_TABLES["runtime_steps"]).where(
                        PUBLIC_TABLES["runtime_steps"].c.project_key == PROJECT_KEY,
                        PUBLIC_TABLES["runtime_steps"].c.run_id == command.run_id,
                        PUBLIC_TABLES["runtime_steps"].c.operation_kind
                        == "artifact.compose_markdown.v1",
                        PUBLIC_TABLES["runtime_steps"].c.state == "RUNNING",
                    )
                )
                .mappings()
                .one()
            )
            attempt = (
                connection.execute(
                    sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                        PUBLIC_TABLES["runtime_effect_attempts"].c.project_key
                        == PROJECT_KEY,
                        PUBLIC_TABLES["runtime_effect_attempts"].c.run_id
                        == command.run_id,
                        PUBLIC_TABLES["runtime_effect_attempts"].c.step_id
                        == artifact_step["step_id"],
                    )
                )
                .mappings()
                .one()
            )
            terminal_event_count = connection.scalar(
                sa.select(sa.func.count())
                .select_from(PUBLIC_TABLES["runtime_events"])
                .where(
                    PUBLIC_TABLES["runtime_events"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_events"].c.run_id == command.run_id,
                    PUBLIC_TABLES["runtime_events"].c.step_id
                    == artifact_step["step_id"],
                    PUBLIC_TABLES["runtime_events"].c.event_type.in_(
                        ("EffectFailed", "OutcomeStaged", "RuntimeValueProduced")
                    ),
                )
            )
        assert attempt["disposition"] == "IN_FLIGHT"
        assert terminal_event_count == 0
        return
    if delivery_mode == "artifact-effect-failed":
        assert deterministic_failure_results == 1
        assert deterministic_failure_handler is not None
        assert deterministic_failure_handler.calls == 1
        with p0c_database.engine.connect() as connection:
            run = (
                connection.execute(
                    sa.select(PUBLIC_TABLES["runtime_runs"]).where(
                        PUBLIC_TABLES["runtime_runs"].c.project_key == PROJECT_KEY,
                        PUBLIC_TABLES["runtime_runs"].c.run_id == command.run_id,
                    )
                )
                .mappings()
                .one()
            )
            failed_step = (
                connection.execute(
                    sa.select(PUBLIC_TABLES["runtime_steps"]).where(
                        PUBLIC_TABLES["runtime_steps"].c.project_key == PROJECT_KEY,
                        PUBLIC_TABLES["runtime_steps"].c.run_id == command.run_id,
                        PUBLIC_TABLES["runtime_steps"].c.operation_kind
                        == "artifact.compose_markdown.v1",
                        PUBLIC_TABLES["runtime_steps"].c.state == "FAILED",
                    )
                )
                .mappings()
                .one()
            )
            attempt = (
                connection.execute(
                    sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                        PUBLIC_TABLES["runtime_effect_attempts"].c.project_key
                        == PROJECT_KEY,
                        PUBLIC_TABLES["runtime_effect_attempts"].c.run_id
                        == command.run_id,
                        PUBLIC_TABLES["runtime_effect_attempts"].c.step_id
                        == failed_step["step_id"],
                    )
                )
                .mappings()
                .one()
            )
            event = (
                connection.execute(
                    sa.select(PUBLIC_TABLES["runtime_events"]).where(
                        PUBLIC_TABLES["runtime_events"].c.project_key == PROJECT_KEY,
                        PUBLIC_TABLES["runtime_events"].c.run_id == command.run_id,
                        PUBLIC_TABLES["runtime_events"].c.event_type == "EffectFailed",
                    )
                )
                .mappings()
                .one()
            )
            failure_value = (
                connection.execute(
                    sa.select(p0c_database.project_tables.successor_values).where(
                        p0c_database.project_tables.successor_values.c.project_key
                        == PROJECT_KEY,
                        p0c_database.project_tables.successor_values.c.object_type
                        == "RuntimeFailure.v1",
                    )
                )
                .mappings()
                .one()
            )
        assert run["state"] == "FAILED"
        assert failed_step["failure_digest"] == attempt["failure_digest"]
        assert attempt["disposition"] == "FAILED"
        assert str(attempt["failure_ref"]).startswith("project-value:runtime-failure:")
        assert event["event_metadata_json"]["required_step_failed"] is True
        assert event["event_metadata_json"]["failure_policy_decision_digest"]
        assert failure_value["state"] == "FAILED"
        failure_body = (
            failure_value["content_json"]
            if failure_value["content_json"] is not None
            else json.loads(bytes(failure_value["content_bytes"]))
        )
        assert failure_body["failure_code"] == ("INJECTED_DETERMINISTIC_FAILURE")
        assert blob_store.store_calls == 0
        return
    expected_unknown_local = {
        "artifact-crash": 1,
        "evidence-admission-crash": 2,
        "claim-admission-crash": 1,
        "admission-crash": 1,
        "admission-recovery-adoption-crash": 1,
    }.get(delivery_mode, 0)
    assert unknown_local_results == expected_unknown_local
    if local_crash_handler is not None and delivery_mode != "delivery-admission-crash":
        assert local_crash_handler.calls == expected_unknown_local
    if recovery_crash_handler is not None:
        assert recovery_crash_handler.calls == 2

    artifact_id = f"artifact:{command.run_id}"
    artifact_incarnation = (
        f"canonical:{command.run_id}:artifact.compose_markdown.v1:incarnation:1"
    )
    with p0c_database.engine.connect() as connection:
        artifact_row = (
            connection.execute(
                sa.select(p0c_database.project_tables.research_objects).where(
                    p0c_database.project_tables.research_objects.c.object_type
                    == "ResearchArtifact.v1"
                )
            )
            .mappings()
            .one_or_none()
        )
        if artifact_row is None:
            step_diagnostics = connection.execute(
                sa.select(
                    PUBLIC_TABLES["runtime_steps"].c.operation_kind,
                    PUBLIC_TABLES["runtime_steps"].c.state,
                    PUBLIC_TABLES["runtime_steps"].c.output_digest,
                ).where(PUBLIC_TABLES["runtime_steps"].c.run_id == command.run_id)
            ).all()
            pytest.fail(f"artifact not admitted; steps={step_diagnostics}")
        assert artifact_row["object_id"] == artifact_id
        assert artifact_row["incarnation"] == artifact_incarnation
        artifact_ref = ResearchLedgerRepository(
            connection, p0c_database.project_tables
        ).get_object(
            p0c_database.scope,
            artifact_id,
            expected_revision=1,
            expected_incarnation=artifact_incarnation,
        )
    delivery_step = next(
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT"
        and step.operation_contract_ref is not None
        and step.operation_contract_ref.kind == "delivery.internal_export.v1"
    )
    exact_artifact_ref = artifact_identity_ref(
        artifact_ref.object_id,
        artifact_ref.revision,
        artifact_ref.content_digest,
    )
    delivery_candidate = command.delivery_template.candidate(exact_artifact_ref)
    assert delivery_candidate.content_digest is not None
    approval_time = shared_clock.now()
    with p0c_database.engine.begin() as connection:
        ApprovalRepository(connection, p0c_database.scope).decide(
            ApprovalBinding(
                approval_id=command.delivery_template.approval_ref,
                actor_id=p0c_database.scope.actor_id,
                run_id=command.run_id,
                step_id=delivery_step.step_id,
                payload_digest=delivery_candidate.content_digest,
                decision="APPROVED",
                expires_at=approval_time + timedelta(hours=1),
                authority_digest=DELIVERY_AUTHORITY_DIGEST,
            )
        )

    gate_receipt = assembly.admit_delivery(
        FirstSpecimenDeliveryGateRequest(
            scope=p0c_database.scope,
            run_id=command.run_id,
            template=command.delivery_template,
            artifact_id=artifact_ref.object_id,
            artifact_revision=artifact_ref.revision,
            artifact_incarnation=artifact_ref.incarnation,
            value_incarnation="delivery-value-inc-1",
            intent_incarnation="delivery-intent-inc-1",
            now=approval_time,
            trace_id="trace:p0c:full-chain:delivery",
        )
    )
    assert gate_receipt.packet.assignment.payload_ref == (
        gate_receipt.packet.export_payload_ref.storage_ref
    )

    idle = 0
    unknown_delivery_results = 0
    if delivery_mode == "delivery-reconcile-lease-expiry":
        first_delivery = nodes[0].run_once()
        reports.append(first_delivery)
        assert first_delivery.claimed == 1
        assert first_delivery.results[0].committed
        assert first_delivery.results[0].disposition.value == "OUTCOME_UNKNOWN"
        unknown_delivery_results = 1
        recovery_claims = nodes[1].claims.claim_due(
            control_scope=nodes[1].control_scope,
            node=nodes[1].identity,
            profile=nodes[1].profile,
            deployment=nodes[1].deployment,
            protocol=nodes[1].protocol,
            limit=1,
            observed_at=shared_clock.now(),
        )
        assert len(recovery_claims) == 1
        assert recovery_claims[0].assignment.assignment_kind is AssignmentKind.RECONCILE
        expired_at = recovery_claims[0].claim_binding.lease_expires_at + timedelta(
            seconds=1
        )
        with p0c_database.engine.begin() as connection:
            reaped = WorkItemClaimRepository(connection).reap_expired(
                ControlPlaneScope(
                    system_actor_id="p0c-full-reaper",
                    permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
                    authority_epoch=AUTHORITY_EPOCH,
                ),
                now=expired_at,
            )
        assert reaped == (recovery_claims[0].assignment.work_item_id,)
        shared_clock.current = expired_at + timedelta(seconds=1)
    for turn in range(80, 140):
        report = nodes[turn % 2].run_once()
        reports.append(report)
        if report.claimed:
            idle = 0
            assert report.results[0].committed, report.results[0].failure_code
            if report.results[0].disposition.value == "OUTCOME_UNKNOWN" and (
                crash_delivery or delivery_mode == "delivery-admission-crash"
            ):
                unknown_delivery_results += 1
                if (
                    delivery_mode == "delivery-crash-wait-retry"
                    and unknown_delivery_results == 2
                ):
                    shared_clock.current += timedelta(seconds=2)
                continue
            assert report.results[0].disposition.value == "SUCCEEDED", report
        else:
            idle += 1
            if idle >= 4:
                break
    assert (
        unknown_delivery_results
        == {
            "happy": 0,
            "artifact-crash": 0,
            "evidence-admission-crash": 0,
            "claim-admission-crash": 0,
            "admission-crash": 0,
            "admission-recovery-adoption-crash": 0,
            "delivery-admission-crash": 1,
            "delivery-crash": 1,
            "delivery-crash-wait-retry": 2,
            "delivery-reconcile-lease-expiry": 1,
        }[delivery_mode]
    )
    assert blob_store.store_calls == 1
    if delivery_mode == "delivery-admission-crash":
        assert local_crash_handler is not None
        assert local_crash_handler.calls == 1

    with p0c_database.engine.connect() as connection:
        object_rows = (
            connection.execute(sa.select(p0c_database.project_tables.research_objects))
            .mappings()
            .all()
        )
        relation_rows = (
            connection.execute(
                sa.select(p0c_database.project_tables.research_relations)
            )
            .mappings()
            .all()
        )
        object_types = {str(row["object_type"]) for row in object_rows}
        relation_types = {str(row["relation_type"]) for row in relation_rows}
        plan_runtime_steps = tuple(
            step
            for step in plan.ordered_steps
            if step.step_kind in {"EFFECT", "ADMISSION"}
        )
        step_rows = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_steps"]).where(
                    PUBLIC_TABLES["runtime_steps"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_steps"].c.run_id == command.run_id,
                )
            )
            .mappings()
            .all()
        )
        primary_work = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_work_items"]).where(
                    PUBLIC_TABLES["runtime_work_items"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_work_items"].c.run_id == command.run_id,
                    PUBLIC_TABLES["runtime_work_items"].c.assignment_kind.in_(
                        ("INTERPRET", "VERIFY_ADMIT")
                    ),
                )
            )
            .mappings()
            .all()
        )
        attempt_rows = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                    PUBLIC_TABLES["runtime_effect_attempts"].c.project_key
                    == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_effect_attempts"].c.run_id == command.run_id,
                )
            )
            .mappings()
            .all()
        )
        receipt_rows = (
            connection.execute(
                sa.select(p0c_database.project_tables.successor_receipts)
            )
            .mappings()
            .all()
        )
        legacy_rows = connection.execute(
            sa.select(LEGACY_DOCUMENTS.c.id, LEGACY_DOCUMENTS.c.content).order_by(
                LEGACY_DOCUMENTS.c.id
            )
        ).all()
        completed_run = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_runs"]).where(
                    PUBLIC_TABLES["runtime_runs"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_runs"].c.run_id == command.run_id,
                )
            )
            .mappings()
            .one()
        )
        union_value_count = connection.scalar(
            sa.select(sa.func.count())
            .select_from(p0c_database.project_tables.successor_values)
            .where(
                p0c_database.project_tables.successor_values.c.object_type
                == "ClaimOrGap.v1"
            )
        )
        if delivery_mode in {
            "admission-crash",
            "admission-recovery-adoption-crash",
        }:
            artifact_commit_intents = (
                connection.execute(
                    sa.select(PUBLIC_TABLES["runtime_commit_intents"]).where(
                        PUBLIC_TABLES["runtime_commit_intents"].c.project_key
                        == PROJECT_KEY,
                        PUBLIC_TABLES["runtime_commit_intents"].c.object_identity_ref
                        == artifact_id,
                    )
                )
                .mappings()
                .all()
            )
            artifact_stages = (
                connection.execute(
                    sa.select(PUBLIC_TABLES["runtime_staged_artifacts"])
                    .join(
                        PUBLIC_TABLES["runtime_values"],
                        sa.and_(
                            PUBLIC_TABLES["runtime_values"].c.project_key
                            == PUBLIC_TABLES["runtime_staged_artifacts"].c.project_key,
                            PUBLIC_TABLES["runtime_values"].c.value_id
                            == PUBLIC_TABLES["runtime_staged_artifacts"].c.value_id,
                        ),
                    )
                    .where(
                        PUBLIC_TABLES["runtime_staged_artifacts"].c.project_key
                        == PROJECT_KEY,
                        PUBLIC_TABLES["runtime_values"].c.object_type
                        == "ResearchArtifact.v1",
                    )
                )
                .mappings()
                .all()
            )
            artifact_recovery_work = (
                connection.execute(
                    sa.select(PUBLIC_TABLES["runtime_work_items"]).where(
                        PUBLIC_TABLES["runtime_work_items"].c.project_key
                        == PROJECT_KEY,
                        PUBLIC_TABLES["runtime_work_items"].c.assignment_kind
                        == "RECONCILE",
                        PUBLIC_TABLES["runtime_work_items"].c.operation_contract_digest
                        == crash_operation.ref.contract_digest,
                    )
                )
                .mappings()
                .all()
            )
            assert len(artifact_commit_intents) == 1
            assert artifact_commit_intents[0]["state"] == "COMMITTED"
            assert len(artifact_stages) == 1
            assert artifact_stages[0]["state"] == "ADMITTED"
            assert (
                sum(row["state"] == "COMPLETED" for row in artifact_recovery_work) == 1
            )
            assert {row["state"] for row in artifact_recovery_work} <= {
                "COMPLETED",
                "PENDING",
                "SUPERSEDED",
            }
    assert "ResearchArtifact.v1" in object_types
    assert "DeliveryIntent.v1" in object_types
    assert "DeliveryReceiptRef.v1" in object_types
    assert "EvidenceQualification.v1" not in object_types
    assert "Document" not in object_types
    assert {"supports", "contradicts", "delivered_as"} <= relation_types
    assert len(plan_runtime_steps) == len(step_rows) == len(primary_work)
    assert len(
        {(row["step_id"], row["assignment_kind"]) for row in primary_work}
    ) == len(primary_work)
    assert {row["state"] for row in step_rows} == {"SUCCEEDED"}
    assert {row["state"] for row in primary_work} == {"COMPLETED"}
    assert len(attempt_rows) == len(primary_work)
    assert {row["disposition"] for row in attempt_rows} == {"SUCCEEDED"}
    assert all(
        row["handler_binding_digest"] == row["handler_realization_digest"]
        for row in attempt_rows
    )
    assert len({row["attempt_id"] for row in attempt_rows}) == len(attempt_rows)
    assert len(receipt_rows) == 1
    assert union_value_count == 0
    assert completed_run["state"] == "COMPLETED"

    for row in primary_work:
        encoded = json.dumps(row["assignment_binding_json"], sort_keys=True)
        assert "content_bytes" not in encoded
        assert "payload_bytes" not in encoded

    assert [row.id for row in legacy_rows] == [101, 102]
    for row in legacy_rows:
        exact = row.content.encode("utf-8")
        assert len(exact) == SEED_CONTENT_BYTES[row.id]
        assert hashlib.sha256(exact).hexdigest() == SEED_CONTENT_SHA256[row.id]

    artifact_row = next(
        row for row in object_rows if row["object_type"] == "ResearchArtifact.v1"
    )
    artifact_value_id = str(artifact_row["content_ref"]).removeprefix("project-value:")
    artifact_metadata = json.loads(p0c_database.value_bytes(artifact_value_id))
    qualification_by_type = {
        row["relation_type"]: row["relation_id"]
        for row in relation_rows
        if row["relation_type"] in {"supports", "contradicts"}
    }
    material_ids = tuple(
        row["object_id"]
        for row in object_rows
        if row["object_type"] == "MaterialRef.v1"
    )
    assert tuple(artifact_metadata["evidence_relation_closure"]) == (
        qualification_by_type["supports"],
        qualification_by_type["contradicts"],
    )
    assert set(artifact_metadata["citation_closure"]) == set(material_ids)
    assert len(artifact_metadata["claim_closure"]) == 1

    delivered_as = next(
        row for row in relation_rows if row["relation_type"] == "delivered_as"
    )
    delivered_source = json.loads(delivered_as["source_object_ref"])
    delivered_target = json.loads(delivered_as["target_object_ref"])
    assert delivered_source["object_id"] == artifact_row["object_id"]
    assert delivered_target["object_type"] == "DeliveryReceiptRef.v1"
    assert delivered_target["object_id"] == receipt_rows[0]["receipt_id"]
    return command


@pytest.mark.parametrize(
    "delivery_mode",
    (
        "happy",
        "artifact-effect-failed",
        "artifact-authority-revoked",
        "artifact-crash",
        "evidence-admission-crash",
        "claim-admission-crash",
        "admission-crash",
        "admission-recovery-adoption-crash",
        "delivery-admission-crash",
        "delivery-crash",
        "delivery-crash-wait-retry",
        "delivery-reconcile-lease-expiry",
    ),
)
def test_full_chain_starts_only_through_production_activation_and_two_nodes(
    p0c_database: LiveP0CDatabase,
    tmp_path: Path,
    delivery_mode: str,
) -> None:
    run_full_chain_first_specimen(p0c_database, tmp_path, delivery_mode)
