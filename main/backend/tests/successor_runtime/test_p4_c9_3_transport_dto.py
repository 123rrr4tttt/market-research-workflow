"""P4 C9 successor runtime transport DTOs (route-free wire boundary)."""

from __future__ import annotations

import pytest
from app.contracts.successor_runtime import (
    API_STATUS_KINDS,
    UI_OBSERVATION_STATES,
    SuccessorRuntimeApiEnvelopeDTO,
    SuccessorRuntimeApiErrorDTO,
    SuccessorRuntimeCommandDTO,
    SuccessorRuntimeEventDTO,
    SuccessorRuntimeMeta,
    SuccessorRuntimeProjectionMetaDTO,
    SuccessorRuntimeProjectScopeRefDTO,
    SuccessorRuntimeQueryDTO,
    SuccessorRuntimeSseObservationDTO,
    SuccessorRuntimeUiObservationDTO,
)
from pydantic import ValidationError


def _scope() -> SuccessorRuntimeProjectScopeRefDTO:
    return SuccessorRuntimeProjectScopeRefDTO(
        project_key="p4-c9-demo",
        resolved_schema="mrw_p4_c9_demo",
        project_registry_revision=1,
        incarnation="scope-inc-c9",
        scope_digest="a" * 64,
    )


def _meta() -> SuccessorRuntimeMeta:
    return SuccessorRuntimeMeta(
        project_key="p4-c9-demo",
        trace_id="trace-1",
        projection_id="projection.run-summary.v1",
    )


def _projection_meta() -> SuccessorRuntimeProjectionMetaDTO:
    return SuccessorRuntimeProjectionMetaDTO(
        project_key="p4-c9-demo",
        trace_id="trace-1",
        projection_id="projection.run-summary.v1",
        project_scope_ref=_scope(),
        projection_revision=3,
        source_digest="a" * 64,
        cursor=2,
    )


def _command() -> SuccessorRuntimeCommandDTO:
    return SuccessorRuntimeCommandDTO(
        command_id="cmd-1",
        command_kind="rebuild_projection",
        project_locator="p4-c9-demo",
        meta=_meta(),
        payload={
            "payload_kind": "rebuild_projection",
            "projection_id": "projection.run-summary.v1",
            "mode": "FULL",
        },
    )


def _query() -> SuccessorRuntimeQueryDTO:
    return SuccessorRuntimeQueryDTO(
        query_id="query-1",
        query_kind="projection_events",
        project_locator="p4-c9-demo",
        meta=_meta(),
        params={
            "params_kind": "projection_events",
            "after_seq": 5,
            "limit": 20,
        },
    )


def _envelope() -> SuccessorRuntimeApiEnvelopeDTO:
    return SuccessorRuntimeApiEnvelopeDTO(
        status="ok",
        data={"projection_id": "projection.run-summary.v1"},
        error=None,
        meta=_projection_meta(),
    )


def _ui() -> SuccessorRuntimeUiObservationDTO:
    return SuccessorRuntimeUiObservationDTO(
        state="ready",
        projection_id="projection.run-summary.v1",
        meta=_projection_meta(),
        data={"items": []},
    )


def _sse() -> SuccessorRuntimeSseObservationDTO:
    return SuccessorRuntimeSseObservationDTO(
        after_seq=1,
        reconnect=True,
        meta=_projection_meta(),
        events=[
            SuccessorRuntimeEventDTO(
                seq=2,
                event_type="projection.updated",
                projection_id="projection.run-summary.v1",
            ),
        ],
        next_seq=2,
    )


def test_command_dto_is_locator_plus_discriminated_typed_intent() -> None:
    restored = SuccessorRuntimeCommandDTO.model_validate(_command().model_dump())
    assert restored == _command()
    assert restored.execute is False
    assert restored.payload.payload_kind == "rebuild_projection"

    mismatched = _command().model_dump()
    mismatched["command_kind"] = "invalidate_projection"
    with pytest.raises(ValidationError):
        SuccessorRuntimeCommandDTO.model_validate(mismatched)

    payload = _command().model_dump()
    payload["execute"] = True
    with pytest.raises(ValidationError):
        SuccessorRuntimeCommandDTO.model_validate(payload)


def test_external_command_dto_rejects_server_scope_and_actor_fields() -> None:
    base = _command().model_dump()
    for field_name in (
        "resolved_schema",
        "project_registry_revision",
        "incarnation",
        "scope_digest",
        "actor_ref",
    ):
        with pytest.raises(ValidationError):
            SuccessorRuntimeCommandDTO.model_validate({**base, field_name: "x"})
    with pytest.raises(ValidationError):
        SuccessorRuntimeCommandDTO.model_validate(
            {**base, "project_scope_ref": _scope().model_dump()}
        )


def test_query_dto_is_locator_plus_discriminated_typed_params() -> None:
    query = _query()
    assert query.read_only is True
    assert query.params.after_seq == 5
    assert SuccessorRuntimeQueryDTO.model_validate(query.model_dump()) == query

    mismatched = query.model_dump()
    mismatched["query_kind"] = "projection_snapshot"
    with pytest.raises(ValidationError):
        SuccessorRuntimeQueryDTO.model_validate(mismatched)

    with pytest.raises(ValidationError):
        SuccessorRuntimeQueryDTO.model_validate(
            {**query.model_dump(), "read_only": False}
        )
    with pytest.raises(ValidationError):
        SuccessorRuntimeQueryDTO.model_validate({**query.model_dump(), "control": 1})


def test_api_envelope_dto_restores_status_data_error_meta() -> None:
    envelope = _envelope()
    assert tuple(API_STATUS_KINDS) == (
        "ok",
        "error",
        "unavailable",
        "blocked",
        "waiting",
    )
    assert envelope.status == "ok"
    assert envelope.data is not None
    assert envelope.error is None
    assert envelope.meta.project_scope_ref == _scope()
    assert envelope.meta.projection_revision == 3
    assert envelope.meta.source_digest == "a" * 64
    assert envelope.meta.cursor == 2
    assert envelope.control_feedback is False
    assert (
        SuccessorRuntimeApiEnvelopeDTO.model_validate(envelope.model_dump()) == envelope
    )

    error_payload = _envelope().model_dump()
    error_payload.update(
        status="error",
        data=None,
        error=SuccessorRuntimeApiErrorDTO(
            code="E1",
            message="boom",
        ).model_dump(),
    )
    assert (
        SuccessorRuntimeApiEnvelopeDTO.model_validate(error_payload).status == "error"
    )

    missing_error = {**error_payload, "error": None}
    with pytest.raises(ValidationError):
        SuccessorRuntimeApiEnvelopeDTO.model_validate(missing_error)

    forbidden_error = _envelope().model_dump()
    forbidden_error["error"] = SuccessorRuntimeApiErrorDTO(
        code="E1",
        message="boom",
    ).model_dump()
    with pytest.raises(ValidationError):
        SuccessorRuntimeApiEnvelopeDTO.model_validate(forbidden_error)

    with pytest.raises(ValidationError):
        SuccessorRuntimeApiEnvelopeDTO.model_validate(
            {**_envelope().model_dump(), "control_feedback": True}
        )
    with pytest.raises(ValidationError):
        SuccessorRuntimeApiEnvelopeDTO.model_validate(
            {**_envelope().model_dump(), "control_directive": "resume"}
        )


def test_ui_dto_six_states_are_independent_and_control_free() -> None:
    assert tuple(UI_OBSERVATION_STATES) == (
        "ready",
        "waiting",
        "blocked",
        "unavailable",
        "conflict",
        "failed",
    )
    for state in UI_OBSERVATION_STATES:
        observation = _ui().model_dump()
        observation["state"] = state
        assert (
            SuccessorRuntimeUiObservationDTO.model_validate(observation).state == state
        )
    with pytest.raises(ValidationError):
        SuccessorRuntimeUiObservationDTO.model_validate(
            {**_ui().model_dump(), "state": "unknown"}
        )
    with pytest.raises(ValidationError):
        SuccessorRuntimeUiObservationDTO.model_validate(
            {**_ui().model_dump(), "control_feedback": True}
        )


def test_sse_dto_after_seq_exclusive_and_reconnect() -> None:
    observation = _sse()
    assert observation.meta.project_scope_ref == _scope()
    assert (
        SuccessorRuntimeSseObservationDTO.model_validate(observation.model_dump())
        == observation
    )

    inclusive = observation.model_dump()
    inclusive["events"][0]["seq"] = 1
    with pytest.raises(ValidationError):
        SuccessorRuntimeSseObservationDTO.model_validate(inclusive)

    mismatched = observation.model_dump()
    mismatched["next_seq"] = 3
    with pytest.raises(ValidationError):
        SuccessorRuntimeSseObservationDTO.model_validate(mismatched)

    empty = observation.model_dump()
    empty["events"] = []
    empty["next_seq"] = observation.after_seq
    assert SuccessorRuntimeSseObservationDTO.model_validate(empty).reconnect is True

    with pytest.raises(ValidationError):
        SuccessorRuntimeSseObservationDTO.model_validate(
            {**observation.model_dump(), "snapshot_authority": "on"}
        )
