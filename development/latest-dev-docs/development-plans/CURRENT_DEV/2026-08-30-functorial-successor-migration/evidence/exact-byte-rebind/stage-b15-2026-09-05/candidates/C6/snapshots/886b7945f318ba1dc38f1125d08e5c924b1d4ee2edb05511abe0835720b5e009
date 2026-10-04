"""Single-Atom Program builder for the C6.3 redaction atom.

The payload is exact-bound: its ValueRef content/provenance digest closes over
the project scope and the source/policy digest without ever containing raw
source bytes.  The same Program is consumed by the legacy evidence adapter and
the successor pre-persistence interpreter.
"""

from __future__ import annotations

import dataclasses
from typing import Annotated, Any

from functorial_kit import Failure

from app.successor_runtime.capabilities import agent_core_c6_3 as c6_3
from app.successor_runtime.capabilities.agent_core_c6_3 import (
    _contract_failure,
    _hex64_failure,
    _raise_contract_failure,
)
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
    "build_agent_core_c6_3_program",
    "compile_agent_core_c6_3_program",
    "exact_contract_ref",
    "payload_value_ref",
    "try_build_agent_core_c6_3_program",
    "try_exact_contract_ref",
    "try_payload_value_ref",
]


def _lift_program_contract_failure(
    outcome: ProgramSpec | ValueRef | OperationContractRef | Failure,
) -> Any:
    if isinstance(outcome, Failure):
        _raise_contract_failure(outcome)
    return outcome


def try_exact_contract_ref(
    catalog: OperationContractCatalogSnapshot,
) -> OperationContractRef | Failure:
    ref = catalog.lookup(c6_3.AGENT_CORE_C6_3_KIND)
    if ref is None:
        return _contract_failure(
            "catalog_contract_invalid",
            f"contract {c6_3.AGENT_CORE_C6_3_KIND} missing from catalog {catalog.catalog_id}",
            contract_kind=c6_3.AGENT_CORE_C6_3_KIND,
            catalog_id=catalog.catalog_id,
        )
    return ref


def exact_contract_ref(
    catalog: OperationContractCatalogSnapshot,
) -> OperationContractRef:
    return _lift_program_contract_failure(try_exact_contract_ref(catalog))


def try_payload_value_ref(
    payload: c6_3.RedactionEvidencePayload,
    *,
    program_id: str,
    project_key: str,
) -> ValueRef | Failure:
    """Build the exact content-addressed ValueRef for one C6.3 payload."""

    if payload.operation_kind != c6_3.AGENT_CORE_C6_3_KIND:
        return _contract_failure(
            "schema_contract_invalid",
            "payload operation_kind is not the frozen C6.3 kind",
            field="RedactionEvidencePayload.operation_kind",
        )
    if payload.project_scope.project_key != project_key:
        return _contract_failure(
            "scope_contract_invalid",
            "payload project scope drift",
            project_key=project_key,
        )
    digest_failure = _hex64_failure(payload.payload_digest, "RedactionEvidencePayload.payload_digest")
    if digest_failure is not None:
        return digest_failure
    plain = dataclasses.asdict(payload)
    exact_text = canonical_json(plain)
    exact_bytes = exact_text.encode("utf-8")
    content_digest_hex = sha256_hex(exact_bytes)
    value_id = f"{program_id}:payload:c6-3"
    provenance_digest = content_digest(
        {
            "schema": "mrw.successor.agent-core.c6-3.payload-provenance.v1",
            "program_id": program_id,
            "project_key": project_key,
            "project_registry_revision": payload.project_scope.registry_revision,
            "resolved_schema": payload.project_scope.resolved_schema,
            "project_scope_incarnation": payload.project_scope.incarnation,
            "project_scope_digest": payload.project_scope.scope_digest,
            "source_observation_ref": payload.source_observation_ref,
            "source_observation_digest": payload.source_observation_digest,
            "source_kind": payload.source_kind,
            "trace_id": payload.trace_id,
            "request_id": payload.request_id,
            "call_id": payload.call_id,
            "interpreter_profile_ref": payload.interpreter_profile_ref,
            "policy_id": payload.policy.policy_id,
            "policy_version": payload.policy.policy_version,
            "policy_digest": payload.policy.policy_digest,
            "content_digest": content_digest_hex,
        }
    )
    return ValueRef(
        value_id=value_id,
        project_key=project_key,
        object_type=c6_3.AGENT_CORE_C6_3_PAYLOAD_TYPE,
        codec_id=c6_3.AGENT_CORE_C6_3_PAYLOAD_CODEC_ID,
        content_digest=content_digest_hex,
        storage_kind="project_value_ref",
        store_id="successor_values",
        store_version="1",
        storage_ref=f"project-value:{value_id}",
        byte_size=len(exact_bytes),
        provenance_digest=provenance_digest,
    )


def payload_value_ref(
    payload: c6_3.RedactionEvidencePayload,
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


def try_build_agent_core_c6_3_program(
    *,
    payload: c6_3.RedactionEvidencePayload,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
    semantic_identity: str = c6_3.AGENT_CORE_C6_3_SEMANTIC_IDENTITY,
    observation_profile: str = c6_3.AGENT_CORE_C6_3_OBSERVATION_PROFILE,
    contract_version: str = "mrw.functorial-successor.program-spec.v1",
) -> (
    Annotated[
        ProgramSpec,
        "kit:prepared-command effect_boundary=successor_program_interpreter "
        "witness=test:test_w05_agent_core_authority_metadata",
    ]
    | Failure
):
    """Build the exact-bound single-Atom Program for one C6.3 payload."""

    if payload.project_scope.project_key != project_key:
        return _contract_failure(
            "scope_contract_invalid",
            "payload project_key does not match Program project_key",
            project_key=project_key,
        )
    if payload.project_scope.registry_revision != project_registry_revision:
        return _contract_failure(
            "scope_contract_invalid",
            "payload registry revision does not match Program registry revision",
            registry_revision=project_registry_revision,
        )
    if payload.project_scope.scope_digest != project_scope_digest:
        return _contract_failure(
            "scope_contract_invalid",
            "payload scope digest does not match Program scope digest",
            scope_digest=project_scope_digest,
        )
    ref = try_exact_contract_ref(catalog)
    if isinstance(ref, Failure):
        return ref
    value_ref = try_payload_value_ref(
        payload,
        program_id=program_id,
        project_key=project_key,
    )
    if isinstance(value_ref, Failure):
        return value_ref
    operation = OperationSpec(
        operation_id=c6_3.AGENT_CORE_C6_3_OPERATION_ID,
        contract_ref=ref,
        input_refs=(value_ref,),
        payload_ref=value_ref,
        allowed_overrides=freeze_json_object({}),
    )
    root = atom_node(
        operation,
        input_type=c6_3.AGENT_CORE_C6_3_PAYLOAD_TYPE,
        output_type=c6_3.AGENT_CORE_C6_3_RESULT_TYPE,
    )
    metadata = freeze_json_object(
        {
            "schema": "mrw.successor.agent-core.c6-3.program-metadata.v1",
            "operation_kind": c6_3.AGENT_CORE_C6_3_KIND,
            "project_registry_revision": project_registry_revision,
            "resolved_schema": payload.project_scope.resolved_schema,
            "project_scope_incarnation": payload.project_scope.incarnation,
            "project_scope_digest": project_scope_digest,
            "source_observation_ref": payload.source_observation_ref,
            "source_observation_digest": payload.source_observation_digest,
            "source_kind": payload.source_kind,
            "trace_id": payload.trace_id,
            "request_id": payload.request_id,
            "call_id": payload.call_id,
            "interpreter_profile_ref": payload.interpreter_profile_ref,
            "policy_id": payload.policy.policy_id,
            "policy_version": payload.policy.policy_version,
            "policy_digest": payload.policy.policy_digest,
            "payload_value_id": value_ref.value_id,
            "payload_storage_ref": value_ref.storage_ref,
            "payload_content_digest": value_ref.content_digest,
            "payload_provenance_digest": value_ref.provenance_digest,
            "canonical_owner": c6_3.AGENT_CORE_C6_3_OWNER,
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


def build_agent_core_c6_3_program(
    *,
    payload: c6_3.RedactionEvidencePayload,
    catalog: OperationContractCatalogSnapshot,
    program_id: str,
    project_key: str,
    project_registry_revision: int,
    project_scope_digest: str,
    semantic_identity: str = c6_3.AGENT_CORE_C6_3_SEMANTIC_IDENTITY,
    observation_profile: str = c6_3.AGENT_CORE_C6_3_OBSERVATION_PROFILE,
    contract_version: str = "mrw.functorial-successor.program-spec.v1",
) -> Annotated[
    ProgramSpec,
    "kit:prepared-command effect_boundary=successor_program_interpreter "
    "witness=test:test_w05_agent_core_authority_metadata",
]:
    return _lift_program_contract_failure(
        try_build_agent_core_c6_3_program(
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


def compile_agent_core_c6_3_program(
    program: ProgramSpec,
    catalog: OperationContractCatalogSnapshot,
    *,
    operation_contracts: OperationContractResolver,
) -> Any:
    """Compile the C6.3 Program through the shared compiler."""

    return compile_program(
        program,
        catalog,
        operation_contracts=operation_contracts,
    )
