from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..contracts import ErrorCode, error_response, success_response
from ..services.projects.context import _normalize_project_key
from ..services.typed_knowledge import contracts
from ..services.typed_knowledge.adapters import live_service
from ..services.typed_knowledge import persistence_boundary
from ._error_responses import error_json_response as _error_json


router = APIRouter(prefix="/typed-knowledge", tags=["typed_knowledge"])


class TypedKnowledgeRouteInfo(BaseModel):
    method: Literal["GET"]
    path: Literal["/api/v1/typed-knowledge/persistence-boundary"]
    tag: Literal["typed_knowledge"]
    public_api_route: bool
    live_db_backed: bool
    response_contract: str


class TypedKnowledgeRouteContractData(BaseModel):
    contract_version: str
    authoritative: bool
    derived_as: Literal["view"]
    route: TypedKnowledgeRouteInfo
    persistence_boundary: dict[str, Any]
    persistence_boundary_meta: dict[str, Any]
    persisted_card_request_response_readback: dict[str, Any]
    boundary_fingerprint: str


class TypedKnowledgeRouteReadiness(BaseModel):
    public_api_route: bool
    api_contract: bool
    repository_contract: bool
    persisted_card_request_response_readback: bool
    live_db_persistence: bool
    live_api_closure: bool
    live_ui_closure: bool
    governance_ui: bool


class TypedKnowledgeRouteMeta(BaseModel):
    contract_readiness: Literal["ready"]
    closed_slice: list[str]
    readiness: TypedKnowledgeRouteReadiness
    remaining_live_gaps: list[str]
    non_goal: str


class TypedKnowledgeRouteContractEnvelope(BaseModel):
    status: Literal["ok"]
    data: TypedKnowledgeRouteContractData
    error: None = None
    meta: TypedKnowledgeRouteMeta


class TypedKnowledgeGovernanceReviewStateRequest(BaseModel):
    project_key: str | None = Field(default=None, max_length=128)
    object_type: str = Field(default=persistence_boundary.OBJECT_TYPE_KNOWLEDGE_ITEM, max_length=32)
    object_key: str = Field(default="ki:robotics-policy", min_length=1, max_length=255)
    review_state: str = Field(default=contracts.REVIEW_STATE_HUMAN_CONFIRMED, max_length=64)
    actor_type: str = Field(default=contracts.ACTOR_HUMAN, max_length=32)
    actor_id: str | None = Field(default=None, max_length=128)


def _typed_project_key(project_key: str | None) -> str:
    return _normalize_project_key(str(project_key or "demo_proj"))


def _required_write_project_key(
    project_key: str | None,
    *,
    route_path: str,
) -> tuple[str | None, dict[str, Any] | None]:
    raw_project_key = str(project_key or "").strip()
    if not raw_project_key:
        return None, {
            "message": "project_key is required for typed-knowledge write requests",
            "details": {
                "field": "project_key",
                "route_path": route_path,
                "recoverable": True,
                "next_action": "retry_with_explicit_project_key",
            },
        }
    normalized_project_key = _normalize_project_key(raw_project_key)
    fallback_project_key = _normalize_project_key("")
    identity_probe = "typed_knowledge_request_identity"
    retains_request_identity = (
        _normalize_project_key(f"{raw_project_key}_{identity_probe}")
        != _normalize_project_key(identity_probe)
    )
    if normalized_project_key == "public" or (
        normalized_project_key == fallback_project_key and not retains_request_identity
    ):
        return None, {
            "message": "project_key must retain an explicit writable identity after normalization",
            "details": {
                "field": "project_key",
                "route_path": route_path,
                "recoverable": True,
                "next_action": "retry_with_explicit_project_key",
            },
        }
    return normalized_project_key, None


def _http_bad_request(exc: Exception, *, project_key: str) -> HTTPException:
    details: dict[str, Any] = {
        "project_key": project_key,
        "exception_type": exc.__class__.__name__,
    }
    if isinstance(exc, persistence_boundary.TypedKnowledgePersistenceBoundaryError):
        details["failure_code"] = exc.failure_code
    return HTTPException(
        status_code=400,
        detail=error_response(
            ErrorCode.INVALID_INPUT,
            str(exc) or "invalid typed-knowledge request",
            details=details,
        ),
    )


@router.get(
    "/persistence-boundary",
    response_model=TypedKnowledgeRouteContractEnvelope,
    response_model_exclude_unset=True,
)
def get_typed_knowledge_persistence_boundary(
    project_key: str = Query(default="demo_proj", min_length=1, max_length=128),
    repository_mode: Literal["contract", "live"] = Query(default="contract"),
) -> dict[str, Any]:
    resolved_project_key = _typed_project_key(project_key)
    if repository_mode == "contract":
        return persistence_boundary.build_public_api_route_contract_envelope(project_key=resolved_project_key)
    try:
        return live_service.read_live_public_route_contract(
            project_key=resolved_project_key,
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_bad_request(exc, project_key=resolved_project_key) from exc


@router.post(
    "/live-sample",
    response_model=dict[str, Any],
    response_model_exclude_unset=True,
)
def seed_typed_knowledge_live_sample(
    project_key: str | None = Query(default=None, max_length=128),
) -> dict[str, Any] | JSONResponse:
    resolved_project_key, project_key_error = _required_write_project_key(
        project_key,
        route_path="/api/v1/typed-knowledge/live-sample",
    )
    if project_key_error is not None:
        return _error_json(
            400,
            ErrorCode.INVALID_INPUT,
            project_key_error["message"],
            details=project_key_error["details"],
        )
    assert resolved_project_key is not None
    try:
        envelope = live_service.seed_live_sample(project_key=resolved_project_key)
        return success_response(envelope["data"], meta=envelope["meta"])
    except Exception as exc:  # noqa: BLE001
        raise _http_bad_request(exc, project_key=resolved_project_key) from exc


@router.get(
    "/writing-context",
    response_model=dict[str, Any],
    response_model_exclude_unset=True,
)
def get_typed_knowledge_writing_context(
    project_key: str = Query(default="demo_proj", min_length=1, max_length=128),
) -> dict[str, Any]:
    resolved_project_key = _typed_project_key(project_key)
    try:
        context = live_service.read_live_writing_context(project_key=resolved_project_key)
        return success_response(
            {
                "project_key": resolved_project_key,
                "route_path": persistence_boundary.WRITING_CONTEXT_ROUTE_PATH,
                "typed_knowledge_context": context,
                "live_db_backed": True,
            }
        )
    except Exception as exc:  # noqa: BLE001
        raise _http_bad_request(exc, project_key=resolved_project_key) from exc


@router.post(
    "/governance/review-state",
    response_model=dict[str, Any],
    response_model_exclude_unset=True,
)
def update_typed_knowledge_governance_review_state(
    payload: TypedKnowledgeGovernanceReviewStateRequest,
) -> dict[str, Any] | JSONResponse:
    resolved_project_key, project_key_error = _required_write_project_key(
        payload.project_key,
        route_path=persistence_boundary.GOVERNANCE_REVIEW_STATE_ROUTE_PATH,
    )
    if project_key_error is not None:
        return _error_json(
            400,
            ErrorCode.INVALID_INPUT,
            project_key_error["message"],
            details=project_key_error["details"],
        )
    assert resolved_project_key is not None
    try:
        mutation = live_service.apply_governance_review_state(
            project_key=resolved_project_key,
            object_type=payload.object_type,
            object_key=payload.object_key,
            review_state=payload.review_state,
            actor_type=payload.actor_type,
            actor_id=payload.actor_id,
        )
        return success_response(mutation)
    except Exception as exc:  # noqa: BLE001
        raise _http_bad_request(exc, project_key=resolved_project_key) from exc
