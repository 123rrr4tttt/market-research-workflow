from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = Path(__file__).with_name("check_stage2_v6_intake_remediation_v3.py")
SPEC = importlib.util.spec_from_file_location(
    "stage2_v6_intake_remediation_checker_v3_test", CHECKER_PATH
)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def test_current_package_passes() -> None:
    checker.validate_manifest(checker.load_object(ROOT / checker.MANIFEST_REL))
    checker.validate_record(checker.load_object(ROOT / checker.RECORD_REL))


def test_schema_and_authority_mutations_fail_closed() -> None:
    record = checker.load_object(ROOT / checker.RECORD_REL)
    drifted = copy.deepcopy(record)
    drifted["schema_version"] = "mrw.stage1.stage2_v6_intake_remediation_record.v4"
    with pytest.raises(ValueError, match="RECORD_SCHEMA"):
        checker.validate_record(drifted)
    elevated = copy.deepcopy(record)
    elevated["authoritative"] = True
    with pytest.raises(ValueError, match="RECORD_AUTHORITY"):
        checker.validate_record(elevated)


def test_predecessor_and_current_hash_mutations_fail_closed() -> None:
    record = checker.load_object(ROOT / checker.RECORD_REL)
    drifted = copy.deepcopy(record)
    drifted["predecessor"]["v2_record"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="V2_RECORD_HASH"):
        checker.validate_record(drifted)
    drifted = copy.deepcopy(record)
    drifted["changed_paths"][0]["successor_sha256"] = "1" * 64
    with pytest.raises(ValueError, match="CURRENT_HASH"):
        checker.validate_record(drifted)


def test_workflow_constant_and_closure_mutations_fail_closed() -> None:
    record = checker.load_object(ROOT / checker.RECORD_REL)
    drifted = copy.deepcopy(record)
    drifted["current_bindings"]["new_record_constant"] = "WRONG_NAME"
    with pytest.raises(ValueError, match="CURRENT_BINDINGS"):
        checker.validate_record(drifted)
    drifted = copy.deepcopy(record)
    drifted["workflow_selector_closure"]["selector_roots"].remove("scripts")
    with pytest.raises(ValueError, match="WORKFLOW_SELECTOR_CONTRACT"):
        checker.validate_record(drifted)


def test_validation_receipt_is_exact() -> None:
    assert (ROOT / checker.VALIDATION_REL).read_bytes() == checker.canonical_bytes(
        checker.validation_receipt()
    )
