"""P4 C9 facade contracts: API/UI unions, command binding, pure validation."""

from __future__ import annotations

from dataclasses import replace

from app.successor_runtime.runtime.facade_contracts import (
    API_STATUS_KINDS,
    UI_OBSERVATION_STATES,
    ApiEnvelope,
    ApiError,
    FacadeCommand,
    FacadeQuery,
    ProjectionEvent,
    ProjectionMeta,
    ProjectionResponseMeta,
    SseObservation,
    UiObservation,
    validate_api_envelope,
    validate_command,
    validate_query,
    validate_response_meta,
    validate_sse_observation,
    validate_ui_observation,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef

_SCOPE = ProjectScopeRef(
    project_key="p4-c9-demo",
    resolved_schema="mrw_p4_c9_demo",
    project_registry_revision=1,
    incarnation="scope-inc-c9",
    scope_digest="a" * 64,
)


def _meta(**overrides: str) -> ProjectionMeta:
    values = {
        "project_key": "p4-c9-demo",
        "trace_id": "trace-1",
        "projection_id": "projection.run-summary.v1",
    }
    values.update(overrides)
    return ProjectionMeta(**values)


def _response_meta(**overrides: object) -> ProjectionResponseMeta:
    values: dict[str, object] = {
        "project_key": "p4-c9-demo",
        "trace_id": "trace-1",
        "projection_id": "projection.run-summary.v1",
        "project_scope_ref": _SCOPE,
        "projection_revision": 3,
        "source_digest": "a" * 64,
        "cursor": 2,
    }
    values.update(overrides)
    return ProjectionResponseMeta(**values)


def _command(**overrides: object) -> FacadeCommand:
    values: dict[str, object] = {
        "command_id": "cmd-1",
        "command_kind": "rebuild_projection",
        "description": "describe a projection rebuild",
        "project_scope_ref": _SCOPE,
        "actor_ref": "actor:user-1",
        "idempotency_key": "idem-1",
        "expected_revision_or_incarnation": "revision:1|inc:scope-inc-c9",
        "meta": _meta(),
        "approval_ref": None,
    }
    values.update(overrides)
    return FacadeCommand(**values)


def _query(**overrides: object) -> FacadeQuery:
    values: dict[str, object] = {
        "query_id": "query-1",
        "query_kind": "projection_snapshot",
        "project_scope_ref": _SCOPE,
        "meta": _meta(),
        "after_seq": None,
    }
    values.update(overrides)
    return FacadeQuery(**values)


def _envelope(**overrides: object) -> ApiEnvelope:
    values: dict[str, object] = {
        "status": "ok",
        "meta": _response_meta(),
        "data": {"projection_id": "projection.run-summary.v1"},
        "error": None,
    }
    values.update(overrides)
    return ApiEnvelope(**values)


def _ui(**overrides: object) -> UiObservation:
    values: dict[str, object] = {
        "state": "ready",
        "projection_id": "projection.run-summary.v1",
        "meta": _response_meta(),
        "data": {"items": []},
        "reason": None,
    }
    values.update(overrides)
    return UiObservation(**values)


def _observation(**overrides: object) -> SseObservation:
    values: dict[str, object] = {
        "after_seq": 1,
        "reconnect": False,
        "meta": _response_meta(),
        "events": (
            ProjectionEvent(
                seq=2,
                event_type="projection.updated",
                projection_id="projection.run-summary.v1",
            ),
        ),
        "next_seq": 2,
    }
    values.update(overrides)
    return SseObservation(**values)


def test_api_and_ui_unions_are_separate() -> None:
    assert tuple(API_STATUS_KINDS) == (
        "ok",
        "error",
        "unavailable",
        "blocked",
        "waiting",
    )
    assert tuple(UI_OBSERVATION_STATES) == (
        "ready",
        "waiting",
        "blocked",
        "unavailable",
        "conflict",
        "failed",
    )


def test_command_binds_scope_actor_idempotency_expected_and_approval() -> None:
    command = _command()
    assert command.project_scope_ref == _SCOPE
    assert command.actor_ref
    assert command.idempotency_key
    assert command.expected_revision_or_incarnation
    assert command.approval_ref is None
    assert command.execution_mode == "VALIDATION_ONLY"
    assert command.execute is False
    assert validate_command(command).valid

    with_approval = replace(command, approval_ref="approval:grant-1")
    assert validate_command(with_approval).valid

    executed = replace(command, execute=True)
    assert any(
        v.code == "COMMAND_EXECUTION_FORBIDDEN"
        for v in validate_command(executed).violations
    )

    unbound = replace(command, project_scope_ref=None)  # type: ignore[arg-type]
    assert any(
        v.code == "PROJECT_SCOPE_REF_REQUIRED"
        for v in validate_command(unbound).violations
    )


def test_query_is_read_only_and_binds_after_seq() -> None:
    query = _query(after_seq=5)
    assert query.read_only is True
    assert validate_query(query).valid

    mutable = replace(query, read_only=False)
    assert any(
        v.code == "QUERY_MUTATION_FORBIDDEN" for v in validate_query(mutable).violations
    )

    negative = replace(query, after_seq=-1)
    assert any(
        v.code == "SSE_AFTER_SEQ_NEGATIVE" for v in validate_query(negative).violations
    )


def test_response_meta_carries_scope_revision_source_digest_cursor() -> None:
    meta = _response_meta()
    assert meta.project_scope_ref == _SCOPE
    assert meta.projection_revision == 3
    assert meta.source_digest == "a" * 64
    assert meta.cursor == 2
    assert validate_response_meta(meta).valid

    negative_revision = replace(meta, projection_revision=-1)
    assert any(
        v.code == "PROJECTION_REVISION_NEGATIVE"
        for v in validate_response_meta(negative_revision).violations
    )
    bad_digest = replace(meta, source_digest="not-hex")
    assert any(
        v.code == "SOURCE_DIGEST_INVALID"
        for v in validate_response_meta(bad_digest).violations
    )
    negative_cursor = replace(meta, cursor=-1)
    assert any(
        v.code == "CURSOR_NEGATIVE"
        for v in validate_response_meta(negative_cursor).violations
    )


def test_api_envelope_restores_status_data_error_meta() -> None:
    envelope = _envelope()
    assert envelope.status == "ok"
    assert envelope.data is not None
    assert envelope.error is None
    assert envelope.meta == _response_meta()
    assert envelope.control_feedback is False
    assert validate_api_envelope(envelope).valid

    error_envelope = _envelope(
        status="error",
        data=None,
        error=ApiError(code="E1", message="boom"),
    )
    assert validate_api_envelope(error_envelope).valid

    missing_error = replace(error_envelope, error=None)
    assert any(
        v.code == "ENVELOPE_ERROR_REQUIRED"
        for v in validate_api_envelope(missing_error).violations
    )

    forbidden_error = replace(envelope, error=ApiError(code="E1", message="boom"))
    assert any(
        v.code == "ENVELOPE_ERROR_FORBIDDEN"
        for v in validate_api_envelope(forbidden_error).violations
    )

    feedback = replace(envelope, control_feedback=True)
    assert any(
        v.code == "CONTROL_FEEDBACK_FORBIDDEN"
        for v in validate_api_envelope(feedback).violations
    )


def test_ui_observation_six_states_are_independent() -> None:
    for state in UI_OBSERVATION_STATES:
        observation = _ui(state=state)  # type: ignore[arg-type]
        assert validate_ui_observation(observation).valid

    unknown = _ui(state="unknown")  # type: ignore[arg-type]
    assert any(
        v.code == "UNKNOWN_UI_STATE"
        for v in validate_ui_observation(unknown).violations
    )

    feedback = replace(_ui(), control_feedback=True)
    assert any(
        v.code == "CONTROL_FEEDBACK_FORBIDDEN"
        for v in validate_ui_observation(feedback).violations
    )


def test_sse_after_seq_is_exclusive_and_reconnect_is_observed() -> None:
    observation = _observation(reconnect=True)
    assert validate_sse_observation(observation).valid

    inclusive = _observation(
        events=(
            ProjectionEvent(
                seq=1,
                event_type="projection.updated",
                projection_id="projection.run-summary.v1",
            ),
        ),
        next_seq=1,
    )
    assert any(
        v.code == "SSE_AFTER_SEQ_EXCLUSIVE"
        for v in validate_sse_observation(inclusive).violations
    )

    duplicate = _observation(
        events=(
            ProjectionEvent(
                seq=2,
                event_type="projection.updated",
                projection_id="projection.run-summary.v1",
            ),
            ProjectionEvent(
                seq=2,
                event_type="projection.updated",
                projection_id="projection.run-summary.v1",
            ),
        ),
        next_seq=2,
    )
    assert any(
        v.code == "SSE_SEQ_MONOTONIC"
        for v in validate_sse_observation(duplicate).violations
    )

    mismatched = _observation(next_seq=3)
    assert any(
        v.code == "SSE_NEXT_SEQ_MISMATCH"
        for v in validate_sse_observation(mismatched).violations
    )

    empty = _observation(events=(), next_seq=1)
    assert validate_sse_observation(empty).valid
