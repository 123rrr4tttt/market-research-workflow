"""Pure task-process observation identities, models, and read-only projection.

This runtime authority contains no database, broker, filesystem, scheduler, or
provider adapter.  Outer projection modules reuse these exact objects and add
only their facility-specific readback functions.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final, Literal, TypeVar

from functorial_kit import Failure
from pydantic import Field, TypeAdapter, model_validator

from .assignments import Digest, FrozenContract, canonical_digest
from .failure_policy import raise_runtime_failure, runtime_failure
from .observations import (
    LegacySourceObservation,
    ObservationClass,
    ObservationFreshness,
)

_T = TypeVar("_T")


class ProcessProjectionError(ValueError):
    """Process observations cannot form a trustworthy projection."""


class SourceBindingMismatch(ProcessProjectionError):
    """One task identity binds multiple run/step/attempt identities."""


def _process_observation_failure(
    message: object,
    *,
    site: str,
    exception_type: type[Exception] = ProcessProjectionError,
) -> Failure:
    """Return one closed runtime failure for the pure observation family."""

    return runtime_failure(
        "PROCESS_OBSERVATION_INVALID",
        message,
        exception_type,
        site=site,
        context={
            "owner": "successor_runtime.runtime.process_observation",
            "operation": site,
        },
    )


def _historical_process_observation_failure(
    message: object,
    *,
    site: str,
) -> Failure:
    """Retain the original failure identity for explicit historical v1 input."""

    return runtime_failure(
        "LEGACY_OBSERVATION_INVALID",
        message,
        ProcessProjectionError,
        site=site,
        context={
            "owner": "successor_runtime.runtime.process_observation",
            "operation": site,
            "input_schema": HISTORICAL_PROCESS_OBSERVATION_PROJECTION_SCHEMA_V1,
        },
    )


def _try_process_observation(
    call: Callable[[], _T],
    *,
    site: str,
) -> _T | Failure:
    """Close validation-library exceptions into the observation failure family."""

    try:
        return call()
    except (TypeError, ValueError, OverflowError, KeyError, AttributeError) as exc:
        return _process_observation_failure(str(exc), site=site)


def _raise_process_observation_failure(
    failure: Failure,
    exception_type: type[Exception],
) -> None:
    """Retain an established exception ABI over a typed pure result."""

    # kit:boundary owner=successor.runtime.process_observation.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=successor.runtime.failure witness=test:test_process_observation_public_exception_abi_lifts_typed_failures  # noqa: E501
    raise_runtime_failure(failure, exception_type)


PROCESS_OBSERVATION_PROJECTOR_ID: Final = "mrw.process-observation.projector.v1"
PROCESS_OBSERVATION_PROJECTOR_VERSION: Final = "1.0.0"
PROCESS_OBSERVATION_PROJECTION_SCHEMA_V1: Final = "mrw.process-observation.v1"
PROCESS_OBSERVATION_TASK_SCHEMA_V1: Final = "mrw.process-observation.task.v1"
PROCESS_OBSERVATION_PROJECTOR_REF: Final = (
    "app.successor_runtime.runtime.process_observation:try_join_process_observations"
)
LINE_EVENT_READBACK_PROJECTOR_REF: Final = (
    "app.successor_runtime.substrate.projections.legacy_process:"
    "project_line_event_readbacks"
)
HISTORICAL_PROCESS_OBSERVATION_PROJECTOR_ID: Final = (
    "successor.legacy_process_observation_join.v1"
)
HISTORICAL_PROCESS_OBSERVATION_PROJECTION_SCHEMA_V1: Final = (
    "mrw.runtime.legacy-process-projection.v1"
)


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


class ProcessTaskProjection(FrozenContract):
    schema_version: Literal[PROCESS_OBSERVATION_TASK_SCHEMA_V1] = (
        PROCESS_OBSERVATION_TASK_SCHEMA_V1
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
    def validate_task(self) -> ProcessTaskProjection:
        if tuple(sorted(self.source_identities)) != self.source_identities:
            _raise_process_observation_failure(
                _process_observation_failure(
                    "process task source identities are not ordered",
                    site="successor_runtime.runtime.process_observation.task.source_identities",
                    exception_type=ValueError,
                ),
                ValueError,
            )
        if (
            self.observation_class is ObservationClass.OBSERVED
            and self.status == "UNKNOWN"
        ):
            _raise_process_observation_failure(
                _process_observation_failure(
                    "OBSERVED process task requires a known display status",
                    site="successor_runtime.runtime.process_observation.task.status",
                    exception_type=ValueError,
                ),
                ValueError,
            )
        if (
            self.observation_class
            in {ObservationClass.CONTRADICTORY, ObservationClass.UNBOUND}
            and self.reason is None
        ):
            _raise_process_observation_failure(
                _process_observation_failure(
                    "CONTRADICTORY/UNBOUND process task requires a reason",
                    site="successor_runtime.runtime.process_observation.task.reason",
                    exception_type=ValueError,
                ),
                ValueError,
            )
        if self.terminal_authority_claim is not None:
            _raise_process_observation_failure(
                _process_observation_failure(
                    "process task projection never claims terminal authority",
                    site="successor_runtime.runtime.process_observation.task.terminal_authority",
                    exception_type=ValueError,
                ),
                ValueError,
            )
        return self


class ProcessObservationProjection(FrozenContract):
    schema_version: Literal[PROCESS_OBSERVATION_PROJECTION_SCHEMA_V1] = (
        PROCESS_OBSERVATION_PROJECTION_SCHEMA_V1
    )
    captured_at: datetime
    tasks: tuple[ProcessTaskProjection, ...] = ()
    view_digest: Digest

    @model_validator(mode="after")
    def validate_view(self) -> ProcessObservationProjection:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            _raise_process_observation_failure(
                _process_observation_failure(
                    "process projection captured_at must be timezone-aware",
                    site="successor_runtime.runtime.process_observation.view.captured_at",
                    exception_type=ValueError,
                ),
                ValueError,
            )
        if tuple(sorted(self.tasks, key=lambda item: item.task_id)) != self.tasks:
            _raise_process_observation_failure(
                _process_observation_failure(
                    "process projection tasks are not canonically ordered",
                    site="successor_runtime.runtime.process_observation.view.tasks",
                    exception_type=ValueError,
                ),
                ValueError,
            )
        expected = canonical_digest(self, exclude_fields={"view_digest"})
        if self.view_digest != expected:
            _raise_process_observation_failure(
                _process_observation_failure(
                    "process projection view_digest mismatch",
                    site="successor_runtime.runtime.process_observation.view.digest",
                    exception_type=ValueError,
                ),
                ValueError,
            )
        return self


def try_process_task_projection(**content: Any) -> ProcessTaskProjection | Failure:
    """Build one task projection without throwing domain validation failures."""

    return _try_process_observation(
        lambda: ProcessTaskProjection(**content),
        site="successor_runtime.runtime.process_observation.task",
    )


def try_process_observation_projection(
    **content: Any,
) -> ProcessObservationProjection | Failure:
    """Build one process projection without throwing domain validation failures."""

    return _try_process_observation(
        lambda: ProcessObservationProjection(**content),
        site="successor_runtime.runtime.process_observation.view",
    )


def join_process_observations(
    observations: Iterable[LegacySourceObservation],
    *,
    captured_at: datetime,
) -> ProcessObservationProjection:
    """Compatibility exception ABI over :func:`try_join_process_observations`."""

    result = try_join_process_observations(observations, captured_at=captured_at)
    if isinstance(result, Failure):
        _raise_process_observation_failure(result, ProcessProjectionError)
    return result


def try_join_process_observations(
    observations: Iterable[LegacySourceObservation],
    *,
    captured_at: datetime,
) -> ProcessObservationProjection | Failure:
    """Join captured observations into a read model or a typed failure."""

    return _try_process_observation(
        lambda: _join_process_observations(observations, captured_at=captured_at),
        site="successor_runtime.runtime.process_observation.join",
    )


def _join_process_observations(
    observations: Iterable[LegacySourceObservation],
    *,
    captured_at: datetime,
) -> ProcessObservationProjection | Failure:
    """Pure join implementation; expected invalidity remains in the codomain."""

    grouped: dict[str, tuple[LegacySourceObservation, ...]] = {}
    for observation in observations:
        if not isinstance(observation, LegacySourceObservation):
            return _process_observation_failure(
                "join requires typed legacy observations",
                site="successor_runtime.runtime.process_observation.join.input",
            )
        grouped.setdefault(observation.source_identity, ())
        grouped[observation.source_identity] = grouped[observation.source_identity] + (
            observation,
        )
    if not grouped:
        return _process_observation_failure(
            "join requires at least one observation",
            site="successor_runtime.runtime.process_observation.join.empty",
        )
    joined_tasks: list[ProcessTaskProjection] = []
    for task_id, items in sorted(grouped.items()):
        task = _join_task(task_id=task_id, observations=items)
        if isinstance(task, Failure):
            return task
        joined_tasks.append(task)
    tasks = tuple(joined_tasks)
    provisional = ProcessObservationProjection.model_construct(
        captured_at=captured_at,
        tasks=tasks,
        view_digest="0" * 64,
    )
    values = provisional.model_dump(mode="python")
    values.pop("view_digest")
    return try_process_observation_projection(
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
) -> ProcessTaskProjection | Failure:
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
    if isinstance(linked_run_ids, Failure):
        return linked_run_ids
    linked_step_ids = _distinct_linked(
        (item.linked_step_id for item in observations), label="step"
    )
    if isinstance(linked_step_ids, Failure):
        return linked_step_ids
    linked_attempt_ids = _distinct_linked(
        (item.linked_attempt_id for item in observations), label="attempt"
    )
    if isinstance(linked_attempt_ids, Failure):
        return linked_attempt_ids
    source_identities = tuple(sorted({item.source_locator for item in observations}))
    common = {
        "task_id": task_id,
        "source_identities": source_identities,
        "linked_run_id": linked_run_ids[0] if linked_run_ids else None,
        "linked_step_id": linked_step_ids[0] if linked_step_ids else None,
        "linked_attempt_id": linked_attempt_ids[0] if linked_attempt_ids else None,
    }
    if contradictory:
        return try_process_task_projection(
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
            return try_process_task_projection(
                **common,
                observation_class=ObservationClass.UNBOUND,
                status="UNKNOWN",
                reason="NO_BOUND_RUNTIME_LINK",
            )
        return try_process_task_projection(
            **common,
            observation_class=ObservationClass.UNAVAILABLE,
            status="UNKNOWN",
            reason="ALL_SOURCES_UNAVAILABLE",
        )
    if not fresh_observed:
        return try_process_task_projection(
            **common,
            observation_class=ObservationClass.STALE,
            status=normalize_observed_status(observed[-1].observed_state),
            reason="NO_FRESH_SOURCE",
        )
    statuses = {
        normalize_observed_status(item.observed_state) for item in fresh_observed
    }
    if len(statuses) > 1:
        return try_process_task_projection(
            **common,
            observation_class=ObservationClass.CONTRADICTORY,
            status="UNKNOWN",
            reason="CONTRADICTORY_DISPLAY_STATES",
        )
    return try_process_task_projection(
        **common,
        observation_class=ObservationClass.OBSERVED,
        status=next(iter(statuses)),
    )


def _distinct_linked(
    values: Iterable[str | None],
    *,
    label: str,
) -> tuple[str, ...] | Failure:
    distinct = tuple(sorted({value for value in values if value is not None}))
    if len(distinct) > 1:
        return _process_observation_failure(
            f"task binds multiple {label} identities: {', '.join(distinct)}",
            site=f"successor_runtime.runtime.process_observation.join.{label}_binding",
            exception_type=SourceBindingMismatch,
        )
    return distinct


@dataclass(frozen=True, slots=True)
class HistoricalProcessObservationProjectionRead:
    """Explicit historical v1 process-projection decode; no rehashing."""

    schema_version: Literal[HISTORICAL_PROCESS_OBSERVATION_PROJECTION_SCHEMA_V1]
    captured_at: datetime
    tasks: tuple[Mapping[str, object], ...]
    view_digest: str


def read_historical_process_observation_projection(
    payload: Mapping[str, object],
) -> HistoricalProcessObservationProjectionRead:
    """Compatibility exception ABI over the typed historical reader."""

    result = try_read_historical_process_observation_projection(payload)
    if isinstance(result, Failure):
        _raise_process_observation_failure(result, ProcessProjectionError)
    return result


def try_read_historical_process_observation_projection(
    payload: Mapping[str, object],
) -> HistoricalProcessObservationProjectionRead | Failure:
    """Decode original historical bytes without rewriting or rehashing them."""

    if payload.get("schema_version") != HISTORICAL_PROCESS_OBSERVATION_PROJECTION_SCHEMA_V1:
        return _historical_process_observation_failure(
            "historical process projection schema mismatch",
            site="successor_runtime.runtime.process_observation.history.schema",
        )
    captured_at_value = payload.get("captured_at")
    try:
        captured_at = TypeAdapter(datetime).validate_python(captured_at_value)
    except (TypeError, ValueError):
        return _historical_process_observation_failure(
            "historical process projection captured_at is invalid",
            site="successor_runtime.runtime.process_observation.history.captured_at",
        )
    raw_tasks = payload.get("tasks", ())
    if not isinstance(raw_tasks, list) or any(
        not isinstance(task, Mapping) for task in raw_tasks
    ):
        return _historical_process_observation_failure(
            "historical process projection tasks are invalid",
            site="successor_runtime.runtime.process_observation.history.tasks",
        )
    digest = payload.get("view_digest")
    if not isinstance(digest, str) or len(digest) != 64:
        return _historical_process_observation_failure(
            "historical process projection view digest is invalid",
            site="successor_runtime.runtime.process_observation.history.digest",
        )
    return HistoricalProcessObservationProjectionRead(
        schema_version=HISTORICAL_PROCESS_OBSERVATION_PROJECTION_SCHEMA_V1,
        captured_at=captured_at,
        tasks=tuple(raw_tasks),
        view_digest=digest,
    )


__all__ = [
    "HISTORICAL_PROCESS_OBSERVATION_PROJECTOR_ID",
    "HISTORICAL_PROCESS_OBSERVATION_PROJECTION_SCHEMA_V1",
    "HistoricalProcessObservationProjectionRead",
    "LINE_EVENT_READBACK_PROJECTOR_REF",
    "PROCESS_OBSERVATION_PROJECTION_SCHEMA_V1",
    "PROCESS_OBSERVATION_PROJECTOR_ID",
    "PROCESS_OBSERVATION_PROJECTOR_REF",
    "PROCESS_OBSERVATION_PROJECTOR_VERSION",
    "PROCESS_OBSERVATION_TASK_SCHEMA_V1",
    "ProcessObservationProjection",
    "ProcessProjectionError",
    "ProcessTaskProjection",
    "SourceBindingMismatch",
    "join_process_observations",
    "normalize_observed_status",
    "read_historical_process_observation_projection",
    "try_join_process_observations",
    "try_process_observation_projection",
    "try_process_task_projection",
    "try_read_historical_process_observation_projection",
]
