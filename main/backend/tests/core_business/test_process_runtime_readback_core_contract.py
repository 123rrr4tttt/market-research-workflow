from __future__ import annotations

import contextlib
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.contract, pytest.mark.mocked]


class _FakeResult:
    def __init__(self, *, scalars_value=None):
        self._scalars_value = scalars_value or []

    def scalars(self):
        return SimpleNamespace(all=lambda: self._scalars_value)


class _RuntimeReadbackSession:
    def __init__(self, jobs: list[SimpleNamespace]):
        self._jobs = jobs

    def execute(self, _query):
        return _FakeResult(scalars_value=self._jobs)

    def get(self, _model, job_id):
        return next((job for job in self._jobs if job.id == job_id), None)


class _RuntimeReadbackSessionLocal:
    def __init__(self, jobs: list[SimpleNamespace]):
        self._jobs = jobs

    def __call__(self):
        session = _RuntimeReadbackSession(self._jobs)
        return _RuntimeReadbackSessionContext(session)


class _RuntimeReadbackSessionContext:
    def __init__(self, session: _RuntimeReadbackSession):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb):
        return False


class _AsyncResultSnapshot:
    status = "STARTED"
    result = None
    info = None

    def ready(self):
        return False


class _AsyncResultFailureSnapshot:
    status = "FAILURE"
    result = RuntimeError("sqlalchemy.exc.MultipleResultsFound: original failure")
    traceback = "Traceback (most recent call last): ..."

    def ready(self):
        return True

    def successful(self):
        return False

    def failed(self):
        return True


class _AsyncResultSuccessSnapshot:
    status = "SUCCESS"
    result = {"inserted": 1, "project_key": "readiness_repair"}
    traceback = None

    def ready(self):
        return True

    def successful(self):
        return True

    def failed(self):
        return False


def _empty_inspect():
    return SimpleNamespace(
        active=lambda: {},
        scheduled=lambda: {},
        reserved=lambda: {},
    )


def test_process_tasks_and_logs_are_explicit_readback_routes_not_dynamic_task_ids(
    core_business_client,
    contract_headers: dict[str, str],
) -> None:
    with (
        patch("app.api.process.celery_app.control.inspect", return_value=_empty_inspect()),
        patch("app.api.process.SessionLocal", new=_RuntimeReadbackSessionLocal([])),
        patch("app.api.process.celery_app.AsyncResult", side_effect=AssertionError("dynamic route used")),
    ):
        tasks_resp = core_business_client.get("/api/v1/process/tasks?line_key=ingest", headers=contract_headers)
        logs_resp = core_business_client.get("/api/v1/process/logs?line_key=ingest", headers=contract_headers)

    assert tasks_resp.status_code == 200, tasks_resp.text
    assert logs_resp.status_code == 200, logs_resp.text

    tasks_body = tasks_resp.json()
    logs_body = logs_resp.json()

    assert tasks_body["status"] == "ok"
    assert logs_body["status"] == "ok"
    assert tasks_body["data"]["line_key"] == "ingest"
    assert logs_body["data"]["line_key"] == "ingest"
    assert tasks_body["data"]["items"] == []
    assert logs_body["data"]["items"] == []
    assert logs_body["data"]["logs"] == []
    assert "task_id" not in tasks_body["data"]
    assert "task_id" not in logs_body["data"]


def test_process_tasks_projects_celery_inspect_worker_readback_fields(
    core_business_client,
    contract_headers: dict[str, str],
) -> None:
    inspect = SimpleNamespace(
        active=lambda: {
            "worker-runtime-a": [
                {
                    "id": "runtime-task-1",
                    "name": "tasks.ingest_pipeline",
                    "kwargs": {
                        "trace_id": "trace-runtime-1",
                        "queue": "queue.ingest",
                    },
                    "delivery_info": {"routing_key": "queue.ingest"},
                }
            ]
        },
        scheduled=lambda: {},
        reserved=lambda: {},
    )

    with (
        patch("app.api.process.celery_app.control.inspect", return_value=inspect),
        patch("app.api.process.SessionLocal", new=_RuntimeReadbackSessionLocal([])),
        patch("app.api.process.celery_app.AsyncResult", return_value=_AsyncResultSnapshot()),
    ):
        resp = core_business_client.get("/api/v1/process/tasks?line_key=ingest&limit=5", headers=contract_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    items = body["data"]["items"]
    assert len(items) == 1
    item = items[0]
    assert item["line_key"] == "ingest"
    assert item["task_id"] == "runtime-task-1"
    assert item["worker_name"] == "worker-runtime-a"
    assert item["queue"] == "queue.ingest"
    assert item["trace_id"] == "trace-runtime-1"
    assert item["status"] == "running"
    assert item["mocked"] is False
    assert item["skipped"] is False
    assert item["readback_path"].startswith("/api/v1/process/tasks")
    assert any(event["event"] == "celery_inspect_active" for event in item["events"])


def test_process_logs_projects_etl_job_run_completion_without_forging_other_lines(
    core_business_client,
    contract_headers: dict[str, str],
) -> None:
    now = datetime(2026, 5, 25, 12, 0, 0)
    jobs = [
        SimpleNamespace(
            id=501,
            job_type="source_library_run",
            status="completed",
            params={
                "line_key": "resource_source_library",
                "task_id": "source-task-1",
                "worker_name": "worker-resource-a",
                "queue": "queue.resource",
                "trace_id": "trace-resource-1",
                "events": [
                    {"event": "resource_action_accepted"},
                    {"event": "worker_started"},
                    {"event": "completed", "status": "completed"},
                ],
            },
            started_at=now - timedelta(minutes=2),
            finished_at=now,
            error=None,
        )
    ]

    with (
        patch("app.api.process.celery_app.control.inspect", return_value=_empty_inspect()),
        patch("app.api.process.SessionLocal", new=_RuntimeReadbackSessionLocal(jobs)),
    ):
        resource_resp = core_business_client.get(
            "/api/v1/process/logs?line_key=resource_source_library&limit=5",
            headers=contract_headers,
        )
        ingest_resp = core_business_client.get(
            "/api/v1/process/logs?line_key=ingest&limit=5",
            headers=contract_headers,
        )

    assert resource_resp.status_code == 200, resource_resp.text
    assert ingest_resp.status_code == 200, ingest_resp.text

    resource_body = resource_resp.json()
    resource_logs = resource_body["data"]["logs"]
    assert len(resource_logs) == 1
    item = resource_logs[0]
    assert item["line_key"] == "resource_source_library"
    assert item["task_id"] == "source-task-1"
    assert item["run_id"] == "501"
    assert item["worker_name"] == "worker-resource-a"
    assert item["queue"] == "queue.resource"
    assert item["trace_id"] == "trace-resource-1"
    assert item["status"] == "completed"
    assert item["mocked"] is False
    assert item["skipped"] is False
    assert item["readback_path"] == "/api/v1/process/db-job-501"
    assert item["readback_endpoint"] == "/api/v1/process/db-job-501"
    assert any(event["event"] == "completed" for event in item["events"])

    ingest_body = ingest_resp.json()
    assert ingest_body["data"]["logs"] == []


def test_process_logs_do_not_forge_terminal_events_from_completed_db_status(
    core_business_client,
    contract_headers: dict[str, str],
) -> None:
    now = datetime(2026, 5, 25, 12, 0, 0)
    jobs = [
        SimpleNamespace(
            id=502,
            job_type="source_library_run",
            status="completed",
            params={
                "line_key": "resource_source_library",
                "task_id": "source-task-2",
                "worker_name": "worker-resource-b",
                "queue": "queue.resource",
                "trace_id": "trace-resource-2",
            },
            started_at=now - timedelta(minutes=2),
            finished_at=now,
            error=None,
        )
    ]

    with (
        patch("app.api.process.celery_app.control.inspect", return_value=_empty_inspect()),
        patch("app.api.process.SessionLocal", new=_RuntimeReadbackSessionLocal(jobs)),
    ):
        resp = core_business_client.get(
            "/api/v1/process/logs?line_key=resource_source_library&limit=5",
            headers=contract_headers,
        )

    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]["logs"][0]
    assert item["status"] == "completed"
    event_names = [event.get("event") for event in item["events"] if isinstance(event, dict)]
    assert "etl_job_started" in event_names
    assert "task_completed" not in event_names


def test_process_tasks_do_not_treat_business_state_as_runtime_status(
    core_business_client,
    contract_headers: dict[str, str],
) -> None:
    now = datetime(2026, 5, 25, 12, 0, 0)
    jobs = [
        SimpleNamespace(
            id=503,
            job_type="policy_ingest",
            status="running",
            params={
                "line_key": "ingest",
                "state": "CA",
                "task_id": "ingest-task-3",
            },
            started_at=now,
            finished_at=None,
            error=None,
        )
    ]

    with (
        patch("app.api.process.celery_app.control.inspect", return_value=_empty_inspect()),
        patch("app.api.process.SessionLocal", new=_RuntimeReadbackSessionLocal(jobs)),
    ):
        resp = core_business_client.get("/api/v1/process/tasks?line_key=ingest&limit=5", headers=contract_headers)

    assert resp.status_code == 200, resp.text
    item = resp.json()["data"]["items"][0]
    assert item["status"] == "running"
    assert item["status"] != "ca"


def test_process_failed_celery_task_result_is_json_compatible(
    core_business_client,
    contract_headers: dict[str, str],
) -> None:
    task_id = "fae77b30-cead-47ec-8d27-46baaf85f2f0"

    with (
        patch("app.api.process.SessionLocal", new=_RuntimeReadbackSessionLocal([])),
        patch("app.api.process.celery_app.AsyncResult", return_value=_AsyncResultFailureSnapshot()),
    ):
        resp = core_business_client.get(
            f"/api/v1/process/{task_id}?project_key=readiness_repair",
            headers=contract_headers,
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    data = body["data"]
    assert data["task_id"] == task_id
    assert data["status"] == "FAILURE"
    assert data["ready"] is True
    assert data["successful"] is False
    assert data["failed"] is True
    assert data["result"] == {
        "message": "sqlalchemy.exc.MultipleResultsFound: original failure",
        "type": "RuntimeError",
    }
    assert data["traceback"] == "Traceback (most recent call last): ..."
    assert data["error_code"] == "TASK_FAILED"


def test_process_async_result_snapshot_projects_failed_result_without_dumping_success_shape():
    from app.api.process import _async_result_snapshot

    with patch("app.api.process.celery_app.AsyncResult", return_value=_AsyncResultFailureSnapshot()):
        failed_snapshot = _async_result_snapshot("failed-task")

    assert failed_snapshot == {
        "status": "failed",
        "result": {
            "message": "sqlalchemy.exc.MultipleResultsFound: original failure",
            "type": "RuntimeError",
        },
        "progress": None,
        "ready": True,
    }

    with patch("app.api.process.celery_app.AsyncResult", return_value=_AsyncResultSuccessSnapshot()):
        success_snapshot = _async_result_snapshot("success-task")

    assert success_snapshot == {
        "status": "completed",
        "result": {"inserted": 1, "project_key": "readiness_repair"},
        "progress": None,
        "ready": True,
    }


def test_process_db_job_exact_endpoint_exposes_runtime_readback_fields_at_data_root(
    core_business_client,
    contract_headers: dict[str, str],
) -> None:
    now = datetime(2026, 5, 25, 12, 0, 0)
    jobs = [
        SimpleNamespace(
            id=504,
            job_type="source_library_run",
            status="completed",
            params={
                "line_key": "resource_source_library",
                "task_id": "source-task-504",
                "worker_name": "worker-resource-exact",
                "queue": "queue.resource",
                "trace_id": "trace-resource-504",
                "events": [
                    {"event": "resource_action_accepted"},
                    {"event": "worker_started"},
                    {"event": "completed", "status": "completed"},
                ],
            },
            started_at=now - timedelta(minutes=3),
            finished_at=now,
            error=None,
            external_provider=None,
            external_job_id=None,
            retry_count=0,
        )
    ]

    with patch("app.api.process.SessionLocal", new=_RuntimeReadbackSessionLocal(jobs)):
        resp = core_business_client.get("/api/v1/process/db-job-504", headers=contract_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    data = body["data"]
    assert data["line_key"] == "resource_source_library"
    assert data["task_id"] == "source-task-504"
    assert data["run_id"] == "504"
    assert data["worker_name"] == "worker-resource-exact"
    assert data["queue"] == "queue.resource"
    assert data["trace_id"] == "trace-resource-504"
    assert data["status"] == "completed"
    assert data["readback_source"] == "etl_job_runs"
    assert data["readback_endpoint"] == "/api/v1/process/db-job-504"
    assert data["readback_path"] == "/api/v1/process/db-job-504"
    assert any(event["event"] == "completed" for event in data["events"])


def test_process_db_job_exact_endpoint_binds_project_key_for_runtime_readback(
    core_business_client,
    contract_headers: dict[str, str],
) -> None:
    now = datetime(2026, 5, 25, 12, 0, 0)
    jobs = [
        SimpleNamespace(
            id=505,
            job_type="writing_llm_action",
            status="completed",
            params={
                "line_key": "writing_knowledge_graph_agent",
                "task_id": "writing-task-505",
                "worker_name": "local.writing_llm_action_service",
                "queue": "local.writing_knowledge_graph_agent",
                "trace_id": "trace-writing-505",
                "events": [
                    {"event": "worker_started"},
                    {"event": "completed", "status": "completed"},
                ],
            },
            started_at=now - timedelta(minutes=1),
            finished_at=now,
            error=None,
            external_provider=None,
            external_job_id=None,
            retry_count=0,
        )
    ]

    with (
        patch("app.api.process.SessionLocal", new=_RuntimeReadbackSessionLocal(jobs)),
        patch("app.api.process.bind_project", return_value=contextlib.nullcontext()) as bind_project,
    ):
        resp = core_business_client.get(
            "/api/v1/process/db-job-505?project_key=demo_proj",
            headers=contract_headers,
        )

    assert resp.status_code == 200, resp.text
    bind_project.assert_called_once_with("demo_proj")
    data = resp.json()["data"]
    assert data["line_key"] == "writing_knowledge_graph_agent"
    assert data["readback_endpoint"] == "/api/v1/process/db-job-505?project_key=demo_proj"
    assert data["readback_path"] == "/api/v1/process/db-job-505?project_key=demo_proj"
