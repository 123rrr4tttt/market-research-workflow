from __future__ import annotations

import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

pytestmark = pytest.mark.integration

try:
    from fastapi.testclient import TestClient

    from app import main as main_module
    from app.main import app as backend_app
    from app.services.workflow_graph.handoff_store import handoff_store
    from app.services.workflow_graph.store import InMemoryHistoricalWorkflowRunReader
    from app.successor_runtime.runtime.ports import ProjectScopeRef

    _IMPORT_ERROR = None
except Exception as exc:  # noqa: BLE001
    _IMPORT_ERROR = exc


PROJECT_KEY = "proj-test"
_ACTOR_TOKEN = "test-batch-token"


@contextmanager
def _trusted_codex_actor():
    with (
        patch.object(main_module.settings, "codex_auth_enabled", True),
        patch.object(main_module, "_parse_codex_auth_tokens", return_value={_ACTOR_TOKEN}),
    ):
        yield


def _project_scope() -> ProjectScopeRef:
    return ProjectScopeRef(
        project_key=PROJECT_KEY,
        resolved_schema="project_proj_test",
        project_registry_revision=1,
        incarnation="scope-1",
        scope_digest="a" * 64,
    )


def _fake_submit_dispatch(*, run_id: str, **kwargs) -> tuple[str, tuple[str, ...]]:
    return (run_id, ("work-1",))


def _handoff_event(*, run_id: str, seq: int, event_type: str, payload: dict) -> dict:
    return {
        "event_id": f"{run_id}:{seq}",
        "event_type": event_type,
        "project_key": None,
        "session_id": None,
        "run_id": run_id,
        "trace_id": f"workflow_graph.{run_id}",
        "created_at": "2026-10-07T00:00:00+00:00",
        "seq": seq,
        "ts": "2026-10-07T00:00:00+00:00",
        "type": event_type,
        "node_id": None,
        "payload": payload,
    }


def _handoff_payload(*, run_id: str, handoff_id: str) -> dict:
    return {
        "run_id": run_id,
        "handoff_id": handoff_id,
        "contract_version": "workflow_graph.handoff.v1",
        "handoff_mode": "pull_prepared_evidence",
        "producer": "workflow_graph.backend_bridge",
        "consumer": "llm_report.generate",
        "evidence_pack": {},
    }


def _handoff_snapshot(*, run_id: str, handoff_id: str) -> dict:
    payload = _handoff_payload(run_id=run_id, handoff_id=handoff_id)
    return {
        "run": {
            "run_id": run_id,
            "status": "succeeded",
            "created_at": "2026-10-07T00:00:00+00:00",
            "updated_at": "2026-10-07T00:00:00+00:00",
            "node_statuses": {},
            "metadata": {"workflow_id": "g1", "project_key": PROJECT_KEY},
        },
        "events": [
            _handoff_event(run_id=run_id, seq=1, event_type="handoff.persisted", payload=payload),
        ],
        "results": {},
    }


class AgentBatchWorkflowClosureIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if _IMPORT_ERROR is not None:
            raise unittest.SkipTest(
                "agent batch workflow closure integration tests require backend dependencies: "
                f"{_IMPORT_ERROR}"
            )
        cls.client = TestClient(backend_app)
        cls.headers = {
            "Authorization": f"Bearer {_ACTOR_TOKEN}",
            "X-Project-Key": PROJECT_KEY,
            "X-Request-Id": "agent-batch-workflow-closure",
        }

    def test_agent_batch_to_workflow_handoff_replay_closure(self):
        submit_payload = {
            "project_key": PROJECT_KEY,
            "batch": {
                "jobs": [
                    {
                        "item_id": "item-1",
                        "item_key": "source-a",
                    }
                ]
            },
        }
        with (
            _trusted_codex_actor(),
            patch("app.api.agent_batch.engine", MagicMock()),
            patch(
                "app.api.agent_batch.ServerProjectScopeResolver.resolve",
                return_value=_project_scope(),
            ),
            patch(
                "app.api.agent_batch.dispatch_submit_run",
                side_effect=_fake_submit_dispatch,
            ) as submit_mock,
        ):
            submit_resp = self.client.post(
                "/api/v1/agent-batch/jobs", json=submit_payload, headers=self.headers
            )

        self.assertEqual(submit_resp.status_code, 200)
        submit_data = submit_resp.json()["data"]
        self.assertEqual(submit_data["accepted_count"], 1)
        self.assertEqual(len(submit_data["accepted_job_items"]), 1)
        job_id = submit_data["job_id"]
        self.assertTrue(submit_data["accepted_job_items"][0]["dispatch_id"].startswith(job_id))

        # The batch dispatch is one installed business_wait Program/Runtime run; the
        # actor must come from the verified host auth path, never from the payload.
        submit_mock.assert_called_once()
        dispatch_kwargs = submit_mock.call_args.kwargs
        self.assertEqual(dispatch_kwargs["run_id"], job_id)
        self.assertEqual(dispatch_kwargs["project_key"], PROJECT_KEY)
        self.assertTrue(dispatch_kwargs["actor_id"].startswith("actor:codex-token:"))
        self.assertEqual(dispatch_kwargs["payloads"][0].item.item_key, "source-a")

        reader = InMemoryHistoricalWorkflowRunReader(
            {job_id: _handoff_snapshot(run_id=job_id, handoff_id="h-1")}
        )
        with (
            _trusted_codex_actor(),
            patch.object(handoff_store, "_reader", reader),
        ):
            handoff_list_resp = self.client.get(
                f"/api/v1/agent-batch/jobs/{job_id}/workflow-handoffs",
                headers=self.headers,
            )

            self.assertEqual(handoff_list_resp.status_code, 200)
            handoff_list_data = handoff_list_resp.json()["data"]
            self.assertEqual(handoff_list_data["runs_total"], 1)
            self.assertEqual(handoff_list_data["handoffs_total"], 1)
            self.assertEqual(handoff_list_data["items"][0]["run_id"], job_id)
            replay_path = handoff_list_data["items"][0]["replay_entry_map"]["h-1"]["workflow_graph"]
            self.assertEqual(
                replay_path,
                f"/api/v1/workflow-graph/runs/{job_id}/handoff/h-1/replay?source=historical",
            )

            replay_resp = self.client.get(replay_path, headers=self.headers)

        self.assertEqual(replay_resp.status_code, 200)
        replay_data = replay_resp.json()["data"]
        self.assertEqual(replay_data["handoff_id"], "h-1")
        self.assertEqual(replay_data["run_id"], job_id)
        self.assertEqual(replay_data["result"]["handoff_id"], "h-1")
        self.assertTrue(replay_data["read_only"])


if __name__ == "__main__":
    unittest.main()
