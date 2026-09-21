# ruff: noqa: E501
from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
PATH = Path(__file__).with_name("check_stage2_v6_intake_remediation_v5.py")
SPEC = importlib.util.spec_from_file_location("stage2_v6_remediation_v5_test", PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def test_current_package_passes() -> None:
    checker.validate_manifest(checker.load(ROOT / checker.MANIFEST))
    checker.validate_record(checker.load(ROOT / checker.RECORD))


def test_mutations_fail_closed() -> None:
    record = checker.load(ROOT / checker.RECORD)
    drifted = copy.deepcopy(record)
    drifted["authoritative"] = True
    with pytest.raises(ValueError, match="RECORD_AUTHORITY"):
        checker.validate_record(drifted)
    drifted = copy.deepcopy(record)
    drifted["changed_paths"][0]["successor_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="CHANGED_CURRENT"):
        checker.validate_record(drifted)


def test_validation_receipt_exact() -> None:
    assert (ROOT / checker.VALIDATION).read_bytes() == checker.canonical(checker.receipt_payload())
