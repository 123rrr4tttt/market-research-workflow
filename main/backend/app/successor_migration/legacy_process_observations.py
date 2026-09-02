"""Offline capture of legacy Celery/DB/process observation shapes.

This adapter parses captured response fixtures (Celery inspect task dicts,
``AsyncResult`` snapshots, ``EtlJobRun`` rows, and worker log lines) into
typed ``LegacySourceObservation`` values.  It performs no Celery, Redis,
filesystem, or process call: the inputs are already captured dicts/lines.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.successor_runtime.runtime.observations import (
    LegacySourceObservation,
    ObservationClass,
    ObservationFreshness,
    ObservationSourceKind,
)


class LegacyProcessObservationError(RuntimeError):
    """Base class for fail-closed legacy process observation capture."""


class MissingProcessSourceIdentity(LegacyProcessObservationError):
    """A captured source cannot be bound to a task/row identity."""


PROCESS_LOG_LEVELS = frozenset({"debug", "info", "warning", "error", "critical"})


def normalize_process_log_level(value: Any) -> str:
    """Normalize one worker log level into the bounded typed vocabulary."""

    normalized = str(value or "").strip().lower() or "info"
    if normalized not in PROCESS_LOG_LEVELS:
        raise LegacyProcessObservationError(
            f"unsupported process log level: {normalized!r}"
        )
    return normalized


def _bound_observation_class(
    *,
    linked_run_id: str | None,
    linked_step_id: str | None,
    linked_attempt_id: str | None,
) -> tuple[ObservationClass, str | None]:
    if any(
        value is not None
        for value in (linked_run_id, linked_step_id, linked_attempt_id)
    ):
        return ObservationClass.OBSERVED, None
    return ObservationClass.UNBOUND, "NO_BOUND_RUNTIME_LINK"


def capture_celery_inspect_task(
    task: Mapping[str, Any],
    *,
    worker: str,
    observed_at: datetime,
    freshness: ObservationFreshness = ObservationFreshness.FRESH,
    linked_run_id: str | None = None,
    linked_step_id: str | None = None,
    linked_attempt_id: str | None = None,
) -> LegacySourceObservation:
    """Capture one Celery inspect task dict (active/scheduled/reserved)."""

    task_id = str(task.get("id") or task.get("request", {}).get("id") or "").strip()
    if not task_id:
        raise MissingProcessSourceIdentity("Celery inspect task dict lacks task id")
    status = (
        str(
            task.get("status")
            or ("pending" if task.get("request") is not None else "active")
        )
        .strip()
        .lower()
    )
    observation_class, reason = _bound_observation_class(
        linked_run_id=linked_run_id,
        linked_step_id=linked_step_id,
        linked_attempt_id=linked_attempt_id,
    )
    return LegacySourceObservation.from_content(
        source_kind=ObservationSourceKind.CELERY_INSPECT,
        source_locator=f"celery-inspect://{worker}/{task_id}",
        source_identity=task_id,
        observed_state=status or "unknown",
        observation_class=observation_class,
        observed_at=observed_at,
        freshness=freshness,
        linked_run_id=linked_run_id,
        linked_step_id=linked_step_id,
        linked_attempt_id=linked_attempt_id,
        raw_evidence_ref=(None if not task else f"fixture:celery-inspect:{task_id}"),
        reason=reason,
    )


def capture_celery_async_result(
    snapshot: Mapping[str, Any],
    *,
    observed_at: datetime,
    freshness: ObservationFreshness = ObservationFreshness.FRESH,
    linked_run_id: str | None = None,
    linked_step_id: str | None = None,
    linked_attempt_id: str | None = None,
) -> LegacySourceObservation:
    """Capture one ``_task_snapshot``-shaped AsyncResult observation."""

    task_id = str(snapshot.get("task_id") or "").strip()
    if not task_id:
        raise MissingProcessSourceIdentity("AsyncResult snapshot lacks task_id")
    status = str(snapshot.get("status") or "").strip().lower()
    ready = snapshot.get("ready")
    successful = snapshot.get("successful")
    contradictory = ready is True and successful is None
    if contradictory:
        return LegacySourceObservation.from_content(
            source_kind=ObservationSourceKind.CELERY_ASYNC_RESULT,
            source_locator=f"celery-async-result://{task_id}",
            source_identity=task_id,
            observed_state="unknown",
            observation_class=ObservationClass.CONTRADICTORY,
            observed_at=observed_at,
            freshness=freshness,
            linked_run_id=linked_run_id,
            linked_step_id=linked_step_id,
            linked_attempt_id=linked_attempt_id,
            raw_evidence_ref=f"fixture:async-result:{task_id}",
            reason="ASYNC_RESULT_READY_WITHOUT_SUCCESS_FLAG",
        )
    if not status:
        return LegacySourceObservation.from_content(
            source_kind=ObservationSourceKind.CELERY_ASYNC_RESULT,
            source_locator=f"celery-async-result://{task_id}",
            source_identity=task_id,
            observed_state="unknown",
            observation_class=ObservationClass.UNAVAILABLE,
            observed_at=observed_at,
            freshness=freshness,
            linked_run_id=linked_run_id,
            linked_step_id=linked_step_id,
            linked_attempt_id=linked_attempt_id,
            raw_evidence_ref=f"fixture:async-result:{task_id}",
            reason="ASYNC_RESULT_STATUS_ABSENT",
        )
    observation_class, reason = _bound_observation_class(
        linked_run_id=linked_run_id,
        linked_step_id=linked_step_id,
        linked_attempt_id=linked_attempt_id,
    )
    return LegacySourceObservation.from_content(
        source_kind=ObservationSourceKind.CELERY_ASYNC_RESULT,
        source_locator=f"celery-async-result://{task_id}",
        source_identity=task_id,
        observed_state=status,
        observation_class=observation_class,
        observed_at=observed_at,
        freshness=freshness,
        linked_run_id=linked_run_id,
        linked_step_id=linked_step_id,
        linked_attempt_id=linked_attempt_id,
        raw_evidence_ref=f"fixture:async-result:{task_id}",
        reason=reason,
    )


def capture_etl_job_run(
    row: Mapping[str, Any],
    *,
    observed_at: datetime,
    freshness: ObservationFreshness = ObservationFreshness.FRESH,
    linked_run_id: str | None = None,
    linked_step_id: str | None = None,
    linked_attempt_id: str | None = None,
) -> LegacySourceObservation:
    """Capture one ``EtlJobRun`` row observation (offline dict shape)."""

    job_id = row.get("id")
    if job_id is None:
        raise MissingProcessSourceIdentity("EtlJobRun row lacks id")
    identity = f"db-job-{job_id}"
    status = str(row.get("status") or "").strip().lower()
    if not status:
        return LegacySourceObservation.from_content(
            source_kind=ObservationSourceKind.ETL_JOB_RUN,
            source_locator=f"etl-job-run://{identity}",
            source_identity=identity,
            observed_state="unknown",
            observation_class=ObservationClass.UNAVAILABLE,
            observed_at=observed_at,
            freshness=freshness,
            linked_run_id=linked_run_id,
            linked_step_id=linked_step_id,
            linked_attempt_id=linked_attempt_id,
            raw_evidence_ref=f"fixture:etl-job-run:{identity}",
            reason="ETL_JOB_RUN_STATUS_ABSENT",
        )
    observation_class, reason = _bound_observation_class(
        linked_run_id=linked_run_id,
        linked_step_id=linked_step_id,
        linked_attempt_id=linked_attempt_id,
    )
    return LegacySourceObservation.from_content(
        source_kind=ObservationSourceKind.ETL_JOB_RUN,
        source_locator=f"etl-job-run://{identity}",
        source_identity=identity,
        observed_state=status,
        observation_class=observation_class,
        observed_at=observed_at,
        freshness=freshness,
        linked_run_id=linked_run_id,
        linked_step_id=linked_step_id,
        linked_attempt_id=linked_attempt_id,
        raw_evidence_ref=f"fixture:etl-job-run:{identity}",
        reason=reason,
    )


def capture_process_log(
    line: Mapping[str, Any],
    *,
    observed_at: datetime,
    freshness: ObservationFreshness = ObservationFreshness.FRESH,
    linked_run_id: str | None = None,
    linked_step_id: str | None = None,
    linked_attempt_id: str | None = None,
) -> LegacySourceObservation:
    """Capture one diagnostic worker log observation."""

    task_id = str(line.get("task_id") or "").strip()
    path = str(line.get("path") or "process-log").strip()
    line_no = str(line.get("line_no") or "").strip()
    level = normalize_process_log_level(line.get("level"))
    if not task_id:
        raise MissingProcessSourceIdentity("process log observation lacks task_id")
    observation_class, reason = _bound_observation_class(
        linked_run_id=linked_run_id,
        linked_step_id=linked_step_id,
        linked_attempt_id=linked_attempt_id,
    )
    return LegacySourceObservation.from_content(
        source_kind=ObservationSourceKind.PROCESS_LOG,
        source_locator=f"process-log://{path}:{line_no or '0'}",
        source_identity=task_id,
        observed_state=level,
        observation_class=observation_class,
        observed_at=observed_at,
        freshness=freshness,
        linked_run_id=linked_run_id,
        linked_step_id=linked_step_id,
        linked_attempt_id=linked_attempt_id,
        raw_evidence_ref=(f"fixture:process-log:{path}:{line_no}" if line_no else None),
        reason=reason,
    )


__all__ = [
    "PROCESS_LOG_LEVELS",
    "LegacyProcessObservationError",
    "MissingProcessSourceIdentity",
    "capture_celery_async_result",
    "capture_celery_inspect_task",
    "capture_etl_job_run",
    "capture_process_log",
    "normalize_process_log_level",
]
