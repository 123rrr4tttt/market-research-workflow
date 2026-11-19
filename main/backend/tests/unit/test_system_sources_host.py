from __future__ import annotations

from pathlib import Path

from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore
from app.services.agent_core.project_tools import build_project_core_tool_registry
from app.services.agent_runtime.system_projection_contracts import SYSTEM_INSPECT_TOOL_NAME, SystemRelation
from app.services.agent_runtime.system_projection import (
    build_system_projection,
    inspect_system_projection,
)
from app.services.agent_runtime.system_sources_host import SYSTEM_OBJECTS


AGENT_TOOL_REFS = (
    "agent_runtime.capability.catalog",
    "agent_runtime.tool.search",
    "agent_runtime.tool_pool.list",
    "skill.search",
    "skill.load",
    "agent_batch.submit",
    "task.cancel",
)
PERSISTENCE_TOOL_REFS = (
    "agent_session.context.read",
    "agent_artifact.search",
    "agent_artifact.read",
    "agent_session.resume_bundle",
    "agent_task.plan.append",
    "agent_long_task.stage.read",
    "agent_long_task.stage.update",
    "task.summary",
)
REGISTRATION_TOOL_REFS = (
    "agent_macro.registration_package.create",
    "agent_macro.registration_package.readback",
    "agent_macro.registration_package.activate",
)
MCP_TOOL_REFS = (
    "mcp.service.catalog",
    "mcp.tools.list",
    "mcp.tool.call",
)
WORKBENCH_TOOL_REFS = (
    "concept_workbench.method.read",
    "concept_workbench.module.read",
    "concept_workbench.project.init",
    "concept_workbench.project.scan",
    "concept_workbench.project.materials",
    "concept_workbench.project.shapes",
    "concept_workbench.project.inspect",
    "concept_workbench.project.check",
    "concept_workbench.project.sync",
    "concept_workbench.project.verify",
)
ORIGINAL_TOOL_REFS = frozenset({
    "agent_runtime.capability.catalog",
    "agent_runtime.tool.search",
    "agent_session.context.read",
    "agent_artifact.search",
    "agent_artifact.read",
})
P0_DISCOVERY_RECOVERY_TOOL_REFS = frozenset({
    "agent_runtime.tool_pool.list",
    "skill.search",
    "skill.load",
    "agent_session.resume_bundle",
    "agent_task.plan.append",
    "agent_long_task.stage.read",
    "agent_long_task.stage.update",
    "task.summary",
    "task.cancel",
})
P1_BATCH_TOOL_REFS = frozenset({"agent_batch.submit"})
P2_TOOL_REFS = frozenset({
    "agent_runtime.tool_pool.list",
    "skill.search",
    "skill.load",
    "agent_batch.submit",
    "agent_session.resume_bundle",
    "agent_task.plan.append",
    "agent_long_task.stage.read",
    "agent_long_task.stage.update",
    "task.summary",
    "task.cancel",
    *REGISTRATION_TOOL_REFS,
    *MCP_TOOL_REFS,
    *WORKBENCH_TOOL_REFS,
})
EXPECTED_P2_TOOL_CONTROL = {
    "agent_runtime.tool_pool.list": ("read_only", "allow", "parallel"),
    "skill.search": ("read_only", "allow", "parallel"),
    "skill.load": ("read_only", "allow", "parallel"),
    "agent_batch.submit": ("write_external", "ask", "serial"),
    "agent_session.resume_bundle": ("read_only", "allow", "parallel"),
    "agent_task.plan.append": ("write_shared", "allow", "serial"),
    "agent_long_task.stage.read": ("read_only", "allow", "parallel"),
    "agent_long_task.stage.update": ("write_shared", "allow", "serial"),
    "task.summary": ("read_only", "allow", "parallel"),
    "task.cancel": ("write_shared", "explicit_user_request", "serial"),
    "agent_macro.registration_package.create": ("write_shared", "allow", "serial"),
    "agent_macro.registration_package.readback": ("read_only", "allow", "parallel"),
    "agent_macro.registration_package.activate": ("write_shared", "allow", "serial"),
    "mcp.service.catalog": ("read_only", "allow", "parallel"),
    "mcp.tools.list": ("read_only", "allow", "parallel"),
    "mcp.tool.call": ("read_only", "allow", "parallel"),
    "concept_workbench.method.read": ("read_only", "allow", "serial"),
    "concept_workbench.module.read": ("read_only", "allow", "serial"),
    **{
        f"concept_workbench.project.{operation}": ("write_shared", "allow", "serial")
        for operation in (
            "init", "scan", "materials", "shapes", "inspect", "check", "sync", "verify",
        )
    },
}


def _source(ref: str):
    return next(source for source in SYSTEM_OBJECTS if source.ref == ref)


def _assert_source_ref_exists(source_ref: str) -> None:
    path_text, _, symbol = source_ref.partition("#")
    repo_root = Path(__file__).resolve().parents[4]
    path = repo_root / path_text
    assert path.is_file(), source_ref
    if not symbol:
        return
    class_name, _, method_name = symbol.partition(".")
    text = path.read_text(encoding="utf-8")
    assert class_name in text, source_ref
    if method_name:
        assert f"def {method_name}(" in text, source_ref


def test_host_declares_two_top_responsibilities_and_three_facilities() -> None:
    top_refs = [source.ref for source in SYSTEM_OBJECTS[:2]]
    facility_refs = [source.ref for source in SYSTEM_OBJECTS[2:]]
    assert top_refs == ["mrw.agent", "mrw.persistence"]
    assert facility_refs == [
        "mrw.agent.registration",
        "mrw.agent.mcp",
        "mrw.agent.workbench",
    ]
    assert all(source.owner_ref and source.source_refs for source in SYSTEM_OBJECTS)
    assert all(len(set(source.purpose_terms)) == len(source.purpose_terms) for source in SYSTEM_OBJECTS)
    assert all(any(term.isascii() for term in source.purpose_terms) for source in SYSTEM_OBJECTS)
    assert all(any(not term.isascii() for term in source.purpose_terms) for source in SYSTEM_OBJECTS)


def test_declared_source_refs_point_to_real_code_symbols() -> None:
    source_refs = tuple(
        source_ref for source in SYSTEM_OBJECTS for source_ref in source.source_refs
    )
    assert len(source_refs) == len(set(source_refs))
    for source_ref in source_refs:
        _assert_source_ref_exists(source_ref)


def test_agent_and_persistence_relations_follow_verified_call_chains() -> None:
    agent = _source("mrw.agent")
    persistence = _source("mrw.persistence")
    assert agent.relations == (
        SystemRelation("uses", "mrw.persistence"),
        SystemRelation("contains", "mrw.agent.registration"),
        SystemRelation("contains", "mrw.agent.mcp"),
        SystemRelation("contains", "mrw.agent.workbench"),
    )
    assert persistence.relations == (SystemRelation("consumed_by", "mrw.agent"),)
    assert all(source.relations == () for source in SYSTEM_OBJECTS[2:])


def test_agent_parent_does_not_duplicate_facility_tool_refs() -> None:
    agent = _source("mrw.agent")
    facility_tools = {
        tool_name
        for source in SYSTEM_OBJECTS[2:]
        for tool_name in source.tool_refs
    }
    assert set(agent.tool_refs).isdisjoint(facility_tools)


def test_host_tools_are_exact_readonly_registry_entries(tmp_path) -> None:  # type: ignore[no-untyped-def]
    assert _source("mrw.agent").tool_refs == AGENT_TOOL_REFS
    assert _source("mrw.persistence").tool_refs == PERSISTENCE_TOOL_REFS
    assert _source("mrw.agent.registration").tool_refs == REGISTRATION_TOOL_REFS
    assert _source("mrw.agent.mcp").tool_refs == MCP_TOOL_REFS
    assert _source("mrw.agent.workbench").tool_refs == WORKBENCH_TOOL_REFS
    assert all(SYSTEM_INSPECT_TOOL_NAME not in source.tool_refs for source in SYSTEM_OBJECTS)

    service = AgentSessionService(store=InMemoryAgentSessionStore())
    registry = build_project_core_tool_registry(service=service)
    for tool_name in (*AGENT_TOOL_REFS, *PERSISTENCE_TOOL_REFS):
        spec = registry.get(tool_name)
        assert spec is not None
        assert spec.name == tool_name
        assert spec.input_schema.get("type") == "object"
        assert spec.risk
        assert spec.permission


def test_p2_adds_exactly_twenty_six_exact_tool_associations() -> None:
    declared = {
        tool_name
        for source in SYSTEM_OBJECTS
        for tool_name in source.tool_refs
    }
    assert len(ORIGINAL_TOOL_REFS) == 5
    assert declared - ORIGINAL_TOOL_REFS == set(P2_TOOL_REFS)
    assert len(P2_TOOL_REFS) == 26


def test_priority_table_records_nine_discovery_one_batch_and_sixteen_facilities() -> None:
    facility_tools = {
        tool_name
        for source in SYSTEM_OBJECTS[2:]
        for tool_name in source.tool_refs
    }
    assert len(P0_DISCOVERY_RECOVERY_TOOL_REFS) == 9
    assert len(P1_BATCH_TOOL_REFS) == 1
    assert len(facility_tools) == 16
    assert P0_DISCOVERY_RECOVERY_TOOL_REFS | P1_BATCH_TOOL_REFS | facility_tools == set(P2_TOOL_REFS)
    assert not P0_DISCOVERY_RECOVERY_TOOL_REFS & P1_BATCH_TOOL_REFS
    assert not P0_DISCOVERY_RECOVERY_TOOL_REFS & facility_tools
    assert not P1_BATCH_TOOL_REFS & facility_tools
    agent = _source("mrw.agent")
    persistence = _source("mrw.persistence")
    assert "task.cancel" in agent.tool_refs
    assert "task.cancel" not in persistence.tool_refs


def test_responsibility_coverage_and_tool_availability_are_distinct() -> None:
    service = AgentSessionService(store=InMemoryAgentSessionStore())
    registry = build_project_core_tool_registry(service=service)
    projection = build_system_projection(SYSTEM_OBJECTS, registry.list_specs())

    for source in SYSTEM_OBJECTS:
        ref = source.ref
        page = inspect_system_projection(projection, {"ref": ref}, None)
        item = page["items"][0]
        assert item["coverage"] == "mapped"
        assert item["availability"] == "mounted"
        assert item["relations"] == []
        assert page["gaps"] == []

    for source in SYSTEM_OBJECTS:
        for tool_name in source.tool_refs:
            page = inspect_system_projection(projection, {"ref": f"tool:{tool_name}"}, None)
            item = page["items"][0]
            assert item["availability"] == "mounted"
            assert item["coverage"] == "mapped"
            assert len(item["system_refs"]) == 1
            assert item["owner_ref"] == f"project_tool:{tool_name}"


def test_p2_registry_control_attributes_are_preserved() -> None:
    service = AgentSessionService(store=InMemoryAgentSessionStore())
    registry = build_project_core_tool_registry(service=service)
    assert len(EXPECTED_P2_TOOL_CONTROL) == 26
    for tool_name, expected in EXPECTED_P2_TOOL_CONTROL.items():
        spec = registry.get(tool_name)
        assert spec is not None
        assert (spec.risk, spec.permission, spec.concurrency) == expected


def test_chinese_purpose_aliases_rank_directed_queries() -> None:
    service = AgentSessionService(store=InMemoryAgentSessionStore())
    registry = build_project_core_tool_registry(service=service)
    projection = build_system_projection(SYSTEM_OBJECTS, registry.list_specs())
    cases = {
        "能力发现": "mrw.agent",
        "工具池": "mrw.agent",
        "技能加载": "mrw.agent",
        "任务恢复": "mrw.persistence",
        "长任务阶段": "mrw.persistence",
        "取消任务": "mrw.agent",
        "注册包": "mrw.agent.registration",
        "接线激活": "mrw.agent.registration",
        "MCP外部工具": "mrw.agent.mcp",
        "架构工作台": "mrw.agent.workbench",
        "原贡献CLI": "mrw.agent.workbench",
    }
    for query, expected_ref in cases.items():
        page = inspect_system_projection(projection, {"query": query}, None)
        assert page["items"][0]["ref"] == expected_ref
