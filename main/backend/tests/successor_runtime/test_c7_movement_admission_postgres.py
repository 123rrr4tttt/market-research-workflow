"""Disposable PostgreSQL evidence for C7 verified-candidate admission."""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from app.successor_migration.document_repository_c7 import (
    CanonicalCommitReadback,
    DocumentRef,
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
from app.successor_runtime.runtime.admission import VerificationBinding
from app.successor_runtime.runtime.assignments import canonical_digest
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres.commit_intents import (
    CommitIntentRepository,
    CommitIntentStatus,
)
from app.successor_runtime.substrate.postgres.ingest_c7_candidate_values import (
    C7_STRUCTURED_VALUE_CODEC_ID,
    C7_STRUCTURED_VALUE_OBJECT_TYPE,
    candidate_value_id,
    candidate_value_incarnation,
    candidate_value_ref,
)
from app.successor_runtime.substrate.postgres.ingest_c7_movement_admission import (
    C7_ADMISSION_REQUEST_EVENT_TYPE,
    C7_ADMISSION_SCHEMA_VERSION,
    C7_EVENT_SCHEMA_VERSION,
    C7_MOVEMENT_CANONICAL_DOCUMENTS,
    C7AdmissionConfig,
    C7AdmissionReceipt,
    C7AdmissionResult,
    C7CandidateRejectedError,
    C7CanonicalAbaError,
    C7CapabilityMismatchError,
    C7IdempotencyConflictError,
    C7NoSpeculativeRetryError,
    C7OutcomeUnknownError,
    C7ReadbackIntegrityError,
    C7RevokedAuthorityError,
    C7RuntimeBindingError,
    C7StaleCanonicalRevisionError,
    admit_verified_candidate,
    build_commit_binding,
    candidate_evidence_digest,
    candidate_provenance_digest,
    candidate_receipt_digest,
    load_authoritative_readback,
    readback_by_idempotency,
    require_locked_canonical_events,
    require_locked_runtime_step_attempt,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_TABLES,
    project_tables,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    RuntimeJournalRepository,
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

DATABASE_NAME = "mrw_c7_movement_admission_test"
ENV_URL = "SUCCESSOR_TEST_DATABASE_URL"
RUN_ID = "run:c7-target-admission"
ACTOR_ID = "actor:p4-c7"
AUTHORITY_EPOCH = 7
IDEMPOTENCY_KEY = "idem:c7-target-admission:001"
EXECUTION_EPOCH = 1
ATTEMPT_INCARNATION = "attempt-inc:c7-target-admission"
ASSIGNMENT_DIGEST = content_digest({"assignment": "c7-target-admission"})
HANDLER_BINDING_DIGEST = content_digest({"handler": "c7-target-admission"})
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


def _assert_database_absent(server: Engine) -> None:
    with server.connect() as connection:
        row = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
            {"database_name": DATABASE_NAME},
        ).scalar_one_or_none()
        assert row is None


def _assert_database_present(server: Engine) -> None:
    with server.connect() as connection:
        row = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
            {"database_name": DATABASE_NAME},
        ).scalar_one_or_none()
        assert row == 1


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
        _assert_database_present(server)
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
        _assert_database_absent(server)
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
        project_tables(sa.MetaData(), RESOLVED_SCHEMA).successor_values.create(
            connection
        )
    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(
                text(f'DROP SCHEMA IF EXISTS "{RESOLVED_SCHEMA}" CASCADE')
            )
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
        incarnation="raw-inc-c7-admission",
        mime_type="application/json",
        provenance_refs=("ingest.c7.admission.v1",),
    )
    envelope = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format="structured_json",
    )
    assert envelope.source_character_length == len(snapshot.raw_bytes.decode("utf-8"))
    decision = select_exactly_one_digestion_alternative(envelope)
    assert decision.source_character_length == envelope.source_character_length
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


def _pure_verified_candidate(**overrides: Any) -> VerifiedMaterialCandidate:
    verified = _base_verified()
    if not overrides:
        return verified
    return dataclasses.replace(verified, **overrides)


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
        "commit_intent_id": "commit:c7-target-admission:001",
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
        "canonical_commit_ref": "canonical:document:c7-target-admission:1",
        "receipt_digest": content_digest({"receipt": "c7-target-admission"}),
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
            updated_by="c7-target-admission",
            approval_ref="approval:c7-target-admission",
        )
    )
    connection.execute(
        PUBLIC_TABLES["runtime_program_refs"]
        .insert()
        .values(
            program_id=PROGRAM_ID,
            project_key=PROJECT_KEY,
            program_digest=program.program_digest,
            project_storage_ref="project-value:program:c7-target-admission",
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
            project_storage_ref="project-value:plan:c7-target-admission",
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
            incarnation="run-inc:c7-target-admission",
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
            claim_binding_json={"claim": "c7-target-admission"},
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
            updated_by="c7-target-admission",
            approval_ref="approval:c7-target-admission",
            rollback_target_ref="rollback:c7-target-admission",
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


def _seed_canonical_head(
    connection: sa.Connection,
    verified: VerifiedMaterialCandidate,
    binding: VerificationBinding,
    config: C7AdmissionConfig,
    *,
    revision: int,
    content_digest_value: str | None = None,
    incarnation: str | None = None,
) -> None:
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
        "revision": revision,
        "incarnation": incarnation or verified.expected_base_incarnation,
        "expected_base_revision": revision - 1,
        "expected_base_incarnation": verified.expected_base_incarnation,
        "content_digest": content_digest_value or verified.payload_content_digest,
        "snapshot_identity_digest": verified.snapshot_identity_digest,
        "raw_content_digest": verified.raw_content_digest,
        "envelope_digest": verified.envelope_digest,
        "payload_content_digest": content_digest_value
        or verified.payload_content_digest,
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
        "evidence_digest": candidate_evidence_digest(verified),
        "provenance_digest": candidate_provenance_digest(verified),
        "candidate_receipt_digest": candidate_receipt_digest(verified),
        "value_ref": candidate_value_ref(candidate_value_id(verified.candidate_id)),
        "value_revision": 1,
        "value_incarnation": candidate_value_incarnation(verified),
        "value_digest": verified.payload_content_digest,
        "value_provenance_digest": verified.provenance_closure_digest,
        "canonical_commit_ref": "canonical:document:c7-target-admission:seed",
        "receipt_digest": content_digest({"receipt": "seed"}),
    }
    values["head_closure_digest"] = canonical_digest(
        {key: value for key, value in values.items() if key != "head_closure_digest"}
    )
    connection.execute(C7_MOVEMENT_CANONICAL_DOCUMENTS.insert().values(**values))


def _seed_intent(
    connection: sa.Connection,
    verified: VerifiedMaterialCandidate,
    config: C7AdmissionConfig,
    binding: VerificationBinding,
    *,
    status: CommitIntentStatus | None = None,
) -> None:
    repo = CommitIntentRepository(connection, _scope())
    prepared = repo.prepare(
        build_commit_binding(verified, config=config, binding=binding)
    )
    if status is not None:
        repo.record_result(
            prepared["commit_intent_id"],
            expected_revision=0,
            status=status,
        )


def _count_canonical_heads(connection: sa.Connection) -> int:
    return int(
        connection.execute(
            sa.select(sa.func.count()).select_from(C7_MOVEMENT_CANONICAL_DOCUMENTS)
        ).scalar_one()
    )


def _count_commit_intents(connection: sa.Connection) -> int:
    return int(
        connection.execute(
            sa.select(sa.func.count()).select_from(
                PUBLIC_TABLES["runtime_commit_intents"]
            )
        ).scalar_one()
    )


def _value_table() -> sa.Table:
    return _PROJECT_VALUE_TABLE


def _count_values(connection: sa.Connection) -> int:
    return int(
        connection.execute(
            sa.select(sa.func.count()).select_from(_value_table())
        ).scalar_one()
    )


def _admit(
    connection: sa.Connection,
    verified: VerifiedMaterialCandidate,
    binding: VerificationBinding,
    *,
    config: C7AdmissionConfig | None = None,
    scope: RuntimeScope | None = None,
    ordered_event_payloads: tuple[dict[str, object], ...] | None = None,
    structured: StructuredMaterialCandidate | None = None,
) -> C7AdmissionResult:
    config = config or _config()
    events = ordered_event_payloads or _ordered_event_payloads(verified, config)
    return admit_verified_candidate(
        connection,
        structured or _base_structured(),
        verified,
        binding,
        events,
        config=config,
        scope=scope or _scope(),
    )


def test_actual_pure_candidate_commits_and_reads_back(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    with disposable_database.begin() as connection:
        result = _admit(connection, verified, binding, config=config)
        assert isinstance(result, C7AdmissionResult)
        assert isinstance(result.readback, CanonicalCommitReadback)
        assert isinstance(result.document_ref, DocumentRef)
        assert isinstance(result.receipt, C7AdmissionReceipt)
        assert result.readback.committed_revision == 1
        assert result.document_ref.revision == 1
        assert result.document_ref.object_id == CANDIDATE_ID
        assert result.document_ref.content_digest == verified.payload_content_digest
        assert result.document_ref.canonical_owner == DOCUMENT_CANONICAL_OWNER
        assert result.receipt.committed_revision == 1
        assert result.receipt.committed_incarnation == SCOPE_INCARNATION
        assert result.receipt.content_digest == verified.payload_content_digest
        assert result.receipt.decision_digest == verified.decision_digest
        assert result.receipt.candidate_digest == verified.candidate_digest
        assert result.receipt.verification_digest == binding.binding_digest
        assert result.receipt.authority_epoch == AUTHORITY_EPOCH
        assert result.receipt.readback_digest
        assert result.receipt.production_canonical_authority is False
        assert result.receipt.live_provider is False
        assert result.receipt.promotion is False
        assert result.receipt.disposable is True

        intent = CommitIntentRepository(connection, _scope()).find_for_readback(
            C7_INGEST_OWNER,
            config.idempotency_key,
        )
        assert intent["state"] == CommitIntentStatus.COMMITTED.value
        assert intent["content_digest"] == verified.payload_content_digest
        assert intent["verification_digest"] == binding.binding_digest
        assert intent["event_digest"] == binding.ordered_event_payload_closure_digest

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
        assert head["revision"] == 1
        assert head["incarnation"] == SCOPE_INCARNATION
        assert head["commit_intent_id"] == config.commit_intent_id
        assert head["attempt_id"] == ATTEMPT_ID
        assert head["capability_id"] == C7_INGEST_OWNER
        assert head["candidate_id"] == verified.candidate_id
        assert head["snapshot_ref"] == verified.snapshot_ref
        assert head["alternative"] == verified.alternative
        assert head["verification_profile_ref"] == verified.verification_profile_ref
        assert head["verification_receipt"] == verified.verification_receipt
        assert head["step_revision"] == EXPECTED_STEP_REVISION
        assert head["attempt_revision"] == EXPECTED_ATTEMPT_REVISION
        assert head["execution_epoch"] == EXECUTION_EPOCH
        assert head["attempt_incarnation"] == ATTEMPT_INCARNATION
        assert head["assignment_digest"] == ASSIGNMENT_DIGEST
        assert head["handler_binding_digest"] == HANDLER_BINDING_DIGEST
        assert head["handler_realization_digest"] == HANDLER_BINDING_DIGEST
        assert head["input_closure_digest"] == verified.snapshot_identity_digest
        assert head["evidence_digest"] == candidate_evidence_digest(verified)
        assert head["provenance_digest"] == candidate_provenance_digest(verified)
        assert head["candidate_receipt_digest"] == candidate_receipt_digest(verified)
        assert head["candidate_digest"] == verified.candidate_digest
        assert head["candidate_verification_digest"] == verified.verification_digest
        assert head["authority_epoch"] == AUTHORITY_EPOCH
        assert head["head_closure_digest"]


def test_exact_duplicate_returns_same_document_ref(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    with disposable_database.begin() as connection:
        first = _admit(connection, verified, binding)
        second = _admit(connection, verified, binding)
        assert first.readback == second.readback
        assert first.document_ref == second.document_ref
        assert first.receipt == second.receipt
        assert _count_canonical_heads(connection) == 1
        assert _count_commit_intents(connection) == 1


def test_candidate_value_written_exact(disposable_database: Engine) -> None:
    verified = _pure_verified_candidate()
    structured = _base_structured()
    binding = _admission_binding(verified)
    config = _config()
    with disposable_database.begin() as connection:
        _admit(connection, verified, binding, config=config)
        assert _count_values(connection) == 1
        row = (
            connection.execute(
                sa.select(_value_table()).where(
                    _value_table().c.project_key == PROJECT_KEY,
                    _value_table().c.value_id
                    == candidate_value_id(verified.candidate_id),
                )
            )
            .mappings()
            .one()
        )
        assert row["value_id"] == candidate_value_id(verified.candidate_id)
        assert row["object_type"] == C7_STRUCTURED_VALUE_OBJECT_TYPE
        assert row["codec_id"] == C7_STRUCTURED_VALUE_CODEC_ID
        assert int(row["revision"]) == 1
        assert row["incarnation"] == candidate_value_incarnation(verified)
        assert row["content_digest"] == verified.payload_content_digest
        assert dict(row["content_json"]) == dict(structured.structured_payload)
        assert row["provenance_digest"] == verified.provenance_closure_digest
        assert dict(row["provenance_json"]) == {
            "provenance_closure_digest": verified.provenance_closure_digest
        }
        assert row["source_ref"] == verified.snapshot_ref
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
        assert head["value_ref"] == candidate_value_ref(
            candidate_value_id(verified.candidate_id)
        )
        assert head["value_digest"] == verified.payload_content_digest


def test_exact_duplicate_returns_same_value_head_and_document_ref(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    with disposable_database.begin() as connection:
        first = _admit(connection, verified, binding)
        second = _admit(connection, verified, binding)
        assert first.document_ref == second.document_ref
        assert _count_values(connection) == 1
        assert _count_canonical_heads(connection) == 1
        assert _count_commit_intents(connection) == 1


def test_structured_verified_pair_drift_fails_closed(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    forged = dataclasses.replace(
        _base_structured(),
        structured_payload={"mutated": True},
        payload_content_digest="",
        candidate_digest="",
    )
    assert isinstance(forged, StructuredMaterialCandidate)
    with disposable_database.begin() as connection:
        with pytest.raises(C7CandidateRejectedError):
            _admit(connection, verified, binding, structured=forged)
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 0
        assert _count_values(connection) == 0


def test_value_mutation_fails_closed(disposable_database: Engine) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    with disposable_database.begin() as connection:
        _admit(connection, verified, binding, config=config)
        connection.execute(
            _value_table()
            .update()
            .where(
                _value_table().c.project_key == PROJECT_KEY,
                _value_table().c.value_id == candidate_value_id(verified.candidate_id),
            )
            .values(content_json={"mutated": True})
        )
        with pytest.raises(C7ReadbackIntegrityError):
            readback_by_idempotency(
                connection,
                scope=_scope(),
                capability_id=C7_INGEST_OWNER,
                idempotency_key=config.idempotency_key,
                binding=binding,
            )


def test_value_stale_revision_fails_closed(disposable_database: Engine) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    with disposable_database.begin() as connection:
        _admit(connection, verified, binding, config=config)
        connection.execute(
            _value_table()
            .update()
            .where(
                _value_table().c.project_key == PROJECT_KEY,
                _value_table().c.value_id == candidate_value_id(verified.candidate_id),
            )
            .values(revision=2)
        )
        with pytest.raises(C7ReadbackIntegrityError):
            readback_by_idempotency(
                connection,
                scope=_scope(),
                capability_id=C7_INGEST_OWNER,
                idempotency_key=config.idempotency_key,
                binding=binding,
            )


def test_value_incarnation_aba_fails_closed(disposable_database: Engine) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    with disposable_database.begin() as connection:
        _admit(connection, verified, binding, config=config)
        connection.execute(
            _value_table()
            .update()
            .where(
                _value_table().c.project_key == PROJECT_KEY,
                _value_table().c.value_id == candidate_value_id(verified.candidate_id),
            )
            .values(incarnation="c7:structured:other")
        )
        with pytest.raises(C7ReadbackIntegrityError):
            readback_by_idempotency(
                connection,
                scope=_scope(),
                capability_id=C7_INGEST_OWNER,
                idempotency_key=config.idempotency_key,
                binding=binding,
            )


def test_missing_value_fails_closed(disposable_database: Engine) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    with disposable_database.begin() as connection:
        _admit(connection, verified, binding, config=config)
        connection.execute(
            _value_table()
            .delete()
            .where(
                _value_table().c.project_key == PROJECT_KEY,
                _value_table().c.value_id == candidate_value_id(verified.candidate_id),
            )
        )
        with pytest.raises(C7ReadbackIntegrityError):
            readback_by_idempotency(
                connection,
                scope=_scope(),
                capability_id=C7_INGEST_OWNER,
                idempotency_key=config.idempotency_key,
                binding=binding,
            )


def test_journal_and_head_receipt_consistent_after_commit(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    with disposable_database.begin() as connection:
        result = _admit(connection, verified, binding, config=config)
        event_row = (
            connection.execute(
                sa.select(PUBLIC_TABLES["runtime_events"]).where(
                    PUBLIC_TABLES["runtime_events"].c.project_key == PROJECT_KEY,
                    PUBLIC_TABLES["runtime_events"].c.run_id == RUN_ID,
                    PUBLIC_TABLES["runtime_events"].c.step_id == STEP_ID,
                    PUBLIC_TABLES["runtime_events"].c.attempt_id == ATTEMPT_ID,
                    PUBLIC_TABLES["runtime_events"].c.seq == 5,
                )
            )
            .mappings()
            .one()
        )
        journal_receipt = event_row["event_metadata_json"]["receipt_digest"]
        assert journal_receipt == config.receipt_digest
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
        assert head["receipt_digest"] == config.receipt_digest
        intent = CommitIntentRepository(connection, _scope()).find_for_readback(
            C7_INGEST_OWNER,
            config.idempotency_key,
        )
        assert intent["receipt_digest"] == config.receipt_digest
        assert result.receipt.receipt_digest == config.receipt_digest


def test_concurrent_journal_receipt_rewrite_blocked_by_lock(
    disposable_database: Engine,
) -> None:
    config = _config()
    scope = _scope()
    events_table = PUBLIC_TABLES["runtime_events"]
    with disposable_database.connect() as holder:
        transaction = holder.begin()
        assert require_locked_canonical_events(holder, scope=scope, config=config) == 5
        with disposable_database.connect() as rival:
            rival.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with pytest.raises(OperationalError):
                rival.execute(
                    events_table.update()
                    .where(
                        events_table.c.project_key == PROJECT_KEY,
                        events_table.c.run_id == RUN_ID,
                        events_table.c.step_id == STEP_ID,
                        events_table.c.attempt_id == ATTEMPT_ID,
                        events_table.c.seq == 5,
                    )
                    .values(
                        event_metadata_json=sa.text(
                            "jsonb_set(event_metadata_json, "
                            "'{receipt_digest}', '\"tampered\"'::jsonb)"
                        )
                    )
                )
            rival.rollback()
        assert require_locked_canonical_events(holder, scope=scope, config=config) == 5
        transaction.rollback()


def test_run_allocator_fence_blocks_concurrent_event_append(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    scope = _scope()
    with disposable_database.connect() as holder:
        transaction = holder.begin()
        run_row = require_locked_runtime_step_attempt(
            holder,
            scope=scope,
            candidate=verified,
            binding=binding,
            config=config,
        )
        assert int(run_row["next_event_seq"]) == 6
        with disposable_database.connect() as rival:
            rival.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with pytest.raises(OperationalError):
                RuntimeJournalRepository(rival, scope).append_transition(
                    run_id=RUN_ID,
                    expected_revision=0,
                    snapshot_values={"state": "RUNNING"},
                    events=(
                        {
                            "event_type": "appended",
                            "schema_version": C7_EVENT_SCHEMA_VERSION,
                            "step_id": STEP_ID,
                            "attempt_id": ATTEMPT_ID,
                            "event_metadata_json": {"extra_ref": "event:append"},
                            "payload_ref": None,
                            "payload_digest": None,
                            "authority_digest": AUTHORITY_DIGEST,
                        },
                    ),
                )
            rival.rollback()
        assert require_locked_canonical_events(holder, scope=scope, config=config) == 5
        transaction.rollback()


def test_run_allocator_next_event_seq_drift_is_rejected(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    with disposable_database.begin() as connection:
        connection.execute(
            PUBLIC_TABLES["runtime_runs"]
            .update()
            .where(
                PUBLIC_TABLES["runtime_runs"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_runs"].c.run_id == RUN_ID,
            )
            .values(next_event_seq=7)
        )
        with pytest.raises(C7RuntimeBindingError):
            _admit(connection, verified, binding)
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 0


def test_run_allocator_allows_unrelated_run_event_sequence(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    with disposable_database.begin() as connection:
        connection.execute(
            PUBLIC_TABLES["runtime_events"]
            .insert()
            .values(
                project_key=PROJECT_KEY,
                run_id=RUN_ID,
                seq=6,
                event_type="unrelated_run_observation",
                schema_version=C7_EVENT_SCHEMA_VERSION,
                step_id=None,
                attempt_id=None,
                event_metadata_json={"observation_digest": content_digest("other")},
                payload_ref=None,
                payload_digest=None,
                authority_digest=AUTHORITY_DIGEST,
            )
        )
        connection.execute(
            PUBLIC_TABLES["runtime_runs"]
            .update()
            .where(
                PUBLIC_TABLES["runtime_runs"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_runs"].c.run_id == RUN_ID,
            )
            .values(next_event_seq=7)
        )
        result = _admit(connection, verified, binding)
        assert result.document_ref.object_id == CANDIDATE_ID
        assert _count_canonical_heads(connection) == 1
        assert _count_commit_intents(connection) == 1


def test_capability_mismatch_is_rejected(disposable_database: Engine) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config(capability_id="ingest_index.c7.v2.verify_admit")
    with disposable_database.begin() as connection:
        with pytest.raises(C7CapabilityMismatchError):
            _admit(connection, verified, binding, config=config)
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 0


def test_binding_step_and_attempt_drift_are_rejected(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    step_drift = _admission_binding(verified, step_id="step:other")
    with disposable_database.begin() as connection:
        with pytest.raises(C7RuntimeBindingError):
            _admit(connection, verified, step_drift)
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 0
    attempt_drift = _admission_binding(
        verified,
        attempt_id=content_digest({"attempt": "other"}),
    )
    with disposable_database.begin() as connection:
        with pytest.raises(C7RuntimeBindingError):
            _admit(connection, verified, attempt_drift)
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 0


def test_program_plan_run_runtime_binding_mismatches(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    program, plan, _admission_step = _program_plan()
    cases: list[tuple[str, Any]] = [
        ("run_id", "run:other"),
        ("program_id", "program:other"),
        ("plan_id", "plan:other"),
    ]
    for field, value in cases:
        drifted_config = _config(**{field: value})
        drifted_binding = _admission_binding(verified, config=drifted_config)
        with disposable_database.begin() as connection:
            with pytest.raises(C7RuntimeBindingError):
                _admit(
                    connection,
                    verified,
                    drifted_binding,
                    config=drifted_config,
                )
            assert _count_canonical_heads(connection) == 0
            assert _count_commit_intents(connection) == 0

    program_drift = _admission_binding(
        verified,
        program_digest=content_digest({"program": "drift"}),
    )
    with (
        disposable_database.begin() as connection,
        pytest.raises(C7RuntimeBindingError),
    ):
        _admit(connection, verified, program_drift)
    plan_drift = _admission_binding(
        verified,
        plan_digest=content_digest({"plan": "drift"}),
    )
    with (
        disposable_database.begin() as connection,
        pytest.raises(C7RuntimeBindingError),
    ):
        _admit(connection, verified, plan_drift)
    assert plan.plan_id
    assert program.program_digest


def test_step_state_revision_and_epoch_drift_are_rejected(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    step_table = PUBLIC_TABLES["runtime_steps"]
    cases: list[tuple[str, Any]] = [
        ("state", "SUCCEEDED"),
        ("revision", EXPECTED_STEP_REVISION + 1),
        ("execution_epoch", EXECUTION_EPOCH + 1),
    ]
    for field, value in cases:
        with disposable_database.begin() as connection:
            connection.execute(
                step_table.update()
                .where(
                    step_table.c.project_key == PROJECT_KEY,
                    step_table.c.run_id == RUN_ID,
                    step_table.c.step_id == STEP_ID,
                )
                .values(**{field: value})
            )
            with pytest.raises(C7RuntimeBindingError):
                _admit(connection, verified, binding)
            assert _count_canonical_heads(connection) == 0
            assert _count_commit_intents(connection) == 0


def test_attempt_state_epoch_incarnation_assignment_handler_revision_drift(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    attempt_table = PUBLIC_TABLES["runtime_effect_attempts"]
    other_digest = content_digest({"other": "identity"})
    cases: list[tuple[str, Any]] = [
        ("disposition", "SUCCEEDED"),
        ("revision", EXPECTED_ATTEMPT_REVISION + 1),
        ("execution_epoch", EXECUTION_EPOCH + 1),
        ("incarnation", "attempt-inc:other"),
        ("assignment_digest", other_digest),
        ("input_digest", other_digest),
        ("authorization_digest", other_digest),
    ]
    for field, value in cases:
        with disposable_database.begin() as connection:
            connection.execute(
                attempt_table.update()
                .where(
                    attempt_table.c.project_key == PROJECT_KEY,
                    attempt_table.c.attempt_id == ATTEMPT_ID,
                )
                .values(**{field: value})
            )
            with pytest.raises(C7RuntimeBindingError):
                _admit(connection, verified, binding)
            assert _count_canonical_heads(connection) == 0
            assert _count_commit_intents(connection) == 0

    with disposable_database.begin() as connection:
        connection.execute(
            attempt_table.update()
            .where(
                attempt_table.c.project_key == PROJECT_KEY,
                attempt_table.c.attempt_id == ATTEMPT_ID,
            )
            .values(
                handler_binding_digest=other_digest,
                handler_realization_digest=other_digest,
            )
        )
        with pytest.raises(C7RuntimeBindingError):
            _admit(connection, verified, binding)
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 0


def test_handler_realization_config_drift_is_rejected(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config(
        handler_realization_digest=content_digest({"handler": "realization-drift"})
    )
    with disposable_database.begin() as connection:
        with pytest.raises(C7RuntimeBindingError):
            _admit(connection, verified, binding, config=config)
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 0


def test_config_handler_binding_realization_equality_is_required(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config(
        handler_binding_digest=HANDLER_BINDING_DIGEST,
        handler_realization_digest=content_digest({"handler": "other-realization"}),
    )
    with disposable_database.begin() as connection:
        with pytest.raises(C7RuntimeBindingError):
            _admit(connection, verified, binding, config=config)
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 0


def test_db_invariant_requires_handler_realization_equality(
    disposable_database: Engine,
) -> None:
    attempt_table = PUBLIC_TABLES["runtime_effect_attempts"]
    with (
        disposable_database.begin() as connection,
        pytest.raises(sa.exc.IntegrityError),
    ):
        connection.execute(
            attempt_table.update()
            .where(
                attempt_table.c.project_key == PROJECT_KEY,
                attempt_table.c.attempt_id == ATTEMPT_ID,
            )
            .values(
                handler_realization_digest=content_digest(
                    {"handler": "other-realization"}
                )
            )
        )


def test_actor_and_project_scope_drift_are_rejected(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    with disposable_database.begin() as connection:
        with pytest.raises(C7CandidateRejectedError):
            _admit(
                connection,
                verified,
                binding,
                scope=_scope(actor_id="actor:other"),
            )
        with pytest.raises(C7CandidateRejectedError):
            _admit(
                connection,
                verified,
                binding,
                scope=RuntimeScope(
                    project_scope=ProjectScopeRef(
                        project_key=PROJECT_KEY,
                        resolved_schema=RESOLVED_SCHEMA,
                        project_registry_revision=REGISTRY_REVISION + 1,
                        incarnation=SCOPE_INCARNATION,
                        scope_digest=content_digest({"scope": "drift"}),
                    ),
                    actor_id=ACTOR_ID,
                ),
            )
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 0


def test_authority_epoch_drift_and_revocation_are_rejected(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    authority_table = PUBLIC_TABLES["runtime_capability_authority"]
    with disposable_database.begin() as connection:
        connection.execute(
            authority_table.update()
            .where(
                authority_table.c.project_key == PROJECT_KEY,
                authority_table.c.capability_id == C7_INGEST_OWNER,
            )
            .values(authority_epoch=AUTHORITY_EPOCH + 1)
        )
        with pytest.raises(C7RevokedAuthorityError):
            _admit(connection, verified, binding)
    with disposable_database.begin() as connection:
        connection.execute(
            authority_table.update()
            .where(
                authority_table.c.project_key == PROJECT_KEY,
                authority_table.c.capability_id == C7_INGEST_OWNER,
            )
            .values(mode="off", successor_claim_enabled=False)
        )
        with pytest.raises(C7RevokedAuthorityError):
            _admit(connection, verified, binding)
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 0


def test_zero_canonical_events_are_rejected(disposable_database: Engine) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    with disposable_database.begin() as connection:
        connection.execute(text("DELETE FROM public.runtime_events"))
        with pytest.raises(C7RuntimeBindingError):
            _admit(connection, verified, binding)
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 0


def test_fresh_journal_drift_is_rejected(disposable_database: Engine) -> None:
    verified = _pure_verified_candidate()
    config = _config()
    drifted_events = list(_ordered_event_payloads(verified, config))
    drifted_events[4]["event_metadata_json"]["receipt_digest"] = content_digest(
        {"receipt": "drifted"}
    )
    drifted_binding = _admission_binding(
        verified,
        config=config,
        ordered_event_payloads=tuple(drifted_events),
    )
    with disposable_database.begin() as connection:
        with pytest.raises(C7RuntimeBindingError):
            _admit(
                connection,
                verified,
                drifted_binding,
                config=config,
                ordered_event_payloads=tuple(drifted_events),
            )
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 0


def test_duplicate_candidate_identity_in_canonical_journal_is_rejected(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    config = _config()
    duplicate = {
        "seq": 6,
        "event_type": "duplicate_candidate_identity",
        "schema_version": C7_EVENT_SCHEMA_VERSION,
        "step_id": STEP_ID,
        "attempt_id": ATTEMPT_ID,
        "event_metadata_json": {"decision_digest": verified.decision_digest},
        "payload_ref": None,
        "payload_digest": None,
        "authority_digest": AUTHORITY_DIGEST,
    }
    events = (*_ordered_event_payloads(verified, config), duplicate)
    binding = _admission_binding(
        verified,
        config=config,
        ordered_event_payloads=events,
    )
    with disposable_database.begin() as connection:
        connection.execute(
            PUBLIC_TABLES["runtime_events"]
            .insert()
            .values(
                project_key=PROJECT_KEY,
                run_id=RUN_ID,
                **duplicate,
            )
        )
        with pytest.raises(
            C7CandidateRejectedError,
            match="decision_digest exactly once",
        ):
            _admit(
                connection,
                verified,
                binding,
                config=config,
                ordered_event_payloads=events,
            )
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 0


def test_candidate_decision_and_provenance_mutation_fail_closed(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    with disposable_database.begin() as connection:
        mutated = dataclasses.replace(
            verified,
            decision_digest=content_digest({"decision": "other"}),
            verification_digest="",
        )
        assert isinstance(mutated, VerifiedMaterialCandidate)
        with pytest.raises(C7CandidateRejectedError):
            _admit(connection, mutated, binding)

        provenance_mutated = dataclasses.replace(
            verified,
            provenance_closure_digest=content_digest({"provenance": "other"}),
            verification_digest="",
        )
        assert isinstance(provenance_mutated, VerifiedMaterialCandidate)
        with pytest.raises(C7CandidateRejectedError):
            _admit(connection, provenance_mutated, binding)
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 0


def test_ordered_event_payload_mutation_fails_closed(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    events = list(_ordered_event_payloads(verified, config))
    events[3]["event_metadata_json"]["candidate_digest"] = content_digest(
        {"candidate": "other"}
    )
    with disposable_database.begin() as connection:
        with pytest.raises(C7CandidateRejectedError):
            _admit(
                connection,
                verified,
                binding,
                config=config,
                ordered_event_payloads=tuple(events),
            )
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 0


def test_self_consistent_rebuilt_binding_with_stale_events_fails_closed(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    config = _config()
    mutated = dataclasses.replace(
        verified,
        decision_digest=content_digest({"decision": "other"}),
        verification_digest="",
    )
    assert isinstance(mutated, VerifiedMaterialCandidate)
    rebuilt = _admission_binding(
        mutated,
        config=config,
        ordered_event_payloads=_ordered_event_payloads(verified, config),
    )
    with disposable_database.begin() as connection:
        with pytest.raises(C7CandidateRejectedError):
            _admit(connection, mutated, rebuilt, config=config)
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 0


def test_conflicting_self_consistent_event_closure_is_idempotency_conflict(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    config = _config()
    binding = _admission_binding(verified, config=config)
    conflicting_events = list(_ordered_event_payloads(verified, config)) + [
        {
            "seq": 6,
            "event_type": "extra",
            "schema_version": C7_EVENT_SCHEMA_VERSION,
            "step_id": STEP_ID,
            "attempt_id": ATTEMPT_ID,
            "event_metadata_json": {"extra_ref": "event:extra"},
            "payload_ref": None,
            "payload_digest": None,
            "authority_digest": AUTHORITY_DIGEST,
        }
    ]
    conflicting_binding = _admission_binding(
        verified,
        config=config,
        ordered_event_payloads=tuple(conflicting_events),
    )
    with disposable_database.begin() as connection:
        _admit(connection, verified, binding, config=config)
        with pytest.raises(C7IdempotencyConflictError):
            _admit(
                connection,
                verified,
                conflicting_binding,
                config=config,
                ordered_event_payloads=tuple(conflicting_events),
            )
        assert _count_canonical_heads(connection) == 1
        assert _count_commit_intents(connection) == 1


def test_committed_config_three_field_drift_is_idempotency_conflict(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    config = _config()
    binding = _admission_binding(verified, config=config)
    with disposable_database.begin() as connection:
        _admit(connection, verified, binding, config=config)
    cases: list[tuple[str, Any]] = [
        ("commit_intent_id", "commit:c7-target-admission:other"),
        ("canonical_commit_ref", "canonical:document:c7-target-admission:other"),
        ("receipt_digest", content_digest({"receipt": "other"})),
    ]
    for field, value in cases:
        drifted_config = _config(**{field: value})
        drifted_binding = _admission_binding(verified, config=drifted_config)
        with disposable_database.begin() as connection:
            with pytest.raises(C7IdempotencyConflictError):
                _admit(
                    connection,
                    verified,
                    drifted_binding,
                    config=drifted_config,
                )
            assert _count_canonical_heads(connection) == 1
            assert _count_commit_intents(connection) == 1


def test_prepared_request_ref_receipt_drift_is_event_digest_conflict(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    config = _config()
    binding = _admission_binding(verified, config=config)
    drifted_config = _config(
        canonical_commit_ref="canonical:document:c7-target-admission:prepared",
        receipt_digest=content_digest({"receipt": "prepared-drift"}),
    )
    drifted_binding = _admission_binding(verified, config=drifted_config)
    with disposable_database.begin() as connection:
        _seed_intent(connection, verified, config, binding)
        with pytest.raises(C7IdempotencyConflictError):
            _admit(
                connection,
                verified,
                drifted_binding,
                config=drifted_config,
            )
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 1


def test_idempotency_conflict_fails_closed(disposable_database: Engine) -> None:
    verified = _pure_verified_candidate()
    config = _config()
    binding = _admission_binding(verified, config=config)
    with disposable_database.begin() as connection:
        other = dataclasses.replace(
            verified,
            payload_content_digest=content_digest({"other": "candidate"}),
            verification_digest="",
        )
        repo = CommitIntentRepository(connection, _scope())
        repo.prepare(
            build_commit_binding(
                other,
                config=config,
                binding=_admission_binding(other, config=config),
            )
        )
        with pytest.raises(C7IdempotencyConflictError):
            _admit(connection, verified, binding, config=config)
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 1


def test_stale_canonical_revision_fails_closed(disposable_database: Engine) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    with disposable_database.begin() as connection:
        _seed_canonical_head(connection, verified, binding, config, revision=2)
        with pytest.raises(C7StaleCanonicalRevisionError):
            _admit(connection, verified, binding, config=config)
        assert _count_commit_intents(connection) == 0


def test_canonical_aba_fails_closed(disposable_database: Engine) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    with disposable_database.begin() as connection:
        _seed_canonical_head(
            connection,
            verified,
            binding,
            config,
            revision=1,
            content_digest_value=content_digest({"mutated": "content"}),
        )
        with pytest.raises(C7CanonicalAbaError):
            _admit(connection, verified, binding, config=config)
        assert _count_commit_intents(connection) == 0


def test_new_object_requires_base_revision_zero(disposable_database: Engine) -> None:
    verified = _pure_verified_candidate()
    shifted = dataclasses.replace(
        verified,
        expected_base_revision=1,
        verification_digest="",
    )
    assert isinstance(shifted, VerifiedMaterialCandidate)
    binding = _admission_binding(shifted)
    with disposable_database.begin() as connection:
        connection.execute(text("DELETE FROM public.runtime_events"))
        _seed_journal_events(connection, shifted, _config())
        with pytest.raises(C7StaleCanonicalRevisionError):
            _admit(connection, shifted, binding)
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 0


def test_unknown_commit_outcome_never_retries(disposable_database: Engine) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    with disposable_database.begin() as connection:
        _seed_intent(
            connection,
            verified,
            config,
            binding,
            status=CommitIntentStatus.UNKNOWN,
        )
        with pytest.raises(C7OutcomeUnknownError):
            _admit(connection, verified, binding, config=config)
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 1


def test_rejected_commit_outcome_never_retries(disposable_database: Engine) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    with disposable_database.begin() as connection:
        _seed_intent(
            connection,
            verified,
            config,
            binding,
            status=CommitIntentStatus.REJECTED,
        )
        with pytest.raises(C7NoSpeculativeRetryError):
            _admit(connection, verified, binding, config=config)
        assert _count_canonical_heads(connection) == 0
        assert _count_commit_intents(connection) == 1


def test_readback_tamper_fails_closed(disposable_database: Engine) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    with disposable_database.begin() as connection:
        _admit(connection, verified, binding, config=config)
        connection.execute(
            C7_MOVEMENT_CANONICAL_DOCUMENTS.update()
            .where(
                C7_MOVEMENT_CANONICAL_DOCUMENTS.c.project_key == PROJECT_KEY,
                C7_MOVEMENT_CANONICAL_DOCUMENTS.c.object_id == CANDIDATE_ID,
            )
            .values(receipt_digest=content_digest({"receipt": "tampered"}))
        )
        with pytest.raises(C7ReadbackIntegrityError):
            readback_by_idempotency(
                connection,
                scope=_scope(),
                capability_id=C7_INGEST_OWNER,
                idempotency_key=config.idempotency_key,
                binding=binding,
            )


def test_head_attempt_tamper_with_recomputed_closure_rejected(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    with disposable_database.begin() as connection:
        _admit(connection, verified, binding, config=config)
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
        values = dict(head)
        values["attempt_id"] = "attempt:tampered"
        connection.execute(
            C7_MOVEMENT_CANONICAL_DOCUMENTS.update()
            .where(
                C7_MOVEMENT_CANONICAL_DOCUMENTS.c.project_key == PROJECT_KEY,
                C7_MOVEMENT_CANONICAL_DOCUMENTS.c.object_id == CANDIDATE_ID,
            )
            .values(
                attempt_id="attempt:tampered",
                head_closure_digest=canonical_digest(
                    {
                        key: value
                        for key, value in values.items()
                        if key != "head_closure_digest"
                    }
                ),
            )
        )
        with pytest.raises(C7ReadbackIntegrityError):
            readback_by_idempotency(
                connection,
                scope=_scope(),
                capability_id=C7_INGEST_OWNER,
                idempotency_key=config.idempotency_key,
                binding=binding,
            )


def test_commit_intent_id_tamper_rejected(disposable_database: Engine) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    with disposable_database.begin() as connection:
        _admit(connection, verified, binding, config=config)
        connection.execute(
            PUBLIC_TABLES["runtime_commit_intents"]
            .update()
            .where(
                PUBLIC_TABLES["runtime_commit_intents"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_commit_intents"].c.commit_intent_id
                == config.commit_intent_id,
            )
            .values(commit_intent_id="commit:c7-target-admission:tampered")
        )
        with pytest.raises(C7ReadbackIntegrityError):
            readback_by_idempotency(
                connection,
                scope=_scope(),
                capability_id=C7_INGEST_OWNER,
                idempotency_key=config.idempotency_key,
                binding=binding,
            )


def test_readback_by_idempotency_returns_stored_facts(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    with disposable_database.begin() as connection:
        result = _admit(connection, verified, binding, config=config)
        stored = readback_by_idempotency(
            connection,
            scope=_scope(),
            capability_id=C7_INGEST_OWNER,
            idempotency_key=config.idempotency_key,
            binding=binding,
        )
        assert stored.readback == result.readback
        assert stored.document_ref == result.document_ref
        assert stored.receipt.canonical_commit_ref == config.canonical_commit_ref
        assert stored.receipt.receipt_digest == config.receipt_digest
        assert stored.receipt.commit_intent_id == config.commit_intent_id


def test_by_idempotency_readback_survives_runtime_terminalization(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    with disposable_database.begin() as connection:
        result = _admit(connection, verified, binding, config=config)
        RuntimeJournalRepository(connection, _scope()).append_transition(
            run_id=RUN_ID,
            expected_revision=0,
            snapshot_values={"state": "RUNNING"},
            events=(
                {
                    "event_type": "attempt_terminalized",
                    "schema_version": C7_EVENT_SCHEMA_VERSION,
                    "step_id": STEP_ID,
                    "attempt_id": ATTEMPT_ID,
                    "event_metadata_json": {
                        "terminal_receipt_digest": result.receipt.receipt_digest
                    },
                    "payload_ref": None,
                    "payload_digest": None,
                    "authority_digest": AUTHORITY_DIGEST,
                },
            ),
        )
        connection.execute(
            PUBLIC_TABLES["runtime_steps"]
            .update()
            .where(
                PUBLIC_TABLES["runtime_steps"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_steps"].c.run_id == RUN_ID,
                PUBLIC_TABLES["runtime_steps"].c.step_id == STEP_ID,
            )
            .values(state="SUCCEEDED", revision=1)
        )
        connection.execute(
            PUBLIC_TABLES["runtime_effect_attempts"]
            .update()
            .where(
                PUBLIC_TABLES["runtime_effect_attempts"].c.project_key == PROJECT_KEY,
                PUBLIC_TABLES["runtime_effect_attempts"].c.attempt_id == ATTEMPT_ID,
            )
            .values(disposition="SUCCEEDED", revision=1)
        )
        stored = readback_by_idempotency(
            connection,
            scope=_scope(),
            capability_id=C7_INGEST_OWNER,
            idempotency_key=config.idempotency_key,
            binding=binding,
        )
        assert stored.document_ref == result.document_ref
        assert stored.readback == result.readback
        duplicate = _admit(connection, verified, binding, config=config)
        assert duplicate.document_ref == result.document_ref
        assert duplicate.readback == result.readback
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
        assert head["step_revision"] == EXPECTED_STEP_REVISION
        assert head["attempt_revision"] == EXPECTED_ATTEMPT_REVISION
        with pytest.raises(C7ReadbackIntegrityError):
            load_authoritative_readback(
                connection,
                scope=_scope(),
                config=config,
                binding=binding,
            )


def test_readback_by_idempotency_rejects_foreign_capability(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    with disposable_database.begin() as connection:
        _admit(connection, verified, binding, config=config)
        with pytest.raises(C7CapabilityMismatchError):
            readback_by_idempotency(
                connection,
                scope=_scope(),
                capability_id="ingest_index.c7.v2.verify_admit",
                idempotency_key=config.idempotency_key,
                binding=binding,
            )


def test_exact_request_readback_rejects_config_drift(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    with disposable_database.begin() as connection:
        _admit(connection, verified, binding, config=config)
        with pytest.raises(C7IdempotencyConflictError):
            load_authoritative_readback(
                connection,
                scope=_scope(),
                config=_config(
                    canonical_commit_ref="canonical:document:c7-target-admission:other"
                ),
                binding=binding,
            )


def test_fault_between_head_write_and_intent_finalize_rolls_back_both_tables(
    disposable_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)

    def _fail_finalize(*_args: object, **_kwargs: object) -> Any:
        raise StaleRevisionError("injected intent CAS failure")

    monkeypatch.setattr(CommitIntentRepository, "record_result", _fail_finalize)
    connection = disposable_database.connect()
    transaction = connection.begin()
    try:
        with pytest.raises(C7OutcomeUnknownError):
            _admit(connection, verified, binding)
        transaction.rollback()
    finally:
        connection.close()
    with disposable_database.connect() as check:
        assert _count_canonical_heads(check) == 0
        assert _count_commit_intents(check) == 0
        assert _count_values(check) == 0


def test_caught_finalize_fault_outer_commit_leaves_zero(
    disposable_database: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)

    def _fail_finalize(*_args: object, **_kwargs: object) -> Any:
        raise StaleRevisionError("injected intent CAS failure")

    monkeypatch.setattr(CommitIntentRepository, "record_result", _fail_finalize)
    with (
        disposable_database.begin() as connection,
        pytest.raises(C7OutcomeUnknownError),
    ):
        _admit(connection, verified, binding)
    with disposable_database.connect() as check:
        assert _count_canonical_heads(check) == 0
        assert _count_commit_intents(check) == 0
        assert _count_values(check) == 0


def test_step_attempt_locks_block_concurrent_terminalization_and_revalidate(
    disposable_database: Engine,
) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    config = _config()
    scope = _scope()
    step_table = PUBLIC_TABLES["runtime_steps"]
    attempt_table = PUBLIC_TABLES["runtime_effect_attempts"]
    with disposable_database.connect() as holder:
        transaction = holder.begin()
        require_locked_runtime_step_attempt(
            holder,
            scope=scope,
            candidate=verified,
            binding=binding,
            config=config,
        )
        with disposable_database.connect() as rival:
            rival.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with pytest.raises(OperationalError):
                rival.execute(
                    step_table.update()
                    .where(
                        step_table.c.project_key == PROJECT_KEY,
                        step_table.c.run_id == RUN_ID,
                        step_table.c.step_id == STEP_ID,
                    )
                    .values(state="SUCCEEDED")
                )
            rival.rollback()
            rival.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with pytest.raises(OperationalError):
                rival.execute(
                    attempt_table.update()
                    .where(
                        attempt_table.c.project_key == PROJECT_KEY,
                        attempt_table.c.attempt_id == ATTEMPT_ID,
                    )
                    .values(disposition="SUCCEEDED")
                )
            rival.rollback()
        holder.execute(
            step_table.update()
            .where(
                step_table.c.project_key == PROJECT_KEY,
                step_table.c.run_id == RUN_ID,
                step_table.c.step_id == STEP_ID,
            )
            .values(state="SUCCEEDED")
        )
        with pytest.raises(C7RuntimeBindingError):
            require_locked_runtime_step_attempt(
                holder,
                scope=scope,
                candidate=verified,
                binding=binding,
                config=config,
            )
        transaction.rollback()


def test_crash_rollback_leaves_zero_residual(disposable_database: Engine) -> None:
    verified = _pure_verified_candidate()
    binding = _admission_binding(verified)
    connection = disposable_database.connect()
    transaction = connection.begin()
    try:
        result = _admit(connection, verified, binding)
        assert result.receipt.committed_revision == 1
        assert result.receipt.schema_version == C7_ADMISSION_SCHEMA_VERSION
        transaction.rollback()
    finally:
        connection.close()
    with disposable_database.connect() as check:
        assert _count_canonical_heads(check) == 0
        assert _count_commit_intents(check) == 0
        assert _count_values(check) == 0
