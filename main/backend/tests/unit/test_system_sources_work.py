from __future__ import annotations

import ast
from pathlib import Path

from app.services.agent_core.contracts import CoreToolSpec
from app.services.agent_core.project_tools import build_project_core_tool_registry
from app.services.agent_sessions.service import AgentSessionService
from app.services.agent_sessions.store import InMemoryAgentSessionStore
from app.services.agent_runtime.system_projection import (
    build_system_projection,
    inspect_system_projection,
)
from app.services.agent_runtime.system_projection_contracts import SystemRelation
from app.services.agent_runtime.system_sources_work import SYSTEM_OBJECTS
from app.services.skill_runtime import SkillRuntime


REPO_ROOT = Path(__file__).resolve().parents[4]
WORKFLOW_SKILL_TOOLS = {
    "skill.workflow_graph.compile": "workflow_graph.compiler",
    "skill.workflow_graph.run": "workflow_graph.runtime",
    "skill.workflow_graph.get_run": "workflow_graph.runtime",
    "skill.workflow_graph.get_run_events": "workflow_graph.runtime",
    "skill.workflow_graph.get_run_agent_session": "workflow_graph.runtime",
    "skill.workflow_graph.replay_run": "workflow_graph.runtime",
    "skill.workflow_graph.get_compiled": "workflow_graph.compiler",
    "skill.workflow_graph.template.list": "workflow_graph.compiler",
    "skill.workflow_graph.template.create": "workflow_graph.compiler",
    "skill.workflow_graph.template.get": "workflow_graph.compiler",
    "skill.workflow_graph.template.patch": "workflow_graph.compiler",
    "skill.workflow_graph.template.delete": "workflow_graph.compiler",
    "skill.workflow_graph.template.version.list": "workflow_graph.compiler",
    "skill.workflow_graph.template.version.create": "workflow_graph.compiler",
    "skill.workflow_graph.template.version.get": "workflow_graph.compiler",
    "skill.workflow_graph.template.version.activate": "workflow_graph.compiler",
    "skill.workflow_graph.curated.get": "workflow_graph.curated",
    "skill.workflow_graph.curated.save_draft": "workflow_graph.curated",
    "skill.workflow_graph.curated.submit": "workflow_graph.curated",
    "skill.workflow_graph.curated.sync": "workflow_graph.curated",
    "skill.workflow_graph.curated.rollback": "workflow_graph.curated",
    "skill.workflow_graph.curated.list_audits": "workflow_graph.curated",
    "skill.workflow_graph.curated.evidence_pack": "workflow_graph.curated",
    "skill.workflow_graph.curated.handoff.reporting": "workflow_graph.curated",
    "skill.workflow_graph.curated.handoff.writing": "workflow_graph.curated",
    "skill.workflow.llm_call": "workflow_graph.executor.llm_call",
}
WRITING_DOCUMENT_TOOLS = {
    "writing.document.list": ("read_only", "allow", "parallel"),
    "writing.document.read": ("read_only", "allow", "parallel"),
    "writing.document.section.read": ("read_only", "allow", "parallel"),
    "writing.document.create": ("write_shared", "ask", "serial"),
    "writing.document.insert_paragraph": ("write_shared", "ask", "serial"),
    "writing.document.citations.upsert": ("write_shared", "ask", "serial"),
}


def _spec(name: str) -> CoreToolSpec:
    return CoreToolSpec(name=name, description_for_model=name, project_service_id=name)


def _symbol_path(source_ref: str) -> tuple[Path, str]:
    path_text, separator, symbol = source_ref.partition("#")
    assert separator, source_ref
    path = REPO_ROOT / path_text
    assert path.is_file(), source_ref
    return path, symbol


def _python_contains_symbol(source_text: str, symbol: str) -> bool:
    tree = ast.parse(source_text)
    names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    assignments = {
        node.targets[0].id
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    }
    return all(part in names or part in assignments for part in symbol.split("."))


def _typescript_contains_symbol(source_text: str, symbol: str) -> bool:
    return all(part in source_text for part in symbol.split("."))


def test_work_declares_three_responsibilities_with_source_backed_relations() -> None:
    assert [source.ref for source in SYSTEM_OBJECTS] == [
        "mrw.workflow",
        "mrw.writing",
        "mrw.consumers",
    ]
    assert build_system_projection(SYSTEM_OBJECTS, [])
    assert {relation.target_ref for source in SYSTEM_OBJECTS for relation in source.relations} <= {
        source.ref for source in SYSTEM_OBJECTS
    }


def test_work_tool_refs_and_llm_boundary_are_exact() -> None:
    by_ref = {source.ref: source for source in SYSTEM_OBJECTS}
    assert by_ref["mrw.workflow"].tool_refs == (
        "workflow_graph.list",
        "workflow_graph.inspect",
        "workflow_graph.run",
        *WORKFLOW_SKILL_TOOLS,
    )
    assert by_ref["mrw.writing"].tool_refs == (
        "report.generate",
        *WRITING_DOCUMENT_TOOLS,
        "skill.workflow_graph.curated.handoff.reporting",
        "skill.workflow_graph.curated.handoff.writing",
    )
    assert by_ref["mrw.consumers"].tool_refs == ()
    projection = build_system_projection(SYSTEM_OBJECTS, tuple(_spec(name) for name in (
        "workflow_graph.list",
        "workflow_graph.inspect",
        "workflow_graph.run",
        "report.generate",
        *WRITING_DOCUMENT_TOOLS,
        *WORKFLOW_SKILL_TOOLS,
    )))
    assert projection.unmapped_tool_names() == ()
    assert "template-derived" in by_ref["mrw.writing"].summary
    assert "report.generate" in by_ref["mrw.writing"].summary


def test_exact_skill_tools_match_original_runtime_owners_and_registry_specs() -> None:
    skill_owners = {
        f"skill.{skill['skill_id']}": skill["owner"]
        for skill in SkillRuntime().list_skills()
        if str(skill["skill_id"]).startswith("workflow_graph.")
        or str(skill["skill_id"]) == "workflow.llm_call"
    }
    assert len(WORKFLOW_SKILL_TOOLS) == 26
    assert skill_owners == WORKFLOW_SKILL_TOOLS

    registry = build_project_core_tool_registry(
        service=AgentSessionService(store=InMemoryAgentSessionStore()),
        source_library_lister=lambda project_key: [],
        structured_data_searcher=lambda *args, **kwargs: {},
    )
    specs = {spec.name: spec for spec in registry.list_specs()}
    assert set(WORKFLOW_SKILL_TOOLS) | set(WRITING_DOCUMENT_TOOLS) <= specs.keys()
    for name, expected_attributes in WRITING_DOCUMENT_TOOLS.items():
        spec = specs[name]
        assert (spec.risk, spec.permission, spec.concurrency) == expected_attributes


def test_handoffs_are_semantically_shared_without_changing_the_original_writer() -> None:
    by_ref = {source.ref: source for source in SYSTEM_OBJECTS}
    shared = {
        "skill.workflow_graph.curated.handoff.reporting",
        "skill.workflow_graph.curated.handoff.writing",
    }
    assert shared <= set(by_ref["mrw.workflow"].tool_refs)
    assert shared <= set(by_ref["mrw.writing"].tool_refs)
    assert set(by_ref["mrw.consumers"].tool_refs).isdisjoint(shared)
    assert by_ref["mrw.consumers"].tool_refs == ()


def test_chinese_purpose_queries_and_exact_tool_pagination_follow_next() -> None:
    registry = build_project_core_tool_registry(
        service=AgentSessionService(store=InMemoryAgentSessionStore()),
        source_library_lister=lambda project_key: [],
        structured_data_searcher=lambda *args, **kwargs: {},
    )
    projection = build_system_projection(SYSTEM_OBJECTS, tuple(registry.list_specs()))
    expected_first = {
        "模板版本": "mrw.workflow",
        "运行读回": "mrw.workflow",
        "curated证据交接": "mrw.workflow",
        "文稿读取": "mrw.writing",
        "段落编辑": "mrw.writing",
        "引文写入": "mrw.writing",
    }
    for query, expected_ref in expected_first.items():
        result = inspect_system_projection(projection, {"query": query, "limit": 1}, None)
        assert result["items"][0]["ref"] == expected_ref

    page = inspect_system_projection(
        projection,
        {"ref": "tool:skill.workflow_graph.curated.handoff.writing", "limit": 1},
        None,
    )
    assert page["items"][0]["ref"] == "tool:skill.workflow_graph.curated.handoff.writing"
    visited_owner_refs: set[str] = set()
    page_count = 1
    while page.get("next") is not None:
        page = inspect_system_projection(projection, page["next"], None)
        page_count += 1
        visited_owner_refs.update(relation["target_ref"] for relation in page["relations"])
        visited_owner_refs.update(
            item["ref"] for item in page["items"] if not item["ref"].startswith("tool:")
        )
        assert page_count < 20
    assert visited_owner_refs == {"mrw.workflow", "mrw.writing"}
    assert page["next"] is None


def test_work_relations_keep_handoff_and_consumption_distinct() -> None:
    by_ref = {source.ref: source for source in SYSTEM_OBJECTS}
    system_relation_type = type(SYSTEM_OBJECTS[0].relations[0])
    assert by_ref["mrw.workflow"].relations == (SystemRelation("produces", "mrw.writing"),)
    assert by_ref["mrw.writing"].relations == (SystemRelation("produces", "mrw.consumers"),)
    assert by_ref["mrw.consumers"].relations == (SystemRelation("observes", "mrw.workflow"),)
    assert system_relation_type is SystemRelation
    assert "not a runtime dependency" in by_ref["mrw.workflow"].summary
    assert "no dedicated Agent operation" in by_ref["mrw.consumers"].summary


def test_work_source_refs_point_to_repo_files_and_declared_symbols() -> None:
    for source in SYSTEM_OBJECTS:
        assert source.source_refs
        for source_ref in source.source_refs:
            path, symbol = _symbol_path(source_ref)
            text = path.read_text(encoding="utf-8")
            if path.suffix == ".py":
                assert _python_contains_symbol(text, symbol), source_ref
            else:
                assert _typescript_contains_symbol(text, symbol), source_ref
