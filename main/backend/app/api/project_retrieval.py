"""Manual project retrieval controls; preview is free of network effects."""
from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, JsonValue

from app.contracts.errors import ErrorCode
from app.contracts.responses import ApiEnvelope, ApiErrorModel, ApiMetaModel
from app.services.project_retrieval.contracts import RetrievalJsonObject
from app.services.project_retrieval.service import ProjectRetrievalService, RetrievalError
from app.services.projects.context import current_project_key

router = APIRouter(prefix="/project-retrieval", tags=["project-retrieval"])
RetrievalEnvelope = ApiEnvelope[dict[str, JsonValue]]


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
        raise RetrievalError(
            ErrorCode.PROJECT_KEY_REQUIRED.value,
            "active project context is required",
            400,
        )
    return key


def _call(
    fn: Callable[[str], RetrievalJsonObject],
) -> RetrievalEnvelope | JSONResponse:
    project_key: str | None = None
    try:
        project_key = _project()
        return RetrievalEnvelope(
            status="ok",
            data=fn(project_key),
            error=None,
            meta=ApiMetaModel(project_key=project_key),
        )
    except RetrievalError as exc:
        envelope = RetrievalEnvelope(
            status="error",
            data=None,
            error=ApiErrorModel(code=exc.code, message=str(exc), details={}),
            meta=ApiMetaModel(project_key=project_key),
        )
        payload = envelope.model_dump()
        payload["detail"] = {
            "error": payload["error"],
            "message": str(exc),
        }
        return JSONResponse(
            status_code=exc.status,
            content=payload,
            headers={"X-Error-Code": exc.code},
        )


@router.get("/modes/current", response_model=RetrievalEnvelope)
def current_mode() -> RetrievalEnvelope | JSONResponse:
    return _call(lambda project_key: ProjectRetrievalService().current(project_key))


@router.post("/modes/refresh", response_model=RetrievalEnvelope)
def refresh_mode() -> RetrievalEnvelope | JSONResponse:
    return _call(lambda project_key: ProjectRetrievalService().refresh(project_key))


@router.post("/plans/preview", response_model=RetrievalEnvelope)
def preview(payload: PreviewRequest) -> RetrievalEnvelope | JSONResponse:
    return _call(
        lambda project_key: ProjectRetrievalService().preview(
            project_key,
            route_id=payload.route_id,
            query_ids=payload.query_ids,
            limits=payload.limits,
        )
    )


@router.post("/runs", response_model=RetrievalEnvelope)
def start(payload: StartRequest) -> RetrievalEnvelope | JSONResponse:
    return _call(
        lambda project_key: ProjectRetrievalService().start(
            project_key,
            plan_id=payload.plan_id,
            idempotency_key=payload.idempotency_key,
        )
    )


@router.get("/runs/{run_id}", response_model=RetrievalEnvelope)
def read_run(run_id: str) -> RetrievalEnvelope | JSONResponse:
    return _call(
        lambda project_key: ProjectRetrievalService().read_run(project_key, run_id)
    )


@router.post(
    "/rapid-proposals/{proposal_id}/continue",
    response_model=RetrievalEnvelope,
)
def continue_saved_frontier(
    proposal_id: str, payload: RapidContinuationRequest
) -> RetrievalEnvelope | JSONResponse:
    return _call(
        lambda project_key: ProjectRetrievalService().continue_saved_frontier(
            project_key,
            plan_id=payload.plan_id,
            proposal_id=proposal_id,
            proposal_version=payload.proposal_version,
            frontier_id=payload.frontier_id,
            remaining_followup_budget=payload.remaining_followup_budget,
        )
    )
