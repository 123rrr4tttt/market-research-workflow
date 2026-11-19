from __future__ import annotations

import ast
import json
from dataclasses import replace
from itertools import count
from pathlib import Path

import pytest

from app.services.agent_core.contracts import AgentCoreRequest, CoreToolCall
from app.services.agent_core.macro_host import AgentMacroHostService, MacroHostError
from app.services.agent_core.project_tools import build_project_core_tool_registry
from app.services.agent_runtime.system_projection import (
    SYSTEM_ID,
    SYSTEM_INSPECT_TOOL_NAME,
    SystemProjectionStaleError,
    build_system_projection,
    inspect_system_projection,
)
from app.services.agent_runtime.system_sources_host import SYSTEM_OBJECTS as HOST_OBJECTS
from app.services.agent_runtime.system_sources_materials import SYSTEM_OBJECTS as MATERIAL_OBJECTS
from app.services.agent_runtime.system_sources_work import SYSTEM_OBJECTS as WORK_OBJECTS
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore


pytestmark = pytest.mark.integration
OBJECTS = (*MATERIAL_OBJECTS, *WORK_OBJECTS, *HOST_OBJECTS)
RESPONSIBILITIES = {
    "mrw.sources", "mrw.ingestion", "mrw.retrieval", "mrw.workflow",
    "mrw.writing", "mrw.consumers", "mrw.agent", "mrw.persistence",
}
FACILITIES = {"mrw.agent.registration", "mrw.agent.mcp", "mrw.agent.workbench"}
REPO = Path(__file__).resolve().parents[4]


def _execute(registry, name, arguments=None, *, project_key=None, session_id="observation"):
    return registry.execute_tool(
        tool_call=CoreToolCall(tool_name=name, arguments=arguments or {}, call_id="acceptance-call"),
        request=AgentCoreRequest(message="inspect the system", session_id=session_id, project_key=project_key),
        emit=lambda _event: None,
    )


def _pages(registry, arguments):
    pages = []
    while True:
        result = _execute(registry, SYSTEM_INSPECT_TOOL_NAME, arguments)
        assert result.status == "completed", result.to_dict()
        page = result.structured_content["result"]
        assert len(page["items"]) + len(page["relations"]) <= page["limit"]
        assert len(json.dumps(result.to_dict(), ensure_ascii=False, separators=(",", ":")).encode()) <= (
            8192 if page["limit"] == 8 else 16384
        )
        pages.append(page)
        if page["next"] is None:
            assert page["truncated"] is False
            return pages
        assert page["next"]["offset"] > page["offset"]
        assert page["next"]["limit"] == page["limit"]
        arguments = page["next"]
        assert len(pages) < 500, "pagination must make progress"


def _assert_python_source_symbol(path: Path, symbol: str) -> None:
    nodes = ast.parse(path.read_text(encoding="utf-8")).body
    for part in symbol.split("."):
        declaration = next(
            (node for node in nodes
             if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == part),
            None,
        )
        assert declaration is not None, f"{path}#{symbol} is not a declared code symbol"
        nodes = declaration.body


def test_eight_declarations_have_real_sources_and_resolvable_cross_relations():
    refs = {obj.ref for obj in OBJECTS}
    assert refs == RESPONSIBILITIES | FACILITIES
    assert len(OBJECTS) == len(refs)
    children = {rel.target_ref for obj in OBJECTS for rel in obj.relations if rel.kind == "contains"}
    assert refs - children == RESPONSIBILITIES
    assert children == FACILITIES
    for obj in OBJECTS:
        assert obj.owner_ref and obj.source_refs
        for source in obj.source_refs:
            filename, _, symbol = source.partition("#")
            path = REPO / filename
            assert path.exists(), source
            if path.suffix == ".py" and symbol:
                _assert_python_source_symbol(path, symbol)
        assert all(rel.target_ref in refs for rel in obj.relations)
        if obj.ref in RESPONSIBILITIES:
            assert any(rel.target_ref in refs and rel.target_ref != obj.ref for rel in obj.relations)


def test_actual_registry_navigates_eight_responsibilities_without_reading_project_materials():
    reads = []
    sessions = AgentSessionService(store=InMemoryAgentSessionStore())
    registry = build_project_core_tool_registry(
        service=sessions, source_library_lister=lambda project: reads.append(project) or [],
    )
    assert sum(spec.name == SYSTEM_INSPECT_TOOL_NAME for spec in registry.list_specs()) == 1
    pages = _pages(registry, {"ref": SYSTEM_ID, "limit": 3})
    items = [item for page in pages for item in page["items"]]
    relations = [relation for page in pages for relation in page["relations"]]
    assert {item["ref"] for item in items if item["kind"] == "responsibility"} == RESPONSIBILITIES
    assert not any(item["ref"] in FACILITIES for item in items)
    assert len({item["ref"] for item in items}) == len(items)
    assert len({(rel["source_ref"], rel["kind"], rel["target_ref"]) for rel in relations}) == len(relations)
    assert len(items) + len(relations) == pages[0]["total"]
    assert len({page["revision"] for page in pages}) == 1
    consumers = next(item for item in items if item["ref"] == "mrw.consumers")
    assert (consumers["coverage"], consumers["availability"]) == ("mapped", "metadata_only")
    assert all(item["coverage"] == "mapped" for item in items if item["kind"] == "responsibility")
    assert all(item["relations"] == [] for item in items)
    assert reads == []


def test_every_mounted_tool_has_exact_reverse_mapping_or_a_readable_unmapped_gap():
    registry = build_project_core_tool_registry(service=AgentSessionService(store=InMemoryAgentSessionStore()))
    unmapped = set()
    for spec in registry.list_specs():
        pages = _pages(registry, {"ref": f"tool:{spec.name}", "limit": 20})
        item = next(item for page in pages for item in page["items"] if item["ref"] == f"tool:{spec.name}")
        expected = {obj.ref for obj in OBJECTS if spec.name in obj.tool_refs}
        if spec.name == SYSTEM_INSPECT_TOOL_NAME:
            expected.add(SYSTEM_ID)
        assert set(item["system_refs"]) == expected
        assert item["availability"] == "mounted"
        assert item["risk"] == spec.risk
        assert item["permission"] == spec.permission
        assert item["project_service_id"] == spec.project_service_id
        assert item["owner_ref"] == f"project_tool:{spec.project_service_id or spec.name}"
        assert item["schema_ref"] == f"tool:{spec.name}#input_schema"
        assert "input_schema" not in item
        if not expected:
            unmapped.add(spec.name)
            assert item["coverage"] == "gap"
            assert any(gap["ref"] == item["ref"] for page in pages for gap in page["gaps"])
    assert unmapped == set(), "every current mounted tool requires a source-grounded semantic mapping"
    root_page = _pages(registry, {"limit": 8})[0]
    root = next(item for item in root_page["items"] if item["ref"] == SYSTEM_ID)
    assert root["unmapped_tool_count"] == len(unmapped)
    coverage_pages = _pages(registry, {"ref": root["coverage_ref"], "limit": 1})
    gap_tools = [item["tool_name"] for page in coverage_pages for item in page["items"] if item["kind"] == "tool"]
    assert len(gap_tools) == len(set(gap_tools))
    assert set(gap_tools) == unmapped


@pytest.mark.parametrize(
    ("parent", "tool"),
    [
        ("mrw.sources", "source.history.read"),
        ("mrw.retrieval", "project.structured_data.search"),
        ("mrw.retrieval", "project.context.resource.read"),
        ("mrw.retrieval", "agent_investigation.trace.read"),
        ("mrw.workflow", "skill.workflow_graph.get_run"),
        ("mrw.workflow", "skill.workflow_graph.template.version.get"),
        ("mrw.writing", "writing.document.read"),
        ("mrw.persistence", "agent_session.resume_bundle"),
        ("mrw.agent", "skill.load"),
        ("mrw.agent.registration", "agent_macro.registration_package.readback"),
        ("mrw.agent.mcp", "mcp.tools.list"),
        ("mrw.agent.workbench", "concept_workbench.method.read"),
    ],
)
def test_filled_paths_expand_with_complete_bounded_pages_and_reverse_identity(parent, tool):
    reads = []
    registry = build_project_core_tool_registry(
        service=AgentSessionService(store=InMemoryAgentSessionStore()),
        source_library_lister=lambda project: reads.append(project) or [],
    )
    pages = _pages(registry, {"ref": parent, "limit": 8})
    refs = [item["ref"] for page in pages for item in page["items"]]
    assert f"tool:{tool}" in refs
    assert len(refs) == len(set(refs))
    tool_pages = _pages(registry, {"ref": f"tool:{tool}", "limit": 1})
    tool_item = tool_pages[0]["items"][0]
    assert parent in tool_item["system_refs"]
    assert tool_item["coverage"] == "mapped"
    assert all(page["gaps"] == [] for page in pages + tool_pages)
    directory = _execute(registry, "agent_runtime.tool.search", {"query": tool, "limit": 20})
    assert directory.status == "completed", directory.to_dict()
    matches = [
        item for item in directory.structured_content["result"]["items"]
        if (item.get("tool_name") or item.get("capability_id") or item.get("name")) == tool
    ]
    assert matches, f"original directory must retain {tool}"
    assert all(parent in item["system_refs"] for item in matches)
    assert reads == []


def test_agent_expands_facilities_without_flattening_them_into_root():
    registry = build_project_core_tool_registry(
        service=AgentSessionService(store=InMemoryAgentSessionStore())
    )
    pages = _pages(registry, {"ref": "mrw.agent", "limit": 1})
    contained = {
        relation["target_ref"] for page in pages for relation in page["relations"]
        if relation["kind"] == "contains"
    }
    assert contained == FACILITIES
    assert FACILITIES <= {item["ref"] for page in pages for item in page["items"]}


def test_original_operation_still_requires_approval_and_owner_failures_are_not_empty():
    def failing_reader(_project):
        raise RuntimeError("original source owner unavailable")

    registry = build_project_core_tool_registry(
        service=AgentSessionService(store=InMemoryAgentSessionStore()), source_library_lister=failing_reader,
    )
    operation = next(item for page in _pages(registry, {"ref": "tool:ingest.source_library.run"}) for item in page["items"]
                     if item["ref"] == "tool:ingest.source_library.run")
    assert operation["permission"] == "ask"
    denied = _execute(registry, "ingest.source_library.run")
    assert denied.status == "needs_approval"
    failed = _execute(registry, "source_library.item.list")
    assert failed.status == "failed"
    assert failed.error["message"] == "original source owner unavailable"


def test_changed_original_spec_invalidates_projection_continuation():
    registry = build_project_core_tool_registry(service=AgentSessionService(store=InMemoryAgentSessionStore()))
    specs = registry.list_specs()
    before = build_system_projection(OBJECTS, specs)
    page = inspect_system_projection(before, {"ref": SYSTEM_ID, "limit": 1}, None)
    changed = tuple(replace(spec, permission="deny") if spec.name == "source_library.item.list" else spec for spec in specs)
    after = build_system_projection(OBJECTS, changed)
    assert before.revision != after.revision
    with pytest.raises(SystemProjectionStaleError):
        inspect_system_projection(after, page["next"], None)


def test_default_host_guidance_navigation_directory_and_two_original_readers(monkeypatch):
    import app.services.source_library as source_library

    reads = []

    def list_effective_items(*, scope, project_key):
        reads.append((scope, project_key))
        return [{"item_key": "source.example", "name": "Example source", "description": "controlled original read",
                 "channel_key": "official_site", "enabled": True, "scope": "project"}]

    monkeypatch.setattr(source_library, "list_effective_items", list_effective_items)
    sessions = AgentSessionService(store=InMemoryAgentSessionStore())
    host = AgentMacroHostService(project_checker=lambda key: key == "project-a", agent_session_service=sessions)
    prepared = host.prepare(project_key="project-a")
    assert SYSTEM_INSPECT_TOOL_NAME in prepared["systemInstructions"]
    mounted = {(namespace["name"], tool["name"]) for namespace in prepared["dynamicTools"]
               for tool in namespace.get("tools", [])}
    assert ("agent_runtime_system", "inspect") in mounted
    bound = host.bind(binding_id=prepared["bindingId"], thread_id="acceptance-thread")
    admission = host.prepare_turn(thread_id="acceptance-thread")
    assert prepared["systemInstructions"] == bound["systemInstructions"] == admission["systemInstructions"]
    host.record_input(thread_id="acceptance-thread", turn_id="acceptance-turn", content="inspect sources and session",
                      admission_id=admission["admissionId"])

    calls = count(1)

    def dispatch(namespace, tool, arguments=None):
        response = host.dispatch(thread_id="acceptance-thread", turn_id="acceptance-turn",
                                 call_id=f"acceptance-{next(calls)}", namespace=namespace, tool=tool,
                                 arguments=arguments or {})
        assert response["success"] is True, response
        return response["resultProjection"]["structured_content"]["result"]

    navigation = dispatch("agent_runtime_system", "inspect", {"query": "来源库"})
    assert any(item["ref"] == "mrw.sources" for item in navigation["items"])
    assert reads == []
    expanded = dispatch("agent_runtime_system", "inspect", {"ref": "mrw.sources", "limit": 20})
    assert any(item["ref"] == "tool:source_library.item.list" for item in expanded["items"])
    directory = dispatch("agent_runtime_tool", "search", {"query": "source_library.item.list", "limit": 20})
    assert any("mrw.sources" in item["system_refs"] for item in directory["items"])
    listed = dispatch("source_library_item", "list")
    assert listed["items"][0]["item_key"] == "source.example"
    assert reads == [("effective", "project-a")]
    persistence = dispatch("agent_runtime_system", "inspect", {"ref": "mrw.persistence", "limit": 20})
    assert any(item["ref"] == "tool:agent_session.context.read" for item in persistence["items"])
    context = dispatch("agent_session_context", "read")
    assert context["session"]["session_id"] == bound["sessionId"]
    host.end_turn(thread_id="acceptance-thread", turn_id="acceptance-turn")
    ended = host.dispatch(thread_id="acceptance-thread", turn_id="acceptance-turn", call_id="ended-inspect",
                          namespace="agent_runtime_system", tool="inspect", arguments={})
    assert ended["success"] is False
    assert "turn ended" in ended["contentItems"][0]["text"]
    with pytest.raises(MacroHostError, match="binding not found"):
        host.environment(binding_id="missing-binding")
