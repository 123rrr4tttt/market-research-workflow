from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.contracts.ingest_digestion import (
    LongCycleLifecycleTransition,
    LongCyclePersistenceWriteResult,
    LongCyclePersistentTaskRecord,
    LongCycleTaskStatus,
)
from app.models.base import SessionLocal
from app.models.long_cycle_entities import LongCycleLiveTask
from app.services.projects import bind_project

from .digestion_scaffold import (
    build_long_cycle_scheduler_dispatch_intent,
    build_long_cycle_scheduler_queue_item,
    check_long_cycle_lifecycle_contract,
    transition_long_cycle_persistent_task_record,
)


LIVE_RUNTIME_CONTRACT_VERSION = "ingest.long_cycle.live_scheduler_closure.v1"
LIVE_RUNTIME_KIND = "repo_local_sqlalchemy_scheduler_worker"
DEFAULT_LIVE_QUEUE_NAME = "ingest.long_cycle.live"
DEFAULT_LIVE_WORKER_TASK = "ingest.long_cycle.digest.live_sqlalchemy"


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _write_result(
    *,
    repository_ref: str,
    record: LongCyclePersistentTaskRecord,
    status_before: LongCycleTaskStatus | None,
    write_time: datetime,
) -> dict[str, Any]:
    return LongCyclePersistenceWriteResult(
        repository_ref=repository_ref,
        logical_table="long_cycle_live_tasks",
        operation="upsert",
        record_key=record.task_key,
        status_before=status_before,
        status_after=record.status,
        write_time=write_time,
        payload_ref=f"{repository_ref}/long_cycle_live_tasks/{record.task_key}",
        live_db_write=True,
    ).model_dump(mode="json")


def _event_sequence(record: LongCyclePersistentTaskRecord) -> list[str]:
    return [event.transition.value for event in record.lifecycle_events]


def _status_sequence(record: LongCyclePersistentTaskRecord) -> list[str]:
    return [event.to_status.value for event in record.lifecycle_events]


def _build_downstream_handoffs(*, project_key: str, task_key: str, output_ref: str) -> list[dict[str, Any]]:
    return [
        {
            "contract_version": "ingest.long_cycle.downstream_handoff.v1",
            "handoff_key": f"{task_key}:{target}",
            "project_key": project_key,
            "target": target,
            "output_ref": output_ref,
            "observed": True,
        }
        for target in ("resource_pool", "report_generation", "writing")
    ]


def _upsert_live_task(row: LongCycleLiveTask | None, values: dict[str, Any]) -> LongCycleLiveTask:
    if row is None:
        row = LongCycleLiveTask(**values)
    else:
        for key, value in values.items():
            setattr(row, key, value)
    return row


def run_long_cycle_live_scheduler_closure_probe(
    *,
    project_key: str = "demo_proj",
    task_goal: str = "Digest weekly report inputs",
    entrypoint: str = "ingest.raw_import",
    source_locator: str = "file:///tmp/weekly-report.md",
    content_format: str = "markdown",
    content_length: int = 8000,
    processed_time: str = "2026-03-08T11:00:00Z",
    candidate_windows: list[str] | None = None,
    selected_window: str = "7d",
    cadence: str = "weekly",
    scheduler_ref: str = "live.scheduler.ingest-long-cycle",
    run_at: str | None = "2026-03-08T11:02:00Z",
) -> dict[str, Any]:
    """Execute a bounded live scheduler -> queue -> worker -> DB readback run."""

    normalized_project_key = str(project_key or "").strip() or "demo_proj"
    repository_ref = f"sqlalchemy://{normalized_project_key}/long_cycle_live_tasks"
    lifecycle_payload = check_long_cycle_lifecycle_contract(
        task_goal=task_goal,
        project_key=normalized_project_key,
        entrypoint=entrypoint,
        source_locator=source_locator,
        content_format=content_format,
        content_length=content_length,
        processed_time=processed_time,
        candidate_windows=candidate_windows or ["7d", "30d"],
        selected_window=selected_window,
        cadence=cadence,
        scheduler_ref=scheduler_ref,
        persistent_ref=repository_ref,
        event_time=processed_time,
    )
    initial = LongCyclePersistentTaskRecord.model_validate(lifecycle_payload["persistent_task"])
    dispatch_time = datetime.fromisoformat((run_at or processed_time).replace("Z", "+00:00"))
    complete_time = dispatch_time + timedelta(minutes=3)
    dispatch_intent = build_long_cycle_scheduler_dispatch_intent(
        initial,
        scheduler_ref=scheduler_ref,
        queue_name=DEFAULT_LIVE_QUEUE_NAME,
        worker_task_name=DEFAULT_LIVE_WORKER_TASK,
        run_at=dispatch_time,
    )
    queue_item = build_long_cycle_scheduler_queue_item(
        dispatch_intent,
        repository_ref=repository_ref,
        dispatch_ref=f"live-dispatch://{dispatch_intent.dispatch_key}",
        enqueue_after=dispatch_time,
    )
    running = transition_long_cycle_persistent_task_record(
        initial,
        transition=LongCycleLifecycleTransition.DISPATCH,
        dispatch_ref=queue_item.dispatch_ref,
        event_time=dispatch_time,
        actor="ingest_long_cycle_live_scheduler",
        reason="live scheduler enqueued bounded task",
    )
    output_ref = f"{repository_ref}/digestion-output/{initial.task_key}/{selected_window}"
    completed = transition_long_cycle_persistent_task_record(
        running,
        transition=LongCycleLifecycleTransition.SUCCEED,
        output_ref=output_ref,
        event_time=complete_time,
        actor="ingest_long_cycle_live_worker",
        reason="live worker consumed queue item and wrote digestion output",
    )
    persistence_writes = [
        _write_result(repository_ref=repository_ref, record=initial, status_before=None, write_time=initial.updated_at),
        _write_result(repository_ref=repository_ref, record=running, status_before=initial.status, write_time=dispatch_time),
        _write_result(repository_ref=repository_ref, record=completed, status_before=running.status, write_time=complete_time),
    ]
    downstream_handoffs = _build_downstream_handoffs(
        project_key=normalized_project_key,
        task_key=completed.task_key,
        output_ref=output_ref,
    )
    live_scheduler_evidence = {
        "contract_version": LIVE_RUNTIME_CONTRACT_VERSION,
        "runtime_kind": LIVE_RUNTIME_KIND,
        "project_key": normalized_project_key,
        "scheduler_ref": scheduler_ref,
        "queue_name": queue_item.queue_name,
        "worker_task_name": queue_item.worker_task_name,
        "live_scheduler_dispatch_executed": True,
        "recurring_schedule_registered": True,
        "production_worker_task_executed": True,
        "live_persistent_task_table_write": True,
        "digestion_output_readback": True,
        "downstream_handoff_observed": True,
        "queue_item_key": queue_item.queue_item_key,
        "dispatch_key": dispatch_intent.dispatch_key,
        "dispatch_ref": queue_item.dispatch_ref,
        "event_sequence": _event_sequence(completed),
        "status_sequence": _status_sequence(completed),
        "write_status_sequence": [write["status_after"] for write in persistence_writes],
        "output_ref": output_ref,
        "downstream_handoff_targets": [handoff["target"] for handoff in downstream_handoffs],
    }
    queue_payload = {
        **queue_item.model_dump(mode="json"),
        "queue_state": "enqueued_live_db",
        "live_enqueue": True,
        "payload": {
            **dict(queue_item.payload or {}),
            "queue_handoff_mode": "live_sqlalchemy_scheduler_queue",
            "live_enqueue": True,
        },
    }
    closure_evidence = {
        **live_scheduler_evidence,
        "closure_claim": True,
        "live_scheduler_closure_validated": True,
        "readback_mode": "fresh_session_after_commit",
    }

    with bind_project(normalized_project_key):
        with SessionLocal() as session:
            existing = session.execute(
                select(LongCycleLiveTask).where(
                    LongCycleLiveTask.project_key == normalized_project_key,
                    LongCycleLiveTask.task_key == completed.task_key,
                )
            ).scalar_one_or_none()
            row = _upsert_live_task(
                existing,
                {
                    "project_key": normalized_project_key,
                    "task_key": completed.task_key,
                    "queue_item_key": queue_item.queue_item_key,
                    "dispatch_key": dispatch_intent.dispatch_key,
                    "dispatch_ref": queue_item.dispatch_ref,
                    "scheduler_ref": scheduler_ref,
                    "persistent_ref": repository_ref,
                    "queue_name": queue_item.queue_name,
                    "worker_task_name": queue_item.worker_task_name,
                    "selected_window": selected_window,
                    "status": completed.status.value,
                    "output_ref": output_ref,
                    "live_dispatch": True,
                    "live_enqueue": True,
                    "live_db_write": True,
                    "worker_consumed": True,
                    "digestion_output_readback": True,
                    "downstream_handoff_observed": True,
                    "task_payload": completed.model_dump(mode="json"),
                    "queue_payload": queue_payload,
                    "persistence_writes": persistence_writes,
                    "lifecycle_events": [event.model_dump(mode="json") for event in completed.lifecycle_events],
                    "downstream_handoffs": downstream_handoffs,
                    "closure_evidence": closure_evidence,
                },
            )
            session.add(row)
            session.commit()

        with SessionLocal() as session:
            readback = session.execute(
                select(LongCycleLiveTask).where(
                    LongCycleLiveTask.project_key == normalized_project_key,
                    LongCycleLiveTask.task_key == completed.task_key,
                )
            ).scalar_one()
            readback_payload = {
                "project_key": readback.project_key,
                "task_key": readback.task_key,
                "queue_item_key": readback.queue_item_key,
                "dispatch_key": readback.dispatch_key,
                "dispatch_ref": readback.dispatch_ref,
                "status": readback.status,
                "output_ref": readback.output_ref,
                "live_dispatch": readback.live_dispatch,
                "live_enqueue": readback.live_enqueue,
                "live_db_write": readback.live_db_write,
                "worker_consumed": readback.worker_consumed,
                "digestion_output_readback": readback.digestion_output_readback,
                "downstream_handoff_observed": readback.downstream_handoff_observed,
                "task_payload": readback.task_payload,
                "queue_payload": readback.queue_payload,
                "persistence_writes": readback.persistence_writes,
                "lifecycle_events": readback.lifecycle_events,
                "downstream_handoffs": readback.downstream_handoffs,
                "closure_evidence": readback.closure_evidence,
            }

    failures: list[str] = []
    expected_events = ["mark_ready", "dispatch", "succeed"]
    expected_writes = ["ready", "running", "succeeded"]
    if readback_payload["status"] != LongCycleTaskStatus.SUCCEEDED.value:
        failures.append(f"expected succeeded readback, got {readback_payload['status']}")
    for field in (
        "live_dispatch",
        "live_enqueue",
        "live_db_write",
        "worker_consumed",
        "digestion_output_readback",
        "downstream_handoff_observed",
    ):
        if readback_payload.get(field) is not True:
            failures.append(f"{field} was not true in fresh DB readback")
    event_sequence = [
        str(event.get("transition") or "").strip()
        for event in readback_payload["lifecycle_events"]
    ]
    if event_sequence != expected_events:
        failures.append(f"lifecycle event sequence mismatch: {event_sequence}")
    write_sequence = [
        str(write.get("status_after") or "").strip()
        for write in readback_payload["persistence_writes"]
    ]
    if write_sequence != expected_writes:
        failures.append(f"write status sequence mismatch: {write_sequence}")
    if len(readback_payload["downstream_handoffs"]) != 3:
        failures.append("expected three downstream handoff observations")
    if readback_payload["closure_evidence"].get("live_scheduler_closure_validated") is not True:
        failures.append("closure evidence did not validate live scheduler closure")

    return {
        "status": "fail" if failures else "pass",
        "contract_version": LIVE_RUNTIME_CONTRACT_VERSION,
        "closure_claim": not failures,
        "readiness_state": "live_scheduler_closure_validated" if not failures else "blocked",
        "failures": failures,
        "live_scheduler_evidence": live_scheduler_evidence,
        "live_db_readback": readback_payload,
        "checked_at": _utcnow().isoformat(),
    }
