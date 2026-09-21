"""C9.1 capability-spec pilot: facade validation without a Program atom."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from app.successor_runtime.specification import (
    CapabilityCellSpec,
    RuntimeKernelABI,
    build_manifest_bytes,
    compile_capability_spec,
)

from .current_candidate_support import (
    assert_b16_predecessor,
    assert_current_binding,
    load_stage_candidate,
)

BACKEND = Path(__file__).resolve().parents[2]
REPOSITORY = BACKEND.parents[1]
TOPIC = (
    REPOSITORY
    / "development/latest-dev-docs/development-plans/CURRENT_DEV"
    / "2026-08-30-functorial-successor-migration"
)
SPEC = TOPIC / "evidence/capability-specs/C9.1.v1.json"
ABI = TOPIC / "evidence/capability-specs/RuntimeKernelABI.v1.json"
BUILD = TOPIC / "evidence/capability-spec-builds/C9.1.BuildManifest.v1.json"
GENERATOR = BACKEND / "scripts/generate_capability_spec_pilots.py"
SPEC_SHA256 = "008a4ea359a962108172ef8d939d16cf4655a7ea62982924d705c769613edda7"
BUILD_SHA256 = "66b33dffcb73a49386fa60a54d76c1ff8b9a81e4632ad0f05416b591896a2b35"
RESPONSES_RELATIVE_PATH = "main/backend/app/contracts/responses.py"
PREDECESSOR_RESPONSES_SHA256 = (
    "87bcfcd3d229f54d724c3bff6a54e84328bd85ff5285267e9e5c23f387b38afa"
)
STAGE_B16_C9_CANDIDATE = (
    TOPIC
    / "evidence/exact-byte-rebind/stage-b16-2026-09-05/candidates/C9/candidate.v2.json"
)

OUTER_CONTRACTS = [
    "facade.command.description-validation.execute-false.v1",
    "facade.query.read-only.v1",
    "api.envelope.status-data-error-meta.v1",
    "api.status.ok-error-unavailable-blocked-waiting.v1",
    "facade.sse.after-seq-exclusive.v1",
    "facade.response.control-feedback-forbidden.v1",
    "api.external.dto.forbid-scope-schema-actor-authority-control.v1",
    "api.internal.server.inject-scope-actor-idempotency-revision-approval.v1",
]
INPUT_CONTRACTS = [
    "api.command.external.locator-typed-intent.v1",
    "api.query.external.locator-typed-intent.v1",
]
OUTPUT_CONTRACTS = [
    "api.envelope.status-data-error-meta.v1",
    "api.status.five-state.v1",
    "ui.observation.six-state-independent.v1",
    "api.sse.after-seq-exclusive.v1",
]
ZERO_AUTHORITY = {
    "canonical_write": False,
    "live_provider": False,
    "external_delivery": False,
    "cutover": False,
    "authority_transfer": False,
}


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _binding_for_path(spec: CapabilityCellSpec, path: str):
    for binding in spec.exact_bindings():
        if binding.path == path:
            return binding
    raise AssertionError(f"missing exact binding: {path}")


def _rewrite_source_binding_hash(raw: dict[str, object], path: str, file_sha256: str) -> None:
    bindings = raw["source_bindings"]
    assert isinstance(bindings, list)
    for binding in bindings:
        assert isinstance(binding, dict)
        if binding["path"] == path:
            binding["file_sha256"] = file_sha256
            return
    raise AssertionError(f"missing source binding: {path}")


def _run(
    root: Path,
    spec: Path,
    abi: Path,
    output: Path,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(GENERATOR),
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
        cwd=BACKEND,
        check=False,
        capture_output=True,
        text=True,
    )


def test_c9_1_spec_declares_exact_bounded_facade_semantics() -> None:
    raw = _load(SPEC)
    spec = CapabilityCellSpec.from_dict(raw)
    live_responses_path = REPOSITORY / RESPONSES_RELATIVE_PATH
    live_responses_sha256 = _sha256(live_responses_path)

    assert _sha256(SPEC) == SPEC_SHA256
    assert spec.cell_id == "C9.1"
    assert spec.entrypoint_kind == "FACADE_VALIDATION"
    assert spec.commutativity_claim == "NOT_CLAIMED"
    assert list(spec.input_contract_refs) == INPUT_CONTRACTS
    assert list(spec.output_contract_refs) == OUTPUT_CONTRACTS
    assert list(spec.ordered_composition_refs) == OUTER_CONTRACTS
    assert "api.status.ok-error-unavailable-blocked-waiting.v1" in (
        spec.operation_contract_refs
    )
    assert "projection.profile.api-five-state-ui-six-state-independent.v1" in (
        spec.profile_refs
    )
    assert "facade.sse.after-seq-exclusive.v1" in spec.operation_contract_refs
    assert (
        "api.external.dto.forbid-scope-schema-actor-authority-control.v1"
        in spec.operation_contract_refs
    )
    assert (
        "api.internal.server.inject-scope-actor-idempotency-revision-approval.v1"
        in spec.operation_contract_refs
    )
    assert spec.recovery_policy_ref == "NONE"
    assert spec.legacy_oracle_ref.endswith("dispatch-false.v1")
    assert "dispatch-false" in spec.shadow_observation_ref
    assert "execute-false" in spec.effect_policy_ref
    assert "query-read-only" in spec.effect_policy_ref
    assert "no-control" in spec.effect_policy_ref
    assert spec.authority_ceiling.to_dict() == ZERO_AUTHORITY

    source_roles = {binding.role: binding for binding in spec.source_bindings}
    assert "frozen10_strict_domain_semantics" in source_roles
    assert "handwritten_external_transport_dto_boundary" in source_roles
    assert "handwritten_internal_facade_validation_contracts" in source_roles
    assert spec.test_bindings
    assert spec.rollback_bindings
    assert _binding_for_path(spec, RESPONSES_RELATIVE_PATH).file_sha256 == (
        PREDECESSOR_RESPONSES_SHA256
    )
    assert live_responses_sha256 != PREDECESSOR_RESPONSES_SHA256
    candidate_path, candidate = load_stage_candidate(REPOSITORY, "C9")
    for binding in spec.exact_bindings():
        path = REPOSITORY / binding.path
        assert path.is_file(), binding.path
        actual = _sha256(path)
        if actual == binding.file_sha256:
            continue
        assert_current_binding(
            REPOSITORY,
            candidate_path,
            candidate,
            binding.path,
            binding.file_sha256,
        )


def test_c9_1_build_is_exact_and_has_no_program_or_control_effect() -> None:
    spec = CapabilityCellSpec.from_dict(_load(SPEC))
    abi = RuntimeKernelABI.from_dict(_load(ABI))
    expected = compile_capability_spec(spec, abi)
    actual = _load(BUILD)

    assert _sha256(BUILD) == BUILD_SHA256
    assert BUILD.read_bytes() == build_manifest_bytes(expected)
    assert actual == expected
    generated = actual["generated"]
    assert isinstance(generated, dict)
    assert "program_skeleton" not in generated
    surface = generated["facade_validation_surface"]
    assert isinstance(surface, dict)
    assert surface == {
        "surface_ref": "facade.command-query-envelope-status-sse-validation.v1",
        "ordered_outer_contract_refs": OUTER_CONTRACTS,
        "expected_kernel_steps": [],
        "program_atom_generated": False,
        "reordering_permitted": False,
        "commutativity_claim": "NOT_CLAIMED",
    }

    semantic = actual["semantic_identity"]
    artifact = actual["artifact_identity"]
    assert isinstance(semantic, dict)
    assert isinstance(artifact, dict)
    assert semantic["runtime_kernel_abi_semantic_digest"] == (
        "870aa856d153119093242b949be709586db0eb08779809feee0ad1b466e1baaa"
    )
    assert semantic["composite_semantic_digest"] != artifact["artifact_digest"]
    assert semantic["does_not_replace_exact_artifact_identity"] is True
    assert artifact["covers_complete_spec_exact_hashes_and_generated_payload"] is True
    assert actual["authority_ceiling"] == ZERO_AUTHORITY
    ownership = actual["ownership"]
    assert isinstance(ownership, dict)
    assert ownership["domain_semantics_generated"] is False
    assert ownership["effect_execution_generated"] is False
    assert ownership["authority_adoption_generated"] is False
    binding_manifest = generated["binding_manifest"]
    assert isinstance(binding_manifest, dict)
    assert binding_manifest["effect_policy_ref"] == (
        "effect.policy.facade.validation-only.execute-false.query-read-only."
        "dispatch-false.no-control.v1"
    )
    assert binding_manifest["recovery_policy_ref"] == "NONE"
    assert actual["candidate_created"] is False


def test_c9_1_stage_b17_candidate_tracks_current_bytes_not_authority() -> None:
    candidate_path, candidate = load_stage_candidate(REPOSITORY, "C9")
    assert candidate["schema"] == "mrw.family_fragment_rebind.candidate.v2"
    assert candidate["status"] == "CANDIDATE_VALID_NOT_AUTHORITY"
    assert candidate["amendment"].endswith("NOT_AUTHORITY")
    assert_b16_predecessor(REPOSITORY, candidate, "C9")
    predecessor = _load(STAGE_B16_C9_CANDIDATE)
    assert predecessor["status"] == "CANDIDATE_VALID_NOT_AUTHORITY"
    for relative, predecessor_sha256 in (
        (RESPONSES_RELATIVE_PATH, PREDECESSOR_RESPONSES_SHA256),
        (
            "main/backend/app/contracts/successor_runtime.py",
            "4a494839fab913e2f6615822fe16df2076317c529a9ccf2a1fc25c40cbb6a068",
        ),
        (
            "main/backend/app/successor_runtime/runtime/facade_contracts.py",
            "47a0a10c17465ea2e6c76fa091fe09747e84dfdcc258968c5aafa51f18ca6b03",
        ),
    ):
        assert_current_binding(
            REPOSITORY,
            candidate_path,
            candidate,
            relative,
            predecessor_sha256,
        )


def test_c9_1_byte_only_binding_change_preserves_semantics_not_artifact() -> None:
    spec = CapabilityCellSpec.from_dict(_load(SPEC))
    abi = RuntimeKernelABI.from_dict(_load(ABI))
    current = compile_capability_spec(spec, abi)
    first = dataclasses.replace(spec.source_bindings[0], file_sha256="0" * 64)
    changed = compile_capability_spec(
        dataclasses.replace(
            spec,
            source_bindings=(first,) + spec.source_bindings[1:],
        ),
        abi,
    )

    assert changed["semantic_identity"] == current["semantic_identity"]
    assert changed["artifact_identity"] != current["artifact_identity"]


def test_c9_1_generator_check_is_read_only_and_drift_fails_without_write(
    tmp_path: Path,
) -> None:
    # Recreate the exact-bound repository surface in an isolated root so drift
    # can be exercised without ever mutating the canonical build artifact.
    raw = _load(SPEC)
    spec = CapabilityCellSpec.from_dict(raw)
    for binding in spec.exact_bindings():
        source = REPOSITORY / binding.path
        target = tmp_path / binding.path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    copied_spec = tmp_path / SPEC.relative_to(REPOSITORY)
    copied_spec.parent.mkdir(parents=True, exist_ok=True)
    local_raw = _load(SPEC)
    copied_spec.write_text(
        json.dumps(local_raw, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    copied_abi = tmp_path / ABI.relative_to(REPOSITORY)
    copied_abi.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ABI, copied_abi)
    output = tmp_path / BUILD.relative_to(REPOSITORY)

    checked = _run(tmp_path, copied_spec, copied_abi, output, "--check")
    assert checked.returncode == 2
    assert "exact binding drift" in checked.stderr
    assert not output.exists()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"manual drift\n")
    drift = (output.read_bytes(), output.stat().st_mtime_ns)
    rejected = _run(tmp_path, copied_spec, copied_abi, output, "--check")
    assert rejected.returncode == 2
    assert "exact binding drift" in rejected.stderr
    assert (output.read_bytes(), output.stat().st_mtime_ns) == drift
