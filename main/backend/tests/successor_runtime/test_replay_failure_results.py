"""Typed failure witnesses for the successor replay core."""

from __future__ import annotations

from functorial_kit import Failure

from app.successor_runtime.runtime.replay import (
    ReplayEvent,
    RuntimeReplayProjection,
    replay_runtime_events_result,
)


def _program_event(**overrides: object) -> dict[str, object]:
    content: dict[str, object] = {
        "project_key": "project",
        "run_id": "run",
        "run_incarnation": "incarnation",
        "seq": 1,
        "event_type": "ProgramAccepted",
        "schema_version": "mrw.runtime.event.program_accepted.v1",
        "step_id": None,
        "attempt_id": None,
        "metadata": {"program_digest": "a" * 64},
        "payload_ref": None,
        "payload_digest": None,
        "authority_digest": "b" * 64,
    }
    content.update(overrides)
    return content


def test_replay_decoders_return_typed_failures_without_throwing() -> None:
    event_failure = ReplayEvent.from_content_result(
        **_program_event(event_type="Unknown", schema_version="unknown")
    )
    projection_failure = RuntimeReplayProjection.from_json_result({"schema": "unknown"})

    assert isinstance(event_failure, Failure)
    assert event_failure.family == "successor.runtime.failure"
    assert event_failure.code == "REPLAY_EVENT_INVALID"
    assert isinstance(projection_failure, Failure)
    assert projection_failure.code == "REPLAY_PROJECTION_INVALID"


def test_replay_fold_failure_preserves_sequence_classification() -> None:
    first = ReplayEvent.from_content(**_program_event())
    second = ReplayEvent.from_content(**_program_event(seq=3))

    result = replay_runtime_events_result((first, second))

    assert isinstance(result, Failure)
    assert result.code == "REPLAY_SEQUENCE_INVALID"
    assert "expected 2, got 3" in result.message
