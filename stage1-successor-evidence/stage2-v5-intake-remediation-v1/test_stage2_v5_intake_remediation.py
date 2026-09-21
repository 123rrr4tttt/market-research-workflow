from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = Path(__file__).with_name("check_stage2_v5_intake_remediation.py")
SPEC = importlib.util.spec_from_file_location("stage2_v5_intake_remediation_checker", CHECKER_PATH)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)


def test_current_package_passes() -> None:
    checker.validate_manifest(checker.load_object(ROOT / checker.MANIFEST_REL))
    checker.validate_record(checker.load_object(ROOT / checker.RECORD_REL))


def test_authority_and_resolution_mutations_fail_closed() -> None:
    record = checker.load_object(ROOT / checker.RECORD_REL)
    elevated = copy.deepcopy(record)
    elevated["authoritative"] = True
    with pytest.raises(ValueError, match="RECORD_AUTHORITY"):
        checker.validate_record(elevated)
    drifted = copy.deepcopy(record)
    drifted["manifest_contract"]["candidate_specific_successor_resolutions"] = 5
    with pytest.raises(ValueError, match="RESOLUTION_COUNT"):
        checker.validate_record(drifted)


def test_validation_receipt_is_exact() -> None:
    expected = checker.canonical_bytes(checker.validation_receipt())
    assert (ROOT / checker.VALIDATION_REL).read_bytes() == expected
