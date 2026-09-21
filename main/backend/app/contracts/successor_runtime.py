"""Transport DTOs for the successor runtime facade (P4 C9).

DTO-only boundary: no routes, no services, no execution and no live I/O.
External request DTOs carry only a project locator plus a
``command_kind``/``query_kind``-discriminated typed payload; actor and
server-resolved ``ProjectScopeRef`` are injected only inside the internal
facade command/query contracts.  Response meta restores project scope,
projection revision, source digest and cursor.  All DTOs forbid unknown
fields so authority/control internals cannot be smuggled onto the wire.
"""

from __future__ import annotations

import itertools
from typing import Annotated, Any, Literal

from functorial_kit import Failure
from pydantic import BaseModel, ConfigDict, Field, model_validator
from mrw_functorial_kit.core.application_failure_semantics import successor_runtime_dto_contract_failures


_SUCCESSOR_FAILURE_WITNESS = "test:test_w01_contract_failures"


def _successor_contract_failure(code: str, message: str, *, operation: str) -> Failure:
    return successor_runtime_dto_contract_failures.fail(
        code,
        message,
        {
            "boundary_class": "PURE_CONTRACT_FAILURE",
            "failure_family": successor_runtime_dto_contract_failures.name,
            "owner": "app.contracts.successor_runtime",
            "operation": operation,
            "public_exception": "ValueError",
            "public_message": message,
            "site": "app.contracts.successor_runtime",
            "witness": _SUCCESSOR_FAILURE_WITNESS,
        },
    )


def _lift_successor_contract_failure(failure: Failure | None) -> None:
    if failure is not None:
        # kit:boundary owner=app.contracts.successor_runtime.pydantic_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor_runtime.dto.contract_failure witness=test:test_w01_contract_failures
        raise ValueError(failure.message)


def _validate_command_payload_kind(
    command_kind: str,
    payload_kind: str,
    *,
    operation: str,
) -> Failure | None:
    if command_kind != payload_kind:
        return _successor_contract_failure(
            "command_payload_kind_mismatch",
            "command_kind must match the typed payload_kind",
            operation=operation,
        )
    return None


def _validate_query_params_kind(
    query_kind: str,
    params_kind: str,
    *,
    operation: str,
) -> Failure | None:
    if query_kind != params_kind:
        return _successor_contract_failure(
            "query_params_kind_mismatch",
            "query_kind must match the typed params_kind",
            operation=operation,
        )
    return None


def _validate_v2_envelope(
    status: str,
    data: dict[str, Any] | None,
    error: object | None,
) -> Failure | None:
    data_required = status in {"ok", "waiting"}
    error_required = status in {"blocked", "unavailable", "conflict", "error"}
    operation = "SuccessorRuntimeEnvelopeV2DTO._validate_envelope"
    if data_required and data is None:
        return _successor_contract_failure(
            "successful_envelope_data_missing",
            "ok/waiting envelope requires data",
            operation=operation,
        )
    if data_required and error is not None:
        return _successor_contract_failure(
            "successful_envelope_error_present",
            "ok/waiting envelope must not carry error details",
            operation=operation,
        )
    if error_required and error is None:
        return _successor_contract_failure(
            "error_envelope_details_missing",
            "error-family envelope requires typed error details",
            operation=operation,
        )
    if error_required and data is not None:
        return _successor_contract_failure(
            "error_envelope_data_present",
            "error-family envelope must not carry data",
            operation=operation,
        )
    return None


def _validate_legacy_envelope(
    status: str,
    data: dict[str, Any] | None,
    error: object | None,
) -> Failure | None:
    operation = "SuccessorRuntimeApiEnvelopeDTO._validate_envelope"
    if status == "error" and error is None:
        return _successor_contract_failure(
            "error_envelope_details_missing",
            "error envelope requires error details",
            operation=operation,
        )
    if status != "error" and error is not None:
        return _successor_contract_failure(
            "non_error_envelope_details_present",
            "non-error envelope must not carry error details",
            operation=operation,
        )
    return None


def _validate_sse_observation(
    after_seq: int,
    events: list[Any],
    next_seq: int,
) -> Failure | None:
    seqs = [event.seq for event in events]
    operation = "SuccessorRuntimeSseObservationDTO._validate_after_seq_exclusive"
    if any(seq <= after_seq for seq in seqs):
        return _successor_contract_failure(
            "sse_event_not_after_cursor",
            "event seq must be strictly greater than after_seq",
            operation=operation,
        )
    if any(current <= previous for previous, current in itertools.pairwise(seqs)):
        return _successor_contract_failure(
            "sse_events_not_strictly_ascending",
            "event seqs must be unique and strictly ascending",
            operation=operation,
        )
    expected_next = seqs[-1] if seqs else after_seq
    if next_seq != expected_next:
        return _successor_contract_failure(
            "sse_next_seq_mismatch",
            "next_seq must match the last event seq",
            operation=operation,
        )
    return None

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

__all__ = [
    "API_STATUS_KINDS",
    "API_STATUS_KINDS_V2",
    "UI_OBSERVATION_STATES",
    "ApiStatusKindV2",
    "InvalidateProjectionPayload",
    "ProjectionEventsParams",
    "ProjectionSnapshotParams",
    "RebuildProjectionPayload",
    "SuccessorRuntimeApiEnvelopeDTO",
    "SuccessorRuntimeApiErrorDTO",
    "SuccessorRuntimeApiErrorV2DTO",
    "SuccessorRuntimeCommandDTO",
    "SuccessorRuntimeCommandMetaV2DTO",
    "SuccessorRuntimeCommandV2DTO",
    "SuccessorRuntimeEnvelopeV2DTO",
    "SuccessorRuntimeEventDTO",
    "SuccessorRuntimeInvalidateProjectionV2Payload",
    "SuccessorRuntimeMeta",
    "SuccessorRuntimeProjectScopeRefDTO",
    "SuccessorRuntimeProjectionMetaDTO",
    "SuccessorRuntimeProjectionMetaV2DTO",
    "SuccessorRuntimeProjectionSnapshotV2Params",
    "SuccessorRuntimeQueryDTO",
    "SuccessorRuntimeQueryMetaV2DTO",
    "SuccessorRuntimeQueryV2DTO",
    "SuccessorRuntimeRebuildProjectionV2Payload",
    "SuccessorRuntimeRollbackProjectionV2Payload",
    "SuccessorRuntimeSseObservationDTO",
    "SuccessorRuntimeUiObservationDTO",
    "SuccessorRuntimeUnresolvedMetaV2DTO",
]


class SuccessorRuntimeMeta(BaseModel):
    """Minimal request meta; never carries server-resolved scope fields."""

    model_config = ConfigDict(extra="forbid")

    project_key: str = Field(..., min_length=1)
    trace_id: str = Field(..., min_length=1)
    projection_id: str = Field(..., min_length=1)


class SuccessorRuntimeProjectScopeRefDTO(BaseModel):
    """Server-resolved scope shape used only in internal/response payloads."""

    model_config = ConfigDict(extra="forbid")

    project_key: str = Field(..., min_length=1)
    resolved_schema: str = Field(..., min_length=1)
    project_registry_revision: int = Field(..., ge=0)
    incarnation: str = Field(..., min_length=1, max_length=128)
    scope_digest: str = Field(..., pattern=r"^[0-9a-f]{64}$")


class SuccessorRuntimeProjectionMetaDTO(SuccessorRuntimeMeta):
    """Response meta: scope, projection revision, source digest and cursor."""

    project_scope_ref: SuccessorRuntimeProjectScopeRefDTO
    projection_revision: int = Field(..., ge=0)
    source_digest: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    cursor: int = Field(..., ge=0)


class SuccessorRuntimeCommandMetaV2DTO(BaseModel):
    """Command response meta: server scope plus command/trace identity."""

    model_config = ConfigDict(extra="forbid")

    project_key: str = Field(..., min_length=1)
    trace_id: str = Field(..., min_length=1)
    command_id: str = Field(..., min_length=1)
    project_scope_ref: SuccessorRuntimeProjectScopeRefDTO


class SuccessorRuntimeProjectionMetaV2DTO(BaseModel):
    """Projection response meta: scope, generation, source digest, cursor."""

    model_config = ConfigDict(extra="forbid")

    project_key: str = Field(..., min_length=1)
    trace_id: str = Field(..., min_length=1)
    projection_id: str = Field(..., min_length=1)
    project_scope_ref: SuccessorRuntimeProjectScopeRefDTO
    projector_id: str = Field(..., min_length=1)
    projector_version: str = Field(..., min_length=1)
    source_kind: str = Field(..., min_length=1)
    source_ref: str = Field(..., min_length=1)
    source_incarnation: str = Field(..., min_length=1)
    projection_generation: int = Field(..., ge=0)
    offset_revision: int = Field(..., ge=0)
    projection_revision: int = Field(..., ge=0)
    source_digest: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    cursor: int = Field(..., ge=0)


class SuccessorRuntimeQueryMetaV2DTO(BaseModel):
    """Query response meta: server scope plus query/trace identity."""

    model_config = ConfigDict(extra="forbid")

    project_key: str = Field(..., min_length=1)
    trace_id: str = Field(..., min_length=1)
    query_id: str = Field(..., min_length=1)
    project_scope_ref: SuccessorRuntimeProjectScopeRefDTO


class SuccessorRuntimeUnresolvedMetaV2DTO(BaseModel):
    """Transport-only meta for scope-resolution failures; no scope is claimed."""

    model_config = ConfigDict(extra="forbid")

    project_key: str = Field(..., min_length=1)
    trace_id: str = Field(..., min_length=1)
    request_id: str = Field(..., min_length=1)
    resolution_state: Literal["UNRESOLVED"] = "UNRESOLVED"


class SuccessorRuntimeApiErrorV2DTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class SuccessorRuntimeRebuildProjectionV2Payload(BaseModel):
    """v2 rebuild intent with the exact server-side projection source key."""

    model_config = ConfigDict(extra="forbid")

    payload_kind: Literal["rebuild_projection"] = "rebuild_projection"
    projection_id: str = Field(..., min_length=1)
    projector_id: str = Field(..., min_length=1)
    projector_version: str = Field(..., min_length=1)
    source_kind: str = Field(..., min_length=1)
    source_ref: str = Field(..., min_length=1)
    source_incarnation: str = Field(..., min_length=1)
    mode: Literal["FULL", "INCREMENTAL"] = "FULL"


class SuccessorRuntimeInvalidateProjectionV2Payload(BaseModel):
    """v2 invalidation intent with the exact server-side projection source key."""

    model_config = ConfigDict(extra="forbid")

    payload_kind: Literal["invalidate_projection"] = "invalidate_projection"
    projection_id: str = Field(..., min_length=1)
    projector_id: str = Field(..., min_length=1)
    projector_version: str = Field(..., min_length=1)
    source_kind: str = Field(..., min_length=1)
    source_ref: str = Field(..., min_length=1)
    source_incarnation: str = Field(..., min_length=1)


class SuccessorRuntimeRollbackProjectionV2Payload(BaseModel):
    """v2 rollback intent with exact key, target and expected active position."""

    model_config = ConfigDict(extra="forbid")

    payload_kind: Literal["rollback_projection"] = "rollback_projection"
    projection_id: str = Field(..., min_length=1)
    projector_id: str = Field(..., min_length=1)
    projector_version: str = Field(..., min_length=1)
    source_kind: str = Field(..., min_length=1)
    source_ref: str = Field(..., min_length=1)
    source_incarnation: str = Field(..., min_length=1)
    target_generation: int = Field(..., ge=0)
    expected_active_generation: int = Field(..., ge=0)
    expected_offset_revision: int = Field(..., ge=0)


CommandPayloadV2 = Annotated[
    SuccessorRuntimeRebuildProjectionV2Payload
    | SuccessorRuntimeInvalidateProjectionV2Payload
    | SuccessorRuntimeRollbackProjectionV2Payload,
    Field(discriminator="payload_kind"),
]


class SuccessorRuntimeCommandV2DTO(BaseModel):
    """External v2 command: locator plus typed intent, no execution fields.

    The wire command never carries actor, resolved schema/scope, authority,
    ``execute``, completion or projection metadata.  The server injects those
    fields only inside the internal facade command contract.
    """

    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(..., min_length=1)
    command_kind: str = Field(..., min_length=1)
    project_locator: str = Field(..., min_length=1)
    trace_id: str = Field(..., min_length=1)
    payload: CommandPayloadV2
    expected_base_token: str | None = Field(default=None, min_length=1)
    approval_locator: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _validate_discriminated_payload(self) -> SuccessorRuntimeCommandV2DTO:
        _lift_successor_contract_failure(
            _validate_command_payload_kind(
                self.command_kind,
                self.payload.payload_kind,
                operation="SuccessorRuntimeCommandV2DTO._validate_discriminated_payload",
            )
        )
        return self


class SuccessorRuntimeQueryV2DTO(BaseModel):
    """External v2 query: locator plus typed read intent only."""

    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(..., min_length=1)
    query_kind: str = Field(..., min_length=1)
    project_locator: str = Field(..., min_length=1)
    trace_id: str = Field(..., min_length=1)
    params: QueryParamsV2

    @model_validator(mode="after")
    def _validate_discriminated_params(self) -> SuccessorRuntimeQueryV2DTO:
        _lift_successor_contract_failure(
            _validate_query_params_kind(
                self.query_kind,
                self.params.params_kind,
                operation="SuccessorRuntimeQueryV2DTO._validate_discriminated_params",
            )
        )
        return self


class SuccessorRuntimeEnvelopeV2DTO(BaseModel):
    """v2 envelope preserving status/data/error/meta with exact variant rules.

    ``ok`` and ``waiting`` require data and forbid error; ``blocked``,
    ``unavailable``, ``conflict`` and ``error`` require a typed error and
    forbid data.  Meta always carries the server scope and trace identity.
    """

    model_config = ConfigDict(extra="forbid")

    status: ApiStatusKindV2
    data: dict[str, Any] | None = None
    error: SuccessorRuntimeApiErrorV2DTO | None = None
    meta: (
        SuccessorRuntimeCommandMetaV2DTO
        | SuccessorRuntimeQueryMetaV2DTO
        | SuccessorRuntimeProjectionMetaV2DTO
        | SuccessorRuntimeUnresolvedMetaV2DTO
    )
    control_feedback: Literal[False] = False

    @model_validator(mode="after")
    def _validate_envelope(self) -> SuccessorRuntimeEnvelopeV2DTO:
        _lift_successor_contract_failure(
            _validate_v2_envelope(self.status, self.data, self.error)
        )
        return self


class RebuildProjectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload_kind: Literal["rebuild_projection"] = "rebuild_projection"
    projection_id: str = Field(..., min_length=1)
    mode: Literal["FULL", "INCREMENTAL"] = "FULL"


class InvalidateProjectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload_kind: Literal["invalidate_projection"] = "invalidate_projection"
    projection_id: str = Field(..., min_length=1)


CommandPayload = Annotated[
    RebuildProjectionPayload | InvalidateProjectionPayload,
    Field(discriminator="payload_kind"),
]


class SuccessorRuntimeCommandDTO(BaseModel):
    """External command DTO: project locator plus typed intent only."""

    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(..., min_length=1)
    command_kind: str = Field(..., min_length=1)
    project_locator: str = Field(..., min_length=1)
    meta: SuccessorRuntimeMeta
    payload: CommandPayload
    execution_mode: Literal["VALIDATION_ONLY"] = "VALIDATION_ONLY"
    execute: Literal[False] = False

    @model_validator(mode="after")
    def _validate_discriminated_payload(self) -> SuccessorRuntimeCommandDTO:
        _lift_successor_contract_failure(
            _validate_command_payload_kind(
                self.command_kind,
                self.payload.payload_kind,
                operation="SuccessorRuntimeCommandDTO._validate_discriminated_payload",
            )
        )
        return self


class ProjectionSnapshotParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    params_kind: Literal["projection_snapshot"] = "projection_snapshot"
    page_size: int | None = Field(default=None, ge=1, le=100)


class SuccessorRuntimeProjectionSnapshotV2Params(BaseModel):
    """v2 snapshot read with the exact server-side projection source key."""

    model_config = ConfigDict(extra="forbid")

    params_kind: Literal["projection_snapshot"] = "projection_snapshot"
    projection_id: str = Field(..., min_length=1)
    projector_id: str = Field(..., min_length=1)
    projector_version: str = Field(..., min_length=1)
    source_kind: str = Field(..., min_length=1)
    source_ref: str = Field(..., min_length=1)
    source_incarnation: str = Field(..., min_length=1)
    page_size: int | None = Field(default=None, ge=1, le=100)


class ProjectionEventsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    params_kind: Literal["projection_events"] = "projection_events"
    after_seq: int = Field(..., ge=0)
    limit: int | None = Field(default=None, ge=1, le=100)


QueryParams = Annotated[
    ProjectionSnapshotParams | ProjectionEventsParams,
    Field(discriminator="params_kind"),
]
QueryParamsV2 = Annotated[
    SuccessorRuntimeProjectionSnapshotV2Params,
    Field(discriminator="params_kind"),
]


class SuccessorRuntimeQueryDTO(BaseModel):
    """External query DTO: project locator plus typed query intent only."""

    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(..., min_length=1)
    query_kind: str = Field(..., min_length=1)
    project_locator: str = Field(..., min_length=1)
    meta: SuccessorRuntimeMeta
    params: QueryParams
    read_only: Literal[True] = True

    @model_validator(mode="after")
    def _validate_discriminated_params(self) -> SuccessorRuntimeQueryDTO:
        _lift_successor_contract_failure(
            _validate_query_params_kind(
                self.query_kind,
                self.params.params_kind,
                operation="SuccessorRuntimeQueryDTO._validate_discriminated_params",
            )
        )
        return self


class SuccessorRuntimeApiErrorDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class SuccessorRuntimeApiEnvelopeDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ApiStatusKind
    data: dict[str, Any] | None = None
    error: SuccessorRuntimeApiErrorDTO | None = None
    meta: SuccessorRuntimeProjectionMetaDTO
    control_feedback: Literal[False] = False

    @model_validator(mode="after")
    def _validate_envelope(self) -> SuccessorRuntimeApiEnvelopeDTO:
        _lift_successor_contract_failure(
            _validate_legacy_envelope(self.status, self.data, self.error)
        )
        return self


class SuccessorRuntimeUiObservationDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state: UiObservationState
    projection_id: str = Field(..., min_length=1)
    meta: SuccessorRuntimeProjectionMetaDTO
    data: dict[str, Any] | None = None
    reason: str | None = None
    control_feedback: Literal[False] = False


class SuccessorRuntimeEventDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int = Field(..., ge=0)
    event_type: str = Field(..., min_length=1)
    projection_id: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class SuccessorRuntimeSseObservationDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    after_seq: int = Field(..., ge=0)
    reconnect: bool = False
    meta: SuccessorRuntimeProjectionMetaDTO
    events: list[SuccessorRuntimeEventDTO] = Field(default_factory=list)
    next_seq: int = Field(..., ge=0)

    @model_validator(mode="after")
    def _validate_after_seq_exclusive(
        self,
    ) -> SuccessorRuntimeSseObservationDTO:
        _lift_successor_contract_failure(
            _validate_sse_observation(self.after_seq, self.events, self.next_seq)
        )
        return self
