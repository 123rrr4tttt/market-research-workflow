from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from ..contracts import ErrorCode, error_response, success_response
from ..contracts.schemas.writing import (
    KeywordCardDetailRequest,
    KeywordCardPreviewRequest,
    KeywordCardRequest,
    LlmActionRequest,
    SuggestRequest,
    TemplateValidateRequest,
)
from ..services.projects import bind_project, current_project_key
from ..services.projects.context import _normalize_project_key
from ..services.writing import (
    WritingVersionConflictError,
    aggregate_cards,
    create_document,
    dispatch_action,
    export_document_markdown,
    get_action_detail,
    get_action_history,
    get_card_detail,
    get_card_preview,
    get_document,
    list_citations,
    list_documents,
    list_templates,
    rebuild_markdown_with_citations,
    save_document_with_conflict,
    save_draft_autosave,
    suggest,
    upsert_citations,
    validate_template_payload,
)


router = APIRouter(prefix="/writing", tags=["writing"])


class WritingDocumentCreateRequest(BaseModel):
    project_key: str | None = Field(default=None, max_length=64)
    title: str = Field(..., min_length=1, max_length=500)
    body_md: str = Field(default="", max_length=50000)
    updated_by_user_id: str | None = Field(default=None, max_length=128)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class WritingDocumentPatchRequest(BaseModel):
    project_key: str | None = Field(default=None, max_length=64)
    title: str | None = Field(default=None, max_length=500)
    body_md: str = Field(default="", max_length=50000)
    base_version: int | None = Field(default=None, ge=1)
    updated_by_user_id: str | None = Field(default=None, max_length=128)


class WritingDraftAutosaveRequest(BaseModel):
    project_key: str | None = Field(default=None, max_length=64)
    draft_body_md: str = Field(default="", max_length=50000)
    base_version: int | None = Field(default=None, ge=1)
    autosave_token: str = Field(..., min_length=1, max_length=128)
    request_id: str | None = Field(default=None, max_length=128)
    selection_snapshot: dict[str, Any] = Field(default_factory=dict)


class WritingCitationUpsertRequest(BaseModel):
    project_key: str | None = Field(default=None, max_length=64)
    citations: list[dict[str, Any]] = Field(default_factory=list)


class WritingExportMarkdownRequest(BaseModel):
    project_key: str | None = Field(default=None, max_length=64)
    doc_id: int = Field(..., ge=1)


def _resolve_project_key(explicit_project_key: str | None = None) -> str:
    candidate = str(explicit_project_key or "").strip() or str(current_project_key() or "").strip()
    if not candidate:
        raise HTTPException(
            status_code=400,
            detail=error_response(ErrorCode.PROJECT_KEY_REQUIRED, "project_key is required"),
        )
    return _normalize_project_key(candidate)


def _resolve_request_id(request: Request) -> str | None:
    return (request.headers.get("X-Request-Id") or "").strip() or None


def _handle_not_found(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=error_response(ErrorCode.NOT_FOUND, str(exc)))


def _handle_conflict(exc: WritingVersionConflictError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail=error_response(
            ErrorCode.INVALID_INPUT,
            "writing document version conflict",
            details=exc.server_snapshot,
        ),
    )


@router.get("/documents")
def list_writing_documents(project_key: str | None = Query(default=None), limit: int = Query(default=50, ge=1, le=100)):
    resolved_project_key = _resolve_project_key(project_key)
    with bind_project(resolved_project_key):
        return success_response({"items": list_documents(project_key=resolved_project_key, limit=limit)})


@router.post("/documents")
def create_writing_document(payload: WritingDocumentCreateRequest):
    resolved_project_key = _resolve_project_key(payload.project_key)
    with bind_project(resolved_project_key):
        return success_response(
            create_document(
                project_key=resolved_project_key,
                title=payload.title,
                body_md=payload.body_md,
                updated_by_user_id=payload.updated_by_user_id,
                metadata_json=payload.metadata_json,
            )
        )


@router.get("/documents/{doc_id}")
def get_writing_document(doc_id: int, project_key: str | None = Query(default=None)):
    resolved_project_key = _resolve_project_key(project_key)
    with bind_project(resolved_project_key):
        try:
            return success_response(get_document(doc_id=doc_id, project_key=resolved_project_key))
        except KeyError as exc:
            raise _handle_not_found(exc) from exc


@router.patch("/documents/{doc_id}")
def patch_writing_document(doc_id: int, payload: WritingDocumentPatchRequest, request: Request):
    resolved_project_key = _resolve_project_key(payload.project_key)
    with bind_project(resolved_project_key):
        try:
            return success_response(
                save_document_with_conflict(
                    doc_id=doc_id,
                    project_key=resolved_project_key,
                    body_md=payload.body_md,
                    title=payload.title,
                    base_version=payload.base_version,
                    if_match=(request.headers.get("If-Match") or "").strip() or None,
                    updated_by_user_id=payload.updated_by_user_id,
                )
            )
        except KeyError as exc:
            raise _handle_not_found(exc) from exc
        except WritingVersionConflictError as exc:
            raise _handle_conflict(exc) from exc


@router.post("/documents/{doc_id}/draft")
def autosave_writing_document_draft(doc_id: int, payload: WritingDraftAutosaveRequest):
    resolved_project_key = _resolve_project_key(payload.project_key)
    with bind_project(resolved_project_key):
        try:
            return success_response(
                save_draft_autosave(
                    doc_id=doc_id,
                    project_key=resolved_project_key,
                    draft_body_md=payload.draft_body_md,
                    base_version=payload.base_version,
                    autosave_token=payload.autosave_token,
                    request_id=payload.request_id,
                    selection_snapshot=payload.selection_snapshot,
                )
            )
        except KeyError as exc:
            raise _handle_not_found(exc) from exc
        except WritingVersionConflictError as exc:
            raise _handle_conflict(exc) from exc


@router.post("/documents/{doc_id}/citations")
def post_writing_document_citations(doc_id: int, payload: WritingCitationUpsertRequest):
    resolved_project_key = _resolve_project_key(payload.project_key)
    with bind_project(resolved_project_key):
        try:
            return success_response(
                {
                    "items": upsert_citations(
                        doc_id=doc_id,
                        project_key=resolved_project_key,
                        citations=payload.citations,
                    )
                }
            )
        except KeyError as exc:
            raise _handle_not_found(exc) from exc


@router.get("/documents/{doc_id}/citations")
def get_writing_document_citations(doc_id: int, project_key: str | None = Query(default=None)):
    resolved_project_key = _resolve_project_key(project_key)
    with bind_project(resolved_project_key):
        try:
            return success_response({"items": list_citations(doc_id=doc_id, project_key=resolved_project_key)})
        except KeyError as exc:
            raise _handle_not_found(exc) from exc


@router.get("/templates")
def get_writing_templates():
    return success_response({"items": list_templates()})


@router.post("/templates/validate")
def post_writing_template_validate(payload: TemplateValidateRequest, request: Request):
    resolved_project_key = _resolve_project_key(payload.project_key)
    model = payload.model_copy(update={"project_key": resolved_project_key, "request_id": _resolve_request_id(request)})
    return success_response(validate_template_payload(model).model_dump())


@router.post("/keyword-cards")
def post_keyword_cards(payload: KeywordCardRequest, request: Request):
    resolved_project_key = _resolve_project_key(payload.project_key)
    model = payload.model_copy(update={"project_key": resolved_project_key, "request_id": _resolve_request_id(request)})
    with bind_project(resolved_project_key):
        return success_response(aggregate_cards(model).model_dump())


@router.post("/keyword-cards/preview")
def post_keyword_card_preview(payload: KeywordCardPreviewRequest, request: Request):
    resolved_project_key = _resolve_project_key(payload.project_key)
    model = payload.model_copy(update={"project_key": resolved_project_key, "request_id": _resolve_request_id(request)})
    with bind_project(resolved_project_key):
        try:
            return success_response(get_card_preview(model).model_dump())
        except KeyError as exc:
            raise _handle_not_found(exc) from exc


@router.get("/cards/{card_id}")
def get_writing_card_detail(
    card_id: str,
    request: Request,
    project_key: str | None = Query(default=None),
    include_provenance: bool = Query(default=True),
    max_provenance_items: int = Query(default=20, ge=1, le=100),
):
    resolved_project_key = _resolve_project_key(project_key)
    model = KeywordCardDetailRequest(
        project_key=resolved_project_key,
        trace_id=_resolve_request_id(request),
        request_id=_resolve_request_id(request),
        card_id=card_id,
        include_provenance=include_provenance,
        max_provenance_items=max_provenance_items,
    )
    with bind_project(resolved_project_key):
        try:
            return success_response(get_card_detail(model).model_dump())
        except KeyError as exc:
            raise _handle_not_found(exc) from exc


@router.get("/suggest")
def get_writing_suggest(
    request: Request,
    query: str = Query(..., min_length=1, max_length=200),
    mode: str = Query(default="keyword"),
    project_key: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=50),
):
    resolved_project_key = _resolve_project_key(project_key)
    model = SuggestRequest(
        project_key=resolved_project_key,
        trace_id=_resolve_request_id(request),
        request_id=_resolve_request_id(request),
        query=query,
        mode=mode,
        limit=limit,
    )
    with bind_project(resolved_project_key):
        return success_response(suggest(model).model_dump())


@router.post("/llm-actions")
def post_writing_llm_action(payload: LlmActionRequest, request: Request):
    resolved_project_key = _resolve_project_key(payload.project_key)
    model = payload.model_copy(
        update={"project_key": resolved_project_key, "request_id": _resolve_request_id(request), "trace_id": payload.trace_id or _resolve_request_id(request)}
    )
    with bind_project(resolved_project_key):
        return success_response(dispatch_action(model).model_dump(by_alias=True))


@router.get("/llm-actions/history")
def get_writing_llm_action_history(project_key: str | None = Query(default=None), limit: int = Query(default=20, ge=1, le=100)):
    resolved_project_key = _resolve_project_key(project_key)
    with bind_project(resolved_project_key):
        items = [item.model_dump() for item in get_action_history(limit=limit, project_key=resolved_project_key)]
        return success_response({"items": items})


@router.get("/llm-actions/{job_id}")
def get_writing_llm_action_detail(job_id: int, project_key: str | None = Query(default=None)):
    resolved_project_key = _resolve_project_key(project_key)
    with bind_project(resolved_project_key):
        try:
            return success_response(get_action_detail(job_id=job_id, project_key=resolved_project_key).model_dump())
        except KeyError as exc:
            raise _handle_not_found(exc) from exc


@router.post("/export/markdown")
def post_writing_export_markdown(payload: WritingExportMarkdownRequest):
    resolved_project_key = _resolve_project_key(payload.project_key)
    with bind_project(resolved_project_key):
        try:
            exported = export_document_markdown(doc_id=payload.doc_id, project_key=resolved_project_key)
            citations = list_citations(doc_id=payload.doc_id, project_key=resolved_project_key)
            markdown = rebuild_markdown_with_citations(body_md=exported["markdown"], citations=citations)
            return Response(
                content=markdown,
                media_type="text/markdown",
                headers={"Content-Disposition": f"attachment; filename={exported['filename']}"},
            )
        except KeyError as exc:
            raise _handle_not_found(exc) from exc
