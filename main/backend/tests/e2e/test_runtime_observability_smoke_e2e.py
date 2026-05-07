from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import Mock, patch
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.main import app

pytestmark = pytest.mark.e2e


def test_metrics_endpoint_exposes_request_metrics() -> None:
    with TestClient(app) as client:
        health = client.get("/api/v1/health", headers={"X-Request-Id": "metrics-smoke-1"})
        metrics = client.get("/metrics")

    assert health.status_code == 200
    assert metrics.status_code == 200
    assert "text/plain" in (metrics.headers.get("content-type") or "")
    body = metrics.text
    assert "market_api_requests_total" in body
    assert "market_api_request_latency_seconds" in body


def test_process_stats_runtime_smoke_returns_ok_with_request_context() -> None:
    inspect = SimpleNamespace(
        active=lambda: {"worker-a": [{"id": "t1"}]},
        registered=lambda: {"worker-a": ["task.alpha", "task.beta"]},
        scheduled=lambda: {"worker-a": [{"id": "t2"}]},
        reserved=lambda: {"worker-a": []},
    )

    with TestClient(app) as client:
        with patch("app.api.process.celery_app.control.inspect", return_value=inspect):
            response = client.get(
                "/api/v1/process/stats",
                headers={"X-Project-Key": "demo_proj", "X-Request-Id": "process-stats-smoke-1"},
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["data"]["active_tasks"] == 1
    assert payload["data"]["scheduled_tasks"] == 1
    assert response.headers.get("X-Request-Id") == "process-stats-smoke-1"
    assert response.headers.get("X-Project-Key-Resolved") == "demo_proj"
    assert response.headers.get("X-Project-Key-Source") == "header"


def test_ingest_commodity_metrics_sync_runtime_smoke_returns_ok_with_request_context() -> None:
    fake_result = {"inserted": 1, "updated": 0, "observations": [{"metric": "gold"}]}

    with TestClient(app) as client:
        with patch("app.services.ingest.commodity.ingest_commodity_metrics", return_value=fake_result):
            response = client.post(
                "/api/v1/ingest/commodity/metrics",
                json={"project_key": "demo_proj", "limit": 1, "async_mode": False},
                headers={"X-Project-Key": "demo_proj", "X-Request-Id": "commodity-sync-smoke-1"},
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["data"]["inserted"] == 1
    assert response.headers.get("X-Request-Id") == "commodity-sync-smoke-1"
    assert response.headers.get("X-Project-Key-Resolved") == "demo_proj"
    assert response.headers.get("X-Project-Key-Source") == "header"


def test_ingest_commodity_metrics_async_runtime_smoke_returns_task_with_request_context() -> None:
    fake_task = SimpleNamespace(id="commodity-task-1")
    fake_tasks_module = Mock()
    fake_tasks_module.task_ingest_commodity_metrics.delay.return_value = fake_task

    with TestClient(app) as client:
        with patch("app.api.ingest._tasks_module", return_value=fake_tasks_module):
            response = client.post(
                "/api/v1/ingest/commodity/metrics",
                json={"project_key": "demo_proj", "limit": 2, "async_mode": True},
                headers={"X-Project-Key": "demo_proj", "X-Request-Id": "commodity-async-smoke-1"},
            )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["data"]["task_id"] == "commodity-task-1"
    assert payload["data"]["async"] is True
    assert payload["data"]["status"] == "queued"
    assert response.headers.get("X-Request-Id") == "commodity-async-smoke-1"
    assert response.headers.get("X-Project-Key-Resolved") == "demo_proj"
