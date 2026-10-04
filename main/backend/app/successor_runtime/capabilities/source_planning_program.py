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
from typing import Annotated, Any, Literal

from functorial_kit import Failure

from app.successor_runtime.capabilities import source_contracts as contracts
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
    "build_resolution_to_planning_materialization",
    "build_source_planning_program",
    "compile_source_planning_program",
    "exact_contract_ref",
    "planning_payload_value_ref",
    "try_build_source_planning_program",
    "try_exact_contract_ref",
    "try_planning_payload_value_ref",
]


def _lift_program_failure(result: Any) -> Any:
    if isinstance(result, Failure):
        contracts.raise_source_contract_failure(result, ValueError)
    return result


def try_exact_contract_ref(
    catalog: OperationContractCatalogSnapshot,
    kind: str,
) -> OperationContractRef | Failure:
    try:
        ref = catalog.lookup(kind)
    except (AttributeError, TypeError, ValueError) as exc:
        return contracts.source_contract_failure(
            "catalog_contract_invalid",
            str(exc),
            operation="source.plan_source_mode.exact_contract_ref",
            site="exact_contract_ref",
            owner=contracts.SOURCE_PLANNING_OWNERS[kind],
        )
    if ref is None:
        return contracts.source_contract_failure(
            "catalog_contract_invalid",
            f"contract {kind} missing from catalog {catalog.catalog_id}",
            operation="source.plan_source_mode.exact_contract_ref",
            site="exact_contract_ref",
            owner=contracts.SOURCE_PLANNING_OWNERS[kind],
        )
    return ref


def exact_contract_ref(
    catalog: OperationContractCatalogSnapshot,
    kind: str,
) -> OperationContractRef:
    return _lift_program_failure(try_exact_contract_ref(catalog, kind))


def try_planning_payload_value_ref(
    payload: contracts.SourceModePlanningPayload,
    *,
    program_id: str,
    project_key: str,
) -> ValueRef | Failure:
    try:
        if payload.project_scope.project_key != project_key:
            return contracts.source_contract_failure(
                "scope_contract_invalid",
                "payload project scope drift",
                operation="source.plan_source_mode.planning_payload_value_ref",
                site="planning_payload_value_ref/project_scope",
                owner=contracts.SOURCE_PLANNING_OWNERS[payload.operation_kind],
            )
        require_hex64(payload.payload_digest, "SourceModePlanningPayload.payload_digest")
        plain = dataclasses.asdict(payload)
        exact_text = canonical_json(plain)
        exact_bytes = exact_text.encode("utf-8")
        content_digest_hex = sha256_hex(exact_bytes)
    except (TypeError, ValueError, AttributeError, KeyError) as exc:
        return contracts.source_contract_failure(
            "digest_contract_invalid" if "digest" in str(exc).lower() else "schema_contract_invalid",
            str(exc),
            operation="source.plan_source_mode.planning_payload_value_ref",
            site="planning_payload_value_ref",
            owner=contracts.SOURCE_PLANNING_OWNERS[payload.operation_kind],
        )
    value_id = f"{program_id}:payload:source-plan"
    provenance_digest = content_digest(
        {
            "schema": "mrw.source.plan-source-mode.payload-provenance.v2",
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
        object_type=contracts.SOURCE_MODE_PLANNING_PAYLOAD_TYPE,
        codec_id=_codec_id_for(payload.operation_kind),
        content_digest=content_digest_hex,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(exact_bytes),
        provenance_digest=provenance_digest,
    )


def planning_payload_value_ref(
    payload: contracts.SourceModePlanningPayload,
    *,
    program_id: str,
    project_key: str,
) -> Annotated[
    ValueRef,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=SourceModePlanningPayload witness=test:test_w06_successor_authority_metadata"
    ],
]:
    return _lift_program_failure(
        try_planning_payload_value_ref(
            payload,
            program_id=program_id,
            project_key=project_key,
        )
    )


def _codec_id_for(kind: str) -> str:
    return contracts.SOURCE_PLANNING_CODEC_IDS[kind]


def build_source_planning_program(
    *,
    payload: contracts.SourceModePlanningPayload,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
    semantic_identity: str | None = None,
    observation_profile: str = contracts.SOURCE_MODE_PLANNING_OBSERVATION_PROFILE,
    contract_version: str = "mrw.functorial-successor.program-spec.v1",
) -> Annotated[
    ProgramSpec,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=payload+catalog+program_inputs witness=test:test_w06_successor_authority_metadata"
    ],
]:
    return _lift_program_failure(
        try_build_source_planning_program(
            payload=payload,
            catalog=catalog,
            program_id=program_id,
            project_key=project_key,
            project_registry_revision=project_registry_revision,
            project_scope_digest=project_scope_digest,
            semantic_identity=semantic_identity,
            observation_profile=observation_profile,
            contract_version=contract_version,
        )
    )


def try_build_source_planning_program(
    *,
    payload: contracts.SourceModePlanningPayload,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
    semantic_identity: str | None = None,
    observation_profile: str = contracts.SOURCE_MODE_PLANNING_OBSERVATION_PROFILE,
    contract_version: str = "mrw.functorial-successor.program-spec.v1",
) -> (
    Annotated[
        ProgramSpec,
        Literal[
            "kit:non-authoritative derived_as=view fact_source=payload+catalog+program_inputs witness=test:test_w06_successor_authority_metadata"
        ],
    ]
    | Failure
):
    """Total exact-bound Program construction; legacy entry lifts failures."""
    if payload.project_scope.project_key != project_key:
        return contracts.source_contract_failure(
            "scope_contract_invalid",
            "payload project_key does not match Program project_key",
            operation="source.plan_source_mode.build_program",
            site="build_program/project_key",
            owner=contracts.SOURCE_PLANNING_OWNERS[payload.operation_kind],
        )
    if payload.project_scope.scope_digest != project_scope_digest:
        return contracts.source_contract_failure(
            "scope_contract_invalid",
            "payload scope digest does not match Program scope digest",
            operation="source.plan_source_mode.build_program",
            site="build_program/scope_digest",
            owner=contracts.SOURCE_PLANNING_OWNERS[payload.operation_kind],
        )
    ref_result = try_exact_contract_ref(catalog, payload.operation_kind)
    if isinstance(ref_result, Failure):
        return ref_result
    value_result = try_planning_payload_value_ref(
        payload,
        program_id=program_id,
        project_key=project_key,
    )
    if isinstance(value_result, Failure):
        return value_result
    ref = ref_result
    value_ref = value_result
    operation = OperationSpec(
        operation_id=payload.operation_kind,
        contract_ref=ref,
        input_refs=(value_ref,),
        payload_ref=value_ref,
        allowed_overrides=freeze_json_object({}),
    )
    root = atom_node(
        operation,
        input_type=contracts.SOURCE_MODE_PLANNING_PAYLOAD_TYPE,
        output_type=contracts.SOURCE_MODE_PLANNING_RESULT_TYPE,
    )
    mode_result = contracts.try_mode_for_kind(payload.operation_kind)
    if isinstance(mode_result, Failure):
        return mode_result
    mode = mode_result
    metadata = freeze_json_object(
        {
            "schema": "mrw.source.plan-source-mode.program-metadata.v2",
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
            "canonical_owner": contracts.SOURCE_PLANNING_OWNERS[payload.operation_kind],
        }
    )
    return ProgramSpec(
        program_id=program_id,
        contract_version=contract_version,
        project_key=project_key,
        project_registry_revision=project_registry_revision,
        project_scope_digest=project_scope_digest,
        semantic_identity=semantic_identity or f"source.plan-{mode}.v2",
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


def compile_source_planning_program(
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


def build_resolution_to_planning_materialization(
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
) -> Annotated[
    SuccessorMaterialization,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=C2.1_successor_chain_inputs witness=test:test_w06_successor_authority_metadata"
    ],
]:
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
        materializer_id="source.resolve-to-plan.materializer.v2",
        materializer_version="2.0.0",
        authority_digest=authority_digest,
        idempotency_key=idempotency_key,
        successor_program=successor_program,
        successor_program_digest=successor_program.program_digest,
        state=state,  # type: ignore[arg-type]
        reason="exact resolved source request materialized into source planning payload",
    )
