from __future__ import annotations

# ruff: noqa: E501

import copy
from pathlib import Path

import pytest

from scripts.formal_release import check_stage1_r2_remediation_record as checker
from scripts.formal_release import generate_stage1_r2_remediation_record as generator


ROOT = Path(__file__).resolve().parents[2]


def sample_record() -> dict[str, object]:
    receipts = []
    results = []
    for check_id in generator.COMMAND_IDS:
        receipt = Path("tests/formal_release") / f"{check_id}.log"
        # Rebind the test module itself under synthetic receipt names in a temporary root in tests below.
        results.append({
            "id": check_id,
            "command": check_id,
            "exit_code": 1 if check_id == "r2_direct_fail_closed_fixture" else 0,
            "result": '{"status": "FAIL"}' if check_id == "r2_direct_fail_closed_fixture" else "PASS",
        })
        receipts.append(receipt)
    record = generator.build_record(ROOT, "2026-09-06T00:00:00Z", results, [])
    record["test_receipts"] = receipts
    return record


def test_constants_keep_dispatch_r2_hashes() -> None:
    assert generator.binding(ROOT, generator.R2_CHECKER)["sha256"] == generator.EXPECTED_R2[generator.R2_CHECKER]
    assert generator.binding(ROOT, generator.R2_TEST)["sha256"] == generator.EXPECTED_R2[generator.R2_TEST]


def test_r2_record_retains_non_authority_and_exact_input_bindings() -> None:
    from typing import get_type_hints

    record = sample_record()
    assert record["authoritative"] is False
    assert record["historical_stage1_record_ref_and_sha256"] == generator.binding(ROOT, generator.HISTORICAL_RECORD)
    assert record["required_file_refs_and_sha256"] == [
        generator.binding(ROOT, generator.R2_CHECKER), generator.binding(ROOT, generator.R2_TEST),
    ]
    annotation = get_type_hints(generator.build_record, include_extras=True)["return"]
    assert "kit:non-authoritative" in annotation.__metadata__[0]
    assert "fact_source=frozen_repository_inputs+validation_receipts" in annotation.__metadata__[0]


def test_record_validator_accepts_exact_record(tmp_path: Path) -> None:
    record = sample_record()
    receipts = []
    for check_id in generator.COMMAND_IDS:
        path = tmp_path / f"{check_id}.log"
        path.write_text("receipt\n", encoding="utf-8")
        relative = path.relative_to(tmp_path)
        receipts.append(generator.binding(tmp_path, relative))
    record["test_receipts"] = receipts
    checker.validate_record(tmp_path, _rebind_repository_refs(tmp_path, record))


def _rebind_repository_refs(tmp_path: Path, record: dict[str, object]) -> dict[str, object]:
    # Copy the exact repository inputs so the checker proves byte binding independent of the live root.
    for relative in (
        generator.HISTORICAL_RECORD, generator.HISTORICAL_REVIEW, generator.R2_CHECKER,
        generator.R2_TEST, generator.WORKFLOW, generator.BRANCH_PROTECTION, generator.SELF_CHECKER,
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    rebound = copy.deepcopy(record)
    rebound["historical_stage1_record_ref_and_sha256"] = generator.binding(tmp_path, generator.HISTORICAL_RECORD)
    rebound["historical_stage1_review_ref_and_sha256"] = generator.binding(tmp_path, generator.HISTORICAL_REVIEW)
    rebound["required_file_refs_and_sha256"] = [generator.binding(tmp_path, generator.R2_CHECKER), generator.binding(tmp_path, generator.R2_TEST)]
    rebound["workflow_refs_and_sha256"] = [generator.binding(tmp_path, generator.WORKFLOW), generator.binding(tmp_path, generator.BRANCH_PROTECTION)]
    rebound["independent_review_or_checker"] = {**generator.binding(tmp_path, generator.SELF_CHECKER), "status": "PASS"}
    return rebound


def test_record_validator_rejects_required_file_drift(tmp_path: Path) -> None:
    record = sample_record()
    for check_id in generator.COMMAND_IDS:
        path = tmp_path / f"{check_id}.log"
        path.write_text("receipt\n", encoding="utf-8")
    record["test_receipts"] = [generator.binding(tmp_path, Path(f"{check_id}.log")) for check_id in generator.COMMAND_IDS]
    record = _rebind_repository_refs(tmp_path, record)
    (tmp_path / generator.R2_CHECKER).write_text("drift\n", encoding="utf-8")
    with pytest.raises(generator.Stage1R2RemediationError, match="binding drift|frozen input drift"):
        checker.validate_record(tmp_path, record)
