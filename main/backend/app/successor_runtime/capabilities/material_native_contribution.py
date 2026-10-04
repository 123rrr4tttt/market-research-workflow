"""Authored native-contribution rule for the existing C7 ingest authority.

The rule lowers one explicit C7 source into the existing ingest capability
bundle, catalog, registry and the exact C7.1 Program.  The capability modules
remain the semantic authority.  The source only declares typed references and
ordered boundaries for the canonical writer, production admission and projector
drivers; it does not execute a canonical commit, CAS/ABA update or DB effect,
and it never promotes registry metadata to durable evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, TYPE_CHECKING, get_args

from functorial_kit.contribution_compiler import (
    NativeContributionRule,
    compile_native_contribution,
)
from functorial_kit.contribution_verification import (
    ContributionVerification,
    VerificationCheck,
)
from functorial_kit.contributions import ContributionObject, contribution_failures
from functorial_kit.core.failure import Failure
from functorial_kit.law_witness import define_law_witness
from functorial_kit.native_contribution import (
    BindingAccepted,
    BindingRejected,
    NativeBindingIssue,
    ProjectedContributionSpec,
)

from app.successor_runtime.capabilities import material_ingest_common as material
from app.successor_runtime.capabilities import material_ingest_movements as movements
from app.successor_runtime.capabilities import material_ingest_program as program
from mrw_functorial_kit.core import material_semantics as kit_material
from mrw_functorial_kit.core.material_semantics import (
    material_digestion_alternative_codec,
    material_digestion_alternatives,
    material_ingest_content_format_codec,
    material_ingest_content_formats,
    material_ingest_failures,
    material_ingest_input_kind_codec,
    material_ingest_input_kinds,
    material_ingest_movement_disposition_codec,
    material_ingest_movement_dispositions,
    material_ingest_terminal_outcome_codec,
    material_ingest_terminal_outcomes,
)
from mrw_functorial_kit.core.w06_semantics import (
    material_ingest_contract_failures,
    material_ingest_registry_failures,
)

MATERIAL_TERMINAL_OUTCOME_MEMBERS = get_args(kit_material.MaterialIngestTerminalOutcome)

if TYPE_CHECKING:  # pragma: no cover
    from app.successor_runtime.assembly.base import FamilyAssembly

__all__ = [
    "ASSEMBLY_CELL_IDS",
    "MATERIAL_ASSEMBLY_CELL_IDS",
    "MATERIAL_NATIVE_CONTRIBUTION_RULE",
    "MATERIAL_NATIVE_RULE_ID",
    "MATERIAL_NATIVE_VERIFICATION_INPUTS",
    "MATERIAL_INGEST_FAILURES",
    "MaterialAssemblyContext",
    "MaterialNativeBinding",
    "MaterialNativeDefinition",
    "MaterialNativeSource",
    "DEFAULT_MATERIAL_NATIVE_SOURCE",
    "compile_material_native_contribution",
    "MATERIAL_COMMIT_READBACK_CELL_ID",
    "MATERIAL_PROJECTION_DIFF_CELL_ID",
    "MATERIAL_RECONCILIATION_CELL_ID",
    "MATERIAL_STAGE_CANDIDATE_CELL_ID",
]

MATERIAL_NATIVE_RULE_ID = "mrw.material.ingest.native-rule.v2"
MATERIAL_NATIVE_VERIFICATION_INPUTS = (
    "mrw.material.ingest.definition",
    "mrw.material.ingest.movement-order",
    "mrw.material.canonical-write-boundary",
    "mrw.material.ingest-admission-boundary",
    "mrw.material.projection-boundary",
    "mrw.material.ingest.failure-vocabulary",
    "mrw.material.ingest.program",
)

MATERIAL_DIGESTION_ALTERNATIVES = material_digestion_alternatives
MATERIAL_TERMINAL_OUTCOMES = material_ingest_terminal_outcomes
MATERIAL_INGEST_FAILURES = material_ingest_failures

MATERIAL_STAGE_CANDIDATE_CELL_ID = "material.ingest.stage-candidate.v2"
MATERIAL_COMMIT_READBACK_CELL_ID = "material.ingest.commit-readback.v2"
MATERIAL_PROJECTION_DIFF_CELL_ID = "material.ingest.projection-diff.v2"
MATERIAL_RECONCILIATION_CELL_ID = "material.ingest.reconciliation.v2"
ASSEMBLY_CELL_IDS = (
    MATERIAL_STAGE_CANDIDATE_CELL_ID,
    MATERIAL_COMMIT_READBACK_CELL_ID,
    MATERIAL_PROJECTION_DIFF_CELL_ID,
    MATERIAL_RECONCILIATION_CELL_ID,
)
MATERIAL_ASSEMBLY_CELL_IDS = ASSEMBLY_CELL_IDS


CANONICAL_WRITE_REF = (
    "app.successor_runtime.substrate.postgres.c7_canonical_write"
    ".PostgresC7CanonicalWritePort"
)
PRODUCTION_ADMISSION_REF = (
    "app.successor_runtime.substrate.postgres.c7_production_admission"
    ".run_c7_production_cutover_admission"
)
PROJECTOR_DRIVER_REF = (
    "app.successor_runtime.substrate.postgres.c7_projector_driver.C7ProjectorDriver"
)


@dataclass(frozen=True, slots=True)
class MaterialNativeSource:
    """One authored C7 fact: typed boundaries only, no durable write authority."""

    contribution_id: str
    owner: str
    bundle_id: str
    operation_kind: str
    payload_codec_id: str
    catalog_operation_id: str
    catalog_payload_codec_id: str
    movement_alternatives: tuple[str, ...]
    canonical_writer_ref: str
    production_admission_ref: str
    projector_driver_ref: str
    failure_profile_id: str
    failure_codes: tuple[str, ...]
    vocabulary_refs: tuple[str, ...]
    rollback_refs: tuple[str, ...]
    assembly_cell_ids: tuple[str, ...]
    canonical_write_authorized: bool = False
    canonical_commit_executed: bool = False


DEFAULT_MATERIAL_NATIVE_SOURCE = MaterialNativeSource(
    contribution_id="mrw.material.ingest.native.v2",
    owner=material.MATERIAL_INGEST_OWNER,
    bundle_id="mrw.material.ingest",
    operation_kind=material.MATERIAL_STAGE_CANDIDATE_KIND,
    payload_codec_id=material.MATERIAL_STAGE_CANDIDATE_PAYLOAD_CODEC_ID,
    catalog_operation_id=material.MATERIAL_OPERATION_SEMANTIC_IDENTITY,
    catalog_payload_codec_id=material.MATERIAL_STAGE_CANDIDATE_PAYLOAD_CODEC_ID,
    movement_alternatives=movements.MATERIAL_INGEST_ALTERNATIVES,
    canonical_writer_ref=CANONICAL_WRITE_REF,
    production_admission_ref=PRODUCTION_ADMISSION_REF,
    projector_driver_ref=PROJECTOR_DRIVER_REF,
    failure_profile_id="material.ingest.stage.failure.v2",
    failure_codes=kit_material.MATERIAL_INGEST_STAGE_FAILURE_CODES,
    vocabulary_refs=(
        material_digestion_alternatives.name,
        material_ingest_terminal_outcomes.name,
        material_ingest_failures.name,
    ),
    rollback_refs=(
        "main/backend/app/successor_runtime/capabilities/material_ingest_movements.py",
        "main/backend/app/successor_runtime/capabilities/material_ingest_registry.py",
        "main/backend/app/successor_runtime/capabilities/material_ingest_program.py",
    ),
    assembly_cell_ids=ASSEMBLY_CELL_IDS,
)


@dataclass(frozen=True, slots=True)
class MaterialNativeDefinition:
    """Lowered view of one authored C7 source over the existing authorities."""

    source: MaterialNativeSource
    bundle: material.MaterialIngestCapabilityBundle
    catalog: object
    registry: object

    @property
    def contribution_id(self) -> str:
        return self.source.contribution_id

    def contribution_objects(self) -> tuple[ContributionObject, ...]:
        input_type = "MaterialIngestSubmission.v2"
        output_type = "StagedMaterialCandidate.v2"
        declared = (
            (input_type, "ObjectType", ()),
            (output_type, "ObjectType", (input_type,)),
            (self.source.catalog_operation_id, "Capability", (input_type, output_type)),
            (
                self.source.catalog_payload_codec_id,
                "PayloadCodec",
                (self.source.catalog_operation_id, input_type),
            ),
            ("material.canonical-writer.v2", "CanonicalWriter", ()),
            ("material.ingest-admission.v2", "Admission", ("material.canonical-writer.v2",)),
            ("material.projection-driver.v2", "Projector", ("material.canonical-writer.v2",)),
        )
        return tuple(
            ContributionObject(
                object_id,
                kind,
                self.source.owner,
                references,
            )
            for object_id, kind, references in declared
        )


def _issue_tuple(
    checks: tuple[tuple[bool, str, str], ...],
) -> tuple[NativeBindingIssue, ...]:
    return tuple(
        NativeBindingIssue(path, message)
        for valid, path, message in checks
        if not valid
    )


def _definition_issues(
    source: MaterialNativeSource,
    definition: MaterialNativeDefinition,
) -> tuple[NativeBindingIssue, ...]:
    bundle = definition.bundle
    operation = bundle.operations[0]
    codec = bundle.codecs[0]
    profiles = bundle.profiles
    return _issue_tuple(
        (
            (bundle.bundle_id == source.bundle_id, "$.source.bundle_id", "bundle identity drift"),
            (operation.ref.kind == source.operation_kind, "$.source.operation_kind", "operation kind drift"),
            (operation.owner_capability_id == material.MATERIAL_INGEST_OWNER, "$.source.owner", "current operation owner drift"),
            (bool(source.owner), "$.source.owner", "current owner is empty"),
            (bool(source.catalog_operation_id), "$.source.catalog_operation_id", "current operation identity is empty"),
            (bool(source.catalog_payload_codec_id), "$.source.catalog_payload_codec_id", "current codec identity is empty"),
            (codec.codec_id == source.payload_codec_id, "$.source.payload_codec_id", "payload codec drift"),  # type: ignore[union-attr]
            (source.movement_alternatives == movements.MATERIAL_INGEST_ALTERNATIVES, "$.source.movement_alternatives", "C7 four-mode order drift"),
            (
                tuple(profiles["failure"].typed_failures) == source.failure_codes,  # type: ignore[union-attr]
                "$.source.failure_codes",
                "typed failure facts drift",
            ),
            (
                profiles["failure"].failure_profile_id == source.failure_profile_id,  # type: ignore[union-attr]
                "$.source.failure_profile_id",
                "failure profile drift",
            ),
            (
                source.vocabulary_refs
                == (
                    material_digestion_alternatives.name,
                    material_ingest_terminal_outcomes.name,
                    material_ingest_failures.name,
                ),
                "$.source.vocabulary_refs",
                "kit vocabulary identity drift",
            ),
            (tuple(material_ingest_terminal_outcomes.members) == MATERIAL_TERMINAL_OUTCOME_MEMBERS, "$.vocabulary.terminal_outcomes", "terminal outcome members drift"),
            (tuple(material_ingest_failures.codes) == kit_material.MATERIAL_INGEST_FAILURE_CODES, "$.vocabulary.failures", "material ingest failure members drift"),
            (material_digestion_alternatives.members == source.movement_alternatives, "$.vocabulary.alternatives", "movement alternative members drift"),
            (source.canonical_writer_ref == CANONICAL_WRITE_REF, "$.source.canonical_writer_ref", "canonical writer reference drift"),
            (source.production_admission_ref == PRODUCTION_ADMISSION_REF, "$.source.production_admission_ref", "production admission reference drift"),
            (source.projector_driver_ref == PROJECTOR_DRIVER_REF, "$.source.projector_driver_ref", "projector driver reference drift"),
            (len({source.canonical_writer_ref, source.production_admission_ref, source.projector_driver_ref}) == 3, "$.source.boundaries", "writer/admission/projector boundaries must stay distinct"),
            (source.canonical_write_authorized is False, "$.source.canonical_write_authorized", "native source does not grant canonical write authority"),
            (source.canonical_commit_executed is False, "$.source.canonical_commit_executed", "native compilation is inert and must not execute a canonical commit"),
            (len(source.rollback_refs) >= 1, "$.source.rollback_refs", "rollback binding is empty"),
            (
                source.assembly_cell_ids == ASSEMBLY_CELL_IDS,
                "$.source.assembly_cell_ids",
                "material assembly cell identity/order drift",
            ),
        )
    )


def lower_material_native_source(source: MaterialNativeSource) -> MaterialNativeDefinition | Failure:
    bundle = material.build_material_ingest_bundle()
    definition = MaterialNativeDefinition(
        source=source,
        bundle=bundle,
        catalog=material.build_material_ingest_catalog(bundle),
        registry=material.build_material_ingest_registry(bundle),
    )
    issues = _definition_issues(source, definition)
    if issues:
        return contribution_failures.fail(
            "CONTRIBUTION_INVALID",
            "native C7 definition is invalid",
            {
                "issues": tuple(
                    {"code": "invalid_spec", "path": issue.path, "message": issue.message}
                    for issue in issues
                )
            },
        )
    return definition


def project_material_native_definition(
    definition: MaterialNativeDefinition,
) -> ProjectedContributionSpec | Failure:
    return ProjectedContributionSpec(
        id=definition.contribution_id,
        owner=definition.source.owner,
        objects=definition.contribution_objects(),
        codecs=(
            material_digestion_alternative_codec,
            material_ingest_input_kind_codec,
            material_ingest_content_format_codec,
            material_ingest_movement_disposition_codec,
            material_ingest_terminal_outcome_codec,
        ),
        vocabularies=(
            material_digestion_alternatives,
            material_ingest_input_kinds,
            material_ingest_content_formats,
            material_ingest_movement_dispositions,
            material_ingest_terminal_outcomes,
        ),
        failures=(
            material_ingest_failures,
            material_ingest_contract_failures,
            material_ingest_registry_failures,
        ),
    )


@dataclass(frozen=True, slots=True)
class MaterialAssemblyContext:
    """Explicit offline assembly boundary with no canonical write closure."""

    project_scope_digest: str


@dataclass(frozen=True, slots=True)
class MaterialNativeBinding:
    """Derived C7 binding over the existing family assembly."""

    definition: MaterialNativeDefinition
    family_assembly: FamilyAssembly

    @property
    def rollback_binding_refs_by_cell(self) -> tuple[tuple[str, ...], ...]:
        return tuple(
            self.definition.source.rollback_refs
            for _ in self.family_assembly.cells
        )


def build_material_native_program(
    definition: MaterialNativeDefinition,
    submission: material.MaterialIngestSubmission,
    *,
    program_id: str,
    project_scope_digest: str,
) -> Annotated[
    object,
    "kit:non-authoritative "
    "derived_as=offline_program_spec "
    "fact_source=c7_native_definition_and_ingest_submission "
    "witness=test:test_exact_c7_1_program_compiles_from_native_catalog_offline",
]:
    """Derive the exact C7.1 Program; compilation itself performs no effect."""

    return program.build_material_stage_candidate_program(
        payload=submission,
        catalog=definition.catalog,  # type: ignore[arg-type]
        program_id=program_id,
        project_key=submission.project_key,
        project_registry_revision=1,
        project_scope_digest=project_scope_digest,
    )


def assemble_material_native_definition(
    definition: MaterialNativeDefinition,
    context: MaterialAssemblyContext,
) -> MaterialNativeBinding | Failure:
    from app.successor_runtime.assembly.material_ingest_assembly import build_material_ingest_assembly

    family_assembly = build_material_ingest_assembly(
        project_scope_digest=context.project_scope_digest,
        canonical_write=None,
        projector_driver=None,
        native_definition=definition,
    )
    return MaterialNativeBinding(
        definition=definition,
        family_assembly=family_assembly,
    )


def validate_material_native_binding(
    definition: MaterialNativeDefinition,
    candidate: object,
) -> BindingAccepted[MaterialNativeBinding] | BindingRejected:
    if not isinstance(candidate, MaterialNativeBinding):
        return BindingRejected((NativeBindingIssue("$.binding", "expected C7NativeBinding"),))
    issues = _issue_tuple(
        (
            (candidate.definition == definition, "$.binding.definition", "definition drift"),
            (
                candidate.family_assembly.family_id == definition.source.bundle_id,
                "$.binding.family_assembly.family_id",
                "family id drift",
            ),
            (
                tuple(cell.cell_id for cell in candidate.family_assembly.cells)
                == definition.source.assembly_cell_ids,
                "$.binding.family_assembly.cells",
                "material ingest cell order drift",
            ),
            (
                tuple(tuple(refs) for refs in candidate.rollback_binding_refs_by_cell)
                == (definition.source.rollback_refs,) * len(candidate.family_assembly.cells),
                "$.binding.rollback_bindings",
                "rollback binding drift from authored source",
            ),
        )
    )
    return BindingRejected(issues) if issues else BindingAccepted(candidate)


def verify_material_native_definition(
    definition: MaterialNativeDefinition,
    native: object,
) -> ContributionVerification | Failure:
    del native

    def _run() -> Failure | None:
        issues = _definition_issues(definition.source, definition)
        if issues:
            return contribution_failures.fail(
                "CONTRIBUTION_INVALID",
                "; ".join(f"{issue.path}: {issue.message}" for issue in issues),
            )
        submission = material.MaterialIngestSubmission(
            idempotency_key="c7-native-law",
            project_key="c7-native-law",
            source_locator="native://catalog-law",
        )
        build_material_native_program(
            definition,
            submission,
            program_id="mrw.material.ingest.native-program.v2",
            project_scope_digest="0" * 64,
        )
        return None

    witness = define_law_witness(
        f"test_material_native_definition_law:{definition.contribution_id}",
        _run,
    )
    if isinstance(witness, Failure):
        return witness
    return ContributionVerification(
        rule_id=MATERIAL_NATIVE_RULE_ID,
        inputs=MATERIAL_NATIVE_VERIFICATION_INPUTS,
        checks=(VerificationCheck(witness=witness, inputs=MATERIAL_NATIVE_VERIFICATION_INPUTS),),
        complete=True,
    )


MATERIAL_NATIVE_CONTRIBUTION_RULE = NativeContributionRule[
    MaterialNativeSource,
    MaterialNativeDefinition,
    MaterialAssemblyContext,
    MaterialNativeBinding,
](
    lower=lower_material_native_source,
    project=project_material_native_definition,
    assemble=assemble_material_native_definition,
    validate_binding=validate_material_native_binding,
    verification=verify_material_native_definition,
)


def compile_material_native_contribution(source: MaterialNativeSource) -> object:
    return compile_native_contribution(source, MATERIAL_NATIVE_CONTRIBUTION_RULE)
