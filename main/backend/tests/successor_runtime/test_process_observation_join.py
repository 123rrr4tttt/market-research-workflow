"""Current typed process observation join witness for C5.4."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.successor_runtime.runtime.observations import (
    LegacySourceObservation,
    ObservationClass,
    ObservationFreshness,
    ObservationSourceKind,
)
from app.successor_runtime.runtime.process_observation import (
    SourceBindingMismatch,
    join_process_observations,
    try_join_process_observations,
)
from functorial_kit import Failure


NOW = datetime(2030, 2, 2, 3, 4, tzinfo=UTC)


def _observation(
    source_kind: ObservationSourceKind,
    source_identity: str,
    *,
    observed_state: str | None = None,
    observation_class: ObservationClass = ObservationClass.OBSERVED,
    freshness: ObservationFreshness = ObservationFreshness.FRESH,
    reason: str | None = None,
    linked_run_id: str | None = "run:1",
) -> LegacySourceObservation:
    return LegacySourceObservation.from_content(
        source_kind=source_kind,
        source_locator=f"fixture://{source_kind.value}/{source_identity}",
        source_identity=source_identity,
        observed_state=observed_state,
        observation_class=observation_class,
        observed_at=NOW,
        freshness=freshness,
        linked_run_id=linked_run_id,
        reason=reason,
    )


def test_join_projects_current_observed_state_without_terminal_authority() -> None:
    active = _observation(
        ObservationSourceKind.CELERY_INSPECT,
        "task-active",
        observed_state="active",
    )
    running = _observation(
        ObservationSourceKind.ETL_JOB_RUN,
        "job-running",
        observed_state="running",
    )
    joined = join_process_observations((active, running), captured_at=NOW)

    assert joined.tasks[0].status == "ACTIVE"
    assert joined.tasks[0].observation_class is ObservationClass.OBSERVED
    assert joined.tasks[0].terminal_authority_claim is None
    assert joined.view_digest == join_process_observations(
        (active, running), captured_at=NOW
    ).view_digest


def test_join_preserves_contradiction_stale_and_unbound() -> None:
    contradictory = _observation(
        ObservationSourceKind.CELERY_ASYNC_RESULT,
        "task-contradictory",
        observed_state="SUCCESS",
        observation_class=ObservationClass.CONTRADICTORY,
        reason="READY_WITHOUT_SUCCESS_FLAG",
    )
    stale = _observation(
        ObservationSourceKind.CELERY_INSPECT,
        "task-stale",
        observed_state="pending",
        freshness=ObservationFreshness.STALE,
    )
    unbound = _observation(
        ObservationSourceKind.PROCESS_LOG,
        "task-unbound",
        observed_state="info",
        observation_class=ObservationClass.UNBOUND,
        reason="NO_BOUND_RUNTIME_LINK",
        linked_run_id=None,
    )

    contradictory_join = join_process_observations((contradictory,), captured_at=NOW)
    stale_join = join_process_observations((stale,), captured_at=NOW)
    unbound_join = join_process_observations((unbound,), captured_at=NOW)

    assert contradictory_join.tasks[0].status == "UNKNOWN"
    assert stale_join.tasks[0].status == "PENDING"
    assert unbound_join.tasks[0].observation_class is ObservationClass.UNBOUND


def test_join_fails_closed_on_empty_or_conflicting_bindings() -> None:
    empty = try_join_process_observations((), captured_at=NOW)
    first = _observation(
        ObservationSourceKind.CELERY_INSPECT,
        "task-conflict",
        observed_state="active",
        linked_run_id="run:1",
    )
    second = _observation(
        ObservationSourceKind.CELERY_INSPECT,
        "task-conflict",
        observed_state="active",
        linked_run_id="run:2",
    )

    assert isinstance(empty, Failure)
    with pytest.raises(SourceBindingMismatch):
        join_process_observations((first, second), captured_at=NOW)
