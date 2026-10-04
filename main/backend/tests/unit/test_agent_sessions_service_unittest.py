from __future__ import annotations

import unittest

import pytest
from functorial_kit import Failure

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
        conflict = self.service.claim_task(session_id, "task-b", owner="worker-b")

        self.assertIsInstance(conflict, Failure)
        assert isinstance(conflict, Failure)
        self.assertEqual((conflict.family, conflict.code), ("agent.runtime.failure", "write_set_conflict"))
        self.assertEqual(
            conflict.context,
            {
                "task_id": "task-b",
                "write_set": ["file:a.py"],
                "conflicting_task_id": "task-a",
                "conflicting_write_set": ["file:a.py"],
            },
        )
        task_b = self.service.store.get_task(session_id, "task-b")
        self.assertEqual(task_b["status"], "pending")

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

    def test_retry_task_repeated_call_is_idempotent(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Retry idempotency flow",
        )
        session_id = bundle["session"]["session_id"]
        research_task = bundle["tasks"][0]["task_id"]

        self.service.release_task(session_id, research_task, status="completed", result_summary="ok")
        retried = self.service.retry_task(session_id, research_task)
        event_count = len(self.service.list_events(session_id))
        stored_after_retry = self.service.store.get_task(session_id, research_task)

        repeated = self.service.retry_task(session_id, research_task)

        self.assertEqual(retried["action_status"], "retried")
        self.assertEqual(repeated["status"], "pending")
        self.assertEqual(repeated["action_status"], "already_pending")
        self.assertEqual(len(self.service.list_events(session_id)), event_count)
        self.assertEqual(self.service.store.get_task(session_id, research_task), stored_after_retry)

    def test_export_failure_package_by_task_id_includes_debug_fields(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Failure export flow",
            project_key="proj-failure",
            metadata={"trace_id": "trace-session"},
            task_blueprints=[
                {
                    "task_id": "task-failed",
                    "subject": "Implementation",
                    "task_type": "implementation",
                    "phase": "implementation",
                    "metadata": {"run_id": "run-failed", "trace_id": "trace-task"},
                }
            ],
        )
        session_id = bundle["session"]["session_id"]
        self.service.release_task(
            session_id,
            "task-failed",
            status="failed",
            result_summary="provider timeout",
            result_payload={"error_code": "provider_timeout", "trace_id": "trace-result"},
            activity="provider failed",
        )
        self.service.store.append_event(
            session_id,
            event_type="provider.failed",
            task_id="task-failed",
            payload={"error": "upstream timeout", "trace_id": "trace-event"},
        )

        exported = self.service.export_failure_package(session_id, task_id="task-failed")

        self.assertEqual(exported["export_status"], "ok")
        package = exported["failure_package"]
        self.assertEqual(package["export_schema_version"], "agent_failure_package.v1")
        self.assertEqual(package["session_id"], session_id)
        self.assertEqual(package["task_id"], "task-failed")
        self.assertEqual(package["run_id"], "run-failed")
        self.assertEqual(package["project_key"], "proj-failure")
        self.assertEqual(package["trace_id"], "trace-task")
        self.assertEqual(package["failed_steps"][0]["task_id"], "task-failed")
        self.assertTrue(any(item.get("detail") == "provider_timeout" for item in package["errors"]))
        self.assertEqual(package["retry_hint"]["next_action"], "retry_task")
        self.assertEqual(package["last_event"]["event_type"], "provider.failed")

    def test_export_failure_package_non_failed_task_returns_empty_contract(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Non failed export flow",
            project_key="proj-ok",
        )
        session_id = bundle["session"]["session_id"]
        task_id = bundle["tasks"][0]["task_id"]

        exported = self.service.export_failure_package(session_id, task_id=task_id)

        self.assertEqual(exported["export_status"], "not_failed")
        self.assertEqual(exported["reason_code"], "task_not_failed")
        self.assertIsNone(exported["failure_package"])
        self.assertEqual(exported["empty_package"]["task_id"], task_id)
        self.assertEqual(exported["empty_package"]["project_key"], "proj-ok")

    def test_export_failure_package_by_session_run_id_uses_failed_tasks(self):
        bundle = self.service.create_session(
            source="workflow_graph",
            entrypoint_type="workflow_graph.run",
            goal="Session run failure export",
            project_key="proj-run",
            logical_task_list_key="run-session-1",
            metadata={"workflow_graph": {"run_id": "run-session-1"}},
        )
        session_id = bundle["session"]["session_id"]
        task_id = bundle["tasks"][0]["task_id"]
        self.service.release_task(
            session_id,
            task_id,
            status="failed",
            result_summary="node failed",
            result_payload={"reason_code": "node_failed"},
        )

        exported = self.service.export_failure_package(session_id, run_id="run-session-1")

        self.assertEqual(exported["export_status"], "ok")
        package = exported["failure_package"]
        self.assertEqual(package["run_id"], "run-session-1")
        self.assertEqual(package["task_id"], task_id)
        self.assertEqual(package["failed_steps"][0]["summary"], "node failed")

    def test_export_failure_package_missing_task_returns_not_found_contract(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Missing task export flow",
        )
        session_id = bundle["session"]["session_id"]

        exported = self.service.export_failure_package(session_id, task_id="missing-task")

        self.assertEqual(exported["export_status"], "not_found")
        self.assertEqual(exported["reason_code"], "task_not_found")
        self.assertIsNone(exported["failure_package"])
        self.assertEqual(exported["empty_package"]["task_id"], "missing-task")

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
        self.assertEqual(resolved["action_status"], "resolved")
        approvals = self.service.list_approvals(session_id=session_id)
        self.assertEqual(len(approvals), 1)

    def test_resolve_approval_repeated_approve_is_idempotent(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Approval idempotency flow",
        )
        session_id = bundle["session"]["session_id"]
        task_id = bundle["tasks"][0]["task_id"]
        self.service.create_or_update_approval(
            approval_id="approval-idem-approve",
            binding_payload={"argv": ["cmd"], "cwd": "/workspace", "env": {}},
            requester_session_id=session_id,
            requester_task_id=task_id,
            requester_actor="user_facing_assistant",
            expires_at=None,
            status="pending",
            audit_log=[{"action": "requested"}],
        )

        resolved = self.service.resolve_approval("approval-idem-approve", approved_by="tester", approved=True)
        event_count = len(self.service.list_events(session_id))
        stored_after_resolve = self.service.store.get_approval("approval-idem-approve")

        repeated = self.service.resolve_approval("approval-idem-approve", approved_by="tester-2", approved=True)

        self.assertEqual(resolved["action_status"], "resolved")
        self.assertEqual(repeated["status"], "approved")
        self.assertEqual(repeated["action_status"], "already_final")
        self.assertEqual(repeated["requested_status"], "approved")
        self.assertEqual(len(self.service.list_events(session_id)), event_count)
        self.assertEqual(self.service.store.get_approval("approval-idem-approve"), stored_after_resolve)

    def test_resolve_approval_conflicting_final_decision_is_noop(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Approval conflict flow",
        )
        session_id = bundle["session"]["session_id"]
        task_id = bundle["tasks"][0]["task_id"]
        self.service.create_or_update_approval(
            approval_id="approval-conflict",
            binding_payload={"argv": ["cmd"], "cwd": "/workspace", "env": {}},
            requester_session_id=session_id,
            requester_task_id=task_id,
            requester_actor="user_facing_assistant",
            expires_at=None,
            status="pending",
            audit_log=[{"action": "requested"}],
        )
        self.service.resolve_approval("approval-conflict", approved_by="tester", approved=True)
        event_count = len(self.service.list_events(session_id))
        stored_after_resolve = self.service.store.get_approval("approval-conflict")

        conflicted = self.service.resolve_approval("approval-conflict", approved_by="tester", approved=False)

        self.assertEqual(conflicted["status"], "approved")
        self.assertEqual(conflicted["action_status"], "conflict")
        self.assertEqual(conflicted["requested_status"], "failed")
        self.assertEqual(conflicted["final_status"], "approved")
        self.assertEqual(len(self.service.list_events(session_id)), event_count)
        self.assertEqual(self.service.store.get_approval("approval-conflict"), stored_after_resolve)

    def test_resolve_approval_repeated_reject_is_idempotent(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Approval reject idempotency flow",
        )
        session_id = bundle["session"]["session_id"]
        task_id = bundle["tasks"][0]["task_id"]
        self.service.create_or_update_approval(
            approval_id="approval-idem-reject",
            binding_payload={"argv": ["cmd"], "cwd": "/workspace", "env": {}},
            requester_session_id=session_id,
            requester_task_id=task_id,
            requester_actor="user_facing_assistant",
            expires_at=None,
            status="pending",
            audit_log=[{"action": "requested"}],
        )

        rejected = self.service.resolve_approval("approval-idem-reject", approved_by="tester", approved=False)
        event_count = len(self.service.list_events(session_id))
        stored_after_reject = self.service.store.get_approval("approval-idem-reject")

        repeated = self.service.resolve_approval("approval-idem-reject", approved_by="tester-2", approved=False)

        self.assertEqual(rejected["status"], "failed")
        self.assertEqual(rejected["action_status"], "resolved")
        self.assertEqual(repeated["status"], "failed")
        self.assertEqual(repeated["action_status"], "already_final")
        self.assertEqual(len(self.service.list_events(session_id)), event_count)
        self.assertEqual(self.service.store.get_approval("approval-idem-reject"), stored_after_reject)

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

if __name__ == "__main__":
    unittest.main()
