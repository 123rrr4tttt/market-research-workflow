"""Disposable-PostgreSQL RuntimeNode canary for C2.2 -> C2.3 -> C2.4.

The canary claims and commits real runtime work items through
``RuntimeNode``/``PostgresRuntimeNodeAdapter``: the C2.2 planner atom, a
materialized C2.3 deterministic provider-effect attempt, an injected
OUTCOME_UNKNOWN that is converged by a readback-only RECONCILE handler, and the
same-journal C2.4 projection apply/delete/rebuild.  No live provider,
credential, network or canonical write is executed; rollback switches the
future owner to legacy only.

The fixture owns a disposable database ``mrw_p3_c2_worker_test`` and drops it
on teardown.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from app.successor_runtime.capabilities import source_library_c2_1 as c21
from app.successor_runtime.capabilities import source_library_c2_2 as c22
from app.successor_runtime.capabilities import source_library_c2_2_interpreters as c22i
from app.successor_runtime.capabilities import source_library_c2_2_program as c22p
from app.successor_runtime.capabilities import source_library_c2_3 as c23
from app.successor_runtime.capabilities import (
    source_library_c2_3_test_interpreters as c23_fixtures,
)
from app.successor_runtime.capabilities.checksum import canonical_json, content_digest
from app.successor_runtime.capabilities.source_library_c2_1 import (
    source_item_definition_content_digest,
)
from app.successor_runtime.capabilities.source_library_c2_1_interpreters import (
    resolve_source_execution_request,
)
from app.successor_runtime.capabilities.source_library_c2_2 import (
    CollectionCompleted,
    SourceCollectionTerminal,
)
from app.successor_runtime.capabilities.source_library_c2_3 import (
    CapturedSourceRecordRef,
)
from app.successor_runtime.capabilities.source_library_c2_4_projection import (
    SourceCollectionProjectionSource,
)
from app.successor_runtime.research.codec import sha256_hex
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    ReturnContractBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.node import (
    DeploymentBinding,
    NodeIdentity,
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
from app.successor_runtime.substrate.postgres.session import (
    create_runtime_engine,
)
from app.successor_runtime.substrate.postgres.source_library_c2_23_canary import (
    PAYLOAD_PUT_REVISION,
    PAYLOAD_VALUE_INCARNATION,
    PAYLOAD_VALUE_REVISION,
    C2_2StoreRehydratedHandler,
    C2_3ReconcileHandler,
    C2_3StoreRehydratedHandler,
    build_c2_3_fixture_program,
    build_c2_3_payload_value_ref,
    build_legacy_c2_2_binding,
    build_legacy_c2_3_binding,
    build_recovery_c2_3_binding,
    build_successor_c2_2_binding,
    build_successor_c2_3_binding,
)
from app.successor_runtime.substrate.postgres.values import ValueRepository
from app.successor_runtime.substrate.projections.source_library_terminal import (
    PostgresSourceLibraryTerminalProjector,
    build_source_library_terminal_table,
    rollback_read_routing,
)

from . import test_p2_c2_1_canary_postgres as canary

pytestmark = pytest.mark.integration

DATABASE_NAME = "mrw_p3_c2_worker_test"
ENV_URL = "SUCCESSOR_TEST_DATABASE_URL"

PROJECT_KEY = canary.PROJECT_KEY
PROJECT_SCHEMA = canary.PROJECT_SCHEMA
REGISTRY_REVISION = canary.REGISTRY_REVISION
SCOPE_INCARNATION = canary.SCOPE_INCARNATION
SCOPE_DIGEST = canary.SCOPE_DIGEST
SCOPE = canary.SCOPE
ACTOR = canary.ACTOR
NOW = canary.NOW
NODE_ID = canary.NODE_ID
NODE_INCARNATION = canary.NODE_INCARNATION
NODE_PROFILE_DIGEST = canary.NODE_PROFILE_DIGEST
DEPLOYMENT_CATALOG_DIGEST = canary.DEPLOYMENT_CATALOG_DIGEST
CANARY_EPOCH = canary.CANARY_EPOCH
CLAIM_POLICY_DIGEST = canary.CLAIM_POLICY_DIGEST
RESOURCE_POLICY_DIGEST = canary.RESOURCE_POLICY_DIGEST
RESOURCE_POLICY_EPOCH = canary.RESOURCE_POLICY_EPOCH
QUEUE_ELIGIBILITY_DIGEST = canary.QUEUE_ELIGIBILITY_DIGEST
ALLOWLIST_DIGEST = canary.ALLOWLIST_DIGEST
CONFIG_DIGEST = canary.CONFIG_DIGEST
ROLLBACK_TARGET = canary.ROLLBACK_TARGET

C2_2_CAPABILITY = "source_library.c2_2.v1"
C2_3_CAPABILITY = "source_library.c2_3.v1"
C2_2_RUN = "run:p3-c2-23:c2-2"
C2_2_WORK = "work:p3-c2-23:c2-2"
C2_2_MIXED_RUN = "run:p3-c2-23:c2-2-mixed"
C2_2_MIXED_WORK = "work:p3-c2-23:c2-2-mixed"
C2_2_PROGRAM = "program:p3-c2-23:c2-2"
C2_3_RUN = "run:p3-c2-23:c2-3"
C2_3_WORK = "work:p3-c2-23:c2-3"
C2_3_UNKNOWN_RUN = "run:p3-c2-23:c2-3-unknown"
C2_3_UNKNOWN_WORK = "work:p3-c2-23:c2-3-unknown"
C2_3_RECONCILE_RUN = "run:p3-c2-23:c2-3-reconcile"
C2_3_RECONCILE_WORK = "work:p3-c2-23:c2-3-reconcile"
C2_3_FAILED_RUN = "run:p3-c2-23:c2-3-failed"
C2_3_FAILED_WORK = "work:p3-c2-23:c2-3-failed"
C2_3_FAILED_RECONCILE_RUN = "run:p3-c2-23:c2-3-failed-reconcile"
C2_3_FAILED_RECONCILE_WORK = "work:p3-c2-23:c2-3-failed-reconcile"
RUN_INCARNATION = "run-inc:p3-c2-23"
ORCHESTRATION_POLICY_REF = "mrw.successor.source-library.c2-2.policy.v1"

_PROJECTION_METADATA = sa.MetaData()
PROJECTION_TABLE = build_source_library_terminal_table(_PROJECTION_METADATA)


def _eligibility(capability_id: str) -> Any:
    return canary.QueueEligibility(
        project_key=PROJECT_KEY,
        capability_id=capability_id,
        resource_class=canary.ResourceClass.CPU_LIGHT,
        units=1,
        policy_epoch=RESOURCE_POLICY_EPOCH,
        policy_digest=RESOURCE_POLICY_DIGEST,
        concurrency_key=capability_id,
        provider_key="provider:p3-c2-23-fixture-only",
    )


def _server_url() -> str:
    env_url = __import__("os").environ.get(ENV_URL)
    if env_url:
        return (
            make_url(env_url)
            .set(database="postgres")
            .render_as_string(hide_password=False)
        )
    return "postgresql+psycopg2://localhost/postgres"


def _create_database() -> Engine:
    server = sa.create_engine(
        _server_url(), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    try:
        with server.connect() as connection:
            connection.execute(
                text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
            connection.execute(text("CREATE DATABASE " + DATABASE_NAME))
    except Exception as exc:  # noqa: BLE001 - environment-dependent skip
        server.dispose()
        pytest.skip(f"cannot create disposable database {DATABASE_NAME}: {exc}")
    return server


def _drop_database(server: Engine) -> None:
    try:
        with server.connect() as connection:
            connection.execute(
                text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
    finally:
        server.dispose()


@pytest.fixture(scope="module")
def disposable_canary_database() -> Iterator[Engine]:
    server = _create_database()
    engine = create_runtime_engine(
        make_url(_server_url())
        .set(database=DATABASE_NAME)
        .render_as_string(hide_password=False),
        poolclass=NullPool,
    )
    project_metadata = sa.MetaData()
    project_tables(project_metadata, PROJECT_SCHEMA)
    with engine.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{PROJECT_SCHEMA}"'))
        PUBLIC_METADATA.create_all(connection, checkfirst=False)
        project_metadata.create_all(connection, checkfirst=False)
        PROJECTION_TABLE.create(connection, checkfirst=True)
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            PUBLIC_METADATA.drop_all(connection, checkfirst=True)
            connection.execute(
                sa.text(f'DROP SCHEMA IF EXISTS "{PROJECT_SCHEMA}" CASCADE')
            )
        engine.dispose()
        _drop_database(server)


def _resolved() -> tuple[Any, c21.SourceExecutionRequest]:
    channels = [
        {
            "channel_key": "handler.cluster",
            "provider_type": "native",
            "enabled": True,
            "extra": {"credential_refs": ["credential:/secret-ref/hc-api-key"]},
        },
        {"channel_key": "market.default", "provider_type": "native", "enabled": True},
    ]
    item = {
        "item_key": "handler.cluster.news",
        "channel_key": "handler.cluster",
        "enabled": True,
        "params": {"keywords": ["robotics"], "limit": 9},
        "extra": {
            "stable_handler_cluster": True,
            "expected_entry_type": "search_template",
        },
        "revision": 3,
        "incarnation": "item-inc-3",
    }
    item["content_digest"] = source_item_definition_content_digest(item)
    payload = c21.payload_from_dicts(
        project_key=PROJECT_KEY,
        registry_revision=REGISTRY_REVISION,
        resolved_schema=PROJECT_SCHEMA,
        scope_incarnation=SCOPE_INCARNATION,
        scope_digest=SCOPE_DIGEST,
        channels=channels,
        item=item,
        params={
            "query_terms": ["robotics"],
            "site_entries": ["https://example.com/search?q={{q}}"],
        },
    )
    resolved = resolve_source_execution_request(payload)
    assert isinstance(resolved, c21.ResolvedResolution)
    return payload, resolved.request


def _c2_2_planning(
    payload: Any, request: c21.SourceExecutionRequest
) -> c22.SourceModePlanningPayload:
    return c22.SourceModePlanningPayload(
        schema_version=c22.SOURCE_MODE_PLANNING_PAYLOAD_SCHEMA,
        operation_kind=c22i.kind_for_mode(request.source_mode.mode),
        project_scope=request.project_scope,
        execution_request=request,
        execution_request_digest=content_digest(request.to_plain()),
        catalog=payload.catalog,
        item_revision=request.item_revision,
        item_incarnation=request.item_incarnation,
        item_content_digest=request.item_content_digest,
        orchestration_policy_ref=ORCHESTRATION_POLICY_REF,
        resource_ceiling_digest=c21.resource_ceiling_digest(),
    )


def _build_c2_2_closure(
    payload: Any, request: c21.SourceExecutionRequest
) -> dict[str, Any]:
    planning = _c2_2_planning(payload, request)
    bundle = c22.build_source_library_c2_2_bundle()
    catalog = c22.build_source_library_c2_2_catalog(bundle)
    registry = c22.build_source_library_c2_2_registry(bundle)
    contract_ref = catalog.lookup(planning.operation_kind)
    assert contract_ref is not None
    program = c22p.build_source_library_c2_2_program(
        payload=planning,
        catalog=catalog,
        program_id=C2_2_PROGRAM,
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = c22p.compile_source_library_c2_2_program(
        program, catalog, operation_contracts=registry
    )
    effect_steps = [
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    ]
    assert len(effect_steps) == 1
    step = effect_steps[0]
    value_ref = c22p.planning_payload_value_ref(
        planning, program_id=C2_2_PROGRAM, project_key=PROJECT_KEY
    )
    binding = build_successor_c2_2_binding(
        contract_digest=contract_ref.contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        runtime_protocol_version="1",
    )
    recovery_binding = canary.RecoveryBinding.from_content(
        recovery_handler_id="recovery.source_library.c2_2.planner.v1",
        recovery_handler_version="1",
        interpreter_profile_digest=binding.interpreter_profile_digest,
        authoritative_readback_profile_ref="readback:c2-2-plan.v1",
    )
    return_binding = ReturnContractBinding.from_contract(
        step.return_contract_ref or "mrw.return.runtime-value.v1",
        step.return_contract,
    )
    assignment = RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id=C2_2_WORK,
        assignment_kind=AssignmentKind.INTERPRET,
        project_key=PROJECT_KEY,
        run_id=C2_2_RUN,
        step_id=step.step_id,
        step_role=CompiledStepRole.EFFECT,
        capability_id=C2_2_CAPABILITY,
        operation_contract_ref=dataclasses.replace(contract_ref),
        operation_contract_digest=contract_ref.contract_digest,
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
        input_refs=(value_ref.storage_ref,),
        input_closure_digest=sha256_hex([value_ref.storage_ref]),
        payload_ref=value_ref.storage_ref,
        payload_digest=planning.payload_digest,
        queue_eligibility_digest=_eligibility(C2_2_CAPABILITY).eligibility_digest,
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        claim_authority_epoch=CANARY_EPOCH,
        claim_policy_digest=CLAIM_POLICY_DIGEST,
        expected_step_revision=0,
        trace_id=f"trace:{C2_2_RUN}",
    )
    return {
        "planning": planning,
        "program": program,
        "plan": plan,
        "contract_ref": contract_ref,
        "payload_ref": value_ref,
        "catalog": catalog,
        "binding": binding,
        "recovery_binding": recovery_binding,
        "assignment": assignment,
        "step_id": step.step_id,
        "plan_digest": plan.plan_digest,
    }


def _build_c2_3_closure(
    request: c23.ProviderEffectRequest,
    *,
    run_id: str,
    work_item_id: str,
    program_id: str,
) -> dict[str, Any]:
    bundle = c23.build_source_library_c2_3_bundle()
    catalog = c23.build_source_library_c2_3_catalog(bundle)
    registry = c23.build_source_library_c2_3_registry(bundle)
    contract_ref = catalog.lookup(c23.SOURCE_LIBRARY_C2_3_KIND)
    assert contract_ref is not None
    program = build_c2_3_fixture_program(
        request=request,
        catalog=catalog,
        program_id=program_id,
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    from app.successor_runtime.substrate.postgres.source_library_c2_23_canary import (
        compile_c2_3_fixture_program,
    )

    plan = compile_c2_3_fixture_program(program, catalog, operation_contracts=registry)
    effect_steps = [
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    ]
    assert len(effect_steps) == 1
    step = effect_steps[0]
    value_ref = build_c2_3_payload_value_ref(
        request, program_id=program_id, project_key=PROJECT_KEY
    )
    binding = build_successor_c2_3_binding(
        contract_digest=contract_ref.contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        runtime_protocol_version="1",
    )
    recovery_binding = build_recovery_c2_3_binding(
        interpreter_profile_digest=binding.interpreter_profile_digest
    )
    return_binding = ReturnContractBinding.from_contract(
        step.return_contract_ref or "mrw.return.runtime-value.v1",
        step.return_contract,
    )
    assignment = RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id=work_item_id,
        assignment_kind=AssignmentKind.INTERPRET,
        project_key=PROJECT_KEY,
        run_id=run_id,
        step_id=step.step_id,
        step_role=CompiledStepRole.EFFECT,
        capability_id=C2_3_CAPABILITY,
        operation_contract_ref=dataclasses.replace(contract_ref),
        operation_contract_digest=contract_ref.contract_digest,
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
        input_refs=(value_ref.storage_ref,),
        input_closure_digest=sha256_hex([value_ref.storage_ref]),
        payload_ref=value_ref.storage_ref,
        payload_digest=request.request_digest,
        queue_eligibility_digest=_eligibility(C2_3_CAPABILITY).eligibility_digest,
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        claim_authority_epoch=CANARY_EPOCH,
        claim_policy_digest=CLAIM_POLICY_DIGEST,
        expected_step_revision=0,
        trace_id=f"trace:{run_id}",
    )
    return {
        "request": request,
        "program": program,
        "plan": plan,
        "contract_ref": contract_ref,
        "payload_ref": value_ref,
        "catalog": catalog,
        "binding": binding,
        "recovery_binding": recovery_binding,
        "assignment": assignment,
        "step_id": step.step_id,
    }


def _seed_base(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.insert(PUBLIC_TABLES["project_scope_registry"]).values(
                project_key=PROJECT_KEY,
                registry_revision=REGISTRY_REVISION,
                resolved_schema=PROJECT_SCHEMA,
                scope_digest=SCOPE_DIGEST,
                incarnation=SCOPE_INCARNATION,
                state="ACTIVE",
                updated_by=ACTOR,
                approval_ref="approval:p3-c2-23-project-scope",
            )
        )
        DeploymentCatalogRepository(connection).put_exact(
            DeploymentCatalog(
                catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
                catalog_version="1.0.0",
                catalog_ref="artifact:p3-c2-23-canary-deployment",
                node_profile_digest=NODE_PROFILE_DIGEST,
                security_profile_digest=canary._digest("c2-23-security"),
                resource_profile_digest=canary._digest("c2-23-resource-profile"),
            )
        )
        RuntimeNodeRepository(connection).register(
            node_id=NODE_ID,
            node_profile_digest=NODE_PROFILE_DIGEST,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            runtime_protocol_version="1",
            started_at=NOW - timedelta(minutes=1),
        )
        for capability_id in (C2_2_CAPABILITY, C2_3_CAPABILITY):
            connection.execute(
                sa.insert(PUBLIC_TABLES["runtime_resource_policies"]).values(
                    resource_policy_id=f"policy:p3-c2-23:{capability_id}",
                    project_key=PROJECT_KEY,
                    capability_id=capability_id,
                    resource_class=canary.ResourceClass.CPU_LIGHT.value,
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
            connection.execute(
                sa.insert(PUBLIC_TABLES["runtime_capability_authority"]).values(
                    project_key=PROJECT_KEY,
                    capability_id=capability_id,
                    mode="canary",
                    authority_epoch=CANARY_EPOCH,
                    successor_claim_enabled=True,
                    legacy_claim_enabled=False,
                    allowlist_digest=ALLOWLIST_DIGEST,
                    config_digest=CONFIG_DIGEST,
                    effective_at=NOW,
                    updated_by=ACTOR,
                    approval_ref=f"approval:p3-c2-23:{capability_id}",
                    rollback_target_ref=ROLLBACK_TARGET,
                    revision=0,
                )
            )
            AuthorityGrantRepository(connection, SCOPE).create(
                AuthorityGrant(
                    grant_id=f"grant:p3-c2-23:{capability_id}",
                    actor_id=ACTOR,
                    capability_id=capability_id,
                    operation_scope_json=canary.AuthorityOperationScope.from_content(
                        operation_kinds=(canary._digest(capability_id),),
                        project_scope_digest=SCOPE_DIGEST,
                    ),
                    resource_ceiling_json=canary.AuthorityResourceCeiling.from_content(
                        limits=(
                            canary.AuthorityResourceLimit(
                                resource_class=canary.ResourceClass.CPU_LIGHT.value,
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


def _insert_work_item_and_approval(
    connection: sa.Connection,
    closure: dict[str, Any],
    *,
    capability_id: str,
    qualification_digest: str | None = None,
    authority_digest: str | None = None,
    expected_step_revision: int | None = None,
) -> None:
    assignment = closure["assignment"]
    program = closure["program"]
    plan = closure["plan"]
    payload_ref = closure["payload_ref"]
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_work_items"]).values(
            work_item_id=assignment.work_item_id,
            project_key=PROJECT_KEY,
            run_id=assignment.run_id,
            step_id=assignment.step_id,
            assignment_kind=assignment.assignment_kind.value,
            capability_id=capability_id,
            operation_contract_digest=assignment.operation_contract_digest,
            assignment_digest=assignment.assignment_digest,
            assignment_binding_json=assignment.model_dump(mode="json"),
            execution_epoch=0,
            assignment_incarnation=assignment.incarnation,
            input_closure_digest=assignment.input_closure_digest,
            claim_authority_epoch=CANARY_EPOCH,
            claim_policy_digest=CLAIM_POLICY_DIGEST,
            handler_binding_kind=assignment.handler_binding_kind.value,
            handler_binding_ref=assignment.handler_binding_ref,
            handler_binding_digest=assignment.handler_binding_digest,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            runtime_protocol_version="1",
            interpreter_profile_digest=assignment.handler_binding.interpreter_profile_digest,
            required_node_profile_selector=NODE_PROFILE_DIGEST,
            program_digest=program.program_digest,
            plan_digest=plan.plan_digest,
            qualification_digest=qualification_digest
            or canary._digest("p3-c2-23-qualification"),
            expected_step_revision=(
                expected_step_revision if expected_step_revision is not None else 0
            ),
            reconciliation_attempt_id=assignment.reconciliation_attempt_id,
            payload_ref=payload_ref.storage_ref,
            payload_digest=assignment.payload_digest,
            authority_digest=authority_digest or canary._digest("p3-c2-23-authority"),
            resource_policy_digest=RESOURCE_POLICY_DIGEST,
            resource_policy_epoch=RESOURCE_POLICY_EPOCH,
            queue_eligibility_digest=assignment.queue_eligibility_digest,
            resource_class="CPU_LIGHT",
            resource_units=1,
            concurrency_key=capability_id,
            provider_key="provider:p3-c2-23-fixture-only",
            recovery_handler_binding_ref=(
                f"handler-binding:sha256:{closure['recovery_binding'].binding_digest}"
            ),
            recovery_handler_binding_digest=closure["recovery_binding"].binding_digest,
            recovery_binding_json=closure["recovery_binding"].model_dump(mode="json"),
            authoritative_readback_profile_ref=(
                closure["recovery_binding"].authoritative_readback_profile_ref
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
    approval = ApprovalBinding(
        approval_id=f"approval:p3-c2-23:{capability_id}:{assignment.work_item_id}",
        actor_id=ACTOR,
        run_id=assignment.run_id,
        step_id=assignment.step_id,
        payload_digest=assignment.payload_digest,
        decision="APPROVED",
        expires_at=NOW + timedelta(days=1),
        authority_digest=canary._digest("p3-c2-23-authority"),
    )
    ApprovalRepository(connection, SCOPE).decide(approval)


def _seed_closure(
    engine: Engine,
    closure: dict[str, Any],
    *,
    capability_id: str,
    run_state: str = "RUNNING",
    step_state: str = "READY",
    work_item_only: bool = False,
    qualification_digest: str | None = None,
    authority_digest: str | None = None,
    expected_step_revision: int | None = None,
) -> None:
    program = closure["program"]
    plan = closure["plan"]
    assignment = closure["assignment"]
    if work_item_only:
        with engine.begin() as connection:
            connection.execute(
                sa.update(PUBLIC_TABLES["runtime_runs"])
                .where(
                    PUBLIC_TABLES["runtime_runs"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_runs"].c.run_id == assignment.run_id,
                )
                .values(state=run_state, updated_at=NOW)
            )
            connection.execute(
                sa.update(PUBLIC_TABLES["runtime_steps"])
                .where(
                    PUBLIC_TABLES["runtime_steps"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_steps"].c.run_id == assignment.run_id,
                    PUBLIC_TABLES["runtime_steps"].c.step_id == assignment.step_id,
                )
                .values(state=step_state, updated_at=NOW)
            )
            _insert_work_item_and_approval(
                connection,
                closure,
                capability_id=capability_id,
                qualification_digest=qualification_digest,
                authority_digest=authority_digest,
                expected_step_revision=expected_step_revision,
            )
        return
    with engine.begin() as connection:
        connection.execute(
            pg_insert(PUBLIC_TABLES["runtime_program_refs"])
            .values(
                program_id=program.program_id,
                project_key=PROJECT_KEY,
                program_digest=program.program_digest,
                project_storage_ref=f"project-value:{program.program_id}",
                contract_version=program.contract_version,
            )
            .on_conflict_do_nothing()
        )
        connection.execute(
            pg_insert(PUBLIC_TABLES["runtime_plan_refs"])
            .values(
                plan_id=plan.plan_id,
                project_key=PROJECT_KEY,
                plan_digest=plan.plan_digest,
                program_id=plan.program_id,
                program_digest=plan.program_digest,
                project_storage_ref=f"project-value:{plan.plan_id}",
                compiler_id=plan.compiler_id,
                compiler_version=plan.compiler_version,
                operation_catalog_id=closure["catalog"].catalog_id,
                catalog_version=closure["catalog"].catalog_version,
                catalog_digest=closure["catalog"].catalog_digest,
                effect_closure_digest=plan.effect_closure_digest,
                authority_closure_digest=plan.authority_closure_digest,
                resource_closure_digest=plan.resource_closure_digest,
            )
            .on_conflict_do_nothing()
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_runs"]).values(
                run_id=assignment.run_id,
                project_key=PROJECT_KEY,
                project_registry_revision=REGISTRY_REVISION,
                project_scope_digest=SCOPE_DIGEST,
                resolved_schema=PROJECT_SCHEMA,
                program_id=program.program_id,
                program_digest=program.program_digest,
                plan_id=plan.plan_id,
                plan_digest=plan.plan_digest,
                state=run_state,
                revision=0,
                next_event_seq=1,
                execution_epoch=0,
                incarnation=RUN_INCARNATION,
                submission_authority_digest=canary._digest("p3-c2-23-submission"),
                qualification_digest=canary._digest("p3-c2-23-qualification"),
                cancellation_requested=False,
            )
        )
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_steps"]).values(
                project_key=PROJECT_KEY,
                run_id=assignment.run_id,
                step_id=assignment.step_id,
                operation_id=closure["plan"].ordered_steps[0].operation_id,
                operation_kind=closure["contract_ref"].kind,
                operation_version=closure["contract_ref"].contract_version,
                state=step_state,
                revision=0,
                execution_epoch=0,
                input_digest=assignment.input_closure_digest,
                effect_class="PURE_LOCAL_RESOLUTION",
                resource_class="CPU_LIGHT",
                concurrency_key=capability_id,
                capability_id=capability_id,
                claim_owner="successor",
                claim_authority_epoch=CANARY_EPOCH,
                claim_policy_digest=CLAIM_POLICY_DIGEST,
                max_attempts=2,
            )
        )
        _insert_work_item_and_approval(connection, closure, capability_id=capability_id)


def _persist_qualification(
    engine: Engine, closure: dict[str, Any], *, capability_id: str
) -> None:
    assignment = closure["assignment"]
    with engine.begin() as connection:
        ProgramRepository(
            connection, project_tables(sa.MetaData(), PROJECT_SCHEMA)
        ).put_exact(SCOPE, closure["program"], closure["program"].program_digest)
        PlanRepository(
            connection, project_tables(sa.MetaData(), PROJECT_SCHEMA)
        ).put_exact(
            SCOPE,
            closure["plan"],
            closure["plan"].plan_digest,
            operation_catalog_id=closure["catalog"].catalog_id,
            catalog_version=closure["catalog"].catalog_version,
            catalog_digest=closure["catalog"].catalog_digest,
        )
        context = PostgresAuthorityProvider(connection, SCOPE).current_context(
            ACTOR,
            capability_id=capability_id,
            approval_refs=(
                f"approval:p3-c2-23:{capability_id}:{assignment.work_item_id}",
            ),
            canonical_base_revision=0,
            canonical_incarnation=f"canonical:{assignment.run_id}:1",
            now=NOW,
        )
        authorization = StepAuthorizationBinding.from_content(
            run_id=assignment.run_id,
            step_id=assignment.step_id,
            operation_kind=closure["contract_ref"].kind,
            operation_contract_digest=closure["contract_ref"].contract_digest,
            capability_id=capability_id,
            claim_owner="successor",
            claim_authority_epoch=CANARY_EPOCH,
            claim_policy_digest=CLAIM_POLICY_DIGEST,
            payload_digest=assignment.payload_digest,
            actor_id=ACTOR,
            project_key=PROJECT_KEY,
            project_registry_revision=REGISTRY_REVISION,
            project_scope_digest=SCOPE_DIGEST,
            interpreter_binding_digest=closure["binding"].binding_digest,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            authority_source_bindings=context.authority_source_bindings,
            grants_digest=context.grants_digest,
            approval_refs=context.approval_refs or (),
            resource_ceiling_digest=context.resource_ceiling_digest,
            resource_policy_epoch=RESOURCE_POLICY_EPOCH,
            queue_eligibility_digest=_eligibility(capability_id).eligibility_digest,
            grant_epoch=context.grant_epoch,
            expires_at=context.expires_at,
            canonical_base_revision=0,
            canonical_incarnation=RUN_INCARNATION,
        )
        qualified = QualifiedPlan.from_content(
            plan_digest=closure["plan"].plan_digest,
            authority_context_digest=context.context_digest,
            step_bindings=(authorization,),
        )
        exact = ExactQualificationBinding.from_content(
            qualification_id=f"qualification:p3-c2-23:{assignment.work_item_id}",
            project_key=PROJECT_KEY,
            run_id=assignment.run_id,
            plan_id=closure["plan"].plan_id,
            plan_digest=closure["plan"].plan_digest,
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
                PUBLIC_TABLES["runtime_runs"].c.run_id == assignment.run_id,
            )
            .values(qualification_digest=qualified.qualification_digest, updated_at=NOW)
        )
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_work_items"])
            .where(
                PUBLIC_TABLES["runtime_work_items"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                == assignment.work_item_id,
            )
            .values(
                qualification_digest=qualified.qualification_digest,
                authority_digest=authorization.binding_digest,
                updated_at=NOW,
            )
        )


def _seed_payload(
    engine: Engine,
    closure: dict[str, Any],
    *,
    codec_id: str,
    object_type: str,
    plain_value: Any,
) -> None:
    ref = closure["payload_ref"]
    content = canonical_json(plain_value).encode("utf-8")
    assert content_digest(plain_value) == ref.content_digest
    with engine.begin() as connection:
        tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)
        ValueRepository(connection, tables).put_exact(
            SCOPE,
            value_id=ref.value_id,
            object_type=object_type,
            codec_id=codec_id,
            content=content,
            expected_digest=ref.content_digest,
            provenance_digest=ref.provenance_digest,
            expected_revision=PAYLOAD_PUT_REVISION,
            expected_incarnation=PAYLOAD_VALUE_INCARNATION,
            source_ref=ref.storage_ref,
            provenance={
                "schema": "mrw.p3-c2-23.payload-provenance.v1",
                "program_id": closure["program"].program_id,
                "content_digest": ref.content_digest,
            },
        )
        ValueRepository(connection, tables).get_exact(
            SCOPE,
            ref.value_id,
            expected_revision=PAYLOAD_VALUE_REVISION,
            expected_incarnation=PAYLOAD_VALUE_INCARNATION,
            expected_digest=ref.content_digest,
        )


def _build_node(engine: Engine, handlers: tuple[Any, ...]) -> RuntimeNode:
    uow_factory = runtime_uow_factory(engine)
    lifecycle = PostgresRuntimeNodeAdapter(uow_factory)
    resolver = ExactInstalledHandlerResolver(handlers)
    profile_digests = frozenset(
        handler.interpreter_profile_digest
        for handler in handlers
        if handler.interpreter_profile_digest
    )
    node = RuntimeNode(
        identity=NodeIdentity(
            node_id=NODE_ID,
            incarnation=NODE_INCARNATION,
            started_at=NOW - timedelta(minutes=1),
        ),
        profile=RuntimeNodeProfile(
            profile_digest=NODE_PROFILE_DIGEST,
            supported_assignment_kinds=frozenset(
                {AssignmentKind.INTERPRET, AssignmentKind.RECONCILE}
            ),
            interpreter_profile_digests=profile_digests,
        ),
        deployment=DeploymentBinding(
            catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            node_profile_digest=NODE_PROFILE_DIGEST,
            runtime_protocol_version="1",
        ),
        protocol=RuntimeNodeProtocol(
            version="1",
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
        clock=canary._TestClock(),
    )
    return node


def _c2_4_source(
    closure: dict[str, Any], outcome: Any
) -> SourceCollectionProjectionSource:
    record = CapturedSourceRecordRef(
        record_id="record:p3-c2-23:1",
        content_ref="content:p3-c2-23:1",
        content_digest=content_digest({"fixture": "p3-c2-23"}),
        source_ref="source:handler.cluster",
    )
    terminal = SourceCollectionTerminal(
        terminal_id="terminal:p3-c2-23",
        mode=closure["planning"].execution_request.source_mode.mode,
        status="ok",
        records_count=1,
    )
    return SourceCollectionProjectionSource(
        source_kind="RUNTIME_JOURNAL",
        source_ref="runtime-run:" + C2_3_RUN,
        run_id=C2_3_RUN,
        run_incarnation=RUN_INCARNATION,
        source_revision=1,
        source_incarnation="inc:p3-c2-23",
        source_digest="",
        project_key=PROJECT_KEY,
        project_scope_digest=SCOPE_DIGEST,
        source_mode=closure["planning"].execution_request.source_mode.mode,
        collection_outcome=CollectionCompleted(terminal=terminal),
        record_refs=(record,),
        ordered_failures=(),
        provider_handoff=None,
        observed_at="2030-09-01T08:00:00Z",
    )


def test_c2_23_runtime_canary_and_projection(
    disposable_canary_database: Engine,
) -> None:
    engine = disposable_canary_database
    payload, request = _resolved()
    c2_2 = _build_c2_2_closure(payload, request)
    planned = c22i.plan_source_mode(c2_2["planning"])
    assert isinstance(planned, c22.PlannedPlanning)
    effect_request = planned.plan.ordered_tasks[0].effect_request

    completed = c23_fixtures.build_deterministic_completed_outcome(
        effect_request,
        attempt_ref=c23_fixtures.build_fixture_attempt_ref(effect_request),
        records=(
            CapturedSourceRecordRef(
                record_id="record:p3-c2-23:1",
                content_ref="content:p3-c2-23:1",
                content_digest=content_digest({"fixture": "p3-c2-23"}),
                source_ref="source:handler.cluster",
            ),
        ),
        observed_at="2030-09-01T08:00:00Z",
    )
    unknown = c23_fixtures.build_deterministic_unknown_outcome(
        effect_request,
        attempt_ref=c23_fixtures.build_fixture_attempt_ref(effect_request),
    )
    unknown_request = dataclasses.replace(
        effect_request,
        request_id=effect_request.request_id + ":unknown",
        request_digest="",
    )
    unknown_attempt = c23_fixtures.build_fixture_attempt_ref(unknown_request)
    gateway = c23_fixtures.FixtureProviderEffectGateway(
        credentials=c23_fixtures.FixtureCredentialResolverPort(
            resolved_refs={"credential:/secret-ref/hc-api-key": "handler_cluster"}
        ),
        effect=c23_fixtures.FixtureProviderEffectPort(
            outcomes={
                effect_request.request_id: completed,
                unknown_request.request_id: unknown,
            }
        ),
        readback=c23_fixtures.FixtureProviderReadbackPort(
            readbacks={
                unknown_attempt.attempt_id: c23.ReadbackTerminal(
                    readback=c23.AuthoritativeProviderReadback(
                        attempt_ref=unknown_attempt.as_ref_string(),
                        provider_job_id="job:p3-c2-23",
                        terminal_status="COMPLETED",
                        readback_receipt_id="readback:p3-c2-23",
                        observed_at="2030-09-01T08:01:00Z",
                    )
                )
            }
        ),
    )

    c2_3_completed = _build_c2_3_closure(
        dataclasses.replace(effect_request, request_id=effect_request.request_id),
        run_id=C2_3_RUN,
        work_item_id=C2_3_WORK,
        program_id="program:p3-c2-23:c2-3",
    )
    c2_3_unknown = _build_c2_3_closure(
        unknown_request,
        run_id=C2_3_UNKNOWN_RUN,
        work_item_id=C2_3_UNKNOWN_WORK,
        program_id="program:p3-c2-23:c2-3-unknown",
    )
    recovery = build_recovery_c2_3_binding(
        interpreter_profile_digest=c2_3_completed["binding"].interpreter_profile_digest
    )

    _seed_base(engine)
    _seed_closure(engine, c2_2, capability_id=C2_2_CAPABILITY)
    _persist_qualification(engine, c2_2, capability_id=C2_2_CAPABILITY)
    _seed_payload(
        engine,
        c2_2,
        codec_id=c22.SOURCE_MODE_PLANNING_PAYLOAD_TYPE.codec_id,
        object_type=c22.SOURCE_MODE_PLANNING_PAYLOAD_TYPE.type_id,
        plain_value=__import__("dataclasses").asdict(c2_2["planning"]),
    )

    legacy_c2_2 = build_legacy_c2_2_binding(
        contract_digest=c2_2["contract_ref"].contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        runtime_protocol_version="1",
    )
    legacy_c2_3 = build_legacy_c2_3_binding(
        contract_digest=c2_3_completed["contract_ref"].contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        runtime_protocol_version="1",
    )
    assert legacy_c2_2.binding_digest != c2_2["binding"].binding_digest
    assert legacy_c2_3.binding_digest != c2_3_completed["binding"].binding_digest
    assert c2_2["plan"].program_digest == c2_2["program"].program_digest
    assert (
        c2_3_completed["plan"].program_digest
        == c2_3_completed["program"].program_digest
    )
    c2_2_handler = C2_2StoreRehydratedHandler(
        uow_factory=runtime_uow_factory(engine),
        handler_binding_digest=c2_2["binding"].binding_digest,
        interpreter_profile_digest=c2_2["binding"].interpreter_profile_digest,
        operation_contract_digest=c2_2["contract_ref"].contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
    )
    c2_3_handler = C2_3StoreRehydratedHandler(
        uow_factory=runtime_uow_factory(engine),
        handler_binding_digest=c2_3_completed["binding"].binding_digest,
        interpreter_profile_digest=c2_3_completed["binding"].interpreter_profile_digest,
        operation_contract_digest=c2_3_completed["contract_ref"].contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        gateway=gateway,
    )
    node = _build_node(engine, (c2_2_handler, c2_3_handler))
    report = node.run_once()
    assert report.claimed == 1
    assert report.results[0].state.value == "COMMITTED"
    assert report.results[0].disposition.value == "SUCCEEDED", report.results[0]
    assert c2_2_handler.provider_calls == 0

    with engine.connect() as connection:
        attempts = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                    PUBLIC_TABLES["runtime_effect_attempts"].c.run_id == C2_2_RUN
                )
            )
            .mappings()
            .all()
        )
        reservations = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_resource_reservations"]).where(
                    PUBLIC_TABLES["runtime_resource_reservations"].c.run_id == C2_2_RUN
                )
            )
            .mappings()
            .all()
        )
    assert len(attempts) == 1
    assert len(reservations) == 1

    _seed_closure(engine, c2_3_completed, capability_id=C2_3_CAPABILITY)
    _persist_qualification(engine, c2_3_completed, capability_id=C2_3_CAPABILITY)
    _seed_payload(
        engine,
        c2_3_completed,
        codec_id=c23.SOURCE_LIBRARY_C2_3_PAYLOAD_CODEC_ID,
        object_type=c23.SOURCE_LIBRARY_C2_3_PAYLOAD_TYPE.type_id,
        plain_value=c2_3_completed["request"].to_plain(),
    )
    report = node.run_once()
    assert report.claimed == 1
    assert report.results[0].state.value == "COMMITTED"
    assert report.results[0].disposition.value == "SUCCEEDED"
    assert c2_3_handler.real_provider_calls == 0
    assert len(c2_3_handler.fixture_calls) == 1

    _seed_closure(engine, c2_3_unknown, capability_id=C2_3_CAPABILITY)
    _persist_qualification(engine, c2_3_unknown, capability_id=C2_3_CAPABILITY)
    _seed_payload(
        engine,
        c2_3_unknown,
        codec_id=c23.SOURCE_LIBRARY_C2_3_PAYLOAD_CODEC_ID,
        object_type=c23.SOURCE_LIBRARY_C2_3_PAYLOAD_TYPE.type_id,
        plain_value=c2_3_unknown["request"].to_plain(),
    )
    report = node.run_once()
    assert report.claimed == 1
    assert report.results[0].state.value == "COMMITTED"
    assert report.results[0].disposition.value == "OUTCOME_UNKNOWN"
    assert len(c2_3_handler.fixture_calls) == 2
    with engine.connect() as connection:
        unknown_work = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_work_items"]).where(
                    PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                    == C2_3_UNKNOWN_WORK
                )
            )
            .mappings()
            .one()
        )
        unknown_run = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_runs"]).where(
                    PUBLIC_TABLES["runtime_runs"].c.run_id == C2_3_UNKNOWN_RUN
                )
            )
            .mappings()
            .one()
        )
        unknown_step = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_steps"]).where(
                    PUBLIC_TABLES["runtime_steps"].c.run_id == C2_3_UNKNOWN_RUN,
                    PUBLIC_TABLES["runtime_steps"].c.step_id
                    == c2_3_unknown["assignment"].step_id,
                )
            )
            .mappings()
            .one()
        )
    unknown_authority_digest = str(unknown_work["authority_digest"])
    unknown_qualification_digest = str(unknown_run["qualification_digest"])
    unknown_step_revision = int(unknown_step["revision"])

    # RECONCILE work item bound to the unknown attempt; readback only.
    with engine.connect() as connection:
        unknown_attempt_row = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                    PUBLIC_TABLES["runtime_effect_attempts"].c.run_id
                    == C2_3_UNKNOWN_RUN
                )
            )
            .mappings()
            .first()
        )
    assert unknown_attempt_row is not None
    original_attempt_id = str(unknown_attempt_row["attempt_id"])
    reconcile_readback = c23_fixtures.FixtureProviderReadbackPort(
        readbacks={
            original_attempt_id: c23.ReadbackTerminal(
                readback=c23.AuthoritativeProviderReadback(
                    attempt_ref=original_attempt_id,
                    provider_job_id="job:p3-c2-23",
                    terminal_status="COMPLETED",
                    readback_receipt_id="readback:p3-c2-23",
                    observed_at="2030-09-01T08:01:00Z",
                )
            )
        }
    )
    reconcile_assignment = c2_3_unknown["assignment"].model_copy(
        update={
            "work_item_id": C2_3_RECONCILE_WORK,
            "run_id": C2_3_UNKNOWN_RUN,
            "assignment_kind": AssignmentKind.RECONCILE,
            "handler_binding_kind": HandlerBindingKind.RECOVERY,
            "handler_binding_ref": f"handler-binding:sha256:{recovery.binding_digest}",
            "handler_binding_digest": recovery.binding_digest,
            "handler_binding": recovery,
            "return_contract_binding": None,
            "expected_step_revision": unknown_step_revision,
            "reconciliation_attempt_id": original_attempt_id,
        }
    )
    reconcile_closure = dict(c2_3_unknown)
    reconcile_closure["assignment"] = reconcile_assignment
    reconcile_closure["binding"] = recovery
    reconcile_closure["recovery_binding"] = recovery
    reconcile_handler = C2_3ReconcileHandler(
        request=c2_3_unknown["request"],
        binding=recovery,
        operation_contract_digest=c2_3_completed["contract_ref"].contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        readback=reconcile_readback,
    )
    node = _build_node(engine, (c2_2_handler, c2_3_handler, reconcile_handler))
    _seed_closure(
        engine,
        reconcile_closure,
        capability_id=C2_3_CAPABILITY,
        run_state="RECONCILING",
        step_state="RECONCILING",
        work_item_only=True,
        qualification_digest=unknown_qualification_digest,
        authority_digest=unknown_authority_digest,
        expected_step_revision=unknown_step_revision,
    )
    report = node.run_once()
    assert report.claimed == 1
    assert report.results[0].state.value == "COMMITTED"
    assert report.results[0].disposition.value == "SUCCEEDED"
    assert len(reconcile_handler.readback_calls) == 1
    assert len(c2_3_handler.fixture_calls) == 2  # no re-execute after readback

    # Counterexample: authoritative FAILED readback stays FAILED, never SUCCEEDED.
    failed_request = dataclasses.replace(
        effect_request,
        request_id=effect_request.request_id + ":unknown-failed",
        request_digest="",
    )
    c2_3_failed = _build_c2_3_closure(
        failed_request,
        run_id=C2_3_FAILED_RUN,
        work_item_id=C2_3_FAILED_WORK,
        program_id="program:p3-c2-23:c2-3-failed",
    )
    gateway.effect._outcomes[failed_request.request_id] = (
        c23_fixtures.build_deterministic_unknown_outcome(
            failed_request,
            attempt_ref=c23_fixtures.build_fixture_attempt_ref(failed_request),
        )
    )
    _seed_closure(engine, c2_3_failed, capability_id=C2_3_CAPABILITY)
    _persist_qualification(engine, c2_3_failed, capability_id=C2_3_CAPABILITY)
    _seed_payload(
        engine,
        c2_3_failed,
        codec_id=c23.SOURCE_LIBRARY_C2_3_PAYLOAD_CODEC_ID,
        object_type=c23.SOURCE_LIBRARY_C2_3_PAYLOAD_TYPE.type_id,
        plain_value=c2_3_failed["request"].to_plain(),
    )
    report = node.run_once()
    assert report.claimed == 1
    assert report.results[0].disposition.value == "OUTCOME_UNKNOWN"
    with engine.connect() as connection:
        failed_attempt = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                    PUBLIC_TABLES["runtime_effect_attempts"].c.run_id == C2_3_FAILED_RUN
                )
            )
            .mappings()
            .one()
        )
        failed_work = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_work_items"]).where(
                    PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                    == C2_3_FAILED_WORK
                )
            )
            .mappings()
            .one()
        )
        failed_run = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_runs"]).where(
                    PUBLIC_TABLES["runtime_runs"].c.run_id == C2_3_FAILED_RUN
                )
            )
            .mappings()
            .one()
        )
        failed_step = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_steps"]).where(
                    PUBLIC_TABLES["runtime_steps"].c.run_id == C2_3_FAILED_RUN,
                    PUBLIC_TABLES["runtime_steps"].c.step_id
                    == c2_3_failed["assignment"].step_id,
                )
            )
            .mappings()
            .one()
        )
    failed_attempt_id = str(failed_attempt["attempt_id"])
    failed_recovery = canary.RecoveryBinding.from_content(
        recovery_handler_id="recovery.source_library.c2_3.fixture_failed_readback.v1",
        recovery_handler_version="1",
        interpreter_profile_digest=c2_3_failed["binding"].interpreter_profile_digest,
        authoritative_readback_profile_ref="mrw.successor.source-library.c2-3.readback.v1",
    )
    failed_readback = c23_fixtures.FixtureProviderReadbackPort(
        readbacks={
            failed_attempt_id: c23.ReadbackTerminal(
                readback=c23.AuthoritativeProviderReadback(
                    attempt_ref=failed_attempt_id,
                    provider_job_id="job:p3-c2-23-failed",
                    terminal_status="FAILED",
                    readback_receipt_id="readback:p3-c2-23-failed",
                    observed_at="2030-09-01T08:02:00Z",
                )
            )
        }
    )
    failed_reconcile_assignment = c2_3_failed["assignment"].model_copy(
        update={
            "work_item_id": C2_3_FAILED_RECONCILE_WORK,
            "run_id": C2_3_FAILED_RUN,
            "assignment_kind": AssignmentKind.RECONCILE,
            "handler_binding_kind": HandlerBindingKind.RECOVERY,
            "handler_binding_ref": (
                f"handler-binding:sha256:{failed_recovery.binding_digest}"
            ),
            "handler_binding_digest": failed_recovery.binding_digest,
            "handler_binding": failed_recovery,
            "return_contract_binding": None,
            "expected_step_revision": int(failed_step["revision"]),
            "reconciliation_attempt_id": failed_attempt_id,
        }
    )
    failed_reconcile_closure = dict(c2_3_failed)
    failed_reconcile_closure["assignment"] = failed_reconcile_assignment
    failed_reconcile_closure["binding"] = failed_recovery
    failed_reconcile_closure["recovery_binding"] = failed_recovery
    failed_reconcile_handler = C2_3ReconcileHandler(
        request=failed_request,
        binding=failed_recovery,
        operation_contract_digest=c2_3_failed["contract_ref"].contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        readback=failed_readback,
    )
    node = _build_node(
        engine,
        (c2_2_handler, c2_3_handler, reconcile_handler, failed_reconcile_handler),
    )
    _seed_closure(
        engine,
        failed_reconcile_closure,
        capability_id=C2_3_CAPABILITY,
        run_state="RECONCILING",
        step_state="RECONCILING",
        work_item_only=True,
        qualification_digest=str(failed_run["qualification_digest"]),
        authority_digest=str(failed_work["authority_digest"]),
        expected_step_revision=int(failed_step["revision"]),
    )
    report = node.run_once()
    assert report.claimed == 1
    assert report.results[0].state.value == "COMMITTED"
    assert report.results[0].disposition.value == "FAILED"
    assert failed_reconcile_handler.readback_calls == [failed_attempt_id]
    assert len(c2_3_handler.fixture_calls) == 3  # failed readback never re-executes

    # Mixed Program A + Plan B must fail closed before any effect/terminal.
    program_b = c22p.build_source_library_c2_2_program(
        payload=c2_2["planning"],
        catalog=c22.build_source_library_c2_2_catalog(
            c22.build_source_library_c2_2_bundle()
        ),
        program_id="p3-mixed-program-b",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan_b = c22p.compile_source_library_c2_2_program(
        program_b,
        c22.build_source_library_c2_2_catalog(c22.build_source_library_c2_2_bundle()),
        operation_contracts=c22.build_source_library_c2_2_registry(
            c22.build_source_library_c2_2_bundle()
        ),
    )
    mixed_assignment = c2_2["assignment"].model_copy(
        update={
            "work_item_id": C2_2_MIXED_WORK,
            "run_id": C2_2_MIXED_RUN,
            "program_digest": c2_2["program"].program_digest,
            "plan_digest": plan_b.plan_digest,
        }
    )
    mixed_closure = dict(c2_2)
    mixed_closure["assignment"] = mixed_assignment
    mixed_closure["plan"] = plan_b
    with engine.begin() as connection:
        connection.execute(
            pg_insert(PUBLIC_TABLES["runtime_program_refs"])
            .values(
                program_id=program_b.program_id,
                project_key=PROJECT_KEY,
                program_digest=program_b.program_digest,
                project_storage_ref=f"project-value:{program_b.program_id}",
                contract_version=program_b.contract_version,
            )
            .on_conflict_do_nothing()
        )
        ProgramRepository(
            connection, project_tables(sa.MetaData(), PROJECT_SCHEMA)
        ).put_exact(SCOPE, program_b, program_b.program_digest)
    _seed_closure(engine, mixed_closure, capability_id=C2_2_CAPABILITY)
    _persist_qualification(engine, mixed_closure, capability_id=C2_2_CAPABILITY)
    _seed_payload(
        engine,
        mixed_closure,
        codec_id=c22.SOURCE_MODE_PLANNING_PAYLOAD_TYPE.codec_id,
        object_type=c22.SOURCE_MODE_PLANNING_PAYLOAD_TYPE.type_id,
        plain_value=__import__("dataclasses").asdict(c2_2["planning"]),
    )
    from app.successor_runtime.runtime.claims import ClaimBinding as _ClaimBinding
    from app.successor_runtime.runtime.node import (
        DefiniteInterpreterFailure as _DefiniteInterpreterFailure,
    )
    from app.successor_runtime.runtime.node import (
        RuntimeExecutionContext as _RuntimeExecutionContext,
    )

    direct_handler = C2_2StoreRehydratedHandler(
        uow_factory=runtime_uow_factory(engine),
        handler_binding_digest=c2_2["binding"].binding_digest,
        interpreter_profile_digest=c2_2["binding"].interpreter_profile_digest,
        operation_contract_digest=c2_2["contract_ref"].contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
    )
    direct_claim = _ClaimBinding.bind(
        mixed_assignment,
        authorization_digest=canary._digest("c2-2-mixed-authority"),
        lease_token="lease:p3-c2-23-mixed",
        lease_expires_at=NOW + timedelta(minutes=5),
        node_id=NODE_ID,
        node_profile_digest=NODE_PROFILE_DIGEST,
        authority_digest=canary._digest("c2-2-mixed-authority"),
        interpreter_profile_digest=c2_2["binding"].interpreter_profile_digest,
    )
    with pytest.raises(_DefiniteInterpreterFailure) as mixed_exc:
        direct_handler.execute(
            mixed_assignment,
            direct_claim,
            _RuntimeExecutionContext(
                node=NodeIdentity(
                    node_id=NODE_ID,
                    incarnation=NODE_INCARNATION,
                    started_at=NOW - timedelta(minutes=1),
                ),
                observed_at=NOW,
            ),
        )
    assert mixed_exc.value.failure_code == "C2_2_PLAN_PROGRAM_BINDING_MISMATCH"
    with engine.connect() as connection:
        mixed_attempts = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                    PUBLIC_TABLES["runtime_effect_attempts"].c.run_id == C2_2_MIXED_RUN
                )
            )
            .mappings()
            .all()
        )
        mixed_work = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_work_items"]).where(
                    PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                    == C2_2_MIXED_WORK
                )
            )
            .mappings()
            .one()
        )
    assert not mixed_attempts
    assert mixed_work["state"] == "READY"
    assert mixed_work["lease_token"] is None
    assert c2_2_handler.provider_calls == 0

    from app.successor_runtime.substrate.postgres.work_items import (
        ClaimBindingMismatch as _ClaimBindingMismatch,
    )

    mixed_node = _build_node(engine, (direct_handler, c2_3_handler))
    with pytest.raises(_ClaimBindingMismatch):
        mixed_node.run_once()
    assert c2_2_handler.provider_calls == 0
    with engine.connect() as connection:
        mixed_events = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_events"]).where(
                    PUBLIC_TABLES["runtime_events"].c.run_id == C2_2_MIXED_RUN
                )
            )
            .mappings()
            .all()
        )
        mixed_attempts = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                    PUBLIC_TABLES["runtime_effect_attempts"].c.run_id == C2_2_MIXED_RUN
                )
            )
            .mappings()
            .all()
        )
        mixed_work_after = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_work_items"]).where(
                    PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                    == C2_2_MIXED_WORK
                )
            )
            .mappings()
            .one()
        )
    assert not mixed_events
    assert not mixed_attempts
    assert mixed_work_after["state"] == "READY"
    assert mixed_work_after["lease_token"] is None

    # C2.4 projection binds the same journal closure on the same database.
    source = _c2_4_source(c2_2, completed)
    with engine.connect() as connection:
        projector = PostgresSourceLibraryTerminalProjector(
            connection,
            project_key=PROJECT_KEY,
            table=PROJECTION_TABLE,
        )
        applied = projector.apply(source)
        rebuilt = projector.rebuild(source)
        assert (
            rebuilt.terminal["projection_digest"]
            == applied.terminal["projection_digest"]
        )
        assert rebuilt.generation == 1
        projector.delete(source)
        with pytest.raises(KeyError):
            projector.load(source)

    # Rollback: future owner switches to legacy; rows/journals retained.
    rollback = rollback_read_routing()
    assert rollback.claim_owner == "legacy"
    assert rollback.projection_rows_retained is True
