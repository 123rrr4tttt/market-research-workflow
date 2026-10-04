"""Single-Atom Program builder for the C6.2 provider-step atom."""

from __future__ import annotations

import dataclasses
from typing import Annotated, Any

from functorial_kit import Failure
from app.successor_runtime.capabilities import agent_core_c6_2 as c6_2
from app.successor_runtime.capabilities.checksum import (
    canonical_json,
    content_digest,
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
    "build_agent_core_c6_2_program",
    "compile_agent_core_c6_2_program",
    "exact_contract_ref",
    "payload_value_ref",
    "try_exact_contract_ref",
    "try_payload_value_ref",
    "try_build_agent_core_c6_2_program",
]


def _lift_program_contract_failure(outcome: ProgramSpec | ValueRef | Failure) -> Any:
    if isinstance(outcome, Failure):
        c6_2._raise_contract_failure(outcome)
    return outcome


def try_exact_contract_ref(
    catalog: OperationContractCatalogSnapshot,
) -> OperationContractRef | Failure:
    ref = catalog.lookup(c6_2.AGENT_CORE_C6_2_KIND)
    if ref is None:
        return c6_2._contract_failure(
            "catalog_contract_invalid",
            f"contract {c6_2.AGENT_CORE_C6_2_KIND} missing from catalog {catalog.catalog_id}",
            catalog_id=catalog.catalog_id,
            operation_kind=c6_2.AGENT_CORE_C6_2_KIND,
        )
    return ref


def exact_contract_ref(
    catalog: OperationContractCatalogSnapshot,
) -> OperationContractRef:
    return _lift_program_contract_failure(try_exact_contract_ref(catalog))


def try_payload_value_ref(
    payload: c6_2.AgentModelStepRequest,
    *,
    program_id: str,
    project_key: str,
) -> ValueRef | Failure:
    """Build the exact content-addressed ValueRef for one C6.2 request."""

    if payload.operation_kind != c6_2.AGENT_CORE_C6_2_KIND:
        return c6_2._contract_failure(
            "schema_contract_invalid",
            "payload operation_kind is not the frozen C6.2 kind",
            operation_kind=payload.operation_kind,
        )
    if payload.project_scope.project_key != project_key:
        return c6_2._contract_failure(
            "scope_contract_invalid",
            "payload project scope drift",
            payload_project_key=payload.project_scope.project_key,
            program_project_key=project_key,
        )
    digest = payload.payload_digest
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        return c6_2._contract_failure(
            "digest_contract_invalid",
            "AgentModelStepRequest.payload_digest must be a 64-char lowercase hex digest",
            field="payload_digest",
        )
    plain = dataclasses.asdict(payload)
    exact_text = canonical_json(plain)
    exact_bytes = exact_text.encode("utf-8")
    content_digest_hex = sha256_hex(exact_bytes)
    value_id = f"{program_id}:payload:c6-2"
    provenance_digest = content_digest(
        {
            "schema": "mrw.successor.agent-core.c6-2.payload-provenance.v1",
            "program_id": program_id,
            "project_key": project_key,
            "project_registry_revision": payload.project_scope.registry_revision,
            "resolved_schema": payload.project_scope.resolved_schema,
            "project_scope_incarnation": payload.project_scope.incarnation,
            "project_scope_digest": payload.project_scope.scope_digest,
            "session_id": payload.session_id,
            "turn_id": payload.turn_id,
            "message_ref": payload.message_ref,
            "transcript_ref": payload.transcript_ref,
            "tool_contract_refs": payload.tool_contract_refs,
            "provider_profile_ref": payload.provider_profile_ref,
            "credential_ref": payload.credential_ref,
            "content_digest": content_digest_hex,
        }
    )
    return ValueRef(
        value_id=value_id,
        project_key=project_key,
        object_type=c6_2.AGENT_CORE_C6_2_PAYLOAD_TYPE,
        codec_id=c6_2.AGENT_CORE_C6_2_PAYLOAD_CODEC_ID,
        content_digest=content_digest_hex,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(exact_bytes),
        provenance_digest=provenance_digest,
    )


def payload_value_ref(
    payload: c6_2.AgentModelStepRequest,
    *,
    program_id: str,
    project_key: str,
) -> ValueRef:
    return _lift_program_contract_failure(
        try_payload_value_ref(
            payload,
            program_id=program_id,
            project_key=project_key,
        )
    )


def try_build_agent_core_c6_2_program(
    *,
    payload: c6_2.AgentModelStepRequest,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
    semantic_identity: str = c6_2.AGENT_CORE_C6_2_SEMANTIC_IDENTITY,
    observation_profile: str = c6_2.AGENT_CORE_C6_2_OBSERVATION_PROFILE,
    contract_version: str = "mrw.functorial-successor.program-spec.v1",
) -> (
    Annotated[
        ProgramSpec,
        "kit:prepared-command effect_boundary=successor_program_interpreter "
        "witness=test:test_w05_agent_core_authority_metadata",
    ]
    | Failure
):
    """Build the exact-bound single-Atom Program for one C6.2 request."""

    if payload.project_scope.project_key != project_key:
        return c6_2._contract_failure(
            "scope_contract_invalid",
            "payload project_key does not match Program project_key",
            payload_project_key=payload.project_scope.project_key,
            program_project_key=project_key,
        )
    if payload.project_scope.registry_revision != project_registry_revision:
        return c6_2._contract_failure(
            "scope_contract_invalid",
            "payload registry revision does not match Program registry revision",
            payload_registry_revision=payload.project_scope.registry_revision,
            program_registry_revision=project_registry_revision,
        )
    if payload.project_scope.scope_digest != project_scope_digest:
        return c6_2._contract_failure(
            "scope_contract_invalid",
            "payload scope digest does not match Program scope digest",
            payload_scope_digest=payload.project_scope.scope_digest,
            program_scope_digest=project_scope_digest,
        )
    exact_ref = try_exact_contract_ref(catalog)
    if isinstance(exact_ref, Failure):
        return exact_ref
    value_ref = try_payload_value_ref(
        payload,
        program_id=program_id,
        project_key=project_key,
    )
    if isinstance(value_ref, Failure):
        return value_ref
    ref = exact_ref
    operation = OperationSpec(
        operation_id=c6_2.AGENT_CORE_C6_2_OPERATION_ID,
        contract_ref=ref,
        input_refs=(value_ref,),
        payload_ref=value_ref,
        allowed_overrides=freeze_json_object({}),
    )
    root = atom_node(
        operation,
        input_type=c6_2.AGENT_CORE_C6_2_PAYLOAD_TYPE,
        output_type=c6_2.AGENT_CORE_C6_2_RESULT_TYPE,
    )
    metadata = freeze_json_object(
        {
            "schema": "mrw.successor.agent-core.c6-2.program-metadata.v1",
            "operation_kind": c6_2.AGENT_CORE_C6_2_KIND,
            "project_registry_revision": project_registry_revision,
            "resolved_schema": payload.project_scope.resolved_schema,
            "project_scope_incarnation": payload.project_scope.incarnation,
            "project_scope_digest": project_scope_digest,
            "session_id": payload.session_id,
            "turn_id": payload.turn_id,
            "message_ref": payload.message_ref,
            "transcript_ref": payload.transcript_ref,
            "tool_contract_refs": payload.tool_contract_refs,
            "provider_profile_ref": payload.provider_profile_ref,
            "credential_ref": payload.credential_ref,
            "iteration": payload.iteration,
            "max_iterations": payload.max_iterations,
            "remaining_tool_calls": payload.remaining_tool_calls,
            "payload_value_id": value_ref.value_id,
            "payload_storage_ref": value_ref.storage_ref,
            "payload_content_digest": value_ref.content_digest,
            "payload_provenance_digest": value_ref.provenance_digest,
            "canonical_owner": c6_2.AGENT_CORE_C6_2_OWNER,
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


def build_agent_core_c6_2_program(
    *,
    payload: c6_2.AgentModelStepRequest,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
    semantic_identity: str = c6_2.AGENT_CORE_C6_2_SEMANTIC_IDENTITY,
    observation_profile: str = c6_2.AGENT_CORE_C6_2_OBSERVATION_PROFILE,
    contract_version: str = "mrw.functorial-successor.program-spec.v1",
) -> Annotated[
    ProgramSpec,
    "kit:prepared-command effect_boundary=successor_program_interpreter "
    "witness=test:test_w05_agent_core_authority_metadata",
]:
    return _lift_program_contract_failure(
        try_build_agent_core_c6_2_program(
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


def compile_agent_core_c6_2_program(
    program: ProgramSpec,
    catalog: OperationContractCatalogSnapshot,
    *,
    operation_contracts: OperationContractResolver,
) -> Any:
    """Compile the C6.2 Program through the shared compiler."""

    return compile_program(
        program,
        catalog,
        operation_contracts=operation_contracts,
    )
