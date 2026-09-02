"""Opt-in PostgreSQL integration coverage for the P0-B durable substrate.

The tests are deliberately inert unless ``SUCCESSOR_TEST_DATABASE_URL`` is
set.  The URL must name a dedicated test/CI database, and setup refuses to
overwrite any pre-existing successor public tables or the project schema used
by this module.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from app.successor_runtime.language.algebra import (
    AlgebraRef,
    OperationSpec,
    ValueRef,
    build_catalog_snapshot,
    freeze_json_object,
)
from app.successor_runtime.language.catalog import OperationContractRegistry
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.language.object_contracts import (
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    OperationContractRef,
    ReturnContract,
    make_operation_contract,
)
from app.successor_runtime.language.program import (
    ProgramSpec,
    atom_node,
    then_node,
)
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.research.object_types import INQUIRY_TYPE
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    CompilerBinding,
    HandlerBindingKind,
    InterpreterBinding,
    RecoveryBinding,
    ReturnContractBinding,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.ports import (
    ControlPlaneScope,
    ProjectScopeRef,
    RuntimeScope,
)
from app.successor_runtime.runtime.qualification import (
    AuthorityContext,
    QualifiedPlan,
    StepAuthorizationBinding,
)
from app.successor_runtime.runtime.recovery import (
    NonStartProof,
    authorize_successor_attempt,
)
from app.successor_runtime.runtime.resources import (
    FairClaimCandidate,
    FairSharePolicy,
    QueueEligibility,
    ResourceClass,
    select_fair_claims,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_METADATA,
    PUBLIC_TABLES,
    ProjectTables,
    project_tables,
)
from app.successor_runtime.substrate.postgres.owner_bindings import (
    OwnerBindingRecord,
    OwnerBindingRepository,
)
from app.successor_runtime.substrate.postgres.plans import PlanRepository
from app.successor_runtime.substrate.postgres.programs import ProgramRepository
from app.successor_runtime.substrate.postgres.research_ledger import (
    ResearchLedgerRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    ExactQualificationBinding,
    PublicPayloadViolation,
    RuntimeJournalRepository,
    StaleRevisionError,
)
from app.successor_runtime.substrate.postgres.session import (
    compute_scope_digest,
    create_runtime_engine,
)
from app.successor_runtime.substrate.postgres.unit_of_work import (
    RuntimeUnitOfWork,
)
from app.successor_runtime.substrate.postgres.work_items import (
    ClaimBindingMismatch,
    ClaimConflict,
    NodeClaimContext,
    WorkItemClaimRepository,
)

pytestmark = pytest.mark.integration

DATABASE_ENV = "SUCCESSOR_TEST_DATABASE_URL"
PROJECT_KEY = "p0b-postgres-integration"
PROJECT_SCHEMA = "mrw_p0b_postgres_integration"
SECONDARY_PROJECT_KEY = "p0b-postgres-integration-b"
SECONDARY_PROJECT_SCHEMA = "mrw_p0b_postgres_integration_b"
REGISTRY_REVISION = 1
SCOPE_INCARNATION = "scope-inc-1"


def _digest(value: str | bytes) -> str:
    encoded = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(encoded).hexdigest()


SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY,
    PROJECT_SCHEMA,
    REGISTRY_REVISION,
    SCOPE_INCARNATION,
)


def _program_value(label: str) -> ValueRef:
    return ValueRef(
        value_id=label,
        project_key=PROJECT_KEY,
        object_type=INQUIRY_TYPE,
        codec_id=INQUIRY_TYPE.codec_id,
        content_digest=_digest(f"{label}:content"),
        storage_kind="project_value_ref",
        store_id="successor-values",
        store_version="1",
        storage_ref=f"value:{label}",
        byte_size=1,
        provenance_digest=_digest(f"{label}:provenance"),
    )


RETURN_CONTRACT = ReturnContract(
    success_modes=("SUCCEEDED",),
    failure_modes=("FAILED",),
    admission_required=False,
    wait_modes=("WAIT",),
    cancel_modes=("CANCELED",),
)
OPERATION_CONTRACTS = tuple(
    make_operation_contract(
        kind=f"test.effect.{ordinal}.v1",
        contract_version="1.0.0",
        input_type=INQUIRY_TYPE,
        output_type=INQUIRY_TYPE,
        return_contract_ref=RUNTIME_VALUE_RETURN_CONTRACT_REF,
        semantic_profile_ref="semantic:integration:v1",
        effect_profile_ref="effect:integration:v1",
        resource_profile_ref="resource:integration:v1",
        failure_profile_ref="failure:integration:v1",
        authority_profile_ref="authority:integration:v1",
        interpreter_compatibility_ref="interpreter:integration:v1",
        observation_profile_ref="observation:integration:v1",
        allowed_override_schema_ref="overrides:integration:v1",
        owner_capability_id="capability-1",
    )
    for ordinal in ("one", "two")
)
OPERATION_CATALOG = build_catalog_snapshot(
    "operation-catalog:integration",
    "1",
    OPERATION_CONTRACTS,
)
OPERATION_REGISTRY = OperationContractRegistry(
    OPERATION_CATALOG,
    OPERATION_CONTRACTS,
)
PROGRAM_ATOMS = tuple(
    atom_node(
        OperationSpec(
            operation_id=f"operation-{ordinal}",
            contract_ref=contract.ref,
            input_refs=(_program_value(f"operation-{ordinal}:input"),),
            payload_ref=_program_value(f"operation-{ordinal}:payload"),
            allowed_overrides=freeze_json_object({}),
        ),
        INQUIRY_TYPE,
        INQUIRY_TYPE,
        RETURN_CONTRACT,
    )
    for ordinal, contract in zip(("one", "two"), OPERATION_CONTRACTS)
)
EXACT_PROGRAM = ProgramSpec(
    program_id="program-1",
    contract_version="1.0.0",
    project_key=PROJECT_KEY,
    project_registry_revision=REGISTRY_REVISION,
    project_scope_digest=SCOPE_DIGEST,
    semantic_identity="ordered-two-effect-inquiry",
    input_type=INQUIRY_TYPE,
    output_type=INQUIRY_TYPE,
    root=then_node(PROGRAM_ATOMS[0], PROGRAM_ATOMS[1]),
    algebra_refs=(AlgebraRef("integration-effects", "1"),),
    transform_refs=(),
    observation_profile="structural",
    metadata=freeze_json_object({}),
    program_digest="",
).with_digest()
PROGRAM_DIGEST = EXACT_PROGRAM.program_digest
EXACT_PLAN = compile_program(
    EXACT_PROGRAM,
    OPERATION_CATALOG,
    operation_contracts=OPERATION_REGISTRY,
)
PLAN_DIGEST = EXACT_PLAN.plan_digest
PLAN_EFFECT_STEPS = tuple(
    step for step in EXACT_PLAN.ordered_steps if step.step_kind == "EFFECT"
)
if len(PLAN_EFFECT_STEPS) != 2:  # pragma: no cover - import-time fixture guard
    raise RuntimeError("integration fixture must compile exactly two EFFECT steps")
STEP_ONE_ID, STEP_TWO_ID = (step.step_id for step in PLAN_EFFECT_STEPS)
PLAN_STEP_BY_ID = {step.step_id: step for step in PLAN_EFFECT_STEPS}
CATALOG_DIGEST = _digest("deployment-catalog")
NODE_PROFILE_DIGEST = _digest("node-profile")
AUTHORITY_DIGEST = _digest("authority-snapshot")
CLAIM_POLICY_DIGEST = _digest("claim-policy")
RESOURCE_POLICY_DIGEST = _digest("resource-policy")
INTERPRETER_PROFILE_DIGEST = _digest("interpreter-profile")
PROVIDER_KEY = "provider:integration"
COMPILER_BINDING = CompilerBinding.from_content(
    compiler_id=EXACT_PLAN.compiler_id,
    compiler_version=EXACT_PLAN.compiler_version,
    compiler_digest=_digest("compiler"),
    operation_catalog_digest=OPERATION_CATALOG.catalog_digest,
    domain_contract_snapshot_digest=_digest("domain-contract-snapshot"),
)
RECOVERY_BINDING = RecoveryBinding.from_content(
    recovery_handler_id="recovery-handler:integration",
    recovery_handler_version="1",
    interpreter_profile_digest=INTERPRETER_PROFILE_DIGEST,
    authoritative_readback_profile_ref="readback:integration:v1",
)
RECOVERY_HANDLER_DIGEST = RECOVERY_BINDING.binding_digest
RETURN_BINDING = ReturnContractBinding.from_contract(
    RUNTIME_VALUE_RETURN_CONTRACT_REF,
    RETURN_CONTRACT,
)


def _interpreter_binding(step_id: str) -> InterpreterBinding:
    step = PLAN_STEP_BY_ID[step_id]
    if step.operation_contract_ref is None:
        raise ValueError(f"compiled effect step has no operation contract: {step_id}")
    return InterpreterBinding.from_content(
        operation_contract_digest=step.operation_contract_ref.contract_digest,
        interpreter_profile_digest=INTERPRETER_PROFILE_DIGEST,
        deployment_catalog_digest=CATALOG_DIGEST,
        runtime_protocol_version="1",
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=1,
        authority_requirement_digest=_digest("authority-requirement"),
    )


@dataclass(frozen=True)
class LiveDatabase:
    engine: Engine
    project_metadata: sa.MetaData
    project_tables: ProjectTables
    project_scope: ProjectScopeRef
    runtime_scope: RuntimeScope


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
def live_database() -> LiveDatabase:
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
    conflicting_schemas = {
        PROJECT_SCHEMA,
        SECONDARY_PROJECT_SCHEMA,
    } & set(inspector.get_schema_names())
    if conflicting_schemas:
        engine.dispose()
        pytest.fail(
            "dedicated database already contains integration schemas "
            f"{sorted(conflicting_schemas)!r}; "
            "refusing overwrite"
        )

    project_metadata = sa.MetaData()
    bound_project_tables = project_tables(project_metadata, PROJECT_SCHEMA)
    try:
        with engine.begin() as connection:
            connection.execute(sa.text(f'CREATE SCHEMA "{PROJECT_SCHEMA}"'))
            connection.execute(sa.text(f'CREATE SCHEMA "{SECONDARY_PROJECT_SCHEMA}"'))
            PUBLIC_METADATA.create_all(connection, checkfirst=False)
            project_metadata.create_all(connection, checkfirst=False)
        project_scope = ProjectScopeRef(
            project_key=PROJECT_KEY,
            resolved_schema=PROJECT_SCHEMA,
            project_registry_revision=REGISTRY_REVISION,
            incarnation=SCOPE_INCARNATION,
            scope_digest=SCOPE_DIGEST,
        )
        yield LiveDatabase(
            engine=engine,
            project_metadata=project_metadata,
            project_tables=bound_project_tables,
            project_scope=project_scope,
            runtime_scope=RuntimeScope(
                project_scope=project_scope,
                actor_id="p0b-postgres-integration",
            ),
        )
    finally:
        with engine.begin() as connection:
            PUBLIC_METADATA.drop_all(connection, checkfirst=True)
            project_metadata.drop_all(connection, checkfirst=True)
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{PROJECT_SCHEMA}"'))
            connection.execute(
                sa.text(f'DROP SCHEMA IF EXISTS "{SECONDARY_PROJECT_SCHEMA}"')
            )
        engine.dispose()


@pytest.fixture(autouse=True)
def empty_successor_tables(live_database: LiveDatabase) -> None:
    project_names = tuple(live_database.project_tables.as_dict())
    public_names = tuple(PUBLIC_TABLES)
    qualified = [f'"public"."{name}"' for name in public_names]
    qualified.extend(f'"{PROJECT_SCHEMA}"."{name}"' for name in project_names)
    with live_database.engine.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE TABLE " + ", ".join(qualified) + " RESTART IDENTITY CASCADE"
            )
        )


def _seed_run(connection: sa.Connection, *, run_id: str = "run-1") -> None:
    connection.execute(
        sa.insert(PUBLIC_TABLES["project_scope_registry"]).values(
            project_key=PROJECT_KEY,
            registry_revision=REGISTRY_REVISION,
            resolved_schema=PROJECT_SCHEMA,
            scope_digest=SCOPE_DIGEST,
            incarnation=SCOPE_INCARNATION,
            state="ACTIVE",
            updated_by="integration-test",
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_program_refs"]).values(
            program_id="program-1",
            project_key=PROJECT_KEY,
            program_digest=PROGRAM_DIGEST,
            project_storage_ref=f"{PROJECT_SCHEMA}:program-1",
            contract_version="1.0.0",
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_runs"]).values(
            run_id=run_id,
            project_key=PROJECT_KEY,
            project_registry_revision=REGISTRY_REVISION,
            project_scope_digest=SCOPE_DIGEST,
            resolved_schema=PROJECT_SCHEMA,
            program_id="program-1",
            program_digest=PROGRAM_DIGEST,
            state="SUBMITTED",
            revision=0,
            next_event_seq=1,
            execution_epoch=0,
            incarnation="run-inc-1",
            submission_authority_digest=AUTHORITY_DIGEST,
        )
    )


def _seed_secondary_run(connection: sa.Connection) -> tuple[str, str, str]:
    incarnation = "scope-inc-b-1"
    scope_digest = compute_scope_digest(
        SECONDARY_PROJECT_KEY,
        SECONDARY_PROJECT_SCHEMA,
        REGISTRY_REVISION,
        incarnation,
    )
    program_digest = _digest("program-b")
    connection.execute(
        sa.insert(PUBLIC_TABLES["project_scope_registry"]).values(
            project_key=SECONDARY_PROJECT_KEY,
            registry_revision=REGISTRY_REVISION,
            resolved_schema=SECONDARY_PROJECT_SCHEMA,
            scope_digest=scope_digest,
            incarnation=incarnation,
            state="ACTIVE",
            updated_by="integration-test",
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_program_refs"]).values(
            program_id="program-b",
            project_key=SECONDARY_PROJECT_KEY,
            program_digest=program_digest,
            project_storage_ref=f"{SECONDARY_PROJECT_SCHEMA}:program-b",
            contract_version="1.0.0",
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_runs"]).values(
            run_id="run-b",
            project_key=SECONDARY_PROJECT_KEY,
            project_registry_revision=REGISTRY_REVISION,
            project_scope_digest=scope_digest,
            resolved_schema=SECONDARY_PROJECT_SCHEMA,
            program_id="program-b",
            program_digest=program_digest,
            state="SUBMITTED",
            revision=0,
            next_event_seq=1,
            execution_epoch=0,
            incarnation="run-inc-b-1",
            submission_authority_digest=AUTHORITY_DIGEST,
        )
    )
    return "run-b", program_digest, scope_digest


def _promote_run_ready(
    connection: sa.Connection,
    live_database: LiveDatabase,
    qualification: ExactQualificationBinding,
    *,
    run_id: str = "run-1",
    include_qualification: bool = True,
) -> None:
    ProgramRepository(connection, live_database.project_tables).put_exact(
        live_database.runtime_scope,
        EXACT_PROGRAM,
        EXACT_PROGRAM.program_digest,
    )
    plans = PlanRepository(connection, live_database.project_tables)
    plans.put_exact(
        live_database.runtime_scope,
        EXACT_PLAN,
        EXACT_PLAN.plan_digest,
        operation_catalog_id=OPERATION_CATALOG.catalog_id,
        catalog_version=OPERATION_CATALOG.catalog_version,
        catalog_digest=OPERATION_CATALOG.catalog_digest,
    )
    assert plans.get(live_database.runtime_scope, EXACT_PLAN.plan_digest) == EXACT_PLAN
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_plan_refs"]).values(
            plan_id=EXACT_PLAN.plan_id,
            project_key=PROJECT_KEY,
            plan_digest=EXACT_PLAN.plan_digest,
            program_id=EXACT_PLAN.program_id,
            program_digest=EXACT_PLAN.program_digest,
            project_storage_ref=f"{PROJECT_SCHEMA}:plan-1",
            compiler_id=EXACT_PLAN.compiler_id,
            compiler_version=EXACT_PLAN.compiler_version,
            operation_catalog_id=OPERATION_CATALOG.catalog_id,
            catalog_version=OPERATION_CATALOG.catalog_version,
            catalog_digest=OPERATION_CATALOG.catalog_digest,
            effect_closure_digest=EXACT_PLAN.effect_closure_digest,
            authority_closure_digest=EXACT_PLAN.authority_closure_digest,
            resource_closure_digest=EXACT_PLAN.resource_closure_digest,
        )
    )
    if include_qualification:
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_qualifications"]).values(
                qualification_id=qualification.qualification_id,
                project_key=qualification.project_key,
                run_id=qualification.run_id,
                plan_id=qualification.plan_id,
                plan_digest=qualification.plan_digest,
                authority_context_digest=qualification.authority_context_digest,
                decision=qualification.decision,
                qualification_digest=(
                    qualification.qualified_plan.qualification_digest
                ),
                qualification_binding_digest=(
                    qualification.qualification_binding_digest
                ),
                qualified_plan_json=qualification.qualified_plan.model_dump(
                    mode="json"
                ),
                qualification_binding_json=qualification.model_dump(mode="json"),
                queue_eligibility_digest=None,
                resource_policy_epoch=None,
                approval_ref=None,
            )
        )
    connection.execute(
        sa.update(PUBLIC_TABLES["runtime_runs"])
        .where(PUBLIC_TABLES["runtime_runs"].c.run_id == run_id)
        .values(
            plan_id=EXACT_PLAN.plan_id,
            plan_digest=EXACT_PLAN.plan_digest,
            state="READY",
            qualification_digest=(qualification.qualified_plan.qualification_digest),
        )
    )


def _event(event_type: str, *, payload_ref: str | None = None) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "schema_version": "mrw.runtime.event.integration.v1",
        "event_metadata_json": {"reason_code": "P0B_POSTGRES_INTEGRATION"},
        "payload_ref": payload_ref,
        "payload_digest": None if payload_ref is None else _digest(payload_ref),
        "authority_digest": AUTHORITY_DIGEST,
    }


def _authority_context(now: datetime) -> AuthorityContext:
    return AuthorityContext.from_content(
        actor_id="integration-test",
        project_key=PROJECT_KEY,
        resolved_schema=PROJECT_SCHEMA,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
        authority_source_bindings=(),
        grants_digest=_digest("grants"),
        grant_epoch=1,
        expires_at=now + timedelta(days=1),
        operation_scope_digest=_digest("operation-scope"),
        resource_ceiling_digest=_digest("resource-ceiling"),
        canonical_base_revision=0,
        canonical_incarnation="run-inc-1",
        approval_refs=(),
    )


def _qualification(
    now: datetime,
    step_bindings: tuple[StepAuthorizationBinding, ...],
    *,
    decision: str = "QUALIFIED",
    qualification_id: str = "qualification-1",
) -> ExactQualificationBinding:
    context = _authority_context(now)
    qualified_plan = QualifiedPlan.from_content(
        plan_digest=EXACT_PLAN.plan_digest,
        authority_context_digest=context.context_digest,
        step_bindings=step_bindings,
        awaiting_approval_steps=(),
        denied_steps=(),
    )
    return ExactQualificationBinding.from_content(
        qualification_id=qualification_id,
        project_key=PROJECT_KEY,
        run_id="run-1",
        plan_id=EXACT_PLAN.plan_id,
        plan_digest=EXACT_PLAN.plan_digest,
        authority_context=context,
        authority_context_digest=context.context_digest,
        qualified_plan=qualified_plan,
        decision=decision,
    )


def _authorization(
    now: datetime,
    *,
    step_id: str,
    payload_digest: str,
    eligibility: QueueEligibility,
    contract_step_id: str | None = None,
    operation_kind: str | None = None,
    operation_contract_digest: str | None = None,
) -> StepAuthorizationBinding:
    compiled_step = PLAN_STEP_BY_ID[contract_step_id or step_id]
    contract_ref = compiled_step.operation_contract_ref
    if contract_ref is None:
        raise ValueError(f"compiled effect step lacks operation ref: {step_id}")
    interpreter = _interpreter_binding(contract_step_id or step_id)
    return StepAuthorizationBinding.from_content(
        run_id="run-1",
        step_id=step_id,
        operation_kind=operation_kind or contract_ref.kind,
        operation_contract_digest=(
            operation_contract_digest or contract_ref.contract_digest
        ),
        capability_id=eligibility.capability_id,
        claim_owner="successor",
        claim_authority_epoch=1,
        claim_policy_digest=CLAIM_POLICY_DIGEST,
        payload_digest=payload_digest,
        actor_id="integration-test",
        project_key=PROJECT_KEY,
        project_registry_revision=REGISTRY_REVISION,
        project_scope_digest=SCOPE_DIGEST,
        interpreter_binding_digest=interpreter.binding_digest,
        deployment_catalog_digest=CATALOG_DIGEST,
        authority_source_bindings=(),
        grants_digest=_digest("grants"),
        approval_refs=(),
        resource_ceiling_digest=_digest("resource-ceiling"),
        resource_policy_epoch=eligibility.policy_epoch,
        queue_eligibility_digest=eligibility.eligibility_digest,
        grant_epoch=1,
        expires_at=now + timedelta(days=1),
        canonical_base_revision=0,
        canonical_incarnation="run-inc-1",
    )


def _authorization_row(
    authorization_id: str,
    binding: StepAuthorizationBinding,
) -> dict[str, Any]:
    return {
        "authorization_id": authorization_id,
        "project_key": binding.project_key,
        "run_id": binding.run_id,
        "step_id": binding.step_id,
        "operation_kind": binding.operation_kind,
        "operation_contract_digest": binding.operation_contract_digest,
        "capability_id": binding.capability_id,
        "claim_owner": binding.claim_owner,
        "claim_authority_epoch": binding.claim_authority_epoch,
        "claim_policy_digest": binding.claim_policy_digest,
        "payload_digest": binding.payload_digest,
        "actor_id": binding.actor_id,
        "project_registry_revision": binding.project_registry_revision,
        "project_scope_digest": binding.project_scope_digest,
        "grant_epoch": binding.grant_epoch,
        "expires_at": binding.expires_at,
        "approval_ref": None,
        "authorization_digest": binding.binding_digest,
        "interpreter_binding_digest": binding.interpreter_binding_digest,
        "deployment_catalog_digest": binding.deployment_catalog_digest,
        "authority_source_bindings_json": [
            item.model_dump(mode="json") for item in binding.authority_source_bindings
        ],
        "grants_digest": binding.grants_digest,
        "approval_refs_json": list(binding.approval_refs),
        "resource_ceiling_digest": binding.resource_ceiling_digest,
        "resource_policy_epoch": binding.resource_policy_epoch,
        "queue_eligibility_digest": binding.queue_eligibility_digest,
        "canonical_base_revision": binding.canonical_base_revision,
        "canonical_incarnation": binding.canonical_incarnation,
        "authorization_binding_json": binding.model_dump(mode="json"),
    }


def _seed_single_effect(
    connection: sa.Connection,
    live_database: LiveDatabase,
    *,
    now: datetime,
    include_qualification: bool = True,
    qualification_decision: str = "QUALIFIED",
    qualified_step_bindings: tuple[StepAuthorizationBinding, ...] | None = None,
    authorization_eligibility: QueueEligibility | None = None,
) -> tuple[QueueEligibility, StepAuthorizationBinding, ExactQualificationBinding]:
    assignment_eligibility = QueueEligibility(
        project_key=PROJECT_KEY,
        capability_id="capability-1",
        resource_class=ResourceClass.CPU_LIGHT,
        units=1,
        policy_epoch=1,
        policy_digest=RESOURCE_POLICY_DIGEST,
        concurrency_key="key:single-effect",
        provider_key=PROVIDER_KEY,
    )
    authorization_eligibility = authorization_eligibility or assignment_eligibility
    step_id = STEP_ONE_ID
    compiled_step = PLAN_STEP_BY_ID[step_id]
    contract_ref = compiled_step.operation_contract_ref
    assert contract_ref is not None
    input_digest = _digest(f"input:{step_id}")
    current_authorization = _authorization(
        now,
        step_id=step_id,
        payload_digest=input_digest,
        eligibility=authorization_eligibility,
    )
    second_authorization = _authorization(
        now,
        step_id=STEP_TWO_ID,
        payload_digest=_digest(f"input:{STEP_TWO_ID}"),
        eligibility=assignment_eligibility,
    )
    qualification = _qualification(
        now,
        qualified_step_bindings or (current_authorization, second_authorization),
        decision=qualification_decision,
    )
    _seed_claim_control(connection, now=now)
    _promote_run_ready(
        connection,
        live_database,
        qualification,
        include_qualification=include_qualification,
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_resource_policies"]).values(
            resource_policy_id="policy-single",
            project_key=PROJECT_KEY,
            capability_id="capability-1",
            resource_class="CPU_LIGHT",
            concurrency_limit=1,
            max_project_active=1,
            max_capability_active=1,
            max_resource_active=1,
            units_ceiling=1,
            provider_limit=1,
            policy_epoch=1,
            policy_digest=RESOURCE_POLICY_DIGEST,
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_steps"]).values(
            project_key=PROJECT_KEY,
            run_id="run-1",
            step_id=step_id,
            operation_id=compiled_step.operation_id,
            operation_kind=contract_ref.kind,
            operation_version=contract_ref.contract_version,
            state="READY",
            execution_epoch=0,
            input_digest=input_digest,
            effect_class="LOCAL_TEST_ONLY",
            resource_class="CPU_LIGHT",
            concurrency_key=assignment_eligibility.concurrency_key,
            capability_id="capability-1",
            claim_owner="successor",
            claim_authority_epoch=1,
            claim_policy_digest=CLAIM_POLICY_DIGEST,
            max_attempts=2,
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_step_authorizations"]).values(
            **_authorization_row("authorization-1", current_authorization)
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_work_items"]).values(
            **_work_item(
                "effect-work-1",
                now=now,
                assignment_kind="INTERPRET",
                step_id=step_id,
                authority_digest=current_authorization.binding_digest,
                qualification_digest=(
                    qualification.qualified_plan.qualification_digest
                ),
                eligibility=assignment_eligibility,
            )
        )
    )
    return assignment_eligibility, current_authorization, qualification


def _work_item(
    work_item_id: str,
    *,
    now: datetime,
    assignment_kind: str = "COMPILE",
    step_id: str | None = None,
    capability_id: str = "capability-1",
    project_key: str = PROJECT_KEY,
    run_id: str = "run-1",
    program_digest: str = PROGRAM_DIGEST,
    fairness_key: str | None = None,
    assignment_incarnation: str = "run-inc-1",
    authority_digest: str = AUTHORITY_DIGEST,
    qualification_digest: str | None = None,
    eligibility: QueueEligibility | None = None,
) -> dict[str, Any]:
    kind = AssignmentKind(assignment_kind)
    if kind is AssignmentKind.COMPILE:
        handler = COMPILER_BINDING
        assignment = RuntimeAssignment(
            runtime_protocol_version="1",
            work_item_id=work_item_id,
            assignment_kind=kind,
            project_key=project_key,
            run_id=run_id,
            capability_id=capability_id,
            handler_binding_kind=HandlerBindingKind.COMPILER,
            handler_binding_ref=(f"handler-binding:sha256:{handler.binding_digest}"),
            handler_binding_digest=handler.binding_digest,
            handler_binding=handler,
            program_digest=program_digest,
            deployment_catalog_digest=CATALOG_DIGEST,
            execution_epoch=0,
            incarnation=assignment_incarnation,
            queue_eligibility_digest=_digest(f"non-effect-eligibility:{work_item_id}"),
            resource_policy_epoch=0,
            claim_authority_epoch=1,
            claim_policy_digest=CLAIM_POLICY_DIGEST,
            trace_id=f"trace:{work_item_id}",
        )
    elif kind is AssignmentKind.INTERPRET:
        if step_id is None or qualification_digest is None:
            raise ValueError("INTERPRET fixture requires step and qualification")
        compiled_step = PLAN_STEP_BY_ID[step_id]
        contract_ref = compiled_step.operation_contract_ref
        if contract_ref is None:
            raise ValueError(f"compiled effect step lacks operation ref: {step_id}")
        eligibility = eligibility or QueueEligibility(
            project_key=project_key,
            capability_id=capability_id,
            resource_class=ResourceClass.CPU_LIGHT,
            units=1,
            policy_epoch=1,
            policy_digest=RESOURCE_POLICY_DIGEST,
            concurrency_key="key:shared-effect-capacity",
            provider_key=PROVIDER_KEY,
        )
        handler = _interpreter_binding(step_id)
        assignment = RuntimeAssignment(
            runtime_protocol_version="1",
            work_item_id=work_item_id,
            assignment_kind=kind,
            project_key=project_key,
            run_id=run_id,
            step_id=step_id,
            step_role=CompiledStepRole.EFFECT,
            capability_id=capability_id,
            operation_contract_ref=OperationContractRef(
                kind=contract_ref.kind,
                contract_version=contract_ref.contract_version,
                contract_digest=contract_ref.contract_digest,
            ),
            operation_contract_digest=contract_ref.contract_digest,
            return_contract_binding=RETURN_BINDING,
            handler_binding_kind=HandlerBindingKind.INTERPRETER,
            handler_binding_ref=(f"handler-binding:sha256:{handler.binding_digest}"),
            handler_binding_digest=handler.binding_digest,
            handler_binding=handler,
            program_digest=program_digest,
            plan_digest=PLAN_DIGEST,
            deployment_catalog_digest=CATALOG_DIGEST,
            execution_epoch=0,
            incarnation=assignment_incarnation,
            input_refs=(f"value:{step_id}",),
            input_closure_digest=_digest(f"input:{step_id}"),
            queue_eligibility_digest=eligibility.eligibility_digest,
            resource_policy_epoch=eligibility.policy_epoch,
            claim_authority_epoch=1,
            claim_policy_digest=CLAIM_POLICY_DIGEST,
            expected_step_revision=0,
            trace_id=f"trace:{work_item_id}",
        )
    else:
        raise ValueError(f"unsupported integration assignment kind: {kind}")
    values: dict[str, Any] = {
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
        "required_node_profile_selector": NODE_PROFILE_DIGEST,
        "program_digest": assignment.program_digest,
        "plan_digest": assignment.plan_digest,
        "qualification_digest": qualification_digest,
        "expected_step_revision": assignment.expected_step_revision,
        "payload_ref": assignment.payload_ref,
        "payload_digest": assignment.payload_digest,
        "authority_digest": authority_digest,
        "resource_policy_digest": RESOURCE_POLICY_DIGEST,
        "resource_policy_epoch": assignment.resource_policy_epoch,
        "queue_eligibility_digest": assignment.queue_eligibility_digest,
        "deadline_at": assignment.deadline_at,
        "fairness_key": fairness_key or project_key,
        "state": "READY",
        "declared_priority": 0,
        "enqueued_at": now,
        "due_at": now,
        "attempt_count": 0,
        "revision": 0,
    }
    if kind is AssignmentKind.INTERPRET:
        assert eligibility is not None
        values.update(
            interpreter_profile_digest=INTERPRETER_PROFILE_DIGEST,
            resource_class=eligibility.resource_class.value,
            resource_units=eligibility.units,
            concurrency_key=eligibility.concurrency_key,
            provider_key=eligibility.provider_key,
            recovery_handler_binding_ref=(
                f"handler-binding:sha256:{RECOVERY_BINDING.binding_digest}"
            ),
            recovery_handler_binding_digest=RECOVERY_HANDLER_DIGEST,
            recovery_binding_json=RECOVERY_BINDING.model_dump(mode="json"),
            authoritative_readback_profile_ref=(
                RECOVERY_BINDING.authoritative_readback_profile_ref
            ),
            delivery_intent_ref="delivery-intent:internal-test-only",
        )
    return values


def _claimed_compile_item(
    work_item_id: str,
    *,
    now: datetime,
    project_key: str = PROJECT_KEY,
    run_id: str = "run-1",
    program_digest: str = PROGRAM_DIGEST,
    capability_id: str = "active-only-capability",
    fairness_key: str | None = None,
) -> dict[str, Any]:
    values = _work_item(
        work_item_id,
        now=now,
        project_key=project_key,
        run_id=run_id,
        program_digest=program_digest,
        capability_id=capability_id,
        fairness_key=fairness_key,
    )
    lease_token = f"lease:{work_item_id}"
    lease_expires_at = now + timedelta(minutes=10)
    assignment = RuntimeAssignment.model_validate(values["assignment_binding_json"])
    binding = ClaimBinding.bind(
        assignment,
        authorization_digest=AUTHORITY_DIGEST,
        lease_token=lease_token,
        lease_expires_at=lease_expires_at,
        node_id="node-1",
        node_profile_digest=NODE_PROFILE_DIGEST,
        authority_digest=AUTHORITY_DIGEST,
    )
    values.update(
        state="CLAIMED",
        attempt_count=1,
        revision=1,
        lease_token=lease_token,
        lease_owner="node-1",
        lease_expires_at=lease_expires_at,
        claim_attempt_id=binding.attempt_id,
        claim_binding_json=binding.model_dump(mode="json"),
        claim_binding_digest=binding.binding_digest,
    )
    return values


def _fair_candidate(row: sa.RowMapping) -> FairClaimCandidate:
    return FairClaimCandidate(
        work_item_id=str(row["work_item_id"]),
        project_key=str(row["project_key"]),
        capability_id=str(row["capability_id"]),
        fairness_key=str(row["fairness_key"]),
        declared_priority=int(row["declared_priority"]),
        enqueue_seq=int(row["enqueue_seq"]),
        enqueued_at=row["enqueued_at"],
        due_at=row["due_at"],
    )


def _seed_claim_control(
    connection: sa.Connection,
    *,
    now: datetime,
    node_ids: tuple[str, ...] = ("node-1", "node-2"),
) -> None:
    _seed_run(connection)
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_deployment_catalogs"]).values(
            catalog_digest=CATALOG_DIGEST,
            catalog_version="1",
            catalog_ref="deployment-catalog:test",
            node_profile_digest=NODE_PROFILE_DIGEST,
            security_profile_digest=_digest("security-profile"),
            resource_profile_digest=_digest("resource-profile"),
        )
    )
    for node_id in node_ids:
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_nodes"]).values(
                node_id=node_id,
                node_profile_digest=NODE_PROFILE_DIGEST,
                deployment_catalog_digest=CATALOG_DIGEST,
                runtime_protocol_version="1",
                state="ACTIVE",
                heartbeat_at=now,
                started_at=now,
            )
        )
    _add_capability_authority(connection, "capability-1", now=now)


def _add_capability_authority(
    connection: sa.Connection,
    capability_id: str,
    *,
    now: datetime,
    project_key: str = PROJECT_KEY,
) -> None:
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_capability_authority"]).values(
            project_key=project_key,
            capability_id=capability_id,
            mode="on",
            authority_epoch=1,
            successor_claim_enabled=True,
            legacy_claim_enabled=False,
            allowlist_digest=_digest("allowlist"),
            config_digest=_digest("config"),
            effective_at=now,
            updated_by="integration-test",
            approval_ref="approval:test",
            rollback_target_ref=f"legacy:{capability_id}",
        )
    )


def _claim_context(
    node_id: str,
    authority_digest: str = AUTHORITY_DIGEST,
) -> NodeClaimContext:
    return NodeClaimContext(
        node_id=node_id,
        node_profile_digest=NODE_PROFILE_DIGEST,
        deployment_catalog_digest=CATALOG_DIGEST,
        runtime_protocol_version="1",
        authority_snapshot_digest=authority_digest,
        interpreter_profile_digests=frozenset({INTERPRETER_PROFILE_DIGEST}),
        lease_seconds=45,
        reservation_seconds=60,
    )


CONTROL_SCOPE = ControlPlaneScope(
    system_actor_id="integration-scheduler",
    permission="runtime.cross_project_claim",
    authority_epoch=1,
)


def test_real_postgres_creates_exact_public_and_project_schema_contracts(
    live_database: LiveDatabase,
) -> None:
    inspector = sa.inspect(live_database.engine)
    assert set(PUBLIC_TABLES) <= set(inspector.get_table_names(schema="public"))
    assert set(live_database.project_tables.as_dict()) == set(
        inspector.get_table_names(schema=PROJECT_SCHEMA)
    )
    work_columns = {
        column["name"]: column
        for column in inspector.get_columns("runtime_work_items", schema="public")
    }
    assert work_columns["enqueue_seq"]["identity"] is not None
    assert "content_bytes" not in {
        column["name"]
        for column in inspector.get_columns("runtime_events", schema="public")
    }
    assert "content_bytes" in {
        column["name"]
        for column in inspector.get_columns("successor_values", schema=PROJECT_SCHEMA)
    }


def test_one_connection_transaction_commits_and_rolls_back_across_schemas(
    live_database: LiveDatabase,
) -> None:
    public_table = PUBLIC_TABLES["runtime_deployment_catalogs"]
    project_table = live_database.project_tables.research_owner_bindings

    with RuntimeUnitOfWork(engine=live_database.engine) as uow:
        assert (
            uow.public_handle().connection
            is uow.project_handle(live_database.project_scope).connection
        )
        uow.connection.execute(
            sa.insert(public_table).values(
                catalog_digest=_digest("rollback-catalog"),
                catalog_version="1",
                catalog_ref="catalog:rollback",
                node_profile_digest=NODE_PROFILE_DIGEST,
                security_profile_digest=_digest("security"),
                resource_profile_digest=_digest("resource"),
            )
        )
        uow.connection.execute(
            sa.insert(project_table).values(
                project_key=PROJECT_KEY,
                object_type="Inquiry.v1",
                owner_epoch=1,
                owner_mode="CANONICAL_OWNED",
                owner_id="ResearchLedger",
                readback_profile_ref="ledger:v1",
                base_incarnation="project-inc-1",
                rollback_evidence_ref="rollback:test",
                effective_at=datetime.now(UTC),
                approval_ref="approval:test",
            )
        )
        uow.rollback()

    with live_database.engine.connect() as connection:
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(public_table)) == 0
        )
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(project_table))
            == 0
        )

    with RuntimeUnitOfWork(engine=live_database.engine) as uow:
        uow.connection.execute(
            sa.insert(public_table).values(
                catalog_digest=_digest("commit-catalog"),
                catalog_version="1",
                catalog_ref="catalog:commit",
                node_profile_digest=NODE_PROFILE_DIGEST,
                security_profile_digest=_digest("security"),
                resource_profile_digest=_digest("resource"),
            )
        )
        uow.connection.execute(
            sa.insert(project_table).values(
                project_key=PROJECT_KEY,
                object_type="Inquiry.v1",
                owner_epoch=1,
                owner_mode="CANONICAL_OWNED",
                owner_id="ResearchLedger",
                readback_profile_ref="ledger:v1",
                base_incarnation="project-inc-1",
                rollback_evidence_ref="rollback:test",
                effective_at=datetime.now(UTC),
                approval_ref="approval:test",
            )
        )
        uow.commit()

    with live_database.engine.connect() as connection:
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(public_table)) == 1
        )
        assert (
            connection.scalar(sa.select(sa.func.count()).select_from(project_table))
            == 1
        )


def test_event_sequence_allocator_and_revision_cas_are_cross_connection_safe(
    live_database: LiveDatabase,
) -> None:
    with live_database.engine.begin() as connection:
        _seed_run(connection)

    first_connection = live_database.engine.connect()
    first_transaction = first_connection.begin()
    first_receipt = RuntimeJournalRepository(
        first_connection, live_database.runtime_scope
    ).append_transition(
        run_id="run-1",
        expected_revision=0,
        snapshot_values={"state": "COMPILING"},
        events=(_event("CompileStarted"),),
    )
    assert first_receipt.first_event_seq == first_receipt.last_event_seq == 1

    second_started = threading.Event()

    def stale_writer() -> str:
        with live_database.engine.connect() as connection:
            transaction = connection.begin()
            connection.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
            second_started.set()
            try:
                RuntimeJournalRepository(
                    connection, live_database.runtime_scope
                ).append_transition(
                    run_id="run-1",
                    expected_revision=0,
                    snapshot_values={"state": "COMPILING"},
                    events=(_event("CompetingCompileStarted"),),
                )
            except StaleRevisionError as exc:
                transaction.rollback()
                return str(exc)
            transaction.commit()
            return "unexpected-success"

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(stale_writer)
        assert second_started.wait(timeout=5)
        first_transaction.commit()
        first_connection.close()
        assert "stale runtime run revision" in future.result(timeout=10)

    with live_database.engine.begin() as connection:
        second_receipt = RuntimeJournalRepository(
            connection, live_database.runtime_scope
        ).append_transition(
            run_id="run-1",
            expected_revision=1,
            snapshot_values={"state": "COMPILING"},
            events=(_event("CompileObserved"),),
        )
        assert second_receipt.first_event_seq == second_receipt.last_event_seq == 2

    with live_database.engine.connect() as connection:
        run = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_runs"]).where(
                    PUBLIC_TABLES["runtime_runs"].c.run_id == "run-1"
                )
            )
            .mappings()
            .one()
        )
        sequences = connection.scalars(
            sa.select(PUBLIC_TABLES["runtime_events"].c.seq).order_by(
                PUBLIC_TABLES["runtime_events"].c.seq
            )
        ).all()
        assert (run["revision"], run["next_event_seq"]) == (2, 3)
        assert sequences == [1, 2]


def test_event_snapshot_and_successor_work_item_rollback_as_one_unit(
    live_database: LiveDatabase,
) -> None:
    now = datetime.now(UTC)
    with live_database.engine.begin() as connection:
        _seed_run(connection)

    invalid_work = _work_item("work-invalid", now=now)
    # Scheduling columns sit outside RuntimeAssignment but are still part of
    # the atomic persistence command.  This reaches the final INSERT and lets
    # PostgreSQL prove snapshot/event rollback after its CHECK rejects it.
    invalid_work["declared_priority"] = -1
    with live_database.engine.connect() as connection:
        transaction = connection.begin()
        with pytest.raises(IntegrityError):
            RuntimeJournalRepository(
                connection, live_database.runtime_scope
            ).append_transition(
                run_id="run-1",
                expected_revision=0,
                snapshot_values={"state": "COMPILING"},
                events=(_event("CompileStarted"),),
                work_items=(invalid_work,),
            )
        transaction.rollback()

    with live_database.engine.connect() as connection:
        run = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_runs"]).where(
                    PUBLIC_TABLES["runtime_runs"].c.run_id == "run-1"
                )
            )
            .mappings()
            .one()
        )
        assert (run["state"], run["revision"], run["next_event_seq"]) == (
            "SUBMITTED",
            0,
            1,
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(PUBLIC_TABLES["runtime_events"])
            )
            == 0
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(
                    PUBLIC_TABLES["runtime_work_items"]
                )
            )
            == 0
        )

    with live_database.engine.begin() as connection:
        receipt = RuntimeJournalRepository(
            connection, live_database.runtime_scope
        ).append_transition(
            run_id="run-1",
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(_event("CompileStarted"),),
            work_items=(_work_item("work-valid", now=now),),
        )
        assert (receipt.event_count, receipt.work_item_count) == (1, 1)

    with live_database.engine.connect() as connection:
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(PUBLIC_TABLES["runtime_events"])
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(
                    PUBLIC_TABLES["runtime_work_items"]
                )
            )
            == 1
        )


def test_two_connections_cannot_duplicate_non_effect_claim_and_expired_compile_replays(
    live_database: LiveDatabase,
) -> None:
    now = datetime.now(UTC)
    with live_database.engine.begin() as connection:
        _seed_claim_control(connection, now=now)
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_work_items"]).values(
                **_work_item("work-replay", now=now)
            )
        )

    def claim(node_id: str, observed_at: datetime) -> tuple[Any, ...]:
        with live_database.engine.begin() as connection:
            return WorkItemClaimRepository(connection).claim_due(
                CONTROL_SCOPE,
                _claim_context(node_id),
                limit=1,
                now=observed_at,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda node: claim(node, now),
                ("node-1", "node-2"),
            )
        )
    assert sorted(len(result) for result in results) == [0, 1]

    expired_at = now + timedelta(minutes=2)
    with live_database.engine.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_work_items"])
            .where(PUBLIC_TABLES["runtime_work_items"].c.work_item_id == "work-replay")
            .values(lease_expires_at=expired_at - timedelta(seconds=1))
        )
        assert WorkItemClaimRepository(connection).reap_expired(
            CONTROL_SCOPE, now=expired_at
        ) == (
            "work-replay",
        )

    replayed = claim("node-2", expired_at)
    assert len(replayed) == 1
    assert replayed[0].work_item_id == "work-replay"
    with live_database.engine.connect() as connection:
        row = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_work_items"]).where(
                    PUBLIC_TABLES["runtime_work_items"].c.work_item_id == "work-replay"
                )
            )
            .mappings()
            .one()
        )
        assert (row["state"], row["attempt_count"], row["revision"]) == (
            "CLAIMED",
            2,
            3,
        )


def test_project_active_limit_is_serialized_across_capabilities_and_connections(
    live_database: LiveDatabase,
) -> None:
    now = datetime.now(UTC)
    work_items = PUBLIC_TABLES["runtime_work_items"]
    policy = FairSharePolicy(
        max_project_active=1,
        max_capability_active=1,
    )
    with live_database.engine.begin() as connection:
        _seed_claim_control(connection, now=now)
        _add_capability_authority(connection, "capability-2", now=now)
        connection.execute(
            sa.insert(work_items),
            (
                _work_item("project-limit-cap-1", now=now),
                _work_item(
                    "project-limit-cap-2",
                    now=now,
                    capability_id="capability-2",
                    fairness_key="same-project-distinct-bucket-b",
                ),
            ),
        )
        seeded = connection.execute(
            sa.select(work_items.c.project_key, work_items.c.fairness_key)
        ).all()
        assert {row.project_key for row in seeded} == {PROJECT_KEY}
        assert len({row.fairness_key for row in seeded}) == 2

    def claim(node_id: str, observed_at: datetime = now) -> tuple[Any, ...]:
        with live_database.engine.begin() as connection:
            return WorkItemClaimRepository(connection).claim_due(
                CONTROL_SCOPE,
                _claim_context(node_id),
                limit=1,
                fairness=policy,
                cursor=0,
                now=observed_at,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(claim, ("node-1", "node-2")))
    assert sorted(len(result) for result in results) == [0, 1]

    claimed = next(result[0] for result in results if result)
    with live_database.engine.connect() as connection:
        rows = (
            connection.execute(
                sa.select(work_items).order_by(work_items.c.work_item_id)
            )
            .mappings()
            .all()
        )
        claimed_rows = [row for row in rows if row["state"] == "CLAIMED"]
        waiting_rows = [row for row in rows if row["state"] == "WAITING"]
        assert len(claimed_rows) == len(waiting_rows) == 1
        assert waiting_rows[0]["wait_reason"] == "RESOURCE_LIMIT"
        assert waiting_rows[0]["lease_token"] is None
        assert waiting_rows[0]["claim_attempt_id"] is None
        assert waiting_rows[0]["claim_binding_digest"] is None

    with live_database.engine.begin() as connection:
        released = WorkItemClaimRepository(connection).release(
            live_database.runtime_scope,
            claimed.work_item_id,
            claimed.lease_token,
            expected_revision=1,
            terminal_state="COMPLETED",
            now=now,
        )
        assert released["state"] == "COMPLETED"
    assert len(claim("node-2", now + timedelta(seconds=2))) == 1


def test_live_project_active_order_matches_pure_selector_counterexample(
    live_database: LiveDatabase,
) -> None:
    now = datetime.now(UTC)
    work_items = PUBLIC_TABLES["runtime_work_items"]
    policy = FairSharePolicy(
        max_project_active=3,
        max_capability_active=3,
    )
    with live_database.engine.begin() as connection:
        _seed_claim_control(connection, now=now)
        run_b, program_b_digest, _scope_b_digest = _seed_secondary_run(connection)
        _add_capability_authority(
            connection,
            "capability-1",
            project_key=SECONDARY_PROJECT_KEY,
            now=now,
        )
        connection.execute(
            sa.insert(work_items).values(
                **_claimed_compile_item(
                    "active-project-a",
                    now=now,
                    fairness_key="bucket-project-a",
                )
            )
        )
        connection.execute(
            sa.insert(work_items),
            (
                _work_item(
                    "ready-project-a",
                    now=now,
                    fairness_key="bucket-project-a",
                ),
                _work_item(
                    "ready-project-b",
                    now=now,
                    project_key=SECONDARY_PROJECT_KEY,
                    run_id=run_b,
                    program_digest=program_b_digest,
                    assignment_incarnation="run-inc-b-1",
                    fairness_key="bucket-project-b",
                ),
            ),
        )
        ready_rows = (
            connection.execute(
                sa.select(work_items)
                .where(work_items.c.state == "READY")
                .order_by(work_items.c.enqueue_seq)
            )
            .mappings()
            .all()
        )
        pure = select_fair_claims(
            tuple(_fair_candidate(row) for row in ready_rows),
            now=now,
            limit=1,
            policy=policy,
            active_by_project={PROJECT_KEY: 1, SECONDARY_PROJECT_KEY: 0},
            active_by_capability={
                (PROJECT_KEY, "capability-1"): 0,
                (SECONDARY_PROJECT_KEY, "capability-1"): 0,
            },
            cursor=0,
        )
        assert tuple(item.work_item_id for item in pure) == ("ready-project-b",)

    with live_database.engine.begin() as connection:
        live = WorkItemClaimRepository(connection).claim_due(
            CONTROL_SCOPE,
            _claim_context("node-2"),
            limit=1,
            fairness=policy,
            cursor=0,
            now=now,
        )
        assert tuple(item.work_item_id for item in live) == tuple(
            item.work_item_id for item in pure
        )


def test_live_capability_active_order_matches_pure_selector_counterexample(
    live_database: LiveDatabase,
) -> None:
    now = datetime.now(UTC)
    work_items = PUBLIC_TABLES["runtime_work_items"]
    policy = FairSharePolicy(
        max_project_active=3,
        max_capability_active=3,
    )
    with live_database.engine.begin() as connection:
        _seed_claim_control(connection, now=now)
        _add_capability_authority(connection, "cap-a", now=now)
        _add_capability_authority(connection, "cap-b", now=now)
        connection.execute(
            sa.insert(work_items).values(
                **_claimed_compile_item(
                    "active-cap-a",
                    now=now,
                    capability_id="cap-a",
                    fairness_key="shared-capability-bucket",
                )
            )
        )
        connection.execute(
            sa.insert(work_items),
            (
                _work_item(
                    "ready-cap-a",
                    now=now,
                    capability_id="cap-a",
                    fairness_key="shared-capability-bucket",
                ),
                _work_item(
                    "ready-cap-b",
                    now=now,
                    capability_id="cap-b",
                    fairness_key="shared-capability-bucket",
                ),
            ),
        )
        ready_rows = (
            connection.execute(
                sa.select(work_items)
                .where(work_items.c.state == "READY")
                .order_by(work_items.c.enqueue_seq)
            )
            .mappings()
            .all()
        )
        pure = select_fair_claims(
            tuple(_fair_candidate(row) for row in ready_rows),
            now=now,
            limit=1,
            policy=policy,
            active_by_project={PROJECT_KEY: 1},
            active_by_capability={
                (PROJECT_KEY, "cap-a"): 1,
                (PROJECT_KEY, "cap-b"): 0,
            },
            cursor=0,
        )
        assert tuple(item.work_item_id for item in pure) == ("ready-cap-b",)

    with live_database.engine.begin() as connection:
        live = WorkItemClaimRepository(connection).claim_due(
            CONTROL_SCOPE,
            _claim_context("node-2"),
            limit=1,
            fairness=policy,
            cursor=0,
            now=now,
        )
        assert tuple(item.work_item_id for item in live) == tuple(
            item.work_item_id for item in pure
        )


def test_live_fairness_interleaves_capabilities_despite_hot_capability_backlog(
    live_database: LiveDatabase,
) -> None:
    now = datetime.now(UTC)
    work_items = PUBLIC_TABLES["runtime_work_items"]
    with live_database.engine.begin() as connection:
        _seed_claim_control(connection, now=now)
        _add_capability_authority(connection, "cap-a", now=now)
        _add_capability_authority(connection, "cap-b", now=now)
        rows = [
            _work_item(
                f"hot-cap-a-{index}",
                now=now,
                capability_id="cap-a",
            )
            for index in range(4)
        ]
        rows.append(_work_item("cold-cap-b", now=now, capability_id="cap-b"))
        connection.execute(sa.insert(work_items), rows)

    with live_database.engine.begin() as connection:
        claimed = WorkItemClaimRepository(connection).claim_due(
            CONTROL_SCOPE,
            _claim_context("node-1"),
            limit=2,
            fairness=FairSharePolicy(
                project_quantum=2,
                capability_quantum=1,
                max_project_active=10,
                max_capability_active=10,
            ),
            cursor=0,
            now=now,
        )
        assert len(claimed) == 2
        claimed_ids = {record.work_item_id for record in claimed}
        claimed_capabilities = set(
            connection.scalars(
                sa.select(work_items.c.capability_id).where(
                    work_items.c.work_item_id.in_(claimed_ids)
                )
            ).all()
        )
        assert claimed_capabilities == {"cap-a", "cap-b"}


def test_typed_public_control_rejects_missing_tampered_and_embedded_payloads(
    live_database: LiveDatabase,
) -> None:
    now = datetime.now(UTC)
    repository = RuntimeJournalRepository(
        object(),  # command construction is effect free
        live_database.runtime_scope,
    )

    missing = _work_item("missing-assignment", now=now)
    missing.pop("assignment_binding_json")
    with pytest.raises(ExactBindingConflict, match="lacks exact assignment"):
        repository.commands(
            run_id="run-1",
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(),
            work_items=(missing,),
        )

    tampered = _work_item("tampered-assignment", now=now)
    tampered["assignment_binding_json"] = {
        **tampered["assignment_binding_json"],
        "trace_id": "trace:tampered-after-freeze",
    }
    with pytest.raises(ExactBindingConflict, match="digest mismatch"):
        repository.commands(
            run_id="run-1",
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(),
            work_items=(tampered,),
        )

    bad_event = {
        **_event("PayloadSmugglingRejected"),
        "event_metadata_json": {"body": "tenant payload"},
    }
    with pytest.raises(PublicPayloadViolation, match="not lifecycle/ref/id/digest"):
        repository.commands(
            run_id="run-1",
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(bad_event,),
        )

    embedded_claim = _work_item("embedded-claim-payload", now=now)
    embedded_claim["claim_binding_json"] = {"payload": "tenant payload"}
    with pytest.raises(PublicPayloadViolation, match="invalid typed control binding"):
        repository.commands(
            run_id="run-1",
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(),
            work_items=(embedded_claim,),
        )


@pytest.mark.parametrize(
    ("mode", "match"),
    (
        ("missing", "exact QUALIFIED plan binding not found"),
        ("rejected", "exact QUALIFIED plan binding not found"),
        ("extra_binding", "closure differs from exact ExecutionPlan"),
        ("missing_binding", "closure differs from exact ExecutionPlan"),
        ("wrong_operation", "step binding drift"),
        ("eligibility_drift", "assignment/authorization exact binding drift"),
    ),
)
def test_effect_claim_rejects_unqualified_or_drifted_plan_membership(
    live_database: LiveDatabase,
    mode: str,
    match: str,
) -> None:
    now = datetime.now(UTC)
    assignment_eligibility = QueueEligibility(
        project_key=PROJECT_KEY,
        capability_id="capability-1",
        resource_class=ResourceClass.CPU_LIGHT,
        units=1,
        policy_epoch=1,
        policy_digest=RESOURCE_POLICY_DIGEST,
        concurrency_key="key:single-effect",
        provider_key=PROVIDER_KEY,
    )
    exact_first = _authorization(
        now,
        step_id=STEP_ONE_ID,
        payload_digest=_digest(f"input:{STEP_ONE_ID}"),
        eligibility=assignment_eligibility,
    )
    exact_second = _authorization(
        now,
        step_id=STEP_TWO_ID,
        payload_digest=_digest(f"input:{STEP_TWO_ID}"),
        eligibility=assignment_eligibility,
    )
    qualified_step_bindings: tuple[StepAuthorizationBinding, ...] | None = None
    authorization_eligibility: QueueEligibility | None = None
    if mode == "extra_binding":
        plan_external = _authorization(
            now,
            step_id="plan-external-step",
            contract_step_id=STEP_ONE_ID,
            payload_digest=_digest("input:plan-external-step"),
            eligibility=assignment_eligibility,
        )
        qualified_step_bindings = (exact_first, exact_second, plan_external)
    elif mode == "missing_binding":
        qualified_step_bindings = (exact_second,)
    elif mode == "wrong_operation":
        wrong_first = _authorization(
            now,
            step_id=STEP_ONE_ID,
            payload_digest=_digest(f"input:{STEP_ONE_ID}"),
            eligibility=assignment_eligibility,
            operation_kind="test.effect.wrong.v1",
            operation_contract_digest=_digest("wrong-operation-contract"),
        )
        qualified_step_bindings = (wrong_first, exact_second)
    elif mode == "eligibility_drift":
        authorization_eligibility = QueueEligibility(
            project_key=PROJECT_KEY,
            capability_id="capability-1",
            resource_class=ResourceClass.CPU_LIGHT,
            units=1,
            policy_epoch=1,
            policy_digest=RESOURCE_POLICY_DIGEST,
            concurrency_key="key:single-effect",
            provider_key="provider:drifted",
        )

    with live_database.engine.begin() as connection:
        _eligibility, authorization, _qualification_record = _seed_single_effect(
            connection,
            live_database,
            now=now,
            include_qualification=mode != "missing",
            qualification_decision=("REJECTED" if mode == "rejected" else "QUALIFIED"),
            qualified_step_bindings=qualified_step_bindings,
            authorization_eligibility=authorization_eligibility,
        )

    with (
        live_database.engine.begin() as connection,
        pytest.raises(ClaimBindingMismatch, match=match),
    ):
        WorkItemClaimRepository(connection).claim_due(
            CONTROL_SCOPE,
            _claim_context("node-1", authorization.binding_digest),
            limit=1,
            now=now,
        )


def test_claim_time_reservation_prevents_oversubscription_and_expiry_requires_reconcile(
    live_database: LiveDatabase,
) -> None:
    now = datetime.now(UTC)
    eligibility = QueueEligibility(
        project_key=PROJECT_KEY,
        capability_id="capability-1",
        resource_class=ResourceClass.CPU_LIGHT,
        units=1,
        policy_epoch=1,
        policy_digest=RESOURCE_POLICY_DIGEST,
        concurrency_key="key:shared-effect-capacity",
        provider_key=PROVIDER_KEY,
    )
    authorizations_by_step = {
        compiled_step.step_id: _authorization(
            now,
            step_id=compiled_step.step_id,
            payload_digest=_digest(f"input:{compiled_step.step_id}"),
            eligibility=eligibility,
        )
        for compiled_step in PLAN_EFFECT_STEPS
    }
    qualification = _qualification(
        now,
        tuple(authorizations_by_step.values()),
    )
    assert tuple(step.step_kind for step in EXACT_PLAN.ordered_steps) == (
        "EFFECT",
        "EFFECT",
    )
    assert EXACT_PLAN.ordered_steps[0].dependencies == ()
    assert EXACT_PLAN.ordered_steps[1].dependencies == (
        EXACT_PLAN.ordered_steps[0].step_id,
    )
    assert EXACT_PLAN.ready_order == tuple(
        step.step_id for step in EXACT_PLAN.ordered_steps
    )
    assert set(authorizations_by_step) == {
        step.step_id for step in EXACT_PLAN.ordered_steps
    }
    for compiled_step in EXACT_PLAN.ordered_steps:
        contract_ref = compiled_step.operation_contract_ref
        assert contract_ref is not None
        binding = authorizations_by_step[compiled_step.step_id]
        assert (
            binding.operation_kind,
            binding.operation_contract_digest,
        ) == (contract_ref.kind, contract_ref.contract_digest)
    assert {
        binding.step_id for binding in qualification.qualified_plan.step_bindings
    } == set(authorizations_by_step)
    steps = PUBLIC_TABLES["runtime_steps"]
    authorizations = PUBLIC_TABLES["runtime_step_authorizations"]
    work_items = PUBLIC_TABLES["runtime_work_items"]
    authorization_digests: dict[str, str] = {}
    with live_database.engine.begin() as connection:
        _seed_claim_control(connection, now=now)
        _promote_run_ready(connection, live_database, qualification)
        connection.execute(
            sa.insert(PUBLIC_TABLES["runtime_resource_policies"]).values(
                resource_policy_id="policy-1",
                project_key=PROJECT_KEY,
                capability_id="capability-1",
                resource_class="CPU_LIGHT",
                concurrency_limit=1,
                max_project_active=1,
                max_capability_active=1,
                max_resource_active=1,
                units_ceiling=1,
                provider_limit=1,
                policy_epoch=1,
                policy_digest=RESOURCE_POLICY_DIGEST,
            )
        )
        for index, compiled_step in enumerate(PLAN_EFFECT_STEPS, start=1):
            step_id = compiled_step.step_id
            work_item_id = f"effect-work-{index}"
            input_digest = _digest(f"input:{step_id}")
            authorization = authorizations_by_step[step_id]
            contract_ref = compiled_step.operation_contract_ref
            assert contract_ref is not None
            authorization_digests[work_item_id] = authorization.binding_digest
            connection.execute(
                sa.insert(steps).values(
                    project_key=PROJECT_KEY,
                    run_id="run-1",
                    step_id=step_id,
                    operation_id=compiled_step.operation_id,
                    operation_kind=contract_ref.kind,
                    operation_version=contract_ref.contract_version,
                    state="READY",
                    execution_epoch=0,
                    input_digest=input_digest,
                    effect_class="LOCAL_TEST_ONLY",
                    resource_class="CPU_LIGHT",
                    concurrency_key=eligibility.concurrency_key,
                    capability_id="capability-1",
                    claim_owner="successor",
                    claim_authority_epoch=1,
                    claim_policy_digest=CLAIM_POLICY_DIGEST,
                    max_attempts=2,
                )
            )
            connection.execute(
                sa.insert(authorizations).values(
                    **_authorization_row(
                        f"authorization-{index}",
                        authorization,
                    )
                )
            )
            connection.execute(
                sa.insert(work_items).values(
                    **_work_item(
                        work_item_id,
                        now=now,
                        assignment_kind="INTERPRET",
                        step_id=step_id,
                        authority_digest=authorization.binding_digest,
                        qualification_digest=(
                            qualification.qualified_plan.qualification_digest
                        ),
                        eligibility=eligibility,
                    )
                )
            )

    def claim_effect(
        node_id: str,
        authority_digest: str,
        observed_at: datetime = now,
    ) -> tuple[Any, ...]:
        with live_database.engine.begin() as connection:
            return WorkItemClaimRepository(connection).claim_due(
                CONTROL_SCOPE,
                _claim_context(node_id, authority_digest),
                limit=1,
                now=observed_at,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda pair: claim_effect(*pair),
                (
                    ("node-1", authorization_digests["effect-work-1"]),
                    ("node-2", authorization_digests["effect-work-2"]),
                ),
            )
        )
    assert sorted(len(result) for result in results) == [0, 1]
    claimed = next(result[0] for result in results if result)
    assert claimed.attempt_id is not None
    assert claimed.claim_binding.attempt_id == claimed.attempt_id
    assert claimed.claim_binding.assignment_digest == claimed.assignment_digest
    assert claimed.claim_binding.handler_binding_digest == (
        claimed.claim_binding.handler_realization_digest
    )

    with live_database.engine.begin() as connection:
        states = connection.execute(
            sa.select(work_items.c.state, work_items.c.wait_reason)
            .where(work_items.c.assignment_kind == "INTERPRET")
            .order_by(
                work_items.c.work_item_id,
            )
        ).all()
        assert sorted(states) == [
            ("CLAIMED", None),
            ("WAITING", "RESOURCE_LIMIT"),
        ]
        reconcile = (
            connection.execute(
                sa.select(work_items).where(
                    work_items.c.assignment_kind == "RECONCILE",
                    work_items.c.reconciliation_attempt_id == claimed.attempt_id,
                )
            )
            .mappings()
            .one()
        )
        assert reconcile["state"] == "PENDING"
        assert reconcile["handler_binding_kind"] == "RECOVERY"
        assert reconcile["handler_binding_digest"] == RECOVERY_HANDLER_DIGEST
        assert reconcile["authoritative_readback_profile_ref"] == (
            "readback:integration:v1"
        )
        attempt = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                    PUBLIC_TABLES["runtime_effect_attempts"].c.attempt_id
                    == claimed.attempt_id
                )
            )
            .mappings()
            .one()
        )
        assert attempt["assignment_digest"] == claimed.assignment_digest
        assert (
            attempt["handler_binding_digest"] == (attempt["handler_realization_digest"])
        )
        assert attempt["claim_binding_digest"] == (claimed.claim_binding.binding_digest)
        reservation = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_resource_reservations"])
            )
            .mappings()
            .one()
        )
        assert reservation["units"] == 1
        assert reservation["provider_key"] == PROVIDER_KEY
        assert reservation["policy_epoch"] == 1
        assert reservation["policy_digest"] == RESOURCE_POLICY_DIGEST
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(
                    PUBLIC_TABLES["runtime_resource_reservations"]
                )
            )
            == 1
        )
        resource_limited_id = connection.scalar(
            sa.select(work_items.c.work_item_id).where(
                work_items.c.assignment_kind == "INTERPRET",
                work_items.c.state == "WAITING",
                work_items.c.wait_reason == "RESOURCE_LIMIT",
            )
        )
        assert resource_limited_id is not None
        expired_at = now + timedelta(minutes=2)
        connection.execute(
            sa.update(work_items)
            .where(work_items.c.work_item_id == claimed.work_item_id)
            .values(lease_expires_at=expired_at - timedelta(seconds=1))
        )
        # Keep the resource-limited peer out of the recovery claim.  Its
        # capacity observation remains durable but is unrelated to this exact
        # attempt's authoritative reconciliation.
        connection.execute(
            sa.update(work_items)
            .where(work_items.c.work_item_id == resource_limited_id)
            .values(due_at=expired_at + timedelta(days=1))
        )

    with live_database.engine.begin() as connection:
        repository = WorkItemClaimRepository(connection)
        assert repository.reap_expired(
            CONTROL_SCOPE, now=expired_at
        ) == (claimed.work_item_id,)
        with pytest.raises(
            ClaimConflict,
            match="cannot return to READY without NonStartProof",
        ):
            repository.release(
                live_database.runtime_scope,
                claimed.work_item_id,
                claimed.lease_token,
                expected_revision=2,
                terminal_state="READY",
                now=expired_at,
            )

    with live_database.engine.connect() as connection:
        original = (
            connection.execute(
                sa.select(work_items).where(
                    work_items.c.work_item_id == claimed.work_item_id
                )
            )
            .mappings()
            .one()
        )
        assert (original["state"], original["wait_reason"]) == (
            "WAITING",
            "BACKOFF",
        )
        assert original["last_failure_ref"].startswith("reconcile-work-item:")
        attempt = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                    PUBLIC_TABLES["runtime_effect_attempts"].c.attempt_id
                    == claimed.attempt_id
                )
            )
            .mappings()
            .one()
        )
        assert attempt["disposition"] == "OUTCOME_UNKNOWN"
        reservation = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_resource_reservations"])
            )
            .mappings()
            .one()
        )
        assert (reservation["state"], reservation["release_reason"]) == (
            "EXPIRED",
            "LEASE_EXPIRED_OUTCOME_UNKNOWN",
        )
        step = (
            connection.execute(
                sa.select(steps).where(steps.c.step_id == claimed.step_id)
            )
            .mappings()
            .one()
        )
        assert step["state"] == "RECONCILING"
        reconcile_rows = (
            connection.execute(
                sa.select(work_items).where(
                    work_items.c.assignment_kind == "RECONCILE",
                    work_items.c.reconciliation_attempt_id == claimed.attempt_id,
                )
            )
            .mappings()
            .all()
        )
        assert {row["state"] for row in reconcile_rows} == {
            "READY",
            "SUPERSEDED",
        }
        reconcile = next(row for row in reconcile_rows if row["state"] == "READY")
        trigger = next(row for row in reconcile_rows if row["state"] == "SUPERSEDED")
        assert reconcile["work_item_id"] != trigger["work_item_id"]
        assert (reconcile["state"], reconcile["expected_step_revision"]) == (
            "READY",
            step["revision"],
        )
        assert (
            RuntimeAssignment.model_validate(
                reconcile["assignment_binding_json"]
            ).assignment_digest
            == reconcile["assignment_digest"]
        )
        event_types = connection.scalars(
            sa.select(PUBLIC_TABLES["runtime_events"].c.event_type).order_by(
                PUBLIC_TABLES["runtime_events"].c.seq
            )
        ).all()
        assert event_types == ["StepClaimed", "LeaseExpiredOutcomeUnknown"]

    reconciled = claim_effect(
        "node-2",
        claimed.claim_binding.authorization_digest,
        expired_at,
    )
    assert len(reconciled) == 1
    assert reconciled[0].work_item_id == reconcile["work_item_id"]
    assert reconciled[0].attempt_id != claimed.attempt_id
    with live_database.engine.connect() as connection:
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(
                    PUBLIC_TABLES["runtime_effect_attempts"]
                )
            )
            == 1
        )
        original = (
            connection.execute(
                sa.select(work_items).where(
                    work_items.c.work_item_id == claimed.work_item_id
                )
            )
            .mappings()
            .one()
        )
        assert (original["state"], original["attempt_count"]) == (
            "WAITING",
            1,
        )

    proof_content: dict[str, Any] = {
        "attempt_id": claimed.attempt_id,
        "interpreter_id": "integration-interpreter",
        "interpreter_version": "1",
        "provider_id": PROVIDER_KEY,
        "provider_version": "1",
        "external_idempotency_key": f"attempt:sha256:{claimed.attempt_id}",
        "authoritative_readback_locator": "readback:integration:v1",
        "authoritative_observation_digest": _digest("not-started-observation"),
        "observed_at": expired_at,
    }
    provisional = NonStartProof.model_construct(
        **proof_content,
        proof_digest="0" * 64,
    )
    proof = NonStartProof(
        **proof_content,
        proof_digest=canonical_digest(
            provisional,
            exclude_fields={"proof_digest"},
        ),
    )
    authorize_successor_attempt(
        prior_attempt_id=claimed.attempt_id,
        proof=proof,
    )
    with pytest.raises(ValueError, match="different attempt"):
        authorize_successor_attempt(
            prior_attempt_id=_digest("different-attempt"),
            proof=proof,
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(
                    PUBLIC_TABLES["runtime_effect_attempts"]
                )
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(PUBLIC_TABLES["runtime_events"])
            )
            == 1
        )


def test_research_ledger_and_runtime_journal_keep_distinct_authority_owners(
    live_database: LiveDatabase,
) -> None:
    binding = OwnerBindingRecord(
        object_type=INQUIRY_TYPE.type_id,
        owner_mode="CANONICAL_OWNED",
        owner_id="ResearchLedger",
        owner_epoch=1,
        readback_profile_ref="ledger-readback:v1",
        base_incarnation="project-inc-1",
        rollback_evidence_ref="rollback:test",
        effective_at=datetime.now(UTC),
        approval_ref="approval:test",
    )
    inquiry = ResearchObjectRef(
        object_id="inquiry-1",
        object_type=INQUIRY_TYPE,
        project_key=PROJECT_KEY,
        owner_binding_ref="ResearchLedger",
        content_ref="project-value:inquiry-1",
        content_digest=_digest("inquiry-content"),
        provenance_closure_digest=_digest("inquiry-provenance"),
        incarnation="inquiry-inc-1",
    )
    with live_database.engine.begin() as connection:
        OwnerBindingRepository(connection, live_database.project_tables).put_exact(
            live_database.runtime_scope,
            binding,
            expected_owner_epoch=0,
            expected_base_incarnation="project-inc-1",
        )
        ResearchLedgerRepository(connection, live_database.project_tables).put_object(
            live_database.runtime_scope,
            inquiry,
            expected_revision=0,
            expected_incarnation="inquiry-inc-1",
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(
                    live_database.project_tables.research_objects
                )
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(PUBLIC_TABLES["runtime_events"])
            )
            == 0
        )

    with live_database.engine.begin() as connection:
        _seed_run(connection)
        RuntimeJournalRepository(
            connection, live_database.runtime_scope
        ).append_transition(
            run_id="run-1",
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(
                _event(
                    "InquiryObserved",
                    payload_ref=inquiry.content_ref,
                ),
            ),
        )

    inspector = sa.inspect(live_database.engine)
    assert not inspector.has_table("research_objects", schema="public")
    with live_database.engine.connect() as connection:
        event = (
            connection.execute(sa.select(PUBLIC_TABLES["runtime_events"]))
            .mappings()
            .one()
        )
        assert event["payload_ref"] == inquiry.content_ref
        assert event["payload_digest"] == _digest(inquiry.content_ref)
        assert (
            connection.scalar(
                sa.select(sa.func.count()).select_from(
                    live_database.project_tables.research_objects
                )
            )
            == 1
        )
