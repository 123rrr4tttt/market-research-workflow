from __future__ import annotations

import unittest
from unittest.mock import patch

import pytest

from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore
from app.services.skill_runtime import SkillRuntime

pytestmark = pytest.mark.unit


class SkillRuntimeUnitTest(unittest.TestCase):
    def test_register_and_invoke_skill(self):
        runtime = SkillRuntime()
        runtime._bootstrapped = True
        runtime.register(
            skill_id="test.echo",
            handler=lambda payload: {"echo": payload.get("value")},
            required_permissions=("test.invoke",),
        )

        out = runtime.invoke(
            skill_id="test.echo",
            payload={"value": "ok"},
            context={"actor_role": "orchestration_runtime", "permissions": ["test.invoke"]},
        )

        self.assertEqual(out["result"]["echo"], "ok")
        self.assertEqual(out["skill_id"], "test.echo")

    def test_invoke_denied_when_missing_permission(self):
        runtime = SkillRuntime()
        runtime._bootstrapped = True
        runtime.register(
            skill_id="test.needs_perm",
            handler=lambda payload: payload,
            required_permissions=("test.invoke",),
        )

        with self.assertRaises(PermissionError) as exc:
            runtime.invoke(
                skill_id="test.needs_perm",
                payload={},
                context={"actor_role": "orchestration_runtime", "permissions": ["test.read"]},
            )
        self.assertIn("missing_required_permissions", str(exc.exception))

    def test_invoke_denied_when_role_not_allowed(self):
        runtime = SkillRuntime()
        runtime._bootstrapped = True
        runtime.register(
            skill_id="test.role",
            handler=lambda payload: payload,
            allowed_actor_roles=("business_capability_wrapper",),
            required_permissions=("test.invoke",),
        )

        with self.assertRaises(PermissionError) as exc:
            runtime.invoke(
                skill_id="test.role",
                payload={},
                context={"actor_role": "orchestration_runtime", "permissions": ["test.invoke"]},
            )
        self.assertIn("actor_role_not_allowed", str(exc.exception))

    def test_invoke_with_args_and_kwargs(self):
        runtime = SkillRuntime()
        runtime._bootstrapped = True

        def _concat(prefix: str, suffix: str = "") -> str:
            return f"{prefix}:{suffix}"

        runtime.register(
            skill_id="test.concat",
            handler=_concat,
            required_permissions=("test.invoke",),
        )

        out = runtime.invoke(
            skill_id="test.concat",
            args=("left",),
            kwargs={"suffix": "right"},
            context={"actor_role": "orchestration_runtime", "permissions": ["test.invoke"]},
        )

        self.assertEqual(out["result"], "left:right")

    def test_invoke_propagates_skill_handler_error_for_upstream_fallback(self):
        runtime = SkillRuntime()
        runtime._bootstrapped = True

        def _boom(_: dict):
            raise RuntimeError("skill_planner_failed")

        runtime.register(
            skill_id="test.skill_planner",
            handler=_boom,
            required_permissions=("test.invoke",),
        )

        with self.assertRaises(RuntimeError) as exc:
            runtime.invoke(
                skill_id="test.skill_planner",
                payload={"query": "q"},
                context={"actor_role": "orchestration_runtime", "permissions": ["test.invoke"]},
            )
        self.assertIn("skill_planner_failed", str(exc.exception))

    def test_loop_guard_blocks_repeated_identical_skill_calls(self):
        runtime = SkillRuntime()
        runtime._bootstrapped = True
        runtime.register(
            skill_id="test.repeat",
            handler=lambda payload: payload,
            required_permissions=("test.invoke",),
        )
        context = {
            "actor_role": "orchestration_runtime",
            "permissions": ["test.invoke"],
            "consumer": "unit.test",
            "trace_id": "trace-loop-1",
        }
        threshold = 10  # keep in sync with default settings.skill_loop_guard_threshold
        for _ in range(threshold - 1):
            out = runtime.invoke(skill_id="test.repeat", payload={"x": 1}, context=context)
            self.assertEqual(out["result"], {"x": 1})
        with self.assertRaises(RuntimeError) as exc:
            runtime.invoke(skill_id="test.repeat", payload={"x": 1}, context=context)
        self.assertIn("tool_loop_detected", str(exc.exception))

    def test_register_updates_agent_batch_task_manifest_entries(self):
        runtime = SkillRuntime()
        runtime._bootstrapped = True
        runtime.register(
            skill_id="test.agent_batch_search",
            handler=lambda payload: payload,
            required_permissions=("test.invoke",),
            execution_profile="agent.dispatch",
            concurrency_class="write_shared",
            approval_policy={"default": "required"},
            artifact_contract={"primary_artifact": "memory.md"},
            agent_batch_task_manifest={
                "channel": "search.market",
                "description": "search override from registered skill",
                "required_keys": ["channel", "query_terms"],
            },
        )

        entries = runtime.list_agent_batch_task_manifest_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["channel"], "search.market")
        self.assertEqual(entries[0]["description"], "search override from registered skill")
        listed = runtime.list_skills()[0]
        self.assertEqual(listed["execution_profile"], "agent.dispatch")
        self.assertEqual(listed["concurrency_class"], "write_shared")
        self.assertEqual(listed["approval_policy"]["default"], "required")

    def test_write_external_requires_approval_context(self):
        runtime = SkillRuntime()
        runtime._bootstrapped = True
        runtime.register(
            skill_id="test.external_write",
            handler=lambda payload: payload,
            required_permissions=("test.invoke",),
            concurrency_class="write_external",
        )

        with self.assertRaises(PermissionError) as exc:
            runtime.invoke(
                skill_id="test.external_write",
                payload={"value": "x"},
                context={"actor_role": "orchestration_runtime", "permissions": ["test.invoke"]},
            )
        self.assertIn("approval_context_required", str(exc.exception))

    def test_write_external_creates_approval_wait_when_session_context_exists(self):
        runtime = SkillRuntime()
        runtime._bootstrapped = True
        runtime.register(
            skill_id="test.external_write",
            handler=lambda payload: payload,
            required_permissions=("test.invoke",),
            concurrency_class="write_external",
            approval_policy={"default": "required"},
        )
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Skill approval",
            task_blueprints=[
                {
                    "task_id": "impl-1",
                    "subject": "Implementation",
                    "task_type": "implementation",
                    "phase": "implementation",
                    "write_set": ["file:a.py"],
                }
            ],
        )
        session_id = bundle["session"]["session_id"]

        with patch("app.services.skill_runtime.get_agent_session_service", return_value=service):
            with self.assertRaises(PermissionError) as exc:
                runtime.invoke(
                    skill_id="test.external_write",
                    payload={"value": "x"},
                    context={
                        "actor_role": "orchestration_runtime",
                        "permissions": ["test.invoke"],
                        "agent_session_id": session_id,
                        "agent_task_id": "impl-1",
                        "consumer": "unit.test",
                    },
                )
        self.assertIn("approval_required:", str(exc.exception))
        approvals = service.list_approvals(session_id=session_id)
        self.assertEqual(len(approvals), 1)
        tasks = service.list_tasks(session_id)
        self.assertTrue(any(item["task_type"] == "approval_wait" for item in tasks))

    def test_write_external_allows_execution_when_approval_granted(self):
        runtime = SkillRuntime()
        runtime._bootstrapped = True
        runtime.register(
            skill_id="test.external_write",
            handler=lambda payload: {"ok": payload.get("value")},
            required_permissions=("test.invoke",),
            concurrency_class="write_external",
        )

        out = runtime.invoke(
            skill_id="test.external_write",
            payload={"value": "done"},
            context={
                "actor_role": "orchestration_runtime",
                "permissions": ["test.invoke"],
                "approval_granted": True,
            },
        )
        self.assertEqual(out["result"]["ok"], "done")

    def test_write_shared_rejects_conflicting_active_write_set(self):
        runtime = SkillRuntime()
        runtime._bootstrapped = True
        runtime.register(
            skill_id="test.shared_write",
            handler=lambda payload: payload,
            required_permissions=("test.invoke",),
            concurrency_class="write_shared",
        )
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Write shared conflict",
            task_blueprints=[
                {
                    "task_id": "impl-a",
                    "subject": "Implementation A",
                    "task_type": "implementation",
                    "phase": "implementation",
                    "write_set": ["file:a.py"],
                },
                {
                    "task_id": "impl-b",
                    "subject": "Implementation B",
                    "task_type": "implementation",
                    "phase": "implementation",
                    "write_set": ["file:a.py"],
                },
            ],
        )
        session_id = bundle["session"]["session_id"]
        service.claim_task(session_id, "impl-a", owner="worker-a")

        with patch("app.services.skill_runtime.get_agent_session_service", return_value=service):
            with self.assertRaises(RuntimeError) as exc:
                runtime.invoke(
                    skill_id="test.shared_write",
                    payload={"value": "x"},
                    context={
                        "actor_role": "orchestration_runtime",
                        "permissions": ["test.invoke"],
                        "agent_session_id": session_id,
                        "agent_task_id": "impl-b",
                    },
                )
        self.assertIn("write_set_conflict", str(exc.exception))
        events = service.list_events(session_id)
        self.assertTrue(any(item["event_type"] == "skill.write_conflict" for item in events))

    def test_write_shared_allows_non_conflicting_write_set(self):
        runtime = SkillRuntime()
        runtime._bootstrapped = True
        runtime.register(
            skill_id="test.shared_write",
            handler=lambda payload: {"ok": payload.get("value")},
            required_permissions=("test.invoke",),
            concurrency_class="write_shared",
        )
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle = service.create_session(
            source="user",
            entrypoint_type="chat",
            goal="Write shared no conflict",
            task_blueprints=[
                {
                    "task_id": "impl-a",
                    "subject": "Implementation A",
                    "task_type": "implementation",
                    "phase": "implementation",
                    "write_set": ["file:a.py"],
                },
                {
                    "task_id": "impl-b",
                    "subject": "Implementation B",
                    "task_type": "implementation",
                    "phase": "implementation",
                    "write_set": ["file:b.py"],
                },
            ],
        )
        session_id = bundle["session"]["session_id"]
        service.claim_task(session_id, "impl-a", owner="worker-a")

        with patch("app.services.skill_runtime.get_agent_session_service", return_value=service):
            out = runtime.invoke(
                skill_id="test.shared_write",
                payload={"value": "done"},
                context={
                    "actor_role": "orchestration_runtime",
                    "permissions": ["test.invoke"],
                    "agent_session_id": session_id,
                    "agent_task_id": "impl-b",
                },
            )
        self.assertEqual(out["result"]["ok"], "done")


if __name__ == "__main__":
    unittest.main()
