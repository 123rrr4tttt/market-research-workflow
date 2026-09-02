from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Self

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.first_specimen import (
    InternalExportInput,
    build_first_specimen_bundle,
)
from app.successor_runtime.language.object_contracts import (
    build_first_specimen_return_contract_registry,
)
from app.successor_runtime.research.artifacts import (
    DELIVERY_CHANNEL,
    DELIVERY_FORMAT,
    DELIVERY_IRREVERSIBILITY_PROFILE,
    DeliveryIntent,
    ResearchArtifact,
    artifact_exact_ref,
)
from app.successor_runtime.runtime.assignments import (
    AssignmentKind,
    CompiledStepRole,
    HandlerBindingKind,
    InterpreterBinding,
    ReturnContractBinding,
    RuntimeAssignment,
    canonical_digest,
)
from app.successor_runtime.runtime.claims import ClaimBinding
from app.successor_runtime.runtime.node import (
    DefiniteInterpreterFailure,
    NodeIdentity,
    RuntimeExecutionContext,
)
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.runtime.transitions import EffectDisposition
from app.successor_runtime.substrate.blob.internal_export import (
    InternalExportInterpreter,
    InternalExportRequest,
)
from app.successor_runtime.substrate.blob.store import ProjectBlobStore
from app.successor_runtime.substrate.postgres.first_specimen_delivery_handler import (
    FirstSpecimenDeliveryEffectStore,
    FirstSpecimenDeliveryReplay,
    InstalledFirstSpecimenDeliveryHandler,
    PostgresFirstSpecimenDeliveryHandler,
    _require_semantic_closure,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_METADATA,
    PUBLIC_TABLES,
    project_tables,
)
from app.successor_runtime.substrate.postgres.runtime_journal import (
    ExactBindingConflict,
)
from app.successor_runtime.substrate.postgres.session import compute_scope_digest

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)
PROJECT_KEY = "alpha"
PROJECT_SCHEMA = "project_alpha"
SCOPE_DIGEST = compute_scope_digest(PROJECT_KEY, PROJECT_SCHEMA, 1, "scope-inc-1")


@compiles(JSONB, "sqlite")
def _sqlite_jsonb(_type: object, _compiler: object, **_kw: object) -> str:
    return "JSON"


def _digest(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode()
    return hashlib.sha256(value).hexdigest()


class _CountingBlobStore(ProjectBlobStore):
    def __init__(self, root: Any) -> None:
        super().__init__(root, fsync=False)
        self.store_calls = 0

    def store(self, scope: object, data: bytes):  # type: ignore[override]
        self.store_calls += 1
        return super().store(scope, data)  # type: ignore[arg-type]


class _ApprovalReader:
    def __init__(self, intent: DeliveryIntent, *, current: bool = True) -> None:
        self.intent = intent
        self.current = current
        self.calls = 0

    def require_current(self, approval_id: str, **expected: object) -> object:
        self.calls += 1
        assert approval_id in self.intent.approval_refs
        if not self.current or expected["authority_digest"] != self.intent.authority_digest:
            raise ExactBindingConflict("approval/authority drift")
        assert expected["payload_digest"] == self.intent.content_digest
        return object()


class _Uow:
    def __init__(self, connection: sa.Connection, *, fail_commit: bool = False) -> None:
        self.connection = connection
        self.fail_commit = fail_commit
        self.transaction: Any = None

    def __enter__(self) -> Self:
        self.transaction = self.connection.begin()
        return self

    def commit(self) -> None:
        if self.fail_commit:
            self.transaction.rollback()
            raise RuntimeError("simulated receipt-event crash")
        self.transaction.commit()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.transaction.is_active:
            self.transaction.rollback()


class _Replay:
    def __init__(self, replay: FirstSpecimenDeliveryReplay) -> None:
        self.replay = replay
        self.loads = 0

    def load_exact(self, *_args: object) -> FirstSpecimenDeliveryReplay:
        self.loads += 1
        _require_semantic_closure(
            self.replay.payload,
            self.replay.delivery_intent,
            self.replay.artifact,
            self.replay.artifact_bytes,
        )
        return self.replay


@pytest.fixture
def delivery_db():
    engine = sa.create_engine("sqlite://")
    connection = engine.connect()
    connection.connection.create_function(
        "num_nonnulls", -1, lambda *values: sum(value is not None for value in values)
    )
    connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS public")
    connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS project_alpha")
    tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)
    tables.successor_values.create(connection)
    PUBLIC_METADATA.create_all(
        connection,
        tables=[
            PUBLIC_TABLES["runtime_values"],
            PUBLIC_TABLES["runtime_staged_artifacts"],
        ],
    )
    connection.commit()
    scope = RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key=PROJECT_KEY,
            resolved_schema=PROJECT_SCHEMA,
            project_registry_revision=1,
            incarnation="scope-inc-1",
            scope_digest=SCOPE_DIGEST,
        ),
        actor_id="runtime-node-a",
    )
    try:
        yield connection, tables, scope
    finally:
        connection.close()
        engine.dispose()


def _assignment() -> tuple[
    InstalledFirstSpecimenDeliveryHandler,
    RuntimeAssignment,
    ClaimBinding,
    RuntimeExecutionContext,
]:
    operation = build_first_specimen_bundle().operation_by_kind(
        "delivery.internal_export.v1"
    )
    deployment = _digest("deployment")
    profile = _digest("delivery-profile")
    authority = _digest("delivery-authority")
    binding = InterpreterBinding.from_content(
        operation_contract_digest=operation.ref.contract_digest,
        interpreter_profile_digest=profile,
        deployment_catalog_digest=deployment,
        runtime_protocol_version="1",
        project_scope_digest=SCOPE_DIGEST,
        resource_policy_epoch=2,
        authority_requirement_digest=authority,
    )
    installation = InstalledFirstSpecimenDeliveryHandler.bind(
        handler_binding_digest=binding.binding_digest,
        interpreter_profile_digest=profile,
    )
    returns = build_first_specimen_return_contract_registry().resolve_required(
        operation.return_contract_ref
    )
    input_refs = (
        "project-value:artifact:metadata",
        "project-value:delivery:intent",
    )
    assignment = RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work:delivery",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key=PROJECT_KEY,
        run_id="run:delivery",
        step_id="step:delivery",
        step_role=CompiledStepRole.EFFECT,
        capability_id=operation.owner_capability_id,
        operation_contract_ref=operation.ref,
        operation_contract_digest=operation.ref.contract_digest,
        return_contract_binding=ReturnContractBinding.from_contract(
            operation.return_contract_ref, returns
        ),
        handler_binding_kind=HandlerBindingKind.INTERPRETER,
        handler_binding_ref=f"handler-binding:sha256:{binding.binding_digest}",
        handler_binding_digest=binding.binding_digest,
        handler_binding=binding,
        program_digest=_digest("program"),
        plan_digest=_digest("plan"),
        deployment_catalog_digest=deployment,
        execution_epoch=0,
        incarnation="run-inc-1",
        input_refs=input_refs,
        input_closure_digest=canonical_digest(input_refs),
        payload_ref="project-value:delivery:intent:payload:delivery.internal_export",
        payload_digest=_digest("dynamic-typed-payload-bytes"),
        queue_eligibility_digest=_digest("delivery-eligibility"),
        resource_policy_epoch=2,
        claim_authority_epoch=5,
        claim_policy_digest=_digest("claim-policy"),
        expected_step_revision=2,
        trace_id="trace:delivery",
    )
    claim = ClaimBinding.bind(
        assignment,
        authorization_digest=_digest("authorization"),
        lease_token="lease:delivery",
        lease_expires_at=NOW + timedelta(minutes=5),
        node_id="runtime-node-a",
        node_profile_digest=_digest("node-profile"),
        interpreter_profile_digest=profile,
        authority_digest=_digest("claim-authority-context"),
        execution_reservation_ref="reservation:delivery",
        execution_reservation_digest=_digest("reservation"),
    )
    context = RuntimeExecutionContext(
        node=NodeIdentity(
            node_id="runtime-node-a",
            incarnation="runtime-node-a:inc-1",
            started_at=NOW - timedelta(minutes=1),
        ),
        observed_at=NOW,
    )
    return installation, assignment, claim, context


def _replay(scope: RuntimeScope, tables: Any, assignment: RuntimeAssignment):
    artifact_bytes = b"# Exact admitted artifact\n"
    artifact = ResearchArtifact(
        artifact_id="artifact:first-specimen",
        content_ref=f"sha256:{_digest(artifact_bytes)}",
        content_digest=None,
        claim_closure=("claim:1",),
        evidence_relation_closure=("qualification:1",),
        citation_closure=("material:1",),
        format="markdown",
        revision=1,
        # The canonical ResearchObjectRef is ADMITTED; the immutable semantic
        # artifact bytes retain their original DRAFT lifecycle field.
        lifecycle_state="DRAFT",
    )
    assert isinstance(assignment.handler_binding, InterpreterBinding)
    intent = DeliveryIntent(
        delivery_intent_id="delivery-intent:first-specimen",
        artifact_ref=artifact_exact_ref(artifact),
        audience="internal-research-review",
        channel=DELIVERY_CHANNEL,
        format=DELIVERY_FORMAT,
        approval_refs=("approval:human:1",),
        authority_digest=assignment.handler_binding.authority_requirement_digest,
        idempotency_key="delivery:first-specimen:internal-only",
        irreversibility_profile=DELIVERY_IRREVERSIBILITY_PROFILE,
    )
    payload_fields = {
        "delivery_intent_id": intent.delivery_intent_id,
        "artifact_ref": intent.artifact_ref,
        "audience": intent.audience,
        "approval_refs": intent.approval_refs,
        "idempotency_key": intent.idempotency_key,
    }
    payload = InternalExportInput(
        **payload_fields,
        payload_digest=content_digest(payload_fields),
    )
    assert intent.content_digest is not None
    request = InternalExportRequest(
        project_key=PROJECT_KEY,
        project_scope_digest=SCOPE_DIGEST,
        run_id=assignment.run_id,
        step_id=assignment.step_id or "",
        attempt_id=_digest("attempt"),
        assignment_digest=assignment.assignment_digest,
        operation_contract_ref=assignment.operation_contract_ref,
        handler_binding_digest=assignment.handler_binding_digest,
        delivery_intent=intent,
        artifact_bytes=artifact_bytes,
        artifact_digest=_digest(artifact_bytes),
        payload_digest=intent.content_digest,
    )
    approvals = _ApprovalReader(intent)
    return FirstSpecimenDeliveryReplay(
        scope=scope,
        tables=tables,
        payload=payload,
        delivery_intent=intent,
        artifact=artifact,
        artifact_bytes=artifact_bytes,
        request=request,
        approvals=approvals,  # type: ignore[arg-type]
    ), approvals


def test_dynamic_payload_executes_internal_only_and_stages_receipt(
    delivery_db, tmp_path
) -> None:
    connection, tables, scope = delivery_db
    installation, assignment, claim, context = _assignment()
    replay, approvals = _replay(scope, tables, assignment)
    store = _CountingBlobStore(tmp_path)
    effect = FirstSpecimenDeliveryEffectStore(
        lambda: _Uow(connection),
        replay=_Replay(replay),
        interpreter=InternalExportInterpreter(
            operation_contract_ref=assignment.operation_contract_ref,
            blob_store=store,
        ),
    )

    outcome = PostgresFirstSpecimenDeliveryHandler(
        installation, effect
    ).execute(assignment, claim, context)

    assert outcome.disposition is EffectDisposition.SUCCEEDED
    assert outcome.receipt_ref is not None
    assert store.store_calls == 1
    assert approvals.calls == 1
    project_rows = connection.execute(
        sa.select(tables.successor_values)
    ).mappings().all()
    assert len(project_rows) == 2
    project = next(
        row
        for row in project_rows
        if row["object_type"] == "DeliveryReceiptRef.v1"
    )
    provider_body = next(
        row
        for row in project_rows
        if row["object_type"] == "InternalExportProviderReceipt.v1"
    )
    public = connection.execute(
        sa.select(PUBLIC_TABLES["runtime_values"])
    ).mappings().one()
    staged = connection.execute(
        sa.select(PUBLIC_TABLES["runtime_staged_artifacts"])
    ).mappings().one()
    assert project["object_type"] == "DeliveryReceiptRef.v1"
    provider_exact = bytes(provider_body["content_bytes"])
    provider_json = json.loads(provider_exact)
    assert hashlib.sha256(provider_exact).hexdigest() == provider_body["content_digest"]
    assert provider_body["content_digest"] == project["write_receipt_digest"]
    assert provider_json == {
        "schema_version": "mrw.internal-export.receipt.v1",
        "delivery_intent_ref": replay.delivery_intent.delivery_intent_id,
        "attempt_ref": replay.request.attempt_id,
        "provider_locator": project["provenance_json"]["provider_locator"],
        "artifact_digest": replay.request.artifact_digest,
        "request_digest": replay.request.request_digest,
        "outcome_time": "2026-08-31T08:00:00+00:00",
    }
    assert project["provenance_json"]["provider_receipt_content_ref"] == (
        f"project-value:{provider_body['value_id']}"
    )
    assert project["provenance_json"]["provider_receipt_content_digest"] == (
        provider_body["content_digest"]
    )
    assert public["project_value_ref"] == f"project-value:{project['value_id']}"
    assert public["value_id"] != provider_body["value_id"]
    assert public["write_receipt_digest"] == project["write_receipt_digest"]
    assert staged["state"] == "STAGED"
    assert staged["receipt_ref"] == outcome.receipt_ref
    assert staged["attempt_id"] == claim.attempt_id
    assert "http" not in str(project["provenance_json"]["provider_locator"])


def test_cw10_commit_crash_reads_marker_without_duplicate_export(
    delivery_db, tmp_path
) -> None:
    connection, tables, scope = delivery_db
    installation, assignment, claim, context = _assignment()
    replay, _ = _replay(scope, tables, assignment)
    blob = _CountingBlobStore(tmp_path)
    interpreter = InternalExportInterpreter(
        operation_contract_ref=assignment.operation_contract_ref,
        blob_store=blob,
    )
    failed = FirstSpecimenDeliveryEffectStore(
        lambda: _Uow(connection, fail_commit=True),
        replay=_Replay(replay),
        interpreter=interpreter,
    )
    first = PostgresFirstSpecimenDeliveryHandler(
        installation, failed
    ).execute(assignment, claim, context)
    assert first.disposition is EffectDisposition.OUTCOME_UNKNOWN
    assert blob.store_calls == 1
    assert connection.scalar(
        sa.select(sa.func.count()).select_from(tables.successor_values)
    ) == 0
    connection.rollback()

    recovered = FirstSpecimenDeliveryEffectStore(
        lambda: _Uow(connection),
        replay=_Replay(replay),
        interpreter=interpreter,
    )
    second = PostgresFirstSpecimenDeliveryHandler(
        installation, recovered
    ).execute(assignment, claim, context)
    assert second.disposition is EffectDisposition.SUCCEEDED
    assert blob.store_calls == 1


def test_approval_drift_fails_before_export(delivery_db, tmp_path) -> None:
    connection, tables, scope = delivery_db
    installation, assignment, claim, context = _assignment()
    replay, approvals = _replay(scope, tables, assignment)
    approvals.current = False
    blob = _CountingBlobStore(tmp_path)
    effect = FirstSpecimenDeliveryEffectStore(
        lambda: _Uow(connection),
        replay=_Replay(replay),
        interpreter=InternalExportInterpreter(
            operation_contract_ref=assignment.operation_contract_ref,
            blob_store=blob,
        ),
    )
    with pytest.raises(DefiniteInterpreterFailure):
        PostgresFirstSpecimenDeliveryHandler(
            installation, effect
        ).execute(assignment, claim, context)
    assert blob.store_calls == 0


def test_base_artifact_and_exact_handler_drift_fail_closed(
    delivery_db, tmp_path
) -> None:
    connection, tables, scope = delivery_db
    installation, assignment, claim, context = _assignment()
    replay, _ = _replay(scope, tables, assignment)
    drifted_artifact = ResearchArtifact(
        artifact_id=replay.artifact.artifact_id,
        content_ref=replay.artifact.content_ref,
        content_digest=None,
        claim_closure=replay.artifact.claim_closure,
        evidence_relation_closure=replay.artifact.evidence_relation_closure,
        citation_closure=replay.artifact.citation_closure,
        format="markdown",
        revision=2,
        lifecycle_state="ADMITTED",
    )
    replay = FirstSpecimenDeliveryReplay(
        scope=replay.scope,
        tables=replay.tables,
        payload=replay.payload,
        delivery_intent=replay.delivery_intent,
        artifact=drifted_artifact,
        artifact_bytes=replay.artifact_bytes,
        request=replay.request,
        approvals=replay.approvals,
    )
    blob = _CountingBlobStore(tmp_path)
    effect = FirstSpecimenDeliveryEffectStore(
        lambda: _Uow(connection),
        replay=_Replay(replay),
        interpreter=InternalExportInterpreter(
            operation_contract_ref=assignment.operation_contract_ref,
            blob_store=blob,
        ),
    )
    with pytest.raises(DefiniteInterpreterFailure):
        PostgresFirstSpecimenDeliveryHandler(
            installation, effect
        ).execute(assignment, claim, context)
    assert blob.store_calls == 0

    wrong_installation = InstalledFirstSpecimenDeliveryHandler.bind(
        handler_binding_digest=_digest("wrong-handler"),
        interpreter_profile_digest=installation.interpreter_profile_digest,
    )
    with pytest.raises(DefiniteInterpreterFailure):
        PostgresFirstSpecimenDeliveryHandler(
            wrong_installation, effect
        ).execute(assignment, claim, context)
    assert blob.store_calls == 0
