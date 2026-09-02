"""Program builders for the four pure C2.2 source-mode planner atoms.

Each planner compiles one exact C2.1-bound ``SourceModePlanningPayload`` into
one Atom Program.  The payload ValueRef and Program metadata close over the
exact C2.1 request digest, project scope and channel catalog identity.

The durable ``Then(C2.1 resolve, Decide(...)) -> MaterializeSuccessor ->
TraverseOrdered(C2.3 execute)`` composition is an integration-line concern
(per the frozen P3 C2 design) and needs shared runtime composition roots.
This family-local line proves the language-level chain with an exact
``SuccessorMaterialization`` record tying a C2.1 program/plan/value to the
successor C2.2 program.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from app.successor_runtime.capabilities import source_library_c2_shared as c2_2
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
    require_hex64,
    sha256_hex,
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
from app.successor_runtime.language.program import (
    ProgramSpec,
    SuccessorMaterialization,
    atom_node,
)

__all__ = [
    "build_c2_1_to_c2_2_materialization",
    "build_source_library_c2_2_program",
    "compile_source_library_c2_2_program",
    "exact_contract_ref",
    "planning_payload_value_ref",
]


def exact_contract_ref(
    catalog: OperationContractCatalogSnapshot,
    kind: str,
) -> OperationContractRef:
    ref = catalog.lookup(kind)
    if ref is None:
        raise ValueError(f"contract {kind} missing from catalog {catalog.catalog_id}")
    return ref


def planning_payload_value_ref(
    payload: c2_2.SourceModePlanningPayload,
    *,
    program_id: str,
    project_key: str,
) -> ValueRef:
    """Build the exact content-addressed ValueRef for one C2.2 payload."""

    if payload.project_scope.project_key != project_key:
        raise ValueError("payload project scope drift")
    require_hex64(payload.payload_digest, "SourceModePlanningPayload.payload_digest")
    plain = dataclasses.asdict(payload)
    exact_text = canonical_json(plain)
    exact_bytes = exact_text.encode("utf-8")
    content_digest_hex = sha256_hex(exact_bytes)
    value_id = f"{program_id}:payload:c2-2"
    provenance_digest = content_digest(
        {
            "schema": "mrw.successor.source-library.c2-2.payload-provenance.v1",
            "program_id": program_id,
            "project_key": project_key,
            "project_scope_digest": payload.project_scope.scope_digest,
            "execution_request_digest": payload.execution_request_digest,
            "catalog_revision": payload.catalog.revision,
            "catalog_incarnation": payload.catalog.incarnation,
            "catalog_digest": payload.catalog.digest,
            "item_revision": payload.item_revision,
            "item_incarnation": payload.item_incarnation,
            "item_content_digest": payload.item_content_digest,
            "content_digest": content_digest_hex,
        }
    )
    return ValueRef(
        value_id=value_id,
        project_key=project_key,
        object_type=c2_2.SOURCE_MODE_PLANNING_PAYLOAD_TYPE,
        codec_id=_codec_id_for(payload.operation_kind),
        content_digest=content_digest_hex,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(exact_bytes),
        provenance_digest=provenance_digest,
    )


def _codec_id_for(kind: str) -> str:
    mode = c2_2.mode_for_kind(kind)
    return f"mrw.successor.source-library.c2-2.{mode}.codec.v1"


def build_source_library_c2_2_program(
    *,
    payload: c2_2.SourceModePlanningPayload,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
    semantic_identity: str | None = None,
    observation_profile: str = c2_2.SOURCE_MODE_PLANNING_OBSERVATION_PROFILE,
    contract_version: str = "mrw.functorial-successor.program-spec.v1",
) -> ProgramSpec:
    """Build the exact-bound single-Atom Program for one C2.2 payload."""

    if payload.project_scope.project_key != project_key:
        raise ValueError("payload project_key does not match Program project_key")
    if payload.project_scope.scope_digest != project_scope_digest:
        raise ValueError("payload scope digest does not match Program scope digest")
    ref = exact_contract_ref(catalog, payload.operation_kind)
    value_ref = planning_payload_value_ref(
        payload,
        program_id=program_id,
        project_key=project_key,
    )
    operation = OperationSpec(
        operation_id=payload.operation_kind,
        contract_ref=ref,
        input_refs=(value_ref,),
        payload_ref=value_ref,
        allowed_overrides=freeze_json_object({}),
    )
    root = atom_node(
        operation,
        input_type=c2_2.SOURCE_MODE_PLANNING_PAYLOAD_TYPE,
        output_type=c2_2.SOURCE_MODE_PLANNING_RESULT_TYPE,
    )
    mode = c2_2.mode_for_kind(payload.operation_kind)
    metadata = freeze_json_object(
        {
            "schema": "mrw.successor.source-library.c2-2.program-metadata.v1",
            "operation_kind": payload.operation_kind,
            "mode": mode,
            "project_registry_revision": project_registry_revision,
            "resolved_schema": payload.project_scope.resolved_schema,
            "project_scope_incarnation": payload.project_scope.incarnation,
            "project_scope_digest": project_scope_digest,
            "execution_request_digest": payload.execution_request_digest,
            "catalog_revision": payload.catalog.revision,
            "catalog_incarnation": payload.catalog.incarnation,
            "catalog_digest": payload.catalog.digest,
            "item_revision": payload.item_revision,
            "item_incarnation": payload.item_incarnation,
            "item_content_digest": payload.item_content_digest,
            "orchestration_policy_ref": payload.orchestration_policy_ref,
            "resource_ceiling_digest": payload.resource_ceiling_digest,
            "payload_value_id": value_ref.value_id,
            "payload_storage_ref": value_ref.storage_ref,
            "payload_content_digest": value_ref.content_digest,
            "payload_provenance_digest": value_ref.provenance_digest,
            "canonical_owner": c2_2.SOURCE_LIBRARY_C2_2_OWNER,
        }
    )
    return ProgramSpec(
        program_id=program_id,
        contract_version=contract_version,
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        semantic_identity=semantic_identity or f"source-library.plan.{mode}",
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
        observation_profile=observation_profile,
        metadata=metadata,
        program_digest="",
    ).with_digest()


def compile_source_library_c2_2_program(
    program: ProgramSpec,
    catalog: OperationContractCatalogSnapshot,
    *,
    operation_contracts: OperationContractResolver,
) -> Any:
    return compile_program(
        program,
        catalog,
        operation_contracts=operation_contracts,
    )


def build_c2_1_to_c2_2_materialization(
    *,
    materialization_id: str,
    predecessor_run_id: str,
    predecessor_step_id: str,
    predecessor_plan_digest: str,
    source_value_ref: ValueRef,
    authority_digest: str,
    idempotency_key: str,
    successor_program: ProgramSpec,
    state: str = "MATERIALIZED",
) -> SuccessorMaterialization:
    """Record the exact C2.1 -> C2.2 language-level chain.

    The record proves the successor C2.2 program consumes a materialized value
    bound to one C2.1 program/plan/value closure without executing any effect.
    """

    return SuccessorMaterialization(
        materialization_id=materialization_id,
        predecessor_run_id=predecessor_run_id,
        predecessor_step_id=predecessor_step_id,
        predecessor_plan_digest=predecessor_plan_digest,
        source_value_ref=source_value_ref,
        materializer_id="source-library.c2-1-to-c2-2.materializer.v1",
        materializer_version="1.0.0",
        authority_digest=authority_digest,
        idempotency_key=idempotency_key,
        successor_program=successor_program,
        successor_program_digest=successor_program.program_digest,
        state=state,  # type: ignore[arg-type]
        reason="exact C2.1 resolved request materialized into C2.2 planner payload",
    )
