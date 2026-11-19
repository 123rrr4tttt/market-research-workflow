from unittest.mock import Mock, patch

from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
from app.services.agent_core.project_tools import (
    _source_library_run_handler_factory,
    _source_library_run_spec,
)
from app.services.resource_pool.search_contract_discovery import query_discovery_parameter_schema


def test_query_tool_schema_uses_authoritative_discovery_parameters() -> None:
    spec = _source_library_run_spec({"capability_id": "ingest.source_library.run"})
    properties = spec.input_schema["properties"]
    override_schema = properties["override_params"]
    assert override_schema["properties"] == query_discovery_parameter_schema()
    item_schema = properties["items"]["items"]["oneOf"][1]
    assert item_schema["properties"]["override_params"] == override_schema
    assert "terminal result" in spec.description_for_model
    assert "project-bound Cell" in spec.description_for_model
    assert "remaining discovery budget" in spec.description_for_model
    assert "Never bypass Cell" in spec.description_for_model


def test_query_tool_forwards_item_proposals_to_original_dispatch() -> None:
    proposal = {
        "template": "https://example.org/search?q={{q}}",
        "evidence_url": "https://example.org/search",
        "reason": "observed GET form",
    }
    call = CoreToolCall(
        call_id="query-call",
        tool_name="ingest.source_library.run",
        arguments={
            "project_key": "demo",
            "items": [
                {
                    "item_key": "source.group",
                    "override_params": {
                        "query_discovery_max_requests": 1,
                        "agent_search_templates": [proposal],
                    },
                },
                "source.other",
            ],
            "override_params": {
                "query_discovery_max_requests": 2,
                "query_discovery_timeout_seconds": 3,
                "write_to_pool": False,
            },
        },
    )
    service = Mock()
    handler = _source_library_run_handler_factory(service=service)
    with (
        patch("app.services.agent_core.project_tools.session_abort_requested", return_value=False),
        patch("app.services.agent_core.project_tools.invoke_skill", return_value={"result": {"task_id": "task"}}) as dispatch,
        patch("app.services.agent_core.project_tools._record_source_library_dispatch_state", return_value={"artifact_id": "dispatch.json"}),
    ):
        result = handler(
            call,
            _source_library_run_spec({"capability_id": call.tool_name}),
            AgentCoreRequest(message="query", project_key="demo", session_id="session"),
            lambda _event: None,
        )
    assert result.status == "completed"
    assert dispatch.call_count == 2
    first, second = [invocation.kwargs for invocation in dispatch.call_args_list]
    assert first["skill_id"] == "ingest.dispatch.source_library_item"
    assert first["payload"]["override_params"] == {
        "query_discovery_max_requests": 1,
        "query_discovery_timeout_seconds": 3,
        "write_to_pool": False,
        "agent_search_templates": [proposal],
    }
    assert second["payload"]["override_params"]["query_discovery_max_requests"] == 2
    assert "agent_search_templates" not in second["payload"]["override_params"]
    assert result.structured_content["next_read_arguments"] == [{"task_id": "task"}, {"task_id": "task"}]
    assert result.structured_content["items"][0]["override_params"] == first["payload"]["override_params"]


def test_external_search_does_not_promote_unmatched_candidates() -> None:
    from app.services.resource_pool.search_template_service import execute_external_site_search

    with (
        patch("app.services.search.web.search_sources", return_value=[{
            "link": "https://example.org/article-1",
            "title": "Unrelated coverage",
            "snippet": "An unrelated article",
        }]),
    ):
        result = execute_external_site_search(
            entry_domain="example.org",
            query_terms=["river training"],
            probe_timeout=2,
            allow_term_fallback=False,
            params={},
        )
    assert len(result.raw_candidates) == 1
    assert result.selected_candidates == []
    assert result.diagnostics["candidate_filter_state"] == "term_filter_empty_no_fallback"
