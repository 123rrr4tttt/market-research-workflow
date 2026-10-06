"""Outer line-event projection plus compatibility exports for process views.

The pure process-observation authority lives in
``runtime.process_observation``.  This module adds the line-event readback
adapter, then re-exports the same runtime objects for historical import paths.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TypedDict, TypeGuard

from app.successor_runtime.capabilities.line_event_readback_port import (
    LineEventReadbackPayload,
    LineEventReadbackPort,
    LineEventReadbackRecord,
)
from app.successor_runtime.runtime.process_observation import (
    HISTORICAL_PROCESS_OBSERVATION_PROJECTION_SCHEMA_V1,
    HISTORICAL_PROCESS_OBSERVATION_PROJECTOR_ID,
    LINE_EVENT_READBACK_PROJECTOR_REF,
    PROCESS_OBSERVATION_PROJECTION_SCHEMA_V1,
    PROCESS_OBSERVATION_PROJECTOR_ID,
    PROCESS_OBSERVATION_PROJECTOR_REF,
    PROCESS_OBSERVATION_PROJECTOR_VERSION,
    PROCESS_OBSERVATION_TASK_SCHEMA_V1,
    HistoricalProcessObservationProjectionRead,
    ProcessObservationProjection,
    ProcessProjectionError,
    ProcessTaskProjection,
    SourceBindingMismatch,
    join_process_observations,
    normalize_observed_status,
    read_historical_process_observation_projection,
)


class LineEventProjectionError(ProcessProjectionError):
    """Line-event readback records cannot form a trustworthy projection."""


class LineEventProjectionRow(TypedDict):
    """One exact outer row built around the canonical readback payload."""

    line_key: str
    record_digest: str
    persistence_decidable: bool
    persistence_observed: bool
    readback_reason: str | None
    payload: LineEventReadbackPayload


def _is_line_event_readback_record(value: object) -> TypeGuard[LineEventReadbackRecord]:
    return isinstance(value, LineEventReadbackRecord)


def project_line_event_readbacks(
    records: Iterable[LineEventReadbackRecord],
) -> tuple[LineEventProjectionRow, ...]:
    """Project typed line-event records through the successor readback port."""

    typed = tuple(records)
    if not typed:
        raise LineEventProjectionError(
            "line-event readback projection requires at least one record"
        )
    for record in typed:
        if not _is_line_event_readback_record(record):
            raise LineEventProjectionError(
                "line-event projection requires typed readback records"
            )
        record.verify_digest()
    ordered = tuple(sorted(typed, key=lambda record: record.line_key))
    if len({record.line_key for record in ordered}) != len(ordered):
        raise LineEventProjectionError(
            "line-event projection cannot carry duplicate line keys"
        )
    rows: list[LineEventProjectionRow] = []
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


LegacyProcessTaskProjection = ProcessTaskProjection
LegacyProcessObservationProjection = ProcessObservationProjection


__all__ = [
    "HISTORICAL_PROCESS_OBSERVATION_PROJECTOR_ID",
    "HISTORICAL_PROCESS_OBSERVATION_PROJECTION_SCHEMA_V1",
    "HistoricalProcessObservationProjectionRead",
    "LINE_EVENT_READBACK_PROJECTOR_REF",
    "LegacyProcessObservationProjection",
    "LegacyProcessTaskProjection",
    "LineEventProjectionError",
    "LineEventProjectionRow",
    "PROCESS_OBSERVATION_PROJECTOR_ID",
    "PROCESS_OBSERVATION_PROJECTOR_REF",
    "PROCESS_OBSERVATION_PROJECTOR_VERSION",
    "PROCESS_OBSERVATION_PROJECTION_SCHEMA_V1",
    "PROCESS_OBSERVATION_TASK_SCHEMA_V1",
    "ProcessProjectionError",
    "ProcessObservationProjection",
    "ProcessTaskProjection",
    "SourceBindingMismatch",
    "join_process_observations",
    "normalize_observed_status",
    "project_line_event_readbacks",
    "read_historical_process_observation_projection",
]
