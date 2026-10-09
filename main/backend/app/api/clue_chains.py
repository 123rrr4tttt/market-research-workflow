from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeGuard, TypeVar

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from ..contracts import ApiEnvelope, ErrorCode, error_response, success_response
from ..contracts.schemas.clue_chains import (
    ClueChainCloseData,
    ClueChainCloseRequest,
    ClueChainCreateRequest,
    ClueChainDecisionRequest,
    ClueChainDecisionResponseData,
    ClueChainDetailData,
    ClueChainExpandRequest,
    ClueChainExpansionData,
    ClueChainListData,
)
from ..services.clue_chains import (
    ClueChainClosedError,
    ClueChainNotFoundError,
    ClueChainObjectMissingError,
    ClueChainService,
    InMemoryClueChainStore,
    expand_external_search,
    expand_source_library_hop,
)


router = APIRouter(prefix="/clue-chains", tags=["clue-chains"])

ClueChainDetailEnvelope = ApiEnvelope[ClueChainDetailData]
ClueChainListEnvelope = ApiEnvelope[ClueChainListData]
ClueChainExpansionEnvelope = ApiEnvelope[ClueChainExpansionData]
ClueChainDecisionEnvelope = ApiEnvelope[ClueChainDecisionResponseData]
ClueChainCloseEnvelope = ApiEnvelope[ClueChainCloseData]

_test_store: InMemoryClueChainStore | None = None
_DEFAULT_EXTERNAL_FIXTURE = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "clue_chains" / "external_search_results.json"
)


def reset_clue_chain_service_for_tests() -> None:
    global _test_store
    _test_store = InMemoryClueChainStore(project_key="demo_proj")


def _service_for_project(project_key: str | None = None) -> ClueChainService:
    if _test_store is not None:
        return ClueChainService(store=_test_store)
    return ClueChainService(project_key=project_key)


def _http_error(status_code: int, code: ErrorCode, message: str, *, details: dict[str, Any] | None = None) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=error_response(code, message, details=details),
        headers={"X-Error-Code": code.value},
    )


def _project_key_from_request(request: Request, payload_project_key: str | None = None) -> str:
    project_key = (
        (payload_project_key or "").strip()
        or str(getattr(request.state, "project_key_resolved", "") or "").strip()
        or (request.headers.get("X-Project-Key") or "").strip()
        or (request.query_params.get("project_key") or "").strip()
    )
    if not project_key:
        raise _http_error(400, ErrorCode.INVALID_INPUT, "project_key is required")
    return project_key


_ModelT = TypeVar("_ModelT", bound=BaseModel)


def _serialize(model_type: type[_ModelT], payload: Mapping[str, object]) -> dict[str, Any]:
    return model_type.model_validate(payload).model_dump()


def _is_object_mapping(value: object) -> TypeGuard[Mapping[object, object]]:
    return isinstance(value, Mapping)


def _object_mapping(value: object) -> Mapping[object, object]:
    return value if _is_object_mapping(value) else {}


def _string_object_mapping(value: object) -> dict[str, object]:
    return {key: item for key, item in _object_mapping(value).items() if isinstance(key, str)}


def _is_object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _object_list(value: object) -> list[object]:
    return value if _is_object_list(value) else []


def _string_list(value: object) -> list[str]:
    return [item for item in _object_list(value) if isinstance(item, str)]


def _map_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (ClueChainNotFoundError, ClueChainObjectMissingError, KeyError)):
        return _http_error(404, ErrorCode.NOT_FOUND, str(exc).strip("'") or "clue chain not found")
    if isinstance(exc, (ClueChainClosedError, ValueError)):
        return _http_error(400, ErrorCode.INVALID_INPUT, str(exc))
    return _http_error(
        500,
        ErrorCode.INTERNAL_ERROR,
        "clue chain request failed",
        details={"exception_type": exc.__class__.__name__},
    )


def _chain_for_api(aggregate: Mapping[str, object]) -> dict[str, Any]:
    chain = _string_object_mapping(aggregate.get("chain")) or {
        key: value for key, value in aggregate.items()
    }
    metadata = _string_object_mapping(chain.get("metadata"))
    metadata.setdefault("internal_status", chain.get("status"))
    metadata.setdefault("objective", chain.get("objective"))
    return {
        "chain_id": str(chain.get("chain_id") or ""),
        "project_key": str(chain.get("project_key") or ""),
        "graph_id": str(chain.get("graph_id") or "default"),
        "title": str(chain.get("title") or ""),
        "question": chain.get("objective"),
        "status": "closed" if chain.get("status") == "closed" else "open",
        "root_node_ids": _string_list(chain.get("seed_node_ids") or chain.get("root_node_ids")),
        "frontier_node_ids": _string_list(chain.get("frontier_node_ids")),
        "hop_ids": [
            str(item_mapping.get("hop_id") or "")
            for item in _object_list(aggregate.get("hops"))
            if (item_mapping := _string_object_mapping(item))
        ],
        "candidate_count": len(_object_list(aggregate.get("candidates"))),
        "evidence_count": len(_object_list(aggregate.get("evidence"))),
        "decision_count": len(_object_list(aggregate.get("decisions"))),
        "created_at": str(chain.get("created_at") or chain.get("updated_at") or ""),
        "updated_at": str(chain.get("updated_at") or chain.get("created_at") or ""),
        "closed_at": chain.get("closed_at"),
        "close_reason": chain.get("close_reason"),
        "metadata": metadata,
    }


def _hop_for_api(hop: Mapping[str, object]) -> dict[str, Any]:
    query_json = hop.get("query_json")
    query = ""
    if (query_mapping := _object_mapping(query_json)):
        query = str(query_mapping.get("query") or query_mapping.get("text") or "")
    elif query_json is not None:
        query = str(query_json)
    status = str(hop.get("status") or "planned")
    return {
        "hop_id": str(hop.get("hop_id") or ""),
        "chain_id": str(hop.get("chain_id") or ""),
        "mode": _api_mode(hop.get("mode")),
        "query": query or None,
        "status": _api_hop_status(status),
        "frontier_node_ids": [str(hop.get("input_node_id"))] if hop.get("input_node_id") else [],
        "candidate_ids": _string_list(hop.get("candidate_ids")),
        "evidence_ids": _string_list(hop.get("evidence_ids")),
        "created_at": str(hop.get("started_at") or ""),
        "completed_at": hop.get("finished_at"),
        "metadata": {
            "internal_status": status,
            "provider": hop.get("provider"),
            "params": _string_object_mapping(hop.get("params")),
            "trace": _string_object_mapping(hop.get("trace")),
        },
    }


def _evidence_for_api(evidence: Mapping[str, object], candidate_by_evidence: Mapping[str, str]) -> dict[str, Any]:
    evidence_id = str(evidence.get("evidence_id") or "")
    source_ref = evidence.get("source_ref")
    return {
        "evidence_id": evidence_id,
        "chain_id": str(evidence.get("chain_id") or ""),
        "hop_id": str(evidence.get("hop_id") or ""),
        "candidate_id": candidate_by_evidence.get(evidence_id),
        "source_type": str(evidence.get("source_kind") or "manual"),
        "source_ref": source_ref if isinstance(source_ref, Mapping) else source_ref,
        "title": evidence.get("title"),
        "url": evidence.get("url"),
        "snippet": evidence.get("snippet"),
        "node_refs": [],
        "created_at": str(evidence.get("captured_at") or ""),
        "metadata": {
            **_string_object_mapping(evidence.get("metadata")),
            "provider": evidence.get("provider"),
            "query": evidence.get("query"),
            "internal_status": evidence.get("status"),
        },
    }


def _candidate_for_api(candidate: Mapping[str, object]) -> dict[str, Any]:
    return {
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "chain_id": str(candidate.get("chain_id") or ""),
        "hop_id": str(candidate.get("hop_id") or ""),
        "label": str(candidate.get("value") or candidate.get("label") or ""),
        "candidate_type": str(candidate.get("entity_type") or candidate.get("candidate_type") or "node"),
        "aliases": _string_list(candidate.get("aliases")),
        "confidence": candidate.get("score"),
        "status": _api_candidate_status(candidate.get("decision_status")),
        "evidence_ids": _string_list(candidate.get("evidence_ids")),
        "target_node_id": candidate.get("graph_node_id"),
        "edge": None,
        "metadata": {
            **_string_object_mapping(candidate.get("metadata")),
            "canonical_key": candidate.get("canonical_key"),
            "properties": _string_object_mapping(candidate.get("properties")),
            "internal_status": candidate.get("decision_status"),
        },
    }


def _decision_for_api(
    decision: Mapping[str, object],
    candidate: Mapping[str, object] | None = None,
) -> dict[str, Any]:
    action = str(decision.get("decision") or decision.get("action") or "defer")
    return {
        "decision_id": str(decision.get("decision_id") or ""),
        "chain_id": str(decision.get("chain_id") or ""),
        "candidate_id": str(decision.get("candidate_id") or ""),
        "action": action,
        "status": _api_candidate_status((candidate or {}).get("decision_status") or _status_for_action(action)),
        "evidence_ids": _string_list(decision.get("evidence_ids")),
        "target_node_id": decision.get("graph_node_id"),
        "merge_candidate_id": decision.get("target_candidate_id"),
        "reason": decision.get("reason"),
        "decided_by": decision.get("actor"),
        "created_at": str(decision.get("created_at") or ""),
        "metadata": _string_object_mapping(decision.get("metadata")),
    }


def _detail_for_api(aggregate: Mapping[str, object]) -> dict[str, Any]:
    candidate_by_evidence: dict[str, str] = {}
    for candidate in _object_list(aggregate.get("candidates")):
        candidate_mapping = _string_object_mapping(candidate)
        if not candidate_mapping:
            continue
        candidate_id = str(candidate_mapping.get("candidate_id") or "")
        for evidence_id in _object_list(candidate_mapping.get("evidence_ids")):
            candidate_by_evidence.setdefault(str(evidence_id), candidate_id)
    candidates_by_id = {
        str(candidate_mapping.get("candidate_id")): candidate_mapping
        for candidate in _object_list(aggregate.get("candidates"))
        if (candidate_mapping := _string_object_mapping(candidate))
    }
    return {
        "chain": _chain_for_api(aggregate),
        "hops": [
            _hop_for_api(item_mapping)
            for item in _object_list(aggregate.get("hops"))
            if (item_mapping := _string_object_mapping(item))
        ],
        "candidates": [
            _candidate_for_api(item_mapping)
            for item in _object_list(aggregate.get("candidates"))
            if (item_mapping := _string_object_mapping(item))
        ],
        "evidence": [
            _evidence_for_api(item_mapping, candidate_by_evidence)
            for item in _object_list(aggregate.get("evidence"))
            if (item_mapping := _string_object_mapping(item))
        ],
        "decisions": [
            _decision_for_api(item_mapping, candidates_by_id.get(str(item_mapping.get("candidate_id"))))
            for item in _object_list(aggregate.get("decisions"))
            if (item_mapping := _string_object_mapping(item))
        ],
    }


def _expansion_for_api(aggregate: Mapping[str, Any], hop_id: str) -> dict[str, Any]:
    detail = _detail_for_api(aggregate)
    hop = next(item for item in detail["hops"] if item["hop_id"] == hop_id)
    evidence_ids = set(hop.get("evidence_ids") or [])
    candidate_ids = set(hop.get("candidate_ids") or [])
    return {
        "chain": detail["chain"],
        "hop": hop,
        "candidates": [item for item in detail["candidates"] if item["candidate_id"] in candidate_ids],
        "evidence": [item for item in detail["evidence"] if item["evidence_id"] in evidence_ids],
    }


def _api_mode(value: Any) -> str:
    text = str(value or "manual")
    if text in {"source_library_search", "external_search", "external_search_fixture", "agent_tool", "manual"}:
        return text
    return "manual"


def _api_hop_status(value: str) -> str:
    return {"planned": "queued", "blocked": "failed"}.get(value, value if value in {"queued", "running", "completed", "failed"} else "queued")


def _api_candidate_status(value: Any) -> str:
    text = str(value or "pending")
    return {
        "promoted": "accepted",
        "accepted": "accepted",
        "rejected": "rejected",
        "merged": "merged",
    }.get(text, "pending")


def _status_for_action(action: str) -> str:
    return {"promote": "promoted", "reject": "rejected", "merge": "merged"}.get(action, "pending")


def _default_query(chain_detail: Mapping[str, object], payload: ClueChainExpandRequest) -> str:
    if payload.query and payload.query.strip():
        return payload.query.strip()
    chain = _object_mapping(chain_detail.get("chain"))
    frontier = _string_list(chain.get("frontier_node_ids"))
    return str(chain.get("title") or chain.get("objective") or " ".join(frontier) or "clue chain")


def _first_frontier_node(chain_detail: Mapping[str, object], payload: ClueChainExpandRequest) -> str:
    if payload.frontier_node_ids:
        return str(payload.frontier_node_ids[0])
    chain = _object_mapping(chain_detail.get("chain"))
    frontier = _string_list(chain.get("frontier_node_ids")) or _string_list(chain.get("seed_node_ids"))
    return str(frontier[0]) if frontier else ""


def _provider_payload(
    *,
    chain_id: str,
    project_key: str,
    chain_detail: Mapping[str, object],
    payload: ClueChainExpandRequest,
) -> dict[str, Any]:
    mode = payload.mode
    query = _default_query(chain_detail, payload)
    input_node_id = _first_frontier_node(chain_detail, payload)
    if mode == "source_library_search":
        return _source_library_record_payload(
            chain_id=chain_id,
            project_key=project_key,
            query=query,
            input_node_id=input_node_id,
            payload=payload,
        )
    if mode in {"external_search", "external_search_fixture"}:
        return _external_search_record_payload(
            chain_id=chain_id,
            project_key=project_key,
            query=query,
            input_node_id=input_node_id,
            payload=payload,
        )
    return {
        "mode": "agent_tool" if mode == "agent_tool" else "manual",
        "input_node_id": input_node_id,
        "query_json": {"query": query},
        "status": "planned",
        "provider": "agent_tool",
        "params": {"limit": payload.limit, **payload.provider_options},
        "trace": {"requires_review": True, "graph_mutation_performed": False},
    }


def _source_library_record_payload(
    *,
    chain_id: str,
    project_key: str,
    query: str,
    input_node_id: str,
    payload: ClueChainExpandRequest,
) -> dict[str, Any]:
    options = _string_object_mapping(payload.provider_options)
    raw_source_items = _object_list(options.get("source_library_items"))
    source_items = [
        _string_object_mapping(item)
        for item in raw_source_items
        if _is_object_mapping(item)
    ] or None
    raw_result: object = expand_source_library_hop(
        chain_id=chain_id,
        project_key=project_key,
        frontier_query=query,
        frontier={"node_id": input_node_id, "label": query},
        source_library_items=source_items,
        domains=_string_list(options.get("domains")) or None,
        max_candidates=payload.limit,
    )
    result = _string_object_mapping(raw_result)
    if not _object_list(result.get("candidates")) and source_items is None:
        raw_result = expand_source_library_hop(
            chain_id=chain_id,
            project_key=project_key,
            frontier_query=query,
            frontier={"node_id": input_node_id, "label": query},
            source_library_items=[_source_library_fixture_item(query)],
            max_candidates=payload.limit,
        )
        result = _string_object_mapping(raw_result)
    evidence = [
        _source_evidence_payload(item_mapping, result)
        for item in _object_list(result.get("evidence"))
        if (item_mapping := _string_object_mapping(item))
    ]
    candidates = [
        _source_candidate_payload(item_mapping)
        for item in _object_list(result.get("candidates"))
        if (item_mapping := _string_object_mapping(item))
    ]
    hop = _object_mapping(result.get("hop"))
    return {
        "hop_id": hop.get("hop_id"),
        "mode": "source_library_search",
        "input_node_id": input_node_id,
        "query_json": {"query": query},
        "provider": "source_library_search",
        "status": "completed",
        "evidence": evidence,
        "candidates": candidates,
        "params": {"limit": payload.limit, **options},
        "trace": {
            "expansion": result.get("trace", {}),
            "replay_manifest": result.get("replay_manifest", {}),
            "requires_review": True,
            "graph_mutation_performed": False,
        },
    }


def _external_search_record_payload(
    *,
    chain_id: str,
    project_key: str,
    query: str,
    input_node_id: str,
    payload: ClueChainExpandRequest,
) -> dict[str, Any]:
    options = _string_object_mapping(payload.provider_options)
    request_payload: dict[str, Any] = {
        "chain_id": chain_id,
        "query": query,
        "focus_node_id": input_node_id,
        "project_key": project_key,
        "provider_name": str(options.get("provider_name") or "fixture_external_search"),
        "limit": payload.limit,
        "live_enabled": bool(options.get("live_enabled")),
        "trace_context": {"api": "clue_chains.expand"},
    }
    if isinstance(options.get("injected_results"), list):
        request_payload["injected_results"] = options["injected_results"]
    elif options.get("fixture_path"):
        request_payload["fixture_path"] = options["fixture_path"]
    else:
        request_payload["injected_results"] = [_external_fixture_result(query)]
        request_payload["fixture_path"] = str(_DEFAULT_EXTERNAL_FIXTURE)
    raw_result: object = expand_external_search(request_payload)
    result = _string_object_mapping(raw_result)
    evidence = [
        _external_evidence_payload(item_mapping, result)
        for item in _object_list(result.get("evidence"))
        if (item_mapping := _string_object_mapping(item))
    ]
    candidates = [
        _external_candidate_payload(item_mapping)
        for item in _object_list(result.get("candidates"))
        if (item_mapping := _string_object_mapping(item))
    ]
    hop = _object_mapping(result.get("hop"))
    trace = _object_mapping(result.get("trace"))
    return {
        "hop_id": hop.get("hop_id"),
        "mode": "external_search",
        "input_node_id": input_node_id,
        "query_json": {"query": query},
        "provider": trace.get("provider_name") or "fixture_external_search",
        "status": "completed" if candidates else "blocked",
        "evidence": evidence,
        "candidates": candidates,
        "params": {"limit": payload.limit, **options},
        "trace": {
            "expansion": result.get("trace", {}),
            "replay": result.get("replay", {}),
            "requires_review": True,
            "graph_mutation_performed": False,
        },
    }


def _source_evidence_payload(
    evidence: Mapping[str, object],
    result: Mapping[str, object],
) -> dict[str, Any]:
    source_ref = _string_object_mapping(evidence.get("source_ref"))
    return {
        "evidence_id": evidence.get("evidence_id"),
        "source_kind": "source_library",
        "source_ref": source_ref,
        "title": evidence.get("title"),
        "snippet": evidence.get("summary") or evidence.get("snippet"),
        "provider": "source_library_search",
        "query": evidence.get("query"),
        "status": "lead",
        "metadata": {"rank": evidence.get("rank"), "trace": evidence.get("trace"), "replay": result.get("replay_manifest")},
    }


def _source_candidate_payload(candidate: Mapping[str, object]) -> dict[str, Any]:
    aliases = _string_list(candidate.get("aliases"))
    source_ref = _string_object_mapping(candidate.get("source_ref"))
    value = aliases[0] if aliases else str(source_ref.get("item_key") or candidate.get("query") or "source-library candidate")
    evidence_ids = [str(candidate.get("evidence_id"))] if candidate.get("evidence_id") else []
    for merged in _object_list(candidate.get("merged_from")):
        merged_mapping = _object_mapping(merged)
        if merged_mapping.get("evidence_id"):
            evidence_ids.append(str(merged_mapping["evidence_id"]))
    return {
        "candidate_id": candidate.get("candidate_id"),
        "entity_type": "SourceLibraryItem",
        "value": value,
        "aliases": aliases or [value],
        "score": candidate.get("score"),
        "evidence_ids": evidence_ids,
        "decision_status": "pending",
        "properties": {"source_ref": source_ref, "rank": candidate.get("rank"), "dedupe_key": candidate.get("dedupe_key")},
        "metadata": {"requires_review": True, "promote_guard": candidate.get("promote_guard")},
    }


def _external_evidence_payload(evidence: Mapping[str, object], result: Mapping[str, object]) -> dict[str, Any]:
    return {
        "evidence_id": evidence.get("evidence_id"),
        "source_kind": "external_search",
        "source_ref": {
            "provider_name": evidence.get("provider_name"),
            "normalized_url": evidence.get("normalized_url"),
            "dedupe_key": evidence.get("dedupe_key"),
            "replay_ref": evidence.get("replay_ref"),
        },
        "url": evidence.get("normalized_url"),
        "title": evidence.get("title"),
        "snippet": evidence.get("snippet"),
        "provider": evidence.get("provider_name"),
        "query": evidence.get("query"),
        "status": "lead",
        "metadata": {"fixture_gate": evidence.get("fixture_gate"), "trace": result.get("trace"), "replay": result.get("replay")},
    }


def _external_candidate_payload(candidate: Mapping[str, object]) -> dict[str, Any]:
    aliases = _string_list(candidate.get("aliases"))
    value = str(candidate.get("title") or candidate.get("normalized_url") or (aliases[0] if aliases else "external candidate"))
    return {
        "candidate_id": candidate.get("candidate_id"),
        "entity_type": "SourceUrl" if candidate.get("candidate_type") == "source_url" else "ExternalAlias",
        "value": value,
        "aliases": aliases or [value],
        "score": None,
        "evidence_ids": _string_list(candidate.get("evidence_refs")),
        "decision_status": "pending",
        "properties": {
            "normalized_url": candidate.get("normalized_url"),
            "provider_name": candidate.get("provider_name"),
            "dedupe_key": candidate.get("dedupe_key"),
        },
        "metadata": {"requires_review": True, "promotion_allowed": False, "fixture_gate": candidate.get("fixture_gate")},
    }


def _source_library_fixture_item(query: str) -> dict[str, Any]:
    slug = "".join(ch if ch.isalnum() else "_" for ch in query.lower()).strip("_")[:48] or "query"
    return {
        "item_key": f"clue_chain.fixture.{slug}",
        "name": f"Source Library fixture for {query}",
        "channel_key": "clue_chain_fixture",
        "description": f"Fixture-gated source-library candidate for {query}",
        "tags": ["clue-chain", "fixture"],
        "params": {"query": query},
        "enabled": True,
        "extra": {"fixture_gated": True},
    }


def _external_fixture_result(query: str) -> dict[str, str]:
    slug = "".join(ch if ch.isalnum() else "-" for ch in query.lower()).strip("-")[:48] or "query"
    return {
        "title": f"External search fixture for {query}",
        "url": f"https://example.org/clue-chain/{slug}",
        "snippet": f"Fixture-gated external result for {query}.",
    }


@router.post("", response_model=ClueChainDetailEnvelope, response_model_exclude_unset=True)
def create_clue_chain(payload: ClueChainCreateRequest, request: Request) -> dict[str, Any]:
    project_key = _project_key_from_request(request, payload.project_key)
    service = _service_for_project(project_key)
    try:
        detail = service.create_chain(
            {
                "project_key": project_key,
                "graph_id": payload.graph_id,
                "title": payload.title,
                "objective": payload.question or payload.title,
                "seed_node_ids": payload.root_node_ids,
                "metadata": payload.metadata,
                "created_by": payload.metadata.get("created_by") or "api",
            }
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_service_error(exc) from exc
    return success_response(_serialize(ClueChainDetailData, _detail_for_api(detail)))


@router.get("", response_model=ClueChainListEnvelope, response_model_exclude_unset=True)
def list_clue_chains(
    request: Request,
    project_key: str | None = Query(default=None),
    graph_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    resolved_project_key = project_key or _project_key_from_request(request)
    service = _service_for_project(resolved_project_key)
    try:
        data = service.list_chains(limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise _map_service_error(exc) from exc
    items = [_chain_for_api({"chain": item, "hops": [], "evidence": [], "candidates": [], "decisions": []}) for item in data["items"]]
    if graph_id:
        items = [item for item in items if item.get("graph_id") == graph_id]
    if status:
        items = [item for item in items if item.get("status") == status]
    return success_response(_serialize(ClueChainListData, {"items": items[:limit], "total": len(items)}))


@router.get("/{chain_id}", response_model=ClueChainDetailEnvelope, response_model_exclude_unset=True)
def get_clue_chain(chain_id: str, request: Request) -> dict[str, Any]:
    service = _service_for_project(_project_key_from_request(request))
    try:
        detail = service.get_chain(chain_id)
    except Exception as exc:  # noqa: BLE001
        raise _map_service_error(exc) from exc
    return success_response(_serialize(ClueChainDetailData, _detail_for_api(detail)))


@router.post("/{chain_id}/expand", response_model=ClueChainExpansionEnvelope, response_model_exclude_unset=True)
def expand_clue_chain(chain_id: str, payload: ClueChainExpandRequest, request: Request) -> dict[str, Any]:
    project_key = _project_key_from_request(request)
    service = _service_for_project(project_key)
    try:
        chain_detail = service.get_chain(chain_id)
        record_payload = _provider_payload(chain_id=chain_id, project_key=project_key, chain_detail=chain_detail, payload=payload)
        recorded = service.record_hop(chain_id, record_payload)
        detail = service.get_chain(chain_id)
    except Exception as exc:  # noqa: BLE001
        raise _map_service_error(exc) from exc
    return success_response(_serialize(ClueChainExpansionData, _expansion_for_api(detail, recorded["hop"]["hop_id"])))


@router.post(
    "/{chain_id}/candidates/{candidate_id}/decision",
    response_model=ClueChainDecisionEnvelope,
    response_model_exclude_unset=True,
)
def decide_clue_chain_candidate(
    chain_id: str,
    candidate_id: str,
    payload: ClueChainDecisionRequest,
    request: Request,
) -> dict[str, Any]:
    service = _service_for_project(_project_key_from_request(request))
    try:
        graph_node_id = payload.target_node_id
        if payload.action == "promote" and not graph_node_id:
            graph_node_id = f"node_{candidate_id}"
        result = service.record_decision(
            chain_id,
            candidate_id,
            {
                "decision": payload.action,
                "reason": payload.reason,
                "graph_node_id": graph_node_id,
                "target_candidate_id": payload.merge_candidate_id,
                "actor": payload.decided_by or "api",
                "metadata": payload.metadata,
            },
        )
        detail = service.get_chain(chain_id)
    except Exception as exc:  # noqa: BLE001
        raise _map_service_error(exc) from exc
    return success_response(
        _serialize(
            ClueChainDecisionResponseData,
            {
                "chain": _chain_for_api(detail),
                "candidate": _candidate_for_api(result["candidate"]),
                "decision": _decision_for_api(result["decision"], result["candidate"]),
            },
        )
    )


@router.post("/{chain_id}/close", response_model=ClueChainCloseEnvelope, response_model_exclude_unset=True)
def close_clue_chain(chain_id: str, payload: ClueChainCloseRequest, request: Request) -> dict[str, Any]:
    service = _service_for_project(_project_key_from_request(request))
    try:
        detail = service.close_chain(
            chain_id,
            {
                "reason": payload.reason,
                "actor": payload.closed_by or "api",
                "metadata": payload.metadata,
            },
        )
    except Exception as exc:  # noqa: BLE001
        raise _map_service_error(exc) from exc
    return success_response(_serialize(ClueChainCloseData, {"chain": _chain_for_api(detail)}))
