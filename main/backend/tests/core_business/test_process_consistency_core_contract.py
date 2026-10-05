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
    def __init__(self, jobs: list[SimpleNamespace] | None = None):
        self._jobs = jobs or []

    def execute(self, _query):
        # /process/list only queries running EtlJobRun rows for DB fallback.
        return _FakeResult(scalars_value=self._jobs)


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
            params={
                "state": "CA",
                "rejected_count": 2,
                "rejection_breakdown": {"content_shell_signature": 2},
            },
            started_at=now - timedelta(minutes=10),
            finished_at=None,
            error=None,
            external_provider=None,
            external_job_id=None,
        ),
        SimpleNamespace(
            id=102,
            job_type="market_ingest",
            status="running",
            params={
                "market": "us",
                "inserted_valid": 3,
                "rejected_count": 1,
                "rejection_breakdown": {"url_policy_low_value_endpoint": 1},
                "handler_allocation": {"handler_used": "crawler_pool"},
            },
            started_at=now - timedelta(minutes=5),
            finished_at=None,
            error=None,
            external_provider=None,
            external_job_id=None,
        ),
        SimpleNamespace(
            id=103,
            job_type="resource_pool",
            status="completed",
            params={"state": "NY", "urls_extracted": 317},
            started_at=now - timedelta(hours=2),
            finished_at=now - timedelta(hours=1, minutes=30),
            error=None,
            external_provider=None,
            external_job_id=None,
        ),
        SimpleNamespace(
            id=104,
            job_type="source_sync",
            status="failed",
            params={"source": "manual"},
            started_at=now - timedelta(hours=1),
            finished_at=now - timedelta(minutes=50),
            error="upstream timeout",
            external_provider=None,
            external_job_id=None,
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

    # Optional quality fields are exposed with stable types.
    for row in history_data["history"]:
        assert "inserted_valid" in row
        assert "rejected_count" in row
        assert "rejection_breakdown" in row
        assert "error_code" in row
        assert "handler_used" in row
        assert "skip_reason" in row
        assert row["inserted_valid"] is None or isinstance(row["inserted_valid"], int)
        assert isinstance(row["rejected_count"], int)
        assert isinstance(row["rejection_breakdown"], dict)
        assert row["error_code"] is None or isinstance(row["error_code"], str)
        assert row["handler_used"] is None or isinstance(row["handler_used"], str)
        assert row["skip_reason"] is None or isinstance(row["skip_reason"], str)

    running_row = next(item for item in history_data["history"] if item["id"] == 102)
    assert running_row["handler_used"] == "crawler_pool"
    assert running_row["skip_reason"] == "url_policy_low_value_endpoint"
    completed_resource_row = next(item for item in history_data["history"] if item["id"] == 103)
    assert completed_resource_row["params"]["urls_extracted"] == 317


def test_process_list_filters_projects_and_deduplicates_celery_db_identity(
    core_business_client,
    contract_headers: dict[str, str],
) -> None:
    now = datetime(2026, 10, 5, 12, 0, 0)
    resource_task_name = "app.services.tasks.task_extract_resource_pool_from_documents"
    inspect = SimpleNamespace(
        active=lambda: {
            "worker-a": [
                {
                    "id": "celery-alpha-1",
                    "name": resource_task_name,
                    "args": ["project_alpha"],
                    "kwargs": {},
                },
                {
                    "id": "celery-beta-1",
                    "name": "task.generic",
                    "args": [],
                    "kwargs": {"project_key": "project_beta"},
                },
                {
                    "id": "celery-unknown-1",
                    "name": "task.unknown",
                    "args": [],
                    "kwargs": {},
                },
            ]
        },
        scheduled=lambda: {},
        reserved=lambda: {
            "worker-a": [
                {
                    "id": "celery-alpha-1",
                    "name": resource_task_name,
                    "args": ["project_alpha"],
                    "kwargs": {},
                }
            ]
        },
        registered=lambda: {"worker-a": [resource_task_name]},
    )
    running_jobs = [
        SimpleNamespace(
            id=910,
            job_type="resource_pool",
            status="running",
            params={
                "project_key": "project_alpha",
                "job_type_full": "resource_pool_extract",
                "task_id": "celery-alpha-1",
                    "worker_name": "worker-a",
            },
            started_at=now,
            finished_at=None,
            error=None,
            external_provider=None,
            external_job_id="celery-alpha-1",
            retry_count=0,
        ),
        SimpleNamespace(
            id=911,
            job_type="resource_pool",
            status="running",
            params={"project_key": "project_beta", "task_id": "celery-beta-1"},
            started_at=now,
            finished_at=None,
            error=None,
            external_provider=None,
            external_job_id="celery-beta-1",
            retry_count=0,
        ),
    ]
    history_status_rows = [SimpleNamespace(status="running", count=2)]

    with (
        patch("app.api.process.celery_app.control.inspect", return_value=inspect),
        patch(
            "app.api.process.SessionLocal",
            side_effect=[
                _FakeSessionLocal(_FakeListSession(running_jobs)),
                _FakeSessionLocal(_FakeHistorySession(running_jobs, history_status_rows)),
            ],
        ),
    ):
        list_resp = core_business_client.get(
            "/api/v1/process/list?project_key=project_alpha&limit=20",
            headers=contract_headers,
        )
        history_resp = core_business_client.get(
            "/api/v1/process/history?project_key=project_alpha&limit=20",
            headers=contract_headers,
        )
        stats_resp = core_business_client.get(
            "/api/v1/process/stats?project_key=project_alpha",
            headers=contract_headers,
        )

    assert list_resp.status_code == 200, list_resp.text
    assert history_resp.status_code == 200, history_resp.text
    assert stats_resp.status_code == 200, stats_resp.text
    tasks = list_resp.json()["data"]["tasks"]
    assert [item["task_id"] for item in tasks] == ["celery-alpha-1"]
    assert tasks[0]["worker"] == "worker-a"
    assert list_resp.json()["data"]["stats"]["total_tasks"] == 1

    history = history_resp.json()["data"]["history"]
    alpha_history = next(item for item in history if item["id"] == 910)
    assert alpha_history["task_id"] == "celery-alpha-1"
    assert alpha_history["task_name"] == "resource_pool_extract"
    assert alpha_history["source"] == "db"
    stats_data = stats_resp.json()["data"]
    assert stats_data["active_tasks"] == 1
    assert stats_data["total_running"] == 1
    assert stats_data["task_count_scope"] == "project"
    assert stats_data["workers_scope"] == "global"


def test_prompt_time_density_priority_contract_fields(core_business_client, contract_headers: dict[str, str]) -> None:
    mocked = [
        {
            "source_domain": "news.example.com",
            "prompt_group_id": "pg-ai",
            "window": "7d",
            "density": 0.2,
            "norm_density": 1.1,
            "dup_ratio": 0.1,
            "collection_priority_score": 0.73,
            "rank": 1,
        }
    ]
    with patch("app.api.stats.query_prompt_time_density_priority", return_value=mocked):
        resp = core_business_client.get(
            "/api/v1/stats/prompt-time-density/priority?candidate_windows=7d&end=2026-03-01",
            headers=contract_headers,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    data = body["data"]
    assert data["total"] == 1
    assert isinstance(data["items"], list)
    row = data["items"][0]
    assert row["rank"] == 1
    assert "collection_priority_score" in row
    assert "norm_density" in row
    assert "dup_ratio" in row


def test_prompt_time_density_priority_invalid_window_returns_422(
    core_business_client,
    contract_headers: dict[str, str],
) -> None:
    resp = core_business_client.get(
        "/api/v1/stats/prompt-time-density/priority?candidate_windows=bad-window",
        headers=contract_headers,
    )

    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "INVALID_INPUT"
