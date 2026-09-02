from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Self

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.first_specimen import (
    CaptureDocumentSnapshotInput,
    ClaimOrGapInput,
    EvidenceQualificationInput,
    MarkdownComposeInput,
    build_first_specimen_bundle,
)
from app.successor_runtime.language.algebra import ValueRef
from app.successor_runtime.language.object_contracts import (
    build_first_specimen_return_contract_registry,
)
from app.successor_runtime.research.claims import Claim
from app.successor_runtime.research.codec import (
    canonical_bytes,
    dataclass_to_json,
    sha256_hex,
)
from app.successor_runtime.research.evidence import EvidenceQualification, Validity
from app.successor_runtime.research.materials import (
    CapturedMaterialSnapshot,
    MaterialRef,
)
from app.successor_runtime.research.object_types import (
    CLAIM_TYPE,
    EVIDENCE_QUALIFICATION_TYPE,
    MATERIAL_REF_TYPE,
    SOURCE_REF_TYPE,
    ObjectType,
)
from app.successor_runtime.research.sources import SourceRef
from app.successor_runtime.runtime.activation import ReadyActivation
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
from app.successor_runtime.substrate.postgres.first_specimen_handlers import (
    FirstSpecimenEffectOutputStore,
    FirstSpecimenEffectReplay,
    FirstSpecimenReplayDrift,
    InstalledFirstSpecimenEffectHandler,
    PostgresFirstSpecimenEffectHandler,
    ReplayedProjectValue,
    require_exact_activation_binding,
)
from app.successor_runtime.substrate.postgres.models import (
    PUBLIC_METADATA,
    PUBLIC_TABLES,
    project_tables,
)
from app.successor_runtime.substrate.postgres.session import compute_scope_digest
from app.successor_runtime.substrate.postgres.values import ValueRepository

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 31, 4, 0, tzinfo=UTC)
PROJECT_KEY = "alpha"
PROJECT_SCHEMA = "project_alpha"
SCOPE_INCARNATION = "scope-inc-3"
SCOPE_DIGEST = compute_scope_digest(
    PROJECT_KEY,
    PROJECT_SCHEMA,
    3,
    SCOPE_INCARNATION,
)


@compiles(JSONB, "sqlite")
def _sqlite_jsonb(_type: object, _compiler: object, **_kw: object) -> str:
    return "JSON"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _scope() -> RuntimeScope:
    return RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key=PROJECT_KEY,
            resolved_schema=PROJECT_SCHEMA,
            project_registry_revision=3,
            incarnation=SCOPE_INCARNATION,
            scope_digest=SCOPE_DIGEST,
        ),
        actor_id="runtime-node-a",
    )


@pytest.fixture
def handler_db():
    engine = sa.create_engine("sqlite://")
    connection = engine.connect()
    connection.connection.create_function(
        "num_nonnulls",
        -1,
        lambda *values: sum(value is not None for value in values),
    )
    connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS public")
    connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS project_alpha")
    tables = project_tables(sa.MetaData(), PROJECT_SCHEMA)
    tables.research_objects.create(connection)
    tables.research_relations.create(connection)
    tables.successor_values.create(connection)
    PUBLIC_METADATA.create_all(
        connection,
        tables=[
            PUBLIC_TABLES["runtime_values"],
            PUBLIC_TABLES["runtime_staged_artifacts"],
        ],
    )
    connection.commit()
    try:
        yield connection, tables, _scope()
    finally:
        connection.close()
        engine.dispose()


class _Uow:
    def __init__(self, connection: sa.Connection) -> None:
        self.connection = connection
        self.transaction: Any = None

    def __enter__(self) -> Self:
        self.transaction = self.connection.begin()
        return self

    def commit(self) -> None:
        self.transaction.commit()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.transaction.is_active:
            self.transaction.rollback()


@dataclass
class _Replay:
    scope: RuntimeScope
    tables: Any
    payload: object
    payload_value: ReplayedProjectValue
    inputs: tuple[ReplayedProjectValue, ...]
    loads: int = 0

    def resolve_scope(
        self,
        _connection: sa.Connection,
        _assignment: RuntimeAssignment,
        *,
        actor_id: str,
    ) -> tuple[RuntimeScope, Any]:
        assert actor_id == "runtime-node-a"
        return self.scope, self.tables

    def load_exact(
        self,
        _connection: sa.Connection,
        _installation: InstalledFirstSpecimenEffectHandler,
        _assignment: RuntimeAssignment,
        _scope: RuntimeScope,
        _tables: Any,
    ) -> FirstSpecimenEffectReplay:
        self.loads += 1
        return FirstSpecimenEffectReplay(
            scope=self.scope,
            tables=self.tables,
            payload=self.payload,
            payload_value=self.payload_value,
            inputs=self.inputs,
        )


def _value(
    *,
    value_id: str,
    object_type: ObjectType,
    codec_id: str,
    exact: bytes,
    provenance: dict[str, object],
) -> ReplayedProjectValue:
    ref = ValueRef(
        value_id=value_id,
        project_key=PROJECT_KEY,
        object_type=object_type,
        codec_id=codec_id,
        content_digest=hashlib.sha256(exact).hexdigest(),
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(exact),
        provenance_digest=sha256_hex(provenance),
    )
    return ReplayedProjectValue(ref=ref, exact_bytes=exact, provenance=provenance)


def _typed_payload_value(kind: str, operation_id: str, payload: object) -> ReplayedProjectValue:
    codec = build_first_specimen_bundle().codec_by_kind(kind)
    exact = canonical_bytes(codec.encode_payload(payload))
    return _value(
        value_id=f"submission:payload:{operation_id}",
        object_type=ObjectType(
            codec.payload_type_id,
            schema_version=codec.codec_version,
            codec_id=codec.codec_id,
            canonical_codec_version=codec.codec_version,
        ),
        codec_id=codec.codec_id,
        exact=exact,
        provenance={
            "operation_kind": kind,
            "codec_id": codec.codec_id,
            "codec_digest": codec.codec_digest,
        },
    )


def _semantic_assignment(
    *,
    kind: str,
    operation_id: str,
    step_id: str,
    inputs: tuple[ReplayedProjectValue, ...],
    payload_value: ReplayedProjectValue,
    scope: RuntimeScope,
) -> tuple[
    InstalledFirstSpecimenEffectHandler,
    RuntimeAssignment,
    ClaimBinding,
    RuntimeExecutionContext,
]:
    operation = build_first_specimen_bundle().operation_by_kind(kind)
    deployment = _digest("deployment")
    profile = _digest(f"profile:{kind}")
    binding = InterpreterBinding.from_content(
        operation_contract_digest=operation.ref.contract_digest,
        interpreter_profile_digest=profile,
        deployment_catalog_digest=deployment,
        runtime_protocol_version="1",
        project_scope_digest=scope.project_scope.scope_digest,
        resource_policy_epoch=2,
        authority_requirement_digest=_digest(f"authority:{kind}"),
    )
    installation = InstalledFirstSpecimenEffectHandler.bind(
        operation_kind=kind,
        handler_binding_digest=binding.binding_digest,
        interpreter_profile_digest=profile,
    )
    input_refs = tuple(value.ref.storage_ref for value in inputs)
    returns = build_first_specimen_return_contract_registry().resolve_required(
        operation.return_contract_ref
    )
    assignment = RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id=f"work:{step_id}",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key=PROJECT_KEY,
        run_id="run-1",
        step_id=step_id,
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
        payload_ref=payload_value.ref.storage_ref,
        payload_digest=payload_value.ref.content_digest,
        queue_eligibility_digest=_digest(f"eligibility:{kind}"),
        resource_policy_epoch=2,
        claim_authority_epoch=7,
        claim_policy_digest=_digest("claim-policy"),
        expected_step_revision=0,
        trace_id=f"trace:{step_id}",
    )
    claim = ClaimBinding.bind(
        assignment,
        authorization_digest=_digest(f"authorization:{kind}"),
        lease_token=f"lease:{step_id}",
        lease_expires_at=NOW + timedelta(minutes=5),
        node_id="runtime-node-a",
        node_profile_digest=_digest("node-profile"),
        interpreter_profile_digest=profile,
        authority_digest=_digest("authority"),
        execution_reservation_ref=f"reservation:{step_id}",
        execution_reservation_digest=_digest(f"reservation:{step_id}"),
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


def _qualification_value(
    label: str,
    direction: str,
    material: MaterialRef,
) -> tuple[EvidenceQualification, ReplayedProjectValue]:
    qualification = EvidenceQualification(
        qualification_id=f"qualification:run-1:{label}",
        project_key=PROJECT_KEY,
        material_ref=material.material_ref_id,
        inquiry_ref="inquiry:run-1",
        claim_ref=None,
        direction=direction,
        scope_statement_ref=f"scope-statement:run-1:{label}",
        uncertainty_profile_ref="uncertainty:first-specimen:explicit",
        verifier_profile_ref="verifier:first-specimen:deterministic",
        provenance_closure_digest=_digest(f"provenance:{label}"),
        validity=Validity(NOW, None),
        observed_at=NOW,
    )
    exact = canonical_bytes(
        dataclass_to_json(qualification, ("qualification_digest",))
    )
    return qualification, _value(
        value_id=qualification.qualification_id,
        object_type=EVIDENCE_QUALIFICATION_TYPE,
        codec_id=EVIDENCE_QUALIFICATION_TYPE.codec_id,
        exact=exact,
        provenance={"semantic_object_id": qualification.qualification_id},
    )


def _insert_qualification_relation(
    connection: sa.Connection,
    tables: Any,
    qualification: EvidenceQualification,
) -> None:
    def endpoint(object_id: str) -> str:
        return json.dumps(
            {
                "object_id": object_id,
                "object_type": "MaterialRef.v1"
                if object_id == qualification.material_ref
                else "Inquiry.v1",
                "project_key": qualification.project_key,
                "revision": 1,
                "incarnation": f"inc:{object_id}",
                "owner_binding_ref": "test-owner",
                "content_ref": f"project-value:{object_id}",
                "content_digest": _digest(f"content:{object_id}"),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    connection.execute(
        sa.insert(tables.research_relations).values(
            project_key=qualification.project_key,
            relation_id=qualification.qualification_id,
            relation_type={
                "SUPPORTS": "supports",
                "CONTRADICTS": "contradicts",
                "CONTEXT": "derived_from",
                "INSUFFICIENT": "opens",
            }[qualification.direction],
            source_object_ref=endpoint(qualification.material_ref),
            target_object_ref=endpoint(qualification.inquiry_ref),
            direction=qualification.direction,
            scope_ref=qualification.scope_statement_ref,
            uncertainty_profile_ref=qualification.uncertainty_profile_ref,
            validity_json={
                "valid_from": qualification.validity.valid_from.isoformat()
                if qualification.validity.valid_from
                else None,
                "valid_to": qualification.validity.valid_to.isoformat()
                if qualification.validity.valid_to
                else None,
                "source_time": qualification.source_time.isoformat()
                if qualification.source_time
                else None,
                "observed_at": qualification.observed_at.isoformat()
                if qualification.observed_at
                else None,
                "claim_ref": qualification.claim_ref,
                "verifier_profile_ref": qualification.verifier_profile_ref,
            },
            provenance_closure_digest=qualification.provenance_closure_digest,
            revision=qualification.revision,
            incarnation=qualification.incarnation,
            state=qualification.state,
            created_at=NOW,
            updated_at=NOW,
        )
    )


def _qualification_specimen(
    connection: sa.Connection,
    tables: Any,
    scope: RuntimeScope,
) -> tuple[
    InstalledFirstSpecimenEffectHandler,
    RuntimeAssignment,
    ClaimBinding,
    RuntimeExecutionContext,
    _Replay,
]:
    bundle = build_first_specimen_bundle()
    operation = bundle.operation_by_kind("evidence.qualify.v1")
    codec = bundle.codec_by_kind("evidence.qualify.v1")
    deployment = _digest("deployment")
    profile = _digest("qualification-interpreter-profile")
    binding = InterpreterBinding.from_content(
        operation_contract_digest=operation.ref.contract_digest,
        interpreter_profile_digest=profile,
        deployment_catalog_digest=deployment,
        runtime_protocol_version="1",
        project_scope_digest=scope.project_scope.scope_digest,
        resource_policy_epoch=2,
        authority_requirement_digest=_digest("authority-requirement"),
    )
    installation = InstalledFirstSpecimenEffectHandler.bind(
        operation_kind="evidence.qualify.v1",
        handler_binding_digest=binding.binding_digest,
        interpreter_profile_digest=profile,
    )
    snapshot = CapturedMaterialSnapshot(
        value_ref="project-value:submission:snapshot:a",
        document_id=101,
        observed_text_hash=_digest("captured-document"),
        observed_updated_at=NOW,
        byte_size=17,
    )
    material = MaterialRef(
        material_ref_id="material:alpha:a",
        source_ref="source:document:101",
        snapshot=snapshot,
    )
    material_provenance = {"source": material.source_ref, "submission": "sub-1"}
    material_value = _value(
        value_id=material.material_ref_id,
        object_type=MATERIAL_REF_TYPE,
        codec_id=MATERIAL_REF_TYPE.codec_id,
        exact=canonical_bytes(material),
        provenance=material_provenance,
    )
    payload_fields = {
        "qualification_id": "qualification:run-1:a",
        "material_ref": material.material_ref_id,
        "inquiry_ref": "inquiry:run-1",
        "direction": "SUPPORTS",
        "scope_statement_ref": "scope-statement:run-1:a",
        "uncertainty_profile_ref": "uncertainty:first-specimen:explicit",
        "verifier_profile_ref": "verifier:first-specimen:deterministic",
    }
    payload = EvidenceQualificationInput(
        **payload_fields,
        payload_digest=content_digest(payload_fields),
    )
    encoded = canonical_bytes(codec.encode_payload(payload))
    payload_provenance = {
        "operation_kind": "evidence.qualify.v1",
        "codec_id": codec.codec_id,
        "codec_digest": codec.codec_digest,
    }
    payload_value = _value(
        value_id="submission:payload:qualify:a",
        object_type=ObjectType(
            codec.payload_type_id,
            schema_version=codec.codec_version,
            codec_id=codec.codec_id,
            canonical_codec_version=codec.codec_version,
        ),
        codec_id=codec.codec_id,
        exact=encoded,
        provenance=payload_provenance,
    )
    return_contract = build_first_specimen_return_contract_registry().resolve_required(
        operation.return_contract_ref
    )
    input_refs = (material_value.ref.storage_ref,)
    assignment = RuntimeAssignment(
        runtime_protocol_version="1",
        work_item_id="work:qualify:a",
        assignment_kind=AssignmentKind.INTERPRET,
        project_key=PROJECT_KEY,
        run_id="run-1",
        step_id="step:qualify:a",
        step_role=CompiledStepRole.EFFECT,
        capability_id=operation.owner_capability_id,
        operation_contract_ref=operation.ref,
        operation_contract_digest=operation.ref.contract_digest,
        return_contract_binding=ReturnContractBinding.from_contract(
            operation.return_contract_ref,
            return_contract,
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
        payload_ref=payload_value.ref.storage_ref,
        payload_digest=payload_value.ref.content_digest,
        queue_eligibility_digest=_digest("eligibility"),
        resource_policy_epoch=2,
        claim_authority_epoch=7,
        claim_policy_digest=_digest("claim-policy"),
        expected_step_revision=0,
        trace_id="trace:qualify:a",
    )
    claim = ClaimBinding.bind(
        assignment,
        authorization_digest=_digest("authorization"),
        lease_token="lease:qualify:a",
        lease_expires_at=NOW + timedelta(minutes=5),
        node_id="runtime-node-a",
        node_profile_digest=_digest("node-profile"),
        interpreter_profile_digest=profile,
        authority_digest=_digest("authority"),
        execution_reservation_ref="reservation:qualify:a",
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
    replay = _Replay(
        scope=scope,
        tables=tables,
        payload=payload,
        payload_value=payload_value,
        inputs=(material_value,),
    )
    return installation, assignment, claim, context, replay


def test_qualification_handler_stages_relation_candidate_without_ledger_write(
    handler_db,
) -> None:
    connection, tables, scope = handler_db
    installation, assignment, claim, context, replay = _qualification_specimen(
        connection, tables, scope
    )
    store = FirstSpecimenEffectOutputStore(
        lambda: _Uow(connection),
        replay=replay,
    )
    handler = PostgresFirstSpecimenEffectHandler(installation, store)

    outcome = handler.execute(assignment, claim, context)

    assert outcome.disposition is EffectDisposition.SUCCEEDED
    assert outcome.result_digest is not None
    assert replay.loads == 1
    project_output = connection.execute(
        sa.select(tables.successor_values).where(
            tables.successor_values.c.value_id == "result:run-1:step:qualify:a:epoch-0"
        )
    ).mappings().one()
    public_output = connection.execute(
        sa.select(PUBLIC_TABLES["runtime_values"])
    ).mappings().one()
    staged = connection.execute(
        sa.select(PUBLIC_TABLES["runtime_staged_artifacts"])
    ).mappings().one()
    assert project_output["object_type"] == "EvidenceQualification.v1"
    assert project_output["provenance_json"]["relation_storage"] == (
        "research_relations_only"
    )
    assert public_output["project_value_ref"].startswith("project-value:")
    assert set(public_output).isdisjoint(
        {"content_bytes", "content_json", "payload", "value_bytes"}
    )
    assert staged["state"] == "STAGED"
    assert staged["attempt_id"] == claim.attempt_id
    assert connection.scalar(
        sa.select(sa.func.count()).select_from(tables.research_relations)
    ) == 0
    assert connection.scalar(
        sa.select(sa.func.count()).select_from(tables.research_objects)
    ) == 0

    connection.commit()
    replay.payload = object()
    second = handler.execute(assignment, claim, context)
    assert second == outcome
    assert replay.loads == 1, "CW08 readback must not re-run upstream semantics"


def test_qualification_handler_fails_closed_on_typed_payload_mismatch(handler_db) -> None:
    connection, tables, scope = handler_db
    installation, assignment, claim, context, replay = _qualification_specimen(
        connection, tables, scope
    )
    replay.payload = object()
    store = FirstSpecimenEffectOutputStore(
        lambda: _Uow(connection),
        replay=replay,
    )

    with pytest.raises(FirstSpecimenReplayDrift, match="payload type drift"):
        store.execute_exact(installation, assignment, claim, context)
    assert connection.scalar(
        sa.select(sa.func.count()).select_from(PUBLIC_TABLES["runtime_values"])
    ) == 0


def test_capture_handler_replays_submission_snapshot_without_document_read(handler_db) -> None:
    connection, tables, scope = handler_db
    source = SourceRef(
        source_ref_id="source:document:101",
        owner_id="legacy_document_store",
        locator="document://alpha/101",
        source_class="existing_project_document",
        observed_at=NOW,
        access_profile_ref="DocumentCanonicalReadPort",
    )
    source_value = _value(
        value_id=source.source_ref_id,
        object_type=SOURCE_REF_TYPE,
        codec_id=SOURCE_REF_TYPE.codec_id,
        exact=canonical_bytes(source),
        provenance={"submission_id": "sub-1", "document_id": 101},
    )
    captured_bytes = b"immutable submission-captured Document bytes"
    captured_digest = hashlib.sha256(captured_bytes).hexdigest()
    captured_provenance = {
        "submission_id": "sub-1",
        "document_id": 101,
        "source_ref": source.source_ref_id,
        "observed_text_hash": captured_digest,
        "observed_updated_at": NOW.isoformat(),
    }
    with connection.begin():
        ValueRepository(connection, tables).put_exact(
            scope,
            value_id="sub-1:snapshot:a",
            object_type="CapturedMaterialSnapshot.v1",
            codec_id="mrw.canonical-json.v1",
            content=captured_bytes,
            expected_digest=captured_digest,
            provenance_digest=sha256_hex(captured_provenance),
            expected_revision=0,
            expected_incarnation="p0c:sub-1:sub-1:snapshot:a",
            source_ref=source.source_ref_id,
            provenance=captured_provenance,
        )
    fields = {
        "source_ref": source.source_ref_id,
        "document_id": 101,
        "content_sha256_hex": captured_digest,
        "observed_updated_at": NOW.isoformat(),
        "byte_size": len(captured_bytes),
    }
    payload = CaptureDocumentSnapshotInput(
        **fields, payload_digest=content_digest(fields)
    )
    payload_value = _typed_payload_value(
        "material.capture_document_snapshot.v1", "capture:a", payload
    )
    installation, assignment, claim, context = _semantic_assignment(
        kind="material.capture_document_snapshot.v1",
        operation_id="material.capture.source.a",
        step_id="step:capture:a",
        inputs=(source_value,),
        payload_value=payload_value,
        scope=scope,
    )
    replay = _Replay(scope, tables, payload, payload_value, (source_value,))
    store = FirstSpecimenEffectOutputStore(
        lambda: _Uow(connection), replay=replay
    )

    outcome = store.execute_exact(installation, assignment, claim, context)

    assert outcome.result_digest == captured_digest
    project_rows = connection.execute(
        sa.select(tables.successor_values)
    ).mappings().all()
    assert [row["value_id"] for row in project_rows] == ["sub-1:snapshot:a"]
    public = connection.execute(
        sa.select(PUBLIC_TABLES["runtime_values"])
    ).mappings().one()
    assert public["value_id"] == "result:run-1:step:capture:a:epoch-0"
    assert public["project_value_ref"] == "project-value:sub-1:snapshot:a"

    connection.commit()
    replay.payload = object()
    assert store.execute_exact(installation, assignment, claim, context) == outcome
    assert replay.loads == 1


def test_runtime_handler_rejects_substituted_exact_binding_before_effect(handler_db) -> None:
    connection, tables, scope = handler_db
    installation, assignment, claim, context, replay = _qualification_specimen(
        connection, tables, scope
    )
    substituted = InstalledFirstSpecimenEffectHandler.bind(
        operation_kind="evidence.qualify.v1",
        handler_binding_digest=_digest("not-installed"),
        interpreter_profile_digest=installation.interpreter_profile_digest,
    )
    handler = PostgresFirstSpecimenEffectHandler(
        substituted,
        FirstSpecimenEffectOutputStore(lambda: _Uow(connection), replay=replay),
    )

    with pytest.raises(DefiniteInterpreterFailure):
        handler.execute(assignment, claim, context)
    assert replay.loads == 0


def test_claim_handler_preserves_support_contradiction_uncertainty_and_provenance(
    handler_db,
) -> None:
    connection, tables, scope = handler_db
    snapshot_a = CapturedMaterialSnapshot(
        "project-value:snapshot:a", 101, _digest("doc-a"), NOW, 10
    )
    snapshot_b = CapturedMaterialSnapshot(
        "project-value:snapshot:b", 102, _digest("doc-b"), NOW, 11
    )
    material_a = MaterialRef("material:a", "source:a", snapshot_a)
    material_b = MaterialRef("material:b", "source:b", snapshot_b)
    support, support_value = _qualification_value("a", "SUPPORTS", material_a)
    contradiction, contradiction_value = _qualification_value(
        "b", "CONTRADICTS", material_b
    )
    fields = {
        "claim_or_gap_id": "claim:run-1",
        "statement_ref": "statement:run-1",
        "inquiry_ref": "inquiry:run-1",
        "support_relation_refs": (support.qualification_id,),
        "contradiction_relation_refs": (contradiction.qualification_id,),
        "uncertainty_profile_ref": "uncertainty:first-specimen:explicit",
        "requirement": "",
        "reason": "",
        "missing_evidence_or_decision": "",
        "reopen_policy": {},
        "closure_condition": "",
    }
    payload = ClaimOrGapInput(**fields, payload_digest=content_digest(fields))
    payload_value = _typed_payload_value(
        "claim.form_or_open_gap.v1", "claim", payload
    )
    installation, assignment, claim, context = _semantic_assignment(
        kind="claim.form_or_open_gap.v1",
        operation_id="claim.form_or_open_gap",
        step_id="step:claim",
        inputs=(support_value, contradiction_value),
        payload_value=payload_value,
        scope=scope,
    )
    replay = _Replay(
        scope,
        tables,
        payload,
        payload_value,
        (support_value, contradiction_value),
    )
    store = FirstSpecimenEffectOutputStore(
        lambda: _Uow(connection), replay=replay
    )

    outcome = store.execute_exact(installation, assignment, claim, context)

    assert outcome.disposition is EffectDisposition.SUCCEEDED
    row = connection.execute(
        sa.select(tables.successor_values).where(
            tables.successor_values.c.value_id
            == "result:run-1:step:claim:epoch-0"
        )
    ).mappings().one()
    body = __import__("json").loads(bytes(row["content_bytes"]))
    assert body["support_relation_refs"] == [support.qualification_id]
    assert body["contradiction_relation_refs"] == [contradiction.qualification_id]
    assert body["uncertainty_profile_ref"] == (
        "uncertainty:first-specimen:explicit"
    )
    assert body["scope"]["provenance_closure_digest"] == row[
        "provenance_json"
    ]["provenance_closure_digest"]

    connection.commit()
    reversed_replay = _Replay(
        scope,
        tables,
        payload,
        payload_value,
        (contradiction_value, support_value),
    )
    reversed_assignment_values = assignment.model_dump(mode="python")
    reversed_refs = (
        contradiction_value.ref.storage_ref,
        support_value.ref.storage_ref,
    )
    reversed_assignment_values.update(
        work_item_id="work:step:claim:reversed",
        step_id="step:claim:reversed",
        input_refs=reversed_refs,
        input_closure_digest=canonical_digest(reversed_refs),
    )
    reversed_assignment = RuntimeAssignment.model_validate(
        reversed_assignment_values
    )
    reversed_claim = ClaimBinding.bind(
        reversed_assignment,
        authorization_digest=_digest("authorization:claim:reversed"),
        lease_token="lease:claim:reversed",
        lease_expires_at=NOW + timedelta(minutes=5),
        node_id="runtime-node-a",
        node_profile_digest=_digest("node-profile"),
        interpreter_profile_digest=installation.interpreter_profile_digest,
        authority_digest=_digest("authority"),
        execution_reservation_ref="reservation:claim:reversed",
        execution_reservation_digest=_digest("reservation:claim:reversed"),
    )
    with pytest.raises(FirstSpecimenReplayDrift, match="ordered relation closure"):
        FirstSpecimenEffectOutputStore(
            lambda: _Uow(connection), replay=reversed_replay
        ).execute_exact(
            installation,
            reversed_assignment,
            reversed_claim,
            context,
        )


def test_markdown_handler_closes_claim_relations_citations_and_exact_bytes(
    handler_db,
) -> None:
    connection, tables, scope = handler_db
    materials: list[MaterialRef] = []
    material_values: list[ReplayedProjectValue] = []
    for label, document_id in (("a", 101), ("b", 102)):
        snapshot = CapturedMaterialSnapshot(
            f"project-value:snapshot:{label}",
            document_id,
            _digest(f"doc:{label}"),
            NOW,
            20 + document_id,
        )
        material = MaterialRef(
            f"material:{label}", f"source:{label}", snapshot
        )
        materials.append(material)
        material_values.append(
            _value(
                value_id=material.material_ref_id,
                object_type=MATERIAL_REF_TYPE,
                codec_id=MATERIAL_REF_TYPE.codec_id,
                exact=canonical_bytes(material),
                provenance={"source": material.source_ref},
            )
        )
    support, support_value = _qualification_value("a", "SUPPORTS", materials[0])
    contradiction, contradiction_value = _qualification_value(
        "b", "CONTRADICTS", materials[1]
    )
    _insert_qualification_relation(connection, tables, support)
    _insert_qualification_relation(connection, tables, contradiction)
    connection.commit()
    provenance_closure = _digest("claim-provenance")
    claim_object = Claim(
        claim_id="claim:run-1",
        statement_ref="statement:run-1",
        support_relation_refs=(support.qualification_id,),
        contradiction_relation_refs=(contradiction.qualification_id,),
        uncertainty_profile_ref="uncertainty:first-specimen:explicit",
        lifecycle_state="DRAFT",
        scope={
            "inquiry_ref": "inquiry:run-1",
            "provenance_closure_digest": provenance_closure,
        },
    )
    claim_value = _value(
        value_id=claim_object.claim_id,
        object_type=CLAIM_TYPE,
        codec_id=CLAIM_TYPE.codec_id,
        exact=canonical_bytes(dataclass_to_json(claim_object, ("content_digest",))),
        provenance={
            "semantic_object_id": claim_object.claim_id,
            "qualification_closure_value_refs": [
                support_value.ref.to_plain(),
                contradiction_value.ref.to_plain(),
            ],
        },
    )
    fields = {
        "artifact_id": "artifact:run-1",
        "claim_closure": (claim_object.claim_id,),
        "evidence_relation_closure": (
            support.qualification_id,
            contradiction.qualification_id,
        ),
        "citation_closure": tuple(
            material.material_ref_id for material in materials
        ),
    }
    payload = MarkdownComposeInput(
        **fields,
        payload_digest=content_digest(fields),
    )
    payload_value = _typed_payload_value(
        "artifact.compose_markdown.v1", "artifact", payload
    )
    inputs = (
        claim_value,
        support_value,
        contradiction_value,
        *material_values,
    )
    installation, assignment, claim, context = _semantic_assignment(
        kind="artifact.compose_markdown.v1",
        operation_id="artifact.compose_markdown",
        step_id="step:artifact",
        inputs=inputs,
        payload_value=payload_value,
        scope=scope,
    )
    replay = _Replay(scope, tables, payload, payload_value, inputs)

    outcome = FirstSpecimenEffectOutputStore(
        lambda: _Uow(connection), replay=replay
    ).execute_exact(installation, assignment, claim, context)

    assert outcome.disposition is EffectDisposition.SUCCEEDED
    rows = connection.execute(
        sa.select(tables.successor_values).where(
            tables.successor_values.c.value_id.like(
                "result:run-1:step:artifact:epoch-0%"
            )
        )
    ).mappings().all()
    assert len(rows) == 2
    by_id = {row["value_id"]: row for row in rows}
    metadata = by_id["result:run-1:step:artifact:epoch-0"]
    markdown = by_id["result:run-1:step:artifact:epoch-0:content"]
    metadata_provenance = metadata["provenance_json"]
    assert "artifact_exact_bytes_hex" not in metadata_provenance
    assert metadata_provenance["artifact_exact_bytes_ref"] == (
        "project-value:result:run-1:step:artifact:epoch-0:content"
    )
    exact_markdown = bytes(markdown["content_bytes"])
    assert hashlib.sha256(exact_markdown).hexdigest() == metadata_provenance[
        "artifact_exact_bytes_digest"
    ]
    for ref in payload.citation_closure:
        assert ref.encode() in exact_markdown
    assert connection.scalar(
        sa.select(sa.func.count()).select_from(tables.research_objects)
    ) == 0


def test_activation_binding_preserves_dynamic_prefix_then_static_suffix(handler_db) -> None:
    connection, tables, scope = handler_db
    installation, base, _claim, _context, replay = _qualification_specimen(
        connection, tables, scope
    )
    static_ref = replay.inputs[0].ref
    payload_ref = replay.payload_value.ref
    dynamic_ref = ValueRef(
        value_id="activation:qualify:a:evidence-bundle",
        project_key=PROJECT_KEY,
        object_type=ObjectType("EvidenceBundle.v1"),
        codec_id="mrw.canonical-json.v1",
        content_digest=_digest("dynamic-evidence-bundle"),
        storage_kind="runtime_blob_ref",
        store_id="successor_activation_values",
        store_version="1",
        storage_ref=f"runtime-blob:sha256:{_digest('dynamic-evidence-bundle')}",
        byte_size=71,
        provenance_digest=_digest("dynamic-provenance"),
    )
    closure = {
        "schema_version": "mrw.activation-input-closure.v1",
        "plan_digest": base.plan_digest,
        "step_id": base.step_id,
        "step_kind": "EFFECT",
        "ordered_dependency_refs": (dynamic_ref.to_plain(),),
        "static_atom_input_refs": (static_ref.to_plain(),),
        "payload_ref": payload_ref.to_plain(),
    }
    input_digest = sha256_hex(closure)
    descriptor_body = {
        **closure,
        "operation_id": "evidence.qualify.source.a",
        "operation_contract_digest": installation.operation_contract_digest,
        "input_closure_digest": input_digest,
    }
    descriptor = ReadyActivation(
        step_id=base.step_id or "",
        step_kind="EFFECT",
        operation_id="evidence.qualify.source.a",
        ordered_dependency_refs=(dynamic_ref,),
        static_atom_input_refs=(static_ref,),
        payload_ref=payload_ref,
        input_closure_digest=input_digest,
        activation_digest=sha256_hex(descriptor_body),
    )
    values = base.model_dump(mode="python")
    values.update(
        input_refs=(dynamic_ref.storage_ref, static_ref.storage_ref),
        input_closure_digest=input_digest,
    )
    assignment = RuntimeAssignment.model_validate(values)

    assert require_exact_activation_binding(
        assignment=assignment,
        plan_digest=assignment.plan_digest or "",
        step_kind="EFFECT",
        operation_id=descriptor.operation_id,
        operation_contract_digest=installation.operation_contract_digest,
        static_refs=(static_ref,),
        payload_ref=payload_ref,
        descriptor=descriptor,
    ) == (dynamic_ref, static_ref)

    reversed_values = assignment.model_dump(mode="python")
    reversed_values["input_refs"] = (
        static_ref.storage_ref,
        dynamic_ref.storage_ref,
    )
    reversed_assignment = RuntimeAssignment.model_validate(reversed_values)
    with pytest.raises(FirstSpecimenReplayDrift, match="static input suffix"):
        require_exact_activation_binding(
            assignment=reversed_assignment,
            plan_digest=reversed_assignment.plan_digest or "",
            step_kind="EFFECT",
            operation_id=descriptor.operation_id,
            operation_contract_digest=installation.operation_contract_digest,
            static_refs=(static_ref,),
            payload_ref=payload_ref,
            descriptor=descriptor,
        )
