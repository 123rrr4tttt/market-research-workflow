from __future__ import annotations

import unittest

import pytest

from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore

pytestmark = pytest.mark.unit


class AgentSessionServiceUnitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = AgentSessionService(store=InMemoryAgentSessionStore())

    def test_create_session_bootstraps_default_tasks_and_artifacts(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Implement Claude-style agent runtime",
            project_key="proj-a",
        )

        session = bundle["session"]
        tasks = bundle["tasks"]
        artifacts = bundle["artifacts"]
        events = bundle["events"]

        self.assertEqual(session["source"], "user")
        self.assertEqual(session["entrypoint_type"], "chat")
        self.assertEqual([task["phase"] for task in tasks], ["research", "synthesis", "implementation", "verification"])
        self.assertEqual(tasks[0]["status"], "pending")
        self.assertEqual(tasks[1]["status"], "blocked")
        self.assertEqual([item["name"] for item in artifacts], ["memory.md", "scratchpad.md"])
        self.assertEqual(events[0]["event_type"], "session.created")

    def test_claim_and_complete_task_unblocks_dependents(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Run coordinator flow",
        )
        session_id = bundle["session"]["session_id"]
        research_task = bundle["tasks"][0]
        synthesis_task = bundle["tasks"][1]

        claimed = self.service.claim_task(session_id, research_task["task_id"], owner="worker-1")
        self.assertEqual(claimed["status"], "claimed")

        completed = self.service.release_task(
            session_id,
            research_task["task_id"],
            status="completed",
            result_summary="Research finished",
            tool_use_count=4,
            token_usage=1200,
        )
        self.assertEqual(completed["status"], "completed")
        tasks = self.service.list_tasks(session_id)
        by_id = {item["task_id"]: item for item in tasks}
        self.assertEqual(by_id[synthesis_task["task_id"]]["status"], "pending")

    def test_claim_rejects_write_set_conflict(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Conflict flow",
            task_blueprints=[
                {
                    "task_id": "task-a",
                    "subject": "Implementation A",
                    "task_type": "implementation",
                    "phase": "implementation",
                    "write_set": ["file:a.py"],
                },
                {
                    "task_id": "task-b",
                    "subject": "Implementation B",
                    "task_type": "implementation",
                    "phase": "implementation",
                    "write_set": ["file:a.py"],
                },
            ],
        )
        session_id = bundle["session"]["session_id"]
        self.service.claim_task(session_id, "task-a", owner="worker-a")
        with self.assertRaises(RuntimeError):
            self.service.claim_task(session_id, "task-b", owner="worker-b")

    def test_retry_task_resets_downstream_dependents(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Retry flow",
        )
        session_id = bundle["session"]["session_id"]
        research_task = bundle["tasks"][0]["task_id"]
        synthesis_task = bundle["tasks"][1]["task_id"]

        self.service.release_task(session_id, research_task, status="completed", result_summary="ok")
        self.service.release_task(session_id, synthesis_task, status="completed", result_summary="ok")

        retried = self.service.retry_task(session_id, research_task)
        self.assertEqual(retried["status"], "pending")
        tasks = {item["task_id"]: item for item in self.service.list_tasks(session_id)}
        self.assertEqual(tasks[synthesis_task]["status"], "blocked")

    def test_persist_and_resolve_approval(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Approval flow",
        )
        session_id = bundle["session"]["session_id"]
        task_id = bundle["tasks"][0]["task_id"]

        created = self.service.create_or_update_approval(
            approval_id="approval-1",
            binding_payload={"argv": ["cmd"], "cwd": "/workspace", "env": {}},
            requester_session_id=session_id,
            requester_task_id=task_id,
            requester_actor="user_facing_assistant",
            expires_at=None,
            status="pending",
            audit_log=[{"action": "requested"}],
        )
        self.assertEqual(created["status"], "pending")

        resolved = self.service.resolve_approval("approval-1", approved_by="tester")
        self.assertEqual(resolved["status"], "approved")
        approvals = self.service.list_approvals(session_id=session_id)
        self.assertEqual(len(approvals), 1)

    def test_request_approval_creates_approval_wait_and_unblocks_on_approve(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Approval wait flow",
            task_blueprints=[
                {
                    "task_id": "impl-standalone",
                    "subject": "Implementation",
                    "task_type": "implementation",
                    "phase": "implementation",
                    "write_set": ["file:a.py"],
                }
            ],
        )
        session_id = bundle["session"]["session_id"]
        implementation_task = bundle["tasks"][0]["task_id"]

        approval = self.service.request_approval(
            session_id=session_id,
            task_id=implementation_task,
            requester_actor="ops_panel",
            binding_payload={"argv": ["deploy"], "cwd": "/workspace"},
            metadata={"force_approval": True},
        )
        self.assertEqual(approval["status"], "pending")

        tasks = {item["task_id"]: item for item in self.service.list_tasks(session_id)}
        approval_wait = next(item for item in tasks.values() if item["task_type"] == "approval_wait")
        self.assertEqual(tasks[implementation_task]["status"], "blocked")
        self.assertEqual(approval_wait["status"], "in_progress")

        self.service.resolve_approval(approval["approval_id"], approved_by="reviewer", approved=True)
        tasks = {item["task_id"]: item for item in self.service.list_tasks(session_id)}
        self.assertEqual(tasks[approval_wait["task_id"]]["status"], "completed")
        self.assertEqual(tasks[implementation_task]["status"], "pending")

    def test_reclaim_expired_tasks_marks_task_expired(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Lease expiry flow",
        )
        session_id = bundle["session"]["session_id"]
        research_task = bundle["tasks"][0]["task_id"]
        self.service.claim_task(session_id, research_task, owner="worker-a", lease_seconds=30)
        self.service.store.update_task(session_id, research_task, {"lease_until": "2000-01-01T00:00:00+00:00"})

        reclaimed = self.service.reclaim_expired_tasks(session_id)
        self.assertEqual(len(reclaimed), 1)
        self.assertEqual(reclaimed[0]["status"], "expired")

    def test_coordinator_pass_completes_synthesis_and_creates_messages(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Coordinator flow",
        )
        session_id = bundle["session"]["session_id"]
        research_task = bundle["tasks"][0]["task_id"]
        self.service.release_task(session_id, research_task, status="completed", result_summary="Research done")

        result = self.service.run_coordinator_pass(session_id)
        actions = [item["action"] for item in result["decisions"]]
        self.assertIn("synthesis_completed", actions)
        self.assertIn("dispatch_worker", actions)
        messages = self.service.list_messages(session_id)
        self.assertTrue(any(str(item.get("actor")) == "coordinator" for item in messages))
        artifacts = self.service.list_artifacts(session_id)
        self.assertTrue(any(item["name"] == "coordinator.spec.json" for item in artifacts))

    def test_project_agent_batch_compat_creates_session_bundle(self):
        bundle = self.service.project_agent_batch_compat(
            command="search ai terminals last 7 days top 5",
            project_key="proj-nl",
            request_payload={"dry_run": False},
            loop_result={
                "parsed": {"channel": "search.market"},
                "plan": {
                    "tasks": [
                        {
                            "channel": "search.market",
                            "query_terms": ["ai terminals"],
                            "max_items": 5,
                        }
                    ],
                    "search_brief": {"summary": "brief"},
                },
                "submit": {"job_id": "abj-1", "accepted_count": 1},
            },
        )

        self.assertTrue(bundle["session"]["compat_mode"])
        self.assertEqual(bundle["session"]["compat_job_id"], "abj-1")
        artifact_names = [item["name"] for item in bundle["artifacts"]]
        self.assertIn("compat.loop_result.json", artifact_names)
        self.assertIn("search_brief.json", artifact_names)


if __name__ == "__main__":
    unittest.main()
