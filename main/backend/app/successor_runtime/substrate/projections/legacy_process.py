"""Offline join projection over typed legacy process observations.

The projector is deliberately read-only and pure: it joins captured
``LegacySourceObservation`` values into disposable task views.  It cannot
write to AgentSession/Process rows and never manufactures a terminal fact,
so Celery/Redis/DB state can never authorize completion, cancellation,
retry, or NOT_STARTED.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.successor_runtime.capabilities.line_event_readback_port import (
    LineEventReadbackPort,
    LineEventReadbackRecord,
)
from app.successor_runtime.runtime.assignments import (
    Digest,
    FrozenContract,
    canonical_digest,
)
from app.successor_runtime.runtime.observations import (
    LegacySourceObservation,
    ObservationClass,
    ObservationFreshness,
)


class ProcessProjectionError(ValueError):
    """Legacy process observations cannot form a trustworthy projection."""


class SourceBindingMismatch(ProcessProjectionError):
    """One task identity binds multiple run/step/attempt identities."""


class LineEventProjectionError(ProcessProjectionError):
    """Line-event readback records cannot form a trustworthy projection."""


_ACTIVE_STATES = frozenset(
    {
        "active",
        "running",
        "started",
        "processing",
        "retry",
        "in_progress",
        "debug",
        "info",
        "warning",
        "error",
        "critical",
    }
)
_PENDING_STATES = frozenset(
    {"pending", "queued", "reserved", "scheduled", "blocked", "waiting"}
)
_COMPLETED_STATES = frozenset(
    {"completed", "finished", "success", "successful", "done", "ok"}
)
_FAILED_STATES = frozenset({"failed", "failure", "error", "dead", "revoked"})
_CANCELED_STATES = frozenset({"cancelled", "canceled", "expired"})


def normalize_observed_status(value: str | None) -> str:
    """Normalize one observed source state without claiming authority."""

    normalized = str(value or "").strip().lower()
    if not normalized:
        return "UNKNOWN"
    if normalized in _ACTIVE_STATES:
        return "ACTIVE"
    if normalized in _PENDING_STATES:
        return "PENDING"
    if normalized in _COMPLETED_STATES:
        return "COMPLETED"
    if normalized in _FAILED_STATES:
        return "FAILED"
    if normalized in _CANCELED_STATES:
        return "CANCELED"
    return "UNKNOWN"


class LegacyProcessTaskProjection(FrozenContract):
    schema_version: Literal["mrw.runtime.legacy-process-task.v1"] = (
        "mrw.runtime.legacy-process-task.v1"
    )
    task_id: str = Field(min_length=1)
    observation_class: ObservationClass
    status: str
    source_identities: tuple[str, ...] = ()
    linked_run_id: str | None = None
    linked_step_id: str | None = None
    linked_attempt_id: Digest | None = None
    terminal_authority_claim: None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_task(self) -> LegacyProcessTaskProjection:
        if tuple(sorted(self.source_identities)) != self.source_identities:
            raise ValueError("process task source identities are not ordered")
        if (
            self.observation_class is ObservationClass.OBSERVED
            and self.status == "UNKNOWN"
        ):
            raise ValueError("OBSERVED process task requires a known display status")
        if (
            self.observation_class
            in {ObservationClass.CONTRADICTORY, ObservationClass.UNBOUND}
            and self.reason is None
        ):
            raise ValueError("CONTRADICTORY/UNBOUND process task requires a reason")
        if self.terminal_authority_claim is not None:
            raise ValueError("process task projection never claims terminal authority")
        return self


class LegacyProcessObservationProjection(FrozenContract):
    schema_version: Literal["mrw.runtime.legacy-process-projection.v1"] = (
        "mrw.runtime.legacy-process-projection.v1"
    )
    captured_at: datetime
    tasks: tuple[LegacyProcessTaskProjection, ...] = ()
    view_digest: Digest

    @model_validator(mode="after")
    def validate_view(self) -> LegacyProcessObservationProjection:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("process projection captured_at must be timezone-aware")
        if tuple(sorted(self.tasks, key=lambda item: item.task_id)) != self.tasks:
            raise ValueError("process projection tasks are not canonically ordered")
        expected = canonical_digest(self, exclude_fields={"view_digest"})
        if self.view_digest != expected:
            raise ValueError("process projection view_digest mismatch")
        return self


def join_process_observations(
    observations: Iterable[LegacySourceObservation],
    *,
    captured_at: datetime,
) -> LegacyProcessObservationProjection:
    """Join captured observations by source identity into one read model."""

    grouped: dict[str, tuple[LegacySourceObservation, ...]] = {}
    for observation in observations:
        if not isinstance(observation, LegacySourceObservation):
            raise ProcessProjectionError("join requires typed legacy observations")
        grouped.setdefault(observation.source_identity, ())  # type: ignore[assignment]
        grouped[observation.source_identity] = grouped[observation.source_identity] + (
            observation,
        )
    if not grouped:
        raise ProcessProjectionError("join requires at least one observation")
    tasks = tuple(
        _join_task(task_id=task_id, observations=items)
        for task_id, items in sorted(grouped.items())
    )
    provisional = LegacyProcessObservationProjection.model_construct(
        captured_at=captured_at,
        tasks=tasks,
        view_digest="0" * 64,
    )
    values = provisional.model_dump(mode="python")
    values.pop("view_digest")
    return LegacyProcessObservationProjection(
        **values,
        view_digest=canonical_digest(
            provisional,
            exclude_fields={"view_digest"},
        ),
    )


def _join_task(
    *,
    task_id: str,
    observations: tuple[LegacySourceObservation, ...],
) -> LegacyProcessTaskProjection:
    contradictory = tuple(
        item
        for item in observations
        if item.observation_class is ObservationClass.CONTRADICTORY
    )
    observed = tuple(
        item
        for item in observations
        if item.observation_class is ObservationClass.OBSERVED
    )
    fresh_observed = tuple(
        item for item in observed if item.freshness is ObservationFreshness.FRESH
    )
    linked_run_ids = _distinct_linked(
        (item.linked_run_id for item in observations), label="run"
    )
    linked_step_ids = _distinct_linked(
        (item.linked_step_id for item in observations), label="step"
    )
    linked_attempt_ids = _distinct_linked(
        (item.linked_attempt_id for item in observations), label="attempt"
    )
    source_identities = tuple(sorted({item.source_locator for item in observations}))
    common = {
        "task_id": task_id,
        "source_identities": source_identities,
        "linked_run_id": linked_run_ids[0] if linked_run_ids else None,
        "linked_step_id": linked_step_ids[0] if linked_step_ids else None,
        "linked_attempt_id": linked_attempt_ids[0] if linked_attempt_ids else None,
    }
    if contradictory:
        return LegacyProcessTaskProjection(
            **common,
            observation_class=ObservationClass.CONTRADICTORY,
            status="UNKNOWN",
            reason=contradictory[0].reason or "CONTRADICTORY_SOURCES",
        )
    if not observed:
        unbound = tuple(
            item
            for item in observations
            if item.observation_class is ObservationClass.UNBOUND
        )
        if unbound and all(
            item.observation_class is ObservationClass.UNBOUND for item in observations
        ):
            return LegacyProcessTaskProjection(
                **common,
                observation_class=ObservationClass.UNBOUND,
                status="UNKNOWN",
                reason="NO_BOUND_RUNTIME_LINK",
            )
        return LegacyProcessTaskProjection(
            **common,
            observation_class=ObservationClass.UNAVAILABLE,
            status="UNKNOWN",
            reason="ALL_SOURCES_UNAVAILABLE",
        )
    if not fresh_observed:
        return LegacyProcessTaskProjection(
            **common,
            observation_class=ObservationClass.STALE,
            status=normalize_observed_status(observed[-1].observed_state),
            reason="NO_FRESH_SOURCE",
        )
    statuses = {
        normalize_observed_status(item.observed_state) for item in fresh_observed
    }
    if len(statuses) > 1:
        return LegacyProcessTaskProjection(
            **common,
            observation_class=ObservationClass.CONTRADICTORY,
            status="UNKNOWN",
            reason="CONTRADICTORY_DISPLAY_STATES",
        )
    return LegacyProcessTaskProjection(
        **common,
        observation_class=ObservationClass.OBSERVED,
        status=next(iter(statuses)),
    )


def _distinct_linked(
    values: Iterable[str | None],
    *,
    label: str,
) -> tuple[str, ...]:
    distinct = tuple(sorted({value for value in values if value is not None}))
    if len(distinct) > 1:
        raise SourceBindingMismatch(
            f"task binds multiple {label} identities: {', '.join(distinct)}"
        )
    return distinct


def project_line_event_readbacks(
    records: Iterable[LineEventReadbackRecord],
) -> tuple[dict[str, object], ...]:
    """Project typed line-event records through the successor readback port.

    The returned rows are read-only projections.  Each record is
    digest-verified and projected through ``LineEventReadbackPort.readback``
    and ``build_payload``; no terminal persistence is fabricated and no
    canonical/scheduler/executor authority is claimed.
    """

    typed = tuple(records)
    if not typed:
        raise LineEventProjectionError(
            "line-event readback projection requires at least one record"
        )
    for record in typed:
        if not isinstance(record, LineEventReadbackRecord):
            raise LineEventProjectionError(
                "line-event projection requires typed readback records"
            )
        record.verify_digest()
    ordered = tuple(sorted(typed, key=lambda record: record.line_key))
    if len({record.line_key for record in ordered}) != len(ordered):
        raise LineEventProjectionError(
            "line-event projection cannot carry duplicate line keys"
        )
    rows: list[dict[str, object]] = []
    for record in ordered:
        readback = LineEventReadbackPort.readback(record)
        payload = LineEventReadbackPort.build_payload(record)
        rows.append(
            {
                "line_key": record.line_key,
                "record_digest": record.digest,
                "persistence_decidable": readback.persistence_decidable,
                "persistence_observed": readback.persistence_observed,
                "readback_reason": readback.reason,
                "payload": payload,
            }
        )
    return tuple(rows)


__all__ = [
    "LegacyProcessObservationProjection",
    "LegacyProcessTaskProjection",
    "LineEventProjectionError",
    "ProcessProjectionError",
    "SourceBindingMismatch",
    "join_process_observations",
    "normalize_observed_status",
    "project_line_event_readbacks",
]
