from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.mocked]


class _FakeResult:
    def __init__(self, *, scalars_value=None, scalar_value=None, all_value=None):
        self._scalars_value = scalars_value
        self._scalar_value = scalar_value
        self._all_value = all_value

    def scalars(self):
        return SimpleNamespace(all=lambda: self._scalars_value)

    def scalar(self):
        return self._scalar_value

    def all(self):
        return self._all_value


class _FakeListSession:
    def execute(self, _query):
        # /process/list only queries running EtlJobRun rows for DB fallback.
        return _FakeResult(scalars_value=[])


class _FakeHistorySession:
    def __init__(self, jobs: list[SimpleNamespace], status_rows: list[SimpleNamespace]):
        self._jobs = jobs
        self._status_rows = status_rows
        self._execute_count = 0

    def execute(self, _query):
        self._execute_count += 1
        if self._execute_count == 1:
            return _FakeResult(scalars_value=self._jobs)
        if self._execute_count == 2:
            return _FakeResult(scalar_value=len(self._jobs))
        if self._execute_count == 3:
            return _FakeResult(all_value=self._status_rows)
        raise AssertionError(f"Unexpected history execute call: {self._execute_count}")


class _FakeSessionLocal:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb):
        return False


def test_process_list_stats_history_consistency_semantics(
    core_business_client,
    contract_headers: dict[str, str],
) -> None:
    now = datetime(2026, 3, 1, 12, 0, 0)
    history_jobs = [
        SimpleNamespace(
            id=101,
            job_type="policy_ingest",
            status="running",
            params={"state": "CA"},
            started_at=now - timedelta(minutes=10),
            finished_at=None,
            error=None,
        ),
        SimpleNamespace(
            id=102,
            job_type="market_ingest",
            status="running",
            params={"market": "us"},
            started_at=now - timedelta(minutes=5),
            finished_at=None,
            error=None,
        ),
        SimpleNamespace(
            id=103,
            job_type="policy_ingest",
            status="completed",
            params={"state": "NY"},
            started_at=now - timedelta(hours=2),
            finished_at=now - timedelta(hours=1, minutes=30),
            error=None,
        ),
        SimpleNamespace(
            id=104,
            job_type="source_sync",
            status="failed",
            params={"source": "manual"},
            started_at=now - timedelta(hours=1),
            finished_at=now - timedelta(minutes=50),
            error="upstream timeout",
        ),
    ]
    history_status_rows = [
        SimpleNamespace(status="running", count=2),
        SimpleNamespace(status="completed", count=1),
        SimpleNamespace(status="failed", count=1),
    ]

    inspect = SimpleNamespace(
        active=lambda: {
            "worker-a": [
                {"id": "a1", "name": "task.alpha", "args": [], "kwargs": {}},
                {"id": "a2", "name": "task.beta", "args": [], "kwargs": {}},
            ]
        },
        scheduled=lambda: {
            "worker-a": [
                {
                    "request": {
                        "id": "s1",
                        "task": "task.gamma",
                        "args": [],
                        "kwargs": {},
                    }
                }
            ]
        },
        reserved=lambda: {
            "worker-b": [
                {"id": "r1", "name": "task.delta", "args": [], "kwargs": {}},
                {"id": "r2", "name": "task.epsilon", "args": [], "kwargs": {}},
            ]
        },
        registered=lambda: {
            "worker-a": ["task.alpha", "task.beta", "task.gamma"],
            "worker-b": ["task.delta", "task.epsilon"],
        },
    )

    with (
        patch("app.api.process.celery_app.control.inspect", return_value=inspect),
        patch(
            "app.api.process.SessionLocal",
            side_effect=[
                _FakeSessionLocal(_FakeListSession()),
                _FakeSessionLocal(_FakeHistorySession(history_jobs, history_status_rows)),
            ],
        ),
    ):
        list_resp = core_business_client.get("/api/v1/process/list?limit=50", headers=contract_headers)
        stats_resp = core_business_client.get("/api/v1/process/stats", headers=contract_headers)
        history_resp = core_business_client.get("/api/v1/process/history?limit=50", headers=contract_headers)

    assert list_resp.status_code == 200, list_resp.text
    assert stats_resp.status_code == 200, stats_resp.text
    assert history_resp.status_code == 200, history_resp.text

    list_body = list_resp.json()
    stats_body = stats_resp.json()
    history_body = history_resp.json()

    assert list_body["status"] == "ok"
    assert stats_body["status"] == "ok"
    assert history_body["status"] == "ok"

    list_data = list_body["data"]
    stats_data = stats_body["data"]
    history_data = history_body["data"]

    list_stats = list_data["stats"]
    list_tasks = list_data["tasks"]

    list_active = sum(1 for t in list_tasks if t["status"] == "active")
    list_pending_or_reserved = sum(1 for t in list_tasks if t["status"] in {"pending", "reserved"})

    # Consistency across /list and /stats count semantics.
    assert list_stats["total_tasks"] == stats_data["total_running"]
    assert list_stats["active_tasks"] == stats_data["active_tasks"] == list_active
    assert list_stats["pending_tasks"] == list_pending_or_reserved
    assert list_stats["pending_tasks"] == stats_data["scheduled_tasks"] + stats_data["reserved_tasks"]

    # Status mapping semantics: list.active reflects runtime running tasks in history.
    assert history_data["status_stats"]["running"] == list_active
    assert set(history_data["status_stats"].keys()) == {"running", "completed", "failed"}
    assert history_data["total"] == sum(history_data["status_stats"].values())
