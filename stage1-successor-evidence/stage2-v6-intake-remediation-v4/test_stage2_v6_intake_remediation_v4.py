# ruff: noqa: E501
from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = Path(__file__).with_name("check_stage2_v6_intake_remediation_v4.py")
SPEC = importlib.util.spec_from_file_location("stage2_v6_intake_remediation_checker_v4_test", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def test_current_package_passes() -> None:
    checker.validate_manifest(checker.load_object(ROOT / checker.MANIFEST_REL))
    checker.validate_record(checker.load_object(ROOT / checker.RECORD_REL))


def test_record_authority_and_schema_fail_closed() -> None:
    record = checker.load_object(ROOT / checker.RECORD_REL)
    drifted = copy.deepcopy(record)
    drifted["authoritative"] = True
    with pytest.raises(ValueError, match="RECORD_AUTHORITY"):
        checker.validate_record(drifted)
    drifted = copy.deepcopy(record)
    drifted["schema_version"] = "wrong"
    with pytest.raises(ValueError, match="RECORD_SCHEMA"):
        checker.validate_record(drifted)


def test_predecessor_and_current_hashes_fail_closed() -> None:
    record = checker.load_object(ROOT / checker.RECORD_REL)
    drifted = copy.deepcopy(record)
    drifted["predecessor"]["record"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="V3_RECORD_BINDING"):
        checker.validate_record(drifted)
    drifted = copy.deepcopy(record)
    drifted["changed_paths"][1]["successor_sha256"] = "1" * 64
    with pytest.raises(ValueError, match="CHANGED_CURRENT"):
        checker.validate_record(drifted)


def test_validation_receipt_is_exact() -> None:
    assert (ROOT / checker.VALIDATION_REL).read_bytes() == checker.canonical_bytes(checker.validation_receipt())
