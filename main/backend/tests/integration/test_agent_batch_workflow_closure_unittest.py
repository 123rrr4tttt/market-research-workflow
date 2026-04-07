from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient

    from app.main import app as backend_app

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


class _DelayTaskStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None, dict]] = []

    def delay(self, item_key: str, project_key: str | None, override_params: dict, **kwargs):
        self.calls.append((item_key, project_key, dict(override_params or {})))
        return SimpleNamespace(id=f"task-{len(self.calls)}")


class _AsyncResultStub:
    def __init__(self, *, status: str, ready: bool, successful: bool, failed: bool, result):
        self.status = status
        self._ready = ready
        self._successful = successful
        self._failed = failed
        self.result = result

    def ready(self) -> bool:
        return self._ready

    def successful(self) -> bool:
        return self._successful

    def failed(self) -> bool:
        return self._failed


class AgentBatchWorkflowClosureIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(f"agent batch workflow closure integration tests require backend dependencies: {_IMPORT_ERROR}")
        cls.client = TestClient(backend_app)
        cls.headers = {"X-Project-Key": "demo_proj", "X-Request-Id": "agent-batch-workflow-closure"}

    def test_agent_batch_to_workflow_handoff_replay_closure(self):
        delay_stub = _DelayTaskStub()
        submit_payload = {
            "project_key": "proj-test",
            "batch": {
                "jobs": [
                    {
                        "item_id": "item-1",
                        "item_key": "source-a",
                    }
                ]
            },
        }
        with patch("app.api.agent_batch.tasks_module.task_run_source_library_item", delay_stub):
            submit_resp = self.client.post("/api/v1/agent-batch/jobs", json=submit_payload, headers=self.headers)

        self.assertEqual(submit_resp.status_code, 200)
        submit_data = submit_resp.json()["data"]
        self.assertEqual(submit_data["accepted_count"], 1)
        self.assertEqual(len(submit_data["accepted_job_items"]), 1)
        job_id = submit_data["job_id"]
        workflow_run_id = submit_data["accepted_job_items"][0]["workflow_run_id"]

        with patch(
            "app.api.agent_batch.celery_app.AsyncResult",
            return_value=_AsyncResultStub(
                status="SUCCESS",
                ready=True,
                successful=True,
                failed=False,
                result={"run_id": "external-run-id-should-not-override-pinned"},
            ),
        ), patch(
            "app.api.agent_batch.handoff_store.list_handoffs",
            return_value={
                "run_id": workflow_run_id,
                "items": [{"handoff_id": "h-1", "handoff_mode": "pull_prepared_evidence"}],
                "total": 1,
                "contract_version": "workflow_graph.handoff.v1",
            },
        ):
            handoff_list_resp = self.client.get(
                f"/api/v1/agent-batch/jobs/{job_id}/workflow-handoffs",
                headers=self.headers,
            )

        self.assertEqual(handoff_list_resp.status_code, 200)
        handoff_list_data = handoff_list_resp.json()["data"]
        self.assertEqual(handoff_list_data["runs_total"], 1)
        self.assertEqual(handoff_list_data["handoffs_total"], 1)
        self.assertEqual(handoff_list_data["items"][0]["run_id"], workflow_run_id)
        replay_path = handoff_list_data["items"][0]["replay_entry_map"]["h-1"]["workflow_graph"]
        self.assertEqual(replay_path, f"/api/v1/workflow-graph/runs/{workflow_run_id}/handoff/h-1/replay")

        with patch(
            "app.api.workflow_graph.handoff_store.replay_handoff",
            return_value={
                "contract_version": "workflow_graph.handoff.v1",
                "run_id": workflow_run_id,
                "handoff_id": "h-1",
                "events": [{"seq": 1, "type": "handoff.persisted"}],
                "result": {"handoff_id": "h-1"},
            },
        ) as replay_mock:
            replay_resp = self.client.get(replay_path, headers=self.headers)

        self.assertEqual(replay_resp.status_code, 200)
        replay_mock.assert_called_once_with(run_id=workflow_run_id, handoff_id="h-1")
        replay_data = replay_resp.json()["data"]
        self.assertEqual(replay_data["handoff_id"], "h-1")
        self.assertEqual(replay_data["run_id"], workflow_run_id)


if __name__ == "__main__":
    unittest.main()
