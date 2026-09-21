from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.task_readback_metadata import (
    build_runtime_readback_payload,
    merge_request_runtime_context,
    merge_runtime_readback_payload,
)


pytestmark = pytest.mark.unit


def test_build_runtime_readback_payload_records_identity_and_event() -> None:
    payload = build_runtime_readback_payload(
        line_key="Search-Discovery Index",
        trace_id="trace-1",
        run_id="run-1",
        task_id="task-1",
        worker_name="celery@worker-a",
        queue="agent_batch.main",
        status="running",
        event="task_dispatched",
        event_source="agent_batch",
    )

    assert payload["line_key"] == "search_discovery_index"
    assert payload["trace_id"] == "trace-1"
    assert payload["run_id"] == "run-1"
    assert payload["task_id"] == "task-1"
    assert payload["worker_name"] == "celery@worker-a"
    assert payload["queue"] == "agent_batch.main"
    assert payload["status"] == "running"
    assert any(event["event"] == "task_dispatched" for event in payload["events"])


def test_merge_runtime_readback_payload_adds_terminal_event_only_when_line_key_present() -> None:
    base = {
        "line_key": "resource_source_library",
        "trace_id": "trace-source",
        "run_id": "run-source",
        "events": [{"event": "worker_started", "status": "running"}],
    }

    merged = merge_runtime_readback_payload(
        base,
        {"queue": "agent_batch.subagent", "worker_name": "celery@source"},
        status="completed",
        event="completed",
        event_source="etl_job_runs",
    )

    assert merged["line_key"] == "resource_source_library"
    assert merged["queue"] == "agent_batch.subagent"
    assert merged["worker_name"] == "celery@source"
    assert merged["status"] == "completed"
    event_names = [event["event"] for event in merged["events"]]
    assert "worker_started" in event_names
    assert "completed" in event_names
    assert "resource_action_accepted" in event_names
    assert "adapter_capture_completed" in event_names
    assert "source_lifecycle_updated" in event_names
    assert "readback_persisted" in event_names

    untouched = merge_runtime_readback_payload({"status": "completed"}, None, status="completed", event="completed")
    assert untouched == {"status": "completed"}


def test_merge_request_runtime_context_prefers_celery_request_fields() -> None:
    request = SimpleNamespace(
        id="celery-task-1",
        hostname="celery@host-a",
        delivery_info={"routing_key": "agent_batch.main", "queue": "fallback"},
    )

    merged = merge_request_runtime_context(
        {
            "line_key": "ingest",
            "trace_id": "trace-ingest",
            "run_id": "run-ingest",
            "worker_name": "dispatch-placeholder",
            "queue": "dispatch-queue",
        },
        request,
    )

    assert merged["task_id"] == "celery-task-1"
    assert merged["worker_name"] == "celery@host-a"
    assert merged["queue"] == "agent_batch.main"
    assert merged["trace_id"] == "trace-ingest"
    assert merged["run_id"] == "run-ingest"
    event_names = [event["event"] for event in merged["events"]]
    assert "worker_started" in event_names
    assert "task_queued" in event_names
