from __future__ import annotations

from app.services.agent_core.project_tools import build_project_core_tool_registry
from app.services.agent_runtime.system_sources_materials import SYSTEM_OBJECTS
from app.services.agent_runtime.system_projection import (
    build_system_projection,
    inspect_system_projection,
)
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore


def _objects() -> dict[str, object]:
    return {source.ref: source for source in SYSTEM_OBJECTS}


def test_materials_declare_three_responsibilities_with_exact_registry_tools() -> None:
    objects = _objects()
    assert set(objects) == {"mrw.sources", "mrw.ingestion", "mrw.retrieval"}
    expected = {
        "mrw.sources": {
            "source.history.read",
            "source.discovery.plan",
            "source.web.search",
            "source.candidate.review",
            "source_library.item.list",
            "source_library.item.search",
            "source_library.item.inspect",
        },
        "mrw.ingestion": {
            "ingest.status.read",
            "ingest.source_library.run",
            "ingest.url_pool.submit",
            "ingest.url_pool.status",
            "skill.ingest.dispatch.source_library_item",
            "skill.ingest.dispatch.market_collect",
            "skill.agent_batch.dispatch.source_library_item",
            "skill.agent_batch.dispatch.market_collect",
        },
        "mrw.retrieval": {
            "project_retrieval.current",
            "project_retrieval.rapid_proposal.save",
            "project_retrieval.rapid_proposal.readback",
            "skill.project_retrieval.current",
            "skill.project_retrieval.preview",
            "skill.project_retrieval.start",
            "skill.project_retrieval.read_run",
            "skill.project_retrieval.continue_saved_frontier",
            "skill.project_retrieval.formalize_material",
            "information_topology.read",
            "project.context.bundle",
            "project.context.resource.read",
            "project.graph.search",
            "project.structured_data.item.read",
            "project.structured_data.items.read",
            "project.structured_data.quality_audit",
            "project.structured_data.search",
            "project.structured_graph.query",
            "project.summary.read",
            "agent_investigation.leads.append",
            "agent_investigation.trace.read",
            "chain.expand",
        },
    }
    for ref, tool_names in expected.items():
        source = objects[ref]
        assert source is not None
        assert source.owner_ref
        assert source.source_refs
        assert source.purpose_terms
        assert set(source.tool_refs) == tool_names


def test_material_relations_are_source_grounded_and_not_symmetric_filler() -> None:
    objects = _objects()
    sources = objects["mrw.sources"]
    ingestion = objects["mrw.ingestion"]
    retrieval = objects["mrw.retrieval"]
    assert [(relation.kind, relation.target_ref) for relation in sources.relations] == [
        ("consumed_by", "mrw.ingestion")
    ]
    assert [(relation.kind, relation.target_ref) for relation in ingestion.relations] == [
        ("consumed_by", "mrw.retrieval")
    ]
    assert [(relation.kind, relation.target_ref) for relation in retrieval.relations] == [
        ("uses", "mrw.ingestion")
    ]


def test_declared_material_tools_exist_in_in_memory_registry() -> None:
    service = AgentSessionService(store=InMemoryAgentSessionStore())
    registry = build_project_core_tool_registry(service=service)
    registered = {spec.name for spec in registry.list_specs()}
    declared = {
        tool_name
        for source in SYSTEM_OBJECTS
        for tool_name in source.tool_refs
    }
    missing = declared - registered
    assert missing == set()


def test_declared_tool_risk_and_permission_boundaries_match_registry() -> None:
    service = AgentSessionService(store=InMemoryAgentSessionStore())
    registry = build_project_core_tool_registry(service=service)
    specs = {spec.name: spec for spec in registry.list_specs()}
    read_only = {
        "source.history.read",
        "information_topology.read",
        "project.context.bundle",
        "project.context.resource.read",
        "project.graph.search",
        "project.structured_data.item.read",
        "project.structured_data.items.read",
        "project.structured_data.quality_audit",
        "project.structured_data.search",
        "project.structured_graph.query",
        "project.summary.read",
        "agent_investigation.trace.read",
    }
    session_write = {"agent_investigation.leads.append", "chain.expand"}
    dispatch = {
        "skill.ingest.dispatch.source_library_item",
        "skill.ingest.dispatch.market_collect",
        "skill.agent_batch.dispatch.source_library_item",
        "skill.agent_batch.dispatch.market_collect",
    }
    for name in read_only:
        assert (specs[name].risk, specs[name].permission) == ("read_only", "allow")
    for name in session_write:
        assert (specs[name].risk, specs[name].permission) == ("write_shared", "allow")
    for name in dispatch:
        assert (specs[name].risk, specs[name].permission) == ("write_shared", "ask")


def test_fixed_purpose_queries_navigate_to_material_responsibilities() -> None:
    service = AgentSessionService(store=InMemoryAgentSessionStore())
    registry = build_project_core_tool_registry(service=service)
    projection = build_system_projection(SYSTEM_OBJECTS, registry.list_specs())
    queries_by_expected_ref = {
        "mrw.sources": ("source decision history", "来源决策历史"),
        "mrw.ingestion": ("collection dispatch", "采集派发"),
        "mrw.retrieval": (
            "stored structured data",
            "stored graph query",
            "stored material readback",
            "stored context resource",
            "线索追踪",
        ),
    }
    for expected_ref, queries in queries_by_expected_ref.items():
        for query in queries:
            result = inspect_system_projection(projection, {"query": query}, None)
            items = result["items"]
            assert items
            assert items[0]["ref"] == expected_ref


def test_responsibility_expansion_reaches_fixed_high_priority_tools() -> None:
    service = AgentSessionService(store=InMemoryAgentSessionStore())
    registry = build_project_core_tool_registry(service=service)
    projection = build_system_projection(SYSTEM_OBJECTS, registry.list_specs())
    expected_tools_by_ref = {
        "mrw.sources": "source.history.read",
        "mrw.ingestion": "ingest.source_library.run",
        "mrw.retrieval": "project.graph.search",
    }
    for ref, expected_tool in expected_tools_by_ref.items():
        result = inspect_system_projection(projection, {"ref": ref, "limit": 20}, None)
        reached = {
            *(
                relation["target_ref"]
                for relation in result["relations"]
                if relation["source_ref"] == ref
            ),
            *(item["ref"] for item in result["items"]),
        }
        assert f"tool:{expected_tool}" in reached
