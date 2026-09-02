from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from app.successor_runtime.specification import (
    IDENTITY_COMPOSITION_REF,
    AuthorityCeiling,
    CapabilityCellSpec,
    ExactFileBinding,
    RuntimeKernelABI,
    build_manifest_bytes,
    compile_capability_spec,
    compose_ordered,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parents[1]
SCRIPT = BACKEND_ROOT / "scripts/generate_capability_spec_pilots.py"


def _binding(
    path: str, digest: str = "1" * 64, role: str = "source"
) -> ExactFileBinding:
    return ExactFileBinding(path=path, file_sha256=digest, role=role)


def _abi(**changes: str) -> RuntimeKernelABI:
    values = {
        "program_protocol_version": "program.v1",
        "plan_protocol_version": "plan.v1",
        "handler_binding_protocol_version": "handler-binding.v1",
        "assignment_protocol_version": "assignment.v1",
        "reducer_protocol_version": "reducer.v1",
        "work_item_protocol_version": "work-item.v1",
    }
    values.update(changes)
    return RuntimeKernelABI(**values).with_digest()


def _spec(**changes: object) -> CapabilityCellSpec:
    values: dict[str, object] = {
        "cell_id": "C7.1",
        "family_id": "C7",
        "owner_capability_id": "ingest.c7_1.v1",
        "entrypoint_kind": "PROGRAM",
        "commutativity_claim": "NOT_CLAIMED",
        "input_contract_refs": ("object.input.v1",),
        "output_contract_refs": ("object.output.v1",),
        "object_contract_refs": ("object.input.v1", "object.output.v1"),
        "operation_contract_refs": ("ingest.snapshot.v1",),
        "program_shape_ref": "program.then.v1",
        "ordered_composition_refs": ("validate.v1", "persist.v1"),
        "interpreter_refs": ("interpreter.ingest.local.v1",),
        "profile_refs": ("effect.ingest.v1", "failure.ingest.v1"),
        "deployment_binding_refs": ("deployment.local-only.v1",),
        "legacy_oracle_ref": "legacy.ingest.shadow.v1",
        "shadow_observation_ref": "observation.ingest.v1",
        "failure_union_refs": ("failure.invalid.v1", "failure.store.v1"),
        "declared_lossy_projection_refs": (),
        "effect_policy_ref": "effect.policy.ingest.v1",
        "resource_policy_ref": "resource.policy.ingest.v1",
        "recovery_policy_ref": "recovery.policy.ingest.v1",
        "readback_policy_ref": "readback.policy.ingest.v1",
        "authority_ceiling": AuthorityCeiling(),
        "adoption_prerequisites": ("P3_PROMOTED", "PILOT_REVIEW_ALLOW"),
        "source_bindings": (_binding("src.py"),),
        "test_bindings": (_binding("test.py", "2" * 64, "focused_test"),),
        "rollback_bindings": (_binding("rollback.py", "3" * 64, "rollback_harness"),),
        "generated_ownership_refs": ("mechanical.scaffolding.v1",),
        "handwritten_ownership_refs": ("domain.interpreter.ingest.v1",),
    }
    values.update(changes)
    return CapabilityCellSpec(**values)  # type: ignore[arg-type]


def test_ordered_composition_has_identity_and_associativity_without_commutativity() -> (
    None
):
    first = ("validate.v1",)
    second = ("persist.v1",)
    third = ("project.v1",)
    assert compose_ordered((IDENTITY_COMPOSITION_REF,), first) == first
    assert compose_ordered(first, (IDENTITY_COMPOSITION_REF,)) == first
    assert compose_ordered(compose_ordered(first, second), third) == compose_ordered(
        first, compose_ordered(second, third)
    )
    assert compose_ordered(first, second) != compose_ordered(second, first)


def test_compiler_is_canonical_and_preserves_declared_order() -> None:
    spec = _spec(
        ordered_composition_refs=(
            IDENTITY_COMPOSITION_REF,
            "validate.v1",
            "persist.v1",
        )
    )
    first = compile_capability_spec(spec, _abi())
    second = compile_capability_spec(spec, _abi())
    assert build_manifest_bytes(first) == build_manifest_bytes(second)
    skeleton = first["generated"]["program_skeleton"]
    assert skeleton["ordered_composition_refs"] == ["validate.v1", "persist.v1"]
    assert skeleton["reordering_permitted"] is False
    assert skeleton["commutativity_claim"] == "NOT_CLAIMED"
    assert first["ownership"]["domain_semantics_generated"] is False
    assert first["ownership"]["effect_execution_generated"] is False
    assert first["candidate_created"] is False


def test_facade_validation_entrypoint_generates_no_program_atom_or_kernel_steps() -> (
    None
):
    manifest = compile_capability_spec(
        _spec(
            cell_id="C9.1",
            family_id="C9",
            owner_capability_id="api.command-query-envelope.v1",
            entrypoint_kind="FACADE_VALIDATION",
            program_shape_ref="facade.command-query-validation.v1",
            ordered_composition_refs=("command-envelope.v1", "query-envelope.v1"),
        ),
        _abi(),
    )
    generated = manifest["generated"]
    assert "program_skeleton" not in generated
    assert generated["facade_validation_surface"] == {
        "surface_ref": "facade.command-query-validation.v1",
        "ordered_outer_contract_refs": ["command-envelope.v1", "query-envelope.v1"],
        "expected_kernel_steps": [],
        "program_atom_generated": False,
        "reordering_permitted": False,
        "commutativity_claim": "NOT_CLAIMED",
    }


def test_order_swap_changes_semantic_digest() -> None:
    forward = compile_capability_spec(_spec(), _abi())
    backward = compile_capability_spec(
        _spec(ordered_composition_refs=("persist.v1", "validate.v1")), _abi()
    )
    assert (
        forward["semantic_identity"]["capability_spec_semantic_digest"]
        != backward["semantic_identity"]["capability_spec_semantic_digest"]
    )
    assert (
        forward["semantic_identity"]["composite_semantic_digest"]
        != backward["semantic_identity"]["composite_semantic_digest"]
    )


def test_identity_reference_preserves_capability_semantic_digest() -> None:
    plain = _spec(ordered_composition_refs=("validate.v1", "persist.v1"))
    with_identities = _spec(
        ordered_composition_refs=(
            IDENTITY_COMPOSITION_REF,
            "validate.v1",
            IDENTITY_COMPOSITION_REF,
            "persist.v1",
            IDENTITY_COMPOSITION_REF,
        )
    )
    assert plain.semantic_digest() == with_identities.semantic_digest()


@pytest.mark.parametrize(
    ("field", "malformed"),
    [
        ("input_contract_refs", "object.input.v1"),
        ("ordered_composition_refs", b"validate.v1"),
        ("profile_refs", {"profile": "effect.v1"}),
        ("failure_union_refs", frozenset({"failure.v1"})),
    ],
)
def test_direct_spec_rejects_non_array_reference_containers(
    field: str,
    malformed: object,
) -> None:
    with pytest.raises(TypeError, match="must be a list or tuple"):
        _spec(**{field: malformed})


@pytest.mark.parametrize(
    ("field", "malformed"),
    [
        ("input_contract_refs", "object.input.v1"),
        ("ordered_composition_refs", {"first": "validate.v1"}),
        ("profile_refs", 7),
        ("source_bindings", "src.py"),
        ("test_bindings", {"path": "test.py"}),
        ("rollback_bindings", ["rollback.py"]),
    ],
)
def test_from_dict_rejects_non_array_or_non_object_fields(
    field: str,
    malformed: object,
) -> None:
    value = _spec().to_dict()
    value[field] = malformed
    with pytest.raises(TypeError):
        CapabilityCellSpec.from_dict(value)


def test_byte_only_binding_changes_only_artifact_identity() -> None:
    first = compile_capability_spec(_spec(), _abi())
    changed_binding = replace(_spec().source_bindings[0], file_sha256="4" * 64)
    second = compile_capability_spec(
        _spec(source_bindings=(changed_binding,)),
        _abi(),
    )
    assert first["semantic_identity"] == second["semantic_identity"]
    assert (
        first["artifact_identity"]["artifact_digest"]
        != second["artifact_identity"]["artifact_digest"]
    )


def test_semantic_sensitive_change_changes_semantic_and_artifact_identity() -> None:
    first = compile_capability_spec(_spec(), _abi())
    second = compile_capability_spec(
        _spec(owner_capability_id="ingest.c7_1.successor.v2"), _abi()
    )
    assert first["semantic_identity"] != second["semantic_identity"]
    assert first["artifact_identity"] != second["artifact_identity"]


def test_runtime_kernel_abi_is_semantic_protocol_identity_not_file_identity() -> None:
    abi = _abi()
    value = abi.to_dict()
    assert "file_sha256" not in value
    assert "artifact_digest" not in value
    assert value["semantic_digest"] == abi.compute_semantic_digest()
    changed = _abi(reducer_protocol_version="reducer.v2")
    assert changed.semantic_digest != abi.semantic_digest


def _write_cli_inputs(root: Path) -> tuple[Path, Path, Path]:
    files = {
        "src.py": b"source\n",
        "test.py": b"test\n",
        "rollback.py": b"rollback\n",
    }
    for name, data in files.items():
        (root / name).write_bytes(data)
    spec = _spec(
        source_bindings=(
            _binding("src.py", hashlib.sha256(files["src.py"]).hexdigest()),
        ),
        test_bindings=(
            _binding(
                "test.py",
                hashlib.sha256(files["test.py"]).hexdigest(),
                "focused_test",
            ),
        ),
        rollback_bindings=(
            _binding(
                "rollback.py",
                hashlib.sha256(files["rollback.py"]).hexdigest(),
                "rollback_harness",
            ),
        ),
    )
    spec_path = root / "spec.json"
    abi_path = root / "abi.json"
    output_path = root / "generated.json"
    spec_path.write_text(json.dumps(spec.to_dict()), encoding="utf-8")
    abi_path.write_text(json.dumps(_abi().to_dict()), encoding="utf-8")
    return spec_path, abi_path, output_path


def _run_cli(
    root: Path, spec: Path, abi: Path, output: Path, *extra: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(root),
            "--spec",
            str(spec),
            "--runtime-kernel-abi",
            str(abi),
            "--output",
            str(output),
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
        cwd=BACKEND_ROOT,
    )


def test_cli_check_is_read_only_and_distinguishes_match_drift_unknown(
    tmp_path: Path,
) -> None:
    spec, abi, output = _write_cli_inputs(tmp_path)
    assert _run_cli(tmp_path, spec, abi, output).returncode == 0
    matching_mtime = output.stat().st_mtime_ns
    assert _run_cli(tmp_path, spec, abi, output).returncode == 0
    assert output.stat().st_mtime_ns == matching_mtime
    assert _run_cli(tmp_path, spec, abi, output, "--check").returncode == 0
    assert output.stat().st_mtime_ns == matching_mtime

    output.write_bytes(b"manual drift\n")
    drift_bytes = output.read_bytes()
    drift_mtime = output.stat().st_mtime_ns
    assert _run_cli(tmp_path, spec, abi, output, "--check").returncode == 1
    assert output.read_bytes() == drift_bytes
    assert output.stat().st_mtime_ns == drift_mtime

    missing = tmp_path / "missing-spec.json"
    assert _run_cli(tmp_path, missing, abi, output, "--check").returncode == 2
    assert output.read_bytes() == drift_bytes


def test_cli_exact_binding_drift_is_unknown_and_does_not_write(tmp_path: Path) -> None:
    spec, abi, output = _write_cli_inputs(tmp_path)
    output.write_bytes(b"protected\n")
    (tmp_path / "src.py").write_bytes(b"mutated\n")
    result = _run_cli(tmp_path, spec, abi, output)
    assert result.returncode == 2
    assert "exact binding drift" in result.stderr
    assert output.read_bytes() == b"protected\n"


@pytest.mark.parametrize(
    ("field", "malformed"),
    [
        ("input_contract_refs", "object.input.v1"),
        ("ordered_composition_refs", {"first": "validate.v1"}),
        ("source_bindings", "src.py"),
        ("rollback_bindings", ["rollback.py"]),
    ],
)
def test_cli_malformed_spec_is_unknown_without_output_or_mtime_change(
    tmp_path: Path,
    field: str,
    malformed: object,
) -> None:
    spec, abi, output = _write_cli_inputs(tmp_path)
    output.write_bytes(b"protected malformed output\n")
    before = output.read_bytes()
    before_mtime = output.stat().st_mtime_ns
    value = json.loads(spec.read_text(encoding="utf-8"))
    value[field] = malformed
    spec.write_text(json.dumps(value), encoding="utf-8")

    result = _run_cli(tmp_path, spec, abi, output, "--check")
    assert result.returncode == 2
    assert "UNKNOWN:" in result.stderr
    assert output.read_bytes() == before
    assert output.stat().st_mtime_ns == before_mtime
