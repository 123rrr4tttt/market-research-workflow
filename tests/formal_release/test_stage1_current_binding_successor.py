from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from scripts.formal_release import generate_stage1_current_binding_successor as tool
from scripts.formal_release import generate_stage1_production_contract_record as stage1


ROOT = Path(__file__).resolve().parents[2]


def _copy(root: Path, relative: Path | str) -> None:
    relative = Path(relative)
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / relative, destination)


def successor_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "source-root"
    root.mkdir()
    historical_path = stage1.OUTPUT_REL
    historical = json.loads((ROOT / historical_path).read_text(encoding="utf-8"))
    fixed = {
        stage1.PLAN_REL,
        stage1.PLAN_FREEZE_REL,
        stage1.STAGE0_COMPLETION_REL,
        historical_path,
        *tool.EXECUTION_CONTRACT_RELS,
        *tool.IMPLEMENTATION_RELS,
        *stage1.SOURCE_RELS,
        *stage1.CONFIGURATION_RELS,
        *stage1.WORKFLOW_RELS,
        *stage1.MIGRATION_RELS,
    }
    fixed.update(stage1._api_rels(ROOT))
    fixed.update(stage1._migration_rels(ROOT))
    fixed.update(
        Path(command["receipt"]["path"])
        for command in historical["commands"].values()
    )
    for relative in sorted(fixed, key=lambda path: path.as_posix()):
        _copy(root, relative)
    return root


def test_build_validates_all_historical_and_current_bindings(tmp_path: Path) -> None:
    root = successor_fixture(tmp_path)
    record = tool.build_successor_record(root, "2026-09-09T00:00:00Z")

    assert record["schema"] == "mrw.stage1.production-contract-binding-successor.v1"
    assert record["predecessor"]["sha256"] == tool.HISTORICAL_RECORD_SHA256
    assert len(record["historical_receipts"]) == 11
    assert {
        receipt["role"] for receipt in record["historical_receipts"]
    } == {"HISTORICAL_ONLY_NOT_FRESH"}
    assert record["historical_binding_coverage"] == {
        "historical_non_receipt_binding_count": 149,
        "historical_receipt_binding_count": 11,
        "historical_total_binding_count": 160,
        "removed_paths": [],
        "removed_count": 0,
        "additive_current_paths": record["historical_binding_coverage"][
            "additive_current_paths"
        ],
        "additive_current_count": len(
            record["historical_binding_coverage"]["additive_current_paths"]
        ),
    }
    assert [row["path"] for row in record["execution_contracts"]] == [
        path.as_posix() for path in tool.EXECUTION_CONTRACT_RELS
    ]
    by_relation = {
        relation: [row for row in record["current_bindings"] if row["relation"] == relation]
        for relation in (
            "IDENTITY",
            "CURRENT_BYTE_SUCCESSOR",
            "ADDITIVE_CURRENT_REQUIREMENT",
        )
    }
    assert all(by_relation.values())
    assert all(
        row["predecessor_sha256"] and row["historical_pointer"]
        for relation in ("IDENTITY", "CURRENT_BYTE_SUCCESSOR")
        for row in by_relation[relation]
    )
    assert all(
        row["predecessor_sha256"] is None and row["historical_pointer"] is None
        for row in by_relation["ADDITIVE_CURRENT_REQUIREMENT"]
    )
    assert tool.validate_successor_record(root, record) == {
        "current_mismatch_count": 0,
        "file_count": record["current_required_files_summary"]["file_count"],
        "historical_receipt_count": 11,
        "projected_candidate_mismatch_count": 0,
        "removed_count": 0,
    }


def test_builder_uses_explicit_source_root(tmp_path: Path) -> None:
    root = successor_fixture(tmp_path)
    relative = Path("main/backend/.env.example")
    (root / relative).write_bytes(b"fixture-only-current-bytes\n")

    record = tool.build_successor_record(root, "2026-09-09T00:00:00Z")
    binding = next(
        row
        for row in record["current_required_files"]["configuration"]
        if row["path"] == relative.as_posix()
    )
    assert binding["sha256"] == stage1.sha256_bytes((root / relative).read_bytes())
    assert binding["sha256"] != stage1.sha256_bytes((ROOT / relative).read_bytes())


def test_historical_hash_tamper_fails_closed(tmp_path: Path) -> None:
    root = successor_fixture(tmp_path)
    path = root / stage1.OUTPUT_REL
    path.write_bytes(path.read_bytes() + b" ")

    with pytest.raises(stage1.Stage1RecordError, match="historical Stage1 record identity"):
        tool.build_successor_record(root, "2026-09-09T00:00:00Z")


def test_historical_receipt_count_must_be_exactly_eleven(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = successor_fixture(tmp_path)
    path = root / stage1.OUTPUT_REL
    historical = json.loads(path.read_text(encoding="utf-8"))
    historical["commands"].pop(next(iter(historical["commands"])))
    raw = (json.dumps(historical, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(raw)
    monkeypatch.setattr(tool, "HISTORICAL_RECORD_SHA256", stage1.sha256_bytes(raw))
    monkeypatch.setattr(tool, "HISTORICAL_RECORD_BYTES", len(raw))

    with pytest.raises(stage1.Stage1RecordError, match="exactly 11"):
        tool.build_successor_record(root, "2026-09-09T00:00:00Z")


def test_historical_required_path_deletion_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = successor_fixture(tmp_path)
    removed = Path("main/backend/app/release_identity.py")
    monkeypatch.setattr(
        stage1,
        "SOURCE_RELS",
        tuple(path for path in stage1.SOURCE_RELS if path != removed),
    )

    with pytest.raises(stage1.Stage1RecordError, match="required-file path removed"):
        tool.build_successor_record(root, "2026-09-09T00:00:00Z")


def test_current_inventory_must_be_stable_across_two_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = successor_fixture(tmp_path)
    real_manifest = stage1._manifest
    first = real_manifest(root)
    second = copy.deepcopy(first)
    second["configuration"][0]["sha256"] = "0" * 64
    calls = iter((first, second))
    monkeypatch.setattr(stage1, "_manifest", lambda _root: next(calls))

    with pytest.raises(stage1.Stage1RecordError, match="changed during construction"):
        tool.build_successor_record(root, "2026-09-09T00:00:00Z")


def test_successor_authority_and_create_only_are_fail_closed(tmp_path: Path) -> None:
    root = successor_fixture(tmp_path)
    record = tool.build_successor_record(root, "2026-09-09T00:00:00Z")
    expanded = copy.deepcopy(record)
    expanded["authority"][stage1.AUTHORITY_KEYS[0]] = True
    with pytest.raises(stage1.Stage1RecordError, match="authority ceiling expanded"):
        tool.validate_successor_record(root, expanded)

    destination = tool.write_successor_create_only(root, record)
    assert destination == root / tool.OUTPUT_REL
    artifact_manifest = json.loads(
        (root / tool.ARTIFACT_MANIFEST_REL).read_text(encoding="utf-8")
    )
    assert [row["path"] for row in artifact_manifest["implementation"]] == [
        path.as_posix() for path in tool.IMPLEMENTATION_RELS
    ]
    assert tool.validate_bundle(root, record)["current_mismatch_count"] == 0
    with pytest.raises(stage1.Stage1RecordError, match="create-only target already exists"):
        tool.write_successor_create_only(root, record)


def test_bundle_rejects_record_byte_drift_without_json_change(tmp_path: Path) -> None:
    root = successor_fixture(tmp_path)
    record = tool.build_successor_record(root, "2026-09-09T00:00:00Z")
    path = tool.write_successor_create_only(root, record)
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(stage1.Stage1RecordError, match="record bytes differ"):
        tool.validate_bundle(root, record)
