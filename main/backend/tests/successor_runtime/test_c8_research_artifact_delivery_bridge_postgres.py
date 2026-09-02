"""Disposable PostgreSQL foundation evidence for the C8 delivery bridge."""

from __future__ import annotations

import dataclasses
import hashlib
import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from app.successor_runtime.capabilities import c8_common as c8
from app.successor_runtime.capabilities import c8_program as c8p
from app.successor_runtime.capabilities.c8_program import (
    C8_3_INPUT_TYPE,
    C8_3_KIND,
    C8_ADMISSION_KIND,
    C8_DELIVERY_INTENT_PREPARE_KIND,
    C8_DELIVERY_INTENT_TYPE,
    C8_RESEARCH_ARTIFACT_TYPE,
    C8_VERIFY_KIND,
    DELIVERY_INTERNAL_EXPORT_KIND,
    build_c8_catalog,
    build_c8_delivery_bridge_bundle,
    build_c8_delivery_bridge_program,
    compile_c8_delivery_bridge_program,
)
from app.successor_runtime.capabilities.checksum import canonical_json, content_digest
from app.successor_runtime.capabilities.first_specimen import (
    build_first_specimen_bundle,
)
from app.successor_runtime.capabilities.first_specimen_delivery_gate import (
    DeliveryIntentTemplate,
)
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.catalog import OperationContractRegistry
from app.successor_runtime.language.normalize import normalize_program
from app.successor_runtime.language.program import Atom, ProgramNode, Then
from app.successor_runtime.research.artifacts import artifact_identity_ref
from app.successor_runtime.research.object_types import (
    CANONICAL_CODEC_ID,
    ObjectType,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompilerBinding,
    HandlerBindingKind,
    QualificationBinding,
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
from app.successor_runtime.runtime.resources import (
    QueueEligibility,
    ResourceClass,
)
from app.successor_runtime.substrate.blob.internal_export import (
    InternalExportInterpreter,
    InternalExportReadbackUnavailable,
)
from app.successor_runtime.substrate.blob.store import ProjectBlobStore
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
from app.successor_runtime.substrate.postgres.c8_artifact_handler import stage_artifact
from app.successor_runtime.substrate.postgres.c8_production import (
    build_postgres_c8_delivery_assembly,
)
from app.successor_runtime.substrate.postgres.first_specimen_activation import (
    FirstSpecimenActivationCatalog,
    persist_qualification_step_shells,
)
from app.successor_runtime.substrate.postgres.first_specimen_delivery_gate import (
    FirstSpecimenDeliveryGateRequest,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_METADATA,
    PUBLIC_TABLES,
    project_tables,
)
from app.successor_runtime.substrate.postgres.nodes import (
    DeploymentCatalog,
    DeploymentCatalogRepository,
    RuntimeNodeRepository,
)
from app.successor_runtime.substrate.postgres.owner_bindings import (
    OwnerBindingRecord,
    OwnerBindingRepository,
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
)
from app.successor_runtime.substrate.postgres.runtime_lifecycle import (
    ActivateQualification,
    AssignmentEnvelope,
    AttachPlan,
    RuntimeLifecycleRepository,
    SubmitRun,
)
from app.successor_runtime.substrate.postgres.session import compute_scope_digest
from app.successor_runtime.substrate.postgres.values import ValueRepository
from app.successor_runtime.substrate.projections.c8_handler_bindings import (
    build_c8_delivery_activation_catalog,
)

pytestmark = pytest.mark.integration

DATABASE_NAME = "mrw_c8_delivery_bridge_test"
ENV_URL = "SUCCESSOR_TEST_DATABASE_URL"
PROJECT_KEY = "p4-c8-delivery"
RESOLVED_SCHEMA = "mrw_p4_c8_delivery"
RESOURCE_POLICY_DIGEST = "0" * 64
NOW = datetime(2031, 1, 1, 8, 0, tzinfo=UTC)
PROJECT_INCARNATION = "c8-delivery-project-incarnation-1"
PROJECT_SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY,
    RESOLVED_SCHEMA,
    1,
    PROJECT_INCARNATION,
)
DELIVERY_AUTHORITY_DIGEST = hashlib.sha256(b"c8-delivery-authority").hexdigest()
DEPLOYMENT_CATALOG_DIGEST = hashlib.sha256(b"c8-delivery-deployment").hexdigest()
NODE_PROFILE_DIGEST = hashlib.sha256(b"c8-delivery-node-profile").hexdigest()
SECURITY_PROFILE_DIGEST = hashlib.sha256(b"c8-delivery-security").hexdigest()
RESOURCE_PROFILE_DIGEST = hashlib.sha256(b"c8-delivery-resource").hexdigest()
CLAIM_POLICY_DIGEST = hashlib.sha256(b"c8-delivery-claim-policy").hexdigest()
RESOURCE_POLICY_EPOCH = 1
AUTHORITY_EPOCH = 1


def _server_url() -> str:
    env_url = os.environ.get(ENV_URL)
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
                text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
            connection.execute(text("CREATE DATABASE " + DATABASE_NAME))
    except Exception as exc:  # noqa: BLE001 - environment-dependent skip
        server.dispose()
        pytest.skip(f"cannot create disposable database {DATABASE_NAME}: {exc}")
    return server


@pytest.fixture(scope="module")
def disposable_database() -> Iterator[Engine]:
    server = _create_database()
    engine = sa.create_engine(
        make_url(_server_url())
        .set(database=DATABASE_NAME)
        .render_as_string(hide_password=False),
        poolclass=NullPool,
    )
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{RESOLVED_SCHEMA}"'))
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(
                text(f'DROP SCHEMA IF EXISTS "{RESOLVED_SCHEMA}" CASCADE')
            )
        engine.dispose()
        with server.connect() as connection:
            connection.execute(
                text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
        server.dispose()


def _digest(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _atoms(node: ProgramNode) -> tuple[Atom, ...]:
    if isinstance(node, Atom):
        return (node,)
    if isinstance(node, Then):
        return _atoms(node.first) + _atoms(node.second)
    return ()


def _runtime_scope() -> RuntimeScope:
    return RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key=PROJECT_KEY,
            resolved_schema=RESOLVED_SCHEMA,
            project_registry_revision=1,
            incarnation=PROJECT_INCARNATION,
            scope_digest=PROJECT_SCOPE_DIGEST,
        ),
        actor_id="human:c8-delivery",
    )


def _initialize_runtime_database(engine: Engine) -> tuple[object, RuntimeScope]:
    metadata = sa.MetaData()
    tables = project_tables(metadata, RESOLVED_SCHEMA)
    scope = _runtime_scope()
    with engine.begin() as connection:
        PUBLIC_METADATA.create_all(connection, checkfirst=False)
        metadata.create_all(connection, checkfirst=False)
        connection.execute(
            sa.insert(PUBLIC_TABLES["project_scope_registry"]).values(
                project_key=PROJECT_KEY,
                registry_revision=1,
                resolved_schema=RESOLVED_SCHEMA,
                scope_digest=PROJECT_SCOPE_DIGEST,
                incarnation=PROJECT_INCARNATION,
                state="ACTIVE",
                updated_by=scope.actor_id,
                approval_ref="approval:c8:scope",
            )
        )
        owners = OwnerBindingRepository(connection, tables)
        for object_type, mode, owner in (
            (
                "ResearchArtifact.v1",
                "CANONICAL_OWNED",
                "ResearchLedger_plus_project_artifact_store",
            ),
            ("DeliveryIntent.v1", "CANONICAL_OWNED", "ResearchLedger"),
            (
                "DeliveryReceiptRef.v1",
                "IMMUTABLE_EXTERNAL_REF",
                "project_receipt_store",
            ),
        ):
            owners.put_exact(
                scope,
                OwnerBindingRecord(
                    object_type=object_type,
                    owner_mode=mode,
                    owner_id=owner,
                    owner_epoch=1,
                    readback_profile_ref="c8-delivery-readback-v1",
                    base_incarnation=PROJECT_INCARNATION,
                    rollback_evidence_ref="rollback:c8-local-test",
                    effective_at=NOW,
                    approval_ref="approval:c8-owner",
                ),
                expected_owner_epoch=0,
                expected_base_incarnation=PROJECT_INCARNATION,
            )
    return tables, scope


def _install_control_facts(
    connection: sa.Connection,
    scope: RuntimeScope,
    activation_catalog: FirstSpecimenActivationCatalog,
) -> None:
    DeploymentCatalogRepository(connection).put_exact(
        DeploymentCatalog(
            catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            catalog_version="1.0.0",
            catalog_ref="artifact:c8-delivery-deployment",
            node_profile_digest=NODE_PROFILE_DIGEST,
            security_profile_digest=SECURITY_PROFILE_DIGEST,
            resource_profile_digest=RESOURCE_PROFILE_DIGEST,
        )
    )
    RuntimeNodeRepository(connection).register(
        node_id="c8-delivery-node",
        node_profile_digest=NODE_PROFILE_DIGEST,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        runtime_protocol_version="1",
        started_at=NOW - timedelta(minutes=1),
    )
    capability_id = "report.c8.3.v1"
    operation_kinds = tuple(
        entry.interpreter_binding.operation_contract_digest
        for entry in activation_catalog.entries
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_capability_authority"]).values(
            project_key=PROJECT_KEY,
            capability_id=capability_id,
            mode="canary",
            authority_epoch=AUTHORITY_EPOCH,
            successor_claim_enabled=True,
            legacy_claim_enabled=False,
            allowlist_digest=_digest("c8-delivery-allowlist"),
            config_digest=DELIVERY_AUTHORITY_DIGEST,
            effective_at=NOW,
            updated_by=scope.actor_id,
            approval_ref="approval:c8-canary",
            rollback_target_ref="canonical:legacy-read-only",
            revision=0,
        )
    )
    connection.execute(
        sa.insert(PUBLIC_TABLES["runtime_resource_policies"]).values(
            resource_policy_id="policy:report.c8.3.v1",
            project_key=PROJECT_KEY,
            capability_id=capability_id,
            resource_class=ResourceClass.CPU_LIGHT.value,
            concurrency_limit=1,
            max_project_active=1,
            max_capability_active=1,
            max_resource_active=1,
            units_ceiling=1,
            provider_limit=None,
            policy_epoch=RESOURCE_POLICY_EPOCH,
            policy_digest=RESOURCE_POLICY_DIGEST,
            revision=0,
        )
    )
    AuthorityGrantRepository(connection, scope).create(
        AuthorityGrant(
            grant_id="grant:c8-delivery",
            actor_id=scope.actor_id,
            capability_id=capability_id,
            operation_scope_json=AuthorityOperationScope.from_content(
                operation_kinds=tuple(
                    item
                    for item in (
                        C8_3_KIND,
                        C8_VERIFY_KIND,
                        C8_ADMISSION_KIND,
                        C8_DELIVERY_INTENT_PREPARE_KIND,
                        DELIVERY_INTERNAL_EXPORT_KIND,
                    )
                ),
                project_scope_digest=PROJECT_SCOPE_DIGEST,
            ),
            resource_ceiling_json=AuthorityResourceCeiling.from_content(
                limits=(
                    AuthorityResourceLimit(
                        resource_class=ResourceClass.CPU_LIGHT.value,
                        units=1,
                    ),
                ),
                max_active=1,
            ),
            credential_ref=None,
            grant_epoch=1,
            expires_at=NOW + timedelta(days=1),
        )
    )
    assert len(operation_kinds) == 5


def _ref(
    *,
    program_id: str,
    project_key: str,
    suffix: str,
    object_type: ObjectType,
    codec_id: str,
) -> ValueRef:
    value_id = f"{program_id}:payload:{suffix}"
    storage_ref = f"project-value:{value_id}"
    return ValueRef(
        value_id=value_id,
        project_key=project_key,
        object_type=object_type,
        codec_id=codec_id,
        content_digest=_digest(storage_ref),
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=storage_ref,
        byte_size=1,
        provenance_digest=_digest(f"provenance:{storage_ref}"),
    )


def _runtime_program():
    first = build_first_specimen_bundle()
    delivery_op = first.operation_by_kind(DELIVERY_INTERNAL_EXPORT_KIND)
    delivery_codec = first.codec_by_kind(DELIVERY_INTERNAL_EXPORT_KIND)
    bundle = build_c8_delivery_bridge_bundle(delivery_op, delivery_codec)
    catalog = build_c8_catalog(bundle)
    stage_payload = c8p.C8ReportStageInput(
        project_key=PROJECT_KEY,
        report_id="report:c8-runtime",
        topic="runtime delivery",
        source_keys=("knowledge:c8-runtime",),
    )
    program_id = "program:c8-runtime"
    program = normalize_program(
        build_c8_delivery_bridge_program(
            delivery_operation=delivery_op,
            delivery_codec=delivery_codec,
            delivery_payload_ref=_ref(
                program_id=program_id,
                project_key=PROJECT_KEY,
                suffix="internal-export-input",
                object_type=ObjectType("InternalExportInput.v1"),
                codec_id=delivery_codec.codec_id,
            ),
            artifact_input_ref=_ref(
                program_id=program_id,
                project_key=PROJECT_KEY,
                suffix="research-artifact",
                object_type=C8_RESEARCH_ARTIFACT_TYPE,
                codec_id=CANONICAL_CODEC_ID,
            ),
            intent_input_ref=_ref(
                program_id=program_id,
                project_key=PROJECT_KEY,
                suffix="delivery-intent",
                object_type=C8_DELIVERY_INTENT_TYPE,
                codec_id=CANONICAL_CODEC_ID,
            ),
            stage_payload=stage_payload,
            catalog=catalog,
            program_id=program_id,
            project_key=PROJECT_KEY,
            project_registry_revision=1,
            project_scope_digest=PROJECT_SCOPE_DIGEST,
        )
    )
    plan = compile_c8_delivery_bridge_program(
        program,
        catalog,
        operation_contracts=OperationContractRegistry(catalog, bundle.operations),
    )
    eligibility = QueueEligibility(
        project_key=PROJECT_KEY,
        capability_id="report.c8.3.v1",
        resource_class=ResourceClass.CPU_LIGHT,
        units=1,
        policy_epoch=RESOURCE_POLICY_EPOCH,
        policy_digest=RESOURCE_POLICY_DIGEST,
        concurrency_key="report.c8.3.v1",
    )
    activation = build_c8_delivery_activation_catalog(
        plan,
        interpreter_profile_digest=bundle.profiles["C8.3"][
            "interpreter"
        ].profile_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
        authority_requirement_digest=DELIVERY_AUTHORITY_DIGEST,
        resource_policy_digest=RESOURCE_POLICY_DIGEST,
        required_node_profile_selector=NODE_PROFILE_DIGEST,
        fairness_key=PROJECT_KEY,
        queue_eligibility=eligibility,
    )
    return delivery_op, bundle, catalog, stage_payload, program, plan, activation


def _bootstrap_runtime(
    engine: Engine,
    tables: object,
    scope: RuntimeScope,
    *,
    catalog: object,
    stage_payload: c8p.C8ReportStageInput,
    program: object,
    plan: object,
    activation: FirstSpecimenActivationCatalog,
) -> None:
    run_id = "run:c8-runtime"
    run_incarnation = "run-inc:c8-runtime"
    compiler = CompilerBinding.from_content(
        compiler_id="mrw.c8.delivery.compiler",
        compiler_version="1.0.0",
        compiler_digest=_digest("c8-delivery-compiler"),
        operation_catalog_digest=catalog.catalog_digest,
        domain_contract_snapshot_digest=_digest("c8-domain-snapshot"),
    )
    compile_assignment = RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id=f"{run_id}:compile",
        assignment_kind=AssignmentKind.COMPILE,
        project_key=PROJECT_KEY,
        run_id=run_id,
        capability_id="mrw.c8.compile",
        handler_binding_kind=HandlerBindingKind.COMPILER,
        handler_binding_ref=f"handler-binding:sha256:{compiler.binding_digest}",
        handler_binding_digest=compiler.binding_digest,
        handler_binding=compiler,
        program_digest=program.program_digest,
        deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
        execution_epoch=0,
        incarnation=run_incarnation,
        input_refs=(),
        input_closure_digest=content_digest(()),
        queue_eligibility_digest=_digest("c8-compile-eligibility"),
        resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        claim_authority_epoch=AUTHORITY_EPOCH,
        claim_policy_digest=CLAIM_POLICY_DIGEST,
        trace_id="trace:c8:compile",
    )
    atoms = {item.operation.operation_id: item for item in _atoms(program.root)}
    stage_ref = atoms["c8.report.stage"].operation.payload_ref
    stage_exact = canonical_json(dataclasses.asdict(stage_payload)).encode("utf-8")
    assert hashlib.sha256(stage_exact).hexdigest() == stage_ref.content_digest
    stage_provenance = {
        "schema": "mrw.successor.c8.c8-3.payload-provenance.v1",
        "program_id": program.program_id,
        "project_key": PROJECT_KEY,
        "semantic_payload_digest": stage_payload.payload_digest,
        "artifact_content_digest": stage_ref.content_digest,
    }
    assert content_digest(stage_provenance) == stage_ref.provenance_digest
    with engine.begin() as connection:
        _install_control_facts(connection, scope, activation)
        ProgramRepository(connection, tables).put_exact(
            scope, program, program.program_digest
        )
        ValueRepository(connection, tables).put_exact(
            scope,
            value_id=stage_ref.value_id,
            object_type=stage_ref.object_type.type_id,
            codec_id=stage_ref.codec_id,
            content=stage_exact,
            expected_digest=stage_ref.content_digest,
            provenance_digest=stage_ref.provenance_digest,
            expected_revision=0,
            expected_incarnation="c8-stage-payload-inc-1",
            provenance=stage_provenance,
        )
        lifecycle = RuntimeLifecycleRepository(connection, scope)
        lifecycle.submit(
            SubmitRun(
                run_id=run_id,
                incarnation=run_incarnation,
                program_id=program.program_id,
                program_digest=program.program_digest,
                program_storage_ref=f"project-value:program:{program.program_id}",
                contract_version=program.contract_version,
                submission_authority_digest=_digest("c8-submission-authority"),
                compile_work=AssignmentEnvelope(
                    assignment=compile_assignment,
                    required_node_profile_selector=NODE_PROFILE_DIGEST,
                    authority_digest=_digest("c8-submission-authority"),
                    resource_policy_digest=RESOURCE_POLICY_DIGEST,
                    fairness_key=PROJECT_KEY,
                ),
                due_at=NOW,
            )
        )
        RuntimeJournalRepository(connection, scope).append_transition(
            run_id=run_id,
            expected_revision=0,
            snapshot_values={"state": "COMPILING"},
            events=(
                {
                    "event_type": "CompileSucceeded",
                    "schema_version": "mrw.runtime.event.compile-succeeded.v1",
                    "event_metadata_json": {"plan_digest": plan.plan_digest},
                    "authority_digest": _digest("c8-submission-authority"),
                },
            ),
        )
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_work_items"])
            .where(
                PUBLIC_TABLES["runtime_work_items"].c.work_item_id
                == compile_assignment.work_item_id
            )
            .values(state="COMPLETED", revision=1)
        )
        PlanRepository(connection, tables).put_exact(
            scope,
            plan,
            plan.plan_digest,
            operation_catalog_id=catalog.catalog_id,
            catalog_version=catalog.catalog_version,
            catalog_digest=catalog.catalog_digest,
        )
        context = PostgresAuthorityProvider(connection, scope).current_context(
            scope.actor_id,
            capability_id="report.c8.3.v1",
            canonical_base_revision=0,
            canonical_incarnation="c8-artifact-inc-1",
            now=NOW,
        )
        authorizations = []
        for step in plan.ordered_steps:
            if step.step_kind not in {"EFFECT", "ADMISSION"}:
                continue
            assert step.operation_contract_ref is not None
            atom = atoms[step.operation_id]
            kind = step.operation_contract_ref.kind
            if kind == DELIVERY_INTERNAL_EXPORT_KIND and step.step_kind == "EFFECT":
                base_revision = 1
                incarnation = "c8-artifact-inc-1"
            elif kind == DELIVERY_INTERNAL_EXPORT_KIND:
                base_revision = 0
                incarnation = "c8-delivery-receipt-inc-1"
            elif kind == C8_ADMISSION_KIND:
                base_revision = 0
                incarnation = "c8-artifact-inc-1"
            else:
                base_revision = 0
                incarnation = f"c8:{kind}:inc-1"
            entry = activation.entry_for(step.operation_contract_ref.contract_digest)
            authorizations.append(
                StepAuthorizationBinding.from_content(
                    run_id=run_id,
                    step_id=step.step_id,
                    operation_kind=kind,
                    operation_contract_digest=step.operation_contract_ref.contract_digest,
                    capability_id="report.c8.3.v1",
                    claim_owner="successor",
                    claim_authority_epoch=AUTHORITY_EPOCH,
                    claim_policy_digest=CLAIM_POLICY_DIGEST,
                    payload_digest=atom.operation.payload_ref.content_digest,
                    actor_id=scope.actor_id,
                    project_key=PROJECT_KEY,
                    project_registry_revision=1,
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
                        ("approval:c8-delivery",)
                        if kind == DELIVERY_INTERNAL_EXPORT_KIND
                        else ()
                    ),
                    canonical_base_revision=base_revision,
                    canonical_incarnation=incarnation,
                )
            )
        qualified = QualifiedPlan.from_content(
            plan_digest=plan.plan_digest,
            authority_context_digest=context.context_digest,
            step_bindings=tuple(authorizations),
        )
        exact = ExactQualificationBinding.from_content(
            qualification_id="qualification:c8-runtime",
            project_key=PROJECT_KEY,
            run_id=run_id,
            plan_id=plan.plan_id,
            plan_digest=plan.plan_digest,
            authority_context=context,
            authority_context_digest=context.context_digest,
            qualified_plan=qualified,
            decision="QUALIFIED",
        )
        qualification_handler = QualificationBinding.from_content(
            authority_reader_id="c8-authority-reader",
            authority_reader_version="1.0.0",
            authority_reader_digest=_digest("c8-authority-reader"),
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            resource_policy_epoch=RESOURCE_POLICY_EPOCH,
        )
        qualify_assignment = RuntimeAssignment(
            runtime_protocol_version="1",
            work_item_id=f"{run_id}:qualify",
            assignment_kind=AssignmentKind.QUALIFY,
            project_key=PROJECT_KEY,
            run_id=run_id,
            capability_id="mrw.c8.qualify",
            handler_binding_kind="QUALIFICATION",
            handler_binding_ref=(
                f"handler-binding:sha256:{qualification_handler.binding_digest}"
            ),
            handler_binding_digest=qualification_handler.binding_digest,
            handler_binding=qualification_handler,
            program_digest=program.program_digest,
            plan_digest=plan.plan_digest,
            deployment_catalog_digest=DEPLOYMENT_CATALOG_DIGEST,
            execution_epoch=0,
            incarnation=run_incarnation,
            queue_eligibility_digest=_digest("c8-qualify-eligibility"),
            resource_policy_epoch=RESOURCE_POLICY_EPOCH,
            claim_authority_epoch=AUTHORITY_EPOCH,
            claim_policy_digest=CLAIM_POLICY_DIGEST,
            trace_id="trace:c8:qualify",
        )
        lifecycle.attach_plan(
            AttachPlan(
                run_id=run_id,
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
                    authority_digest=context.context_digest,
                    resource_policy_digest=RESOURCE_POLICY_DIGEST,
                    fairness_key=PROJECT_KEY,
                ),
                due_at=NOW,
            )
        )
        persist_qualification_step_shells(
            connection,
            scope,
            run_id=run_id,
            plan=plan,
            catalog=activation,
            authorizations=exact.qualified_plan.step_bindings,
            observed_at=NOW,
        )
        QualificationStoreRepository(connection, scope).persist(exact)
        lifecycle.activate_qualification(
            ActivateQualification(
                run_id=run_id,
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


class _Clock:
    def __init__(self) -> None:
        self.current = NOW + timedelta(minutes=1)

    def now(self) -> datetime:
        observed = self.current
        self.current += timedelta(milliseconds=10)
        return observed


class _CountingBlobStore(ProjectBlobStore):
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
            "injected C8 crash after export before PostgreSQL receipt"
        )


def _stage_runtime_draft(engine: Engine, scope: RuntimeScope, plan: object) -> None:
    source_digest = _digest("c8-source")
    handle_id = "handle:c8-source"
    fields_digest = _digest("c8-fields")
    citation = c8.CitationRef(
        citation_id="citation:c8-source",
        source_identity="source:c8",
        source_digest=source_digest,
        position=1,
        source_revision=1,
        source_incarnation="source-inc-1",
        handle_id=handle_id,
        fields_digest=fields_digest,
    )
    draft = c8.ResearchDraftArtifact(
        artifact_id="report:c8-runtime",
        project_key=PROJECT_KEY,
        markdown_bytes=b"# C8 runtime delivery\n\nExact internal export.\n",
        base_revision=0,
        base_incarnation="draft-base-inc-1",
        provenance_closure=(
            c8.ProvenanceClosureEntry(
                identity="source:c8",
                digest=source_digest,
                revision=1,
                incarnation="source-inc-1",
                handle_id=handle_id,
                fields_digest=fields_digest,
            ),
        ),
        citation_closure=c8.CitationClosure((citation,)),
        declared_legacy_metadata_loss=(),
    )
    draft = dataclasses.replace(
        draft,
        artifact_digest=c8.research_draft_artifact_digest(draft),
    )
    stage_step = next(
        step
        for step in plan.ordered_steps
        if step.step_kind == "EFFECT"
        and step.operation_contract_ref is not None
        and step.operation_contract_ref.kind == C8_3_KIND
    )
    with engine.begin() as connection:
        stage_artifact(
            connection,
            scope=scope,
            artifact=draft,
            run_id="run:c8-runtime",
            step_id=stage_step.step_id,
            qualifier_ref="qualifier:c8-runtime-draft",
        )


def test_delivery_bridge_program_and_catalog_bind_exact_shared_contract(
    disposable_database: Engine,
    tmp_path: Path,
) -> None:
    first = build_first_specimen_bundle()
    delivery_op = first.operation_by_kind(DELIVERY_INTERNAL_EXPORT_KIND)
    delivery_codec = first.codec_by_kind(DELIVERY_INTERNAL_EXPORT_KIND)
    bundle = build_c8_delivery_bridge_bundle(delivery_op, delivery_codec)
    catalog = build_c8_catalog(bundle)
    stage_payload = c8p.C8ReportStageInput(
        project_key=PROJECT_KEY,
        report_id="report:c8-delivery",
        topic="robotics",
        source_keys=("knowledge:1",),
    )
    program = build_c8_delivery_bridge_program(
        delivery_operation=delivery_op,
        delivery_codec=delivery_codec,
        delivery_payload_ref=_ref(
            program_id="program:c8-delivery",
            project_key=PROJECT_KEY,
            suffix="internal-export-input",
            object_type=ObjectType("InternalExportInput.v1"),
            codec_id=delivery_codec.codec_id,
        ),
        artifact_input_ref=_ref(
            program_id="program:c8-delivery",
            project_key=PROJECT_KEY,
            suffix="research-artifact",
            object_type=C8_RESEARCH_ARTIFACT_TYPE,
            codec_id=CANONICAL_CODEC_ID,
        ),
        intent_input_ref=_ref(
            program_id="program:c8-delivery",
            project_key=PROJECT_KEY,
            suffix="delivery-intent",
            object_type=C8_DELIVERY_INTENT_TYPE,
            codec_id=CANONICAL_CODEC_ID,
        ),
        stage_payload=stage_payload,
        catalog=catalog,
        program_id="program:c8-delivery",
        project_key=PROJECT_KEY,
        project_registry_revision=1,
        project_scope_digest="0" * 64,
    )
    plan = compile_c8_delivery_bridge_program(
        program,
        catalog,
        operation_contracts=c8p.build_c8_registry(bundle),
    )
    kinds = tuple(
        step.operation_contract_ref.kind
        for step in plan.ordered_steps
        if step.operation_contract_ref is not None
    )
    assert DELIVERY_INTERNAL_EXPORT_KIND in kinds
    assert len(set(kinds)) == 5
    profile_digest = bundle.profiles["C8.3"]["interpreter"].profile_digest
    eligibility = QueueEligibility(
        project_key=PROJECT_KEY,
        capability_id="report.c8.3.v1",
        resource_class=ResourceClass.CPU_LIGHT,
        units=1,
        policy_epoch=1,
        policy_digest=RESOURCE_POLICY_DIGEST,
    )
    activation_catalog = build_c8_delivery_activation_catalog(
        plan,
        interpreter_profile_digest=profile_digest,
        deployment_catalog_digest=_digest("deployment-c8-delivery"),
        project_scope_digest="0" * 64,
        authority_requirement_digest=_digest("authority-c8-delivery"),
        resource_policy_digest=RESOURCE_POLICY_DIGEST,
        required_node_profile_selector="node-profile:c8",
        fairness_key=PROJECT_KEY,
        queue_eligibility=eligibility,
    )
    assert len(activation_catalog.entries) == 5
    delivery_entry = activation_catalog.entry_for(delivery_op.ref.contract_digest)
    assert delivery_entry.external_gate_required is True
    assert delivery_entry.interpreter_binding.operation_contract_digest == (
        delivery_op.ref.contract_digest
    )
    for entry in activation_catalog.entries:
        assert entry.recovery_binding.interpreter_profile_digest == (
            entry.interpreter_binding.interpreter_profile_digest
        )
    assert program.input_type == C8_3_INPUT_TYPE
    assembly = build_postgres_c8_delivery_assembly(
        engine=disposable_database,
        bundle=bundle,
        activation_catalog=activation_catalog,
        delivery_interpreter=InternalExportInterpreter(
            operation_contract_ref=delivery_op.ref,
            blob_store=ProjectBlobStore(tmp_path / "c8-internal-export"),
        ),
    )
    assert len(assembly.handlers) == 5
    assert len(assembly.recovery_handlers) == 5
    assert {handler.operation_contract_digest for handler in assembly.handlers} == {
        entry.operation_contract_digest for entry in activation_catalog.entries
    }


def test_c8_delivery_bridge_runs_through_gate_runtime_node_and_receipt_readback(
    disposable_database: Engine,
    tmp_path: Path,
) -> None:
    tables, scope = _initialize_runtime_database(disposable_database)
    (
        delivery_op,
        bundle,
        catalog,
        stage_payload,
        program,
        plan,
        activation,
    ) = _runtime_program()
    _bootstrap_runtime(
        disposable_database,
        tables,
        scope,
        catalog=catalog,
        stage_payload=stage_payload,
        program=program,
        plan=plan,
        activation=activation,
    )
    _stage_runtime_draft(disposable_database, scope, plan)
    blob_store = _CountingBlobStore(tmp_path / "c8-runtime-export")
    assembly = build_postgres_c8_delivery_assembly(
        engine=disposable_database,
        bundle=bundle,
        activation_catalog=activation,
        delivery_interpreter=_CrashAfterExportInterpreter(
            operation_contract_ref=delivery_op.ref,
            blob_store=blob_store,
        ),
    )
    assembly.activate_initial(
        scope=scope,
        run_id="run:c8-runtime",
        observed_at=NOW + timedelta(minutes=1),
    )
    profile_digests = frozenset(
        entry.interpreter_binding.interpreter_profile_digest
        for entry in activation.entries
    )
    clock = _Clock()
    node = assembly.compose_node(
        identity=NodeIdentity(
            node_id="c8-delivery-node",
            incarnation="c8-delivery-node-inc-1",
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
            system_actor_id="c8-delivery-node",
            permission=RUNTIME_CROSS_PROJECT_CLAIM_PERMISSION,
            authority_epoch=AUTHORITY_EPOCH,
        ),
        clock=clock,
    )
    idle = 0
    for _ in range(40):
        report = node.run_once()
        if report.claimed:
            idle = 0
            assert report.results[0].committed
            assert report.results[0].disposition.value == "SUCCEEDED"
        else:
            idle += 1
            if idle == 3:
                break
    with disposable_database.connect() as connection:
        artifact = (
            connection.execute(
                sa.select(tables.research_objects).where(
                    tables.research_objects.c.object_type == "ResearchArtifact.v1"
                )
            )
            .mappings()
            .one_or_none()
        )
        if artifact is None:
            steps = connection.execute(
                sa.select(
                    PUBLIC_TABLES["runtime_steps"].c.operation_kind,
                    PUBLIC_TABLES["runtime_steps"].c.step_id,
                    PUBLIC_TABLES["runtime_steps"].c.state,
                    PUBLIC_TABLES["runtime_steps"].c.failure_digest,
                ).where(PUBLIC_TABLES["runtime_steps"].c.run_id == "run:c8-runtime")
            ).all()
            work = connection.execute(
                sa.select(
                    PUBLIC_TABLES["runtime_work_items"].c.assignment_kind,
                    PUBLIC_TABLES["runtime_work_items"].c.state,
                    PUBLIC_TABLES["runtime_work_items"].c.step_id,
                    PUBLIC_TABLES["runtime_work_items"].c.wait_reason,
                ).where(
                    PUBLIC_TABLES["runtime_work_items"].c.run_id == "run:c8-runtime"
                )
            ).all()
            pytest.fail(f"C8 ResearchArtifact absent; steps={steps}; work={work}")
        delivery_effect_step = next(
            step
            for step in plan.ordered_steps
            if step.step_kind == "EFFECT"
            and step.operation_contract_ref is not None
            and step.operation_contract_ref.kind == DELIVERY_INTERNAL_EXPORT_KIND
        )
        delivery_step = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_steps"]).where(
                    PUBLIC_TABLES["runtime_steps"].c.run_id == "run:c8-runtime",
                    PUBLIC_TABLES["runtime_steps"].c.step_id
                    == delivery_effect_step.step_id,
                    PUBLIC_TABLES["runtime_steps"].c.state == "PENDING",
                )
            )
            .mappings()
            .one()
        )
    template = DeliveryIntentTemplate(
        value_id="delivery-template:c8-runtime",
        delivery_intent_id="delivery-intent:c8-runtime",
        audience="internal-review",
        approval_ref="approval:c8-delivery",
        authority_digest=DELIVERY_AUTHORITY_DIGEST,
        idempotency_key="delivery:c8-runtime",
    )
    candidate = template.candidate(
        artifact_identity_ref(
            str(artifact["object_id"]),
            int(artifact["revision"]),
            str(artifact["content_digest"]),
        )
    )
    assert candidate.content_digest is not None
    gate_request = FirstSpecimenDeliveryGateRequest(
        scope=scope,
        run_id="run:c8-runtime",
        artifact_id=str(artifact["object_id"]),
        artifact_revision=int(artifact["revision"]),
        artifact_incarnation=str(artifact["incarnation"]),
        template=template,
        value_incarnation="c8-delivery-value-inc-1",
        intent_incarnation="c8-delivery-intent-inc-1",
        now=clock.now(),
        trace_id="trace:c8:delivery-gate",
    )
    with pytest.raises(RecordNotFound, match="approval"):
        assembly.admit_delivery(gate_request)
    with disposable_database.begin() as connection:
        ApprovalRepository(connection, scope).decide(
            ApprovalBinding(
                approval_id=template.approval_ref,
                actor_id=scope.actor_id,
                run_id="run:c8-runtime",
                step_id=str(delivery_step["step_id"]),
                payload_digest=candidate.content_digest,
                decision="APPROVED",
                expires_at=clock.now() + timedelta(hours=1),
                authority_digest=DELIVERY_AUTHORITY_DIGEST,
            )
        )
    first_gate = assembly.admit_delivery(gate_request)
    with pytest.raises(ExactBindingConflict, match="not awaiting its human gate"):
        assembly.admit_delivery(gate_request)
    assert first_gate.packet.assignment.assignment_digest
    idle = 0
    unknown_delivery_results = 0
    for _ in range(20):
        report = node.run_once()
        if report.claimed:
            idle = 0
            assert report.results[0].committed
            if report.results[0].disposition.value == "OUTCOME_UNKNOWN":
                unknown_delivery_results += 1
                continue
            assert report.results[0].disposition.value == "SUCCEEDED"
        else:
            idle += 1
            if idle == 3:
                break
    with disposable_database.begin() as connection:
        connection.execute(
            sa.update(PUBLIC_TABLES["runtime_capability_authority"])
            .where(
                PUBLIC_TABLES["runtime_capability_authority"].c.project_key
                == PROJECT_KEY,
                PUBLIC_TABLES["runtime_capability_authority"].c.capability_id
                == "report.c8.3.v1",
            )
            .values(
                successor_claim_enabled=False,
                legacy_claim_enabled=True,
                revision=1,
            )
        )
    with disposable_database.connect() as connection:
        receipt_count = connection.scalar(
            sa.select(sa.func.count()).select_from(tables.successor_receipts)
        )
        delivered_count = connection.scalar(
            sa.select(sa.func.count())
            .select_from(tables.research_relations)
            .where(tables.research_relations.c.relation_type == "delivered_as")
        )
        delivery_work_count = connection.scalar(
            sa.select(sa.func.count())
            .select_from(PUBLIC_TABLES["runtime_work_items"])
            .where(
                PUBLIC_TABLES["runtime_work_items"].c.run_id == "run:c8-runtime",
                PUBLIC_TABLES["runtime_work_items"].c.step_id
                == delivery_effect_step.step_id,
                PUBLIC_TABLES["runtime_work_items"].c.assignment_kind == "INTERPRET",
            )
        )
        run = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_runs"]).where(
                    PUBLIC_TABLES["runtime_runs"].c.run_id == "run:c8-runtime"
                )
            )
            .mappings()
            .one()
        )
    assert receipt_count == 1
    assert delivered_count == 1
    assert delivery_work_count == 1
    assert unknown_delivery_results == 1
    assert blob_store.store_calls == 1
    assert run["state"] == "COMPLETED"
