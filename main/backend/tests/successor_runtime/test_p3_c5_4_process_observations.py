"""C5.4 offline Celery/DB/process observation capture and join acceptance."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.successor_migration.legacy_process_observations import (
    LegacyProcessObservationError,
    capture_celery_async_result,
    capture_celery_inspect_task,
    capture_etl_job_run,
    capture_process_log,
)
from app.successor_runtime.runtime.observations import (
    LegacySourceObservation,
    ObservationClass,
    ObservationFreshness,
    ObservationSourceKind,
)
from app.successor_runtime.substrate.projections.legacy_process import (
    ProcessProjectionError,
    SourceBindingMismatch,
    join_process_observations,
    normalize_observed_status,
)

pytestmark = pytest.mark.unit

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[1]


def _now() -> datetime:
    return datetime(2030, 2, 2, 3, 4, tzinfo=UTC)


def test_offline_celery_inspect_and_db_rows_capture_typed_observations() -> None:
    now = _now()
    inspect = capture_celery_inspect_task(
        {"id": "task-inspect-1", "name": "task_poll_crawler_job", "status": "active"},
        worker="worker-a",
        observed_at=now,
        linked_run_id="run:1",
        linked_step_id="step:1",
        linked_attempt_id="a" * 64,
    )
    job = capture_etl_job_run(
        {
            "id": 17,
            "job_type": "crawler",
            "status": "running",
            "params": {"job_type_full": "crawler_job"},
            "external_provider": "provider-a",
        },
        observed_at=now,
        linked_run_id="run:1",
    )

    assert inspect.source_kind is ObservationSourceKind.CELERY_INSPECT
    assert inspect.observation_class is ObservationClass.OBSERVED
    assert inspect.observed_state == "active"
    assert inspect.linked_attempt_id == "a" * 64
    assert job.source_kind is ObservationSourceKind.ETL_JOB_RUN
    assert job.source_identity == "db-job-17"
    assert len(inspect.source_digest) == 64
    assert inspect.terminal_authority_claim is None
    assert job.terminal_authority_claim is None


def test_async_result_contradictory_and_missing_status_are_fail_closed() -> None:
    now = _now()
    contradictory = capture_celery_async_result(
        {"task_id": "task-async-1", "status": "SUCCESS", "ready": True},
        observed_at=now,
    )
    unavailable = capture_celery_async_result(
        {"task_id": "task-async-2", "ready": False},
        observed_at=now,
    )

    assert contradictory.observation_class is ObservationClass.CONTRADICTORY
    assert contradictory.reason == "ASYNC_RESULT_READY_WITHOUT_SUCCESS_FLAG"
    assert unavailable.observation_class is ObservationClass.UNAVAILABLE
    assert unavailable.reason == "ASYNC_RESULT_STATUS_ABSENT"
    assert contradictory.terminal_authority_claim is None


def test_join_projection_keeps_contradiction_and_unbound_explicit() -> None:
    now = _now()
    active = capture_celery_inspect_task(
        {"id": "task-join-1", "status": "active"},
        worker="worker-a",
        observed_at=now,
        linked_run_id="run:1",
    )
    running = capture_etl_job_run(
        {"id": 1, "status": "running"},
        observed_at=now,
        linked_run_id="run:1",
    )
    success = capture_celery_async_result(
        {"task_id": "db-job-1", "status": "SUCCESS", "ready": True, "successful": True},
        observed_at=now,
        linked_run_id="run:1",
    )
    joined = join_process_observations(
        (active, running),
        captured_at=now,
    )
    contradictory = join_process_observations(
        (success, running),
        captured_at=now,
    )
    unbound = LegacySourceObservation.from_content(
        source_kind=ObservationSourceKind.PROCESS_LOG,
        source_locator="process-log://unknown",
        source_identity="task-unbound-1",
        observed_state=None,
        observation_class=ObservationClass.UNBOUND,
        observed_at=now,
        freshness=ObservationFreshness.FRESH,
        reason="NO_BOUND_RUNTIME_LINK",
    )
    unbound_join = join_process_observations(
        (unbound,),
        captured_at=now,
    )

    task = joined.tasks[0]
    assert task.observation_class is ObservationClass.OBSERVED
    assert task.status == "ACTIVE"
    assert task.linked_run_id == "run:1"
    assert task.terminal_authority_claim is None
    assert contradictory.tasks[0].observation_class is ObservationClass.CONTRADICTORY
    assert contradictory.tasks[0].status == "UNKNOWN"
    assert unbound_join.tasks[0].observation_class is ObservationClass.UNBOUND


def test_stale_only_join_is_stale_and_digest_is_deterministic() -> None:
    now = _now()
    fresh = capture_celery_inspect_task(
        {"id": "task-stale-1", "status": "pending"},
        worker="worker-a",
        observed_at=now,
        linked_run_id="run:1",
    )
    stale = capture_celery_inspect_task(
        {"id": "task-stale-1", "status": "pending"},
        worker="worker-a",
        observed_at=now,
        freshness=ObservationFreshness.STALE,
        linked_run_id="run:1",
    )
    first = join_process_observations((fresh,), captured_at=now)
    second = join_process_observations((fresh,), captured_at=now)
    stale_view = join_process_observations((stale,), captured_at=now)

    assert first.view_digest == second.view_digest
    assert first.tasks[0].observation_class is ObservationClass.OBSERVED
    assert stale_view.tasks[0].observation_class is ObservationClass.STALE
    assert stale_view.tasks[0].status == "PENDING"


def test_join_requires_at_least_one_typed_observation() -> None:
    with pytest.raises(ProcessProjectionError):
        join_process_observations((), captured_at=_now())


def test_status_normalization_matches_legacy_vocabulary() -> None:
    assert normalize_observed_status("completed") == "COMPLETED"
    assert normalize_observed_status("started") == "ACTIVE"
    assert normalize_observed_status("queued") == "PENDING"
    assert normalize_observed_status("failure") == "FAILED"
    assert normalize_observed_status("canceled") == "CANCELED"
    assert normalize_observed_status("info") == "ACTIVE"
    assert normalize_observed_status(None) == "UNKNOWN"


def test_successor_runtime_c5_files_have_no_infra_or_legacy_imports() -> None:
    runtime_root = BACKEND / "app" / "successor_runtime"
    for relative in (
        "runtime/observations.py",
        "substrate/projections/agent_session.py",
        "substrate/projections/legacy_process.py",
    ):
        source = (runtime_root / relative).read_text(encoding="utf-8")
        for forbidden in (
            "import celery",
            "import redis",
            "app.services",
            "app.successor_migration",
        ):
            assert forbidden not in source, f"{relative} contains {forbidden!r}"


def test_process_log_capture_is_offline_only() -> None:
    now = _now()
    log = capture_process_log(
        {
            "path": "worker.log",
            "line_no": "12",
            "level": "info",
            "task_id": "task-log-1",
        },
        observed_at=now,
        linked_run_id="run:1",
    )
    assert log.source_kind is ObservationSourceKind.PROCESS_LOG
    assert log.observed_state == "info"
    assert log.observation_class is ObservationClass.OBSERVED
    assert log.raw_evidence_ref == "fixture:process-log:worker.log:12"


def test_unbound_variants_cover_every_source_kind() -> None:
    now = _now()
    captures = (
        capture_celery_inspect_task(
            {"id": "task-unbound-a", "status": "active"},
            worker="worker-a",
            observed_at=now,
        ),
        capture_celery_async_result(
            {
                "task_id": "task-unbound-b",
                "status": "SUCCESS",
                "ready": True,
                "successful": True,
            },
            observed_at=now,
        ),
        capture_etl_job_run(
            {"id": 99, "status": "running"},
            observed_at=now,
        ),
        capture_process_log(
            {
                "path": "worker.log",
                "line_no": "3",
                "level": "info",
                "task_id": "task-unbound-c",
            },
            observed_at=now,
        ),
    )
    for observation in captures:
        assert observation.observation_class is ObservationClass.UNBOUND
        assert observation.reason == "NO_BOUND_RUNTIME_LINK"


def test_process_log_level_is_normalized_and_unsupported_level_fails_closed() -> None:
    now = _now()
    normalized = capture_process_log(
        {"path": "worker.log", "level": "info", "task_id": "task-log-level"},
        observed_at=now,
        linked_run_id="run:1",
    )
    assert normalized.observed_state == "info"
    assert normalized.observation_class is ObservationClass.OBSERVED
    with pytest.raises(LegacyProcessObservationError):
        capture_process_log(
            {"path": "worker.log", "level": "verbose", "task_id": "task-log-bad"},
            observed_at=now,
            linked_run_id="run:1",
        )


def test_multiple_runtime_bindings_for_one_task_raise_source_binding_mismatch() -> None:
    now = _now()
    first = capture_celery_inspect_task(
        {"id": "task-multi-binding", "status": "active"},
        worker="worker-a",
        observed_at=now,
        linked_run_id="run:1",
    )
    second = capture_celery_inspect_task(
        {"id": "task-multi-binding", "status": "active"},
        worker="worker-a",
        observed_at=now,
        linked_run_id="run:2",
    )
    with pytest.raises(SourceBindingMismatch):
        join_process_observations((first, second), captured_at=now)
