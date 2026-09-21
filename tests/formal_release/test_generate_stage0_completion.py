from __future__ import annotations

import copy
import importlib.util
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/formal_release/generate_stage0_completion.py"
SPEC = importlib.util.spec_from_file_location("stage0_completion", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)

RECEIPT_BYTES = b"command receipt\n"
RECEIPT_SHA = hashlib.sha256(RECEIPT_BYTES).hexdigest()
FOCUSED_FIXTURE_BYTES = b"32 passed in 1.00s\n"
HISTORICAL_COMPLETION_V2 = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release/stage0-evidence/"
    "functorial-refactor-completion.v2.json"
)


def evidence() -> dict[str, object]:
    current = json.loads(
        (ROOT / HISTORICAL_COMPLETION_V2).read_text(encoding="utf-8")
    )
    commands = copy.deepcopy(current["commands"])
    for group, contracts in tool.COMMAND_CONTRACTS.items():
        for row, contract in zip(commands[group], contracts, strict=True):
            receipt_path = contract["receipt_path"]
            receipt_bytes = (
                FOCUSED_FIXTURE_BYTES
                if receipt_path.endswith("stage0-v4-completion-focused.log")
                else (ROOT / receipt_path).read_bytes()
            )
            row["receipt"] = {
                "path": receipt_path,
                "sha256": tool.sha256_bytes(receipt_bytes),
            }
            if "observed" in contract:
                row["observed"] = contract["observed"]
            else:
                row.pop("observed", None)
    return {
        "observed_at": current["observed_at"],
        "current_byte_rebind": current["current_byte_rebind"],
        "kit": {"result": "PASS"},
        "commands": commands,
        "skip_block": [],
        "negative_findings": current["negative_findings"],
    }


def _mixed_candidate_payload(family: str) -> tuple[dict[str, object], bytes, Path]:
    relative = tool._candidate_relative(ROOT, family)
    raw = (ROOT / relative).read_bytes()
    payload = json.loads(raw)
    return payload, raw, relative


def mixed_root(tmp_path: Path) -> Path:
    """Create an isolated completion fixture with the required mixed lineage."""
    root = tmp_path / "repo"
    for relative in (
        tool.PLAN_REL,
        tool.PLAN_FREEZE_REL,
        tool.BASELINE_REL,
        tool.LEDGER_REL,
        tool.KIT_REL,
        *tool.DECLARED_LOSS_REL.values(),
        *tool.MAP_RELS,
    ):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)

    shutil.copyfile(ROOT / tool.PLAN_REL, root / tool.PLAN_REL)
    shutil.copyfile(ROOT / tool.PLAN_FREEZE_REL, root / tool.PLAN_FREEZE_REL)
    (root / tool.BASELINE_REL).write_bytes(b"[]")
    _write_json(root / tool.LEDGER_REL, {"entries": {}})
    _write_json(
        root / tool.KIT_REL,
        {
            "schema": "stage0-kit-applicability.v1",
            "status": "CONSUMER_GATE_CLOSED_WITH_UPSTREAM_FINDINGS_RETAINED",
            "scope": {"authority": "NOT_AUTHORITY", "authority_all_false": True},
            "languages": {
                "python": {
                    "consumer_gate_status": "CONSUMER_GATE_CLOSED",
                    "upstream_execution": {
                        "status": "BLOCKED",
                        "ceiling": "UPSTREAM_PYTHON_BLOCKED",
                    },
                    "ceiling": "PYTHON_CONSUMER_CLOSED",
                },
                "typescript": {
                    "upstream_execution": {"status": "PASS", "ceiling": "UPSTREAM_TS_PASS"},
                    "ceiling": "TS_NOT_APPLICABLE",
                },
                "rust": {
                    "upstream_execution": {"status": "PARTIAL", "ceiling": "UPSTREAM_RUST_PARTIAL"},
                    "ceiling": "RUST_NOT_APPLICABLE",
                },
            },
            "ceiling": ["KIT_FINDINGS_RETAINED", "NOT_LIVE"],
        },
    )
    for relative in tool.DECLARED_LOSS_REL.values():
        _write_json(root / relative, {"status": "COMPLETE", "items": [{"decision": "IMPLEMENTED"}]})

    (root / "stage0-command-receipt.txt").write_bytes(RECEIPT_BYTES)
    (root / "negative-finding-receipt.txt").write_bytes(RECEIPT_BYTES)
    shutil.copyfile(ROOT / tool.FRONTEND_FULL_E2E_NEGATIVE_REL, root / tool.FRONTEND_FULL_E2E_NEGATIVE_REL)
    for rows in tool.COMMAND_CONTRACTS.values():
        for row in rows:
            source = ROOT / row["receipt_path"]
            destination = root / row["receipt_path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            if row["receipt_path"].endswith("stage0-v4-completion-focused.log"):
                destination.write_bytes(FOCUSED_FIXTURE_BYTES)
            else:
                shutil.copyfile(source, destination)

    candidate_rows: list[dict[str, object]] = []
    for family in tool.FAMILIES:
        payload, raw, relative = _mixed_candidate_payload(family)
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        candidate_rows.append(
            {
                "family": family,
                "stage": tool.CURRENT_CANDIDATE_STAGES[family],
                "candidate_path": relative.as_posix(),
                "candidate_id": payload["candidate_id"],
                "candidate_content_digest": payload["content_digest"],
                "candidate_file_sha256": tool.sha256_bytes(raw),
                "status": "CANDIDATE_VALID_NOT_AUTHORITY",
            }
        )

    _write_json(
        root / tool.MAP_RELS[0],
        {"status": "ACTIVE_MUTABLE_MAP", "priority_order": []},
    )
    _write_json(
        root / tool.MAP_RELS[1],
        {
            "status": "ACTIVE_MUTABLE_MAP",
            "authority": {"promotion": False},
            "priority_order": [
                {"shared_family_projection": {"rows": candidate_rows}}
            ],
        },
    )
    return root


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def test_build_binds_mixed_lineage_and_nine_candidates(tmp_path: Path) -> None:
    root = mixed_root(tmp_path)
    record = tool.build_completion_record(root, evidence())

    assert record["status"] == tool.STATUS
    assert record["schema"] == tool.SCHEMA
    assert record["schema_version"] == tool.SCHEMA_VERSION
    assert record["record_id"] == "stage0-functorial-refactor-completion-v4"
    assert record["authoritative"] is False
    assert record["derived_as"] == "external_claim"
    assert record["current_byte_rebind"] == evidence()["current_byte_rebind"]
    assert record["candidate_commit"] is None
    assert record["candidate_tree"] is None
    assert set(record["authority"].values()) == {False}
    assert record["bindings"]["candidate_stages"] == tool.CURRENT_CANDIDATE_STAGES
    assert [row["family"] for row in record["bindings"]["current_candidates"]] == list(tool.FAMILIES)
    candidate_rows = {
        row["family"]: row for row in record["bindings"]["current_candidates"]
    }
    assert tool.CURRENT_CANDIDATE_STAGES["I1"] in candidate_rows["I1"]["path"]
    assert candidate_rows["I1"]["candidate_id"] == (
        "ab3f9b96856d3c8e41b30d96ac8c1291dad5a71abe7d68d95d40d2f83ff07e66"
    )
    assert candidate_rows["I1"]["file_sha256"] == (
        "0a263650a98213f5b45e2a4cd5f5ba90fec96c6ac2731b3ebc39dc7ef285865f"
    )
    assert all(
        tool.CURRENT_CANDIDATE_STAGES[family] in candidate_rows[family]["path"]
        for family in tool.FAMILIES
    )
    tool.validate_completion_record(root, record)
    assert record["bindings"]["baseline"]["entry_count"] == 0
    assert record["bindings"]["ledger"]["entry_count"] == 0
    assert record["bindings"]["declared_loss"]["collect"]["item_count"] == 1
    assert record["bindings"]["declared_loss"]["ingest"]["item_count"] == 1


def test_hardened_v4_contracts_fail_closed(tmp_path: Path) -> None:
    root = mixed_root(tmp_path)
    record = tool.build_completion_record(root, evidence())
    tool.validate_completion_record(root, record)

    payload = evidence()
    payload["negative_findings"][0]["status"] = "PASS"
    with pytest.raises(tool.CompletionError, match="must not be marked PASS"):
        tool.build_completion_record(root, payload)

    payload = evidence()
    payload["current_byte_rebind"]["candidate_stages"]["I1"] = "stage-b19-2026-09-05"
    with pytest.raises(
        tool.CompletionError,
        match="candidate_stages must be exactly the current nine-family mapping",
    ):
        tool.build_completion_record(root, payload)

    payload = evidence()
    payload["current_byte_rebind"]["candidate_stages"]["C10"] = "stage-b19-2026-09-05"
    with pytest.raises(
        tool.CompletionError,
        match="candidate_stages must be exactly the current nine-family mapping",
    ):
        tool.build_completion_record(root, payload)

    payload = evidence()
    payload["commands"]["root"][0]["command"] = "unreviewed command"
    with pytest.raises(
        tool.CompletionError,
        match="command identity drifted from the Stage 0 contract",
    ):
        tool.build_completion_record(root, payload)

    payload = evidence()
    del payload["commands"]["root"][-1]
    with pytest.raises(
        tool.CompletionError,
        match="row count drifted from the Stage 0 contract",
    ):
        tool.build_completion_record(root, payload)

    payload = evidence()
    payload["commands"]["root"][0]["observed"] = "730 passed; 53 subtests; 2 warnings"
    with pytest.raises(
        tool.CompletionError,
        match="observed summary drifted from the Stage 0 contract",
    ):
        tool.build_completion_record(root, payload)

    drifted_receipt_record = tool.build_completion_record(root, evidence())
    receipt = root / tool.COMMAND_CONTRACTS["root"][0]["receipt_path"]
    receipt_bytes = receipt.read_bytes().replace(b"729 passed", b"730 passed")
    receipt.write_bytes(receipt_bytes)
    drifted_receipt_record["commands"]["root"][0]["receipt"]["sha256"] = (
        tool.sha256_bytes(receipt_bytes)
    )
    try:
        with pytest.raises(
            tool.CompletionError,
            match="root receipt counts drift from observed summary",
        ):
            tool.validate_completion_record(root, drifted_receipt_record)
    finally:
        receipt.write_bytes(receipt_bytes.replace(b"730 passed", b"729 passed"))

    authority_record = tool.build_completion_record(root, evidence())
    authority_record["bindings"]["current_candidates"][0]["status"] = "PRODUCTION_AUTHORITY"
    with pytest.raises(
        tool.CompletionError,
        match="byte, identity, status, or non-authority binding drift",
    ):
        tool.validate_completion_record(root, authority_record)

    freeze_raw = (root / tool.PLAN_FREEZE_REL).read_bytes()
    freeze = json.loads(freeze_raw)
    try:
        freeze["schema_version"] = "fixture.v1"
        _write_json(root / tool.PLAN_FREEZE_REL, freeze)
        with pytest.raises(
            tool.CompletionError,
            match="freeze schema_version drift",
        ):
            tool.build_completion_record(root, evidence())

        freeze = json.loads(freeze_raw)
        freeze["frozen_files"][0]["bytes"] += 1
        _write_json(root / tool.PLAN_FREEZE_REL, freeze)
        with pytest.raises(
            tool.CompletionError,
            match="byte count drift",
        ):
            tool.build_completion_record(root, evidence())

        freeze = json.loads(freeze_raw)
        freeze["frozen_files"][0]["lines"] += 1
        _write_json(root / tool.PLAN_FREEZE_REL, freeze)
        with pytest.raises(
            tool.CompletionError,
            match="line count drift",
        ):
            tool.build_completion_record(root, evidence())
    finally:
        (root / tool.PLAN_FREEZE_REL).write_bytes(freeze_raw)

    wrong_path = tool.build_completion_record(root, evidence())
    wrong_path["bindings"]["stage_plan"]["path"] = "04_plan.md"
    with pytest.raises(tool.CompletionError, match="stage plan binding drift"):
        tool.validate_completion_record(root, wrong_path)

    wrong_freeze = tool.build_completion_record(root, evidence())
    wrong_freeze["bindings"]["stage_plan_freeze"]["schema_version"] = "fixture.v1"
    with pytest.raises(tool.CompletionError, match="stage_plan_freeze binding drift"):
        tool.validate_completion_record(root, wrong_freeze)

    tool.validate_completion_record(root, record)


def negative_finding() -> dict[str, object]:
    return {
        "classification": "EXCLUDED_NON_STAGE0_RUNTIME_DEPENDENCY",
        "observed_result": "FAIL",
        "owner": "upstream-kit",
        "reason": "upstream default-feature compile failure retained",
        "test": "upstream rust cargo test",
        "evidence": {
            "path": "negative-finding-receipt.txt",
            "sha256": RECEIPT_SHA,
        },
        "stage0_dependency": False,
    }


def test_receipt_failure_signals_fail_closed_even_with_passed_summary() -> None:
    failure_logs = [
        "729 passed, 2 warnings in 1.00s\n1 failed in 0.01s\n",
        "85 passed\n2 failed\n1 did not run\n",
        "1645 passed\n1 error in 0.01s\n",
        "=========== 1 failed, 85 passed in 0.01s ===========\n",
        "npm ERR! Lifecycle script `lint` failed\n",
        "npm error Missing script: lint\n",
        "main.ts(1,7): error TS2322: Type mismatch\n",
        "src/app.tsx\n  1:1  error  Unexpected token\n",
        "error during build:\nTypeError: invalid input\n",
        "Traceback (most recent call last):\n  File...\n",
        "Process exited with exit code 1\n",
        "Process killed\n",
        "EXIT=1\n",
        "SIGKILL\n",
    ]
    for text in failure_logs:
        with pytest.raises(tool.CompletionError, match="failure signal"):
            tool._validate_receipt_failure_signals(text)

    harmless_logs = [
        "85 passed\n12 skipped\n",
        "0 failed, 85 passed in 1.00s\n",
        "No errors found.\n",
        "derive maps client error to FAILED\n",
        "Process exited with exit code 0\n",
        "PG_MATRIX_RESULT failed_shards=0 failures=0 errors=0\n",
    ]
    for text in harmless_logs:
        tool._validate_receipt_failure_signals(text)


def test_reviewer_receipt_append_and_collusive_refreeze_fail_closed(
    tmp_path: Path,
) -> None:
    root = mixed_root(tmp_path)
    record = tool.build_completion_record(root, evidence())

    receipt_relative = tool.COMMAND_CONTRACTS["root"][0]["receipt_path"]
    receipt = root / receipt_relative
    receipt_bytes = receipt.read_bytes() + b"1 failed in 0.01s\n"
    receipt.write_bytes(receipt_bytes)
    record["commands"]["root"][0]["receipt"]["sha256"] = tool.sha256_bytes(
        receipt_bytes
    )
    with pytest.raises(
        tool.CompletionError,
        match="receipt log contains a failure signal: 1 failed",
    ):
        tool.validate_completion_record(root, record)

    plan_raw = (root / tool.PLAN_REL).read_bytes() + b"collusive amendment\n"
    (root / tool.PLAN_REL).write_bytes(plan_raw)
    freeze = tool._load(root, tool.PLAN_FREEZE_REL)
    freeze["frozen_files"][0] = {
        "path": tool.PLAN_REL.as_posix(),
        "sha256": tool.sha256_bytes(plan_raw),
        "bytes": len(plan_raw),
        "lines": len(plan_raw.splitlines()),
    }
    _write_json(root / tool.PLAN_FREEZE_REL, freeze)
    receipt.write_bytes(receipt_bytes.removesuffix(b"1 failed in 0.01s\n"))
    record["commands"]["root"][0]["receipt"]["sha256"] = tool.sha256_bytes(
        receipt.read_bytes()
    )
    record["bindings"]["stage_plan"]["sha256"] = tool.sha256_bytes(plan_raw)
    record["bindings"]["stage_plan_freeze"]["sha256"] = tool.sha256_bytes(
        (root / tool.PLAN_FREEZE_REL).read_bytes()
    )
    with pytest.raises(
        tool.CompletionError,
        match="module-pinned SHA256/bytes/lines contract",
    ):
        tool.validate_completion_record(root, record)

def test_non_pass_command_fails_closed(tmp_path: Path) -> None:
    payload = evidence()
    payload["commands"]["root"][0]["result"] = "BLOCKED"
    root = mixed_root(tmp_path)
    with pytest.raises(tool.CompletionError, match="non-PASS"):
        tool.build_completion_record(root, payload)


def test_command_exit_code_and_receipt_fail_closed(tmp_path: Path) -> None:
    payload = evidence()
    payload["commands"]["root"][0]["exit_code"] = 99
    with pytest.raises(tool.CompletionError, match="exit_code 0"):
        tool.build_completion_record(mixed_root(tmp_path), payload)

    payload = evidence()
    payload["commands"]["root"][0]["receipt"]["sha256"] = "0" * 64
    with pytest.raises(tool.CompletionError, match="receipt sha256 drift"):
        tool.build_completion_record(mixed_root(tmp_path), payload)

    root = mixed_root(tmp_path)
    record = tool.build_completion_record(root, evidence())
    receipt_relative = tool.COMMAND_CONTRACTS["root"][0]["receipt_path"]
    (root / receipt_relative).write_bytes(b"drift\n")
    with pytest.raises(tool.CompletionError, match="receipt sha256 drift"):
        tool.validate_completion_record(root, record)


def test_command_receipt_path_contract_and_symlink_fail_closed(tmp_path: Path) -> None:
    root = mixed_root(tmp_path)
    payload = evidence()
    row = payload["commands"]["root"][0]
    row["receipt"]["path"] = "stage0-command-receipt.txt"
    with pytest.raises(
        tool.CompletionError,
        match="receipt path drifted from the Stage 0 contract",
    ):
        tool.build_completion_record(root, payload)

    linked = mixed_root(tmp_path / "symlink")
    receipt = linked / tool.COMMAND_CONTRACTS["root"][0]["receipt_path"]
    receipt.unlink()
    receipt.symlink_to("missing-target")
    with pytest.raises(tool.CompletionError, match="required input missing"):
        tool.build_completion_record(linked, evidence())


def test_legacy_b19_evidence_fails_closed(tmp_path: Path) -> None:
    payload = evidence()
    payload["b19"] = payload["current_byte_rebind"]
    del payload["current_byte_rebind"]
    with pytest.raises(
        tool.CompletionError, match="legacy b19 evidence key is rejected"
    ):
        tool.build_completion_record(mixed_root(tmp_path), payload)


def test_unbound_negative_and_skip_fail_closed(tmp_path: Path) -> None:
    root = mixed_root(tmp_path)
    payload = evidence()
    payload["negative_findings"] = [
        {
            "id": "N1",
            "classification": "EXCLUDED_NON_STAGE0_RUNTIME_DEPENDENCY",
            "observed_result": "FAIL",
        }
    ]
    with pytest.raises(tool.CompletionError, match="unowned"):
        tool.build_completion_record(root, payload)

    payload = evidence()
    payload["skip_block"] = [{"classification": "SKIP", "owner": "lane", "reason": "fixture"}]
    with pytest.raises(tool.CompletionError, match="SKIP/BLOCKED"):
        tool.build_completion_record(root, payload)


def test_negative_finding_binding_structure_and_receipt_fail_closed(tmp_path: Path) -> None:
    root = mixed_root(tmp_path)
    payload = evidence()
    payload["negative_findings"] = []
    with pytest.raises(
        tool.CompletionError,
        match="negative finding count drift from bound evidence",
    ):
        tool.build_completion_record(root, payload)

    payload = evidence()
    payload["negative_findings"][0]["result"] = "PASS"
    with pytest.raises(
        tool.CompletionError,
        match="must not be marked PASS",
    ):
        tool.build_completion_record(root, payload)

    payload = evidence()
    payload["negative_findings"][0]["owner"] = "unbound-owner"
    with pytest.raises(
        tool.CompletionError,
        match="owner drift from bound frontend full E2E evidence",
    ):
        tool.build_completion_record(root, payload)

    payload = evidence()
    payload["negative_findings"][0]["test"] = "unbound.test"
    with pytest.raises(
        tool.CompletionError,
        match="outside the bound frontend full E2E set",
    ):
        tool.build_completion_record(root, payload)

    payload = evidence()
    payload["negative_findings"][0]["reason"] = "arbitrary PASS prose"
    with pytest.raises(
        tool.CompletionError,
        match="completion reason drift",
    ):
        tool.build_completion_record(root, payload)

    payload = evidence()
    payload["negative_findings"][0]["observed_result"] = "PASS"
    with pytest.raises(
        tool.CompletionError,
        match="must preserve observed_result FAIL",
    ):
        tool.build_completion_record(root, payload)

    payload = evidence()
    payload["negative_findings"][0]["stage0_dependency"] = True
    with pytest.raises(
        tool.CompletionError,
        match="stage0_dependency false",
    ):
        tool.build_completion_record(root, payload)

    payload = evidence()
    payload["negative_findings"][0]["evidence"]["sha256"] = "0" * 64
    with pytest.raises(
        tool.CompletionError,
        match="negative finding evidence sha256 drift",
    ):
        tool.build_completion_record(root, payload)

    payload = evidence()
    payload["negative_findings"][0]["evidence"]["path"] = "negative-finding-receipt.txt"
    payload["negative_findings"][0]["evidence"]["sha256"] = tool.sha256_bytes(
        (ROOT / tool.FRONTEND_FULL_E2E_NEGATIVE_REL).read_bytes()
    )
    bound_record = tool.build_completion_record(root, evidence())
    bound_record["negative_findings"][0]["evidence"]["path"] = "negative-finding-receipt.txt"
    with pytest.raises(
        tool.CompletionError,
        match="negative finding evidence binding drifted",
    ):
        tool.validate_completion_record(root, bound_record)

    record = tool.build_completion_record(root, evidence())
    record["negative_findings"][0]["evidence"]["sha256"] = "0" * 64
    with pytest.raises(tool.CompletionError, match="evidence sha256 drift"):
        tool.validate_completion_record(root, record)


def test_baseline_and_ledger_counts_recomputed(tmp_path: Path) -> None:
    root = mixed_root(tmp_path)
    record = tool.build_completion_record(root, evidence())
    record["bindings"]["baseline"]["entry_count"] = 7
    with pytest.raises(tool.CompletionError, match="baseline entry_count drift"):
        tool.validate_completion_record(root, record)

    record = tool.build_completion_record(root, evidence())
    record["bindings"]["ledger"]["entry_count"] = 727
    with pytest.raises(tool.CompletionError, match="ledger entry_count drift"):
        tool.validate_completion_record(root, record)


def test_kit_claim_scope_and_derived_summary_fail_closed(tmp_path: Path) -> None:
    root = mixed_root(tmp_path)
    payload = evidence()
    payload["kit"] = {"result": "PASS", "scope": {"stage": "0"}}
    with pytest.raises(tool.CompletionError, match="may only declare result PASS"):
        tool.build_completion_record(root, payload)

    record = tool.build_completion_record(root, evidence())
    record["kit"]["languages"]["rust"]["ceiling"] = "ARBITRARY"
    with pytest.raises(tool.CompletionError, match="derived kit summary drift"):
        tool.validate_completion_record(root, record)

    kit = tool._load(root, tool.KIT_REL)
    kit["status"] = "PASS"
    _write_json(root / tool.KIT_REL, kit)
    with pytest.raises(tool.CompletionError, match="consumer gate is not closed"):
        tool.build_completion_record(root, evidence())


def test_validator_rejects_v1_schema(tmp_path: Path) -> None:
    root = mixed_root(tmp_path)
    record = tool.build_completion_record(root, evidence())
    record["schema"] = "mrw.formal_release.stage0.functorial_refactor_completion.v1"
    record["schema_version"] = "mrw.stage0.functorial-refactor-completion.v1"
    record["record_id"] = "stage0-functorial-refactor-completion-v1"
    with pytest.raises(tool.CompletionError, match="unexpected completion record schema"):
        tool.validate_completion_record(root, record)


def test_candidate_byte_drift_fails_closed(tmp_path: Path) -> None:
    payload = evidence()
    root = mixed_root(tmp_path)
    candidate = ROOT / tool._candidate_relative(ROOT, "C2")
    drifted = tmp_path / "candidate.v2.json"
    drifted.write_bytes(candidate.read_bytes() + b"\n")
    # Validate the record against its isolated root after changing the binding: a
    # stale digest is rejected without touching any repository file.
    record = tool.build_completion_record(root, payload)
    record["bindings"]["current_candidates"][0]["file_sha256"] = "0" * 64
    with pytest.raises(
        tool.CompletionError,
        match="byte, identity, status, or non-authority binding drift",
    ):
        tool.validate_completion_record(root, record)


def test_create_only_refuses_existing_target(tmp_path: Path) -> None:
    root = mixed_root(tmp_path)
    record = tool.build_completion_record(root, evidence())
    output = root / "completion.json"
    output.write_text("existing\n", encoding="utf-8")
    with pytest.raises(tool.CompletionError, match="create-only"):
        tool.write_create_only(root, record, root / "completion.json")


def test_serialized_record_is_deterministic(tmp_path: Path) -> None:
    root = mixed_root(tmp_path)
    first = tool.build_completion_record(root, evidence())
    second = tool.build_completion_record(root, evidence())
    assert json.dumps(first, ensure_ascii=True, indent=2, sort_keys=True) == json.dumps(
        second, ensure_ascii=True, indent=2, sort_keys=True
    )


def test_governance_map_rejects_stale_current_candidate_stage() -> None:
    authority = tool._load(ROOT, tool.MAP_RELS[1])
    drifted = copy.deepcopy(authority)
    projection = next(
        item
        for item in drifted["priority_order"]
        if item["surface"]
        == "shared successor family fragment registration projection"
    )["shared_family_projection"]
    projection["rows"][0]["candidate_path"] = projection["rows"][0][
        "candidate_path"
    ].replace("stage-b19-2026-09-05", "stage-b18-2026-09-05")

    with pytest.raises(
        tool.CompletionError, match="C2 reference does not use"
    ):
        tool._validate_map_candidate_refs(
            ROOT,
            drifted,
            tool.MAP_RELS[1],
            tool.CURRENT_CANDIDATE_STAGES,
        )


def test_mixed_root_governance_map_rejects_stale_i1_b19(tmp_path: Path) -> None:
    root = mixed_root(tmp_path)
    authority = tool._load(root, tool.MAP_RELS[1])
    projection = authority["priority_order"][0]["shared_family_projection"]
    i1 = next(row for row in projection["rows"] if row["family"] == "I1")
    i1["candidate_path"] = i1["candidate_path"].replace(
        tool.CURRENT_CANDIDATE_STAGES["I1"], "stage-b19-2026-09-05"
    )
    with pytest.raises(tool.CompletionError, match="I1 reference does not use"):
        tool._validate_map_candidate_refs(
            root,
            authority,
            tool.MAP_RELS[1],
            tool.CURRENT_CANDIDATE_STAGES,
        )


def test_mixed_root_rejects_declared_i1_stage_drift(tmp_path: Path) -> None:
    root = mixed_root(tmp_path)
    authority = tool._load(root, tool.MAP_RELS[1])
    projection = authority["priority_order"][0]["shared_family_projection"]
    i1 = next(row for row in projection["rows"] if row["family"] == "I1")
    i1["stage"] = "stage-b19-2026-09-05"
    with pytest.raises(tool.CompletionError, match="I1 stage drift"):
        tool._validate_map_candidate_refs(
            root,
            authority,
            tool.MAP_RELS[1],
            tool.CURRENT_CANDIDATE_STAGES,
        )


def test_candidate_stages_reject_complete_b18_history_without_current(
    tmp_path: Path,
) -> None:
    b18 = tool.CANDIDATE_ROOT_PARENT_REL / "stage-b18-2026-09-05/candidates"
    for family in tool.FAMILIES:
        candidate = tmp_path / b18 / family / "candidate.v2.json"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text("{}\n", encoding="utf-8")

    with pytest.raises(tool.CompletionError, match="C2=stage-b19-2026-09-05"):
        tool._candidate_stages(tmp_path)


def test_candidate_stages_reject_i1_stale_b19(tmp_path: Path) -> None:
    root = mixed_root(tmp_path)
    (root / tool._candidate_relative(root, "I1")).unlink()
    stale_b19 = (
        root
        / tool.CANDIDATE_ROOT_PARENT_REL
        / "stage-b19-2026-09-05/candidates/I1/candidate.v2.json"
    )
    stale_b19.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / stale_b19.relative_to(root), stale_b19)

    with pytest.raises(
        tool.CompletionError,
        match=f"I1={tool.CURRENT_CANDIDATE_STAGES['I1']}",
    ):
        tool._candidate_stages(root)


def test_candidate_stages_reject_missing_family(tmp_path: Path) -> None:
    root = mixed_root(tmp_path)
    (root / tool._candidate_relative(root, "C3")).unlink()
    with pytest.raises(tool.CompletionError, match="C3=stage-b19-2026-09-05"):
        tool._candidate_stages(root)


def test_validator_rejects_legacy_unified_stage_binding(tmp_path: Path) -> None:
    root = mixed_root(tmp_path)
    record = tool.build_completion_record(root, evidence())
    record["bindings"]["candidate_stage"] = "stage-b19-2026-09-05"
    del record["bindings"]["candidate_stages"]
    with pytest.raises(
        tool.CompletionError, match="legacy unified candidate_stage"
    ):
        tool.validate_completion_record(root, record)


def test_validator_rejects_legacy_b19_record(tmp_path: Path) -> None:
    root = mixed_root(tmp_path)
    record = tool.build_completion_record(root, evidence())
    record["b19"] = record["current_byte_rebind"]
    del record["current_byte_rebind"]
    with pytest.raises(
        tool.CompletionError, match="legacy b19 evidence key is rejected"
    ):
        tool.validate_completion_record(root, record)


def test_checker_cli_passes_mixed_lineage_and_fails_stage_drift(
    tmp_path: Path,
) -> None:
    root = mixed_root(tmp_path)
    record = tool.build_completion_record(root, evidence())
    record_path = root / "completion.json"
    tool.write_create_only(root, record, record_path)
    checker = ROOT / "scripts/formal_release/check_stage0_completion.py"

    passed = subprocess.run(
        [sys.executable, checker.as_posix(), record_path.as_posix(), "--repo-root", root.as_posix()],
        capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        check=False,
    )
    assert passed.returncode == 0
    assert passed.stdout.strip() == "PASS"

    drifted = copy.deepcopy(record)
    drifted["bindings"]["candidate_stages"]["I1"] = "stage-b19-2026-09-05"
    drifted_path = root / "drifted.json"
    drifted_path.write_text(json.dumps(drifted), encoding="utf-8")
    failed = subprocess.run(
        [sys.executable, checker.as_posix(), drifted_path.as_posix(), "--repo-root", root.as_posix()],
        capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        check=False,
    )
    assert failed.returncode == 1
    assert "current candidate stage drift" in failed.stderr
