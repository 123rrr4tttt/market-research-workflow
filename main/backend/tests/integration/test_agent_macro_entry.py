from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from functorial_kit import Failure

from app.api.agent_chat import (
    AgentChatTurnRequest,
    _native_macro_observation,
    _prepare_agent_core_session,
    _raise_macro_environment_failure,
    _resolve_runtime_variant,
)


def test_native_entry_projects_structured_call_and_verified_skill_mount() -> None:
    invocation = SimpleNamespace(
        thread_id="thread-1",
        turn_id="turn-1",
        tool_call_count=1,
        tool_calls=(
            {
                "call_id": "call-1",
                "namespace": "project_retrieval",
                "tool": "read_run",
                "success": True,
            },
        ),
    )
    binding = SimpleNamespace(
        skills=(
            SimpleNamespace(
                name="agent-macro-pilot",
                path="/tmp/agent-macro-pilot/SKILL.md",
                content_digest="a" * 64,
            ),
        )
    )

    observation = _native_macro_observation(invocation, binding=binding)

    assert observation["delivery_ready"] is False
    assert observation["delivery_status"] == "not_observed"
    assert observation["skill_mount_status"] == "observed"
    assert observation["tool_call_identity_status"] == "observed"
    assert observation["tool_calls"] == [
        {
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "call_id": "call-1",
            "tool_name": "project_retrieval.read_run",
            "status": "completed",
            "success": True,
            "result_status": "returned_to_native_turn",
        }
    ]


def test_runtime_variant_is_required_and_native_selection_is_explicit() -> None:
    with pytest.raises(ValueError, match="runtime_variant is required"):
        _resolve_runtime_variant(AgentChatTurnRequest(message="hello"))
    assert (
        _resolve_runtime_variant(
            AgentChatTurnRequest(
                message="continue Rapid",
                runtime_variant="agent_macro_rapid_native",
            )
        )
        == "agent_macro_rapid_native"
    )
    assert (
        _resolve_runtime_variant(
            AgentChatTurnRequest(message="old turn", runtime_variant="agent_core_v3")
        )
        == "agent_core_v3"
    )


def test_macro_environment_failure_surfaces_specific_error() -> None:
    failure = Failure(
        "capability_input_missing", "macro_environment_invalid", "package is not activated"
    )
    with pytest.raises(HTTPException) as exc:
        _raise_macro_environment_failure(failure)
    assert exc.value.status_code == 400
    assert exc.value.detail["error"]["code"] == "macro_environment_unavailable"
    assert "macro_environment_invalid" in exc.value.detail["error"]["message"]


def test_prepare_agent_core_session_records_trusted_host_identity() -> None:
    captured: dict[str, object] = {}

    class Service:
        def get_session(self, session_id):
            return {"session_id": session_id, "project_key": "p1"}

        def create_host_user_message(self, context, *, content, approval_id=None):
            captured["context"] = context
            captured["content"] = content
            return {"message_id": "m1"}

    service = Service()
    with patch("app.api.agent_chat.get_agent_session_service", return_value=service):
        _, _, session_id, project_key, context = _prepare_agent_core_session(
            AgentChatTurnRequest(message="hello", session_id="s1"),
            command="hello",
            project_key="p1",
            runtime_variant="agent_macro_native",
        )

    assert session_id == "s1"
    assert project_key == "p1"
    assert captured["content"] == "hello"
    assert context.host_thread_id == "agent-chat:s1"
    assert context.session_id == "s1"
    assert context.user_message_id
    assert context.turn_id
