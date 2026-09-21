#!/usr/bin/env python3
"""Isolated witness for Contract 13 item 1.

This imports the current process API with bytecode writes disabled by the caller,
uses in-process fakes only, and neither opens a database nor performs network I/O.
It does not edit the source under test.  The proposed after-state is modeled by a
temporary wrapper around the actual projection function.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[3]
PROCESS_PATH = REPO_ROOT / "main/backend/app/api/process.py"
EXPECTED_CONTRACT_SHA256 = "ac1629315b3ae91aa9de59b7ae87da04a5f10c54d643e406d8785a0783071717"
EXPECTED_PROCESS_BEFORE_SHA256 = "790b6cb90086d6ba1171309e572b7e7be4c906db3705170dbd4a12ca7ea16c63"
EXPECTED_PROCESS_AFTER_SHA256 = "5687389bdad57881a0f96543ba32ac4eaaaeef0f7939f8f7e36e16316ed7ee61"
OLD_LINE = "    task_id = _first_runtime_value(_runtime_task_id_from_payload(params, result_payload, progress_payload))\n"
NEW_LINES = (
    "    task_id = _first_runtime_value(\n"
    "        _runtime_task_id_from_payload(params, result_payload, progress_payload),\n"
    "        f\"{_DB_JOB_PREFIX}{job.id}\" if job.id is not None else None,\n"
    "    )\n"
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fake_job(*, task_id: str | None = None) -> SimpleNamespace:
    params: dict[str, object] = {
        "item_key": "handler.cluster.rss",
        "project_key": "demo_proj",
        "handler_allocation": {"handler_used": "crawler_pool"},
        "rejection_breakdown": {"url_policy_low_value_endpoint": 1},
    }
    if task_id is not None:
        params["task_id"] = task_id
    return SimpleNamespace(
        id=7,
        status="running",
        job_type="source_library_run",
        params=params,
        started_at=datetime(2026, 3, 1, 0, 0, 0, tzinfo=timezone.utc),
        error=None,
        external_provider="scrapyd",
        external_job_id="spider-job-77",
        retry_count=1,
    )


def main() -> int:
    import fastapi

    # Import only after repository paths have been established by PYTHONPATH.
    from app.api import process as process_api

    source_bytes = PROCESS_PATH.read_bytes()
    before_sha256 = sha256_bytes(source_bytes)
    assert before_sha256 == EXPECTED_PROCESS_BEFORE_SHA256
    source_text = source_bytes.decode("utf-8")
    assert source_text.count(OLD_LINE) == 1
    candidate_bytes = source_text.replace(OLD_LINE, NEW_LINES, 1).encode("utf-8")
    after_sha256 = sha256_bytes(candidate_bytes)
    assert after_sha256 == EXPECTED_PROCESS_AFTER_SHA256

    signature = inspect.signature(process_api.get_task_info)
    query_default = signature.parameters["project_key"].default
    assert type(query_default).__module__ == "fastapi.params"
    assert type(query_default).__qualname__ == "Query"
    assert repr(query_default) == "Query(None)"
    assert query_default is not None
    assert query_default.default is None
    assert bool(query_default) is True

    missing_job = fake_job()
    explicit_job = fake_job(task_id="provider-task-9")
    actual_task_info_converter = process_api._db_job_to_runtime_task_info

    captured_bind_values: list[object] = []
    direct_omitted_project_keys: list[object] = []
    direct_none_project_keys: list[object] = []
    http_project_keys: list[object] = []

    def capture_project_key(target: list[object]):
        def wrapper(task_id: str, job: object, *, project_key: object = None):
            target.append(project_key)
            return actual_task_info_converter(task_id, job, project_key=project_key)

        return wrapper

    @contextmanager
    def capture_bind(value: object):
        captured_bind_values.append(value)
        yield

    # Actual direct Python call with project_key omitted.  The Query object is
    # truthy, so the function body sends it to bind_project.
    with (
        patch.object(process_api, "bind_project", side_effect=capture_bind),
        patch.object(process_api, "_resolve_db_job", return_value=missing_job),
        patch.object(
            process_api,
            "_db_job_to_runtime_task_info",
            side_effect=capture_project_key(direct_omitted_project_keys),
        ),
    ):
        direct_omitted_response = process_api.get_task_info("db-job-7")
    assert len(captured_bind_values) == 1
    assert captured_bind_values[0] is query_default
    assert direct_omitted_project_keys == [query_default]

    def forbidden_bind(_value: object):
        raise AssertionError("bind_project must not run when project_key is resolved to None")

    # A correct direct-call fixture passes None explicitly.  This fixes fixture
    # invocation only: the actual current overlay still returns task_id=None.
    with (
        patch.object(process_api, "bind_project", side_effect=forbidden_bind),
        patch.object(process_api, "_resolve_db_job", return_value=missing_job),
        patch.object(
            process_api,
            "_db_job_to_runtime_task_info",
            side_effect=capture_project_key(direct_none_project_keys),
        ),
    ):
        direct_none_response = process_api.get_task_info("db-job-7", project_key=None)
    assert direct_none_project_keys == [None]

    # FastAPI's request parser resolves the missing query parameter to None.
    test_app = FastAPI()
    test_app.include_router(process_api.router)
    with (
        patch.object(process_api, "bind_project", side_effect=forbidden_bind),
        patch.object(process_api, "_resolve_db_job", return_value=missing_job),
        patch.object(
            process_api,
            "_db_job_to_runtime_task_info",
            side_effect=capture_project_key(http_project_keys),
        ),
        TestClient(test_app) as client,
    ):
        http_response = client.get("/process/db-job-7")
    assert http_response.status_code == 200
    assert http_project_keys == [None]
    http_body = http_response.json()

    with patch.object(process_api, "_resolve_db_job", return_value=missing_job):
        logs_response = process_api.get_task_logs("db-job-7", tail=50)

    before_missing = process_api._db_job_to_runtime_task_info("db-job-7", missing_job, project_key=None)
    before_explicit = process_api._db_job_to_runtime_task_info("db-job-7", explicit_job, project_key=None)

    actual_projection = process_api._db_job_projection

    def proposed_projection(**kwargs):
        projected = actual_projection(**kwargs)
        if projected is None:
            return None
        job = kwargs["job"]
        return {
            **projected,
            "task_id": process_api._first_runtime_value(
                projected.get("task_id"),
                f"{process_api._DB_JOB_PREFIX}{job.id}" if job.id is not None else None,
            ),
        }

    with patch.object(process_api, "_db_job_projection", side_effect=proposed_projection):
        after_missing = process_api._db_job_to_runtime_task_info("db-job-7", missing_job, project_key=None)
        after_explicit = process_api._db_job_to_runtime_task_info("db-job-7", explicit_job, project_key=None)

    observations = {
        "schema_version": "mrw.stage1.contract13.process_api_witness.v2",
        "isolated": True,
        "database_contacted": False,
        "network_contacted": False,
        "runtime": {
            "python_function": "app.api.process.get_task_info",
            "fastapi_version": fastapi.__version__,
        },
        "source_binding": {
            "path": str(PROCESS_PATH.relative_to(REPO_ROOT)),
            "before_sha256": before_sha256,
            "proposed_after_sha256": after_sha256,
            "replacement_occurrences": 1,
        },
        "query_default": {
            "type": f"{type(query_default).__module__}.{type(query_default).__qualname__}",
            "repr": repr(query_default),
            "str": str(query_default),
            "is_none": query_default is None,
            "truthy": bool(query_default),
            "field_default_type": f"{type(query_default.default).__module__}.{type(query_default.default).__qualname__}",
            "field_default_repr": repr(query_default.default),
            "direct_omitted_bind_argument_is_declared_default": captured_bind_values[0] is query_default,
            "direct_omitted_converter_project_key_type": f"{type(direct_omitted_project_keys[0]).__module__}.{type(direct_omitted_project_keys[0]).__qualname__}",
            "direct_omitted_info_task_id": direct_omitted_response["data"]["task_id"],
            "direct_explicit_none_converter_project_key_is_none": direct_none_project_keys[0] is None,
            "direct_explicit_none_info_task_id": direct_none_response["data"]["task_id"],
            "http_omitted_query_converter_project_key_is_none": http_project_keys[0] is None,
            "http_omitted_query_info_task_id": http_body["data"]["task_id"],
            "interpretation": {
                "direct_python_omitted": "Receives the declared fastapi.params.Query object and, because it is truthy, passes that object to bind_project.",
                "direct_python_explicit_none": "Receives None and does not call bind_project; this is the correct isolated fixture invocation.",
                "fastapi_http_omitted": "FastAPI request parsing resolves the missing query parameter to the Query field default None before invoking the endpoint.",
            },
        },
        "identity_overlay": {
            "before": {
                "missing_payload_projection_task_id": before_missing["task_id"],
                "missing_payload_info_task_id": direct_none_response["data"]["task_id"],
                "missing_payload_logs_task_id": logs_response["data"]["task_id"],
                "explicit_payload_info_task_id": before_explicit["task_id"],
            },
            "proposed_after": {
                "missing_payload_projection_task_id": after_missing["task_id"],
                "missing_payload_info_task_id": after_missing["task_id"],
                "missing_payload_logs_task_id": logs_response["data"]["task_id"],
                "explicit_payload_info_task_id": after_explicit["task_id"],
            },
            "merge_order": "{**task_info, **runtime_projection}; runtime_projection is later and overwrites task_info.task_id.",
            "precedence_rule": "first_non_empty(payload task_id, db-job-{job.id})",
            "fixture_conclusion": "Passing project_key=None repairs the direct-call fixture boundary but leaves current production projection task_id=None; it cannot remove the overlay defect.",
        },
        "assertions": {
            "direct_default_is_query_object": query_default is captured_bind_values[0],
            "fastapi_http_default_is_none": http_project_keys[0] is None,
            "correct_direct_fixture_still_exposes_defect": direct_none_response["data"]["task_id"] is None,
            "before_info_logs_mismatch": direct_none_response["data"]["task_id"] != logs_response["data"]["task_id"],
            "after_missing_payload_identity_consistent": after_missing["task_id"] == logs_response["data"]["task_id"] == "db-job-7",
            "explicit_provider_task_id_precedes_fallback": after_explicit["task_id"] == "provider-task-9",
        },
    }

    assert all(observations["assertions"].values())
    print(json.dumps(observations, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
