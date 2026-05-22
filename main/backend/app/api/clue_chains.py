from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request

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


router = APIRouter(prefix="/clue-chains", tags=["clue-chains"])

ClueChainDetailEnvelope = ApiEnvelope[ClueChainDetailData]
ClueChainListEnvelope = ApiEnvelope[ClueChainListData]
ClueChainExpansionEnvelope = ApiEnvelope[ClueChainExpansionData]
ClueChainDecisionEnvelope = ApiEnvelope[ClueChainDecisionResponseData]
ClueChainCloseEnvelope = ApiEnvelope[ClueChainCloseData]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_error(status_code: int, code: ErrorCode, message: str, *, details: dict[str, Any] | None = None) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=error_response(code, message, details=details),
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


class _InMemoryClueChainService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._chains: dict[str, dict[str, Any]] = {}

    def reset(self) -> None:
        with self._lock:
            self._chains.clear()

    def create_chain(self, payload: ClueChainCreateRequest, *, project_key: str) -> dict[str, Any]:
        if not payload.root_node_ids:
            raise ValueError("root_node_ids must include at least one graph node")
        now = _now_iso()
        chain_id = f"chain_{uuid4().hex}"
        chain = {
            "chain_id": chain_id,
            "project_key": project_key,
            "graph_id": payload.graph_id.strip(),
            "title": payload.title.strip(),
            "question": payload.question,
            "status": "open",
            "root_node_ids": list(payload.root_node_ids),
            "frontier_node_ids": list(payload.root_node_ids),
            "hop_ids": [],
            "candidate_count": 0,
            "evidence_count": 0,
            "decision_count": 0,
            "created_at": now,
            "updated_at": now,
            "closed_at": None,
            "close_reason": None,
            "metadata": dict(payload.metadata),
        }
        detail = {"chain": chain, "hops": [], "candidates": [], "evidence": [], "decisions": []}
        with self._lock:
            self._chains[chain_id] = detail
            return deepcopy(detail)

    def list_chains(
        self,
        *,
        project_key: str | None = None,
        graph_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        with self._lock:
            items = [deepcopy(detail["chain"]) for detail in self._chains.values()]
        if project_key:
            items = [item for item in items if item.get("project_key") == project_key]
        if graph_id:
            items = [item for item in items if item.get("graph_id") == graph_id]
        if status:
            items = [item for item in items if item.get("status") == status]
        items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        limited = items[:limit]
        return {"items": limited, "total": len(items)}

    def get_chain(self, chain_id: str) -> dict[str, Any]:
        with self._lock:
            detail = self._chains.get(chain_id)
            if detail is None:
                raise KeyError("clue chain not found")
            return deepcopy(detail)

    def expand_chain(self, chain_id: str, payload: ClueChainExpandRequest) -> dict[str, Any]:
        with self._lock:
            detail = self._chains.get(chain_id)
            if detail is None:
                raise KeyError("clue chain not found")
            if detail["chain"]["status"] == "closed":
                raise ValueError("closed clue chains cannot be expanded")

            now = _now_iso()
            hop_id = f"hop_{uuid4().hex}"
            candidate_id = f"cand_{uuid4().hex}"
            evidence_id = f"evid_{uuid4().hex}"
            frontier_node_ids = list(payload.frontier_node_ids or detail["chain"]["frontier_node_ids"])
            query = (payload.query or " ".join(frontier_node_ids) or detail["chain"]["title"]).strip()

            hop = {
                "hop_id": hop_id,
                "chain_id": chain_id,
                "mode": payload.mode,
                "query": query,
                "status": "completed",
                "frontier_node_ids": frontier_node_ids,
                "candidate_ids": [candidate_id],
                "evidence_ids": [evidence_id],
                "created_at": now,
                "completed_at": now,
                "metadata": {"provider_options": payload.provider_options, **payload.metadata},
            }
            evidence = {
                "evidence_id": evidence_id,
                "chain_id": chain_id,
                "hop_id": hop_id,
                "candidate_id": candidate_id,
                "source_type": payload.mode,
                "source_ref": "clue_chain_api_contract_stub",
                "title": f"Expansion evidence for {query}",
                "url": None,
                "snippet": f"Stub evidence generated for {payload.mode} query: {query}",
                "node_refs": frontier_node_ids,
                "created_at": now,
                "metadata": {"fixture_gated": True},
            }
            candidate = {
                "candidate_id": candidate_id,
                "chain_id": chain_id,
                "hop_id": hop_id,
                "label": query,
                "candidate_type": "node",
                "aliases": [query],
                "confidence": 0.5,
                "status": "pending",
                "evidence_ids": [evidence_id],
                "target_node_id": None,
                "edge": None,
                "metadata": {"generated_by": "clue_chain_api_contract_stub"},
            }

            detail["hops"].append(hop)
            detail["evidence"].append(evidence)
            detail["candidates"].append(candidate)
            detail["chain"]["hop_ids"].append(hop_id)
            detail["chain"]["frontier_node_ids"] = [candidate_id]
            detail["chain"]["candidate_count"] = len(detail["candidates"])
            detail["chain"]["evidence_count"] = len(detail["evidence"])
            detail["chain"]["updated_at"] = now
            return {"chain": deepcopy(detail["chain"]), "hop": deepcopy(hop), "candidates": [deepcopy(candidate)], "evidence": [deepcopy(evidence)]}

    def decide_candidate(self, chain_id: str, candidate_id: str, payload: ClueChainDecisionRequest) -> dict[str, Any]:
        with self._lock:
            detail = self._chains.get(chain_id)
            if detail is None:
                raise KeyError("clue chain not found")
            candidate = next((item for item in detail["candidates"] if item["candidate_id"] == candidate_id), None)
            if candidate is None:
                raise KeyError("clue chain candidate not found")
            if payload.action == "merge" and not (payload.merge_candidate_id or payload.target_node_id):
                raise ValueError("merge decisions require merge_candidate_id or target_node_id")

            now = _now_iso()
            status_by_action = {"promote": "accepted", "reject": "rejected", "merge": "merged"}
            target_node_id = payload.target_node_id
            if payload.action == "promote" and not target_node_id:
                target_node_id = f"node_{candidate_id}"
            candidate["status"] = status_by_action[payload.action]
            candidate["target_node_id"] = target_node_id
            decision = {
                "decision_id": f"decision_{uuid4().hex}",
                "chain_id": chain_id,
                "candidate_id": candidate_id,
                "action": payload.action,
                "status": candidate["status"],
                "evidence_ids": list(candidate.get("evidence_ids") or []),
                "target_node_id": target_node_id,
                "merge_candidate_id": payload.merge_candidate_id,
                "reason": payload.reason,
                "decided_by": payload.decided_by,
                "created_at": now,
                "metadata": dict(payload.metadata),
            }
            detail["decisions"].append(decision)
            detail["chain"]["decision_count"] = len(detail["decisions"])
            detail["chain"]["updated_at"] = now
            return {"chain": deepcopy(detail["chain"]), "candidate": deepcopy(candidate), "decision": deepcopy(decision)}

    def close_chain(self, chain_id: str, payload: ClueChainCloseRequest) -> dict[str, Any]:
        with self._lock:
            detail = self._chains.get(chain_id)
            if detail is None:
                raise KeyError("clue chain not found")
            now = _now_iso()
            detail["chain"]["status"] = "closed"
            detail["chain"]["closed_at"] = now
            detail["chain"]["close_reason"] = payload.reason
            detail["chain"]["updated_at"] = now
            detail["chain"]["metadata"] = {**detail["chain"]["metadata"], **payload.metadata}
            if payload.closed_by:
                detail["chain"]["metadata"]["closed_by"] = payload.closed_by
            return {"chain": deepcopy(detail["chain"])}


_service = _InMemoryClueChainService()


def reset_clue_chain_service_for_tests() -> None:
    _service.reset()


def _serialize(model_type: type[Any], payload: dict[str, Any]) -> dict[str, Any]:
    return model_type.model_validate(payload).model_dump()


def _map_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, KeyError):
        return _http_error(404, ErrorCode.NOT_FOUND, str(exc).strip("'") or "clue chain not found")
    if isinstance(exc, ValueError):
        return _http_error(400, ErrorCode.INVALID_INPUT, str(exc))
    return _http_error(
        500,
        ErrorCode.INTERNAL_ERROR,
        "clue chain request failed",
        details={"exception_type": exc.__class__.__name__},
    )


@router.post("", response_model=ClueChainDetailEnvelope, response_model_exclude_unset=True)
def create_clue_chain(payload: ClueChainCreateRequest, request: Request) -> dict[str, Any]:
    project_key = _project_key_from_request(request, payload.project_key)
    try:
        detail = _service.create_chain(payload, project_key=project_key)
    except Exception as exc:  # noqa: BLE001
        raise _map_service_error(exc) from exc
    return success_response(_serialize(ClueChainDetailData, detail))


@router.get("", response_model=ClueChainListEnvelope, response_model_exclude_unset=True)
def list_clue_chains(
    request: Request,
    project_key: str | None = Query(default=None),
    graph_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    resolved_project_key = project_key or _project_key_from_request(request)
    try:
        data = _service.list_chains(project_key=resolved_project_key, graph_id=graph_id, status=status, limit=limit)
    except Exception as exc:  # noqa: BLE001
        raise _map_service_error(exc) from exc
    return success_response(_serialize(ClueChainListData, data))


@router.get("/{chain_id}", response_model=ClueChainDetailEnvelope, response_model_exclude_unset=True)
def get_clue_chain(chain_id: str) -> dict[str, Any]:
    try:
        detail = _service.get_chain(chain_id)
    except Exception as exc:  # noqa: BLE001
        raise _map_service_error(exc) from exc
    return success_response(_serialize(ClueChainDetailData, detail))


@router.post("/{chain_id}/expand", response_model=ClueChainExpansionEnvelope, response_model_exclude_unset=True)
def expand_clue_chain(chain_id: str, payload: ClueChainExpandRequest) -> dict[str, Any]:
    try:
        data = _service.expand_chain(chain_id, payload)
    except Exception as exc:  # noqa: BLE001
        raise _map_service_error(exc) from exc
    return success_response(_serialize(ClueChainExpansionData, data))


@router.post(
    "/{chain_id}/candidates/{candidate_id}/decision",
    response_model=ClueChainDecisionEnvelope,
    response_model_exclude_unset=True,
)
def decide_clue_chain_candidate(chain_id: str, candidate_id: str, payload: ClueChainDecisionRequest) -> dict[str, Any]:
    try:
        data = _service.decide_candidate(chain_id, candidate_id, payload)
    except Exception as exc:  # noqa: BLE001
        raise _map_service_error(exc) from exc
    return success_response(_serialize(ClueChainDecisionResponseData, data))


@router.post("/{chain_id}/close", response_model=ClueChainCloseEnvelope, response_model_exclude_unset=True)
def close_clue_chain(chain_id: str, payload: ClueChainCloseRequest) -> dict[str, Any]:
    try:
        data = _service.close_chain(chain_id, payload)
    except Exception as exc:  # noqa: BLE001
        raise _map_service_error(exc) from exc
    return success_response(_serialize(ClueChainCloseData, data))
