"""C7.1 CapabilityCellSpec pilot against the existing P4 scaffold bytes."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.successor_migration.legacy_ingest_c7 import (
    capture_legacy_ingest_c7_fixture,
)
from app.successor_runtime.capabilities import ingest_c7_common as c7
from app.successor_runtime.specification import (
    CapabilityCellSpec,
    RuntimeKernelABI,
    build_manifest_bytes,
    compile_capability_spec,
)
from tests.successor_runtime.p4_c7_fixture import (
    compiled_effect_step,
    program_and_plan,
    runtime_assignment,
    submission,
    verification_binding,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parents[1]
TOPIC = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration"
)
SPEC_PATH = TOPIC / "evidence/capability-specs/C7.1.v1.json"
ABI_PATH = TOPIC / "evidence/capability-specs/RuntimeKernelABI.v1.json"
BUILD_PATH = TOPIC / "evidence/capability-spec-builds/C7.1.BuildManifest.v1.json"
C7_FRAGMENT_PATH = TOPIC / "evidence/p4-fragments/C7.json"
FROZEN_10_PATH = TOPIC / "10_functorial-successor-domain-contract-snapshot.v1.json"
SCRIPT = BACKEND_ROOT / "scripts/generate_capability_spec_pilots.py"


def _load(path: Path) -> dict[str, Any]:
    value = json.loads((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _spec() -> CapabilityCellSpec:
    return CapabilityCellSpec.from_dict(_load(SPEC_PATH))


def _abi() -> RuntimeKernelABI:
    return RuntimeKernelABI.from_dict(_load(ABI_PATH))


def _run_cli(
    repo_root: Path,
    spec: Path,
    abi: Path,
    output: Path,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo_root),
            "--spec",
            str(spec),
            "--runtime-kernel-abi",
            str(abi),
            "--output",
            str(output),
            *extra,
        ],
        cwd=BACKEND_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_spec_maps_the_current_c7_1_semantics_without_authority_expansion() -> None:
    spec = _spec()
    manifest = _load(BUILD_PATH)
    fragment = _load(C7_FRAGMENT_PATH)
    cell = next(item for item in fragment["cells"] if item["cell_id"] == "C7.1")

    assert spec.cell_id == "C7.1"
    assert spec.family_id == "C7"
    assert spec.entrypoint_kind == "PROGRAM"
    assert spec.commutativity_claim == "NOT_CLAIMED"
    assert spec.ordered_composition_refs == (
        "EFFECT:ingest_index.stage_candidate.v1",
        "ADMISSION:mrw.return.ingest.document-admission.v1",
    )
    assert spec.operation_contract_refs == (c7.STAGE_CANDIDATE_KIND,)
    assert c7.C7_ADMISSION_RETURN_CONTRACT_REF in spec.output_contract_refs
    assert c7.C7_INGEST_OWNER == spec.owner_capability_id
    assert c7.C7_INGEST_OWNER != c7.DOCUMENT_CANONICAL_OWNER
    assert any("EFFECTFUL" in ref for ref in spec.profile_refs)
    assert cell["successor_observation"]["step_kinds"] == ["EFFECT", "ADMISSION"]
    assert cell["successor_observation"]["return_contract_ref"] == (
        c7.C7_ADMISSION_RETURN_CONTRACT_REF
    )
    assert cell["successor_observation"]["execution_class"] == "EFFECTFUL"
    assert cell["legacy_observation"]["writer_calls"] == 0
    assert cell["legacy_observation"]["provider_calls"] == 0
    legacy, replay = capture_legacy_ingest_c7_fixture(submission())
    assert legacy["interpreter_id"] == spec.legacy_oracle_ref
    assert legacy["writer_calls"] == replay.writer_calls == 0
    assert legacy["provider_calls"] == 0
    assert legacy["authority"] is False
    assert manifest["authority_ceiling"] == {
        "canonical_write": False,
        "live_provider": False,
        "external_delivery": False,
        "cutover": False,
        "authority_transfer": False,
    }
    assert manifest["candidate_created"] is False
    assert manifest["generated"]["program_skeleton"][
        "ordered_composition_refs"
    ] == list(spec.ordered_composition_refs)
    assert manifest["generated"]["program_skeleton"]["reordering_permitted"] is False


def test_spec_binds_frozen_10_and_current_source_test_rollback_bytes() -> None:
    spec = _spec()
    bindings = {binding.path: binding for binding in spec.exact_bindings()}
    frozen_path = FROZEN_10_PATH.as_posix()
    assert bindings[frozen_path].role == "frozen10_domain_contract_snapshot"
    assert any(
        binding.role.startswith("c7_1_source_") for binding in spec.source_bindings
    )
    assert any(
        binding.role.startswith("c7_1_focused_") for binding in spec.test_bindings
    )
    assert any(
        binding.role.startswith("c7_1_rollback_") for binding in spec.rollback_bindings
    )
    for binding in spec.exact_bindings():
        path = REPOSITORY_ROOT / binding.path
        assert path.is_file(), binding.path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == binding.file_sha256


def test_existing_program_plan_assignment_has_exact_seven_field_closure() -> None:
    program, plan, _ref, _payload_ref = program_and_plan()
    effect_step = compiled_effect_step(plan)
    assignment = runtime_assignment()
    observed = {
        "program_digest": program.program_digest,
        "plan_digest": plan.plan_digest,
        "step_id": effect_step.step_id,
        "step_role": assignment.step_role.value,
        "operation_contract_digest": assignment.operation_contract_digest,
        "interpreter_profile_digest": (
            assignment.handler_binding.interpreter_profile_digest
        ),
        "verification_binding_digest": verification_binding().binding_digest,
    }
    fragment = _load(C7_FRAGMENT_PATH)
    cell = next(item for item in fragment["cells"] if item["cell_id"] == "C7.1")
    frozen_closure = cell["successor_observation"]["runtime_assignment_closure"]
    assert set(frozen_closure) == {
        "program_digest",
        "plan_digest",
        "step_id",
        "step_role",
        "operation_contract_digest",
        "interpreter_profile_digest",
        "verification_binding_digest",
    }
    assert frozen_closure["step_role"] == "EFFECT"
    for key in (
        "program_digest",
        "plan_digest",
        "operation_contract_digest",
        "interpreter_profile_digest",
        "verification_binding_digest",
    ):
        assert len(frozen_closure[key]) == 64
    assert frozen_closure["step_id"].startswith("step-")
    assert observed["program_digest"] == assignment.program_digest
    assert observed["plan_digest"] == assignment.plan_digest
    assert observed["step_id"] == assignment.step_id
    assert observed["step_role"] == "EFFECT"
    assert observed["operation_contract_digest"] == (
        effect_step.operation_contract_ref.contract_digest
    )
    assert assignment.program_digest == program.program_digest
    assert assignment.plan_digest == plan.plan_digest
    assert (
        assignment.handler_binding_digest == assignment.handler_binding.binding_digest
    )


def test_staging_and_generated_ownership_keep_domain_and_authority_handwritten() -> (
    None
):
    manifest = _load(BUILD_PATH)
    outcome = c7.stage_ingest_submission(submission())
    receipt = outcome.receipt
    assert receipt["admission_implied"] is False
    assert receipt["document_write_boundary"] is False
    assert receipt["provider_calls"] == 0
    assert receipt["authority"] is False
    assert manifest["ownership"]["generated_files_manual_edit"] == "PROHIBITED"
    assert manifest["ownership"]["domain_semantics_generated"] is False
    assert manifest["ownership"]["effect_execution_generated"] is False
    assert manifest["ownership"]["authority_adoption_generated"] is False
    assert (
        "c7_1.domain-transformation.handwritten.v1"
        in manifest["ownership"]["handwritten"]
    )
    assert (
        "capability-spec.contract-catalog-binding-scaffolding.v1"
        in manifest["ownership"]["generated"]
    )


def test_semantic_identity_and_exact_artifact_identity_remain_distinct() -> None:
    spec = _spec()
    abi = _abi()
    current = compile_capability_spec(spec, abi)
    manifest = _load(BUILD_PATH)
    assert current == manifest
    assert (REPOSITORY_ROOT / BUILD_PATH).read_bytes() == build_manifest_bytes(manifest)

    first_source = spec.source_bindings[0]
    byte_only_change = replace(
        spec,
        source_bindings=(
            replace(first_source, file_sha256="0" * 64),
            *spec.source_bindings[1:],
        ),
    )
    changed_artifact = compile_capability_spec(byte_only_change, abi)
    assert changed_artifact["semantic_identity"] == current["semantic_identity"]
    assert changed_artifact["artifact_identity"] != current["artifact_identity"]

    semantic_change = replace(spec, owner_capability_id="ingest_index.c7.v2")
    changed_semantics = compile_capability_spec(semantic_change, abi)
    assert changed_semantics["semantic_identity"] != current["semantic_identity"]
    assert changed_semantics["artifact_identity"] != current["artifact_identity"]
    assert current["semantic_identity"]["does_not_replace_exact_artifact_identity"]


def test_real_check_matches_without_mtime_change_and_drift_is_read_only(
    tmp_path: Path,
) -> None:
    output = REPOSITORY_ROOT / BUILD_PATH
    before = output.read_bytes()
    before_mtime = output.stat().st_mtime_ns
    result = _run_cli(
        REPOSITORY_ROOT,
        REPOSITORY_ROOT / SPEC_PATH,
        REPOSITORY_ROOT / ABI_PATH,
        output,
        "--check",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("MATCH:")
    assert output.read_bytes() == before
    assert output.stat().st_mtime_ns == before_mtime

    spec = _spec()
    for binding in spec.exact_bindings():
        source = REPOSITORY_ROOT / binding.path
        destination = tmp_path / binding.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    temporary_spec = tmp_path / SPEC_PATH
    temporary_abi = tmp_path / ABI_PATH
    temporary_output = tmp_path / BUILD_PATH
    temporary_spec.parent.mkdir(parents=True, exist_ok=True)
    temporary_abi.parent.mkdir(parents=True, exist_ok=True)
    temporary_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPOSITORY_ROOT / SPEC_PATH, temporary_spec)
    shutil.copyfile(REPOSITORY_ROOT / ABI_PATH, temporary_abi)
    temporary_output.write_bytes(b"manual drift\n")
    drift_bytes = temporary_output.read_bytes()
    drift_mtime = temporary_output.stat().st_mtime_ns

    drift = _run_cli(
        tmp_path,
        temporary_spec,
        temporary_abi,
        temporary_output,
        "--check",
    )
    assert drift.returncode == 1
    assert drift.stderr.startswith("DRIFT:")
    assert temporary_output.read_bytes() == drift_bytes
    assert temporary_output.stat().st_mtime_ns == drift_mtime
