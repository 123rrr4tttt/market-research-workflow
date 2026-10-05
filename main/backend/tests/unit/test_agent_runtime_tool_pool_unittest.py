from __future__ import annotations

from app.services.agent_runtime.tool_pool import (
    AgentToolPoolAssembler,
    IMPLEMENTED_TOOL_IDS,
    ToolPoolRequest,
)


def test_tool_pool_exposes_structured_batch_without_retired_nl_metadata() -> None:
    pool = AgentToolPoolAssembler().assemble(
        ToolPoolRequest(project_key="demo_proj")
    )
    tools = {
        str(item.get("capability_id")): item
        for item in list(pool.get("tools") or [])
    }

    assert "agent_batch.submit" in tools
    assert "agent_batch.nl_command.submit" not in tools
    structured = tools["agent_batch.submit"]
    assert structured["implemented"] is True
    assert structured["required_input"] == ["jobs", "project_key"]
    assert "natural-language" not in str(structured["description"]).lower()
    assert "command" not in str(structured["description"]).lower()


def test_tool_pool_exports_control_owner_actions_without_coordinator_continue() -> None:
    pool = AgentToolPoolAssembler().assemble(
        ToolPoolRequest(project_key="demo_proj", agent_mode="read_only")
    )
    tools = {
        str(item.get("capability_id")): item
        for item in list(pool.get("tools") or [])
    }

    assert "task.continue" not in IMPLEMENTED_TOOL_IDS
    assert "task.continue" not in tools
    assert tools["task.cancel"]["approval_level"] == "explicit_user_request"
    assert tools["task.cancel"]["concurrency_class"] == "write_shared"
    assert tools["task.retry"]["approval_level"] == "explicit_user_request"
    assert tools["task.summary"]["implemented"] is True
    assert tools["task.summary"]["approval_level"] == "none"
    assert tools["task.summary"]["concurrency_class"] == "read_only"
