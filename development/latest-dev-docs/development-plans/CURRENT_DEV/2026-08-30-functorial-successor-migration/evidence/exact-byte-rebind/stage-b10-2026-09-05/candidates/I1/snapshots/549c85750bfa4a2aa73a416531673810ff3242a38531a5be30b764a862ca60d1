"""Pure deterministic compiler for mechanical capability pilot manifests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .capability_cell_spec import (
    CapabilityCellSpec,
    canonical_json_bytes,
    digest_json,
)
from .runtime_kernel_abi import RuntimeKernelABI

MANIFEST_SCHEMA = "mrw.functorial_successor.capability_spec_build_manifest.v1"
COMPILER_VERSION = "1.0.0"


class CapabilitySpecCompileError(ValueError):
    """Fail-closed invalid specification or exact binding."""


def _exact_hashes(spec: CapabilityCellSpec) -> list[dict[str, str]]:
    bindings = [
        {"path": item.path, "file_sha256": item.file_sha256, "role": item.role}
        for item in spec.exact_bindings()
    ]
    if len({item["path"] for item in bindings}) != len(bindings):
        raise CapabilitySpecCompileError("exact file binding paths must be unique")
    return sorted(bindings, key=lambda item: (item["path"], item["role"]))


def _generated_payload(spec: CapabilityCellSpec) -> dict[str, Any]:
    operations = [
        {
            "operation_contract_ref": ref,
            "owner_capability_id": spec.owner_capability_id,
            "domain_semantics_generated": False,
        }
        for ref in spec.operation_contract_refs
    ]
    program_surface: dict[str, Any]
    if spec.entrypoint_kind == "PROGRAM":
        program_surface = {
            "program_skeleton": {
                "shape_ref": spec.program_shape_ref,
                "ordered_composition_refs": list(spec.ordered_composition_refs),
                "reordering_permitted": False,
                "commutativity_claim": spec.commutativity_claim,
            }
        }
    else:
        program_surface = {
            "facade_validation_surface": {
                "surface_ref": spec.program_shape_ref,
                "ordered_outer_contract_refs": list(spec.ordered_composition_refs),
                "expected_kernel_steps": [],
                "program_atom_generated": False,
                "reordering_permitted": False,
                "commutativity_claim": spec.commutativity_claim,
            }
        }
    return {
        "operation_contract_descriptors": operations,
        **program_surface,
        "profile_refs": list(spec.profile_refs),
        "catalog_registration": {
            "operation_contract_refs": list(spec.operation_contract_refs),
            "registration_is_authority_adoption": False,
        },
        "handler_binding_closure": {
            "operation_contract_refs": list(spec.operation_contract_refs),
            "interpreter_refs": list(spec.interpreter_refs),
            "deployment_binding_refs": list(spec.deployment_binding_refs),
            "exact_handler_binding_required": True,
            "handler_implementation_generated": False,
        },
        "evidence_fragment": {
            "cell_id": spec.cell_id,
            "family_id": spec.family_id,
            "legacy_oracle_ref": spec.legacy_oracle_ref,
            "shadow_observation_ref": spec.shadow_observation_ref,
            "failure_union_refs": list(spec.failure_union_refs),
            "declared_lossy_projection_refs": list(spec.declared_lossy_projection_refs),
        },
        "binding_manifest": {
            "input_contract_refs": list(spec.input_contract_refs),
            "output_contract_refs": list(spec.output_contract_refs),
            "object_contract_refs": list(spec.object_contract_refs),
            "effect_policy_ref": spec.effect_policy_ref,
            "resource_policy_ref": spec.resource_policy_ref,
            "recovery_policy_ref": spec.recovery_policy_ref,
            "readback_policy_ref": spec.readback_policy_ref,
        },
        "parameterized_focused_gates": {
            "test_binding_roles": [item.role for item in spec.test_bindings],
            "legacy_shadow_required": True,
            "authority_ceiling_required": True,
        },
        "rollback_harness": {
            "rollback_binding_roles": [item.role for item in spec.rollback_bindings],
            "rollback_implementation_generated": False,
        },
    }


def compile_capability_spec(
    spec: CapabilityCellSpec,
    runtime_kernel_abi: RuntimeKernelABI,
) -> dict[str, Any]:
    """Compile one spec without importing or invoking any runtime interpreter."""

    exact_hashes = _exact_hashes(spec)
    generated = _generated_payload(spec)
    spec_semantic_digest = spec.semantic_digest()
    abi_digest = runtime_kernel_abi.compute_semantic_digest()
    composite_semantic_digest = digest_json(
        {
            "capability_spec_semantic_digest": spec_semantic_digest,
            "runtime_kernel_abi_semantic_digest": abi_digest,
        }
    )
    generated_payload_digest = digest_json(generated)
    artifact_payload = {
        "spec": spec.to_dict(),
        "runtime_kernel_abi": runtime_kernel_abi.to_dict(),
        "exact_file_hashes": exact_hashes,
        "generated_payload": generated,
        "generated_payload_digest": generated_payload_digest,
        "generated_bytes_sha256": generated_payload_digest,
    }
    artifact_digest = digest_json(artifact_payload)
    return {
        "schema": MANIFEST_SCHEMA,
        "version": "1.0.0",
        "compiler_version": COMPILER_VERSION,
        "cell_id": spec.cell_id,
        "family_id": spec.family_id,
        "semantic_identity": {
            "capability_spec_semantic_digest": spec_semantic_digest,
            "runtime_kernel_abi_semantic_digest": abi_digest,
            "composite_semantic_digest": composite_semantic_digest,
            "does_not_replace_exact_artifact_identity": True,
        },
        "artifact_identity": {
            "artifact_digest": artifact_digest,
            "generated_payload_digest": generated_payload_digest,
            "generated_bytes_sha256": generated_payload_digest,
            "covers_complete_spec_exact_hashes_and_generated_payload": True,
        },
        "runtime_kernel_abi": runtime_kernel_abi.to_dict(),
        "exact_file_hashes": exact_hashes,
        "generated": generated,
        "ownership": {
            "generated": list(spec.generated_ownership_refs),
            "handwritten": list(spec.handwritten_ownership_refs),
            "generated_files_manual_edit": "PROHIBITED",
            "domain_semantics_generated": False,
            "effect_execution_generated": False,
            "authority_adoption_generated": False,
        },
        "authority_ceiling": spec.authority_ceiling.to_dict(),
        "adoption_prerequisites": list(spec.adoption_prerequisites),
        "candidate_created": False,
    }


def build_manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    """Canonical generated bytes; callers may add no formatting or comments."""

    return canonical_json_bytes(manifest) + b"\n"
