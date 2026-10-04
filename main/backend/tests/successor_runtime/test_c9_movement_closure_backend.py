"""Pure C9 movement-closure backend tests (C9-M001/M003 transport contracts).

These tests exercise the additive v2 DTOs, the exact envelope variant rules,
the pure facade service (one port call per request, no execution), the bounded
API factory, and the deterministic pure rebuild surface.  No database,
provider, network or live registration is touched.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from app.api import successor_runtime as api_module
from app.contracts.successor_runtime import (
    API_STATUS_KINDS_V2,
    SuccessorRuntimeCommandV2DTO,
    SuccessorRuntimeEnvelopeV2DTO,
    SuccessorRuntimeProjectionMetaV2DTO,
    SuccessorRuntimeProjectionSnapshotV2Params,
    SuccessorRuntimeQueryV2DTO,
    SuccessorRuntimeRebuildProjectionV2Payload,
    SuccessorRuntimeRollbackProjectionV2Payload,
)
from app.successor_runtime.runtime import facade as facade_module
from app.successor_runtime.runtime.facade import SuccessorRuntimeFacade
from app.successor_runtime.runtime.facade_contracts import (
    API_STATUS_KINDS,
    PROJECTION_REQUEST_IDENTITY_CONTRACT,
    PROJECTION_ROLLBACK_TRANSITION_CONTRACT,
    C9CommandBaseConflict,
    C9CommandBlocked,
    C9CommandConflict,
    C9Unavailable,
    CommandMetaV2,
    CommandReceipt,
    CommandSubmissionPort,
    FacadeCommandV2,
    FacadeQueryV2,
    ProjectionCandidateValueV2,
    ProjectionResponseMetaV2,
    ProjectionRollbackTransitionReceiptV2,
    ProjectionSnapshotDataV2,
    QueryMetaV2,
    QueryReadPort,
    QueryResult,
    RollbackPositionV1,
    derive_projection_request_identity,
    validate_api_envelope_v2,
    validate_projection_snapshot_data_v2,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres import projection_query_read_port
from app.successor_runtime.substrate.postgres.c7_projector_driver import (
    MATERIAL_CANONICAL_SOURCE_KIND,
    MATERIAL_SEARCH_PROJECTOR_ID,
    MATERIAL_SEARCH_PROJECTOR_VERSION,
)
from app.successor_runtime.substrate.postgres.projection_offsets import (
    ProjectionOffsetKey,
)
from app.successor_runtime.substrate.postgres.projection_query_read_port import (
    ACTIVE_PROJECT_MATERIAL_PROJECTOR_ID,
    ACTIVE_PROJECT_MATERIAL_PROJECTOR_VERSION,
    PostgresProjectionQueryReadPort,
)
from app.successor_runtime.substrate.projections.projection_sources import (
    MATERIAL_SEGMENT_SCHEMA,
    MATERIAL_SOURCE_SCHEMA,
    PROJECT_SOURCE_CLOSURE_SCHEMA,
    KNOWLEDGE_OBJECT_SCHEMA,
    KNOWLEDGE_SOURCE_SCHEMA,
    TASK_EVENT_SCHEMA,
    TASK_SOURCE_SCHEMA,
    MaterialSegment,
    MaterialSource,
    ProjectSourceClosure,
    KnowledgeObject,
    KnowledgeSource,
    TaskSourceEvent,
    TaskSource,
    build_knowledge_view,
)
from app.successor_runtime.substrate.projections.projection_sources import (
    canonical_json as c9_canonical_json,
)
from app.successor_runtime.substrate.projections.projection_sources import (
    content_digest as c9_content_digest,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

_BACKEND = Path(__file__).resolve().parents[2]
_REBUILD_SCRIPT = _BACKEND / "scripts" / "c9_projection_rebuild.py"

SCOPE = ProjectScopeRef(
    project_key="p4-c9-demo",
    resolved_schema="mrw_p4_c9_demo",
    project_registry_revision=1,
    incarnation="scope-inc-c9-v2",
    scope_digest="b" * 64,
)
ACTOR = "actor:user-1"
TRACE = "trace-v2-1"
PROJECTION_ID = "projection.run-summary.v1"
SOURCE_IDENTITY = {
    "projector_id": "projection.project-source-identity.v2",
    "projector_version": "2.0.0",
    "source_kind": "projection_source",
    "source_ref": f"projection:{SCOPE.project_key}:source",
    "source_incarnation": SCOPE.incarnation,
}
REBUILD_KEY = ProjectionOffsetKey(
    projector_id=SOURCE_IDENTITY["projector_id"],
    projector_version=SOURCE_IDENTITY["projector_version"],
    source_kind=SOURCE_IDENTITY["source_kind"],
    source_ref=SOURCE_IDENTITY["source_ref"],
    source_incarnation=SOURCE_IDENTITY["source_incarnation"],
)


def _command_dto(**overrides: Any) -> SuccessorRuntimeCommandV2DTO:
    values: dict[str, Any] = {
        "command_id": "cmd-v2-1",
        "command_kind": "rebuild_projection",
        "project_locator": SCOPE.project_key,
        "trace_id": TRACE,
        "payload": SuccessorRuntimeRebuildProjectionV2Payload(
            projection_id=PROJECTION_ID,
            **SOURCE_IDENTITY,
        ),
    }
    values.update(overrides)
    return SuccessorRuntimeCommandV2DTO(**values)


def _query_dto(**overrides: Any) -> SuccessorRuntimeQueryV2DTO:
    values: dict[str, Any] = {
        "query_id": "query-v2-1",
        "query_kind": "projection_snapshot",
        "project_locator": SCOPE.project_key,
        "trace_id": TRACE,
        "params": SuccessorRuntimeProjectionSnapshotV2Params(
            projection_id=PROJECTION_ID,
            **SOURCE_IDENTITY,
        ),
    }
    values.update(overrides)
    return SuccessorRuntimeQueryV2DTO(**values)


def _command(**overrides: Any) -> FacadeCommandV2:
    values: dict[str, Any] = {
        "command_id": "cmd-v2-1",
        "command_kind": "rebuild_projection",
        "description": "rebuild projection",
        "project_scope_ref": SCOPE,
        "actor_ref": ACTOR,
        "idempotency_key": "a" * 64,
        "expected_base_token": None,
        "meta": CommandMetaV2(
            project_key=SCOPE.project_key,
            trace_id=TRACE,
            command_id="cmd-v2-1",
            project_scope_ref=SCOPE,
        ),
        "payload": {
            "projection_id": PROJECTION_ID,
            **SOURCE_IDENTITY,
        },
    }
    values.update(overrides)
    return FacadeCommandV2(**values)


def _query(**overrides: Any) -> FacadeQueryV2:
    values: dict[str, Any] = {
        "query_id": "query-v2-1",
        "query_kind": "projection_snapshot",
        "project_scope_ref": SCOPE,
        "actor_ref": ACTOR,
        "meta": QueryMetaV2(
            project_key=SCOPE.project_key,
            trace_id=TRACE,
            query_id="query-v2-1",
            project_scope_ref=SCOPE,
        ),
        "params": {
            "projection_id": PROJECTION_ID,
            **SOURCE_IDENTITY,
        },
    }
    values.update(overrides)
    return FacadeQueryV2(**values)


def test_active_material_selector_resolves_to_exact_persisted_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_scope = RuntimeScope(project_scope=SCOPE, actor_id=ACTOR)
    material_payload = {
        "schema_version": "mrw.projection.material-source.v2",
        "material_ref": f"material:{SCOPE.project_key}",
        "revision": 7,
        "incarnation": SCOPE.incarnation,
        "segments": [],
    }
    resolved = SimpleNamespace(
        projector_id="projection.project-source-identity.v2",
        projector_version="2.0.0",
        source_kind="projection_source",
        source_ref=f"projection:{SCOPE.project_key}:source",
        source_incarnation=SCOPE.incarnation,
        projection_generation=3,
        offset_revision=5,
        source_revision=7,
        source_digest="c" * 64,
        offset_ref="projection:source:manifest:7",
        material_value_id="projection:source:material:7",
        material_value_ref="project-value:projection:source:material:7",
        material_content_digest="d" * 64,
        material_byte_size=123,
        material_source=SimpleNamespace(to_plain=lambda: material_payload),
    )
    monkeypatch.setattr(
        projection_query_read_port,
        "load_current_material_projection_source",
        lambda connection, scope: resolved,
    )
    monkeypatch.setattr(
        PostgresProjectionQueryReadPort,
        "_require_current_scope",
        lambda self: None,
    )
    query = FacadeQueryV2(
        query_id="query:active-material",
        query_kind="projection_snapshot",
        project_scope_ref=SCOPE,
        actor_ref=ACTOR,
        meta=QueryMetaV2(
            project_key=SCOPE.project_key,
            trace_id="trace:active-material",
            query_id="query:active-material",
            project_scope_ref=SCOPE,
        ),
        params={
            "params_kind": "projection_snapshot",
            "projection_id": ACTIVE_PROJECT_MATERIAL_PROJECTOR_ID,
            "projector_id": ACTIVE_PROJECT_MATERIAL_PROJECTOR_ID,
            "projector_version": ACTIVE_PROJECT_MATERIAL_PROJECTOR_VERSION,
            "source_kind": "material",
            "source_ref": f"material:{SCOPE.project_key}",
            "source_incarnation": f"active-project:{SCOPE.project_key}",
            "page_size": 25,
        },
    )

    result = PostgresProjectionQueryReadPort(object(), runtime_scope).read(query)  # type: ignore[arg-type]

    assert result.meta.projection_id == ACTIVE_PROJECT_MATERIAL_PROJECTOR_ID
    assert result.meta.projector_id == resolved.projector_id
    assert result.meta.source_ref == resolved.source_ref
    assert result.meta.source_incarnation == SCOPE.incarnation
    assert result.meta.source_digest == "c" * 64
    assert result.data.offset_ref == resolved.offset_ref
    assert result.data.projection_revision == 7
    assert result.data.candidate_values[0].sink == "material"
    assert result.data.candidate_values[0].payload == material_payload
    assert validate_projection_snapshot_data_v2(result.data, result.meta).valid


@pytest.mark.parametrize("source_ref", ("", "document:"))
def test_material_document_source_ref_errors_use_business_identity(
    source_ref: str,
) -> None:
    with pytest.raises(C9Unavailable, match="material projection") as exc:
        projection_query_read_port._object_id_from_source_ref(source_ref)

    assert "C7" not in str(exc.value)


def test_material_projector_rejects_development_projection_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_scope = RuntimeScope(project_scope=SCOPE, actor_id=ACTOR)
    monkeypatch.setattr(
        PostgresProjectionQueryReadPort,
        "_require_current_scope",
        lambda self: None,
    )
    query = FacadeQueryV2(
        query_id="query:material-projection-identity",
        query_kind="projection_snapshot",
        project_scope_ref=SCOPE,
        actor_ref=ACTOR,
        meta=QueryMetaV2(
            project_key=SCOPE.project_key,
            trace_id="trace:material-projection-identity",
            query_id="query:material-projection-identity",
            project_scope_ref=SCOPE,
        ),
        params={
            "params_kind": "projection_snapshot",
            "projection_id": "projection.development-placeholder.v1",
            "projector_id": MATERIAL_SEARCH_PROJECTOR_ID,
            "projector_version": MATERIAL_SEARCH_PROJECTOR_VERSION,
            "source_kind": MATERIAL_CANONICAL_SOURCE_KIND,
            "source_ref": "document:material-1",
            "source_incarnation": SCOPE.incarnation,
            "page_size": 25,
        },
    )

    with pytest.raises(C9Unavailable, match="material projection_id") as exc:
        PostgresProjectionQueryReadPort(object(), runtime_scope).read(query)  # type: ignore[arg-type]

    assert "C7" not in str(exc.value)


class CountingSubmissionPort(CommandSubmissionPort):
    def __init__(
        self,
        *,
        receipt: CommandReceipt | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls = 0
        self.receipt = receipt
        self.error = error
        self.last_command: FacadeCommandV2 | None = None

    def submit(self, command: FacadeCommandV2) -> CommandReceipt:
        self.calls += 1
        self.last_command = command
        if self.error is not None:
            raise self.error
        return self.receipt or CommandReceipt(
            receipt_ref=(
                "material-projection-receipt:"
                "idem:material-projections:cmd-v2-1"
            ),
            command_id=command.command_id,
            request_digest=command.idempotency_key,
            state="STARTED",
            idempotency_id="idem:material-projections:cmd-v2-1",
            logical_request_id=command.command_id,
        )


class CountingQueryPort(QueryReadPort):
    def __init__(
        self,
        *,
        result: QueryResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.calls = 0
        self.result = result
        self.error = error
        self.last_query: FacadeQueryV2 | None = None

    def read(self, query: FacadeQueryV2) -> QueryResult:
        self.calls += 1
        self.last_query = query
        if self.error is not None:
            raise self.error
        return self.result or QueryResult(
            data={"projection_generation": 3},
            meta=ProjectionResponseMetaV2(
                project_key=SCOPE.project_key,
                trace_id=TRACE,
                projection_id="projection.run-summary.v1",
                project_scope_ref=SCOPE,
                projector_id=SOURCE_IDENTITY["projector_id"],
                projector_version=SOURCE_IDENTITY["projector_version"],
                source_kind=SOURCE_IDENTITY["source_kind"],
                source_ref=SOURCE_IDENTITY["source_ref"],
                source_incarnation=SOURCE_IDENTITY["source_incarnation"],
                projection_generation=3,
                offset_revision=1,
                projection_revision=3,
                source_digest="c" * 64,
                cursor=2,
            ),
        )


class StubResolver:
    def __init__(self, scope: ProjectScopeRef) -> None:
        self.scope = scope
        self.calls = 0

    def resolve(self, project_locator: str) -> ProjectScopeRef:
        self.calls += 1
        if project_locator != self.scope.project_key:
            raise LookupError("unknown project locator")
        return self.scope


def _load_rebuild_module():
    import sys

    spec = importlib.util.spec_from_file_location(
        "c9_projection_rebuild",
        _REBUILD_SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["c9_projection_rebuild"] = module
    spec.loader.exec_module(module)
    return module


def test_v2_external_command_dto_omits_authority_and_execution_fields() -> None:
    dto = _command_dto()
    assert set(dto.model_fields) == {
        "command_id",
        "command_kind",
        "project_locator",
        "trace_id",
        "payload",
        "expected_base_token",
        "approval_locator",
    }
    assert "actor" not in dto.model_fields
    assert "project_scope_ref" not in dto.model_fields
    assert "authority" not in dto.model_fields
    assert "execute" not in dto.model_fields
    assert "execution_mode" not in dto.model_fields
    assert dto.expected_base_token is None
    assert dto.approval_locator is None
    with pytest.raises(ValidationError):
        _command_dto(execute=True)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        _command_dto(actor_ref="actor:smuggled")  # type: ignore[call-arg]


def test_v2_external_query_dto_is_locator_only_and_read_only() -> None:
    dto = _query_dto()
    assert set(dto.model_fields) == {
        "query_id",
        "query_kind",
        "project_locator",
        "trace_id",
        "params",
    }
    assert "read_only" not in dto.model_fields
    assert "actor" not in dto.model_fields
    with pytest.raises(ValidationError):
        _query_dto(read_only=False)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        _query_dto(project_scope_ref="scope")  # type: ignore[call-arg]


def test_v2_discriminated_payload_must_match_kind() -> None:
    with pytest.raises(ValidationError):
        _command_dto(command_kind="invalidate_projection")


def test_v2_envelope_variant_rules_are_exact() -> None:
    meta = SuccessorRuntimeProjectionMetaV2DTO(
        project_key=SCOPE.project_key,
        trace_id=TRACE,
        projection_id="projection.run-summary.v1",
        project_scope_ref={
            "project_key": SCOPE.project_key,
            "resolved_schema": SCOPE.resolved_schema,
            "project_registry_revision": SCOPE.project_registry_revision,
            "incarnation": SCOPE.incarnation,
            "scope_digest": SCOPE.scope_digest,
        },
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
    )
    for status in ("ok", "waiting"):
        ok_envelope = SuccessorRuntimeEnvelopeV2DTO(
            status=status,
            data={"receipt_ref": "material-projection-receipt:1"},
            meta=meta,
        )
        assert ok_envelope.error is None
        with pytest.raises(ValidationError):
            SuccessorRuntimeEnvelopeV2DTO(status=status, meta=meta)
        with pytest.raises(ValidationError):
            SuccessorRuntimeEnvelopeV2DTO(
                status=status,
                data={},
                error={"code": "E", "message": "boom"},
                meta=meta,
            )
    for status in ("blocked", "unavailable", "conflict", "error"):
        error_envelope = SuccessorRuntimeEnvelopeV2DTO(
            status=status,
            error={"code": "E", "message": "boom"},
            meta=meta,
        )
        assert error_envelope.data is None
        with pytest.raises(ValidationError):
            SuccessorRuntimeEnvelopeV2DTO(status=status, meta=meta)
        with pytest.raises(ValidationError):
            SuccessorRuntimeEnvelopeV2DTO(
                status=status,
                data={},
                error={"code": "E", "message": "boom"},
                meta=meta,
            )
    assert tuple(API_STATUS_KINDS_V2) == (
        "ok",
        "waiting",
        "blocked",
        "unavailable",
        "conflict",
        "error",
    )
    assert tuple(API_STATUS_KINDS) == (
        "ok",
        "error",
        "unavailable",
        "blocked",
        "waiting",
    )


def test_facade_calls_submission_port_exactly_once_and_maps_receipts() -> None:
    port = CountingSubmissionPort()
    facade = SuccessorRuntimeFacade(
        submission_port=port, query_port=CountingQueryPort()
    )
    envelope = facade.submit(_command())
    assert port.calls == 1
    assert envelope.status == "waiting"
    assert envelope.data is not None
    assert envelope.data["receipt_ref"] == (
        "material-projection-receipt:idem:material-projections:cmd-v2-1"
    )
    assert envelope.error is None
    assert envelope.control_feedback is False
    assert validate_api_envelope_v2(envelope).valid

    terminal_port = CountingSubmissionPort(
        receipt=CommandReceipt(
            receipt_ref="material-projection-receipt:terminal",
            command_id="cmd-v2-1",
            request_digest="a" * 64,
            state="TERMINAL",
            idempotency_id="idem:material-projections:cmd-v2-1",
            logical_request_id="cmd-v2-1",
        )
    )
    facade = SuccessorRuntimeFacade(
        submission_port=terminal_port,
        query_port=CountingQueryPort(),
    )
    envelope = facade.submit(_command())
    assert terminal_port.calls == 1
    assert envelope.status == "ok"
    assert envelope.data["state"] == "TERMINAL"


def test_facade_terminal_replay_is_stable_and_started_never_claims_completion() -> None:
    started_port = CountingSubmissionPort()
    started_facade = SuccessorRuntimeFacade(
        submission_port=started_port,
        query_port=CountingQueryPort(),
    )

    started = started_facade.submit(_command())
    started_replay = started_facade.submit(_command())

    assert started_port.calls == 2
    assert started == started_replay
    assert started.status == "waiting"
    assert started.data is not None
    assert started.data["state"] == "STARTED"

    terminal_receipt = CommandReceipt(
        receipt_ref="material-projection-receipt:terminal-stable",
        command_id="cmd-v2-1",
        request_digest="a" * 64,
        state="TERMINAL",
        idempotency_id="idem:material-projections:cmd-v2-1",
        logical_request_id="cmd-v2-1",
        authority_context_digest="b" * 64,
        grant_epoch=7,
        grants_digest="c" * 64,
        observed_at="2030-09-01T08:00:00+00:00",
    )
    terminal_port = CountingSubmissionPort(receipt=terminal_receipt)
    terminal_facade = SuccessorRuntimeFacade(
        submission_port=terminal_port,
        query_port=CountingQueryPort(),
    )

    terminal = terminal_facade.submit(_command())
    terminal_replay = terminal_facade.submit(_command())

    assert terminal_port.calls == 2
    assert terminal == terminal_replay
    assert terminal.status == "ok"
    assert terminal.data is not None
    assert terminal.data["state"] == "TERMINAL"
    assert terminal.data["receipt_ref"] == terminal_receipt.receipt_ref
    assert terminal.data["observed_at"] == terminal_receipt.observed_at


def test_facade_calls_query_port_exactly_once() -> None:
    port = CountingQueryPort()
    facade = SuccessorRuntimeFacade(
        submission_port=CountingSubmissionPort(),
        query_port=port,
    )
    envelope = facade.query(_query())
    assert port.calls == 1
    assert envelope.status == "ok"
    assert envelope.data["projection_generation"] == 3
    assert envelope.meta.projection_revision == 3
    assert envelope.meta.source_digest == "c" * 64
    assert envelope.control_feedback is False


def _typed_projection_result() -> tuple[
    ProjectionResponseMetaV2, ProjectionSnapshotDataV2
]:
    meta = ProjectionResponseMetaV2(
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
        offset_revision=2,
        projection_revision=1,
        source_digest="c" * 64,
        cursor=4,
    )
    snapshot = ProjectionSnapshotDataV2(
        projection_id=PROJECTION_ID,
        projector_id=SOURCE_IDENTITY["projector_id"],
        projector_version=SOURCE_IDENTITY["projector_version"],
        source_kind=SOURCE_IDENTITY["source_kind"],
        source_ref=SOURCE_IDENTITY["source_ref"],
        source_incarnation=SOURCE_IDENTITY["source_incarnation"],
        projection_generation=1,
        offset_revision=2,
        projection_revision=1,
        source_digest="c" * 64,
        cursor=4,
        offset_ref=(
            f"value:{SCOPE.resolved_schema}:material-projection:generation:1:cc"
        ),
        candidate_values=(
            ProjectionCandidateValueV2(
                value_id="material-projection:knowledge:generation-1:dddddddddddd",
                value_ref=(
                    f"value:{SCOPE.resolved_schema}:material-projection:"
                    "knowledge:generation-1:dddddddddddd"
                ),
                content_digest="d" * 64,
                byte_size=10,
                sink="knowledge",
                payload={
                    "schema_version": "mrw.projection.knowledge-view.v2",
                    "sink": "knowledge",
                    "declared_losses": ["LOCAL_EXACT", "postgres readback"],
                },
            ),
        ),
    )
    return meta, snapshot


def test_projection_snapshot_data_serializes_all_fixed_fields() -> None:
    meta, snapshot = _typed_projection_result()
    assert validate_projection_snapshot_data_v2(snapshot, meta).valid
    port = CountingQueryPort(result=QueryResult(data=snapshot, meta=meta))
    facade = SuccessorRuntimeFacade(
        submission_port=CountingSubmissionPort(),
        query_port=port,
    )
    envelope = facade.query(_query())
    assert envelope.status == "ok"
    assert envelope.error is None
    dto = api_module._envelope_dto(envelope)
    dumped = dto.model_dump(mode="json")
    meta_fields = {
        "projector_id",
        "projector_version",
        "source_kind",
        "source_ref",
        "source_incarnation",
        "projection_generation",
        "offset_revision",
        "projection_revision",
        "source_digest",
        "cursor",
    }
    assert meta_fields.issubset(set(dumped["meta"]))
    assert dumped["meta"]["projector_id"] == SOURCE_IDENTITY["projector_id"]
    assert dumped["meta"]["source_ref"] == SOURCE_IDENTITY["source_ref"]
    assert dumped["meta"]["projection_generation"] == 1
    assert dumped["meta"]["offset_revision"] == 2
    assert dumped["data"]["projector_id"] == SOURCE_IDENTITY["projector_id"]
    assert dumped["data"]["source_ref"] == SOURCE_IDENTITY["source_ref"]
    assert dumped["data"]["projection_generation"] == 1
    assert dumped["data"]["offset_revision"] == 2
    assert dumped["data"]["projection_revision"] == 1
    assert dumped["data"]["source_digest"] == "c" * 64
    assert dumped["data"]["cursor"] == 4
    assert dumped["data"]["offset_ref"].startswith(f"value:{SCOPE.resolved_schema}:")
    candidate = dumped["data"]["candidate_values"][0]
    assert set(candidate) == {
        "value_id",
        "value_ref",
        "content_digest",
        "byte_size",
        "sink",
        "payload",
    }
    dto_meta = SuccessorRuntimeProjectionMetaV2DTO.model_validate(dumped["meta"])
    assert (
        dto_meta.model_dump(mode="json")["projector_id"]
        == SOURCE_IDENTITY["projector_id"]
    )


def test_projection_snapshot_meta_data_mismatch_fails_closed() -> None:
    meta, snapshot = _typed_projection_result()
    drifted = dataclasses.replace(snapshot, source_ref="c9:source-closure:drifted")
    port = CountingQueryPort(result=QueryResult(data=drifted, meta=meta))
    facade = SuccessorRuntimeFacade(
        submission_port=CountingSubmissionPort(),
        query_port=port,
    )
    envelope = facade.query(_query())
    assert port.calls == 1
    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "PROJECTION_META_DATA_MISMATCH"
    assert isinstance(envelope.meta, QueryMetaV2)


def test_facade_maps_conflict_blocked_unavailable_and_failures() -> None:
    for error, expected in (
        (C9CommandConflict("changed body"), "conflict"),
        (C9CommandBaseConflict("stale base"), "conflict"),
        (C9CommandBlocked("approval pending"), "blocked"),
        (C9Unavailable("store down"), "unavailable"),
        (RuntimeError("boom"), "error"),
    ):
        port = CountingSubmissionPort(error=error)
        facade = SuccessorRuntimeFacade(
            submission_port=port,
            query_port=CountingQueryPort(),
        )
        envelope = facade.submit(_command())
        assert port.calls == 1
        assert envelope.status == expected
        assert envelope.error is not None
        assert envelope.data is None
        assert validate_api_envelope_v2(envelope).valid

    base_port = CountingSubmissionPort(error=C9CommandBaseConflict("stale base"))
    facade = SuccessorRuntimeFacade(
        submission_port=base_port,
        query_port=CountingQueryPort(),
    )
    envelope = facade.submit(_command())
    assert envelope.status == "conflict"
    assert envelope.error is not None
    assert envelope.error.code == "COMMAND_BASE_CONFLICT"

    query_port = CountingQueryPort(error=C9Unavailable("offset missing"))
    facade = SuccessorRuntimeFacade(
        submission_port=CountingSubmissionPort(),
        query_port=query_port,
    )
    envelope = facade.query(_query())
    assert query_port.calls == 1
    assert envelope.status == "unavailable"
    assert envelope.error is not None
    assert envelope.meta.query_id == "query-v2-1"


def test_facade_rejects_invalid_command_without_calling_port() -> None:
    port = CountingSubmissionPort()
    facade = SuccessorRuntimeFacade(
        submission_port=port,
        query_port=CountingQueryPort(),
    )
    command = _command(execute=True)  # type: ignore[call-arg]
    envelope = facade.submit(command)
    assert port.calls == 0
    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "COMMAND_CONTRACT_VIOLATION"


def test_request_identity_binds_contract_scope_actor_command_and_payload() -> None:
    assert PROJECTION_REQUEST_IDENTITY_CONTRACT == "projection.request_identity.v2"
    base = derive_projection_request_identity(
        scope_digest=SCOPE.scope_digest,
        actor_ref=ACTOR,
        command_id="cmd-v2-1",
        command_kind="rebuild_projection",
        payload={"projection_id": "projection.run-summary.v1"},
        expected_base_token="generation:1|revision:1|incarnation:scope-inc-c9-v2",
        approval_locator="approval:c9:grant",
    )
    assert len(base) == 64
    assert base != derive_projection_request_identity(
        scope_digest="c" * 64,
        actor_ref=ACTOR,
        command_id="cmd-v2-1",
        command_kind="rebuild_projection",
        payload={"projection_id": "projection.run-summary.v1"},
        expected_base_token="generation:1|revision:1|incarnation:scope-inc-c9-v2",
        approval_locator="approval:c9:grant",
    )
    assert base != derive_projection_request_identity(
        scope_digest=SCOPE.scope_digest,
        actor_ref="actor:other",
        command_id="cmd-v2-1",
        command_kind="rebuild_projection",
        payload={"projection_id": "projection.run-summary.v1"},
        expected_base_token="generation:1|revision:1|incarnation:scope-inc-c9-v2",
        approval_locator="approval:c9:grant",
    )
    assert base != derive_projection_request_identity(
        scope_digest=SCOPE.scope_digest,
        actor_ref=ACTOR,
        command_id="cmd-v2-2",
        command_kind="rebuild_projection",
        payload={"projection_id": "projection.run-summary.v1"},
        expected_base_token="generation:1|revision:1|incarnation:scope-inc-c9-v2",
        approval_locator="approval:c9:grant",
    )
    assert base != derive_projection_request_identity(
        scope_digest=SCOPE.scope_digest,
        actor_ref=ACTOR,
        command_id="cmd-v2-1",
        command_kind="rebuild_projection",
        payload={"projection_id": "projection.run-summary.v1"},
        expected_base_token="generation:2|revision:1|incarnation:scope-inc-c9-v2",
        approval_locator="approval:c9:grant",
    )
    assert base != derive_projection_request_identity(
        scope_digest=SCOPE.scope_digest,
        actor_ref=ACTOR,
        command_id="cmd-v2-1",
        command_kind="rebuild_projection",
        payload={"projection_id": "projection.run-summary.v1"},
        expected_base_token="generation:1|revision:1|incarnation:scope-inc-c9-v2",
        approval_locator="approval:c9:other",
    )


def test_bind_server_command_binds_base_and_approval_into_digest() -> None:
    base = _command_dto(
        expected_base_token="generation:1|revision:1|incarnation:scope-inc-c9-v2",
        approval_locator="approval:c9:grant",
    )
    changed_base = _command_dto(
        expected_base_token="generation:2|revision:2|incarnation:scope-inc-c9-v2",
        approval_locator="approval:c9:grant",
    )
    changed_approval = _command_dto(
        expected_base_token="generation:1|revision:1|incarnation:scope-inc-c9-v2",
        approval_locator="approval:c9:other",
    )
    bound = api_module.bind_server_command(base, scope=SCOPE, actor_ref=ACTOR)
    bound_base = api_module.bind_server_command(
        changed_base, scope=SCOPE, actor_ref=ACTOR
    )
    bound_approval = api_module.bind_server_command(
        changed_approval, scope=SCOPE, actor_ref=ACTOR
    )
    assert bound.idempotency_key != bound_base.idempotency_key
    assert bound.idempotency_key != bound_approval.idempotency_key
    assert bound.expected_base_token == base.expected_base_token
    assert bound.approval_locator == base.approval_locator


def test_rollback_projection_dto_model_dump_frontend_fixture() -> None:
    payload = SuccessorRuntimeRollbackProjectionV2Payload(
        projection_id=PROJECTION_ID,
        **SOURCE_IDENTITY,
        target_generation=0,
        expected_active_generation=1,
        expected_offset_revision=2,
    )
    dto = _command_dto(command_kind="rollback_projection", payload=payload)
    dumped = dto.model_dump(mode="json")
    assert dumped["payload"]["payload_kind"] == "rollback_projection"
    assert dumped["payload"]["projection_id"] == PROJECTION_ID
    assert dumped["payload"]["target_generation"] == 0
    assert dumped["payload"]["expected_active_generation"] == 1
    assert dumped["payload"]["expected_offset_revision"] == 2
    for field in (
        "projector_id",
        "projector_version",
        "source_kind",
        "source_ref",
        "source_incarnation",
    ):
        assert dumped["payload"][field] == SOURCE_IDENTITY[field]
    bound = api_module.bind_server_command(dto, scope=SCOPE, actor_ref=ACTOR)
    assert bound.command_kind == "rollback_projection"
    assert bound.payload["target_generation"] == 0
    assert bound.payload["expected_active_generation"] == 1
    assert bound.payload["expected_offset_revision"] == 2
    facade = SuccessorRuntimeFacade(
        submission_port=CountingSubmissionPort(),
        query_port=CountingQueryPort(),
    )
    envelope = facade.submit(bound)
    assert envelope.status in {"ok", "waiting"}
    assert envelope.error is None


def test_rollback_receipt_wire_known_vector_and_model_dump() -> None:
    wire = {
        "contract": PROJECTION_ROLLBACK_TRANSITION_CONTRACT,
        "ref": "rollback:" + "a" * 64,
        "digest": "",
        "projection_id": PROJECTION_ID,
        "projector_id": SOURCE_IDENTITY["projector_id"],
        "projector_version": SOURCE_IDENTITY["projector_version"],
        "source_kind": SOURCE_IDENTITY["source_kind"],
        "source_ref": SOURCE_IDENTITY["source_ref"],
        "source_incarnation": SOURCE_IDENTITY["source_incarnation"],
        "from": {
            "projection_generation": 0,
            "offset_revision": 1,
            "projection_revision": 1,
            "source_digest": "c" * 64,
            "cursor": 4,
            "offset_ref": (
                f"value:{SCOPE.resolved_schema}:material-projection:"
                "generation:0:aa"
            ),
        },
        "to": {
            "projection_generation": 1,
            "offset_revision": 2,
            "projection_revision": 1,
            "source_digest": "c" * 64,
            "cursor": 4,
            "offset_ref": (
                f"value:{SCOPE.resolved_schema}:material-projection:"
                "generation:1:cc"
            ),
        },
        "generation_completeness_digest": "e" * 64,
    }
    content_without_digest = {
        key: value for key, value in wire.items() if key != "digest"
    }
    observed = hashlib.sha256(
        c9_canonical_json(content_without_digest).encode("utf-8")
    ).hexdigest()
    expected = "b398cf1cd88dc2de2076237728dc24203a03c31f8dcc9485541f15158204fddd"
    assert observed == expected
    receipt = ProjectionRollbackTransitionReceiptV2(
        ref=wire["ref"],
        digest=observed,
        projection_id=wire["projection_id"],
        projector_id=wire["projector_id"],
        projector_version=wire["projector_version"],
        source_kind=wire["source_kind"],
        source_ref=wire["source_ref"],
        source_incarnation=wire["source_incarnation"],
        from_position=RollbackPositionV1(**wire["from"]),
        to_position=RollbackPositionV1(**wire["to"]),
        generation_completeness_digest=wire["generation_completeness_digest"],
    )
    assert receipt.to_plain() == {**wire, "digest": observed}
    assert set(receipt.to_plain()) == set(wire)
    meta, snapshot = _typed_projection_result()
    snapshot = dataclasses.replace(
        snapshot,
        rollback_transition=receipt.to_plain(),
    )
    port = CountingQueryPort(result=QueryResult(data=snapshot, meta=meta))
    facade = SuccessorRuntimeFacade(
        submission_port=CountingSubmissionPort(),
        query_port=port,
    )
    envelope = facade.query(_query())
    assert envelope.status == "ok"
    dto = api_module._envelope_dto(envelope)
    dumped = dto.model_dump(mode="json")
    assert set(dumped["data"]["rollback_transition"]) == set(wire)


def test_facade_rejects_scope_actor_identity_mismatch_without_port_call() -> None:
    other_scope = ProjectScopeRef(
        project_key="p4-c9-other",
        resolved_schema="mrw_p4_c9_other",
        project_registry_revision=1,
        incarnation="scope-inc-c9-other",
        scope_digest="d" * 64,
    )
    submission = CountingSubmissionPort()
    query_port = CountingQueryPort()
    facade = SuccessorRuntimeFacade(
        submission_port=submission,
        query_port=query_port,
    )
    command = _command(project_scope_ref=other_scope)
    envelope = facade.submit(command)
    assert submission.calls == 0
    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "COMMAND_CONTRACT_VIOLATION"

    query = _query(actor_ref="")
    envelope = facade.query(query)
    assert query_port.calls == 0
    assert envelope.status == "error"
    assert envelope.error is not None
    assert envelope.error.code == "QUERY_CONTRACT_VIOLATION"


def test_api_router_factory_is_bounded_and_injects_dependencies() -> None:
    assert not hasattr(api_module, "router")
    resolver = StubResolver(SCOPE)
    submission = CountingSubmissionPort()
    facade = SuccessorRuntimeFacade(
        submission_port=submission,
        query_port=CountingQueryPort(),
    )
    router = api_module.create_successor_runtime_router(
        resolver=resolver,
        facade=facade,
        actor_provider=lambda request: ACTOR,
    )
    other_router = api_module.create_successor_runtime_router(
        resolver=resolver,
        facade=facade,
        actor_provider=lambda request: ACTOR,
    )
    assert router is not other_router
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        response = client.post(
            "/material-projections/v2/commands",
            json={
                "command_id": "cmd-v2-1",
                "command_kind": "rebuild_projection",
                "project_locator": SCOPE.project_key,
                "trace_id": TRACE,
                "payload": {
                    "payload_kind": "rebuild_projection",
                    "projection_id": PROJECTION_ID,
                    **SOURCE_IDENTITY,
                },
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "waiting"
        assert body["data"]["receipt_ref"] == (
            "material-projection-receipt:idem:material-projections:cmd-v2-1"
        )
        assert body["error"] is None
        assert body["meta"]["command_id"] == "cmd-v2-1"
        assert body["meta"]["project_scope_ref"]["scope_digest"] == SCOPE.scope_digest
        assert body["control_feedback"] is False
    assert resolver.calls == 1
    assert submission.calls == 1

    query_response = client.post(
        "/material-projections/v2/queries",
        json={
            "query_id": "query-v2-1",
            "query_kind": "projection_snapshot",
            "project_locator": SCOPE.project_key,
            "trace_id": TRACE,
            "params": {
                "params_kind": "projection_snapshot",
                "projection_id": PROJECTION_ID,
                **SOURCE_IDENTITY,
            },
        },
    )
    assert query_response.status_code == 200
    query_body = query_response.json()
    assert query_body["status"] == "ok"
    assert query_body["meta"]["projection_revision"] == 3


def test_api_resolver_and_actor_failures_return_typed_envelope_not_http_500() -> None:
    failing_resolver = StubResolver(SCOPE)

    def fail_actor(request: object) -> str:
        raise PermissionError("actor lookup failed")

    facade = SuccessorRuntimeFacade(
        submission_port=CountingSubmissionPort(),
        query_port=CountingQueryPort(),
    )
    app = FastAPI()
    app.include_router(
        api_module.create_successor_runtime_router(
            resolver=failing_resolver,
            facade=facade,
            actor_provider=lambda request: ACTOR,
        )
    )
    with TestClient(app) as client:
        response = client.post(
            "/material-projections/v2/commands",
            json={
                "command_id": "cmd-v2-resolve-fail",
                "command_kind": "rebuild_projection",
                "project_locator": "unknown-project",
                "trace_id": TRACE,
                "payload": {
                    "payload_kind": "rebuild_projection",
                    "projection_id": PROJECTION_ID,
                    **SOURCE_IDENTITY,
                },
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == "SCOPE_RESOLUTION_FAILED"
        assert body["meta"]["resolution_state"] == "UNRESOLVED"
        assert body["meta"]["request_id"] == "cmd-v2-resolve-fail"

    app = FastAPI()
    app.include_router(
        api_module.create_successor_runtime_router(
            resolver=StubResolver(SCOPE),
            facade=facade,
            actor_provider=fail_actor,
        )
    )
    with TestClient(app) as client:
        response = client.post(
            "/material-projections/v2/queries",
            json={
                "query_id": "query-v2-actor-fail",
                "query_kind": "projection_snapshot",
                "project_locator": SCOPE.project_key,
                "trace_id": TRACE,
                "params": {
                    "params_kind": "projection_snapshot",
                    "projection_id": PROJECTION_ID,
                    **SOURCE_IDENTITY,
                },
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "error"
        assert body["error"]["code"] == "ACTOR_RESOLUTION_FAILED"
        assert body["meta"]["resolution_state"] == "UNRESOLVED"


def test_api_envelope_dto_rejects_unknown_status() -> None:
    with pytest.raises(ValidationError):
        SuccessorRuntimeEnvelopeV2DTO(
            status="unknown",
            data={},
            meta=SuccessorRuntimeProjectionMetaV2DTO(
                project_key=SCOPE.project_key,
                trace_id=TRACE,
                projection_id="projection.run-summary.v1",
                project_scope_ref={
                    "project_key": SCOPE.project_key,
                    "resolved_schema": SCOPE.resolved_schema,
                    "project_registry_revision": SCOPE.project_registry_revision,
                    "incarnation": SCOPE.incarnation,
                    "scope_digest": SCOPE.scope_digest,
                },
                projector_id=SOURCE_IDENTITY["projector_id"],
                projector_version=SOURCE_IDENTITY["projector_version"],
                source_kind=SOURCE_IDENTITY["source_kind"],
                source_ref=SOURCE_IDENTITY["source_ref"],
                source_incarnation=SOURCE_IDENTITY["source_incarnation"],
                projection_generation=0,
                offset_revision=0,
                projection_revision=0,
                source_digest="c" * 64,
                cursor=0,
            ),
        )


def _canonical_closure() -> ProjectSourceClosure:
    session = TaskSource(
        schema_version=TASK_SOURCE_SCHEMA,
        project_scope_ref=SCOPE.project_key,
        session_ref="runtime-session:closure:001",
        revision="1",
        incarnation=SCOPE.incarnation,
        events=(
            TaskSourceEvent(
                schema_version=TASK_EVENT_SCHEMA,
                sequence=0,
                event_kind="SESSION_CREATED",
                event_ref="event:closure:001:created",
            ),
        ),
    )
    graph = KnowledgeSource(
        schema_version=KNOWLEDGE_SOURCE_SCHEMA,
        project_scope_ref=SCOPE.project_key,
        graph_ref="research-graph:closure:001",
        revision="1",
        incarnation=SCOPE.incarnation,
        objects=(
            KnowledgeObject(
                schema_version=KNOWLEDGE_OBJECT_SCHEMA,
                object_id="obj:closure:001",
                object_type="Market",
                label="market",
            ),
        ),
        relations=(),
    )
    search = MaterialSource(
        schema_version=MATERIAL_SOURCE_SCHEMA,
        project_scope_ref=SCOPE.project_key,
        search_ref="c7-search:closure:001",
        revision="1",
        incarnation=SCOPE.incarnation,
        segments=(
            MaterialSegment(
                schema_version=MATERIAL_SEGMENT_SCHEMA,
                segment_id="seg:closure:001",
                field_path="text",
                segment_text="robots",
            ),
        ),
        provider_status="NOT_EXECUTED",
        vectorization_status="NOT_EXECUTED",
    )
    return ProjectSourceClosure(
        schema_version=PROJECT_SOURCE_CLOSURE_SCHEMA,
        project_scope_ref=SCOPE.project_key,
        closure_id=f"projection:{SCOPE.project_key}:source",
        revision="1",
        incarnation=SCOPE.incarnation,
        runtime_session_source=session,
        research_graph_source=graph,
        c7_search_source=search,
    )


def test_rebuild_script_pure_surface_is_deterministic_and_loss_explicit() -> None:
    module = _load_rebuild_module()
    closure = _canonical_closure()
    plain_without_digest = {
        key: value
        for key, value in closure.to_plain().items()
        if key != "closure_digest"
    }
    assert c9_content_digest(plain_without_digest) == closure.closure_digest
    raw_bytes = c9_canonical_json(closure.to_plain()).encode("utf-8")
    assert (
        c9_content_digest(closure.to_plain()) == hashlib.sha256(raw_bytes).hexdigest()
    )
    first = module._payload_for_sink("knowledge", closure)
    expected = build_knowledge_view(
        closure.research_graph_source,
        declared_losses=module._projection_declared_losses("knowledge"),
    ).to_plain()
    assert first == expected
    assert first["project_scope_ref"] == SCOPE.project_key
    assert first["declared_losses"]
    assert first["coverage_incomplete_flags"][0].startswith("projection.")
    assert "coverage-incomplete" in first["coverage_incomplete_flags"][0]
    assert c9_content_digest(first) == c9_content_digest(expected)
    assert module.build_loss_profile("elasticsearch") == (
        "DECLARED_LOSS",
        "no provider call",
    )
    assert module.build_loss_profile("qdrant") == (
        "DECLARED_LOSS",
        "no provider call",
    )
    assert module.build_loss_profile("graph_provider") == (
        "DECLARED_LOSS",
        "no provider call",
    )
    assert module.build_loss_profile("knowledge") == (
        "LOCAL_EXACT",
        "postgres readback",
    )
    assert module.CANDIDATE_OBJECT_TYPES["knowledge"] == (
        "mrw.projection.knowledge-view.v2"
    )
    assert "graph_provider" in module.EXTERNAL_DECLARED_LOSS_SINKS
    assert "graph_provider" not in module.REQUIRED_LOCAL_SINKS
    value_id = module.candidate_value_id("knowledge", REBUILD_KEY, 1, "d" * 64)
    assert value_id.startswith("material-projection:knowledge:")
    assert "generation-1:" in value_id
    assert value_id.endswith(":" + "d" * 12)
    other_key = ProjectionOffsetKey(
        projector_id="projector:other",
        projector_version="2.0.0",
        source_kind="projection_source",
        source_ref="projection:other:source",
        source_incarnation=SCOPE.incarnation,
    )
    assert (
        module.candidate_value_id("knowledge", other_key, 1, "d" * 64)
        != value_id
    )
    source_rows = (
        {
            "value_id": "projection:source:knowledge:001",
            "object_type": KNOWLEDGE_SOURCE_SCHEMA,
            "content_digest": "e" * 64,
            "byte_size": 10,
            "revision": 1,
        },
    )
    assert module.source_closure_digest(
        f"projection:{SCOPE.project_key}:source", source_rows
    ) == module.source_closure_digest(
        f"projection:{SCOPE.project_key}:source", source_rows
    )
    assert module.source_closure_revision(source_rows) == 1
    assert (
        "required_sinks"
        not in module.PostgresC9ProjectionRebuilder.rebuild.__annotations__
    )
    assert (
        "rebuild_id" not in module.PostgresC9ProjectionRebuilder.rebuild.__annotations__
    )


def test_facade_module_never_imports_effects() -> None:
    import ast

    source = Path(facade_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(facade_module.__file__))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    forbidden = ("sqlalchemy", "fastapi", "starlette", "substrate", "provider")
    assert not any(
        name.split(".", 1)[0] in forbidden or any(part in name for part in forbidden)
        for name in imported
    )
