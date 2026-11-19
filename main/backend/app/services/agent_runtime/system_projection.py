from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import TYPE_CHECKING, Annotated, TypeGuard

from app.contracts.json import JSONObject
from .system_projection_contracts import (
    EXPECTED_RESPONSIBILITY_REFS,
    SYSTEM_ID,
    SYSTEM_INSPECT_DESCRIPTION,
    SYSTEM_INSPECT_TOOL_NAME,
    SYSTEM_PROJECTION_ARGUMENTS,
    SYSTEM_PROJECTION_CONTRACT_VERSION,
    SYSTEM_RELATION_KINDS,
    UNMAPPED_TOOLS_COVERAGE_REF,
    SystemObjectSource,
    SystemRelation,
    system_inspect_capability,
    system_inspect_input_schema,
)

if TYPE_CHECKING:
    from app.services.agent_core.contracts import CoreToolSpec


class SystemProjectionError(ValueError):
    code = "system_projection_input_invalid"


class SystemProjectionRefNotFoundError(SystemProjectionError):
    code = "system_ref_not_found"


class SystemProjectionStaleError(SystemProjectionError):
    code = "stale_projection"


class SystemProjectionItemTooLargeError(SystemProjectionError):
    code = "system_projection_item_too_large"


@dataclass(frozen=True, slots=True)
class SystemProjection:
    objects: tuple[SystemObjectSource, ...]
    specs: tuple[CoreToolSpec, ...]
    revision: str

    def spec_for_tool(self, tool_name: str) -> CoreToolSpec | None:
        exact_name = str(tool_name or "").strip()
        return next((spec for spec in self.specs if spec.name == exact_name), None)

    def tool_owners(self, tool_name: str) -> tuple[SystemObjectSource, ...]:
        exact_name = str(tool_name or "").strip()
        owners = (
            source
            for source in self.objects
            if exact_name in source.tool_refs
            or (source.ref == SYSTEM_ID and exact_name == SYSTEM_INSPECT_TOOL_NAME)
        )
        return tuple(sorted(owners, key=lambda source: source.ref))

    def system_refs_for_tool(self, tool_name: str) -> tuple[str, ...]:
        return tuple(source.ref for source in self.tool_owners(tool_name))

    def unmapped_tool_names(self) -> tuple[str, ...]:
        mapped = {
            tool_name for source in self.objects for tool_name in source.tool_refs
        }
        return tuple(spec.name for spec in self.specs if spec.name not in mapped)


@dataclass(frozen=True, slots=True)
class _RequestTarget:
    source: SystemObjectSource | None = None
    tool_name: str | None = None
    coverage_collection: bool = False

    @property
    def ref(self) -> str:
        if self.coverage_collection:
            return UNMAPPED_TOOLS_COVERAGE_REF
        if self.tool_name is not None:
            return f"tool:{self.tool_name}"
        if self.source is not None:
            return self.source.ref
        raise ValueError("request target is empty")


@dataclass(frozen=True, slots=True)
class _SequenceEntry:
    kind: str
    value: JSONObject


def _text(value: object) -> str:
    return str(value or "").strip()


def _is_argument_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


def _validate_source(source: SystemObjectSource) -> None:
    if not source.ref:
        raise ValueError("system object ref is required")
    if source.ref == SYSTEM_ID:
        raise ValueError("mrw.system is derived and cannot be authored")
    if not source.title or not source.summary or not source.owner_ref:
        raise ValueError(f"system object {source.ref} requires title, summary, and owner_ref")
    if len(source.summary) > 240:
        raise ValueError(f"system object {source.ref} summary exceeds 240 characters")
    if not source.source_refs or any(not _text(ref) for ref in source.source_refs):
        raise ValueError(f"system object {source.ref} requires nonempty source_refs")
    if any(not _text(term) for term in source.purpose_terms):
        raise ValueError(f"system object {source.ref} has an empty purpose term")
    if any(not _text(tool) or tool.startswith("tool:") for tool in source.tool_refs):
        raise ValueError(f"system object {source.ref} has an invalid tool ref")
    if len(set(source.tool_refs)) != len(source.tool_refs):
        raise ValueError(f"system object {source.ref} has duplicate tool refs")
    if len(set(source.relations)) != len(source.relations):
        raise ValueError(f"system object {source.ref} has duplicate relations")
    for relation in source.relations:
        if relation.kind not in SYSTEM_RELATION_KINDS:
            raise ValueError(f"system object {source.ref} has unsupported relation kind: {relation.kind}")
        if not relation.target_ref or relation.target_ref.startswith("tool:"):
            raise ValueError(f"system object {source.ref} relations must target system objects")


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _result_bytes(value: object) -> int:
    return len(_canonical_json(value).encode("utf-8"))


def _spec_summary(spec: CoreToolSpec) -> JSONObject:
    return {
        "name": spec.name,
        "title": spec.title,
        "description_for_model": spec.description_for_model,
        "risk": spec.risk,
        "permission": spec.permission,
        "concurrency": spec.concurrency,
        "project_service_id": spec.project_service_id,
        "input_schema": dict(spec.input_schema or {}),
    }


def _revision(objects: Sequence[SystemObjectSource], specs: Sequence[CoreToolSpec]) -> str:
    payload = {
        "contract_version": SYSTEM_PROJECTION_CONTRACT_VERSION,
        "objects": [
            {
                "ref": source.ref,
                "title": source.title,
                "summary": source.summary,
                "owner_ref": source.owner_ref,
                "source_refs": list(source.source_refs),
                "purpose_terms": list(source.purpose_terms),
                "tool_refs": list(source.tool_refs),
                "relations": [
                    {"kind": relation.kind, "target_ref": relation.target_ref}
                    for relation in source.relations
                ],
            }
            for source in sorted(objects, key=lambda item: item.ref)
        ],
        "registry_specs": [_spec_summary(spec) for spec in sorted(specs, key=lambda item: item.name)],
    }
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _top_level_sources(
    objects: Sequence[SystemObjectSource],
) -> tuple[SystemObjectSource, ...]:
    children = {
        source.ref: tuple(
            relation.target_ref
            for relation in source.relations
            if relation.kind == "contains"
        )
        for source in objects
    }
    incoming = dict.fromkeys(children, 0)
    for targets in children.values():
        for target in targets:
            incoming[target] += 1
    roots = {ref for ref, count in incoming.items() if count == 0}
    pending = list(roots)
    visited = 0
    while pending:
        ref = pending.pop()
        visited += 1
        for target in children[ref]:
            incoming[target] -= 1
            if incoming[target] == 0:
                pending.append(target)
    if visited != len(objects):
        raise ValueError("system contains relations must be acyclic")
    return tuple(sorted((source for source in objects if source.ref in roots), key=lambda source: source.ref))


def build_system_projection(
    objects: Sequence[SystemObjectSource],
    specs: Sequence[CoreToolSpec],
) -> Annotated[
    SystemProjection,
    "kit:non-authoritative derived_as=view "
    "fact_source=system_sources_SYSTEM_OBJECTS+CoreToolRegistry.list_specs "
    "witness=test:test_registry_registers_one_system_inspect_after_original_registration",
]:
    """Build the immutable semantic index without invoking a business handler."""

    authored = tuple(objects)
    authored_refs = {source.ref for source in authored}
    if len(authored_refs) != len(authored):
        raise ValueError("system object refs must be unique")
    for source in authored:
        _validate_source(source)
        for relation in source.relations:
            if relation.target_ref not in authored_refs:
                raise ValueError(
                    f"system object {source.ref} has unresolved relation target: {relation.target_ref}"
                )

    top_level = _top_level_sources(authored)
    normalized_specs = tuple(sorted(specs, key=lambda spec: spec.name))
    if len({spec.name for spec in normalized_specs}) != len(normalized_specs):
        raise ValueError("CoreToolSpec names must be unique")

    root = SystemObjectSource(
        ref=SYSTEM_ID,
        title="MRW system",
        summary=(
            "Market Research Workflow: materials and sources, ingestion, retrieval, workflow, "
            "writing, consumers, agent sessions, and persistent state."
        ),
        owner_ref=SYSTEM_ID,
        source_refs=(
            "main/backend/docs/agent-cell-current.md",
            "main/backend/app/services/agent_runtime/system_projection.py#build_system_projection",
        ),
        purpose_terms=("mrw", "system", "系统", "整体结构", "系统导航"),
        tool_refs=(SYSTEM_INSPECT_TOOL_NAME,),
        relations=tuple(
            SystemRelation(kind="contains", target_ref=source.ref)
            for source in top_level
        ),
    )
    return SystemProjection(
        objects=(root, *authored),
        specs=normalized_specs,
        revision=_revision(authored, normalized_specs),
    )


def _integer(value: object, *, field: str, minimum: int, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SystemProjectionError(f"{field} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        upper = f" and {maximum}" if maximum is not None else ""
        raise SystemProjectionError(f"{field} must be between {minimum}{upper}")
    return value


def _source_by_ref(projection: SystemProjection, ref: str) -> SystemObjectSource | None:
    return next((source for source in projection.objects if source.ref == ref), None)


def _request_target(projection: SystemProjection, ref: str) -> _RequestTarget | None:
    if ref == UNMAPPED_TOOLS_COVERAGE_REF:
        return _RequestTarget(coverage_collection=True)
    if ref.startswith("tool:"):
        tool_name = ref[5:]
        if projection.spec_for_tool(tool_name) is not None or projection.tool_owners(tool_name):
            return _RequestTarget(tool_name=tool_name)
        return None
    source = _source_by_ref(projection, ref)
    return _RequestTarget(source=source) if source is not None else None


def _source_relations(
    projection: SystemProjection,
    source: SystemObjectSource,
) -> tuple[SystemRelation, ...]:
    relations = list(source.relations)
    if source.ref != SYSTEM_ID:
        relations.extend(
            SystemRelation(kind="uses", target_ref=f"tool:{tool_name}")
            for tool_name in source.tool_refs
        )
    elif projection.spec_for_tool(SYSTEM_INSPECT_TOOL_NAME) is not None:
        relations.append(
            SystemRelation(kind="uses", target_ref=f"tool:{SYSTEM_INSPECT_TOOL_NAME}")
        )
    return tuple(sorted(set(relations), key=lambda relation: (relation.kind, relation.target_ref)))


def _tool_relations(
    projection: SystemProjection,
    tool_name: str,
) -> tuple[SystemRelation, ...]:
    return tuple(
        SystemRelation(kind="consumed_by", target_ref=owner.ref)
        for owner in sorted(
            projection.tool_owners(tool_name), key=lambda source: source.ref
        )
    )


def _match_score(query: str, text: str, *, exact: int, contains: int) -> int:
    needle = query.casefold()
    haystack = _text(text).casefold()
    if not needle or not haystack:
        return 0
    if needle == haystack:
        return exact
    if needle in haystack:
        return contains
    return 0


def _object_score(query: str, source: SystemObjectSource) -> int:
    if not query:
        return 0
    score = _match_score(query, source.ref, exact=100, contains=70)
    score += _match_score(query, source.title, exact=75, contains=45)
    score += _match_score(query, source.summary, exact=30, contains=12)
    normalized_query = query.casefold()
    for term in source.purpose_terms:
        normalized_term = _text(term).casefold()
        if not normalized_term:
            continue
        if normalized_term == normalized_query:
            score += 60
        elif normalized_term in normalized_query or normalized_query in normalized_term:
            score += 35
    return score


def _tool_score(projection: SystemProjection, query: str, tool_name: str) -> int:
    spec = projection.spec_for_tool(tool_name)
    title = spec.title if spec is not None and spec.title else tool_name
    description = spec.description_for_model if spec is not None else f"Declared tool {tool_name}"
    score = _match_score(query, tool_name, exact=100, contains=65)
    score += _match_score(query, title, exact=70, contains=40)
    score += _match_score(query, description, exact=25, contains=12)
    owner_scores = [_object_score(query, owner) for owner in projection.tool_owners(tool_name)]
    if owner_scores and max(owner_scores) >= 60:
        score += min(35, max(owner_scores) // 2)
    return score


def _object_item(source: SystemObjectSource, projection: SystemProjection) -> JSONObject:
    mounted = any(projection.spec_for_tool(tool) for tool in source.tool_refs)
    item: JSONObject = {
        "ref": source.ref,
        "kind": "system" if source.ref == SYSTEM_ID else "responsibility",
        "title": source.title,
        "summary": source.summary[:240],
        "owner_ref": source.owner_ref,
        "source_refs": list(source.source_refs),
        "coverage": "mapped",
        "availability": (
            "metadata_only" if not source.tool_refs else "mounted" if mounted else "unmounted"
        ),
        "relations": [],
    }
    if source.ref == SYSTEM_ID:
        item["unmapped_tool_count"] = len(projection.unmapped_tool_names())
        item["coverage_ref"] = UNMAPPED_TOOLS_COVERAGE_REF
    return item


def _tool_item(projection: SystemProjection, tool_name: str) -> JSONObject:
    spec = projection.spec_for_tool(tool_name)
    owners = projection.tool_owners(tool_name)
    owner_refs = [owner.ref for owner in owners]
    entrypoint = (spec.project_service_id or spec.name) if spec is not None else tool_name
    return {
        "ref": f"tool:{tool_name}",
        "kind": "tool",
        "title": spec.title or tool_name if spec is not None else tool_name,
        "summary": (
            spec.description_for_model if spec is not None else f"Declared tool {tool_name} is not mounted."
        )[:240],
        "owner_ref": f"project_tool:{entrypoint}",
        "source_refs": [
            "main/backend/app/services/agent_core/project_tools.py#build_project_core_tool_registry"
        ],
        "coverage": "mapped" if spec is not None and owners else "gap",
        "availability": "mounted" if spec is not None else "unmounted",
        "relations": [],
        "system_refs": owner_refs,
        "tool_name": tool_name,
        "schema_ref": f"tool:{tool_name}#input_schema",
        "risk": spec.risk if spec is not None else None,
        "permission": spec.permission if spec is not None else None,
        "project_service_id": spec.project_service_id if spec is not None else None,
    }


def _coverage_collection_item(projection: SystemProjection) -> JSONObject:
    return {
        "ref": UNMAPPED_TOOLS_COVERAGE_REF,
        "kind": "coverage",
        "title": "Unmounted-from-responsibility tool coverage",
        "summary": f"{len(projection.unmapped_tool_names())} registered tools have no responsibility declaration.",
        "owner_ref": "main/backend/app/services/agent_core/project_tools.py#build_project_core_tool_registry",
        "source_refs": (
            "main/backend/docs/agent-cell-current.md",
            "main/backend/app/services/agent_core/project_tools.py#build_project_core_tool_registry",
        ),
        "coverage": "mapped",
        "availability": "metadata_only",
        "relations": [],
        "count": len(projection.unmapped_tool_names()),
    }


def _request_item(projection: SystemProjection, target: _RequestTarget) -> JSONObject:
    if target.coverage_collection:
        return _coverage_collection_item(projection)
    if target.tool_name is not None:
        return _tool_item(projection, target.tool_name)
    if target.source is not None:
        return _object_item(target.source, projection)
    raise ValueError("request target is empty")


def _target_item(projection: SystemProjection, ref: str) -> JSONObject:
    if ref.startswith("tool:"):
        return _tool_item(projection, ref[5:])
    source = _source_by_ref(projection, ref)
    if source is None:
        raise ValueError(f"unresolved system target: {ref}")
    return _object_item(source, projection)


def _query_items(projection: SystemProjection, query: str) -> list[JSONObject]:
    candidates: list[tuple[int, str, JSONObject]] = []
    for source in projection.objects:
        score = _object_score(query, source)
        if score > 0:
            candidates.append((score, source.ref, _object_item(source, projection)))

    declared_tools = {
        tool_name for source in projection.objects for tool_name in source.tool_refs
    }
    for tool_name in sorted(declared_tools | {spec.name for spec in projection.specs}):
        score = _tool_score(projection, query, tool_name)
        if score > 0:
            candidates.append((score, f"tool:{tool_name}", _tool_item(projection, tool_name)))

    candidates.sort(key=lambda item: (-item[0], item[1]))
    if not candidates:
        root = _source_by_ref(projection, SYSTEM_ID)
        if root is None:
            raise ValueError("projection has no root object")
        return [_object_item(root, projection)]
    return [item for _score, _ref, item in candidates]


def _relation_entry(target: _RequestTarget, relation: SystemRelation) -> _SequenceEntry:
    return _SequenceEntry(
        "relation",
        {
            "kind": relation.kind,
            "source_ref": target.ref,
            "target_ref": relation.target_ref,
        },
    )


def _ref_sequence(projection: SystemProjection, target: _RequestTarget) -> list[_SequenceEntry]:
    if target.coverage_collection:
        return [
            _SequenceEntry("item", _coverage_collection_item(projection)),
            *(
                _SequenceEntry("item", _tool_item(projection, tool_name))
                for tool_name in projection.unmapped_tool_names()
            ),
        ]

    if target.tool_name is not None:
        relations = _tool_relations(projection, target.tool_name)
    elif target.source is not None:
        relations = _source_relations(projection, target.source)
    else:
        raise ValueError("request target is empty")

    entries = [_SequenceEntry("item", _request_item(projection, target))]
    entries.extend(_relation_entry(target, relation) for relation in relations)
    target_refs = sorted(
        {relation.target_ref for relation in relations if relation.target_ref != target.ref}
    )
    entries.extend(_SequenceEntry("item", _target_item(projection, ref)) for ref in target_refs)
    return entries


def _item_gap(projection: SystemProjection, item: JSONObject) -> JSONObject | None:
    ref = _text(item.get("ref"))
    if ref == SYSTEM_ID:
        missing = [
            responsibility
            for responsibility in EXPECTED_RESPONSIBILITY_REFS
            if _source_by_ref(projection, responsibility) is None
        ]
        if missing:
            return {
                "ref": SYSTEM_ID,
                "owner_ref": "main/backend/app/services/agent_core/project_tools.py#build_project_core_tool_registry",
                "reason": f"{len(missing)} responsibility declarations are pending",
                "blocked_by": "system_projection:responsibility_declarations",
            }
        return None

    if item.get("kind") == "tool":
        tool_name = _text(item.get("tool_name"))
        if projection.spec_for_tool(tool_name) is None:
            return {
                "ref": f"tool:{tool_name}",
                "owner_ref": _text(item.get("owner_ref")) or SYSTEM_ID,
                "reason": "declared tool is absent from the supplied registry",
                "blocked_by": "CoreToolRegistry:tool_not_registered",
            }
        if not projection.system_refs_for_tool(tool_name):
            return {
                "ref": f"tool:{tool_name}",
                "owner_ref": _text(item.get("owner_ref")) or SYSTEM_ID,
                "reason": "system_owner_unmapped",
                "blocked_by": (
                    "main/backend/app/services/agent_core/project_tools.py:"
                    f"system_projection:{tool_name}"
                ),
            }
        return None

    source = _source_by_ref(projection, ref)
    if source is None:
        return None
    missing_tools = [
        tool_name
        for tool_name in source.tool_refs
        if projection.spec_for_tool(tool_name) is None
    ]
    if not missing_tools:
        return None
    return {
        "ref": ref,
        "owner_ref": source.owner_ref,
        "reason": f"{len(missing_tools)} declared tool(s) are unmounted",
        "blocked_by": "CoreToolRegistry:tool_not_registered",
    }


def _next_arguments(
    *,
    query: str | None,
    ref: str | None,
    limit: int,
    offset: int,
    revision: str,
) -> JSONObject:
    result: JSONObject = {"limit": limit, "offset": offset, "revision": revision}
    if query is not None:
        result["query"] = query
    if ref is not None:
        result["ref"] = ref
    return result


def _result_for_page(
    projection: SystemProjection,
    *,
    query: str | None,
    ref: str | None,
    request: _RequestTarget | None,
    entries: list[_SequenceEntry],
    total: int,
    offset: int,
    limit: int,
    project_key: str | None,
) -> JSONObject:
    page_items = [entry.value for entry in entries if entry.kind == "item"]
    gaps: list[JSONObject] = []
    for item in page_items:
        gap = _item_gap(projection, item)
        if gap is not None:
            gaps.append(gap)
    result: JSONObject = {
        "contract_version": SYSTEM_PROJECTION_CONTRACT_VERSION,
        "system_id": SYSTEM_ID,
        "revision": projection.revision,
        "project_key": project_key,
        "items": page_items,
        "relations": [entry.value for entry in entries if entry.kind == "relation"],
        "total": total,
        "offset": offset,
        "limit": limit,
        "truncated": offset + len(entries) < total,
        "next": None,
        "gaps": gaps,
    }
    if result["truncated"]:
        result["next"] = _next_arguments(
            query=query,
            ref=ref,
            limit=limit,
            offset=offset + len(entries),
            revision=projection.revision,
        )
    return result


def inspect_system_projection_with_budget(
    projection: SystemProjection,
    arguments: object,
    project_key: str | None,
    *,
    byte_budget: int,
    measure: Callable[[JSONObject], int],
) -> JSONObject:
    if not _is_argument_mapping(arguments):
        raise SystemProjectionError("arguments must be an object")
    unknown = set(arguments) - SYSTEM_PROJECTION_ARGUMENTS
    if unknown:
        raise SystemProjectionError(f"unknown system projection argument: {sorted(unknown)[0]}")

    has_query = "query" in arguments
    has_ref = "ref" in arguments
    if has_query and has_ref:
        raise SystemProjectionError("query and ref are mutually exclusive")
    query_value = arguments.get("query")
    ref_value = arguments.get("ref")
    if has_query and not isinstance(query_value, str):
        raise SystemProjectionError("query must be a string")
    if has_ref and (not isinstance(ref_value, str) or not _text(ref_value)):
        raise SystemProjectionError("ref must be a nonempty string")
    query = _text(query_value) if has_query else None
    ref = _text(ref_value) if has_ref else None
    if has_query and len(query_value if isinstance(query_value, str) else "") > 256:
        raise SystemProjectionError("query must contain at most 256 characters")

    limit = _integer(arguments.get("limit", 8), field="limit", minimum=1, maximum=20)
    offset = _integer(arguments.get("offset", 0), field="offset", minimum=0)
    revision_value = arguments.get("revision")
    if "revision" in arguments and (
        not isinstance(revision_value, str) or not _text(revision_value)
    ):
        raise SystemProjectionError("revision must be a nonempty string")
    supplied_revision = _text(revision_value) if "revision" in arguments else None

    request: _RequestTarget | None = None
    if ref is not None:
        request = _request_target(projection, ref)
        if request is None:
            raise SystemProjectionRefNotFoundError(f"unknown system ref: {ref}")
    if supplied_revision is not None and supplied_revision != projection.revision:
        raise SystemProjectionStaleError(
            "system projection revision changed; restart the same query from offset 0"
        )

    if request is not None:
        entries = _ref_sequence(projection, request)
    elif query is not None:
        entries = [
            _SequenceEntry("item", item) for item in _query_items(projection, query)
        ]
    else:
        root = _source_by_ref(projection, SYSTEM_ID)
        if root is None:
            raise ValueError("projection has no root object")
        request = _RequestTarget(source=root)
        entries = _ref_sequence(projection, request)

    total = len(entries)
    available = max(0, total - offset)
    for count in range(min(limit, available), 0, -1):
        result = _result_for_page(
            projection,
            entries=entries[offset : offset + count],
            query=query,
            ref=ref,
            request=request,
            total=total,
            offset=offset,
            limit=limit,
            project_key=project_key,
        )
        if measure(result) <= byte_budget:
            return result
    if available == 0:
        empty_result = _result_for_page(
            projection,
            entries=[],
            query=query,
            ref=ref,
            request=request,
            total=total,
            offset=offset,
            limit=limit,
            project_key=project_key,
        )
        if measure(empty_result) <= byte_budget:
            return empty_result
        raise SystemProjectionItemTooLargeError(
            "the empty system projection page exceeds the response budget"
        )
    raise SystemProjectionItemTooLargeError(
        "the first system projection entry exceeds the response budget"
    )


def inspect_system_projection(
    projection: SystemProjection,
    arguments: Mapping[str, object],
    project_key: str | None,
) -> JSONObject:
    """Return one bounded pure projection page; this measures only result JSON."""

    if not _is_argument_mapping(arguments):
        raise SystemProjectionError("arguments must be an object")
    limit_value = arguments.get("limit", 8)
    budget = 8192 if limit_value == 8 else 16384
    return inspect_system_projection_with_budget(
        projection,
        arguments,
        project_key,
        byte_budget=budget,
        measure=_result_bytes,
    )


__all__ = [
    "SYSTEM_ID",
    "SYSTEM_INSPECT_DESCRIPTION",
    "SYSTEM_INSPECT_TOOL_NAME",
    "SYSTEM_PROJECTION_CONTRACT_VERSION",
    "UNMAPPED_TOOLS_COVERAGE_REF",
    "SystemObjectSource",
    "SystemProjection",
    "SystemProjectionError",
    "SystemProjectionItemTooLargeError",
    "SystemProjectionRefNotFoundError",
    "SystemProjectionStaleError",
    "SystemRelation",
    "build_system_projection",
    "inspect_system_projection",
    "inspect_system_projection_with_budget",
    "system_inspect_input_schema",
    "system_inspect_capability",
]
