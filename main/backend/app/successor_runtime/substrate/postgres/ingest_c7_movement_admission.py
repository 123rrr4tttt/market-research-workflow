"""Disposable PostgreSQL admission for the pure C7 verified candidate.

This effect slice consumes the concrete pure
``ingest_c7_movements.VerifiedMaterialCandidate`` together with a separate
exact runtime ``VerificationBinding`` and the exact ordered event payloads.
The canonical ``runtime_events`` journal is the ordered event authority: the
admission reads its rows ordered by project/run/step/attempt and ``seq`` and
requires verbatim equivalence with the caller-supplied records and the binding
event closure.  Event metadata contains only digest/ref/id scalar values.

The slice never promotes, never calls a live provider, and never claims
production canonical authority.  The only database writes are made to a
disposable test/CI database.  The capability identity is fixed to
``C7_INGEST_OWNER``; the admission step must be ``RUNNING`` and its effect
attempt ``IN_FLIGHT`` with exact epoch/incarnation/assignment/handler/revision
identity.  Step, attempt, project-scope and capability-authority rows are
locked ``FOR UPDATE`` and revalidated before the canonical mutation, which runs
inside an interpreter-owned savepoint.  Readback requires the original
``VerificationBinding`` and reconstructs the pure candidate from the head; a
head digest recomputed from the same mutable row is never sufficient.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import sqlalchemy as sa
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.ingest_c7_common import (
    ADMISSION_READBACK_CONTRACT_ID,
    C7_INGEST_OWNER,
    DOCUMENT_CANONICAL_OWNER,
)
from app.successor_runtime.capabilities.ingest_c7_movements import (
    StructuredMaterialCandidate,
    VerifiedMaterialCandidate,
)
from app.successor_runtime.runtime.admission import (
    CommitIntent,
    CommitIntentState,
    VerificationBinding,
    event_payload_digest,
    ordered_event_closure_digest,
    require_admission_binding,
)
from app.successor_runtime.runtime.assignments import canonical_digest
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.substrate.postgres.authority import (
    CapabilityAuthorityRepository,
    ProjectScopeRegistryRepository,
)
from app.successor_runtime.substrate.postgres.c7_document_readback import (
    CanonicalCommitReadback,
    DocumentRef,
    document_ref_from_readback,
)
from app.successor_runtime.substrate.postgres.commit_intents import (
    CommitIntentBinding,
    CommitIntentRepository,
    CommitIntentStatus,
)
from app.successor_runtime.substrate.postgres.models import PUBLIC_TABLES
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    StaleRevisionError,
)

from .ingest_c7_candidate_values import (
    C7StructuredValueRef,
    C7ValueHandoffError,
    C7ValueIntegrityError,
    candidate_value_id,
    candidate_value_incarnation,
    candidate_value_ref,
    readback_candidate_value,
    require_exact_candidate_pair,
    store_candidate_value,
)

__all__ = [
    "C7_ADMISSION_REQUEST_EVENT_TYPE",
    "C7_ADMISSION_SCHEMA_VERSION",
    "C7AdmissionConfig",
    "C7AdmissionReceipt",
    "C7AdmissionResult",
    "C7CandidateRejectedError",
    "C7CanonicalAbaError",
    "C7CapabilityMismatchError",
    "C7IdempotencyConflictError",
    "C7MovementAdmissionError",
    "C7NoSpeculativeRetryError",
    "C7OutcomeUnknownError",
    "C7ReadbackIntegrityError",
    "C7RevokedAuthorityError",
    "C7RuntimeBindingError",
    "C7StaleCanonicalRevisionError",
    "admit_verified_candidate",
    "build_commit_binding",
    "build_commit_intent",
    "candidate_evidence_digest",
    "candidate_provenance_digest",
    "candidate_receipt_digest",
    "load_authoritative_readback",
    "readback_by_idempotency",
    "require_locked_canonical_events",
    "require_locked_capability_authority",
    "require_locked_runtime_step_attempt",
]

C7_ADMISSION_SCHEMA_VERSION = "mrw.successor.c7.verify-admit.v1"
C7_ADMISSION_REQUEST_EVENT_TYPE = "admission_requested"
C7_EVENT_SCHEMA_VERSION = "mrw.successor.ingest-c7.events.v1"
_DIGEST_REF_METADATA_SUFFIXES = (
    "_digest",
    "_ref",
    "_id",
    "_key",
    "_epoch",
    "_revision",
    "_seq",
)

C7_MOVEMENT_CANONICAL_DOCUMENTS = sa.Table(
    "c7_movement_canonical_documents",
    sa.MetaData(),
    sa.Column("project_key", sa.String(128), primary_key=True),
    sa.Column("object_id", sa.String(128), primary_key=True),
    sa.Column("commit_intent_id", sa.String(128), nullable=False),
    sa.Column("canonical_owner", sa.String(128), nullable=False),
    sa.Column("run_id", sa.String(128), nullable=False),
    sa.Column("step_id", sa.String(128), nullable=False),
    sa.Column("attempt_id", sa.String(128), nullable=False),
    sa.Column("capability_id", sa.String(128), nullable=False),
    sa.Column("actor_id", sa.String(128), nullable=False),
    sa.Column("program_digest", sa.String(64), nullable=False),
    sa.Column("plan_digest", sa.String(64), nullable=False),
    sa.Column("step_revision", sa.BigInteger, nullable=False),
    sa.Column("attempt_revision", sa.BigInteger, nullable=False),
    sa.Column("execution_epoch", sa.BigInteger, nullable=False),
    sa.Column("attempt_incarnation", sa.String(128), nullable=False),
    sa.Column("assignment_digest", sa.String(64), nullable=False),
    sa.Column("handler_binding_digest", sa.String(64), nullable=False),
    sa.Column("handler_realization_digest", sa.String(64), nullable=False),
    sa.Column("input_closure_digest", sa.String(64), nullable=False),
    sa.Column("revision", sa.BigInteger, nullable=False),
    sa.Column("incarnation", sa.String(128), nullable=False),
    sa.Column("expected_base_revision", sa.BigInteger, nullable=False),
    sa.Column("expected_base_incarnation", sa.String(128), nullable=False),
    sa.Column("content_digest", sa.String(64), nullable=False),
    sa.Column("snapshot_identity_digest", sa.String(64), nullable=False),
    sa.Column("raw_content_digest", sa.String(64), nullable=False),
    sa.Column("envelope_digest", sa.String(64), nullable=False),
    sa.Column("payload_content_digest", sa.String(64), nullable=False),
    sa.Column("ordered_source_closure_digest", sa.String(64), nullable=False),
    sa.Column("provenance_closure_digest", sa.String(64), nullable=False),
    sa.Column("decision_digest", sa.String(64), nullable=False),
    sa.Column("candidate_digest", sa.String(64), nullable=False),
    sa.Column("candidate_verification_digest", sa.String(64), nullable=False),
    sa.Column("ordered_event_closure_digest", sa.String(64), nullable=False),
    sa.Column("verification_digest", sa.String(64), nullable=False),
    sa.Column("authority_digest", sa.String(64), nullable=False),
    sa.Column("authority_epoch", sa.BigInteger, nullable=False),
    sa.Column("candidate_id", sa.String(128), nullable=False),
    sa.Column("snapshot_ref", sa.String(256), nullable=False),
    sa.Column("alternative", sa.String(32), nullable=False),
    sa.Column("verification_profile_ref", sa.String(128), nullable=False),
    sa.Column("verification_receipt", sa.String(256), nullable=False),
    sa.Column("evidence_digest", sa.String(64), nullable=False),
    sa.Column("provenance_digest", sa.String(64), nullable=False),
    sa.Column("candidate_receipt_digest", sa.String(64), nullable=False),
    sa.Column("value_ref", sa.String(256), nullable=False),
    sa.Column("value_revision", sa.BigInteger, nullable=False),
    sa.Column("value_incarnation", sa.String(128), nullable=False),
    sa.Column("value_digest", sa.String(64), nullable=False),
    sa.Column("value_provenance_digest", sa.String(64), nullable=False),
    sa.Column("canonical_commit_ref", sa.String(256), nullable=False),
    sa.Column("receipt_digest", sa.String(64), nullable=False),
    sa.Column("head_closure_digest", sa.String(64), nullable=False),
)


class C7MovementAdmissionError(RuntimeError):
    """Base error for fail-closed verified-candidate admission."""


class C7CandidateRejectedError(C7MovementAdmissionError):
    """Verified candidate identity no longer matches its binding."""


class C7StaleCanonicalRevisionError(C7MovementAdmissionError):
    """Canonical base revision or incarnation is stale."""


class C7CanonicalAbaError(C7MovementAdmissionError):
    """Same object identity now holds different candidate bytes/identity."""


class C7RevokedAuthorityError(C7MovementAdmissionError):
    """Current capability authority is absent, revoked, or drifted."""


class C7CapabilityMismatchError(C7MovementAdmissionError):
    """Admission is bound to a capability other than C7_INGEST_OWNER."""


class C7RuntimeBindingError(C7MovementAdmissionError):
    """Persisted run/step/attempt/event identity drifts from binding/config."""


class C7IdempotencyConflictError(C7MovementAdmissionError):
    """Same idempotency key is already bound to a different exact request."""


class C7OutcomeUnknownError(C7MovementAdmissionError):
    """A commit outcome is unknown; no speculative retry is allowed."""


class C7NoSpeculativeRetryError(C7MovementAdmissionError):
    """Terminal rejection or missing readback forbids a new attempt."""


class C7ReadbackIntegrityError(C7MovementAdmissionError):
    """Authoritative readback detects intent/head/binding/journal drift."""


@dataclass(frozen=True, slots=True)
class C7AdmissionConfig:
    commit_intent_id: str
    run_id: str
    step_id: str
    attempt_id: str
    program_id: str
    plan_id: str
    capability_id: str
    idempotency_key: str
    execution_epoch: int
    attempt_incarnation: str
    assignment_digest: str
    handler_binding_digest: str
    handler_realization_digest: str
    expected_step_revision: int
    expected_attempt_revision: int
    canonical_commit_ref: str
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class C7AdmissionReceipt:
    schema_version: str = C7_ADMISSION_SCHEMA_VERSION
    readback_contract_ref: str = ADMISSION_READBACK_CONTRACT_ID
    commit_intent_id: str = ""
    idempotency_key: str = ""
    capability_id: str = ""
    run_id: str = ""
    step_id: str = ""
    attempt_id: str = ""
    program_digest: str = ""
    plan_digest: str = ""
    canonical_owner: str = ""
    project_key: str = ""
    object_id: str = ""
    expected_base_revision: int = 0
    expected_base_incarnation: str = ""
    committed_revision: int = 0
    committed_incarnation: str = ""
    content_digest: str = ""
    snapshot_identity_digest: str = ""
    raw_content_digest: str = ""
    envelope_digest: str = ""
    payload_content_digest: str = ""
    ordered_source_closure_digest: str = ""
    provenance_closure_digest: str = ""
    decision_digest: str = ""
    candidate_digest: str = ""
    candidate_verification_digest: str = ""
    ordered_event_closure_digest: str = ""
    verification_digest: str = ""
    authority_digest: str = ""
    authority_epoch: int = 0
    canonical_commit_ref: str = ""
    receipt_digest: str = ""
    readback_digest: str = ""
    production_canonical_authority: Literal[False] = False
    live_provider: Literal[False] = False
    promotion: Literal[False] = False
    disposable: Literal[True] = True


@dataclass(frozen=True, slots=True)
class C7AdmissionResult:
    readback: CanonicalCommitReadback
    document_ref: DocumentRef
    receipt: C7AdmissionReceipt


def candidate_evidence_digest(candidate: VerifiedMaterialCandidate) -> str:
    """Close the pure candidate/decision/verification identities as evidence."""

    return content_digest(
        {
            "schema": "mrw.successor.c7.admission.evidence.v1",
            "snapshot_identity_digest": candidate.snapshot_identity_digest,
            "decision_digest": candidate.decision_digest,
            "candidate_digest": candidate.candidate_digest,
            "verification_digest": candidate.verification_digest,
        }
    )


def candidate_provenance_digest(candidate: VerifiedMaterialCandidate) -> str:
    """Close the pure candidate provenance closure into a binding field."""

    return content_digest(
        {
            "schema": "mrw.successor.c7.admission.provenance.v1",
            "provenance_closure_digest": candidate.provenance_closure_digest,
        }
    )


def candidate_receipt_digest(candidate: VerifiedMaterialCandidate) -> str:
    """Close the pure verification profile/receipt into a binding field."""

    return content_digest(
        {
            "schema": "mrw.successor.c7.admission.receipt.v1",
            "verification_profile_ref": candidate.verification_profile_ref,
            "verification_receipt": candidate.verification_receipt,
        }
    )


def _canonical_event_record(record: Mapping[str, object]) -> dict[str, object]:
    """Normalize one caller event record to the canonical row representation."""

    return {
        "seq": int(record["seq"]),
        "event_type": str(record["event_type"]),
        "schema_version": str(record["schema_version"]),
        "step_id": str(record["step_id"]),
        "attempt_id": str(record["attempt_id"]),
        "event_metadata_json": dict(record["event_metadata_json"]),
        "payload_ref": record.get("payload_ref"),
        "payload_digest": record.get("payload_digest"),
        "authority_digest": str(record["authority_digest"]),
    }


def _event_row_record(row: Mapping[str, object]) -> dict[str, object]:
    """Project one canonical ``runtime_events`` row to the shared record shape."""

    return {
        "seq": int(row["seq"]),
        "event_type": str(row["event_type"]),
        "schema_version": str(row["schema_version"]),
        "step_id": str(row["step_id"]) if row["step_id"] is not None else None,
        "attempt_id": str(row["attempt_id"]) if row["attempt_id"] is not None else None,
        "event_metadata_json": dict(row["event_metadata_json"]),
        "payload_ref": row["payload_ref"],
        "payload_digest": row["payload_digest"],
        "authority_digest": str(row["authority_digest"]),
    }


def _require_digest_ref_metadata(metadata: Mapping[str, object]) -> None:
    """Reject any event metadata that is not scalar digest/ref identity data."""

    for key, value in metadata.items():
        normalized = str(key)
        if not normalized.endswith(_DIGEST_REF_METADATA_SUFFIXES):
            raise C7RuntimeBindingError(
                f"event metadata key is not digest/ref identity: {normalized}"
            )
        if isinstance(
            value, (bytes, bytearray, memoryview, dict, list, tuple, set, frozenset)
        ):
            raise C7RuntimeBindingError(
                f"event metadata value is not a scalar digest/ref: {normalized}"
            )
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise C7RuntimeBindingError(
                f"event metadata value type is not scalar: {normalized}"
            )


def _load_journal_events(
    connection: Connection,
    *,
    scope: RuntimeScope,
    config: C7AdmissionConfig,
    expected_seqs: tuple[int, ...] | None = None,
) -> tuple[dict[str, object], ...]:
    table = PUBLIC_TABLES["runtime_events"]
    statement = sa.select(table).where(
        table.c.project_key == scope.project_scope.project_key,
        table.c.run_id == config.run_id,
        table.c.step_id == config.step_id,
        table.c.attempt_id == config.attempt_id,
    )
    if expected_seqs is not None:
        statement = statement.where(table.c.seq.in_(expected_seqs))
    rows = (
        connection.execute(statement.order_by(table.c.seq).with_for_update())
        .mappings()
        .all()
    )
    return tuple(dict(row) for row in rows)


def require_locked_canonical_events(
    connection: Connection,
    *,
    scope: RuntimeScope,
    config: C7AdmissionConfig,
) -> int:
    """Lock the exact canonical event rows for the caller's transaction.

    The ``FOR UPDATE`` lock is held until the caller's outer transaction ends;
    a second validation re-reads the same locked rows without releasing them.
    """

    rows = _load_journal_events(connection, scope=scope, config=config)
    if not rows:
        raise C7RuntimeBindingError("zero canonical runtime events")
    return len(rows)


def _require_run_allocator_fence(
    connection: Connection,
    *,
    scope: RuntimeScope,
    config: C7AdmissionConfig,
    expected_revision: int | None,
    expected_next_event_seq: int | None,
) -> Mapping[str, object]:
    """Lock the run allocator row and bind it to the validated event window."""

    table = PUBLIC_TABLES["runtime_runs"]
    run = (
        connection.execute(
            sa.select(table)
            .where(
                table.c.project_key == scope.project_scope.project_key,
                table.c.run_id == config.run_id,
            )
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if run is None:
        raise C7RuntimeBindingError("persisted runtime run is absent")
    max_event_seq = connection.execute(
        sa.select(sa.func.max(PUBLIC_TABLES["runtime_events"].c.seq)).where(
            PUBLIC_TABLES["runtime_events"].c.project_key
            == scope.project_scope.project_key,
            PUBLIC_TABLES["runtime_events"].c.run_id == config.run_id,
        )
    ).scalar_one_or_none()
    expected_allocator = int(max_event_seq or 0) + 1
    if int(run["next_event_seq"]) != expected_allocator:
        raise C7RuntimeBindingError("runtime run event allocator drift")
    if expected_revision is not None and int(run["revision"]) != expected_revision:
        raise C7RuntimeBindingError(
            "runtime run revision drifted across journal validation"
        )
    if (
        expected_next_event_seq is not None
        and int(run["next_event_seq"]) != expected_next_event_seq
    ):
        raise C7RuntimeBindingError(
            "runtime run next_event_seq drifted across journal validation"
        )
    return run


def _require_journal_event_authority(
    connection: Connection,
    *,
    scope: RuntimeScope,
    config: C7AdmissionConfig,
    binding: VerificationBinding,
    ordered_event_payloads: Sequence[object],
    existing: Mapping[str, object] | None,
    expected_run_revision: int | None = None,
    expected_run_next_event_seq: int | None = None,
) -> None:
    caller_records = [
        _canonical_event_record(record) for record in ordered_event_payloads
    ]
    expected_seqs = tuple(int(record["seq"]) for record in caller_records)
    if not expected_seqs or expected_seqs != tuple(sorted(set(expected_seqs))):
        raise C7RuntimeBindingError(
            "ordered event request seq values must be unique and increasing"
        )
    rows = _load_journal_events(
        connection,
        scope=scope,
        config=config,
        expected_seqs=expected_seqs,
    )
    if not rows:
        raise C7RuntimeBindingError("zero canonical runtime events")
    row_records = [_event_row_record(row) for row in rows]
    if row_records != caller_records:
        if existing is not None:
            raise C7IdempotencyConflictError(
                "canonical event journal differs from the exact request"
            )
        raise C7RuntimeBindingError("canonical event journal drift")
    digests = tuple(event_payload_digest(record) for record in caller_records)
    if (
        digests != binding.ordered_event_payload_digests
        or ordered_event_closure_digest(digests)
        != binding.ordered_event_payload_closure_digest
    ):
        if existing is not None:
            raise C7IdempotencyConflictError(
                "canonical event closure differs from the exact request binding"
            )
        raise C7RuntimeBindingError("canonical event closure drift")
    for record in row_records:
        _require_digest_ref_metadata(record["event_metadata_json"])
    request_events = [
        record
        for record in caller_records
        if record["event_type"] == C7_ADMISSION_REQUEST_EVENT_TYPE
    ]
    if len(request_events) != 1:
        if existing is not None:
            raise C7IdempotencyConflictError(
                "exact-once admission request event is missing or duplicated"
            )
        raise C7RuntimeBindingError("exactly one admission_requested event is required")
    expected_request_metadata = {
        "commit_intent_id": config.commit_intent_id,
        "idempotency_key": config.idempotency_key,
        "canonical_commit_ref": config.canonical_commit_ref,
        "receipt_digest": config.receipt_digest,
        "run_id": config.run_id,
        "step_id": config.step_id,
        "attempt_id": config.attempt_id,
    }
    actual_request_metadata = dict(request_events[0]["event_metadata_json"])
    for field, expected in expected_request_metadata.items():
        if actual_request_metadata.get(field) != expected:
            if existing is not None:
                raise C7IdempotencyConflictError(
                    f"admission request event {field} identity drift"
                )
            raise C7RuntimeBindingError(
                f"admission request event {field} identity drift"
            )
    _require_run_allocator_fence(
        connection,
        scope=scope,
        config=config,
        expected_revision=expected_run_revision,
        expected_next_event_seq=expected_run_next_event_seq,
    )


def _require_candidate_bound_events(
    ordered_event_payloads: Sequence[object],
    candidate: VerifiedMaterialCandidate,
) -> None:
    expected = (
        ("snapshot_identity_digest", candidate.snapshot_identity_digest),
        ("raw_content_digest", candidate.raw_content_digest),
        ("envelope_digest", candidate.envelope_digest),
        ("decision_digest", candidate.decision_digest),
        ("candidate_digest", candidate.candidate_digest),
        ("verification_digest", candidate.verification_digest),
        ("provenance_closure_digest", candidate.provenance_closure_digest),
    )
    found: dict[str, list[str]] = {field: [] for field, _value in expected}
    for event in ordered_event_payloads:
        if not isinstance(event, Mapping):
            continue
        metadata = event.get("event_metadata_json")
        if not isinstance(metadata, Mapping):
            metadata = event.get("payload")
        if not isinstance(metadata, Mapping):
            continue
        for field, value in expected:
            if field in metadata:
                found[field].append(str(metadata[field]))
    for field, value in expected:
        if found[field] != [value]:
            raise C7CandidateRejectedError(
                f"ordered event payload must bind candidate {field} exactly once"
            )


def _require_exact_candidate_binding(
    candidate: VerifiedMaterialCandidate,
    binding: VerificationBinding,
    ordered_event_payloads: Sequence[object],
    *,
    scope: RuntimeScope,
) -> None:
    if not isinstance(candidate, VerifiedMaterialCandidate):
        raise C7CandidateRejectedError(
            "admission requires the concrete pure VerifiedMaterialCandidate"
        )
    if not isinstance(binding, VerificationBinding):
        raise C7CandidateRejectedError(
            "admission requires an exact VerificationBinding"
        )
    try:
        binding.require_exact_ordered_event_payloads(list(ordered_event_payloads))
    except ValueError as exc:
        raise C7CandidateRejectedError("ordered event payload drift") from exc
    _require_candidate_bound_events(ordered_event_payloads, candidate)

    if binding.canonical_owner != DOCUMENT_CANONICAL_OWNER:
        raise C7CandidateRejectedError("canonical owner drift")
    if (
        candidate.provider_calls != 0
        or candidate.canonical_write_authorized is not False
    ):
        raise C7CandidateRejectedError(
            "pure candidate grants provider or canonical write"
        )
    scope_ref = scope.project_scope
    checks = (
        ("project_key", candidate.project_key, binding.project_key),
        ("object_id", candidate.canonical_object_id, binding.canonical_object_id),
        ("actor", candidate.actor, binding.actor_id),
        ("authority_digest", candidate.authority_digest, binding.authority_digest),
        (
            "input_closure",
            candidate.snapshot_identity_digest,
            binding.input_closure_digest,
        ),
        (
            "output_content",
            candidate.payload_content_digest,
            binding.output_content_digest,
        ),
        (
            "evidence",
            candidate_evidence_digest(candidate),
            binding.evidence_digest,
        ),
        (
            "provenance",
            candidate_provenance_digest(candidate),
            binding.provenance_digest,
        ),
        (
            "receipt",
            candidate_receipt_digest(candidate),
            binding.receipt_digest,
        ),
        (
            "project_registry_revision",
            scope_ref.project_registry_revision,
            binding.project_registry_revision,
        ),
        (
            "project_scope_digest",
            scope_ref.scope_digest,
            binding.project_scope_digest,
        ),
        ("resolved_schema", scope_ref.resolved_schema, binding.resolved_schema),
    )
    for field, supplied, expected in checks:
        if supplied != expected:
            raise C7CandidateRejectedError(f"verified candidate/binding {field} drift")
    if (
        candidate.project_key != scope_ref.project_key
        or candidate.expected_base_revision != binding.canonical_base_revision
        or candidate.expected_base_incarnation != binding.canonical_incarnation
        or candidate.actor != scope.actor_id
    ):
        raise C7CandidateRejectedError("verified candidate scope/base/actor drift")


def _require_current_scope(
    connection: Connection, scope: RuntimeScope
) -> Mapping[str, object]:
    try:
        row = ProjectScopeRegistryRepository(connection, scope).load(for_update=True)
    except RecordNotFound as exc:
        raise C7CandidateRejectedError(
            "active project scope registry row is absent"
        ) from exc
    expected = {
        "project_key": scope.project_scope.project_key,
        "resolved_schema": scope.project_scope.resolved_schema,
        "registry_revision": scope.project_scope.project_registry_revision,
        "scope_digest": scope.project_scope.scope_digest,
        "incarnation": scope.project_scope.incarnation,
    }
    for column, value in expected.items():
        if row[column] != value:
            raise C7CandidateRejectedError(f"project scope {column} drift")
    if row["state"] != "ACTIVE":
        raise C7CandidateRejectedError("project scope is not active")
    return row


def require_locked_capability_authority(
    connection: Connection,
    scope: RuntimeScope,
    candidate: VerifiedMaterialCandidate,
) -> Mapping[str, object]:
    """Lock and revalidate the single C7 capability authority row."""

    try:
        row = CapabilityAuthorityRepository(connection, scope).load(
            C7_INGEST_OWNER,
            for_update=True,
        )
    except RecordNotFound as exc:
        raise C7RevokedAuthorityError("capability authority is absent") from exc
    if (
        row["mode"] == "off"
        or not row["successor_claim_enabled"]
        or row["legacy_claim_enabled"]
    ):
        raise C7RevokedAuthorityError("capability authority is revoked")
    if int(row["authority_epoch"]) != candidate.authority_epoch:
        raise C7RevokedAuthorityError("capability authority epoch drift")
    if row["config_digest"] != candidate.authority_digest:
        raise C7RevokedAuthorityError("capability authority digest drift")
    return row


def _load_persisted_runtime(
    connection: Connection,
    *,
    scope: RuntimeScope,
    candidate: VerifiedMaterialCandidate,
    binding: VerificationBinding,
    config: C7AdmissionConfig,
    for_update: bool,
) -> tuple[Mapping[str, object], Mapping[str, object], Mapping[str, object]]:
    if config.capability_id != C7_INGEST_OWNER:
        raise C7CapabilityMismatchError(
            "admission capability must be exactly C7_INGEST_OWNER"
        )
    if binding.step_id != config.step_id:
        raise C7RuntimeBindingError("binding step_id does not equal config step_id")
    if binding.attempt_id != config.attempt_id:
        raise C7RuntimeBindingError(
            "binding attempt_id does not equal config attempt_id"
        )
    project_key = scope.project_scope.project_key
    run = (
        connection.execute(
            sa.select(PUBLIC_TABLES["runtime_runs"])
            .where(
                PUBLIC_TABLES["runtime_runs"].c.project_key == project_key,
                PUBLIC_TABLES["runtime_runs"].c.run_id == config.run_id,
            )
            .with_for_update()
            if for_update
            else sa.select(PUBLIC_TABLES["runtime_runs"]).where(
                PUBLIC_TABLES["runtime_runs"].c.project_key == project_key,
                PUBLIC_TABLES["runtime_runs"].c.run_id == config.run_id,
            )
        )
        .mappings()
        .one_or_none()
    )
    if run is None:
        raise C7RuntimeBindingError("persisted runtime run is absent")
    run_checks = (
        ("program_id", run["program_id"], config.program_id),
        ("program_digest", run["program_digest"], binding.program_digest),
        ("plan_id", run["plan_id"], config.plan_id),
        ("plan_digest", run["plan_digest"], binding.plan_digest),
        (
            "project_registry_revision",
            int(run["project_registry_revision"]),
            scope.project_scope.project_registry_revision,
        ),
        (
            "project_scope_digest",
            run["project_scope_digest"],
            scope.project_scope.scope_digest,
        ),
        (
            "resolved_schema",
            run["resolved_schema"],
            scope.project_scope.resolved_schema,
        ),
    )
    for field, supplied, expected in run_checks:
        if supplied != expected:
            raise C7RuntimeBindingError(f"persisted runtime run {field} drift")

    step_statement = sa.select(PUBLIC_TABLES["runtime_steps"]).where(
        PUBLIC_TABLES["runtime_steps"].c.project_key == project_key,
        PUBLIC_TABLES["runtime_steps"].c.run_id == config.run_id,
        PUBLIC_TABLES["runtime_steps"].c.step_id == config.step_id,
    )
    if for_update:
        step_statement = step_statement.with_for_update()
    step = connection.execute(step_statement).mappings().one_or_none()
    if step is None:
        raise C7RuntimeBindingError("persisted runtime step is absent")
    if step["capability_id"] != C7_INGEST_OWNER:
        raise C7CapabilityMismatchError(
            "persisted step capability is not C7_INGEST_OWNER"
        )
    if step["state"] != "RUNNING":
        raise C7RuntimeBindingError("persisted step is not RUNNING")
    if int(step["revision"]) != int(config.expected_step_revision):
        raise C7RuntimeBindingError("persisted step revision drift")
    if int(step["execution_epoch"]) != int(config.execution_epoch):
        raise C7RuntimeBindingError("persisted step execution epoch drift")
    if step["claim_owner"] != "successor":
        raise C7RuntimeBindingError("persisted step claim owner drift")
    if int(step["claim_authority_epoch"]) != candidate.authority_epoch:
        raise C7RuntimeBindingError("persisted step claim authority epoch drift")
    if step["claim_policy_digest"] != binding.authority_digest:
        raise C7RuntimeBindingError("persisted step claim policy digest drift")

    attempt_statement = sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
        PUBLIC_TABLES["runtime_effect_attempts"].c.project_key == project_key,
        PUBLIC_TABLES["runtime_effect_attempts"].c.attempt_id == config.attempt_id,
    )
    if for_update:
        attempt_statement = attempt_statement.with_for_update()
    attempt = connection.execute(attempt_statement).mappings().one_or_none()
    if attempt is None:
        raise C7RuntimeBindingError("persisted effect attempt is absent")
    if attempt["disposition"] != "IN_FLIGHT":
        raise C7RuntimeBindingError("persisted effect attempt is not IN_FLIGHT")
    attempt_checks = (
        ("run_id", attempt["run_id"], config.run_id),
        ("step_id", attempt["step_id"], config.step_id),
        ("idempotency_key", attempt["idempotency_key"], config.idempotency_key),
        ("revision", int(attempt["revision"]), int(config.expected_attempt_revision)),
        (
            "execution_epoch",
            int(attempt["execution_epoch"]),
            int(config.execution_epoch),
        ),
        ("incarnation", attempt["incarnation"], config.attempt_incarnation),
        ("assignment_digest", attempt["assignment_digest"], config.assignment_digest),
        (
            "handler_binding_digest",
            attempt["handler_binding_digest"],
            config.handler_binding_digest,
        ),
        (
            "handler_realization_digest",
            attempt["handler_realization_digest"],
            config.handler_realization_digest,
        ),
        ("input_digest", attempt["input_digest"], binding.input_closure_digest),
        (
            "authorization_digest",
            attempt["authorization_digest"],
            binding.authority_digest,
        ),
    )
    for field, supplied, expected in attempt_checks:
        if supplied != expected:
            raise C7RuntimeBindingError(f"persisted effect attempt {field} drift")
    return run, step, attempt


def require_locked_runtime_step_attempt(
    connection: Connection,
    *,
    scope: RuntimeScope,
    candidate: VerifiedMaterialCandidate,
    binding: VerificationBinding,
    config: C7AdmissionConfig,
) -> Mapping[str, object]:
    """Lock and revalidate the admission step and its effect attempt."""

    if config.handler_binding_digest != config.handler_realization_digest:
        raise C7RuntimeBindingError(
            "config handler binding and realization digests must be equal"
        )
    run, _step, _attempt = _load_persisted_runtime(
        connection,
        scope=scope,
        candidate=candidate,
        binding=binding,
        config=config,
        for_update=True,
    )
    return run


def _canonical_head(
    connection: Connection,
    scope: RuntimeScope,
    object_id: str,
    *,
    for_update: bool = False,
) -> dict[str, object] | None:
    statement = sa.select(C7_MOVEMENT_CANONICAL_DOCUMENTS).where(
        C7_MOVEMENT_CANONICAL_DOCUMENTS.c.project_key
        == scope.project_scope.project_key,
        C7_MOVEMENT_CANONICAL_DOCUMENTS.c.object_id == object_id,
    )
    if for_update:
        statement = statement.with_for_update()
    row = connection.execute(statement).mappings().one_or_none()
    return None if row is None else dict(row)


def _head_closure_digest(head: Mapping[str, object]) -> str:
    fields = {key: value for key, value in head.items() if key != "head_closure_digest"}
    return canonical_digest(fields)


def _reconstruct_candidate(head: Mapping[str, object]) -> VerifiedMaterialCandidate:
    try:
        return VerifiedMaterialCandidate(
            candidate_id=str(head["candidate_id"]),
            candidate_digest=str(head["candidate_digest"]),
            envelope_digest=str(head["envelope_digest"]),
            snapshot_ref=str(head["snapshot_ref"]),
            snapshot_identity_digest=str(head["snapshot_identity_digest"]),
            raw_content_digest=str(head["raw_content_digest"]),
            payload_content_digest=str(head["payload_content_digest"]),
            ordered_source_closure_digest=str(head["ordered_source_closure_digest"]),
            provenance_closure_digest=str(head["provenance_closure_digest"]),
            decision_digest=str(head["decision_digest"]),
            alternative=str(head["alternative"]),
            project_key=str(head["project_key"]),
            canonical_object_id=str(head["object_id"]),
            expected_base_revision=int(head["expected_base_revision"]),
            expected_base_incarnation=str(head["expected_base_incarnation"]),
            actor=str(head["actor_id"]),
            authority_digest=str(head["authority_digest"]),
            authority_epoch=int(head["authority_epoch"]),
            verification_profile_ref=str(head["verification_profile_ref"]),
            verification_receipt=str(head["verification_receipt"]),
            verification_digest=str(head["candidate_verification_digest"]),
        )
    except (TypeError, ValueError) as exc:
        raise C7ReadbackIntegrityError(
            "canonical head cannot reconstruct the pure verified candidate"
        ) from exc


def _head_matches(
    candidate: VerifiedMaterialCandidate,
    binding: VerificationBinding,
    config: C7AdmissionConfig,
    head: Mapping[str, object],
    value_ref: C7StructuredValueRef,
) -> bool:
    return (
        head["commit_intent_id"] == config.commit_intent_id
        and head["canonical_owner"] == DOCUMENT_CANONICAL_OWNER
        and head["run_id"] == config.run_id
        and head["step_id"] == config.step_id
        and head["attempt_id"] == config.attempt_id
        and head["capability_id"] == C7_INGEST_OWNER
        and head["actor_id"] == candidate.actor
        and head["program_digest"] == binding.program_digest
        and head["plan_digest"] == binding.plan_digest
        and int(head["step_revision"]) == int(config.expected_step_revision)
        and int(head["attempt_revision"]) == int(config.expected_attempt_revision)
        and int(head["execution_epoch"]) == int(config.execution_epoch)
        and head["attempt_incarnation"] == config.attempt_incarnation
        and head["assignment_digest"] == config.assignment_digest
        and head["handler_binding_digest"] == config.handler_binding_digest
        and head["handler_realization_digest"] == config.handler_realization_digest
        and head["input_closure_digest"] == binding.input_closure_digest
        and int(head["revision"]) == candidate.expected_base_revision + 1
        and head["incarnation"] == candidate.expected_base_incarnation
        and int(head["expected_base_revision"]) == candidate.expected_base_revision
        and head["expected_base_incarnation"] == candidate.expected_base_incarnation
        and head["content_digest"] == candidate.payload_content_digest
        and head["snapshot_identity_digest"] == candidate.snapshot_identity_digest
        and head["raw_content_digest"] == candidate.raw_content_digest
        and head["envelope_digest"] == candidate.envelope_digest
        and head["payload_content_digest"] == candidate.payload_content_digest
        and head["ordered_source_closure_digest"]
        == candidate.ordered_source_closure_digest
        and head["provenance_closure_digest"] == candidate.provenance_closure_digest
        and head["decision_digest"] == candidate.decision_digest
        and head["candidate_digest"] == candidate.candidate_digest
        and head["candidate_verification_digest"] == candidate.verification_digest
        and head["ordered_event_closure_digest"]
        == binding.ordered_event_payload_closure_digest
        and head["verification_digest"] == binding.binding_digest
        and head["authority_digest"] == candidate.authority_digest
        and int(head["authority_epoch"]) == candidate.authority_epoch
        and head["candidate_id"] == candidate.candidate_id
        and head["snapshot_ref"] == candidate.snapshot_ref
        and head["alternative"] == candidate.alternative
        and head["verification_profile_ref"] == candidate.verification_profile_ref
        and head["verification_receipt"] == candidate.verification_receipt
        and head["evidence_digest"] == candidate_evidence_digest(candidate)
        and head["provenance_digest"] == candidate_provenance_digest(candidate)
        and head["candidate_receipt_digest"] == candidate_receipt_digest(candidate)
        and head["value_ref"] == value_ref.value_ref
        and int(head["value_revision"]) == value_ref.revision
        and head["value_incarnation"] == value_ref.incarnation
        and head["value_digest"] == value_ref.content_digest
        and head["value_provenance_digest"] == value_ref.provenance_digest
        and str(head["head_closure_digest"]) == _head_closure_digest(head)
    )


def build_commit_binding(
    candidate: VerifiedMaterialCandidate,
    *,
    config: C7AdmissionConfig,
    binding: VerificationBinding,
) -> CommitIntentBinding:
    return CommitIntentBinding(
        commit_intent_id=config.commit_intent_id,
        run_id=config.run_id,
        step_id=config.step_id,
        capability_id=C7_INGEST_OWNER,
        canonical_owner_ref=DOCUMENT_CANONICAL_OWNER,
        object_identity_ref=candidate.canonical_object_id,
        expected_base_revision=candidate.expected_base_revision,
        expected_base_incarnation=candidate.expected_base_incarnation,
        content_digest=candidate.payload_content_digest,
        event_digest=binding.ordered_event_payload_closure_digest,
        verification_digest=binding.binding_digest,
        authority_digest=candidate.authority_digest,
        idempotency_key=config.idempotency_key,
    )


def build_commit_intent(
    candidate: VerifiedMaterialCandidate,
    *,
    config: C7AdmissionConfig,
    scope: RuntimeScope,
    binding: VerificationBinding,
) -> CommitIntent:
    return CommitIntent(
        commit_intent_id=config.commit_intent_id,
        canonical_owner=DOCUMENT_CANONICAL_OWNER,
        project_key=candidate.project_key,
        object_id=candidate.canonical_object_id,
        project_registry_revision=scope.project_scope.project_registry_revision,
        project_scope_digest=scope.project_scope.scope_digest,
        expected_base_revision=candidate.expected_base_revision,
        expected_incarnation=candidate.expected_base_incarnation,
        content_digest=candidate.payload_content_digest,
        ordered_event_closure_digest=binding.ordered_event_payload_closure_digest,
        verification_binding_digest=binding.binding_digest,
        authority_digest=candidate.authority_digest,
        idempotency_key=config.idempotency_key,
        state=CommitIntentState.PREPARED,
    )


def _load_commit_intent(
    connection: Connection,
    scope: RuntimeScope,
    config: C7AdmissionConfig,
) -> dict[str, object] | None:
    try:
        row = CommitIntentRepository(connection, scope).find_for_readback(
            config.capability_id,
            config.idempotency_key,
        )
    except RecordNotFound:
        return None
    return dict(row)


def _insert_canonical_head(
    connection: Connection,
    *,
    scope: RuntimeScope,
    candidate: VerifiedMaterialCandidate,
    binding: VerificationBinding,
    config: C7AdmissionConfig,
    value_ref: C7StructuredValueRef,
) -> None:
    values: dict[str, object] = {
        "project_key": scope.project_scope.project_key,
        "object_id": candidate.canonical_object_id,
        "commit_intent_id": config.commit_intent_id,
        "canonical_owner": DOCUMENT_CANONICAL_OWNER,
        "run_id": config.run_id,
        "step_id": config.step_id,
        "attempt_id": config.attempt_id,
        "capability_id": C7_INGEST_OWNER,
        "actor_id": candidate.actor,
        "program_digest": binding.program_digest,
        "plan_digest": binding.plan_digest,
        "step_revision": int(config.expected_step_revision),
        "attempt_revision": int(config.expected_attempt_revision),
        "execution_epoch": int(config.execution_epoch),
        "attempt_incarnation": config.attempt_incarnation,
        "assignment_digest": config.assignment_digest,
        "handler_binding_digest": config.handler_binding_digest,
        "handler_realization_digest": config.handler_realization_digest,
        "input_closure_digest": binding.input_closure_digest,
        "revision": candidate.expected_base_revision + 1,
        "incarnation": candidate.expected_base_incarnation,
        "expected_base_revision": candidate.expected_base_revision,
        "expected_base_incarnation": candidate.expected_base_incarnation,
        "content_digest": candidate.payload_content_digest,
        "snapshot_identity_digest": candidate.snapshot_identity_digest,
        "raw_content_digest": candidate.raw_content_digest,
        "envelope_digest": candidate.envelope_digest,
        "payload_content_digest": candidate.payload_content_digest,
        "ordered_source_closure_digest": candidate.ordered_source_closure_digest,
        "provenance_closure_digest": candidate.provenance_closure_digest,
        "decision_digest": candidate.decision_digest,
        "candidate_digest": candidate.candidate_digest,
        "candidate_verification_digest": candidate.verification_digest,
        "ordered_event_closure_digest": binding.ordered_event_payload_closure_digest,
        "verification_digest": binding.binding_digest,
        "authority_digest": candidate.authority_digest,
        "authority_epoch": candidate.authority_epoch,
        "candidate_id": candidate.candidate_id,
        "snapshot_ref": candidate.snapshot_ref,
        "alternative": candidate.alternative,
        "verification_profile_ref": candidate.verification_profile_ref,
        "verification_receipt": candidate.verification_receipt,
        "evidence_digest": candidate_evidence_digest(candidate),
        "provenance_digest": candidate_provenance_digest(candidate),
        "candidate_receipt_digest": candidate_receipt_digest(candidate),
        "value_ref": value_ref.value_ref,
        "value_revision": int(value_ref.revision),
        "value_incarnation": value_ref.incarnation,
        "value_digest": value_ref.content_digest,
        "value_provenance_digest": value_ref.provenance_digest,
        "canonical_commit_ref": config.canonical_commit_ref,
        "receipt_digest": config.receipt_digest,
    }
    values["head_closure_digest"] = _head_closure_digest(values)
    connection.execute(C7_MOVEMENT_CANONICAL_DOCUMENTS.insert().values(**values))


def _finalize_commit_intent(
    connection: Connection,
    scope: RuntimeScope,
    config: C7AdmissionConfig,
) -> None:
    repo = CommitIntentRepository(connection, scope)
    try:
        repo.record_result(
            config.commit_intent_id,
            expected_revision=0,
            status=CommitIntentStatus.COMMITTED,
            canonical_commit_ref=config.canonical_commit_ref,
            receipt_digest=config.receipt_digest,
        )
    except StaleRevisionError as exc:
        raise C7OutcomeUnknownError(
            "commit intent CAS failed after canonical head write"
        ) from exc


def _require_intent_head_closure(
    intent: Mapping[str, object],
    head: Mapping[str, object],
    binding: VerificationBinding,
    candidate: VerifiedMaterialCandidate,
) -> None:
    if str(head["head_closure_digest"]) != _head_closure_digest(head):
        raise C7ReadbackIntegrityError("canonical head closure digest mismatch")
    checks = (
        ("commit_intent_id", intent["commit_intent_id"], head["commit_intent_id"]),
        ("project_key", intent["project_key"], head["project_key"]),
        ("object_id", intent["object_identity_ref"], head["object_id"]),
        ("canonical_owner", intent["canonical_owner_ref"], head["canonical_owner"]),
        ("capability_id", intent["capability_id"], head["capability_id"]),
        ("run_id", intent["run_id"], head["run_id"]),
        ("step_id", intent["step_id"], head["step_id"]),
        (
            "expected_base_revision",
            intent["expected_base_revision"],
            head["expected_base_revision"],
        ),
        (
            "expected_base_incarnation",
            intent["expected_base_incarnation"],
            head["expected_base_incarnation"],
        ),
        ("content_digest", intent["content_digest"], head["content_digest"]),
        (
            "ordered_event_closure_digest",
            intent["event_digest"],
            head["ordered_event_closure_digest"],
        ),
        (
            "verification_digest",
            intent["verification_digest"],
            head["verification_digest"],
        ),
        ("authority_digest", intent["authority_digest"], head["authority_digest"]),
        (
            "canonical_commit_ref",
            intent["canonical_commit_ref"],
            head["canonical_commit_ref"],
        ),
        ("receipt_digest", intent["receipt_digest"], head["receipt_digest"]),
    )
    for field, intent_value, head_value in checks:
        if intent_value != head_value:
            raise C7ReadbackIntegrityError(
                f"canonical head {field} does not match committed intent"
            )
    if int(head["revision"]) != int(head["expected_base_revision"]) + 1:
        raise C7ReadbackIntegrityError(
            "canonical head revision does not follow the expected base"
        )
    binding_checks = (
        ("program_digest", head["program_digest"], binding.program_digest),
        ("plan_digest", head["plan_digest"], binding.plan_digest),
        ("step_id", head["step_id"], binding.step_id),
        ("attempt_id", head["attempt_id"], binding.attempt_id),
        ("actor_id", head["actor_id"], binding.actor_id),
        ("authority_digest", head["authority_digest"], binding.authority_digest),
        (
            "ordered_event_closure_digest",
            head["ordered_event_closure_digest"],
            binding.ordered_event_payload_closure_digest,
        ),
        ("verification_digest", head["verification_digest"], binding.binding_digest),
        ("capability_id", head["capability_id"], C7_INGEST_OWNER),
        (
            "input_closure_digest",
            head["input_closure_digest"],
            binding.input_closure_digest,
        ),
    )
    for field, head_value, expected in binding_checks:
        if head_value != expected:
            raise C7ReadbackIntegrityError(
                f"canonical head {field} does not match VerificationBinding"
            )
    pure_checks = (
        ("candidate_id", head["candidate_id"], candidate.candidate_id),
        ("snapshot_ref", head["snapshot_ref"], candidate.snapshot_ref),
        ("alternative", head["alternative"], candidate.alternative),
        (
            "verification_profile_ref",
            head["verification_profile_ref"],
            candidate.verification_profile_ref,
        ),
        (
            "verification_receipt",
            head["verification_receipt"],
            candidate.verification_receipt,
        ),
        (
            "snapshot_identity_digest",
            head["snapshot_identity_digest"],
            candidate.snapshot_identity_digest,
        ),
        (
            "raw_content_digest",
            head["raw_content_digest"],
            candidate.raw_content_digest,
        ),
        ("envelope_digest", head["envelope_digest"], candidate.envelope_digest),
        (
            "payload_content_digest",
            head["payload_content_digest"],
            candidate.payload_content_digest,
        ),
        (
            "ordered_source_closure_digest",
            head["ordered_source_closure_digest"],
            candidate.ordered_source_closure_digest,
        ),
        (
            "provenance_closure_digest",
            head["provenance_closure_digest"],
            candidate.provenance_closure_digest,
        ),
        ("decision_digest", head["decision_digest"], candidate.decision_digest),
        ("candidate_digest", head["candidate_digest"], candidate.candidate_digest),
        (
            "candidate_verification_digest",
            head["candidate_verification_digest"],
            candidate.verification_digest,
        ),
        (
            "authority_epoch",
            int(head["authority_epoch"]),
            candidate.authority_epoch,
        ),
        (
            "expected_base_revision",
            int(head["expected_base_revision"]),
            candidate.expected_base_revision,
        ),
        (
            "expected_base_incarnation",
            head["expected_base_incarnation"],
            candidate.expected_base_incarnation,
        ),
        ("canonical_object_id", head["object_id"], candidate.canonical_object_id),
        ("actor_id", head["actor_id"], candidate.actor),
        ("authority_digest", head["authority_digest"], candidate.authority_digest),
        ("content_digest", head["content_digest"], candidate.payload_content_digest),
    )
    for field, head_value, expected in pure_checks:
        if head_value != expected:
            raise C7ReadbackIntegrityError(
                f"canonical head {field} does not match reconstructed candidate"
            )
    expected_evidence = candidate_evidence_digest(candidate)
    expected_provenance = candidate_provenance_digest(candidate)
    expected_receipt = candidate_receipt_digest(candidate)
    closure_checks = (
        (
            "evidence",
            head["evidence_digest"],
            expected_evidence,
            binding.evidence_digest,
        ),
        (
            "provenance",
            head["provenance_digest"],
            expected_provenance,
            binding.provenance_digest,
        ),
        (
            "candidate_receipt",
            head["candidate_receipt_digest"],
            expected_receipt,
            binding.receipt_digest,
        ),
    )
    for field, head_value, expected, binding_value in closure_checks:
        if head_value != expected or expected != binding_value:
            raise C7ReadbackIntegrityError(
                f"canonical head {field} digest does not close candidate/binding"
            )


def _require_head_runtime_closure(
    connection: Connection,
    head: Mapping[str, object],
) -> None:
    """Cross-check head historical runtime closure against current rows."""

    project_key = str(head["project_key"])
    step = (
        connection.execute(
            sa.select(PUBLIC_TABLES["runtime_steps"]).where(
                PUBLIC_TABLES["runtime_steps"].c.project_key == project_key,
                PUBLIC_TABLES["runtime_steps"].c.run_id == head["run_id"],
                PUBLIC_TABLES["runtime_steps"].c.step_id == head["step_id"],
            )
        )
        .mappings()
        .one_or_none()
    )
    if step is None:
        raise C7ReadbackIntegrityError(
            "canonical head step has no persisted runtime step"
        )
    if int(step["revision"]) != int(head["step_revision"]) or int(
        step["execution_epoch"]
    ) != int(head["execution_epoch"]):
        raise C7ReadbackIntegrityError(
            "canonical head step closure does not match persisted step"
        )
    attempt = (
        connection.execute(
            sa.select(PUBLIC_TABLES["runtime_effect_attempts"]).where(
                PUBLIC_TABLES["runtime_effect_attempts"].c.project_key == project_key,
                PUBLIC_TABLES["runtime_effect_attempts"].c.attempt_id
                == head["attempt_id"],
            )
        )
        .mappings()
        .one_or_none()
    )
    if attempt is None:
        raise C7ReadbackIntegrityError(
            "canonical head attempt has no persisted effect attempt"
        )
    attempt_checks = (
        ("revision", int(attempt["revision"]), int(head["attempt_revision"])),
        (
            "execution_epoch",
            int(attempt["execution_epoch"]),
            int(head["execution_epoch"]),
        ),
        ("incarnation", attempt["incarnation"], head["attempt_incarnation"]),
        ("assignment_digest", attempt["assignment_digest"], head["assignment_digest"]),
        (
            "handler_binding_digest",
            attempt["handler_binding_digest"],
            head["handler_binding_digest"],
        ),
        (
            "handler_realization_digest",
            attempt["handler_realization_digest"],
            head["handler_realization_digest"],
        ),
        ("input_digest", attempt["input_digest"], head["input_closure_digest"]),
        (
            "authorization_digest",
            attempt["authorization_digest"],
            head["authority_digest"],
        ),
    )
    for field, attempt_value, expected in attempt_checks:
        if attempt_value != expected:
            raise C7ReadbackIntegrityError(
                f"canonical head attempt {field} does not match persisted attempt"
            )


def _readback_digest(
    intent: Mapping[str, object],
    head: Mapping[str, object],
) -> str:
    return canonical_digest(
        {
            "schema_version": C7_ADMISSION_SCHEMA_VERSION,
            "readback_contract_ref": ADMISSION_READBACK_CONTRACT_ID,
            "commit_intent_id": str(intent["commit_intent_id"]),
            "idempotency_key": str(intent["idempotency_key"]),
            "capability_id": str(head["capability_id"]),
            "run_id": str(head["run_id"]),
            "step_id": str(head["step_id"]),
            "attempt_id": str(head["attempt_id"]),
            "program_digest": str(head["program_digest"]),
            "plan_digest": str(head["plan_digest"]),
            "step_revision": int(head["step_revision"]),
            "attempt_revision": int(head["attempt_revision"]),
            "execution_epoch": int(head["execution_epoch"]),
            "attempt_incarnation": str(head["attempt_incarnation"]),
            "assignment_digest": str(head["assignment_digest"]),
            "handler_binding_digest": str(head["handler_binding_digest"]),
            "handler_realization_digest": str(head["handler_realization_digest"]),
            "input_closure_digest": str(head["input_closure_digest"]),
            "canonical_owner": str(head["canonical_owner"]),
            "project_key": str(head["project_key"]),
            "object_id": str(head["object_id"]),
            "expected_base_revision": int(head["expected_base_revision"]),
            "expected_base_incarnation": str(head["expected_base_incarnation"]),
            "committed_revision": int(head["revision"]),
            "committed_incarnation": str(head["incarnation"]),
            "content_digest": str(head["content_digest"]),
            "snapshot_identity_digest": str(head["snapshot_identity_digest"]),
            "raw_content_digest": str(head["raw_content_digest"]),
            "envelope_digest": str(head["envelope_digest"]),
            "payload_content_digest": str(head["payload_content_digest"]),
            "ordered_source_closure_digest": str(head["ordered_source_closure_digest"]),
            "provenance_closure_digest": str(head["provenance_closure_digest"]),
            "decision_digest": str(head["decision_digest"]),
            "candidate_digest": str(head["candidate_digest"]),
            "candidate_verification_digest": str(head["candidate_verification_digest"]),
            "ordered_event_closure_digest": str(head["ordered_event_closure_digest"]),
            "verification_digest": str(head["verification_digest"]),
            "authority_digest": str(head["authority_digest"]),
            "authority_epoch": int(head["authority_epoch"]),
            "value_ref": str(head["value_ref"]),
            "value_revision": int(head["value_revision"]),
            "value_incarnation": str(head["value_incarnation"]),
            "value_digest": str(head["value_digest"]),
            "value_provenance_digest": str(head["value_provenance_digest"]),
            "canonical_commit_ref": str(head["canonical_commit_ref"]),
            "receipt_digest": str(head["receipt_digest"]),
        }
    )


def _readback_committed(
    connection: Connection,
    *,
    scope: RuntimeScope,
    intent: Mapping[str, object],
    binding: VerificationBinding,
    verify_current_runtime: bool,
) -> C7AdmissionResult:
    head = _canonical_head(connection, scope, str(intent["object_identity_ref"]))
    if head is None:
        raise C7OutcomeUnknownError("committed intent has no canonical head")
    candidate = _reconstruct_candidate(head)
    _require_intent_head_closure(intent, head, binding, candidate)
    if verify_current_runtime:
        _require_head_runtime_closure(connection, head)
    try:
        readback_candidate_value(
            connection,
            scope=scope,
            head=head,
            candidate=candidate,
        )
    except C7ValueHandoffError as exc:
        raise C7ReadbackIntegrityError(
            f"canonical head value closure failed: {exc}"
        ) from exc
    readback = CanonicalCommitReadback(
        commit_intent_id=str(intent["commit_intent_id"]),
        idempotency_key=str(intent["idempotency_key"]),
        capability_id=str(intent["capability_id"]),
        project_key=str(head["project_key"]),
        object_id=str(head["object_id"]),
        committed_revision=int(head["revision"]),
        committed_incarnation=str(head["incarnation"]),
        content_digest=str(head["content_digest"]),
        canonical_commit_ref=str(head["canonical_commit_ref"]),
    )
    receipt = C7AdmissionReceipt(
        commit_intent_id=str(intent["commit_intent_id"]),
        idempotency_key=str(intent["idempotency_key"]),
        capability_id=str(intent["capability_id"]),
        run_id=str(head["run_id"]),
        step_id=str(head["step_id"]),
        attempt_id=str(head["attempt_id"]),
        program_digest=str(head["program_digest"]),
        plan_digest=str(head["plan_digest"]),
        canonical_owner=str(head["canonical_owner"]),
        project_key=str(head["project_key"]),
        object_id=str(head["object_id"]),
        expected_base_revision=int(head["expected_base_revision"]),
        expected_base_incarnation=str(head["expected_base_incarnation"]),
        committed_revision=int(head["revision"]),
        committed_incarnation=str(head["incarnation"]),
        content_digest=str(head["content_digest"]),
        snapshot_identity_digest=str(head["snapshot_identity_digest"]),
        raw_content_digest=str(head["raw_content_digest"]),
        envelope_digest=str(head["envelope_digest"]),
        payload_content_digest=str(head["payload_content_digest"]),
        ordered_source_closure_digest=str(head["ordered_source_closure_digest"]),
        provenance_closure_digest=str(head["provenance_closure_digest"]),
        decision_digest=str(head["decision_digest"]),
        candidate_digest=str(head["candidate_digest"]),
        candidate_verification_digest=str(head["candidate_verification_digest"]),
        ordered_event_closure_digest=str(head["ordered_event_closure_digest"]),
        verification_digest=str(head["verification_digest"]),
        authority_digest=str(head["authority_digest"]),
        authority_epoch=int(head["authority_epoch"]),
        canonical_commit_ref=str(head["canonical_commit_ref"]),
        receipt_digest=str(head["receipt_digest"]),
        readback_digest=_readback_digest(intent, head),
    )
    return C7AdmissionResult(
        readback=readback,
        document_ref=document_ref_from_readback(readback),
        receipt=receipt,
    )


def load_authoritative_readback(
    connection: Connection,
    *,
    scope: RuntimeScope,
    config: C7AdmissionConfig,
    binding: VerificationBinding,
) -> C7AdmissionResult:
    """Exact-request readback; the caller config must match the stored fact."""

    intent = _load_commit_intent(connection, scope, config)
    if intent is None or intent["state"] != CommitIntentStatus.COMMITTED.value:
        raise C7OutcomeUnknownError(
            "authoritative readback requires a committed commit intent"
        )
    if (
        str(intent["commit_intent_id"]) != config.commit_intent_id
        or intent["canonical_commit_ref"] != config.canonical_commit_ref
        or intent["receipt_digest"] != config.receipt_digest
    ):
        raise C7IdempotencyConflictError(
            "exact request readback identity does not match stored intent"
        )
    return _readback_committed(
        connection,
        scope=scope,
        intent=intent,
        binding=binding,
        verify_current_runtime=True,
    )


def readback_by_idempotency(
    connection: Connection,
    *,
    scope: RuntimeScope,
    capability_id: str,
    idempotency_key: str,
    binding: VerificationBinding,
) -> C7AdmissionResult:
    """Stored-fact readback keyed only by capability and idempotency."""

    if capability_id != C7_INGEST_OWNER:
        raise C7CapabilityMismatchError(
            "readback capability must be exactly C7_INGEST_OWNER"
        )
    try:
        intent = CommitIntentRepository(connection, scope).find_for_readback(
            capability_id,
            idempotency_key,
        )
    except RecordNotFound as exc:
        raise C7OutcomeUnknownError(
            "readback intent not found for capability/idempotency"
        ) from exc
    if intent["state"] != CommitIntentStatus.COMMITTED.value:
        raise C7OutcomeUnknownError("readback requires a committed commit intent")
    return _readback_committed(
        connection,
        scope=scope,
        intent=dict(intent),
        binding=binding,
        verify_current_runtime=False,
    )


def admit_verified_candidate(
    connection: Connection,
    structured_candidate: StructuredMaterialCandidate,
    verified_candidate: VerifiedMaterialCandidate,
    binding: VerificationBinding,
    ordered_event_payloads: Sequence[object],
    *,
    config: C7AdmissionConfig,
    scope: RuntimeScope,
) -> C7AdmissionResult:
    """Prepare, commit, and authoritatively read back one verified candidate.

    The caller owns the transaction.  On any failure the caller must roll back
    the connection; the canonical mutation additionally runs inside an
    interpreter-owned savepoint so a caught finalize fault leaves zero rows
    even when the caller commits the outer transaction.
    """

    try:
        require_exact_candidate_pair(structured_candidate, verified_candidate)
    except C7ValueIntegrityError as exc:
        raise C7CandidateRejectedError(
            f"structured/verified candidate pair drift: {exc}"
        ) from exc
    _require_exact_candidate_binding(
        verified_candidate,
        binding,
        ordered_event_payloads,
        scope=scope,
    )
    committed = _load_commit_intent(connection, scope, config)
    if committed is not None:
        committed_state = str(committed["state"])
        if committed_state == CommitIntentStatus.UNKNOWN.value:
            raise C7OutcomeUnknownError(
                "commit outcome is unknown; no speculative retry is allowed"
            )
        if committed_state == CommitIntentStatus.REJECTED.value:
            raise C7NoSpeculativeRetryError(
                "commit intent is terminally rejected; no new attempt is allowed"
            )
        if committed_state == CommitIntentStatus.COMMITTED.value:
            commit_binding = build_commit_binding(
                verified_candidate,
                config=config,
                binding=binding,
            )
            try:
                CommitIntentRepository(connection, scope).prepare(commit_binding)
            except ExactBindingConflict as exc:
                raise C7IdempotencyConflictError(
                    "commit idempotency key is already bound to a different exact "
                    "request"
                ) from exc
            if (
                str(committed["commit_intent_id"]) != config.commit_intent_id
                or committed["canonical_commit_ref"] != config.canonical_commit_ref
                or committed["receipt_digest"] != config.receipt_digest
            ):
                raise C7IdempotencyConflictError(
                    "committed intent exact request identity drift"
                )
            _require_journal_event_authority(
                connection,
                scope=scope,
                config=config,
                binding=binding,
                ordered_event_payloads=ordered_event_payloads,
                existing=committed,
            )
            return _readback_committed(
                connection,
                scope=scope,
                intent=committed,
                binding=binding,
                verify_current_runtime=False,
            )
    run_row = require_locked_runtime_step_attempt(
        connection,
        scope=scope,
        candidate=verified_candidate,
        binding=binding,
        config=config,
    )
    expected_run_revision = int(run_row["revision"])
    expected_run_next_event_seq = int(run_row["next_event_seq"])
    _require_current_scope(connection, scope)
    authority = require_locked_capability_authority(
        connection, scope, verified_candidate
    )

    existing = _load_commit_intent(connection, scope, config)
    if existing is not None:
        state = str(existing["state"])
        if state == CommitIntentStatus.UNKNOWN.value:
            raise C7OutcomeUnknownError(
                "commit outcome is unknown; no speculative retry is allowed"
            )
        if state == CommitIntentStatus.REJECTED.value:
            raise C7NoSpeculativeRetryError(
                "commit intent is terminally rejected; no new attempt is allowed"
            )
        if state not in {
            CommitIntentStatus.PREPARED.value,
            CommitIntentStatus.COMMITTED.value,
        }:
            raise C7NoSpeculativeRetryError(f"unsupported commit intent state: {state}")
        commit_binding = build_commit_binding(
            verified_candidate,
            config=config,
            binding=binding,
        )
        repo = CommitIntentRepository(connection, scope)
        try:
            repo.prepare(commit_binding)
        except ExactBindingConflict as exc:
            raise C7IdempotencyConflictError(
                "commit idempotency key is already bound to a different exact request"
            ) from exc
        if state == CommitIntentStatus.COMMITTED.value and (
            str(existing["commit_intent_id"]) != config.commit_intent_id
            or existing["canonical_commit_ref"] != config.canonical_commit_ref
            or existing["receipt_digest"] != config.receipt_digest
        ):
            raise C7IdempotencyConflictError(
                "committed intent exact request identity drift"
            )

    _require_journal_event_authority(
        connection,
        scope=scope,
        config=config,
        binding=binding,
        ordered_event_payloads=ordered_event_payloads,
        existing=existing,
        expected_run_revision=expected_run_revision,
        expected_run_next_event_seq=expected_run_next_event_seq,
    )

    head = _canonical_head(
        connection,
        scope,
        verified_candidate.canonical_object_id,
        for_update=True,
    )
    expected_value_ref = C7StructuredValueRef(
        value_id=candidate_value_id(verified_candidate.candidate_id),
        value_ref=candidate_value_ref(
            candidate_value_id(verified_candidate.candidate_id)
        ),
        revision=1,
        incarnation=candidate_value_incarnation(verified_candidate),
        content_digest=verified_candidate.payload_content_digest,
        provenance_digest=verified_candidate.provenance_closure_digest,
        source_ref=verified_candidate.snapshot_ref,
    )
    if head is not None:
        if not _head_matches(
            verified_candidate,
            binding,
            config,
            head,
            expected_value_ref,
        ):
            if (
                int(head["revision"]) != verified_candidate.expected_base_revision + 1
                or head["incarnation"] != verified_candidate.expected_base_incarnation
            ):
                raise C7StaleCanonicalRevisionError(
                    "canonical base revision/incarnation is stale"
                )
            raise C7CanonicalAbaError(
                "same canonical identity now holds different candidate bytes"
            )
    elif verified_candidate.expected_base_revision != 0:
        raise C7StaleCanonicalRevisionError(
            "new canonical object requires expected base revision 0"
        )

    if existing is not None:
        state = str(existing["state"])
        if state == CommitIntentStatus.COMMITTED.value:
            if head is None:
                raise C7OutcomeUnknownError(
                    "committed intent has no authoritative canonical head"
                )
            return load_authoritative_readback(
                connection,
                scope=scope,
                config=config,
                binding=binding,
            )
        if state != CommitIntentStatus.PREPARED.value:
            raise C7NoSpeculativeRetryError(f"unsupported commit intent state: {state}")
    elif head is not None:
        raise C7OutcomeUnknownError(
            "canonical head exists without a prepared commit intent"
        )

    intent = build_commit_intent(
        verified_candidate,
        config=config,
        scope=scope,
        binding=binding,
    )
    try:
        require_admission_binding(
            binding,
            intent,
            current_authority_digest=str(authority["config_digest"]),
            current_base_revision=(
                int(head["revision"])
                if head is not None
                else verified_candidate.expected_base_revision
            ),
            current_incarnation=(
                str(head["incarnation"])
                if head is not None
                else verified_candidate.expected_base_incarnation
            ),
            ordered_event_payloads=list(ordered_event_payloads),
        )
    except ValueError as exc:
        raise C7CandidateRejectedError(f"admission binding rejection: {exc}") from exc

    _require_current_scope(connection, scope)
    require_locked_capability_authority(connection, scope, verified_candidate)
    require_locked_runtime_step_attempt(
        connection,
        scope=scope,
        candidate=verified_candidate,
        binding=binding,
        config=config,
    )
    _require_journal_event_authority(
        connection,
        scope=scope,
        config=config,
        binding=binding,
        ordered_event_payloads=ordered_event_payloads,
        existing=existing,
        expected_run_revision=expected_run_revision,
        expected_run_next_event_seq=expected_run_next_event_seq,
    )

    try:
        with connection.begin_nested():
            if existing is None:
                commit_binding = build_commit_binding(
                    verified_candidate,
                    config=config,
                    binding=binding,
                )
                repo = CommitIntentRepository(connection, scope)
                try:
                    repo.prepare(commit_binding)
                except ExactBindingConflict as exc:
                    raise C7IdempotencyConflictError(
                        "commit idempotency key is already bound to a different "
                        "exact request"
                    ) from exc
            stored_value_ref = store_candidate_value(
                connection,
                scope=scope,
                structured=structured_candidate,
                verified=verified_candidate,
            )
            if head is None:
                _insert_canonical_head(
                    connection,
                    scope=scope,
                    candidate=verified_candidate,
                    binding=binding,
                    config=config,
                    value_ref=stored_value_ref,
                )
            _finalize_commit_intent(connection, scope, config)
    except IntegrityError as exc:
        raise C7CanonicalAbaError("concurrent canonical head write conflict") from exc

    return load_authoritative_readback(
        connection,
        scope=scope,
        config=config,
        binding=binding,
    )
