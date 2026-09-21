from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
from threading import RLock
from typing import Annotated, Any

from prometheus_client import Gauge


WORKER_TELEMETRY_STREAM = "mrw:production-observability:worker-telemetry"
WORKER_TELEMETRY_CONTRACT_VERSION = "production.observability.worker-telemetry.v1"
WORKER_TELEMETRY_SOURCE = f"redis.stream:{WORKER_TELEMETRY_STREAM}"
WORKER_TELEMETRY_MAXLEN = 1000

_IDENTITY_FIELDS = (
    "request_id",
    "trace_id",
    "run_id",
    "project_key",
    "candidate_id",
    "task_id",
    "task_name",
    "worker_name",
    "queue",
)
_CANDIDATE_KEYS = ("candidate_id", "item_key", "source_id", "candidate_review_key")
_RUN_KEYS = ("run_id", "workflow_run_id")
_WORKER_TELEMETRY_GAUGE = Gauge(
    "market_api_production_worker_observability_status",
    "Current worker/structured-log/trace source observation status",
    ("source", "record_type", "status"),
)
_WORKER_EVENT_GAUGE = Gauge(
    "market_api_production_worker_event_records",
    "Worker telemetry records retained in the bounded local stream",
    ("source", "record_type", "task_name", "worker_name", "queue", "status"),
)
_logger = logging.getLogger("app.production_observability.worker")
_active_tasks: dict[str, dict[str, str]] = {}
_active_lock = RLock()


def _text(value: Any, *, max_length: int = 128) -> str:
    return str(value if value is not None else "").strip()[:max_length]


def _identity_from_mapping(value: Mapping[str, Any], output: dict[str, str]) -> None:
    for key in ("request_id", "trace_id", "project_key", "task_id", "worker_name", "queue"):
        text = _text(value.get(key))
        if text:
            output.setdefault(key, text)
    for key in _RUN_KEYS:
        text = _text(value.get(key))
        if text:
            output.setdefault("run_id", text)
    for key in _CANDIDATE_KEYS:
        text = _text(value.get(key))
        if text:
            output.setdefault("candidate_id", text)


def _visit_identity(value: Any, output: dict[str, str], depth: int = 0) -> None:
    if depth > 3:
        return
    if isinstance(value, Mapping):
        _identity_from_mapping(value, output)
        for item in value.values():
            _visit_identity(item, output, depth + 1)
    elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        for item in value:
            _visit_identity(item, output, depth + 1)


def build_worker_telemetry_identity(
    *,
    args: Iterable[Any] = (),
    kwargs: Mapping[str, Any] | None = None,
    task: Any = None,
) -> Annotated[
    dict[str, str],
    "kit:non-authoritative derived_as=view fact_source=args+kwargs+celery_task_request "
    "witness=test:test_identity_uses_allowlist_and_nested_runtime_readback",
]:
    identity: dict[str, str] = {}
    _visit_identity(tuple(args), identity)
    _visit_identity(dict(kwargs or {}), identity)
    request = getattr(task, "request", None)
    _visit_identity({"task_id": getattr(request, "id", None), "worker_name": getattr(request, "hostname", None)}, identity)
    delivery_info = getattr(request, "delivery_info", None)
    if isinstance(delivery_info, Mapping):
        queue = _text(delivery_info.get("routing_key") or delivery_info.get("queue"))
        if queue:
            identity.setdefault("queue", queue)
    task_name = _text(getattr(task, "name", None) or getattr(request, "task", None))
    if task_name:
        identity.setdefault("task_name", task_name)
    return {key: identity[key] for key in _IDENTITY_FIELDS if identity.get(key)}


def _record(
    identity: Mapping[str, Any],
    *,
    record_type: str,
    event: str,
    status: str,
    duration_ms: int | None = None,
) -> dict[str, str]:
    observed_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "contract_version": WORKER_TELEMETRY_CONTRACT_VERSION,
        "record_type": record_type,
        "event": event,
        "status": status,
        "observed_at": observed_at,
        **{key: _text(identity.get(key)) for key in _IDENTITY_FIELDS},
    }
    if duration_ms is not None:
        payload["duration_ms"] = str(max(0, int(duration_ms)))
    digest_input = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["record_id"] = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
    return payload


def _records_for_event(
    identity: Mapping[str, Any],
    *,
    event: str,
    status: str,
    duration_ms: int | None = None,
) -> tuple[dict[str, str], ...]:
    return (
        _record(identity, record_type="worker_event", event=event, status=status, duration_ms=duration_ms),
        _record(identity, record_type="structured_log", event=f"worker_{event}", status=status, duration_ms=duration_ms),
        _record(identity, record_type="trace", event=f"worker.{event}", status=status, duration_ms=duration_ms),
    )


def _redis_client() -> Any:
    from ..settings.config import settings
    import redis

    return redis.Redis.from_url(
        str(getattr(settings, "redis_url", "") or ""),
        socket_connect_timeout=0.5,
        socket_timeout=0.5,
    )


def publish_worker_telemetry(records: Iterable[Mapping[str, Any]], client: Any = None) -> bool:
    items = tuple(records)
    if not items:
        return True
    try:
        active_client = client if client is not None else _redis_client()
        for item in items:
            _logger.info(
                "structured_worker_telemetry %s",
                json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            )
            active_client.xadd(
                WORKER_TELEMETRY_STREAM,
                {key: value for key, value in item.items() if _text(value)},
                maxlen=WORKER_TELEMETRY_MAXLEN,
                approximate=False,
            )
        return True
    except Exception as exc:  # noqa: BLE001 - telemetry must never mask the task effect
        _logger.warning(
            "event=worker_telemetry_publish_failed error_type=%s record_types=%s",
            type(exc).__name__,
            ",".join(sorted({_text(item.get("record_type")) for item in items})),
        )
        return False


def _started_at_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def install_worker_telemetry(app: Any) -> None:
    from celery import signals

    @signals.task_prerun.connect(weak=False)
    def _record_task_prerun(task=None, args=None, kwargs=None, **_unused: Any) -> None:
        identity = build_worker_telemetry_identity(args=args or (), kwargs=kwargs or {}, task=task)
        task_id = identity.get("task_id")
        if task_id:
            with _active_lock:
                _active_tasks[task_id] = {**identity, "_started_at_ms": str(_started_at_ms())}
        publish_worker_telemetry(_records_for_event(identity, event="started", status="running"))

    @signals.task_postrun.connect(weak=False)
    def _record_task_postrun(task=None, args=None, kwargs=None, state=None, **_unused: Any) -> None:
        identity = build_worker_telemetry_identity(args=args or (), kwargs=kwargs or {}, task=task)
        task_id = identity.get("task_id")
        started_text: str | None = None
        if task_id:
            with _active_lock:
                prior = _active_tasks.pop(task_id, None)
                if prior:
                    identity = {**prior, **identity}
                    started_text = prior.get("_started_at_ms")
        normalized_state = _text(state).upper()
        status = "succeeded" if normalized_state == "SUCCESS" else "failed" if normalized_state == "FAILURE" else "completed"
        duration_ms = max(0, _started_at_ms() - int(started_text)) if started_text else None
        publish_worker_telemetry(
            _records_for_event(identity, event="terminal", status=status, duration_ms=duration_ms)
        )

    @signals.task_failure.connect(weak=False)
    def _record_task_failure(task=None, args=None, kwargs=None, **_unused: Any) -> None:
        identity = build_worker_telemetry_identity(args=args or (), kwargs=kwargs or {}, task=task)
        publish_worker_telemetry(_records_for_event(identity, event="failed", status="failed"))


@dataclass(frozen=True, slots=True)
class WorkerTelemetrySnapshot:
    source: str
    read_status: str
    records: tuple[dict[str, str], ...]
    read_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        records = tuple(self.records)
        by_type = {
            record_type: tuple(item for item in records if item.get("record_type") == record_type)
            for record_type in ("worker_event", "structured_log", "trace")
        }
        request_ids = {
            item.get("request_id")
            for item in records
            if item.get("request_id") and all(
                any(
                    sibling.get("request_id") == item.get("request_id")
                    and sibling.get("record_type") == record_type
                    for sibling in records
                )
                for record_type in by_type
            )
        }
        latest = records[-1] if records else {}
        source_status = self.read_status
        return {
            "source": self.source,
            "read_status": source_status,
            "read_error": self.read_error,
            "record_counts": {key: len(value) for key, value in by_type.items()},
            "status": "observed" if source_status == "ok" and records else "unknown",
            "structured_logs_status": "observed" if source_status == "ok" and by_type["structured_log"] else "not_observed",
            "traces_status": "observed" if source_status == "ok" and by_type["trace"] else "not_observed",
            "correlatable_request_ids": sorted(request_ids),
            "latest_record": dict(latest) if latest else None,
        }


def read_worker_telemetry_snapshot(client: Any = None) -> WorkerTelemetrySnapshot:
    try:
        active_client = client if client is not None else _redis_client()
        raw_rows = active_client.xrange(
            WORKER_TELEMETRY_STREAM,
            min="-",
            max="+",
            count=WORKER_TELEMETRY_MAXLEN,
        )
    except Exception as exc:  # noqa: BLE001 - metrics/health must report unavailable source
        return WorkerTelemetrySnapshot(
            source=WORKER_TELEMETRY_SOURCE,
            read_status="error",
            records=(),
            read_error=type(exc).__name__,
        )
    records: list[dict[str, str]] = []
    for _stream_id, fields in raw_rows or []:
        if not isinstance(fields, Mapping):
            continue
        normalized_fields: dict[str, Any] = {}
        for raw_key, raw_value in fields.items():
            key = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else str(raw_key)
            normalized_fields[key] = raw_value
        item = {
            key: value.decode("utf-8") if isinstance(value, bytes) else str(value)
            for key, value in normalized_fields.items()
        }
        if item.get("contract_version") == WORKER_TELEMETRY_CONTRACT_VERSION:
            records.append({key: value for key, value in item.items() if _text(value)})
    return WorkerTelemetrySnapshot(
        source=WORKER_TELEMETRY_SOURCE,
        read_status="ok",
        records=tuple(records),
    )


def export_worker_telemetry_metrics(snapshot: WorkerTelemetrySnapshot) -> None:
    source = snapshot.source
    statuses = (
        "observed" if snapshot.read_status == "ok" and snapshot.records else "unknown",
        "not_observed",
        "error" if snapshot.read_status == "error" else "unknown",
    )
    for record_type in ("worker_event", "structured_log", "trace"):
        current = statuses[0] if snapshot.read_status == "ok" and any(
            item.get("record_type") == record_type for item in snapshot.records
        ) else statuses[1 if snapshot.read_status == "ok" else 2]
        for status in ("observed", "not_observed", "error"):
            _WORKER_TELEMETRY_GAUGE.labels(source, record_type, status).set(
                1.0 if status == current else 0.0
            )
    groups: dict[tuple[str, str, str, str, str], int] = {}
    for item in snapshot.records:
        record_type = item.get("record_type") or "unknown"
        key = (
            record_type,
            item.get("task_name") or "unknown",
            item.get("worker_name") or "unknown",
            item.get("queue") or "unknown",
            item.get("status") or "unknown",
        )
        groups[key] = groups.get(key, 0) + 1
    for record_type in ("worker_event", "structured_log", "trace"):
        _WORKER_EVENT_GAUGE.labels(source, record_type, "unknown", "unknown", "unknown", "unknown").set(0.0)
    for (record_type, task_name, worker_name, queue, status), count in groups.items():
        _WORKER_EVENT_GAUGE.labels(
            source, record_type, task_name, worker_name, queue, status
        ).set(float(count))


__all__ = [
    "WORKER_TELEMETRY_CONTRACT_VERSION",
    "WORKER_TELEMETRY_MAXLEN",
    "WORKER_TELEMETRY_SOURCE",
    "WORKER_TELEMETRY_STREAM",
    "WorkerTelemetrySnapshot",
    "build_worker_telemetry_identity",
    "export_worker_telemetry_metrics",
    "install_worker_telemetry",
    "publish_worker_telemetry",
    "read_worker_telemetry_snapshot",
]
