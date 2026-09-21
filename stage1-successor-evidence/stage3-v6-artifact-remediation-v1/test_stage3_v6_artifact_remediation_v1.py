#!/usr/bin/env python3
"""Focused checks for the Stage 3 v6 artifact remediation package."""

from __future__ import annotations

import importlib.util
import copy
import json
import sys
from pathlib import Path

import pytest

from scripts.formal_release import source_closure


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


builder = load_module(
    "stage3_v6_artifact_remediation_builder",
    HERE / "build_stage3_v6_artifact_remediation_v1.py",
)
checker = load_module(
    "stage3_v6_artifact_remediation_checker",
    HERE / "check_stage3_v6_artifact_remediation_v1.py",
)


def receipt(name: str) -> dict:
    return json.loads((HERE / "raw" / name).read_text(encoding="utf-8"))


def historical_receipt_source_root() -> Path:
    record = checker.load(checker.ROOT / checker.RECORD)
    value = record["predecessor"]["receipt_source_root"]
    assert isinstance(value, str) and Path(value).is_absolute()
    return Path(value)


def write_junit(path: Path, *, tests: int = 2, failures: int = 0) -> None:
    path.write_text(
        "<?xml version='1.0' encoding='utf-8'?>"
        f"<testsuite name='sample' tests='{tests}' failures='{failures}' errors='0' skipped='0'/>",
        encoding="utf-8",
    )


def make_relocated_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    relocated = tmp_path / "relocated"
    source = tmp_path / "original-source"
    evidence = tmp_path / "v6-history"
    candidate = tmp_path / "v6-candidate"
    for root in (relocated, source, evidence, candidate):
        root.mkdir()
    package = HERE.relative_to(builder.ROOT)
    raw = package / "raw"
    for root in (relocated, source):
        (root / package).mkdir(parents=True)
        (root / raw).mkdir()

    contract = checker.CONTRACT
    (relocated / contract).parent.mkdir(parents=True)
    (relocated / contract).write_bytes(b"contract\n")
    contract_sha256 = checker.sha(relocated / contract)
    monkeypatch.setattr(checker, "CONTRACT_SHA256", contract_sha256)
    observation = {
        "authoritative": False,
        "contract": {"path": contract.as_posix(), "sha256": contract_sha256},
        "paths": [
            {
                "observation_scope": "RESUMED_REPAIR_OBSERVATION_NOT_TASK_START",
                "observed_source_sha256": "1" * 64,
                "path": path,
                "v6_sha256": "2" * 64,
            }
            for path in checker.OBSERVED_ARTIFACT_PATHS
        ],
        "predecessor": {
            "commit": checker.V6_COMMIT,
            "evidence": [],
            "root": str(candidate),
            "tree": checker.V6_TREE,
        },
        "production_release_authorized": False,
        "schema_version": "mrw.stage3_v6_artifact_repair.input_observation.v1",
        "status": "INPUTS_VERIFIED_REPAIR_IN_PROGRESS",
        "successor_created": False,
    }
    evidence_names = {}
    for name in (
        "candidate-manifest.v6.json",
        "closure.final.v6.json",
        "stage2-record.final.v6.json",
        "r1.final.v6.json",
        "r2.pass.v6.json",
        "r3.pass.v6.json",
    ):
        (evidence / name).write_bytes(f"{name}\n".encode())
        evidence_names[name] = checker.sha(evidence / name)
    evidence_refs = []
    for name in evidence_names:
        evidence_refs.append({"path": str(evidence / name), "sha256": checker.sha(evidence / name)})
    observation["predecessor"]["evidence"] = evidence_refs
    observation_path = relocated / checker.INPUT_OBSERVATION
    observation_path.write_text(json.dumps(observation), encoding="utf-8")

    historical_path = relocated / checker.HISTORICAL_V6_REMEDIATION_RECORD
    historical_path.parent.mkdir(parents=True)
    historical_path.write_text(
        json.dumps({"schema_version": "mrw.stage1.stage2_v6_intake_remediation_record.v5", "authoritative": False}),
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "EVIDENCE_ROOT", evidence)
    monkeypatch.setattr(checker, "EVIDENCE_HASHES", evidence_names)
    monkeypatch.setattr(checker, "HISTORICAL_V6_REMEDIATION_SHA256", checker.sha(historical_path))

    for relative in checker.REQUIRED_ARTIFACT_PATHS:
        path = relocated / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"current source\n")
    extension = Path("main/frontend-modern/src/new-gate.ts")
    extension_path = relocated / extension
    extension_path.parent.mkdir(parents=True)
    extension_path.write_bytes(b"export {};\n")

    log_name = "bound-final.log"
    junit_name = "bound-final.xml"
    (source / raw / log_name).write_bytes(b"clean pytest output\n")
    write_junit(source / raw / junit_name)
    log_hash = checker.sha(source / raw / log_name)
    junit_hash = checker.sha(source / raw / junit_name)
    pytest_receipt = {
        "artifacts": [
            {"path": str(source / raw / log_name), "sha256": log_hash},
            {"path": str(source / raw / junit_name), "sha256": junit_hash},
        ],
        "authoritative": False,
        "command": ["python", "-m", "pytest"],
        "cwd": str(source / "main/backend"),
        "elapsed_seconds": 1.0,
        "environment": {"PYTHONHASHSEED": "0"},
        "exit_code": 0,
        "isolation": "getaddrinfo fail-fast injection only",
    }
    receipt_name = "bound-final.json"
    (relocated / raw / log_name).write_bytes(b"clean pytest output\n")
    (relocated / raw / junit_name).write_bytes((source / raw / junit_name).read_bytes())
    receipt_path = relocated / raw / receipt_name
    receipt_path.write_text(json.dumps(pytest_receipt), encoding="utf-8")

    frontend_log_name = "frontend-build.log"
    frontend_receipt_name = "frontend-build.json"
    (source / raw / frontend_log_name).write_bytes(b"frontend build\n")
    (relocated / raw / frontend_log_name).write_bytes(b"frontend build\n")
    frontend_receipt = {
        "artifacts": [
            {
                "path": str(source / raw / frontend_log_name),
                "sha256": checker.sha(source / raw / frontend_log_name),
            }
        ],
        "authoritative": False,
        "command": ["pnpm", "build"],
        "cwd": str(source / "main/frontend-modern"),
        "elapsed_seconds": 2.0,
        "environment": {"DO_NOT_TRACK": "1"},
        "exit_code": 0,
    }
    command_receipt_path = relocated / raw / frontend_receipt_name
    command_receipt_path.write_text(json.dumps(frontend_receipt), encoding="utf-8")

    rows = []
    all_paths = (*checker.REQUIRED_ARTIFACT_PATHS, extension.as_posix())
    for item in all_paths:
        current_hash = checker.sha(relocated / item)
        v6_hash = (
            "2" * 64
            if item in checker.OBSERVED_ARTIFACT_PATHS
            else "0" * 64
        )
        rows.append(
            {
                "path": item,
                "v6_sha256": v6_hash,
                "v6_present": item in checker.OBSERVED_ARTIFACT_PATHS,
                "current_sha256": current_hash,
                "changed": v6_hash != current_hash,
            }
        )
    for relative in {checker.BUILDER, checker.CHECKER, checker.PACKAGE_TEST}:
        path = relocated / relative
        path.write_bytes(b"package script\n")

    record = {
        "schema_version": "mrw.stage1.stage3_v6_artifact_remediation_record.v1",
        "status": "PASS_STAGE3_V6_ARTIFACT_REMEDIATION_NOT_AUTHORITY",
        "authoritative": False,
        "authority_ceiling": checker.CEILING,
        "contract": {"path": contract.as_posix(), "sha256": contract_sha256},
        "predecessor": {
            "candidate_root": str(candidate),
            "commit": checker.V6_COMMIT,
            "tree": checker.V6_TREE,
            "evidence": evidence_refs,
            "input_observation": {
                "path": checker.INPUT_OBSERVATION.as_posix(),
                "sha256": checker.sha(observation_path),
            },
            "receipt_source_root": str(source),
            "v6_intake_remediation_record": {
                "path": checker.HISTORICAL_V6_REMEDIATION_RECORD.as_posix(),
                "sha256": checker.sha(historical_path),
            },
        },
        "artifact_paths": rows,
        "additional_binding_paths": [extension.as_posix()],
        "test_receipts": [
            {
                "path": (raw / receipt_name).as_posix(),
                "sha256": checker.sha(receipt_path),
                "role": "final",
                "kind": "pytest",
            }
        ],
        "command_receipts": [
            {
                "path": (raw / frontend_receipt_name).as_posix(),
                "sha256": checker.sha(command_receipt_path),
                "kind": "frontend-tool",
            }
        ],
        "fresh_test_summary": {
            "receipt_count": 1,
            "final_receipt_count": 1,
            "command_receipt_count": 1,
            "all_exit_codes_zero": True,
            "junit_failures": 0,
            "junit_errors": 0,
            "junit_skipped": 0,
        },
        "current_bindings": {
            "record": checker.RECORD.as_posix(),
            "builder": checker.BUILDER.as_posix(),
            "checker": checker.CHECKER.as_posix(),
            "test": checker.PACKAGE_TEST.as_posix(),
        },
        "external_effects": "NONE_LOCAL_DETERMINISTIC_VALIDATION_ONLY",
        "production_release_authorized": False,
    }
    record_path = relocated / checker.RECORD
    record_path.write_text(json.dumps(record), encoding="utf-8")
    return relocated, receipt_path, source / raw / junit_name


def test_relocated_root_full_checker_projects_only_local_raw(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relocated, receipt_path, original_junit = make_relocated_fixture(tmp_path, monkeypatch)
    record = checker.load(relocated / checker.RECORD)
    expected_members = checker.manifest_members(record, root=relocated)
    assert checker.validate_record(
        record,
        root=relocated,
        receipt_paths=(receipt_path,),
    ) == tuple(Path(row["path"]) for row in expected_members)

    (relocated / checker.RECORD).unlink()
    assert checker.manifest_members(record, root=relocated) == expected_members
    checker.validate_record(record, root=relocated, receipt_paths=(receipt_path,))
    (relocated / checker.INPUT_OBSERVATION.parent / "raw" / "bound-final.xml").unlink()
    assert original_junit.is_file()
    with pytest.raises(ValueError, match="RELOCATED_ARTIFACT_MISSING"):
        checker.validate_record(
            record,
            root=relocated,
            receipt_paths=(receipt_path,),
        )


def test_accepts_current_clean_pytest_receipt_with_junit() -> None:
    parsed = checker.validate_receipt(
        receipt("source-selector.json"),
        root=checker.ROOT,
        source_root=historical_receipt_source_root(),
    )
    assert parsed["junit"]["failures"] == 0
    assert parsed["junit"]["errors"] == 0
    assert parsed["junit"]["skipped"] == 0


def test_accepts_focused_receipt_without_claiming_dns_injection() -> None:
    payload = receipt("focused-final.json")
    assert payload["isolation"] == "none added"
    assert checker.validate_receipt(
        payload,
        root=checker.ROOT,
        source_root=historical_receipt_source_root(),
    )["junit"]["failures"] == 0
    payload["isolation"] = "complete network isolation"
    with pytest.raises(ValueError, match="RECEIPT_ISOLATION"):
        checker.validate_receipt(
            payload,
            root=checker.ROOT,
            source_root=historical_receipt_source_root(),
        )


def test_accepts_each_frontend_command_receipt_without_junit() -> None:
    names = (
        "frontend-build.json",
        "frontend-frozen-install.json",
        "frontend-lint.json",
        "frontend-storybook.json",
        "frontend-typecheck.json",
        "frontend-build-development-takeover-20260908.json",
        "frontend-frozen-install-development-takeover-20260908.json",
        "frontend-lint-development-takeover-20260908.json",
        "frontend-storybook-development-takeover-20260908.json",
        "frontend-typecheck-development-takeover-20260908.json",
    )
    for name in names:
        parsed = checker.validate_command_receipt(
            receipt(name),
            root=checker.ROOT,
            source_root=historical_receipt_source_root(),
        )
        assert ".xml" not in parsed["log"]["path"]
        assert parsed["log"]["path"].endswith(".log")


def test_rejects_non_pytest_command_as_pytest_receipt(tmp_path: Path) -> None:
    payload = receipt("source-selector.json")
    payload["command"] = ["python", "-c", "import sys; sys.exit(0)"]
    with pytest.raises(ValueError, match="RECEIPT_NOT_PYTEST"):
        checker.validate_receipt(payload, root=tmp_path)


def test_rejects_dirty_junit_without_hardcoding_pass_count(tmp_path: Path) -> None:
    junit = tmp_path / "dirty.xml"
    write_junit(junit, tests=7, failures=1)
    with pytest.raises(ValueError, match="JUNIT_NOT_CLEAN"):
        checker.validate_junit(junit)

    clean = tmp_path / "clean.xml"
    write_junit(clean, tests=41)
    assert checker.validate_junit(clean)["tests"] == 41


def test_rejects_authoritative_command_receipt(tmp_path: Path) -> None:
    payload = receipt("frontend-build.json")
    payload["authoritative"] = True
    with pytest.raises(ValueError, match="COMMAND_RECEIPT_AUTHORITY"):
        checker.validate_command_receipt(payload, root=tmp_path)


def test_rejects_unknown_frontend_command_receipt(tmp_path: Path) -> None:
    payload = receipt("frontend-build.json")
    payload["command"] = ["python", "-c", "print('pass')"]
    with pytest.raises(ValueError, match="COMMAND_RECEIPT_COMMAND_KIND"):
        checker.validate_command_receipt(
            payload,
            root=checker.ROOT,
            source_root=historical_receipt_source_root(),
        )


def test_rejects_missing_manifest_member(tmp_path: Path) -> None:
    member = tmp_path / "member.txt"
    member.write_bytes(b"member\n")
    manifest = {
        "schema_version": "mrw.stage1.stage3_v6_artifact_remediation_manifest.v1",
        "status": "COMPLETE_NOT_AUTHORITY",
        "authoritative": False,
        "authority_ceiling": checker.CEILING,
        "member_count": 2,
        "members": [
            {"path": "member.txt", "bytes": member.stat().st_size, "sha256": checker.sha(member)},
            {"path": "missing.txt", "bytes": 0, "sha256": "0" * 64},
        ],
    }
    with pytest.raises(OSError):
        checker.validate_manifest(manifest, root=tmp_path)


def test_rejects_source_hash_drift(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_bytes(b"current\n")
    drifted = {"path": source.name, "sha256": "0" * 64}
    with pytest.raises(ValueError, match="REF_HASH"):
        checker.validate_file_hash(drifted, root=tmp_path)


def test_builder_parses_dynamic_changed_and_receipt_boundaries() -> None:
    args = builder.parse_args(
        (
            "--write",
            "--test-receipt",
            "raw/source-selector.json",
            "--command-receipt",
            "raw/frontend-build.json",
            "--final-test-receipt",
            "raw/source-selector-final.json",
            "--changed-path",
            "main/frontend-modern/package.json",
            "--changed-path",
            "main/frontend-modern/src/example.ts",
        )
    )
    assert args.test_receipt == [Path("raw/source-selector.json")]
    assert args.command_receipt == [Path("raw/frontend-build.json")]
    assert args.final_test_receipt == Path("raw/source-selector-final.json")
    assert args.changed_path == [
        Path("main/frontend-modern/package.json"),
        Path("main/frontend-modern/src/example.ts"),
    ]


def test_builder_rejects_write_without_explicit_final_boundary(tmp_path: Path) -> None:
    args = builder.parse_args(
        (
            "--write",
            "--test-receipt",
            "raw/source-selector.json",
            "--command-receipt",
            "raw/frontend-build.json",
            "--changed-path",
            "main/frontend-modern/package.json",
        )
    )
    assert args.final_test_receipt is None
    with pytest.raises(ValueError, match="final-test-receipt is required"):
        builder.main(args)


def test_correction1_paths_and_frozen_predecessor_are_fixed() -> None:
    assert builder.CORRECTION_RECORD == checker.CORRECTION_RECORD
    assert builder.CORRECTION_MANIFEST == checker.CORRECTION_MANIFEST
    assert builder.CORRECTION_VALIDATION == checker.CORRECTION_VALIDATION
    assert builder.PRIOR_ATTEMPT_RECORD_SHA256 == checker.PRIOR_ATTEMPT_RECORD_SHA256
    assert checker.CORRECTION_RECORD.as_posix().endswith(
        "stage3-v6-artifact-remediation-record.v1.correction1.json"
    )
    assert builder.CORRECTION_FINAL_BINDING_PATHS == (
        builder.INTAKE_PATH,
        builder.INTAKE_TEST_PATH,
        builder.SOURCE_CLOSURE_PATH,
        builder.SOURCE_CLOSURE_TEST_PATH,
    )
    assert builder.CORRECTION_FINAL_BINDING_PATHS == (
        checker.CORRECTION_FINAL_BINDING_PATHS
    )


def test_correction1_selector_policy_matches_live_selector_contract() -> None:
    policy = checker.workflow_selector_policy_binding()
    assert policy["python_roots"] == list(source_closure.WORKFLOW_SELECTOR_PYTHON_ROOTS)
    assert policy["shell_roots"] == list(source_closure.WORKFLOW_SELECTOR_SHELL_ROOTS)
    assert policy["json_roots"] == list(source_closure.WORKFLOW_SELECTOR_JSON_ROOTS)
    assert policy["json_subtree_roots"] == list(
        source_closure.WORKFLOW_SELECTOR_JSON_SUBTREE_ROOTS
    )
    assert policy["json_subtree_required_parent_component"] == "sidecar-inputs"


def test_checker_accepts_original_and_correction_record_paths_only() -> None:
    assert checker._selected_record_paths(None) == (
        checker.RECORD,
        checker.MANIFEST,
        checker.VALIDATION,
        False,
    )
    assert checker._selected_record_paths(checker.CORRECTION_RECORD) == (
        checker.CORRECTION_RECORD,
        checker.CORRECTION_MANIFEST,
        checker.CORRECTION_VALIDATION,
        True,
    )
    with pytest.raises(ValueError, match="RECORD_PATH_UNSUPPORTED"):
        checker._selected_record_paths(Path("stage1-successor-evidence/other-record.json"))


def test_builder_correction_mode_is_explicit_and_mutually_exclusive() -> None:
    args = builder.parse_args(
        (
            "--write-correction1",
            "--test-receipt",
            "raw/source-selector.json",
            "--command-receipt",
            "raw/frontend-build.json",
            "--final-test-receipt",
            "raw/source-selector-final.json",
        )
    )
    assert args.write_correction1 is True
    assert args.check is False and args.write is False

    exclusive = builder.parse_args(
        (
            "--write",
            "--write-correction1",
            "--test-receipt",
            "raw/source-selector.json",
            "--command-receipt",
            "raw/frontend-build.json",
            "--final-test-receipt",
            "raw/source-selector-final.json",
        )
    )
    with pytest.raises(ValueError, match="mutually exclusive"):
        builder.main(exclusive)


def test_checker_validates_bounded_correction1_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relocated, receipt_path, _junit = make_relocated_fixture(tmp_path, monkeypatch)
    record = checker.load(relocated / checker.RECORD)
    prior_path = relocated / checker.PRIOR_ATTEMPT_RECORD
    prior_path.write_bytes(b"prior attempt\n")
    prior_hash = checker.sha(prior_path)
    monkeypatch.setattr(checker, "PRIOR_ATTEMPT_RECORD_SHA256", prior_hash)
    for path in (checker.SOURCE_CLOSURE_PATH, checker.SOURCE_CLOSURE_TEST_PATH):
        target = relocated / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"selector policy\n")

    final_bindings = [
        {
            "path": path.as_posix(),
            "sha256": checker.sha(relocated / path),
        }
        for path in checker.CORRECTION_FINAL_BINDING_PATHS
    ]
    corrected = copy.deepcopy(record)
    corrected["correction"] = {
        "attempt": 1,
        "reason": "INTAKE_C6_AND_WORKFLOW_SELECTOR_POLICY_BYTE_DRIFT",
        "predecessor_record": {
            "path": checker.PRIOR_ATTEMPT_RECORD.as_posix(),
            "sha256": prior_hash,
        },
        "final_bindings": final_bindings,
        "workflow_selector_policy": checker.workflow_selector_policy_binding(
            root=relocated
        ),
    }
    corrected["artifact_paths"].append(
        {
            "path": checker.PRIOR_ATTEMPT_RECORD.as_posix(),
            "v6_sha256": "0" * 64,
            "v6_present": False,
            "current_sha256": prior_hash,
            "changed": True,
        }
    )
    corrected["additional_binding_paths"].append(checker.PRIOR_ATTEMPT_RECORD.as_posix())
    for path in (checker.SOURCE_CLOSURE_PATH, checker.SOURCE_CLOSURE_TEST_PATH):
        corrected["artifact_paths"].append(
            {
                "path": path.as_posix(),
                "v6_sha256": "0" * 64,
                "v6_present": False,
                "current_sha256": checker.sha(relocated / path),
                "changed": True,
            }
        )
        corrected["additional_binding_paths"].append(path.as_posix())
    corrected["current_bindings"]["record"] = checker.CORRECTION_RECORD.as_posix()

    expected_members = checker.manifest_members(
        corrected,
        root=relocated,
        record_path=checker.CORRECTION_RECORD,
    )
    assert checker.validate_record(
        corrected,
        root=relocated,
        receipt_paths=(receipt_path,),
        record_path=checker.CORRECTION_RECORD,
    ) == tuple(Path(row["path"]) for row in expected_members)
    assert set(checker.CORRECTION_FINAL_BINDING_PATHS) <= {
        Path(row["path"]) for row in expected_members
    }

    drifted = copy.deepcopy(corrected)
    drifted["correction"]["final_bindings"][0]["sha256"] = "f" * 64
    with pytest.raises(ValueError, match="CORRECTION_BINDING"):
        checker.validate_record(
            drifted,
            root=relocated,
            receipt_paths=(receipt_path,),
            record_path=checker.CORRECTION_RECORD,
        )

    omitted = copy.deepcopy(corrected)
    omitted["additional_binding_paths"].remove(
        checker.SOURCE_CLOSURE_TEST_PATH.as_posix()
    )
    with pytest.raises(ValueError, match="CORRECTION_SELECTOR_BINDINGS_MISSING"):
        checker.validate_record(
            omitted,
            root=relocated,
            receipt_paths=(receipt_path,),
            record_path=checker.CORRECTION_RECORD,
        )


def test_real_record_payload_selects_correction_record_binding() -> None:
    prior = checker.load(builder.ROOT / builder.RECORD)
    receipt_source_root = Path(prior["predecessor"]["receipt_source_root"])
    assert receipt_source_root.is_absolute()
    test_receipts = [
        Path(row["path"])
        for row in prior["test_receipts"]
    ]
    final_receipt = next(
        Path(row["path"])
        for row in prior["test_receipts"]
        if row["role"] == "final"
    )
    command_receipts = [Path(row["path"]) for row in prior["command_receipts"]]

    original = builder.record_payload(
        receipt_paths=test_receipts,
        command_receipt_paths=command_receipts,
        final_receipt=final_receipt,
        receipt_source_root=receipt_source_root,
        changed_paths=[Path(row) for row in prior["additional_binding_paths"]],
    )
    correction = builder.record_payload(
        receipt_paths=test_receipts,
        command_receipt_paths=command_receipts,
        final_receipt=final_receipt,
        receipt_source_root=receipt_source_root,
        changed_paths=[Path(row) for row in prior["additional_binding_paths"]],
        correction1=True,
    )

    assert original["current_bindings"]["record"] == builder.RECORD.as_posix()
    assert "correction" not in original
    assert correction["current_bindings"]["record"] == builder.CORRECTION_RECORD.as_posix()
    assert correction["correction"]["attempt"] == 1
    assert correction["correction"]["predecessor_record"] == {
        "path": builder.PRIOR_ATTEMPT_RECORD.as_posix(),
        "sha256": builder.PRIOR_ATTEMPT_RECORD_SHA256,
    }
    assert correction["correction"]["final_bindings"] == [
        {
            "path": path.as_posix(),
            "sha256": builder.sha(builder.ROOT / path),
        }
        for path in builder.CORRECTION_FINAL_BINDING_PATHS
    ]
    assert correction["correction"]["workflow_selector_policy"] == (
        checker.workflow_selector_policy_binding(root=builder.ROOT)
    )
    assert builder.PRIOR_ATTEMPT_RECORD.as_posix() in correction["additional_binding_paths"]

    expected_members = checker.manifest_members(
        correction,
        root=builder.ROOT,
        record_path=builder.CORRECTION_RECORD,
    )
    assert checker.validate_record(
        correction,
        receipt_paths=tuple(builder.ROOT / path for path in test_receipts),
        record_path=builder.CORRECTION_RECORD,
    ) == tuple(Path(row["path"]) for row in expected_members)
