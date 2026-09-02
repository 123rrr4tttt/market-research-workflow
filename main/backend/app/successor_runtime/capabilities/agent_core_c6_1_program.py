"""Single-Atom Program builder for the C6.1 bounded episode atom."""

from __future__ import annotations

import dataclasses
from typing import Any

from app.successor_runtime.capabilities import agent_core_c6_1 as c6_1
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
from app.successor_runtime.language.catalog import OperationContractCatalogSnapshot
from app.successor_runtime.language.compile import compile_program
from app.successor_runtime.language.object_contracts import (
    OperationContractRef,
    OperationContractResolver,
)
from app.successor_runtime.language.program import ProgramSpec, atom_node

__all__ = [
    "build_agent_core_c6_1_program",
    "compile_agent_core_c6_1_program",
    "exact_contract_ref",
    "payload_value_ref",
]


def exact_contract_ref(
    catalog: OperationContractCatalogSnapshot,
) -> OperationContractRef:
    ref = catalog.lookup(c6_1.AGENT_CORE_C6_1_KIND)
    if ref is None:
        raise ValueError(
            f"contract {c6_1.AGENT_CORE_C6_1_KIND} missing from catalog "
            f"{catalog.catalog_id}"
        )
    return ref


def payload_value_ref(
    payload: c6_1.AgentTurnRequest,
    *,
    program_id: str,
    project_key: str,
) -> ValueRef:
    """Build the exact content-addressed ValueRef for one C6.1 request."""

    if payload.operation_kind != c6_1.AGENT_CORE_C6_1_KIND:
        raise ValueError("payload operation_kind is not the frozen C6.1 kind")
    if payload.project_scope.project_key != project_key:
        raise ValueError("payload project scope drift")
    require_hex64(payload.payload_digest, "AgentTurnRequest.payload_digest")
    plain = dataclasses.asdict(payload)
    exact_text = canonical_json(plain)
    exact_bytes = exact_text.encode("utf-8")
    content_digest_hex = sha256_hex(exact_bytes)
    value_id = f"{program_id}:payload:c6-1"
    provenance_digest = content_digest(
        {
            "schema": "mrw.successor.agent-core.c6-1.payload-provenance.v1",
            "program_id": program_id,
            "project_key": project_key,
            "project_registry_revision": payload.project_scope.registry_revision,
            "resolved_schema": payload.project_scope.resolved_schema,
            "project_scope_incarnation": payload.project_scope.incarnation,
            "project_scope_digest": payload.project_scope.scope_digest,
            "session_id": payload.session_id,
            "turn_id": payload.turn_id,
            "message_ref": payload.message_ref,
            "max_iterations": payload.max_iterations,
            "max_tool_calls": payload.max_tool_calls,
            "approval_policy": payload.approval_policy,
            "approved_call_ids": payload.approved_call_ids,
            "resume_call_id": payload.resume_call_id,
            "cancel_requested": payload.cancel_requested,
            "content_digest": content_digest_hex,
        }
    )
    return ValueRef(
        value_id=value_id,
        project_key=project_key,
        object_type=c6_1.AGENT_CORE_C6_1_PAYLOAD_TYPE,
        codec_id=c6_1.AGENT_CORE_C6_1_PAYLOAD_CODEC_ID,
        content_digest=content_digest_hex,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(exact_bytes),
        provenance_digest=provenance_digest,
    )


def build_agent_core_c6_1_program(
    *,
    payload: c6_1.AgentTurnRequest,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
    semantic_identity: str = c6_1.AGENT_CORE_C6_1_SEMANTIC_IDENTITY,
    observation_profile: str = c6_1.AGENT_CORE_C6_1_OBSERVATION_PROFILE,
    contract_version: str = "mrw.functorial-successor.program-spec.v1",
) -> ProgramSpec:
    """Build the exact-bound single-Atom Program for one C6.1 request."""

    if payload.project_scope.project_key != project_key:
        raise ValueError("payload project_key does not match Program project_key")
    if payload.project_scope.registry_revision != project_registry_revision:
        raise ValueError(
            "payload registry revision does not match Program registry revision"
        )
    if payload.project_scope.scope_digest != project_scope_digest:
        raise ValueError("payload scope digest does not match Program scope digest")
    ref = exact_contract_ref(catalog)
    value_ref = payload_value_ref(
        payload,
        program_id=program_id,
        project_key=project_key,
    )
    operation = OperationSpec(
        operation_id=c6_1.AGENT_CORE_C6_1_OPERATION_ID,
        contract_ref=ref,
        input_refs=(value_ref,),
        payload_ref=value_ref,
        allowed_overrides=freeze_json_object({}),
    )
    root = atom_node(
        operation,
        input_type=c6_1.AGENT_CORE_C6_1_PAYLOAD_TYPE,
        output_type=c6_1.AGENT_CORE_C6_1_RESULT_TYPE,
    )
    metadata = freeze_json_object(
        {
            "schema": "mrw.successor.agent-core.c6-1.program-metadata.v1",
            "operation_kind": c6_1.AGENT_CORE_C6_1_KIND,
            "project_registry_revision": project_registry_revision,
            "resolved_schema": payload.project_scope.resolved_schema,
            "project_scope_incarnation": payload.project_scope.incarnation,
            "project_scope_digest": project_scope_digest,
            "session_id": payload.session_id,
            "turn_id": payload.turn_id,
            "message_ref": payload.message_ref,
            "max_iterations": payload.max_iterations,
            "max_tool_calls": payload.max_tool_calls,
            "approval_policy": payload.approval_policy,
            "approved_call_ids": payload.approved_call_ids,
            "resume_call_id": payload.resume_call_id,
            "cancel_requested": payload.cancel_requested,
            "payload_value_id": value_ref.value_id,
            "payload_storage_ref": value_ref.storage_ref,
            "payload_content_digest": value_ref.content_digest,
            "payload_provenance_digest": value_ref.provenance_digest,
            "canonical_owner": c6_1.AGENT_CORE_C6_1_OWNER,
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


def compile_agent_core_c6_1_program(
    program: ProgramSpec,
    catalog: OperationContractCatalogSnapshot,
    *,
    operation_contracts: OperationContractResolver,
) -> Any:
    """Compile the C6.1 Program through the shared compiler."""

    return compile_program(
        program,
        catalog,
        operation_contracts=operation_contracts,
    )
