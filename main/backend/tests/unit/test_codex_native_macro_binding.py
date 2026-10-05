from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from functorial_kit import Failure

from app.services.llm.codex_app_server import CodexAppServerCore, _CodexFailureSignal
from app.services.llm.codex_macro_binding import (
    NativeAgentBinding,
    NativeSkillBinding,
    NativeToolBinding,
    assemble_agent_macro_binding,
    build_agent_macro_pilot_binding,
    build_agent_macro_rapid_binding,
    resolve_agent_macro_environment,
)
from app.services.llm.native_tool_context import current_native_tool_call_context
from app.services.agent_core.contracts import CoreToolSpec
from app.services.agent_core.project_tools import build_project_core_tool_registry


PILOT_SKILL = Path(__file__).resolve().parents[2] / "skills" / "agent-macro-pilot" / "SKILL.md"


class _FakeConnect:
    def __init__(self, websocket):
        self.websocket = websocket

    async def __aenter__(self):
        return self.websocket

    async def __aexit__(self, exc_type, exc, traceback):
        return False


class _FakeWebSocket:
    def __init__(self, messages):
        self.messages = [json.dumps(item) for item in messages]
        self.sent: list[dict] = []

    async def send(self, payload):
        self.sent.append(json.loads(payload))

    async def recv(self):
        return self.messages.pop(0)


class _Store:
    def __init__(self, artifacts=()):
        self.artifacts = list(artifacts)

    def list_project_artifacts(self, *, project_key):
        return [dict(item) for item in self.artifacts if item.get("project_key") == project_key]

    def list_artifacts(self, session_id):
        return [dict(item) for item in self.artifacts]


class _Service:
    def __init__(self, artifacts=()):
        self.store = _Store(artifacts)


class _FakeRegistry:
    def __init__(self, specs):
        self.specs = list(specs)

    def list_specs(self):
        return list(self.specs)

    def get(self, name):
        return next((spec for spec in self.specs if spec.name == name), None)


def _core() -> CodexAppServerCore:
    return CodexAppServerCore(
        codex_bin_resolver=lambda: "/tmp/codex",
        workdir_resolver=lambda: "/tmp/mrw-native-project",
        disabled_features_resolver=lambda: [],
        idle_ttl_seconds=300,
        start_timeout_seconds=1,
    )


def _binding(**overrides) -> NativeAgentBinding:
    values = {
        "binding_id": "test.v1",
        "project_key": "alpha",
        "scope_id": "session-1",
        "skills": (),
        "tools": (),
        "base_instructions": "base instructions",
        "developer_instructions": "developer instructions",
        "sandbox": "workspace-write",
    }
    values.update(overrides)
    return NativeAgentBinding(**values)


def _pilot_skill_binding(**overrides) -> NativeAgentBinding:
    skill = NativeSkillBinding.from_path(name="agent-macro-pilot", path=PILOT_SKILL)
    return _binding(skills=(skill,), **overrides)


def test_native_binding_rejects_invalid_authoring(tmp_path) -> None:
    skill = NativeSkillBinding.from_path(name="agent-macro-pilot", path=PILOT_SKILL)
    binding = _pilot_skill_binding()
    with pytest.raises(ValueError, match="existing SKILL.md"):
        NativeSkillBinding.from_path(name="valid", path=tmp_path / "SKILL.md")
    other_file = tmp_path / "other.md"
    other_file.write_text("skill")
    with pytest.raises(ValueError, match="existing SKILL.md"):
        NativeSkillBinding.from_path(name="valid", path=other_file)
    for changes, message in [({"name": "invalid name"}, "name is invalid"),
                             ({"content_digest": "bad"}, "must be sha256")]:
        with pytest.raises(ValueError, match=message):
            replace(skill, **changes)
    tool = NativeToolBinding("read", "Read", {"type": "object"}, lambda _: {})
    for changes, error, message in [
        ({"name": "invalid name"}, ValueError, "name is invalid"),
        ({"namespace": "invalid namespace"}, ValueError, "namespace is invalid"),
        ({"description": " "}, ValueError, "description is required"),
        ({"handler": None}, TypeError, "handler must be callable"),
        ({"input_schema": {"type": "array"}}, ValueError, "describe an object"),
    ]:
        with pytest.raises(error, match=message):
            replace(tool, **changes)
    for field in ("binding_id", "project_key", "scope_id", "base_instructions", "developer_instructions"):
        with pytest.raises(ValueError, match=f"{field} is required"):
            replace(binding, **{field: " "})
    for changes, message in [
        ({"core_mode": "other"}, "only represents native-agent"),
        ({"sandbox": "danger-full-access"}, "sandbox must be"),
        ({"approval_policy": "always"}, "approval requests are not supported"),
        ({"skills": (skill, skill)}, "identities must be unique"),
        ({"tools": (tool, tool)}, "identities must be unique"),
    ]:
        with pytest.raises(ValueError, match=message):
            replace(binding, **changes)


def test_native_api_rejects_invalid_authoring_before_process_start() -> None:
    core = _core()
    with patch.object(core, "_ensure_process") as start:
        with pytest.raises(TypeError, match="binding must be a NativeAgentBinding"):
            core.invoke_native("prompt", binding=None)
        for thread, turn in [("", "turn"), ("thread", " ")]:
            with pytest.raises(ValueError, match="thread_id and turn_id are required"):
                core.interrupt_native_turn(thread_id=thread, turn_id=turn)
        start.assert_not_called()


@pytest.mark.parametrize("failure_site", ["skill", "turn_id", "rpc"])
def test_native_rpc_failure_lift_preserves_failure_and_public_abi(failure_site) -> None:
    binding = _pilot_skill_binding()
    skill = binding.skills[0]
    messages = [
        {"id": 1, "result": {}},
        {"id": 2, "result": {}},
        {"id": 3, "result": {"data": [{"skills": [
            {"name": skill.name, "path": skill.path, "enabled": True}
        ]}]}},
        {"id": 4, "result": {"thread": {"id": "thread-1"}}},
        {"id": 5, "result": {"turn": {}}},
    ]
    if failure_site == "skill":
        messages[2]["result"] = {"data": []}
    elif failure_site == "rpc":
        messages[4] = {"id": 5, "error": {"code": -1, "message": "provider rejected request"}}
    core = _core()
    kwargs = dict(endpoint="ws://127.0.0.1:1", prompt="prompt", binding=binding,
                  model="gpt-test", timeout_seconds=5, reasoning_effort=None)
    with patch("app.services.llm.codex_app_server.websockets.connect",
               return_value=_FakeConnect(_FakeWebSocket(messages))):
        with pytest.raises(_CodexFailureSignal) as raw:
            asyncio.run(core._invoke_native_async_raw(**kwargs))
    failure = raw.value.failure
    assert failure.family == "codex.invocation.failure"
    assert failure.code == ("rpc_error" if failure_site == "rpc" else "server_event_error")
    assert failure.context["operation"] == {
        "skill": "app_server.native.skills_list",
        "turn_id": "app_server.native.turn_start",
        "rpc": "app_server.rpc.turn/start",
    }[failure_site]
    with patch.object(core, "_invoke_native_async_raw", new=AsyncMock(side_effect=raw.value)):
        with pytest.raises(RuntimeError) as public:
            asyncio.run(core._invoke_native_async(**kwargs))
    assert str(public.value) == failure.context["public_message"]


def test_native_binding_digest_and_thread_key_include_project_scope() -> None:
    first = _binding(scope_id="session-1")
    second = _binding(scope_id="session-2")
    assert first.environment_digest != second.environment_digest
    assert first.environment_digest != replace(
        first, developer_instructions="changed native instructions"
    ).environment_digest
    assert first.capability_status() == {
        "dynamic_tools": "supported",
        "skills_extra_roots": "supported",
        "same_process_continuation": "supported",
        "thread_resume_after_process_exit": "not_supported",
        "turn_interrupt": "supported",
        "approval_requests": "not_supported",
    }

    core = _core()
    calls: list[dict] = []

    async def fake_request(ws, *, request_id, method, params, timeout_seconds):
        calls.append(dict(params))
        return {"thread": {"id": f"thread-{len(calls)}"}}

    with patch.object(core, "_request", side_effect=fake_request):
        first_thread = asyncio.run(
            core._ensure_thread_id(
                object(), model="gpt-test", timeout_seconds=5, binding=first
            )
        )
        reused_thread = asyncio.run(
            core._ensure_thread_id(
                object(), model="gpt-test", timeout_seconds=5, binding=first
            )
        )
        second_thread = asyncio.run(
            core._ensure_thread_id(
                object(), model="gpt-test", timeout_seconds=5, binding=second
            )
        )

    assert first_thread == reused_thread == "thread-1"
    assert second_thread == "thread-2"
    assert len(calls) == 2
    assert calls[0]["dynamicTools"] == first.dynamic_tool_specs()
    assert calls[0]["approvalPolicy"] == "never"
    assert calls[0]["sandbox"] == "workspace-write"


def test_native_failed_turn_does_not_return_agent_text() -> None:
    binding = _binding()
    websocket = _FakeWebSocket(
        [
            {"method": "item/agentMessage/delta", "params": {"turnId": "turn-1", "delta": "partial"}},
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {"id": "turn-1", "status": "failed", "error": {"message": "provider failed"}},
                },
            },
        ]
    )
    with pytest.raises(_CodexFailureSignal, match="codex native Agent turn did not complete successfully") as rejected:
        asyncio.run(
            _core()._collect_turn_result(
                websocket,
                thread_id="thread-1",
                turn_id="turn-1",
                timeout_seconds=5,
                binding=binding,
            )
        )
    assert rejected.value.failure.family == "codex.invocation.failure"
    assert rejected.value.failure.code == "server_event_error"
    assert rejected.value.failure.context["operation"] == "app_server.native.turn_completed"
    assert rejected.value.failure.context["turn_status"] == "failed"


def test_active_macro_identity_uses_canonical_project_artifacts_across_sessions() -> None:
    from app.services.agent_sessions.service import AgentSessionService
    from app.services.agent_sessions.store import InMemoryAgentSessionStore
    from app.services.agent_core.macro_environment import select_active_macro_identity

    service = AgentSessionService(store=InMemoryAgentSessionStore())
    bundle_a = service.create_session(
        source="user",
        entrypoint_type="agent_core",
        goal="activate",
        project_key="alpha",
        task_blueprints=[],
    )
    session_a = bundle_a["session"]["session_id"]

    project_artifact = service.store.upsert_project_artifact({
        "project_key": "alpha",
        "name": "macro-registration/agent.macro.pilot@1.json",
        "artifact_type": "agent_macro.registration_package",
        "content_json": {
            "package_id": "agent.macro.pilot",
            "package_version": "1",
            "activation": {"status": "activated"},
        },
        "metadata": {"project_key": "alpha", "project_scope": True, "activation_status": "activated"},
    })
    assert not isinstance(project_artifact, Failure)

    bundle_b = service.create_session(
        source="user",
        entrypoint_type="agent_core",
        goal="read",
        project_key="alpha",
        task_blueprints=[],
    )
    session_b = bundle_b["session"]["session_id"]
    assert session_b != session_a

    # Canonical project artifact discovery is cross-session.
    assert select_active_macro_identity(service, "alpha") == (("agent.macro.pilot",), ("1",))

    # Cross-project isolation.
    assert select_active_macro_identity(service, "beta") == ((), ())

    # A session-only artifact is not promoted to canonical project discovery.
    session_only = service.store.upsert_artifact({
        "session_id": session_b,
        "name": "macro-registration/agent.macro.pilot@2.json",
        "artifact_type": "agent_macro.registration_package",
        "content_json": {
            "package_id": "agent.macro.pilot",
            "package_version": "2",
            "activation": {"status": "activated"},
        },
        "metadata": {"project_key": "alpha"},
    })
    assert not isinstance(session_only, Failure)
    assert select_active_macro_identity(service, "alpha") == (("agent.macro.pilot",), ("1",))

    # A project with no canonical artifact must not fall back to a session-only one.
    bundle_c = service.create_session(
        source="user",
        entrypoint_type="agent_core",
        goal="read",
        project_key="gamma",
        task_blueprints=[],
    )
    session_c = bundle_c["session"]["session_id"]
    session_only_c = service.store.upsert_artifact({
        "session_id": session_c,
        "name": "macro-registration/agent.macro.pilot@3.json",
        "artifact_type": "agent_macro.registration_package",
        "content_json": {
            "package_id": "agent.macro.pilot",
            "package_version": "3",
            "activation": {"status": "activated"},
        },
        "metadata": {"project_key": "gamma"},
    })
    assert not isinstance(session_only_c, Failure)
    assert select_active_macro_identity(service, "gamma") == ((), ())


def test_resolve_agent_macro_environment_delegates_to_active_selector() -> None:
    registry = _FakeRegistry([CoreToolSpec(name="source.web.search", description_for_model="search")])
    service = object()
    with patch(
        "app.services.agent_core.project_tools.build_project_core_tool_registry",
        return_value=registry,
    ), patch(
        "app.services.agent_core.macro_environment.select_active_macro_identity",
        return_value=(("agent.macro.pilot",), ("1",)),
    ) as select, patch(
        "app.services.agent_core.macro_environment.resolve_macro_environment",
        return_value="resolved",
    ) as resolve:
        result = resolve_agent_macro_environment(project_key="alpha", service=service)
    assert result == "resolved"
    assert select.call_args.args == (service, "alpha", None, None)
    assert resolve.call_args.args[2] == ("agent.macro.pilot",)
    assert resolve.call_args.args[3] == ("1",)


def test_assemble_agent_macro_binding_builds_declaration_observation() -> None:
    resolved = SimpleNamespace(
        package=None,
        declared_tools=(),
        skills=(),
        environment_digest="d" * 64,
    )
    context = SimpleNamespace(session_id="s")
    with patch(
        "app.services.llm.codex_macro_binding.resolve_agent_macro_environment",
        return_value=resolved,
    ), patch(
        "app.services.agent_core.macro_environment.assemble_native_macro_binding",
        return_value=_binding(binding_id="agent.macro.base"),
    ):
        assembly = assemble_agent_macro_binding(
            project_key="alpha",
            service=object(),
            trusted_host_context=context,
        )
    assert not isinstance(assembly, Failure)
    assert assembly.binding.binding_id == "agent.macro.base"
    assert assembly.package_id is None
    assert assembly.package_version is None
    assert assembly.declared_tool_names == ()
    assert assembly.skill_names == ()
    assert assembly.environment_digest == "d" * 64


def test_pilot_builder_surfaces_failure_without_fallback() -> None:
    failure = Failure("capability_input_missing", "macro_environment_invalid", "bad package")
    with patch(
        "app.services.llm.codex_macro_binding.assemble_agent_macro_binding",
        return_value=failure,
    ):
        result = build_agent_macro_pilot_binding(
            project_key="alpha", scope_id="s", service=object(), session_id="s"
        )
    assert isinstance(result, Failure)
    assert result.code == "macro_environment_invalid"


def test_rapid_builder_keeps_ordinary_core_without_global_capability_ban() -> None:
    registry = _FakeRegistry([
        CoreToolSpec(name="source.web.search", description_for_model="search"),
        CoreToolSpec(name="agent_batch.submit", description_for_model="submit"),
    ])
    with patch(
        "app.services.agent_core.project_tools.build_project_core_tool_registry",
        return_value=registry,
    ), patch(
        "app.services.agent_core.macro_environment.get_agent_macro_facility_catalog",
        return_value=(),
    ):
        binding = build_agent_macro_rapid_binding(
            project_key="alpha", scope_id="codex-webui-base", service=_Service(), session_id="s"
        )
    assert not isinstance(binding, Failure)
    assert binding.binding_id == "agent.macro.base"
    assert {tool.logical_name for tool in binding.tools} == {
        "source_web.search", "agent_batch.submit",
    }
    instructions = f"{binding.base_instructions} {binding.developer_instructions}".lower()
    assert "shell" not in instructions
    assert "browser" not in instructions
    assert "mcp" not in instructions


def test_native_dispatch_passes_occurrence_identity_to_handler() -> None:
    observed: list[tuple[str, str, str]] = []

    def handler(arguments):
        context = current_native_tool_call_context()
        if context is not None:
            observed.append((context.call_id, context.thread_id, context.turn_id))
        return {"ok": True}

    tool = NativeToolBinding("read", "Read", {"type": "object", "properties": {}}, handler)
    binding = _binding(tools=(tool,))
    websocket = _FakeWebSocket([])
    asyncio.run(
        _core()._dispatch_server_request(
            websocket,
            data={
                "id": 90,
                "method": "item/tool/call",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "callId": "call-1",
                    "tool": "read",
                    "arguments": {"run_id": "run-7"},
                },
            },
            binding=binding,
            thread_id="thread-1",
            turn_id="turn-1",
        )
    )
    assert observed == [("call-1", "thread-1", "turn-1")]
    assert current_native_tool_call_context() is None


def test_same_arguments_distinct_calls_have_distinct_identity() -> None:
    observed: list[str] = []

    def handler(arguments):
        context = current_native_tool_call_context()
        observed.append(context.call_id if context is not None else "")
        return {"ok": True}

    tool = NativeToolBinding("read", "Read", {"type": "object", "properties": {}}, handler)
    binding = _binding(tools=(tool,))
    websocket = _FakeWebSocket([])

    def dispatch(call_id):
        asyncio.run(
            _core()._dispatch_server_request(
                websocket,
                data={
                    "id": 90,
                    "method": "item/tool/call",
                    "params": {
                        "threadId": "thread-1",
                        "turnId": "turn-1",
                        "callId": call_id,
                        "tool": "read",
                        "arguments": {"run_id": "run-7"},
                    },
                },
                binding=binding,
                thread_id="thread-1",
                turn_id="turn-1",
            )
        )

    dispatch("call-1")
    dispatch("call-2")
    assert observed == ["call-1", "call-2"]


def test_native_tool_context_resets_after_handler_exception() -> None:
    def handler(arguments):
        raise RuntimeError("boom")

    tool = NativeToolBinding("read", "Read", {"type": "object", "properties": {}}, handler)
    binding = _binding(tools=(tool,))
    websocket = _FakeWebSocket([])
    handled = asyncio.run(
        _core()._dispatch_server_request(
            websocket,
            data={
                "id": 90,
                "method": "item/tool/call",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "callId": "call-1",
                    "tool": "read",
                    "arguments": {"run_id": "run-7"},
                },
            },
            binding=binding,
            thread_id="thread-1",
            turn_id="turn-1",
        )
    )
    assert handled is True
    assert websocket.sent[-1]["result"]["success"] is False
    assert current_native_tool_call_context() is None


def test_duplicate_native_tool_call_id_reuses_response_without_reexecution() -> None:
    observed: list[dict] = []
    tool = NativeToolBinding(
        "read",
        "Read",
        {"type": "object", "properties": {}},
        lambda arguments: observed.append(dict(arguments)) or {"ok": True},
    )
    binding = _binding(tools=(tool,))
    websocket = _FakeWebSocket([])
    call = {
        "method": "item/tool/call",
        "params": {
            "threadId": "thread-1",
            "turnId": "turn-1",
            "callId": "call-1",
            "tool": "read",
            "arguments": {"run_id": "run-7"},
        },
    }
    answered: dict = {}
    first = asyncio.run(
        _core()._dispatch_server_request(
            websocket,
            data={"id": 90, **call},
            binding=binding,
            thread_id="thread-1",
            turn_id="turn-1",
            answered_calls=answered,
        )
    )
    second = asyncio.run(
        _core()._dispatch_server_request(
            websocket,
            data={"id": 91, **call},
            binding=binding,
            thread_id="thread-1",
            turn_id="turn-1",
            answered_calls=answered,
        )
    )
    assert first is True and second is False
    assert observed == [{"run_id": "run-7"}]
    assert websocket.sent[0]["result"] == websocket.sent[1]["result"]


def test_approval_request_is_explicitly_not_supported() -> None:
    websocket = _FakeWebSocket([])
    handled = asyncio.run(
        _core()._dispatch_server_request(
            websocket,
            data={
                "id": 44,
                "method": "item/commandExecution/requestApproval",
                "params": {},
            },
            binding=_binding(),
            thread_id="thread-1",
            turn_id="turn-1",
        )
    )
    assert handled is False
    assert websocket.sent == [
        {
            "jsonrpc": "2.0",
            "id": 44,
            "error": {
                "code": -32601,
                "message": (
                    "server request not supported by this binding: "
                    "item/commandExecution/requestApproval"
                ),
            },
        }
    ]


def test_interrupt_uses_protocol_method() -> None:
    core = _core()
    calls: list[tuple[str, dict]] = []

    async def fake_initialize(ws, *, timeout_seconds):
        calls.append(("initialize", {"timeout_seconds": timeout_seconds}))

    async def fake_request(ws, *, request_id, method, params, timeout_seconds):
        calls.append((method, dict(params)))
        return {}

    with (
        patch(
            "app.services.llm.codex_app_server.websockets.connect",
            return_value=_FakeConnect(_FakeWebSocket([])),
        ),
        patch.object(core, "_initialize_socket", side_effect=fake_initialize),
        patch.object(core, "_request", side_effect=fake_request),
    ):
        interrupted = asyncio.run(
            core._interrupt_native_turn_async(
                endpoint="ws://127.0.0.1:1",
                thread_id="thread-1",
                turn_id="turn-1",
                timeout_seconds=5,
            )
        )

    assert interrupted is True
    assert calls[-1] == (
        "turn/interrupt",
        {"threadId": "thread-1", "turnId": "turn-1"},
    )


def test_project_registry_keeps_structured_batch_and_drops_legacy_nl_tool() -> None:
    with patch(
        "app.services.agent_core.project_tools._register_agent_macro_facilities"
    ):
        registry = build_project_core_tool_registry(service=Mock())

    names = {spec.name for spec in registry.list_specs()}
    assert "agent_batch.submit" in names
    assert "agent_batch.nl_command.submit" not in names
    structured_spec = registry.get("agent_batch.submit")
    assert "command" not in dict(structured_spec.input_schema["properties"])
