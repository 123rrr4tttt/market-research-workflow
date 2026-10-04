from __future__ import annotations

import asyncio
from dataclasses import replace
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services.llm.codex_app_server import CodexAppServerCore, _CodexFailureSignal
from app.services.llm.codex_macro_binding import (
    NativeSkillBinding,
    NativeToolBinding,
    build_agent_macro_pilot_binding,
    build_agent_macro_rapid_binding,
)
from app.services.agent_core.contracts import CoreToolResult, CoreToolSpec
from app.services.agent_core.project_tools import build_project_core_tool_registry


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


def _core() -> CodexAppServerCore:
    return CodexAppServerCore(
        codex_bin_resolver=lambda: "/tmp/codex",
        workdir_resolver=lambda: "/tmp/mrw-native-project",
        disabled_features_resolver=lambda: [],
        idle_ttl_seconds=300,
        start_timeout_seconds=1,
    )


def test_native_binding_rejects_invalid_authoring(tmp_path) -> None:
    binding = build_agent_macro_pilot_binding(project_key="alpha", scope_id="session-1")
    skill = binding.skills[0]
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
    binding = build_agent_macro_pilot_binding(project_key="alpha", scope_id="session-1")
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


def test_native_binding_digest_and_thread_key_include_project_scope_and_skill() -> None:
    first = build_agent_macro_pilot_binding(project_key="alpha", scope_id="session-1")
    second = build_agent_macro_pilot_binding(project_key="alpha", scope_id="session-2")
    assert first.environment_digest != second.environment_digest
    assert first.environment_digest != replace(
        first, developer_instructions="changed native instructions"
    ).environment_digest
    assert first.skill_roots == (
        str(first.skills[0].root),
    )
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
    assert calls[0]["sandbox"] == "read-only"


def test_rapid_binding_projects_registered_effects_as_dynamic_tools() -> None:
    class FakeRegistry:
        def __init__(self):
            self.specs = {
                "source.web.search": CoreToolSpec(
                    name="source.web.search",
                    description_for_model="search",
                    input_schema={"type": "object", "properties": {}},
                ),
                "ingest.url_pool.submit": CoreToolSpec(
                    name="ingest.url_pool.submit",
                    description_for_model="ingest",
                    input_schema={"type": "object", "properties": {}},
                ),
            }

        def get(self, name):
            return self.specs.get(name)

        def list_specs(self):
            return list(self.specs.values())

        def execute_tool(self, *, tool_call, tool_spec, request, emit):
            return CoreToolResult(
                call_id=tool_call.call_id,
                tool_name=tool_call.tool_name,
                status="completed",
                model_summary="ok",
                structured_content={"project_key": request.project_key},
            )

    with patch(
        "app.services.agent_core.project_tools.build_project_core_tool_registry",
        return_value=FakeRegistry(),
    ), patch("app.services.projects.context.bind_project", return_value=_FakeContext()):
        binding = build_agent_macro_rapid_binding(
            project_key="hk_water_investigation",
            scope_id="session-1",
            service=object(),
            session_id="session-1",
        )

    assert binding.binding_id == "agent-macro-rapid.v1"
    assert {tool.logical_name for tool in binding.tools} == {
        "source_web.search",
        "ingest_url_pool.submit",
    }
    result = binding.tools[0].handler({})
    assert result["status"] == "completed"


class _FakeContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


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


def test_native_turn_mounts_skill_and_dispatches_existing_read_only_handler() -> None:
    observed: list[dict] = []

    def fake_read_run(payload):
        observed.append(dict(payload))
        return {"run_id": payload["run_id"], "status": "completed", "receipt": {}}

    with patch("app.services.project_retrieval.skill.read_run", side_effect=fake_read_run):
        binding = build_agent_macro_pilot_binding(
            project_key="alpha", scope_id="session-1"
        )
    skill = binding.skills[0]
    websocket = _FakeWebSocket(
        [
            {"id": 1, "result": {}},
            {"id": 2, "result": {}},
            {
                "id": 3,
                "result": {
                    "data": [
                        {
                            "cwd": "/tmp/mrw-native-project",
                            "skills": [
                                {
                                    "name": skill.name,
                                    "path": skill.path,
                                    "enabled": True,
                                }
                            ],
                        }
                    ]
                },
            },
            {"id": 4, "result": {"thread": {"id": "thread-1"}}},
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "item/tool/call",
                "params": {
                    "threadId": "thread-1",
                    "turnId": "turn-1",
                    "callId": "call-1",
                    "namespace": "project_retrieval",
                    "tool": "read_run",
                    "arguments": {"run_id": "run-7"},
                },
            },
            {"id": 5, "result": {"turn": {"id": "turn-1"}}},
            {
                "method": "item/agentMessage/delta",
                "params": {"threadId": "thread-1", "turnId": "turn-1", "delta": "done"},
            },
            {
                "method": "turn/completed",
                "params": {
                    "threadId": "thread-1",
                    "turn": {"id": "turn-1", "status": "completed"},
                },
            },
        ]
    )
    core = _core()
    with patch(
        "app.services.llm.codex_app_server.websockets.connect",
        return_value=_FakeConnect(websocket),
    ):
        result = asyncio.run(
            core._invoke_native_async_raw(
                endpoint="ws://127.0.0.1:1",
                prompt="read run-7",
                binding=binding,
                model="gpt-test",
                timeout_seconds=5,
                reasoning_effort="medium",
            )
        )

    assert result.content == "done"
    assert result.thread_id == "thread-1"
    assert result.turn_id == "turn-1"
    assert result.tool_call_count == 1
    assert result.tool_calls == (
        {
            "call_id": "call-1",
            "namespace": "project_retrieval",
            "tool": "read_run",
            "success": True,
        },
    )
    assert observed == [{"run_id": "run-7"}]
    requests = {
        item.get("id"): item
        for item in websocket.sent
        if "id" in item and "method" in item
    }
    assert requests[2]["method"] == "skills/extraRoots/set"
    assert requests[2]["params"] == {"extraRoots": list(binding.skill_roots)}
    assert requests[4]["params"]["dynamicTools"] == binding.dynamic_tool_specs()
    assert requests[5]["params"]["input"][1] == skill.turn_input()
    tool_response = next(
        item["result"]
        for item in websocket.sent
        if item.get("id") == 5 and "result" in item
    )
    assert tool_response["success"] is True
    assert '"run_id": "run-7"' in tool_response["contentItems"][0]["text"]


def test_native_failed_turn_does_not_return_agent_text() -> None:
    binding = build_agent_macro_pilot_binding(project_key="alpha", scope_id="session-1")
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


def test_duplicate_native_tool_call_id_reuses_response_without_reexecution() -> None:
    binding = build_agent_macro_pilot_binding(project_key="alpha", scope_id="session-1")
    observed: list[dict] = []
    tool = replace(
        binding.tools[0],
        handler=lambda arguments: observed.append(dict(arguments)) or {"ok": True},
    )
    binding = replace(binding, tools=(tool,))
    websocket = _FakeWebSocket([])
    call = {
        "method": "item/tool/call",
        "params": {
            "threadId": "thread-1",
            "turnId": "turn-1",
            "callId": "call-1",
            "namespace": "project_retrieval",
            "tool": "read_run",
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
            binding=build_agent_macro_pilot_binding(
                project_key="alpha", scope_id="session-1"
            ),
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
