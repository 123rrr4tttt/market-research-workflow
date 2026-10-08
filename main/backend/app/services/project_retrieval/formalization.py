"""Provider-backed proposal of domain claims from one persisted document body.

The result is deliberately below the topology write boundary.  It contains
local keys and source provenance, while the retrieval executor remains the
only owner of persistent identities, references, and graph writes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
import json
from dataclasses import asdict, dataclass
from typing import Any, cast

from functorial_kit import Failure

from app.services.information_topology.modules.retrieval import validate_evidence_v2
from .contracts import FormalizationResult
from app.successor_runtime.capabilities.retrieval_common import ProjectRetrievalFailureCode, retrieval_failure


ModelInvoke = Callable[[str], object]


@dataclass(frozen=True, slots=True)
class FormalizationDocument:
    document_id: str
    title: str
    url: str
    updated_at: str
    body_digest: str
    body: str


@dataclass(frozen=True, slots=True)
class FormalizationVocabulary:
    name: str
    node_types: tuple[str, ...]
    edge_types: tuple[str, ...]
    outline_sections: tuple[str, ...]
    pools: tuple[str, ...]
    grades: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FormalizationRoute:
    route_id: str
    pool: str
    outline_sections: tuple[str, ...]
    node_types: tuple[str, ...]
    target_edges: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FormalizationInput:
    project_key: str
    plan_id: str
    route_id: str
    query_id: str
    candidate_id: str
    document: FormalizationDocument
    domain_vocabulary: FormalizationVocabulary
    route: FormalizationRoute
    run_id: str | None = None
    session_id: str | None = None

_RELATION_CLASSES = frozenset({"线索链", "逻辑依赖", "证据网"})
_VOCABULARY_KEYS = {
    "name": ("name", "域名"),
    "node_types": ("node_types", "节点类型"),
    "edge_types": ("edge_types", "边类型"),
    "outline_sections": ("outline_sections", "大纲节"),
    "pools": ("pools", "池"),
    "grades": ("grades", "档"),
}


def _invalid(code: ProjectRetrievalFailureCode, message: str, path: str) -> Failure:
    return retrieval_failure(code, message, site="formalization.validation", path=path)


def _failed(code: ProjectRetrievalFailureCode, message: str, *, path: str | None = None) -> FormalizationResult:
    error: dict[str, Any] = {"code": code, "message": message}
    if path is not None:
        error["context"] = {"path": path}
    return cast(FormalizationResult, {"status": "failed", "error": error})


def _failure_result(failure: Failure) -> FormalizationResult:
    context: Mapping[str, object] = failure.context if isinstance(failure.context, Mapping) else {}
    path = context.get("path")
    return _failed(
        cast(ProjectRetrievalFailureCode, failure.code),
        failure.message,
        path=path if isinstance(path, str) else None,
    )


def _failure_path(failure: Failure) -> str:
    context: Mapping[str, object] = failure.context if isinstance(failure.context, Mapping) else {}
    path = context.get("path")
    return path if isinstance(path, str) else "response"


def _object(value: object, path: str, *, code: ProjectRetrievalFailureCode) -> Mapping[str, Any] | Failure:
    if not isinstance(value, Mapping):
        return _invalid(code, "expected an object", path)
    return cast(Mapping[str, Any], value)


def _text(value: object, path: str, *, code: ProjectRetrievalFailureCode) -> str | Failure:
    if not isinstance(value, str) or not value.strip():
        return _invalid(code, "expected a nonempty string", path)
    return value.strip()


def _source_text(value: object, path: str, *, code: ProjectRetrievalFailureCode) -> str | Failure:
    """Validate source bytes represented as text without normalizing them."""
    if not isinstance(value, str) or not value.strip():
        return _invalid(code, "expected nonempty source text", path)
    return value


def _identity(value: object, path: str, *, code: ProjectRetrievalFailureCode) -> str | Failure:
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip():
        return _invalid(code, "expected a nonempty string or integer identity", path)
    return str(value).strip()


def _string_list(
    value: object, path: str, *, code: ProjectRetrievalFailureCode, nonempty: bool = True,
) -> list[str] | Failure:
    if not isinstance(value, list):
        return _invalid(code, "expected an array of nonempty strings", path)
    values = cast(list[object], value)
    if ((nonempty and not values)
            or any(not isinstance(item, str) or not item.strip() for item in values)):
        return _invalid(code, "expected an array of nonempty strings", path)
    normalized = [item.strip() for item in values if isinstance(item, str)]
    if len(normalized) != len(set(normalized)):
        return _invalid(code, "values must be unique", path)
    return normalized


def _only_keys(
    value: Mapping[str, Any], expected: set[str], path: str, *, code: ProjectRetrievalFailureCode,
) -> Failure | None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing or unknown:
        detail: list[str] = []
        if missing:
            detail.append(f"missing {missing}")
        if unknown:
            detail.append(f"unknown {unknown}")
        return _invalid(code, "; ".join(detail), path)
    return None


def _vocabulary_text(value: Mapping[str, Any], aliases: tuple[str, str], path: str) -> str | Failure:
    selected = [value[key] for key in aliases if key in value]
    if len(selected) != 1:
        return _invalid("FORMALIZATION_INPUT_INVALID", f"expected exactly one of {list(aliases)}", path)
    return _text(selected[0], path, code="FORMALIZATION_INPUT_INVALID")


def _vocabulary_list(value: Mapping[str, Any], aliases: tuple[str, str], path: str) -> list[str] | Failure:
    selected = [value[key] for key in aliases if key in value]
    if len(selected) != 1:
        return _invalid("FORMALIZATION_INPUT_INVALID", f"expected exactly one of {list(aliases)}", path)
    return _string_list(selected[0], path, code="FORMALIZATION_INPUT_INVALID")


def _vocabulary(raw: object) -> FormalizationVocabulary | Failure:
    value = _object(raw, "domain_vocabulary", code="FORMALIZATION_INPUT_INVALID")
    if isinstance(value, Failure):
        return value
    name = _vocabulary_text(value, ("name", "域名"), "domain_vocabulary.name")
    if isinstance(name, Failure):
        return name
    node_types = _vocabulary_list(value, ("node_types", "节点类型"), "domain_vocabulary.node_types")
    if isinstance(node_types, Failure):
        return node_types
    edge_types = _vocabulary_list(value, ("edge_types", "边类型"), "domain_vocabulary.edge_types")
    if isinstance(edge_types, Failure):
        return edge_types
    outline_sections = _vocabulary_list(value, ("outline_sections", "大纲节"), "domain_vocabulary.outline_sections")
    if isinstance(outline_sections, Failure):
        return outline_sections
    pools = _vocabulary_list(value, ("pools", "池"), "domain_vocabulary.pools")
    if isinstance(pools, Failure):
        return pools
    grades = _vocabulary_list(value, ("grades", "档"), "domain_vocabulary.grades")
    if isinstance(grades, Failure):
        return grades
    return FormalizationVocabulary(
        name=name, node_types=tuple(node_types), edge_types=tuple(edge_types),
        outline_sections=tuple(outline_sections), pools=tuple(pools), grades=tuple(grades),
    )


def _input(payload: Mapping[str, Any]) -> FormalizationInput | Failure:
    required = ("project_key", "plan_id", "route_id", "query_id", "candidate_id")
    identity: dict[str, str] = {}
    for key in required:
        member = _text(payload.get(key), key, code="FORMALIZATION_INPUT_INVALID")
        if isinstance(member, Failure):
            return member
        identity[key] = member
    run_id = payload.get("run_id")
    session_id = payload.get("session_id")
    if run_id is None and session_id is None:
        return _invalid("FORMALIZATION_INPUT_INVALID", "run_id or session_id is required", "run_id")
    if run_id is not None:
        member = _identity(run_id, "run_id", code="FORMALIZATION_INPUT_INVALID")
        if isinstance(member, Failure):
            return member
        identity["run_id"] = member
    if session_id is not None:
        member = _identity(session_id, "session_id", code="FORMALIZATION_INPUT_INVALID")
        if isinstance(member, Failure):
            return member
        identity["session_id"] = member

    nested_document = payload.get("material", payload.get("document"))
    if payload.get("material") is not None and payload.get("document") is not None:
        if payload["material"] != payload["document"]:
            return _invalid("FORMALIZATION_INPUT_INVALID", "conflicting material body aliases", "material")
    if nested_document is None:
        document: Mapping[str, Any] = {
            "document_id": payload.get("material_id", payload.get("document_id")), "title": payload.get("title"),
            "url": payload.get("url"), "body": payload.get("body"),
            "updated_at": payload.get("material_updated_at", payload.get("document_updated_at")), "body_digest": payload.get("body_digest"),
        }
    else:
        document_value = _object(nested_document, "document", code="FORMALIZATION_INPUT_INVALID")
        if isinstance(document_value, Failure):
            return document_value
        document = document_value
    normalized_document: dict[str, str] = {}
    if document.get("material_id") is not None and document.get("document_id") is not None:
        if str(document["material_id"]) != str(document["document_id"]):
            return _invalid("FORMALIZATION_INPUT_INVALID", "conflicting material identity aliases", "material.material_id")
    if payload.get("material_id") is not None and payload.get("document_id") is not None:
        if str(payload["material_id"]) != str(payload["document_id"]):
            return _invalid("FORMALIZATION_INPUT_INVALID", "conflicting material identity aliases", "material_id")
    document_id = _identity(document.get("material_id", document.get("document_id")), "document.document_id",
                            code="FORMALIZATION_INPUT_INVALID")
    if isinstance(document_id, Failure):
        return document_id
    normalized_document["document_id"] = document_id
    for key in ("title", "url", "updated_at", "body_digest"):
        member = _text(document.get(key), f"document.{key}", code="FORMALIZATION_INPUT_INVALID")
        if isinstance(member, Failure):
            return member
        normalized_document[key] = member
    body = _source_text(document.get("body"), "document.body", code="FORMALIZATION_INPUT_INVALID")
    if isinstance(body, Failure):
        return body
    normalized_document["body"] = body
    actual_digest = sha256(normalized_document["body"].encode("utf-8")).hexdigest()
    if normalized_document["body_digest"] != actual_digest:
        return _invalid(
            "FORMALIZATION_INPUT_INVALID", "body digest does not match the supplied body",
            "document.body_digest",
        )

    vocabulary = _vocabulary(payload.get("domain_vocabulary"))
    if isinstance(vocabulary, Failure):
        return vocabulary
    route = _object(payload.get("source_route", payload.get("route")), "source_route",
                    code="FORMALIZATION_INPUT_INVALID")
    if isinstance(route, Failure):
        return route
    route_id = _text(route.get("route_id"), "route.route_id", code="FORMALIZATION_INPUT_INVALID")
    if isinstance(route_id, Failure):
        return route_id
    if route_id != identity["route_id"]:
        return _invalid("FORMALIZATION_INPUT_INVALID", "route identity does not match payload", "route.route_id")
    pool = _text(route.get("pool"), "route.pool", code="FORMALIZATION_INPUT_INVALID")
    if isinstance(pool, Failure):
        return pool
    outline_sections = _string_list(route.get("outline_sections"), "route.outline_sections",
                                    code="FORMALIZATION_INPUT_INVALID")
    if isinstance(outline_sections, Failure):
        return outline_sections
    node_types = _string_list(route.get("node_types"), "route.node_types",
                              code="FORMALIZATION_INPUT_INVALID")
    if isinstance(node_types, Failure):
        return node_types
    target_edges = _string_list(route.get("target_edges"), "route.target_edges",
                                code="FORMALIZATION_INPUT_INVALID")
    if isinstance(target_edges, Failure):
        return target_edges
    normalized_route = FormalizationRoute(
        route_id=route_id, pool=pool, outline_sections=tuple(outline_sections),
        node_types=tuple(node_types), target_edges=tuple(target_edges),
    )
    containment = (
        ("pool", [pool], vocabulary.pools),
        ("outline_sections", outline_sections, vocabulary.outline_sections),
        ("node_types", node_types, vocabulary.node_types),
        ("target_edges", target_edges, vocabulary.edge_types),
    )
    for route_field, values, allowed in containment:
        outside = sorted(set(values) - set(allowed))
        if outside:
            return _invalid(
                "FORMALIZATION_INPUT_INVALID",
                f"route values are outside the domain vocabulary: {outside}",
                f"route.{route_field}",
            )
    query = payload.get("query")
    if query is not None:
        query = _object(query, "query", code="FORMALIZATION_INPUT_INVALID")
        if isinstance(query, Failure):
            return query
        query_id = _text(query.get("query_id"), "query.query_id", code="FORMALIZATION_INPUT_INVALID")
        if isinstance(query_id, Failure):
            return query_id
        if query_id != identity["query_id"]:
            return _invalid("FORMALIZATION_INPUT_INVALID", "query identity does not match payload", "query.query_id")
        query_route = _text(query.get("route_id"), "query.route_id", code="FORMALIZATION_INPUT_INVALID")
        if isinstance(query_route, Failure):
            return query_route
        if query_route != identity["route_id"]:
            return _invalid("FORMALIZATION_INPUT_INVALID", "query belongs to another route", "query.route_id")
    return FormalizationInput(
        project_key=identity["project_key"], plan_id=identity["plan_id"],
        route_id=identity["route_id"], query_id=identity["query_id"],
        candidate_id=identity["candidate_id"],
        document=FormalizationDocument(
            document_id=normalized_document["document_id"],
            title=normalized_document["title"], url=normalized_document["url"],
            updated_at=normalized_document["updated_at"],
            body_digest=normalized_document["body_digest"],
            body=normalized_document["body"],
        ),
        domain_vocabulary=vocabulary, route=normalized_route,
        run_id=identity.get("run_id"), session_id=identity.get("session_id"),
    )


def _prompt(value: FormalizationInput) -> str:
    contract = {
        "status": "proposed | no_claim",
        "proposal": {
            "nodes": [{
                "local_key": "local key", "name": "verbatim-grounded label",
                "type_id": "node:<domain node type>",
            }],
            "judgment": {
                "from_key": "node local_key", "to_key": "node local_key", "edge_type": "route target edge",
                "judgment": "one claim supported or qualified by the quote", "scope": "claim scope",
                "outline_section": "route outline section", "pools": ["route pool"],
                "relation_classes": ["证据网"],
            },
            "evidence": {
                "original_location": "location in this document", "original_excerpt": "exact body substring",
                "grade": "domain grade", "conflict": False, "effect": "支持 | 反驳 | 限定",
                "applicable_scope": "scope", "inference_note": "quote-to-claim reasoning",
                "proves": "事实关系 | 表达事实",
                "source_role": "直接记录 | 当事方陈述 | 机构自报 | 二手转述 | 研究推论",
                "independence_group": "source independence identity",
            },
            "clue": {"name": "short clue name", "scene_key": "local_key of a node:现场 node"},
        },
        "gaps": ["reason no defensible claim can be proposed, or remaining qualification"],
    }
    model_input = {
        "project_key": value.project_key, "plan_id": value.plan_id,
        "route_id": value.route_id, "query_id": value.query_id,
        "candidate_id": value.candidate_id, "document": asdict(value.document),
        "domain_vocabulary": asdict(value.domain_vocabulary), "route": asdict(value.route),
    }
    return (
        "Read the supplied document and return exactly one JSON object. Do not use markdown. "
        "Propose one semantic claim only when an exact quote in document.body warrants it. "
        "For no_claim return only status and nonempty gaps; omit proposal entirely. "
        "For proposed return status, proposal and optional gaps. "
        "Use only route-constrained domain vocabulary values. Do not invent topology IDs, refs, "
        "extra relations, facts, or quotations. Return no_claim with explicit gaps when the body "
        "does not warrant a claim. The required response contract is:\n"
        + json.dumps(contract, ensure_ascii=False, sort_keys=True)
        + "\nINPUT:\n"
        + json.dumps(model_input, ensure_ascii=False, sort_keys=True)
    )


def _response_value(response: object) -> Mapping[str, Any] | Failure:
    if hasattr(response, "content"):
        response = getattr(response, "content")
    if isinstance(response, Mapping):
        return cast(Mapping[str, Any], response)
    if isinstance(response, Sequence) and not isinstance(response, (str, bytes, bytearray)):
        sequence = cast(Sequence[object], response)
        text_parts: list[str] = []
        for item in sequence:
            if not isinstance(item, Mapping):
                continue
            item_mapping = cast(Mapping[str, object], item)
            text = item_mapping.get("text")
            if isinstance(text, str):
                text_parts.append(text)
        response = "".join(text_parts)
    if not isinstance(response, str):
        return _invalid("FORMALIZATION_RESPONSE_INVALID", "provider did not return JSON text or an object", "response")
    text = response.strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    try:
        parsed: object = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        return _invalid(
            "FORMALIZATION_RESPONSE_INVALID", f"provider response is not valid JSON: {exc}", "response",
        )
    return _object(parsed, "response", code="FORMALIZATION_RESPONSE_INVALID")


def _gaps(value: object, *, required: bool) -> list[str] | Failure:
    if value is None and not required:
        return []
    return _string_list(value, "response.gaps", code="FORMALIZATION_RESPONSE_INVALID", nonempty=required)


def _proposal(raw: object, source: FormalizationInput) -> dict[str, Any] | Failure:
    code = "FORMALIZATION_PROPOSAL_INVALID"
    value = _object(raw, "response.proposal", code=code)
    if isinstance(value, Failure):
        return value
    invalid = _only_keys(value, {"nodes", "judgment", "evidence", "clue"}, "response.proposal", code=code)
    if invalid is not None:
        return invalid

    raw_nodes = value["nodes"]
    if not isinstance(raw_nodes, list) or not raw_nodes:
        return _invalid(code, "expected at least one node", "response.proposal.nodes")
    nodes: list[dict[str, str]] = []
    node_keys: set[str] = set()
    allowed_node_types = set(source.domain_vocabulary.node_types)
    for index, raw_node in enumerate(cast(list[object], raw_nodes)):
        path = f"response.proposal.nodes[{index}]"
        node = _object(raw_node, path, code=code)
        if isinstance(node, Failure):
            return node
        invalid = _only_keys(node, {"local_key", "name", "type_id"}, path, code=code)
        if invalid is not None:
            return invalid
        local_key = _text(node["local_key"], f"{path}.local_key", code=code)
        if isinstance(local_key, Failure):
            return local_key
        name = _text(node["name"], f"{path}.name", code=code)
        if isinstance(name, Failure):
            return name
        type_id = _text(node["type_id"], f"{path}.type_id", code=code)
        if isinstance(type_id, Failure):
            return type_id
        if local_key in node_keys:
            return _invalid(code, "node local keys must be unique", f"{path}.local_key")
        if not type_id.startswith("node:") or type_id[5:] not in allowed_node_types:
            return _invalid(code, "node type is outside the domain vocabulary", f"{path}.type_id")
        node_keys.add(local_key)
        nodes.append({"local_key": local_key, "name": name, "type_id": type_id})

    judgment = _object(value["judgment"], "response.proposal.judgment", code=code)
    if isinstance(judgment, Failure):
        return judgment
    judgment_keys = {"from_key", "to_key", "edge_type", "judgment", "scope", "outline_section",
                     "pools", "relation_classes"}
    invalid = _only_keys(judgment, judgment_keys, "response.proposal.judgment", code=code)
    if invalid is not None:
        return invalid
    normalized_judgment: dict[str, Any] = {}
    for key in ("from_key", "to_key", "edge_type", "judgment", "scope", "outline_section"):
        member = _text(judgment[key], f"response.proposal.judgment.{key}", code=code)
        if isinstance(member, Failure):
            return member
        normalized_judgment[key] = member
    for key in ("pools", "relation_classes"):
        member = _string_list(judgment[key], f"response.proposal.judgment.{key}", code=code)
        if isinstance(member, Failure):
            return member
        normalized_judgment[key] = member
    if normalized_judgment["from_key"] not in node_keys or normalized_judgment["to_key"] not in node_keys:
        return _invalid(code, "judgment endpoints must refer to proposed node local keys",
                        "response.proposal.judgment")
    if normalized_judgment["edge_type"] not in source.route.target_edges:
        return _invalid(code, "edge type is outside the route and domain vocabulary",
                        "response.proposal.judgment.edge_type")
    if normalized_judgment["outline_section"] not in source.route.outline_sections:
        return _invalid(code, "outline section is outside the route and domain vocabulary",
                        "response.proposal.judgment.outline_section")
    if normalized_judgment["pools"] != [source.route.pool]:
        return _invalid(code, "judgment pools must equal the selected route pool",
                        "response.proposal.judgment.pools")
    if (any(item not in _RELATION_CLASSES for item in normalized_judgment["relation_classes"])
            or "证据网" not in normalized_judgment["relation_classes"]):
        return _invalid(code, "relation classes must be profile values and include 证据网",
                        "response.proposal.judgment.relation_classes")

    evidence = _object(value["evidence"], "response.proposal.evidence", code=code)
    if isinstance(evidence, Failure):
        return evidence
    evidence_keys = {"original_location", "original_excerpt", "grade", "conflict", "effect",
                     "applicable_scope", "inference_note", "proves", "source_role", "independence_group"}
    invalid = _only_keys(evidence, evidence_keys, "response.proposal.evidence", code=code)
    if invalid is not None:
        return invalid
    normalized_evidence: dict[str, Any] = {}
    for key in evidence_keys - {"conflict", "original_excerpt"}:
        member = _text(evidence[key], f"response.proposal.evidence.{key}", code=code)
        if isinstance(member, Failure):
            return member
        normalized_evidence[key] = member
    excerpt = _source_text(evidence["original_excerpt"], "response.proposal.evidence.original_excerpt", code=code)
    if isinstance(excerpt, Failure):
        return excerpt
    normalized_evidence["original_excerpt"] = excerpt
    if type(evidence["conflict"]) is not bool:
        return _invalid(code, "conflict must be boolean", "response.proposal.evidence.conflict")
    normalized_evidence["conflict"] = evidence["conflict"]
    if normalized_evidence["grade"] not in source.domain_vocabulary.grades:
        return _invalid(code, "evidence grade is outside the domain vocabulary",
                        "response.proposal.evidence.grade")
    if normalized_evidence["original_excerpt"] not in source.document.body:
        return _invalid(code, "evidence excerpt is not an exact substring of document.body",
                        "response.proposal.evidence.original_excerpt")
    evidence_failure = validate_evidence_v2(normalized_evidence)
    if evidence_failure is not None:
        return _invalid(code, evidence_failure.message, "response.proposal.evidence")

    clue = _object(value["clue"], "response.proposal.clue", code=code)
    if isinstance(clue, Failure):
        return clue
    invalid = _only_keys(clue, {"name", "scene_key"}, "response.proposal.clue", code=code)
    if invalid is not None:
        return invalid
    normalized_clue: dict[str, str] = {}
    for key in ("name", "scene_key"):
        member = _text(clue[key], f"response.proposal.clue.{key}", code=code)
        if isinstance(member, Failure):
            return member
        normalized_clue[key] = member
    scene_nodes = {node["local_key"] for node in nodes if node["type_id"] == "node:现场"}
    if normalized_clue["scene_key"] not in scene_nodes:
        return _invalid(code, "clue scene_key must refer to a proposed node:现场 node",
                        "response.proposal.clue.scene_key")

    document = source.document
    provenance = {
        "project_key": source.project_key, "plan_id": source.plan_id,
        "route_id": source.route_id, "query_id": source.query_id,
        "candidate_id": source.candidate_id,
        "document_id": document.document_id, "document_url": document.url,
        "document_updated_at": document.updated_at, "body_digest": document.body_digest,
    }
    if source.run_id is not None:
        provenance["run_id"] = source.run_id
    if source.session_id is not None:
        provenance["session_id"] = source.session_id
    return {"nodes": nodes, "judgment": normalized_judgment, "evidence": normalized_evidence,
            "clue": normalized_clue, "provenance": provenance}


def _validated_response(response: Mapping[str, Any], source: FormalizationInput) -> dict[str, Any] | Failure:
    status = response.get("status")
    if status == "no_claim":
        invalid = _only_keys(response, {"status", "gaps"}, "response", code="FORMALIZATION_RESPONSE_INVALID")
        if invalid is not None:
            return invalid
        gaps = _gaps(response.get("gaps"), required=True)
        if isinstance(gaps, Failure):
            return gaps
        return {"status": "no_claim", "gaps": gaps}
    if status != "proposed":
        return _invalid(
            "FORMALIZATION_RESPONSE_INVALID", "status must be proposed or no_claim", "response.status",
        )
    invalid = _only_keys(response, {"status", "proposal", "gaps"}, "response",
                         code="FORMALIZATION_RESPONSE_INVALID")
    if invalid is not None:
        return invalid
    proposal = _proposal(response.get("proposal"), source)
    if isinstance(proposal, Failure):
        return proposal
    gaps = _gaps(response.get("gaps"), required=False)
    if isinstance(gaps, Failure):
        return gaps
    return {"status": "proposed", "proposal": proposal, "gaps": gaps}


def formalize_document(
    payload: object, *, model_invoke: ModelInvoke | None = None,
) -> FormalizationResult:
    """Return one validated proposal/no-claim result without writing topology state.

    ``model_invoke`` is a narrow injection seam for deterministic fixtures.  A
    production caller omits it and therefore always resolves the configured
    provider through ``get_chat_model``.  Provider failure is explicit; this
    function never supplies synthetic or heuristic proposal text.
    """
    if not isinstance(payload, Mapping):
        return _failed("FORMALIZATION_INPUT_INVALID", "payload must be an object", path="payload")
    source = _input(cast(Mapping[str, Any], payload))
    if isinstance(source, Failure):
        return _failure_result(source)
    return formalize_normalized(source, model_invoke=model_invoke)


def formalize_normalized(
    source: FormalizationInput, *, model_invoke: ModelInvoke | None = None,
) -> FormalizationResult:
    """Run the provider-backed proposal against one already-normalized input."""
    prompt = _prompt(source)
    try:
        invoke = model_invoke
        if invoke is None:
            # Import at the actual effect boundary so pure proposal validation
            # and injected fixtures do not initialize a provider stack.
            from app.services.llm.provider import get_chat_model

            model = get_chat_model(temperature=0.0, max_tokens=2400)
            invoke = model.invoke
        raw_response = invoke(prompt)
    except Exception as exc:
        return _failed("FORMALIZATION_PROVIDER_FAILED", str(exc))

    initial_value = _response_value(raw_response)
    initial_result = (
        initial_value if isinstance(initial_value, Failure)
        else _validated_response(initial_value, source)
    )
    if not isinstance(initial_result, Failure):
        return cast(FormalizationResult, initial_result)

    # A correction is a second provider judgment, never a parser or evidence
    # shortcut. Its result passes the same strict validator exactly once.
    correction = (
        prompt
        + f"\nYour previous response was invalid at {_failure_path(initial_result)}: {initial_result.message}. "
        "Re-evaluate the body and return exactly one valid JSON object. "
        "Use no_claim if the evidence requirements cannot be met."
    )
    try:
        corrected_response = invoke(correction)
    except Exception as provider_exc:
        return _failed("FORMALIZATION_PROVIDER_FAILED", str(provider_exc))
    corrected_value = _response_value(corrected_response)
    corrected_result = (
        corrected_value if isinstance(corrected_value, Failure)
        else _validated_response(corrected_value, source)
    )
    if isinstance(corrected_result, Failure):
        return _failure_result(corrected_result)
    return cast(FormalizationResult, corrected_result)


def formalize_material(
    payload: object, *, model_invoke: ModelInvoke | None = None,
) -> FormalizationResult:
    """Canonical material capability; legacy provenance keys remain read aliases."""
    result = cast(dict[str, Any], dict(formalize_document(payload, model_invoke=model_invoke)))
    if isinstance(result.get("proposal"), Mapping):
        proposal = dict(cast(Mapping[str, Any], result["proposal"]))
        provenance_value = proposal.get("provenance")
        provenance = (
            dict(cast(Mapping[str, Any], provenance_value))
            if isinstance(provenance_value, Mapping)
            else {}
        )
        for key in ("id", "url", "updated_at"):
            if "document_" + key in provenance:
                provenance["material_" + key] = provenance["document_" + key]
        proposal["provenance"] = provenance
        result["proposal"] = proposal
    return cast(FormalizationResult, result)
