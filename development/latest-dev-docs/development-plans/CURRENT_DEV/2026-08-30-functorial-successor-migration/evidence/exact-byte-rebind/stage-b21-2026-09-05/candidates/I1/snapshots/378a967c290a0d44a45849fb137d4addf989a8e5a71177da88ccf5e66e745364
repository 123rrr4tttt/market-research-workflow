"""Real-PostgreSQL canary + rollback for the P2 C2.1 source-library atom.

The fixture is opt-in and disposable: it skips unless
``SUCCESSOR_TEST_DATABASE_URL`` names a dedicated test/CI PostgreSQL database,
refuses pre-existing successor public tables, creates the frozen public
schema, and drops it again on teardown.  The canary work item is claimed
through the real PostgreSQL work-item claim transaction and consumed by a
``RuntimeNode`` adapter handler that runs the exact successor interpreter.
No provider, network or credential effect is executed.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from app.successor_runtime.capabilities.source_library_c2_1 import (
    deployment_catalog_digest,
)
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
    CapabilityAuthority,
    CapabilityAuthorityRepository,
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
    ExactBindingConflict,
    ExactQualificationBinding,
    RecordNotFound,
    RuntimeJournalRepository,
    StaleRevisionError,
    validate_runtime_assignment_row,
)
from app.successor_runtime.substrate.postgres.session import (
    compute_scope_digest,
    create_runtime_engine,
)
from app.successor_runtime.substrate.postgres.source_library_c2_1_canary import (
    C2_1SuccessorResolutionHandler,
    CanaryPhase,
    SourceLibraryC2_1CanaryService,
    SourceLibraryC2_1CanaryTransitionPacket,
    authority_digest,
    select_future_owner,
)
from app.successor_runtime.substrate.postgres.unit_of_work import RuntimeUnitOfWork

pytestmark = pytest.mark.integration

DATABASE_ENV = "SUCCESSOR_TEST_DATABASE_URL"
PROJECT_KEY = "p2-c2-1-canary-postgres"
PROJECT_SCHEMA = "mrw_p2_c2_1_canary"
REGISTRY_REVISION = 1
SCOPE_INCARNATION = "c2-1-canary-incarnation-1"
SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY,
    PROJECT_SCHEMA,
    REGISTRY_REVISION,
    SCOPE_INCARNATION,
)
ACTOR = "human:c2-1-canary-postgres"
RUN_ID = "run:p2-c2-1-canary"
RUN_INCARNATION = "run-inc:c2-1-canary"
PROGRAM_ID = "program:p2-c2-1-canary"
WORK_ITEM_ID = "work:p2-c2-1-canary"
CAPABILITY_ID = "source_library.c2_1.v1"
ROLLBACK_TARGET = "rollback:legacy:c2-1"
CANARY_APPROVAL_ID = "approval:c2-1-promote-canary"
ROLLBACK_APPROVAL_ID = "approval:c2-1-rollback-legacy"
CANARY_EPOCH = 1
ITEM_REVISION = 7
ITEM_INCARNATION = "item-inc:c2-1-canary"
NODE_ID = "node:c2-1-canary"
NODE_INCARNATION = "node-inc:c2-1-canary"
NOW = datetime(2030, 9, 1, 8, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class _C2_1Fixture:
    bundle: Any
    catalog: Any
    registry: Any
    contract_ref: Any
    payload: Any
    program: Any
    plan: Any
    step: Any
    step_id: str
    payload_value_ref: Any
    successor_binding: Any
    legacy_binding: Any
    recovery_binding: Any
    return_binding: Any
    assignment: Any
    step_authorization: Any
    shadow_before_digest: str
    canary_after_digest: str
    rollback_after_digest: str
    interpreter: Any
    require_exact_resolution_binding: Any
    resolution_binding_mismatch: type[Exception]
    interpreter_failure: type[Any]
    interpreter_success: type[Any]
    resolved_resolution: type[Any]
    require_resource_ceiling: Any
    freeze_json_object: Any


@dataclass(frozen=True, slots=True)
class _CanaryLiveDatabase:
    engine: Engine
    c2_1: _C2_1Fixture


def _digest(value: str | bytes) -> str:
    encoded = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(encoded).hexdigest()


ALLOWLIST_DIGEST = _digest("c2-1-allowlist")
CONFIG_DIGEST = _digest("c2-1-config")
DEPLOYMENT_CATALOG_DIGEST = deployment_catalog_digest()
CLAIM_POLICY_DIGEST = _digest("c2-1-claim-policy")
RESOURCE_POLICY_DIGEST = _digest("c2-1-resource-policy")
QUEUE_ELIGIBILITY = QueueEligibility(
    project_key=PROJECT_KEY,
    capability_id=CAPABILITY_ID,
    resource_class=ResourceClass.CPU_LIGHT,
    units=1,
    policy_epoch=1,
    policy_digest=RESOURCE_POLICY_DIGEST,
    concurrency_key="c2-1:concurrency",
    provider_key="provider:c2-1-local-pure-only",
)
QUEUE_ELIGIBILITY_DIGEST = QUEUE_ELIGIBILITY.eligibility_digest
NODE_PROFILE_DIGEST = _digest("c2-1-node-profile")
QUALIFICATION_DIGEST = _digest("c2-1-qualification")
RESOURCE_POLICY_EPOCH = 1

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

_C2_1: _C2_1Fixture | None = None


def _c2_1() -> _C2_1Fixture:
    global _C2_1
    if _C2_1 is not None:
        return _C2_1

    from app.successor_migration.legacy_source_library import (
        build_legacy_source_library_c2_1_binding,
        build_successor_source_library_c2_1_binding,
    )
    from app.successor_runtime.capabilities.source_library_c2_1 import (
        ResolvedResolution,
        build_source_library_c2_1_bundle,
        build_source_library_c2_1_catalog,
        build_source_library_c2_1_registry,
        payload_from_dicts,
        resource_ceiling_digest,
        source_item_definition_content_digest,
    )
    from app.successor_runtime.capabilities.source_library_c2_1_interpreters import (
        InterpreterFailure,
        InterpreterSuccess,
        ResolutionBindingMismatch,
        SourceLibraryC2_1SuccessorInterpreter,
        require_exact_resolution_binding,
        require_resource_ceiling,
    )
    from app.successor_runtime.capabilities.source_library_c2_1_program import (
        build_source_library_c2_1_program,
        compile_source_library_c2_1_program,
        exact_contract_ref,
        payload_value_ref,
    )
    from app.successor_runtime.language.algebra import freeze_json_object
    from app.successor_runtime.language.object_contracts import OperationContractRef
    from app.successor_runtime.research.codec import sha256_hex

    bundle = build_source_library_c2_1_bundle()
    catalog = build_source_library_c2_1_catalog(bundle)
    registry = build_source_library_c2_1_registry(bundle)
    contract_ref = exact_contract_ref(catalog)
    item = {
        "item_key": "handler.cluster.news",
        "channel_key": "handler.cluster",
        "enabled": True,
        "params": {"keywords": ["robotics"], "limit": 9},
        "extra": {"stable_handler_cluster": True},
        "revision": ITEM_REVISION,
        "incarnation": ITEM_INCARNATION,
    }
    item["content_digest"] = source_item_definition_content_digest(item)
    payload = payload_from_dicts(
        project_key=PROJECT_KEY,
        registry_revision=REGISTRY_REVISION,
        resolved_schema=PROJECT_SCHEMA,
        scope_incarnation=SCOPE_INCARNATION,
        scope_digest=SCOPE_DIGEST,
        channels=(
            {
                "channel_key": "handler.cluster",
                "provider_type": "native",
                "enabled": True,
            },
            {
                "channel_key": "crawler.demo_proj",
                "provider_type": "scrapy",
                "enabled": True,
            },
            {
                "channel_key": "market.default",
                "provider_type": "native",
                "enabled": True,
            },
        ),
        item=item,
        params={"query_terms": ["robotics"]},
    )
    program = build_source_library_c2_1_program(
        payload=payload,
        catalog=catalog,
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = compile_source_library_c2_1_program(
        program,
        catalog,
        operation_contracts=registry,
    )
    effect_steps = tuple(
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    )
    if len(effect_steps) != 1:  # pragma: no cover - fixture guard
        raise RuntimeError("C2.1 plan must compile exactly one EFFECT step")
    step = effect_steps[0]
    step_id = step.step_id
    value_ref = payload_value_ref(
        payload,
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
    )

    successor_binding = build_successor_source_library_c2_1_binding(
        contract_digest=contract_ref.contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        runtime_protocol_version="1",
    )
    legacy_binding = build_legacy_source_library_c2_1_binding(
        contract_digest=contract_ref.contract_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        runtime_protocol_version="1",
    )
    recovery_binding = RecoveryBinding.from_content(
        recovery_handler_id="recovery.c2-1.local-pure",
        recovery_handler_version="1",
        interpreter_profile_digest=successor_binding.interpreter_profile_digest,
        authoritative_readback_profile_ref="readback:c2-1-observation.v1",
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
            kind=contract_ref.kind,
            contract_version=contract_ref.contract_version,
            contract_digest=contract_ref.contract_digest,
        ),
        operation_contract_digest=contract_ref.contract_digest,
        return_contract_binding=return_binding,
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=(
            f"handler-binding:sha256:{successor_binding.binding_digest}"
        ),
        handler_binding_digest=successor_binding.binding_digest,
        handler_binding=successor_binding,
        program_digest=program.program_digest,
        plan_digest=plan.plan_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        execution_epoch=0,
        incarnation=RUN_INCARNATION,
        input_refs=(value_ref.storage_ref,),
        input_closure_digest=sha256_hex([value_ref.storage_ref]),
        payload_ref=value_ref.storage_ref,
        payload_digest=payload.payload_digest,
        queue_eligibility_digest=QUEUE_ELIGIBILITY_DIGEST,
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        claim_authority_epoch=CANARY_EPOCH,
        claim_policy_digest=CLAIM_POLICY_DIGEST,
        expected_step_revision=0,
        trace_id=f"trace:{RUN_ID}",
    )
    step_authorization = StepAuthorizationBinding.from_content(
        run_id=RUN_ID,
        step_id=step_id,
        operation_kind=contract_ref.kind,
        operation_contract_digest=contract_ref.contract_digest,
        capability_id=CAPABILITY_ID,
        claim_owner="successor",
        claim_authority_epoch=CANARY_EPOCH,
        claim_policy_digest=CLAIM_POLICY_DIGEST,
        payload_digest=payload.payload_digest,
        actor_id=ACTOR,
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
        interpreter_binding_digest=successor_binding.binding_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        authority_source_bindings=(),
        grants_digest=_digest("c2-1-grants"),
        approval_refs=(CANARY_APPROVAL_ID,),
        resource_ceiling_digest=resource_ceiling_digest(),
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        queue_eligibility_digest=QUEUE_ELIGIBILITY_DIGEST,
        grant_epoch=1,
        expires_at=NOW + timedelta(days=1),
        canonical_base_revision=0,
        canonical_incarnation=RUN_INCARNATION,
    )
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
        approval_ref="approval:c2-1-shadow-baseline",
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
    _C2_1 = _C2_1Fixture(
        bundle=bundle,
        catalog=catalog,
        registry=registry,
        contract_ref=contract_ref,
        payload=payload,
        program=program,
        plan=plan,
        step=step,
        step_id=step_id,
        payload_value_ref=value_ref,
        successor_binding=successor_binding,
        legacy_binding=legacy_binding,
        recovery_binding=recovery_binding,
        return_binding=return_binding,
        assignment=assignment,
        step_authorization=step_authorization,
        shadow_before_digest=shadow_before_digest,
        canary_after_digest=canary_after_digest,
        rollback_after_digest=rollback_after_digest,
        interpreter=SourceLibraryC2_1SuccessorInterpreter(),
        require_exact_resolution_binding=require_exact_resolution_binding,
        resolution_binding_mismatch=ResolutionBindingMismatch,
        interpreter_failure=InterpreterFailure,
        interpreter_success=InterpreterSuccess,
        resolved_resolution=ResolvedResolution,
        require_resource_ceiling=require_resource_ceiling,
        freeze_json_object=freeze_json_object,
    )
    return _C2_1


def _require_dedicated_database_url() -> str:
    database_url = os.environ.get(DATABASE_ENV)
    if not database_url:
        pytest.skip(f"{DATABASE_ENV} is not set")
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        pytest.fail(f"{DATABASE_ENV} must use a PostgreSQL driver")
    database_name = url.database or ""
    if database_name in {"postgres", "template0", "template1"} or not re.search(
        r"(?:test|testing|ci)", database_name, re.IGNORECASE
    ):
        pytest.fail(
            f"{DATABASE_ENV} must name a dedicated test/CI database; "
            f"refusing database {database_name!r}"
        )
    return database_url


def _scope_row() -> dict[str, Any]:
    return {
        "project_key": PROJECT_KEY,
        "registry_revision": REGISTRY_REVISION,
        "resolved_schema": PROJECT_SCHEMA,
        "scope_digest": SCOPE_DIGEST,
        "incarnation": SCOPE_INCARNATION,
        "state": "ACTIVE",
        "updated_by": ACTOR,
        "approval_ref": "approval:c2-1-project-scope",
    }


def _program_ref_row(c2_1: _C2_1Fixture) -> dict[str, Any]:
    return {
        "program_id": PROGRAM_ID,
        "project_key": PROJECT_KEY,
        "program_digest": c2_1.program.program_digest,
        "project_storage_ref": f"project-value:{PROGRAM_ID}",
        "contract_version": c2_1.program.contract_version,
    }


def _plan_ref_row(c2_1: _C2_1Fixture) -> dict[str, Any]:
    return {
        "plan_id": c2_1.plan.plan_id,
        "project_key": PROJECT_KEY,
        "plan_digest": c2_1.plan.plan_digest,
        "program_id": c2_1.plan.program_id,
        "program_digest": c2_1.plan.program_digest,
        "project_storage_ref": f"project-value:{c2_1.plan.plan_id}",
        "compiler_id": c2_1.plan.compiler_id,
        "compiler_version": c2_1.plan.compiler_version,
        "operation_catalog_id": c2_1.catalog.catalog_id,
        "catalog_version": c2_1.catalog.catalog_version,
        "catalog_digest": c2_1.catalog.catalog_digest,
        "effect_closure_digest": c2_1.plan.effect_closure_digest,
        "authority_closure_digest": c2_1.plan.authority_closure_digest,
        "resource_closure_digest": c2_1.plan.resource_closure_digest,
    }


def _run_row(c2_1: _C2_1Fixture) -> dict[str, Any]:
    return {
        "run_id": RUN_ID,
        "project_key": PROJECT_KEY,
        "project_registry_revision": REGISTRY_REVISION,
        "project_scope_digest": SCOPE_DIGEST,
        "resolved_schema": PROJECT_SCHEMA,
        "program_id": PROGRAM_ID,
        "program_digest": c2_1.program.program_digest,
        "plan_id": c2_1.plan.plan_id,
        "plan_digest": c2_1.plan.plan_digest,
        "state": "RUNNING",
        "revision": 0,
        "next_event_seq": 1,
        "execution_epoch": 0,
        "incarnation": RUN_INCARNATION,
        "submission_authority_digest": _digest("c2-1-submission-authority"),
        "qualification_digest": QUALIFICATION_DIGEST,
        "cancellation_requested": False,
    }


def _step_row(c2_1: _C2_1Fixture) -> dict[str, Any]:
    return {
        "project_key": PROJECT_KEY,
        "run_id": RUN_ID,
        "step_id": c2_1.step_id,
        "operation_id": c2_1.step.operation_id,
        "operation_kind": c2_1.contract_ref.kind,
        "operation_version": c2_1.contract_ref.contract_version,
        "state": "READY",
        "revision": 0,
        "execution_epoch": 0,
        "input_digest": c2_1.assignment.input_closure_digest,
        "effect_class": "PURE_LOCAL_RESOLUTION",
        "resource_class": "CPU_LIGHT",
        "concurrency_key": "c2-1:concurrency",
        "capability_id": CAPABILITY_ID,
        "claim_owner": "successor",
        "claim_authority_epoch": CANARY_EPOCH,
        "claim_policy_digest": CLAIM_POLICY_DIGEST,
        "max_attempts": 2,
    }


def _work_item_row(c2_1: _C2_1Fixture) -> dict[str, Any]:
    assignment = c2_1.assignment
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
        "interpreter_profile_digest": c2_1.successor_binding.interpreter_profile_digest,
        "required_node_profile_selector": NODE_PROFILE_DIGEST,
        "program_digest": assignment.program_digest,
        "plan_digest": assignment.plan_digest,
        "qualification_digest": QUALIFICATION_DIGEST,
        "expected_step_revision": assignment.expected_step_revision,
        "payload_ref": assignment.payload_ref,
        "payload_digest": assignment.payload_digest,
        "authority_digest": c2_1.step_authorization.binding_digest,
        "resource_policy_digest": RESOURCE_POLICY_DIGEST,
        "resource_policy_epoch": assignment.resource_policy_epoch,
        "queue_eligibility_digest": assignment.queue_eligibility_digest,
        "resource_class": "CPU_LIGHT",
        "resource_units": 1,
        "concurrency_key": "c2-1:concurrency",
        "provider_key": "provider:c2-1-local-pure-only",
        "recovery_handler_binding_ref": (
            f"handler-binding:sha256:{c2_1.recovery_binding.binding_digest}"
        ),
        "recovery_handler_binding_digest": c2_1.recovery_binding.binding_digest,
        "recovery_binding_json": c2_1.recovery_binding.model_dump(mode="json"),
        "authoritative_readback_profile_ref": (
            c2_1.recovery_binding.authoritative_readback_profile_ref
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
        "approval_ref": "approval:c2-1-shadow-baseline",
        "rollback_target_ref": ROLLBACK_TARGET,
        "revision": 0,
    }


def _seed(connection: sa.Connection, c2_1: _C2_1Fixture) -> None:
    connection.execute(
        sa.insert(PUBLIC_TABLES["project_scope_registry"]).values(**_scope_row())
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_program_refs"]).values(
            **_program_ref_row(c2_1)
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_plan_refs"]).values(**_plan_ref_row(c2_1))
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_runs"]).values(**_run_row(c2_1))
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_steps"]).values(**_step_row(c2_1))
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_work_items"]).values(**_work_item_row(c2_1))
    )
    DeploymentCatalogRepository(connection).put_exact(
        DeploymentCatalog(
            catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            catalog_version="1.0.0",
            catalog_ref="artifact:c2-1-canary-deployment",
            node_profile_digest=NODE_PROFILE_DIGEST,
            security_profile_digest=_digest("c2-1-security"),
            resource_profile_digest=_digest("c2-1-resource-profile"),
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
            resource_policy_id="policy:c2-1-canary",
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
            grant_id="grant:c2-1-canary",
            actor_id=ACTOR,
            capability_id=CAPABILITY_ID,
            operation_scope_json=AuthorityOperationScope.from_content(
                operation_kinds=(c2_1.contract_ref.kind,),
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
            step_id=c2_1.step_id,
            payload_digest=c2_1.payload.payload_digest,
            decision="APPROVED",
            expires_at=NOW + timedelta(days=1),
            authority_digest=c2_1.canary_after_digest,
        )
    )
    approvals.decide(
        ApprovalBinding(
            approval_id=ROLLBACK_APPROVAL_ID,
            actor_id=ACTOR,
            run_id=RUN_ID,
            step_id=c2_1.step_id,
            payload_digest=c2_1.payload.payload_digest,
            decision="APPROVED",
            expires_at=NOW + timedelta(days=1),
            authority_digest=c2_1.rollback_after_digest,
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_capability_authority"]).values(
            **_authority_row()
        )
    )


@pytest.fixture(scope="module")
def live_canary_database() -> Iterator[Engine]:
    database_url = _require_dedicated_database_url()
    engine = create_runtime_engine(database_url, poolclass=NullPool)
    inspector = sa.inspect(engine)
    existing_public = set(inspector.get_table_names(schema="public")) & set(
        PUBLIC_TABLES
    )
    if existing_public:
        engine.dispose()
        pytest.fail(
            "dedicated database already contains successor public tables; "
            f"refusing overwrite: {sorted(existing_public)}"
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


@pytest.fixture
def canary_database(live_canary_database: Engine) -> _CanaryLiveDatabase:
    c2_1 = _c2_1()
    qualified = [f'"public"."{name}"' for name in PUBLIC_TABLES]
    with live_canary_database.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE TABLE " + ", ".join(qualified) + " RESTART IDENTITY CASCADE"
            )
        )
        _seed(connection, c2_1)
    return _CanaryLiveDatabase(engine=live_canary_database, c2_1=c2_1)


def _persist_qualification(
    engine: Engine,
    c2_1: _C2_1Fixture,
) -> tuple[Any, Any, Any]:
    """Persist the exact C2.1 plan/qualification closure required by claim."""

    with engine.begin() as connection:
        ProgramRepository(
            connection,
            project_tables(sa.MetaData(), PROJECT_SCHEMA),
        ).put_exact(
            SCOPE,
            c2_1.program,
            c2_1.program.program_digest,
        )
        PlanRepository(
            connection,
            project_tables(sa.MetaData(), PROJECT_SCHEMA),
        ).put_exact(
            SCOPE,
            c2_1.plan,
            c2_1.plan.plan_digest,
            operation_catalog_id=c2_1.catalog.catalog_id,
            catalog_version=c2_1.catalog.catalog_version,
            catalog_digest=c2_1.catalog.catalog_digest,
        )
        context = PostgresAuthorityProvider(connection, SCOPE).current_context(
            ACTOR,
            capability_id=CAPABILITY_ID,
            approval_refs=(CANARY_APPROVAL_ID,),
            canonical_base_revision=0,
            canonical_incarnation=f"canonical:{RUN_ID}:c2-1:1",
            now=NOW,
        )
        authorization = StepAuthorizationBinding.from_content(
            run_id=RUN_ID,
            step_id=c2_1.step_id,
            operation_kind=c2_1.contract_ref.kind,
            operation_contract_digest=c2_1.contract_ref.contract_digest,
            capability_id=CAPABILITY_ID,
            claim_owner="successor",
            claim_authority_epoch=CANARY_EPOCH,
            claim_policy_digest=CLAIM_POLICY_DIGEST,
            payload_digest=c2_1.payload.payload_digest,
            actor_id=ACTOR,
            project_key=PROJECT_KEY,
            project_registry_revision=REGISTRY_REVISION,
            project_scope_digest=SCOPE_DIGEST,
            interpreter_binding_digest=c2_1.successor_binding.binding_digest,
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
            plan_digest=c2_1.plan.plan_digest,
            authority_context_digest=context.context_digest,
            step_bindings=(authorization,),
        )
        exact = ExactQualificationBinding.from_content(
            qualification_id="qualification:c2-1-canary",
            project_key=PROJECT_KEY,
            run_id=RUN_ID,
            plan_id=c2_1.plan.plan_id,
            plan_digest=c2_1.plan.plan_digest,
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
    return context, authorization, exact


class _TestClock:
    def __init__(self) -> None:
        self.current = NOW + timedelta(minutes=2)

    def now(self) -> datetime:
        result = self.current
        self.current += timedelta(seconds=1)
        return result


def _build_canary_node(
    engine: Engine,
    c2_1: _C2_1Fixture,
    *,
    handler: C2_1SuccessorResolutionHandler | None = None,
) -> tuple[RuntimeNode, PostgresRuntimeNodeAdapter, C2_1SuccessorResolutionHandler]:
    if handler is None:
        handler = C2_1SuccessorResolutionHandler(
            program=c2_1.program,
            plan=c2_1.plan,
            contract_ref=c2_1.contract_ref,
            payload_ref=c2_1.payload_value_ref,
            payload=c2_1.payload,
            catalog=c2_1.catalog,
            binding=c2_1.successor_binding,
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
                {c2_1.successor_binding.interpreter_profile_digest}
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
    return node, lifecycle, handler


def _canary_packet(c2_1: _C2_1Fixture) -> SourceLibraryC2_1CanaryTransitionPacket:
    return SourceLibraryC2_1CanaryTransitionPacket.from_content(
        transition_id="transition:c2-1:promote-canary",
        capability_id=CAPABILITY_ID,
        run_id=RUN_ID,
        step_id=c2_1.step_id,
        work_item_id=WORK_ITEM_ID,
        program_digest=c2_1.program.program_digest,
        plan_digest=c2_1.plan.plan_digest,
        payload_digest=c2_1.payload.payload_digest,
        payload_ref=c2_1.payload_value_ref.storage_ref,
        successor_binding_digest=c2_1.successor_binding.binding_digest,
        source_phase=CanaryPhase.SHADOW,
        target_phase=CanaryPhase.CANARY,
        expected_authority_epoch=0,
        expected_authority_revision=0,
        expected_run_revision=0,
        approval_ref=CANARY_APPROVAL_ID,
        rollback_target_ref=ROLLBACK_TARGET,
        allowlist_digest=ALLOWLIST_DIGEST,
        config_digest=CONFIG_DIGEST,
        effective_at=NOW,
        before_authority_digest=c2_1.shadow_before_digest,
        after_authority_digest=c2_1.canary_after_digest,
    )


def _rollback_packet(
    c2_1: _C2_1Fixture, *, expected_run_revision: int
) -> SourceLibraryC2_1CanaryTransitionPacket:
    return SourceLibraryC2_1CanaryTransitionPacket.from_content(
        transition_id="transition:c2-1:rollback-legacy",
        capability_id=CAPABILITY_ID,
        run_id=RUN_ID,
        step_id=c2_1.step_id,
        work_item_id=WORK_ITEM_ID,
        program_digest=c2_1.program.program_digest,
        plan_digest=c2_1.plan.plan_digest,
        payload_digest=c2_1.payload.payload_digest,
        payload_ref=c2_1.payload_value_ref.storage_ref,
        successor_binding_digest=c2_1.successor_binding.binding_digest,
        source_phase=CanaryPhase.CANARY,
        target_phase=CanaryPhase.OFF,
        expected_authority_epoch=CANARY_EPOCH,
        expected_authority_revision=1,
        expected_run_revision=expected_run_revision,
        approval_ref=ROLLBACK_APPROVAL_ID,
        rollback_target_ref=ROLLBACK_TARGET,
        allowlist_digest=ALLOWLIST_DIGEST,
        config_digest=CONFIG_DIGEST,
        effective_at=NOW,
        before_authority_digest=c2_1.canary_after_digest,
        after_authority_digest=c2_1.rollback_after_digest,
    )


def _rebuilt(
    packet: SourceLibraryC2_1CanaryTransitionPacket,
    **overrides: object,
) -> SourceLibraryC2_1CanaryTransitionPacket:
    content = dataclasses.asdict(packet)
    content.pop("transition_packet_digest")
    content.update(overrides)
    return SourceLibraryC2_1CanaryTransitionPacket.from_content(**content)


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


def _load_run(engine: Engine) -> dict[str, Any]:
    with engine.connect() as connection:
        return RuntimeJournalRepository(connection, SCOPE).load_run(RUN_ID)


def test_canary_success_rollback_preserves_observation_and_selects_legacy(
    canary_database: _CanaryLiveDatabase,
) -> None:
    engine = canary_database.engine
    c2_1 = canary_database.c2_1
    provider_calls: list[str] = []
    observations: list[str] = []
    downstream_calls: list[str] = []

    with RuntimeUnitOfWork(engine=engine) as uow:
        service = SourceLibraryC2_1CanaryService(uow.connection, SCOPE)
        receipt = service.promote_canary(_canary_packet(c2_1), now=NOW)
        uow.commit()
    assert receipt.event_seq == 1
    assert receipt.run_revision == 1
    assert receipt.authority_epoch == CANARY_EPOCH
    assert receipt.authority_revision == 1
    assert receipt.before_authority_digest == c2_1.shadow_before_digest
    assert receipt.after_authority_digest == c2_1.canary_after_digest

    with RuntimeUnitOfWork(engine=engine) as uow:
        authority = CapabilityAuthorityRepository(uow.connection, SCOPE).load(
            CAPABILITY_ID
        )
        persisted = _load_work_item(uow.connection)
        assignment = validate_runtime_assignment_row(persisted)

    assert authority["mode"] == "canary"
    assert authority["successor_claim_enabled"] is True
    assert authority["legacy_claim_enabled"] is False
    assert int(authority["authority_epoch"]) == CANARY_EPOCH
    assert assignment.assignment_kind is AssignmentKind.INTERPRET
    assert assignment.step_role is CompiledStepRole.EFFECT
    assert assignment.handler_binding == c2_1.successor_binding
    assert assignment.program_digest == c2_1.program.program_digest
    assert assignment.plan_digest == c2_1.plan.plan_digest
    assert assignment.payload_digest == c2_1.payload.payload_digest
    assert assignment.claim_authority_epoch == CANARY_EPOCH
    assert persisted["state"] == "READY"

    _context, authorization, _exact = _persist_qualification(engine, c2_1)

    expected = c2_1.interpreter.interpret(
        program=c2_1.program,
        plan=c2_1.plan,
        contract_ref=c2_1.contract_ref,
        payload_ref=c2_1.payload_value_ref,
        payload=c2_1.payload,
        project_scope=c2_1.payload.project_scope,
        catalog=c2_1.catalog,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=c2_1.successor_binding,
    )
    assert isinstance(expected, c2_1.interpreter_success)
    assert isinstance(expected.value, c2_1.resolved_resolution)
    observation_digest = expected.value.observation_digest
    request = expected.value.request
    assert request.project_scope == c2_1.payload.project_scope
    assert request.item_revision == ITEM_REVISION
    assert request.item_incarnation == ITEM_INCARNATION
    assert request.item_content_digest == c2_1.payload.item.content_digest
    assert request.catalog_digest == c2_1.payload.catalog.digest
    assert c2_1.require_resource_ceiling(c2_1.payload) is None
    assert c2_1.payload.project_scope.resolved_schema == PROJECT_SCHEMA
    assert c2_1.payload.project_scope.scope_digest == SCOPE_DIGEST

    node, _lifecycle, handler = _build_canary_node(engine, c2_1)
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
        step = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_steps"]).where(
                    PUBLIC_TABLES["runtime_steps"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_steps"].c.run_id == RUN_ID,
                    PUBLIC_TABLES["runtime_steps"].c.step_id == c2_1.step_id,
                )
            )
            .mappings()
            .one()
        )
        work = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_work_items"]).where(
                    PUBLIC_TABLES["runtime_work_items"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_work_items"].c.work_item_id == WORK_ITEM_ID,
                )
            )
            .mappings()
            .one()
        )
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
    assert attempt["handler_binding_digest"] == c2_1.successor_binding.binding_digest
    assert (
        attempt["handler_realization_digest"] == c2_1.successor_binding.binding_digest
    )
    assert step["state"] == "SUCCEEDED"
    assert step["output_digest"] == observation_digest
    assert work["state"] == "COMPLETED"
    assert work["lease_token"] is None
    assert work["lease_owner"] is None
    assert all(reservation["state"] == "RELEASED" for reservation in reservations)
    terminal = next(
        event for event in events if event["event_type"] == "RuntimeValueProduced"
    )
    assert terminal["schema_version"] == "mrw.runtime.event.effect_succeeded.v1"
    assert terminal["step_id"] == c2_1.step_id
    assert terminal["attempt_id"] == attempt["attempt_id"]
    assert terminal["authority_digest"] == authorization.binding_digest
    assert events[0]["event_type"] == "CapabilityAuthorityChanged"
    assert (
        events[0]["event_metadata_json"]["before_authority_digest"]
        == c2_1.shadow_before_digest
    )
    assert (
        events[0]["event_metadata_json"]["after_authority_digest"]
        == c2_1.canary_after_digest
    )
    assert (
        events[0]["event_metadata_json"]["payload_digest"]
        == c2_1.payload.payload_digest
    )
    assert (
        events[0]["event_metadata_json"]["program_digest"]
        == c2_1.program.program_digest
    )
    assert events[0]["event_metadata_json"]["plan_digest"] == c2_1.plan.plan_digest
    assert (
        events[0]["event_metadata_json"]["successor_binding_digest"]
        == c2_1.successor_binding.binding_digest
    )

    observations.append(observation_digest)
    downstream_calls.append("successor")
    provider_calls.append("none")
    run_revision = int(_load_run(engine)["revision"])
    event_count = len(events)

    with RuntimeUnitOfWork(engine=engine) as uow:
        service = SourceLibraryC2_1CanaryService(uow.connection, SCOPE)
        rollback = service.rollback_legacy(
            _rollback_packet(c2_1, expected_run_revision=run_revision),
            now=NOW,
        )
        uow.commit()
    assert rollback.authority_epoch == CANARY_EPOCH + 1
    assert rollback.before_authority_digest == c2_1.canary_after_digest
    assert rollback.after_authority_digest == c2_1.rollback_after_digest

    authority = _load_authority(engine)
    assert authority["mode"] == "off"
    assert authority["successor_claim_enabled"] is False
    assert authority["legacy_claim_enabled"] is True
    assert int(authority["authority_epoch"]) == CANARY_EPOCH + 1
    assert select_future_owner(authority) == "legacy"

    with engine.connect() as connection:
        after_events = RuntimeJournalRepository(connection, SCOPE).load_events(RUN_ID)
        attempt_after = (
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
        step_after = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_steps"]).where(
                    PUBLIC_TABLES["runtime_steps"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_steps"].c.run_id == RUN_ID,
                    PUBLIC_TABLES["runtime_steps"].c.step_id == c2_1.step_id,
                )
            )
            .mappings()
            .one()
        )
    assert len(after_events) == event_count + 1
    assert after_events[-1]["event_type"] == "CapabilityAuthorityChanged"
    assert (
        after_events[-1]["event_metadata_json"]["after_authority_digest"]
        == c2_1.rollback_after_digest
    )
    assert attempt_after["disposition"] == "SUCCEEDED"
    assert step_after["output_digest"] == observation_digest

    assert provider_calls == ["none"]
    assert observations == [observation_digest]
    assert downstream_calls == ["successor"]


def test_stale_run_revision_rolls_back_authority_and_event_together(
    canary_database: _CanaryLiveDatabase,
) -> None:
    engine = canary_database.engine
    c2_1 = canary_database.c2_1
    packet = _rebuilt(_canary_packet(c2_1), expected_run_revision=999)
    with (
        pytest.raises(StaleRevisionError),
        RuntimeUnitOfWork(engine=engine) as uow,
    ):
        SourceLibraryC2_1CanaryService(uow.connection, SCOPE).promote_canary(
            packet, now=NOW
        )

    authority = _load_authority(engine)
    assert authority["mode"] == "shadow"
    assert authority["successor_claim_enabled"] is False
    assert authority["legacy_claim_enabled"] is True
    assert int(authority["authority_epoch"]) == 0
    assert int(authority["revision"]) == 0
    run = _load_run(engine)
    assert int(run["revision"]) == 0
    assert int(run["next_event_seq"]) == 1
    with engine.connect() as connection:
        events = RuntimeJournalRepository(connection, SCOPE).load_events(RUN_ID)
    assert events == ()


def test_stale_authority_epoch_and_revision_fail_closed(
    canary_database: _CanaryLiveDatabase,
) -> None:
    engine = canary_database.engine
    c2_1 = canary_database.c2_1
    stale_epoch = _rebuilt(_canary_packet(c2_1), expected_authority_epoch=9)
    with (
        pytest.raises(ExactBindingConflict, match="epoch"),
        RuntimeUnitOfWork(engine=engine) as uow,
    ):
        SourceLibraryC2_1CanaryService(uow.connection, SCOPE).promote_canary(
            stale_epoch, now=NOW
        )

    stale_after = authority_digest(
        project_key=PROJECT_KEY,
        capability_id=CAPABILITY_ID,
        mode=CanaryPhase.CANARY.mode,
        authority_epoch=1,
        successor_claim_enabled=True,
        legacy_claim_enabled=False,
        allowlist_digest=ALLOWLIST_DIGEST,
        config_digest=CONFIG_DIGEST,
        effective_at=NOW,
        updated_by=ACTOR,
        approval_ref=CANARY_APPROVAL_ID,
        rollback_target_ref=ROLLBACK_TARGET,
        revision=1000,
    )
    stale_revision = _rebuilt(
        _canary_packet(c2_1),
        expected_authority_revision=999,
        after_authority_digest=stale_after,
    )
    with (
        pytest.raises(StaleRevisionError, match="revision"),
        RuntimeUnitOfWork(engine=engine) as uow,
    ):
        SourceLibraryC2_1CanaryService(uow.connection, SCOPE).promote_canary(
            stale_revision, now=NOW
        )

    authority = _load_authority(engine)
    assert authority["mode"] == "shadow"
    assert int(authority["revision"]) == 0


def test_approval_payload_and_authority_mismatch_roll_back(
    canary_database: _CanaryLiveDatabase,
) -> None:
    engine = canary_database.engine
    c2_1 = canary_database.c2_1
    with engine.begin() as connection:
        ApprovalRepository(connection, SCOPE).decide(
            ApprovalBinding(
                approval_id="approval:c2-1-wrong-authority",
                actor_id=ACTOR,
                run_id=RUN_ID,
                step_id=c2_1.step_id,
                payload_digest=c2_1.payload.payload_digest,
                decision="APPROVED",
                expires_at=NOW + timedelta(days=1),
                authority_digest="1" * 64,
            )
        )
        ApprovalRepository(connection, SCOPE).decide(
            ApprovalBinding(
                approval_id="approval:c2-1-wrong-payload",
                actor_id=ACTOR,
                run_id=RUN_ID,
                step_id=c2_1.step_id,
                payload_digest="2" * 64,
                decision="APPROVED",
                expires_at=NOW + timedelta(days=1),
                authority_digest=c2_1.canary_after_digest,
            )
        )

    wrong_approval_refs = (
        "approval:c2-1-wrong-authority",
        "approval:c2-1-wrong-payload",
    )
    for approval_ref in wrong_approval_refs:
        wrong_after = authority_digest(
            project_key=PROJECT_KEY,
            capability_id=CAPABILITY_ID,
            mode=CanaryPhase.CANARY.mode,
            authority_epoch=1,
            successor_claim_enabled=True,
            legacy_claim_enabled=False,
            allowlist_digest=ALLOWLIST_DIGEST,
            config_digest=CONFIG_DIGEST,
            effective_at=NOW,
            updated_by=ACTOR,
            approval_ref=approval_ref,
            rollback_target_ref=ROLLBACK_TARGET,
            revision=1,
        )
        packet = _rebuilt(
            _canary_packet(c2_1),
            approval_ref=approval_ref,
            after_authority_digest=wrong_after,
        )
        with (
            pytest.raises(ExactBindingConflict, match="approval"),
            RuntimeUnitOfWork(engine=engine) as uow,
        ):
            SourceLibraryC2_1CanaryService(uow.connection, SCOPE).promote_canary(
                packet, now=NOW
            )

    authority = _load_authority(engine)
    assert authority["mode"] == "shadow"
    assert int(authority["revision"]) == 0
    with engine.connect() as connection:
        events = RuntimeJournalRepository(connection, SCOPE).load_events(RUN_ID)
    assert events == ()


def test_stale_successor_binding_and_mutated_payload_reject(
    canary_database: _CanaryLiveDatabase,
) -> None:
    engine = canary_database.engine
    c2_1 = canary_database.c2_1
    wrong_binding = _rebuilt(
        _canary_packet(c2_1),
        successor_binding_digest=c2_1.legacy_binding.binding_digest,
    )
    with (
        pytest.raises(ExactBindingConflict, match="binding drift"),
        RuntimeUnitOfWork(engine=engine) as uow,
    ):
        SourceLibraryC2_1CanaryService(uow.connection, SCOPE).promote_canary(
            wrong_binding, now=NOW
        )

    authority = _load_authority(engine)
    assert authority["mode"] == "shadow"
    assert int(authority["revision"]) == 0

    mutated = replace(
        c2_1.payload,
        params=c2_1.freeze_json_object({"query_terms": ["tampered"]}),
        payload_digest="",
    )
    with pytest.raises(
        c2_1.resolution_binding_mismatch, match="payload ref content digest"
    ):
        c2_1.require_exact_resolution_binding(
            program=c2_1.program,
            plan=c2_1.plan,
            contract_ref=c2_1.contract_ref,
            payload_ref=c2_1.payload_value_ref,
            payload=mutated,
            project_scope=c2_1.payload.project_scope,
            catalog=c2_1.catalog,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            binding=c2_1.successor_binding,
        )
    failure = c2_1.interpreter.interpret(
        program=c2_1.program,
        plan=c2_1.plan,
        contract_ref=c2_1.contract_ref,
        payload_ref=c2_1.payload_value_ref,
        payload=mutated,
        project_scope=c2_1.payload.project_scope,
        catalog=c2_1.catalog,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        binding=c2_1.successor_binding,
    )
    assert isinstance(failure, c2_1.interpreter_failure)
    assert failure.code == "ASSIGNMENT_BINDING_MISMATCH"


def test_double_claim_authority_is_impossible(
    canary_database: _CanaryLiveDatabase,
) -> None:
    engine = canary_database.engine
    with pytest.raises(ValueError, match="both"):
        CapabilityAuthority(
            capability_id=CAPABILITY_ID,
            mode="canary",
            authority_epoch=1,
            successor_claim_enabled=True,
            legacy_claim_enabled=True,
            allowlist_digest=ALLOWLIST_DIGEST,
            config_digest=CONFIG_DIGEST,
            effective_at=NOW,
            approval_ref=CANARY_APPROVAL_ID,
            rollback_target_ref=ROLLBACK_TARGET,
        )

    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_capability_authority"]).values(
                project_key="double-claim-project",
                capability_id="double-claim-cap",
                mode="canary",
                authority_epoch=1,
                successor_claim_enabled=True,
                legacy_claim_enabled=True,
                allowlist_digest=ALLOWLIST_DIGEST,
                config_digest=CONFIG_DIGEST,
                effective_at=NOW,
                updated_by=ACTOR,
                approval_ref="approval:double-claim",
                rollback_target_ref=ROLLBACK_TARGET,
            )
        )

    with pytest.raises(ExactBindingConflict, match="cannot enable"):
        select_future_owner(
            {"successor_claim_enabled": True, "legacy_claim_enabled": True}
        )

    assert CanaryPhase.CANARY.successor_claim_enabled is True
    assert CanaryPhase.CANARY.legacy_claim_enabled is False


def test_missing_rollback_target_rejected() -> None:
    c2_1 = _c2_1()
    with pytest.raises(ValueError, match="rollback_target_ref"):
        _rebuilt(_canary_packet(c2_1), rollback_target_ref="")


def test_wrong_project_scope_rejected(
    canary_database: _CanaryLiveDatabase,
) -> None:
    engine = canary_database.engine
    c2_1 = canary_database.c2_1
    other_scope = RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key="other-project",
            resolved_schema="mrw_other_project",
            project_registry_revision=1,
            incarnation="other-incarnation-1",
            scope_digest=_digest("other-scope"),
        ),
        actor_id=ACTOR,
    )
    with pytest.raises(RecordNotFound), RuntimeUnitOfWork(engine=engine) as uow:
        SourceLibraryC2_1CanaryService(uow.connection, other_scope).promote_canary(
            _canary_packet(c2_1), now=NOW
        )


def test_after_authority_digest_requires_exact_epoch_increment(
    canary_database: _CanaryLiveDatabase,
) -> None:
    engine = canary_database.engine
    c2_1 = canary_database.c2_1
    non_increment_after = authority_digest(
        project_key=PROJECT_KEY,
        capability_id=CAPABILITY_ID,
        mode=CanaryPhase.CANARY.mode,
        authority_epoch=0,
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
    packet = _rebuilt(
        _canary_packet(c2_1),
        after_authority_digest=non_increment_after,
    )
    with (
        pytest.raises(ExactBindingConflict, match="after authority digest mismatch"),
        RuntimeUnitOfWork(engine=engine) as uow,
    ):
        SourceLibraryC2_1CanaryService(uow.connection, SCOPE).promote_canary(
            packet, now=NOW
        )
    authority = _load_authority(engine)
    assert authority["mode"] == "shadow"
    assert int(authority["revision"]) == 0


def test_expired_approval_rejected(
    canary_database: _CanaryLiveDatabase,
) -> None:
    engine = canary_database.engine
    c2_1 = canary_database.c2_1
    with engine.begin() as connection:
        ApprovalRepository(connection, SCOPE).decide(
            ApprovalBinding(
                approval_id="approval:c2-1-expired",
                actor_id=ACTOR,
                run_id=RUN_ID,
                step_id=c2_1.step_id,
                payload_digest=c2_1.payload.payload_digest,
                decision="APPROVED",
                expires_at=NOW - timedelta(days=1),
                authority_digest=c2_1.canary_after_digest,
            )
        )
    expired_after = authority_digest(
        project_key=PROJECT_KEY,
        capability_id=CAPABILITY_ID,
        mode=CanaryPhase.CANARY.mode,
        authority_epoch=1,
        successor_claim_enabled=True,
        legacy_claim_enabled=False,
        allowlist_digest=ALLOWLIST_DIGEST,
        config_digest=CONFIG_DIGEST,
        effective_at=NOW,
        updated_by=ACTOR,
        approval_ref="approval:c2-1-expired",
        rollback_target_ref=ROLLBACK_TARGET,
        revision=1,
    )
    packet = _rebuilt(
        _canary_packet(c2_1),
        approval_ref="approval:c2-1-expired",
        after_authority_digest=expired_after,
    )
    with (
        pytest.raises(ExactBindingConflict, match="approval"),
        RuntimeUnitOfWork(engine=engine) as uow,
    ):
        SourceLibraryC2_1CanaryService(uow.connection, SCOPE).promote_canary(
            packet, now=NOW
        )
    assert _load_authority(engine)["mode"] == "shadow"
    with engine.connect() as connection:
        events = RuntimeJournalRepository(connection, SCOPE).load_events(RUN_ID)
    assert events == ()


def test_work_item_stale_claim_epoch_rejected(
    canary_database: _CanaryLiveDatabase,
) -> None:
    engine = canary_database.engine
    c2_1 = canary_database.c2_1
    table = PUBLIC_TABLES["runtime_work_items"]
    stale_assignment = c2_1.assignment.model_copy(update={"claim_authority_epoch": 9})
    with engine.begin() as connection:
        connection.execute(
            sa.update(table)
            .where(
                table.c.project_key == PROJECT_KEY,
                table.c.work_item_id == WORK_ITEM_ID,
            )
            .values(
                claim_authority_epoch=9,
                assignment_binding_json=stale_assignment.model_dump(mode="json"),
                assignment_digest=stale_assignment.assignment_digest,
                updated_at=NOW,
            )
        )
    with (
        pytest.raises(ExactBindingConflict, match="work binding drift"),
        RuntimeUnitOfWork(engine=engine) as uow,
    ):
        SourceLibraryC2_1CanaryService(uow.connection, SCOPE).promote_canary(
            _canary_packet(c2_1), now=NOW
        )
    assert _load_authority(engine)["mode"] == "shadow"


def test_second_canary_claim_impossible(
    canary_database: _CanaryLiveDatabase,
) -> None:
    engine = canary_database.engine
    c2_1 = canary_database.c2_1
    with RuntimeUnitOfWork(engine=engine) as uow:
        SourceLibraryC2_1CanaryService(uow.connection, SCOPE).promote_canary(
            _canary_packet(c2_1), now=NOW
        )
        uow.commit()
    with (
        pytest.raises(ExactBindingConflict, match="source authority phase mismatch"),
        RuntimeUnitOfWork(engine=engine) as uow,
    ):
        SourceLibraryC2_1CanaryService(uow.connection, SCOPE).promote_canary(
            _canary_packet(c2_1), now=NOW
        )
    authority = _load_authority(engine)
    assert authority["mode"] == "canary"
    assert int(authority["revision"]) == 1
    with engine.connect() as connection:
        events = RuntimeJournalRepository(connection, SCOPE).load_events(RUN_ID)
    assert len(events) == 1


def test_mutated_item_identity_rejects() -> None:
    c2_1 = _c2_1()
    original_item = c2_1.payload.item
    mutated = replace(
        c2_1.payload,
        item=replace(
            original_item,
            item_key="mutated.item",
            content_digest="",
        ),
        payload_digest="",
    )
    with pytest.raises(
        c2_1.resolution_binding_mismatch, match="payload ref content digest"
    ):
        c2_1.require_exact_resolution_binding(
            program=c2_1.program,
            plan=c2_1.plan,
            contract_ref=c2_1.contract_ref,
            payload_ref=c2_1.payload_value_ref,
            payload=mutated,
            project_scope=c2_1.payload.project_scope,
            catalog=c2_1.catalog,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            binding=c2_1.successor_binding,
        )


def test_deployment_catalog_swap_rejects() -> None:
    c2_1 = _c2_1()
    assert DEPLOYMENT_CATALOG_DIGEST != c2_1.catalog.catalog_digest
    with pytest.raises(
        c2_1.resolution_binding_mismatch,
        match="deployment catalog",
    ):
        c2_1.require_exact_resolution_binding(
            program=c2_1.program,
            plan=c2_1.plan,
            contract_ref=c2_1.contract_ref,
            payload_ref=c2_1.payload_value_ref,
            payload=c2_1.payload,
            project_scope=c2_1.payload.project_scope,
            catalog=c2_1.catalog,
            deployment_catalog_digest=c2_1.catalog.catalog_digest,
            binding=c2_1.successor_binding,
        )
    failure = c2_1.interpreter.interpret(
        program=c2_1.program,
        plan=c2_1.plan,
        contract_ref=c2_1.contract_ref,
        payload_ref=c2_1.payload_value_ref,
        payload=c2_1.payload,
        project_scope=c2_1.payload.project_scope,
        catalog=c2_1.catalog,
        deployment_catalog_digest=c2_1.catalog.catalog_digest,
        binding=c2_1.successor_binding,
    )
    assert isinstance(failure, c2_1.interpreter_failure)
    assert failure.code == "ASSIGNMENT_BINDING_MISMATCH"


def test_real_claim_stale_authority_epoch_rejects(
    canary_database: _CanaryLiveDatabase,
) -> None:
    engine = canary_database.engine
    c2_1 = canary_database.c2_1
    with RuntimeUnitOfWork(engine=engine) as uow:
        SourceLibraryC2_1CanaryService(uow.connection, SCOPE).promote_canary(
            _canary_packet(c2_1), now=NOW
        )
        uow.commit()
    _persist_qualification(engine, c2_1)
    with engine.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_capability_authority"])
            .where(
                PUBLIC_TABLES["runtime_capability_authority"].c.project_key
                == PROJECT_KEY,
                PUBLIC_TABLES["runtime_capability_authority"].c.capability_id
                == CAPABILITY_ID,
            )
            .values(authority_epoch=99, updated_at=NOW)
        )
    node, _lifecycle, _handler = _build_canary_node(engine, c2_1)
    with pytest.raises(ExactBindingConflict, match="stale"):
        node.run_once()
    with engine.connect() as connection:
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
        work = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_work_items"]).where(
                    PUBLIC_TABLES["runtime_work_items"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_work_items"].c.work_item_id == WORK_ITEM_ID,
                )
            )
            .mappings()
            .one()
        )
    assert len(attempts) == 0
    assert work["state"] == "READY"


def test_real_claim_double_claim_authority_rejects(
    canary_database: _CanaryLiveDatabase,
) -> None:
    engine = canary_database.engine
    c2_1 = canary_database.c2_1
    with RuntimeUnitOfWork(engine=engine) as uow:
        SourceLibraryC2_1CanaryService(uow.connection, SCOPE).promote_canary(
            _canary_packet(c2_1), now=NOW
        )
        uow.commit()
    _persist_qualification(engine, c2_1)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_capability_authority"])
            .where(
                PUBLIC_TABLES["runtime_capability_authority"].c.project_key
                == PROJECT_KEY,
                PUBLIC_TABLES["runtime_capability_authority"].c.capability_id
                == CAPABILITY_ID,
            )
            .values(
                successor_claim_enabled=True,
                legacy_claim_enabled=True,
                updated_at=NOW,
            )
        )
    with engine.connect() as connection:
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
    assert len(attempts) == 0
