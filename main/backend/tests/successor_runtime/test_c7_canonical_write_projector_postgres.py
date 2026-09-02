"""Disposable PostgreSQL evidence for C7.2 canonical write and C7.3 driver.

The C7.2 canonical commit-write handler is installed through the real
``build_c7_assembly`` wiring path and executes ``admit_verified_candidate``
against a disposable PostgreSQL database.  The C7.3 projector driver persists
search/graph projection values in the successor project ``successor_values``
table and advances ``runtime_projection_offsets`` with an exact CAS.  All
writes stay inside successor-owned tables; the disposable database is dropped
on module teardown.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

from app.successor_runtime.assembly.c7_assembly import (
    C7_AUTHORITY_REQUIREMENT_DIGEST,
    C7_2CanonicalCommitWriteHandler,
    C7_3ProjectorDriverHandler,
    C7CanonicalWriteClosure,
    C7ProjectorDriverClosure,
    build_c7_assembly,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.ingest_c7_common import (
    C7_INGEST_OWNER,
    C7_OPERATION_CATALOG_ID,
    C7_OPERATION_CATALOG_VERSION,
    DOCUMENT_CANONICAL_OWNER,
)
from app.successor_runtime.capabilities.ingest_c7_movements import (
    DeterministicChunkPort,
    DeterministicExtractPort,
    DeterministicPassThroughPort,
    DeterministicSummarizePort,
    StructuredMaterialCandidate,
    VerifiedMaterialCandidate,
    capture_raw_snapshot_exact,
    execute_c7_movement,
    normalize_ingest_envelope,
    select_exactly_one_digestion_alternative,
    verify_structured_candidate,
)
from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    ReturnContract,
)
from app.successor_runtime.runtime.admission import VerificationBinding
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    ReturnContractBinding,
    RuntimeAssignment,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    InterpreterOutcome,
    NodeIdentity,
    RuntimeExecutionContext,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.postgres.c7_canonical_write import (
    PostgresC7CanonicalWritePort,
)
from app.successor_runtime.substrate.postgres.c7_projector_driver import (
    C7_GRAPH_PROJECTOR_ID,
    C7_SEARCH_PROJECTOR_ID,
    C7ProjectorDriver,
    C7ProjectorIntegrityError,
    projection_offset_key,
    verify_projection_value_readback,
)
from app.successor_runtime.substrate.postgres.commit_intents import (
    CommitIntentRepository,
    CommitIntentStatus,
)
from app.successor_runtime.substrate.postgres.ingest_c7_movement_admission import (
    C7_ADMISSION_REQUEST_EVENT_TYPE,
    C7_EVENT_SCHEMA_VERSION,
    C7_MOVEMENT_CANONICAL_DOCUMENTS,
    C7AdmissionConfig,
    C7AdmissionResult,
    C7CanonicalAbaError,
    C7RevokedAuthorityError,
    admit_verified_candidate,
    candidate_evidence_digest,
    candidate_provenance_digest,
    candidate_receipt_digest,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_TABLES,
    project_tables,
)
from app.successor_runtime.substrate.postgres.projection_offsets import (
    ProjectionOffsetRepository,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    StaleRevisionError,
)
from tests.successor_runtime.p4_c7_fixture import (
    ATTEMPT_ID,
    AUTHORITY_DIGEST,
    CANDIDATE_ID,
    PROGRAM_ID,
    PROJECT_KEY,
    REGISTRY_REVISION,
    RESOLVED_SCHEMA,
    SCOPE_DIGEST,
    SCOPE_INCARNATION,
    catalog,
    compiled_admission_step,
    program_and_plan,
)

pytestmark = pytest.mark.integration

DATABASE_NAME = "mrw_c7_canonical_write_projector_test"
ENV_URL = "SUCCESSOR_TEST_DATABASE_URL"
RUN_ID = "run:c7-canonical-write"
ACTOR_ID = "actor:p4-c7"
AUTHORITY_EPOCH = 7
IDEMPOTENCY_KEY = "idem:c7-canonical-write:001"
EXECUTION_EPOCH = 1
ATTEMPT_INCARNATION = "attempt-inc:c7-canonical-write"
ASSIGNMENT_DIGEST = content_digest({"assignment": "c7-canonical-write"})
HANDLER_BINDING_DIGEST = content_digest({"handler": "c7-canonical-write"})
EXPECTED_STEP_REVISION = 0
EXPECTED_ATTEMPT_REVISION = 0
NOW = datetime(2030, 8, 31, 8, 0, tzinfo=UTC)
_PROJECT_VALUE_TABLE = project_tables(sa.MetaData(), RESOLVED_SCHEMA).successor_values


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


def _drop_database(server: Engine) -> None:
    try:
        with server.connect() as connection:
            connection.execute(
                text("DROP DATABASE IF EXISTS " + DATABASE_NAME + " WITH (FORCE)")
            )
    finally:
        server.dispose()


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
        for table in PUBLIC_TABLES.values():
            table.create(connection)
        C7_MOVEMENT_CANONICAL_DOCUMENTS.create(connection)
        _PROJECT_VALUE_TABLE.create(connection)
    try:
        yield engine
    finally:
        engine.dispose()
        _drop_database(server)


@lru_cache(maxsize=1)
def _program_plan() -> tuple[Any, Any, Any]:
    program, plan, _ref, _payload_ref = program_and_plan()
    return program, plan, compiled_admission_step(plan)


STEP_ID = _program_plan()[2].step_id


def _scope(*, actor_id: str = ACTOR_ID) -> RuntimeScope:
    return RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key=PROJECT_KEY,
            resolved_schema=RESOLVED_SCHEMA,
            project_registry_revision=REGISTRY_REVISION,
            incarnation=SCOPE_INCARNATION,
            scope_digest=SCOPE_DIGEST,
        ),
        actor_id=actor_id,
    )


@lru_cache(maxsize=1)
def _base_pair() -> tuple[StructuredMaterialCandidate, VerifiedMaterialCandidate]:
    snapshot = capture_raw_snapshot_exact(
        project_key=PROJECT_KEY,
        source_locator="https://example.invalid/report",
        raw_bytes=b'{"title": " Q2 Market ", "text": " Market grew 12%  in Q2. "}',
        incarnation="raw-inc-c7-canonical-write",
        mime_type="application/json",
        provenance_refs=("ingest.c7.admission.v1",),
    )
    envelope = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format="structured_json",
    )
    decision = select_exactly_one_digestion_alternative(envelope)
    trace = execute_c7_movement(
        snapshot=snapshot,
        envelope=envelope,
        decision=decision,
        extract=DeterministicExtractPort(),
        chunk=DeterministicChunkPort(),
        summarize=DeterministicSummarizePort(),
        pass_through=DeterministicPassThroughPort(),
    )
    assert isinstance(trace.outcome, StructuredMaterialCandidate)
    verified = verify_structured_candidate(
        snapshot=snapshot,
        envelope=envelope,
        decision=decision,
        candidate=trace.outcome,
        expected_candidate_digest=trace.outcome.candidate_digest,
        expected_project_key=PROJECT_KEY,
        actor=ACTOR_ID,
        authority_digest=AUTHORITY_DIGEST,
        authority_epoch=AUTHORITY_EPOCH,
        canonical_base_revision=0,
        canonical_base_incarnation=SCOPE_INCARNATION,
        canonical_object_id=CANDIDATE_ID,
    )
    assert isinstance(verified, VerifiedMaterialCandidate)
    return trace.outcome, verified


def _base_verified() -> VerifiedMaterialCandidate:
    return _base_pair()[1]


def _base_structured() -> StructuredMaterialCandidate:
    return _base_pair()[0]


def _ordered_event_payloads(
    verified: VerifiedMaterialCandidate,
    config: C7AdmissionConfig,
) -> tuple[dict[str, object], ...]:
    return (
        {
            "seq": 1,
            "event_type": "raw_snapshot_captured",
            "schema_version": C7_EVENT_SCHEMA_VERSION,
            "step_id": STEP_ID,
            "attempt_id": ATTEMPT_ID,
            "event_metadata_json": {
                "snapshot_ref": verified.snapshot_ref,
                "snapshot_identity_digest": verified.snapshot_identity_digest,
                "raw_content_digest": verified.raw_content_digest,
            },
            "payload_ref": None,
            "payload_digest": None,
            "authority_digest": AUTHORITY_DIGEST,
        },
        {
            "seq": 2,
            "event_type": "envelope_normalized",
            "schema_version": C7_EVENT_SCHEMA_VERSION,
            "step_id": STEP_ID,
            "attempt_id": ATTEMPT_ID,
            "event_metadata_json": {
                "envelope_digest": verified.envelope_digest,
                "payload_content_digest": verified.payload_content_digest,
            },
            "payload_ref": None,
            "payload_digest": None,
            "authority_digest": AUTHORITY_DIGEST,
        },
        {
            "seq": 3,
            "event_type": "decision_selected",
            "schema_version": C7_EVENT_SCHEMA_VERSION,
            "step_id": STEP_ID,
            "attempt_id": ATTEMPT_ID,
            "event_metadata_json": {
                "decision_digest": verified.decision_digest,
            },
            "payload_ref": None,
            "payload_digest": None,
            "authority_digest": AUTHORITY_DIGEST,
        },
        {
            "seq": 4,
            "event_type": "candidate_verified",
            "schema_version": C7_EVENT_SCHEMA_VERSION,
            "step_id": STEP_ID,
            "attempt_id": ATTEMPT_ID,
            "event_metadata_json": {
                "candidate_digest": verified.candidate_digest,
                "verification_digest": verified.verification_digest,
                "provenance_closure_digest": verified.provenance_closure_digest,
            },
            "payload_ref": None,
            "payload_digest": None,
            "authority_digest": AUTHORITY_DIGEST,
        },
        {
            "seq": 5,
            "event_type": C7_ADMISSION_REQUEST_EVENT_TYPE,
            "schema_version": C7_EVENT_SCHEMA_VERSION,
            "step_id": STEP_ID,
            "attempt_id": ATTEMPT_ID,
            "event_metadata_json": {
                "commit_intent_id": config.commit_intent_id,
                "idempotency_key": config.idempotency_key,
                "canonical_commit_ref": config.canonical_commit_ref,
                "receipt_digest": config.receipt_digest,
                "run_id": config.run_id,
                "step_id": config.step_id,
                "attempt_id": config.attempt_id,
            },
            "payload_ref": None,
            "payload_digest": None,
            "authority_digest": AUTHORITY_DIGEST,
        },
    )


def _admission_binding(
    verified: VerifiedMaterialCandidate,
    *,
    config: C7AdmissionConfig | None = None,
    **overrides: Any,
) -> VerificationBinding:
    config = config or _config()
    program, plan, admission_step = _program_plan()
    values: dict[str, Any] = {
        "program_digest": program.program_digest,
        "plan_digest": plan.plan_digest,
        "step_id": admission_step.step_id,
        "attempt_id": ATTEMPT_ID,
        "input_closure_digest": verified.snapshot_identity_digest,
        "output_content_digest": verified.payload_content_digest,
        "ordered_event_payloads": _ordered_event_payloads(verified, config),
        "schema_digest": content_digest({"schema": "ingest.c7.admission.v1"}),
        "compiler_identity": plan.compiler_id,
        "interpreter_identity": "successor.ingest_index.c7.pure.v1",
        "verifier_identity": "ingest.validator.c7.v1",
        "actor_id": verified.actor,
        "project_key": verified.project_key,
        "authority_digest": verified.authority_digest,
        "project_registry_revision": REGISTRY_REVISION,
        "project_scope_digest": SCOPE_DIGEST,
        "resolved_schema": RESOLVED_SCHEMA,
        "canonical_owner": DOCUMENT_CANONICAL_OWNER,
        "canonical_object_id": verified.canonical_object_id,
        "canonical_base_revision": verified.expected_base_revision,
        "canonical_incarnation": verified.expected_base_incarnation,
        "evidence_digest": candidate_evidence_digest(verified),
        "receipt_digest": candidate_receipt_digest(verified),
        "provenance_digest": candidate_provenance_digest(verified),
        "qualifier": "staged-candidate",
    }
    values.update(overrides)
    return VerificationBinding.from_content(**values)


def _config(**overrides: Any) -> C7AdmissionConfig:
    _program, plan, _admission_step = _program_plan()
    values: dict[str, Any] = {
        "commit_intent_id": "commit:c7-canonical-write:001",
        "run_id": RUN_ID,
        "step_id": STEP_ID,
        "attempt_id": ATTEMPT_ID,
        "program_id": PROGRAM_ID,
        "plan_id": plan.plan_id,
        "capability_id": C7_INGEST_OWNER,
        "idempotency_key": IDEMPOTENCY_KEY,
        "execution_epoch": EXECUTION_EPOCH,
        "attempt_incarnation": ATTEMPT_INCARNATION,
        "assignment_digest": ASSIGNMENT_DIGEST,
        "handler_binding_digest": HANDLER_BINDING_DIGEST,
        "handler_realization_digest": HANDLER_BINDING_DIGEST,
        "expected_step_revision": EXPECTED_STEP_REVISION,
        "expected_attempt_revision": EXPECTED_ATTEMPT_REVISION,
        "canonical_commit_ref": "canonical:document:c7-canonical-write:1",
        "receipt_digest": content_digest({"receipt": "c7-canonical-write"}),
    }
    values.update(overrides)
    return C7AdmissionConfig(**values)  # type: ignore[arg-type]


def _seed_journal_events(
    connection: sa.Connection,
    verified: VerifiedMaterialCandidate,
    config: C7AdmissionConfig,
) -> None:
    for record in _ordered_event_payloads(verified, config):
        connection.execute(
            PUBLIC_TABLES["runtime_events"]
            .insert()
            .values(
                project_key=PROJECT_KEY,
                run_id=config.run_id,
                seq=record["seq"],
                event_type=record["event_type"],
                schema_version=record["schema_version"],
                step_id=record["step_id"],
                attempt_id=record["attempt_id"],
                event_metadata_json=record["event_metadata_json"],
                payload_ref=record["payload_ref"],
                payload_digest=record["payload_digest"],
                authority_digest=record["authority_digest"],
            )
        )


def _seed_base(connection: sa.Connection) -> None:
    program, plan, admission_step = _program_plan()
    verified = _base_verified()
    config = _config()
    connection.execute(
        PUBLIC_TABLES["project_scope_registry"]
        .insert()
        .values(
            project_key=PROJECT_KEY,
            registry_revision=REGISTRY_REVISION,
            resolved_schema=RESOLVED_SCHEMA,
            scope_digest=SCOPE_DIGEST,
            incarnation=SCOPE_INCARNATION,
            state="ACTIVE",
            updated_by="c7-canonical-write",
            approval_ref="approval:c7-canonical-write",
        )
    )
    connection.execute(
        PUBLIC_TABLES["runtime_program_refs"]
        .insert()
        .values(
            program_id=PROGRAM_ID,
            project_key=PROJECT_KEY,
            program_digest=program.program_digest,
            project_storage_ref="project-value:program:c7-canonical-write",
            contract_version="mrw.functorial-successor.program-spec.v1",
        )
    )
    connection.execute(
        PUBLIC_TABLES["runtime_plan_refs"]
        .insert()
        .values(
            plan_id=plan.plan_id,
            project_key=PROJECT_KEY,
            plan_digest=plan.plan_digest,
            program_id=PROGRAM_ID,
            program_digest=program.program_digest,
            project_storage_ref="project-value:plan:c7-canonical-write",
            compiler_id=plan.compiler_id,
            compiler_version=plan.compiler_version,
            operation_catalog_id=C7_OPERATION_CATALOG_ID,
            catalog_version=C7_OPERATION_CATALOG_VERSION,
            catalog_digest=catalog().catalog_digest,
            effect_closure_digest=plan.effect_closure_digest,
            authority_closure_digest=plan.authority_closure_digest,
            resource_closure_digest=plan.resource_closure_digest,
        )
    )
    connection.execute(
        PUBLIC_TABLES["runtime_runs"]
        .insert()
        .values(
            run_id=RUN_ID,
            project_key=PROJECT_KEY,
            project_registry_revision=REGISTRY_REVISION,
            project_scope_digest=SCOPE_DIGEST,
            resolved_schema=RESOLVED_SCHEMA,
            program_id=PROGRAM_ID,
            program_digest=program.program_digest,
            plan_id=plan.plan_id,
            plan_digest=plan.plan_digest,
            state="READY",
            revision=0,
            next_event_seq=len(_ordered_event_payloads(verified, config)) + 1,
            execution_epoch=EXECUTION_EPOCH,
            incarnation="run-inc:c7-canonical-write",
            submission_authority_digest=AUTHORITY_DIGEST,
            qualification_digest=AUTHORITY_DIGEST,
        )
    )
    _seed_journal_events(connection, verified, config)
    connection.execute(
        PUBLIC_TABLES["runtime_steps"]
        .insert()
        .values(
            project_key=PROJECT_KEY,
            run_id=RUN_ID,
            step_id=STEP_ID,
            operation_id="ingest_index.verify_admit",
            operation_kind="ingest_index.verify_admit.v1",
            operation_version="1.0.0",
            state="RUNNING",
            revision=EXPECTED_STEP_REVISION,
            execution_epoch=EXECUTION_EPOCH,
            input_digest=AUTHORITY_DIGEST,
            output_digest=AUTHORITY_DIGEST,
            effect_class="EFFECTFUL",
            resource_class="CPU_LIGHT",
            capability_id=C7_INGEST_OWNER,
            claim_owner="successor",
            claim_authority_epoch=AUTHORITY_EPOCH,
            claim_policy_digest=AUTHORITY_DIGEST,
        )
    )
    connection.execute(
        PUBLIC_TABLES["runtime_effect_attempts"]
        .insert()
        .values(
            attempt_id=ATTEMPT_ID,
            project_key=PROJECT_KEY,
            run_id=RUN_ID,
            step_id=STEP_ID,
            execution_epoch=EXECUTION_EPOCH,
            incarnation=ATTEMPT_INCARNATION,
            assignment_digest=ASSIGNMENT_DIGEST,
            handler_binding_digest=HANDLER_BINDING_DIGEST,
            handler_realization_digest=HANDLER_BINDING_DIGEST,
            idempotency_key=IDEMPOTENCY_KEY,
            authorization_digest=AUTHORITY_DIGEST,
            input_digest=verified.snapshot_identity_digest,
            claim_binding_json={"claim": "c7-canonical-write"},
            claim_binding_digest=AUTHORITY_DIGEST,
            disposition="IN_FLIGHT",
            revision=EXPECTED_ATTEMPT_REVISION,
        )
    )
    connection.execute(
        PUBLIC_TABLES["runtime_capability_authority"]
        .insert()
        .values(
            project_key=PROJECT_KEY,
            capability_id=C7_INGEST_OWNER,
            mode="on",
            authority_epoch=AUTHORITY_EPOCH,
            successor_claim_enabled=True,
            legacy_claim_enabled=False,
            allowlist_digest=AUTHORITY_DIGEST,
            config_digest=AUTHORITY_DIGEST,
            effective_at=NOW,
            updated_by="c7-canonical-write",
            approval_ref="approval:c7-canonical-write",
            rollback_target_ref="rollback:c7-canonical-write",
        )
    )
    assert admission_step.step_id


def _reset(engine: Engine) -> None:
    names = (
        "c7_movement_canonical_documents",
        "runtime_commit_intents",
        "runtime_events",
        "runtime_effect_attempts",
        "runtime_steps",
        "runtime_runs",
        "runtime_plan_refs",
        "runtime_program_refs",
        "project_scope_registry",
        "runtime_capability_authority",
        "runtime_projection_offsets",
    )
    qualified = ", ".join(f'"public"."{name}"' for name in names)
    qualified += f', "{RESOLVED_SCHEMA}"."successor_values"'
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {qualified} RESTART IDENTITY CASCADE"))
        _seed_base(connection)


@pytest.fixture(autouse=True)
def clean_database(disposable_database: Engine) -> Iterator[None]:
    _reset(disposable_database)
    yield


def _admit(
    connection: sa.Connection,
    verified: VerifiedMaterialCandidate,
    binding: VerificationBinding,
    *,
    config: C7AdmissionConfig | None = None,
    scope: RuntimeScope | None = None,
) -> C7AdmissionResult:
    config = config or _config()
    return admit_verified_candidate(
        connection,
        _base_structured(),
        verified,
        binding,
        _ordered_event_payloads(verified, config),
        config=config,
        scope=scope or _scope(),
    )


def _canonical_write_closure(engine: Engine) -> C7CanonicalWriteClosure:
    verified = _base_verified()
    config = _config()
    binding = _admission_binding(verified, config=config)
    return C7CanonicalWriteClosure(
        write_port=PostgresC7CanonicalWritePort(),
        connection_factory=engine.connect,
        structured_candidate=_base_structured(),
        verified_candidate=verified,
        binding=binding,
        ordered_event_payloads=_ordered_event_payloads(verified, config),
        config=config,
        scope=_scope(),
    )


def _canonical_write_handler(engine: Engine) -> C7_2CanonicalCommitWriteHandler:
    assembly = build_c7_assembly(
        project_scope_digest=SCOPE_DIGEST,
        canonical_write=_canonical_write_closure(engine),
    )
    handler = next(
        item
        for item in assembly.handlers
        if isinstance(item, C7_2CanonicalCommitWriteHandler)
    )
    assert assembly.cell("C7.2").status == "INSTALLED"
    return handler


def _interpreter_binding(handler: object) -> InterpreterBinding:
    binding = InterpreterBinding.from_content(
        operation_contract_digest=handler.operation_contract_digest,
        interpreter_profile_digest=handler.interpreter_profile_digest,
        deployment_catalog_digest=handler.deployment_catalog_digest,
        runtime_protocol_version="1",
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=1,
        authority_requirement_digest=C7_AUTHORITY_REQUIREMENT_DIGEST,
    )
    assert binding.binding_digest == handler.handler_binding_digest
    return binding


def _assignment_for(handler: object) -> RuntimeAssignment:
    binding = _interpreter_binding(handler)
    return RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work:c7-canonical-write:001",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key=PROJECT_KEY,
        run_id=RUN_ID,
        step_id=STEP_ID,
        step_role=CompiledStepRole.EFFECT,
        capability_id=C7_INGEST_OWNER,
        operation_contract_ref=OperationContractRef(
            kind="ingest_index.commit_intent.readback.v1",
            contract_version="1",
            contract_digest=handler.operation_contract_digest,
        ),
        operation_contract_digest=handler.operation_contract_digest,
        return_contract_binding=ReturnContractBinding.from_contract(
            "mrw.successor.c7.admission.v1",
            ReturnContract(
                success_modes=("SUCCEEDED",),
                failure_modes=("FAILED",),
                admission_required=True,
                wait_modes=("WAIT",),
                cancel_modes=("CANCELED",),
            ),
        ),
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
        handler_binding_digest=binding.binding_digest,
        handler_binding=binding,
        program_digest=binding.binding_digest,
        deployment_catalog_digest=handler.deployment_catalog_digest,
        execution_epoch=EXECUTION_EPOCH,
        incarnation="run-inc:c7-canonical-write",
        input_refs=(),
        input_closure_digest=binding.binding_digest,
        queue_eligibility_digest=("0" * 64),
        resource_policy_epoch=1,
        claim_authority_epoch=AUTHORITY_EPOCH,
        claim_policy_digest=("0" * 64),
        expected_step_revision=EXPECTED_STEP_REVISION,
        trace_id="trace:c7-canonical-write:001",
    )


def _claim_for(handler: object, assignment: RuntimeAssignment) -> ClaimBinding:
    return ClaimBinding.bind(
        assignment,
        authorization_digest=AUTHORITY_DIGEST,
        lease_token="lease:c7-canonical-write",
        lease_expires_at=NOW,
        node_id="node:c7-canonical-write",
        node_profile_digest=("0" * 64),
        authority_digest=AUTHORITY_DIGEST,
        interpreter_profile_digest=handler.interpreter_profile_digest,
    )


def _context() -> RuntimeExecutionContext:
    return RuntimeExecutionContext(
        node=NodeIdentity(
            node_id="node:c7-canonical-write",
            incarnation="node-inc:c7-canonical-write",
            started_at=NOW,
        ),
        observed_at=NOW,
    )


def _seed_canonical_head(
    connection: sa.Connection,
    verified: VerifiedMaterialCandidate,
    binding: VerificationBinding,
    config: C7AdmissionConfig,
    *,
    content_digest_value: str,
) -> None:
    from app.successor_runtime.runtime.assignments import canonical_digest
    from app.successor_runtime.substrate.postgres.ingest_c7_candidate_values import (
        candidate_value_id,
        candidate_value_incarnation,
        candidate_value_ref,
    )

    values: dict[str, object] = {
        "project_key": PROJECT_KEY,
        "object_id": verified.canonical_object_id,
        "commit_intent_id": config.commit_intent_id,
        "canonical_owner": DOCUMENT_CANONICAL_OWNER,
        "run_id": RUN_ID,
        "step_id": STEP_ID,
        "attempt_id": ATTEMPT_ID,
        "capability_id": C7_INGEST_OWNER,
        "actor_id": verified.actor,
        "program_digest": binding.program_digest,
        "plan_digest": binding.plan_digest,
        "step_revision": config.expected_step_revision,
        "attempt_revision": config.expected_attempt_revision,
        "execution_epoch": config.execution_epoch,
        "attempt_incarnation": config.attempt_incarnation,
        "assignment_digest": config.assignment_digest,
        "handler_binding_digest": config.handler_binding_digest,
        "handler_realization_digest": config.handler_realization_digest,
        "input_closure_digest": binding.input_closure_digest,
        "revision": 1,
        "incarnation": SCOPE_INCARNATION,
        "expected_base_revision": 0,
        "expected_base_incarnation": SCOPE_INCARNATION,
        "content_digest": content_digest_value,
        "snapshot_identity_digest": verified.snapshot_identity_digest,
        "raw_content_digest": verified.raw_content_digest,
        "envelope_digest": verified.envelope_digest,
        "payload_content_digest": content_digest_value,
        "ordered_source_closure_digest": verified.ordered_source_closure_digest,
        "provenance_closure_digest": verified.provenance_closure_digest,
        "decision_digest": verified.decision_digest,
        "candidate_digest": verified.candidate_digest,
        "candidate_verification_digest": verified.verification_digest,
        "ordered_event_closure_digest": binding.ordered_event_payload_closure_digest,
        "verification_digest": binding.binding_digest,
        "authority_digest": verified.authority_digest,
        "authority_epoch": verified.authority_epoch,
        "candidate_id": verified.candidate_id,
        "snapshot_ref": verified.snapshot_ref,
        "alternative": verified.alternative,
        "verification_profile_ref": verified.verification_profile_ref,
        "verification_receipt": verified.verification_receipt,
        "evidence_digest": binding.evidence_digest,
        "provenance_digest": binding.provenance_digest,
        "candidate_receipt_digest": binding.receipt_digest,
        "value_ref": candidate_value_ref(candidate_value_id(verified.candidate_id)),
        "value_revision": 1,
        "value_incarnation": candidate_value_incarnation(verified),
        "value_digest": verified.payload_content_digest,
        "value_provenance_digest": verified.provenance_closure_digest,
        "canonical_commit_ref": "canonical:document:c7-canonical-write:aba",
        "receipt_digest": content_digest({"receipt": "aba"}),
    }
    values["head_closure_digest"] = canonical_digest(
        {key: value for key, value in values.items() if key != "head_closure_digest"}
    )
    connection.execute(C7_MOVEMENT_CANONICAL_DOCUMENTS.insert().values(**values))


def test_c7_2_assembly_installs_canonical_write_handler(
    disposable_database: Engine,
) -> None:
    assembly = build_c7_assembly(
        project_scope_digest=SCOPE_DIGEST,
        canonical_write=_canonical_write_closure(disposable_database),
    )
    assert assembly.coverage()["C7.2"] == "INSTALLED"
    assert assembly.coverage()["C7.1"] == "UNWIRED_DECLARED"
    assert assembly.coverage()["C7.4"] == "UNWIRED_DECLARED"
    rollback = {item.cell_id: item for item in assembly.rollback_bindings}
    assert rollback["C7.2"].status == "PRESENT"
    assert rollback["C7.2"].binding_refs
    assert rollback["C7.1"].status == "DECLARED_GAP"
    assert rollback["C7.4"].status == "DECLARED_GAP"


def test_c7_2_handler_commits_and_reads_back(
    disposable_database: Engine,
) -> None:
    handler = _canonical_write_handler(disposable_database)
    assignment = _assignment_for(handler)
    claim = _claim_for(handler, assignment)
    outcome = handler.execute(assignment, claim, _context())

    assert isinstance(outcome, InterpreterOutcome)
    assert outcome.disposition is EffectDisposition.SUCCEEDED
    assert outcome.result_digest
    assert outcome.receipt_ref == "canonical:document:c7-canonical-write:1"

    with disposable_database.connect() as connection:
        head = (
            connection.execute(
                sa.select(C7_MOVEMENT_CANONICAL_DOCUMENTS).where(
                    C7_MOVEMENT_CANONICAL_DOCUMENTS.c.project_key == PROJECT_KEY,
                    C7_MOVEMENT_CANONICAL_DOCUMENTS.c.object_id == CANDIDATE_ID,
                )
            )
            .mappings()
            .one()
        )
        assert int(head["revision"]) == 1
        assert head["commit_intent_id"] == _config().commit_intent_id
        intent = CommitIntentRepository(connection, _scope()).find_for_readback(
            C7_INGEST_OWNER,
            IDEMPOTENCY_KEY,
        )
        assert intent["state"] == CommitIntentStatus.COMMITTED.value


def test_c7_2_exact_duplicate_returns_same_readback(
    disposable_database: Engine,
) -> None:
    handler = _canonical_write_handler(disposable_database)
    assignment = _assignment_for(handler)
    claim = _claim_for(handler, assignment)
    first = handler.execute(assignment, claim, _context())
    second = handler.execute(assignment, claim, _context())
    assert first == second
    with disposable_database.connect() as connection:
        head_count = int(
            connection.execute(
                sa.select(sa.func.count()).select_from(C7_MOVEMENT_CANONICAL_DOCUMENTS)
            ).scalar_one()
        )
        intent_count = int(
            connection.execute(
                sa.select(sa.func.count()).select_from(
                    PUBLIC_TABLES["runtime_commit_intents"]
                )
            ).scalar_one()
        )
    assert head_count == 1
    assert intent_count == 1


def test_c7_2_authority_epoch_drift_fails_closed(
    disposable_database: Engine,
) -> None:
    verified = _base_verified()
    binding = _admission_binding(verified)
    with disposable_database.begin() as connection:
        connection.execute(
            PUBLIC_TABLES["runtime_capability_authority"]
            .update()
            .where(
                PUBLIC_TABLES["runtime_capability_authority"].c.project_key
                == PROJECT_KEY,
                PUBLIC_TABLES["runtime_capability_authority"].c.capability_id
                == C7_INGEST_OWNER,
            )
            .values(authority_epoch=AUTHORITY_EPOCH + 1)
        )
        with pytest.raises(C7RevokedAuthorityError):
            _admit(connection, verified, binding)


def test_c7_2_aba_rejects_same_identity_different_bytes(
    disposable_database: Engine,
) -> None:
    verified = _base_verified()
    config = _config()
    binding = _admission_binding(verified, config=config)
    with disposable_database.begin() as connection:
        _seed_canonical_head(
            connection,
            verified,
            binding,
            config,
            content_digest_value=content_digest({"mutated": "aba"}),
        )
        with pytest.raises(C7CanonicalAbaError):
            _admit(connection, verified, binding, config=config)


def test_c7_3_assembly_registers_search_and_graph_projectors(
    disposable_database: Engine,
) -> None:
    closure = C7ProjectorDriverClosure(
        connection_factory=disposable_database.connect,
        scope=_scope(),
        object_id=CANDIDATE_ID,
        expected_source_incarnation=SCOPE_INCARNATION,
    )
    assembly = build_c7_assembly(
        project_scope_digest=SCOPE_DIGEST,
        projector_driver=closure,
    )
    assert assembly.coverage()["C7.3"] == "INSTALLED"
    assert assembly.coverage()["C7.1"] == "UNWIRED_DECLARED"
    assert assembly.coverage()["C7.4"] == "UNWIRED_DECLARED"
    assert assembly.projector_registry is not None
    registered = {
        (contract.key.projector_id, contract.projection_id)
        for contract in assembly.projector_registry.projectors
    }
    assert registered == {
        (C7_SEARCH_PROJECTOR_ID, "projection.c7-search.v1"),
        (C7_GRAPH_PROJECTOR_ID, "projection.c7-graph.v1"),
    }
    rollback = {item.cell_id: item for item in assembly.rollback_bindings}
    assert rollback["C7.3"].status == "PRESENT"
    assert rollback["C7.3"].binding_refs


def test_c7_3_driver_persists_offsets_and_rebuilds(
    disposable_database: Engine,
) -> None:
    verified = _base_verified()
    binding = _admission_binding(verified)
    with disposable_database.begin() as connection:
        result = _admit(connection, verified, binding)
        assert result.document_ref.revision == 1
        scope = _scope()
        driver = C7ProjectorDriver(connection, scope)
        search, graph = driver.rebuild_document(
            CANDIDATE_ID,
            mode="FULL",
            expected_source_incarnation=SCOPE_INCARNATION,
        )
        assert search.projection_kind == "search"
        assert graph.projection_kind == "graph"
        assert search.source_revision == 1
        assert graph.source_revision == 1
        assert search.source_digest == verified.payload_content_digest
        assert graph.source_digest == verified.payload_content_digest
        search_key = projection_offset_key("search", result.document_ref)
        graph_key = projection_offset_key("graph", result.document_ref)
        offsets = ProjectionOffsetRepository(connection, scope)
        search_offset = offsets.load_source(search_key)
        graph_offset = offsets.load_source(graph_key)
        assert search_offset is not None
        assert graph_offset is not None
        assert search_offset["offset_ref"] == search.value_ref
        assert graph_offset["offset_ref"] == graph.value_ref
        verify_projection_value_readback(
            connection,
            scope,
            value_ref=search.value_ref,
            projection_digest=search.projection_digest,
        )
        verify_projection_value_readback(
            connection,
            scope,
            value_ref=graph.value_ref,
            projection_digest=graph.projection_digest,
        )

        value_count = int(
            connection.execute(
                sa.select(sa.func.count()).select_from(_PROJECT_VALUE_TABLE)
            ).scalar_one()
        )
        search_again, graph_again = driver.rebuild_document(
            CANDIDATE_ID,
            mode="FULL",
            expected_source_incarnation=SCOPE_INCARNATION,
        )
        assert search_again.projection_digest == search.projection_digest
        assert search_again.offset_ref == search.offset_ref
        assert search_again.value_ref == search.value_ref
        assert search_again.source_revision == search.source_revision
        assert search_again.store_writes == 0
        assert graph_again.projection_digest == graph.projection_digest
        assert graph_again.offset_ref == graph.offset_ref
        assert graph_again.value_ref == graph.value_ref
        assert graph_again.source_revision == graph.source_revision
        assert graph_again.store_writes == 0
        assert (
            int(
                connection.execute(
                    sa.select(sa.func.count()).select_from(_PROJECT_VALUE_TABLE)
                ).scalar_one()
            )
            == value_count
        )

        connection.execute(
            C7_MOVEMENT_CANONICAL_DOCUMENTS.update()
            .where(
                C7_MOVEMENT_CANONICAL_DOCUMENTS.c.project_key == PROJECT_KEY,
                C7_MOVEMENT_CANONICAL_DOCUMENTS.c.object_id == CANDIDATE_ID,
            )
            .values(revision=2)
        )
        search_advanced, graph_advanced = driver.rebuild_document(
            CANDIDATE_ID,
            mode="INCREMENTAL",
            expected_source_incarnation=SCOPE_INCARNATION,
        )
        assert search_advanced.source_revision == 2
        assert graph_advanced.source_revision == 2
        assert search_advanced.offset_ref != search.value_ref
        assert graph_advanced.offset_ref != graph.value_ref

        tampered = offsets.load_source(search_key, for_update=True)
        assert tampered is not None
        original_revision = int(tampered["revision"])
        connection.execute(
            PUBLIC_TABLES["runtime_projection_offsets"]
            .update()
            .where(
                PUBLIC_TABLES["runtime_projection_offsets"].c.project_key
                == PROJECT_KEY,
                PUBLIC_TABLES["runtime_projection_offsets"].c.projection_offset_id
                == tampered["projection_offset_id"],
            )
            .values(revision=original_revision + 5)
        )
        with pytest.raises(StaleRevisionError):
            offsets.advance(
                tampered["projection_offset_id"],
                key=search_key,
                expected_revision=original_revision,
                expected_generation=int(tampered["projection_generation"]),
                expected_source_revision=int(tampered["source_revision"]),
                expected_source_digest=str(tampered["source_digest"]),
                source_revision=3,
                source_digest=search.source_digest,
                offset_ref="document-revision:3",
            )


def test_c7_3_driver_rejects_incarnation_drift(
    disposable_database: Engine,
) -> None:
    verified = _base_verified()
    binding = _admission_binding(verified)
    with disposable_database.begin() as connection:
        _admit(connection, verified, binding)
        connection.execute(
            C7_MOVEMENT_CANONICAL_DOCUMENTS.update()
            .where(
                C7_MOVEMENT_CANONICAL_DOCUMENTS.c.project_key == PROJECT_KEY,
                C7_MOVEMENT_CANONICAL_DOCUMENTS.c.object_id == CANDIDATE_ID,
            )
            .values(incarnation="scope-inc:drifted")
        )
        driver = C7ProjectorDriver(connection, _scope())
        with pytest.raises(C7ProjectorIntegrityError):
            driver.rebuild_document(
                CANDIDATE_ID,
                expected_source_incarnation=SCOPE_INCARNATION,
            )


def test_c7_3_handler_rejects_drifted_binding(
    disposable_database: Engine,
) -> None:
    closure = C7ProjectorDriverClosure(
        connection_factory=disposable_database.connect,
        scope=_scope(),
        object_id=CANDIDATE_ID,
        expected_source_incarnation=SCOPE_INCARNATION,
    )
    assembly = build_c7_assembly(
        project_scope_digest=SCOPE_DIGEST,
        projector_driver=closure,
    )
    handler = next(
        item
        for item in assembly.handlers
        if isinstance(item, C7_3ProjectorDriverHandler)
    )
    assignment = _assignment_for(handler)
    claim = _claim_for(handler, assignment)
    drifted = replace(handler, handler_binding_digest="0" * 64)
    with pytest.raises(DefiniteInterpreterFailure):
        drifted.execute(assignment, claim, _context())
