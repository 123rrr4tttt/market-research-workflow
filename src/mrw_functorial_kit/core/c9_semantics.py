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

C9ProjectorOutcome = Literal[
    "PROJECTION_APPLIED",
    "PROJECTION_REBUILT",
    "PROJECTION_NO_CHANGE",
]
C9RuntimeEventKind = Literal[
    "SESSION_CREATED",
    "SESSION_TASK_ASSIGNED",
    "SESSION_PROJECTION_REFRESHED",
    "SESSION_TERMINAL_SUCCEEDED",
    "SESSION_TERMINAL_FAILED",
]
C9SessionStatus = Literal[
    "WAITING",
    "RUNNING",
    "TERMINAL_SUCCEEDED",
    "TERMINAL_FAILED",
]
C9SearchSegmentKind = Literal[
    "TEXT_SEGMENT",
    "FIELD_SEGMENT",
]
C9ProjectionLossKind = Literal[
    "DECLARED_LOSS",
    "OMITTED_FIELD",
    "NOT_EXECUTED",
]
C9ProjectionSourceSchema = Literal[
    "mrw.successor.c9.runtime-session-source.v1",
    "mrw.successor.c9.research-graph-source.v1",
    "mrw.successor.c9.c7-search-source.v1",
]
C9ProjectorFailureCode = Literal[
    "SOURCE_UNAVAILABLE",
    "SOURCE_DRIFT",
    "SOURCE_INCARNATION_STALE",
    "OFFSET_STALE",
    "PROJECTION_OFFSET_CLOSURE_DRIFT",
    "EXTERNAL_INDEX_EFFECT_FAILED",
    "REBUILD_FAILED",
]

c9_projector_outcomes = define_vocabulary(
    "c9.projector.outcome", get_args(C9ProjectorOutcome)
)
c9_runtime_event_kinds = define_vocabulary(
    "c9.runtime.event.kind", get_args(C9RuntimeEventKind)
)
c9_session_statuses = define_vocabulary(
    "c9.session.status", get_args(C9SessionStatus)
)
c9_search_segment_kinds = define_vocabulary(
    "c9.search.segment.kind", get_args(C9SearchSegmentKind)
)
c9_projection_loss_kinds = define_vocabulary(
    "c9.projection.loss.kind", get_args(C9ProjectionLossKind)
)
c9_projection_source_schemas = define_vocabulary(
    "c9.projection.source.schema", get_args(C9ProjectionSourceSchema)
)
c9_projector_failures = define_failure_family(
    "c9.projector.failure", get_args(C9ProjectorFailureCode)
)

__all__ = [
    "c9_projection_loss_kinds",
    "c9_projection_source_schemas",
    "c9_projector_failures",
    "c9_projector_outcomes",
    "c9_runtime_event_kinds",
    "c9_search_segment_kinds",
    "c9_session_statuses",
]
