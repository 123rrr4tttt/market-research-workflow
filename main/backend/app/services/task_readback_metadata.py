from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Mapping
from functorial_kit import Failure
from mrw_functorial_kit.core.application_failure_semantics import task_readback_contract_failures


SUCCESS_TERMINAL_STATUSES = {"completed", "succeeded", "applied", "available", "healthy"}
LINE_REQUIRED_EVENTS: dict[str, tuple[str, ...]] = {
    "ingest": (
        "submission_accepted",
        "task_queued",
        "worker_started",
        "source_fetch_completed",
        "index_handoff_recorded",
        "readback_persisted",
    ),
    "search_discovery_index": (
        "search_or_discovery_run_accepted",
        "task_queued",
        "worker_started",
        "index_refresh_started",
        "index_refresh_completed",
        "results_readback_persisted",
    ),
    "resource_source_library": (
        "resource_action_accepted",
        "task_queued",
        "worker_started",
        "adapter_capture_completed",
        "source_lifecycle_updated",
        "readback_persisted",
    ),
    "writing_knowledge_graph_agent": (
        "agent_batch_submitted",
        "task_queued",
        "worker_started",
        "agent_event_persisted",
        "approval_state_recorded",
        "artifact_readback_persisted",
    ),
}
LINE_ACCEPTED_EVENT: dict[str, str] = {
    line_key: events[0] for line_key, events in LINE_REQUIRED_EVENTS.items()
}
_FAILURE_WITNESS = "test:test_w01_request_failures"
_FAILURE_CONTEXT_KEYS = frozenset(
    {"owner", "operation", "failure_family", "public_exception", "public_message", "witness"}
)


def _task_readback_failure(message: str, *, operation: str) -> Failure:
    return task_readback_contract_failures.fail(
        "line_key_required",
        message,
        {
            "owner": "task_readback_metadata",
            "operation": operation,
            "failure_family": task_readback_contract_failures.name,
            "public_exception": "ValueError",
            "public_message": message,
            "witness": _FAILURE_WITNESS,
        },
    )


def _raise_task_readback_failure(failure: Failure) -> None:
    context = failure.context or {}
    if not task_readback_contract_failures.matches(failure) or _FAILURE_CONTEXT_KEYS - set(context):
        # kit:boundary owner=task_readback_metadata.failure_lift class=PROGRAMMER_DEFECT failure_family=none witness=test:test_w01_request_failures
        raise TypeError("task readback failure lift context is incomplete or inconsistent")
    # kit:boundary owner=task_readback_metadata.failure_lift class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=task.readback.contract_failure witness=test:test_w01_request_failures
    raise ValueError(str(context["public_message"]))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_line_key(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text.lower().replace("-", "_").replace(" ", "_")


def non_empty_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def runtime_event(event: str, *, status: str | None = None, source: str = "runtime") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event": event,
        "event_source": source,
        "timestamp": utc_now_iso(),
    }
    if status:
        payload["status"] = str(status).strip().lower()
    return payload


def append_runtime_event(
    events: list[Any],
    event: str,
    *,
    status: str | None = None,
    source: str = "runtime",
) -> list[Any]:
    normalized_event = str(event or "").strip()
    if not normalized_event:
        return events
    for item in events:
        if isinstance(item, dict) and str(item.get("event") or "").strip() == normalized_event:
            return events
        if isinstance(item, str) and item.strip() == normalized_event:
            return events
    return [*events, runtime_event(normalized_event, status=status, source=source)]


def ensure_contract_events(
    events: list[Any],
    *,
    line_key: str,
    status: str | None,
    event: str | None = None,
    source: str = "runtime",
) -> list[Any]:
    required_events = LINE_REQUIRED_EVENTS.get(line_key)
    if not required_events:
        return events

    normalized_status = str(status or "").strip().lower()
    normalized_event = str(event or "").strip()
    normalized_event_lower = normalized_event.lower()
    contract_events: list[str] = []

    if normalized_status in {"queued", "scheduled", "pending"} or any(
        marker in normalized_event_lower for marker in ("dispatch", "accepted", "submitted", "queued")
    ):
        accepted_event = LINE_ACCEPTED_EVENT.get(line_key)
        if accepted_event:
            contract_events.append(accepted_event)
        contract_events.append("task_queued")

    if normalized_status in {"running", "started", "active"} or normalized_event_lower == "worker_started":
        contract_events.append("task_queued")
        contract_events.append("worker_started")

    if normalized_status in SUCCESS_TERMINAL_STATUSES or normalized_event_lower in SUCCESS_TERMINAL_STATUSES:
        contract_events.extend(required_events)

    merged = list(events)
    for contract_event in contract_events:
        merged = append_runtime_event(merged, contract_event, status=normalized_status or status, source=source)
    return merged


def extract_runtime_readback_payload(*payloads: Any) -> dict[str, Any]:
    for payload in payloads:
        if not isinstance(payload, Mapping):
            continue
        direct = payload.get("runtime_readback")
        if isinstance(direct, Mapping):
            return dict(direct)
        nested = payload.get("task_readback")
        if isinstance(nested, Mapping):
            return dict(nested)
    return {}


def request_runtime_context(task_request: Any) -> dict[str, Any]:
    if task_request is None:
        return {}
    delivery_info = getattr(task_request, "delivery_info", None)
    if not isinstance(delivery_info, Mapping):
        delivery_info = {}
    return {
        "task_id": non_empty_text(getattr(task_request, "id", None)),
        "worker_name": non_empty_text(getattr(task_request, "hostname", None)),
        "queue": non_empty_text(delivery_info.get("routing_key"))
        or non_empty_text(delivery_info.get("queue"))
        or non_empty_text(delivery_info.get("exchange")),
    }


def build_runtime_readback_payload(
    *,
    line_key: str,
    trace_id: str | None = None,
    run_id: str | None = None,
    task_id: str | None = None,
    worker_name: str | None = None,
    queue: str | None = None,
    status: str | None = "running",
    events: list[Any] | None = None,
    event: str | None = None,
    event_source: str = "runtime",
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=view fact_source=task.runtime_readback witness=test:test_w01_meta",
]:
    normalized_line_key = normalize_line_key(line_key)
    if not normalized_line_key:
        _raise_task_readback_failure(
            _task_readback_failure(
                "line_key is required for runtime readback metadata",
                operation="build_runtime_readback_payload",
            )
        )
    payload: dict[str, Any] = {
        "line_key": normalized_line_key,
        "status": str(status or "running").strip().lower(),
        "events": list(events or []),
    }
    for key, value in {
        "trace_id": trace_id,
        "run_id": run_id,
        "task_id": task_id,
        "worker_name": worker_name,
        "queue": queue,
    }.items():
        text = non_empty_text(value)
        if text:
            payload[key] = text
    if event:
        payload["events"] = append_runtime_event(
            payload["events"],
            event,
            status=payload["status"],
            source=event_source,
        )
    payload["events"] = ensure_contract_events(
        payload["events"],
        line_key=normalized_line_key,
        status=payload["status"],
        event=event,
        source=event_source,
    )
    return payload


def merge_runtime_readback_payload(
    base: Mapping[str, Any] | None,
    runtime_readback: Mapping[str, Any] | None,
    *,
    status: str | None = None,
    event: str | None = None,
    event_source: str = "runtime",
) -> dict[str, Any]:
    payload = dict(base or {})
    metadata = dict(runtime_readback or extract_runtime_readback_payload(payload))
    line_key = normalize_line_key(metadata.get("line_key") or payload.get("line_key"))
    if not line_key:
        return payload

    payload["line_key"] = line_key
    for key in ("task_id", "run_id", "worker_name", "queue", "trace_id"):
        value = non_empty_text(metadata.get(key) or payload.get(key))
        if value:
            payload[key] = value

    resolved_status = str(status or metadata.get("status") or payload.get("status") or "running").strip().lower()
    payload["status"] = resolved_status

    events: list[Any] = []
    for candidate in (payload.get("events"), metadata.get("events")):
        if isinstance(candidate, list):
            for item in candidate:
                if item not in events:
                    events.append(item)
    if event:
        events = append_runtime_event(events, event, status=resolved_status, source=event_source)
    events = ensure_contract_events(
        events,
        line_key=line_key,
        status=resolved_status,
        event=event,
        source=event_source,
    )
    payload["events"] = events
    return payload


def merge_request_runtime_context(
    runtime_readback: Mapping[str, Any] | None,
    task_request: Any,
    *,
    fallback_worker_name: str | None = None,
    fallback_queue: str | None = None,
    status: str = "running",
    event: str = "worker_started",
) -> dict[str, Any]:
    metadata = dict(runtime_readback or {})
    context = request_runtime_context(task_request)
    for key in ("task_id", "worker_name", "queue"):
        value = non_empty_text(context.get(key))
        if value:
            metadata[key] = value
    metadata.setdefault("worker_name", non_empty_text(fallback_worker_name))
    metadata.setdefault("queue", non_empty_text(fallback_queue))
    line_key = normalize_line_key(metadata.get("line_key"))
    if not line_key:
        _raise_task_readback_failure(
            _task_readback_failure(
                "line_key is required for runtime request context",
                operation="merge_request_runtime_context",
            )
        )
    return build_runtime_readback_payload(
        line_key=line_key,
        trace_id=non_empty_text(metadata.get("trace_id")),
        run_id=non_empty_text(metadata.get("run_id") or metadata.get("workflow_run_id")),
        task_id=non_empty_text(metadata.get("task_id")),
        worker_name=non_empty_text(metadata.get("worker_name")),
        queue=non_empty_text(metadata.get("queue")),
        status=status,
        events=list(metadata.get("events") or []) if isinstance(metadata.get("events"), list) else [],
        event=event,
        event_source="celery_worker",
    )
