from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..contracts import fail, ok, ok_page
from ..contracts.errors import ErrorCode
from ..services.crawlers_mgmt import (
    CrawlerProjectNotFoundError,
    deploy_project,
    get_deploy_run,
    get_project,
    import_project,
    list_projects,
    rollback_project,
)


router = APIRouter(prefix="/crawler", tags=["crawler"])


def _resolve_registration_project_key(request: Request) -> str | None:
    header_key = str(request.headers.get("X-Project-Key") or "").strip()
    if header_key:
        return header_key
    query_key = str(request.query_params.get("project_key") or "").strip()
    if query_key:
        return query_key
    return None


class ImportCrawlerProjectPayload(BaseModel):
    project_key: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    repo_url: str | None = Field(default=None, min_length=1, max_length=2048)
    branch: str | None = Field(default=None, min_length=1, max_length=128)
    provider_hint: str | None = Field(default=None, min_length=1, max_length=64)
    enable_now: bool = True
    description: str | None = None
    source_type: str = Field(default="git", min_length=1, max_length=32)
    source_uri: str | None = None
    provider: str = Field(default="scrapyd", min_length=1, max_length=64)
    version: str | None = Field(default=None, max_length=128)
    manifest: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeployCrawlerProjectPayload(BaseModel):
    requested_version: str | None = Field(default=None, max_length=128)
    planner_mode: str | None = Field(default=None, max_length=16)
    async_mode: bool = Field(default=False)


class RollbackCrawlerProjectPayload(BaseModel):
    target_version: str | None = Field(default=None, max_length=128)
    to_version: str | None = Field(default=None, max_length=128)
    planner_mode: str | None = Field(default=None, max_length=16)
    async_mode: bool = Field(default=False)


@router.post("/projects/import")
def import_crawler_project_api(payload: ImportCrawlerProjectPayload):
    try:
        saved = import_project(payload.model_dump())
        return JSONResponse(status_code=200, content=ok(saved))
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content=fail(ErrorCode.INVALID_INPUT, str(exc)),
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content=fail(ErrorCode.INTERNAL_ERROR, str(exc)),
        )


@router.get("/projects")
def list_crawler_projects_api(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    try:
        items, total = list_projects(page=page, page_size=page_size)
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return JSONResponse(
            status_code=200,
            content=ok_page(
                {"items": items},
                page=page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
            ),
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content=fail(ErrorCode.INTERNAL_ERROR, str(exc)),
        )


@router.get("/projects/{project_key}")
def get_crawler_project_api(project_key: str):
    try:
        data = get_project(project_key=project_key)
        if data is None:
            return JSONResponse(
                status_code=404,
                content=fail(ErrorCode.NOT_FOUND, f"crawler project not found: {project_key}"),
            )
        return JSONResponse(status_code=200, content=ok(data))
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content=fail(ErrorCode.INTERNAL_ERROR, str(exc)),
        )


@router.post("/projects/{project_key}/deploy")
def deploy_crawler_project_api(
    project_key: str,
    payload: DeployCrawlerProjectPayload,
    request: Request,
):
    try:
        result = deploy_project(
            project_key=project_key,
            requested_version=payload.requested_version,
            planner_mode=payload.planner_mode,
            async_mode=payload.async_mode,
            registration_project_key=_resolve_registration_project_key(request),
        )
        return JSONResponse(status_code=200, content=ok(result))
    except CrawlerProjectNotFoundError as exc:
        return JSONResponse(
            status_code=404,
            content=fail(ErrorCode.NOT_FOUND, str(exc)),
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content=fail(ErrorCode.INVALID_INPUT, str(exc)),
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content=fail(ErrorCode.INTERNAL_ERROR, str(exc)),
        )


@router.post("/projects/{project_key}/rollback")
def rollback_crawler_project_api(
    project_key: str,
    payload: RollbackCrawlerProjectPayload,
    request: Request,
):
    try:
        result = rollback_project(
            project_key=project_key,
            target_version=payload.to_version or payload.target_version,
            planner_mode=payload.planner_mode,
            async_mode=payload.async_mode,
            registration_project_key=_resolve_registration_project_key(request),
        )
        return JSONResponse(status_code=200, content=ok(result))
    except CrawlerProjectNotFoundError as exc:
        return JSONResponse(
            status_code=404,
            content=fail(ErrorCode.NOT_FOUND, str(exc)),
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content=fail(ErrorCode.INVALID_INPUT, str(exc)),
        )
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content=fail(ErrorCode.INTERNAL_ERROR, str(exc)),
        )


@router.get("/deploy-runs/{run_id}")
def get_crawler_deploy_run_api(run_id: int):
    try:
        run = get_deploy_run(run_id)
        if run is None:
            return JSONResponse(
                status_code=404,
                content=fail(ErrorCode.NOT_FOUND, f"crawler deploy run not found: {run_id}"),
            )
        return JSONResponse(status_code=200, content=ok(run))
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content=fail(ErrorCode.INTERNAL_ERROR, str(exc)),
        )


@router.get("/deploy-runs")
def list_crawler_deploy_runs_api(
    limit: int = Query(default=50, ge=1, le=200),
):
    try:
        from ..services.crawlers_mgmt import list_deploy_runs

        rows = list_deploy_runs(limit=limit)
        return JSONResponse(status_code=200, content=ok({"items": rows}))
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content=fail(ErrorCode.INTERNAL_ERROR, str(exc)),
        )


@router.get("/projects/{project_key}/deploy-runs")
def list_crawler_project_deploy_runs_api(
    project_key: str,
    limit: int = Query(default=50, ge=1, le=200),
):
    try:
        from ..services.crawlers_mgmt import list_deploy_runs

        rows = list_deploy_runs(project_key=project_key, limit=limit)
        return JSONResponse(status_code=200, content=ok({"items": rows}))
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content=fail(ErrorCode.INTERNAL_ERROR, str(exc)),
        )
