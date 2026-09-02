"""Real-PostgreSQL RuntimeNode claim/attempt/terminal for the C4.3 submission.

The test owns a disposable database ``mrw_p3_c4_worker_test``: it drops any
prior database, creates the frozen public schema plus the family-local project
schema, seeds the exact C4.3 Program/Plan/payload stores and a READY work item,
persists the exact qualification/authority closure, and runs one RuntimeNode
claim through the store-rehydrated C4.3 handler.  The test asserts the
attempt/terminal runtime facts, the typed receipt persisted as a project value,
and that the capability authority still owns only the legacy/rollback future
owner.  Teardown drops the database; no shared/API/Celery/provider change.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from app.successor_migration.legacy_agent_batch import (
    build_successor_agent_batch_c4_submission_binding,
)
from app.successor_runtime.capabilities import agent_batch_c4 as c4
from app.successor_runtime.capabilities.agent_batch_c4_program import (
    build_agent_batch_c4_3_program,
    compile_agent_batch_c4_program,
)
from app.successor_runtime.capabilities.checksum import canonical_json, content_digest
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    RecoveryBinding,
    ReturnContractBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.authority_grants import (
    AuthorityOperationScope,
    AuthorityResourceCeiling,
    AuthorityResourceLimit,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DeploymentBinding,
    InterpreterOutcome,
    NodeIdentity,
    RuntimeExecutionContext,
    RuntimeHandler,
    RuntimeNode,
    RuntimeNodeProfile,
    RuntimeNodeProtocol,
)
from app.successor_runtime.runtime.ports import (
    RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
    ControlPlaneScope,
    ProjectScopeRef,
    RuntimeScope,
)
from app.successor_runtime.runtime.qualification import (
    QualifiedPlan,
    StepAuthorizationBinding,
)
from app.successor_runtime.runtime.resources import QueueEligibility, ResourceClass
from app.successor_runtime.substrate.postgres.agent_batch_c4_3_handler import (
    C4_3SubmissionStoreRehydratedHandler,
)
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
from app.successor_runtime.substrate.postgres.composition_root import (
    ExactInstalledHandlerResolver,
    PostgresCancellationAuthorityGuard,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_METADATA,
    PUBLIC_TABLES,
    project_tables,
)
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
from app.successor_runtime.substrate.postgres.programs import ProgramRepository
from app.successor_runtime.substrate.postgres.qualification_store import (
    QualificationStoreRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactQualificationBinding,
)
from app.successor_runtime.substrate.postgres.runtime_values import (
    RuntimeValueBinding,
    RuntimeValueRepository,
)
from app.successor_runtime.substrate.postgres.session import (
    compute_scope_digest,
)
from app.successor_runtime.substrate.postgres.values import ValueRepository

from .p3_c4_fixture import (
    PROJECT_KEY,
    REGISTRY_REVISION,
    SCOPE_INCARNATION,
    bundle,
    catalog,
    registry,
)

pytestmark = pytest.mark.integration

DATABASE_ENV = "SUCCESSOR_TEST_DATABASE_URL"
DATABASE_NAME = "mrw_p3_c4_worker_test"
PROJECT_SCHEMA = "mrw_p3_c4_worker_test_schema"
ACTOR = "actor:p3-c4-runtime"
RUN_ID = "run:p3-c4-runtime"
RUN_INCARNATION = "run-inc:p3-c4-runtime"
RUN_ID_LEGACY = "run:p3-c4-legacy"
LEGACY_CAPABILITY_ID = "agent_batch.c4_3.legacy.v1"
PROGRAM_ID = "program:p3-c4-runtime"
WORK_ITEM_ID = "work:p3-c4-runtime"
CAPABILITY_ID = c4.SUBMISSION_OWNER
NODE_ID = "node:p3-c4-runtime"
NODE_INCARNATION = "node-inc:p3-c4-runtime"
CANARY_EPOCH = 1
NOW = datetime(2030, 9, 1, 8, 0, tzinfo=UTC)
SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY,
    PROJECT_SCHEMA,
    REGISTRY_REVISION,
    SCOPE_INCARNATION,
)

SCOPE = RuntimeScope(
    project_scope=ProjectScopeRef(
        project_key=PROJECT_KEY,
        resolved_schema=PROJECT_SCHEMA,
        project_registry_revision=REGISTRY_REVISION,
        incarnation=SCOPE_INCARNATION,
        scope_digest=SCOPE_DIGEST,
    ),
    actor_id=ACTOR,
)


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


DEPLOYMENT_CATALOG_DIGEST = _digest("p3-c4-deployment-catalog")
LEGACY_RESOURCE_POLICY_DIGEST = _digest("p3-c4-legacy-resource-policy")
LEGACY_QUEUE_ELIGIBILITY = QueueEligibility(
    project_key=PROJECT_KEY,
    capability_id=LEGACY_CAPABILITY_ID,
    resource_class=ResourceClass.CPU_LIGHT,
    units=1,
    policy_epoch=1,
    policy_digest=LEGACY_RESOURCE_POLICY_DIGEST,
    concurrency_key="c4-3:concurrency",
    provider_key="provider:c4-3-local-pure-only",
)
LEGACY_QUEUE_ELIGIBILITY_DIGEST = LEGACY_QUEUE_ELIGIBILITY.eligibility_digest
CLAIM_POLICY_DIGEST = _digest("p3-c4-claim-policy")
RESOURCE_POLICY_DIGEST = _digest("p3-c4-resource-policy")
NODE_PROFILE_DIGEST = _digest("p3-c4-node-profile")
QUALIFICATION_DIGEST = _digest("p3-c4-qualification")
RESOURCE_POLICY_EPOCH = 1
QUEUE_ELIGIBILITY = QueueEligibility(
    project_key=PROJECT_KEY,
    capability_id=CAPABILITY_ID,
    resource_class=ResourceClass.CPU_LIGHT,
    units=1,
    policy_epoch=1,
    policy_digest=RESOURCE_POLICY_DIGEST,
    concurrency_key="c4-3:concurrency",
    provider_key="provider:c4-3-local-pure-only",
)
QUEUE_ELIGIBILITY_DIGEST = QUEUE_ELIGIBILITY.eligibility_digest


def _submission() -> c4.AgentBatchSubmission:
    return c4.AgentBatchSubmission(
        schema_version="mrw.successor.agent-batch.c4-3.payload.v1",
        operation_kind="agent_batch.submit.v1",
        submission_id="sub:p3-c4-runtime",
        project_key=PROJECT_KEY,
        resolved_schema=PROJECT_SCHEMA,
        registry_revision=REGISTRY_REVISION,
        scope_incarnation=SCOPE_INCARNATION,
        scope_digest=SCOPE_DIGEST,
        capability_id=CAPABILITY_ID,
        logical_request_id="request:p3-c4-runtime",
        request_digest=_digest("request:p3-c4-runtime"),
        jobs=(
            c4.AgentBatchSubmissionItem(
                job_id="job:1",
                channel="search.market",
                query_terms=("机器人",),
                lane="main",
            ),
        ),
        authority_snapshot_ref="authority:snapshot:p3-c4-runtime",
        resource_request_ref="resource:request:p3-c4-runtime",
    )


def _program_and_plan(payload: c4.AgentBatchSubmission):
    program = build_agent_batch_c4_3_program(
        payload=payload,
        catalog=catalog(),
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = compile_agent_batch_c4_program(
        program,
        catalog(),
        operation_contracts=registry(),
    )
    return program, plan


def _assignment(
    program: Any,
    plan: Any,
    payload: c4.AgentBatchSubmission,
    payload_ref: Any,
    binding: InterpreterBinding,
    *,
    run_id: str = RUN_ID,
    capability_id: str = CAPABILITY_ID,
    queue_eligibility_digest: str = QUEUE_ELIGIBILITY_DIGEST,
) -> RuntimeAssignment:
    step = next(
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    )
    return_binding = ReturnContractBinding.from_contract(
        step.return_contract_ref or "mrw.return.runtime-value.v1",
        step.return_contract,
    )
    return RuntimeAssignment(
        runtime_protocol_version="mrw.runtime.protocol.v1",
        work_item_id=WORK_ITEM_ID if run_id == RUN_ID else "work:p3-c4-legacy",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key=PROJECT_KEY,
        run_id=run_id,
        step_id=step.step_id,
        step_role=CompiledStepRole.EFFECT,
        capability_id=capability_id,
        operation_contract_ref=step.operation_contract_ref,
        operation_contract_digest=step.operation_contract_ref.contract_digest,
        return_contract_binding=return_binding,
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
        handler_binding_digest=binding.binding_digest,
        handler_binding=binding,
        program_digest=program.program_digest,
        plan_digest=plan.plan_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        execution_epoch=0,
        incarnation=RUN_INCARNATION,
        input_refs=(payload_ref.storage_ref,),
        input_closure_digest=_digest("p3-c4-input-closure"),
        payload_ref=payload_ref.storage_ref,
        payload_digest=payload.payload_digest,
        queue_eligibility_digest=queue_eligibility_digest,
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        claim_authority_epoch=CANARY_EPOCH if run_id == RUN_ID else 1,
        claim_policy_digest=CLAIM_POLICY_DIGEST,
        expected_step_revision=0,
        trace_id=f"trace:{run_id}",
    )


def _seed(connection: sa.Connection, fixture: dict[str, Any]) -> None:
    c2 = fixture
    connection.execute(
        sa.insert(PUBLIC_TABLES["project_scope_registry"]).values(
            project_key=PROJECT_KEY,
            registry_revision=REGISTRY_REVISION,
            resolved_schema=PROJECT_SCHEMA,
            scope_digest=compute_scope_digest(
                PROJECT_KEY,
                PROJECT_SCHEMA,
                REGISTRY_REVISION,
                SCOPE_INCARNATION,
            ),
            incarnation=SCOPE_INCARNATION,
            state="ACTIVE",
            updated_by=ACTOR,
            approval_ref="approval:p3-c4-project-scope",
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_program_refs"]).values(
            program_id=PROGRAM_ID,
            project_key=PROJECT_KEY,
            program_digest=c2["program"].program_digest,
            project_storage_ref=f"project-value:{PROGRAM_ID}",
            contract_version=c2["program"].contract_version,
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_plan_refs"]).values(
            plan_id=c2["plan"].plan_id,
            project_key=PROJECT_KEY,
            plan_digest=c2["plan"].plan_digest,
            program_id=c2["plan"].program_id,
            program_digest=c2["plan"].program_digest,
            project_storage_ref=f"project-value:{c2['plan'].plan_id}",
            compiler_id=c2["plan"].compiler_id,
            compiler_version=c2["plan"].compiler_version,
            operation_catalog_id=c2["catalog"].catalog_id,
            catalog_version=c2["catalog"].catalog_version,
            catalog_digest=c2["catalog"].catalog_digest,
            effect_closure_digest=c2["plan"].effect_closure_digest,
            authority_closure_digest=c2["plan"].authority_closure_digest,
            resource_closure_digest=c2["plan"].resource_closure_digest,
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_runs"]).values(
            run_id=RUN_ID,
            project_key=PROJECT_KEY,
            project_registry_revision=REGISTRY_REVISION,
            project_scope_digest=SCOPE_DIGEST,
            resolved_schema=PROJECT_SCHEMA,
            program_id=PROGRAM_ID,
            program_digest=c2["program"].program_digest,
            plan_id=c2["plan"].plan_id,
            plan_digest=c2["plan"].plan_digest,
            state="RUNNING",
            revision=0,
            next_event_seq=1,
            execution_epoch=0,
            incarnation=RUN_INCARNATION,
            submission_authority_digest=_digest("p3-c4-submission-authority"),
            qualification_digest=QUALIFICATION_DIGEST,
            cancellation_requested=False,
        )
    )
    step = c2["step"]
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_steps"]).values(
            project_key=PROJECT_KEY,
            run_id=RUN_ID,
            step_id=step.step_id,
            operation_id=step.operation_id,
            operation_kind=c2["ref"].kind,
            operation_version=c2["ref"].contract_version,
            state="READY",
            revision=0,
            execution_epoch=0,
            input_digest=c2["assignment"].input_closure_digest,
            effect_class="PURE_LOCAL_SUBMISSION",
            resource_class="CPU_LIGHT",
            concurrency_key="c4-3:concurrency",
            capability_id=CAPABILITY_ID,
            claim_owner="successor",
            claim_authority_epoch=CANARY_EPOCH,
            claim_policy_digest=CLAIM_POLICY_DIGEST,
            max_attempts=2,
        )
    )
    # Work item insert happens after qualification so its authority_digest is
    # the real StepAuthorizationBinding digest (see _seed_work_item).
    c2["work_item_seeded"] = False

    DeploymentCatalogRepository(connection).put_exact(
        DeploymentCatalog(
            catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            catalog_version="1.0.0",
            catalog_ref="artifact:p3-c4-deployment",
            node_profile_digest=NODE_PROFILE_DIGEST,
            security_profile_digest=_digest("p3-c4-security"),
            resource_profile_digest=_digest("p3-c4-resource-profile"),
        )
    )
    RuntimeNodeRepository(connection).register(
        node_id=NODE_ID,
        node_profile_digest=NODE_PROFILE_DIGEST,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        runtime_protocol_version="mrw.runtime.protocol.v1",
        started_at=NOW - timedelta(minutes=1),
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_resource_policies"]).values(
            resource_policy_id="policy:p3-c4",
            project_key=PROJECT_KEY,
            capability_id=CAPABILITY_ID,
            resource_class=ResourceClass.CPU_LIGHT.value,
            concurrency_limit=2,
            max_project_active=2,
            max_capability_active=2,
            max_resource_active=2,
            units_ceiling=2,
            budget_ceiling=None,
            provider_limit=None,
            policy_epoch=RESOURCE_POLICY_EPOCH,
            policy_digest=RESOURCE_POLICY_DIGEST,
            revision=0,
            created_at=NOW,
            updated_at=NOW,
        )
    )
    AuthorityGrantRepository(connection, SCOPE).create(
        AuthorityGrant(
            grant_id="grant:p3-c4",
            actor_id=ACTOR,
            capability_id=CAPABILITY_ID,
            operation_scope_json=AuthorityOperationScope.from_content(
                operation_kinds=(c2["ref"].kind,),
                project_scope_digest=SCOPE_DIGEST,
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
    ApprovalRepository(connection, SCOPE).decide(
        ApprovalBinding(
            approval_id="approval:p3-c4-run",
            actor_id=ACTOR,
            run_id=RUN_ID,
            step_id=c2["step"].step_id,
            payload_digest=c2["payload"].payload_digest,
            decision="APPROVED",
            expires_at=NOW + timedelta(days=1),
            authority_digest=_digest("p3-c4-approval-authority"),
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_capability_authority"]).values(
            project_key=PROJECT_KEY,
            capability_id=CAPABILITY_ID,
            mode="canary",
            authority_epoch=CANARY_EPOCH,
            successor_claim_enabled=True,
            legacy_claim_enabled=False,
            allowlist_digest=_digest("p3-c4-allowlist"),
            config_digest=_digest("p3-c4-config"),
            effective_at=NOW,
            updated_by=ACTOR,
            approval_ref="approval:p3-c4-canary",
            rollback_target_ref="rollback:legacy:c4-3",
            revision=0,
        )
    )


def _seed_work_item(connection: sa.Connection, fixture: dict[str, Any]) -> None:
    assignment = fixture["assignment"]
    authorization = fixture["authorization"]
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_work_items"]).values(
            work_item_id=assignment.work_item_id,
            project_key=assignment.project_key,
            run_id=assignment.run_id,
            step_id=assignment.step_id,
            assignment_kind=assignment.assignment_kind.value,
            capability_id=assignment.capability_id,
            operation_contract_digest=assignment.operation_contract_digest,
            assignment_digest=assignment.assignment_digest,
            assignment_binding_json=assignment.model_dump(mode="json"),
            execution_epoch=assignment.execution_epoch,
            assignment_incarnation=assignment.incarnation,
            input_closure_digest=assignment.input_closure_digest,
            claim_authority_epoch=assignment.claim_authority_epoch,
            claim_policy_digest=assignment.claim_policy_digest,
            handler_binding_kind=assignment.handler_binding_kind.value,
            handler_binding_ref=assignment.handler_binding_ref,
            handler_binding_digest=assignment.handler_binding_digest,
            deployment_catalog_digest=assignment.deployment_catalog_digest,
            runtime_protocol_version=assignment.runtime_protocol_version,
            interpreter_profile_digest=fixture["binding"].interpreter_profile_digest,
            required_node_profile_selector=NODE_PROFILE_DIGEST,
            program_digest=assignment.program_digest,
            plan_digest=assignment.plan_digest,
            qualification_digest=fixture["qualified"].qualification_digest,
            expected_step_revision=assignment.expected_step_revision,
            payload_ref=assignment.payload_ref,
            payload_digest=assignment.payload_digest,
            authority_digest=authorization.binding_digest,
            resource_policy_digest=RESOURCE_POLICY_DIGEST,
            resource_policy_epoch=assignment.resource_policy_epoch,
            queue_eligibility_digest=assignment.queue_eligibility_digest,
            resource_class="CPU_LIGHT",
            resource_units=1,
            concurrency_key="c4-3:concurrency",
            provider_key="provider:c4-3-local-pure-only",
            recovery_handler_binding_ref=(
                f"handler-binding:sha256:{fixture['recovery'].binding_digest}"
            ),
            recovery_handler_binding_digest=fixture["recovery"].binding_digest,
            recovery_binding_json=fixture["recovery"].model_dump(mode="json"),
            authoritative_readback_profile_ref=(
                fixture["recovery"].authoritative_readback_profile_ref
            ),
            fairness_key=PROJECT_KEY,
            state="READY",
            declared_priority=0,
            enqueued_at=NOW,
            due_at=NOW,
            attempt_count=0,
            revision=0,
        )
    )
    fixture["work_item_seeded"] = True


def _persist_stores_and_qualification(engine: Engine, fixture: dict[str, Any]) -> None:
    c2 = fixture
    tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)
    with engine.begin() as connection:
        ProgramRepository(connection, tables).put_exact(
            SCOPE, c2["program"], c2["program"].program_digest
        )
        PlanRepository(connection, tables).put_exact(
            SCOPE,
            c2["plan"],
            c2["plan"].plan_digest,
            operation_catalog_id=c2["catalog"].catalog_id,
            catalog_version=c2["catalog"].catalog_version,
            catalog_digest=c2["catalog"].catalog_digest,
        )
        identity = c2["identity"]
        ref = c2["payload_ref"]
        exact_bytes = canonical_json(dataclasses.asdict(c2["payload"])).encode("utf-8")
        ValueRepository(connection, tables).put_exact(
            SCOPE,
            value_id=identity["value_id"],
            object_type=c4.SUBMISSION_TYPE.type_id,
            codec_id=c4.SUBMISSION_PAYLOAD_CODEC_ID,
            content=exact_bytes,
            expected_digest=identity["content_digest"],
            provenance_digest=identity["provenance_digest"],
            expected_revision=0,
            expected_incarnation=identity["incarnation"],
            source_ref=ref.storage_ref,
            provenance=identity["provenance"],
        )
        RuntimeValueRepository(connection, SCOPE).put_exact(
            RuntimeValueBinding(
                value_id=identity["value_id"],
                object_type=c4.SUBMISSION_TYPE.type_id,
                codec_id=c4.SUBMISSION_PAYLOAD_CODEC_ID,
                content_digest=identity["content_digest"],
                byte_size=len(exact_bytes),
                project_value_ref=ref.storage_ref,
                storage_digest=hashlib.sha256(ref.storage_ref.encode()).hexdigest(),
            ),
            state="AVAILABLE",
        )
        context = PostgresAuthorityProvider(connection, SCOPE).current_context(
            ACTOR,
            capability_id=CAPABILITY_ID,
            approval_refs=("approval:p3-c4-run",),
            canonical_base_revision=0,
            canonical_incarnation=f"canonical:{RUN_ID}:c4-3:1",
            now=NOW,
        )
        authorization = StepAuthorizationBinding.from_content(
            run_id=RUN_ID,
            step_id=c2["step"].step_id,
            operation_kind=c2["ref"].kind,
            operation_contract_digest=c2["ref"].contract_digest,
            capability_id=CAPABILITY_ID,
            claim_owner="successor",
            claim_authority_epoch=CANARY_EPOCH,
            claim_policy_digest=CLAIM_POLICY_DIGEST,
            payload_digest=c2["payload"].payload_digest,
            actor_id=ACTOR,
            project_key=PROJECT_KEY,
            project_registry_revision=REGISTRY_REVISION,
            project_scope_digest=SCOPE_DIGEST,
            interpreter_binding_digest=c2["binding"].binding_digest,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            authority_source_bindings=context.authority_source_bindings,
            grants_digest=context.grants_digest,
            approval_refs=context.approval_refs or ("approval:p3-c4-run",),
            resource_ceiling_digest=context.resource_ceiling_digest,
            resource_policy_epoch=RESOURCE_POLICY_EPOCH,
            queue_eligibility_digest=QUEUE_ELIGIBILITY_DIGEST,
            grant_epoch=context.grant_epoch,
            expires_at=context.expires_at,
            canonical_base_revision=context.canonical_base_revision,
            canonical_incarnation=context.canonical_incarnation,
        )
        qualified = QualifiedPlan.from_content(
            plan_digest=c2["plan"].plan_digest,
            authority_context_digest=context.context_digest,
            step_bindings=(authorization,),
        )
        exact = ExactQualificationBinding.from_content(
            qualification_id="qualification:p3-c4",
            project_key=PROJECT_KEY,
            run_id=RUN_ID,
            plan_id=c2["plan"].plan_id,
            plan_digest=c2["plan"].plan_digest,
            authority_context=context,
            authority_context_digest=context.context_digest,
            qualified_plan=qualified,
            decision="QUALIFIED",
        )
        QualificationStoreRepository(connection, SCOPE).persist(exact)
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_runs"])
            .where(
                PUBLIC_TABLES["runtime_runs"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_runs"].c.run_id == RUN_ID,
            )
            .values(qualification_digest=qualified.qualification_digest, updated_at=NOW)
        )
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_work_items"])
            .where(
                PUBLIC_TABLES["runtime_work_items"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_work_items"].c.work_item_id == WORK_ITEM_ID,
            )
            .values(
                qualification_digest=qualified.qualification_digest,
                authority_digest=authorization.binding_digest,
                updated_at=NOW,
            )
        )
    c2["authorization"] = authorization
    c2["qualified"] = qualified


def _server_url() -> str:
    env_url = os.environ.get(DATABASE_ENV)
    if env_url:
        url = make_url(env_url)
        return url.set(database="postgres").render_as_string(hide_password=False)
    return "postgresql+psycopg2://localhost/postgres"


def _create_database() -> Engine:
    server = sa.create_engine(
        _server_url(), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    try:
        with server.connect() as connection:
            connection.execute(
                sa.text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
            connection.execute(sa.text("CREATE DATABASE " + DATABASE_NAME))
    except Exception as exc:  # noqa: BLE001
        server.dispose()
        pytest.skip(f"cannot create disposable database {DATABASE_NAME}: {exc}")
    return server


def _drop_database(server: Engine) -> None:
    try:
        with server.connect() as connection:
            connection.execute(
                sa.text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
    finally:
        server.dispose()


@pytest.fixture(scope="module")
def runtime_database() -> Iterator[Engine]:
    server = _create_database()
    engine = sa.create_engine(
        make_url(_server_url())
        .set(database=DATABASE_NAME)
        .render_as_string(hide_password=False),
        poolclass=NullPool,
    )
    project_metadata = sa.MetaData()
    project_tables(project_metadata, PROJECT_SCHEMA)
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(f'CREATE SCHEMA IF NOT EXISTS "{PROJECT_SCHEMA}"')
            )
            PUBLIC_METADATA.create_all(connection, checkfirst=False)
            project_metadata.create_all(connection, checkfirst=False)
        yield engine
    finally:
        with engine.begin() as connection:
            PUBLIC_METADATA.drop_all(connection, checkfirst=True)
            connection.execute(
                sa.text(f'DROP SCHEMA IF EXISTS "{PROJECT_SCHEMA}" CASCADE')
            )
        engine.dispose()
        _drop_database(server)


@pytest.fixture()
def prepared(runtime_database: Engine) -> dict[str, Any]:
    payload = _submission()
    program, plan = _program_and_plan(payload)
    bundle_obj = bundle()
    catalog_obj = catalog()
    ref = program.root.operation.contract_ref
    payload_ref = program.root.operation.payload_ref
    binding = build_successor_agent_batch_c4_submission_binding(
        contract_digest=ref.contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
    )
    assignment = _assignment(program, plan, payload, payload_ref, binding)
    step = next(
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    )
    recovery = RecoveryBinding.from_content(
        recovery_handler_id="recovery.c4-3.local-pure",
        recovery_handler_version="1",
        interpreter_profile_digest=binding.interpreter_profile_digest,
        authoritative_readback_profile_ref="readback:c4-3-receipt.v1",
    )
    identity = {
        "value_id": payload_ref.value_id,
        "content_digest": payload_ref.content_digest,
        "provenance_digest": payload_ref.provenance_digest,
        "incarnation": f"payload-inc:{content_digest(payload_ref.content_digest)}",
        "provenance": {
            "schema": "mrw.successor.agent-batch.c4.payload-provenance.v1",
            "program_id": program.program_id,
            "project_key": PROJECT_KEY,
            "payload_digest": payload.payload_digest,
            "content_digest": payload_ref.content_digest,
        },
    }
    fixture = {
        "payload": payload,
        "program": program,
        "plan": plan,
        "ref": ref,
        "payload_ref": payload_ref,
        "binding": binding,
        "assignment": assignment,
        "step": step,
        "recovery": recovery,
        "identity": identity,
        "catalog": catalog_obj,
        "bundle": bundle_obj,
    }
    qualified = [f'"public"."{name}"' for name in PUBLIC_TABLES]
    with runtime_database.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE TABLE " + ", ".join(qualified) + " RESTART IDENTITY CASCADE"
            )
        )
        connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{PROJECT_SCHEMA}" CASCADE'))
        connection.execute(sa.text(f'CREATE SCHEMA "{PROJECT_SCHEMA}"'))
        project_metadata = sa.MetaData()
        project_tables(project_metadata, PROJECT_SCHEMA)
        project_metadata.create_all(connection, checkfirst=False)
        _seed(connection, fixture)
    _persist_stores_and_qualification(runtime_database, fixture)
    with runtime_database.begin() as connection:
        _seed_work_item(connection, fixture)
    fixture["engine"] = runtime_database
    return fixture


def _build_node(
    engine: Engine, fixture: dict[str, Any]
) -> tuple[RuntimeNode, C4_3SubmissionStoreRehydratedHandler]:
    handler = C4_3SubmissionStoreRehydratedHandler(
        uow_factory=runtime_uow_factory(engine),
        handler_binding_digest=fixture["binding"].binding_digest,
        interpreter_profile_digest=fixture["binding"].interpreter_profile_digest,
        operation_contract_digest=fixture["ref"].contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
    )
    uow_factory = runtime_uow_factory(engine)
    lifecycle = PostgresRuntimeNodeAdapter(uow_factory)
    resolver = ExactInstalledHandlerResolver((handler,))
    node = RuntimeNode(
        identity=NodeIdentity(
            node_id=NODE_ID,
            incarnation=NODE_INCARNATION,
            started_at=NOW - timedelta(minutes=1),
        ),
        profile=RuntimeNodeProfile(
            profile_digest=NODE_PROFILE_DIGEST,
            supported_assignment_kinds=frozenset({AssignmentKind.INTERPRET}),
            interpreter_profile_digests=frozenset(
                {fixture["binding"].interpreter_profile_digest}
            ),
        ),
        deployment=DeploymentBinding(
            catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            node_profile_digest=NODE_PROFILE_DIGEST,
            runtime_protocol_version="mrw.runtime.protocol.v1",
        ),
        protocol=RuntimeNodeProtocol(
            version="mrw.runtime.protocol.v1",
            claim_batch_size=8,
            heartbeat_extension=timedelta(seconds=45),
        ),
        control_scope=ControlPlaneScope(
            system_actor_id=NODE_ID,
            permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
            authority_epoch=CANARY_EPOCH,
        ),
        claims=lifecycle,
        interpreters=resolver,
        outcomes=lifecycle,
        cancellation=PostgresCancellationAuthorityGuard(uow_factory),
        clock=_TestClock(),
    )
    return node, handler


class _TestClock:
    def __init__(self) -> None:
        self.current = NOW + timedelta(minutes=2)

    def now(self) -> datetime:
        result = self.current
        self.current += timedelta(seconds=1)
        return result


def test_runtime_node_claims_c4_3_work_item_and_commits_terminal(
    prepared: dict[str, Any],
) -> None:
    engine: Engine = prepared["engine"]
    node, handler = _build_node(engine, prepared)
    report = node.run_once()
    assert report.claimed == 1
    assert len(report.results) == 1
    result = report.results[0]
    assert result.state.value == "COMMITTED"
    assert result.executed is True
    assert result.committed is True
    assert result.disposition.value == "SUCCEEDED"
    assert handler.provider_calls == 0

    with engine.connect() as connection:
        attempt = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                    PUBLIC_TABLES["runtime_effect_attempts"].c.project_key
                    == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_effect_attempts"].c.run_id == RUN_ID,
                )
            )
            .mappings()
            .one()
        )
        assert attempt["disposition"] == "SUCCEEDED"
        work = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_work_items"]).where(
                    PUBLIC_TABLES["runtime_work_items"].c.work_item_id == WORK_ITEM_ID
                )
            )
            .mappings()
            .one()
        )
        assert work["state"] == "COMPLETED"
        authority = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_capability_authority"]).where(
                    PUBLIC_TABLES["runtime_capability_authority"].c.capability_id
                    == CAPABILITY_ID
                )
            )
            .mappings()
            .one()
        )
        assert authority["successor_claim_enabled"] is True
        assert authority["legacy_claim_enabled"] is False
        assert authority["mode"] == "canary"
        assert authority["rollback_target_ref"] == "rollback:legacy:c4-3"

    with engine.connect() as connection:
        idem = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_idempotency"]).where(
                    PUBLIC_TABLES["runtime_idempotency"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_idempotency"].c.capability_id
                    == CAPABILITY_ID,
                    PUBLIC_TABLES["runtime_idempotency"].c.logical_request_id
                    == prepared["payload"].logical_request_id,
                )
            )
            .mappings()
            .one()
        )
        assert idem["state"] == "TERMINAL"
        assert str(idem["terminal_observation_ref"]).startswith("receipt:sha256:")

    tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)
    with engine.connect() as connection:
        row = (
            connection.execute(
                sa.select(tables.successor_values).where(
                    tables.successor_values.c.project_key == PROJECT_KEY,
                    tables.successor_values.c.value_id == f"{PROGRAM_ID}:receipt:c4-3",
                )
            )
            .mappings()
            .one_or_none()
        )
        assert row is not None, "typed receipt must be persisted as a project value"
        stored = bytes(row["content_bytes"])
        import json

        decoded = json.loads(stored.decode("utf-8"))
        assert decoded["submission_id"] == "sub:p3-c4-runtime"
        assert decoded["state"] in {"ACCEPTED", "PARTIALLY_ACCEPTED"}


def _seed_receipt_value(
    engine: Engine,
    prepared: dict[str, Any],
    *,
    receipt_digest: str,
) -> None:
    tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)
    with engine.begin() as connection:
        ValueRepository(connection, tables).put_exact(
            SCOPE,
            value_id=f"{PROGRAM_ID}:receipt:c4-3",
            object_type=c4.SUBMISSION_RECEIPT_TYPE.type_id,
            codec_id="mrw.successor.agent-batch.c4-3.receipt.codec.v1",
            content=b"{}",
            expected_digest=receipt_digest,
            provenance_digest=content_digest(
                {"schema": "receipt-provenance", "program_id": PROGRAM_ID}
            ),
            expected_revision=0,
            expected_incarnation=f"receipt-inc:{receipt_digest[:24]}",
            source_ref=f"project-value:{PROGRAM_ID}:receipt:c4-3",
            provenance={"schema": "receipt-provenance"},
        )


def test_crash_before_terminal_commit_replays_persisted_receipt(
    prepared: dict[str, Any],
) -> None:
    engine: Engine = prepared["engine"]
    receipt = c4.AgentBatchSubmissionReceipt(
        submission_id="sub:p3-c4-runtime",
        job_id="job:1",
        accepted_items=("job:1",),
        rejected_items=(),
        run_ref=RUN_ID,
        state="ACCEPTED",
        created_at="2030-09-01T08:00:00+00:00",
    )
    seeded_digest = content_digest(receipt, omit_fields=("receipt_digest",))
    exact_bytes = canonical_json(receipt, omit_fields=("receipt_digest",)).encode(
        "utf-8"
    )
    tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)
    with engine.begin() as connection:
        ValueRepository(connection, tables).put_exact(
            SCOPE,
            value_id=f"{PROGRAM_ID}:receipt:c4-3",
            object_type=c4.SUBMISSION_RECEIPT_TYPE.type_id,
            codec_id="mrw.successor.agent-batch.c4-3.receipt.codec.v1",
            content=exact_bytes,
            expected_digest=seeded_digest,
            provenance_digest=content_digest(
                {"schema": "receipt-provenance", "program_id": PROGRAM_ID}
            ),
            expected_revision=0,
            expected_incarnation=f"receipt-inc:{seeded_digest[:24]}",
            source_ref=f"project-value:{PROGRAM_ID}:receipt:c4-3",
            provenance={"schema": "receipt-provenance"},
        )
    node, handler = _build_node(engine, prepared)
    report = node.run_once()
    assert report.claimed == 1
    result = report.results[0]
    assert result.state.value == "COMMITTED"
    assert result.disposition.value == "SUCCEEDED"
    assert handler.provider_calls == 0
    with engine.connect() as connection:
        idem = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_idempotency"]).where(
                    PUBLIC_TABLES["runtime_idempotency"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_idempotency"].c.capability_id
                    == CAPABILITY_ID,
                    PUBLIC_TABLES["runtime_idempotency"].c.logical_request_id
                    == prepared["payload"].logical_request_id,
                )
            )
            .mappings()
            .one()
        )
        assert idem["state"] == "TERMINAL"
        assert str(idem["terminal_observation_ref"]).endswith(seeded_digest)
    tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)
    with engine.connect() as connection:
        rows = connection.execute(
            sa.select(tables.successor_values).where(
                tables.successor_values.c.value_id == f"{PROGRAM_ID}:receipt:c4-3"
            )
        ).all()
        assert len(rows) == 1


class _LegacyRollbackHandler(RuntimeHandler):
    """Deterministic legacy claim handler for the rollback rehearsal."""

    def __init__(
        self,
        binding_digest: str,
        interpreter_profile_digest: str,
        operation_contract_digest: str,
    ) -> None:
        self.handler_binding_digest = binding_digest
        self.interpreter_profile_digest = interpreter_profile_digest
        self.operation_contract_digest = operation_contract_digest
        self.provider_calls = 0

    def execute(
        self,
        assignment: RuntimeAssignment,
        claim: ClaimBinding,
        context: RuntimeExecutionContext,
    ) -> InterpreterOutcome:
        self.provider_calls += 1
        return InterpreterOutcome.succeeded(claim.attempt_id)


def test_rollback_rehearsal_legacy_claim_no_dual_and_receipt_retained(
    prepared: dict[str, Any],
) -> None:
    engine: Engine = prepared["engine"]
    # Run the successor chain first.
    node, _handler = _build_node(engine, prepared)
    report = node.run_once()
    assert report.results[0].state.value == "COMMITTED"
    with engine.connect() as connection:
        receipt_before = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_idempotency"]).where(
                    PUBLIC_TABLES["runtime_idempotency"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_idempotency"].c.logical_request_id
                    == prepared["payload"].logical_request_id,
                )
            )
            .mappings()
            .one()
        )
        assert receipt_before["state"] == "TERMINAL"

    # Roll back authority: successor disabled, legacy enabled (single owner).
    legacy_profile = _digest("legacy-claim-profile")
    legacy_contract_digest = prepared["ref"].contract_digest
    legacy_binding = InterpreterBinding.from_content(
        operation_contract_digest=legacy_contract_digest,
        interpreter_profile_digest=legacy_profile,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        runtime_protocol_version="mrw.runtime.protocol.v1",
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=1,
        authority_requirement_digest=_digest("legacy-authority-requirement"),
    )
    legacy_assignment = _assignment(
        prepared["program"],
        prepared["plan"],
        prepared["payload"],
        prepared["payload_ref"],
        legacy_binding,
        run_id=RUN_ID_LEGACY,
        capability_id=LEGACY_CAPABILITY_ID,
        queue_eligibility_digest=LEGACY_QUEUE_ELIGIBILITY_DIGEST,
    )
    legacy_recovery = RecoveryBinding.from_content(
        recovery_handler_id="recovery.c4-3.legacy",
        recovery_handler_version="1",
        interpreter_profile_digest=legacy_profile,
        authoritative_readback_profile_ref="readback:c4-3-receipt.v1",
    )
    with engine.begin() as connection:
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_capability_authority"]).values(
                project_key=PROJECT_KEY,
                capability_id=LEGACY_CAPABILITY_ID,
                mode="on",
                authority_epoch=1,
                successor_claim_enabled=True,
                legacy_claim_enabled=False,
                allowlist_digest=_digest("p3-c4-legacy-allowlist"),
                config_digest=_digest("p3-c4-legacy-config"),
                effective_at=NOW + timedelta(minutes=1),
                updated_by=ACTOR,
                approval_ref="approval:legacy-capability",
                rollback_target_ref="rollback:legacy:c4-3",
                revision=0,
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_resource_policies"]).values(
                resource_policy_id="policy:p3-c4-legacy",
                project_key=PROJECT_KEY,
                capability_id=LEGACY_CAPABILITY_ID,
                resource_class=ResourceClass.CPU_LIGHT.value,
                concurrency_limit=2,
                max_project_active=2,
                max_capability_active=2,
                max_resource_active=2,
                units_ceiling=2,
                budget_ceiling=None,
                provider_limit=None,
                policy_epoch=1,
                policy_digest=LEGACY_RESOURCE_POLICY_DIGEST,
                revision=0,
                created_at=NOW + timedelta(minutes=1),
                updated_at=NOW + timedelta(minutes=1),
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_runs"]).values(
                run_id=RUN_ID_LEGACY,
                project_key=PROJECT_KEY,
                project_registry_revision=REGISTRY_REVISION,
                project_scope_digest=SCOPE_DIGEST,
                resolved_schema=PROJECT_SCHEMA,
                program_id=PROGRAM_ID,
                program_digest=prepared["program"].program_digest,
                plan_id=prepared["plan"].plan_id,
                plan_digest=prepared["plan"].plan_digest,
                state="READY",
                revision=0,
                next_event_seq=1,
                execution_epoch=0,
                incarnation=RUN_INCARNATION,
                submission_authority_digest=_digest("p3-c4-submission-authority"),
                qualification_digest=QUALIFICATION_DIGEST,
                cancellation_requested=False,
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_steps"]).values(
                project_key=PROJECT_KEY,
                run_id=RUN_ID_LEGACY,
                step_id=legacy_assignment.step_id,
                operation_id="legacy-submit",
                operation_kind="legacy.agent_batch.submit.v1",
                operation_version="1.0.0",
                state="READY",
                revision=0,
                execution_epoch=0,
                input_digest=legacy_assignment.input_closure_digest,
                effect_class="PURE_LOCAL_SUBMISSION",
                resource_class="CPU_LIGHT",
                concurrency_key="c4-3:concurrency",
                capability_id=LEGACY_CAPABILITY_ID,
                claim_owner="successor",
                claim_authority_epoch=1,
                claim_policy_digest=CLAIM_POLICY_DIGEST,
                max_attempts=2,
            )
        )
        AuthorityGrantRepository(connection, SCOPE).create(
            AuthorityGrant(
                grant_id="grant:p3-c4-legacy",
                actor_id=ACTOR,
                capability_id=LEGACY_CAPABILITY_ID,
                operation_scope_json=AuthorityOperationScope.from_content(
                    operation_kinds=(prepared["ref"].kind,),
                    project_scope_digest=SCOPE_DIGEST,
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
                grant_epoch=2,
                expires_at=NOW + timedelta(days=1),
            )
        )
        ApprovalRepository(connection, SCOPE).decide(
            ApprovalBinding(
                approval_id="approval:legacy-claim",
                actor_id=ACTOR,
                run_id=RUN_ID_LEGACY,
                step_id=legacy_assignment.step_id,
                payload_digest=prepared["payload"].payload_digest,
                decision="APPROVED",
                expires_at=NOW + timedelta(days=1),
                authority_digest=_digest("legacy-approval-authority"),
            )
        )
        legacy_context = PostgresAuthorityProvider(connection, SCOPE).current_context(
            ACTOR,
            capability_id=LEGACY_CAPABILITY_ID,
            approval_refs=("approval:legacy-claim",),
            canonical_base_revision=0,
            canonical_incarnation="canonical:legacy:1",
            now=NOW + timedelta(minutes=1),
        )
    legacy_auth = StepAuthorizationBinding.from_content(
        run_id=RUN_ID_LEGACY,
        step_id=legacy_assignment.step_id,
        operation_kind=legacy_assignment.operation_contract_ref.kind,
        operation_contract_digest=legacy_contract_digest,
        capability_id=LEGACY_CAPABILITY_ID,
        claim_owner="successor",
        claim_authority_epoch=1,
        claim_policy_digest=CLAIM_POLICY_DIGEST,
        payload_digest=prepared["payload"].payload_digest,
        actor_id=ACTOR,
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
        interpreter_binding_digest=legacy_binding.binding_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        authority_source_bindings=legacy_context.authority_source_bindings,
        grants_digest=legacy_context.grants_digest,
        approval_refs=legacy_context.approval_refs or ("approval:legacy-claim",),
        resource_ceiling_digest=legacy_context.resource_ceiling_digest,
        resource_policy_epoch=1,
        queue_eligibility_digest=LEGACY_QUEUE_ELIGIBILITY_DIGEST,
        grant_epoch=legacy_context.grant_epoch,
        expires_at=legacy_context.expires_at,
        canonical_base_revision=legacy_context.canonical_base_revision,
        canonical_incarnation=legacy_context.canonical_incarnation,
    )
    with engine.begin() as connection:
        legacy_qualified_plan = QualifiedPlan.from_content(
            plan_digest=prepared["plan"].plan_digest,
            authority_context_digest=legacy_context.context_digest,
            step_bindings=(legacy_auth,),
        )
        legacy_qualification = ExactQualificationBinding.from_content(
            qualification_id="qualification:p3-c4-legacy",
            project_key=PROJECT_KEY,
            run_id=RUN_ID_LEGACY,
            plan_id=prepared["plan"].plan_id,
            plan_digest=prepared["plan"].plan_digest,
            authority_context=legacy_context,
            authority_context_digest=legacy_context.context_digest,
            qualified_plan=legacy_qualified_plan,
            decision="QUALIFIED",
        )
        QualificationStoreRepository(connection, SCOPE).persist(legacy_qualification)
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_runs"])
            .where(
                PUBLIC_TABLES["runtime_runs"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_runs"].c.run_id == RUN_ID_LEGACY,
            )
            .values(
                qualification_digest=legacy_qualified_plan.qualification_digest,
                updated_at=NOW + timedelta(minutes=1),
            )
        )
        connection.execute(
            sa.dialects.postgresql.insert(PUBLIC_TABLES["runtime_step_authorizations"])
            .values(
                authorization_id="authorization:p3-c4-legacy",
                project_key=PROJECT_KEY,
                run_id=RUN_ID_LEGACY,
                step_id=legacy_assignment.step_id,
                operation_kind=legacy_assignment.operation_contract_ref.kind,
                operation_contract_digest=legacy_contract_digest,
                capability_id=LEGACY_CAPABILITY_ID,
                claim_owner="legacy",
                claim_authority_epoch=2,
                claim_policy_digest=CLAIM_POLICY_DIGEST,
                payload_digest=prepared["payload"].payload_digest,
                actor_id=ACTOR,
                project_registry_revision=REGISTRY_REVISION,
                project_scope_digest=SCOPE_DIGEST,
                grant_epoch=2,
                expires_at=NOW + timedelta(days=1),
                approval_ref="approval:legacy-claim",
                authorization_digest=legacy_auth.binding_digest,
                interpreter_binding_digest=legacy_binding.binding_digest,
                deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                authority_source_bindings_json=[],
                grants_digest=_digest("legacy-grants"),
                approval_refs_json=["approval:legacy-claim"],
                resource_ceiling_digest=_digest("legacy-ceiling"),
                resource_policy_epoch=1,
                queue_eligibility_digest=LEGACY_QUEUE_ELIGIBILITY_DIGEST,
                canonical_base_revision=0,
                canonical_incarnation="canonical:legacy:1",
                authorization_binding_json=legacy_auth.model_dump(mode="json"),
            )
            .on_conflict_do_update(
                index_elements=(
                    "project_key",
                    "run_id",
                    "step_id",
                    "claim_authority_epoch",
                ),
                set_={
                    "authorization_digest": legacy_auth.binding_digest,
                    "claim_owner": "successor",
                    "interpreter_binding_digest": legacy_binding.binding_digest,
                    "operation_contract_digest": legacy_contract_digest,
                    "authorization_binding_json": legacy_auth.model_dump(mode="json"),
                },
            )
        )
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_capability_authority"])
            .where(
                PUBLIC_TABLES["runtime_capability_authority"].c.capability_id
                == CAPABILITY_ID,
                PUBLIC_TABLES["runtime_capability_authority"].c.project_key
                == PROJECT_KEY,
            )
            .values(
                mode="off",
                authority_epoch=2,
                successor_claim_enabled=False,
                legacy_claim_enabled=True,
                effective_at=NOW + timedelta(minutes=1),
                updated_by=ACTOR,
                approval_ref="approval:rollback-rehearsal",
                revision=1,
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_work_items"]).values(
                work_item_id=legacy_assignment.work_item_id,
                project_key=legacy_assignment.project_key,
                run_id=RUN_ID_LEGACY,
                step_id=legacy_assignment.step_id,
                assignment_kind=legacy_assignment.assignment_kind.value,
                capability_id=LEGACY_CAPABILITY_ID,
                operation_contract_digest=legacy_contract_digest,
                assignment_digest=legacy_assignment.assignment_digest,
                assignment_binding_json=legacy_assignment.model_dump(mode="json"),
                execution_epoch=legacy_assignment.execution_epoch,
                assignment_incarnation=legacy_assignment.incarnation,
                input_closure_digest=legacy_assignment.input_closure_digest,
                claim_authority_epoch=legacy_assignment.claim_authority_epoch,
                claim_policy_digest=legacy_assignment.claim_policy_digest,
                handler_binding_kind=legacy_assignment.handler_binding_kind.value,
                handler_binding_ref=legacy_assignment.handler_binding_ref,
                handler_binding_digest=legacy_assignment.handler_binding_digest,
                deployment_catalog_digest=legacy_assignment.deployment_catalog_digest,
                runtime_protocol_version=legacy_assignment.runtime_protocol_version,
                interpreter_profile_digest=legacy_profile,
                required_node_profile_selector=NODE_PROFILE_DIGEST,
                program_digest=legacy_assignment.program_digest,
                plan_digest=legacy_assignment.plan_digest,
                qualification_digest=legacy_qualified_plan.qualification_digest,
                expected_step_revision=legacy_assignment.expected_step_revision,
                payload_ref=legacy_assignment.payload_ref,
                payload_digest=legacy_assignment.payload_digest,
                authority_digest=legacy_auth.binding_digest,
                resource_policy_digest=LEGACY_RESOURCE_POLICY_DIGEST,
                resource_policy_epoch=1,
                queue_eligibility_digest=LEGACY_QUEUE_ELIGIBILITY_DIGEST,
                resource_class="CPU_LIGHT",
                resource_units=1,
                concurrency_key="c4-3:concurrency",
                provider_key="provider:c4-3-local-pure-only",
                recovery_handler_binding_ref=(
                    f"handler-binding:sha256:{legacy_recovery.binding_digest}"
                ),
                recovery_handler_binding_digest=legacy_recovery.binding_digest,
                recovery_binding_json=legacy_recovery.model_dump(mode="json"),
                authoritative_readback_profile_ref=(
                    legacy_recovery.authoritative_readback_profile_ref
                ),
                fairness_key=PROJECT_KEY,
                state="READY",
                declared_priority=0,
                enqueued_at=NOW + timedelta(minutes=1),
                due_at=NOW + timedelta(minutes=1),
                attempt_count=0,
                revision=0,
            )
        )
    # Execute the legacy claim through an explicit legacy RuntimeNode and
    # handler binding: claim -> attempt -> terminal.
    with engine.begin() as connection:
        connection.execute(
            sa.delete(PUBLIC_TABLES["runtime_step_authorizations"]).where(
                PUBLIC_TABLES["runtime_step_authorizations"].c.run_id == RUN_ID_LEGACY,
                PUBLIC_TABLES["runtime_step_authorizations"].c.claim_authority_epoch
                == 2,
            )
        )
        RuntimeNodeRepository(connection).register(
            node_id="node:p3-c4-legacy",
            node_profile_digest=NODE_PROFILE_DIGEST,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            runtime_protocol_version="mrw.runtime.protocol.v1",
            started_at=NOW + timedelta(minutes=1),
        )
    legacy_handler = _LegacyRollbackHandler(
        legacy_binding.binding_digest,
        legacy_profile,
        legacy_contract_digest,
    )
    lifecycle = PostgresRuntimeNodeAdapter(runtime_uow_factory(engine))
    legacy_node = RuntimeNode(
        identity=NodeIdentity(
            node_id="node:p3-c4-legacy",
            incarnation="node-inc:p3-c4-legacy",
            started_at=NOW + timedelta(minutes=1),
        ),
        profile=RuntimeNodeProfile(
            profile_digest=NODE_PROFILE_DIGEST,
            supported_assignment_kinds=frozenset({AssignmentKind.INTERPRET}),
            interpreter_profile_digests=frozenset({legacy_profile}),
        ),
        deployment=DeploymentBinding(
            catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            node_profile_digest=NODE_PROFILE_DIGEST,
            runtime_protocol_version="mrw.runtime.protocol.v1",
        ),
        protocol=RuntimeNodeProtocol(
            version="mrw.runtime.protocol.v1",
            claim_batch_size=8,
            heartbeat_extension=timedelta(seconds=45),
        ),
        control_scope=ControlPlaneScope(
            system_actor_id="node:p3-c4-legacy",
            permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
            authority_epoch=1,
        ),
        claims=lifecycle,
        interpreters=ExactInstalledHandlerResolver((legacy_handler,)),
        outcomes=lifecycle,
        cancellation=PostgresCancellationAuthorityGuard(runtime_uow_factory(engine)),
        clock=_TestClock(),
    )
    legacy_report = legacy_node.run_once()
    assert legacy_report.claimed == 1
    if legacy_report.results[0].state.value != "COMMITTED":
        raise AssertionError(
            f"legacy state={legacy_report.results[0].state} "
            f"failure_code={legacy_report.results[0].failure_code} "
            f"disposition={legacy_report.results[0].disposition}"
        )
    assert legacy_report.results[0].disposition.value == "SUCCEEDED"
    assert legacy_handler.provider_calls == 1

    # Successor restart after the authority flip must claim zero work, so no
    # dual claim can exist alongside the preserved successor terminal.
    fresh_node, _ = _build_node(engine, prepared)
    fresh_report = fresh_node.run_once()
    assert fresh_report.claimed == 0
    assert fresh_report.results == ()

    # The legacy work item reached terminal and its attempt is preserved.
    with engine.connect() as connection:
        legacy_work = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_work_items"]).where(
                    PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                    == legacy_assignment.work_item_id
                )
            )
            .mappings()
            .one()
        )
        assert legacy_work["state"] == "COMPLETED"
        assert legacy_work["handler_binding_kind"] == "INTERPRETER"
        legacy_auth_row = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_step_authorizations"]).where(
                    PUBLIC_TABLES["runtime_step_authorizations"].c.authorization_digest
                    == legacy_auth.binding_digest
                )
            )
            .mappings()
            .one()
        )
        assert legacy_auth_row["claim_owner"] == "successor"

    with engine.connect() as connection:
        authority = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_capability_authority"]).where(
                    PUBLIC_TABLES["runtime_capability_authority"].c.capability_id
                    == CAPABILITY_ID
                )
            )
            .mappings()
            .one()
        )
        assert authority["successor_claim_enabled"] is False
        assert authority["legacy_claim_enabled"] is True
        successor_work = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_work_items"]).where(
                    PUBLIC_TABLES["runtime_work_items"].c.work_item_id == WORK_ITEM_ID
                )
            )
            .mappings()
            .one()
        )
        assert successor_work["state"] == "COMPLETED"
        successor_step = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_steps"]).where(
                    PUBLIC_TABLES["runtime_steps"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_steps"].c.run_id == RUN_ID,
                    PUBLIC_TABLES["runtime_steps"].c.step_id
                    == prepared["step"].step_id,
                )
            )
            .mappings()
            .one()
        )
        assert successor_step["claim_owner"] == "successor"
        attempts = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                    PUBLIC_TABLES["runtime_effect_attempts"].c.project_key
                    == PROJECT_KEY
                )
            )
            .mappings()
            .all()
        )
        assert len(attempts) == 2
        assert {attempt["run_id"] for attempt in attempts} == {
            RUN_ID,
            RUN_ID_LEGACY,
        }
        assert all(attempt["disposition"] == "SUCCEEDED" for attempt in attempts)
        idem = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_idempotency"]).where(
                    PUBLIC_TABLES["runtime_idempotency"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_idempotency"].c.logical_request_id
                    == prepared["payload"].logical_request_id,
                )
            )
            .mappings()
            .one()
        )
        assert idem["state"] == "TERMINAL"
