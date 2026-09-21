#!/usr/bin/env python3
"""Focused tests for the Stage 3 remediation correction2 package."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


checker = load_module(
    "stage3_v6_artifact_remediation_correction2_checker_tests",
    HERE / "check_stage3_v6_artifact_remediation_correction2.py",
)
builder = load_module(
    "stage3_v6_artifact_remediation_correction2_builder_tests",
    HERE / "build_stage3_v6_artifact_remediation_correction2.py",
)


def correction1_inputs():
    return checker.validate_correction1_inputs()


@pytest.fixture
def isolated_receipt():
    expected_count = 2
    with tempfile.TemporaryDirectory(
        prefix=f"{checker.ISOLATED_BUNDLE_PREFIX}-fixture-",
        dir=HERE,
    ) as temporary:
        bundle = Path(temporary)
        run_id = bundle.name.removeprefix(f"{checker.ISOLATED_BUNDLE_PREFIX}-")
        log = bundle / "pytest.log"
        junit = bundle / "pytest.junit.xml"
        nodeids_path = bundle / "nodeids.json"
        plugin = bundle / "mrw_pytest_receipt_plugin_v2.py"
        receipt_path = bundle / "receipt.json"
        nodeids = ["tests/sample.py::test_a", "tests/sample.py::test_b"]
        log.write_bytes(b"2 passed\n")
        junit.write_text(
            "<testsuite tests='2' failures='0' errors='0' skipped='0'>"
            "<testcase classname='tests.sample' name='test_a'/>"
            "<testcase classname='tests.sample' name='test_b'/>"
            "</testsuite>",
            encoding="utf-8",
        )
        nodeids_path.write_text(json.dumps(nodeids) + "\n", encoding="utf-8")
        plugin.write_bytes(b"# fixture plugin\n")
        inputs = []
        for relative in checker.ISOLATED_TEST_TARGETS:
            current = checker.ROOT / relative
            inputs.append(
                {
                    "path": relative,
                    "sha256": checker.sha(current),
                    "size_bytes": current.stat().st_size,
                }
            )
        allowlisted = {key: "fixture" for key in checker.ISOLATED_ENVIRONMENT_KEYS}
        allowlisted.update(
            {
                "GIT_CONFIG_COUNT": "0",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_NOSYSTEM": "1",
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            }
        )
        expected = {
            "collected": expected_count,
            "passed": expected_count,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
        }
        artifact_paths = (log, junit, nodeids_path, plugin)
        receipt = {
            "schema": checker.ISOLATED_RECEIPT_SCHEMA,
            "status": f"PASS_COMPLETE_EXACT_{expected_count}",
            "authoritative": False,
            "authority": {
                "candidate_promotion": False,
                "production_release": False,
                "deployment": False,
                "live_write": False,
            },
            "run_id": run_id,
            "expected_count": expected_count,
            "bundle": bundle.as_posix(),
            "execution": {
                "argv": [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-p",
                    "no:cacheprovider",
                    "-p",
                    "mrw_pytest_receipt_plugin_v2",
                    "-q",
                    *checker.ISOLATED_TEST_TARGETS,
                    f"--junitxml={(bundle / 'temporary.junit.xml').as_posix()}",
                ],
                "cwd": checker.ROOT.as_posix(),
                "process_exit_code": 0,
                "execution_error": None,
            },
            "environment": {
                "inherit_ambient": False,
                "allowlisted": allowlisted,
                "explicitly_not_inherited": list(checker.PYTEST_CONTROL_VARIABLES),
            },
            "inputs": {
                "before": inputs,
                "after": copy.deepcopy(inputs),
                "after_error": None,
                "unchanged_during_run": True,
            },
            "results": {
                "expected": expected,
                "observed": expected,
                "junit_suite_attributes": {
                    "tests": expected_count,
                    "failures": 0,
                    "errors": 0,
                    "skipped": 0,
                },
                "junit_testcase_derived": {
                    "tests": expected_count,
                    "failures": 0,
                    "errors": 0,
                    "skipped": 0,
                    "passed": expected_count,
                },
                "junit_counts_consistent": True,
                "junit_error": None,
                "nodeids_error": None,
                "nodeids_unique": True,
                "nodeids_normalization": "sorted UTF-8 RFC8259 JSON with no whitespace",
                "nodeids_sha256": checker.sha_bytes(
                    json.dumps(
                        nodeids,
                        ensure_ascii=True,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode("utf-8")
                ),
                "nodeids": nodeids,
            },
            "artifacts": [
                {
                    "path": path.as_posix(),
                    "present": True,
                    "sha256": checker.sha(path),
                    "size_bytes": path.stat().st_size,
                }
                for path in artifact_paths
            ],
            "cleanup": {
                "runtime_directory_removed_before_publish": True,
                "error": None,
            },
        }
        receipt_path.write_bytes(checker.canonical(receipt))
        yield receipt_path.relative_to(checker.ROOT), expected_count, checker.HERE


def test_fixed_correction1_trio_hashes_and_in_memory_package(isolated_receipt) -> None:
    for relative, expected_hash in checker.CORRECTION1_HASHES.items():
        assert checker.sha(checker.ROOT / relative) == expected_hash
    receipt_path, expected_count, bundle_parent = isolated_receipt
    record, manifest, validation = checker.build_expected_payloads(
        isolated_receipt_path=receipt_path,
        isolated_expected_count=expected_count,
        isolated_bundle_parent=bundle_parent,
    )
    assert record["status"] == "PASS_COMPLETE_MEMBER_CLOSURE_NOT_AUTHORITY"
    for payload in (record, manifest, validation):
        assert payload["authoritative"] is False
        assert payload["production_release_authorized"] is False
        assert payload["production_release_status"] == "PRODUCTION_RELEASE_NOT_AUTHORIZED"


def test_closure_contains_every_artifact_path_and_correction1_member(isolated_receipt) -> None:
    record, manifest, _validation = correction1_inputs()
    receipt_path, expected_count, bundle_parent = isolated_receipt
    closure, _expanded, _drifts, _binding = checker.collect_member_closure(
        record,
        manifest,
        isolated_receipt_path=receipt_path,
        isolated_expected_count=expected_count,
        isolated_bundle_parent=bundle_parent,
    )
    paths = {row["path"] for row in closure}
    assert {row["path"] for row in record["artifact_paths"]} <= paths
    assert {row["path"] for row in manifest["members"]} <= paths
    assert {path.as_posix() for path in checker.CORRECTION1_HASHES} <= paths


def test_closure_contains_receipts_and_all_receipt_artifacts(isolated_receipt) -> None:
    record, manifest, _validation = correction1_inputs()
    receipt_path, expected_count, bundle_parent = isolated_receipt
    closure, _expanded, _drifts, _binding = checker.collect_member_closure(
        record,
        manifest,
        isolated_receipt_path=receipt_path,
        isolated_expected_count=expected_count,
        isolated_bundle_parent=bundle_parent,
    )
    paths = {row["path"] for row in closure}
    source_root = Path(record["predecessor"]["receipt_source_root"])
    for field in ("test_receipts", "command_receipts"):
        for ref in record[field]:
            assert ref["path"] in paths
            receipt = checker.load(checker.ROOT / ref["path"])
            for artifact in receipt["artifacts"]:
                assert Path(artifact["path"]).relative_to(source_root).as_posix() in paths


def test_nested_v3_manifest_closure_is_expanded(isolated_receipt) -> None:
    record, manifest, _validation = correction1_inputs()
    receipt_path, expected_count, bundle_parent = isolated_receipt
    closure, expanded, _drifts, _binding = checker.collect_member_closure(
        record,
        manifest,
        isolated_receipt_path=receipt_path,
        isolated_expected_count=expected_count,
        isolated_bundle_parent=bundle_parent,
    )
    paths = {row["path"] for row in closure}
    required_manifests = {
        Path("stage1-successor-evidence/current-byte-remediation-v3/bindings/artifact-manifest.v3.json"),
        Path("stage1-successor-evidence/current-byte-remediation-v3/semantic-bindings/artifact-manifest.v3.json"),
    }
    assert required_manifests <= set(expanded)
    for nested_path in required_manifests:
        nested = checker.load(checker.ROOT / nested_path)
        assert {row["path"] for row in nested["members"]} <= paths


def test_declared_hash_drift_is_rejected() -> None:
    nested_path = Path(
        "stage1-successor-evidence/current-byte-remediation-v3/bindings/artifact-manifest.v3.json"
    )
    nested = checker.load(checker.ROOT / nested_path)
    corrupted = copy.deepcopy(nested["members"][0])
    corrupted["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="NESTED_TEST_HASH_DRIFT"):
        checker.validate_declared_member(
            corrupted,
            root=checker.ROOT,
            label="NESTED_TEST",
        )


def test_nested_manifest_self_hash_drift_is_rejected(isolated_receipt) -> None:
    record, manifest, _validation = correction1_inputs()
    changed = copy.deepcopy(record)
    nested_path = (
        "stage1-successor-evidence/current-byte-remediation-v3/"
        "bindings/artifact-manifest.v3.json"
    )
    row = next(item for item in changed["artifact_paths"] if item["path"] == nested_path)
    row["current_sha256"] = "0" * 64
    receipt_path, expected_count, bundle_parent = isolated_receipt
    with pytest.raises(ValueError, match="NESTED_MANIFEST_SELF_HASH_DRIFT"):
        checker.collect_member_closure(
            changed,
            manifest,
            isolated_receipt_path=receipt_path,
            isolated_expected_count=expected_count,
            isolated_bundle_parent=bundle_parent,
        )


def test_direct_correction1_member_drift_is_rebound_not_rejected(isolated_receipt) -> None:
    record, manifest, _validation = correction1_inputs()
    changed = copy.deepcopy(manifest)
    row = next(item for item in changed["members"] if item["path"].endswith("stage2_candidate_intake.py"))
    row["bytes"] = 1
    row["sha256"] = "0" * 64
    receipt_path, expected_count, bundle_parent = isolated_receipt
    closure, _expanded, drifts, _binding = checker.collect_member_closure(
        record,
        changed,
        isolated_receipt_path=receipt_path,
        isolated_expected_count=expected_count,
        isolated_bundle_parent=bundle_parent,
    )
    closure_by_path = {item["path"]: item for item in closure}
    live_path = row["path"]
    assert closure_by_path[live_path]["sha256"] == checker.sha(checker.ROOT / live_path)
    assert any(item["path"] == live_path and item["changed"] is True for item in drifts)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("authoritative", True, "RECORD_AUTHORITY"),
        ("production_release_authorized", True, "RECORD_RELEASE"),
        ("authority_ceiling", "UNBOUNDED", "RECORD_CEILING"),
    ],
)
def test_authority_ceiling_is_fail_closed(
    field: str,
    value: object,
    error: str,
    isolated_receipt,
) -> None:
    receipt_path, expected_count, bundle_parent = isolated_receipt
    record, manifest, _validation = checker.build_expected_payloads(
        isolated_receipt_path=receipt_path,
        isolated_expected_count=expected_count,
        isolated_bundle_parent=bundle_parent,
    )
    changed = copy.deepcopy(record)
    changed[field] = value
    with pytest.raises(ValueError, match=error):
        checker.validate_record(changed, record)
    assert manifest["authoritative"] is False
    assert manifest["production_release_authorized"] is False


def test_manifest_membership_omission_is_rejected(isolated_receipt) -> None:
    receipt_path, expected_count, bundle_parent = isolated_receipt
    _record, manifest, _validation = checker.build_expected_payloads(
        isolated_receipt_path=receipt_path,
        isolated_expected_count=expected_count,
        isolated_bundle_parent=bundle_parent,
    )
    changed = copy.deepcopy(manifest)
    changed["members"].pop()
    changed["member_count"] -= 1
    with pytest.raises(ValueError, match="MANIFEST_DRIFT"):
        checker.validate_manifest(changed, manifest)


def test_atomic_bundle_is_create_only(tmp_path: Path) -> None:
    output = tmp_path / "package"
    payloads = {"record.json": b"record\n", "manifest.json": b"manifest\n"}
    builder.atomic_publish_bundle(output, payloads)
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    with pytest.raises(FileExistsError, match="create-only output exists"):
        builder.atomic_publish_bundle(output, {"record.json": b"changed\n"})
    assert {path.name: path.read_bytes() for path in output.iterdir()} == before
    assert not list(tmp_path.glob(".package.staging-*"))
