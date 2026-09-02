"""CapabilityCellSpec pilot for C8.2 ordered writing composition."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from app.successor_migration.legacy_c8_interpreter import (
    LegacyC8DonorRegistry,
    LegacyC8ProgramInterpreter,
    LegacyC8WritingComposeDonor,
    LegacyC8WritingStageDonor,
)
from app.successor_runtime.capabilities import c8_program as c8p
from app.successor_runtime.capabilities.c8_typed_knowledge import demand_read
from app.successor_runtime.capabilities.c8_writing import (
    compose_writing_handoff,
    project_writing_card,
    stage_writing_artifact,
)
from app.successor_runtime.capabilities.checksum import content_digest
from app.successor_runtime.specification import (
    CapabilityCellSpec,
    RuntimeKernelABI,
    build_manifest_bytes,
    compile_capability_spec,
)

from .p4_c8_fixture import (
    PROJECT_KEY,
    captured_item,
    legacy_item,
    new_registry,
)

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BACKEND_ROOT.parents[1]
TOPIC_ROOT = REPOSITORY_ROOT / (
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration"
)
SPEC_PATH = TOPIC_ROOT / "evidence/capability-specs/C8.2.v1.json"
ABI_PATH = TOPIC_ROOT / "evidence/capability-specs/RuntimeKernelABI.v1.json"
BUILD_PATH = TOPIC_ROOT / ("evidence/capability-spec-builds/C8.2.BuildManifest.v1.json")
FROZEN_10_PATH = TOPIC_ROOT / "10_functorial-successor-domain-contract-snapshot.v1.json"
GENERATOR = BACKEND_ROOT / "scripts/generate_capability_spec_pilots.py"

PROGRAM_ID = "program:capability-spec-pilot-c8-2"
PROJECT_REGISTRY_REVISION = 1
PROJECT_SCOPE_DIGEST = content_digest(
    {"project": PROJECT_KEY, "incarnation": "capability-spec-pilot-c8-2"}
)


def _load_inputs() -> tuple[CapabilityCellSpec, RuntimeKernelABI, dict]:
    spec = CapabilityCellSpec.from_dict(json.loads(SPEC_PATH.read_text()))
    abi = RuntimeKernelABI.from_dict(json.loads(ABI_PATH.read_text()))
    manifest = json.loads(BUILD_PATH.read_text())
    return spec, abi, manifest


def _payload() -> c8p.C8WritingComposeInput:
    return c8p.C8WritingComposeInput(
        project_key=PROJECT_KEY,
        knowledge_item_key="ki:robotics",
        selection_hash="selection:robotics",
        selection_text="robotics investment",
        demand_fields=("canonical_statement", "evidence_refs"),
    )


def _program_plan() -> tuple:
    bundle = c8p.build_c8_bundle()
    catalog = c8p.build_c8_catalog(bundle)
    program = c8p.build_c8_program(
        cell_id="C8.2",
        payload=_payload(),
        catalog=catalog,
        program_id=PROGRAM_ID,
        project_key=PROJECT_KEY,
        project_registry_revision=PROJECT_REGISTRY_REVISION,
        project_scope_digest=PROJECT_SCOPE_DIGEST,
    )
    plan = c8p.compile_c8_program(
        program,
        catalog,
        operation_contracts=c8p.build_c8_registry(bundle),
    )
    return bundle, catalog, program, plan


def _legacy_trace(program, plan, catalog) -> dict:
    donors = LegacyC8DonorRegistry()
    donors.register(
        catalog.lookup(c8p.C8_2_COMPOSE_KIND).contract_digest,
        LegacyC8WritingComposeDonor(
            items_by_key={"ki:robotics": legacy_item()},
            selection_hash="selection:robotics",
            selection_text="robotics investment",
        ).run,
    )
    donors.register(
        catalog.lookup(c8p.C8_2_STAGE_KIND).contract_digest,
        LegacyC8WritingStageDonor(normalized_query="robotics investment").run,
    )
    payload = _payload()
    return LegacyC8ProgramInterpreter().consume(
        program,
        plan,
        donors=donors,
        seed_inputs={plan.ordered_steps[0].step_id: (payload, payload.payload_digest)},
    )


def _run_generator(
    root: Path, spec: Path, abi: Path, output: Path, *extra: str
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
        cwd=BACKEND_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_exact_build_is_canonical_and_read_only_check_preserves_mtime() -> None:
    spec, abi, manifest = _load_inputs()
    assert manifest == compile_capability_spec(spec, abi)
    assert BUILD_PATH.read_bytes() == build_manifest_bytes(manifest)
    before = BUILD_PATH.stat().st_mtime_ns
    result = _run_generator(REPOSITORY_ROOT, SPEC_PATH, ABI_PATH, BUILD_PATH, "--check")
    assert result.returncode == 0, result.stderr
    assert BUILD_PATH.stat().st_mtime_ns == before


def test_check_reports_drift_without_writing(tmp_path: Path) -> None:
    spec_value = json.loads(SPEC_PATH.read_text())
    for binding in (
        spec_value["source_bindings"]
        + spec_value["test_bindings"]
        + spec_value["rollback_bindings"]
    ):
        source = REPOSITORY_ROOT / binding["path"]
        target = tmp_path / binding["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    copied_spec = tmp_path / "C8.2.v1.json"
    copied_abi = tmp_path / "RuntimeKernelABI.v1.json"
    output = tmp_path / "C8.2.BuildManifest.v1.json"
    copied_spec.write_bytes(SPEC_PATH.read_bytes())
    copied_abi.write_bytes(ABI_PATH.read_bytes())
    output.write_bytes(b"manual drift\n")
    before_bytes = output.read_bytes()
    before_mtime = output.stat().st_mtime_ns

    result = _run_generator(tmp_path, copied_spec, copied_abi, output, "--check")
    assert result.returncode == 1
    assert "DRIFT:" in result.stderr
    assert output.read_bytes() == before_bytes
    assert output.stat().st_mtime_ns == before_mtime


def test_exact_bindings_include_frozen_10_and_match_current_bytes() -> None:
    spec, _, manifest = _load_inputs()
    frozen_10_relative = FROZEN_10_PATH.relative_to(REPOSITORY_ROOT).as_posix()
    bindings = {binding.path: binding for binding in spec.exact_bindings()}
    assert bindings[frozen_10_relative].role == "frozen10_strict_domain_semantics"
    assert manifest["exact_file_hashes"] == sorted(
        (
            {
                "path": binding.path,
                "file_sha256": binding.file_sha256,
                "role": binding.role,
            }
            for binding in spec.exact_bindings()
        ),
        key=lambda binding: (binding["path"], binding["role"]),
    )
    for binding in spec.exact_bindings():
        path = REPOSITORY_ROOT / binding.path
        assert path.is_file(), binding.path
        assert hashlib.sha256(path.read_bytes()).hexdigest() == binding.file_sha256


def test_order_swap_changes_semantic_digest() -> None:
    spec, abi, original = _load_inputs()
    swapped = dataclasses.replace(
        spec,
        ordered_composition_refs=tuple(reversed(spec.ordered_composition_refs)),
    )
    changed = compile_capability_spec(swapped, abi)
    assert changed["semantic_identity"] != original["semantic_identity"]
    assert changed["artifact_identity"] != original["artifact_identity"]


def test_byte_only_binding_change_preserves_semantics_and_changes_artifact() -> None:
    spec, abi, original = _load_inputs()
    first = dataclasses.replace(spec.source_bindings[0], file_sha256="f" * 64)
    changed = compile_capability_spec(
        dataclasses.replace(
            spec,
            source_bindings=(first,) + spec.source_bindings[1:],
        ),
        abi,
    )
    assert changed["semantic_identity"] == original["semantic_identity"]
    assert changed["artifact_identity"] != original["artifact_identity"]


def test_pure_transform_profile_keeps_expected_shared_effect_step_shape_explicit() -> (
    None
):
    spec, _, manifest = _load_inputs()
    bundle, _, _, plan = _program_plan()
    profiles = bundle.profiles["C8.2"]
    assert profiles["effect"].execution_class == "PURE_TRANSFORM"
    assert profiles["effect"].network_required is False
    assert profiles["effect"].external_visibility == "NONE"
    assert profiles["failure"].typed_failures == (
        "WRITING_SYNTHESIS_INCOMPLETE",
        "WRITING_STAGE_INVALID",
    )
    assert profiles["failure"].readback_profile_ref == "c8.writing.readback.v1"
    assert profiles["resource"].resource_classes == ("CPU_LIGHT",)
    assert [step.step_kind for step in plan.ordered_steps] == ["EFFECT", "EFFECT"]
    assert spec.profile_refs == (
        "c8.c8-2.effect@1.0.0#execution_class=PURE_TRANSFORM",
        "mrw.successor.execution-plan.v1#expected_step_shape=EFFECT,EFFECT",
        "c8.c8-2.semantic@1.0.0",
        "c8.c8-2.failure@1.0.0",
        "c8.c8-2.resource@1.0.0",
        "c8.c8-2.authority@1.0.0",
    )
    assert spec.failure_union_refs == profiles["failure"].typed_failures
    assert spec.resource_policy_ref == "c8.c8-2.resource@1.0.0#CPU_LIGHT"
    assert spec.recovery_policy_ref == (
        "c8.writing.recovery.v1#retained-staged-values-no-authority-reversal"
    )
    assert spec.readback_policy_ref == (
        "c8.writing.readback.v1#read-handle-revision-incarnation-provenance"
    )
    assert manifest["generated"]["profile_refs"] == list(spec.profile_refs)
    binding_manifest = manifest["generated"]["binding_manifest"]
    assert binding_manifest["resource_policy_ref"] == spec.resource_policy_ref
    assert binding_manifest["recovery_policy_ref"] == spec.recovery_policy_ref
    assert binding_manifest["readback_policy_ref"] == spec.readback_policy_ref
    assert manifest["generated"]["program_skeleton"]["ordered_composition_refs"] == [
        c8p.C8_2_COMPOSE_KIND,
        c8p.C8_2_STAGE_KIND,
    ]
    assert manifest["generated"]["program_skeleton"]["reordering_permitted"] is False


def test_same_exact_program_plan_donor_dataflow_and_successor_parity() -> None:
    _, catalog, program, plan = _program_plan()
    trace = _legacy_trace(program, plan, catalog)
    executions = trace["step_executions"]
    assert trace["consumed_program_digest"] == program.program_digest
    assert trace["consumed_plan_digest"] == plan.plan_digest
    assert executions[1]["input_digest"] == content_digest(executions[0]["output"])

    item = captured_item()
    read = demand_read(
        (item,),
        item_key=item.key,
        fields=("canonical_statement", "evidence_refs"),
        project_key=PROJECT_KEY,
        registry=new_registry(),
    )
    handoff = compose_writing_handoff(
        read,
        selection_hash="selection:robotics",
        selection_text="robotics investment",
    )
    artifact = stage_writing_artifact(project_writing_card(handoff))
    assert executions[0]["output"]["canonical_statement"] == (
        handoff.canonical_statement
    )
    assert executions[1]["output"]["evidence"] == artifact.card.canonical_statement
    assert artifact.card.handle == read.handle
    assert artifact.provenance.canonical_revision == 1
    assert artifact.provenance.canonical_incarnation == "p4-c8-captured-1"
    assert artifact.provenance.canonical_digest == item.canonical_ref.content_digest
    assert artifact.provenance_chain == (
        "demand_read",
        "writing_handoff",
        "writing_card",
        "staged_artifact",
    )
    assert "not_demand_read:topic_cluster_keys" in artifact.declared_loss


def test_no_admission_export_or_authority_expansion() -> None:
    _, _, manifest = _load_inputs()
    _, catalog, program, plan = _program_plan()
    trace = _legacy_trace(program, plan, catalog)
    assert trace["provider_calls"] == 0
    assert trace["store_writes"] == 0
    assert all(
        execution["output"].get("export_calls", 0) == 0
        for execution in trace["step_executions"]
    )
    assert all(
        execution["output"].get("provider_calls", 0) == 0
        for execution in trace["step_executions"]
    )
    assert all(
        execution["output"].get("authority", False) is False
        for execution in trace["step_executions"]
    )
    assert all(
        step.return_contract.admission_required is False for step in plan.ordered_steps
    )
    assert manifest["authority_ceiling"] == {
        "canonical_write": False,
        "live_provider": False,
        "external_delivery": False,
        "cutover": False,
        "authority_transfer": False,
    }
    assert manifest["candidate_created"] is False
    assert manifest["ownership"]["authority_adoption_generated"] is False
