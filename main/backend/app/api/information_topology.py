"""HTTP transport for project-scoped information-topology operations."""
from __future__ import annotations

from typing import Any, Mapping

from fastapi import APIRouter, HTTPException, Request

from app.contracts.responses import ApiEnvelope, ApiErrorModel, ApiMetaModel, ok
from app.services.information_topology.contracts import topology_failures
from app.services.information_topology.service import InformationTopologyService
from app.services.projects.context import current_project_key
from app.contracts.schemas.information_topology import (
    ExportRequest, ImportRequest, MappingPreviewRequest, PatchRequest,
    RelationsFindRequest, ResolveRequest, TopologyReadRequest,
)

router = APIRouter(prefix="/information-topology", tags=["information-topology"])
InformationTopologyEnvelope = ApiEnvelope[dict[str, Any]]


def _error(status: int, code: str, message: str, details: Mapping[str, Any] | None = None,
           project_key: str | None = None) -> HTTPException:
    envelope = ApiEnvelope[Any](
        status="error", data=None,
        error=ApiErrorModel(code=code, message=message, details=dict(details or {})),
        meta=ApiMetaModel(project_key=project_key),
    )
    return HTTPException(status_code=status, detail=envelope.model_dump())


def _service(request: Request, project_key: str) -> InformationTopologyService:
    service = getattr(request.app.state, "information_topology_service", None)
    if not isinstance(service, InformationTopologyService):
        raise _error(503, "INFORMATION_TOPOLOGY_UNAVAILABLE",
                     "information-topology dependencies are not configured", project_key=project_key)
    return service


def _scope(project_key: str) -> str:
    current = str(current_project_key() or "").strip()
    if not current:
        raise _error(400, "PROJECT_KEY_REQUIRED", "active project context is required")
    return current


def _failure(result: Any, project_key: str) -> Any:
    if not topology_failures.matches(result):
        return result
    code = result.code
    status = {
        "INVALID_STRUCTURE": 422, "INVALID_PATCH": 422, "INVALID_WIRE_FORMAT": 422,
        "VERSION_CONFLICT": 409, "NOT_FOUND": 404, "STALE_REFERENCE": 409,
        "UNRESOLVABLE_REFERENCE": 404, "UNKNOWN_PROFILE": 422,
        "MAPPING_NOT_APPLICABLE": 422, "SOURCE_CHANGED": 409, "IDENTITY_CONFLICT": 409,
    }.get(code, 400)
    raise _error(status, code, result.message, dict(result.context or {}), project_key)


def _check_project_refs(value: Any, project_key: str) -> None:
    if isinstance(value, Mapping):
        candidate = value.get("project_key")
        if candidate is not None and candidate != project_key:
            raise _error(404, "UNRESOLVABLE_REFERENCE", "reference is outside the active project",
                         {"project_key": candidate}, project_key)
        for child in value.values():
            _check_project_refs(child, project_key)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _check_project_refs(child, project_key)


@router.get("/profiles", response_model=InformationTopologyEnvelope)
def describe_profiles(request: Request) -> dict[str, Any]:
    project_key = _scope(current_project_key())
    return ok(_service(request, project_key).describe_profiles(project_key))


@router.get("/topologies", response_model=InformationTopologyEnvelope)
def list_topologies(request: Request) -> dict[str, Any]:
    """List current state identities for read-only discovery by project clients."""
    project_key = _scope(current_project_key())
    return ok(_failure(_service(request, project_key).list_topologies(project_key), project_key))


@router.post("/resolve", response_model=InformationTopologyEnvelope)
def resolve_refs(payload: ResolveRequest, request: Request) -> dict[str, Any]:
    project_key = _scope(current_project_key())
    _check_project_refs(payload.model_dump(), project_key)
    return ok(_failure(_service(request, project_key).resolve(project_key, payload.model_dump()["refs"]), project_key))


@router.post("/topologies/read", response_model=InformationTopologyEnvelope)
def read_topology(payload: TopologyReadRequest, request: Request) -> dict[str, Any]:
    project_key = _scope(current_project_key())
    return ok(_failure(_service(request, project_key).read_topology(
        project_key, payload.topology_ref.model_dump(), payload.filters), project_key))


@router.post("/relations/find", response_model=InformationTopologyEnvelope)
def find_relations(payload: RelationsFindRequest, request: Request) -> dict[str, Any]:
    project_key = _scope(current_project_key())
    _check_project_refs(payload.model_dump(), project_key)
    return ok(_failure(_service(request, project_key).find_relations(
        project_key, payload.ref.model_dump(), payload.relation_types, payload.direction), project_key))


@router.post("/mappings/preview", response_model=InformationTopologyEnvelope)
def preview_mapping(payload: MappingPreviewRequest, request: Request) -> dict[str, Any]:
    project_key = _scope(current_project_key())
    return ok(_failure(_service(request, project_key).preview_mapping(
        project_key, payload.mapping_ref, [ref.model_dump() for ref in payload.input_refs]), project_key))


@router.post("/patches", response_model=InformationTopologyEnvelope)
def apply_patch(payload: PatchRequest, request: Request) -> dict[str, Any]:
    project_key = _scope(current_project_key())
    _check_project_refs(payload.model_dump(), project_key)
    state_patches = [item.model_dump() for item in payload.state_patches]
    if payload.target is not None:
        state_patches.insert(0, {
            "target": payload.target.model_dump(), "base_revision": payload.base_revision,
            "patch": [operation.model_dump() for operation in (payload.patch or [])],
        })
    result = _service(request, project_key).apply_batch(
        project_key,
        state_patches=state_patches,
        link_writes=[item.model_dump() for item in payload.link_writes],
        read_set=[item.model_dump() for item in payload.read_set],
        link_read_set=[item.model_dump() for item in payload.link_read_set],
    )
    return ok(_failure(result, project_key))


@router.post("/imports", response_model=InformationTopologyEnvelope)
def import_structure(payload: ImportRequest, request: Request) -> dict[str, Any]:
    project_key = _scope(current_project_key())
    _check_project_refs(payload.source, project_key)
    result = _service(request, project_key).import_structure(project_key, payload.module_id, payload.source)
    return ok({"import_result": _failure(result, project_key)})


@router.post("/exports", response_model=InformationTopologyEnvelope)
def export_structure(payload: ExportRequest, request: Request) -> dict[str, Any]:
    project_key = _scope(current_project_key())
    result = _service(request, project_key).export_structure(
        project_key, payload.target.model_dump(), payload.format)
    return ok({"export_result": _failure(result, project_key)})


__all__ = ["router"]
