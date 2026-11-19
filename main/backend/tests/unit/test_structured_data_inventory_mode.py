from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
from app.services.agent_core.registry import CoreToolRegistry
from app.services.agent_core.tool_contribution import register_project_tool_contributions
from app.services.agent_runtime.read_only_tools import read_only_project_tool_sources
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore


def _execute(searcher, *, arguments, message="native macro host tool call"):
    service = AgentSessionService(store=InMemoryAgentSessionStore())
    registry = CoreToolRegistry()
    source = next(
        source
        for source in read_only_project_tool_sources(
            service=service, structured_data_searcher=searcher
        )
        if source.tool_spec.name == "project.structured_data.search"
    )
    assert register_project_tool_contributions(registry, (source,)) is None
    return registry.execute_tool(
        tool_call=CoreToolCall(
            tool_name="project.structured_data.search",
            arguments=arguments,
            call_id="structured-mode-call",
        ),
        request=AgentCoreRequest(
            message=message,
            session_id="session-1",
            project_key="demo_proj",
        ),
        emit=lambda _event: None,
    )


def test_inventory_mode_ignores_request_message_and_keeps_empty_query() -> None:
    reads = []

    def searcher(**arguments):
        reads.append(arguments)
        return {
            "project_key": "demo_proj",
            "query": "",
            "query_mode": "inventory",
            "inventory": [{"dataset": "materials", "sample_count": 0, "total_rows": 7}],
            "total_stored_rows": 7,
        }

    result = _execute(searcher, arguments={"mode": "inventory"})
    assert reads == [{"project_key": "demo_proj", "query": None, "limit": 12, "datasets": None}]
    assert result.status == "completed"
    content = result.structured_content["result"]
    assert content["query"] == ""
    assert content["query_mode"] == "inventory"
    assert content["inventory"][0]["total_rows"] == 7
    assert "inventory" in result.model_summary


def test_search_mode_keeps_legacy_message_fallback() -> None:
    reads = []

    def searcher(**arguments):
        reads.append(arguments)
        return {"project_key": "demo_proj", "query_mode": "search", "items": []}

    result = _execute(searcher, arguments={"mode": "search", "query": ""}, message="legacy query")
    assert reads == [{"project_key": "demo_proj", "query": "legacy query", "limit": 12, "datasets": None}]
    assert result.status == "completed"
    assert result.structured_content["result"]["query_mode"] == "search"


def test_schema_exposes_only_inventory_and_search_modes() -> None:
    service = AgentSessionService(store=InMemoryAgentSessionStore())
    source = next(
        source
        for source in read_only_project_tool_sources(service=service)
        if source.tool_spec.name == "project.structured_data.search"
    )
    assert source.tool_spec.input_schema["properties"]["mode"]["enum"] == ["search", "inventory"]
    assert source.tool_spec.input_schema["additionalProperties"] is False
