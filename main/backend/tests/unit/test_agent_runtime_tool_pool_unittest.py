from __future__ import annotations

from app.services.agent_runtime.tool_pool import (
    AgentToolPoolAssembler,
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
