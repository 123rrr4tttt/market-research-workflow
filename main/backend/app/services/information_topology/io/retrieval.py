"""Loss-aware mapping between source retrieval records and topology storage.

This module only moves declared structures. It never runs a search, upgrades a
candidate, or edits source-owned prose. Database access is supplied through an
explicit port so callers must use the PostgreSQL repository in production.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import Annotated, Any, Callable, Mapping, Protocol, Sequence

from functorial_kit import Failure
from sqlalchemy.orm import Session

from ..contracts import BoundRef, Element, ElementRef, Endpoint, TopologyState, topology_failures
from ..bindings import ProjectSemanticBinding, resolve_project_semantics
from ..modules.retrieval import (
    DomainVocabulary, domain_vocabulary_element, make_retrieval_profile,
    profile_from_state_payload, validate_evidence_v2,
)
from ..profiles import ProfileSpec, decode_state, validate_state
from ..repository import InformationTopologyRepository, StateWrite


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value: Any) -> str:
    return sha256(_canonical(value)).hexdigest()


def _state_digest(state: TopologyState) -> str:
    return _digest({
        "profile_id": state.profile_id,
        "profile_version": state.profile_version,
        "elements": [{
            "ref": _source_ref_wire_for_element(element.ref),
            "attributes": dict(element.attributes),
            "endpoints": [{"role": endpoint.role, "position": endpoint.position,
                "target": _source_ref_wire_for_element(endpoint.target)} for endpoint in element.endpoints],
        } for element in state.elements],
    })


def _source_ref_wire_for_element(ref: BoundRef) -> dict[str, Any]:
    return {"ref": {"project_key": ref.ref.project_key, "module_id": ref.ref.module_id,
        "namespace": ref.ref.namespace, "type_id": ref.ref.type_id, "local_id": ref.ref.local_id},
        "observed_revision": ref.observed_revision, "content_digest": ref.content_digest}


@dataclass(frozen=True, slots=True)
class ImportPreview:
    state: TopologyState
    profile: ProfileSpec
    state_key: tuple[str, str, str, str]
    source_digest: str
    source_revision: str
    provenance: Mapping[str, Any]
    loss: tuple[str, ...]
    warnings: tuple[str, ...]


class RetrievalTopologyStore(Protocol):
    """Explicit persistence boundary; implementations must be DB-backed."""

    def read(self, session: Session, key: tuple[str, str, str, str]) -> Mapping[str, Any] | None: ...
    def write(self, session: Session, preview: ImportPreview, *, expected_revision: int | None) -> Any: ...


class RepositoryRetrievalStore:
    """Adapter over the P02 PostgreSQL repository."""

    def __init__(self, repository: InformationTopologyRepository):
        self.repository = repository

    def read(self, session: Session, key: tuple[str, str, str, str]) -> Mapping[str, Any] | None:
        return self.repository.read_state(session, key)

    def write(self, session: Session, preview: ImportPreview, *, expected_revision: int | None) -> Any:
        return self.repository.apply_batch(session, states=(StateWrite(
            preview.state_key, preview.state, expected_revision, preview.provenance,
        ),))


def _source_ref_wire(vocabulary: DomainVocabulary) -> dict[str, Any]:
    ref = vocabulary.source_ref
    return {
        "project_key": ref.ref.project_key, "module_id": ref.ref.module_id,
        "namespace": ref.ref.namespace, "type_id": ref.ref.type_id,
        "local_id": ref.ref.local_id, "observed_revision": ref.observed_revision,
        "content_digest": ref.content_digest,
    }


def resolve_domain_vocabulary(project_key: str, source: Mapping[str, Any]) -> DomainVocabulary | Failure:
    """Read the explicit seven-field domain declaration and its bound source.

    The request contract uses ``domain_vocabulary`` with the exact seven keys
    from ``域.json`` and ``domain_source_ref`` as a BoundRef-shaped object:
    ``{ref: {project_key,module_id,namespace,type_id,local_id},
    observed_revision,content_digest}``. No fixed survey root or global profile
    registry participates in resolving it.
    """
    raw = source.get("domain_vocabulary")
    bound = source.get("domain_source_ref")
    fields = {"域名", "节点类型", "边类型", "问题意识视角", "大纲节", "池", "档"}
    identity_fields = {"project_key", "module_id", "namespace", "type_id", "local_id"}
    if not isinstance(raw, Mapping) or set(raw) != fields:
        return topology_failures.fail("INVALID_STRUCTURE", "domain_vocabulary must contain exactly the seven declared source fields")
    if not isinstance(bound, Mapping) or set(bound) != {"ref", "observed_revision", "content_digest"}:
        return topology_failures.fail("INVALID_STRUCTURE", "domain_source_ref must be an explicit bound source reference")
    identity = bound["ref"]
    if not isinstance(identity, Mapping) or set(identity) != identity_fields:
        return topology_failures.fail("INVALID_STRUCTURE", "domain_source_ref.ref identity is incomplete")
    if identity.get("project_key") != project_key:
        return topology_failures.fail("SOURCE_CHANGED", "domain vocabulary source belongs to another project")
    revision, digest = bound["observed_revision"], bound["content_digest"]
    if not isinstance(revision, str) or not revision or (digest is not None and not isinstance(digest, str)):
        return topology_failures.fail("INVALID_STRUCTURE", "domain source needs observed_revision and optional content_digest")
    arrays = ("节点类型", "边类型", "问题意识视角", "大纲节", "池", "档")
    if not isinstance(raw["域名"], str) or any(
        not isinstance(raw[key], list) or not raw[key]
        or any(not isinstance(value, str) or not value.strip() for value in raw[key]) for key in arrays
    ):
        return topology_failures.fail("INVALID_STRUCTURE", "domain vocabulary values must be nonempty strings and arrays")
    return DomainVocabulary(
        raw["域名"], tuple(raw["节点类型"]), tuple(raw["边类型"]), tuple(raw["问题意识视角"]),
        tuple(raw["大纲节"]), tuple(raw["池"]), tuple(raw["档"]),
        BoundRef(ElementRef(**dict(identity)), revision, digest),
    )


def _require_list(source: Mapping[str, Any], key: str) -> list[Mapping[str, Any]] | Failure:
    value = source.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        return topology_failures.fail("INVALID_WIRE_FORMAT", f"{key} must be an array of objects")
    return list(value)


def _source_yes_no(value: Any, field: str) -> bool | Failure:
    """Decode Rapid's declared 是/否 booleans without Python truthiness."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str) and value == "":
        return False
    if value == 1 or (isinstance(value, str) and value in {"是", "true", "True", "1"}):
        return True
    if value == 0 or (isinstance(value, str) and value in {"否", "false", "False", "0"}):
        return False
    return topology_failures.fail("INVALID_WIRE_FORMAT", f"{field} must be a boolean or Rapid 是/否 value")


def _source_multi(value: Any) -> list[str] | Failure:
    """Normalize Rapid multi-value columns using the native reader separators."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [part.strip() for part in re.split(r"[；;、|]", value) if part.strip()]
    if isinstance(value, (list, tuple)):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return topology_failures.fail("INVALID_WIRE_FORMAT", "multi-value source field must be text or a string array")


def build_import_preview(
    *, project_key: str, module_id: str, namespace: str,
    source: Mapping[str, Any], vocabulary: DomainVocabulary,
    semantic_binding: ProjectSemanticBinding[DomainVocabulary] | None = None,
    report_body: str | None = None, report_ref: Mapping[str, Any] | None = None,
) -> Annotated[ImportPreview | Failure, "kit:non-authoritative derived_as=view fact_source=source.graph+materials+domain_vocabulary witness=test:test_source_records_map_to_profile_and_export_keeps_order_report_and_extensions"]:
    """Map source-owned graph records into one validated topology state.

    ``source`` may contain the original ``图.json`` and companion ``材料.tsv``
    parsed as rows. Raw graph/report values are retained in provenance for an
    inverse projection; unsupported companion fields are listed as losses.
    """
    if not project_key or not module_id or not namespace:
        return topology_failures.fail("INVALID_STRUCTURE", "project/module/namespace must be explicit")
    if vocabulary.source_ref.ref.project_key != project_key:
        return topology_failures.fail("SOURCE_CHANGED", "domain vocabulary is bound to another project")
    if semantic_binding is not None and (
        semantic_binding.project_key != project_key or semantic_binding.semantics != vocabulary
    ):
        return topology_failures.fail("SOURCE_CHANGED", "semantic binding does not match the import project and vocabulary")
    graph = source.get("graph")
    if not isinstance(graph, Mapping):
        return topology_failures.fail("INVALID_WIRE_FORMAT", "source.graph must contain the original graph object")
    if graph.get("证据口径") != 2:
        return topology_failures.fail("INVALID_WIRE_FORMAT", "only original graph format 2 is importable as formal evidence")
    required = ("线索ID", "轮次", "现场", "生成日", "节点", "边", "证据", "线索")
    if any(key not in graph for key in required):
        return topology_failures.fail("INVALID_WIRE_FORMAT", "formal source graph is missing required fields")
    lists = {
        "nodes": _require_list(graph, "节点"),
        "edges": _require_list(graph, "边"),
        "evidence": _require_list(graph, "证据"),
        "clues": _require_list(graph, "线索"),
        "dependencies": _require_list(graph, "依赖"),
        "materials": _require_list(source, "materials"),
    }
    companion_categories = (
        ("source_routes", "route_id", "source_route"),
        ("keyword_plans", "plan_id", "keyword_plan"),
        ("source_registry", "source_id", "source_registry"),
        ("attempts", "attempt_id", "attempt"),
        ("candidates", "candidate_id", "candidate"),
        ("gaps", "gap_id", "gap"),
    )
    companion_lists = {key: _require_list(source, key) for key, _, _ in companion_categories}
    failure = next((value for value in (*lists.values(), *companion_lists.values()) if isinstance(value, Failure)), None)
    if failure is not None:
        return failure
    nodes, edges, evidence, clues, dependencies, materials = (lists[key] for key in ("nodes", "edges", "evidence", "clues", "dependencies", "materials"))
    companions = [(item, id_field, category) for key, id_field, category in companion_categories
                  for item in companion_lists[key]]

    records: dict[str, tuple[str, Mapping[str, Any]]] = {}
    for record, id_field, category in [
        *((item, "节点ID", "node") for item in nodes),
        *((item, "边ID", "judgment") for item in edges),
        *((item, "证据ID", "evidence") for item in evidence),
        *((item, "线索ID", "clue") for item in clues),
        *((item, "依赖ID", "logical_dependency") for item in dependencies),
        *((item, "材料ID", "material") for item in materials),
        *companions,
    ]:
        identity = record.get(id_field)
        if not isinstance(identity, str) or not identity:
            return topology_failures.fail("INVALID_WIRE_FORMAT", f"record lacks {id_field}")
        if identity in records:
            return topology_failures.fail("IDENTITY_CONFLICT", "duplicate source identity", {"id": identity})
        records[identity] = (category, record)

    # Keep a missing material target explicit as an unresolved reference node.
    # This preserves graph connectivity without inventing source-owned metadata.
    unresolved_material_refs: dict[str, list[str]] = {}
    for raw in evidence:
        target_id = raw.get("材料ID")
        if isinstance(target_id, str) and target_id and target_id not in records:
            unresolved_material_refs.setdefault(target_id, []).append(str(raw.get("证据ID", "")))
    for target_id in unresolved_material_refs:
        records[target_id] = ("material", {"材料ID": target_id, "__unresolved_reference__": True})

    if semantic_binding is not None:
        profile = semantic_binding.profile
    else:
        try:
            profile = make_retrieval_profile(vocabulary)
        except (AttributeError, TypeError, ValueError) as error:
            return topology_failures.fail("INVALID_STRUCTURE", "domain vocabulary declaration is invalid", {"reason": str(error)})
    source_revision = str(source.get("source_revision") or vocabulary.source_ref.observed_revision)
    source_digest = _digest({"source": source, "vocabulary": _source_ref_wire(vocabulary)})
    storage_state_id = source.get("storage_state_id", graph["线索ID"])
    if not isinstance(storage_state_id, str) or not storage_state_id.strip():
        return topology_failures.fail("INVALID_WIRE_FORMAT", "storage_state_id must be a nonempty string")
    state_key = (project_key, module_id, namespace, storage_state_id)
    revision_by_id = {identity: source_revision for identity in records}

    def bound(identity: str) -> BoundRef:
        category, _ = records[identity]
        type_id = "node:" + str(records[identity][1].get("类型")) if category == "node" else category
        return BoundRef(ElementRef(project_key, module_id, namespace, type_id, identity), revision_by_id[identity])

    elements: list[Element] = []
    extension: dict[str, Any] = {}
    for identity, (category, raw) in records.items():
        attrs: dict[str, Any] = {}
        endpoints: list[Endpoint] = []
        if category == "node":
            attrs = {"source_type": raw["类型"], "name": raw["名称"]}
            for key, target in (("现场归属", "scene_ref"), ("注册", "registration"), ("备注", "note")):
                if key in raw:
                    attrs[target] = raw[key]
        elif category == "judgment":
            attrs = {"edge_type": raw["边类型"], "judgment": raw["判断"], "scope": raw["范围"],
                     "judgment_version": raw["判断版本"], "outline_section": str(raw["大纲节"]),
                     "pools": list(raw.get("池", [])), "relation_classes": list(raw["关系类"]),
                     "evidence_ids": list(raw["证据ID"]), "from_id": raw["从"], "to_id": raw["到"]}
            for role, source_key in (("from", "从"), ("to", "到")):
                target_id = raw[source_key]
                if target_id not in records:
                    return topology_failures.fail("UNRESOLVABLE_REFERENCE", "edge endpoint is absent", {"id": target_id})
                endpoints.append(Endpoint(role, bound(target_id)))
            for key, target in (("中介状态", "mediation_status"), ("注册", "registration"), ("修订自", "semantic_successor_of")):
                if key in raw and raw[key] is not None:
                    attrs[target] = raw[key]
        elif category == "evidence":
            attrs = {"grade": raw["档"], "conflict": raw["打架"] == "是", "effect": raw["作用"],
                     "name": str(raw.get("名称", "")),
                     "original_location": raw["原文定位"], "original_excerpt": raw["原文摘录"],
                     "applicable_scope": raw["适用范围"], "inference_note": raw["推论说明"],
                     "proves": raw["证明对象"], "source_role": raw["来源角色"],
                     "independence_group": raw["独立组"],
                     "upstream_material_ids": [raw["上游材料ID"]] if raw.get("上游材料ID") else [],
                     "conflicting_evidence_ids": [raw["冲突证据ID"]] if raw.get("冲突证据ID") else []}
            for role, target_id in (("judgment", raw["边ID"]), ("material", raw["材料ID"])):
                if target_id not in records:
                    return topology_failures.fail("UNRESOLVABLE_REFERENCE", "evidence reference is absent", {"id": target_id})
                endpoints.append(Endpoint(role, bound(target_id)))
            failure = validate_evidence_v2(attrs)
            if failure:
                return failure
        elif category == "clue":
            order = raw["顺序"]
            if not isinstance(order, list):
                return topology_failures.fail("INVALID_WIRE_FORMAT", "clue 顺序 must be an ordered array")
            invalidated = _source_yes_no(raw.get("作废", False), "作废")
            gate_skipped = _source_yes_no(raw.get("门禁跳过", False), "门禁跳过")
            if isinstance(invalidated, Failure):
                return topology_failures.fail("INVALID_WIRE_FORMAT", invalidated.message, {"id": identity})
            if isinstance(gate_skipped, Failure):
                return topology_failures.fail("INVALID_WIRE_FORMAT", gate_skipped.message, {"id": identity})
            attrs = {"clue_id": raw["线索ID"], "round_id": raw["轮次"], "name": str(raw.get("名称", "")),
                     "scene_id": raw["现场"],
                     "generation_date": str(graph["生成日"]), "invalidated": invalidated,
                     "external_clue_ids": raw.get("外链", []), "pools": raw.get("池", []),
                     "chain_status": raw.get("链状态", ""), "chain_kind": raw.get("链类", ""),
                     "stop_reason": raw.get("停因", ""), "next_hop": raw.get("下一跳", ""),
                     "gate_skipped": gate_skipped, "skip_reason": raw.get("跳过理由", ""),
                     "closing_note": raw.get("收束说明", ""), "scene_label": raw["现场"]}
            for position, target_id in enumerate(order):
                if target_id not in records:
                    # Discontinuities are source structure, not unresolved element refs.
                    if isinstance(target_id, str) and target_id.startswith("断口:"):
                        extension.setdefault("discontinuities", []).append({"clue_id": identity, "position": position, "id": target_id})
                        continue
                    return topology_failures.fail("UNRESOLVABLE_REFERENCE", "clue order reference is absent", {"id": target_id})
                endpoints.append(Endpoint("item", bound(target_id), position))
        elif category == "logical_dependency":
            attrs = {"dependency_id": identity, "broken": raw["断否"] == "是"}
            for role, source_key in (("before", "先"), ("after", "后")):
                target_id = raw[source_key]
                if target_id not in records:
                    return topology_failures.fail("UNRESOLVABLE_REFERENCE", "dependency reference is absent", {"id": target_id})
                endpoints.append(Endpoint(role, bound(target_id)))
        elif category == "material":
            if raw.get("__unresolved_reference__") is True:
                attrs = {"title": "", "url": "", "grade": "", "reference_status": "unresolved_reference",
                         "node_ids": [], "edge_ids": [], "relation_classes": [], "snapshot_path": []}
            else:
                multi_fields = {
                    "node_ids": _source_multi(raw.get("节点ID")),
                    "edge_ids": _source_multi(raw.get("边ID")),
                    "relation_classes": _source_multi(raw.get("关系类")),
                    "snapshot_path": _source_multi(raw.get("快照路径")),
                }
                failure = next((value for value in multi_fields.values() if isinstance(value, Failure)), None)
                if failure is not None:
                    return topology_failures.fail("INVALID_WIRE_FORMAT", failure.message, {"id": identity})
                attrs = {"title": str(raw.get("标题", "")),
                         "url": raw.get("URL", raw.get("url", "")),
                         "grade": str(raw.get("档", "")), "outline_section": str(raw.get("大纲节", "")),
                         **multi_fields, "next_hop": str(raw.get("下一跳", "")),
                         "perspective": str(raw.get("问题意识视角", "")), "registration": str(raw.get("注册", "")),
                         "candidate_key": str(raw.get("候选键", "")), "candidate_id": str(raw.get("候选ID", ""))}
        elif category == "source_route":
            attrs = {"route_id": raw["route_id"], "pool": str(raw["pool"]),
                     "outline_anchor": str(raw.get("outline_anchor", "")),
                     "outline_section": str(raw.get("outline_section", "")),
                     "perspective": str(raw.get("perspective", "")),
                     "proposed_node_type": str(raw.get("proposed_node_type", "")),
                     "proposed_edge_type": str(raw.get("proposed_edge_type", "")),
                     "entry": str(raw.get("entry", "")), "status": str(raw["status"])}
        elif category == "keyword_plan":
            execution_status = str(raw["execution_status"])
            if execution_status == "未执行":
                execution_status = "not_executed"
            attrs = {"plan_id": raw["plan_id"], "kind": str(raw["kind"]),
                     "expression": str(raw["expression"]), "execution_status": execution_status,
                     "source_route_id": str(raw.get("source_route_id", ""))}
            if raw.get("result"):
                attrs["result"] = str(raw["result"])
        elif category == "source_registry":
            attrs = {"source_id": raw["source_id"], "route_id": str(raw.get("route_id", "")),
                     "url": str(raw["url"]), "status": str(raw["status"]),
                     "snapshot_path": str(raw.get("snapshot_path", ""))}
            if raw.get("verified_at"):
                attrs["verified_at"] = str(raw["verified_at"])
        elif category == "attempt":
            result = {"命中": "hit", "未命中": "miss", "访问失败": "access_failed",
                      "偏题": "off_topic"}.get(str(raw["result"]), str(raw["result"]))
            attrs = {"attempt_id": raw["attempt_id"], "query_id": str(raw["query_id"]),
                     "round_id": str(raw["round_id"]), "clue_key": str(raw["clue_key"]),
                     "executed_at": str(raw["executed_at"]), "tool": str(raw["tool"]),
                     "actual_query": str(raw["actual_query"]), "result": result,
                     "source_ids": list(raw.get("source_ids", [])), "material_ids": list(raw.get("material_ids", [])),
                     "next_step": str(raw.get("next_step", "")), "result_note": str(raw.get("result_note", "")),
                     "raw_return_location": str(raw.get("raw_return_location", ""))}
        elif category == "candidate":
            attrs = {"candidate_kind": str(raw["candidate_kind"]), "status": str(raw.get("status", "candidate")),
                     "source_note": str(raw.get("source_note", "")), "authority": str(raw.get("authority", "discovery")),
                     "warnings": list(raw.get("warnings", [])), "conflict_records": list(raw.get("conflict_records", []))}
            targets = raw.get("refers_to", [])
            if not isinstance(targets, list):
                return topology_failures.fail("INVALID_WIRE_FORMAT", "candidate refers_to must be an array")
            for target_id in targets:
                if target_id not in records:
                    return topology_failures.fail("UNRESOLVABLE_REFERENCE", "candidate target is absent", {"id": target_id})
                endpoints.append(Endpoint("refers_to", bound(target_id)))
        elif category == "gap":
            attrs = {"gap_kind": str(raw["gap_kind"]), "description": str(raw["description"]),
                     "investigation_gap": bool(raw["investigation_gap"]), "owner": str(raw.get("owner", "")),
                     "source": str(raw.get("source", "")), "status": str(raw.get("status", ""))}
        elements.append(Element(bound(identity), attrs, tuple(endpoints)))

    # Keep exact owner records and companion documents outside the constrained profile.
    extension["source_graph"] = dict(graph)
    extension["materials"] = materials
    extension["source_companions"] = {
        key: _require_list(source, key)
        for key in ("source_routes", "keyword_plans", "source_registry", "attempts", "candidates", "gaps")
    }
    extension["unresolved_material_refs"] = [
        {"material_id": material_id, "evidence_ids": evidence_ids, "status": "unresolved_reference"}
        for material_id, evidence_ids in sorted(unresolved_material_refs.items())
    ]
    if report_ref is not None:
        extension["report_ref"] = dict(report_ref)
    if report_body is not None:
        extension["report_body"] = report_body
    original_files = source.get("original_files", {})
    if not isinstance(original_files, Mapping) or any(
        not isinstance(path, str) or not isinstance(body, str) for path, body in original_files.items()
    ):
        return topology_failures.fail("INVALID_WIRE_FORMAT", "original_files must map source paths to exact text")
    extension["original_files"] = dict(original_files)
    extension["source_extensions"] = dict(source.get("extensions", {})) if isinstance(source.get("extensions", {}), Mapping) else {}
    elements.append(domain_vocabulary_element(vocabulary))
    if report_body is not None and report_ref is not None:
        report_path = report_ref.get("path")
        report_revision = report_ref.get("revision")
        if not isinstance(report_path, str) or not report_path or not isinstance(report_revision, str) or not report_revision:
            return topology_failures.fail("INVALID_WIRE_FORMAT", "report reference needs source path and revision")
        report_identity = str(report_ref.get("id") or report_path)
        elements.append(Element(
            BoundRef(ElementRef(project_key, module_id, namespace, "report_source_binding", report_identity), source_revision),
            {"report_ref": dict(report_ref), "body_revision": report_revision,
             "body_digest": _digest(report_body), "summary_source": f"{report_path}#body"},
        ))
    state = TopologyState(profile.profile_id, profile.version, tuple(elements))
    failure = validate_state(profile, state)
    if failure:
        return failure
    initial_state_digest = _state_digest(state)
    loss = tuple(sorted(set(source) - {"graph", "materials", "report_body", "report_ref", "extensions",
                                       "domain_vocabulary", "domain_source_ref",
                                       "source_revision", "original_files", "namespace", "storage_state_id", "source_routes",
                                       "keyword_plans", "source_registry", "attempts", "candidates", "gaps"}))
    return ImportPreview(state, profile, state_key, source_digest, source_revision,
        {"source_digest": source_digest, "source_revision": source_revision,
                          "domain_source": _source_ref_wire(vocabulary), "initial_state_digest": initial_state_digest,
                          "original": extension,
                          "loss": list(loss)}, loss, ())


def export_retrieval_bundle(
    *, state: TopologyState, provenance: Mapping[str, Any],
) -> dict[str, Any] | Failure:
    """Export preserved originals plus current DB state and explicit extensions.

    Unknown MRW fields live in ``mrw-extension.json``. The original source graph
    remains unmodified as an owner artifact; edits are represented in the
    canonical topology payload until the source owner applies them.
    """
    original = provenance.get("original")
    if not isinstance(original, Mapping) or not isinstance(original.get("source_graph"), Mapping):
        return topology_failures.fail("INVALID_WIRE_FORMAT", "stored source provenance is absent")
    graph = json.loads(json.dumps(original["source_graph"], ensure_ascii=False))
    unchanged = provenance.get("initial_state_digest") == _state_digest(state)
    vocabulary_record = next((element for element in state.elements
        if element.ref.ref.type_id == "domain_vocabulary"), None)
    vocabulary_attributes = vocabulary_record.attributes if vocabulary_record is not None else {}
    exported_vocabulary = {
        "域名": vocabulary_attributes.get("name"), "节点类型": vocabulary_attributes.get("node_types"),
        "边类型": vocabulary_attributes.get("edge_types"), "问题意识视角": vocabulary_attributes.get("perspectives"),
        "大纲节": vocabulary_attributes.get("outline_sections"), "池": vocabulary_attributes.get("pools"),
        "档": vocabulary_attributes.get("grades"),
    } if vocabulary_record is not None else None
    stored_source_ref = vocabulary_attributes.get("source_ref", {})
    exported_domain_source_ref = {
        "ref": {key: stored_source_ref[key] for key in
            ("project_key", "module_id", "namespace", "type_id", "local_id")},
        "observed_revision": stored_source_ref.get("observed_revision"),
        "content_digest": stored_source_ref.get("content_digest"),
    } if vocabulary_record is not None else None
    if not unchanged:
        if vocabulary_record is not None:
            value = vocabulary_record.attributes
            domain_source_ref = exported_domain_source_ref
            companions = original.get("source_companions", {})
            first_ref = state.elements[0].ref.ref
            source = {
                "namespace": first_ref.namespace,
                "storage_state_id": "provenance-check",
                "source_revision": provenance.get("source_revision", "unknown"),
                "domain_vocabulary": exported_vocabulary,
                "domain_source_ref": domain_source_ref,
                "graph": original["source_graph"], "materials": original.get("materials", []),
                "original_files": original.get("original_files", {}),
                "extensions": original.get("source_extensions", {}),
                **{key: companions.get(key, []) for key in
                    ("source_routes", "keyword_plans", "source_registry", "attempts", "candidates", "gaps")},
            }
            if original.get("report_body") is not None:
                source["report_body"] = original["report_body"]
            if original.get("report_ref") is not None:
                source["report_ref"] = original["report_ref"]
            vocabulary = resolve_domain_vocabulary(first_ref.project_key, source)
            if not isinstance(vocabulary, Failure):
                expected = build_import_preview(project_key=first_ref.project_key,
                    module_id=first_ref.module_id, namespace=first_ref.namespace,
                    source=source, vocabulary=vocabulary, report_body=source.get("report_body"),
                    report_ref=source.get("report_ref"))
                unchanged = not isinstance(expected, Failure) and _state_digest(expected.state) == _state_digest(state)
    elements = {element.ref.ref.local_id: element for element in state.elements}
    graph_rows = (("节点", "node:"), ("边", "judgment"), ("证据", "evidence"), ("线索", "clue"),
                  ("依赖", "logical_dependency"))
    for collection, type_prefix in (() if unchanged else graph_rows):
        for row in graph.get(collection, []):
            identity_key = {"节点": "节点ID", "边": "边ID", "证据": "证据ID", "线索": "线索ID", "依赖": "依赖ID"}[collection]
            current = elements.get(row.get(identity_key))
            if current is None:
                continue
            attrs = current.attributes
            if collection == "节点":
                row.update({"类型": attrs["source_type"], "名称": attrs["name"]})
                for key, source_key in (("现场归属", "scene_ref"), ("注册", "registration"), ("备注", "note")):
                    if source_key in attrs:
                        row[key] = attrs[source_key]
            elif collection == "边":
                translations = {"边类型": "edge_type", "判断": "judgment", "范围": "scope",
                                "判断版本": "judgment_version", "大纲节": "outline_section",
                                "池": "pools", "关系类": "relation_classes", "证据ID": "evidence_ids",
                                "从": "from_id", "到": "to_id", "中介状态": "mediation_status",
                                "修订自": "semantic_successor_of", "注册": "registration"}
                for key, source_key in translations.items():
                    if source_key in attrs:
                        row[key] = attrs[source_key]
            elif collection == "证据":
                translations = {"名称": "name", "档": "grade", "打架": "conflict", "作用": "effect",
                                "原文定位": "original_location", "原文摘录": "original_excerpt",
                                "适用范围": "applicable_scope", "推论说明": "inference_note",
                                "证明对象": "proves", "来源角色": "source_role", "独立组": "independence_group"}
                for key, source_key in translations.items():
                    if source_key in attrs:
                        value = attrs[source_key]
                        row[key] = ("是" if value else "否") if key == "打架" else value
            elif collection == "线索":
                if "name" in attrs:
                    row["名称"] = attrs["name"]
                order = {
                    endpoint.position: endpoint.target.ref.local_id
                    for endpoint in current.endpoints if endpoint.role == "item" and endpoint.position is not None
                }
                for gap in original.get("discontinuities", []):
                    if gap.get("clue_id") == row.get(identity_key):
                        order[int(gap["position"])] = str(gap["id"])
                row["顺序"] = [order[position] for position in sorted(order)]
            elif collection == "依赖":
                row["断否"] = "是" if attrs.get("broken") else "否"
    return {
        "format": "retrieval-source-bundle.v1",
        "domain_vocabulary": exported_vocabulary,
        "domain_source_ref": exported_domain_source_ref,
        "source_graph": graph,
        "materials": list(original.get("materials", [])),
        "source_companions": dict(original.get("source_companions", {})),
        "unresolved_material_refs": list(original.get("unresolved_material_refs", [])),
        "report_body": original.get("report_body"),
        "report_ref": original.get("report_ref"),
        "original_files": dict(original.get("original_files", {})),
        "topology": {
            "profile_id": state.profile_id, "profile_version": state.profile_version,
            "elements": [{"ref": {"ref": {
                "project_key": item.ref.ref.project_key, "module_id": item.ref.ref.module_id,
                "namespace": item.ref.ref.namespace, "type_id": item.ref.ref.type_id,
                "local_id": item.ref.ref.local_id}, "observed_revision": item.ref.observed_revision,
                "content_digest": item.ref.content_digest}, "attributes": dict(item.attributes),
                "endpoints": [{"role": ep.role, "position": ep.position,
                    "target": {"ref": {"project_key": ep.target.ref.project_key,
                        "module_id": ep.target.ref.module_id, "namespace": ep.target.ref.namespace,
                        "type_id": ep.target.ref.type_id, "local_id": ep.target.ref.local_id},
                        "observed_revision": ep.target.observed_revision,
                        "content_digest": ep.target.content_digest}} for ep in item.endpoints]}
                for item in state.elements],
        },
        "mrw-extension.json": {"source_extensions": dict(original.get("source_extensions", {})),
                                "loss": list(provenance.get("loss", [])),
                                "topology_edits_require_source_owner_apply": True},
    }


def export_retrieval_directory(destination: str | Path, bundle: Mapping[str, Any]) -> Path:
    """Write a new export directory without ever replacing source-owned files."""
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=False)
    try:
        (root / "图.json").write_text(
            json.dumps(bundle["source_graph"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (root / "拓扑结构.json").write_text(
            json.dumps(bundle["topology"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (root / "材料.tsv.json").write_text(
            json.dumps(bundle.get("materials", []), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (root / "检索伴随结构.json").write_text(
            json.dumps(bundle.get("source_companions", {}), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (root / "mrw-extension.json").write_text(
            json.dumps(bundle["mrw-extension.json"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report_body = bundle.get("report_body")
        if report_body is not None:
            (root / "报告原文.md").write_text(str(report_body), encoding="utf-8")
        report_ref = bundle.get("report_ref")
        if report_ref is not None:
            (root / "报告来源绑定.json").write_text(
                json.dumps(report_ref, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for relative, body in bundle.get("original_files", {}).items():
            path = PurePosixPath(relative)
            if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
                # kit:boundary owner=information_topology.io.retrieval.export_retrieval_directory.invalid_source_path class=PROGRAMMER_DEFECT failure_family=none witness=test:test_export_retrieval_directory_rejects_invalid_original_paths
                raise ValueError(f"invalid relative source path: {relative!r}")
            target = root.joinpath(*path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                # kit:boundary owner=information_topology.io.retrieval.export_retrieval_directory.path_collision class=PROGRAMMER_DEFECT failure_family=none witness=test:test_export_retrieval_directory_rejects_invalid_original_paths
                raise ValueError(f"source path collides with generated export file: {relative!r}")
            target.write_text(body, encoding="utf-8")
        return root
    except Exception:
        # The path was newly created by this call; remove only its own partial export.
        import shutil
        shutil.rmtree(root)
        # kit:boundary owner=information_topology.io.retrieval.export_retrieval_directory.cleanup_reraise class=LEGACY_COMPATIBILITY_EXCEPTION failure_family=information_topology witness=test:test_export_retrieval_directory_rejects_invalid_original_paths
        raise


class RetrievalStructureIO:
    """P06-compatible port implementation; caller injects its DB session factory."""

    def __init__(self, *, vocabulary_resolver: Callable[[str, Mapping[str, Any]], DomainVocabulary | Failure] | None = None,
                 store: RetrievalTopologyStore,
                 session_factory, profiles: Mapping[tuple[str, str], ProfileSpec] | None = None):
        self.vocabulary_resolver = vocabulary_resolver or resolve_domain_vocabulary
        self.store = store
        self.session_factory = session_factory
        self.profiles = profiles

    def import_structure(self, *, project_key: str, module_id: str, source: Mapping[str, Any]) -> Any:
        vocabulary = self.vocabulary_resolver(project_key, source)
        if isinstance(vocabulary, Failure):
            return vocabulary
        def read_import_semantics(*, source_ref: ElementRef, observed_revision: str,
                                  content_digest: str | None) -> DomainVocabulary | Failure:
            requested = BoundRef(source_ref, observed_revision, content_digest)
            return vocabulary if vocabulary.source_ref == requested else topology_failures.fail(
                "STALE_REFERENCE", "import semantic snapshot differs from its requested source observation"
            )

        binding = resolve_project_semantics(
            read_import_semantics,
            vocabulary.source_ref,
            project_key=project_key,
            profile_factory=make_retrieval_profile,
        )
        if isinstance(binding, Failure):
            return binding
        preview = build_import_preview(project_key=project_key, module_id=module_id,
            namespace=str(source.get("namespace", "retrieval")), source=source,
            vocabulary=binding.semantics, semantic_binding=binding,
            report_body=source.get("report_body"), report_ref=source.get("report_ref"))
        if isinstance(preview, Failure):
            return preview
        with self.session_factory() as session:
            with session.begin():
                existing = self.store.read(session, preview.state_key)
                if existing is not None:
                    prior_digest = (existing.get("provenance") or {}).get("source_digest")
                    if prior_digest != preview.source_digest:
                        return topology_failures.fail("SOURCE_CHANGED", "source identity already exists with changed content")
                    return {"accepted": True, "idempotent": True, "revision": existing["revision"],
                            "state_id": preview.state_key[3], "loss": list(preview.loss)}
                result = self.store.write(session, preview, expected_revision=None)
                if isinstance(result, Failure):
                    return result
                return {"accepted": True, "idempotent": False, "revision": result[0]["revision"],
                        "state_id": preview.state_key[3], "loss": list(preview.loss)}

    def export_structure(self, *, project_key: str, target: Mapping[str, Any], format: str) -> Any:
        if format != "retrieval-source-bundle.v1":
            return topology_failures.fail("INVALID_STRUCTURE", "unsupported retrieval export format")
        key = (project_key, str(target["module_id"]), str(target["namespace"]), str(target["state_id"]))
        with self.session_factory() as session:
            row = self.store.read(session, key)
        if row is None or row.get("deleted"):
            return topology_failures.fail("NOT_FOUND", "retrieval topology state was not found")
        profile = (self.profiles or {}).get((row["profile_id"], row["profile_version"]))
        if profile is None:
            profile = profile_from_state_payload(project_key, row["profile_id"], row["profile_version"], row["payload"])
            if isinstance(profile, Failure):
                return profile
        state = decode_state(profile, row["payload"])
        if isinstance(state, Failure):
            return state
        return export_retrieval_bundle(state=state, provenance=row.get("provenance") or {})
