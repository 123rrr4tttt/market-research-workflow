from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from app.successor_runtime.specification import (
    AuthorityCeiling,
    CapabilityCellSpec,
    ExactFileBinding,
    RuntimeKernelABI,
    compile_capability_spec,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
FRAGMENT_ROOT = REPOSITORY_ROOT / (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/p3-fragments"
)


def _abi() -> RuntimeKernelABI:
    return RuntimeKernelABI(
        program_protocol_version="current-program-protocol.v1",
        plan_protocol_version="current-plan-protocol.v1",
        handler_binding_protocol_version="current-handler-binding-protocol.v1",
        assignment_protocol_version="current-assignment-protocol.v1",
        reducer_protocol_version="current-reducer-protocol.v1",
        work_item_protocol_version="current-work-item-protocol.v1",
    ).with_digest()


def _binding(path: Path, role: str) -> ExactFileBinding:
    return ExactFileBinding(
        path=path.relative_to(REPOSITORY_ROOT).as_posix(),
        file_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        role=role,
    )


def _oracle_spec(
    *,
    family: str,
    cell: dict[str, Any],
    fragment_path: Path,
    shape: str,
    ordered_refs: tuple[str, ...],
) -> CapabilityCellSpec:
    operation_refs = tuple(
        str(item["operation_kind"]) for item in cell["operation_bindings"]
    )
    return CapabilityCellSpec(
        cell_id=str(cell["cell_id"]),
        family_id=family,
        owner_capability_id=str(cell["owner_capability_id"]),
        entrypoint_kind="PROGRAM",
        commutativity_claim="NOT_CLAIMED",
        input_contract_refs=(f"oracle.{family.lower()}.input.v1",),
        output_contract_refs=(f"oracle.{family.lower()}.output.v1",),
        object_contract_refs=(
            f"oracle.{family.lower()}.input.v1",
            f"oracle.{family.lower()}.output.v1",
        ),
        operation_contract_refs=operation_refs,
        program_shape_ref=shape,
        ordered_composition_refs=ordered_refs,
        interpreter_refs=(
            str(
                cell["successor_observation"].get("interpreter_id")
                or cell["successor_observation"]["projector_id"]
            ),
        ),
        profile_refs=(f"oracle.{family.lower()}.profile.v1",),
        deployment_binding_refs=("deployment.local-only.v1",),
        legacy_oracle_ref=str(cell["legacy_observation"]["interpreter_id"]),
        shadow_observation_ref=f"oracle.{family.lower()}.shadow.v1",
        failure_union_refs=(f"oracle.{family.lower()}.failure-union.v1",),
        declared_lossy_projection_refs=(),
        effect_policy_ref=f"oracle.{family.lower()}.effect-policy.v1",
        resource_policy_ref=f"oracle.{family.lower()}.resource-policy.v1",
        recovery_policy_ref=f"oracle.{family.lower()}.recovery-policy.v1",
        readback_policy_ref=f"oracle.{family.lower()}.readback-policy.v1",
        authority_ceiling=AuthorityCeiling(),
        adoption_prerequisites=("P3_PROMOTED_REFERENCE_ORACLE",),
        source_bindings=(_binding(fragment_path, "promoted_reference_fragment"),),
        test_bindings=(_binding(Path(__file__), "oracle_focused_test"),),
        rollback_bindings=(
            _binding(
                REPOSITORY_ROOT
                / "main/backend/scripts/generate_capability_spec_pilots.py",
                "rollback_descriptor_generator",
            ),
        ),
        generated_ownership_refs=("mechanical.oracle-harness.v1",),
        handwritten_ownership_refs=(f"{family.lower()}.domain-implementation",),
    )


@pytest.mark.parametrize(
    ("family", "cell_id", "shape", "ordered_refs"),
    [
        (
            "C3",
            "C3.1",
            "program.traverse-ordered-map-fold.v1",
            ("traverse-ordered.v1", "map-output.v1", "fold.v1"),
        ),
        (
            "C5",
            "C5.1",
            "program.observation-projection.v1",
            ("observe-journal.v1", "project-read-model.v1"),
        ),
        (
            "C6",
            "C6.2",
            "program.effect-receipt.v1",
            ("effect-attempt.v1", "typed-receipt.v1", "readback.v1"),
        ),
    ],
)
def test_promoted_family_shape_is_expressible_without_mutating_oracle(
    family: str,
    cell_id: str,
    shape: str,
    ordered_refs: tuple[str, ...],
) -> None:
    path = FRAGMENT_ROOT / f"{family}.json"
    before = path.read_bytes()
    before_mtime = path.stat().st_mtime_ns
    fragment = json.loads(before)
    cell = next(item for item in fragment["cells"] if item["cell_id"] == cell_id)

    if family == "C3":
        assert any(
            "traversal" in binding["role"] for binding in cell["operation_bindings"]
        )
    elif family == "C5":
        assert cell["successor_observation"]["is_authority"] is False
    else:
        assert "receipt_digest" in cell["successor_observation"]

    manifest = compile_capability_spec(
        _oracle_spec(
            family=family,
            cell=cell,
            fragment_path=path,
            shape=shape,
            ordered_refs=ordered_refs,
        ),
        _abi(),
    )
    assert manifest["generated"]["program_skeleton"][
        "ordered_composition_refs"
    ] == list(ordered_refs)
    assert (
        manifest["generated"]["parameterized_focused_gates"]["legacy_shadow_required"]
        is True
    )
    assert (
        manifest["generated"]["rollback_harness"]["rollback_implementation_generated"]
        is False
    )
    assert manifest["authority_ceiling"] == {
        "canonical_write": False,
        "live_provider": False,
        "external_delivery": False,
        "cutover": False,
        "authority_transfer": False,
    }
    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == before_mtime
