"""Single-Atom Program builder for the C2.1 source-library resolve atom.

The builder consumes the frozen operation catalog and shared Program AST
without modifying any shared root.  The payload is exact-bound: its ValueRef
content/provenance digest closes over the project scope and channel-catalog
revision/incarnation/digest, so Program/Plan/payload/catalog cannot drift.

Canonical type ids and payload types come from the single DTO vocabulary in
``source_library_c2_1.py``, reached through the capabilities package facade.
"""

from __future__ import annotations

import dataclasses
from typing import Annotated, Any, Literal

from functorial_kit import Failure

from app.successor_runtime.capabilities import source_resolution as resolution
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
from app.successor_runtime.language.program import ProgramSpec, atom_node

__all__ = [
    "build_source_resolution_program",
    "compile_source_resolution_program",
    "exact_contract_ref",
    "payload_value_ref",
    "try_build_source_resolution_program",
    "try_exact_contract_ref",
    "try_payload_value_ref",
]


def _lift_program_failure(result: Any) -> Any:
    if isinstance(result, Failure):
        contracts.raise_source_contract_failure(result, ValueError)
    return result


def try_exact_contract_ref(
    catalog: OperationContractCatalogSnapshot,
) -> OperationContractRef | Failure:
    try:
        ref = catalog.lookup(resolution.SOURCE_RESOLUTION_KIND)
    except (AttributeError, TypeError, ValueError) as exc:
        return contracts.source_contract_failure(
            "catalog_contract_invalid",
            str(exc),
            operation="source.resolve_execution_request.exact_contract_ref",
            site="exact_contract_ref",
            owner=resolution.SOURCE_RESOLUTION_OWNER,
        )
    if ref is None:
        return contracts.source_contract_failure(
            "catalog_contract_invalid",
            f"contract {resolution.SOURCE_RESOLUTION_KIND} missing from catalog {catalog.catalog_id}",
            operation="source.resolve_execution_request.exact_contract_ref",
            site="exact_contract_ref",
            owner=resolution.SOURCE_RESOLUTION_OWNER,
        )
    return ref


def exact_contract_ref(
    catalog: OperationContractCatalogSnapshot,
) -> OperationContractRef:
    return _lift_program_failure(try_exact_contract_ref(catalog))


def try_payload_value_ref(
    payload: resolution.SourceResolutionPayload,
    *,
    program_id: str,
    project_key: str,
) -> ValueRef | Failure:
    try:
        if payload.operation_kind != resolution.SOURCE_RESOLUTION_KIND:
            return contracts.source_contract_failure(
                "schema_contract_invalid",
                "payload operation_kind is not the source resolution kind",
                operation="source.resolve_execution_request.payload_value_ref",
                site="payload_value_ref/operation_kind",
                owner=resolution.SOURCE_RESOLUTION_OWNER,
            )
        if payload.project_scope.project_key != project_key:
            return contracts.source_contract_failure(
                "scope_contract_invalid",
                "payload project scope drift",
                operation="source.resolve_execution_request.payload_value_ref",
                site="payload_value_ref/project_scope",
                owner=resolution.SOURCE_RESOLUTION_OWNER,
            )
        require_hex64(payload.catalog.digest, "payload catalog digest")
        plain = dataclasses.asdict(payload)
        exact_text = canonical_json(plain)
        exact_bytes = exact_text.encode("utf-8")
        content_digest_hex = sha256_hex(exact_bytes)
        require_hex64(payload.payload_digest, "SourceResolutionPayload.payload_digest")
    except (TypeError, ValueError, AttributeError, KeyError) as exc:
        return contracts.source_contract_failure(
            "digest_contract_invalid" if "digest" in str(exc).lower() else "schema_contract_invalid",
            str(exc),
            operation="source.resolve_execution_request.payload_value_ref",
            site="payload_value_ref",
            owner=resolution.SOURCE_RESOLUTION_OWNER,
        )
    value_id = f"{program_id}:payload:source-resolve"
    provenance_digest = content_digest(
        {
            "schema": "mrw.source.resolve-execution-request.payload-provenance.v2",
            "program_id": program_id,
            "project_key": project_key,
            "project_registry_revision": payload.project_scope.registry_revision,
            "resolved_schema": payload.project_scope.resolved_schema,
            "project_scope_incarnation": payload.project_scope.incarnation,
            "project_scope_digest": payload.project_scope.scope_digest,
            "catalog_revision": payload.catalog.revision,
            "catalog_incarnation": payload.catalog.incarnation,
            "catalog_digest": payload.catalog.digest,
            "item_revision": payload.item.revision,
            "item_incarnation": payload.item.incarnation,
            "item_content_digest": payload.item.content_digest,
            "content_digest": content_digest_hex,
        }
    )
    return ValueRef(
        value_id=value_id,
        project_key=project_key,
        object_type=resolution.SOURCE_RESOLUTION_PAYLOAD_TYPE,
        codec_id=resolution.SOURCE_RESOLUTION_PAYLOAD_CODEC_ID,
        content_digest=content_digest_hex,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(exact_bytes),
        provenance_digest=provenance_digest,
    )


def payload_value_ref(
    payload: resolution.SourceResolutionPayload,
    *,
    program_id: str,
    project_key: str,
) -> ValueRef:
    return _lift_program_failure(try_payload_value_ref(payload, program_id=program_id, project_key=project_key))


def build_source_resolution_program(
    *,
    payload: resolution.SourceResolutionPayload,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
    semantic_identity: str = resolution.SOURCE_RESOLUTION_SEMANTIC_IDENTITY,
    observation_profile: str = resolution.SOURCE_RESOLUTION_OBSERVATION_PROFILE,
    contract_version: str = "mrw.functorial-successor.program-spec.v1",
) -> Annotated[
    ProgramSpec,
    Literal[
        "kit:non-authoritative derived_as=view fact_source=payload+catalog+program_inputs witness=test:test_w06_successor_authority_metadata"
    ],
]:
    return _lift_program_failure(
        try_build_source_resolution_program(
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


def try_build_source_resolution_program(
    *,
    payload: resolution.SourceResolutionPayload,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
    semantic_identity: str = resolution.SOURCE_RESOLUTION_SEMANTIC_IDENTITY,
    observation_profile: str = resolution.SOURCE_RESOLUTION_OBSERVATION_PROFILE,
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
            operation="source.resolve_execution_request.build_program",
            site="build_program/project_key",
            owner=resolution.SOURCE_RESOLUTION_OWNER,
        )
    if payload.project_scope.registry_revision != project_registry_revision:
        return contracts.source_contract_failure(
            "scope_contract_invalid",
            "payload registry revision does not match Program registry revision",
            operation="source.resolve_execution_request.build_program",
            site="build_program/registry_revision",
            owner=resolution.SOURCE_RESOLUTION_OWNER,
        )
    if payload.project_scope.scope_digest != project_scope_digest:
        return contracts.source_contract_failure(
            "scope_contract_invalid",
            "payload scope digest does not match Program scope digest",
            operation="source.resolve_execution_request.build_program",
            site="build_program/scope_digest",
            owner=resolution.SOURCE_RESOLUTION_OWNER,
        )
    ref_result = try_exact_contract_ref(catalog)
    if isinstance(ref_result, Failure):
        return ref_result
    value_result = try_payload_value_ref(
        payload,
        program_id=program_id,
        project_key=project_key,
    )
    if isinstance(value_result, Failure):
        return value_result
    ref = ref_result
    value_ref = value_result
    operation = OperationSpec(
        operation_id=resolution.SOURCE_RESOLUTION_OPERATION_ID,
        contract_ref=ref,
        input_refs=(value_ref,),
        payload_ref=value_ref,
        allowed_overrides=freeze_json_object({}),
    )
    root = atom_node(
        operation,
        input_type=resolution.SOURCE_RESOLUTION_PAYLOAD_TYPE,
        output_type=resolution.SOURCE_RESOLUTION_RESULT_TYPE,
    )
    metadata = freeze_json_object(
        {
            "schema": "mrw.source.resolve-execution-request.program-metadata.v2",
            "operation_kind": resolution.SOURCE_RESOLUTION_KIND,
            "project_registry_revision": project_registry_revision,
            "resolved_schema": payload.project_scope.resolved_schema,
            "project_scope_incarnation": payload.project_scope.incarnation,
            "project_scope_digest": project_scope_digest,
            "catalog_revision": payload.catalog.revision,
            "catalog_incarnation": payload.catalog.incarnation,
            "catalog_digest": payload.catalog.digest,
            "item_revision": payload.item.revision,
            "item_incarnation": payload.item.incarnation,
            "item_content_digest": payload.item.content_digest,
            "payload_value_id": value_ref.value_id,
            "payload_storage_ref": value_ref.storage_ref,
            "payload_content_digest": value_ref.content_digest,
            "payload_provenance_digest": value_ref.provenance_digest,
            "canonical_owner": resolution.SOURCE_RESOLUTION_OWNER,
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


def compile_source_resolution_program(
    program: ProgramSpec,
    catalog: OperationContractCatalogSnapshot,
    *,
    operation_contracts: OperationContractResolver,
) -> Any:
    """Compile the C2.1 Program through the shared compiler."""

    return compile_program(
        program,
        catalog,
        operation_contracts=operation_contracts,
    )
