"""Runtime-bound Program builder for the frozen P0-C first specimen.

Unlike the P0-A compile fixture, this builder accepts only project-scoped,
content-addressed values that have already been persisted by the submission
transaction.  It keeps the frozen operation catalog and shared AST closed: the
capability contributes values and named transforms, not a new AST node.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.successor_runtime.language.algebra import (
    AlgebraRef,
    OperationSpec,
    ValueRef,
    freeze_json_object,
)
from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot
from app.successor_runtime.language.combinators import (
    FIRST_SPECIMEN_SEMANTIC_IDENTITY,
    PROGRAM_CONTRACT_VERSION,
    Registries,
)
from app.successor_runtime.language.program import (
    DecisionBranch,
    ProgramNode,
    ProgramSpec,
    atom_node,
    content_addressed_literal,
    decide_node,
    identity_node,
    map_output_node,
    pure_node,
    then_node,
    zip_ordered_node,
)
from app.successor_runtime.research.object_types import (
    CAPTURED_MATERIAL_SNAPSHOT_TYPE,
    DELIVERY_INTENT_TYPE,
    DELIVERY_RECEIPT_REF_TYPE,
    EVIDENCE_QUALIFICATION_TYPE,
    INQUIRY_TYPE,
    MATERIAL_REF_TYPE,
    RESEARCH_ARTIFACT_TYPE,
    RESEARCH_INTENT_TYPE,
    RESEARCH_PLAN_TYPE,
    SOURCE_REF_TYPE,
    ObjectType,
)

DELIVERY_TEMPLATE_TYPE = ObjectType("DeliveryIntentTemplate.v1")
EVIDENCE_BUNDLE_TYPE = ObjectType("EvidenceBundle.v1")
EVIDENCE_QUALIFICATION_BUNDLE_TYPE = ObjectType(
    "EvidenceQualificationBundle.v1"
)
CLAIM_OR_GAP_TYPE = ObjectType("ClaimOrGap.v1")

_OPERATION_IDS = (
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


def _require_real_value_ref(ref: ValueRef, project_key: str) -> None:
    if ref.project_key != project_key:
        raise ValueError("first-specimen ValueRef project scope drift")
    for field_name in ("content_digest", "provenance_digest"):
        digest = getattr(ref, field_name)
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise ValueError(f"ValueRef.{field_name} must be canonical sha256 hex")
        if digest == "0" * 64:
            raise ValueError(f"ValueRef.{field_name} cannot be a placeholder digest")
    if ref.byte_size <= 0:
        raise ValueError("runtime first-specimen ValueRef must bind non-empty bytes")
    if not ref.storage_ref or ref.storage_ref == ref.value_id:
        raise ValueError("runtime first-specimen ValueRef requires an opaque storage locator")


@dataclass(frozen=True, slots=True)
class ExactOperationValues:
    """Persisted values closed over by one Atom operation."""

    input_refs: tuple[ValueRef, ...]
    payload_ref: ValueRef

    def validate(self, project_key: str) -> None:
        if not self.input_refs:
            raise ValueError("Atom requires at least one exact input ValueRef")
        for ref in self.input_refs + (self.payload_ref,):
            _require_real_value_ref(ref, project_key)


@dataclass(frozen=True, slots=True)
class FirstSpecimenProgramValues:
    """All concrete values used by the runtime-specific first specimen."""

    intent: ValueRef
    inquiry: ValueRef
    research_plan: ValueRef
    source_a: ValueRef
    source_b: ValueRef
    delivery_template: ValueRef
    operations: tuple[tuple[str, ExactOperationValues], ...]

    def __post_init__(self) -> None:
        project_key = self.intent.project_key
        for ref in (
            self.intent,
            self.inquiry,
            self.research_plan,
            self.source_a,
            self.source_b,
            self.delivery_template,
        ):
            _require_real_value_ref(ref, project_key)
        if self.delivery_template.object_type != DELIVERY_TEMPLATE_TYPE:
            raise ValueError("delivery_template must use DeliveryIntentTemplate.v1")
        ids = tuple(operation_id for operation_id, _ in self.operations)
        if ids != _OPERATION_IDS:
            raise ValueError(
                "runtime first-specimen operation values must use the frozen ordered IDs"
            )
        for _, binding in self.operations:
            binding.validate(project_key)

    def for_operation(self, operation_id: str) -> ExactOperationValues:
        for candidate, binding in self.operations:
            if candidate == operation_id:
                return binding
        raise KeyError(operation_id)


def _qualification_pair_merge(left: Any, right: Any) -> dict[str, Any]:
    return {"evidence_qualifications": [left, right]}


def _material_to_qualification_input(material: Any) -> dict[str, Any]:
    if isinstance(material, dict):
        material_ref = material.get("material_ref_id", material.get("material_ref"))
    else:
        material_ref = getattr(material, "material_ref_id", material)
    if not isinstance(material_ref, str) or not material_ref:
        raise ValueError("qualification transform requires MaterialRef identity")
    return {"material_ref": material_ref}


def _claim_or_gap_identity(outcome: Any) -> dict[str, Any]:
    return outcome


def _artifact_identity(artifact: Any) -> Any:
    return artifact


def _claim_or_gap_discriminator(outcome: Any) -> str:
    if not isinstance(outcome, dict):
        raise ValueError("claim-or-gap discriminator requires a canonical object")
    explicit_kind = outcome.get("kind")
    if explicit_kind in {"claim", "gap"}:
        return str(explicit_kind)
    has_claim_identity = isinstance(outcome.get("claim_id"), str)
    has_gap_identity = isinstance(outcome.get("gap_id"), str)
    if has_claim_identity == has_gap_identity:
        raise ValueError("claim-or-gap discriminator requires one exact variant identity")
    return "claim" if has_claim_identity else "gap"


def _artifact_and_delivery_template_merge(
    artifact: Any, template: Any
) -> dict[str, Any]:
    """Produce a delivery candidate without inventing approval or authority.

    The right value is the exact stored template read by the interpreter.  Its
    approval and authority fields are later revalidated by ``DeliveryGate``.
    """

    template_mapping = dict(template)
    values = dict(template_mapping.get("delivery_template", template_mapping))
    if isinstance(artifact, dict):
        artifact_ref = artifact.get("artifact_ref") or artifact.get("artifact_id")
    else:
        artifact_value = getattr(artifact, "artifact", artifact)
        artifact_ref = getattr(artifact_value, "artifact_id", None)
    if not artifact_ref:
        raise ValueError("delivery candidate requires an exact artifact identity")
    values["artifact_ref"] = artifact_ref
    return values


def _contract_ref(catalog: OperationContractCatalogSnapshot, kind: str):
    ref = catalog.lookup(kind)
    if ref is None:
        raise ValueError(f"contract {kind} missing from catalog")
    return ref


def _atom(
    *,
    catalog: OperationContractCatalogSnapshot,
    values: FirstSpecimenProgramValues,
    operation_id: str,
    kind: str,
    input_type: ObjectType,
    output_type: ObjectType,
) -> ProgramNode:
    binding = values.for_operation(operation_id)
    return atom_node(
        OperationSpec(
            operation_id=operation_id,
            contract_ref=_contract_ref(catalog, kind),
            input_refs=binding.input_refs,
            payload_ref=binding.payload_ref,
            allowed_overrides=freeze_json_object({}),
        ),
        input_type=input_type,
        output_type=output_type,
    )


def _source_path(
    *,
    label: str,
    source_ref: ValueRef,
    catalog: OperationContractCatalogSnapshot,
    values: FirstSpecimenProgramValues,
    material_to_qualification_ref: Any,
) -> ProgramNode:
    source = pure_node(
        RESEARCH_PLAN_TYPE,
        SOURCE_REF_TYPE,
        content_addressed_literal({"source_value_ref": source_ref.to_plain()}),
        "mrw.functorial-successor.value-ref.literal.v1",
    )
    capture = _atom(
        catalog=catalog,
        values=values,
        operation_id=f"material.capture.source.{label}",
        kind="material.capture_document_snapshot.v1",
        input_type=SOURCE_REF_TYPE,
        output_type=CAPTURED_MATERIAL_SNAPSHOT_TYPE,
    )
    read = _atom(
        catalog=catalog,
        values=values,
        operation_id=f"material.read.source.{label}",
        kind="material.read_canonical_ref.v1",
        input_type=CAPTURED_MATERIAL_SNAPSHOT_TYPE,
        output_type=MATERIAL_REF_TYPE,
    )
    qualification_input = map_output_node(
        identity_node(MATERIAL_REF_TYPE),
        material_to_qualification_ref,
        EVIDENCE_BUNDLE_TYPE,
    )
    qualify = _atom(
        catalog=catalog,
        values=values,
        operation_id=f"evidence.qualify.source.{label}",
        kind="evidence.qualify.v1",
        input_type=EVIDENCE_BUNDLE_TYPE,
        output_type=EVIDENCE_QUALIFICATION_TYPE,
    )
    root: ProgramNode = source
    for node in (capture, read, qualification_input, qualify):
        root = then_node(root, node)
    return root


def build_runtime_first_specimen_program(
    *,
    catalog: OperationContractCatalogSnapshot,
    registries: Registries,
    values: FirstSpecimenProgramValues,
    program_id: str,
    project_key: str,
    project_scope_digest: str,
    project_registry_revision: int,
    delivery_template: dict[str, Any],
    semantic_identity: str = FIRST_SPECIMEN_SEMANTIC_IDENTITY,
    observation_profile: str = "mrw.successor.first-specimen.observation.v1",
    contract_version: str = PROGRAM_CONTRACT_VERSION,
) -> ProgramSpec:
    """Build the P0-C Program over exact values from the submission UoW."""

    if values.intent.project_key != project_key:
        raise ValueError("Program values do not belong to project_key")
    authority_digest = delivery_template.get("authority_digest")
    if authority_digest == "0" * 64:
        raise ValueError("delivery template cannot carry placeholder authority")
    if delivery_template.get("approval_refs") in (None, (), []):
        raise ValueError("delivery template requires an explicit human approval ref")

    qualification_merge = registries.merges.register_merge(
        name="mrw.first_specimen.runtime.qualification_pair_merge",
        version="1",
        left_type=EVIDENCE_QUALIFICATION_TYPE,
        right_type=EVIDENCE_QUALIFICATION_TYPE,
        output_type=EVIDENCE_QUALIFICATION_BUNDLE_TYPE,
        func=_qualification_pair_merge,
    )
    material_to_qualification = registries.transforms.register_transform(
        name="mrw.first_specimen.runtime.material_to_qualification_input",
        version="1",
        input_type=MATERIAL_REF_TYPE,
        output_type=EVIDENCE_BUNDLE_TYPE,
        func=_material_to_qualification_input,
    )
    claim_branch = registries.transforms.register_transform(
        name="mrw.first_specimen.runtime.claim_branch",
        version="1",
        input_type=CLAIM_OR_GAP_TYPE,
        output_type=CLAIM_OR_GAP_TYPE,
        func=_claim_or_gap_identity,
        preserves_value_ref=True,
    )
    gap_branch = registries.transforms.register_transform(
        name="mrw.first_specimen.runtime.gap_branch",
        version="1",
        input_type=CLAIM_OR_GAP_TYPE,
        output_type=CLAIM_OR_GAP_TYPE,
        func=_claim_or_gap_identity,
        preserves_value_ref=True,
    )
    discriminator = registries.discriminators.register_discriminator(
        name="mrw.first_specimen.runtime.claim_or_gap",
        version="1",
        input_type=CLAIM_OR_GAP_TYPE,
        branch_ids=("claim", "gap"),
        func=_claim_or_gap_discriminator,
    )
    artifact_identity = registries.transforms.register_transform(
        name="mrw.first_specimen.runtime.artifact_identity",
        version="1",
        input_type=RESEARCH_ARTIFACT_TYPE,
        output_type=RESEARCH_ARTIFACT_TYPE,
        func=_artifact_identity,
        preserves_value_ref=True,
    )
    delivery_merge = registries.merges.register_merge(
        name="mrw.first_specimen.runtime.artifact_delivery_template",
        version="1",
        left_type=RESEARCH_ARTIFACT_TYPE,
        right_type=DELIVERY_TEMPLATE_TYPE,
        output_type=DELIVERY_INTENT_TYPE,
        func=_artifact_and_delivery_template_merge,
    )

    inquiry = pure_node(
        RESEARCH_INTENT_TYPE,
        INQUIRY_TYPE,
        content_addressed_literal({"inquiry_value_ref": values.inquiry.to_plain()}),
        "mrw.functorial-successor.value-ref.literal.v1",
    )
    plan = pure_node(
        INQUIRY_TYPE,
        RESEARCH_PLAN_TYPE,
        content_addressed_literal(
            {"research_plan_value_ref": values.research_plan.to_plain()}
        ),
        "mrw.functorial-successor.value-ref.literal.v1",
    )
    left = _source_path(
        label="a",
        source_ref=values.source_a,
        catalog=catalog,
        values=values,
        material_to_qualification_ref=material_to_qualification,
    )
    right = _source_path(
        label="b",
        source_ref=values.source_b,
        catalog=catalog,
        values=values,
        material_to_qualification_ref=material_to_qualification,
    )
    qualifications = zip_ordered_node(
        left,
        right,
        qualification_merge,
        EVIDENCE_QUALIFICATION_BUNDLE_TYPE,
    )
    claim_or_gap = _atom(
        catalog=catalog,
        values=values,
        operation_id="claim.form_or_open_gap",
        kind="claim.form_or_open_gap.v1",
        input_type=EVIDENCE_QUALIFICATION_BUNDLE_TYPE,
        output_type=CLAIM_OR_GAP_TYPE,
    )
    decide = decide_node(
        discriminator,
        (
            DecisionBranch(
                "claim",
                "outcome.claim_id != None",
                map_output_node(
                    identity_node(CLAIM_OR_GAP_TYPE), claim_branch, CLAIM_OR_GAP_TYPE
                ),
            ),
            DecisionBranch(
                "gap",
                "outcome.gap_id != None",
                map_output_node(
                    identity_node(CLAIM_OR_GAP_TYPE), gap_branch, CLAIM_OR_GAP_TYPE
                ),
            ),
        ),
    )
    compose = _atom(
        catalog=catalog,
        values=values,
        operation_id="artifact.compose_markdown",
        kind="artifact.compose_markdown.v1",
        input_type=CLAIM_OR_GAP_TYPE,
        output_type=RESEARCH_ARTIFACT_TYPE,
    )
    template = pure_node(
        RESEARCH_ARTIFACT_TYPE,
        DELIVERY_TEMPLATE_TYPE,
        content_addressed_literal(
            {
                "delivery_template_value_ref": values.delivery_template.to_plain(),
                "delivery_template": delivery_template,
            }
        ),
        "mrw.functorial-successor.delivery-template.v1",
    )
    delivery_candidate = zip_ordered_node(
        map_output_node(
            identity_node(RESEARCH_ARTIFACT_TYPE),
            artifact_identity,
            RESEARCH_ARTIFACT_TYPE,
        ),
        template,
        delivery_merge,
        DELIVERY_INTENT_TYPE,
    )
    deliver = _atom(
        catalog=catalog,
        values=values,
        operation_id="delivery.internal_export",
        kind="delivery.internal_export.v1",
        input_type=DELIVERY_INTENT_TYPE,
        output_type=DELIVERY_RECEIPT_REF_TYPE,
    )

    root: ProgramNode = inquiry
    for node in (
        plan,
        qualifications,
        claim_or_gap,
        decide,
        compose,
        delivery_candidate,
        deliver,
    ):
        root = then_node(root, node)

    metadata = freeze_json_object(
        {
            "first_specimen_contract_ref": (
                "11_functorial-successor-first-specimen-contract.v1.json"
            ),
            "first_specimen_schema_ref": (
                "16_functorial-successor-first-specimen-schema-bundle.v1.1.schema.json"
            ),
            "runtime_value_closure": [
                values.intent.storage_ref,
                values.inquiry.storage_ref,
                values.research_plan.storage_ref,
                values.source_a.storage_ref,
                values.source_b.storage_ref,
                values.delivery_template.storage_ref,
            ],
            "delivery_candidate_construction": (
                "ordered ZipOrdered(artifact, exact stored template)"
            ),
            "delivery_gate_required": True,
        }
    )
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
        algebra_refs=(AlgebraRef("mrw.successor.language.algebra", "1"),),
        transform_refs=(
            material_to_qualification,
            qualification_merge,
            claim_branch,
            gap_branch,
            discriminator,
            artifact_identity,
            delivery_merge,
        ),
        observation_profile=observation_profile,
        metadata=metadata,
        program_digest="",
    ).with_digest()


__all__ = [
    "DELIVERY_TEMPLATE_TYPE",
    "ExactOperationValues",
    "FirstSpecimenProgramValues",
    "build_runtime_first_specimen_program",
]
