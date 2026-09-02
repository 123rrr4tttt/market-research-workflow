from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from app.successor_runtime.language.algebra import freeze_json_object
from app.successor_runtime.language.plan import identity_plan, with_plan_digest
from app.successor_runtime.language.program import ProgramSpec, identity_node
from app.successor_runtime.research.evidence import EvidenceQualification, Validity
from app.successor_runtime.research.identities import ResearchObjectRef
from app.successor_runtime.research.object_types import (
    CLAIM_TYPE,
    DELIVERY_INTENT_TYPE,
    DELIVERY_RECEIPT_REF_TYPE,
    GAP_TYPE,
    INQUIRY_TYPE,
    MATERIAL_REF_TYPE,
    RESEARCH_ARTIFACT_TYPE,
    RESEARCH_INTENT_TYPE,
    RESEARCH_PLAN_TYPE,
    SOURCE_REF_TYPE,
    ObjectType,
)
from app.successor_runtime.research.relations import ResearchRelation
from app.successor_runtime.runtime.ports import ProjectScopeRef, RuntimeScope
from app.successor_runtime.substrate.postgres.models import project_tables
from app.successor_runtime.substrate.postgres.owner_bindings import (
    OwnerBindingRecord,
    OwnerBindingRepository,
)
from app.successor_runtime.substrate.postgres.plans import PlanRepository
from app.successor_runtime.substrate.postgres.programs import ProgramRepository
from app.successor_runtime.substrate.postgres.research_ledger import (
    ExactContentConflict,
    OwnerBindingViolation,
    ProjectRecordNotFound,
    ResearchLedgerRepository,
)
from app.successor_runtime.substrate.postgres.session import compute_scope_digest
from app.successor_runtime.substrate.postgres.values import (
    ReceiptRepository,
    ValueRepository,
    derive_value_write_intent_digest,
)

pytestmark = pytest.mark.unit

_PROJECT_SCOPE_INCARNATION = "project-scope-inc-1"
_PROJECT_SCOPE_DIGEST = compute_scope_digest(
    "alpha",
    "project_alpha",
    3,
    _PROJECT_SCOPE_INCARNATION,
)


@compiles(JSONB, "sqlite")
def _sqlite_jsonb(_type: object, _compiler: object, **_kw: object) -> str:
    return "JSON"


def _digest(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode()
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def project_db():
    engine = sa.create_engine("sqlite://")
    connection = engine.connect()
    connection.connection.create_function(
        "num_nonnulls", -1, lambda *values: sum(value is not None for value in values)
    )
    connection.exec_driver_sql("ATTACH DATABASE ':memory:' AS project_alpha")
    metadata = sa.MetaData()
    tables = project_tables(metadata, "project_alpha")
    metadata.create_all(connection)
    connection.commit()
    scope = RuntimeScope(
        project_scope=ProjectScopeRef(
            project_key="alpha",
            resolved_schema="project_alpha",
            project_registry_revision=3,
            incarnation=_PROJECT_SCOPE_INCARNATION,
            scope_digest=_PROJECT_SCOPE_DIGEST,
        ),
        actor_id="tester",
    )
    transaction = connection.begin()
    try:
        yield connection, tables, scope
    finally:
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()


def _binding(
    object_type: str,
    owner_id: str = "ResearchLedger",
    owner_mode: str = "CANONICAL_OWNED",
) -> OwnerBindingRecord:
    now = datetime(2026, 8, 30, tzinfo=UTC)
    return OwnerBindingRecord(
        object_type=object_type,
        owner_mode=owner_mode,
        owner_id=owner_id,
        owner_epoch=1,
        readback_profile_ref="ledger-readback-v1",
        base_incarnation="project-inc-1",
        rollback_evidence_ref="rollback:none",
        effective_at=now,
        approval_ref="approval-1",
    )


def _object(object_id: str, object_type: ObjectType, owner: str) -> ResearchObjectRef:
    return ResearchObjectRef(
        object_id=object_id,
        object_type=object_type,
        project_key="alpha",
        owner_binding_ref=owner,
        content_ref=f"value://{object_id}",
        content_digest=_digest(object_id + ":content"),
        provenance_closure_digest=_digest(object_id + ":provenance"),
    )


def test_owner_matrix_and_evidence_qualification_are_relation_only(project_db) -> None:
    connection, tables, scope = project_db
    owners = OwnerBindingRepository(connection, tables)
    ledger = ResearchLedgerRepository(connection, tables)
    owners.put_exact(
        scope,
        _binding(INQUIRY_TYPE.type_id),
        expected_owner_epoch=0,
        expected_base_incarnation="project-inc-1",
    )
    owners.put_exact(
        scope,
        _binding(
            MATERIAL_REF_TYPE.type_id,
            "CapturedMaterialSnapshot",
            "IMMUTABLE_EXTERNAL_REF",
        ),
        expected_owner_epoch=0,
        expected_base_incarnation="project-inc-1",
    )
    inquiry = _object("inquiry-1", INQUIRY_TYPE, "ResearchLedger")
    material = _object("material-1", MATERIAL_REF_TYPE, "CapturedMaterialSnapshot")
    ledger.put_object(scope, inquiry, expected_revision=0, expected_incarnation="inc-1")
    ledger.put_object(scope, material, expected_revision=0, expected_incarnation="inc-1")

    qualification = EvidenceQualification(
        qualification_id="eq-1",
        project_key="alpha",
        material_ref="material-1",
        inquiry_ref="inquiry-1",
        claim_ref=None,
        direction="SUPPORTS",
        scope_statement_ref="scope:claim",
        uncertainty_profile_ref="uncertainty:none",
        verifier_profile_ref="verifier:v1",
        provenance_closure_digest=_digest("eq-provenance"),
        validity=Validity(None, None),
    )
    ledger.put_evidence_qualification(
        scope,
        qualification,
        source_ref=material,
        target_ref=inquiry,
        expected_revision=0,
        expected_incarnation="inc-1",
    )
    assert connection.scalar(sa.select(sa.func.count()).select_from(tables.research_objects)) == 2
    assert connection.scalar(sa.select(sa.func.count()).select_from(tables.research_relations)) == 1


@pytest.mark.parametrize(
    ("object_type", "owner_mode", "owner_id"),
    (
        (RESEARCH_INTENT_TYPE, "CANONICAL_OWNED", "ResearchLedger"),
        (INQUIRY_TYPE, "CANONICAL_OWNED", "ResearchLedger"),
        (RESEARCH_PLAN_TYPE, "CANONICAL_OWNED", "ResearchLedger"),
        (SOURCE_REF_TYPE, "IMMUTABLE_EXTERNAL_REF", "legacy_source_or_document_locator"),
        (MATERIAL_REF_TYPE, "IMMUTABLE_EXTERNAL_REF", "CapturedMaterialSnapshot"),
        (CLAIM_TYPE, "CANONICAL_OWNED", "ResearchLedger"),
        (GAP_TYPE, "CANONICAL_OWNED", "ResearchLedger"),
        (
            RESEARCH_ARTIFACT_TYPE,
            "CANONICAL_OWNED",
            "ResearchLedger_plus_project_artifact_store",
        ),
        (DELIVERY_INTENT_TYPE, "CANONICAL_OWNED", "ResearchLedger"),
        (DELIVERY_RECEIPT_REF_TYPE, "IMMUTABLE_EXTERNAL_REF", "project_receipt_store"),
    ),
)
def test_first_slice_owner_matrix_accepts_only_frozen_bindings(
    project_db,
    object_type: ObjectType,
    owner_mode: str,
    owner_id: str,
) -> None:
    connection, tables, scope = project_db
    binding = _binding(object_type.type_id, owner_id, owner_mode)
    OwnerBindingRepository(connection, tables).put_exact(
        scope,
        binding,
        expected_owner_epoch=0,
        expected_base_incarnation="project-inc-1",
    )
    ref = _object(f"object-{object_type.type_id}", object_type, owner_id)
    assert ResearchLedgerRepository(connection, tables).put_object(
        scope,
        ref,
        expected_revision=0,
        expected_incarnation="inc-1",
    ) == ref


@pytest.mark.parametrize(
    ("object_type", "owner_mode", "owner_id"),
    (
        (MATERIAL_REF_TYPE.type_id, "CANONICAL_OWNED", "ResearchLedger"),
        (INQUIRY_TYPE.type_id, "IMMUTABLE_EXTERNAL_REF", "ResearchLedger"),
        (RESEARCH_ARTIFACT_TYPE.type_id, "CANONICAL_OWNED", "ResearchLedger"),
        ("EvidenceQualification.v1", "CANONICAL_OWNED", "ResearchLedger"),
        ("DeliveryAttempt.v1", "RUNTIME_FACT", "ExecutionJournal"),
    ),
)
def test_first_slice_owner_matrix_rejects_wrong_or_non_object_bindings(
    project_db,
    object_type: str,
    owner_mode: str,
    owner_id: str,
) -> None:
    connection, tables, scope = project_db
    with pytest.raises(OwnerBindingViolation):
        OwnerBindingRepository(connection, tables).put_exact(
            scope,
            _binding(object_type, owner_id, owner_mode),
            expected_owner_epoch=0,
            expected_base_incarnation="project-inc-1",
        )


def test_put_object_rechecks_matrix_against_corrupt_material_owner_binding(project_db) -> None:
    connection, tables, scope = project_db
    now = datetime(2026, 8, 30, tzinfo=UTC)
    connection.execute(
        sa.insert(tables.research_owner_bindings).values(
            project_key="alpha",
            object_type=MATERIAL_REF_TYPE.type_id,
            owner_mode="CANONICAL_OWNED",
            owner_id="ResearchLedger",
            owner_epoch=1,
            readback_profile_ref="ledger-readback-v1",
            base_incarnation="project-inc-1",
            rollback_evidence_ref="rollback:none",
            effective_at=now,
            superseded_at=None,
            approval_ref="approval-1",
            created_at=now,
            updated_at=now,
        )
    )
    material = _object("material-1", MATERIAL_REF_TYPE, "ResearchLedger")
    with pytest.raises(OwnerBindingViolation, match="IMMUTABLE_EXTERNAL_REF"):
        ResearchLedgerRepository(connection, tables).put_object(
            scope,
            material,
            expected_revision=0,
            expected_incarnation="inc-1",
        )


def test_delivery_receipt_is_external_ref_linked_only_by_delivered_as(project_db) -> None:
    connection, tables, scope = project_db
    owners = OwnerBindingRepository(connection, tables)
    ledger = ResearchLedgerRepository(connection, tables)
    owners.put_exact(
        scope,
        _binding(
            RESEARCH_ARTIFACT_TYPE.type_id,
            "ResearchLedger_plus_project_artifact_store",
        ),
        expected_owner_epoch=0,
        expected_base_incarnation="project-inc-1",
    )
    owners.put_exact(
        scope,
        _binding(
            DELIVERY_RECEIPT_REF_TYPE.type_id,
            "project_receipt_store",
            "IMMUTABLE_EXTERNAL_REF",
        ),
        expected_owner_epoch=0,
        expected_base_incarnation="project-inc-1",
    )
    artifact = _object(
        "artifact-1",
        RESEARCH_ARTIFACT_TYPE,
        "ResearchLedger_plus_project_artifact_store",
    )
    now = datetime(2026, 8, 30, tzinfo=UTC)
    receipt_content = {"provider": "internal", "status": "ok"}
    receipt_digest = _digest(b'{"provider":"internal","status":"ok"}')
    ReceiptRepository(connection, tables).put_exact(
        scope,
        receipt_id="receipt-1",
        receipt_digest=receipt_digest,
        delivery_intent_ref="intent-1",
        attempt_ref="attempt-1",
        provider_locator="internal://receipt-1",
        content=receipt_content,
        outcome_time=now,
    )
    receipt = replace(
        _object(
            "receipt-1",
            DELIVERY_RECEIPT_REF_TYPE,
            "project_receipt_store",
        ),
        content_ref="successor_receipts/receipt-1",
        content_digest=receipt_digest,
    )
    ledger.put_object(scope, artifact, expected_revision=0, expected_incarnation="inc-1")
    ledger.put_object(scope, receipt, expected_revision=0, expected_incarnation="inc-1")
    relation = ResearchRelation(
        relation_id="delivered-as-1",
        relation_type="delivered_as",
        project_key="alpha",
        source_ref=artifact,
        target_ref=receipt,
        provenance_closure_digest=_digest("delivery-provenance"),
    )
    assert ledger.put_relation(
        scope,
        relation,
        expected_revision=0,
        expected_incarnation="inc-1",
    ) == relation
    assert connection.scalar(
        sa.select(sa.func.count()).select_from(tables.research_relations)
    ) == 1

    unverified_receipt = _object(
        "receipt-without-readback",
        DELIVERY_RECEIPT_REF_TYPE,
        "project_receipt_store",
    )
    ledger.put_object(
        scope,
        unverified_receipt,
        expected_revision=0,
        expected_incarnation="inc-1",
    )
    with pytest.raises(ProjectRecordNotFound, match="authoritative receipt readback"):
        ledger.put_relation(
            scope,
            replace(
                relation,
                relation_id="delivered-as-without-readback",
                target_ref=unverified_receipt,
                relation_digest=None,
            ),
            expected_revision=0,
            expected_incarnation="inc-1",
        )


def test_existing_document_content_cannot_become_a_ledger_object(project_db) -> None:
    connection, tables, scope = project_db
    owners = OwnerBindingRepository(connection, tables)
    with pytest.raises(OwnerBindingViolation):
        owners.put_exact(
            scope,
            _binding("Document.v1", "legacy_document_store"),
            expected_owner_epoch=0,
            expected_base_incarnation="project-inc-1",
        )


def _program() -> ProgramSpec:
    object_type = ObjectType("Inquiry.v1")
    return ProgramSpec(
        program_id="program-1",
        contract_version="1.0.0",
        project_key="alpha",
        project_registry_revision=3,
        project_scope_digest=_PROJECT_SCOPE_DIGEST,
        semantic_identity="identity-inquiry",
        input_type=object_type,
        output_type=object_type,
        root=identity_node(object_type),
        algebra_refs=(),
        transform_refs=(),
        observation_profile="structural",
        metadata=freeze_json_object({}),
        program_digest="",
    ).with_digest()


def test_exact_program_plan_and_value_round_trip(project_db) -> None:
    connection, tables, scope = project_db
    program = _program()
    programs = ProgramRepository(connection, tables)
    programs.put_exact(scope, program, program.program_digest)
    assert programs.get(scope, program.program_id, expected_digest=program.program_digest) == program

    plan = identity_plan(program.input_type)
    plan = with_plan_digest(replace(plan, program_id=program.program_id, program_digest=program.program_digest, plan_digest=""))
    plans = PlanRepository(connection, tables)
    plans.put_exact(
        scope,
        plan,
        plan.plan_digest,
        operation_catalog_id="catalog-1",
        catalog_version="1",
        catalog_digest=_digest("catalog"),
    )
    assert plans.get(scope, plan.plan_digest) == plan

    payload = b"exact document snapshot bytes"
    values = ValueRepository(connection, tables)
    stored = values.put_exact(
        scope,
        value_id="value-1",
        object_type="CapturedMaterialSnapshot.v1",
        codec_id="bytes.v1",
        content=payload,
        expected_digest=_digest(payload),
        provenance_digest=_digest("provenance"),
        expected_revision=0,
        expected_incarnation="value-inc-1",
    )
    assert stored.revision == 1
    assert values.get_exact(
        scope,
        "value-1",
        expected_revision=1,
        expected_incarnation="value-inc-1",
        expected_digest=_digest(payload),
    ) == payload
    row = connection.execute(
        sa.select(tables.successor_values).where(
            tables.successor_values.c.project_key == "alpha",
            tables.successor_values.c.value_id == "value-1",
        )
    ).mappings().one()
    assert row["write_intent_digest"] == derive_value_write_intent_digest(
        project_key="alpha",
        value_id="value-1",
        object_type="CapturedMaterialSnapshot.v1",
        codec_id="bytes.v1",
        content_digest=_digest(payload),
        provenance_digest=_digest("provenance"),
        source_ref=None,
        expected_revision=0,
        expected_incarnation="value-inc-1",
        state="AVAILABLE",
    )


def test_value_write_intent_rejects_unbound_digest_and_retry_mutation(project_db) -> None:
    connection, tables, scope = project_db
    payload = b"intent-bound snapshot"
    values = ValueRepository(connection, tables)
    common = {
        "value_id": "value-intent-1",
        "object_type": "CapturedMaterialSnapshot.v1",
        "codec_id": "bytes.v1",
        "content": payload,
        "expected_digest": _digest(payload),
        "provenance_digest": _digest("provenance"),
        "expected_revision": 0,
        "expected_incarnation": "value-intent-inc-1",
    }
    with pytest.raises(
        ExactContentConflict,
        match="write intent digest does not bind exact value write",
    ):
        values.put_exact(scope, **common, write_intent_digest=_digest("unbound"))
    assert connection.execute(sa.select(sa.func.count()).select_from(
        tables.successor_values
    )).scalar_one() == 0

    values.put_exact(scope, **common)
    repeated = values.put_exact(scope, **common)
    assert repeated.revision == 1
    with pytest.raises(
        ExactContentConflict,
        match="existing value identity has a different exact write binding",
    ):
        values.put_exact(scope, **common, source_ref="document:mutated")


def test_same_digest_with_different_bytes_and_receipt_mutation_fail_closed(project_db) -> None:
    connection, tables, scope = project_db
    payload = b"authoritative"
    digest = _digest(payload)
    now = datetime(2026, 8, 30, tzinfo=UTC)
    connection.execute(sa.insert(tables.successor_values).values(
        project_key="alpha", value_id="other", object_type="Blob.v1", codec_id="bytes.v1",
        content_digest=digest, byte_size=7, content_bytes=b"corrupt",
        source_ref=None, provenance_json={}, provenance_digest=_digest("p"), state="AVAILABLE",
        revision=1, incarnation="inc-1", write_intent_digest=_digest("i"),
        write_receipt_digest=None, created_at=now, updated_at=now,
    ))
    with pytest.raises(ExactContentConflict):
        ValueRepository(connection, tables).put_exact(
            scope, value_id="value-1", object_type="Blob.v1", codec_id="bytes.v1",
            content=payload, expected_digest=digest, provenance_digest=_digest("p"),
            expected_revision=0, expected_incarnation="inc-1", write_intent_digest=_digest("i"),
        )

    receipts = ReceiptRepository(connection, tables)
    receipt = {"provider": "internal", "status": "ok"}
    receipt_digest = _digest(b'{"provider":"internal","status":"ok"}')
    receipts.put_exact(
        scope, receipt_id="receipt-1", receipt_digest=receipt_digest,
        delivery_intent_ref="intent-1", attempt_ref="attempt-1",
        provider_locator="internal://receipt-1", content=receipt, outcome_time=now,
    )
    with pytest.raises(ExactContentConflict):
        receipts.put_exact(
            scope, receipt_id="receipt-1", receipt_digest=receipt_digest,
            delivery_intent_ref="intent-1", attempt_ref="attempt-mutated",
            provider_locator="internal://receipt-1", content=receipt, outcome_time=now,
        )


def test_project_sql_is_schema_qualified_for_postgresql() -> None:
    metadata = sa.MetaData()
    tables = project_tables(metadata, "tenant_research")
    sql = str(
        sa.select(tables.research_program_specs).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "tenant_research.research_program_specs" in sql


def test_repository_leaves_transaction_outcome_to_caller(project_db) -> None:
    connection, tables, scope = project_db
    OwnerBindingRepository(connection, tables).put_exact(
        scope,
        _binding(INQUIRY_TYPE.type_id),
        expected_owner_epoch=0,
        expected_base_incarnation="project-inc-1",
    )
    assert connection.scalar(
        sa.select(sa.func.count()).select_from(tables.research_owner_bindings)
    ) == 1
    connection.rollback()
    assert connection.scalar(
        sa.select(sa.func.count()).select_from(tables.research_owner_bindings)
    ) == 0
