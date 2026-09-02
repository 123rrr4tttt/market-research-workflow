"""Read-only replay of legacy AgentSession/AgentTask row observations.

This sibling adapter is the only place that knows the legacy session/task
dict shapes.  It never writes to legacy rows and never claims successor
authority: the captured observations are disposable fixtures for rollback
compatibility, while the runtime journal remains canonical.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from app.successor_runtime.runtime.assignments import (
    Digest,
    FrozenContract,
    canonical_digest,
)
from app.successor_runtime.runtime.observations import ObservationClass


class LegacyAgentSessionError(RuntimeError):
    """Base class for fail-closed legacy session/task observations."""


class UnsupportedLegacySessionStatus(LegacyAgentSessionError):
    """A legacy status is not part of the frozen compatibility vocabulary."""


class IncompleteLegacySessionPayload(LegacyAgentSessionError):
    """A legacy row cannot form a complete typed observation."""


SESSION_STATUSES = frozenset(
    {"pending", "active", "blocked", "completed", "failed", "canceled", "unknown"}
)
TASK_STATUSES = frozenset(
    {
        "pending",
        "claimed",
        "in_progress",
        "blocked",
        "completed",
        "failed",
        "canceled",
        "expired",
        "unknown",
    }
)


class LegacyAgentSessionObservation(FrozenContract):
    schema_version: Literal["mrw.migration.legacy-agent-session.v1"] = (
        "mrw.migration.legacy-agent-session.v1"
    )
    session_id: str = Field(min_length=1)
    status: str
    current_phase: str | None = None
    task_count: int = Field(ge=0)
    owner_ref: str | None = None
    observed_at: datetime
    observation_class: ObservationClass
    source_ref: str = Field(min_length=1)
    source_digest: Digest
    terminal_authority_claim: None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_observation(self) -> LegacyAgentSessionObservation:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("legacy session observed_at must be timezone-aware")
        if self.status not in SESSION_STATUSES:
            raise UnsupportedLegacySessionStatus(
                f"unsupported legacy session status: {self.status!r}"
            )
        if (
            self.observation_class is ObservationClass.OBSERVED
            and self.status == "unknown"
        ):
            raise ValueError("OBSERVED legacy session cannot have unknown status")
        if self.terminal_authority_claim is not None:
            raise ValueError("legacy session observation never claims authority")
        expected = canonical_digest(self, exclude_fields={"source_digest"})
        if self.source_digest != expected:
            raise ValueError("legacy session source_digest mismatch")
        return self

    @classmethod
    def from_content(cls, **content: object) -> LegacyAgentSessionObservation:
        if "source_digest" in content:
            raise ValueError("source_digest is derived, not caller supplied")
        provisional = cls.model_construct(**content, source_digest="0" * 64)
        return cls(
            **content,
            source_digest=canonical_digest(
                provisional,
                exclude_fields={"source_digest"},
            ),
        )


class LegacyAgentTaskObservation(FrozenContract):
    schema_version: Literal["mrw.migration.legacy-agent-task.v1"] = (
        "mrw.migration.legacy-agent-task.v1"
    )
    session_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    status: str
    phase: str | None = None
    blocked_by: tuple[str, ...] = ()
    write_set: tuple[str, ...] = ()
    owner_ref: str | None = None
    lease_until: datetime | None = None
    result_payload_ref: str | None = None
    observed_at: datetime
    observation_class: ObservationClass
    source_ref: str = Field(min_length=1)
    source_digest: Digest
    terminal_authority_claim: None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_observation(self) -> LegacyAgentTaskObservation:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("legacy task observed_at must be timezone-aware")
        if self.lease_until is not None and (
            self.lease_until.tzinfo is None or self.lease_until.utcoffset() is None
        ):
            raise ValueError("legacy task lease_until must be timezone-aware")
        if self.status not in TASK_STATUSES:
            raise UnsupportedLegacySessionStatus(
                f"unsupported legacy task status: {self.status!r}"
            )
        if tuple(sorted(self.blocked_by)) != self.blocked_by:
            raise ValueError("legacy task blocked_by is not canonically ordered")
        if tuple(sorted(self.write_set)) != self.write_set:
            raise ValueError("legacy task write_set is not canonically ordered")
        if (
            self.observation_class is ObservationClass.OBSERVED
            and self.status == "unknown"
        ):
            raise ValueError("OBSERVED legacy task cannot have unknown status")
        if self.terminal_authority_claim is not None:
            raise ValueError("legacy task observation never claims authority")
        expected = canonical_digest(self, exclude_fields={"source_digest"})
        if self.source_digest != expected:
            raise ValueError("legacy task source_digest mismatch")
        return self

    @classmethod
    def from_content(cls, **content: object) -> LegacyAgentTaskObservation:
        if "source_digest" in content:
            raise ValueError("source_digest is derived, not caller supplied")
        provisional = cls.model_construct(**content, source_digest="0" * 64)
        return cls(
            **content,
            source_digest=canonical_digest(
                provisional,
                exclude_fields={"source_digest"},
            ),
        )


class LegacyAgentSessionReadModel(FrozenContract):
    """Projection-only read model replaying one legacy session bundle."""

    schema_version: Literal["mrw.migration.legacy-agent-session-read-model.v1"] = (
        "mrw.migration.legacy-agent-session-read-model.v1"
    )
    session: LegacyAgentSessionObservation
    tasks: tuple[LegacyAgentTaskObservation, ...] = ()
    read_model_digest: Digest
    authority: Literal["PROJECTION_ONLY"] = "PROJECTION_ONLY"
    rollback_observation: str = (
        "read-only compat view; runtime journal remains the canonical run/step owner"
    )

    @model_validator(mode="after")
    def validate_read_model(self) -> LegacyAgentSessionReadModel:
        if tuple(sorted(self.tasks, key=lambda item: item.task_id)) != self.tasks:
            raise ValueError("legacy session tasks are not canonically ordered")
        if any(item.session_id != self.session.session_id for item in self.tasks):
            raise ValueError("legacy session read model contains a foreign task")
        expected = canonical_digest(self, exclude_fields={"read_model_digest"})
        if self.read_model_digest != expected:
            raise ValueError("legacy session read_model_digest mismatch")
        return self


def _required(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise IncompleteLegacySessionPayload(
            f"legacy session payload requires non-empty {key!r}"
        )
    return value.strip()


def _normalize_status(value: Any, *, allowed: frozenset[str]) -> str:
    status = str(value or "").strip().lower()
    if not status:
        return "unknown"
    if status not in allowed:
        raise UnsupportedLegacySessionStatus(f"unsupported legacy status: {status!r}")
    return status


def capture_legacy_session(
    payload: Mapping[str, Any],
    *,
    observed_at: datetime,
    source_ref: str,
) -> LegacyAgentSessionObservation:
    session_id = _required(payload, "session_id")
    status = _normalize_status(
        payload.get("status"),
        allowed=SESSION_STATUSES,
    )
    current_phase = payload.get("current_phase")
    if current_phase is not None and not isinstance(current_phase, str):
        raise IncompleteLegacySessionPayload("current_phase must be a string or null")
    task_count = payload.get("task_count", 0)
    if (
        not isinstance(task_count, int)
        or isinstance(task_count, bool)
        or task_count < 0
    ):
        raise IncompleteLegacySessionPayload(
            "task_count must be a non-negative integer"
        )
    observation_class = (
        ObservationClass.UNAVAILABLE
        if status == "unknown"
        else ObservationClass.OBSERVED
    )
    return LegacyAgentSessionObservation.from_content(
        session_id=session_id,
        status=status,
        current_phase=current_phase,
        task_count=task_count,
        owner_ref=payload.get("owner"),
        observed_at=observed_at,
        observation_class=observation_class,
        source_ref=source_ref,
        reason=None
        if observation_class is ObservationClass.OBSERVED
        else "STATUS_UNKNOWN",
    )


def capture_legacy_task(
    payload: Mapping[str, Any],
    *,
    observed_at: datetime,
    source_ref: str,
) -> LegacyAgentTaskObservation:
    session_id = _required(payload, "session_id")
    task_id = _required(payload, "task_id")
    status = _normalize_status(payload.get("status"), allowed=TASK_STATUSES)
    blocked_by = _ordered_unique(payload.get("blocked_by"))
    write_set = _ordered_unique(payload.get("write_set"))
    lease_until = payload.get("lease_until")
    if lease_until is not None and not isinstance(lease_until, datetime):
        raise IncompleteLegacySessionPayload("lease_until must be a datetime or null")
    observation_class = (
        ObservationClass.UNAVAILABLE
        if status == "unknown"
        else ObservationClass.OBSERVED
    )
    return LegacyAgentTaskObservation.from_content(
        session_id=session_id,
        task_id=task_id,
        status=status,
        phase=payload.get("phase"),
        blocked_by=blocked_by,
        write_set=write_set,
        owner_ref=payload.get("owner"),
        lease_until=lease_until,
        result_payload_ref=payload.get("result_payload_ref"),
        observed_at=observed_at,
        observation_class=observation_class,
        source_ref=source_ref,
        reason=None
        if observation_class is ObservationClass.OBSERVED
        else "STATUS_UNKNOWN",
    )


def project_legacy_session_read_model(
    session_payload: Mapping[str, Any],
    task_payloads: list[Mapping[str, Any]],
    *,
    observed_at: datetime,
    source_ref: str,
) -> LegacyAgentSessionReadModel:
    session = capture_legacy_session(
        session_payload,
        observed_at=observed_at,
        source_ref=source_ref,
    )
    tasks = tuple(
        capture_legacy_task(
            payload,
            observed_at=observed_at,
            source_ref=f"{source_ref}/tasks/{payload['task_id']}",
        )
        for payload in sorted(task_payloads, key=lambda item: str(item.get("task_id")))
    )
    provisional = LegacyAgentSessionReadModel.model_construct(
        session=session,
        tasks=tasks,
        read_model_digest="0" * 64,
    )
    values = provisional.model_dump(mode="python")
    values.pop("read_model_digest")
    return LegacyAgentSessionReadModel(
        **values,
        read_model_digest=canonical_digest(
            provisional,
            exclude_fields={"read_model_digest"},
        ),
    )


def _ordered_unique(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise IncompleteLegacySessionPayload(
            "blocked_by/write_set must be a list or null"
        )
    return tuple(sorted({str(item).strip() for item in value if str(item).strip()}))


__all__ = [
    "SESSION_STATUSES",
    "TASK_STATUSES",
    "IncompleteLegacySessionPayload",
    "LegacyAgentSessionError",
    "LegacyAgentSessionObservation",
    "LegacyAgentSessionReadModel",
    "LegacyAgentTaskObservation",
    "UnsupportedLegacySessionStatus",
    "capture_legacy_session",
    "capture_legacy_task",
    "project_legacy_session_read_model",
]
