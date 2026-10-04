"""Kit registration projection for the existing C9 semantic vocabulary.

The source schemas, runtime events, session statuses, search segment kinds and
loss kinds mirror the pure definitions in ``substrate/projections/c9_sources``.
The projector outcome and normalized projector failure classification are
registration projections only; they do not claim live projector delivery,
runtime closure, cutover, or replacement of the Postgres adapter's exceptions.
"""

from __future__ import annotations

from typing import Literal, get_args

from functorial_kit import define_failure_family, define_vocabulary

ProjectionProjectorOutcome = Literal[
    "PROJECTION_APPLIED",
    "PROJECTION_REBUILT",
    "PROJECTION_NO_CHANGE",
]
ProjectionRuntimeEventKind = Literal[
    "TASK_CREATED",
    "TASK_ASSIGNED",
    "TASK_PROJECTION_REFRESHED",
    "TASK_TERMINAL_SUCCEEDED",
    "TASK_TERMINAL_FAILED",
]
ProjectionSessionStatus = Literal[
    "WAITING",
    "RUNNING",
    "TERMINAL_SUCCEEDED",
    "TERMINAL_FAILED",
]
ProjectionSearchSegmentKind = Literal[
    "TEXT_SEGMENT",
    "FIELD_SEGMENT",
]
ProjectionProjectionLossKind = Literal[
    "DECLARED_LOSS",
    "OMITTED_FIELD",
    "NOT_EXECUTED",
]
ProjectionProjectionSourceSchema = Literal[
    "mrw.projection.task-source.v2",
    "mrw.projection.knowledge-source.v2",
    "mrw.projection.material-source.v2",
]
ProjectionProcessingFailureCode = Literal[
    "SOURCE_UNAVAILABLE",
    "SOURCE_DRIFT",
    "SOURCE_INCARNATION_STALE",
    "OFFSET_STALE",
    "PROJECTION_OFFSET_CLOSURE_DRIFT",
    "EXTERNAL_INDEX_EFFECT_FAILED",
    "REBUILD_FAILED",
]

projection_projector_outcomes = define_vocabulary(
    "projection.outcome", get_args(ProjectionProjectorOutcome)
)
projection_runtime_event_kinds = define_vocabulary(
    "projection.task.event.kind", get_args(ProjectionRuntimeEventKind)
)
projection_session_statuses = define_vocabulary(
    "projection.task.status", get_args(ProjectionSessionStatus)
)
projection_search_segment_kinds = define_vocabulary(
    "projection.material.segment.kind", get_args(ProjectionSearchSegmentKind)
)
projection_projection_loss_kinds = define_vocabulary(
    "projection.loss.kind", get_args(ProjectionProjectionLossKind)
)
projection_projection_source_schemas = define_vocabulary(
    "projection.source.schema", get_args(ProjectionProjectionSourceSchema)
)
projection_processing_failures = define_failure_family(
    "projection.processing.failure", get_args(ProjectionProcessingFailureCode)
)

__all__ = [
    "projection_projection_loss_kinds",
    "projection_projection_source_schemas",
    "projection_processing_failures",
    "projection_projector_outcomes",
    "projection_runtime_event_kinds",
    "projection_search_segment_kinds",
    "projection_session_statuses",
]
