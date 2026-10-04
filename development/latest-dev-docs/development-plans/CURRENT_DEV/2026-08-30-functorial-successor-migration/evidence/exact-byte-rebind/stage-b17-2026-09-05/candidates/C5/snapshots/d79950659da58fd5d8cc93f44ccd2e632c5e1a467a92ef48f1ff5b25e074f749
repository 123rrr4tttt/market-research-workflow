"""Journal-derived read-only AgentSession/AgentTask projection.

The successor runtime journal is the only authority: session/task status is
folded from ordered runtime events, never from the mutable ``runtime_runs`` /
``runtime_steps`` snapshots.  A terminal-looking control snapshot without the
corresponding terminal event therefore projects as ``UNKNOWN`` instead of
manufacturing a terminal sequence.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.engine import Connection

from app.successor_runtime.runtime.assignments import (
    Digest,
    FrozenContract,
    canonical_digest,
)
from app.successor_runtime.runtime.ports import RuntimeScope
from app.successor_runtime.runtime.replay import (
    ReplayEvent,
    RuntimeReplayError,
    RuntimeReplayProjection,
    replay_runtime_events,
)
from app.successor_runtime.runtime.transitions import (
    EffectDisposition,
    RunState,
    StepState,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
    RecordNotFound,
    _mapping_rows,
    _one_mapping,
    _scope_key,
    _table,
)

from .runtime_run import RuntimeJournalSource


class AgentSessionProjectionError(ExactBindingConflict):
    """The journal cannot produce a trustworthy session/task read model."""


class SessionStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    UNKNOWN = "unknown"


class TaskStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    EXPIRED = "expired"
    NOT_SELECTED = "not_selected"
    UNKNOWN = "unknown"


class AgentTaskSnapshot(FrozenContract):
    schema_version: Literal["mrw.successor.agent-task-snapshot.v1"] = (
        "mrw.successor.agent-task-snapshot.v1"
    )
    task_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    step_state: StepState
    status: TaskStatus
    attempt_id: str | None = None
    disposition: EffectDisposition | None = None
    blocked_by: tuple[str, ...] = ()
    failure_ref: str | None = None
    revision: int = 0

    @model_validator(mode="after")
    def validate_snapshot(self) -> AgentTaskSnapshot:
        if self.revision < 0:
            raise ValueError("agent task snapshot revision must be non-negative")
        if self.task_id != self.step_id:
            raise ValueError("agent task snapshot task_id must bind step_id")
        return self


class AgentSessionSnapshot(FrozenContract):
    """Disposable session read model bound to one journal run incarnation."""

    schema_version: Literal["mrw.successor.agent-session-snapshot.v1"] = (
        "mrw.successor.agent-session-snapshot.v1"
    )
    session_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    run_incarnation: str = Field(min_length=1)
    status: SessionStatus
    current_phase: str | None = None
    last_seq: int = Field(ge=1)
    source_revision: int = Field(ge=1)
    source_digest: Digest
    projection_digest: Digest
    tasks: tuple[AgentTaskSnapshot, ...] = ()
    observed_event_types: tuple[str, ...] = ()
    terminal_events: tuple[str, ...] = ()
    fabricated_terminal: Literal[False] = False

    @model_validator(mode="after")
    def validate_projection(self) -> AgentSessionSnapshot:
        if self.source_revision != self.last_seq:
            raise ValueError("session projection source revision must equal last_seq")
        if tuple(sorted(self.tasks, key=lambda item: item.task_id)) != self.tasks:
            raise ValueError("session projection tasks are not canonically ordered")
        terminal = frozenset(self.terminal_events)
        if (
            self.status is SessionStatus.COMPLETED
            and "RunCompletionDerived" not in terminal
        ):
            raise ValueError(
                "session COMPLETED requires the exact terminal journal event"
            )
        if self.status is SessionStatus.FAILED and not (
            terminal & {"RequiredStepFailed", "AuthoritativeReadbackFailed"}
        ):
            raise ValueError("session FAILED requires the exact terminal journal event")
        if self.status is SessionStatus.CANCELED and not (
            terminal
            & {
                "CancellationRequested",
                "RequiredCleanupAndReadbackSettled",
                "SuccessorMaterialized",
            }
        ):
            raise ValueError(
                "session CANCELED requires the exact terminal journal event"
            )
        if self.fabricated_terminal:
            raise ValueError("session projection must never fabricate terminal state")
        expected = canonical_digest(self, exclude_fields={"projection_digest"})
        if self.projection_digest != expected:
            raise ValueError("session projection_digest mismatch")
        return self


def fold_agent_session(
    projection: RuntimeReplayProjection,
    *,
    session_id: str | None = None,
) -> AgentSessionSnapshot:
    """Fold one replay projection into a disposable session/task read model."""

    if not isinstance(projection, RuntimeReplayProjection):
        raise AgentSessionProjectionError("session fold requires replay projection")
    session = session_id or projection.run_id
    tasks = tuple(
        _task_snapshot(projection, step_id=step_id, state=state, session_id=session)
        for step_id, state in projection.steps
    )
    status, terminal_events = _session_status(projection)
    provisional = AgentSessionSnapshot.model_construct(
        session_id=session,
        run_id=projection.run_id,
        run_incarnation=projection.run_incarnation,
        status=status,
        last_seq=projection.last_seq,
        source_revision=projection.last_seq,
        source_digest=projection.event_chain_digest,
        projection_digest="0" * 64,
        tasks=tasks,
        observed_event_types=projection.observed_event_types,
        terminal_events=terminal_events,
    )
    values = provisional.model_dump(mode="python")
    values.pop("projection_digest")
    return AgentSessionSnapshot(
        **values,
        projection_digest=canonical_digest(
            provisional,
            exclude_fields={"projection_digest"},
        ),
    )


def _task_snapshot(
    projection: RuntimeReplayProjection,
    *,
    step_id: str,
    state: StepState,
    session_id: str,
) -> AgentTaskSnapshot:
    attempt_steps = dict(projection.attempt_step_bindings)
    attempts = dict(projection.attempts)
    attempt_ids = sorted(
        attempt_id
        for attempt_id, bound_step in attempt_steps.items()
        if bound_step == step_id
    )
    attempt_id = attempt_ids[0] if attempt_ids else None
    return AgentTaskSnapshot(
        task_id=step_id,
        session_id=session_id,
        step_id=step_id,
        step_state=state,
        status=_task_status(state),
        attempt_id=attempt_id,
        disposition=attempts.get(attempt_id) if attempt_id is not None else None,
    )


def _task_status(state: StepState) -> TaskStatus:
    if state is StepState.SUCCEEDED:
        return TaskStatus.COMPLETED
    if state is StepState.FAILED:
        return TaskStatus.FAILED
    if state in {StepState.CANCELLED, StepState.SUPERSEDED}:
        return TaskStatus.CANCELED
    if state in {StepState.NOT_SELECTED, StepState.SKIPPED_BY_DECISION}:
        return TaskStatus.NOT_SELECTED
    if state in {
        StepState.PENDING,
        StepState.AWAITING_APPROVAL,
        StepState.READY,
        StepState.RETRY_SCHEDULED,
    }:
        return TaskStatus.PENDING
    if state is StepState.CLAIMED:
        return TaskStatus.CLAIMED
    if state in {StepState.RUNNING, StepState.COMMITTING}:
        return TaskStatus.IN_PROGRESS
    if state in {
        StepState.WAITING_EXTERNAL,
        StepState.RECONCILING,
        StepState.CANCEL_REQUESTED,
    }:
        return TaskStatus.BLOCKED
    return TaskStatus.UNKNOWN


def _session_status(
    projection: RuntimeReplayProjection,
) -> tuple[SessionStatus, tuple[str, ...]]:
    observed = frozenset(projection.observed_event_types)
    if projection.run_state is RunState.COMPLETED:
        terminal = (
            ("RunCompletionDerived",) if "RunCompletionDerived" in observed else ()
        )
        return (
            SessionStatus.COMPLETED if terminal else SessionStatus.UNKNOWN,
            terminal,
        )
    if projection.run_state is RunState.FAILED:
        terminal = tuple(
            event
            for event in (
                "RequiredStepFailed",
                "AuthoritativeReadbackFailed",
            )
            if event in observed
        )
        return (
            SessionStatus.FAILED if terminal else SessionStatus.UNKNOWN,
            terminal,
        )
    if projection.run_state is RunState.CANCELLED:
        terminal = tuple(
            event
            for event in (
                "CancellationRequested",
                "RequiredCleanupAndReadbackSettled",
                "SuccessorMaterialized",
            )
            if event in observed
        )
        return (
            SessionStatus.CANCELED if terminal else SessionStatus.UNKNOWN,
            terminal,
        )
    if projection.run_state is RunState.SUPERSEDED:
        terminal = (
            ("SuccessorMaterialized",) if "SuccessorMaterialized" in observed else ()
        )
        return (
            SessionStatus.CANCELED if terminal else SessionStatus.UNKNOWN,
            terminal,
        )
    status = {
        RunState.SUBMITTED: SessionStatus.PENDING,
        RunState.COMPILING: SessionStatus.PENDING,
        RunState.AWAITING_APPROVAL: SessionStatus.BLOCKED,
        RunState.READY: SessionStatus.ACTIVE,
        RunState.RUNNING: SessionStatus.ACTIVE,
        RunState.WAITING: SessionStatus.BLOCKED,
        RunState.RECONCILING: SessionStatus.BLOCKED,
        RunState.CANCELLING: SessionStatus.BLOCKED,
    }.get(projection.run_state, SessionStatus.UNKNOWN)
    return status, ()


class PostgresAgentSessionReadAdapter:
    """Read-only adapter that folds journal events without any write."""

    source_kind = "runtime_journal"

    def __init__(self, connection: Connection, scope: RuntimeScope) -> None:
        self.connection = connection
        self.scope = scope

    def load(self, source: RuntimeJournalSource) -> AgentSessionSnapshot:
        if source.source_kind != self.source_kind:
            raise AgentSessionProjectionError("agent session source kind mismatch")
        if source.source_ref != f"runtime-run:{source.run_id}":
            raise AgentSessionProjectionError(
                "agent session source_ref is not canonical"
            )
        self._require_source_identity(source)
        events = self._load_events(source)
        try:
            projection = replay_runtime_events(events)
        except RuntimeReplayError as exc:
            raise AgentSessionProjectionError(
                "agent session journal replay failed closed"
            ) from exc
        return fold_agent_session(projection)

    def _require_source_identity(self, source: RuntimeJournalSource) -> None:
        runs = _table("runtime_runs")
        row = _one_mapping(
            self.connection.execute(
                select(
                    runs.c.project_key,
                    runs.c.run_id,
                    runs.c.incarnation,
                ).where(
                    runs.c.project_key == _scope_key(self.scope),
                    runs.c.run_id == source.run_id,
                )
            )
        )
        if row is None:
            raise RecordNotFound(
                f"agent session projection source not found: {source.run_id}"
            )
        if row["incarnation"] != source.run_incarnation:
            raise AgentSessionProjectionError(
                "agent session projection source incarnation is stale"
            )

    def _load_events(self, source: RuntimeJournalSource) -> tuple[ReplayEvent, ...]:
        table = _table("runtime_events")
        rows = _mapping_rows(
            self.connection.execute(
                select(table)
                .where(
                    table.c.project_key == _scope_key(self.scope),
                    table.c.run_id == source.run_id,
                    table.c.seq >= 1,
                )
                .order_by(table.c.seq)
            )
        )
        return tuple(
            ReplayEvent.from_content(
                project_key=str(row["project_key"]),
                run_id=str(row["run_id"]),
                run_incarnation=source.run_incarnation,
                seq=int(row["seq"]),
                event_type=str(row["event_type"]),
                schema_version=str(row["schema_version"]),
                step_id=None if row["step_id"] is None else str(row["step_id"]),
                attempt_id=(
                    None if row["attempt_id"] is None else str(row["attempt_id"])
                ),
                metadata=dict(row["event_metadata_json"]),
                payload_ref=(
                    None if row["payload_ref"] is None else str(row["payload_ref"])
                ),
                payload_digest=(
                    None
                    if row["payload_digest"] is None
                    else str(row["payload_digest"])
                ),
                authority_digest=str(row["authority_digest"]),
            )
            for row in rows
        )


__all__ = [
    "AgentSessionProjectionError",
    "AgentSessionSnapshot",
    "AgentTaskSnapshot",
    "PostgresAgentSessionReadAdapter",
    "SessionStatus",
    "TaskStatus",
    "fold_agent_session",
]
