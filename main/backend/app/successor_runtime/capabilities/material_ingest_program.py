"""Shared ProgramSpec/compiler builders for the C7.1 staged candidate atom.

The C7.1 atom compiles through the shared successor Program AST and compiler
as one exact ``ProgramSpec`` with one EFFECT step and one CompiledAdmission
step.  No C7-owned shadow Program/Plan vocabulary exists here.
"""

from __future__ import annotations

import dataclasses
from typing import Annotated, Any, Literal

from app.successor_runtime.capabilities import material_ingest_common as material
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    require_hex64,
)
from app.successor_runtime.language.algebra import (
    AlgebraRef,
    OperationSpec,
    ValueRef,
    freeze_json_object,
)
from app.successor_runtime.language.catalog import (
    OperationContractCatalogSnapshot,
)
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    OperationContractResolver,
)
from app.successor_runtime.language.program import ProgramSpec, atom_node

__all__ = [
    "build_material_stage_candidate_program",
    "compile_material_ingest_program",
    "exact_contract_ref",
    "payload_value_ref",
]


def exact_contract_ref(
    catalog: OperationContractCatalogSnapshot,
    *,
    kind: str,
) -> OperationContractRef:
    ref = catalog.lookup(kind)
    if ref is None:
        material.raise_material_ingest_contract_failure(
            material.material_ingest_contract_failure(
                "lookup_not_found",
                f"contract {kind} missing from catalog {catalog.catalog_id}",
                operation="material.ingest.program",
                site="exact_contract_ref",
            )
        )
    return ref


def payload_value_ref(
    payload: material.MaterialIngestSubmission,
    *,
    program_id: str,
    project_key: str,
    codec_id: str,
    value_suffix: str,
) -> ValueRef:
    """Exact content-addressed ValueRef for the C7.1 payload."""

    if payload.project_key != project_key:
        material.raise_material_ingest_contract_failure(
            material.material_ingest_contract_failure(
                "program_binding_invalid",
                "payload project scope drift",
                operation="material.ingest.program",
                site="payload_value_ref/project_key",
            )
        )
    plain = dataclasses.asdict(payload)
    exact_text = canonical_json(plain)
    exact_bytes = exact_text.encode("utf-8")
    require_hex64(payload.payload_digest, "payload payload_digest")
    value_id = f"{program_id}:payload:{value_suffix}"
    provenance_digest = content_digest(
        {
            "schema": "mrw.material.ingest.stage-candidate.payload-provenance.v2",
            "program_id": program_id,
            "project_key": project_key,
            "payload_digest": payload.payload_digest,
            "content_digest": payload.payload_digest,
        }
    )
    return ValueRef(
        value_id=value_id,
        project_key=project_key,
        object_type=material.MATERIAL_STAGE_CANDIDATE_PAYLOAD_TYPE,
        codec_id=codec_id,
        content_digest=payload.payload_digest,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(exact_bytes),
        provenance_digest=provenance_digest,
    )


def build_material_stage_candidate_program(
    *,
    payload: material.MaterialIngestSubmission,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
) -> Annotated[ProgramSpec, Literal["kit:non-authoritative derived_as=view fact_source=payload+catalog+program_inputs witness=test:test_w06_successor_authority_metadata"]]:
    """Compilable single-Atom Program for the C7.1 staged candidate."""

    if payload.project_key != project_key:
        material.raise_material_ingest_contract_failure(
            material.material_ingest_contract_failure(
                "program_binding_invalid",
                "payload project_key does not match Program project_key",
                operation="material.ingest.program",
                site="build_ingest_c7_1_program/project_key",
            )
        )
    ref = exact_contract_ref(catalog, kind=material.MATERIAL_STAGE_CANDIDATE_KIND)
    value_ref = payload_value_ref(
        payload,
        program_id=program_id,
        project_key=project_key,
        codec_id=material.MATERIAL_STAGE_CANDIDATE_PAYLOAD_CODEC_ID,
        value_suffix="material-stage-candidate",
    )
    operation = OperationSpec(
        operation_id=material.MATERIAL_STAGE_CANDIDATE_OPERATION_ID,
        contract_ref=ref,
        input_refs=(value_ref,),
        payload_ref=value_ref,
        allowed_overrides=freeze_json_object({}),
    )
    root = atom_node(
        operation,
        input_type=material.MATERIAL_STAGE_CANDIDATE_PAYLOAD_TYPE,
        output_type=material.STAGED_MATERIAL_CANDIDATE_RESULT_TYPE,
    )
    metadata = freeze_json_object(
        {
            "schema": "mrw.material.ingest.stage-candidate.program-metadata.v2",
            "operation_kind": material.MATERIAL_STAGE_CANDIDATE_KIND,
            "project_registry_revision": project_registry_revision,
            "project_scope_digest": project_scope_digest,
            "payload_value_id": value_ref.value_id,
            "payload_storage_ref": value_ref.storage_ref,
            "payload_content_digest": value_ref.content_digest,
            "payload_provenance_digest": value_ref.provenance_digest,
            "canonical_owner": material.MATERIAL_INGEST_OWNER,
            "return_contract_ref": material.MATERIAL_ADMISSION_RETURN_CONTRACT_REF,
            "admission_required": True,
        }
    )
    return ProgramSpec(
        program_id=program_id,
        contract_version="mrw.functorial-successor.program-spec.v1",
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        semantic_identity=material.MATERIAL_OPERATION_SEMANTIC_IDENTITY,
        input_type=root.input_type,
        output_type=root.output_type,
        root=root,
        algebra_refs=(
            AlgebraRef(
                algebra_id="mrw.successor.language.algebra",
                algebra_version="1",
            ),
        ),
        transform_refs=(),
        observation_profile=material.MATERIAL_OBSERVATION_PROFILE,
        metadata=metadata,
        program_digest="",
    ).with_digest()


def compile_material_ingest_program(
    program: ProgramSpec,
    catalog: OperationContractCatalogSnapshot,
    *,
    operation_contracts: OperationContractResolver,
) -> Any:
    """Compile the C7.1 Program through the shared compiler."""

    return compile_program(
        program,
        catalog,
        operation_contracts=operation_contracts,
    )
