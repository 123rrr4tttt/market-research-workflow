"""Production C7 verified-candidate admission runner.

This repository-owned program is the bounded successor controller that drives
one C7 canonical document admission against a migrated PostgreSQL database.
It performs exactly the same deterministic pure movement, exact runtime
preflight, and ``admit_verified_candidate`` program path that the disposable
movement-admission evidence exercises, but it resolves the active
``project_scope_registry`` row from the database and seeds only missing runtime
rows.

Scope boundaries
----------------
* The runner never calls a live provider, never promotes, never writes legacy
  tables, and never changes the project scope registry.
* It writes successor-owned rows only: runtime program/plan/run/step/attempt/
  authority/event rows, ``c7_movement_canonical_documents``, the project
  ``successor_values`` row and the runtime commit-intent row.
* The public ``c7_movement_canonical_documents`` table must already exist via
  Alembic revision ``20260903_000003`` (or the disposable test/CI schema
  creation used by the proven movement-admission suite).  No runtime path may
  create it with ``.create()`` on a migrated database.
* ``runtime_journal.JournalCommandSet`` only appends transitions to an existing
  locked run row; it has no creation API for the initial program/plan/run/step/
  attempt rows.  The exact initial rows are therefore seeded with the same
  column values as the proven disposable movement-admission fixture, then the
  admission slice itself locks and validates them.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine

from app.successor_runtime.capabilities import ingest_c7_common as c7
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
from app.successor_runtime.capabilities.ingest_c7_program import (
    build_ingest_c7_1_program,
    compile_ingest_c7_program,
)
from app.successor_runtime.runtime.admission import VerificationBinding
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres.commit_intents import (
    CommitIntentRepository,
    CommitIntentStatus,
)
from app.successor_runtime.substrate.postgres.authority import (
    ProjectScopeRegistryRepository,
)
from app.successor_runtime.substrate.postgres.ingest_c7_movement_admission import (
    C7_ADMISSION_REQUEST_EVENT_TYPE,
    C7_EVENT_SCHEMA_VERSION,
    C7_MOVEMENT_CANONICAL_DOCUMENTS,
    C7AdmissionConfig,
    C7AdmissionResult,
    admit_verified_candidate,
    candidate_evidence_digest,
    candidate_provenance_digest,
    candidate_receipt_digest,
    readback_by_idempotency,
)
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.runtime_journal import RecordNotFound

__all__ = [
    "C7ProductionAdmissionInput",
    "C7ProductionAdmissionOutcome",
    "build_c7_production_parts",
    "resolve_active_scope",
    "run_c7_production_cutover_admission",
    "seed_c7_runtime_preflight",
]


@dataclass(frozen=True, slots=True)
class C7ProductionAdmissionInput:
    """Deterministic input for one bounded C7 canonical admission."""

    project_key: str
    trace_id: str
    actor_id: str
    approval_ref: str
    canonical_object_id: str
    source_locator: str
    raw_bytes: bytes
    raw_incarnation: str
    authority_epoch: int = 1
    content_format: str = "structured_json"

    def __post_init__(self) -> None:
        for field_name in (
            "project_key",
            "trace_id",
            "actor_id",
            "approval_ref",
            "canonical_object_id",
            "source_locator",
            "raw_incarnation",
        ):
            if not str(getattr(self, field_name) or "").strip():
                raise ValueError(f"{field_name} is required")
        if not self.raw_bytes:
            raise ValueError("raw_bytes is required")
        if self.authority_epoch <= 0:
            raise ValueError("authority_epoch must be positive")
        if self.content_format not in {"structured_json"}:
            raise ValueError("unsupported C7 content format")


@dataclass(frozen=True, slots=True)
class C7RuntimeSeed:
    """Compiled program/plan and exact runtime seed values."""

    program: Any
    plan: Any
    admission_step: Any
    structured: StructuredMaterialCandidate
    verified: VerifiedMaterialCandidate
    config: C7AdmissionConfig
    binding: VerificationBinding
    ordered_event_payloads: tuple[Mapping[str, object], ...]


@dataclass(frozen=True, slots=True)
class C7ProductionAdmissionOutcome:
    """Receipt/readback result and pre/post row counts."""

    status: str
    result: C7AdmissionResult
    canonical_rows_before: int
    canonical_rows_after: int
    seed_rows_before: Mapping[str, int]


def resolve_active_scope(
    connection: Connection,
    project_key: str,
    actor_id: str,
) -> RuntimeScope:
    """Load the sole ACTIVE project scope row and build the exact scope."""

    table = PUBLIC_TABLES["project_scope_registry"]
    rows = list(
        connection.execute(
            sa.select(table).where(
                table.c.project_key == project_key,
                table.c.state == "ACTIVE",
            )
        ).mappings()
    )
    if not rows:
        raise RecordNotFound(f"active project scope registry row not found: {project_key}")
    if len(rows) != 1:
        raise RuntimeError("project scope registry has multiple ACTIVE rows")
    row = rows[0]
    return RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key=project_key,
            resolved_schema=str(row["resolved_schema"]),
            project_registry_revision=int(row["registry_revision"]),
            incarnation=str(row["incarnation"]),
            scope_digest=str(row["scope_digest"]),
        ),
        actor_id=actor_id,
    )


def _authority_digest(*, project_key: str, approval_ref: str) -> str:
    return content_digest(
        {
            "authority": "c7-production",
            "project_key": project_key,
            "approval_ref": approval_ref,
        }
    )


def _submission_payload(
    admission_input: C7ProductionAdmissionInput,
) -> dict[str, Any]:
    try:
        payload = json.loads(admission_input.raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("raw_bytes must be UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("raw_bytes JSON payload must be an object")
    if not str(payload.get("title") or "").strip() or not str(
        payload.get("text") or ""
    ).strip():
        raise ValueError("raw_bytes JSON payload requires title/text fields")
    return dict(payload)


def _program_plan(
    admission_input: C7ProductionAdmissionInput,
    scope: RuntimeScope,
) -> tuple[Any, Any, Any]:
    bundle = c7.build_ingest_c7_bundle()
    catalog = c7.build_ingest_c7_catalog(bundle)
    registry = c7.build_ingest_c7_registry(bundle)
    program_id = f"program:c7-production:{admission_input.trace_id}"
    request_key = f"req:c7-production:{admission_input.trace_id}"
    submission = c7.C7IngestSubmission(
        idempotency_key=f"idem:c7-production:{admission_input.trace_id}",
        project_key=admission_input.project_key,
        source_locator=admission_input.source_locator,
        request_key=request_key,
        raw_payload=_submission_payload(admission_input),
    )
    program = build_ingest_c7_1_program(
        payload=submission,
        catalog=catalog,
        program_id=program_id,
        project_key=admission_input.project_key,
        project_registry_revision=scope.project_scope.project_registry_revision,
        project_scope_digest=scope.project_scope.scope_digest,
    )
    plan = compile_ingest_c7_program(program, catalog, operation_contracts=registry)
    steps = [step for step in plan.ordered_steps if step.step_kind == "ADMISSION"]
    if len(steps) != 1:
        raise AssertionError("C7.1 plan must contain exactly one ADMISSION step")
    return program, plan, steps[0]


def _verified_pair(
    admission_input: C7ProductionAdmissionInput,
    scope: RuntimeScope,
) -> tuple[StructuredMaterialCandidate, VerifiedMaterialCandidate]:
    authority_digest = _authority_digest(
        project_key=admission_input.project_key,
        approval_ref=admission_input.approval_ref,
    )
    snapshot = capture_raw_snapshot_exact(
        project_key=admission_input.project_key,
        source_locator=admission_input.source_locator,
        raw_bytes=admission_input.raw_bytes,
        incarnation=admission_input.raw_incarnation,
        mime_type="application/json",
        provenance_refs=(admission_input.approval_ref,),
    )
    envelope = normalize_ingest_envelope(
        snapshot=snapshot,
        input_kind="url_driven_external",
        content_format=admission_input.content_format,
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
    if not isinstance(trace.outcome, StructuredMaterialCandidate):
        raise AssertionError("deterministic C7 trace must produce a structured candidate")
    structured = trace.outcome
    verified = verify_structured_candidate(
        snapshot=snapshot,
        envelope=envelope,
        decision=decision,
        candidate=structured,
        expected_candidate_digest=structured.candidate_digest,
        expected_project_key=admission_input.project_key,
        actor=admission_input.actor_id,
        authority_digest=authority_digest,
        authority_epoch=admission_input.authority_epoch,
        canonical_base_revision=0,
        canonical_base_incarnation=scope.project_scope.incarnation,
        canonical_object_id=admission_input.canonical_object_id,
    )
    if not isinstance(verified, VerifiedMaterialCandidate):
        raise AssertionError("C7 verification must produce a verified candidate")
    return structured, verified


def _ordered_event_payloads(
    verified: VerifiedMaterialCandidate,
    config: C7AdmissionConfig,
) -> tuple[dict[str, object], ...]:
    return (
        {
            "seq": 1,
            "event_type": "raw_snapshot_captured",
            "schema_version": C7_EVENT_SCHEMA_VERSION,
            "step_id": config.step_id,
            "attempt_id": config.attempt_id,
            "event_metadata_json": {
                "snapshot_ref": verified.snapshot_ref,
                "snapshot_identity_digest": verified.snapshot_identity_digest,
                "raw_content_digest": verified.raw_content_digest,
            },
            "payload_ref": None,
            "payload_digest": None,
            "authority_digest": verified.authority_digest,
        },
        {
            "seq": 2,
            "event_type": "envelope_normalized",
            "schema_version": C7_EVENT_SCHEMA_VERSION,
            "step_id": config.step_id,
            "attempt_id": config.attempt_id,
            "event_metadata_json": {
                "envelope_digest": verified.envelope_digest,
                "payload_content_digest": verified.payload_content_digest,
            },
            "payload_ref": None,
            "payload_digest": None,
            "authority_digest": verified.authority_digest,
        },
        {
            "seq": 3,
            "event_type": "decision_selected",
            "schema_version": C7_EVENT_SCHEMA_VERSION,
            "step_id": config.step_id,
            "attempt_id": config.attempt_id,
            "event_metadata_json": {"decision_digest": verified.decision_digest},
            "payload_ref": None,
            "payload_digest": None,
            "authority_digest": verified.authority_digest,
        },
        {
            "seq": 4,
            "event_type": "candidate_verified",
            "schema_version": C7_EVENT_SCHEMA_VERSION,
            "step_id": config.step_id,
            "attempt_id": config.attempt_id,
            "event_metadata_json": {
                "candidate_digest": verified.candidate_digest,
                "verification_digest": verified.verification_digest,
                "provenance_closure_digest": verified.provenance_closure_digest,
            },
            "payload_ref": None,
            "payload_digest": None,
            "authority_digest": verified.authority_digest,
        },
        {
            "seq": 5,
            "event_type": C7_ADMISSION_REQUEST_EVENT_TYPE,
            "schema_version": C7_EVENT_SCHEMA_VERSION,
            "step_id": config.step_id,
            "attempt_id": config.attempt_id,
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
            "authority_digest": verified.authority_digest,
        },
    )


def _config(
    admission_input: C7ProductionAdmissionInput,
    *,
    plan: Any,
    admission_step: Any,
    verified: VerifiedMaterialCandidate,
) -> C7AdmissionConfig:
    trace = admission_input.trace_id
    return C7AdmissionConfig(
        commit_intent_id=f"commit:c7-production:{trace}",
        run_id=f"run:c7-production:{trace}",
        step_id=str(admission_step.step_id),
        attempt_id=content_digest({"attempt": f"c7-production:{trace}"}),
        program_id=f"program:c7-production:{trace}",
        plan_id=str(plan.plan_id),
        capability_id=C7_INGEST_OWNER,
        idempotency_key=f"idem:c7-production:{trace}",
        execution_epoch=1,
        attempt_incarnation=f"attempt-inc:c7-production:{trace}",
        assignment_digest=content_digest(
            {"assignment": f"c7-production:{trace}"}
        ),
        handler_binding_digest=content_digest(
            {"handler": f"c7-production:{trace}"}
        ),
        handler_realization_digest=content_digest(
            {"handler": f"c7-production:{trace}"}
        ),
        expected_step_revision=0,
        expected_attempt_revision=0,
        canonical_commit_ref=f"canonical:document:c7-production:{trace}",
        receipt_digest=content_digest({"receipt": f"c7-production:{trace}"}),
    )


def _binding(
    verified: VerifiedMaterialCandidate,
    *,
    config: C7AdmissionConfig,
    program: Any,
    plan: Any,
    admission_step: Any,
    scope: RuntimeScope,
) -> VerificationBinding:
    return VerificationBinding.from_content(
        program_digest=str(program.program_digest),
        plan_digest=str(plan.plan_digest),
        step_id=str(admission_step.step_id),
        attempt_id=config.attempt_id,
        input_closure_digest=verified.snapshot_identity_digest,
        output_content_digest=verified.payload_content_digest,
        ordered_event_payloads=list(_ordered_event_payloads(verified, config)),
        schema_digest=content_digest({"schema": "ingest.c7.admission.v1"}),
        compiler_identity=str(plan.compiler_id),
        interpreter_identity="successor.ingest_index.c7.pure.v1",
        verifier_identity="ingest.validator.c7.v1",
        actor_id=verified.actor,
        project_key=verified.project_key,
        authority_digest=verified.authority_digest,
        project_registry_revision=scope.project_scope.project_registry_revision,
        project_scope_digest=scope.project_scope.scope_digest,
        resolved_schema=scope.project_scope.resolved_schema,
        canonical_owner=DOCUMENT_CANONICAL_OWNER,
        canonical_object_id=verified.canonical_object_id,
        canonical_base_revision=verified.expected_base_revision,
        canonical_incarnation=verified.expected_base_incarnation,
        evidence_digest=candidate_evidence_digest(verified),
        receipt_digest=candidate_receipt_digest(verified),
        provenance_digest=candidate_provenance_digest(verified),
        qualifier="staged-candidate",
    )


def build_c7_production_parts(
    admission_input: C7ProductionAdmissionInput,
    scope: RuntimeScope,
) -> C7RuntimeSeed:
    """Build every exact value consumed by the proven admission slice."""

    program, plan, admission_step = _program_plan(admission_input, scope)
    structured, verified = _verified_pair(admission_input, scope)
    config = _config(admission_input, plan=plan, admission_step=admission_step, verified=verified)
    events = _ordered_event_payloads(verified, config)
    binding = _binding(
        verified,
        config=config,
        program=program,
        plan=plan,
        admission_step=admission_step,
        scope=scope,
    )
    return C7RuntimeSeed(
        program=program,
        plan=plan,
        admission_step=admission_step,
        structured=structured,
        verified=verified,
        config=config,
        binding=binding,
        ordered_event_payloads=events,
    )


def _exists(
    connection: Connection,
    table: sa.Table,
    *,
    where: Sequence[object],
) -> bool:
    return connection.execute(sa.select(sa.literal(1)).select_from(table).where(*where)).first() is not None


def seed_c7_runtime_preflight(
    connection: Connection,
    *,
    scope: RuntimeScope,
    admission_input: C7ProductionAdmissionInput,
    seed: C7RuntimeSeed,
) -> None:
    """Insert missing exact runtime rows in dependency order."""

    program = seed.program
    plan = seed.plan
    verified = seed.verified
    config = seed.config
    authority_digest = verified.authority_digest
    now = datetime.now(UTC)

    registry_row = PUBLIC_TABLES["project_scope_registry"]
    active_scope = ProjectScopeRegistryRepository(connection, scope).load()
    if int(active_scope["registry_revision"]) != scope.project_scope.project_registry_revision:
        raise RuntimeError("project scope registry revision drifted during admission")

    program_table = PUBLIC_TABLES["runtime_program_refs"]
    if not _exists(
        connection,
        program_table,
        where=(
            program_table.c.project_key == scope.project_scope.project_key,
            program_table.c.program_id == config.program_id,
        ),
    ):
        connection.execute(
            program_table.insert().values(
                program_id=config.program_id,
                project_key=scope.project_scope.project_key,
                program_digest=program.program_digest,
                project_storage_ref=f"project-value:program:c7-production:{admission_input.trace_id}",
                contract_version="mrw.functorial-successor.program-spec.v1",
            )
        )

    plan_table = PUBLIC_TABLES["runtime_plan_refs"]
    if not _exists(
        connection,
        plan_table,
        where=(
            plan_table.c.project_key == scope.project_scope.project_key,
            plan_table.c.plan_id == config.plan_id,
        ),
    ):
        connection.execute(
            plan_table.insert().values(
                plan_id=config.plan_id,
                project_key=scope.project_scope.project_key,
                plan_digest=plan.plan_digest,
                program_id=config.program_id,
                program_digest=program.program_digest,
                project_storage_ref=f"project-value:plan:c7-production:{admission_input.trace_id}",
                compiler_id=plan.compiler_id,
                compiler_version=plan.compiler_version,
                operation_catalog_id=C7_OPERATION_CATALOG_ID,
                catalog_version=C7_OPERATION_CATALOG_VERSION,
                catalog_digest=c7.build_ingest_c7_catalog(
                    c7.build_ingest_c7_bundle()
                ).catalog_digest,
                effect_closure_digest=plan.effect_closure_digest,
                authority_closure_digest=plan.authority_closure_digest,
                resource_closure_digest=plan.resource_closure_digest,
            )
        )

    runs_table = PUBLIC_TABLES["runtime_runs"]
    run_exists = _exists(
        connection,
        runs_table,
        where=(
            runs_table.c.project_key == scope.project_scope.project_key,
            runs_table.c.run_id == config.run_id,
        ),
    )
    events = seed.ordered_event_payloads
    if not run_exists:
        connection.execute(
            runs_table.insert().values(
                run_id=config.run_id,
                project_key=scope.project_scope.project_key,
                project_registry_revision=scope.project_scope.project_registry_revision,
                project_scope_digest=scope.project_scope.scope_digest,
                resolved_schema=scope.project_scope.resolved_schema,
                program_id=config.program_id,
                program_digest=program.program_digest,
                plan_id=config.plan_id,
                plan_digest=plan.plan_digest,
                state="READY",
                revision=0,
                next_event_seq=len(events) + 1,
                execution_epoch=config.execution_epoch,
                incarnation=f"run-inc:c7-production:{admission_input.trace_id}",
                submission_authority_digest=authority_digest,
                qualification_digest=authority_digest,
            )
        )

    events_table = PUBLIC_TABLES["runtime_events"]
    if not run_exists:
        for record in events:
            connection.execute(
                events_table.insert().values(
                    project_key=scope.project_scope.project_key,
                    run_id=config.run_id,
                    seq=int(record["seq"]),
                    event_type=str(record["event_type"]),
                    schema_version=str(record["schema_version"]),
                    step_id=str(record["step_id"]),
                    attempt_id=str(record["attempt_id"]),
                    event_metadata_json=record["event_metadata_json"],
                    payload_ref=record["payload_ref"],
                    payload_digest=record["payload_digest"],
                    authority_digest=str(record["authority_digest"]),
                )
            )

    steps_table = PUBLIC_TABLES["runtime_steps"]
    if not _exists(
        connection,
        steps_table,
        where=(
            steps_table.c.project_key == scope.project_scope.project_key,
            steps_table.c.run_id == config.run_id,
            steps_table.c.step_id == config.step_id,
        ),
    ):
        connection.execute(
            steps_table.insert().values(
                project_key=scope.project_scope.project_key,
                run_id=config.run_id,
                step_id=config.step_id,
                operation_id="ingest_index.verify_admit",
                operation_kind="ingest_index.verify_admit.v1",
                operation_version="1.0.0",
                state="RUNNING",
                revision=config.expected_step_revision,
                execution_epoch=config.execution_epoch,
                input_digest=authority_digest,
                output_digest=authority_digest,
                effect_class="EFFECTFUL",
                resource_class="CPU_LIGHT",
                capability_id=C7_INGEST_OWNER,
                claim_owner="successor",
                claim_authority_epoch=admission_input.authority_epoch,
                claim_policy_digest=authority_digest,
            )
        )

    attempts_table = PUBLIC_TABLES["runtime_effect_attempts"]
    if not _exists(
        connection,
        attempts_table,
        where=(
            attempts_table.c.project_key == scope.project_scope.project_key,
            attempts_table.c.attempt_id == config.attempt_id,
        ),
    ):
        connection.execute(
            attempts_table.insert().values(
                attempt_id=config.attempt_id,
                project_key=scope.project_scope.project_key,
                run_id=config.run_id,
                step_id=config.step_id,
                execution_epoch=config.execution_epoch,
                incarnation=config.attempt_incarnation,
                assignment_digest=config.assignment_digest,
                handler_binding_digest=config.handler_binding_digest,
                handler_realization_digest=config.handler_realization_digest,
                idempotency_key=config.idempotency_key,
                authorization_digest=authority_digest,
                input_digest=verified.snapshot_identity_digest,
                claim_binding_json={"claim": f"c7-production:{admission_input.trace_id}"},
                claim_binding_digest=authority_digest,
                disposition="IN_FLIGHT",
                revision=config.expected_attempt_revision,
            )
        )

    authority_table = PUBLIC_TABLES["runtime_capability_authority"]
    if not _exists(
        connection,
        authority_table,
        where=(
            authority_table.c.project_key == scope.project_scope.project_key,
            authority_table.c.capability_id == C7_INGEST_OWNER,
        ),
    ):
        connection.execute(
            authority_table.insert().values(
                project_key=scope.project_scope.project_key,
                capability_id=C7_INGEST_OWNER,
                mode="on",
                authority_epoch=admission_input.authority_epoch,
                successor_claim_enabled=True,
                legacy_claim_enabled=False,
                allowlist_digest=authority_digest,
                config_digest=authority_digest,
                effective_at=now,
                updated_by=admission_input.actor_id,
                approval_ref=admission_input.approval_ref,
                rollback_target_ref=f"rollback:c7-production:{admission_input.trace_id}",
            )
        )


def _canonical_row_count(connection: Connection, project_key: str) -> int:
    return int(
        connection.execute(
            sa.select(sa.func.count())
            .select_from(C7_MOVEMENT_CANONICAL_DOCUMENTS)
            .where(C7_MOVEMENT_CANONICAL_DOCUMENTS.c.project_key == project_key)
        ).scalar_one()
    )


def _seed_row_counts(connection: Connection, scope: RuntimeScope) -> dict[str, int]:
    table_names = (
        "runtime_program_refs",
        "runtime_plan_refs",
        "runtime_runs",
        "runtime_events",
        "runtime_steps",
        "runtime_effect_attempts",
        "runtime_capability_authority",
    )
    counts: dict[str, int] = {}
    for table_name in table_names:
        table = PUBLIC_TABLES[table_name]
        if "project_key" in table.c:
            statement = (
                sa.select(sa.func.count())
                .select_from(table)
                .where(table.c.project_key == scope.project_scope.project_key)
            )
        else:
            statement = sa.select(sa.func.count()).select_from(table)
        counts[table_name] = int(connection.execute(statement).scalar_one())
    return counts


def run_c7_production_cutover_admission(
    engine: Engine,
    *,
    admission_input: C7ProductionAdmissionInput,
) -> C7ProductionAdmissionOutcome:
    """Run one bounded C7 admission in a single caller-owned transaction.

    Replaying the same trace/idempotency key returns the committed canonical
    binding (``REPLAYED_COMMITTED``) instead of writing a second row.
    """

    with engine.begin() as connection:
        scope = resolve_active_scope(
            connection,
            admission_input.project_key,
            admission_input.actor_id,
        )
        seed = build_c7_production_parts(admission_input, scope)
        before = _canonical_row_count(connection, admission_input.project_key)
        seed_counts_before = _seed_row_counts(connection, scope)
        config = seed.config
        repo = CommitIntentRepository(connection, scope)
        try:
            existing = repo.find_for_readback(C7_INGEST_OWNER, config.idempotency_key)
        except RecordNotFound:
            existing = None
        if existing is not None and existing["state"] == CommitIntentStatus.COMMITTED.value:
            result = readback_by_idempotency(
                connection,
                scope=scope,
                capability_id=C7_INGEST_OWNER,
                idempotency_key=config.idempotency_key,
                binding=seed.binding,
            )
            status = "REPLAYED_COMMITTED"
        else:
            seed_c7_runtime_preflight(
                connection,
                scope=scope,
                admission_input=admission_input,
                seed=seed,
            )
            result = admit_verified_candidate(
                connection,
                seed.structured,
                seed.verified,
                seed.binding,
                seed.ordered_event_payloads,
                config=config,
                scope=scope,
            )
            status = "COMMITTED"
        after = _canonical_row_count(connection, admission_input.project_key)
        return C7ProductionAdmissionOutcome(
            status=status,
            result=result,
            canonical_rows_before=before,
            canonical_rows_after=after,
            seed_rows_before=seed_counts_before,
        )
