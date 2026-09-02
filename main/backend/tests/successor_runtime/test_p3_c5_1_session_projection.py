"""C5.1 journal-derived read-only session/task projection acceptance."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from app.successor_migration.legacy_agent_sessions import (
    IncompleteLegacySessionPayload,
    UnsupportedLegacySessionStatus,
    project_legacy_session_read_model,
)
from app.successor_runtime.runtime.replay import (
    ReplayEvent,
    RuntimeReplayProjection,
    replay_runtime_events,
)
from app.successor_runtime.runtime.transitions import RunState
from app.successor_runtime.substrate.projections.agent_session import (
    AgentSessionProjectionError,
    SessionStatus,
    TaskStatus,
    fold_agent_session,
)

from .test_p0d_event_replay import _real_happy_event_shape


def _happy_projection() -> RuntimeReplayProjection:
    return replay_runtime_events(_real_happy_event_shape())


def test_happy_journal_folds_to_completed_session_with_digest_binding() -> None:
    projection = _happy_projection()
    snapshot = fold_agent_session(projection)

    assert snapshot.session_id == projection.run_id
    assert snapshot.status is SessionStatus.COMPLETED
    assert snapshot.source_revision == snapshot.last_seq == 9
    assert snapshot.source_digest == projection.event_chain_digest
    assert snapshot.terminal_events == ("RunCompletionDerived",)
    assert len(snapshot.projection_digest) == 64
    assert len(snapshot.tasks) == 1
    task = snapshot.tasks[0]
    assert task.task_id == "step-a"
    assert task.status is TaskStatus.COMPLETED
    assert task.attempt_id == "attempt-a"
    assert task.disposition.value == "SUCCEEDED"
    assert fold_agent_session(projection) == snapshot


def test_terminal_control_snapshot_without_terminal_event_cannot_fabricate() -> None:
    partial = replay_runtime_events(_real_happy_event_shape()[:8])
    drifted = replace(partial, run_state=RunState.COMPLETED)

    snapshot = fold_agent_session(drifted)

    assert snapshot.status is SessionStatus.UNKNOWN
    assert snapshot.terminal_events == ()
    assert snapshot.fabricated_terminal is False


def test_fold_rejects_non_replay_projection() -> None:
    with pytest.raises(AgentSessionProjectionError):
        fold_agent_session({"not": "a projection"})  # type: ignore[arg-type]


def test_legacy_session_read_model_replays_without_authority() -> None:
    now = datetime(2030, 1, 1, tzinfo=UTC)
    read_model = project_legacy_session_read_model(
        {"session_id": "legacy-session", "status": "active", "task_count": 2},
        [
            {
                "session_id": "legacy-session",
                "task_id": "task-b",
                "status": "completed",
                "blocked_by": ["task-a"],
                "write_set": ["value:b"],
            },
            {
                "session_id": "legacy-session",
                "task_id": "task-a",
                "status": "in_progress",
            },
        ],
        observed_at=now,
        source_ref="legacy:agent-sessions:legacy-session",
    )

    assert read_model.session.status == "active"
    assert [item.task_id for item in read_model.tasks] == ["task-a", "task-b"]
    assert read_model.tasks[1].blocked_by == ("task-a",)
    assert read_model.authority == "PROJECTION_ONLY"
    assert read_model.session.terminal_authority_claim is None
    assert len(read_model.read_model_digest) == 64


def test_legacy_replay_rejects_invalid_status_and_missing_identity() -> None:
    now = datetime(2030, 1, 1, tzinfo=UTC)
    with pytest.raises(UnsupportedLegacySessionStatus):
        project_legacy_session_read_model(
            {"session_id": "s", "status": "bogus"},
            [],
            observed_at=now,
            source_ref="legacy:agent-sessions:s",
        )
    with pytest.raises(IncompleteLegacySessionPayload):
        project_legacy_session_read_model(
            {"status": "active"},
            [],
            observed_at=now,
            source_ref="legacy:agent-sessions:s",
        )


def test_session_status_vocabulary_is_bounded() -> None:
    assert SessionStatus.__members__ == {
        "PENDING": SessionStatus.PENDING,
        "ACTIVE": SessionStatus.ACTIVE,
        "BLOCKED": SessionStatus.BLOCKED,
        "COMPLETED": SessionStatus.COMPLETED,
        "FAILED": SessionStatus.FAILED,
        "CANCELED": SessionStatus.CANCELED,
        "UNKNOWN": SessionStatus.UNKNOWN,
    }


def test_replay_event_helper_stays_source_grounded() -> None:
    events = _real_happy_event_shape()
    assert events[0].event_type == "ProgramAccepted"
    assert events[-1].event_type == "RunCompletionDerived"
    assert all(isinstance(event, ReplayEvent) for event in events)
