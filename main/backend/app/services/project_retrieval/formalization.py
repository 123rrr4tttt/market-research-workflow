"""Provider-backed proposal of domain claims from one persisted document body.

The result is deliberately below the topology write boundary.  It contains
local keys and source provenance, while the retrieval executor remains the
only owner of persistent identities, references, and graph writes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from hashlib import sha256
import json
from typing import Any

from functorial_kit import Failure

from app.services.information_topology.modules.retrieval import validate_evidence_v2
from .failures import retrieval_failure


ModelInvoke = Callable[[str], Any]

_RELATION_CLASSES = frozenset({"线索链", "逻辑依赖", "证据网"})
_VOCABULARY_KEYS = {
    "name": ("name", "域名"),
    "node_types": ("node_types", "节点类型"),
    "edge_types": ("edge_types", "边类型"),
    "outline_sections": ("outline_sections", "大纲节"),
    "pools": ("pools", "池"),
    "grades": ("grades", "档"),
}


def _invalid(code: str, message: str, path: str) -> Failure:
    return retrieval_failure(code, message, site="formalization.validation", path=path)


def _failed(code: str, message: str, *, path: str | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if path is not None:
        error["context"] = {"path": path}
    return {"status": "failed", "error": error}


def _failure_result(failure: Failure) -> dict[str, Any]:
    context = failure.context if isinstance(failure.context, Mapping) else {}
    path = context.get("path")
    return _failed(failure.code, failure.message, path=path if isinstance(path, str) else None)


def _failure_path(failure: Failure) -> str:
    context = failure.context if isinstance(failure.context, Mapping) else {}
    path = context.get("path")
    return path if isinstance(path, str) else "response"


def _object(value: object, path: str, *, code: str) -> Mapping[str, Any] | Failure:
    if not isinstance(value, Mapping):
        return _invalid(code, "expected an object", path)
    return value


def _text(value: object, path: str, *, code: str) -> str | Failure:
    if not isinstance(value, str) or not value.strip():
        return _invalid(code, "expected a nonempty string", path)
    return value.strip()


def _source_text(value: object, path: str, *, code: str) -> str | Failure:
    """Validate source bytes represented as text without normalizing them."""
    if not isinstance(value, str) or not value.strip():
        return _invalid(code, "expected nonempty source text", path)
    return value


def _identity(value: object, path: str, *, code: str) -> str | Failure:
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).strip():
        return _invalid(code, "expected a nonempty string or integer identity", path)
    return str(value).strip()


def _string_list(value: object, path: str, *, code: str, nonempty: bool = True) -> list[str] | Failure:
    if (not isinstance(value, list) or (nonempty and not value)
            or any(not isinstance(item, str) or not item.strip() for item in value)):
        return _invalid(code, "expected an array of nonempty strings", path)
    normalized = [item.strip() for item in value]
    if len(normalized) != len(set(normalized)):
        return _invalid(code, "values must be unique", path)
    return normalized


def _only_keys(value: Mapping[str, Any], expected: set[str], path: str, *, code: str) -> Failure | None:
    missing = sorted(expected - set(value))
    unknown = sorted(set(value) - expected)
    if missing or unknown:
        detail = []
        if missing:
            detail.append(f"missing {missing}")
        if unknown:
            detail.append(f"unknown {unknown}")
        return _invalid(code, "; ".join(detail), path)
    return None


def _vocabulary(raw: object) -> dict[str, Any] | Failure:
    value = _object(raw, "domain_vocabulary", code="FORMALIZATION_INPUT_INVALID")
    if isinstance(value, Failure):
        return value
    result: dict[str, Any] = {}
    for canonical, aliases in _VOCABULARY_KEYS.items():
        selected = [value[key] for key in aliases if key in value]
        if len(selected) != 1:
            return _invalid(
                "FORMALIZATION_INPUT_INVALID",
                f"expected exactly one of {list(aliases)}",
                f"domain_vocabulary.{canonical}",
            )
        member = (_text(selected[0], f"domain_vocabulary.{canonical}",
                        code="FORMALIZATION_INPUT_INVALID")
                  if canonical == "name" else
                  _string_list(selected[0], f"domain_vocabulary.{canonical}",
                               code="FORMALIZATION_INPUT_INVALID"))
        if isinstance(member, Failure):
            return member
        result[canonical] = member
    return result


def _input(payload: Mapping[str, Any]) -> dict[str, Any] | Failure:
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

    nested_document = payload.get("document")
    if nested_document is None:
        document: Mapping[str, Any] = {
            "document_id": payload.get("document_id"), "title": payload.get("title"),
            "url": payload.get("url"), "body": payload.get("body"),
            "updated_at": payload.get("document_updated_at"), "body_digest": payload.get("body_digest"),
        }
    else:
        document = _object(nested_document, "document", code="FORMALIZATION_INPUT_INVALID")
        if isinstance(document, Failure):
            return document
    normalized_document: dict[str, str] = {}
    document_id = _identity(document.get("document_id"), "document.document_id",
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
    normalized_route: dict[str, Any] = {"route_id": route_id}
    pool = _text(route.get("pool"), "route.pool", code="FORMALIZATION_INPUT_INVALID")
    if isinstance(pool, Failure):
        return pool
    normalized_route["pool"] = pool
    for key in ("outline_sections", "node_types", "target_edges"):
        member = _string_list(route.get(key), f"route.{key}", code="FORMALIZATION_INPUT_INVALID")
        if isinstance(member, Failure):
            return member
        normalized_route[key] = member
    containment = (
        ("pool", [normalized_route["pool"]], "pools"),
        ("outline_sections", normalized_route["outline_sections"], "outline_sections"),
        ("node_types", normalized_route["node_types"], "node_types"),
        ("target_edges", normalized_route["target_edges"], "edge_types"),
    )
    for route_field, values, vocabulary_field in containment:
        outside = sorted(set(values) - set(vocabulary[vocabulary_field]))
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
    return {**identity, "document": normalized_document, "domain_vocabulary": vocabulary,
            "route": normalized_route}


def _prompt(value: Mapping[str, Any]) -> str:
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
        "project_key": value["project_key"], "plan_id": value["plan_id"],
        "route_id": value["route_id"], "query_id": value["query_id"],
        "candidate_id": value["candidate_id"], "document": value["document"],
        "domain_vocabulary": value["domain_vocabulary"], "route": value["route"],
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


def _response_value(response: Any) -> Mapping[str, Any] | Failure:
    if hasattr(response, "content"):
        response = response.content
    if isinstance(response, Mapping):
        return response
    if isinstance(response, Sequence) and not isinstance(response, (str, bytes, bytearray)):
        text_parts = [item.get("text") for item in response if isinstance(item, Mapping)
                      and isinstance(item.get("text"), str)]
        response = "".join(text_parts)
    if not isinstance(response, str):
        return _invalid("FORMALIZATION_RESPONSE_INVALID", "provider did not return JSON text or an object", "response")
    text = response.strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        return _invalid(
            "FORMALIZATION_RESPONSE_INVALID", f"provider response is not valid JSON: {exc}", "response",
        )
    return _object(parsed, "response", code="FORMALIZATION_RESPONSE_INVALID")


def _gaps(value: object, *, required: bool) -> list[str] | Failure:
    if value is None and not required:
        return []
    return _string_list(value, "response.gaps", code="FORMALIZATION_RESPONSE_INVALID", nonempty=required)


def _proposal(raw: object, source: Mapping[str, Any]) -> dict[str, Any] | Failure:
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
    allowed_node_types = set(source["domain_vocabulary"]["node_types"])
    for index, raw_node in enumerate(raw_nodes):
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
    if normalized_judgment["edge_type"] not in source["route"]["target_edges"]:
        return _invalid(code, "edge type is outside the route and domain vocabulary",
                        "response.proposal.judgment.edge_type")
    if normalized_judgment["outline_section"] not in source["route"]["outline_sections"]:
        return _invalid(code, "outline section is outside the route and domain vocabulary",
                        "response.proposal.judgment.outline_section")
    if normalized_judgment["pools"] != [source["route"]["pool"]]:
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
    if normalized_evidence["grade"] not in source["domain_vocabulary"]["grades"]:
        return _invalid(code, "evidence grade is outside the domain vocabulary",
                        "response.proposal.evidence.grade")
    if normalized_evidence["original_excerpt"] not in source["document"]["body"]:
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

    document = source["document"]
    provenance = {
        "project_key": source["project_key"], "plan_id": source["plan_id"],
        "route_id": source["route_id"], "query_id": source["query_id"],
        "candidate_id": source["candidate_id"],
        "document_id": document["document_id"], "document_url": document["url"],
        "document_updated_at": document["updated_at"], "body_digest": document["body_digest"],
    }
    if "run_id" in source:
        provenance["run_id"] = source["run_id"]
    if "session_id" in source:
        provenance["session_id"] = source["session_id"]
    return {"nodes": nodes, "judgment": normalized_judgment, "evidence": normalized_evidence,
            "clue": normalized_clue, "provenance": provenance}


def _validated_response(response: Mapping[str, Any], source: Mapping[str, Any]) -> dict[str, Any] | Failure:
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
    payload: Mapping[str, Any], *, model_invoke: ModelInvoke | None = None,
) -> Mapping[str, Any]:
    """Return one validated proposal/no-claim result without writing topology state.

    ``model_invoke`` is a narrow injection seam for deterministic fixtures.  A
    production caller omits it and therefore always resolves the configured
    provider through ``get_chat_model``.  Provider failure is explicit; this
    function never supplies synthetic or heuristic proposal text.
    """
    if not isinstance(payload, Mapping):
        return _failed("FORMALIZATION_INPUT_INVALID", "payload must be an object", path="payload")
    source = _input(payload)
    if isinstance(source, Failure):
        return _failure_result(source)

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
        return initial_result

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
    return corrected_result
