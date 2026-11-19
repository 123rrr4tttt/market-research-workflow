from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.agent_core.contracts import CoreToolSpec
from app.services.agent_runtime.system_projection_contracts import (
    SYSTEM_INSPECT_TOOL_NAME,
    UNMAPPED_TOOLS_COVERAGE_REF,
    SystemObjectSource,
    SystemRelation,
    system_inspect_input_schema,
)
from app.services.agent_runtime.system_projection import (
    SystemProjectionError,
    SystemProjectionItemTooLargeError,
    build_system_projection,
    inspect_system_projection,
)
from app.services.agent_runtime.system_sources_materials import SYSTEM_OBJECTS


def _spec(name: str, *, description: str | None = None) -> CoreToolSpec:
    return CoreToolSpec(
        name=name,
        title=name,
        description_for_model=description or f"Execute {name}.",
        project_service_id=name,
    )


def _source(
    ref: str,
    *,
    relations: tuple[SystemRelation, ...] = (),
    tools: tuple[str, ...] = (),
    source_refs: tuple[str, ...] = ("test/source.py#object",),
    purpose_terms: tuple[str, ...] | None = None,
) -> SystemObjectSource:
    return SystemObjectSource(
        ref=ref,
        title=ref,
        summary=f"{ref} responsibility.",
        owner_ref=f"owner.{ref}",
        source_refs=source_refs,
        purpose_terms=purpose_terms or (ref,),
        tool_refs=tools,
        relations=relations,
    )


def _utf8(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _pages(projection, arguments: dict, *, project_key: str | None = None) -> list[dict]:
    pages: list[dict] = []
    next_arguments: dict | None = dict(arguments)
    while next_arguments is not None:
        page = inspect_system_projection(projection, next_arguments, project_key)
        pages.append(page)
        next_arguments = page.get("next")
    return pages


def test_build_rejects_duplicate_objects_and_unresolved_relations() -> None:
    source = _source("mrw.a", relations=(SystemRelation("contains", "mrw.missing"),))
    with pytest.raises(ValueError, match="unresolved relation target"):
        build_system_projection((source,), [])
    with pytest.raises(ValueError, match="system object refs must be unique"):
        build_system_projection((_source("mrw.a"), _source("mrw.a")), [])


def test_responsibility_coverage_is_mapped_without_dedicated_tool() -> None:
    projection = build_system_projection(
        (
            _source(
                "mrw.consumers",
                relations=(SystemRelation("observes", "mrw.writing"),),
                tools=(),
            ),
            _source("mrw.writing"),
        ),
        [],
    )
    result = inspect_system_projection(projection, {"ref": "mrw.consumers"}, None)
    consumers = result["items"][0]
    assert consumers["coverage"] == "mapped"
    assert consumers["availability"] == "metadata_only"
    assert consumers["relations"] == []
    assert result["gaps"] == []


def test_query_uses_input_text_and_deterministic_score_order() -> None:
    projection = build_system_projection(SYSTEM_OBJECTS, [])
    sources = inspect_system_projection(projection, {"query": "数据源"}, None)
    assert sources["items"][0]["ref"] == "mrw.sources"

    irrelevant = inspect_system_projection(projection, {"query": "unrelated xyz"}, None)
    assert [item["ref"] for item in irrelevant["items"]] == ["mrw.system"]

    blank = inspect_system_projection(projection, {"query": ""}, None)
    assert [item["ref"] for item in blank["items"]] == ["mrw.system"]

    ranked = build_system_projection(
        (
            _source("mrw.alpha", purpose_terms=("secondary beta",)),
            _source("mrw.beta"),
        ),
        [],
    )
    result = inspect_system_projection(ranked, {"query": "beta"}, None)
    assert [item["ref"] for item in result["items"]] == ["mrw.beta", "mrw.alpha"]


def test_exact_ref_uses_mixed_atomic_sequence_without_duplicate_refs() -> None:
    projection = build_system_projection(
        (
            _source("mrw.a", relations=(SystemRelation("uses", "mrw.b"),)),
            _source("mrw.b"),
        ),
        [],
    )
    pages = _pages(projection, {"ref": "mrw.system", "limit": 1})
    assert len(pages) == 5
    assert [page["items"][0]["ref"] if page["items"] else None for page in pages] == [
        "mrw.system",
        None,
        None,
        "mrw.a",
        "mrw.b",
    ]
    assert [page["relations"][0]["target_ref"] for page in pages[1:3]] == [
        "mrw.a",
        "mrw.b",
    ]
    assert all(len(page["items"]) + len(page["relations"]) <= 1 for page in pages)
    assert all(item["relations"] == [] for page in pages for item in page["items"])
    assert sum(len(page["items"]) + len(page["relations"]) for page in pages) == pages[0]["total"] == 5


def test_root_members_follow_explicit_contains_not_ref_prefixes() -> None:
    projection = build_system_projection(
        (
            _source("mrw.a", relations=(SystemRelation("contains", "extension.shared"),)),
            _source("mrw.b", relations=(SystemRelation("contains", "extension.shared"),)),
            _source("extension.shared", relations=(SystemRelation("uses", "mrw.a"),)),
            _source("mrw.a.independent"),
        ),
        [],
    )
    root_pages = _pages(projection, {"ref": "mrw.system", "limit": 1})
    root_refs = {item["ref"] for page in root_pages for item in page["items"]}
    assert root_refs == {"mrw.system", "mrw.a", "mrw.b", "mrw.a.independent"}
    assert "extension.shared" not in root_refs
    assert all(
        relation["target_ref"] != "extension.shared"
        for page in root_pages for relation in page["relations"]
    )
    for parent in ("mrw.a", "mrw.b"):
        pages = _pages(projection, {"ref": parent, "limit": 1})
        assert sum(
            item["ref"] == "extension.shared" for page in pages for item in page["items"]
        ) == 1
    child = inspect_system_projection(projection, {"ref": "extension.shared"}, None)
    assert child["items"][0]["ref"] == "extension.shared"


def test_only_contains_cycles_are_rejected() -> None:
    with pytest.raises(ValueError, match="contains relations must be acyclic"):
        build_system_projection(
            (
                _source("mrw.a", relations=(SystemRelation("contains", "mrw.b"),)),
                _source("mrw.b", relations=(SystemRelation("contains", "mrw.a"),)),
            ),
            [],
        )
    with pytest.raises(ValueError, match="contains relations must be acyclic"):
        build_system_projection(
            (_source("mrw.a", relations=(SystemRelation("contains", "mrw.a"),)),), []
        )
    projection = build_system_projection(
        (
            _source("mrw.a", relations=(SystemRelation("uses", "mrw.b"),)),
            _source("mrw.b", relations=(SystemRelation("produces", "mrw.a"),)),
        ),
        [],
    )
    assert len(inspect_system_projection(projection, {"ref": "mrw.system"}, None)["items"]) == 3


def test_tool_entrypoint_identity_is_not_inferred_from_semantic_owners() -> None:
    shared = _spec("shared.read")
    projection = build_system_projection(
        (
            _source("mrw.a", tools=("shared.read", "missing.read")),
            _source("mrw.b", tools=("shared.read",)),
        ),
        [shared],
    )
    item = inspect_system_projection(projection, {"ref": "tool:shared.read"}, None)["items"][0]
    assert item["owner_ref"] == "project_tool:shared.read"
    assert item["system_refs"] == ["mrw.a", "mrw.b"]
    assert item["source_refs"] == [
        "main/backend/app/services/agent_core/project_tools.py#build_project_core_tool_registry"
    ]
    missing = inspect_system_projection(projection, {"ref": "tool:missing.read"}, None)["items"][0]
    assert missing["owner_ref"] == "project_tool:missing.read"
    assert missing["availability"] == "unmounted"


def test_exact_tool_ref_contains_all_owning_responsibilities() -> None:
    projection = build_system_projection(
        (
            _source("mrw.a", tools=("shared.tool.read",)),
            _source("mrw.b", tools=("shared.tool.read",)),
        ),
        [_spec("shared.tool.read")],
    )
    result = inspect_system_projection(projection, {"ref": "tool:shared.tool.read"}, None)
    tool = result["items"][0]
    assert tool["system_refs"] == ["mrw.a", "mrw.b"]
    assert {relation["target_ref"] for relation in result["relations"]} == {"mrw.a", "mrw.b"}
    assert {item["ref"] for item in result["items"][1:]} == {"mrw.a", "mrw.b"}


def test_declared_unmounted_and_registered_unmapped_tools_are_distinct_gaps() -> None:
    projection = build_system_projection(
        (_source("mrw.a", tools=("declared.unmounted",)),),
        [_spec("registered.unmapped")],
    )
    unmounted = inspect_system_projection(
        projection, {"ref": "tool:declared.unmounted"}, None
    )
    assert unmounted["items"][0]["availability"] == "unmounted"
    assert unmounted["gaps"][0]["blocked_by"] == "CoreToolRegistry:tool_not_registered"

    unmapped = inspect_system_projection(
        projection, {"ref": "tool:registered.unmapped"}, None
    )
    tool = unmapped["items"][0]
    assert tool["availability"] == "mounted"
    assert tool["coverage"] == "gap"
    assert tool["system_refs"] == []
    assert unmapped["gaps"][0]["reason"] == "system_owner_unmapped"

    with pytest.raises(SystemProjectionError) as caught:
        inspect_system_projection(projection, {"ref": "tool:absent.tool"}, None)
    assert caught.value.code == "system_ref_not_found"


def test_unmapped_coverage_collection_is_paginated_without_root_inline_list() -> None:
    specs = [_spec(f"unmapped.{index:03d}") for index in range(105)]
    projection = build_system_projection((), specs)
    root = inspect_system_projection(projection, {}, None)
    assert root["items"][0]["unmapped_tool_count"] == 105
    assert root["items"][0]["coverage_ref"] == UNMAPPED_TOOLS_COVERAGE_REF
    assert root["relations"] == []
    assert _utf8(root) <= 8192

    pages = _pages(projection, {"ref": UNMAPPED_TOOLS_COVERAGE_REF, "limit": 1})
    refs = [page["items"][0]["ref"] for page in pages]
    assert refs[0] == UNMAPPED_TOOLS_COVERAGE_REF
    assert refs[1:] == [f"tool:unmapped.{index:03d}" for index in range(105)]
    assert len(refs) == len(set(refs)) == 106
    assert all(len(page["items"]) + len(page["relations"]) <= 1 for page in pages)
    assert all(page["gaps"] == [] for page in pages[:1])
    assert all(len(page["gaps"]) <= 1 for page in pages)


def test_revision_changes_for_registry_and_semantic_projection() -> None:
    source = _source("mrw.a", tools=("shared.tool",))
    before = build_system_projection((source,), [_spec("shared.tool")])
    changed_spec = build_system_projection(
        (source,), [_spec("shared.tool", description="Changed description.")]
    )
    changed_semantics = build_system_projection(
        (
            SystemObjectSource(
                ref="mrw.a",
                title="mrw.a",
                summary="changed",
                owner_ref="owner.mrw.a",
                source_refs=("test/source.py#object",),
                purpose_terms=("mrw.a",),
                tool_refs=("shared.tool",),
                relations=(),
            ),
        ),
        [_spec("shared.tool")],
    )
    assert before.revision != changed_spec.revision
    assert before.revision != changed_semantics.revision
    with pytest.raises(SystemProjectionError) as caught:
        inspect_system_projection(
            before,
            {"ref": "mrw.system", "revision": changed_spec.revision},
            None,
        )
    assert caught.value.code == "stale_projection"


def test_query_ref_mutex_and_input_ranges_are_classified() -> None:
    projection = build_system_projection((), [])
    invalid_cases = (
        {"query": "", "ref": "mrw.system"},
        {"query": "x", "limit": 0},
        {"query": "x", "limit": 21},
        {"query": "x", "offset": -1},
        {"query": "x", "unknown": True},
        {"query": "x", "revision": ""},
    )
    for arguments in invalid_cases:
        with pytest.raises(SystemProjectionError) as caught:
            inspect_system_projection(projection, arguments, None)
        assert caught.value.code == "system_projection_input_invalid"
    with pytest.raises(SystemProjectionError) as caught:
        inspect_system_projection(projection, object(), None)
    assert caught.value.code == "system_projection_input_invalid"
    with pytest.raises(SystemProjectionError) as caught:
        inspect_system_projection(projection, {"query": " " * 257}, None)
    assert caught.value.code == "system_projection_input_invalid"


def test_budget_consumes_only_fitting_prefix_and_fails_on_huge_item() -> None:
    huge_source = _source(
        "mrw.huge",
        source_refs=(Path("/dev/null").read_text()[:20000] or "x" * 20000,),
    )
    projection = build_system_projection(
        (huge_source, _source("mrw.small")), [_spec(SYSTEM_INSPECT_TOOL_NAME)]
    )
    result = inspect_system_projection(
        projection, {"ref": "mrw.system", "limit": 20}, None
    )
    assert _utf8(result) <= 16384
    assert result["truncated"] is True
    assert result["next"]["offset"] > 0

    with pytest.raises(SystemProjectionItemTooLargeError):
        inspect_system_projection(projection, {"ref": "mrw.huge", "limit": 1}, None)

    with pytest.raises(SystemProjectionItemTooLargeError):
        inspect_system_projection(
            projection,
            {"ref": "mrw.system", "offset": 100},
            "p" * 9000,
        )


def test_input_schema_is_bounded_and_root_result_uses_project_context_only() -> None:
    schema = system_inspect_input_schema()
    assert _utf8(schema) <= 4096
    assert schema["additionalProperties"] is False
    projection = build_system_projection(
        SYSTEM_OBJECTS, [_spec(SYSTEM_INSPECT_TOOL_NAME)]
    )
    root = inspect_system_projection(projection, {}, "demo_proj")
    assert root["project_key"] == "demo_proj"
    assert root["system_id"] == "mrw.system"
    assert any(
        relation["target_ref"] == f"tool:{SYSTEM_INSPECT_TOOL_NAME}"
        for relation in root["relations"]
    )
    assert _utf8(root) <= 8192
