"""Bounded v2 successor runtime API factory (C9-M001 transport surface).

This module registers nothing.  It only builds a router with injected server
scope resolver, facade and actor provider; the caller decides whether and
where to include the router.  Every command/query is server-resolved before
the facade port is called, and external DTOs never carry actor, scope,
authority or execution fields.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable

from fastapi import APIRouter, Request

from app.contracts.successor_runtime import (
    SuccessorRuntimeCommandMetaV2DTO,
    SuccessorRuntimeCommandV2DTO,
    SuccessorRuntimeEnvelopeV2DTO,
    SuccessorRuntimeProjectionMetaV2DTO,
    SuccessorRuntimeProjectScopeRefDTO,
    SuccessorRuntimeQueryMetaV2DTO,
    SuccessorRuntimeQueryV2DTO,
    SuccessorRuntimeUnresolvedMetaV2DTO,
)
from app.successor_runtime.runtime.facade import SuccessorRuntimeFacade
from app.successor_runtime.runtime.facade_contracts import (
    ApiEnvelopeV2,
    CommandMetaV2,
    FacadeCommandV2,
    FacadeQueryV2,
    ProjectionResponseMetaV2,
    ProjectionSnapshotDataV2,
    QueryMetaV2,
    derive_c9_request_digest,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef
from app.successor_runtime.substrate.postgres.session import ProjectScopeResolver

__all__ = [
    "bind_server_command",
    "bind_server_query",
    "create_successor_runtime_router",
]


def bind_server_command(
    dto: SuccessorRuntimeCommandV2DTO,
    *,
    scope: ProjectScopeRef,
    actor_ref: str,
) -> FacadeCommandV2:
    """Inject server scope/actor and derive the exact request identity."""

    payload = dto.payload.model_dump(mode="json")
    request_digest = derive_c9_request_digest(
        scope_digest=scope.scope_digest,
        actor_ref=actor_ref,
        command_id=dto.command_id,
        command_kind=dto.command_kind,
        payload=payload,
        expected_base_token=dto.expected_base_token,
        approval_locator=dto.approval_locator,
    )
    return FacadeCommandV2(
        command_id=dto.command_id,
        command_kind=dto.command_kind,
        description=f"successor runtime command {dto.command_kind}",
        project_scope_ref=scope,
        actor_ref=actor_ref,
        idempotency_key=request_digest,
        expected_base_token=dto.expected_base_token,
        meta=CommandMetaV2(
            project_key=scope.project_key,
            trace_id=dto.trace_id,
            command_id=dto.command_id,
            project_scope_ref=scope,
        ),
        approval_locator=dto.approval_locator,
        payload=payload,
    )


def bind_server_query(
    dto: SuccessorRuntimeQueryV2DTO,
    *,
    scope: ProjectScopeRef,
    actor_ref: str,
) -> FacadeQueryV2:
    """Inject server scope into a read-only query description."""

    return FacadeQueryV2(
        query_id=dto.query_id,
        query_kind=dto.query_kind,
        project_scope_ref=scope,
        actor_ref=actor_ref,
        meta=QueryMetaV2(
            project_key=scope.project_key,
            trace_id=dto.trace_id,
            query_id=dto.query_id,
            project_scope_ref=scope,
        ),
        params=dto.params.model_dump(mode="json"),
    )


def _scope_dto(scope: ProjectScopeRef) -> SuccessorRuntimeProjectScopeRefDTO:
    return SuccessorRuntimeProjectScopeRefDTO(
        project_key=scope.project_key,
        resolved_schema=scope.resolved_schema,
        project_registry_revision=scope.project_registry_revision,
        incarnation=scope.incarnation,
        scope_digest=scope.scope_digest,
    )


def _meta_dto(
    meta: CommandMetaV2 | QueryMetaV2 | ProjectionResponseMetaV2,
) -> (
    SuccessorRuntimeCommandMetaV2DTO
    | SuccessorRuntimeQueryMetaV2DTO
    | SuccessorRuntimeProjectionMetaV2DTO
):
    if isinstance(meta, CommandMetaV2):
        return SuccessorRuntimeCommandMetaV2DTO(
            project_key=meta.project_key,
            trace_id=meta.trace_id,
            command_id=meta.command_id,
            project_scope_ref=_scope_dto(meta.project_scope_ref),
        )
    if isinstance(meta, QueryMetaV2):
        return SuccessorRuntimeQueryMetaV2DTO(
            project_key=meta.project_key,
            trace_id=meta.trace_id,
            query_id=meta.query_id,
            project_scope_ref=_scope_dto(meta.project_scope_ref),
        )
    return SuccessorRuntimeProjectionMetaV2DTO(
        project_key=meta.project_key,
        trace_id=meta.trace_id,
        projection_id=meta.projection_id,
        project_scope_ref=_scope_dto(meta.project_scope_ref),
        projector_id=meta.projector_id,
        projector_version=meta.projector_version,
        source_kind=meta.source_kind,
        source_ref=meta.source_ref,
        source_incarnation=meta.source_incarnation,
        projection_generation=meta.projection_generation,
        offset_revision=meta.offset_revision,
        projection_revision=meta.projection_revision,
        source_digest=meta.source_digest,
        cursor=meta.cursor,
    )


def _envelope_dto(envelope: ApiEnvelopeV2) -> SuccessorRuntimeEnvelopeV2DTO:
    error = None
    if envelope.error is not None:
        error = {
            "code": envelope.error.code,
            "message": envelope.error.message,
            "details": dict(envelope.error.details),
        }
    data = None
    if envelope.data is not None:
        data = (
            dataclasses.asdict(envelope.data)
            if isinstance(envelope.data, ProjectionSnapshotDataV2)
            else dict(envelope.data)
        )
    return SuccessorRuntimeEnvelopeV2DTO(
        status=envelope.status,
        data=data,
        error=error,
        meta=_meta_dto(envelope.meta),
    )


def _resolution_failure_dto(
    dto: SuccessorRuntimeCommandV2DTO | SuccessorRuntimeQueryV2DTO,
    *,
    code: str,
    message: str,
) -> SuccessorRuntimeEnvelopeV2DTO:
    request_id = getattr(dto, "command_id", None) or dto.query_id
    return SuccessorRuntimeEnvelopeV2DTO(
        status="error",
        data=None,
        error={"code": code, "message": message},
        meta=SuccessorRuntimeUnresolvedMetaV2DTO(
            project_key=dto.project_locator,
            trace_id=dto.trace_id,
            request_id=request_id,
        ),
    )


def create_successor_runtime_router(
    *,
    resolver: ProjectScopeResolver,
    facade: SuccessorRuntimeFacade,
    actor_provider: Callable[[Request], str],
) -> APIRouter:
    """Return an unregistered router bound to injected server dependencies."""

    router = APIRouter(prefix="/successor-runtime/v2", tags=["successor-runtime-v2"])

    @router.post(
        "/commands",
        response_model=SuccessorRuntimeEnvelopeV2DTO,
    )
    def submit_command(
        dto: SuccessorRuntimeCommandV2DTO,
        request: Request,
    ) -> SuccessorRuntimeEnvelopeV2DTO:
        try:
            scope = resolver.resolve(dto.project_locator)
        except Exception as exc:  # noqa: BLE001 - typed envelope, never HTTP 500
            return _resolution_failure_dto(
                dto,
                code="SCOPE_RESOLUTION_FAILED",
                message=str(exc),
            )
        try:
            actor_ref = actor_provider(request)
        except Exception as exc:  # noqa: BLE001 - typed envelope, never HTTP 500
            return _resolution_failure_dto(
                dto,
                code="ACTOR_RESOLUTION_FAILED",
                message=str(exc),
            )
        command = bind_server_command(dto, scope=scope, actor_ref=actor_ref)
        return _envelope_dto(facade.submit(command))

    @router.post(
        "/queries",
        response_model=SuccessorRuntimeEnvelopeV2DTO,
    )
    def run_query(
        dto: SuccessorRuntimeQueryV2DTO,
        request: Request,
    ) -> SuccessorRuntimeEnvelopeV2DTO:
        try:
            scope = resolver.resolve(dto.project_locator)
        except Exception as exc:  # noqa: BLE001 - typed envelope, never HTTP 500
            return _resolution_failure_dto(
                dto,
                code="SCOPE_RESOLUTION_FAILED",
                message=str(exc),
            )
        try:
            actor_ref = actor_provider(request)
        except Exception as exc:  # noqa: BLE001 - typed envelope, never HTTP 500
            return _resolution_failure_dto(
                dto,
                code="ACTOR_RESOLUTION_FAILED",
                message=str(exc),
            )
        query = bind_server_query(dto, scope=scope, actor_ref=actor_ref)
        return _envelope_dto(facade.query(query))

    return router
