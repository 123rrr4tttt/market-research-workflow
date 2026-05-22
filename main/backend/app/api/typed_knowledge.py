from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..services.typed_knowledge import persistence_boundary


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


@router.get(
    "/persistence-boundary",
    response_model=TypedKnowledgeRouteContractEnvelope,
    response_model_exclude_unset=True,
)
def get_typed_knowledge_persistence_boundary(
    project_key: str = Query(default="demo_proj", min_length=1, max_length=128),
) -> dict[str, Any]:
    return persistence_boundary.build_public_api_route_contract_envelope(project_key=project_key)
