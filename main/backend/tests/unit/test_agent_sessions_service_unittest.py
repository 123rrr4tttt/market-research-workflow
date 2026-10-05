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

    def _task_blueprint(self, task_id: str, *, task_type: str = "implementation") -> dict:
        return {
            "task_id": task_id,
            "subject": task_type.title(),
            "task_type": task_type,
            "phase": "research" if task_type == "research" else "implementation",
            "execution_mode": "worker",
        }

    def test_create_session_without_blueprints_creates_no_tasks_or_artifacts(self):
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
        self.assertEqual(tasks, [])
        self.assertIsNone(session["root_task_id"])
        self.assertEqual(artifacts, [])
        self.assertEqual(events[0]["event_type"], "session.created")

    def test_explicit_task_blueprints_are_preserved(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Explicit owner tasks",
            task_blueprints=[
                self._task_blueprint("task-a", task_type="research"),
                {**self._task_blueprint("task-b"), "blocked_by_refs": ["prev"]},
            ],
        )

        self.assertEqual(bundle["session"]["root_task_id"], "task-a")
        self.assertEqual([task["status"] for task in bundle["tasks"]], ["pending", "blocked"])

    def test_new_coordinator_blueprints_are_rejected_before_writes(self):
        retired = {**self._task_blueprint("retired-task"), "execution_mode": " Coordinator "}
        result = self.service.create_session(
            source="user", entrypoint_type="chat", goal="Reject retired mode",
            task_blueprints=[retired],
        )
        self.assertIsInstance(result, Failure)
        self.assertEqual(result.code, "execution_mode_invalid")
        self.assertEqual(self.service.list_sessions(), [])

        bundle = self.service.create_session(
            source="user", entrypoint_type="chat", goal="Append current tasks",
            task_blueprints=[self._task_blueprint("existing-task")],
        )
        session_id = bundle["session"]["session_id"]
        before = self.service.get_session_bundle(session_id)
        result = self.service.append_task_blueprints(
            session_id,
            task_blueprints=[self._task_blueprint("valid-task"), retired],
        )
        self.assertIsInstance(result, Failure)
        self.assertEqual(result.code, "execution_mode_invalid")
        self.assertEqual(self.service.get_session_bundle(session_id), before)

    def test_stored_coordinator_mode_and_messages_remain_readable(self):
        bundle = self.service.create_session(
            source="user", entrypoint_type="chat", goal="Historical coordinator facts",
            task_blueprints=[self._task_blueprint("historical-task")],
        )
        session_id = bundle["session"]["session_id"]
        self.service.store.update_task(
            session_id, "historical-task", {"execution_mode": "coordinator"},
        )
        self.service.store.create_message({
            "session_id": session_id, "role": "coordinator", "actor": "coordinator",
            "content": "Historical decision",
        })
        restored = self.service.get_session_bundle(session_id)
        self.assertEqual(restored["tasks"][0]["execution_mode"], "coordinator")
        self.assertEqual(restored["messages"][-1]["role"], "coordinator")
        self.assertEqual(restored["messages"][-1]["content"], "Historical decision")

    def test_blank_claim_owner_fails_closed_without_coordinator_fallback(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Blank owner flow",
            task_blueprints=[self._task_blueprint("task-owner-required")],
        )
        session_id = bundle["session"]["session_id"]

        claimed = self.service.claim_task(session_id, "task-owner-required", owner=" ")

        self.assertIsInstance(claimed, Failure)
        assert isinstance(claimed, Failure)
        self.assertEqual(claimed.code, "task_not_claimable")
        self.assertEqual(claimed.message, "task owner is required")
        self.assertEqual(self.service.store.get_task(session_id, "task-owner-required")["status"], "pending")

    def test_automatic_projections_do_not_target_retired_coordinator_artifacts(self):
        batch_blueprints = self.service._build_agent_batch_job_blueprints(
            job_id="job-cleanup",
            accepted_items=[{"item_id": "item-1", "index": 1, "snapshot": {"status": "pending"}}],
            rejected_items=[],
        )
        workflow_blueprints = self.service._build_workflow_graph_task_blueprints(
            graph_id="graph-cleanup",
            run_id="run-cleanup",
            workflow={"topo_order": ["node-a"], "nodes": {"node-a": {"depends_on": []}}},
        )

        for blueprints in (batch_blueprints, workflow_blueprints):
            for blueprint in blueprints:
                targets = list(dict(blueprint["task_spec"]).get("artifact_targets") or [])
                self.assertNotIn("memory.md", targets)
                self.assertNotIn("scratchpad.md", targets)
        self.assertEqual(
            batch_blueprints[0]["task_spec"]["artifact_targets"],
            ["compat.job.submit.json"],
        )
        self.assertEqual(
            workflow_blueprints[0]["task_spec"]["artifact_targets"],
            ["workflow_graph.snapshot.json"],
        )

    def test_approval_wait_projection_has_no_retired_artifact_targets(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Approval artifact cleanup",
            task_blueprints=[
                {**self._task_blueprint("task-gated"), "write_set": ["file:external"]},
            ],
        )
        session_id = bundle["session"]["session_id"]
        approval = self.service.request_approval(
            session_id=session_id,
            task_id="task-gated",
            requester_actor="ops_panel",
            binding_payload={"argv": ["deploy"], "cwd": "/workspace"},
            metadata={"force_approval": True},
        )

        wait_task = next(
            task
            for task in self.service.list_tasks(session_id)
            if task["task_type"] == "approval_wait"
        )
        self.assertEqual(approval["status"], "pending")
        self.assertEqual(wait_task["task_spec"]["artifact_targets"], [])

    def test_claim_and_complete_task_unblocks_dependents(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Run coordinator flow",
            task_blueprints=[
                self._task_blueprint("task-research", task_type="research"),
                {**self._task_blueprint("task-synthesis"), "blocked_by_refs": ["prev"]},
            ],
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
            task_blueprints=[
                self._task_blueprint("task-research", task_type="research"),
                {**self._task_blueprint("task-synthesis"), "blocked_by_refs": ["prev"]},
            ],
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
            task_blueprints=[self._task_blueprint("task-retry")],
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

    def test_cancel_session_records_owner_facts_and_can_retry_task(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Cancel and retry flow",
            task_blueprints=[self._task_blueprint("task-cancel")],
        )
        session_id = bundle["session"]["session_id"]
        task_id = bundle["tasks"][0]["task_id"]

        canceled = self.service.cancel_session(session_id)
        repeated = self.service.cancel_session(session_id)
        tasks = {item["task_id"]: item for item in self.service.list_tasks(session_id)}
        events = [item["event_type"] for item in self.service.list_events(session_id)]

        self.assertEqual(canceled["status"], "canceled")
        self.assertEqual(repeated["status"], "canceled")
        self.assertEqual(tasks[task_id]["status"], "canceled")
        self.assertEqual(events.count("session.canceled"), 1)

        retried = self.service.retry_task(session_id, task_id)
        self.assertEqual(retried["action_status"], "retried")
        self.assertEqual(retried["status"], "pending")
        self.assertEqual(self.service.get_session(session_id)["status"], "pending")

    def test_session_summary_is_read_only_projection(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Summary projection flow",
            task_blueprints=[
                {
                    "task_id": "summary-task",
                    "subject": "Complete summary input",
                    "task_type": "implementation",
                    "phase": "implementation",
                }
            ],
        )
        session_id = bundle["session"]["session_id"]
        task_id = "summary-task"
        self.service.release_task(session_id, task_id, status="completed", result_summary="done")
        self.service.create_message(session_id, role="assistant", content="task completed")
        event_count = len(self.service.list_events(session_id))

        summary = self.service.get_session_summary(session_id)
        after = self.service.list_artifacts(session_id)

        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["task_counts"], {"completed": 1})
        self.assertEqual(summary["latest_message"]["content"], "task completed")
        self.assertEqual(summary["completed_results"][0]["summary"], "done")
        self.assertEqual(after, [])
        self.assertEqual(len(self.service.list_events(session_id)), event_count)

    def test_missing_session_summary_returns_failure(self):
        result = self.service.get_session_summary("missing-session")
        self.assertIsInstance(result, Failure)
        assert isinstance(result, Failure)
        self.assertEqual(result.code, "session_not_found")

    def test_historical_session_artifacts_remain_listable(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Historical artifact flow",
        )
        session_id = bundle["session"]["session_id"]
        created = self.service.store.upsert_artifact(
            {
                "session_id": session_id,
                "artifact_type": "session_memory_markdown",
                "name": "memory.md",
                "mime_type": "text/markdown",
                "content_text": "historical projection",
                "metadata": {"historical": True},
            }
        )
        artifacts = self.service.list_artifacts(session_id)

        self.assertEqual(created["name"], "memory.md")
        self.assertEqual([item["name"] for item in artifacts], ["memory.md"])
        self.assertEqual(artifacts[0]["metadata"], {"historical": True})

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
            task_blueprints=[self._task_blueprint("task-ok")],
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
            task_blueprints=[self._task_blueprint("task-workflow")],
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
            task_blueprints=[self._task_blueprint("task-approval")],
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
            task_blueprints=[self._task_blueprint("task-approval-idem")],
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
            task_blueprints=[self._task_blueprint("task-approval-conflict")],
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
            task_blueprints=[self._task_blueprint("task-approval-reject")],
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
            task_blueprints=[self._task_blueprint("task-lease")],
        )
        session_id = bundle["session"]["session_id"]
        research_task = bundle["tasks"][0]["task_id"]
        self.service.claim_task(session_id, research_task, owner="worker-a", lease_seconds=30)
        self.service.store.update_task(session_id, research_task, {"lease_until": "2000-01-01T00:00:00+00:00"})

        reclaimed = self.service.reclaim_expired_tasks(session_id)
        self.assertEqual(len(reclaimed), 1)
        self.assertEqual(reclaimed[0]["status"], "expired")

    def test_coordinator_pass_is_retired(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Retired coordinator flow",
        )
        session_id = bundle["session"]["session_id"]

        self.assertFalse(hasattr(self.service, "run_coordinator_pass"))
        self.assertFalse(hasattr(self.service, "coordinator_runtime"))
        self.assertFalse(hasattr(self.service, "memory_runtime"))
        self.assertEqual(self.service.list_messages(session_id)[0]["actor"], "session_entrypoint")

if __name__ == "__main__":
    unittest.main()
