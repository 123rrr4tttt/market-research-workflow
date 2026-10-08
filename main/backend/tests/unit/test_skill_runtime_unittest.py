from __future__ import annotations

import unittest
from collections.abc import Mapping
from typing import TypeGuard
from unittest.mock import Mock, patch

import pytest
from functorial_kit import Failure

from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore
from app.services.skill_runtime import SkillInvocationContext, SkillRuntime

pytestmark = pytest.mark.unit


def _runtime() -> SkillRuntime:
    return SkillRuntime(bootstrap=False)


def _identity(payload: object) -> object:
    return payload


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _object_mapping(value: object) -> Mapping[str, object]:
    if not _is_object_mapping(value):
        raise AssertionError(f"expected mapping, received {type(value).__name__}")
    return {str(key): item for key, item in value.items()}


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _object_list(value: object) -> list[object]:
    if isinstance(value, Failure):
        raise AssertionError(value.message)
    if not _is_object_list(value):
        raise AssertionError(f"expected list, received {type(value).__name__}")
    return value


def _payload_value(payload: object) -> object:
    return _object_mapping(payload).get("value")


def _echo(payload: object) -> dict[str, object]:
    return {"echo": _payload_value(payload)}


def _ok(payload: object) -> dict[str, object]:
    return {"ok": _payload_value(payload)}


def _session_id(bundle: object) -> str:
    if isinstance(bundle, Failure):
        raise AssertionError(bundle.message)
    session = _object_mapping(_object_mapping(bundle).get("session"))
    return str(session["session_id"])


class SkillRuntimeUnitTest(unittest.TestCase):
    def test_context_bound_handler_keeps_actor_proof_outside_payload(self):
        from app.services.request_identity import authenticated_actor_context
        actor = authenticated_actor_context(actor_id="trusted-skill-actor", source="test", auth_mode="session")
        seen = []
        def handler(payload, *, invocation_context):
            seen.append((payload, invocation_context["actor_context"]))
            return {"accepted": True}
        runtime = _runtime()
        runtime.register(skill_id="test.context", handler=handler, pass_invocation_context=True)
        payload = {"actor_id": "forged", "invocation_context": {"actor_context": "forged"}}
        runtime.invoke(skill_id="test.context", payload=payload, context={"actor_context": actor})
        self.assertIs(seen[0][1], actor)
        self.assertEqual(seen[0][0], payload)
        with self.assertRaises(TypeError):
            runtime.invoke(skill_id="test.context", kwargs={"invocation_context": {"actor_context": "forged"}})
        self.assertEqual(len(seen), 1)

    def test_register_and_invoke_skill(self):
        runtime = _runtime()
        runtime.register(
            skill_id="test.echo",
            handler=_echo,
            required_permissions=("test.invoke",),
        )

        out = runtime.invoke(
            skill_id="test.echo",
            payload={"value": "ok"},
            context={"actor_role": "orchestration_runtime", "permissions": ["test.invoke"]},
        )

        self.assertEqual(_object_mapping(out["result"])["echo"], "ok")
        self.assertEqual(out["skill_id"], "test.echo")

    def test_invoke_denied_when_missing_permission(self):
        runtime = _runtime()
        handler = Mock(side_effect=_identity)
        runtime.register(
            skill_id="test.needs_perm",
            handler=handler,
            required_permissions=("test.invoke",),
            repeatable_read=True,
        )

        for _ in range(11):
            with self.assertRaises(PermissionError) as exc:
                runtime.invoke(
                    skill_id="test.needs_perm",
                    payload={},
                    context={"actor_role": "orchestration_runtime", "permissions": ["test.read"]},
                )
            self.assertIn("missing_required_permissions", str(exc.exception))
        handler.assert_not_called()

    def test_invoke_denied_when_role_not_allowed(self):
        runtime = _runtime()
        handler = Mock(side_effect=_identity)
        runtime.register(
            skill_id="test.role",
            handler=handler,
            allowed_actor_roles=("business_capability_wrapper",),
            required_permissions=("test.invoke",),
            repeatable_read=True,
        )

        for _ in range(11):
            with self.assertRaises(PermissionError) as exc:
                runtime.invoke(
                    skill_id="test.role",
                    payload={},
                    context={"actor_role": "orchestration_runtime", "permissions": ["test.invoke"]},
                )
            self.assertIn("actor_role_not_allowed", str(exc.exception))
        handler.assert_not_called()

    def test_invoke_with_args_and_kwargs(self):
        runtime = _runtime()

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
        runtime = _runtime()

        def _boom(_: object) -> object:
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
        runtime = _runtime()
        effects: list[object] = []

        def effect(payload: object) -> object:
            effects.append(payload)
            return payload

        runtime.register(
            skill_id="test.repeat",
            handler=effect,
            required_permissions=("test.invoke",),
        )
        context: SkillInvocationContext = {
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
        self.assertEqual(len(effects), threshold - 1)
        self.assertFalse(runtime.list_skills()[0]["repeatable_read"])

    def test_loop_guard_still_blocks_declared_effects(self):
        for concurrency_class in ("write_shared", "write_external", "privileged"):
            with self.subTest(concurrency_class=concurrency_class):
                runtime = _runtime()
                effect = Mock(side_effect=_identity)
                skill_id = f"test.repeat.{concurrency_class}"
                runtime.register(skill_id=skill_id, handler=effect, concurrency_class=concurrency_class)
                context: SkillInvocationContext = {
                    "actor_role": "orchestration_runtime", "approval_granted": True,
                    "consumer": "unit.test", "trace_id": f"trace-loop-{concurrency_class}",
                }
                for _ in range(9):
                    runtime.invoke(skill_id=skill_id, payload={"x": 1}, context=context)
                with self.assertRaisesRegex(RuntimeError, "^tool_loop_detected$"):
                    runtime.invoke(skill_id=skill_id, payload={"x": 1}, context=context)
                self.assertEqual(effect.call_count, 9)

    def test_repeatable_reads_cannot_be_registered_for_effect_classes(self):
        for concurrency_class in ("write_shared", "write_external", "privileged"):
            with self.subTest(concurrency_class=concurrency_class):
                runtime = _runtime()
                with self.assertRaisesRegex(ValueError, "^repeatable_read requires read_only concurrency_class$"):
                    runtime.register(
                        skill_id="test.invalid_read", handler=_identity,
                        concurrency_class=concurrency_class, repeatable_read=True,
                    )
                self.assertEqual(runtime.list_skills(), [])

    def test_repeatable_read_registration_rejects_non_boolean_values(self):
        runtime = _runtime()
        register = getattr(runtime, "register")
        invalid_values: tuple[object, ...] = (None, 1, "false", {})
        for raw in invalid_values:
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(ValueError, "^repeatable_read must be a boolean$"):
                    register(skill_id="test.invalid_read", handler=_identity, repeatable_read=raw)
                self.assertEqual(runtime.list_skills(), [])

    def test_register_updates_agent_batch_task_manifest_entries(self):
        runtime = _runtime()
        runtime.register(
            skill_id="test.agent_batch_search",
            handler=_identity,
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
        self.assertEqual(_object_mapping(listed["approval_policy"])["default"], "required")

    def test_write_external_requires_approval_context(self):
        runtime = _runtime()
        handler = Mock(side_effect=_identity)
        runtime.register(
            skill_id="test.external_write",
            handler=handler,
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
        handler.assert_not_called()

    def test_write_external_creates_approval_wait_when_session_context_exists(self):
        runtime = _runtime()
        handler = Mock(side_effect=_identity)
        runtime.register(
            skill_id="test.external_write",
            handler=handler,
            required_permissions=("test.invoke",),
            concurrency_class="write_external",
            approval_policy={"default": "required"},
        )
        service = AgentSessionService(store=InMemoryAgentSessionStore())
        bundle: object = service.create_session(
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
        session_id = _session_id(bundle)

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
        handler.assert_not_called()
        approvals: object = service.list_approvals(session_id=session_id)
        self.assertEqual(len(_object_list(approvals)), 1)
        tasks: object = service.list_tasks(session_id)
        self.assertTrue(any(_object_mapping(item)["task_type"] == "approval_wait" for item in _object_list(tasks)))

    def test_write_external_allows_execution_when_approval_granted(self):
        runtime = _runtime()
        runtime.register(
            skill_id="test.external_write",
            handler=_ok,
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
        self.assertEqual(_object_mapping(out["result"])["ok"], "done")

if __name__ == "__main__":
    unittest.main()
