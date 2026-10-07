from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

import pytest
from functorial_kit import Failure

from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore
from mrw_functorial_kit.core.agent_service_semantics import agent_session_failures

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

    def test_store_rejects_nested_non_json_values_without_writing_session(self):
        store = InMemoryAgentSessionStore()
        invalid_values = (
            datetime.now(timezone.utc),
            ("tuple",),
            {1: "non-string-key"},
            float("nan"),
        )

        for index, invalid_value in enumerate(invalid_values):
            with self.subTest(index=index):
                session_id = f"session-invalid-json-{index}"
                result = store.create_session(
                    {
                        "session_id": session_id,
                        "metadata": {"nested": {"value": invalid_value}},
                    }
                )

                self.assertIsInstance(result, Failure)
                self.assertEqual(result.code, "json_value_invalid")
                self.assertIsInstance(store.get_session(session_id), Failure)

        command_result = store.commit_session_command(
            "session-command-invalid-json",
            session_create={
                "session_id": "session-command-invalid-json",
                "metadata": {"nested": ("tuple",)},
            },
            expected_session_statuses=None,
            session_changes={},
            task_creates=[],
            task_mutations=[],
            message_creates=[],
            artifact_upserts=[],
            approval_mutation=None,
            events=[],
        )
        self.assertIsInstance(command_result, Failure)
        self.assertEqual(command_result.code, "json_value_invalid")
        self.assertIsInstance(
            store.get_session("session-command-invalid-json"),
            Failure,
        )

    def test_concurrent_event_appends_keep_unique_monotonic_sequence(self):
        store = InMemoryAgentSessionStore()
        created = store.create_session({"session_id": "session-event-sequence"})
        self.assertNotIsInstance(created, Failure)

        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(
                executor.map(
                    lambda index: store.append_event(
                        "session-event-sequence",
                        event_type="test.concurrent",
                        payload={"index": index},
                    ),
                    range(32),
                )
            )

        self.assertFalse(any(isinstance(result, Failure) for result in results))
        events = store.list_events("session-event-sequence")
        self.assertEqual([event["seq"] for event in events], list(range(1, 33)))

    def test_create_session_command_rolls_back_all_facts_when_event_fails(self):
        failure = agent_session_failures.fail(
            "backend_unavailable",
            "forced command event failure",
            {"operation": "append_event"},
        )
        with patch.object(self.service.store, "append_event", return_value=failure):
            result = self.service.create_session(
                source="user",
                entrypoint_type="chat",
                goal="Atomic create",
                task_blueprints=[self._task_blueprint("atomic-create-task")],
            )

        self.assertIsInstance(result, Failure)
        self.assertEqual(self.service.list_sessions(), [])

    def test_message_and_blueprint_commands_roll_back_when_event_fails(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Atomic child commands",
            task_blueprints=[self._task_blueprint("existing-command-task")],
        )
        session_id = bundle["session"]["session_id"]
        before = self.service.get_session_bundle(session_id)
        failure = agent_session_failures.fail(
            "backend_unavailable",
            "forced command event failure",
            {"operation": "append_event"},
        )

        with patch.object(self.service.store, "append_event", return_value=failure):
            message_result = self.service.create_message(
                session_id,
                role="assistant",
                content="must rollback",
            )
        self.assertIsInstance(message_result, Failure)
        self.assertEqual(self.service.get_session_bundle(session_id), before)

        with patch.object(self.service.store, "append_event", return_value=failure):
            blueprint_result = self.service.append_task_blueprints(
                session_id,
                task_blueprints=[self._task_blueprint("must-not-persist")],
            )
        self.assertIsInstance(blueprint_result, Failure)
        self.assertEqual(self.service.get_session_bundle(session_id), before)

    def test_approval_resolution_command_rolls_back_approval_tasks_and_events(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Atomic approval resolution",
            task_blueprints=[self._task_blueprint("approval-command-task")],
        )
        session_id = bundle["session"]["session_id"]
        approval = self.service.request_approval(
            session_id=session_id,
            task_id="approval-command-task",
            requester_actor="reviewer",
            binding_payload={"action": "write"},
            metadata={"force_approval": True},
        )
        before_bundle = self.service.get_session_bundle(session_id)
        before_approval = self.service.store.get_approval(approval["approval_id"])
        failure = agent_session_failures.fail(
            "backend_unavailable",
            "forced approval event failure",
            {"operation": "append_event"},
        )

        with patch.object(self.service.store, "append_event", return_value=failure):
            resolved = self.service.resolve_approval(
                approval["approval_id"],
                approved_by="reviewer",
            )

        self.assertIsInstance(resolved, Failure)
        self.assertEqual(self.service.get_session_bundle(session_id), before_bundle)
        self.assertEqual(
            self.service.store.get_approval(approval["approval_id"]),
            before_approval,
        )

    def test_session_current_phase_remains_an_explicit_host_plan_fact(self):
        bundle = self.service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Phase cache retirement",
            task_blueprints=[
                self._task_blueprint("phase-research", task_type="research"),
                {**self._task_blueprint("phase-implementation"), "blocked_by": ["phase-research"]},
            ],
        )
        session_id = bundle["session"]["session_id"]
        self.assertEqual(bundle["session"]["current_phase"], "research")

        self.service.store.update_task(
            session_id,
            "phase-research",
            {"status": "completed", "result_summary": "done"},
        )

        self.assertEqual(self.service.get_session(session_id)["current_phase"], "research")
        self.assertEqual(self.service.store.get_session(session_id)["current_phase"], "research")

    def test_runtime_associated_session_does_not_write_task_lifecycle_into_session_state(self):
        bundle = self.service.create_session(
            source="successor_runtime",
            entrypoint_type="runtime_projection",
            goal="Canonical runtime lifecycle",
            project_key="proj-runtime",
            compat_job_id="runtime-run-1",
            task_blueprints=[self._task_blueprint("runtime-step")],
        )
        session_id = bundle["session"]["session_id"]
        initial_status = self.service.store.get_session(session_id)["status"]

        observed = self.service.store.update_task(
            session_id,
            "runtime-step",
            {"status": "completed", "result_summary": "historical task observation"},
        )

        self.assertEqual(observed["status"], "completed")
        self.assertEqual(self.service.store.get_session(session_id)["status"], initial_status)

    def test_approval_mutations_reject_noncanonical_json_before_state_change(self):
        store = InMemoryAgentSessionStore()
        created = store.create_or_update_approval(
            {
                "approval_id": "approval-invalid-json",
                "binding_hash": "binding",
                "binding_payload": {"action": "write"},
                "status": "pending",
            }
        )
        self.assertNotIsInstance(created, Failure)
        before = store.get_approval("approval-invalid-json")

        result = store.confirm_host_approval(
            "approval-invalid-json",
            expected_binding_payload={"action": "write"},
            confirmation_metadata={"invalid": ("tuple",)},
        )

        self.assertIsInstance(result, Failure)
        self.assertEqual(result.code, "json_value_invalid")
        self.assertEqual(store.get_approval("approval-invalid-json"), before)

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
        self.service.store.update_task(
            session_id,
            task_id,
            {"status": "completed", "result_summary": "done"},
        )
        self.service.store.update_session(session_id, {"status": "completed"})
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
        self.service.store.update_task(
            session_id,
            "task-failed",
            {
                "status": "failed",
                "result_summary": "provider timeout",
                "result_payload": {"error_code": "provider_timeout", "trace_id": "trace-result"},
                "last_activity": "provider failed",
                "recent_activities": ["provider failed"],
            },
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
        self.assertFalse(package["retry_hint"]["retryable"])
        self.assertEqual(package["retry_hint"]["next_action"], "inspect_runtime_run")
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
        self.service.store.update_task(
            session_id,
            task_id,
            {
                "status": "failed",
                "result_summary": "node failed",
                "result_payload": {"reason_code": "node_failed"},
            },
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
