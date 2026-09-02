"""Focused acceptance for the S1 horizontal line-event/readback port.

The tests never import or execute the donor ``task_readback_metadata``
module.  Donor behavior is expressed only as inline fixtures: the
worker-required line keys, the canonical worker_started chain and the typed
readback payload that must stay fail-closed until the terminal
``readback_persisted`` observation is present.
"""

from __future__ import annotations

import pytest

from app.successor_runtime.capabilities.line_event_readback_port import (
    AUTHORITY_SNAPSHOT,
    KNOWN_LINE_KEYS,
    LINE_EVENT_CHAINS,
    TERMINAL_READBACK_EVENTS,
    IllegalEventMigrationError,
    LineEvent,
    LineEventReadbackPort,
    LineEventReadbackRecord,
    UnknownLineEventError,
    UnknownLineKeyError,
)

pytestmark = pytest.mark.unit

# Donor semantic fixture: resource_source_library required events, in the
# order the legacy worker readback metadata builder guarantees.
DONOR_RESOURCE_EVENTS = (
    "resource_action_accepted",
    "task_queued",
    "worker_started",
    "adapter_capture_completed",
    "source_lifecycle_updated",
    "readback_persisted",
)


def _resource_started_record() -> LineEventReadbackRecord:
    record = LineEventReadbackPort.empty("resource_source_library")
    return LineEventReadbackPort.observe(
        record,
        event="worker_started",
        status="running",
        source="celery_worker",
        task_id="worker-task-1",
        trace_id="trace-resource-1",
        run_id="run-resource-1",
        worker_name="celery@worker-a",
        queue="agent_batch.main",
    )


def test_successor_line_chain_keeps_worker_started_order_and_idempotency() -> None:
    record = _resource_started_record()

    assert record.line_key == "resource_source_library"
    assert record.status == "running"
    assert record.event_names == DONOR_RESOURCE_EVENTS[:3]
    assert record.events[2].source == "celery_worker"
    assert record.task_id == "worker-task-1"
    assert record.worker_name == "celery@worker-a"
    assert record.queue == "agent_batch.main"

    duplicate = LineEventReadbackPort.observe(
        record,
        event="worker_started",
        status="running",
        source="celery_worker",
        task_id="worker-task-2",
    )
    assert duplicate.event_names == record.event_names
    assert len(duplicate.events) == len(record.events)
    assert duplicate.task_id == "worker-task-2"
    assert duplicate.events[2].observed_at == record.events[2].observed_at


def test_readback_before_terminal_event_is_undecidable_even_after_completed() -> None:
    record = _resource_started_record()
    for event in DONOR_RESOURCE_EVENTS[3:5]:
        record = LineEventReadbackPort.observe(
            record,
            event=event,
            status="running",
            source="celery_worker",
        )
    completed = LineEventReadbackPort.observe(record, status="completed")

    assert completed.status == "completed"
    assert completed.event_names == DONOR_RESOURCE_EVENTS[:-1]
    result = LineEventReadbackPort.readback(completed)
    assert result.persistence_decidable is False
    assert result.persistence_observed is False
    assert result.canonical_write_authority is False
    assert "readback_persisted" in (result.reason or "")


def test_record_constructor_rejects_gapped_non_canonical_chain() -> None:
    started = _resource_started_record()
    with pytest.raises(IllegalEventMigrationError):
        LineEventReadbackRecord(
            line_key="resource_source_library",
            events=(
                started.events[0],
                LineEvent(
                    event=DONOR_RESOURCE_EVENTS[4],
                    source="status_scaffold",
                ),
            ),
        )


def test_success_trace_marks_persistence_only_after_explicit_readback() -> None:
    record = _resource_started_record()
    for event in DONOR_RESOURCE_EVENTS[3:5]:
        record = LineEventReadbackPort.observe(
            record,
            event=event,
            status="running",
            source="celery_worker",
        )
    record = LineEventReadbackPort.observe(record, status="completed")
    assert LineEventReadbackPort.readback(record).persistence_decidable is False
    record = LineEventReadbackPort.observe(
        record,
        event="readback_persisted",
        source="worker_readback",
    )

    result = LineEventReadbackPort.readback(record)
    assert result.persistence_decidable is True
    assert result.persistence_observed is True
    assert result.canonical_write_authority is False
    payload = LineEventReadbackPort.build_payload(record)
    assert [item["event"] for item in payload["events"]] == list(DONOR_RESOURCE_EVENTS)
    assert payload["readback"]["persistence_decidable"] is True
    assert payload["authority"]["canonical_write"] is False


def test_acceptance_trace_builder_reaches_terminal_readback() -> None:
    record = LineEventReadbackPort.empty("ingest")
    record = LineEventReadbackPort.build_acceptance_trace(record)

    assert record.event_names == LINE_EVENT_CHAINS["ingest"]
    result = LineEventReadbackPort.readback(record)
    assert result.persistence_decidable is True
    assert result.persistence_observed is True


def test_four_worker_required_lanes_share_canonical_chain_contract() -> None:
    assert KNOWN_LINE_KEYS == frozenset(LINE_EVENT_CHAINS)
    assert KNOWN_LINE_KEYS == {
        "ingest",
        "search_discovery_index",
        "resource_source_library",
        "writing_knowledge_graph_agent",
    }
    for line_key, events in LINE_EVENT_CHAINS.items():
        assert events[0] and events[1] == "task_queued"
        assert events[2] == "worker_started"
        assert events[-1] in TERMINAL_READBACK_EVENTS
        assert len(events) == len(set(events))
        record = LineEventReadbackPort.empty(line_key)
        for event in events:
            record = LineEventReadbackPort.observe(
                record,
                event=event,
                status="running" if event == "worker_started" else None,
            )
        assert record.event_names == events
        assert LineEventReadbackPort.readback(record).persistence_decidable is True


def test_normalization_and_fail_closed_unknown_line_key() -> None:
    record = LineEventReadbackPort.empty("Search-Discovery Index")
    assert record.line_key == "search_discovery_index"

    with pytest.raises(UnknownLineKeyError):
        LineEventReadbackPort.empty("")
    with pytest.raises(UnknownLineKeyError):
        LineEventReadbackPort.empty("unregistered_line")
    with pytest.raises(UnknownLineKeyError):
        LineEventReadbackRecord(line_key="no_such_line")


def test_unknown_and_non_canonical_events_are_rejected() -> None:
    record = _resource_started_record()
    with pytest.raises(UnknownLineEventError):
        LineEventReadbackPort.observe(record, event="completed")
    with pytest.raises(UnknownLineEventError):
        LineEventReadbackPort.observe(record, event="")


def test_illegal_status_transitions_and_immutability_are_typed_failures() -> None:
    started = _resource_started_record()
    with pytest.raises(IllegalEventMigrationError):
        LineEventReadbackPort.observe(started, status="completed")

    for event in DONOR_RESOURCE_EVENTS[3:5]:
        started = LineEventReadbackPort.observe(
            started,
            event=event,
            status="running",
            source="celery_worker",
        )
    completed = LineEventReadbackPort.observe(started, status="completed")
    assert completed.status == "completed"
    assert LineEventReadbackPort.readback(completed).persistence_decidable is False

    failed = LineEventReadbackPort.observe(started, status="failed")
    assert failed.status == "failed"
    assert LineEventReadbackPort.readback(failed).persistence_decidable is False
    with pytest.raises(IllegalEventMigrationError):
        LineEventReadbackPort.observe(
            failed,
            event="readback_persisted",
            status="failed",
        )

    original_names = started.event_names
    original_digest = started.digest
    LineEventReadbackPort.observe(started, event="readback_persisted")
    assert started.event_names == original_names
    assert started.digest == original_digest


def test_record_digest_fails_closed_on_content_tampering() -> None:
    record = _resource_started_record()
    record.verify_digest()
    mutated = LineEventReadbackRecord(
        line_key=record.line_key,
        events=record.events,
        status=record.status,
        task_id=record.task_id,
        run_id=record.run_id,
        trace_id=record.trace_id,
        worker_name=record.worker_name,
        queue=record.queue,
        digest=record.digest,
    )
    assert mutated == record
    tampered = LineEventReadbackRecord(
        line_key=record.line_key,
        events=record.events,
        status="completed",
        task_id=record.task_id,
        run_id=record.run_id,
        trace_id=record.trace_id,
        worker_name=record.worker_name,
        queue=record.queue,
        digest=record.digest,
    )
    with pytest.raises(IllegalEventMigrationError):
        tampered.verify_digest()


def test_authority_defaults_are_all_false() -> None:
    assert AUTHORITY_SNAPSHOT == {
        "canonical_write": False,
        "live_provider": False,
        "external_delivery": False,
        "scheduler": False,
        "executor": False,
        "cutover": False,
    }
    assert LineEventReadbackPort.canonical_write_authority is False
    assert LineEventReadbackPort.live_provider_authority is False
    assert LineEventReadbackPort.scheduler_authority is False
    assert LineEventReadbackPort.executor_authority is False
    assert LineEventReadbackPort.cutover_authority is False


def test_acceptance_trace_payload_matches_legacy_shaped_fixture() -> None:
    record = LineEventReadbackPort.empty("resource_source_library")
    record = LineEventReadbackPort.observe(
        record,
        event="worker_started",
        status="running",
        source="celery_worker",
        task_id="celery-task-resource-1",
        run_id="run-resource-1",
        trace_id="trace-resource-1",
        worker_name="celery@worker-a",
        queue="agent_batch.main",
    )
    record = LineEventReadbackPort.observe(
        record,
        event="readback_persisted",
        source="worker_readback",
    )
    payload = LineEventReadbackPort.build_payload(record)

    assert payload["line_key"] == "resource_source_library"
    assert payload["status"] == "completed"
    assert payload["task_id"] == "celery-task-resource-1"
    assert payload["worker_name"] == "celery@worker-a"
    assert payload["queue"] == "agent_batch.main"
    assert [item["event"] for item in payload["events"]] == list(DONOR_RESOURCE_EVENTS)
    assert payload["events"][0]["event_source"] == "successor_scaffold"
    assert payload["events"][2]["event_source"] == "celery_worker"
    assert payload["events"][5]["event_source"] == "worker_readback"
    assert payload["readback"]["terminal_event"] == "readback_persisted"
    assert payload["readback"]["persistence_observed"] is True


def test_merge_context_keeps_first_identity_and_adds_routing() -> None:
    record = _resource_started_record()
    merged = LineEventReadbackPort.merge_context(
        record,
        {
            "task_id": "celery-task-1",
            "queue": "agent_batch.subagent",
            "trace_id": "trace-merged",
        },
    )
    assert merged.task_id == "celery-task-1"
    assert merged.queue == "agent_batch.subagent"
    assert merged.trace_id == "trace-merged"
    assert merged.event_names == record.event_names
    assert merged is not record
