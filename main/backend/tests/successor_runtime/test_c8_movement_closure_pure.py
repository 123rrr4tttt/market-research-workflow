"""Pure C8 movement closure tests (strict v2 APIs)."""

from __future__ import annotations

import dataclasses
from types import MappingProxyType

import pytest

from app.services.typed_knowledge.contracts import (
    build_downstream_contract_draft,
    build_writing_knowledge_handoff,
)
from app.successor_migration.legacy_c8_writing import LegacyC8WritingAdapter
from app.successor_runtime.capabilities import c8_common as c8
from app.successor_runtime.capabilities import c8_consumer
from app.successor_runtime.capabilities.c8_consumer import (
    consume_graph_projection_test_only,
)
from app.successor_runtime.capabilities.c8_graph import (
    project_graph_occurrences,
    project_graph_occurrences_test_only,
)
from app.successor_runtime.capabilities.c8_report import (
    build_c8_research_artifact_candidate,
    build_report_admission_intent_v2,
    build_report_delivery_intent_v2,
    build_report_stage,
    confirm_report_admission_readback,
    confirm_report_admission_readback_test_only,
    prepare_report_export,
    research_artifact_from_candidate,
    verify_report_stage,
)
from app.successor_runtime.capabilities.c8_test_interpreter import (
    TestOnlyLossProfileRegistry,
    TestOnlyMaterialIssuanceRegistry,
    TestOnlyVerifierRegistry,
)
from app.successor_runtime.capabilities.c8_typed_knowledge import (
    StrictReadHandleRegistry,
    strict_issued_demand_read,
    strict_issued_demand_read_test_only,
)
from app.successor_runtime.capabilities.c8_writing import (
    LEGACY_CARD_METADATA_LOSS,
    compose_markdown_draft,
    compose_markdown_draft_test_only,
)
from app.successor_runtime.research.artifacts import artifact_exact_ref

from .p4_c8_fixture import PROJECT_KEY, legacy_item

FORMATION_PROFILE = c8.FormationProfile(
    profile_id="mrw.c8.formation.structured-material.v1",
    profile_version="1",
)


def _material(**overrides: object) -> c8.CanonicalMaterialRead:
    payload = {
        "title": "Robotics Market",
        "text": "机器人产品市场证据",
        "source": "captured-fixture",
    }
    values = {
        "material_identity": "material:p4-c8:001",
        "project_key": PROJECT_KEY,
        "candidate_id": "candidate:001",
        "document_identity": "doc:001",
        "head_revision": 1,
        "head_incarnation": "head-1",
        "head_closure_digest": "0" * 64,
        "value_revision": 1,
        "value_incarnation": "value-1",
        "value_digest": c8.c8_canonical_digest(payload),
        "snapshot_ref": "c7-snapshot:001",
        "provenance_digest": c8.c8_canonical_digest({"snapshot": "c7-snapshot:001"}),
        "structured_payload": payload,
    }
    values.update(overrides)
    return c8.CanonicalMaterialRead(**values)


def _candidate(material: c8.CanonicalMaterialRead) -> c8.TypedKnowledgeCandidate:
    return c8.form_typed_knowledge_candidate(
        material,
        formation_profile=FORMATION_PROFILE,
        candidate_id="knowledge-candidate:001",
        canonical_statement="机器人产品市场证据",
        primary_type_node_key="Topic",
        evidence_refs=("ev:1", "ev:2"),
    )


def _context() -> tuple:
    issuance = TestOnlyMaterialIssuanceRegistry()
    material = _material()
    capability = issuance.authorize()
    witness = issuance.register(material, capability)
    registry = StrictReadHandleRegistry(issuance)
    return issuance, witness, registry


def _read(
    context: tuple,
    *,
    material: c8.CanonicalMaterialRead | None = None,
    candidate: c8.TypedKnowledgeCandidate | None = None,
) -> c8.IssuedKnowledgeRead:
    _issuance, witness, registry = context
    material = material or _material()
    candidate = candidate or _candidate(material)
    return strict_issued_demand_read_test_only(
        material,
        witness,
        candidate,
        registry,
        fields=("canonical_statement", "evidence_refs"),
    )


def _citation(
    read: c8.IssuedKnowledgeRead,
    citation_id: str,
    position: int,
) -> c8.CitationRef:
    return c8.CitationRef(
        citation_id=citation_id,
        source_identity=read.handle.canonical_identity,
        source_digest=read.handle.canonical_digest,
        position=position,
        source_revision=read.handle.revision,
        source_incarnation=read.handle.incarnation,
        handle_id=read.handle.handle_id,
        fields_digest=read.handle.fields_digest,
    )


def _spec(citation_ceiling: int = 2) -> c8.WritingCompositionSpec:
    return c8.WritingCompositionSpec(
        project_key=PROJECT_KEY,
        base_revision=1,
        base_incarnation="value-1",
        byte_ceiling=4096,
        citation_ceiling=citation_ceiling,
    )


def test_strict_issued_demand_read_is_field_bounded() -> None:
    read = _read(_context())
    assert set(read.fields) == {"canonical_statement", "evidence_refs"}
    assert read.handle.canonical_identity == "material:p4-c8:001"
    assert read.handle.revision == 1
    assert read.handle.incarnation == "value-1"


def test_forged_handle_is_rejected() -> None:
    context = _context()
    registry = context[2]
    material = _material()
    candidate = _candidate(material)
    read = _read(context)
    other_context = _context()
    forged = strict_issued_demand_read_test_only(
        material,
        other_context[1],
        candidate,
        other_context[2],
        fields=("canonical_statement",),
    ).handle
    with pytest.raises(c8.UnavailableProjection, match="forged"):
        registry.resolve(forged, material=material, candidate=candidate)
    with pytest.raises(c8.C8ProjectionError, match="digest mismatch"):
        dataclasses.replace(read.handle, handle_id="0" * 64)
    with pytest.raises(c8.C8ProjectionError, match="digest mismatch"):
        dataclasses.replace(
            read,
            fields={"canonical_statement": "tampered"},
        )


def test_material_registration_requires_exact_entry_and_capability() -> None:
    context = _context()
    registry = context[2]
    material = _material()
    candidate = _candidate(material)
    unregistered = _material(material_identity="material:unregistered")
    with pytest.raises(c8.UnavailableProjection, match="not an issued exact registry"):
        registry.issue(
            material=unregistered,
            witness=context[1],
            candidate=candidate,
            domain="typed_knowledge",
            object_key="ki:robotics",
            fields=("canonical_statement",),
        )
    issuance = context[0]
    with pytest.raises(c8.C8ProjectionError, match="not authentic"):
        issuance.register(
            material,
            _FakeCapability(_secret=object()),
        )


class _FakeCapability:
    def __init__(self, *, _secret: object) -> None:
        self._secret = _secret


def test_stale_aba_project_and_head_drift_are_rejected() -> None:
    context = _context()
    registry = context[2]
    material = _material()
    candidate = _candidate(material)
    read = strict_issued_demand_read_test_only(
        material,
        context[1],
        candidate,
        registry,
        fields=("canonical_statement",),
    )
    stale_material = dataclasses.replace(
        material,
        value_revision=2,
        attestation_digest="",
    )
    with pytest.raises(c8.UnavailableProjection, match="drifted"):
        registry.resolve(
            read.handle,
            material=stale_material,
            candidate=dataclasses.replace(candidate, revision=2),
        )
    aba_material = dataclasses.replace(
        _material(),
        value_revision=2,
        value_incarnation="value-2",
        attestation_digest="",
    )
    with pytest.raises(c8.UnavailableProjection, match="drifted"):
        registry.resolve(
            read.handle,
            material=aba_material,
            candidate=dataclasses.replace(
                _candidate(aba_material),
                revision=2,
                incarnation="value-2",
            ),
        )
    project_material = dataclasses.replace(
        material,
        project_key="other-project",
        attestation_digest="",
    )
    with pytest.raises(c8.UnavailableProjection, match="drifted"):
        registry.resolve(
            read.handle,
            material=project_material,
            candidate=candidate,
        )
    head_drift = dataclasses.replace(
        material,
        head_revision=2,
        attestation_digest="",
    )
    with pytest.raises(c8.UnavailableProjection, match="drifted"):
        registry.resolve(
            read.handle,
            material=head_drift,
            candidate=candidate,
        )


def test_issued_read_fields_are_immutable_and_read_digest_full() -> None:
    read = _read(_context())
    with pytest.raises(TypeError):
        read.fields["canonical_statement"] = "tampered"
    mutable = dict(read.fields)
    constructed = c8.IssuedKnowledgeRead(
        handle=read.handle,
        candidate=read.candidate,
        fields=mutable,
    )
    mutable["canonical_statement"] = "tampered"
    assert constructed.fields["canonical_statement"] == "机器人产品市场证据"
    expected_digest = c8.c8_canonical_digest(
        {
            "handle_id": constructed.handle.handle_id,
            "candidate_digest": constructed.candidate.candidate_digest,
            "fields": [
                (name, constructed.fields[name]) for name in sorted(constructed.fields)
            ],
        }
    )
    assert constructed.read_digest == expected_digest


def test_deep_freeze_rejects_unsupported_and_non_string_keys() -> None:
    with pytest.raises(TypeError, match="string mapping keys"):
        c8.c8_canonical_digest({1: "value"})
    with pytest.raises(TypeError, match="finite"):
        c8.c8_canonical_digest({"value": float("nan")})
    with pytest.raises(TypeError, match="unsupported"):
        c8.c8_canonical_digest({"value": {"nested": object()}})


def test_material_payload_deep_freeze_and_value_digest_recompute() -> None:
    payload = {"nested": {"x": 1}, "items": [1, 2]}
    material = c8.CanonicalMaterialRead(
        **{
            **_material_payload_values(),
            "structured_payload": payload,
            "value_digest": c8.c8_canonical_digest(payload),
        }
    )
    assert isinstance(material.structured_payload, MappingProxyType)
    assert isinstance(material.structured_payload["items"], tuple)
    payload["nested"]["x"] = 99
    payload["items"].append(3)
    assert material.structured_payload["nested"]["x"] == 1
    assert material.structured_payload["items"] == (1, 2)
    with pytest.raises(TypeError):
        material.structured_payload["nested"]["x"] = 99
    with pytest.raises(TypeError):
        material.structured_payload["items"][0] = 99
    assert material.value_digest == c8.canonical_material_digest(material)
    assert c8.validate_canonical_material(material) is material
    with pytest.raises(c8.C8ProjectionError, match="value digest"):
        dataclasses.replace(
            material,
            value_digest="1" * 64,
            attestation_digest="",
        )
    with pytest.raises(TypeError, match="string mapping keys"):
        c8.CanonicalMaterialRead(
            **{
                **_material_payload_values(),
                "structured_payload": {1: "x"},
                "value_digest": "",
            }
        )
    with pytest.raises(TypeError, match="finite"):
        c8.CanonicalMaterialRead(
            **{
                **_material_payload_values(),
                "structured_payload": {"v": float("inf")},
                "value_digest": "",
            }
        )
    with pytest.raises(TypeError, match="unsupported"):
        c8.CanonicalMaterialRead(
            **{
                **_material_payload_values(),
                "structured_payload": {"v": object()},
                "value_digest": "",
            }
        )


def _material_payload_values() -> dict[str, object]:
    return {
        "material_identity": "material:p4-c8:001",
        "project_key": PROJECT_KEY,
        "candidate_id": "candidate:001",
        "document_identity": "doc:001",
        "head_revision": 1,
        "head_incarnation": "head-1",
        "head_closure_digest": "0" * 64,
        "value_revision": 1,
        "value_incarnation": "value-1",
        "snapshot_ref": "c7-snapshot:001",
        "provenance_digest": c8.c8_canonical_digest({"snapshot": "c7-snapshot:001"}),
    }


def test_registry_no_overwrite_and_duplicate_idempotency() -> None:
    issuance = TestOnlyMaterialIssuanceRegistry()
    material = _material()
    capability = issuance.authorize()
    first = issuance.register(material, capability)
    second = issuance.register(material, capability)
    assert first is second
    other = dataclasses.replace(material, value_revision=2, attestation_digest="")
    with pytest.raises(c8.C8ProjectionError, match="rebinding"):
        issuance.register(other, capability)


def test_citation_order_removal_duplicate_and_conflict() -> None:
    refs = (
        c8.CitationRef("c:1", "source:1", "0" * 64, 1),
        c8.CitationRef("c:2", "source:2", "0" * 64, 2),
        c8.CitationRef("c:1", "source:1", "0" * 64, 3),
    )
    with pytest.raises(c8.C8ProjectionError, match="duplicate citation"):
        c8.validate_citation_closure(c8.CitationClosure(refs))
    collapsed, dropped = c8.collapse_duplicate_citations(c8.CitationClosure(refs))
    assert [ref.citation_id for ref in collapsed.refs] == ["c:1", "c:2"]
    assert dropped == ("c:1",)
    bad_order = (
        c8.CitationRef("c:1", "source:1", "0" * 64, 2),
        c8.CitationRef("c:2", "source:2", "0" * 64, 3),
    )
    with pytest.raises(c8.C8ProjectionError, match="contiguous"):
        c8.validate_citation_closure(c8.CitationClosure(bad_order))
    conflicting = (
        c8.CitationRef("c:1", "source:1", "0" * 64, 1),
        c8.CitationRef("c:1", "source:other", "0" * 64, 2),
    )
    with pytest.raises(c8.C8ProjectionError, match="conflicting citation"):
        c8.validate_citation_closure(c8.CitationClosure(conflicting))


def test_markdown_draft_preserves_citations_and_declares_legacy_loss() -> None:
    read = _read(_context())
    closure = c8.CitationClosure(
        (
            _citation(read, "ev:1", 1),
            _citation(read, "ev:2", 2),
        )
    )
    artifact = compose_markdown_draft_test_only(
        artifact_id="draft:001",
        reads=(read,),
        citation_closure=closure,
        spec=_spec(),
    )
    assert artifact.artifact_digest == c8.research_draft_artifact_digest(artifact)
    assert b"1. ev:1 (material:p4-c8:001)" in artifact.markdown_bytes
    assert artifact.provenance_closure[0].identity == "material:p4-c8:001"
    assert artifact.provenance_closure[0].fields_digest == read.handle.fields_digest
    assert set(LEGACY_CARD_METADATA_LOSS) == set(artifact.declared_legacy_metadata_loss)


def test_citation_must_bind_exact_issued_read() -> None:
    read = _read(_context())
    other_material = _material(material_identity="material:other")
    other_issuance = TestOnlyMaterialIssuanceRegistry()
    other_witness = other_issuance.register(
        other_material,
        other_issuance.authorize(),
    )
    other_registry = StrictReadHandleRegistry(other_issuance)
    other_read = strict_issued_demand_read_test_only(
        other_material,
        other_witness,
        _candidate(other_material),
        other_registry,
        fields=("canonical_statement", "evidence_refs"),
    )
    closure = c8.CitationClosure(
        (
            c8.CitationRef(
                citation_id="ev:1",
                source_identity=other_read.handle.canonical_identity,
                source_digest=other_read.handle.canonical_digest,
                position=1,
                source_revision=other_read.handle.revision,
                source_incarnation=other_read.handle.incarnation,
                handle_id=other_read.handle.handle_id,
                fields_digest=other_read.handle.fields_digest,
            ),
            _citation(read, "ev:2", 2),
        )
    )
    with pytest.raises(c8.UnavailableProjection, match="not an issued read"):
        compose_markdown_draft_test_only(
            artifact_id="draft:bad",
            reads=(read,),
            citation_closure=closure,
            spec=_spec(),
        )


def test_production_writing_rejects_test_only_read() -> None:
    read = _read(_context())
    closure = c8.CitationClosure((_citation(read, "ev:1", 1),))
    with pytest.raises(c8.UnavailableProjection, match="TEST_ONLY"):
        compose_markdown_draft(
            artifact_id="draft:prod",
            reads=(read,),
            citation_closure=closure,
            spec=c8.WritingCompositionSpec(
                project_key=PROJECT_KEY,
                base_revision=1,
                base_incarnation="value-1",
                byte_ceiling=4096,
                citation_ceiling=1,
            ),
        )


def test_report_authority_separation_and_state_variants() -> None:
    read = _read(_context())
    closure = c8.CitationClosure(
        (
            _citation(read, "ev:1", 1),
            _citation(read, "ev:2", 2),
        )
    )
    artifact = compose_markdown_draft_test_only(
        artifact_id="draft:001",
        reads=(read,),
        citation_closure=closure,
        spec=_spec(),
    )
    stage = build_report_stage(
        stage_id="stage:001",
        project_key=PROJECT_KEY,
        artifact=artifact,
        citation_closure=closure,
    )
    assert stage.authority == "stage_no_admission"
    verification = verify_report_stage(
        stage,
        citation_closure=closure,
        artifact=artifact,
    )
    assert verification.state == "VERIFIED"
    admission = build_report_admission_intent_v2(verification)
    verifier_registry = TestOnlyVerifierRegistry()
    verification_witness = verifier_registry.register(
        verification,
        verifier_registry.authorize(),
    )
    stamped = verifier_registry.resolve(verification.verification_id)
    readback = confirm_report_admission_readback_test_only(
        admission,
        witness=verification_witness,
        verifier_registry=verifier_registry,
        verification=stamped,
    )
    assert readback.state == "ADMITTED"
    preparation = prepare_report_export(readback)
    assert preparation.state == "PREPARED"
    delivery = build_report_delivery_intent_v2(
        preparation,
        approval_digest="0" * 64,
        approval_epoch=1,
    )
    assert delivery.state == "APPROVED"
    with pytest.raises(c8.UnavailableProjection, match="external delivery"):
        build_report_delivery_intent_v2(
            preparation,
            approval_digest="0" * 64,
            approval_epoch=1,
            external=True,
        )
    with pytest.raises(c8.UnavailableProjection, match="approval digest"):
        build_report_delivery_intent_v2(
            preparation,
            approval_digest="",
            approval_epoch=1,
        )
    unverified = c8.ReportVerification(
        verification_id="verification:unverified",
        stage_id=stage.stage_id,
        project_key=PROJECT_KEY,
        artifact_digest=stage.artifact_digest,
        citation_closure_digest="0" * 64,
        state="UNVERIFIED",
        failure_reason="not verified",
    )
    with pytest.raises(c8.UnavailableProjection, match="verified"):
        build_report_admission_intent_v2(unverified)


def _occurrence(
    occurrence_id: str,
    *,
    source: str = "source:1",
    target: str = "target:1",
    position: int = 1,
    edge_type: str = "references",
) -> c8.GraphOccurrence:
    occurrence = c8.GraphOccurrence(
        occurrence_id=occurrence_id,
        edge_type=edge_type,
        source_identity=source,
        target_identity=target,
        position=position,
    )
    return dataclasses.replace(
        occurrence,
        occurrence_digest=c8.graph_occurrence_digest(occurrence),
    )


def _loss_context() -> tuple:
    profile = c8.GraphLossProfile(
        profile_id="mrw.c8.graph-loss.v1",
        filter=("blocked",),
        truncation=("long",),
        redaction=("secret",),
        casefold=True,
        duplicate_collapse=True,
        omitted_fields=("internal_note",),
    )
    registry = TestOnlyLossProfileRegistry()
    witness = registry.register(profile, registry.authorize())
    return profile, registry, witness


def test_graph_occurrence_collision_and_loss_profile() -> None:
    profile, registry, witness = _loss_context()
    with pytest.raises(c8.C8ProjectionError, match="collision"):
        project_graph_occurrences_test_only(
            generation_id="gen:1",
            project_key=PROJECT_KEY,
            occurrences=(_occurrence("o:1"), _occurrence("o:1")),
            loss_profile=profile,
            loss_profile_registry=registry,
            loss_witness=witness,
            provenance_digest="0" * 64,
        )
    varied = (
        _occurrence("o:1"),
        _occurrence("o:2", source="SOURCE:1", target="TARGET:1"),
        _occurrence("o:3", edge_type="blocked"),
        _occurrence("o:4", edge_type="long", position=2),
        _occurrence("o:5"),
        _occurrence("o:6", edge_type="secret"),
    )
    generation = project_graph_occurrences_test_only(
        generation_id="gen:1",
        project_key=PROJECT_KEY,
        occurrences=varied,
        loss_profile=profile,
        loss_profile_registry=registry,
        loss_witness=witness,
        provenance_digest="0" * 64,
    )
    loss_text = "\n".join(generation.declared_loss)
    assert "filter:blocked:o:3" in loss_text
    assert "truncation:long:o:4" in loss_text
    assert "casefold:o:2" in loss_text
    assert "redaction:o:6" in loss_text
    assert "duplicate_collapse:o:5" in loss_text
    assert "omitted_field:internal_note" in loss_text
    assert {occ.occurrence_id for occ in generation.occurrences} == {"o:1", "o:6"}


def test_consumer_preserves_provenance_and_never_synthesizes() -> None:
    profile, registry, witness = _loss_context()
    generation = project_graph_occurrences_test_only(
        generation_id="gen:1",
        project_key=PROJECT_KEY,
        occurrences=(_occurrence("o:1"),),
        loss_profile=profile,
        loss_profile_registry=registry,
        loss_witness=witness,
        provenance_digest="0" * 64,
    )
    result = consume_graph_projection_test_only(
        consumer_id="consumer:1",
        projection=generation,
        project_key=PROJECT_KEY,
        active_generation_id="gen:1",
        active_offset="0",
        active_provenance_digest="0" * 64,
    )
    assert result.state == "AVAILABLE"
    assert result.declared_loss == generation.declared_loss
    assert result.provider_calls == 0
    assert result.store_writes == 0
    assert result.export_calls == 0
    with pytest.raises(c8.C8ProjectionError, match="never creates claim"):
        consume_graph_projection_test_only(
            consumer_id="consumer:1",
            projection=generation,
            project_key=PROJECT_KEY,
            active_generation_id="gen:1",
            active_offset="0",
            active_provenance_digest="0" * 64,
            request_claim_support=True,
        )
    with pytest.raises(c8.C8ProjectionError, match="stale graph generation"):
        consume_graph_projection_test_only(
            consumer_id="consumer:1",
            projection=generation,
            project_key=PROJECT_KEY,
            active_generation_id="gen:stale",
            active_offset="0",
            active_provenance_digest="0" * 64,
        )


def test_production_consumer_rejects_test_only_active_handle() -> None:
    profile, registry, witness = _loss_context()
    generation = project_graph_occurrences_test_only(
        generation_id="gen:1",
        project_key=PROJECT_KEY,
        occurrences=(_occurrence("o:1"),),
        loss_profile=profile,
        loss_profile_registry=registry,
        loss_witness=witness,
        provenance_digest="0" * 64,
    )
    handle = _ActiveReadHandle(
        generation_id="gen:1",
        offset="0",
        provenance_digest="0" * 64,
    )
    with pytest.raises(c8.C8ProjectionError, match="TEST_ONLY"):
        c8_consumer.consume_graph_projection(
            consumer_id="consumer:1",
            projection=generation,
            project_key=PROJECT_KEY,
            active_read_handle=handle,
        )


class _ActiveReadHandle(c8.TestOnlySealedValue):
    def __init__(
        self, *, generation_id: str, offset: str, provenance_digest: str
    ) -> None:
        self.generation_id = generation_id
        self.offset = offset
        self.provenance_digest = provenance_digest


def test_self_signed_material_verifier_and_loss_rejected_by_production() -> None:
    context = _context()
    material = _material()
    candidate = _candidate(material)
    with pytest.raises(c8.UnavailableProjection, match="TEST_ONLY"):
        strict_issued_demand_read(
            material,
            context[1],
            candidate,
            context[2],
            fields=("canonical_statement",),
        )
    read = _read(context)
    closure = c8.CitationClosure(
        (
            _citation(read, "ev:1", 1),
            _citation(read, "ev:2", 2),
        )
    )
    artifact = compose_markdown_draft_test_only(
        artifact_id="draft:001",
        reads=(read,),
        citation_closure=closure,
        spec=_spec(),
    )
    stage = build_report_stage(
        stage_id="stage:001",
        project_key=PROJECT_KEY,
        artifact=artifact,
        citation_closure=closure,
    )
    verification = verify_report_stage(
        stage,
        citation_closure=closure,
        artifact=artifact,
    )
    verifier_registry = TestOnlyVerifierRegistry()
    verification_witness = verifier_registry.register(
        verification,
        verifier_registry.authorize(),
    )
    stamped = verifier_registry.resolve(verification.verification_id)
    with pytest.raises(c8.UnavailableProjection, match="TEST_ONLY"):
        confirm_report_admission_readback(
            build_report_admission_intent_v2(stamped),
            witness=verification_witness,
            verifier_registry=verifier_registry,
            verification=stamped,
        )
    profile, registry, witness = _loss_context()
    with pytest.raises(c8.C8ProjectionError, match="TEST_ONLY"):
        project_graph_occurrences(
            generation_id="gen:1",
            project_key=PROJECT_KEY,
            occurrences=(_occurrence("o:1"),),
            loss_profile=profile,
            loss_profile_registry=registry,
            loss_witness=witness,
            provenance_digest="0" * 64,
        )


def test_legacy_card_metadata_loss_named_observation() -> None:
    item = legacy_item()
    contract = build_downstream_contract_draft(item)
    handoff = build_writing_knowledge_handoff(
        contract,
        selection_hash="selection:robotics",
        selection_text="robotics investment",
    )
    observation = LegacyC8WritingAdapter().build_card_observation(
        handoff,
        normalized_query="robotics investment",
    )
    assert observation["retrieved_at"] == "non_deterministic_excluded"
    assert all(
        name in LEGACY_CARD_METADATA_LOSS
        for name in ("legacy_score", "legacy_wall_clock_retrieved_at")
    )


def test_research_artifact_candidate_adapter_is_deterministic_and_closed() -> None:
    read = _read(_context())
    closure = c8.CitationClosure(
        (
            _citation(read, "ev:1", 1),
            _citation(read, "ev:2", 2),
        )
    )
    draft = compose_markdown_draft_test_only(
        artifact_id="draft:001",
        reads=(read,),
        citation_closure=closure,
        spec=_spec(),
    )
    stage = build_report_stage(
        stage_id="stage:001",
        project_key=PROJECT_KEY,
        artifact=draft,
        citation_closure=closure,
    )
    verification = verify_report_stage(
        stage,
        citation_closure=closure,
        artifact=draft,
    )
    candidate = build_c8_research_artifact_candidate(
        candidate_id="artifact:001",
        draft=draft,
        verification=verification,
        markdown_ref="project-value:markdown:001",
        markdown_digest="0" * 64,
        provenance_digest="0" * 64,
    )
    assert candidate.claim_closure == ()
    assert candidate.evidence_relation_closure == ()
    assert candidate.citation_closure == ("ev:1", "ev:2")
    assert candidate.source_base_revision == 1
    assert candidate.source_base_incarnation == "value-1"
    assert candidate.canonical_revision == 1
    assert candidate.canonical_incarnation == "research-artifact-1"
    assert candidate.payload_digest
    second = build_c8_research_artifact_candidate(
        candidate_id="artifact:001",
        draft=draft,
        verification=verification,
        markdown_ref="project-value:markdown:001",
        markdown_digest="0" * 64,
        provenance_digest="0" * 64,
    )
    assert second == candidate
    artifact = research_artifact_from_candidate(candidate)
    assert artifact.format == "markdown"
    assert artifact_exact_ref(artifact)

    with pytest.raises(c8.UnavailableProjection, match="verified"):
        build_c8_research_artifact_candidate(
            candidate_id="artifact:bad",
            draft=draft,
            verification=c8.ReportVerification(
                verification_id="v:unverified",
                stage_id=stage.stage_id,
                project_key=PROJECT_KEY,
                artifact_digest=stage.artifact_digest,
                citation_closure_digest="0" * 64,
                state="UNVERIFIED",
            ),
            markdown_ref="project-value:markdown:001",
            markdown_digest="0" * 64,
            provenance_digest="0" * 64,
        )
    with pytest.raises(c8.UnavailableProjection, match="stale"):
        build_c8_research_artifact_candidate(
            candidate_id="artifact:bad",
            draft=draft,
            verification=c8.ReportVerification(
                verification_id="v:stale",
                stage_id="s:1",
                project_key=PROJECT_KEY,
                artifact_digest="1" * 64,
                citation_closure_digest="0" * 64,
                state="VERIFIED",
            ),
            markdown_ref="project-value:markdown:001",
            markdown_digest="0" * 64,
            provenance_digest="0" * 64,
        )
    with pytest.raises(c8.UnavailableProjection, match="cross-project"):
        build_c8_research_artifact_candidate(
            candidate_id="artifact:bad",
            draft=draft,
            verification=c8.ReportVerification(
                verification_id="v:cross",
                stage_id=stage.stage_id,
                project_key="other-project",
                artifact_digest=stage.artifact_digest,
                citation_closure_digest="0" * 64,
                state="VERIFIED",
            ),
            markdown_ref="project-value:markdown:001",
            markdown_digest="0" * 64,
            provenance_digest="0" * 64,
        )
    with pytest.raises(c8.UnavailableProjection, match="TEST_ONLY"):
        build_c8_research_artifact_candidate(
            candidate_id="artifact:bad",
            draft=draft,
            verification=verification,
            markdown_ref="project-value:markdown:001",
            markdown_digest="0" * 64,
            provenance_digest="0" * 64,
            witness=read.witness_marker,
        )
