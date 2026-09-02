"""Real-PostgreSQL RuntimeNode canary for the P3 C3 collect family.

The test owns a disposable database named ``mrw_p3_c3_worker_test``: it drops
any prior database, creates it, installs the frozen public schema plus the
family project schema, seeds one exact successor work item, claims and
executes it through a real ``RuntimeNode``/``PostgresRuntimeNodeAdapter``
path, and drops the database again on teardown.  The handler runs the
deterministic no-provider ordered traversal and fold for the compiled
TraverseOrdered successor Program epoch with ``provider_calls=0``.
Rollback switches only the future claim owner back to legacy.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from app.successor_migration.legacy_collect_runtime import (
    build_legacy_collect_c3_1_binding,
    build_successor_collect_c3_2_binding,
)
from app.successor_runtime.capabilities import collect_c3 as c3
from app.successor_runtime.capabilities import collect_c3_interpreters as ci
from app.successor_runtime.capabilities import collect_c3_program as cp
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    sha256_hex,
)
from app.successor_runtime.language.algebra import freeze_json_object
from app.successor_runtime.language.object_contracts import OperationContractRef
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
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
    DefiniteInterpreterFailure,
    DeploymentBinding,
    NodeIdentity,
    RuntimeExecutionContext,
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
from app.successor_runtime.substrate.postgres.approvals import (
    ApprovalBinding,
    ApprovalRepository,
)
from app.successor_runtime.substrate.postgres.authority import (
    AuthorityGrant,
    AuthorityGrantRepository,
    CapabilityAuthorityRepository,
)
from app.successor_runtime.substrate.postgres.authority_provider import (
    PostgresAuthorityProvider,
)
from app.successor_runtime.substrate.postgres.collect_c3_canary import (
    C3CollectComposedRuntimeHandler,
    C3CollectRollbackService,
    CanaryPhase,
    authority_digest,
    select_future_owner,
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
    RuntimeJournalRepository,
    StaleRevisionError,
)
from app.successor_runtime.substrate.postgres.session import (
    compute_scope_digest,
    create_runtime_engine,
)
from app.successor_runtime.substrate.postgres.unit_of_work import RuntimeUnitOfWork
from app.successor_runtime.substrate.postgres.values import ValueRepository

pytestmark = pytest.mark.integration

DATABASE_NAME = "mrw_p3_c3_worker_test"
DATABASE_ENV = "SUCCESSOR_TEST_DATABASE_URL"
PROJECT_KEY = "p3-c3-canary-postgres"
PROJECT_SCHEMA = "mrw_p3_c3_canary"
REGISTRY_REVISION = 1
SCOPE_INCARNATION = "c3-canary-incarnation-1"
SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY,
    PROJECT_SCHEMA,
    REGISTRY_REVISION,
    SCOPE_INCARNATION,
)
ACTOR = "human:c3-canary-postgres"
RUN_ID = "run:p3-c3-canary"
RUN_INCARNATION = "run-inc:c3-canary"
PROGRAM_ID = "program:p3-c3-canary"
TRAVERSAL_PROGRAM_ID = "program:p3-c3-canary-traversal"
PURE_FOLD_PROGRAM_ID = "program:p3-c3-canary-pure-fold"
WORK_ITEM_ID = "work:p3-c3-canary"
CAPABILITY_ID = "collect.c3_1.v1"
ROLLBACK_TARGET = "rollback:legacy:c3"
CANARY_APPROVAL_ID = "approval:c3-promote-canary"
ROLLBACK_APPROVAL_ID = "approval:c3-rollback-legacy"
CANARY_EPOCH = 1
NODE_ID = "node:c3-canary"
NODE_INCARNATION = "node-inc:c3-canary"
NOW = datetime(2030, 9, 1, 8, 0, tzinfo=UTC)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


ALLOWLIST_DIGEST = _digest("c3-allowlist")
CONFIG_DIGEST = _digest("c3-config")
DEPLOYMENT_CATALOG_DIGEST = c3.deployment_catalog_digest()
CLAIM_POLICY_DIGEST = _digest("c3-claim-policy")
RESOURCE_POLICY_DIGEST = _digest("c3-resource-policy")
NODE_PROFILE_DIGEST = _digest("c3-node-profile")
QUALIFICATION_DIGEST = _digest("c3-qualification")
RESOURCE_POLICY_EPOCH = 1

QUEUE_ELIGIBILITY = QueueEligibility(
    project_key=PROJECT_KEY,
    capability_id=CAPABILITY_ID,
    resource_class=ResourceClass.CPU_LIGHT,
    units=1,
    policy_epoch=RESOURCE_POLICY_EPOCH,
    policy_digest=RESOURCE_POLICY_DIGEST,
    concurrency_key="c3:concurrency",
    provider_key="provider:c3-local-pure-only",
)
QUEUE_ELIGIBILITY_DIGEST = QUEUE_ELIGIBILITY.eligibility_digest

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


@dataclass(frozen=True, slots=True)
class _C3Fixture:
    bundle: Any
    catalog: Any
    registry: Any
    contract_ref: Any
    payload: Any
    composed_program: Any
    composed_plan: Any
    pure_fold_program: Any
    pure_fold_plan: Any
    step: Any
    step_id: str
    payload_value_ref: Any
    successor_binding: Any
    legacy_binding: Any
    recovery_binding: Any
    return_binding: Any
    assignment: Any
    element_payloads: tuple[Any, ...]
    family_plan: Any
    expected_aggregate_digest: str
    shadow_before_digest: str
    canary_after_digest: str
    rollback_after_digest: str


_C3: _C3Fixture | None = None


def _snapshot() -> c3.CollectLegacyRequestSnapshot:
    return c3.CollectLegacyRequestSnapshot(
        schema_version=c3.COLLECT_REQUEST_SNAPSHOT_SCHEMA_REF,
        flow="collect",
        channel="search.market",
        project_key=PROJECT_KEY,
        query_terms=("t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8"),
        urls=(),
        limit=80,
        options=c3.freeze_json_object({}),
        source_context=c3.freeze_json_object({}),
        snapshot_digest="",
    )


def _policy() -> c3.CollectResourcePolicy:
    return c3.CollectResourcePolicy(
        schema_ref=c3.COLLECT_RESOURCE_POLICY_SCHEMA_REF,
        max_parallelism=2,
        deadline_seconds=60,
        cancellation="COORDINATED",
        backpressure=True,
        provider_concurrency_key="search.market",
        policy_digest="",
    )


def _c3() -> _C3Fixture:
    global _C3
    if _C3 is not None:
        return _C3

    bundle = c3.build_collect_c3_bundle()
    catalog = c3.build_collect_c3_catalog(bundle)
    registry = c3.build_collect_c3_registry(bundle)
    contract_ref = cp.exact_contract_ref(catalog, kind=c3.COLLECT_C3_1_KIND)
    request_ref = c3.build_collect_request_ref(
        request_id="c3-canary-request",
        project_key=PROJECT_KEY,
        channel="search.market",
    )
    snapshot = _snapshot()
    policy = _policy()
    family_plan = c3.build_collect_batch_plan(
        request_ref=request_ref,
        snapshot=snapshot,
        plan_id=f"shadow:{PROGRAM_ID}",
        resource_policy=policy,
        authority_scope_ref="project:p3-c3-canary-postgres",
    )
    element_payloads = tuple(
        c3.collect_batch_element_payload_from_dicts(
            request_ref=request_ref.to_plain(),
            request_snapshot=snapshot.to_plain(),
            element=family_plan.elements[index].to_plain(),
            resource_policy=policy.to_plain(),
            authority_scope_ref="project:p3-c3-canary-postgres",
        )
        for index in range(len(family_plan.elements))
    )
    composed_program = cp.build_collect_c3_composed_program(
        element_payloads=element_payloads,
        catalog=catalog,
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    composed_plan = _compile_with_registry(composed_program, catalog, registry)
    effect_steps = tuple(
        step
        for step in composed_plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    )
    if len(effect_steps) != 1:  # pragma: no cover - fixture guard
        raise RuntimeError("composed C3 plan must compile exactly one EFFECT step")
    step = effect_steps[0]
    if step.operation_contract_ref.kind != c3.COLLECT_C3_2_KIND:
        raise RuntimeError("composed fold step must bind the C3.2 fold contract")
    step_id = step.step_id
    fold_contract_ref = bundle.operation_c3_2.ref

    value_ref = cp.build_family_payload_value_ref(
        element_payloads,
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
    )

    fold_sequence = c3.OrderedCollectElementOutcomeSequence(
        schema_version="mrw.successor.collect.c3.outcome-sequence.v1",
        parent_request_ref=request_ref,
        outcomes=(
            c3.CollectElementSucceeded(
                schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
                element_id="e0",
                input_index=0,
                counts=c3.CollectCounts(inserted=1),
                legacy_observation_ref="legacy:" + "0" * 64,
                outcome_digest="",
            ),
        ),
        sequence_digest="",
    )
    fold_payload = c3.build_collect_fold_payload(
        parent_request_ref=request_ref,
        ordered_outcomes=fold_sequence,
    )
    pure_fold_program = cp.build_collect_c3_2_pure_fold_program(
        payload=fold_payload,
        catalog=catalog,
        program_id=PURE_FOLD_PROGRAM_ID,
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    pure_fold_plan = _compile_with_registry(pure_fold_program, catalog, registry)

    successor_binding = build_successor_collect_c3_2_binding(
        contract_digest=fold_contract_ref.contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        runtime_protocol_version="1",
    )
    legacy_binding = build_legacy_collect_c3_1_binding(
        contract_digest=contract_ref.contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        runtime_protocol_version="1",
    )
    recovery_binding = RecoveryBinding.from_content(
        recovery_handler_id="recovery.c3-2.local-pure",
        recovery_handler_version="1",
        interpreter_profile_digest=successor_binding.interpreter_profile_digest,
        authoritative_readback_profile_ref="readback:c3-aggregate-outcome.v1",
    )
    return_binding = ReturnContractBinding.from_contract(
        step.return_contract_ref or "mrw.return.runtime-value.v1",
        step.return_contract,
    )
    assignment = RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id=WORK_ITEM_ID,
        assignment_kind=AssignmentKind.INTERPRET,
        project_key=PROJECT_KEY,
        run_id=RUN_ID,
        step_id=step_id,
        step_role=CompiledStepRole.EFFECT,
        capability_id=CAPABILITY_ID,
        operation_contract_ref=OperationContractRef(
            kind=fold_contract_ref.kind,
            contract_version=fold_contract_ref.contract_version,
            contract_digest=fold_contract_ref.contract_digest,
        ),
        operation_contract_digest=fold_contract_ref.contract_digest,
        return_contract_binding=return_binding,
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=(
            f"handler-binding:sha256:{successor_binding.binding_digest}"
        ),
        handler_binding_digest=successor_binding.binding_digest,
        handler_binding=successor_binding,
        program_digest=composed_program.program_digest,
        plan_digest=composed_plan.plan_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        execution_epoch=0,
        incarnation=RUN_INCARNATION,
        input_refs=(value_ref.storage_ref,),
        input_closure_digest=sha256_hex(
            canonical_json({"input_refs": (value_ref.storage_ref,)}).encode("utf-8")
        ),
        payload_ref=value_ref.storage_ref,
        payload_digest=value_ref.content_digest,
        queue_eligibility_digest=QUEUE_ELIGIBILITY_DIGEST,
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        claim_authority_epoch=CANARY_EPOCH,
        claim_policy_digest=CLAIM_POLICY_DIGEST,
        expected_step_revision=0,
        trace_id=f"trace:{RUN_ID}",
    )

    class _ExpectedRunner:
        def run(self, element: c3.CollectBatchElement) -> c3.CollectElementOutcome:
            return c3.CollectElementSucceeded(
                schema_version=c3.COLLECT_ELEMENT_OUTCOME_SCHEMA_REF,
                element_id=element.element_id,
                input_index=element.input_index,
                counts=c3.CollectCounts(inserted=len(element.query_terms)),
                links=tuple(
                    f"https://shadow.example/{term}" for term in element.query_terms
                ),
                receipt=None,
                legacy_observation_ref="legacy:"
                + content_digest(
                    {
                        "schema": "mrw.successor.collect.c3.shadow-element.v1",
                        "element_id": element.element_id,
                        "input_index": element.input_index,
                    }
                ),
                outcome_digest="",
            )

    traversal_result = ci.run_ordered_traversal(family_plan, _ExpectedRunner())
    observation = getattr(traversal_result, "observation", None)
    if observation is None:  # pragma: no cover - fixture guard
        raise RuntimeError("canary fixture traversal aborted")
    sequence = c3.OrderedCollectElementOutcomeSequence(
        schema_version="mrw.successor.collect.c3.outcome-sequence.v1",
        parent_request_ref=request_ref,
        outcomes=observation.ordered_outcomes,
        sequence_digest="",
    )
    aggregate = c3.fold_ordered_results(
        sequence,
        aggregation_policy_ref=c3.COLLECT_AGGREGATION_POLICY_ACCUMULATE_REF,
        observation_profile_ref=c3.COLLECT_FOLD_OBSERVATION_PROFILE,
    )
    assert isinstance(aggregate, c3.CollectAggregateSucceeded)
    expected_aggregate_digest = aggregate.aggregate_digest

    shadow_before_digest = authority_digest(
        project_key=PROJECT_KEY,
        capability_id=CAPABILITY_ID,
        mode=CanaryPhase.SHADOW.mode,
        authority_epoch=0,
        successor_claim_enabled=False,
        legacy_claim_enabled=True,
        allowlist_digest=ALLOWLIST_DIGEST,
        config_digest=CONFIG_DIGEST,
        effective_at=NOW,
        updated_by=ACTOR,
        approval_ref="approval:c3-shadow-baseline",
        rollback_target_ref=ROLLBACK_TARGET,
        revision=0,
    )
    canary_after_digest = authority_digest(
        project_key=PROJECT_KEY,
        capability_id=CAPABILITY_ID,
        mode=CanaryPhase.CANARY.mode,
        authority_epoch=CANARY_EPOCH,
        successor_claim_enabled=True,
        legacy_claim_enabled=False,
        allowlist_digest=ALLOWLIST_DIGEST,
        config_digest=CONFIG_DIGEST,
        effective_at=NOW,
        updated_by=ACTOR,
        approval_ref=CANARY_APPROVAL_ID,
        rollback_target_ref=ROLLBACK_TARGET,
        revision=1,
    )
    rollback_after_digest = authority_digest(
        project_key=PROJECT_KEY,
        capability_id=CAPABILITY_ID,
        mode=CanaryPhase.OFF.mode,
        authority_epoch=CANARY_EPOCH + 1,
        successor_claim_enabled=False,
        legacy_claim_enabled=True,
        allowlist_digest=ALLOWLIST_DIGEST,
        config_digest=CONFIG_DIGEST,
        effective_at=NOW,
        updated_by=ACTOR,
        approval_ref=ROLLBACK_APPROVAL_ID,
        rollback_target_ref=ROLLBACK_TARGET,
        revision=2,
    )
    _C3 = _C3Fixture(
        bundle=bundle,
        catalog=catalog,
        registry=registry,
        contract_ref=contract_ref,
        payload=element_payloads[0],
        composed_program=composed_program,
        composed_plan=composed_plan,
        pure_fold_program=pure_fold_program,
        pure_fold_plan=pure_fold_plan,
        step=step,
        step_id=step_id,
        payload_value_ref=value_ref,
        successor_binding=successor_binding,
        legacy_binding=legacy_binding,
        recovery_binding=recovery_binding,
        return_binding=return_binding,
        assignment=assignment,
        element_payloads=element_payloads,
        family_plan=family_plan,
        expected_aggregate_digest=expected_aggregate_digest,
        shadow_before_digest=shadow_before_digest,
        canary_after_digest=canary_after_digest,
        rollback_after_digest=rollback_after_digest,
    )
    return _C3


def _compile_with_registry(program: Any, catalog: Any, registry: Any) -> Any:
    from app.successor_runtime.language.compile import compile_program

    return compile_program(
        program,
        catalog,
        operation_contracts=registry,
        transform_registry=cp.build_collect_c3_transform_registry(),
    )


def _server_url() -> str:
    env_url = os.environ.get(DATABASE_ENV)
    if env_url:
        url = make_url(env_url)
        return url.set(database="postgres").render_as_string(hide_password=False)
    return "postgresql+psycopg2://localhost/postgres"


def _create_database() -> Engine:
    server_url = _server_url()
    server = sa.create_engine(
        server_url, isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    try:
        with server.connect() as connection:
            connection.execute(
                sa.text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
            connection.execute(sa.text("CREATE DATABASE " + DATABASE_NAME))
    except Exception as exc:  # noqa: BLE001 - environment-dependent skip
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
def disposable_database() -> Iterator[Engine]:
    server = _create_database()
    engine = create_runtime_engine(
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
        engine.dispose()
        _drop_database(server)


def _scope_row() -> dict[str, Any]:
    return {
        "project_key": PROJECT_KEY,
        "registry_revision": REGISTRY_REVISION,
        "resolved_schema": PROJECT_SCHEMA,
        "scope_digest": SCOPE_DIGEST,
        "incarnation": SCOPE_INCARNATION,
        "state": "ACTIVE",
        "updated_by": ACTOR,
        "approval_ref": "approval:c3-project-scope",
    }


def _program_ref_row(c3_fixture: _C3Fixture) -> dict[str, Any]:
    return {
        "program_id": PROGRAM_ID,
        "project_key": PROJECT_KEY,
        "program_digest": c3_fixture.composed_program.program_digest,
        "project_storage_ref": f"project-value:{PROGRAM_ID}",
        "contract_version": c3_fixture.composed_program.contract_version,
    }


def _plan_ref_row(c3_fixture: _C3Fixture) -> dict[str, Any]:
    return {
        "plan_id": c3_fixture.composed_plan.plan_id,
        "project_key": PROJECT_KEY,
        "plan_digest": c3_fixture.composed_plan.plan_digest,
        "program_id": c3_fixture.composed_plan.program_id,
        "program_digest": c3_fixture.composed_plan.program_digest,
        "project_storage_ref": f"project-value:{c3_fixture.composed_plan.plan_id}",
        "compiler_id": c3_fixture.composed_plan.compiler_id,
        "compiler_version": c3_fixture.composed_plan.compiler_version,
        "operation_catalog_id": c3_fixture.catalog.catalog_id,
        "catalog_version": c3_fixture.catalog.catalog_version,
        "catalog_digest": c3_fixture.catalog.catalog_digest,
        "effect_closure_digest": c3_fixture.composed_plan.effect_closure_digest,
        "authority_closure_digest": (c3_fixture.composed_plan.authority_closure_digest),
        "resource_closure_digest": c3_fixture.composed_plan.resource_closure_digest,
    }


def _run_row(c3_fixture: _C3Fixture) -> dict[str, Any]:
    return {
        "run_id": RUN_ID,
        "project_key": PROJECT_KEY,
        "project_registry_revision": REGISTRY_REVISION,
        "project_scope_digest": SCOPE_DIGEST,
        "resolved_schema": PROJECT_SCHEMA,
        "program_id": PROGRAM_ID,
        "program_digest": c3_fixture.composed_program.program_digest,
        "plan_id": c3_fixture.composed_plan.plan_id,
        "plan_digest": c3_fixture.composed_plan.plan_digest,
        "state": "RUNNING",
        "revision": 0,
        "next_event_seq": 1,
        "execution_epoch": 0,
        "incarnation": RUN_INCARNATION,
        "submission_authority_digest": _digest("c3-submission-authority"),
        "qualification_digest": QUALIFICATION_DIGEST,
        "cancellation_requested": False,
    }


def _step_row(c3_fixture: _C3Fixture) -> dict[str, Any]:
    return {
        "project_key": PROJECT_KEY,
        "run_id": RUN_ID,
        "step_id": c3_fixture.step_id,
        "operation_id": c3_fixture.step.operation_id,
        "operation_kind": c3_fixture.contract_ref.kind,
        "operation_version": c3_fixture.contract_ref.contract_version,
        "state": "READY",
        "revision": 0,
        "execution_epoch": 0,
        "input_digest": c3_fixture.assignment.input_closure_digest,
        "effect_class": "PURE_LOCAL_TRAVERSAL",
        "resource_class": "CPU_LIGHT",
        "concurrency_key": "c3:concurrency",
        "capability_id": CAPABILITY_ID,
        "claim_owner": "successor",
        "claim_authority_epoch": CANARY_EPOCH,
        "claim_policy_digest": CLAIM_POLICY_DIGEST,
        "max_attempts": 2,
    }


def _work_item_row(c3_fixture: _C3Fixture) -> dict[str, Any]:
    assignment = c3_fixture.assignment
    return {
        "work_item_id": assignment.work_item_id,
        "project_key": assignment.project_key,
        "run_id": assignment.run_id,
        "step_id": assignment.step_id,
        "assignment_kind": assignment.assignment_kind.value,
        "capability_id": assignment.capability_id,
        "operation_contract_digest": assignment.operation_contract_digest,
        "assignment_digest": assignment.assignment_digest,
        "assignment_binding_json": assignment.model_dump(mode="json"),
        "execution_epoch": assignment.execution_epoch,
        "assignment_incarnation": assignment.incarnation,
        "input_closure_digest": assignment.input_closure_digest,
        "claim_authority_epoch": assignment.claim_authority_epoch,
        "claim_policy_digest": assignment.claim_policy_digest,
        "handler_binding_kind": assignment.handler_binding_kind.value,
        "handler_binding_ref": assignment.handler_binding_ref,
        "handler_binding_digest": assignment.handler_binding_digest,
        "deployment_catalog_digest": assignment.deployment_catalog_digest,
        "runtime_protocol_version": assignment.runtime_protocol_version,
        "interpreter_profile_digest": (
            c3_fixture.successor_binding.interpreter_profile_digest
        ),
        "required_node_profile_selector": NODE_PROFILE_DIGEST,
        "program_digest": assignment.program_digest,
        "plan_digest": assignment.plan_digest,
        "qualification_digest": QUALIFICATION_DIGEST,
        "expected_step_revision": assignment.expected_step_revision,
        "payload_ref": assignment.payload_ref,
        "payload_digest": assignment.payload_digest,
        "authority_digest": _digest("c3-step-authorization"),
        "resource_policy_digest": RESOURCE_POLICY_DIGEST,
        "resource_policy_epoch": assignment.resource_policy_epoch,
        "queue_eligibility_digest": assignment.queue_eligibility_digest,
        "resource_class": "CPU_LIGHT",
        "resource_units": 1,
        "concurrency_key": "c3:concurrency",
        "provider_key": "provider:c3-local-pure-only",
        "recovery_handler_binding_ref": (
            f"handler-binding:sha256:{c3_fixture.recovery_binding.binding_digest}"
        ),
        "recovery_handler_binding_digest": (c3_fixture.recovery_binding.binding_digest),
        "recovery_binding_json": c3_fixture.recovery_binding.model_dump(mode="json"),
        "authoritative_readback_profile_ref": (
            c3_fixture.recovery_binding.authoritative_readback_profile_ref
        ),
        "fairness_key": PROJECT_KEY,
        "state": "READY",
        "declared_priority": 0,
        "enqueued_at": NOW,
        "due_at": NOW,
        "attempt_count": 0,
        "revision": 0,
    }


def _authority_row() -> dict[str, Any]:
    return {
        "project_key": PROJECT_KEY,
        "capability_id": CAPABILITY_ID,
        "mode": CanaryPhase.SHADOW.mode,
        "authority_epoch": 0,
        "successor_claim_enabled": False,
        "legacy_claim_enabled": True,
        "allowlist_digest": ALLOWLIST_DIGEST,
        "config_digest": CONFIG_DIGEST,
        "effective_at": NOW,
        "updated_by": ACTOR,
        "approval_ref": "approval:c3-shadow-baseline",
        "rollback_target_ref": ROLLBACK_TARGET,
        "revision": 0,
    }


def _seed(connection: sa.Connection, c3_fixture: _C3Fixture) -> None:
    connection.execute(
        sa.insert(PUBLIC_TABLES["project_scope_registry"]).values(**_scope_row())
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_program_refs"]).values(
            **_program_ref_row(c3_fixture)
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_plan_refs"]).values(
            **_plan_ref_row(c3_fixture)
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_runs"]).values(**_run_row(c3_fixture))
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_steps"]).values(**_step_row(c3_fixture))
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_work_items"]).values(
            **_work_item_row(c3_fixture)
        )
    )
    DeploymentCatalogRepository(connection).put_exact(
        DeploymentCatalog(
            catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            catalog_version="1.0.0",
            catalog_ref="artifact:c3-canary-deployment",
            node_profile_digest=NODE_PROFILE_DIGEST,
            security_profile_digest=_digest("c3-security"),
            resource_profile_digest=_digest("c3-resource-profile"),
        )
    )
    RuntimeNodeRepository(connection).register(
        node_id=NODE_ID,
        node_profile_digest=NODE_PROFILE_DIGEST,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        runtime_protocol_version="1",
        started_at=NOW - timedelta(minutes=1),
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_resource_policies"]).values(
            resource_policy_id="policy:c3-canary",
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
            grant_id="grant:c3-canary",
            actor_id=ACTOR,
            capability_id=CAPABILITY_ID,
            operation_scope_json=AuthorityOperationScope.from_content(
                operation_kinds=(
                    c3_fixture.contract_ref.kind,
                    c3_fixture.bundle.operation_c3_2.ref.kind,
                ),
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
    approvals = ApprovalRepository(connection, SCOPE)
    approvals.decide(
        ApprovalBinding(
            approval_id=CANARY_APPROVAL_ID,
            actor_id=ACTOR,
            run_id=RUN_ID,
            step_id=c3_fixture.step_id,
            payload_digest=c3_fixture.assignment.payload_digest,
            decision="APPROVED",
            expires_at=NOW + timedelta(days=1),
            authority_digest=c3_fixture.canary_after_digest,
        )
    )
    approvals.decide(
        ApprovalBinding(
            approval_id=ROLLBACK_APPROVAL_ID,
            actor_id=ACTOR,
            run_id=RUN_ID,
            step_id=c3_fixture.step_id,
            payload_digest=c3_fixture.assignment.payload_digest,
            decision="APPROVED",
            expires_at=NOW + timedelta(days=1),
            authority_digest=c3_fixture.rollback_after_digest,
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_capability_authority"]).values(
            **_authority_row()
        )
    )


def _persist_qualification(engine: Engine, c3_fixture: _C3Fixture) -> tuple[Any, Any]:
    with engine.begin() as connection:
        ProgramRepository(
            connection,
            project_tables(sa.MetaData(), PROJECT_SCHEMA),
        ).put_exact(
            SCOPE,
            c3_fixture.composed_program,
            c3_fixture.composed_program.program_digest,
        )
        PlanRepository(
            connection,
            project_tables(sa.MetaData(), PROJECT_SCHEMA),
        ).put_exact(
            SCOPE,
            c3_fixture.composed_plan,
            c3_fixture.composed_plan.plan_digest,
            operation_catalog_id=c3_fixture.catalog.catalog_id,
            catalog_version=c3_fixture.catalog.catalog_version,
            catalog_digest=c3_fixture.catalog.catalog_digest,
        )
        fold_contract = c3_fixture.bundle.operation_c3_2.ref
        context = PostgresAuthorityProvider(connection, SCOPE).current_context(
            ACTOR,
            capability_id=CAPABILITY_ID,
            approval_refs=(CANARY_APPROVAL_ID,),
            canonical_base_revision=0,
            canonical_incarnation=f"canonical:{RUN_ID}:c3:1",
            now=NOW,
        )
        authorization = StepAuthorizationBinding.from_content(
            run_id=RUN_ID,
            step_id=c3_fixture.step_id,
            operation_kind=fold_contract.kind,
            operation_contract_digest=fold_contract.contract_digest,
            capability_id=CAPABILITY_ID,
            claim_owner="successor",
            claim_authority_epoch=CANARY_EPOCH,
            claim_policy_digest=CLAIM_POLICY_DIGEST,
            payload_digest=c3_fixture.assignment.payload_digest,
            actor_id=ACTOR,
            project_key=PROJECT_KEY,
            project_registry_revision=REGISTRY_REVISION,
            project_scope_digest=SCOPE_DIGEST,
            interpreter_binding_digest=(c3_fixture.successor_binding.binding_digest),
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            authority_source_bindings=context.authority_source_bindings,
            grants_digest=context.grants_digest,
            approval_refs=context.approval_refs or (CANARY_APPROVAL_ID,),
            resource_ceiling_digest=context.resource_ceiling_digest,
            resource_policy_epoch=RESOURCE_POLICY_EPOCH,
            queue_eligibility_digest=QUEUE_ELIGIBILITY_DIGEST,
            grant_epoch=context.grant_epoch,
            expires_at=context.expires_at,
            canonical_base_revision=context.canonical_base_revision,
            canonical_incarnation=context.canonical_incarnation,
        )
        qualified = QualifiedPlan.from_content(
            plan_digest=c3_fixture.composed_plan.plan_digest,
            authority_context_digest=context.context_digest,
            step_bindings=(authorization,),
        )
        exact = ExactQualificationBinding.from_content(
            qualification_id="qualification:c3-canary",
            project_key=PROJECT_KEY,
            run_id=RUN_ID,
            plan_id=c3_fixture.composed_plan.plan_id,
            plan_digest=c3_fixture.composed_plan.plan_digest,
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
            .values(
                qualification_digest=qualified.qualification_digest,
                updated_at=NOW,
            )
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
    return context, authorization


class _TestClock:
    def __init__(self) -> None:
        self.current = NOW + timedelta(minutes=2)

    def now(self) -> datetime:
        result = self.current
        self.current += timedelta(seconds=1)
        return result


def _build_node(
    engine: Engine,
    c3_fixture: _C3Fixture,
    *,
    handler: C3CollectComposedRuntimeHandler | None = None,
) -> tuple[RuntimeNode, C3CollectComposedRuntimeHandler]:
    if handler is None:
        handler = C3CollectComposedRuntimeHandler(
            composed_program=c3_fixture.composed_program,
            composed_plan=c3_fixture.composed_plan,
            catalog=c3_fixture.catalog,
            binding=c3_fixture.successor_binding,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            uow_factory=runtime_uow_factory(engine),
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
                {c3_fixture.successor_binding.interpreter_profile_digest}
            ),
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
        clock=_TestClock(),
    )
    return node, handler


def _load_authority(engine: Engine) -> dict[str, Any]:
    with engine.connect() as connection:
        return CapabilityAuthorityRepository(connection, SCOPE).load(CAPABILITY_ID)


def _load_work_item(connection: sa.Connection) -> dict[str, Any]:
    table = PUBLIC_TABLES["runtime_work_items"]
    return dict(
        connection.execute(
            sa.select(table).where(
                table.c.project_key == PROJECT_KEY,
                table.c.work_item_id == WORK_ITEM_ID,
            )
        )
        .mappings()
        .one()
    )


def _execution_context() -> RuntimeExecutionContext:
    return RuntimeExecutionContext(
        node=NodeIdentity(
            node_id=NODE_ID,
            incarnation=NODE_INCARNATION,
            started_at=NOW - timedelta(minutes=1),
        ),
        observed_at=NOW,
    )


def _direct_claim(assignment: Any) -> ClaimBinding:
    return ClaimBinding.bind(
        assignment,
        authorization_digest=assignment.handler_binding.binding_digest,
        lease_token="lease:c3-negative",
        lease_expires_at=NOW + timedelta(minutes=5),
        node_id=NODE_ID,
        node_profile_digest=NODE_PROFILE_DIGEST,
        authority_digest=assignment.handler_binding.binding_digest,
        interpreter_profile_digest=(
            assignment.handler_binding.interpreter_profile_digest
        ),
    )


def _assert_zero_terminal(engine: Engine) -> None:
    with engine.connect() as connection:
        work = _load_work_item(connection)
        events = RuntimeJournalRepository(connection, SCOPE).load_events(RUN_ID)
        attempts = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                    PUBLIC_TABLES["runtime_effect_attempts"].c.project_key
                    == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_effect_attempts"].c.run_id == RUN_ID,
                )
            )
            .mappings()
            .all()
        )
    assert work["state"] == "READY"
    assert work["lease_token"] is None
    assert not attempts
    assert all(event["event_type"] != "RuntimeValueProduced" for event in events)


def _store_mutated_payload(
    engine: Engine,
    *,
    value_ref: Any,
    payloads: tuple[Any, ...],
) -> None:
    exact_bytes = canonical_json([payload.to_plain() for payload in payloads]).encode(
        "utf-8"
    )
    assert sha256_hex(exact_bytes) == value_ref.content_digest
    with engine.begin() as connection:
        ValueRepository(
            connection,
            project_tables(sa.MetaData(), PROJECT_SCHEMA),
        ).put_exact(
            SCOPE.project_scope,
            value_id=value_ref.value_id,
            object_type=value_ref.object_type.type_id,
            codec_id=value_ref.codec_id,
            content=exact_bytes,
            expected_digest=value_ref.content_digest,
            provenance_digest=value_ref.provenance_digest,
            expected_revision=0,
            expected_incarnation=cp.family_payload_incarnation(
                program_id=PROGRAM_ID,
                project_key=PROJECT_KEY,
                value_ref=value_ref,
            ),
            source_ref=value_ref.storage_ref,
            provenance={
                "schema": "mrw.successor.collect.c3.family-payload-provenance.v1",
                "program_id": PROGRAM_ID,
                "project_key": PROJECT_KEY,
                "element_count": len(payloads),
                "content_digest": value_ref.content_digest,
            },
        )


def _tampered_composed_handler(
    engine: Engine,
    c3_fixture: _C3Fixture,
    *,
    mutated_payloads: tuple[Any, ...],
    element_digests_override: tuple[str, ...] | None = None,
    count_override: int | None = None,
) -> tuple[C3CollectComposedRuntimeHandler, Any]:
    mutated_ref = cp.build_family_payload_value_ref(
        mutated_payloads,
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
    )
    mutated_ref = dataclasses.replace(
        mutated_ref,
        value_id=(
            f"{PROGRAM_ID}:payload:family:mutated:{mutated_ref.content_digest[:16]}"
        ),
        storage_ref=(
            f"project-value:{PROGRAM_ID}:payload:family:mutated:"
            f"{mutated_ref.content_digest[:16]}"
        ),
    )
    metadata = dict(c3_fixture.composed_program.metadata)
    metadata.update(
        {
            "payload_value_id": mutated_ref.value_id,
            "payload_storage_ref": mutated_ref.storage_ref,
            "payload_content_digest": mutated_ref.content_digest,
            "payload_provenance_digest": mutated_ref.provenance_digest,
            "payload_object_type": mutated_ref.object_type.type_id,
            "payload_codec_id": mutated_ref.codec_id,
            "payload_byte_size": mutated_ref.byte_size,
            "payload_incarnation": cp.family_payload_incarnation(
                program_id=PROGRAM_ID,
                project_key=PROJECT_KEY,
                value_ref=mutated_ref,
            ),
        }
    )
    if element_digests_override is not None:
        metadata["payload_element_digests"] = tuple(element_digests_override)
    if count_override is not None:
        metadata["payload_element_count"] = count_override
        metadata["element_payload_count"] = count_override
    tampered_program = dataclasses.replace(
        c3_fixture.composed_program,
        metadata=freeze_json_object(metadata),
        program_digest="",
    ).with_digest()
    tampered_plan = _compile_with_registry(
        tampered_program,
        c3_fixture.catalog,
        c3_fixture.registry,
    )
    assignment = c3_fixture.assignment.model_copy(
        update={
            "program_digest": tampered_program.program_digest,
            "plan_digest": tampered_plan.plan_digest,
            "input_refs": (mutated_ref.storage_ref,),
            "payload_ref": mutated_ref.storage_ref,
            "payload_digest": mutated_ref.content_digest,
            "input_closure_digest": sha256_hex(
                canonical_json({"input_refs": (mutated_ref.storage_ref,)}).encode(
                    "utf-8"
                )
            ),
        }
    )
    handler = C3CollectComposedRuntimeHandler(
        composed_program=tampered_program,
        composed_plan=tampered_plan,
        catalog=c3_fixture.catalog,
        binding=c3_fixture.successor_binding,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        uow_factory=runtime_uow_factory(engine),
    )
    _store_mutated_payload(
        engine,
        value_ref=mutated_ref,
        payloads=mutated_payloads,
    )
    return handler, assignment


@pytest.fixture
def canary_database(disposable_database: Engine) -> tuple[Engine, _C3Fixture]:
    c3_fixture = _c3()
    qualified = [f'"public"."{name}"' for name in PUBLIC_TABLES]
    with disposable_database.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE TABLE " + ", ".join(qualified) + " RESTART IDENTITY CASCADE"
            )
        )
        connection.execute(
            sa.text(f'DELETE FROM "{PROJECT_SCHEMA}"."successor_values"')
        )
        _seed(connection, c3_fixture)
    _seed_payload_value(disposable_database, c3_fixture)
    _promote_canary_authority(disposable_database, c3_fixture)
    _persist_qualification(disposable_database, c3_fixture)
    return disposable_database, c3_fixture


def _seed_payload_value(engine: Engine, c3_fixture: _C3Fixture) -> None:
    metadata = dict(c3_fixture.composed_program.metadata)
    exact_bytes = canonical_json(
        [payload.to_plain() for payload in c3_fixture.element_payloads]
    ).encode("utf-8")
    assert sha256_hex(exact_bytes) == metadata["payload_content_digest"]
    with engine.begin() as connection:
        ValueRepository(
            connection,
            project_tables(sa.MetaData(), PROJECT_SCHEMA),
        ).put_exact(
            SCOPE.project_scope,
            value_id=metadata["payload_value_id"],
            object_type=metadata["payload_object_type"],
            codec_id=metadata["payload_codec_id"],
            content=exact_bytes,
            expected_digest=metadata["payload_content_digest"],
            provenance_digest=metadata["payload_provenance_digest"],
            expected_revision=0,
            expected_incarnation=metadata["payload_incarnation"],
            source_ref=metadata["payload_storage_ref"],
            provenance={
                "schema": "mrw.successor.collect.c3.family-payload-provenance.v1",
                "program_id": c3_fixture.composed_program.program_id,
                "project_key": PROJECT_KEY,
                "element_count": len(c3_fixture.element_payloads),
                "content_digest": metadata["payload_content_digest"],
            },
        )


def _promote_canary_authority(engine: Engine, c3_fixture: _C3Fixture) -> None:
    from app.successor_runtime.substrate.postgres.authority import (
        CapabilityAuthority,
    )

    with engine.begin() as connection:
        CapabilityAuthorityRepository(connection, SCOPE).revise(
            CapabilityAuthority(
                capability_id=CAPABILITY_ID,
                mode=CanaryPhase.CANARY.mode,
                authority_epoch=CANARY_EPOCH,
                successor_claim_enabled=True,
                legacy_claim_enabled=False,
                allowlist_digest=ALLOWLIST_DIGEST,
                config_digest=CONFIG_DIGEST,
                effective_at=NOW,
                approval_ref=CANARY_APPROVAL_ID,
                rollback_target_ref=ROLLBACK_TARGET,
            ),
            expected_revision=0,
        )


def test_runtime_node_claims_compiled_traversal_and_commits_ordered_fold(
    canary_database: tuple[Engine, _C3Fixture],
) -> None:
    engine, c3_fixture = canary_database
    node, handler = _build_node(engine, c3_fixture)

    report = node.run_once()
    assert report.claimed == 1
    assert len(report.results) == 1
    result = report.results[0]
    assert result.state.value == "COMMITTED"
    assert result.executed is True
    assert result.committed is True
    assert result.disposition.value == "SUCCEEDED"
    assert handler.provider_calls == 0
    assert handler.executions == 1
    assert handler.composed_program_digest == c3_fixture.composed_program.program_digest
    assert handler.composed_plan_digest == c3_fixture.composed_plan.plan_digest
    assert c3_fixture.composed_plan.output_type.type_id == (
        c3.COLLECT_FOLD_RESULT_TYPE.type_id
    )

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
        step = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_steps"]).where(
                    PUBLIC_TABLES["runtime_steps"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_steps"].c.run_id == RUN_ID,
                    PUBLIC_TABLES["runtime_steps"].c.step_id == c3_fixture.step_id,
                )
            )
            .mappings()
            .one()
        )
        work = _load_work_item(connection)
        reservations = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_resource_reservations"]).where(
                    PUBLIC_TABLES["runtime_resource_reservations"].c.project_key
                    == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_resource_reservations"].c.run_id == RUN_ID,
                )
            )
            .mappings()
            .all()
        )
        events = RuntimeJournalRepository(connection, SCOPE).load_events(RUN_ID)
    assert attempt["attempt_id"] == result.attempt_id
    assert attempt["disposition"] == "SUCCEEDED"
    assert attempt["handler_binding_digest"] == (
        c3_fixture.successor_binding.binding_digest
    )
    assert step["state"] == "SUCCEEDED"
    assert step["output_digest"] == c3_fixture.expected_aggregate_digest
    assert work["state"] == "COMPLETED"
    assert work["lease_token"] is None
    assert work["lease_owner"] is None
    assert all(reservation["state"] == "RELEASED" for reservation in reservations)
    terminal = next(
        event for event in events if event["event_type"] == "RuntimeValueProduced"
    )
    assert terminal["schema_version"] == "mrw.runtime.event.effect_succeeded.v1"
    assert terminal["step_id"] == c3_fixture.step_id
    assert terminal["attempt_id"] == attempt["attempt_id"]


def test_rollback_changes_only_future_owner_and_preserves_terminal_facts(
    canary_database: tuple[Engine, _C3Fixture],
) -> None:
    engine, c3_fixture = canary_database
    node, handler = _build_node(engine, c3_fixture)
    report = node.run_once()
    assert report.claimed == 1
    assert handler.provider_calls == 0

    with engine.connect() as connection:
        before_events = RuntimeJournalRepository(connection, SCOPE).load_events(RUN_ID)
    before_terminal = next(
        event
        for event in before_events
        if event["event_type"] == "RuntimeValueProduced"
    )
    with engine.connect() as connection:
        run_row = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_runs"]).where(
                    PUBLIC_TABLES["runtime_runs"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_runs"].c.run_id == RUN_ID,
                )
            )
            .mappings()
            .one()
        )
        run_revision = int(run_row["revision"])

    with RuntimeUnitOfWork(engine=engine) as uow:
        service = C3CollectRollbackService(uow.connection, SCOPE)
        rollback = service.rollback_future_owner_only(
            transition_id="transition:c3:rollback-legacy",
            capability_id=CAPABILITY_ID,
            run_id=RUN_ID,
            step_id=c3_fixture.step_id,
            work_item_id=WORK_ITEM_ID,
            program_digest=c3_fixture.composed_program.program_digest,
            plan_digest=c3_fixture.composed_plan.plan_digest,
            payload_digest=c3_fixture.assignment.payload_digest,
            payload_ref=c3_fixture.payload_value_ref.storage_ref,
            successor_binding_digest=c3_fixture.successor_binding.binding_digest,
            expected_authority_epoch=CANARY_EPOCH,
            expected_authority_revision=1,
            expected_run_revision=run_revision,
            approval_ref=ROLLBACK_APPROVAL_ID,
            rollback_target_ref=ROLLBACK_TARGET,
            allowlist_digest=ALLOWLIST_DIGEST,
            config_digest=CONFIG_DIGEST,
            before_authority_digest=c3_fixture.canary_after_digest,
            after_authority_digest=c3_fixture.rollback_after_digest,
            effective_at=NOW,
            now=NOW,
        )
        uow.commit()

    assert rollback.authority_epoch == CANARY_EPOCH + 1
    assert rollback.after_authority_digest == c3_fixture.rollback_after_digest
    authority = _load_authority(engine)
    assert authority["mode"] == "off"
    assert authority["successor_claim_enabled"] is False
    assert authority["legacy_claim_enabled"] is True
    assert select_future_owner(authority) == "legacy"

    with engine.connect() as connection:
        after_events = RuntimeJournalRepository(connection, SCOPE).load_events(RUN_ID)
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
        step = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_steps"]).where(
                    PUBLIC_TABLES["runtime_steps"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_steps"].c.run_id == RUN_ID,
                    PUBLIC_TABLES["runtime_steps"].c.step_id == c3_fixture.step_id,
                )
            )
            .mappings()
            .one()
        )
    assert len(after_events) == len(before_events) + 1
    assert after_events[-1]["event_type"] == "CapabilityAuthorityChanged"
    assert (
        after_events[-1]["event_metadata_json"]["after_authority_digest"]
        == c3_fixture.rollback_after_digest
    )
    assert after_events[-1]["event_metadata_json"]["future_owner_ref"] == "legacy"
    after_terminal = next(
        event for event in after_events if event["event_type"] == "RuntimeValueProduced"
    )
    assert after_terminal["attempt_id"] == before_terminal["attempt_id"]
    assert attempt["disposition"] == "SUCCEEDED"
    assert step["output_digest"] == c3_fixture.expected_aggregate_digest


def test_stale_run_revision_rolls_back_rollback_authority_and_event_together(
    canary_database: tuple[Engine, _C3Fixture],
) -> None:
    engine, c3_fixture = canary_database
    with (
        pytest.raises(StaleRevisionError),
        RuntimeUnitOfWork(engine=engine) as uow,
    ):
        C3CollectRollbackService(uow.connection, SCOPE).rollback_future_owner_only(
            transition_id="transition:c3:stale",
            capability_id=CAPABILITY_ID,
            run_id=RUN_ID,
            step_id=c3_fixture.step_id,
            work_item_id=WORK_ITEM_ID,
            program_digest=c3_fixture.composed_program.program_digest,
            plan_digest=c3_fixture.composed_plan.plan_digest,
            payload_digest=c3_fixture.assignment.payload_digest,
            payload_ref=c3_fixture.payload_value_ref.storage_ref,
            successor_binding_digest=c3_fixture.successor_binding.binding_digest,
            expected_authority_epoch=CANARY_EPOCH,
            expected_authority_revision=1,
            expected_run_revision=999,
            approval_ref=ROLLBACK_APPROVAL_ID,
            rollback_target_ref=ROLLBACK_TARGET,
            allowlist_digest=ALLOWLIST_DIGEST,
            config_digest=CONFIG_DIGEST,
            before_authority_digest=c3_fixture.canary_after_digest,
            after_authority_digest=c3_fixture.rollback_after_digest,
            effective_at=NOW,
            now=NOW,
        )

    authority = _load_authority(engine)
    assert authority["mode"] == "canary"
    assert authority["successor_claim_enabled"] is True
    assert int(authority["revision"]) == 1
    with engine.connect() as connection:
        events = RuntimeJournalRepository(connection, SCOPE).load_events(RUN_ID)
    assert all(event["event_type"] != "CapabilityAuthorityChanged" for event in events)


def test_restart_handler_rehydrates_exact_payload_closure(
    canary_database: tuple[Engine, _C3Fixture],
) -> None:
    engine, c3_fixture = canary_database
    node, handler = _build_node(engine, c3_fixture)
    report = node.run_once()
    assert report.claimed == 1
    assert handler.provider_calls == 0

    fresh = C3CollectComposedRuntimeHandler(
        composed_program=c3_fixture.composed_program,
        composed_plan=c3_fixture.composed_plan,
        catalog=c3_fixture.catalog,
        binding=c3_fixture.successor_binding,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        uow_factory=runtime_uow_factory(engine),
    )
    with RuntimeUnitOfWork(engine=engine) as uow:
        payloads, scope = fresh.rehydrate_payload_closure(
            uow.connection,
            c3_fixture.assignment,
        )
    metadata = dict(c3_fixture.composed_program.metadata)
    assert scope.project_scope.resolved_schema == PROJECT_SCHEMA
    assert len(payloads) == metadata["payload_element_count"]
    assert tuple(payload.payload_digest for payload in payloads) == tuple(
        metadata["payload_element_digests"]
    )


def test_mutated_stored_payload_content_fails_before_effect(
    canary_database: tuple[Engine, _C3Fixture],
) -> None:
    engine, c3_fixture = canary_database
    handler = C3CollectComposedRuntimeHandler(
        composed_program=c3_fixture.composed_program,
        composed_plan=c3_fixture.composed_plan,
        catalog=c3_fixture.catalog,
        binding=c3_fixture.successor_binding,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        uow_factory=runtime_uow_factory(engine),
    )
    metadata = dict(c3_fixture.composed_program.metadata)
    with engine.begin() as connection:
        table = project_tables(sa.MetaData(), PROJECT_SCHEMA).successor_values
        connection.execute(
            sa.update(table)
            .where(
                table.c.project_key == PROJECT_KEY,
                table.c.value_id == metadata["payload_value_id"],
            )
            .values(content_bytes=b"tampered-family-payload-bytes")
        )
    assignment = c3_fixture.assignment
    with pytest.raises(DefiniteInterpreterFailure, match="C3_PAYLOAD_STORE_DRIFT"):
        handler.execute(
            assignment,
            _direct_claim(assignment),
            _execution_context(),
        )
    assert handler.provider_calls == 0
    assert handler.executions == 0
    _assert_zero_terminal(engine)


def test_tampered_assignment_ref_or_digest_fails_closed(
    canary_database: tuple[Engine, _C3Fixture],
) -> None:
    engine, c3_fixture = canary_database
    handler = C3CollectComposedRuntimeHandler(
        composed_program=c3_fixture.composed_program,
        composed_plan=c3_fixture.composed_plan,
        catalog=c3_fixture.catalog,
        binding=c3_fixture.successor_binding,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        uow_factory=runtime_uow_factory(engine),
    )
    assignment = c3_fixture.assignment.model_copy(
        update={
            "payload_ref": "project-value:wrong-family-payload",
            "payload_digest": "2" * 64,
        }
    )
    with pytest.raises(
        DefiniteInterpreterFailure, match="EXACT_C3_COMPOSED_BINDING_DRIFT"
    ):
        handler.execute(
            assignment,
            _direct_claim(assignment),
            _execution_context(),
        )
    assert handler.provider_calls == 0
    assert handler.executions == 0
    _assert_zero_terminal(engine)


def test_mutated_payload_count_and_order_fail_closed(
    canary_database: tuple[Engine, _C3Fixture],
) -> None:
    engine, c3_fixture = canary_database
    first, second = c3_fixture.element_payloads
    original_digests = tuple(
        dict(c3_fixture.composed_program.metadata)["payload_element_digests"]
    )

    count_handler, count_assignment = _tampered_composed_handler(
        engine,
        c3_fixture,
        mutated_payloads=(first,),
        element_digests_override=original_digests,
        count_override=2,
    )
    with pytest.raises(DefiniteInterpreterFailure, match="C3_PAYLOAD_COUNT_DRIFT"):
        count_handler.execute(
            count_assignment,
            _direct_claim(count_assignment),
            _execution_context(),
        )
    assert count_handler.provider_calls == 0
    assert count_handler.executions == 0
    _assert_zero_terminal(engine)

    order_handler, order_assignment = _tampered_composed_handler(
        engine,
        c3_fixture,
        mutated_payloads=(second, first),
        element_digests_override=original_digests,
        count_override=2,
    )
    with pytest.raises(
        DefiniteInterpreterFailure, match="C3_PAYLOAD_ORDER_OR_DIGEST_DRIFT"
    ):
        order_handler.execute(
            order_assignment,
            _direct_claim(order_assignment),
            _execution_context(),
        )
    assert order_handler.provider_calls == 0
    assert order_handler.executions == 0
    _assert_zero_terminal(engine)
