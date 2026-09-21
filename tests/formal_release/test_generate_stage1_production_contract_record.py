from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
from typing import Annotated, Any, get_args, get_origin, get_type_hints

import pytest
import shlex


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/formal_release/generate_stage1_production_contract_record.py"
CHECKER_SCRIPT = ROOT / "scripts/formal_release/check_stage1_production_contract_record.py"
SPEC = importlib.util.spec_from_file_location("stage1_production_contract_record", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tool)

CHECKER_SPEC = importlib.util.spec_from_file_location(
    "stage1_production_contract_record_checker", CHECKER_SCRIPT
)
assert CHECKER_SPEC is not None and CHECKER_SPEC.loader is not None
checker = importlib.util.module_from_spec(CHECKER_SPEC)
CHECKER_SPEC.loader.exec_module(checker)

FORMAL_DIR = tool.FORMAL_RELEASE_DIR
OUTPUT = FORMAL_DIR / "stage1-evidence/production-contract-implementation.v1.json"


def _receipt_bytes(command_id: str) -> bytes:
    if command_id == "resource_cleanup":
        return (tool.RESOURCE_CLEANUP_SUMMARY + "\n").encode("utf-8")
    if command_id == "workflow_contract":
        return b"workflow contract\nall required workflow categories present\n"
    return b"command receipt\nall selected checks passed\n"


def _summary(command_id: str) -> str:
    return {
        "r3_direct": "static production contract PASS",
        "focused_backend_stage1": "41 passed",
        "migration_single_head": "single head: 20260905_000001; revisions: 43",
        "compose_config_dev": "configuration valid: dev",
        "compose_config_production": "configuration valid: production",
        "frontend_lint": "lint passed; 0 errors",
        "frontend_typecheck": "typecheck passed; 0 errors",
        "frontend_build": "build succeeded",
        "workflow_contract": "all required workflow categories present",
        "architecture_gate": "285 passed",
        "resource_cleanup": tool.RESOURCE_CLEANUP_SUMMARY,
    }[command_id]


def _cleanup_command(run_id: str = "0123456789abcdef") -> str:
    return (
        f"STAGE1_TEMP_ROOT=/private/tmp/stage1-contract-record-{run_id} "
        "main/backend/.venv311/bin/python -c "
        f"'{tool.RESOURCE_CLEANUP_PROGRAM}'"
    )


def evidence() -> dict[str, object]:
    commands: dict[str, object] = {}
    for contract in tool.COMMAND_CONTRACTS:
        command_id = contract["id"]
        receipt_bytes = _receipt_bytes(command_id)
        commands[command_id] = {
            "command": (
                _cleanup_command()
                if command_id == "resource_cleanup"
                else contract["command"]
            ),
            "result": "PASS",
            "exit_code": 0,
            "summary": _summary(command_id),
            "receipt": {
                "path": f"stage1-receipts/{command_id}.log",
                "sha256": hashlib.sha256(receipt_bytes).hexdigest(),
            },
        }
    return {
        "observed_at": "2026-09-05T12:00:00+00:00",
        "commands": commands,
        "known_gaps": [
            {
                "id": "runtime-drill",
                "stage_floor": "STAGE_5",
                "owner": "stage5-runtime",
                "reason": "real backup/restore and rollback drills remain outside Stage1",
                "status": "RETAINED_LATER_STAGE",
            }
        ],
    }


def test_stage1_record_return_has_exact_non_authority_metadata() -> None:
    return_hint = get_type_hints(tool.build_stage1_record, include_extras=True)["return"]
    assert get_origin(return_hint) is Annotated
    value, metadata = get_args(return_hint)
    assert value == dict[str, Any]
    tokens = shlex.split(metadata)
    assert tokens[0] == "kit:non-authoritative"
    fields = dict(token.split("=", 1) for token in tokens[1:])
    assert fields == {
        "derived_as": "evidence",
        "fact_source": "stage_plan_freeze+stage0_completion+command_receipts+file_manifest",
        "witness": "test:test_build_validate_create_only_and_exact_rebuild",
    }


def stage1_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for relative in (
        tool.PLAN_REL,
        tool.PLAN_FREEZE_REL,
        tool.STAGE0_COMPLETION_REL,

        *tool.SOURCE_RELS,
        *tool.CONFIGURATION_RELS,
        *tool.WORKFLOW_RELS,
        *tool.MIGRATION_RELS,
    ):
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if relative in {tool.PLAN_REL, tool.PLAN_FREEZE_REL, tool.STAGE0_COMPLETION_REL}:
            shutil.copyfile(ROOT / relative, destination)
        else:
            destination.write_bytes(f"stable fixture: {relative.as_posix()}\n".encode())

    for name in ("root_a.py", "root_b.py", tool.MIGRATION_MERGE_REL.name):
        destination = root / tool.MIGRATION_VERSIONS_DIR / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            'revision = "20260905_000001"\ndown_revision = None\n', encoding="utf-8"
        )
    classified_api = root / "main/backend/app/api/health.py"
    classified_api.parent.mkdir(parents=True, exist_ok=True)
    classified_api.write_text("# installed API fixture\n", encoding="utf-8")

    receipts = root / "stage1-receipts"
    receipts.mkdir()
    for contract in tool.COMMAND_CONTRACTS:
        command_id = contract["id"]
        (receipts / f"{command_id}.log").write_bytes(_receipt_bytes(command_id))
    return root


def test_build_validate_create_only_and_exact_rebuild(tmp_path: Path) -> None:
    root = stage1_fixture(tmp_path)
    assert not (root / OUTPUT).exists()
    record = tool.build_stage1_record(root, evidence())
    assert record["authoritative"] is False
    assert record["derived_as"] == "evidence"
    assert record["status"] == "PRODUCTION_CONTRACT_IMPLEMENTED_NOT_AUTHORITY"
    assert record["candidate_commit"] is None
    assert record["candidate_tree"] is None
    assert record["candidate"] == {"commit": None, "tree": None}
    assert set(record["commands"]) == {
        "r3_direct",
        "focused_backend_stage1",
        "migration_single_head",
        "compose_config_dev",
        "compose_config_production",
        "frontend_lint",
        "frontend_typecheck",
        "frontend_build",
        "workflow_contract",
        "architecture_gate",
        "resource_cleanup",
    }
    assert len(record["bindings"]["required_files"]["migration"]) > 3
    source_paths = {
        row["path"]
        for row in record["bindings"]["required_files"]["source"]
    }
    for required in (
        "functorial-kit.json",
        "sketches.json",
        "registries/failures.json",
        "main/backend/app/api/__init__.py",
        "main/backend/app/api/agent_chat.py",
        "main/backend/app/api/codex_auth.py",
        "main/backend/app/composition/production.py",
        "main/backend/app/composition/production_runtime.py",
        "main/backend/app/composition/production_route_bindings.json",
        "scripts/materialize_functorial_kit_consumer_gate.py",
        "tools/functorial-kit/consumer-gate.manifest.json",
        "tools/functorial-kit/consumer-gate.patch",
        "tests/formal_release/test_functorial_kit_consumer_gate.py",
        "main/backend/app/main.py",
        "main/backend/app/services/codex_oauth.py",
        "main/backend/app/services/request_identity.py",
        "main/backend/app/settings/config.py",
        "main/backend/app/production_observability/__init__.py",
        "main/backend/tests/production_composition/test_production_composition.py",
        "main/backend/tests/production_composition/test_production_auth_bootstrap.py",
        "main/backend/tests/production_composition/test_production_runtime_bindings.py",
        "main/backend/tests/production_composition/test_production_stream_observation.py",
        "main/backend/tests/production_composition/test_route_effect_contract.py",
        "main/backend/tests/production_composition/test_s1_operation_authority_adapters.py",
        "main/backend/tests/production_observability/test_r7_failclosed_hardening_unittest.py",
        "main/ops/rollback.sh",
        "main/backend/tests/ops_production_contract/test_rollback_adapter.py",
        "tests/formal_release/test_s1_workflow_contract.py",
        "tests/formal_release/test_s1_production_compose_contract.py",
    ):
        assert required in source_paths
    assert "main/backend/app/api/health.py" in source_paths
    assert "main/ops/docker-compose.production.yml" in {
        row["path"] for row in record["bindings"]["required_files"]["configuration"]
    }
    assert "main/frontend-modern/pnpm-workspace.yaml" in {
        row["path"] for row in record["bindings"]["required_files"]["configuration"]
    }
    assert tool.validate_stage1_record(root, record) is None

    destination = tool.write_create_only(root, record)
    assert destination == root / OUTPUT
    serialized = json.loads(destination.read_text(encoding="utf-8"))
    assert serialized == record
    with pytest.raises(tool.Stage1RecordError, match="create-only target already exists"):
        tool.write_create_only(root, record)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (
            lambda value: value.update(authoritative=True),
            "non-authority",
        ),
        (
            lambda value: value.update(candidate_commit="0" * 64),
            "unfrozen candidate",
        ),
        (
            lambda value: value.update(candidate_tree="1" * 64),
            "unfrozen candidate",
        ),
        (
            lambda value: value["candidate"].update(commit="2" * 64),
            "unfrozen candidate",
        ),
        (
            lambda value: value["commands"]["r3_direct"].update(result="true"),
            "result must be PASS",
        ),
        (
            lambda value: value["commands"]["migration_single_head"].pop("receipt"),
            "fields drifted",
        ),
        (
            lambda value: value["commands"]["r3_direct"].update(command="true"),
            "command identity drifted",
        ),
        (
            lambda value: value["commands"]["r3_direct"]["receipt"].update(
                path="stage1-receipts/wrong.log"
            ),
            "required input missing",
        ),
        (
            lambda value: value["commands"]["r3_direct"]["receipt"].update(
                sha256="4" * 64
            ),
            "receipt sha256 drift",
        ),
        (
            lambda value: value["commands"].pop("architecture_gate"),
            "command id set",
        ),
        (
            lambda value: value["commands"]["frontend_lint"].update(summary="lint failed; 1 error"),
            "summary drifted",
        ),
        (
            lambda value: value["bindings"]["stage_plan"].update(sha256="2" * 64),
            "frozen plan binding",
        ),
        (
            lambda value: value["bindings"]["required_files"]["source"][0].update(
                sha256="3" * 64
            ),
            "manifest drift",
        ),
        (
            lambda value: value["known_gaps"][0].update(stage_floor="STAGE_1"),
            "Stage 2 or later",
        ),
    ],
)
def test_record_mutation_fails_closed(tmp_path: Path, mutator, message: str) -> None:
    root = stage1_fixture(tmp_path)
    record = tool.build_stage1_record(root, evidence())
    value = copy.deepcopy(record)
    mutator(value)
    with pytest.raises(tool.Stage1RecordError, match=message):
        tool.validate_stage1_record(root, value)


def test_stage1_command_contracts_match_stable_implementation() -> None:
    assert Path("scripts/formal_release/check_functorial_kit_dependency_audit.py") in tool.SOURCE_RELS
    assert Path("tests/formal_release/test_check_functorial_kit_dependency_audit.py") in tool.SOURCE_RELS
    contracts = {item["id"]: item for item in tool.COMMAND_CONTRACTS}
    assert contracts["r3_direct"]["command"].endswith(
        "scripts/formal_release/check_static_production_contract.py"
    )
    assert "main/backend/tests/production_composition" in (
        contracts["focused_backend_stage1"]["command"]
    )
    workflow_command = contracts["workflow_contract"]["command"]
    assert workflow_command.endswith(
        "tests/formal_release/test_s1_workflow_contract.py "
        "tests/formal_release/test_s1_production_compose_contract.py"
    )
    assert " -m pytest -q tests/formal_release" not in workflow_command
    assert contracts["compose_config_production"]["command"].endswith(
        "scripts/formal_release/check_production_compose_config.py"
    )
    assert tool.RESOURCE_CLEANUP_COMMAND_PATTERN.fullmatch(_cleanup_command())


def test_pseudo_resource_cleanup_command_is_rejected(tmp_path: Path) -> None:
    root = stage1_fixture(tmp_path)
    payload = evidence()
    assert isinstance(payload["commands"], dict)
    payload["commands"]["resource_cleanup"]["command"] = (
        "post-Stage1 resource cleanup audit"
    )
    with pytest.raises(
        tool.Stage1RecordError,
        match="executable cleanup program",
    ):
        tool.build_stage1_record(root, payload)


def test_source_receipt_plan_and_summary_drift_fail_closed(tmp_path: Path) -> None:
    root = stage1_fixture(tmp_path)
    original_record = tool.build_stage1_record(root, evidence())
    tool.validate_stage1_record(root, original_record)

    source = root / "pyproject.toml"
    raw = source.read_bytes()
    source.write_bytes(raw + b"\n")
    with pytest.raises(tool.Stage1RecordError, match="required source"):
        tool.validate_stage1_record(root, original_record)
    source.write_bytes(raw)

    receipt = root / "stage1-receipts/architecture_gate.log"
    receipt_raw = receipt.read_bytes()
    receipt.write_bytes(b"286 passed\n")
    with pytest.raises(tool.Stage1RecordError, match="receipt sha256 drift"):
        tool.validate_stage1_record(root, original_record)
    receipt.write_bytes(receipt_raw)

    plan = root / tool.PLAN_REL
    plan_raw = plan.read_bytes()
    plan.write_bytes(plan_raw + b"\n")
    with pytest.raises(tool.Stage1RecordError, match="plan identity drift"):
        tool.build_stage1_record(root, evidence())
    plan.write_bytes(plan_raw)
    tool.validate_stage1_record(root, original_record)


def test_failure_signal_in_receipt_summary_fails_closed(tmp_path: Path) -> None:
    root = stage1_fixture(tmp_path)
    receipt = root / "stage1-receipts/resource_cleanup.log"
    receipt.write_bytes(b"residual resources: 0\nUNEXECUTED check\n")
    payload = evidence()
    assert isinstance(payload["commands"], dict)
    payload["commands"]["resource_cleanup"]["receipt"]["sha256"] = hashlib.sha256(
        receipt.read_bytes()
    ).hexdigest()
    with pytest.raises(tool.Stage1RecordError, match="failure signal"):
        tool.build_stage1_record(root, payload)


def test_checker_reports_formal_preflight_envelope(tmp_path: Path, capsys) -> None:
    root = stage1_fixture(tmp_path)
    record = tool.build_stage1_record(root, evidence())
    destination = root / "record.json"
    destination.write_text(json.dumps(record), encoding="utf-8")
    assert checker.main([str(destination), "--repo-root", str(root)]) == 0
    passed = json.loads(capsys.readouterr().out)
    assert passed["schema_version"] == "mrw.formal-release-preflight.v1"
    assert passed["checker"] == tool.CHECKER
    assert passed["authoritative"] is False
    assert passed["derived_as"] == "preflight"
    assert passed["status"] == "PASS"

    tampered = copy.deepcopy(record)
    tampered["status"] = "FAIL"
    destination.write_text(json.dumps(tampered), encoding="utf-8")
    assert checker.main([str(destination), "--repo-root", str(root)]) == 1
    failed = json.loads(capsys.readouterr().out)
    assert failed["status"] == "FAIL"
    assert failed["authoritative"] is False
    assert failed["derived_as"] == "preflight"


def test_zero_error_success_summary_is_not_a_failure_signal(tmp_path: Path) -> None:
    tool._assert_receipt_clean(
        b"eslint finished\n",
        "frontend_lint",
    )


def test_existing_target_and_output_escape_rejected(tmp_path: Path) -> None:
    root = stage1_fixture(tmp_path)
    record = tool.build_stage1_record(root, evidence())
    destination = root / OUTPUT
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(b"existing")
    with pytest.raises(tool.Stage1RecordError, match="create-only target already exists"):
        tool.write_create_only(root, record)
    with pytest.raises(tool.Stage1RecordError, match="output escapes repository root"):
        tool.write_create_only(root, record, tmp_path / "outside.json")
