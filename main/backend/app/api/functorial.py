"""FastAPI routes for the functorial operator / motif / workflow catalog.

``PROJECTION_ONLY`` HTTP surface for the lightweight functorial development
projection. It has no production canonical-write, promotion, cutover, or
authority-transfer authority. Catalog reads/upserts use the shared local
projection services; workflow execution delegates to ``run_workflow``.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..contracts import ApiEnvelope, ErrorCode, error_response
from ..contracts.responses import ok
from ..services.agent_core.functorial.catalog import (
    ensure_operator_catalog,
    get_operator,
    list_operators,
    upsert_operator,
)
from ..services.agent_core.functorial.contracts import OperatorRisk
from ..services.agent_core.functorial.motif import compose_motif
from ..services.agent_core.functorial.operator import OperatorValidationError
from ..services.agent_core.functorial.operator import OperatorSpec
from ..services.agent_core.functorial.registry import catalog as functorial_catalog
from ..services.agent_core.functorial.run import run_workflow
from ..services.agent_core.functorial.workflow import build_workflow_program


router = APIRouter(prefix="/functorial", tags=["functorial"])

FunctorialEnvelope = ApiEnvelope[dict[str, Any]]


class OperatorUpsertPayload(BaseModel):
    operator_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    impl_ref: str = Field(..., min_length=1)
    risk: OperatorRisk


class MotifComposePayload(BaseModel):
    motif_id: str = Field(..., min_length=1)
    name: str | None = Field(default=None)
    composition: list[str] = Field(default_factory=list)


class WorkflowBuildPayload(BaseModel):
    workflow_id: str = Field(..., min_length=1)
    name: str | None = Field(default=None)
    steps: list[Any] = Field(
        ...,
        description='Ordered refs: "operator:<id>"/"motif:<id>" strings or {"ref": ...} dicts',
    )
    laws: list[str] | str | None = Field(default=None)


class WorkflowRunPayload(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    project_key: str | None = Field(default=None)


def _http_error(status_code: int, code: ErrorCode, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=error_response(code, message))


def _service_http_error(exc: Exception) -> HTTPException:
    message = str(exc) or exc.__class__.__name__
    if isinstance(exc, KeyError):
        return _http_error(404, ErrorCode.NOT_FOUND, message)
    if isinstance(exc, (OperatorValidationError, TypeError, ValueError)):
        return _http_error(400, ErrorCode.INVALID_INPUT, message)
    return _http_error(500, ErrorCode.INTERNAL_ERROR, message)


def _require_record(record: dict[str, Any] | None, kind: str) -> dict[str, Any]:
    if record is None:
        raise _http_error(404, ErrorCode.NOT_FOUND, f"{kind} not found")
    return record


@router.get("/operators", response_model=FunctorialEnvelope)
def functorial_list_operators() -> dict[str, Any]:
    ensure_operator_catalog()
    items = list_operators()
    return ok({"items": items, "total": len(items)})


@router.get("/operators/{operator_id}", response_model=FunctorialEnvelope)
def functorial_get_operator(operator_id: str) -> dict[str, Any]:
    ensure_operator_catalog()
    record = _require_record(get_operator(operator_id), "operator")
    return ok({"operator": record})


@router.post("/operators", response_model=FunctorialEnvelope)
def functorial_upsert_operator(payload: OperatorUpsertPayload) -> dict[str, Any]:
    try:
        spec = OperatorSpec(**payload.model_dump())
        record = upsert_operator(spec)
    except Exception as exc:  # noqa: BLE001
        raise _service_http_error(exc) from exc
    return ok({"operator": record})


@router.get("/motifs", response_model=FunctorialEnvelope)
def functorial_list_motifs() -> dict[str, Any]:
    items = functorial_catalog.list("motifs")
    return ok({"items": items, "total": len(items)})


@router.post("/motifs", response_model=FunctorialEnvelope)
def functorial_compose_motif(payload: MotifComposePayload) -> dict[str, Any]:
    try:
        spec = compose_motif(payload.motif_id, payload.name, payload.composition)
    except Exception as exc:  # noqa: BLE001
        raise _service_http_error(exc) from exc
    record = functorial_catalog.get("motifs", spec.motif_id)
    return ok({"motif": record if record is not None else spec.to_dict()})


@router.get("/workflows", response_model=FunctorialEnvelope)
def functorial_list_workflows() -> dict[str, Any]:
    items = functorial_catalog.list("workflows")
    return ok({"items": items, "total": len(items)})


@router.get("/workflows/{workflow_id}", response_model=FunctorialEnvelope)
def functorial_get_workflow(workflow_id: str) -> dict[str, Any]:
    record = _require_record(functorial_catalog.get("workflows", workflow_id), "workflow")
    return ok({"workflow": record})


@router.post("/workflows", response_model=FunctorialEnvelope)
def functorial_build_workflow(payload: WorkflowBuildPayload) -> dict[str, Any]:
    try:
        spec = build_workflow_program(
            workflow_id=payload.workflow_id,
            name=payload.name,
            steps=payload.steps,
            laws=payload.laws,
        )
    except Exception as exc:  # noqa: BLE001
        raise _service_http_error(exc) from exc
    record = functorial_catalog.get("workflows", spec.workflow_id)
    return ok({"workflow": record if record is not None else spec.to_dict()})


@router.post("/workflows/{workflow_id}/run", response_model=FunctorialEnvelope)
def functorial_run_workflow(workflow_id: str, body: WorkflowRunPayload) -> dict[str, Any]:
    _require_record(functorial_catalog.get("workflows", workflow_id), "workflow")
    project_key = (body.project_key or "").strip() or "demo_proj_compare_0303_121137"
    result = run_workflow(workflow_id, body.inputs, project_key)
    return ok({**result, "authority": "PROJECTION_ONLY"})
