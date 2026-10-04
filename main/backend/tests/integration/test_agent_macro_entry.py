from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.agent_chat import (
    AgentChatTurnRequest,
    _native_macro_observation,
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
