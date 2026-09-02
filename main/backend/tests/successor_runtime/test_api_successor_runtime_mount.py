"""WP-I1-06 successor runtime route-mount tests.

Covers the default LOCAL_ONLY app mount: final ``/api/v1/successor-runtime/v2``
route table, typed command/query envelopes, all six v2 status states, typed
rejections, no control feedback, closed authority ceiling and preserved legacy
routes.  No database, provider, network or live registration is touched.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine

from app.api import router as api_router
from app.api import successor_runtime as api_module
from app.contracts.successor_runtime import (
    SuccessorRuntimeCommandMetaV2DTO,
    SuccessorRuntimeEnvelopeV2DTO,
    SuccessorRuntimeProjectScopeRefDTO,
)
from app.successor_runtime.assembly import (
    ALL_I1_CELLS,
    local_assembly_scope_digest,
)
from app.successor_runtime.assembly.app_assembly import (
    AUTHORITY_CEILING_CLOSED,
    LOCAL_ONLY_MOUNT_ACTOR,
    SuccessorRuntimeAppDependencies,
    build_successor_runtime_app_dependencies,
)
from app.successor_runtime.assembly.successor_assembly import (
    assemble_successor_runtime,
)
from app.successor_runtime.runtime.facade import SuccessorRuntimeFacade
from app.successor_runtime.runtime.facade_contracts import (
    C9CommandBlocked,
    C9CommandConflict,
    C9Unavailable,
    CommandReceipt,
    CommandSubmissionPort,
    FacadeCommandV2,
    FacadeQueryV2,
    ProjectionResponseMetaV2,
    QueryReadPort,
    QueryResult,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef

pytestmark = pytest.mark.unit

LOCAL_PROJECT = "local-mount-demo"
TRACE = "trace:mount:1"
PROJECTION_ID = "projection.run-summary.v1"
SOURCE_IDENTITY = {
    "projector_id": "projector:c9-mount",
    "projector_version": "1",
    "source_kind": "successor_values",
    "source_ref": "c9:mount:source:001",
    "source_incarnation": "inc:c9-mount",
}
SCOPE = ProjectScopeRef(
    project_key=LOCAL_PROJECT,
    resolved_schema="mrw_p_local_mount_demo",
    project_registry_revision=0,
    incarnation="inc:c9-mount",
    scope_digest=local_assembly_scope_digest(),
)
CONTROL_TOP_LEVEL_FIELDS = (
    "actor",
    "authority",
    "execute",
    "execution_mode",
    "approval",
    "scope",
    "schema",
    "control",
)


def _engine():
    return create_engine("sqlite+pysqlite:///:memory:", future=True)


def _command_body(**overrides: Any) -> dict[str, Any]:
    body = {
        "command_id": "cmd-mount-1",
        "command_kind": "rebuild_projection",
        "project_locator": LOCAL_PROJECT,
        "trace_id": TRACE,
        "payload": {
            "payload_kind": "rebuild_projection",
            "projection_id": PROJECTION_ID,
            **SOURCE_IDENTITY,
        },
    }
    body.update(overrides)
    return body


def _query_body(**overrides: Any) -> dict[str, Any]:
    body = {
        "query_id": "query-mount-1",
        "query_kind": "projection_snapshot",
        "project_locator": LOCAL_PROJECT,
        "trace_id": TRACE,
        "params": {
            "params_kind": "projection_snapshot",
            "projection_id": PROJECTION_ID,
            **SOURCE_IDENTITY,
        },
    }
    body.update(overrides)
    return body


def _app_with_router(*, router: Any | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(router or api_router, prefix="/api/v1")
    return app


class _CommandPort(CommandSubmissionPort):
    def __init__(
        self,
        *,
        receipt: CommandReceipt | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls = 0
        self.last: FacadeCommandV2 | None = None
        self._receipt = receipt
        self._error = error

    def submit(self, command: FacadeCommandV2) -> CommandReceipt:
        self.calls += 1
        self.last = command
        if self._error is not None:
            raise self._error
        return self._receipt or CommandReceipt(
            receipt_ref="receipt:local-only-mount",
            command_id=command.command_id,
            request_digest=command.idempotency_key,
            state="TERMINAL",
            idempotency_id="idem:local-only-mount",
            logical_request_id=command.command_id,
        )


class _QueryPort(QueryReadPort):
    def __init__(
        self,
        *,
        result: QueryResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls = 0
        self.last: FacadeQueryV2 | None = None
        self._result = result
        self._error = error

    def read(self, query: FacadeQueryV2) -> QueryResult:
        self.calls += 1
        self.last = query
        if self._error is not None:
            raise self._error
        return self._result or QueryResult(
            data={"projection_generation": 1, "cells": {"C9.1": "INSTALLED"}},
            meta=ProjectionResponseMetaV2(
                project_key=SCOPE.project_key,
                trace_id=TRACE,
                projection_id=PROJECTION_ID,
                project_scope_ref=SCOPE,
                projector_id=SOURCE_IDENTITY["projector_id"],
                projector_version=SOURCE_IDENTITY["projector_version"],
                source_kind=SOURCE_IDENTITY["source_kind"],
                source_ref=SOURCE_IDENTITY["source_ref"],
                source_incarnation=SOURCE_IDENTITY["source_incarnation"],
                projection_generation=1,
                offset_revision=0,
                projection_revision=1,
                source_digest="c" * 64,
                cursor=0,
            ),
        )


class _StubResolver:
    def __init__(self, scope: ProjectScopeRef) -> None:
        self.scope = scope
        self.calls = 0

    def resolve(self, project_locator: str) -> ProjectScopeRef:
        self.calls += 1
        if project_locator != self.scope.project_key:
            raise LookupError("unknown project locator")
        return self.scope


def test_default_dependencies_are_closed_local_only() -> None:
    deps = build_successor_runtime_app_dependencies()
    assert isinstance(deps, SuccessorRuntimeAppDependencies)
    assert isinstance(deps.facade, SuccessorRuntimeFacade)
    assert deps.assembly_options.c9.facade is deps.facade
    assert deps.configuration == "local_only_closed_fixture_options"
    assert deps.candidate is None
    assert deps.authority_ceiling == dict(AUTHORITY_CEILING_CLOSED)
    assert all(value is False for value in deps.authority_ceiling.values())
    assert deps.actor_provider is not None
    resolved = deps.resolver.resolve(LOCAL_PROJECT)
    assert resolved.project_key == LOCAL_PROJECT
    assert resolved.scope_digest == local_assembly_scope_digest()
    with pytest.raises(Exception, match="LOCAL_ONLY"):
        deps.resolver.resolve_expected(LOCAL_PROJECT, 0, "0" * 64)


def test_default_mount_options_keep_assembly_fail_closed() -> None:
    deps = build_successor_runtime_app_dependencies()
    assembly = assemble_successor_runtime(
        engine=_engine(),
        options=deps.assembly_options,
    )
    coverage = assembly.coverage()
    assert coverage["C9.1"] == "INSTALLED"
    assert coverage["C9.2"] == "INSTALLED"
    assert coverage["C8.3"] == "INSTALLED"
    installed = {
        cell_id for cell_id, status in coverage.items() if status == "INSTALLED"
    }
    assert installed == set(ALL_I1_CELLS)
    assert len(assembly.projector_registry.projectors) == 6


def test_mounted_command_returns_typed_envelope() -> None:
    deps = build_successor_runtime_app_dependencies()
    port = _CommandPort()
    facade = SuccessorRuntimeFacade(
        submission_port=port,
        query_port=_QueryPort(),
    )
    router = api_module.create_successor_runtime_router(
        resolver=deps.resolver,
        facade=facade,
        actor_provider=deps.actor_provider,
    )
    app = _app_with_router(router=router)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/successor-runtime/v2/commands",
            json=_command_body(),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["data"]["state"] == "TERMINAL"
    assert body["error"] is None
    assert body["meta"]["command_id"] == "cmd-mount-1"
    assert body["meta"]["project_scope_ref"]["project_key"] == LOCAL_PROJECT
    assert body["control_feedback"] is False
    assert port.calls == 1
    assert port.last is not None
    assert port.last.actor_ref == LOCAL_ONLY_MOUNT_ACTOR
    assert port.last.execute is False
    for key in CONTROL_TOP_LEVEL_FIELDS:
        assert key not in body


def test_mounted_query_returns_typed_projection_envelope() -> None:
    deps = build_successor_runtime_app_dependencies()
    port = _QueryPort()
    facade = SuccessorRuntimeFacade(
        submission_port=_CommandPort(),
        query_port=port,
    )
    router = api_module.create_successor_runtime_router(
        resolver=deps.resolver,
        facade=facade,
        actor_provider=deps.actor_provider,
    )
    app = _app_with_router(router=router)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/successor-runtime/v2/queries",
            json=_query_body(),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["data"]["cells"]["C9.1"] == "INSTALLED"
    assert body["error"] is None
    assert body["meta"]["projection_id"] == PROJECTION_ID
    assert body["meta"]["projector_id"] == SOURCE_IDENTITY["projector_id"]
    assert body["control_feedback"] is False
    assert port.calls == 1
    assert port.last is not None
    assert port.last.read_only is True
    for key in CONTROL_TOP_LEVEL_FIELDS:
        assert key not in body


@pytest.mark.parametrize(
    ("status", "port_error", "receipt_state", "error_code"),
    [
        ("ok", None, "TERMINAL", None),
        ("waiting", None, "STARTED", None),
        ("blocked", C9CommandBlocked("blocked by authority"), None, "COMMAND_BLOCKED"),
        (
            "unavailable",
            C9Unavailable("runtime unavailable"),
            None,
            "COMMAND_UNAVAILABLE",
        ),
        ("conflict", C9CommandConflict("base conflict"), None, "COMMAND_CONFLICT"),
        ("error", ValueError("submission failed"), None, "COMMAND_FAILED"),
    ],
)
def test_mounted_router_exposes_all_six_v2_status_states(
    status: str,
    port_error: Exception | None,
    receipt_state: str | None,
    error_code: str | None,
) -> None:
    receipt = None
    if receipt_state is not None:
        receipt = CommandReceipt(
            receipt_ref="receipt:status-test",
            command_id="cmd-status",
            request_digest="a" * 64,
            state=receipt_state,  # type: ignore[arg-type]
            idempotency_id="idem:status",
            logical_request_id="cmd-status",
        )
    port = _CommandPort(receipt=receipt, error=port_error)
    facade = SuccessorRuntimeFacade(
        submission_port=port,
        query_port=_QueryPort(),
    )
    router = api_module.create_successor_runtime_router(
        resolver=_StubResolver(SCOPE),
        facade=facade,
        actor_provider=lambda request: "actor:test",
    )
    app = _app_with_router(router=router)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/successor-runtime/v2/commands",
            json=_command_body(command_id="cmd-status"),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == status
    assert body["control_feedback"] is False
    if status in {"ok", "waiting"}:
        assert body["data"] is not None
        assert body["error"] is None
    else:
        assert body["data"] is None
        assert body["error"] is not None
        assert body["error"]["code"] == error_code
    assert port.calls == 1


def test_scope_and_actor_rejections_return_typed_envelope() -> None:
    facade = SuccessorRuntimeFacade(
        submission_port=_CommandPort(),
        query_port=_QueryPort(),
    )
    router = api_module.create_successor_runtime_router(
        resolver=_StubResolver(SCOPE),
        facade=facade,
        actor_provider=lambda request: "actor:test",
    )
    app = _app_with_router(router=router)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/successor-runtime/v2/commands",
            json=_command_body(project_locator="unknown-project"),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "SCOPE_RESOLUTION_FAILED"
    assert body["meta"]["resolution_state"] == "UNRESOLVED"
    assert body["meta"]["request_id"] == "cmd-mount-1"
    assert body["control_feedback"] is False

    def _fail_actor(request: Request) -> str:
        raise PermissionError("actor lookup failed")

    actor_router = api_module.create_successor_runtime_router(
        resolver=_StubResolver(SCOPE),
        facade=facade,
        actor_provider=_fail_actor,
    )
    app = _app_with_router(router=actor_router)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/successor-runtime/v2/queries",
            json=_query_body(),
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["error"]["code"] == "ACTOR_RESOLUTION_FAILED"
    assert body["meta"]["resolution_state"] == "UNRESOLVED"
    assert body["control_feedback"] is False


def test_unknown_authority_fields_are_rejected_before_facade() -> None:
    port = _CommandPort()
    facade = SuccessorRuntimeFacade(
        submission_port=port,
        query_port=_QueryPort(),
    )
    router = api_module.create_successor_runtime_router(
        resolver=_StubResolver(SCOPE),
        facade=facade,
        actor_provider=lambda request: "actor:test",
    )
    app = _app_with_router(router=router)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/successor-runtime/v2/commands",
            json=_command_body(execute=True),
        )
    assert response.status_code == 422
    assert port.calls == 0
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/successor-runtime/v2/commands",
            json=_command_body(authority={"execute": True}),
        )
    assert response.status_code == 422
    assert port.calls == 0


def test_envelope_dto_forbids_control_feedback_and_unknown_status() -> None:
    meta = SuccessorRuntimeCommandMetaV2DTO(
        project_key=SCOPE.project_key,
        trace_id=TRACE,
        command_id="cmd-mount-1",
        project_scope_ref=SuccessorRuntimeProjectScopeRefDTO(
            project_key=SCOPE.project_key,
            resolved_schema=SCOPE.resolved_schema,
            project_registry_revision=SCOPE.project_registry_revision,
            incarnation=SCOPE.incarnation,
            scope_digest=SCOPE.scope_digest,
        ),
    )
    with pytest.raises(ValidationError):
        SuccessorRuntimeEnvelopeV2DTO(
            status="ok",
            data={},
            error=None,
            meta=meta,
            control_feedback=True,  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError):
        SuccessorRuntimeEnvelopeV2DTO(
            status="unknown",
            data={},
            error=None,
            meta=meta,
            control_feedback=False,
        )
    envelope = SuccessorRuntimeEnvelopeV2DTO(
        status="ok",
        data={},
        error=None,
        meta=meta,
        control_feedback=False,
    )
    assert envelope.control_feedback is False


def test_mount_preserves_legacy_routes_and_adds_only_new_prefix() -> None:
    paths = {route.path for route in api_router.routes}
    assert "/successor-runtime/v2/commands" in paths
    assert "/successor-runtime/v2/queries" in paths
    assert len(paths) > 200
    app = _app_with_router()
    mounted_paths = {route.path for route in app.routes}
    assert "/api/v1/successor-runtime/v2/commands" in mounted_paths
    assert "/api/v1/successor-runtime/v2/queries" in mounted_paths
    assert len(mounted_paths) > 200


def test_router_factory_remains_module_bounded() -> None:
    assert not hasattr(api_module, "router")
    facade = SuccessorRuntimeFacade(
        submission_port=_CommandPort(),
        query_port=_QueryPort(),
    )
    first = api_module.create_successor_runtime_router(
        resolver=_StubResolver(SCOPE),
        facade=facade,
        actor_provider=lambda request: "actor:test",
    )
    second = api_module.create_successor_runtime_router(
        resolver=_StubResolver(SCOPE),
        facade=facade,
        actor_provider=lambda request: "actor:test",
    )
    assert first is not second
