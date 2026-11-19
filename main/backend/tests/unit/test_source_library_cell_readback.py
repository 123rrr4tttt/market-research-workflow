from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
from app.services.agent_core.registry import CoreToolRegistry
from app.services.agent_core.tool_contribution import register_project_tool_contributions
from app.services.agent_runtime.read_only_tools import read_only_project_tool_sources
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore


TASK_ID = "a92e5936-aa84-41eb-a2cd-049bc019c3b6"
PROJECT_KEY = "hk_water_investigation"
ITEM_KEY = "water.handler"
SESSION_ID = "as-test"


class _PendingAsyncResult:
    status = "PENDING"

    def ready(self) -> bool:
        return False


class _SuccessAsyncResult:
    status = "SUCCESS"
    result: dict[str, Any] = {}

    def ready(self) -> bool:
        return True

    def successful(self) -> bool:
        return True


class _FailureAsyncResult:
    status = "FAILURE"
    result = RuntimeError("adapter unavailable")

    def ready(self) -> bool:
        return True

    def successful(self) -> bool:
        return False


def _service_with_dispatch(*, artifact: bool = True) -> AgentSessionService:
    service = AgentSessionService(store=InMemoryAgentSessionStore())
    session = service.create_session(
        source="user", entrypoint_type="interactive_agent", goal="read dispatch"
    )
    assert isinstance(session, dict)
    global SESSION_ID
    SESSION_ID = str(session["session"]["session_id"])
    if artifact:
        stored = service.store.upsert_artifact(
            {
                "session_id": SESSION_ID,
                "name": "ingest.source_library_dispatches.json",
                "artifact_type": "source_library_dispatch_state",
                "metadata": {"project_key": PROJECT_KEY},
                "content_json": {
                    "contract_version": "ingest.source_library.dispatch_state.v1",
                    "session_id": SESSION_ID,
                    "project_key": PROJECT_KEY,
                    "dispatches": [
                        {
                            "session_id": SESSION_ID,
                            "project_key": PROJECT_KEY,
                            "items": [
                                {
                                    "item_key": ITEM_KEY,
                                    "task_id": TASK_ID,
                                    "skill_id": "ingest.dispatch.source_library_item",
                                }
                            ],
                        }
                    ],
                },
            }
        )
        assert isinstance(stored, dict)
    return service


def _execute(
    service: AgentSessionService,
    arguments: dict[str, Any] | None = None,
    *,
    project_key: str = PROJECT_KEY,
):
    sources = read_only_project_tool_sources(
        service=service,
        source_library_lister=lambda _project: [],
        structured_data_searcher=lambda **_arguments: {},
    )
    registry = CoreToolRegistry()
    assert register_project_tool_contributions(registry, sources) is None
    return registry.execute_tool(
        tool_call=CoreToolCall(
            call_id="readback-call",
            tool_name="ingest.status.read",
            arguments=arguments or {},
        ),
        request=AgentCoreRequest(
            message="read task",
            session_id=SESSION_ID,
            project_key=project_key,
        ),
        emit=lambda _event: None,
    )


def _terminal_payload() -> dict[str, Any]:
    return {
        "terminal_output": {
            "contract_version": "source_library.terminal_output.v1",
            "status": "ok",
            "source_mode": "site_search",
            "item": {"item_key": ITEM_KEY},
            "request": {"project_key": PROJECT_KEY},
            "results": {
                "records": [
                    {
                        "record_id": "record-1",
                        "url": "https://example.org/source",
                        "title": "Observed source",
                        "content_text": "x" * 4200,
                    }
                ],
                "stats": {"records": 1, "errors": 0},
            },
            "errors": [],
        },
        "result": {
            "execution_request": {"project_key": PROJECT_KEY, "item_key": ITEM_KEY},
            "candidate_pipeline": {
                "detail_fetch": {"enabled": True, "fetch_target_count": 1},
                "search_route": {"service_chain": ["primary", "fallback", "slow_lane"]},
                "query_contract": {
                    "statuses": ["needs_exploration"],
                    "reason_codes": ["query_contract_not_verified"],
                    "discovery_budget": {"remaining_requests": 3},
                    "exploration_requests": [
                        {
                            "method": "GET",
                            "source_url": "https://example.org/search?q={{q}}",
                            "required_tools": ["source.web.search"],
                            "params": {"q": "water"},
                        }
                    ],
                },
            },
        },
    }


def test_terminal_dispatch_readback_preserves_records_and_query_contract() -> None:
    service = _service_with_dispatch()
    async_result = _SuccessAsyncResult()
    async_result.result = _terminal_payload()
    with (
        patch("app.services.job_logger.list_jobs", return_value=[]),
        patch("app.celery_app.celery_app.AsyncResult", return_value=async_result) as async_result_mock,
    ):
        response = _execute(service, {"task_id": TASK_ID})

    assert response.status == "completed"
    assert async_result_mock.call_args.args == (TASK_ID,)
    tasks = response.structured_content["result"]["dispatched_tasks"]
    assert len(tasks) == 1
    task = tasks[0]
    assert task["task_id"] == TASK_ID
    assert task["state"] == "SUCCESS"
    assert task["status"] == "completed"
    assert task["successful"] is True
    terminal = task["terminal_output"]
    record = terminal["results"]["records"][0]
    assert record["url"] == "https://example.org/source"
    assert len(record["content_text"]) == 4000
    assert record["content_text_truncated"] is True
    query_contract = terminal["candidate_pipeline"]["query_contract"]
    assert query_contract["statuses"] == ["needs_exploration"]
    assert query_contract["discovery_budget"] == {"remaining_requests": 3}
    request = query_contract["exploration_requests"][0]
    assert request["source_url"] == "https://example.org/search?q={{q}}"
    assert request["required_tools"] == ["source.web.search"]
    assert request["params"] == {"q": "water"}


@pytest.mark.parametrize(
    ("arguments", "project_key"),
    [
        ({"task_id": "foreign-task"}, PROJECT_KEY),
        ({"task_id": TASK_ID}, "other_project"),
    ],
)
def test_unauthorized_task_never_touches_backend(arguments: dict[str, Any], project_key: str) -> None:
    service = _service_with_dispatch()
    with (
        patch("app.services.job_logger.list_jobs", return_value=[]),
        patch(
            "app.celery_app.celery_app.AsyncResult",
            side_effect=AssertionError("Celery must not be called"),
        ),
    ):
        response = _execute(service, arguments, project_key=project_key)

    assert response.status == "failed"
    assert response.error["type"] == "task_not_in_session"
    assert response.structured_content["result"]["dispatched_tasks"] == []


def test_more_than_five_explicit_tasks_is_invalid_before_backend() -> None:
    service = _service_with_dispatch()
    with patch(
        "app.celery_app.celery_app.AsyncResult",
        side_effect=AssertionError("Celery must not be called"),
    ):
        response = _execute(service, {"task_id": [str(index) for index in range(6)]})

    assert response.status == "failed"
    assert response.error["type"] == "invalid_task_id"


def test_pending_and_failure_are_not_empty_success() -> None:
    service = _service_with_dispatch()
    with (
        patch("app.services.job_logger.list_jobs", return_value=[]),
        patch("app.celery_app.celery_app.AsyncResult", return_value=_PendingAsyncResult()),
    ):
        pending = _execute(service, {"task_id": TASK_ID})
    assert pending.status == "completed"
    pending_task = pending.structured_content["result"]["dispatched_tasks"][0]
    assert pending_task["state"] == "PENDING"
    assert pending_task["status"] == "unknown"
    assert pending_task["state_observed"] is False
    assert pending_task["ready"] is False
    assert pending_task["successful"] is None
    assert "terminal_output" not in pending_task

    with (
        patch("app.services.job_logger.list_jobs", return_value=[]),
        patch("app.celery_app.celery_app.AsyncResult", return_value=_FailureAsyncResult()),
    ):
        failed = _execute(service, {"task_id": TASK_ID})
    assert failed.status == "completed"
    failed_task = failed.structured_content["result"]["dispatched_tasks"][0]
    assert failed_task["status"] == "failed"
    assert failed_task["successful"] is False
    assert failed_task["error"] == {
        "type": "RuntimeError",
        "message": "adapter unavailable",
    }
    assert "terminal_output" not in failed_task


def test_missing_terminal_output_adapter_error_does_not_become_empty() -> None:
    service = _service_with_dispatch()
    async_result = _SuccessAsyncResult()
    async_result.result = {"project_key": PROJECT_KEY, "item_key": ITEM_KEY}
    with (
        patch("app.services.job_logger.list_jobs", return_value=[]),
        patch("app.celery_app.celery_app.AsyncResult", return_value=async_result),
        patch(
            "app.services.source_library.terminal_output.to_terminal_output_dto",
            side_effect=RuntimeError("adapter unavailable"),
        ),
    ):
        response = _execute(service, {"task_id": TASK_ID})

    assert response.status == "failed"
    assert response.error["type"] == "RuntimeError"
    assert response.error["message"] == "adapter unavailable"
    assert response.structured_content["result"]["dispatched_tasks"] == []


def test_no_dispatch_artifact_preserves_legacy_recent_status() -> None:
    service = _service_with_dispatch(artifact=False)
    jobs = [
        {
            "id": 7,
            "job_type": "source_library_run",
            "status": "running",
            "params": {"item_key": ITEM_KEY, "project_key": PROJECT_KEY},
        }
    ]
    with patch("app.services.job_logger.list_jobs", return_value=jobs):
        response = _execute(service)

    assert response.status == "completed"
    result = response.structured_content["result"]
    assert result["recent_jobs"][0]["id"] == 7
    assert result["dispatched_tasks"] == []


def test_default_readback_uses_latest_authorized_dispatch() -> None:
    service = _service_with_dispatch()
    with (
        patch("app.services.job_logger.list_jobs", return_value=[]),
        patch("app.celery_app.celery_app.AsyncResult", return_value=_PendingAsyncResult()) as async_result_mock,
    ):
        response = _execute(service)

    assert response.status == "completed"
    assert async_result_mock.call_args.args == (TASK_ID,)
    assert response.structured_content["result"]["dispatched_tasks"][0]["task_id"] == TASK_ID


def test_terminal_project_mismatch_is_rejected() -> None:
    service = _service_with_dispatch()
    async_result = _SuccessAsyncResult()
    async_result.result = _terminal_payload()
    async_result.result["terminal_output"]["request"]["project_key"] = "other_project"
    with (
        patch("app.services.job_logger.list_jobs", return_value=[]),
        patch("app.celery_app.celery_app.AsyncResult", return_value=async_result),
    ):
        response = _execute(service, {"task_id": TASK_ID})
    assert response.status == "failed"
    assert response.error["type"] == "ValueError"
    assert response.structured_content["result"]["dispatched_tasks"] == []


def test_explicit_task_readback_is_not_overridden_by_old_job_error() -> None:
    service = _service_with_dispatch()
    async_result = _SuccessAsyncResult()
    async_result.result = _terminal_payload()
    with (
        patch("app.services.job_logger.list_jobs", side_effect=RuntimeError("old job unavailable")),
        patch("app.celery_app.celery_app.AsyncResult", return_value=async_result),
    ):
        response = _execute(service, {"task_id": TASK_ID})
    assert response.status == "completed"
    assert response.error is None
    assert response.structured_content["result"]["dispatched_tasks"][0]["ready"] is True
