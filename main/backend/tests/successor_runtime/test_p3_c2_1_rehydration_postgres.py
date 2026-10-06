"""Real-PostgreSQL store-rehydration tests for the C2.1 successor handler.

The handler under test captures no Program/Plan/payload fixture.  Stores are
seeded with exact bytes; handler A is constructed and discarded; a fresh
handler B/RuntimeNode rehydrates everything from stores and completes the
claimed READY work item.  Negative cases mutate stores before a direct handler
execute and assert fail-closed ``DefiniteInterpreterFailure`` with zero
terminal writes; one claim-time negative proves the full node path writes
nothing before the effect.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from app.successor_runtime.assembly.base import successor_binding
from app.successor_runtime.capabilities import source_resolution as c2_1_cap
from app.successor_runtime.capabilities import (
    source_provider_test_interpreters as c2_3_fixtures,
)
from app.successor_runtime.capabilities.checksum import canonical_json
from app.successor_runtime.capabilities.source_resolution_interpreters import (
    InterpreterSuccess,
    SourceResolutionSuccessorInterpreter,
    authority_requirement_digest,
    successor_interpreter_profile_digest,
)
from app.successor_runtime.capabilities.source_resolution_program import (
    build_source_resolution_program,
    compile_source_resolution_program,
    exact_contract_ref,
    payload_value_ref,
)
from app.successor_runtime.assembly.source_assembly import build_source_assembly
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
from app.successor_runtime.research.codec import sha256_hex
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
    RuntimeJournalRepository,
)
from app.successor_runtime.substrate.postgres.runtime_values import (
    RuntimeValueBinding,
    RuntimeValueRepository,
)
from app.successor_runtime.substrate.postgres.session import (
    compute_scope_digest,
    create_runtime_engine,
)
from app.successor_runtime.substrate.postgres.source_library_c2_1_canary import (
    authority_digest,
)
from app.successor_runtime.substrate.postgres.source_library_c2_1_handler import (
    C2_1_DEPLOYMENT_CATALOG_DRIFT,
    C2_1_PAYLOAD_CODEC_DRIFT,
    C2_1_PAYLOAD_STORE_DRIFT,
    C2_1_PLAN_STORE_DRIFT,
    C2_1_SCOPE_REHYDRATION_DRIFT,
    HISTORICAL_C2_1_FAILURE_CODES,
    SourceLibraryC2_1StoreRehydratedHandler,
    c2_1_expected_payload_value_identity,
)
from app.successor_runtime.substrate.postgres.values import (
    ValueRepository,
    derive_value_write_intent_digest,
)
from app.successor_runtime.substrate.postgres.work_items import ClaimBindingMismatch

pytestmark = pytest.mark.integration

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_PACKET = (
    _REPOSITORY_ROOT / "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/"
    "P2C21CapabilityPacket.v5.json"
)

DATABASE_ENV = "SUCCESSOR_TEST_DATABASE_URL"
PROJECT_KEY = "p3-c2-1-rehydration-postgres"
PROJECT_SCHEMA = "mrw_p3_c2_1_rehydration"
REGISTRY_REVISION = 1
SCOPE_INCARNATION = "c2-1-rehydration-incarnation-1"
SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY,
    PROJECT_SCHEMA,
    REGISTRY_REVISION,
    SCOPE_INCARNATION,
)
ACTOR = "human:c2-1-rehydration-postgres"
RUN_ID = "run:p3-c2-1-rehydration"
RUN_INCARNATION = "run-inc:c2-1-rehydration"
PROGRAM_ID = "program:p3-c2-1-rehydration"
WORK_ITEM_ID = "work:p3-c2-1-rehydration"
CAPABILITY_ID = "source_library.c2_1.v1"
CANARY_APPROVAL_ID = "approval:c2-1-rehydration"
CANARY_EPOCH = 1
ITEM_REVISION = 7
ITEM_INCARNATION = "item-inc:c2-1-rehydration"
NODE_ID = "node:c2-1-rehydration"
NODE_INCARNATION = "node-inc:c2-1-rehydration"
NOW = datetime(2030, 9, 1, 8, 0, tzinfo=UTC)


def _digest(value: str | bytes) -> str:
    encoded = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(encoded).hexdigest()


ALLOWLIST_DIGEST = _digest("c2-1-rehydration-allowlist")
CONFIG_DIGEST = _digest("c2-1-rehydration-config")
DEPLOYMENT_CATALOG_DIGEST = c2_1_cap.deployment_catalog_digest()
CLAIM_POLICY_DIGEST = _digest("c2-1-rehydration-claim-policy")
RESOURCE_POLICY_DIGEST = _digest("c2-1-rehydration-resource-policy")
RESOURCE_POLICY_EPOCH = 1
NODE_PROFILE_DIGEST = _digest("c2-1-rehydration-node-profile")
QUALIFICATION_DIGEST = _digest("c2-1-rehydration-qualification")
QUEUE_ELIGIBILITY = QueueEligibility(
    project_key=PROJECT_KEY,
    capability_id=CAPABILITY_ID,
    resource_class=ResourceClass.CPU_LIGHT,
    units=1,
    policy_epoch=RESOURCE_POLICY_EPOCH,
    policy_digest=RESOURCE_POLICY_DIGEST,
    concurrency_key="c2-1:rehydration",
    provider_key="provider:c2-1-local-pure-only",
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
class _C2Fixture:
    catalog: Any
    contract_ref: Any
    payload: Any
    program: Any
    plan: Any
    step: Any
    step_id: str
    payload_value_ref: Any
    successor_binding: Any
    recovery_binding: Any
    assignment: RuntimeAssignment
    step_authorization: StepAuthorizationBinding
    authority_digest: str
    interpreter: SourceResolutionSuccessorInterpreter
    interpreter_success: type[InterpreterSuccess]


_C2_1: _C2Fixture | None = None


def _c2_1() -> _C2Fixture:
    global _C2_1
    if _C2_1 is not None:
        return _C2_1

    bundle = c2_1_cap.build_source_resolution_bundle()
    catalog = c2_1_cap.build_source_resolution_catalog(bundle)
    registry = c2_1_cap.build_source_resolution_registry(bundle)
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
    item["content_digest"] = c2_1_cap.source_item_definition_content_digest(item)
    payload = c2_1_cap.payload_from_dicts(
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
    program = build_source_resolution_program(
        payload=payload,
        catalog=catalog,
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
    )
    plan = compile_source_resolution_program(
        program,
        catalog,
        operation_contracts=registry,
    )
    effect_steps = tuple(
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT" and step.operation_contract_ref is not None
    )
    assert len(effect_steps) == 1
    step = effect_steps[0]
    value_ref = payload_value_ref(
        payload,
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
    )
    binding = successor_binding(
        operation_contract_digest=contract_ref.contract_digest,
        interpreter_profile_digest=successor_interpreter_profile_digest(),
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=SCOPE_DIGEST,
        authority_requirement_digest=authority_requirement_digest(),
        runtime_protocol_version="1",
    )
    recovery_binding = RecoveryBinding.from_content(
        recovery_handler_id="recovery.c2-1.local-pure",
        recovery_handler_version="1",
        interpreter_profile_digest=binding.interpreter_profile_digest,
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
        step_id=step.step_id,
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
        payload_digest=payload.payload_digest,
        queue_eligibility_digest=QUEUE_ELIGIBILITY_DIGEST,
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        claim_authority_epoch=CANARY_EPOCH,
        claim_policy_digest=CLAIM_POLICY_DIGEST,
        expected_step_revision=0,
        trace_id=f"trace:{RUN_ID}",
    )
    active_authority_digest = authority_digest(
        project_key=PROJECT_KEY,
        capability_id=CAPABILITY_ID,
        mode="canary",
        authority_epoch=CANARY_EPOCH,
        successor_claim_enabled=True,
        legacy_claim_enabled=False,
        allowlist_digest=ALLOWLIST_DIGEST,
        config_digest=CONFIG_DIGEST,
        effective_at=NOW,
        updated_by=ACTOR,
        approval_ref=CANARY_APPROVAL_ID,
        rollback_target_ref="retired:none",
        revision=1,
    )
    step_authorization = StepAuthorizationBinding.from_content(
        run_id=RUN_ID,
        step_id=step.step_id,
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
        interpreter_binding_digest=binding.binding_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        authority_source_bindings=(),
        grants_digest=_digest("c2-1-rehydration-grants"),
        approval_refs=(CANARY_APPROVAL_ID,),
        resource_ceiling_digest=c2_1_cap.resource_ceiling_digest(),
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        queue_eligibility_digest=QUEUE_ELIGIBILITY_DIGEST,
        grant_epoch=1,
        expires_at=NOW + timedelta(days=1),
        canonical_base_revision=0,
        canonical_incarnation=RUN_INCARNATION,
    )
    _C2_1 = _C2Fixture(
        catalog=catalog,
        contract_ref=contract_ref,
        payload=payload,
        program=program,
        plan=plan,
        step=step,
        step_id=step.step_id,
        payload_value_ref=value_ref,
        successor_binding=binding,
        recovery_binding=recovery_binding,
        assignment=assignment,
        step_authorization=step_authorization,
        authority_digest=active_authority_digest,
        interpreter=SourceResolutionSuccessorInterpreter(),
        interpreter_success=InterpreterSuccess,
    )
    return _C2_1


def _scope_row() -> dict[str, Any]:
    return {
        "project_key": PROJECT_KEY,
        "registry_revision": REGISTRY_REVISION,
        "resolved_schema": PROJECT_SCHEMA,
        "scope_digest": SCOPE_DIGEST,
        "incarnation": SCOPE_INCARNATION,
        "state": "ACTIVE",
        "updated_by": ACTOR,
        "approval_ref": "approval:c2-1-rehydration-scope",
    }


def _program_ref_row(c2_1: _C2Fixture) -> dict[str, Any]:
    return {
        "program_id": PROGRAM_ID,
        "project_key": PROJECT_KEY,
        "program_digest": c2_1.program.program_digest,
        "project_storage_ref": f"project-value:{PROGRAM_ID}",
        "contract_version": c2_1.program.contract_version,
    }


def _plan_ref_row(c2_1: _C2Fixture) -> dict[str, Any]:
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


def _run_row(c2_1: _C2Fixture) -> dict[str, Any]:
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
        "submission_authority_digest": _digest("c2-1-rehydration-submission"),
        "qualification_digest": QUALIFICATION_DIGEST,
        "cancellation_requested": False,
    }


def _step_row(c2_1: _C2Fixture) -> dict[str, Any]:
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
        "concurrency_key": "c2-1:rehydration",
        "capability_id": CAPABILITY_ID,
        "claim_owner": "successor",
        "claim_authority_epoch": CANARY_EPOCH,
        "claim_policy_digest": CLAIM_POLICY_DIGEST,
        "max_attempts": 2,
    }


def _work_item_row(c2_1: _C2Fixture) -> dict[str, Any]:
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
        "interpreter_profile_digest": (
            c2_1.successor_binding.interpreter_profile_digest
        ),
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
        "concurrency_key": "c2-1:rehydration",
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


def _authority_row(c2_1: _C2Fixture) -> dict[str, Any]:
    return {
        "project_key": PROJECT_KEY,
        "capability_id": CAPABILITY_ID,
        "mode": "canary",
        "authority_epoch": CANARY_EPOCH,
        "successor_claim_enabled": True,
        "legacy_claim_enabled": False,
        "allowlist_digest": ALLOWLIST_DIGEST,
        "config_digest": CONFIG_DIGEST,
        "effective_at": NOW,
        "updated_by": ACTOR,
        "approval_ref": CANARY_APPROVAL_ID,
        "rollback_target_ref": "retired:none",
        "revision": 1,
    }


def _seed(connection: sa.Connection, c2_1: _C2Fixture) -> None:
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
        sa.insert(PUBLIC_TABLES["runtime_work_items"]).values(
            **_work_item_row(c2_1)
        )
    )
    DeploymentCatalogRepository(connection).put_exact(
        DeploymentCatalog(
            catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            catalog_version="1.0.0",
            catalog_ref="artifact:c2-1-rehydration-deployment",
            node_profile_digest=NODE_PROFILE_DIGEST,
            security_profile_digest=_digest("c2-1-rehydration-security"),
            resource_profile_digest=_digest("c2-1-rehydration-resource-profile"),
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
            resource_policy_id="policy:c2-1-rehydration",
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
            grant_id="grant:c2-1-rehydration",
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
    ApprovalRepository(connection, SCOPE).decide(
        ApprovalBinding(
            approval_id=CANARY_APPROVAL_ID,
            actor_id=ACTOR,
            run_id=RUN_ID,
            step_id=c2_1.step_id,
            payload_digest=c2_1.payload.payload_digest,
            decision="APPROVED",
            expires_at=NOW + timedelta(days=1),
            authority_digest=c2_1.authority_digest,
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_capability_authority"]).values(
            **_authority_row(c2_1)
        )
    )


def _persist_qualification(
    engine: Engine,
    c2_1: _C2Fixture,
) -> tuple[Any, StepAuthorizationBinding, ExactQualificationBinding]:
    with engine.begin() as connection:
        tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)
        ProgramRepository(connection, tables).put_exact(
            SCOPE,
            c2_1.program,
            c2_1.program.program_digest,
        )
        PlanRepository(connection, tables).put_exact(
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
            qualification_id="qualification:c2-1-rehydration",
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


@dataclass(frozen=True, slots=True)
class _Prepared:
    engine: Engine
    c2_1: Any
    authorization: Any


def _make_handler(
    engine: Engine | None,
) -> SourceLibraryC2_1StoreRehydratedHandler:
    uow_factory = (
            runtime_uow_factory(engine)
            if engine is not None
            else lambda: (_ for _ in ()).throw(AssertionError("handler not executed"))
    )
    gateway = c2_3_fixtures.FixtureProviderEffectGateway(
        credentials=c2_3_fixtures.FixtureCredentialResolverPort(),
        effect=c2_3_fixtures.FixtureProviderEffectPort(),
        readback=c2_3_fixtures.FixtureProviderReadbackPort(),
    )
    assembly = build_source_assembly(
        uow_factory=uow_factory,
        project_scope_digest=SCOPE_DIGEST,
        provider_gateway=gateway,
    )
    handlers = tuple(
        handler
        for handler in assembly.handlers
        if isinstance(handler, SourceLibraryC2_1StoreRehydratedHandler)
    )
    assert len(handlers) == 1
    return handlers[0]


def _persist_payload_stores(engine: Engine, c2_1: Any) -> None:
    identity = c2_1_expected_payload_value_identity(c2_1.program)
    ref = c2_1.payload_value_ref
    assert identity.value_id == ref.value_id
    assert identity.storage_ref == ref.storage_ref
    assert identity.content_digest == ref.content_digest
    assert identity.provenance_digest == ref.provenance_digest
    exact_bytes = canonical_json(dataclasses.asdict(c2_1.payload)).encode("utf-8")
    assert hashlib.sha256(exact_bytes).hexdigest() == identity.content_digest
    with engine.begin() as connection:
        tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)
        ValueRepository(connection, tables).put_exact(
            SCOPE,
            value_id=identity.value_id,
            object_type=identity.object_type,
            codec_id=identity.codec_id,
            content=exact_bytes,
            expected_digest=identity.content_digest,
            provenance_digest=identity.provenance_digest,
            expected_revision=0,
            expected_incarnation=identity.incarnation,
            source_ref=identity.storage_ref,
            provenance=dict(identity.provenance),
            write_intent_digest=identity.write_intent_digest,
        )
        RuntimeValueRepository(connection, SCOPE).put_exact(
            RuntimeValueBinding(
                value_id=identity.value_id,
                object_type=identity.object_type,
                codec_id=identity.codec_id,
                content_digest=identity.content_digest,
                byte_size=len(exact_bytes),
                project_value_ref=identity.storage_ref,
                storage_digest=hashlib.sha256(
                    identity.storage_ref.encode()
                ).hexdigest(),
                write_intent_digest=identity.write_intent_digest,
            ),
            state="AVAILABLE",
        )


def _build_node(
    engine: Engine,
    handler: SourceLibraryC2_1StoreRehydratedHandler,
) -> tuple[RuntimeNode, PostgresRuntimeNodeAdapter]:
    c2_1 = _c2_1()
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
    return node, lifecycle


def _direct_claim(assignment: Any, authorization: Any) -> ClaimBinding:
    return ClaimBinding.bind(
        assignment,
        authorization_digest=authorization.binding_digest,
        lease_token="lease:c2-1-store-direct",
        lease_expires_at=NOW + timedelta(minutes=5),
        node_id=NODE_ID,
        node_profile_digest=NODE_PROFILE_DIGEST,
        authority_digest=authorization.binding_digest,
        interpreter_profile_digest=(
            assignment.handler_binding.interpreter_profile_digest
        ),
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


def _execute_direct(
    prepared: _Prepared,
    *,
    handler: SourceLibraryC2_1StoreRehydratedHandler | None = None,
) -> Any:
    if handler is None:
        handler = _make_handler(prepared.engine)
    claim = _direct_claim(prepared.c2_1.assignment, prepared.authorization)
    return handler.execute(
        prepared.c2_1.assignment,
        claim,
        _execution_context(),
    )


def _assert_zero_terminal(engine: Engine) -> None:
    with engine.connect() as connection:
        attempts = (
            connection.execute(sa.select(PUBLIC_TABLES["runtime_effect_attempts"]))
            .mappings()
            .all()
        )
        events = (
            connection.execute(sa.select(PUBLIC_TABLES["runtime_events"]))
            .mappings()
            .all()
        )
        work = _load_work_item(connection)
    assert not attempts
    assert all(event["event_type"] != "RuntimeValueProduced" for event in events)
    assert work["state"] == "READY"
    assert work["lease_token"] is None


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


@pytest.fixture(scope="module")
def live_rehydrated_database() -> Iterator[Engine]:
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
def rehydrated_database(
    live_rehydrated_database: Engine,
) -> _Prepared:
    engine = live_rehydrated_database
    c2_1 = _c2_1()
    qualified = [f'"public"."{name}"' for name in PUBLIC_TABLES]
    with engine.begin() as connection:
        connection.execute(
            sa.text(f'DROP SCHEMA IF EXISTS "{PROJECT_SCHEMA}" CASCADE')
        )
        connection.execute(sa.text(f'CREATE SCHEMA "{PROJECT_SCHEMA}"'))
        project_metadata = sa.MetaData()
        project_tables(project_metadata, PROJECT_SCHEMA)
        project_metadata.create_all(connection, checkfirst=False)
        connection.execute(
            sa.text(
                "TRUNCATE TABLE " + ", ".join(qualified) + " RESTART IDENTITY CASCADE"
            )
        )
        _seed(connection, c2_1)
    _context, authorization, _exact = _persist_qualification(engine, c2_1)
    _persist_payload_stores(engine, c2_1)
    return _Prepared(engine=engine, c2_1=c2_1, authorization=authorization)


def test_frozen_packet_stays_historical_and_current_handler_comes_from_native_assembly() -> None:
    packet = json.loads(_PACKET.read_bytes())
    c2_1 = _c2_1()
    contract = packet["operation_contract"]
    assert contract["owner_capability_id"] == "source_library.c2_1.v1"
    assert (
        contract["payload_codec_id"]
        == c2_1_cap.SOURCE_RESOLUTION_HISTORICAL_PAYLOAD_CODEC_ID
    )
    assert contract["contract_digest"] != c2_1.contract_ref.contract_digest
    assert contract["operation_catalog_digest"] != c2_1.catalog.catalog_digest
    assert contract["deployment_catalog_digest"] != contract["operation_catalog_digest"]
    assert packet["interpreters"]["same_program_digest"] != c2_1.program.program_digest
    assert packet["interpreters"]["same_plan_digest"] != c2_1.plan.plan_digest
    handler = _make_handler(None)
    assert handler.handler_binding_digest == c2_1.successor_binding.binding_digest
    assert handler.operation_contract_digest == c2_1.contract_ref.contract_digest
    assert handler.deployment_catalog_digest == DEPLOYMENT_CATALOG_DIGEST


def test_current_failure_codes_are_business_named_and_history_is_not_rewritten() -> None:
    current = {
        C2_1_DEPLOYMENT_CATALOG_DRIFT,
        C2_1_PAYLOAD_CODEC_DRIFT,
        C2_1_PAYLOAD_STORE_DRIFT,
        C2_1_PLAN_STORE_DRIFT,
        C2_1_SCOPE_REHYDRATION_DRIFT,
    }
    assert all(code.startswith("SOURCE_REQUEST_RESOLUTION_") for code in current)
    assert "C2_1_PAYLOAD_CODEC_DRIFT" in HISTORICAL_C2_1_FAILURE_CODES
    assert current.isdisjoint(HISTORICAL_C2_1_FAILURE_CODES)


def test_fresh_handler_rehydrates_stores_and_completes_exact_terminal(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    authorization = rehydrated_database.authorization

    handler_a = _make_handler(engine)
    node_a, _ = _build_node(engine, handler_a)
    del handler_a, node_a

    handler_b = _make_handler(engine)
    node_b, _lifecycle_b = _build_node(engine, handler_b)
    report = node_b.run_once()
    assert report.claimed == 1
    assert len(report.results) == 1
    result = report.results[0]
    assert result.state.value == "COMMITTED"
    assert result.executed is True
    assert result.committed is True
    assert result.disposition.value == "SUCCEEDED"
    assert handler_b.provider_calls == 0

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
    observation_digest = expected.value.observation_digest

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
        work = _load_work_item(connection)
        authority = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_capability_authority"]).where(
                    PUBLIC_TABLES["runtime_capability_authority"].c.project_key
                    == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_capability_authority"].c.capability_id
                    == CAPABILITY_ID,
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
                    PUBLIC_TABLES["runtime_resource_reservations"].c.run_id
                    == RUN_ID,
                )
            )
            .mappings()
            .all()
        )
        events = RuntimeJournalRepository(
            connection,
            SCOPE,
        ).load_events(RUN_ID)
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
    assert authority["mode"] == "canary"
    assert authority["successor_claim_enabled"] is True
    assert authority["legacy_claim_enabled"] is False
    assert authority["authority_epoch"] == CANARY_EPOCH
    assert all(reservation["state"] == "RELEASED" for reservation in reservations)
    terminal = next(
        event for event in events if event["event_type"] == "RuntimeValueProduced"
    )
    assert terminal["schema_version"] == "mrw.runtime.event.effect_succeeded.v1"
    assert terminal["step_id"] == c2_1.step_id
    assert terminal["attempt_id"] == attempt["attempt_id"]
    assert terminal["authority_digest"] == authorization.binding_digest
    assert terminal["seq"] == events[-1]["seq"]
    event_count = len(events)

    handler_c = _make_handler(engine)
    node_c, _ = _build_node(engine, handler_c)
    second = node_c.run_once()
    assert second.claimed == 0
    assert second.results == ()
    with engine.connect() as connection:
        after = RuntimeJournalRepository(
            connection,
            SCOPE,
        ).load_events(RUN_ID)
        attempts_after = (
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
    assert len(after) == event_count
    assert len(attempts_after) == 1


def test_payload_byte_mutation_fails_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)
    with engine.begin() as connection:
        connection.execute(
            sa.update(tables.successor_values)
            .where(
                tables.successor_values.c.project_key == PROJECT_KEY,
                tables.successor_values.c.value_id == c2_1.payload_value_ref.value_id,
            )
            .values(content_bytes=b'{"tampered": true}')
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PAYLOAD_STORE_DRIFT
    _assert_zero_terminal(engine)


def test_content_digest_drift_fails_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    with engine.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_values"])
            .where(
                PUBLIC_TABLES["runtime_values"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_values"].c.value_id
                == c2_1.payload_value_ref.value_id,
            )
            .values(content_digest="1" * 64)
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PAYLOAD_STORE_DRIFT
    _assert_zero_terminal(engine)


def test_provenance_json_drift_fails_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    identity = c2_1_expected_payload_value_identity(c2_1.program)
    tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)
    tampered = {**dict(identity.provenance), "tampered": True}
    with engine.begin() as connection:
        connection.execute(
            sa.update(tables.successor_values)
            .where(
                tables.successor_values.c.project_key == PROJECT_KEY,
                tables.successor_values.c.value_id == identity.value_id,
            )
            .values(provenance_json=tampered)
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PAYLOAD_STORE_DRIFT
    _assert_zero_terminal(engine)

    consistent = {**tampered, "content_digest": identity.content_digest}
    with engine.begin() as connection:
        connection.execute(
            sa.update(tables.successor_values)
            .where(
                tables.successor_values.c.project_key == PROJECT_KEY,
                tables.successor_values.c.value_id == identity.value_id,
            )
            .values(
                provenance_json=consistent,
                provenance_digest=hashlib.sha256(
                    canonical_json(consistent).encode("utf-8")
                ).hexdigest(),
            )
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PAYLOAD_STORE_DRIFT
    _assert_zero_terminal(engine)


def test_successor_values_incarnation_aba_fails_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    identity = c2_1_expected_payload_value_identity(c2_1.program)
    tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)
    foreign_incarnation = "payload-inc:" + "b" * 64
    foreign_intent = derive_value_write_intent_digest(
        project_key=PROJECT_KEY,
        value_id=identity.value_id,
        object_type=identity.object_type,
        codec_id=identity.codec_id,
        content_digest=identity.content_digest,
        provenance_digest=identity.provenance_digest,
        source_ref=identity.storage_ref,
        expected_revision=0,
        expected_incarnation=foreign_incarnation,
        state="AVAILABLE",
    )
    with engine.begin() as connection:
        connection.execute(
            sa.update(tables.successor_values)
            .where(
                tables.successor_values.c.project_key == PROJECT_KEY,
                tables.successor_values.c.value_id == identity.value_id,
            )
            .values(
                incarnation=foreign_incarnation,
                write_intent_digest=foreign_intent,
            )
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PAYLOAD_STORE_DRIFT
    _assert_zero_terminal(engine)


def test_revision_drift_fails_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    identity = c2_1_expected_payload_value_identity(c2_1.program)
    tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)
    with engine.begin() as connection:
        connection.execute(
            sa.update(tables.successor_values)
            .where(
                tables.successor_values.c.project_key == PROJECT_KEY,
                tables.successor_values.c.value_id == identity.value_id,
            )
            .values(revision=99)
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PAYLOAD_STORE_DRIFT
    _assert_zero_terminal(engine)


def test_write_intent_digest_drift_fails_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    identity = c2_1_expected_payload_value_identity(c2_1.program)
    tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)
    with engine.begin() as connection:
        for table in (
            tables.successor_values,
            PUBLIC_TABLES["runtime_values"],
        ):
            connection.execute(
                sa.update(table)
                .where(
                    table.c.project_key == PROJECT_KEY,
                    table.c.value_id == identity.value_id,
                )
                .values(write_intent_digest="1" * 64)
            )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PAYLOAD_STORE_DRIFT
    _assert_zero_terminal(engine)


def test_program_plan_mismatch_fails_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)
    with engine.begin() as connection:
        connection.execute(
            sa.update(tables.research_execution_plans)
            .where(
                tables.research_execution_plans.c.project_key == PROJECT_KEY,
                tables.research_execution_plans.c.plan_digest == c2_1.plan.plan_digest,
            )
            .values(program_digest="1" * 64)
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PLAN_STORE_DRIFT
    _assert_zero_terminal(engine)


def test_project_scope_aba_fails_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    registry = PUBLIC_TABLES["project_scope_registry"]

    def content(revision: int, suffix: str) -> tuple[str, str]:
        incarnation = f"scope-inc:c2-1-rehydrate-{suffix}"
        return (
            incarnation,
            compute_scope_digest(
                PROJECT_KEY,
                PROJECT_SCHEMA,
                revision,
                incarnation,
            ),
        )

    b_incarnation, b_digest = content(2, "B")
    returned_incarnation, returned_digest = content(1, "A-returned")
    with engine.begin() as connection:
        connection.execute(
            sa.update(registry)
            .where(
                registry.c.project_key == PROJECT_KEY,
                registry.c.registry_revision == 1,
            )
            .values(state="RETIRED")
        )
        connection.execute(
            sa.insert(registry).values(
                project_key=PROJECT_KEY,
                registry_revision=2,
                resolved_schema=PROJECT_SCHEMA,
                scope_digest=b_digest,
                incarnation=b_incarnation,
                state="ACTIVE",
                updated_by=ACTOR,
                approval_ref="approval:c2-1-scope-aba",
            )
        )
        connection.execute(
            sa.delete(registry).where(
                registry.c.project_key == PROJECT_KEY,
                registry.c.registry_revision == 2,
            )
        )
        connection.execute(
            sa.update(registry)
            .where(
                registry.c.project_key == PROJECT_KEY,
                registry.c.registry_revision == 1,
            )
            .values(
                state="ACTIVE",
                incarnation=returned_incarnation,
                scope_digest=returned_digest,
                updated_by=ACTOR,
                approval_ref="approval:c2-1-scope-aba-return",
            )
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_SCOPE_REHYDRATION_DRIFT
    _assert_zero_terminal(engine)


def test_wrong_payload_codec_and_ref_fail_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)

    with engine.begin() as connection:
        for table in (
            tables.successor_values,
            PUBLIC_TABLES["runtime_values"],
        ):
            connection.execute(
                sa.update(table)
                .where(
                    table.c.project_key == PROJECT_KEY,
                    table.c.value_id == c2_1.payload_value_ref.value_id,
                )
                .values(codec_id="mrw.wrong.payload.codec.v1")
            )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PAYLOAD_CODEC_DRIFT
    _assert_zero_terminal(engine)

    with engine.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_values"])
            .where(
                PUBLIC_TABLES["runtime_values"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_values"].c.value_id
                == c2_1.payload_value_ref.value_id,
            )
            .values(project_value_ref="project-value:wrong-ref")
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_PAYLOAD_STORE_DRIFT
    _assert_zero_terminal(engine)


def test_deployment_catalog_drift_fails_closed_with_zero_terminal_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    with engine.begin() as connection:
        connection.execute(
            sa.delete(PUBLIC_TABLES["runtime_nodes"]).where(
                PUBLIC_TABLES["runtime_nodes"].c.node_id == NODE_ID
            )
        )
        connection.execute(
            sa.delete(PUBLIC_TABLES["runtime_deployment_catalogs"]).where(
                PUBLIC_TABLES["runtime_deployment_catalogs"].c.catalog_digest
                == DEPLOYMENT_CATALOG_DIGEST
            )
        )
    with pytest.raises(DefiniteInterpreterFailure) as excinfo:
        _execute_direct(rehydrated_database)
    assert excinfo.value.failure_code == C2_1_DEPLOYMENT_CATALOG_DRIFT
    _assert_zero_terminal(engine)


def test_program_plan_ref_drift_fails_before_claim_with_zero_writes(
    rehydrated_database: _Prepared,
) -> None:
    engine = rehydrated_database.engine
    c2_1 = rehydrated_database.c2_1
    with engine.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_plan_refs"])
            .where(
                PUBLIC_TABLES["runtime_plan_refs"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_plan_refs"].c.plan_digest
                == c2_1.plan.plan_digest,
            )
            .values(program_digest="1" * 64)
        )
    handler = _make_handler(engine)
    node, _ = _build_node(engine, handler)
    with pytest.raises(ClaimBindingMismatch):
        node.run_once()
    _assert_zero_terminal(engine)
