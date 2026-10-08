from __future__ import annotations

from app.services.agent_core.project_tools import build_project_core_tool_registry
from app.services.agent_runtime.tool_pool import (
    AgentToolPoolAssembler,
    ToolPoolRequest,
)
from app.services.agent_sessions.service import AgentSessionService, InMemoryAgentSessionStore


def _service() -> AgentSessionService:
    return AgentSessionService(store=InMemoryAgentSessionStore())


def test_tool_pool_exposes_structured_batch_without_retired_nl_metadata() -> None:
    service = _service()
    registry = build_project_core_tool_registry(service=service)
    pool = AgentToolPoolAssembler(service=service).assemble(
        ToolPoolRequest(project_key="demo_proj")
    )
    tools = {
        str(item.get("capability_id")): item
        for item in list(pool.get("tools") or [])
    }

    assert "agent_batch.submit" in tools
    assert "agent_batch.nl_command.submit" not in tools
    structured = tools["agent_batch.submit"]
    registered = registry.get("agent_batch.submit")
    assert registered is not None
    assert structured["implemented"] is True
    assert structured["required_input"] == []
    assert set(structured["input_schema"]["properties"]) >= {"jobs", "project_key"}
    assert structured["input_schema"] == registered.input_schema
    assert structured["output_schema"] == registered.output_schema
    assert "natural-language" not in str(structured["description"]).lower()
    assert "command" not in str(structured["description"]).lower()


def test_tool_pool_exports_control_owner_actions_without_coordinator_continue() -> None:
    pool = AgentToolPoolAssembler(service=_service()).assemble(
        ToolPoolRequest(project_key="demo_proj", agent_mode="read_only")
    )
    tools = {
        str(item.get("capability_id")): item
        for item in list(pool.get("tools") or [])
    }

    assert "task.continue" not in tools
    assert tools["task.cancel"]["approval_level"] == "explicit_user_request"
    assert tools["task.cancel"]["concurrency_class"] == "write_shared"
    assert "task.retry" not in tools
    assert tools["task.summary"]["implemented"] is True
    assert tools["task.summary"]["approval_level"] == "none"
    assert tools["task.summary"]["concurrency_class"] == "read_only"


def test_tool_pool_preserves_stream_flags_and_external_mcp_status() -> None:
    pool = AgentToolPoolAssembler(service=_service()).assemble(
        ToolPoolRequest(
            project_key="demo_proj",
            feature_flags={
                "agent_batch_as_tool_enabled": False,
                "agent_stream_enabled": False,
            },
        )
    )
    tools = {
        str(item.get("capability_id")): item
        for item in list(pool.get("tools") or [])
    }

    assert tools["agent_batch.submit"]["enabled"] is False
    assert tools["agent_session.stream"]["enabled"] is False
    assert tools["agent_session.stream"]["implemented"] is True
    external_search = tools["mcp.service.external-search"]
    assert external_search["implemented"] is False
    assert external_search["service_status"] == "not_configured"
    assert external_search["configured"] is False
