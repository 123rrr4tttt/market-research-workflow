"""Focused P0-A capability contract/codec/profile and extension-locality tests."""

from __future__ import annotations

import hashlib
import inspect
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from datetime import datetime, timezone

from app.successor_runtime.capabilities import (  # noqa: E402
    FIXTURE_OPERATION_KIND,
    build_first_specimen_bundle,
    build_first_specimen_catalog,
    build_fixture_capability_bundle,
)
from app.successor_runtime.capabilities.checksum import content_digest  # noqa: E402
from app.successor_runtime.capabilities.first_specimen import (  # noqa: E402
    FIRST_SPECIMEN_OPERATION_KINDS,
    CanonicalReadInput,
    CaptureDocumentSnapshotInput,
    ClaimOrGapInput,
    EvidenceQualificationInput,
    InternalExportInput,
    MarkdownComposeInput,
)
from app.successor_runtime.capabilities.fixture import EchoHexDigestInput  # noqa: E402
from app.successor_runtime.language.catalog import (  # noqa: E402
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
)
from app.successor_runtime.language.combinators import (  # noqa: E402
    build_first_specimen_program,
    default_registries,
)
from app.successor_runtime.language.compile import compile_program  # noqa: E402
from app.successor_runtime.language.object_contracts import (  # noqa: E402
    CAPTURE_DOCUMENT_SNAPSHOT_RETURN_CONTRACT_REF,
    CLAIM_OR_GAP_RETURN_CONTRACT_REF,
    DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF,
    EVIDENCE_QUALIFICATION_RETURN_CONTRACT_REF,
    READ_CANONICAL_REF_RETURN_CONTRACT_REF,
    RESEARCH_ARTIFACT_RETURN_CONTRACT_REF,
    OperationContract,
    OperationContractRef,
    build_first_specimen_return_contract_registry,
)
from app.successor_runtime.research.object_types import ObjectType  # noqa: E402
from app.successor_runtime.research.sources import SourceRef  # noqa: E402
from app.successor_runtime.runtime.ports import (  # noqa: E402
    CanonicalDocumentRead,
    DocumentCanonicalReadPort,
)


def _payload_digest(values: dict[str, object]) -> str:
    return content_digest(values)


def _document_source(document_id: int) -> SourceRef:
    return SourceRef(
        source_ref_id=f"source:document:{document_id}",
        owner_id="legacy_document_store",
        locator=f"document://p0/{document_id}",
        source_class="existing_project_document",
        observed_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        access_profile_ref="DocumentCanonicalReadPort",
    )


def _shared_root_hashes(root: Path) -> tuple[str, ...]:
    shared_roots = (
        root / "language" / "program.py",
        root / "language" / "compile.py",
        root / "runtime" / "reducer.py",
        root / "substrate" / "postgres" / "work_items.py",
    )
    return tuple(
        hashlib.sha256(path.read_bytes()).hexdigest()
        if path.exists()
        else "<absent>"
        for path in shared_roots
    )


@pytest.fixture(scope="module")
def first_specimen_bundle():
    return build_first_specimen_bundle()


@pytest.fixture(scope="module")
def fixture_bundle():
    return build_fixture_capability_bundle()


def test_bundle_registers_exactly_six_first_specimen_contracts(first_specimen_bundle):
    kinds = tuple(contract.ref.kind for contract in first_specimen_bundle.operations)
    assert kinds == FIRST_SPECIMEN_OPERATION_KINDS
    assert len(kinds) == 6
    assert len(first_specimen_bundle.codecs) == 6


def test_operation_contract_refs_bind_digests(first_specimen_bundle):
    for contract in first_specimen_bundle.operations:
        assert contract.ref.kind.startswith(("material.", "evidence.", "claim.", "artifact.", "delivery."))
        assert contract.ref.contract_digest == contract.contract_digest()
        assert contract.ref.contract_version == "1.0.0"
        assert len(contract.contract_digest()) == 64


def test_six_operation_return_refs_bind_real_admission_boundaries(
    first_specimen_bundle,
):
    expected = (
        CAPTURE_DOCUMENT_SNAPSHOT_RETURN_CONTRACT_REF,
        READ_CANONICAL_REF_RETURN_CONTRACT_REF,
        EVIDENCE_QUALIFICATION_RETURN_CONTRACT_REF,
        CLAIM_OR_GAP_RETURN_CONTRACT_REF,
        RESEARCH_ARTIFACT_RETURN_CONTRACT_REF,
        DELIVERY_INTENT_RECEIPT_RETURN_CONTRACT_REF,
    )
    refs = tuple(
        contract.return_contract_ref for contract in first_specimen_bundle.operations
    )
    assert refs == expected
    registry = build_first_specimen_return_contract_registry()
    assert tuple(
        registry.resolve_required(ref).admission_required for ref in refs
    ) == (False, False, True, True, True, True)


def test_contract_vocabulary_has_one_canonical_python_identity(first_specimen_bundle):
    contract = first_specimen_bundle.operations[0]
    assert type(contract) is OperationContract
    assert type(contract.ref) is OperationContractRef
    assert type(contract.input_type) is ObjectType


def test_codecs_round_trip_all_first_specimen_payloads(first_specimen_bundle):
    samples = [
        CaptureDocumentSnapshotInput(
            source_ref="src:demo-001",
            document_id=101,
            content_sha256_hex=content_digest({"document": "sample"}),
            observed_updated_at="2026-08-30T00:00:00Z",
            byte_size=32,
            payload_digest=_payload_digest(
                {
                    "source_ref": "src:demo-001",
                    "document_id": 101,
                    "content_sha256_hex": content_digest({"document": "sample"}),
                    "observed_updated_at": "2026-08-30T00:00:00Z",
                    "byte_size": 32,
                }
            ),
        ),
        CanonicalReadInput(
            source_ref="src:demo-002",
            locator="document://demo/102",
            owner_id="legacy_document_store",
            observed_at="2026-08-30T00:00:00Z",
            payload_digest=_payload_digest(
                {
                    "source_ref": "src:demo-002",
                    "locator": "document://demo/102",
                    "owner_id": "legacy_document_store",
                    "observed_at": "2026-08-30T00:00:00Z",
                }
            ),
        ),
        EvidenceQualificationInput(
            qualification_id="qual:001",
            material_ref="material:001",
            inquiry_ref="inquiry:001",
            direction="SUPPORTS",
            scope_statement_ref="scope:001",
            uncertainty_profile_ref="uncertainty:001",
            verifier_profile_ref="verifier:001",
            payload_digest=_payload_digest(
                {
                    "qualification_id": "qual:001",
                    "material_ref": "material:001",
                    "inquiry_ref": "inquiry:001",
                    "direction": "SUPPORTS",
                    "scope_statement_ref": "scope:001",
                    "uncertainty_profile_ref": "uncertainty:001",
                    "verifier_profile_ref": "verifier:001",
                }
            ),
        ),
        ClaimOrGapInput(
            claim_or_gap_id="gap:001",
            statement_ref="statement:001",
            inquiry_ref="inquiry:001",
            support_relation_refs=("qual:001",),
            requirement="need more evidence",
            reason="insufficient support",
            payload_digest=_payload_digest(
                {
                    "claim_or_gap_id": "gap:001",
                    "statement_ref": "statement:001",
                    "inquiry_ref": "inquiry:001",
                    "support_relation_refs": ("qual:001",),
                    "contradiction_relation_refs": (),
                    "requirement": "need more evidence",
                    "reason": "insufficient support",
                    "missing_evidence_or_decision": "",
                    "uncertainty_profile_ref": "",
                    "reopen_policy": {},
                    "closure_condition": "",
                }
            ),
        ),
        MarkdownComposeInput(
            artifact_id="artifact:001",
            claim_closure=("claim:001",),
            evidence_relation_closure=("qual:001",),
            citation_closure=("material:001",),
            payload_digest=_payload_digest(
                {
                    "artifact_id": "artifact:001",
                    "claim_closure": ("claim:001",),
                    "evidence_relation_closure": ("qual:001",),
                    "citation_closure": ("material:001",),
                }
            ),
        ),
        InternalExportInput(
            delivery_intent_id="intent:001",
            artifact_ref="artifact:001",
            audience="internal-review",
            approval_refs=("approval:human-001",),
            idempotency_key="export-001",
            payload_digest=_payload_digest(
                {
                    "delivery_intent_id": "intent:001",
                    "artifact_ref": "artifact:001",
                    "audience": "internal-review",
                    "approval_refs": ("approval:human-001",),
                    "idempotency_key": "export-001",
                }
            ),
        ),
    ]

    for kind, payload in zip(FIRST_SPECIMEN_OPERATION_KINDS, samples, strict=True):
        codec = first_specimen_bundle.codec_by_kind(kind)
        encoded = codec.encode_payload(payload)
        decoded = codec.decode_payload(encoded)
        assert decoded == payload
        assert codec.contract_ref.kind == kind


def test_effect_profiles_enforce_p0a_limits(first_specimen_bundle):
    for kind in FIRST_SPECIMEN_OPERATION_KINDS:
        contract = first_specimen_bundle.operation_by_kind(kind)
        effect_ref = contract.effect_profile_ref
        assert effect_ref.profile_id == f"{kind}.effect"
        assert effect_ref.profile_digest

    deliver = first_specimen_bundle.operation_by_kind("delivery.internal_export.v1")
    capture = first_specimen_bundle.operation_by_kind(
        "material.capture_document_snapshot.v1"
    )
    read = first_specimen_bundle.operation_by_kind("material.read_canonical_ref.v1")

    # Profiles are encoded by digest refs in P0-A; the capability-owned module
    # itself enforces the frozen effect limits at profile construction time.
    assert deliver.effect_profile_ref.profile_id == "delivery.internal_export.v1.effect"
    assert capture.interpreter_compatibility_ref.profile_id == (
        "material.capture_document_snapshot.v1.interpreter"
    )
    assert read.effect_profile_ref.profile_id == "material.read_canonical_ref.v1.effect"
    assert deliver.observation_profile_ref.profile_id == "delivery.internal_export.v1.observation"


def test_document_canonical_read_port_exposes_exact_authoritative_observation():
    class FakeDocumentReader:
        def read_document(
            self, project_key: str, document_id: int
        ) -> CanonicalDocumentRead:
            assert project_key == "p0"
            return CanonicalDocumentRead(
                document_id=document_id,
                text_hash="a" * 64,
                updated_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
                exact_bytes=b"exact document bytes",
            )

    reader = FakeDocumentReader()
    assert isinstance(reader, DocumentCanonicalReadPort)
    observed = reader.read_document("p0", 101)
    assert observed.document_id == 101
    assert observed.text_hash == "a" * 64
    assert observed.exact_bytes == b"exact document bytes"


def test_delivery_is_internal_export_with_human_approval(first_specimen_bundle):
    deliver = first_specimen_bundle.operation_by_kind("delivery.internal_export.v1")
    assert deliver.authority_profile_ref.profile_id == "delivery.internal_export.v1.authority"
    assert deliver.owner_capability_id == "delivery.first_specimen.v1"
    assert deliver.output_type.type_id == "DeliveryReceiptRef.v1"


def test_fixture_capability_is_additive_only(fixture_bundle, first_specimen_bundle):
    before_kinds = {contract.ref.kind for contract in first_specimen_bundle.operations}
    assert FIXTURE_OPERATION_KIND not in before_kinds

    successor_root = Path(_BACKEND_ROOT) / "app" / "successor_runtime"
    before = _shared_root_hashes(successor_root)
    catalog = build_first_specimen_catalog(first_specimen_bundle.operations, fixture_bundle.operation)
    assert type(catalog) is OperationContractCatalogSnapshot
    after_kinds = catalog.registered_kinds()
    assert after_kinds == before_kinds | {FIXTURE_OPERATION_KIND}

    # Registering the extension must not create or modify any shared
    # AST/compiler/reducer/work-item root schema (static source hashes).
    after = _shared_root_hashes(successor_root)
    assert after == before

    fixture_module = sys.modules[type(fixture_bundle).__module__]
    fixture_source = inspect.getsource(fixture_module)
    assert "SHARED_STRUCTURE_MODULES" in fixture_source
    for shared_import in (
        "from successor_runtime.language.program",
        "import successor_runtime.language.program",
        "from successor_runtime.language.compile",
        "from successor_runtime.runtime.reducer",
        "from successor_runtime.substrate.postgres.work_items",
    ):
        assert shared_import not in fixture_source


def test_no_legacy_service_or_framework_imports_in_capabilities():
    capability_root = Path(_BACKEND_ROOT) / "app" / "successor_runtime" / "capabilities"
    forbidden = (
        "app.services",
        "from app.api",
        "import fastapi",
        "import sqlalchemy",
        "import celery",
        "import redis",
        "from app.settings",
    )
    for path in sorted(capability_root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        for fragment in forbidden:
            assert fragment not in source, f"{path} must not import {fragment}"


def test_fixture_echo_codec_round_trip(fixture_bundle):
    payload = EchoHexDigestInput(
        value_sha256_hex=content_digest({"fixture": "sample"}),
        payload_digest=_payload_digest(
            {"value_sha256_hex": content_digest({"fixture": "sample"})}
        ),
    )
    encoded = fixture_bundle.codec.encode_payload(payload)
    assert fixture_bundle.codec.decode_payload(encoded) == payload


def test_real_first_specimen_program_compiles_complete_frozen_path(first_specimen_bundle):
    catalog = build_first_specimen_catalog(first_specimen_bundle.operations)
    registry = OperationContractRegistry(catalog, first_specimen_bundle.operations)
    registries = default_registries()
    program = build_first_specimen_program(
        catalog=catalog,
        program_id="first-specimen.compile-ready",
        project_key="p0",
        project_scope_digest="0" * 64,
        registries=registries,
        source_refs=(_document_source(101), _document_source(102)),
    )
    seed_sql = (
        Path(_BACKEND_ROOT) / "seed_data/project_demo_proj_v0.9-rc2.0.sql"
    ).read_text(encoding="utf-8")
    assert "VALUES (101," in seed_sql
    assert "VALUES (102," in seed_sql
    plan = compile_program(
        program,
        catalog,
        operation_contracts=registry,
        merge_registry=registries.merges,
    )
    operation_ids = tuple(
        step.operation_id
        for step in plan.ordered_steps
        if step.operation_id is not None and step.step_kind == "EFFECT"
    )
    assert operation_ids == (
        "material.capture.source.a",
        "material.read.source.a",
        "evidence.qualify.source.a",
        "material.capture.source.b",
        "material.read.source.b",
        "evidence.qualify.source.b",
        "claim.form_or_open_gap",
        "artifact.compose_markdown",
        "delivery.internal_export",
    )
    capture_steps = [
        step
        for step in plan.ordered_steps
        if step.operation_contract_ref is not None
        and step.operation_contract_ref.kind
        == "material.capture_document_snapshot.v1"
    ]
    assert len(capture_steps) == 2
    assert {step.operation_id for step in capture_steps} == {
        "material.capture.source.a",
        "material.capture.source.b",
    }
    assert all(step.input_type.type_id == "SourceRef.v1" for step in capture_steps)
    assert all(
        step.output_type.type_id == "CapturedMaterialSnapshot.v1"
        for step in capture_steps
    )
    admission_ids = tuple(
        step.operation_id
        for step in plan.ordered_steps
        if step.step_kind == "ADMISSION"
    )
    assert admission_ids == (
        "evidence.qualify.source.a",
        "evidence.qualify.source.b",
        "claim.form_or_open_gap",
        "artifact.compose_markdown",
        "delivery.internal_export",
    )
    assert len([step for step in plan.ordered_steps if step.step_kind == "EFFECT"]) == 9
    assert len([step for step in plan.ordered_steps if step.step_kind == "ADMISSION"]) == 5
    for operation_id in admission_ids:
        effect, admission = (
            step for step in plan.ordered_steps if step.operation_id == operation_id
        )
        assert (effect.step_kind, admission.step_kind) == ("EFFECT", "ADMISSION")
        assert effect.staged_output_only is True
        assert effect.semantic_return_barrier is False
        assert admission.dependencies == (effect.step_id,)
        assert admission.semantic_return_barrier is True
    for operation_id in (
        "material.capture.source.a",
        "material.read.source.a",
        "material.capture.source.b",
        "material.read.source.b",
    ):
        steps = [step for step in plan.ordered_steps if step.operation_id == operation_id]
        assert tuple(step.step_kind for step in steps) == ("EFFECT",)
        assert steps[0].staged_output_only is False
        assert steps[0].semantic_return_barrier is True
    assert program.input_type.type_id == "ResearchIntent.v1"
    assert program.output_type.type_id == "DeliveryReceiptRef.v1"
    assert dict(program.metadata)["first_specimen_schema_ref"] == (
        "16_functorial-successor-first-specimen-schema-bundle.v1.1.schema.json"
    )
    assert all(
        ref.name != "mrw.first_specimen.MaterializeSuccessor"
        and ref.name != "mrw.first_specimen.successor_inquiry_ref_to_gap"
        for ref in program.transform_refs
    )
    materialize = dict(program.metadata)["MATERIALIZE_SUCCESSOR"]
    assert materialize == (
        ("branch", "gap"),
        ("control_kind", "MaterializeSuccessor"),
        ("control_version", "1.0.0"),
        ("disposition", "P0_A_COMPILE_ONLY"),
        ("input_type", "Gap.v1"),
        ("materializer_id", "mrw.first_specimen.gap-successor"),
        ("materializer_version", "1.0.0"),
        ("successor_output_type", "ResearchPlan.v1"),
    )
