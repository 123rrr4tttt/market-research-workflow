"""Manual project retrieval controls; preview is free of network effects."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.contracts.responses import ApiEnvelope, ApiErrorModel, ApiMetaModel, ok
from app.services.project_retrieval.service import ProjectRetrievalService, RetrievalError
from app.services.projects.context import current_project_key

router = APIRouter(prefix="/project-retrieval", tags=["project-retrieval"])
RetrievalEnvelope = ApiEnvelope[dict[str, Any]]


class PreviewRequest(BaseModel):
    route_id: str = Field(min_length=1)
    query_ids: list[str] | None = None
    limits: dict[str, int] | None = None


class StartRequest(BaseModel):
    plan_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1, max_length=255)


class RapidContinuationRequest(BaseModel):
    plan_id: str = Field(min_length=1)
    proposal_version: str = Field(min_length=1)
    frontier_id: str = Field(min_length=1)
    remaining_followup_budget: int = Field(ge=1, le=20)


def _project() -> str:
    key = str(current_project_key() or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="active project context is required")
    return key


def _call(fn, project_key: str) -> dict[str, Any]:
    try:
        return ok(fn())
    except RetrievalError as exc:
        raise HTTPException(
            status_code=exc.status,
            detail=ApiEnvelope[Any](
                status="error", data=None,
                error=ApiErrorModel(code=exc.code, message=str(exc), details={}),
                meta=ApiMetaModel(project_key=project_key),
            ).model_dump(),
        ) from exc


@router.get("/modes/current", response_model=RetrievalEnvelope)
def current_mode() -> dict[str, Any]:
    project_key = _project()
    return _call(lambda: ProjectRetrievalService().current(project_key), project_key)


@router.post("/modes/refresh", response_model=RetrievalEnvelope)
def refresh_mode() -> dict[str, Any]:
    project_key = _project()
    return _call(lambda: ProjectRetrievalService().refresh(project_key), project_key)


@router.post("/plans/preview", response_model=RetrievalEnvelope)
def preview(payload: PreviewRequest) -> dict[str, Any]:
    project_key = _project()
    return _call(lambda: ProjectRetrievalService().preview(
        project_key, route_id=payload.route_id, query_ids=payload.query_ids, limits=payload.limits,
    ), project_key)


@router.post("/runs", response_model=RetrievalEnvelope)
def start(payload: StartRequest) -> dict[str, Any]:
    project_key = _project()
    return _call(lambda: ProjectRetrievalService().start(
        project_key, plan_id=payload.plan_id, idempotency_key=payload.idempotency_key,
    ), project_key)


@router.get("/runs/{run_id}", response_model=RetrievalEnvelope)
def read_run(run_id: str) -> dict[str, Any]:
    project_key = _project()
    return _call(lambda: ProjectRetrievalService().read_run(project_key, run_id), project_key)


@router.post(
    "/rapid-proposals/{proposal_id}/continue",
    response_model=RetrievalEnvelope,
)
def continue_saved_frontier(
    proposal_id: str, payload: RapidContinuationRequest
) -> dict[str, Any]:
    project_key = _project()
    return _call(
        lambda: ProjectRetrievalService().continue_saved_frontier(
            project_key,
            plan_id=payload.plan_id,
            proposal_id=proposal_id,
            proposal_version=payload.proposal_version,
            frontier_id=payload.frontier_id,
            remaining_followup_budget=payload.remaining_followup_budget,
        ),
        project_key,
    )
