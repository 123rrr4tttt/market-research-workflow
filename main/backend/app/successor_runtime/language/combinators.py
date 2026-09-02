"""Program combinators and the first-specimen builder."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.successor_runtime.research.claims import Gap
from app.successor_runtime.research.codec import sha256_hex as research_sha256_hex
from app.successor_runtime.research.inquiries import Inquiry, PlanWorkItem, ResearchPlan
from app.successor_runtime.research.object_types import (
    CAPTURED_MATERIAL_SNAPSHOT_TYPE,
    DELIVERY_INTENT_TYPE,
    DELIVERY_RECEIPT_REF_TYPE,
    EVIDENCE_QUALIFICATION_TYPE,
    GAP_TYPE,
    INQUIRY_TYPE,
    MATERIAL_REF_TYPE,
    RESEARCH_ARTIFACT_TYPE,
    RESEARCH_INTENT_TYPE,
    RESEARCH_PLAN_TYPE,
    SOURCE_REF_TYPE,
)
from app.successor_runtime.research.sources import SourceRef

from .algebra import (
    AlgebraRef,
    FrozenJsonObject,
    ObjectType,
    OperationContractCatalogSnapshot,
    OperationContractRef,
    OperationSpec,
    ValueRef,
    canonical_digest,
    freeze_json_object,
)
from .program import (
    DecisionBranch,
    ProgramNode,
    ProgramSpec,
    SuccessorMaterialization,
    atom_node,
    content_addressed_literal,
    decide_node,
    identity_node,
    map_output_node,
    pure_node,
    then_node,
    traverse_ordered_node,
    zip_ordered_node,
)
from .transforms import (
    DiscriminatorRef,
    MergeRef,
    TransformRef,
    TransformRegistry,
)

PROGRAM_CONTRACT_VERSION = "mrw.functorial-successor.program-spec.v1"
FIRST_SPECIMEN_SEMANTIC_IDENTITY = "first-document-ref-to-internal-delivery"


@dataclass(frozen=True, slots=True)
class Registries:
    transforms: TransformRegistry
    merges: TransformRegistry
    discriminators: TransformRegistry


def _material_ref_merge(
    left: Any,
    right: Any,
) -> dict:
    return {"materials": [left, right]}


def _material_to_qualification_input(material: Any) -> dict:
    return {
        "material_ref": material,
        "inquiry_ref": "inquiry:first-specimen",
    }


def _qualification_pair_merge(left: Any, right: Any) -> dict:
    return {"evidence_qualifications": [left, right]}


def _claim_outcome_transform(outcome: Any) -> dict:
    return dict(outcome)


def _outcome_discriminator(outcome: Any) -> str:
    if outcome.get("kind") == "claim":
        return "claim"
    return "gap"


def _artifact_to_delivery_intent(artifact: Any) -> dict:
    return {
        "delivery_intent_id": "delivery-intent:first-specimen",
        "artifact_ref": artifact,
        "audience": "internal-review",
        "channel": "internal_export",
        "format": "markdown",
        "approval_refs": ["approval:human:first-specimen"],
        "authority_digest": "0" * 64,
        "idempotency_key": "first-specimen-internal-export",
        "irreversibility_profile": "internal_content_addressed_export",
    }


def default_registries() -> Registries:
    transforms = TransformRegistry(
        registry_id="mrw.successor.first_specimen.transforms.v1",
        registry_version="1",
    )
    merges = TransformRegistry(
        registry_id="mrw.successor.first_specimen.merges.v1",
        registry_version="1",
    )
    discriminators = TransformRegistry(
        registry_id="mrw.successor.first_specimen.discriminators.v1",
        registry_version="1",
    )
    return Registries(
        transforms=transforms,
        merges=merges,
        discriminators=discriminators,
    )


def register_first_specimen_transforms(
    registries: Registries,
    *,
    material_ref_type: ObjectType,
    evidence_bundle_type: ObjectType,
    outcome_type: ObjectType,
    program_output_type: ObjectType,
) -> "tuple[TransformRef, ...]":
    merge_ref = registries.merges.register_merge(
        name="mrw.first_specimen.material_merge",
        version="1",
        left_type=material_ref_type,
        right_type=material_ref_type,
        output_type=evidence_bundle_type,
        func=_material_ref_merge,
    )
    claim_ref = registries.transforms.register_transform(
        name="mrw.first_specimen.claim_to_delivery",
        version="1",
        input_type=outcome_type,
        output_type=program_output_type,
        func=_claim_outcome_transform,
    )
    gap_ref = registries.transforms.register_transform(
        name="mrw.first_specimen.gap_branch",
        version="1",
        input_type=outcome_type,
        output_type=program_output_type,
        func=_claim_outcome_transform,
    )
    return (claim_ref, gap_ref, merge_ref)


def _metadata(value: "dict[str, Any] | None") -> FrozenJsonObject:
    return freeze_json_object(value or {})


def _spec(
    *,
    root: ProgramNode,
    program_id: str,
    project_key: str,
    project_scope_digest: str,
    semantic_identity: str,
    observation_profile: str,
    contract_version: str,
    project_registry_revision: int,
    metadata: FrozenJsonObject,
    algebra_refs: "tuple[AlgebraRef, ...]",
    transform_refs: "tuple[TransformRef, ...]",
) -> ProgramSpec:
    return ProgramSpec(
        program_id=program_id,
        contract_version=contract_version,
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        semantic_identity=semantic_identity,
        input_type=root.input_type,
        output_type=root.output_type,
        root=root,
        algebra_refs=algebra_refs,
        transform_refs=transform_refs,
        observation_profile=observation_profile,
        metadata=metadata,
        program_digest="",
    ).with_digest()


def _common(
    *,
    root: ProgramNode,
    program_id: str,
    project_key: str,
    project_scope_digest: str,
    semantic_identity: str,
    observation_profile: str,
    contract_version: str,
    project_registry_revision: int,
    metadata: "dict[str, Any] | None",
    transform_refs: "tuple[TransformRef, ...]",
) -> ProgramSpec:
    return _spec(
        root=root,
        program_id=program_id,
        project_key=project_key,
        project_scope_digest=project_scope_digest,
        semantic_identity=semantic_identity,
        observation_profile=observation_profile,
        contract_version=contract_version,
        project_registry_revision=project_registry_revision,
        metadata=_metadata(metadata),
        algebra_refs=(
            AlgebraRef(
                algebra_id="mrw.successor.language.algebra",
                algebra_version="1",
            ),
        ),
        transform_refs=transform_refs,
    )


def identity_program(
    object_type: ObjectType,
    *,
    program_id: str,
    project_key: str,
    project_scope_digest: str,
    semantic_identity: str,
    observation_profile: str,
    contract_version: str = PROGRAM_CONTRACT_VERSION,
    project_registry_revision: int = 1,
    metadata: "dict[str, Any] | None" = None,
) -> ProgramSpec:
    return _common(
        root=identity_node(object_type),
        program_id=program_id,
        project_key=project_key,
        project_scope_digest=project_scope_digest,
        semantic_identity=semantic_identity,
        observation_profile=observation_profile,
        contract_version=contract_version,
        project_registry_revision=project_registry_revision,
        metadata=metadata,
        transform_refs=(),
    )


def pure_program(
    input_type: ObjectType,
    output_type: ObjectType,
    literal_value: Any,
    literal_codec: str,
    *,
    program_id: str,
    project_key: str,
    project_scope_digest: str,
    semantic_identity: str,
    observation_profile: str,
    contract_version: str = PROGRAM_CONTRACT_VERSION,
    project_registry_revision: int = 1,
    metadata: "dict[str, Any] | None" = None,
) -> ProgramSpec:
    root = pure_node(
        input_type=input_type,
        output_type=output_type,
        literal_value=literal_value,
        literal_codec=literal_codec,
    )
    return _common(
        root=root,
        program_id=program_id,
        project_key=project_key,
        project_scope_digest=project_scope_digest,
        semantic_identity=semantic_identity,
        observation_profile=observation_profile,
        contract_version=contract_version,
        project_registry_revision=project_registry_revision,
        metadata=metadata,
        transform_refs=(),
    )


def atom_program(
    operation: OperationSpec,
    *,
    input_type: ObjectType,
    output_type: ObjectType,
    program_id: str,
    project_key: str,
    project_scope_digest: str,
    semantic_identity: str,
    observation_profile: str,
    contract_version: str = PROGRAM_CONTRACT_VERSION,
    project_registry_revision: int = 1,
    metadata: "dict[str, Any] | None" = None,
    transform_refs: "tuple[TransformRef, ...]" = (),
) -> ProgramSpec:
    root = atom_node(operation, input_type=input_type, output_type=output_type)
    return _common(
        root=root,
        program_id=program_id,
        project_key=project_key,
        project_scope_digest=project_scope_digest,
        semantic_identity=semantic_identity,
        observation_profile=observation_profile,
        contract_version=contract_version,
        project_registry_revision=project_registry_revision,
        metadata=metadata,
        transform_refs=transform_refs,
    )


def then_program(
    first: ProgramSpec,
    second: ProgramSpec,
    *,
    program_id: str,
    project_key: str,
    project_scope_digest: str,
    semantic_identity: str,
    observation_profile: str,
    contract_version: str = PROGRAM_CONTRACT_VERSION,
    project_registry_revision: int = 1,
    metadata: "dict[str, Any] | None" = None,
) -> ProgramSpec:
    root = then_node(first.root, second.root)
    return _common(
        root=root,
        program_id=program_id,
        project_key=project_key,
        project_scope_digest=project_scope_digest,
        semantic_identity=semantic_identity,
        observation_profile=observation_profile,
        contract_version=contract_version,
        project_registry_revision=project_registry_revision,
        metadata=metadata,
        transform_refs=first.transform_refs + second.transform_refs,
    )


def map_output_program(
    source: ProgramSpec,
    transform_ref: TransformRef,
    target_type: ObjectType,
    *,
    program_id: str,
    project_key: str,
    project_scope_digest: str,
    semantic_identity: str,
    observation_profile: str,
    contract_version: str = PROGRAM_CONTRACT_VERSION,
    project_registry_revision: int = 1,
    metadata: "dict[str, Any] | None" = None,
) -> ProgramSpec:
    root = map_output_node(source.root, transform_ref, target_type)
    return _common(
        root=root,
        program_id=program_id,
        project_key=project_key,
        project_scope_digest=project_scope_digest,
        semantic_identity=semantic_identity,
        observation_profile=observation_profile,
        contract_version=contract_version,
        project_registry_revision=project_registry_revision,
        metadata=metadata,
        transform_refs=source.transform_refs + (transform_ref,),
    )


def zip_ordered_program(
    left: ProgramSpec,
    right: ProgramSpec,
    merge_ref: MergeRef,
    output_type: ObjectType,
    *,
    program_id: str,
    project_key: str,
    project_scope_digest: str,
    semantic_identity: str,
    observation_profile: str,
    contract_version: str = PROGRAM_CONTRACT_VERSION,
    project_registry_revision: int = 1,
    metadata: "dict[str, Any] | None" = None,
) -> ProgramSpec:
    root = zip_ordered_node(left.root, right.root, merge_ref)
    return _spec(
        root=root,
        program_id=program_id,
        project_key=project_key,
        project_scope_digest=project_scope_digest,
        semantic_identity=semantic_identity,
        observation_profile=observation_profile,
        contract_version=contract_version,
        project_registry_revision=project_registry_revision,
        metadata=_metadata(metadata),
        algebra_refs=(
            AlgebraRef(
                algebra_id="mrw.successor.language.algebra",
                algebra_version="1",
            ),
        ),
        transform_refs=left.transform_refs + right.transform_refs + (merge_ref,),
    )


def traverse_ordered_program(
    element_program: ProgramNode,
    traversal_policy: str,
    *,
    program_id: str,
    project_key: str,
    project_scope_digest: str,
    semantic_identity: str,
    observation_profile: str,
    contract_version: str = PROGRAM_CONTRACT_VERSION,
    project_registry_revision: int = 1,
    metadata: "dict[str, Any] | None" = None,
) -> ProgramSpec:
    root = traverse_ordered_node(element_program, traversal_policy)
    return _common(
        root=root,
        program_id=program_id,
        project_key=project_key,
        project_scope_digest=project_scope_digest,
        semantic_identity=semantic_identity,
        observation_profile=observation_profile,
        contract_version=contract_version,
        project_registry_revision=project_registry_revision,
        metadata=metadata,
        transform_refs=(),
    )


def decide_program(
    discriminator_ref: DiscriminatorRef,
    branches: "tuple[DecisionBranch, ...]",
    *,
    program_id: str,
    project_key: str,
    project_scope_digest: str,
    semantic_identity: str,
    observation_profile: str,
    contract_version: str = PROGRAM_CONTRACT_VERSION,
    project_registry_revision: int = 1,
    metadata: "dict[str, Any] | None" = None,
    transform_refs: "tuple[TransformRef, ...]" = (),
) -> ProgramSpec:
    root = decide_node(discriminator_ref, branches)
    return _common(
        root=root,
        program_id=program_id,
        project_key=project_key,
        project_scope_digest=project_scope_digest,
        semantic_identity=semantic_identity,
        observation_profile=observation_profile,
        contract_version=contract_version,
        project_registry_revision=project_registry_revision,
        metadata=metadata,
        transform_refs=transform_refs,
    )


def build_first_specimen_program(
    *,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_scope_digest: str,
    semantic_identity: str = FIRST_SPECIMEN_SEMANTIC_IDENTITY,
    observation_profile: str = "mrw.successor.first-specimen.observation.v1",
    contract_version: str = PROGRAM_CONTRACT_VERSION,
    project_registry_revision: int = 1,
    metadata: "dict[str, Any] | None" = None,
    research_intent_type: ObjectType = RESEARCH_INTENT_TYPE,
    inquiry_type: ObjectType = INQUIRY_TYPE,
    research_plan_type: ObjectType = RESEARCH_PLAN_TYPE,
    source_ref_type: ObjectType = SOURCE_REF_TYPE,
    captured_snapshot_type: ObjectType = CAPTURED_MATERIAL_SNAPSHOT_TYPE,
    material_ref_type: ObjectType = MATERIAL_REF_TYPE,
    evidence_bundle_type: ObjectType = ObjectType("EvidenceBundle.v1"),
    evidence_qualification_type: ObjectType = EVIDENCE_QUALIFICATION_TYPE,
    evidence_qualification_bundle_type: ObjectType = ObjectType(
        "EvidenceQualificationBundle.v1"
    ),
    outcome_type: ObjectType = ObjectType("ClaimOrGap.v1"),
    artifact_type: ObjectType = RESEARCH_ARTIFACT_TYPE,
    delivery_intent_type: ObjectType = DELIVERY_INTENT_TYPE,
    program_output_type: ObjectType = DELIVERY_RECEIPT_REF_TYPE,
    registries: Registries,
    source_refs: "tuple[SourceRef, SourceRef]",
    intent_type: "ObjectType | None" = None,
) -> ProgramSpec:
    # ``intent_type`` was the initial builder argument name.  It remains an
    # explicit compatibility alias for the canonical ResearchIntent input.
    if intent_type is not None:
        research_intent_type = intent_type
    if len(source_refs) != 2:
        raise ValueError(
            "first specimen requires exactly two existing SourceRef inputs"
        )
    if source_refs[0].locator == source_refs[1].locator:
        raise ValueError("first specimen requires two distinct Document locators")
    for source_ref in source_refs:
        if not source_ref.locator.startswith("document://"):
            raise ValueError(
                "first specimen SourceRef must bind an existing Document locator"
            )

    qualification_pair_merge_ref = registries.merges.register_merge(
        name="mrw.first_specimen.qualification_pair_merge",
        version="1",
        left_type=evidence_qualification_type,
        right_type=evidence_qualification_type,
        output_type=evidence_qualification_bundle_type,
        func=_qualification_pair_merge,
    )
    material_to_qualification_input_ref = registries.transforms.register_transform(
        name="mrw.first_specimen.material_to_qualification_input",
        version="1",
        input_type=material_ref_type,
        output_type=evidence_bundle_type,
        func=_material_to_qualification_input,
    )
    claim_branch_ref = registries.transforms.register_transform(
        name="mrw.first_specimen.claim_branch",
        version="1",
        input_type=outcome_type,
        output_type=outcome_type,
        func=_claim_outcome_transform,
    )
    gap_branch_ref = registries.transforms.register_transform(
        name="mrw.first_specimen.gap_branch",
        version="1",
        input_type=outcome_type,
        output_type=outcome_type,
        func=_claim_outcome_transform,
    )
    discriminator_ref = registries.discriminators.register_discriminator(
        name="mrw.first_specimen.claim_or_gap",
        version="1",
        input_type=outcome_type,
        branch_ids=("claim", "gap"),
        func=_outcome_discriminator,
    )
    delivery_intent_ref = registries.transforms.register_transform(
        name="mrw.first_specimen.artifact_to_delivery_intent",
        version="1",
        input_type=artifact_type,
        output_type=delivery_intent_type,
        func=_artifact_to_delivery_intent,
    )

    inquiry_node = pure_node(
        input_type=research_intent_type,
        output_type=inquiry_type,
        literal_codec="mrw.functorial-successor.first-specimen.inquiry.v1",
        literal_value=content_addressed_literal(
            {
                "inquiry_id": "inquiry:first-specimen",
                "intent_ref": "intent:first-specimen",
                "question_or_hypothesis": "bounded first-specimen inquiry",
                "acceptance_conditions": ["two exact existing document captures"],
                "stop_conditions": ["claim or explicit gap formed"],
                "uncertainty_ceiling": "explicit",
            }
        ),
    )
    plan_node = pure_node(
        input_type=inquiry_type,
        output_type=research_plan_type,
        literal_codec="mrw.functorial-successor.first-specimen.research-plan.v1",
        literal_value=content_addressed_literal(
            {
                "plan_id": "plan:first-specimen",
                "inquiry_ref": "inquiry:first-specimen",
                "work_items": [
                    {"work_id": "source:a", "operator": "capture_read_qualify"},
                    {"work_id": "source:b", "operator": "capture_read_qualify"},
                ],
                "budget": {"documents": 2},
                "deadline": None,
                "replan_policy": {"mode": "open_gap"},
            }
        ),
    )

    left_path = _source_qualification_path(
        catalog=catalog,
        source_label="a",
        source_ref=source_refs[0],
        research_plan_type=research_plan_type,
        source_ref_type=source_ref_type,
        captured_snapshot_type=captured_snapshot_type,
        material_ref_type=material_ref_type,
        evidence_bundle_type=evidence_bundle_type,
        evidence_qualification_type=evidence_qualification_type,
        material_to_qualification_input_ref=material_to_qualification_input_ref,
    )
    right_path = _source_qualification_path(
        catalog=catalog,
        source_label="b",
        source_ref=source_refs[1],
        research_plan_type=research_plan_type,
        source_ref_type=source_ref_type,
        captured_snapshot_type=captured_snapshot_type,
        material_ref_type=material_ref_type,
        evidence_bundle_type=evidence_bundle_type,
        evidence_qualification_type=evidence_qualification_type,
        material_to_qualification_input_ref=material_to_qualification_input_ref,
    )
    qualifications_node = zip_ordered_node(
        left_path,
        right_path,
        qualification_pair_merge_ref,
        output_type=evidence_qualification_bundle_type,
    )
    claim_or_gap_node = _catalog_atom(
        catalog,
        operation_id="claim.form_or_open_gap",
        kind="claim.form_or_open_gap.v1",
        input_type=evidence_qualification_bundle_type,
        output_type=outcome_type,
    )
    outcome_decision_node = decide_node(
        discriminator_ref,
        (
            DecisionBranch(
                branch_id="claim",
                guard="outcome.kind == 'claim'",
                program=map_output_node(
                    identity_node(outcome_type), claim_branch_ref, outcome_type
                ),
            ),
            DecisionBranch(
                branch_id="gap",
                guard="outcome.kind == 'gap'",
                program=map_output_node(
                    identity_node(outcome_type), gap_branch_ref, outcome_type
                ),
            ),
        ),
    )
    compose_node = _catalog_atom(
        catalog,
        operation_id="artifact.compose_markdown",
        kind="artifact.compose_markdown.v1",
        input_type=outcome_type,
        output_type=artifact_type,
    )
    delivery_intent_node = map_output_node(
        identity_node(artifact_type),
        delivery_intent_ref,
        delivery_intent_type,
    )
    delivery_node = _catalog_atom(
        catalog,
        operation_id="delivery.internal_export",
        kind="delivery.internal_export.v1",
        input_type=delivery_intent_type,
        output_type=program_output_type,
    )

    # The input is the canonical ResearchIntent.  Inquiry and ResearchPlan are
    # explicit pure nodes; each SourceRef then has its own ordered
    # capture/read/qualification path.  The gap branch remains an explicit
    # ClaimOrGap value.  A named post-run materializer may create a distinct
    # successor ProgramSpec; the running plan is never expanded in place.
    root: ProgramNode = inquiry_node
    for node in (
        plan_node,
        qualifications_node,
        claim_or_gap_node,
        outcome_decision_node,
        compose_node,
        delivery_intent_node,
        delivery_node,
    ):
        root = then_node(root, node)
    first_specimen_metadata = {
        **(metadata or {}),
        "first_specimen_contract_ref": (
            "11_functorial-successor-first-specimen-contract.v1.json"
        ),
        "first_specimen_schema_ref": (
            "16_functorial-successor-first-specimen-schema-bundle.v1.1.schema.json"
        ),
        "ordered_semantic_path": [
            "ResearchIntent",
            "Inquiry",
            "ResearchPlan",
            "SourceRef:a",
            "CapturedMaterialSnapshot:a",
            "MaterialRef:a",
            "EvidenceQualification:a",
            "SourceRef:b",
            "CapturedMaterialSnapshot:b",
            "MaterialRef:b",
            "EvidenceQualification:b",
            "Claim_or_Gap",
            "ResearchArtifact_markdown",
            "DeliveryIntent",
            "DeliveryAttempt_internal_export",
            "DeliveryReceiptRef",
            "post_run_successor_materialization_from_Gap",
        ],
        "MATERIALIZE_SUCCESSOR": {
            "branch": "gap",
            "disposition": "P0_A_COMPILE_ONLY",
            "control_kind": "MaterializeSuccessor",
            "control_version": "1.0.0",
            "materializer_id": "mrw.first_specimen.gap-successor",
            "materializer_version": "1.0.0",
            "input_type": "Gap.v1",
            "successor_output_type": "ResearchPlan.v1",
        },
        "delivery_internal_export": {
            "input_type": "DeliveryIntent.v1",
            "runtime_fact": "DeliveryAttempt.v1",
            "output_type": "DeliveryReceiptRef.v1",
        },
    }
    return _spec(
        root=root,
        program_id=program_id,
        project_key=project_key,
        project_scope_digest=project_scope_digest,
        semantic_identity=semantic_identity,
        observation_profile=observation_profile,
        contract_version=contract_version,
        project_registry_revision=project_registry_revision,
        metadata=_metadata(first_specimen_metadata),
        algebra_refs=(
            AlgebraRef(
                algebra_id="mrw.successor.language.algebra",
                algebra_version="1",
            ),
        ),
        transform_refs=(
            material_to_qualification_input_ref,
            qualification_pair_merge_ref,
            claim_branch_ref,
            gap_branch_ref,
            discriminator_ref,
            delivery_intent_ref,
        ),
    )


FIRST_SPECIMEN_GAP_MATERIALIZER_ID = "mrw.first_specimen.gap-successor"
FIRST_SPECIMEN_GAP_MATERIALIZER_VERSION = "1.0.0"


def materialize_first_specimen_gap_successor(
    *,
    predecessor_program: ProgramSpec,
    predecessor_run_id: str,
    predecessor_step_id: str,
    predecessor_plan_digest: str,
    source_value_ref: ValueRef,
    gap: Gap,
    successor_intent_ref: str,
    authority_digest: str,
    materializer_id: str = FIRST_SPECIMEN_GAP_MATERIALIZER_ID,
    materializer_version: str = FIRST_SPECIMEN_GAP_MATERIALIZER_VERSION,
) -> SuccessorMaterialization:
    """Materialize a deterministic Gap -> Inquiry -> ResearchPlan successor.

    Repeating the call with the same closed identity returns an equivalent
    materialization.  The function does not persist, enqueue, or mutate either
    ProgramSpec.
    """

    if not isinstance(gap, Gap):
        raise TypeError("first-specimen successor materializer requires a typed Gap")
    if not successor_intent_ref:
        raise ValueError("successor Inquiry requires an admitted ResearchIntent ref")
    if source_value_ref.project_key != predecessor_program.project_key:
        raise ValueError("source ValueRef and predecessor ProgramSpec project drift")

    source_value_ref_digest = canonical_digest(source_value_ref)
    identity_input = {
        "predecessor_run_id": predecessor_run_id,
        "predecessor_step_id": predecessor_step_id,
        "predecessor_plan_digest": predecessor_plan_digest,
        "source_value_ref_digest": source_value_ref_digest,
        "materializer_id": materializer_id,
        "materializer_version": materializer_version,
        "authority_digest": authority_digest,
    }
    materialization_digest = canonical_digest(
        {"identity_kind": "SuccessorMaterialization.v1", **identity_input}
    )
    idempotency_key = canonical_digest(
        {"identity_kind": "SuccessorMaterializationIdempotency.v1", **identity_input}
    )
    materialization_id = f"successor-materialization:sha256:{materialization_digest}"
    gap_id = gap.gap_id
    inquiry_content = {
        "inquiry_id": f"inquiry:successor:sha256:{materialization_digest}",
        # A Gap is the source of an ``opens`` relation.  It is not a
        # ResearchIntent and must never be smuggled into ``intent_ref``.
        "intent_ref": successor_intent_ref,
        "question_or_hypothesis": gap.reason or "resolve the predecessor evidence gap",
        "acceptance_conditions": [gap.closure_condition],
        "stop_conditions": [
            "claim or an exact successor Gap is admitted",
        ],
        "uncertainty_ceiling": "explicit",
    }
    inquiry_payload = {
        **inquiry_content,
        "content_digest": research_sha256_hex(inquiry_content),
    }
    inquiry = Inquiry(
        inquiry_id=inquiry_payload["inquiry_id"],
        intent_ref=inquiry_payload["intent_ref"],
        question_or_hypothesis=inquiry_payload["question_or_hypothesis"],
        acceptance_conditions=tuple(inquiry_payload["acceptance_conditions"]),
        stop_conditions=tuple(inquiry_payload["stop_conditions"]),
        uncertainty_ceiling=inquiry_payload["uncertainty_ceiling"],
        content_digest=inquiry_payload["content_digest"],
    )
    work_item = PlanWorkItem(
        work_id=f"work:resolve-gap:sha256:{materialization_digest}",
        operator="resolve_or_narrow_gap",
    )
    plan_content = {
        "plan_id": f"research-plan:successor:sha256:{materialization_digest}",
        "inquiry_ref": inquiry.inquiry_id,
        "work_items": [
            {
                "work_id": work_item.work_id,
                "operator": work_item.operator,
                "depends_on": [],
            }
        ],
        "budget": {"successor_programs": 1},
        "deadline": None,
        "replan_policy": {
            "mode": "open_gap",
            "source_gap_ref": gap_id,
        },
    }
    plan_payload = {
        **plan_content,
        "content_digest": research_sha256_hex(plan_content),
    }
    research_plan = ResearchPlan(
        plan_id=plan_payload["plan_id"],
        inquiry_ref=plan_payload["inquiry_ref"],
        work_items=(work_item,),
        budget=dict(plan_payload["budget"]),
        deadline=None,
        replan_policy=dict(plan_payload["replan_policy"]),
        content_digest=plan_payload["content_digest"],
    )
    root = then_node(
        pure_node(
            input_type=GAP_TYPE,
            output_type=INQUIRY_TYPE,
            literal_codec="mrw.functorial-successor.gap-successor.inquiry.v1",
            literal_value=inquiry_payload,
        ),
        pure_node(
            input_type=INQUIRY_TYPE,
            output_type=RESEARCH_PLAN_TYPE,
            literal_codec="mrw.functorial-successor.gap-successor.plan.v1",
            literal_value=plan_payload,
        ),
    )
    successor_program = _spec(
        root=root,
        program_id=f"{predecessor_program.program_id}.successor.{materialization_digest}",
        project_key=predecessor_program.project_key,
        project_scope_digest=predecessor_program.project_scope_digest,
        semantic_identity=f"{predecessor_program.semantic_identity}.gap-successor",
        observation_profile=predecessor_program.observation_profile,
        contract_version=predecessor_program.contract_version,
        project_registry_revision=predecessor_program.project_registry_revision,
        metadata=_metadata(
            {
                "materialization_id": materialization_id,
                "predecessor_program_id": predecessor_program.program_id,
                "predecessor_program_digest": predecessor_program.program_digest,
                "predecessor_run_id": predecessor_run_id,
                "predecessor_step_id": predecessor_step_id,
                "predecessor_plan_digest": predecessor_plan_digest,
                "source_value_ref_digest": source_value_ref_digest,
                "materializer_id": materializer_id,
                "materializer_version": materializer_version,
                "authority_digest": authority_digest,
                "successor_inquiry_id": inquiry.inquiry_id,
                "successor_research_plan_id": research_plan.plan_id,
                "source_gap_ref": gap_id,
            }
        ),
        algebra_refs=predecessor_program.algebra_refs,
        transform_refs=(),
    )
    return SuccessorMaterialization(
        materialization_id=materialization_id,
        predecessor_run_id=predecessor_run_id,
        predecessor_step_id=predecessor_step_id,
        predecessor_plan_digest=predecessor_plan_digest,
        source_value_ref=source_value_ref,
        materializer_id=materializer_id,
        materializer_version=materializer_version,
        authority_digest=authority_digest,
        idempotency_key=idempotency_key,
        successor_program=successor_program,
        successor_program_digest=successor_program.program_digest,
        state="MATERIALIZED",
        reason=f"materialized successor for Gap {gap_id}",
    )


def _source_qualification_path(
    *,
    catalog: OperationContractCatalogSnapshot,
    source_label: str,
    source_ref: SourceRef,
    research_plan_type: ObjectType,
    source_ref_type: ObjectType,
    captured_snapshot_type: ObjectType,
    material_ref_type: ObjectType,
    evidence_bundle_type: ObjectType,
    evidence_qualification_type: ObjectType,
    material_to_qualification_input_ref: TransformRef,
) -> ProgramNode:
    source_node = pure_node(
        input_type=research_plan_type,
        output_type=source_ref_type,
        literal_codec="mrw.functorial-successor.first-specimen.source-ref.v1",
        literal_value=content_addressed_literal(
            {
                "source_ref_id": source_ref.source_ref_id,
                "owner_id": source_ref.owner_id,
                "locator": source_ref.locator,
                "source_class": source_ref.source_class,
                "access_profile_ref": source_ref.access_profile_ref,
                "observed_at": source_ref.observed_at.isoformat(),
            }
        ),
    )
    capture_node = _catalog_atom(
        catalog,
        operation_id=f"material.capture.source.{source_label}",
        kind="material.capture_document_snapshot.v1",
        input_type=source_ref_type,
        output_type=captured_snapshot_type,
    )
    read_node = _catalog_atom(
        catalog,
        operation_id=f"material.read.source.{source_label}",
        kind="material.read_canonical_ref.v1",
        input_type=captured_snapshot_type,
        output_type=material_ref_type,
    )
    qualification_input_node = map_output_node(
        identity_node(material_ref_type),
        material_to_qualification_input_ref,
        evidence_bundle_type,
    )
    qualification_node = _catalog_atom(
        catalog,
        operation_id=f"evidence.qualify.source.{source_label}",
        kind="evidence.qualify.v1",
        input_type=evidence_bundle_type,
        output_type=evidence_qualification_type,
    )
    path: ProgramNode = source_node
    for node in (
        capture_node,
        read_node,
        qualification_input_node,
        qualification_node,
    ):
        path = then_node(path, node)
    return path


def _contract_ref(
    catalog: OperationContractCatalogSnapshot, kind: str
) -> OperationContractRef:
    ref = catalog.lookup(kind)
    if ref is None:
        raise ValueError(f"contract {kind} missing from catalog")
    return ref


def _catalog_atom(
    catalog: OperationContractCatalogSnapshot,
    *,
    operation_id: str,
    kind: str,
    input_type: ObjectType,
    output_type: ObjectType,
) -> ProgramNode:
    return atom_node(
        operation=OperationSpec(
            operation_id=operation_id,
            contract_ref=_contract_ref(catalog, kind),
            input_refs=(_value_ref(operation_id + ".input", input_type),),
            payload_ref=_value_ref(operation_id + ".payload", input_type),
            allowed_overrides=freeze_json_object({}),
        ),
        input_type=input_type,
        output_type=output_type,
    )


def _value_ref(value_id: str, object_type: ObjectType) -> ValueRef:
    return ValueRef(
        value_id=value_id,
        project_key="project",
        object_type=object_type,
        codec_id=object_type.codec_id,
        content_digest=canonical_digest({"value_id": value_id}),
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=value_id,
        byte_size=0,
        provenance_digest="0" * 64,
    )
