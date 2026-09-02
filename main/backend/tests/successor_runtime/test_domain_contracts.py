"""Focused P0-A domain contract tests for the functorial successor."""

from __future__ import annotations

import sys
from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.successor_runtime.capabilities import profiles as capability_profiles
from app.successor_runtime.capabilities.catalog import build_first_specimen_catalog
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.capabilities.first_specimen import (
    build_first_specimen_bundle,
)
from app.successor_runtime.language.catalog import (  # noqa: E402
    FIRST_SPECIMEN_CONTRACT_REF,
    FIRST_SPECIMEN_DOMAIN_SNAPSHOT_ID,
    FIRST_SPECIMEN_DOMAIN_SNAPSHOT_VERSION,
    FIRST_SPECIMEN_OBJECT_CONTRACT_REFS,
    FIRST_SPECIMEN_OPERATION_KINDS,
    FIRST_SPECIMEN_RELATION_CONTRACT_REFS,
    OperationContractCatalogSnapshot,
    OperationContractRegistry,
    build_first_specimen_domain_snapshot,
    build_first_specimen_object_contracts,
)
from app.successor_runtime.language.checksum import (  # noqa: E402
    UnsupportedCanonicalValueError,
    canonical_json,
    is_sha256_hex,
)
from app.successor_runtime.language.object_contracts import (  # noqa: E402
    OperationContract,
    OperationContractRef,
    make_operation_contract,
)
from app.successor_runtime.language.profiles import (  # noqa: E402
    PROFILE_FAMILIES,
    ContractProfileRef,
    SemanticProfile,
)
from app.successor_runtime.research.artifacts import (  # noqa: E402
    EFFECT_DISPOSITIONS,
    DeliveryAttempt,
    DeliveryIntent,
    DeliveryReceiptRef,
    ResearchArtifact,
)
from app.successor_runtime.research.claims import Claim, Gap  # noqa: E402
from app.successor_runtime.research.evidence import (  # noqa: E402
    EvidenceQualification,
    Validity,
)
from app.successor_runtime.research.identities import ResearchObjectRef  # noqa: E402
from app.successor_runtime.research.inquiries import (  # noqa: E402
    Inquiry,
    ResearchIntent,
    ResearchPlan,
)
from app.successor_runtime.research.materials import (  # noqa: E402
    CapturedMaterialSnapshot,
    MaterialRef,
)
from app.successor_runtime.research.object_types import ObjectType  # noqa: E402
from app.successor_runtime.research.provenance import (  # noqa: E402
    ProvenanceClosure,
    ProvenanceEntry,
)
from app.successor_runtime.research.relations import (  # noqa: E402
    RELATION_CONTRACT_BY_ID,
    ResearchRelation,
)
from app.successor_runtime.research.sources import SourceRef  # noqa: E402

UTC = timezone.utc
DIGEST64 = "a" * 64


def make_source_ref() -> SourceRef:
    return SourceRef(
        source_ref_id="src-1",
        owner_id="project:documents",
        locator="documents:42",
        source_class="existing_document",
        access_profile_ref="readonly:project_documents",
        observed_at=datetime(2026, 8, 30, tzinfo=UTC),
    )


def make_snapshot() -> CapturedMaterialSnapshot:
    return CapturedMaterialSnapshot(
        value_ref="value:snapshot-1",
        document_id=42,
        observed_text_hash="abc123",
        observed_updated_at=datetime(2026, 8, 29, tzinfo=UTC),
        byte_size=1024,
    )


def make_material_ref() -> MaterialRef:
    return MaterialRef(
        material_ref_id="mat-1",
        source_ref=make_source_ref().source_ref_id,
        snapshot=make_snapshot(),
    )


def make_intent() -> ResearchIntent:
    return ResearchIntent(
        intent_id="intent-1",
        project_key="proj-a",
        purpose="assess a market signal from existing documents",
        audience_or_use="internal research review",
        scope={"sources": ["documents"]},
        as_of=datetime(2026, 8, 30, tzinfo=UTC),
        constraints={"approved_sources": ["documents"]},
        expected_delivery={"format": "markdown", "channel": "internal_export"},
    )


def test_research_intent_is_immutable_with_canonical_digest() -> None:
    intent = make_intent()
    assert is_dataclass(intent)
    assert is_sha256_hex(intent.content_digest)
    assert canonical_json(intent) == canonical_json(intent)
    assert intent.audience_or_use == "internal research review"
    assert intent.constraints == {"approved_sources": ["documents"]}
    second = make_intent()
    assert second.content_digest == intent.content_digest
    with pytest.raises(FrozenInstanceError):
        intent.purpose = "changed"


def test_frozen_required_semantic_fields_are_required() -> None:
    base_intent = dict(
        intent_id="intent-1",
        project_key="proj-a",
        purpose="assess a market signal from existing documents",
        audience_or_use="internal research review",
        scope={"sources": ["documents"]},
        as_of=datetime(2026, 8, 30, tzinfo=UTC),
        constraints={"approved_sources": ["documents"]},
        expected_delivery={"format": "markdown", "channel": "internal_export"},
    )
    with pytest.raises(TypeError):
        ResearchIntent(**{k: v for k, v in base_intent.items() if k != "audience_or_use"})
    with pytest.raises(ValueError):
        ResearchIntent(**{**base_intent, "audience_or_use": None})
    with pytest.raises(TypeError):
        ResearchIntent(**{k: v for k, v in base_intent.items() if k != "constraints"})
    with pytest.raises(ValueError):
        ResearchIntent(**{**base_intent, "constraints": None})

    with pytest.raises(TypeError):
        Inquiry(
            inquiry_id="inq-1",
            intent_ref="intent-1",
            question_or_hypothesis="is the signal real?",
            acceptance_conditions=("one source",),
            stop_conditions=("budget exhausted",),
        )
    with pytest.raises(ValueError):
        Inquiry(
            inquiry_id="inq-1",
            intent_ref="intent-1",
            question_or_hypothesis="is the signal real?",
            acceptance_conditions=("one source",),
            stop_conditions=("budget exhausted",),
            uncertainty_ceiling=None,
        )

    base_plan = dict(
        plan_id="plan-1",
        inquiry_ref="inq-1",
        work_items=(),
        budget={"hours": 8},
        deadline=datetime(2026, 8, 30, tzinfo=UTC),
        replan_policy={"authority": "human"},
    )
    with pytest.raises(TypeError):
        ResearchPlan(**{k: v for k, v in base_plan.items() if k != "replan_policy"})
    with pytest.raises(ValueError):
        ResearchPlan(**{**base_plan, "replan_policy": None})
    plan_with_null_deadline = ResearchPlan(
        **{k: v for k, v in base_plan.items() if k != "deadline"},
        deadline=None,
    )
    assert plan_with_null_deadline.deadline is None

    with pytest.raises(TypeError):
        SourceRef(
            source_ref_id="src-1",
            owner_id="project:documents",
            locator="documents:42",
            source_class="existing_document",
            observed_at=datetime(2026, 8, 30, tzinfo=UTC),
        )
    with pytest.raises(ValueError):
        SourceRef(
            source_ref_id="src-1",
            owner_id="project:documents",
            locator="documents:42",
            source_class="existing_document",
            access_profile_ref=None,
            observed_at=datetime(2026, 8, 30, tzinfo=UTC),
        )


def test_canonical_json_is_deterministic_and_sorted() -> None:
    left = {"b": 2, "a": [3, 1], "nested": {"z": None, "y": True}}
    right = {"nested": {"y": True, "z": None}, "b": 2, "a": [3, 1]}
    assert canonical_json(left) == canonical_json(right)
    assert canonical_json(left) == '{"a":[3,1],"b":2,"nested":{"y":true,"z":null}}'


def test_canonical_codec_refuses_default_str_coercion() -> None:
    with pytest.raises(UnsupportedCanonicalValueError):
        canonical_json({"blob": b"raw-bytes"})
    with pytest.raises(UnsupportedCanonicalValueError):
        canonical_json(object())
    for path in (
        ROOT / "app/successor_runtime/research/codec.py",
        ROOT / "app/successor_runtime/language/checksum.py",
    ):
        assert "default=str" not in path.read_text()


def test_material_ref_and_evidence_qualification_are_type_separated() -> None:
    material = make_material_ref()
    qualification = EvidenceQualification(
        qualification_id="eq-1",
        project_key="proj-a",
        material_ref=material.material_ref_id,
        inquiry_ref="inq-1",
        claim_ref=None,
        direction="SUPPORTS",
        scope_statement_ref="scope-1",
        uncertainty_profile_ref="uncertainty-1",
        verifier_profile_ref="verifier-1",
        provenance_closure_digest=DIGEST64,
        validity=Validity(valid_from=None, valid_to=None),
    )
    assert isinstance(material, MaterialRef)
    assert isinstance(qualification, EvidenceQualification)
    assert not isinstance(material, EvidenceQualification)
    assert not isinstance(qualification, MaterialRef)
    assert qualification.RELATION_STORAGE == "research_relations_only"
    assert qualification.DUPLICATE_RESEARCH_OBJECT_FORBIDDEN is True
    assert "EvidenceQualification.v1" in FIRST_SPECIMEN_RELATION_CONTRACT_REFS
    assert "EvidenceQualification.v1" not in FIRST_SPECIMEN_OBJECT_CONTRACT_REFS
    assert is_sha256_hex(material.content_digest)
    assert is_sha256_hex(material.provenance_digest)
    assert is_sha256_hex(qualification.qualification_digest)


def test_evidence_qualification_digest_is_direction_sensitive() -> None:
    base = dict(
        qualification_id="eq-1",
        project_key="proj-a",
        material_ref=make_material_ref().material_ref_id,
        inquiry_ref="inq-1",
        claim_ref=None,
        direction="SUPPORTS",
        scope_statement_ref="scope-1",
        uncertainty_profile_ref="uncertainty-1",
        verifier_profile_ref="verifier-1",
        provenance_closure_digest=DIGEST64,
        validity=Validity(valid_from=None, valid_to=None),
    )
    support = EvidenceQualification(**base)
    contradict = EvidenceQualification(**{**base, "direction": "CONTRADICTS"})
    assert support.qualification_digest != contradict.qualification_digest
    with pytest.raises(ValueError):
        EvidenceQualification(**{**base, "direction": "NOT_A_DIRECTION"})
    with pytest.raises(TypeError):
        EvidenceQualification(**{k: v for k, v in base.items() if k != "claim_ref"})
    with pytest.raises(ValueError):
        EvidenceQualification(**{**base, "material_ref": make_material_ref()})
    with pytest.raises(TypeError):
        EvidenceQualification(**{**base, "validity": "VALID"})


def test_delivery_attempt_runtime_fact_owner_is_separate_from_receipt() -> None:
    artifact = ResearchArtifact(
        artifact_id="artifact-1",
        content_ref="value:artifact-1",
        content_digest=None,
        claim_closure=("claim-1",),
        evidence_relation_closure=("eq-1",),
        citation_closure=("mat-1",),
        format="markdown",
        revision=1,
        lifecycle_state="ADMITTED",
    )
    delivery_intent = DeliveryIntent(
        delivery_intent_id="delivery-1",
        artifact_ref=artifact.artifact_id,
        audience="internal",
        channel="internal_export",
        format="markdown",
        approval_refs=("approval-1",),
        authority_digest=DIGEST64,
        idempotency_key="idem-1",
        irreversibility_profile="internal_content_addressed_export",
    )
    attempt = DeliveryAttempt(
        attempt_id="attempt-1",
        delivery_intent_ref=delivery_intent.delivery_intent_id,
        assignment_digest=DIGEST64,
        handler_binding_digest=DIGEST64,
        effect_disposition="SUCCEEDED",
    )
    receipt = DeliveryReceiptRef(
        receipt_ref="receipt-1",
        delivery_intent_ref=delivery_intent.delivery_intent_id,
        attempt_ref=attempt.attempt_id,
        provider_locator="internal://export/receipt-1",
        receipt_digest=DIGEST64,
        outcome_time=datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
    )
    contracts = {
        contract.object_type.type_id: contract
        for contract in build_first_specimen_object_contracts()
    }
    assert contracts["DeliveryAttempt.v1"].owner_mode == "RUNTIME_FACT"
    assert contracts["DeliveryAttempt.v1"].owner_binding_ref == "ExecutionJournal"
    assert contracts["DeliveryReceiptRef.v1"].owner_mode == "IMMUTABLE_EXTERNAL_REF"
    assert contracts["DeliveryReceiptRef.v1"].owner_binding_ref == "project_receipt_store"
    assert receipt.attempt_ref == attempt.attempt_id
    assert attempt.effect_disposition in EFFECT_DISPOSITIONS
    assert RELATION_CONTRACT_BY_ID["delivered_as.v1"].requires_authoritative_receipt
    with pytest.raises(ValueError):
        DeliveryAttempt(
            attempt_id="attempt-2",
            delivery_intent_ref="delivery-1",
            assignment_digest=DIGEST64,
            handler_binding_digest=DIGEST64,
            effect_disposition="MADE_UP",
        )


def test_research_object_ref_relation_and_provenance() -> None:
    claim_ref = ResearchObjectRef(
        object_id="claim-1",
        object_type=ObjectType("Claim.v1"),
        project_key="proj-a",
        owner_binding_ref="research-ledger",
        content_ref="value:claim-1",
        content_digest=DIGEST64,
        provenance_closure_digest=DIGEST64,
    )
    gap_ref = ResearchObjectRef(
        object_id="gap-1",
        object_type=ObjectType("Gap.v1"),
        project_key="proj-a",
        owner_binding_ref="research-ledger",
        content_ref="value:gap-1",
        content_digest=DIGEST64,
        provenance_closure_digest=DIGEST64,
    )
    relation = ResearchRelation(
        relation_id="rel-1",
        relation_type="derived_from",
        project_key="proj-a",
        source_ref=claim_ref,
        target_ref=gap_ref,
        provenance_closure_digest=DIGEST64,
    )
    assert is_sha256_hex(relation.relation_digest)
    closure = ProvenanceClosure(
        closure_id="prov-1",
        project_key="proj-a",
        entries=(ProvenanceEntry(entry_id="entry-1", object_ref=claim_ref),),
    )
    assert is_sha256_hex(closure.closure_digest)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    (
        ("object_id", ""),
        ("project_key", " "),
        ("owner_binding_ref", ""),
        ("content_ref", ""),
        ("content_digest", "not-a-digest"),
        ("provenance_closure_digest", "f" * 63),
        ("revision", 0),
        ("incarnation", "bad incarnation"),
        ("lifecycle_state", "UNKNOWN"),
    ),
)
def test_research_object_ref_rejects_invalid_identity_fields(
    field_name: str, invalid_value: object
) -> None:
    values = {
        "object_id": "claim-1",
        "object_type": ObjectType("Claim.v1"),
        "project_key": "proj-a",
        "revision": 1,
        "incarnation": "inc-1",
        "owner_binding_ref": "research-ledger",
        "content_ref": "value:claim-1",
        "content_digest": DIGEST64,
        "provenance_closure_digest": DIGEST64,
        "lifecycle_state": "ADMITTED",
    }
    values[field_name] = invalid_value
    with pytest.raises(ValueError):
        ResearchObjectRef(**values)


def test_domain_snapshot_matches_frozen_first_specimen() -> None:
    snapshot = build_first_specimen_domain_snapshot()
    assert snapshot.snapshot_id == FIRST_SPECIMEN_DOMAIN_SNAPSHOT_ID
    assert snapshot.snapshot_version == FIRST_SPECIMEN_DOMAIN_SNAPSHOT_VERSION
    assert snapshot.first_specimen_contract_ref == FIRST_SPECIMEN_CONTRACT_REF
    assert snapshot.object_contract_refs == (
        "ResearchIntent.v1",
        "Inquiry.v1",
        "ResearchPlan.v1",
        "SourceRef.v1",
        "MaterialRef.v1",
        "Claim.v1",
        "Gap.v1",
        "ResearchArtifact.v1",
        "DeliveryIntent.v1",
        "DeliveryAttempt.v1",
        "DeliveryReceiptRef.v1",
    )
    assert snapshot.relation_contract_refs == (
        "EvidenceQualification.v1",
        "derived_from.v1",
        "answers.v1",
        "opens.v1",
        "cites.v1",
        "supersedes.v1",
        "delivered_as.v1",
    )
    assert snapshot.operation_contract_refs == FIRST_SPECIMEN_OPERATION_KINDS
    assert is_sha256_hex(snapshot.snapshot_digest)
    with pytest.raises(FrozenInstanceError):
        snapshot.snapshot_version = "9"


def test_operation_contract_catalog_and_registry_resolve() -> None:
    bundle = build_first_specimen_bundle()
    catalog = build_first_specimen_catalog(bundle.operations)
    assert len(catalog.entries) == 6
    assert is_sha256_hex(catalog.catalog_digest)
    ref = catalog.lookup("delivery.internal_export.v1")
    assert ref is not None
    assert ref.kind == "delivery.internal_export.v1"
    assert catalog.requires("evidence.qualify.v1")
    assert not catalog.requires("no.such.kind.v1")
    registry = OperationContractRegistry(catalog, bundle.operations)
    resolved = registry.resolve_required(ref)
    assert isinstance(resolved, OperationContract)
    assert resolved.ref.contract_digest == ref.contract_digest
    missing = OperationContractRef("no.such.kind.v1", "1", "0" * 64)
    assert registry.resolve(missing) is None
    with pytest.raises(KeyError):
        registry.resolve_required(missing)


def test_operation_contract_catalog_indexes_multiple_versions_by_exact_ref() -> None:
    original = build_first_specimen_bundle().operations[0]
    successor = make_operation_contract(
        kind=original.ref.kind,
        contract_version="2.0.0",
        input_type=original.input_type,
        output_type=original.output_type,
        return_contract_ref=original.return_contract_ref,
        semantic_profile_ref=original.semantic_profile_ref,
        effect_profile_ref=original.effect_profile_ref,
        resource_profile_ref=original.resource_profile_ref,
        failure_profile_ref=original.failure_profile_ref,
        authority_profile_ref=original.authority_profile_ref,
        interpreter_compatibility_ref=original.interpreter_compatibility_ref,
        observation_profile_ref=original.observation_profile_ref,
        allowed_override_schema_ref=original.allowed_override_schema_ref,
        owner_capability_id=original.owner_capability_id,
    )
    contracts = (original, successor)
    catalog = OperationContractCatalogSnapshot(
        catalog_id="multi-version",
        catalog_version="1",
        entries=tuple(
            (
                contract.ref.kind,
                contract.ref.contract_version,
                contract.ref.contract_digest,
                contract.owner_capability_id,
            )
            for contract in contracts
        ),
    )
    registry = OperationContractRegistry(catalog, contracts)
    assert catalog.lookup(original.ref) == original.ref
    assert catalog.lookup(successor.ref) == successor.ref
    assert registry.resolve_required(original.ref) is original
    assert registry.resolve_required(successor.ref) is successor
    with pytest.raises(ValueError, match="ambiguous operation contract kind"):
        catalog.lookup(original.ref.kind)
    with pytest.raises(ValueError, match="ambiguous operation contract kind"):
        catalog.find(original.ref.kind)


def test_operation_contract_digest_mismatch_fails_closed() -> None:
    contract = build_first_specimen_bundle().operations[0]
    with pytest.raises(ValueError):
        OperationContract(
            ref=OperationContractRef(
                contract.ref.kind,
                contract.ref.contract_version,
                "0" * 64,
            ),
            input_type=contract.input_type,
            output_type=contract.output_type,
            return_contract_ref=contract.return_contract_ref,
            semantic_profile_ref=contract.semantic_profile_ref,
            effect_profile_ref=contract.effect_profile_ref,
            resource_profile_ref=contract.resource_profile_ref,
            failure_profile_ref=contract.failure_profile_ref,
            authority_profile_ref=contract.authority_profile_ref,
            interpreter_compatibility_ref=contract.interpreter_compatibility_ref,
            observation_profile_ref=contract.observation_profile_ref,
            allowed_override_schema_ref=contract.allowed_override_schema_ref,
            owner_capability_id=contract.owner_capability_id,
        )


def test_profiles_have_unified_refs_and_content_digests() -> None:
    from app.successor_runtime.language import profiles as language_profiles

    assert PROFILE_FAMILIES == (
        "SemanticProfile", "EffectProfile", "ResourceProfile",
        "FailureProfile", "AuthorityProfile", "InterpreterProfile",
    )
    for name in PROFILE_FAMILIES + ("ContractProfileRef", "ObservationProfile"):
        assert getattr(language_profiles, name) is getattr(capability_profiles, name)
    values = dict(
        semantic_profile_id="profile.semantic",
        semantic_profile_version="1",
        reads=("SourceRef.v1",),
        creates=("Claim.v1",),
        creates_relations=("EvidenceQualification.v1",),
        declared_loss=(),
        observation_profile_ref="profile.observation",
    )
    semantic = SemanticProfile(**values, profile_digest=content_digest(values))
    assert is_sha256_hex(semantic.profile_digest)
    assert isinstance(semantic.ref, ContractProfileRef)
    assert semantic.ref.to_ref_string() == "profile.semantic@1"
    changed_values = {**values, "reads": values["reads"] + ("Claim.v1",)}
    changed = SemanticProfile(
        **changed_values,
        profile_digest=content_digest(changed_values),
    )
    assert changed.profile_digest != semantic.profile_digest


def test_object_contracts_cover_frozen_owner_matrix() -> None:
    contracts = {
        contract.object_type.type_id: contract
        for contract in build_first_specimen_object_contracts()
    }
    assert set(contracts) == set(FIRST_SPECIMEN_OBJECT_CONTRACT_REFS)
    assert len(contracts) == 11
    assert contracts["ResearchIntent.v1"].owner_mode == "CANONICAL_OWNED"
    assert contracts["ResearchIntent.v1"].owner_binding_ref == "ResearchLedger"
    assert contracts["SourceRef.v1"].owner_mode == "IMMUTABLE_EXTERNAL_REF"
    assert contracts["MaterialRef.v1"].owner_mode == "IMMUTABLE_EXTERNAL_REF"
    assert contracts["ResearchArtifact.v1"].owner_binding_ref == (
        "ResearchLedger_plus_project_artifact_store"
    )
    assert "purpose" in contracts["ResearchIntent.v1"].required_fields
    for contract in contracts.values():
        assert is_sha256_hex(contract.contract_digest)


def test_object_contract_required_fields_match_frozen_snapshot() -> None:
    contracts = {
        contract.object_type.type_id: contract
        for contract in build_first_specimen_object_contracts()
    }
    assert contracts["ResearchIntent.v1"].required_fields == (
        "purpose",
        "audience_or_use",
        "scope",
        "as_of",
        "constraints",
        "expected_delivery",
    )
    assert contracts["Inquiry.v1"].required_fields == (
        "question_or_hypothesis",
        "acceptance_conditions",
        "stop_conditions",
        "uncertainty_ceiling",
    )
    assert contracts["ResearchPlan.v1"].required_fields == (
        "inquiry_ref",
        "ordered_or_partial_order_work",
        "budget",
        "deadline",
        "replan_policy",
    )
    assert contracts["SourceRef.v1"].required_fields == (
        "owner_id",
        "locator",
        "source_class",
        "access_profile",
        "observed_at",
    )
    intent_fields = {field.name for field in fields(ResearchIntent)}
    inquiry_fields = {field.name for field in fields(Inquiry)}
    plan_fields = {field.name for field in fields(ResearchPlan)}
    source_fields = {field.name for field in fields(SourceRef)}
    assert {"audience_or_use", "constraints"} <= intent_fields
    assert "uncertainty_ceiling" in inquiry_fields
    assert {"deadline", "replan_policy"} <= plan_fields
    assert "access_profile_ref" in source_fields


def test_successor_pure_core_has_no_forbidden_facility_or_legacy_imports() -> None:
    package_root = ROOT / "app" / "successor_runtime"
    forbidden = (
        "fastapi",
        "sqlalchemy",
        "celery",
        "redis",
        "settings",
        "app.services",
        "app.api",
        "app.models",
    )
    for pure_root in ("research", "language", "capabilities"):
        for path in (package_root / pure_root).rglob("*.py"):
            text = path.read_text().lower()
            for token in forbidden:
                assert token not in text, f"{path} references forbidden token {token}"


def test_claim_and_gap_require_frozen_scope_and_reopen_fields() -> None:
    with pytest.raises(ValueError):
        Claim(
            claim_id="claim-1",
            statement_ref="statement-1",
            support_relation_refs=(),
            contradiction_relation_refs=(),
            uncertainty_profile_ref="uncertainty-1",
            lifecycle_state="DRAFT",
            scope={},
        )
    with pytest.raises(ValueError):
        Gap(
            gap_id="gap-1",
            inquiry_ref="inquiry-1",
            requirement="evidence",
            reason="missing",
            closure_condition="material added",
            reopen_policy={},
            missing_evidence_or_decision="",
        )
