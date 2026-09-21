#!/usr/bin/env python3
"""Exercise the task-owned HTTP -> Celery worker -> Redis result chain."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
import urllib.parse
import urllib.request


def _get(url: str, token: str, headers: dict[str, str] | None = None) -> tuple[int, object]:
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8")
        content_type = response.headers.get("content-type", "")
        return response.status, json.loads(body) if "json" in content_type else body


_IDENTITY_FIELDS = (
    "request_id",
    "run_id",
    "trace_id",
    "project_key",
    "candidate_id",
    "task_id",
    "task_name",
    "worker_name",
    "queue",
)


def _identity_summary(value: object) -> dict[str, object]:
    """Keep correlation identity while excluding arbitrary response payloads."""
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in _IDENTITY_FIELDS if value.get(key) is not None}


def _runtime_summary(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    summary = _identity_summary(value)
    for key in ("status", "line_key"):
        if value.get(key) is not None:
            summary[key] = value[key]
    events = value.get("events")
    if isinstance(events, list):
        summary["events"] = [
            {key: item[key] for key in ("event", "status") if isinstance(item, dict) and item.get(key) is not None}
            for item in events
            if isinstance(item, dict)
        ]
    return summary


def _effect_boundary(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {
        key: value[key]
        for key in ("external_provider_calls", "database_writes", "filesystem_writes", "queue_side_effects")
        if value.get(key) is not None
    }


def _worker_probe_summary(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    result = value.get("result")
    result_summary: dict[str, object] = {}
    if isinstance(result, dict):
        result_summary = _identity_summary(result)
        for key in ("status", "contract_version", "effect_sinks"):
            if result.get(key) is not None:
                result_summary[key] = result[key]
        result_summary["effect_boundary"] = _effect_boundary(result.get("effect_boundary"))
        result_summary["runtime_readback"] = _runtime_summary(result.get("runtime_readback"))
    return {
        key: value[key]
        for key in ("task_id", "ready", "successful")
        if value.get(key) is not None
    } | {"result": result_summary}


def _telemetry_summary(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    summary = {
        key: value[key]
        for key in (
            "source",
            "status",
            "read_status",
            "structured_logs_status",
            "traces_status",
            "record_counts",
            "correlatable_request_ids",
        )
        if value.get(key) is not None
    }
    latest = value.get("latest_record")
    if isinstance(latest, dict):
        latest_summary = _identity_summary(latest)
        for key in ("record_type", "event", "status"):
            if latest.get(key) is not None:
                latest_summary[key] = latest[key]
        summary["latest_record"] = latest_summary
    return summary


def _metrics_summary(lines: list[str]) -> dict[str, object]:
    families = sorted({line.split("{", 1)[0] for line in lines})
    statuses = sorted(
        {
            fragment.split('status="', 1)[1].split('"', 1)[0]
            for line in lines
            if 'status="' in line
            for fragment in [line]
        }
    )
    return {
        "sample_count": len(lines),
        "families": families,
        "statuses": statuses,
        "observed": bool(lines),
    }


def main() -> int:
    base_url = os.getenv("STAGE5_BACKEND_URL", "http://127.0.0.1:18380").rstrip("/")
    token = os.environ["STAGE5_METRICS_TOKEN"]
    request_id = "stage5-live-worker-http-request"
    run_id = f"stage5-worker-run:{request_id}"
    trace_id = "stage5-live-worker-http-trace"
    project_key = "stage5_observability_20260913"
    candidate_id = "stage5:worker-telemetry-probe"
    identity_headers = {
        "X-Request-Id": request_id,
        "X-Trace-Id": trace_id,
        "X-Project-Key": project_key,
    }
    query = urllib.parse.urlencode({"dispatch_worker_probe": "1"})
    dispatch_status, dispatch = _get(
        f"{base_url}/api/v1/health/deep?{query}", token, identity_headers
    )
    readback_status, readback = _get(
        f"{base_url}/api/v1/health/deep", token, identity_headers
    )
    metrics_status, metrics = _get(f"{base_url}/metrics", token)
    metrics_text = str(metrics)
    worker_metric_lines = [
        line
        for line in metrics_text.splitlines()
        if line.startswith((
            "market_api_production_observability_worker_",
            "market_api_production_worker_event_records",
        ))
    ]
    worker_probe = ((dispatch or {}).get("details") or {}).get("worker_probe") or {}
    worker_result = worker_probe.get("result") or {}
    runtime = worker_result.get("runtime_readback") or {}
    telemetry = ((readback or {}).get("details") or {}).get("worker_observability") or {}
    checks = {
        "dispatch_http_200": dispatch_status == 200,
        "dispatch_result_ready": worker_probe.get("ready") is True,
        "dispatch_result_successful": worker_probe.get("successful") is True,
        "task_completed": worker_result.get("status") == "completed",
        "effect_boundary_zero": worker_result.get("effect_boundary")
        == {
            "external_provider_calls": 0,
            "database_writes": 0,
            "filesystem_writes": 0,
            "queue_side_effects": 0,
        },
        "identity_correlated": (
            worker_result.get("request_id") == request_id
            and worker_result.get("run_id") == run_id
            and worker_result.get("trace_id") == trace_id
            and runtime.get("run_id") == run_id
            and runtime.get("trace_id") == trace_id
            and runtime.get("queue") == "celery"
        ),
        "worker_event_observed": telemetry.get("record_counts", {}).get("worker_event", 0) >= 2,
        "structured_log_observed": telemetry.get("structured_logs_status") == "observed",
        "trace_observed": telemetry.get("traces_status") == "observed",
        "request_correlated": request_id in telemetry.get("correlatable_request_ids", []),
        "metrics_http_200": metrics_status == 200,
        "worker_metric_exported": bool(worker_metric_lines),
    }
    payload = {
        "schema": "mrw.stage5.observability.live-worker-chain.v1",
        "status": "PASS_LOCAL_LIVE_WORKER_CHAIN_NOT_AUTHORITY"
        if all(checks.values())
        else "FAIL_LOCAL_LIVE_WORKER_CHAIN",
        "authoritative": False,
        "observed_at": datetime.now(UTC).isoformat(),
        "boundary": {
            "execution": "HTTP deep-health request -> Redis broker -> independent Celery prefork worker -> Redis result backend",
            "task": "task_worker_observability_noop",
            "external_provider_calls": 0,
            "database_writes": 0,
            "filesystem_writes": 0,
            "queue_side_effects": 0,
            "not_claimed": ["production authority", "external OpenTelemetry collector"],
        },
        "identity": {
            "request_id": request_id,
            "run_id": run_id,
            "trace_id": trace_id,
            "project_key": project_key,
            "candidate_id": candidate_id,
            "candidate_identity_redacted": True,
        },
        "checks": checks,
        # Evidence stores only the allowlisted status/identity/observation
        # projection.  The complete HTTP bodies remain process-local.
        "dispatch": {
            "http_status": dispatch_status,
            "health_status": (dispatch or {}).get("status") if isinstance(dispatch, dict) else None,
            "worker_probe": _worker_probe_summary(worker_probe),
        },
        "readback": {
            "http_status": readback_status,
            "health_status": (readback or {}).get("status") if isinstance(readback, dict) else None,
            "worker_observability": _telemetry_summary(telemetry),
        },
        "metrics": {
            "http_status": metrics_status,
            "worker_metric_summary": _metrics_summary(worker_metric_lines),
        },
    }
    output = Path(os.getenv("STAGE5_WORKER_PROBE_OUTPUT", "stage5-evidence/observability/live-worker-chain-result.v1.json"))
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["status"].startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
