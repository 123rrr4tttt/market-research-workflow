"""Pure ahead-of-time facade contracts for the successor runtime (P4 C9).

Family-local scaffold boundary only.  Commands are descriptions that validate
without executing and bind ``ProjectScopeRef``, actor, idempotency, expected
revision/incarnation and optional approval.  Queries are read-only and may
carry an exclusive ``after_seq``.  The API envelope restores
``status/data/error/meta`` with the API status union
``ok/error/unavailable/blocked/waiting``, while UI observations keep the
independent six-state union.  Responses never carry control feedback.  No
transport, provider, network, database or runtime execution module is
imported beyond the pure runtime ports.
"""

from __future__ import annotations

import hashlib
import itertools
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

from app.successor_runtime.research.codec import canonical_json
from app.successor_runtime.runtime.ports import ProjectScopeRef

API_STATUS_KINDS: tuple[str, ...] = (
    "ok",
    "error",
    "unavailable",
    "blocked",
    "waiting",
)
ApiStatusKind = Literal[
    "ok",
    "error",
    "unavailable",
    "blocked",
    "waiting",
]
UI_OBSERVATION_STATES: tuple[str, ...] = (
    "ready",
    "waiting",
    "blocked",
    "unavailable",
    "conflict",
    "failed",
)
UiObservationState = Literal[
    "ready",
    "waiting",
    "blocked",
    "unavailable",
    "conflict",
    "failed",
]
API_STATUS_KINDS_V2: tuple[str, ...] = (
    "ok",
    "waiting",
    "blocked",
    "unavailable",
    "conflict",
    "error",
)
ApiStatusKindV2 = Literal[
    "ok",
    "waiting",
    "blocked",
    "unavailable",
    "conflict",
    "error",
]
C9_LOCAL_SINK_NAMES: tuple[str, ...] = ("agent_session", "graph", "search")
C9_ROLLBACK_TRANSITION_CONTRACT = "C9RollbackTransitionReceipt.v1"
FacadeExecutionMode = Literal["VALIDATION_ONLY"]

__all__ = [
    "API_STATUS_KINDS",
    "API_STATUS_KINDS_V2",
    "C9_LOCAL_SINK_NAMES",
    "C9_ROLLBACK_TRANSITION_CONTRACT",
    "UI_OBSERVATION_STATES",
    "ApiEnvelope",
    "ApiEnvelopeV2",
    "ApiError",
    "ApiErrorV2",
    "ApiStatusKindV2",
    "C9CommandBaseConflict",
    "C9CommandBlocked",
    "C9CommandConflict",
    "C9ContractViolation",
    "C9RollbackTransitionReceiptV1",
    "C9TransactionFatal",
    "C9Unavailable",
    "CommandMetaV2",
    "CommandReceipt",
    "CommandSubmissionPort",
    "ContractViolation",
    "FacadeCommand",
    "FacadeCommandV2",
    "FacadeMetaV2",
    "FacadeQuery",
    "FacadeQueryV2",
    "ProjectionCandidateValueV2",
    "ProjectionEvent",
    "ProjectionMeta",
    "ProjectionResponseMeta",
    "ProjectionResponseMetaV2",
    "ProjectionSnapshotDataV2",
    "QueryMetaV2",
    "QueryReadPort",
    "QueryResult",
    "RollbackPositionV1",
    "SseObservation",
    "UiObservation",
    "ValidationResult",
    "derive_c9_request_digest",
    "projection_key_digest",
    "rollback_transition_id",
    "rollback_transition_ref",
    "validate_api_envelope",
    "validate_api_envelope_v2",
    "validate_api_status",
    "validate_api_status_v2",
    "validate_command",
    "validate_command_meta_v2",
    "validate_command_v2",
    "validate_envelope_meta_v2",
    "validate_facade_meta_v2",
    "validate_meta",
    "validate_project_scope_ref",
    "validate_projection_response_meta_v2",
    "validate_projection_snapshot_data_v2",
    "validate_query",
    "validate_query_meta_v2",
    "validate_query_v2",
    "validate_response_meta",
    "validate_sse_observation",
    "validate_ui_observation",
    "validate_ui_state",
]


@dataclass(frozen=True)
class ProjectionMeta:
    """Mandatory project/trace/projection identity carried by every facade."""

    project_key: str
    trace_id: str
    projection_id: str


@dataclass(frozen=True)
class ProjectionResponseMeta:
    """Server-side response meta: scope, projection revision, source, cursor."""

    project_key: str
    trace_id: str
    projection_id: str
    project_scope_ref: ProjectScopeRef
    projection_revision: int
    source_digest: str
    cursor: int


@dataclass(frozen=True)
class FacadeCommand:
    """Description/validation-only command; never executes by contract."""

    command_id: str
    command_kind: str
    description: str
    project_scope_ref: ProjectScopeRef
    actor_ref: str
    idempotency_key: str
    expected_revision_or_incarnation: str
    meta: ProjectionMeta
    approval_ref: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    execution_mode: FacadeExecutionMode = "VALIDATION_ONLY"
    execute: Literal[False] = False


@dataclass(frozen=True)
class FacadeQuery:
    """Read-only projection query; never mutates or feeds back into control."""

    query_id: str
    query_kind: str
    project_scope_ref: ProjectScopeRef
    meta: ProjectionMeta
    params: Mapping[str, Any] = field(default_factory=dict)
    after_seq: int | None = None
    read_only: Literal[True] = True


@dataclass(frozen=True)
class ApiError:
    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ApiEnvelope:
    """API transport envelope: status/data/error/meta plus no control feedback."""

    status: ApiStatusKind
    meta: ProjectionResponseMeta
    data: Mapping[str, Any] | None = None
    error: ApiError | None = None
    control_feedback: Literal[False] = False


@dataclass(frozen=True)
class UiObservation:
    """Design-only UI observation with its own six-state union."""

    state: UiObservationState
    projection_id: str
    meta: ProjectionResponseMeta
    data: Mapping[str, Any] | None = None
    reason: str | None = None
    control_feedback: Literal[False] = False


@dataclass(frozen=True)
class ProjectionEvent:
    seq: int
    event_type: str
    projection_id: str
    payload: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SseObservation:
    """SSE projection observation with an exclusive ``after_seq`` cursor."""

    after_seq: int
    reconnect: bool
    meta: ProjectionResponseMeta
    events: tuple[ProjectionEvent, ...] = ()
    next_seq: int | None = None


@dataclass(frozen=True)
class ContractViolation:
    code: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    violations: tuple[ContractViolation, ...] = ()


def _result(violations: list[ContractViolation]) -> ValidationResult:
    return ValidationResult(
        valid=not violations,
        violations=tuple(violations),
    )


def _require_nonempty(
    value: str,
    name: str,
    violations: list[ContractViolation],
) -> None:
    if not isinstance(value, str) or not value.strip():
        violations.append(
            ContractViolation(
                code="FIELD_REQUIRED",
                message=f"{name} must be a non-empty string",
            )
        )


def _require_hex64(
    value: str,
    name: str,
    violations: list[ContractViolation],
) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        violations.append(
            ContractViolation(
                code="SOURCE_DIGEST_INVALID",
                message=f"{name} must be canonical SHA-256 hex",
            )
        )


def validate_meta(meta: ProjectionMeta) -> ValidationResult:
    violations: list[ContractViolation] = []
    for name in ("project_key", "trace_id", "projection_id"):
        _require_nonempty(getattr(meta, name), name, violations)
    return _result(violations)


def validate_response_meta(meta: ProjectionResponseMeta) -> ValidationResult:
    violations: list[ContractViolation] = []
    for name in ("project_key", "trace_id", "projection_id"):
        _require_nonempty(getattr(meta, name), name, violations)
    violations.extend(validate_project_scope_ref(meta.project_scope_ref).violations)
    if not isinstance(meta.projection_revision, int) or meta.projection_revision < 0:
        violations.append(
            ContractViolation(
                code="PROJECTION_REVISION_NEGATIVE",
                message="projection_revision must be non-negative",
            )
        )
    _require_hex64(meta.source_digest, "source_digest", violations)
    if not isinstance(meta.cursor, int) or meta.cursor < 0:
        violations.append(
            ContractViolation(
                code="CURSOR_NEGATIVE",
                message="cursor must be non-negative",
            )
        )
    return _result(violations)


def validate_project_scope_ref(scope: ProjectScopeRef) -> ValidationResult:
    if not isinstance(scope, ProjectScopeRef):
        return _result(
            [
                ContractViolation(
                    code="PROJECT_SCOPE_REF_REQUIRED",
                    message="facade requests must bind a server-resolved ProjectScopeRef",
                )
            ]
        )
    return _result([])


def validate_api_status(status: ApiStatusKind) -> ValidationResult:
    if status not in API_STATUS_KINDS:
        return _result(
            [
                ContractViolation(
                    code="UNKNOWN_API_STATUS",
                    message=f"unknown API status kind: {status!r}",
                )
            ]
        )
    return _result([])


def validate_ui_state(state: UiObservationState) -> ValidationResult:
    if state not in UI_OBSERVATION_STATES:
        return _result(
            [
                ContractViolation(
                    code="UNKNOWN_UI_STATE",
                    message=f"unknown UI observation state: {state!r}",
                )
            ]
        )
    return _result([])


def validate_command(command: FacadeCommand) -> ValidationResult:
    violations: list[ContractViolation] = list(validate_meta(command.meta).violations)
    violations.extend(validate_project_scope_ref(command.project_scope_ref).violations)
    for name in (
        "command_id",
        "command_kind",
        "description",
        "actor_ref",
        "idempotency_key",
        "expected_revision_or_incarnation",
    ):
        _require_nonempty(getattr(command, name), name, violations)
    if command.approval_ref is not None and not command.approval_ref.strip():
        violations.append(
            ContractViolation(
                code="APPROVAL_REF_EMPTY",
                message="approval_ref must be None or a non-empty reference",
            )
        )
    if command.execution_mode != "VALIDATION_ONLY":
        violations.append(
            ContractViolation(
                code="COMMAND_EXECUTION_FORBIDDEN",
                message="facade commands are description/validation only",
            )
        )
    if command.execute is not False:
        violations.append(
            ContractViolation(
                code="COMMAND_EXECUTION_FORBIDDEN",
                message="facade commands must never execute",
            )
        )
    return _result(violations)


def validate_query(query: FacadeQuery) -> ValidationResult:
    violations: list[ContractViolation] = list(validate_meta(query.meta).violations)
    violations.extend(validate_project_scope_ref(query.project_scope_ref).violations)
    for name in ("query_id", "query_kind"):
        _require_nonempty(getattr(query, name), name, violations)
    if query.read_only is not True:
        violations.append(
            ContractViolation(
                code="QUERY_MUTATION_FORBIDDEN",
                message="facade queries are read-only",
            )
        )
    if query.after_seq is not None and query.after_seq < 0:
        violations.append(
            ContractViolation(
                code="SSE_AFTER_SEQ_NEGATIVE",
                message="after_seq must be non-negative",
            )
        )
    return _result(violations)


def validate_api_envelope(envelope: ApiEnvelope) -> ValidationResult:
    violations: list[ContractViolation] = list(
        validate_api_status(envelope.status).violations
    )
    violations.extend(validate_response_meta(envelope.meta).violations)
    if envelope.status == "error" and envelope.error is None:
        violations.append(
            ContractViolation(
                code="ENVELOPE_ERROR_REQUIRED",
                message="error envelope requires error details",
            )
        )
    if envelope.status != "error" and envelope.error is not None:
        violations.append(
            ContractViolation(
                code="ENVELOPE_ERROR_FORBIDDEN",
                message="non-error envelope must not carry error details",
            )
        )
    if envelope.control_feedback is not False:
        violations.append(
            ContractViolation(
                code="CONTROL_FEEDBACK_FORBIDDEN",
                message="projection responses must not feed control state",
            )
        )
    return _result(violations)


def validate_ui_observation(observation: UiObservation) -> ValidationResult:
    violations: list[ContractViolation] = list(
        validate_ui_state(observation.state).violations
    )
    violations.extend(validate_response_meta(observation.meta).violations)
    _require_nonempty(observation.projection_id, "projection_id", violations)
    if observation.control_feedback is not False:
        violations.append(
            ContractViolation(
                code="CONTROL_FEEDBACK_FORBIDDEN",
                message="UI observations must not feed control state",
            )
        )
    return _result(violations)


def validate_sse_observation(observation: SseObservation) -> ValidationResult:
    violations: list[ContractViolation] = list(
        validate_response_meta(observation.meta).violations
    )
    if observation.after_seq < 0:
        violations.append(
            ContractViolation(
                code="SSE_AFTER_SEQ_NEGATIVE",
                message="after_seq must be non-negative",
            )
        )
    seqs = [event.seq for event in observation.events]
    if any(seq <= observation.after_seq for seq in seqs):
        violations.append(
            ContractViolation(
                code="SSE_AFTER_SEQ_EXCLUSIVE",
                message="event seq must be strictly greater than after_seq",
            )
        )
    if any(current <= previous for previous, current in itertools.pairwise(seqs)):
        violations.append(
            ContractViolation(
                code="SSE_SEQ_MONOTONIC",
                message="event seqs must be unique and strictly ascending",
            )
        )
    expected_next = seqs[-1] if seqs else observation.after_seq
    if observation.next_seq != expected_next:
        violations.append(
            ContractViolation(
                code="SSE_NEXT_SEQ_MISMATCH",
                message="next_seq must be the last event seq or after_seq when empty",
            )
        )
    return _result(violations)


class C9CommandConflict(ValueError):
    """Raised when one command id is already bound to a different intent."""


class C9CommandBaseConflict(ValueError):
    """Raised when the expected projection base no longer matches server state."""


class C9CommandBlocked(RuntimeError):
    """Raised when the server refuses to accept a command for now."""


class C9Unavailable(RuntimeError):
    """Raised when the requested projection/read state is unavailable."""


class C9ContractViolation(ValueError):
    """Raised when an internal facade contract is malformed."""


class C9TransactionFatal(RuntimeError):
    """Raised when committed submission state is partial/inconsistent.

    The facade must re-raise this type so the caller's unit of work rolls back;
    it must never be mapped into a success/error envelope that could commit a
    partial submission.
    """


@dataclass(frozen=True)
class FacadeMetaV2:
    """Request identity shared by every v2 facade message."""

    project_key: str
    trace_id: str
    projection_id: str


@dataclass(frozen=True)
class CommandMetaV2:
    """Command-scoped response meta; distinct from projection meta."""

    project_key: str
    trace_id: str
    command_id: str
    project_scope_ref: ProjectScopeRef


@dataclass(frozen=True)
class QueryMetaV2:
    """Query-scoped response meta; distinct from projection meta."""

    project_key: str
    trace_id: str
    query_id: str
    project_scope_ref: ProjectScopeRef


@dataclass(frozen=True)
class ProjectionResponseMetaV2:
    """Server response meta: scope, projection revision, source, cursor."""

    project_key: str
    trace_id: str
    projection_id: str
    project_scope_ref: ProjectScopeRef
    projector_id: str
    projector_version: str
    source_kind: str
    source_ref: str
    source_incarnation: str
    projection_generation: int
    offset_revision: int
    projection_revision: int
    source_digest: str
    cursor: int


@dataclass(frozen=True)
class ProjectionCandidateValueV2:
    """One exact local projection candidate value bound in a snapshot."""

    value_id: str
    value_ref: str
    content_digest: str
    byte_size: int
    sink: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class RollbackPositionV1:
    """Exact position binding shared by ``from`` and ``to`` in a rollback."""

    projection_generation: int
    offset_revision: int
    projection_revision: int
    source_digest: str
    cursor: int
    offset_ref: str

    def to_plain(self) -> Mapping[str, Any]:
        return {
            "projection_generation": self.projection_generation,
            "offset_revision": self.offset_revision,
            "projection_revision": self.projection_revision,
            "source_digest": self.source_digest,
            "cursor": self.cursor,
            "offset_ref": self.offset_ref,
        }


@dataclass(frozen=True)
class C9RollbackTransitionReceiptV1:
    """Unified rollback receipt schema aligned with the frontend.

    ``digest`` is the canonical SHA-256 of the receipt excluding the ``digest``
    field itself; ``ref``/identity binds the full ``from`` position, the exact
    ``to`` target and the generation completeness digest, so an ABA
    generation cycle always produces a distinct receipt.
    """

    ref: str
    digest: str
    projection_id: str
    projector_id: str
    projector_version: str
    source_kind: str
    source_ref: str
    source_incarnation: str
    from_position: RollbackPositionV1
    to_position: RollbackPositionV1
    generation_completeness_digest: str
    observed_at: str = ""
    contract: str = C9_ROLLBACK_TRANSITION_CONTRACT

    def to_plain(self) -> Mapping[str, Any]:
        return {
            "contract": self.contract,
            "ref": self.ref,
            "digest": self.digest,
            "projection_id": self.projection_id,
            "projector_id": self.projector_id,
            "projector_version": self.projector_version,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "source_incarnation": self.source_incarnation,
            "from": self.from_position.to_plain(),
            "to": self.to_position.to_plain(),
            "generation_completeness_digest": self.generation_completeness_digest,
        }


@dataclass(frozen=True)
class ProjectionSnapshotDataV2:
    """Typed success data for a projection snapshot query.

    The object rebinds the exact source key, generation, offset revision,
    projection revision, source digest and cursor so envelope ``meta`` and
    ``data`` cannot drift apart.  Candidate values carry value/ref/digest when
    the local PostgreSQL readback provides them.
    """

    projection_id: str
    projector_id: str
    projector_version: str
    source_kind: str
    source_ref: str
    source_incarnation: str
    projection_generation: int
    offset_revision: int
    projection_revision: int
    source_digest: str
    cursor: int
    offset_ref: str
    candidate_values: tuple[ProjectionCandidateValueV2, ...] = ()
    rollback_transition: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class FacadeCommandV2:
    """Server-resolved command description; ``execute`` stays False."""

    command_id: str
    command_kind: str
    description: str
    project_scope_ref: ProjectScopeRef
    actor_ref: str
    idempotency_key: str
    expected_base_token: str | None
    meta: CommandMetaV2
    approval_locator: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    execute: Literal[False] = False


@dataclass(frozen=True)
class FacadeQueryV2:
    """Server-resolved read-only query description."""

    query_id: str
    query_kind: str
    project_scope_ref: ProjectScopeRef
    actor_ref: str
    meta: QueryMetaV2
    params: Mapping[str, Any] = field(default_factory=dict)
    read_only: Literal[True] = True


@dataclass(frozen=True)
class ApiErrorV2:
    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ApiEnvelopeV2:
    """v2 API envelope preserving status/data/error/meta without feedback."""

    status: ApiStatusKindV2
    meta: CommandMetaV2 | QueryMetaV2 | ProjectionResponseMetaV2
    data: Mapping[str, Any] | ProjectionSnapshotDataV2 | None = None
    error: ApiErrorV2 | None = None
    control_feedback: Literal[False] = False


@dataclass(frozen=True)
class CommandReceipt:
    """Durable submission receipt returned by a command submission port."""

    receipt_ref: str
    command_id: str
    request_digest: str
    state: Literal["STARTED", "TERMINAL"]
    idempotency_id: str
    logical_request_id: str
    run_id: str | None = None
    authority_context_digest: str | None = None
    grant_epoch: int | None = None
    grants_digest: str | None = None
    observed_at: str | None = None


@dataclass(frozen=True)
class QueryResult:
    """Read-only query result with complete projection response meta."""

    data: Mapping[str, Any] | ProjectionSnapshotDataV2
    meta: ProjectionResponseMetaV2


@runtime_checkable
class CommandSubmissionPort(Protocol):
    """One durable submission; the facade calls it exactly once."""

    def submit(self, command: FacadeCommandV2) -> CommandReceipt: ...


@runtime_checkable
class QueryReadPort(Protocol):
    """One read-only projection query; the facade calls it exactly once."""

    def read(self, query: FacadeQueryV2) -> QueryResult: ...


def projection_key_digest(
    *,
    projector_id: str,
    projector_version: str,
    source_kind: str,
    source_ref: str,
    source_incarnation: str,
) -> str:
    """Canonical digest over the exact projector/source key."""

    return hashlib.sha256(
        canonical_json(
            {
                "projector_id": projector_id,
                "projector_version": projector_version,
                "source_kind": source_kind,
                "source_ref": source_ref,
                "source_incarnation": source_incarnation,
            }
        ).encode("utf-8")
    ).hexdigest()


def rollback_transition_id(
    *,
    from_position: Mapping[str, Any],
    to_position: Mapping[str, Any],
    generation_completeness_digest: str,
) -> str:
    """ABA-aware rollback identity binding from + to + completeness."""

    if len(generation_completeness_digest) != 64 or any(
        character not in "0123456789abcdef"
        for character in generation_completeness_digest
    ):
        raise ValueError("generation_completeness_digest must be canonical SHA-256 hex")
    return hashlib.sha256(
        canonical_json(
            {
                "from": dict(from_position),
                "to": dict(to_position),
                "generation_completeness_digest": generation_completeness_digest,
            }
        ).encode("utf-8")
    ).hexdigest()


def rollback_transition_ref(transition_id: str) -> str:
    """Deterministic receipt ref bound to the full transition identity."""

    if len(transition_id) != 64 or any(
        character not in "0123456789abcdef" for character in transition_id
    ):
        raise ValueError("transition_id must be canonical SHA-256 hex")
    return f"rollback:{transition_id}"


def derive_c9_request_digest(
    *,
    scope_digest: str,
    actor_ref: str,
    command_id: str,
    command_kind: str,
    payload: Mapping[str, Any],
    expected_base_token: str | None = None,
    approval_locator: str | None = None,
) -> str:
    """Derive exact request identity from scope, actor and typed intent."""

    if len(scope_digest) != 64 or any(
        character not in "0123456789abcdef" for character in scope_digest
    ):
        raise ValueError("scope_digest must be canonical SHA-256 hex")
    if not actor_ref.strip() or not command_id.strip() or not command_kind.strip():
        raise ValueError("actor_ref/command_id/command_kind must be non-empty")
    content = {
        "contract": "C9RequestIdentity.v1",
        "scope_digest": scope_digest,
        "actor_ref": actor_ref,
        "command_id": command_id,
        "command_kind": command_kind,
        "payload": dict(payload),
        "expected_base_token": expected_base_token,
        "approval_locator": approval_locator,
    }
    return hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()


def validate_facade_meta_v2(meta: FacadeMetaV2) -> ValidationResult:
    violations: list[ContractViolation] = []
    if not isinstance(meta, FacadeMetaV2):
        return _result(
            [
                ContractViolation(
                    code="FACADE_META_REQUIRED",
                    message="v2 facade messages require FacadeMetaV2",
                )
            ]
        )
    for name in ("project_key", "trace_id", "projection_id"):
        _require_nonempty(getattr(meta, name), name, violations)
    return _result(violations)


def validate_command_meta_v2(meta: CommandMetaV2) -> ValidationResult:
    violations: list[ContractViolation] = []
    if not isinstance(meta, CommandMetaV2):
        return _result(
            [
                ContractViolation(
                    code="COMMAND_META_REQUIRED",
                    message="command envelope requires CommandMetaV2",
                )
            ]
        )
    for name in ("project_key", "trace_id", "command_id"):
        _require_nonempty(getattr(meta, name), name, violations)
    violations.extend(validate_project_scope_ref(meta.project_scope_ref).violations)
    return _result(violations)


def validate_query_meta_v2(meta: QueryMetaV2) -> ValidationResult:
    violations: list[ContractViolation] = []
    if not isinstance(meta, QueryMetaV2):
        return _result(
            [
                ContractViolation(
                    code="QUERY_META_REQUIRED",
                    message="query envelope requires QueryMetaV2",
                )
            ]
        )
    for name in ("project_key", "trace_id", "query_id"):
        _require_nonempty(getattr(meta, name), name, violations)
    violations.extend(validate_project_scope_ref(meta.project_scope_ref).violations)
    return _result(violations)


def validate_projection_response_meta_v2(
    meta: ProjectionResponseMetaV2,
) -> ValidationResult:
    violations: list[ContractViolation] = []
    if not isinstance(meta, ProjectionResponseMetaV2):
        return _result(
            [
                ContractViolation(
                    code="PROJECTION_META_REQUIRED",
                    message="projection response requires ProjectionResponseMetaV2",
                )
            ]
        )
    for name in ("project_key", "trace_id", "projection_id"):
        _require_nonempty(getattr(meta, name), name, violations)
    violations.extend(validate_project_scope_ref(meta.project_scope_ref).violations)
    for name in (
        "projector_id",
        "projector_version",
        "source_kind",
        "source_ref",
        "source_incarnation",
    ):
        _require_nonempty(getattr(meta, name), name, violations)
    for name in ("projection_generation", "offset_revision"):
        value = getattr(meta, name)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            violations.append(
                ContractViolation(
                    code="PROJECTION_POSITION_NEGATIVE",
                    message=f"{name} must be a non-negative integer",
                )
            )
    if not isinstance(meta.projection_revision, int) or meta.projection_revision < 0:
        violations.append(
            ContractViolation(
                code="PROJECTION_REVISION_NEGATIVE",
                message="projection_revision must be non-negative",
            )
        )
    _require_hex64(meta.source_digest, "source_digest", violations)
    if not isinstance(meta.cursor, int) or meta.cursor < 0:
        violations.append(
            ContractViolation(
                code="CURSOR_NEGATIVE",
                message="cursor must be non-negative",
            )
        )
    return _result(violations)


def validate_projection_snapshot_data_v2(
    data: ProjectionSnapshotDataV2,
    meta: ProjectionResponseMetaV2,
) -> ValidationResult:
    """Fail closed when typed snapshot data drifts from envelope meta."""

    violations: list[ContractViolation] = []
    if not isinstance(data, ProjectionSnapshotDataV2):
        return _result(
            [
                ContractViolation(
                    code="PROJECTION_DATA_REQUIRED",
                    message="success projection query requires typed snapshot data",
                )
            ]
        )
    if not isinstance(meta, ProjectionResponseMetaV2):
        return _result(
            [
                ContractViolation(
                    code="PROJECTION_META_REQUIRED",
                    message="projection query requires ProjectionResponseMetaV2",
                )
            ]
        )
    exact_pairs = (
        ("projection_id", "projection_id"),
        ("projector_id", "projector_id"),
        ("projector_version", "projector_version"),
        ("source_kind", "source_kind"),
        ("source_ref", "source_ref"),
        ("source_incarnation", "source_incarnation"),
        ("projection_generation", "projection_generation"),
        ("offset_revision", "offset_revision"),
        ("projection_revision", "projection_revision"),
        ("source_digest", "source_digest"),
        ("cursor", "cursor"),
    )
    for data_field, meta_field in exact_pairs:
        if getattr(data, data_field) != getattr(meta, meta_field):
            violations.append(
                ContractViolation(
                    code="PROJECTION_META_DATA_MISMATCH",
                    message=f"snapshot data {data_field} drifts from envelope meta",
                )
            )
    if data.projection_id != meta.projection_id:
        violations.append(
            ContractViolation(
                code="PROJECTION_META_DATA_MISMATCH",
                message="snapshot projection_id drifts from envelope meta",
            )
        )
    _require_nonempty(data.offset_ref, "offset_ref", violations)
    for value in data.candidate_values:
        if not isinstance(value, ProjectionCandidateValueV2):
            violations.append(
                ContractViolation(
                    code="PROJECTION_VALUE_TYPE_INVALID",
                    message="candidate values must be typed ProjectionCandidateValueV2",
                )
            )
            continue
        _require_nonempty(value.value_id, "value_id", violations)
        _require_nonempty(value.value_ref, "value_ref", violations)
        _require_nonempty(value.sink, "sink", violations)
        _require_hex64(value.content_digest, "content_digest", violations)
        if not isinstance(value.byte_size, int) or value.byte_size < 0:
            violations.append(
                ContractViolation(
                    code="PROJECTION_VALUE_SIZE_NEGATIVE",
                    message="value byte_size must be non-negative",
                )
            )
        if value.sink not in C9_LOCAL_SINK_NAMES:
            violations.append(
                ContractViolation(
                    code="PROJECTION_SINK_UNREGISTERED",
                    message=f"candidate sink is not in the fixed registry: {value.sink}",
                )
            )
        if not isinstance(value.payload, Mapping):
            violations.append(
                ContractViolation(
                    code="PROJECTION_PAYLOAD_MISSING",
                    message="candidate payload must be decoded typed JSON",
                )
            )
    if data.rollback_transition is not None:
        transition = data.rollback_transition
        if not isinstance(transition, Mapping):
            violations.append(
                ContractViolation(
                    code="PROJECTION_ROLLBACK_TRANSITION_MISMATCH",
                    message="rollback transition must be the exact wire object",
                )
            )
            return _result(violations)
        to_position = transition.get("to")
        if (
            not isinstance(to_position, Mapping)
            or to_position.get("projection_generation") != data.projection_generation
            or to_position.get("offset_revision") != data.offset_revision
            or to_position.get("source_digest") != data.source_digest
        ):
            violations.append(
                ContractViolation(
                    code="PROJECTION_ROLLBACK_TRANSITION_MISMATCH",
                    message="rollback transition drifts from snapshot position",
                )
            )
    return _result(violations)


def validate_envelope_meta_v2(
    meta: CommandMetaV2 | QueryMetaV2 | ProjectionResponseMetaV2,
) -> ValidationResult:
    if isinstance(meta, CommandMetaV2):
        return validate_command_meta_v2(meta)
    if isinstance(meta, QueryMetaV2):
        return validate_query_meta_v2(meta)
    if isinstance(meta, ProjectionResponseMetaV2):
        return validate_projection_response_meta_v2(meta)
    return _result(
        [
            ContractViolation(
                code="ENVELOPE_META_REQUIRED",
                message="envelope must carry command/query/projection meta",
            )
        ]
    )


def validate_api_status_v2(status: ApiStatusKindV2) -> ValidationResult:
    if status not in API_STATUS_KINDS_V2:
        return _result(
            [
                ContractViolation(
                    code="UNKNOWN_API_STATUS",
                    message=f"unknown API status kind: {status!r}",
                )
            ]
        )
    return _result([])


def validate_command_v2(command: FacadeCommandV2) -> ValidationResult:
    violations: list[ContractViolation] = list(
        validate_command_meta_v2(command.meta).violations
    )
    for name in (
        "command_id",
        "command_kind",
        "description",
        "actor_ref",
        "idempotency_key",
    ):
        _require_nonempty(getattr(command, name), name, violations)
    if (
        command.expected_base_token is not None
        and not command.expected_base_token.strip()
    ):
        violations.append(
            ContractViolation(
                code="EXPECTED_BASE_TOKEN_EMPTY",
                message="expected_base_token must be None or non-empty",
            )
        )
    if command.approval_locator is not None and not command.approval_locator.strip():
        violations.append(
            ContractViolation(
                code="APPROVAL_LOCATOR_EMPTY",
                message="approval_locator must be None or non-empty",
            )
        )
    if command.project_scope_ref != command.meta.project_scope_ref:
        violations.append(
            ContractViolation(
                code="COMMAND_SCOPE_IDENTITY_MISMATCH",
                message="command scope must equal the server-resolved command meta scope",
            )
        )
    if command.meta.project_key != command.project_scope_ref.project_key:
        violations.append(
            ContractViolation(
                code="COMMAND_PROJECT_KEY_MISMATCH",
                message="command meta project_key must equal the resolved scope project_key",
            )
        )
    if command.meta.command_id != command.command_id:
        violations.append(
            ContractViolation(
                code="COMMAND_ID_MISMATCH",
                message="command meta command_id must equal the command id",
            )
        )
    if command.execute is not False:
        violations.append(
            ContractViolation(
                code="COMMAND_EXECUTION_FORBIDDEN",
                message="v2 facade commands must never execute",
            )
        )
    return _result(violations)


def validate_query_v2(query: FacadeQueryV2) -> ValidationResult:
    violations: list[ContractViolation] = list(
        validate_query_meta_v2(query.meta).violations
    )
    for name in ("query_id", "query_kind"):
        _require_nonempty(getattr(query, name), name, violations)
    _require_nonempty(query.actor_ref, "actor_ref", violations)
    if query.project_scope_ref != query.meta.project_scope_ref:
        violations.append(
            ContractViolation(
                code="QUERY_SCOPE_IDENTITY_MISMATCH",
                message="query scope must equal the server-resolved query meta scope",
            )
        )
    if query.meta.project_key != query.project_scope_ref.project_key:
        violations.append(
            ContractViolation(
                code="QUERY_PROJECT_KEY_MISMATCH",
                message="query meta project_key must equal the resolved scope project_key",
            )
        )
    if query.meta.query_id != query.query_id:
        violations.append(
            ContractViolation(
                code="QUERY_ID_MISMATCH",
                message="query meta query_id must equal the query id",
            )
        )
    if query.read_only is not True:
        violations.append(
            ContractViolation(
                code="QUERY_MUTATION_FORBIDDEN",
                message="v2 facade queries are read-only",
            )
        )
    return _result(violations)


def validate_api_envelope_v2(envelope: ApiEnvelopeV2) -> ValidationResult:
    violations: list[ContractViolation] = list(
        validate_api_status_v2(envelope.status).violations
    )
    violations.extend(validate_envelope_meta_v2(envelope.meta).violations)
    data_required = envelope.status in {"ok", "waiting"}
    error_required = envelope.status in {
        "blocked",
        "unavailable",
        "conflict",
        "error",
    }
    if data_required and envelope.data is None:
        violations.append(
            ContractViolation(
                code="ENVELOPE_DATA_REQUIRED",
                message="ok/waiting envelope requires data",
            )
        )
    if data_required and envelope.error is not None:
        violations.append(
            ContractViolation(
                code="ENVELOPE_ERROR_FORBIDDEN",
                message="ok/waiting envelope must not carry error details",
            )
        )
    if error_required and envelope.error is None:
        violations.append(
            ContractViolation(
                code="ENVELOPE_ERROR_REQUIRED",
                message="error-family envelope requires typed error details",
            )
        )
    if error_required and envelope.data is not None:
        violations.append(
            ContractViolation(
                code="ENVELOPE_DATA_FORBIDDEN",
                message="error-family envelope must not carry data",
            )
        )
    if envelope.control_feedback is not False:
        violations.append(
            ContractViolation(
                code="CONTROL_FEEDBACK_FORBIDDEN",
                message="v2 envelopes must not feed control state",
            )
        )
    return _result(violations)
