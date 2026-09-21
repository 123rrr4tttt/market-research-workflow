#!/usr/bin/env python3
# ruff: noqa: E501, TRY003, TRY300, TRY301
"""Bind Stage 1 production-contract evidence into a deterministic record.

The command never runs implementation gates.  It receives one-time board
receipts as JSON, binds them to frozen plan bytes and exact implementation
files, and prints or create-only writes the non-authoritative result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Any

from scripts.formal_release.model import Finding, PreflightReport


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FORMAL_RELEASE_DIR = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release"
)
PLAN_REL = FORMAL_RELEASE_DIR / "04_production-deployment-stage-plan.v1.md"
PLAN_FREEZE_REL = FORMAL_RELEASE_DIR / "05_production-deployment-stage-plan.freeze.v1.json"
STAGE0_COMPLETION_REL = (
    FORMAL_RELEASE_DIR
    / "stage0-evidence/functorial-refactor-completion.v4.json"
)
OUTPUT_REL = FORMAL_RELEASE_DIR / "stage1-evidence/production-contract-implementation.v1.json"

PLAN_SHA256 = "d04ae870b5d2a13afacdc7a07e9d5a89b7ab77e7b6c2d6cdd4bd2101151f76fa"
PLAN_BYTES = 24713
PLAN_LINES = 420

SCHEMA = "mrw.formal_release.stage1.production_contract_implementation.v1"
SCHEMA_VERSION = "mrw.stage1.production-contract-implementation.v1"
RECORD_ID = "stage1-production-contract-implementation-v1"
STATUS = "PRODUCTION_CONTRACT_IMPLEMENTED_NOT_AUTHORITY"
CHECKER = "stage1-production-contract-record-checker"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PASS = "PASS"

AUTHORITY_KEYS = (
    "deployment",
    "candidate_promotion",
    "production_canonical_write",
    "live_provider",
    "external_delivery",
    "canary",
    "cutover",
    "authority_transfer",
    "legacy_retirement",
    "push",
)

SOURCE_RELS = (
    Path("pyproject.toml"),
    Path("functorial-kit.json"),
    Path("sketches.json"),
    Path("registries/failures.json"),
    Path("main/backend/app/release_identity.py"),
    Path("main/backend/app/main.py"),
    Path("main/backend/app/web_ui_routes.py"),
    Path("main/backend/app/settings/config.py"),
    Path("main/backend/app/settings/graph.py"),
    Path("main/backend/app/api/__init__.py"),
    Path("main/backend/app/api/agent_chat.py"),
    Path("main/backend/app/api/codex_auth.py"),
    Path("main/backend/app/composition/__init__.py"),
    Path("main/backend/app/composition/production.py"),
    Path("main/backend/app/composition/production_runtime.py"),
    Path("main/backend/app/composition/production_route_bindings.json"),
    Path("main/backend/app/services/codex_oauth.py"),
    Path("main/backend/app/services/request_identity.py"),
    Path("scripts/check_backend_migration_graph.py"),
    Path("scripts/formal_release/check_functorial_kit_dependency_audit.py"),
    Path("scripts/formal_release/check_static_production_contract.py"),
    Path("scripts/formal_release/source_closure.py"),
    Path("scripts/formal_release/check_production_compose_config.py"),
    Path("scripts/formal_release/generate_stage1_production_contract_record.py"),
    Path("scripts/formal_release/check_stage1_production_contract_record.py"),
    Path("scripts/formal_release/generate_stage1_current_binding_successor.py"),
    Path("scripts/formal_release/check_stage1_current_binding_successor.py"),
    Path("scripts/materialize_functorial_kit_consumer_gate.py"),
    Path("tools/functorial-kit/consumer-gate.manifest.json"),
    Path("tools/functorial-kit/consumer-gate.patch"),
    Path(
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-09-04-formal-production-release/stage1-evidence/independent-review.v1.md"
    ),
    Path("main/backend/app/production_contract/__init__.py"),
    Path("main/backend/app/production_contract/policy.py"),
    Path("main/backend/app/production_contract/types.py"),
    Path("main/backend/app/production_observability/alerts.py"),
    Path("main/backend/app/production_observability/contracts.py"),
    Path("main/backend/app/production_observability/config.py"),
    Path("main/backend/app/production_observability/decision.py"),
    Path("main/backend/app/production_observability/errors.py"),
    Path("main/backend/app/production_observability/__init__.py"),
    Path("main/backend/app/production_observability/observations.py"),
    Path("main/backend/app/production_observability/receipts.py"),
    Path("main/backend/app/production_observability/runtime.py"),
    Path("main/ops/production_contract/__init__.py"),
    Path("main/ops/production_contract/fixture_recovery_tools.py"),
    Path("main/ops/rollback.sh"),
    Path("tests/test_architecture.py"),
    Path("tests/formal_release/test_check_functorial_kit_dependency_audit.py"),
    Path("tests/formal_release/test_check_static_production_contract.py"),
    Path("tests/formal_release/test_source_closure.py"),
    Path("tests/formal_release/test_check_production_compose_config.py"),
    Path("tests/formal_release/test_s1_production_compose_contract.py"),
    Path("tests/formal_release/test_s1_workflow_contract.py"),
    Path("tests/formal_release/test_generate_stage1_production_contract_record.py"),
    Path("tests/formal_release/test_stage1_current_binding_successor.py"),
    Path("tests/formal_release/test_functorial_kit_consumer_gate.py"),
    Path("main/backend/tests/production_composition/test_production_composition.py"),
    Path("main/backend/tests/production_composition/test_production_auth_bootstrap.py"),
    Path("main/backend/tests/production_composition/test_production_runtime_bindings.py"),
    Path("main/backend/tests/production_composition/test_production_stream_observation.py"),
    Path("main/backend/tests/production_composition/test_route_effect_contract.py"),
    Path("main/backend/tests/production_composition/test_s1_operation_authority_adapters.py"),
    Path("main/backend/tests/production_contract/test_s1_migration_graph.py"),
    Path("main/backend/tests/production_contract/test_s1_production_policy.py"),
    Path("main/backend/tests/production_identity/test_release_identity.py"),
    Path("main/backend/tests/production_observability/test_production_observability_core_unittest.py"),
    Path("main/backend/tests/production_observability/test_r7_failclosed_hardening_unittest.py"),
    Path("main/backend/tests/production_observability/test_r7_runtime_controller_unittest.py"),
    Path("main/backend/tests/ops_production_contract/test_fixture_recovery_tools.py"),
    Path("main/backend/tests/ops_production_contract/test_rollback_adapter.py"),
)

CONFIGURATION_RELS = (
    Path("main/ops/docker-compose.yml"),
    Path("main/ops/docker-compose.production.yml"),
    Path("main/backend/.env.example"),
    Path("main/backend/.env.production.example"),
    Path("main/backend/Dockerfile"),
    Path("main/backend/Dockerfile.test"),
    Path("main/frontend-modern/package.json"),
    Path("main/frontend-modern/pnpm-lock.yaml"),
    Path("main/frontend-modern/pnpm-workspace.yaml"),
    Path("main/backend/requirements.txt"),
)

WORKFLOW_RELS = (
    Path(".github/workflows/backend-tests.yml"),
    Path(".github/branch-protection-required-checks.json"),
)

MIGRATION_VERSIONS_DIR = Path("main/backend/migrations/versions")
MIGRATION_RELS = (
    Path("main/backend/alembic.ini"),
    Path("main/backend/migrations/env.py"),
    Path("main/backend/migrations/util.py"),
)
MIGRATION_MERGE_REL = Path(
    "main/backend/migrations/versions/20260905_000001_merge_release_heads.py"
)

COMMAND_CONTRACTS: tuple[dict[str, str], ...] = (
    {
        "id": "r3_direct",
        "command": (
            "PYTHONPATH=src main/backend/.venv311/bin/python "
            "scripts/formal_release/check_static_production_contract.py"
        ),
        "summary_pattern": r"^static production contract PASS$",
    },
    {
        "id": "focused_backend_stage1",
        "command": (
            "PYTHONPATH=src:main/backend main/backend/.venv311/bin/python -m pytest -q "
            "-p no:cacheprovider "
            "main/backend/tests/production_composition "
            "main/backend/tests/production_contract "
            "main/backend/tests/production_identity "
            "main/backend/tests/production_observability "
            "main/backend/tests/ops_production_contract"
        ),
        "summary_pattern": r"^\d+ passed(?:; \d+ warnings)?$",
    },
    {
        "id": "migration_single_head",
        "command": (
            "main/backend/.venv311/bin/python scripts/check_backend_migration_graph.py "
            "--expect-single-head --expect-head 20260905_000001 --json"
        ),
        "summary_pattern": (
            r"^single head: 20260905_000001; revisions: [1-9]\d*$"
        ),
    },
    {
        "id": "compose_config_dev",
        "command": "docker compose --profile dev -f main/ops/docker-compose.yml config --quiet",
        "summary_pattern": r"^configuration valid: dev$",
    },
    {
        "id": "compose_config_production",
        "command": (
            "PYTHONPATH=src main/backend/.venv311/bin/python "
            "scripts/formal_release/check_production_compose_config.py"
        ),
        "summary_pattern": r"^configuration valid: production$",
    },
    {
        "id": "frontend_lint",
        "command": "cd main/frontend-modern && pnpm lint",
        "summary_pattern": r"^lint passed; 0 errors$",
    },
    {
        "id": "frontend_typecheck",
        "command": "cd main/frontend-modern && pnpm exec tsc -b",
        "summary_pattern": r"^typecheck passed; 0 errors$",
    },
    {
        "id": "frontend_build",
        "command": "cd main/frontend-modern && pnpm build",
        "summary_pattern": r"^build succeeded$",
    },
    {
        "id": "workflow_contract",
        "command": (
            "PYTHONPATH=src main/backend/.venv311/bin/python -m pytest -q "
            "-p no:cacheprovider "
            "tests/formal_release/test_s1_workflow_contract.py "
            "tests/formal_release/test_s1_production_compose_contract.py"
        ),
        "summary_pattern": r"^all required workflow categories present$",
    },
    {
        "id": "architecture_gate",
        "command": (
            "PYTHONPATH=src .venv/bin/python -m pytest -q "
            "-p no:cacheprovider tests/test_architecture.py"
        ),
        "summary_pattern": r"^\d+ passed$",
    },
    {
        "id": "resource_cleanup",
        "command": "post-Stage1 resource cleanup audit",
        "summary_pattern": r"^residual resources: 0$",
    },
)

RESOURCE_CLEANUP_PROGRAM = (
    "import os,pathlib,shutil,subprocess,sys; "
    "root=pathlib.Path(os.environ[\"STAGE1_TEMP_ROOT\"]); "
    "marker=root.name; existed=root.exists(); "
    "shutil.rmtree(root) if existed else None; "
    "lines=subprocess.check_output([\"ps\",\"-axo\",\"command=\"],text=True).splitlines(); "
    "current=str(os.getpid()); parent=str(os.getppid()); "
    "runners=[line for line in lines if marker in line and current not in line "
    "and parent not in line]; temp_removed=not root.exists(); "
    'print(f"resource cleanup passed; temp removed: {str(temp_removed).lower()}; runner processes: {len(runners)}"); '
    "sys.exit(1) if not temp_removed or runners else None"
)
RESOURCE_CLEANUP_COMMAND_PATTERN = re.compile(
    r"^STAGE1_TEMP_ROOT=/private/tmp/stage1-contract-record-"
    r"[A-Za-z0-9][A-Za-z0-9_-]{15,} main/backend/\.venv311/bin/python -c '"
    + re.escape(RESOURCE_CLEANUP_PROGRAM)
    + r"'$"
)
RESOURCE_CLEANUP_SUMMARY = (
    "resource cleanup passed; temp removed: true; runner processes: 0"
)

RECEIPT_FAILURE_PATTERN = re.compile(
    r"\b(?:FAIL(?:ED)?|BLOCKED|UNEXECUTED|SKIP(?:PED)?|CANCEL(?:LED)?|"
    r"CANCELED|ERRORS?|FATAL|ABORTED|KILLED|TIMEOUT|TIMED OUT)\b",
    re.IGNORECASE,
)
NONZERO_EXIT_PATTERN = re.compile(
    r"\b(?:EXIT(?:ED)?(?: CODE)?|STATUS)\s*[=:]?\s*[1-9]\d*\b", re.IGNORECASE
)
KNOWN_GAP_STAGES = frozenset(
    {"STAGE_2", "STAGE_3", "STAGE_4", "STAGE_5", "STAGE_6", "STAGE_7", "STAGE_8", "STAGE_9"}
)


class Stage1RecordError(RuntimeError):
    """Raised whenever Stage1 record construction or validation fails closed."""


GenerationError = Stage1RecordError
ValidationError = Stage1RecordError


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe(root: Path, relative: Path | str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise Stage1RecordError(f"path escapes repository root: {relative}")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise Stage1RecordError(f"path escapes repository root: {relative}") from exc
    return candidate


def _read(root: Path, relative: Path | str) -> bytes:
    safe = _safe(root, relative)
    path = root / safe
    if not path.is_file() or path.is_symlink():
        raise Stage1RecordError(f"required input missing: {safe.as_posix()}")
    return path.read_bytes()


def _ref(root: Path, relative: Path) -> dict[str, str]:
    raw = _read(root, relative)
    return {"path": relative.as_posix(), "sha256": sha256_bytes(raw)}


def _required_file_binding(root: Path, relative: Path) -> dict[str, str]:
    return _ref(root, relative)


def _migration_rels(root: Path) -> tuple[Path, ...]:
    versions_root = root / MIGRATION_VERSIONS_DIR
    if not versions_root.is_dir():
        raise Stage1RecordError(f"required input missing: {MIGRATION_VERSIONS_DIR.as_posix()}")
    discovered = tuple(
        MIGRATION_VERSIONS_DIR / path.name
        for path in sorted(versions_root.glob("*.py"))
        if path.name != "__init__.py"
    )
    if MIGRATION_MERGE_REL not in discovered:
        raise Stage1RecordError("required migration merge revision is missing")
    return MIGRATION_RELS + discovered


def _api_rels(root: Path) -> tuple[Path, ...]:
    """Bind every installed API handler that the route-effect registry classifies."""
    api_root = root / "main/backend/app/api"
    if not api_root.is_dir():
        raise Stage1RecordError("required input missing: main/backend/app/api")
    return tuple(
        Path("main/backend/app/api") / path.name
        for path in sorted(api_root.glob("*.py"))
    )


def _manifest(root: Path) -> dict[str, list[dict[str, str]]]:
    return {
        "source": [
            _required_file_binding(root, item)
            for item in dict.fromkeys(SOURCE_RELS + _api_rels(root))
        ],
        "configuration": [_required_file_binding(root, item) for item in CONFIGURATION_RELS],
        "workflow": [_required_file_binding(root, item) for item in WORKFLOW_RELS],
        "migration": [_required_file_binding(root, item) for item in _migration_rels(root)],
    }


def _validate_frozen_plan(root: Path) -> tuple[dict[str, str], dict[str, Any]]:
    raw = _read(root, PLAN_REL)
    lines = len(raw.decode("utf-8", errors="strict").splitlines())
    if sha256_bytes(raw) != PLAN_SHA256 or len(raw) != PLAN_BYTES or lines != PLAN_LINES:
        raise Stage1RecordError("frozen Stage 1 plan identity drift from module-pinned bytes")
    freeze_raw = _read(root, PLAN_FREEZE_REL)
    try:
        freeze = json.loads(freeze_raw)
    except json.JSONDecodeError as exc:
        raise Stage1RecordError("stage plan freeze is invalid JSON") from exc
    if not isinstance(freeze, dict) or freeze.get("schema_version") != (
        "mrw.production-deployment-stage-plan.freeze.v1"
    ):
        raise Stage1RecordError("stage plan freeze schema_version drift")
    if freeze.get("status") != "FROZEN_FOR_IMPLEMENTATION_V1":
        raise Stage1RecordError("stage plan freeze is not FROZEN_FOR_IMPLEMENTATION_V1")
    files = freeze.get("frozen_files")
    if not isinstance(files, list) or len(files) != 1:
        raise Stage1RecordError("stage plan freeze must contain exactly one file")
    expected = {
        "path": PLAN_REL.as_posix(),
        "sha256": PLAN_SHA256,
        "bytes": PLAN_BYTES,
        "lines": PLAN_LINES,
    }
    if files[0] != expected:
        raise Stage1RecordError("stage plan freeze entry drift")
    plan_binding = {"path": PLAN_REL.as_posix(), "sha256": sha256_bytes(raw)}
    return plan_binding, {
        "path": PLAN_FREEZE_REL.as_posix(),
        "sha256": sha256_bytes(freeze_raw),
        "schema_version": freeze["schema_version"],
    }


def _validate_stage0_completion(root: Path) -> dict[str, str]:
    raw = _read(root, STAGE0_COMPLETION_REL)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Stage1RecordError("Stage0 completion record is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise Stage1RecordError("Stage0 completion record JSON root must be an object")
    if (
        payload.get("schema_version") != "mrw.stage0.functorial-refactor-completion.v4"
        or payload.get("status") != "FUNCTORIAL_REFACTOR_COMPLETE_NOT_PRODUCTION_QUALIFIED"
        or payload.get("authoritative") is not False
        or payload.get("derived_as") != "external_claim"
    ):
        raise Stage1RecordError("Stage0 completion identity or non-authority binding drift")
    return {
        "path": STAGE0_COMPLETION_REL.as_posix(),
        "sha256": sha256_bytes(raw),
    }


def _assert_authority_false(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        return
    if "authoritative" in value and value["authoritative"] is not False:
        raise Stage1RecordError(f"{label} must be non-authoritative")
    for key, item in value.items():
        _assert_authority_false(item, f"{label}.{key}")


def _require_commands(root: Path, evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = evidence.get("commands")
    if not isinstance(rows, dict) or set(rows) != {item["id"] for item in COMMAND_CONTRACTS}:
        raise Stage1RecordError("command id set drifted from the Stage 1 contract")
    normalized: dict[str, dict[str, Any]] = {}
    for contract in COMMAND_CONTRACTS:
        command_id = contract["id"]
        row = rows[command_id]
        if not isinstance(row, dict) or set(row) != {
            "command",
            "result",
            "exit_code",
            "summary",
            "receipt",
        }:
            raise Stage1RecordError(f"commands.{command_id} fields drifted")
        if command_id == "resource_cleanup":
            if RESOURCE_CLEANUP_COMMAND_PATTERN.fullmatch(row["command"]) is None:
                raise Stage1RecordError(
                    "commands.resource_cleanup must use the executable cleanup program"
                )
        elif row["command"] != contract["command"]:
            raise Stage1RecordError(f"commands.{command_id} command identity drifted")
        if row["result"] != PASS:
            raise Stage1RecordError(f"commands.{command_id} result must be PASS")
        if isinstance(row["exit_code"], bool) or row["exit_code"] != 0:
            raise Stage1RecordError(f"commands.{command_id} must record exit_code 0")
        summary = row["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise Stage1RecordError(f"commands.{command_id} summary is required")
        expected_summary = (
            RESOURCE_CLEANUP_SUMMARY if command_id == "resource_cleanup" else None
        )
        if expected_summary is not None:
            if summary != expected_summary:
                raise Stage1RecordError("commands.resource_cleanup summary drifted")
        elif re.fullmatch(contract["summary_pattern"], summary) is None:
            raise Stage1RecordError(f"commands.{command_id} summary drifted from its command contract")
        receipt = row["receipt"]
        if not isinstance(receipt, dict) or set(receipt) != {"path", "sha256"}:
            raise Stage1RecordError(f"commands.{command_id} requires path and sha256 receipt binding")
        relative = Path(receipt["path"])
        raw = _read(root, relative)
        actual_sha = sha256_bytes(raw)
        if receipt["sha256"] != actual_sha:
            raise Stage1RecordError(f"commands.{command_id} receipt sha256 drift")
        _assert_receipt_clean(raw, command_id)
        normalized[command_id] = {
            "command": row["command"],
            "result": PASS,
            "exit_code": 0,
            "summary": summary,
            "receipt": {"path": relative.as_posix(), "sha256": actual_sha},
        }
    return normalized


def _assert_receipt_clean(raw: bytes, command_id: str) -> None:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Stage1RecordError(f"commands.{command_id} receipt is not UTF-8") from exc
    if RECEIPT_FAILURE_PATTERN.search(text) is not None:
        raise Stage1RecordError(f"commands.{command_id} receipt contains a failure signal")
    if NONZERO_EXIT_PATTERN.search(text) is not None:
        raise Stage1RecordError(f"commands.{command_id} receipt contains a nonzero exit signal")


def _require_known_gaps(evidence: dict[str, Any]) -> list[dict[str, str]]:
    rows = evidence.get("known_gaps")
    if not isinstance(rows, list):
        raise Stage1RecordError("known_gaps must be a list")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "stage_floor", "owner", "reason", "status"}:
            raise Stage1RecordError("known gap fields drifted")
        gap_id = row["id"]
        if not isinstance(gap_id, str) or not gap_id or gap_id in seen:
            raise Stage1RecordError("known gap ids must be unique nonempty strings")
        seen.add(gap_id)
        if row["stage_floor"] not in KNOWN_GAP_STAGES:
            raise Stage1RecordError("known gaps must be retained at Stage 2 or later")
        if row["status"] != "RETAINED_LATER_STAGE":
            raise Stage1RecordError("known gap status must be RETAINED_LATER_STAGE")
        for key in ("owner", "reason"):
            if not isinstance(row[key], str) or not row[key].strip():
                raise Stage1RecordError(f"known gap {key} is required")
        normalized.append({key: row[key] for key in ("id", "stage_floor", "owner", "reason", "status")})
    return normalized


def _evidence_header(evidence: dict[str, Any]) -> str:
    observed_at = evidence.get("observed_at")
    if not isinstance(observed_at, str) or not observed_at.strip():
        raise Stage1RecordError("observed_at is required for deterministic binding")
    return observed_at


def _candidate_unfrozen() -> dict[str, Any]:
    return {"commit": None, "tree": None}


def build_stage1_record(
    root: Path,
    evidence: dict[str, Any],
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=evidence "
    "fact_source=stage_plan_freeze+stage0_completion+command_receipts+file_manifest "
    "witness=test:test_build_validate_create_only_and_exact_rebuild",
]:
    """Build a deterministic record, raising on every fail-closed condition."""
    if not isinstance(evidence, dict):
        raise Stage1RecordError("evidence root must be an object")
    observed_at = _evidence_header(evidence)
    plan, plan_freeze = _validate_frozen_plan(root)
    stage0 = _validate_stage0_completion(root)
    commands = _require_commands(root, evidence)
    known_gaps = _require_known_gaps(evidence)
    authority = {key: False for key in AUTHORITY_KEYS}
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "record_id": RECORD_ID,
        "stage": "STAGE_1",
        "status": STATUS,
        "authoritative": False,
        "derived_as": "evidence",
        "candidate_commit": None,
        "candidate_tree": None,
        "candidate": _candidate_unfrozen(),
        "authority": authority,
        "observed_at": observed_at,
        "bindings": {
            "stage_plan": plan,
            "stage_plan_freeze": plan_freeze,
            "stage0_completion": stage0,
            "required_files": _manifest(root),
        },
        "commands": commands,
        "known_gaps": known_gaps,
    }
    validate_stage1_record(root, record)
    return record


def validate_stage1_record(root: Path, record: dict[str, Any]) -> None:
    """Validate one generated record and every source byte it binds."""
    if not isinstance(record, dict) or set(record) != {
        "schema",
        "schema_version",
        "record_id",
        "stage",
        "status",
        "authoritative",
        "derived_as",
        "candidate_commit",
        "candidate_tree",
        "candidate",
        "authority",
        "observed_at",
        "bindings",
        "commands",
        "known_gaps",
    }:
        raise Stage1RecordError("unexpected Stage1 record schema or field set")
    if (
        record["schema"] != SCHEMA
        or record["schema_version"] != SCHEMA_VERSION
        or record["record_id"] != RECORD_ID
        or record["stage"] != "STAGE_1"
        or record["status"] != STATUS
        or record["authoritative"] is not False
        or record["derived_as"] != "evidence"
        or record["candidate_commit"] is not None
        or record["candidate_tree"] is not None
        or record["candidate"] != _candidate_unfrozen()
    ):
        raise Stage1RecordError(
            "Stage1 identity, non-authority, evidence projection, or unfrozen candidate binding drift"
        )
    authority = record["authority"]
    if not isinstance(authority, dict) or set(authority) != set(AUTHORITY_KEYS):
        raise Stage1RecordError("Stage1 authority key set drift")
    if any(authority.get(key) is not False for key in AUTHORITY_KEYS):
        raise Stage1RecordError("all Stage1 authority flags must be false")
    _assert_authority_false(record, "Stage1 record")
    if not isinstance(record["observed_at"], str) or not record["observed_at"].strip():
        raise Stage1RecordError("observed_at binding drift")
    plan, plan_freeze = _validate_frozen_plan(root)
    stage0 = _validate_stage0_completion(root)
    bindings = record["bindings"]
    if not isinstance(bindings, dict) or set(bindings) != {
        "stage_plan",
        "stage_plan_freeze",
        "stage0_completion",
        "required_files",
    }:
        raise Stage1RecordError("Stage1 binding field set drift")
    if bindings["stage_plan"] != plan or bindings["stage_plan_freeze"] != plan_freeze:
        raise Stage1RecordError("frozen plan binding drift")
    if bindings["stage0_completion"] != stage0:
        raise Stage1RecordError("Stage0 completion binding drift")
    if bindings["required_files"] != _manifest(root):
        raise Stage1RecordError("required source, configuration, workflow, or migration manifest drift")
    evidence_commands = {
        command_id: dict(row)
        for command_id, row in record.get("commands", {}).items()
    }
    known_gaps = record.get("known_gaps", [])
    reconstructed = {
        "observed_at": record["observed_at"],
        "commands": evidence_commands,
        "known_gaps": known_gaps,
    }
    expected_commands = _require_commands(root, reconstructed)
    expected_gaps = _require_known_gaps(reconstructed)
    if record["commands"] != expected_commands:
        raise Stage1RecordError("Stage1 command receipt binding drift")
    if record["known_gaps"] != expected_gaps:
        raise Stage1RecordError("Stage1 known-gap binding drift")


def write_create_only(
    root: Path,
    record: dict[str, Any],
    output: Path | None = None,
) -> Path:
    destination = (output or (root / OUTPUT_REL)).resolve()
    try:
        destination.relative_to(root.resolve())
    except ValueError as exc:
        raise Stage1RecordError("output escapes repository root") from exc
    if destination.exists():
        try:
            shown = destination.relative_to(root.resolve()).as_posix()
        except ValueError:
            shown = str(destination)
        raise Stage1RecordError(f"create-only target already exists: {shown}")
    payload = (json.dumps(record, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as exc:
        raise Stage1RecordError(f"create-only target already exists: {destination}") from exc
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
    return destination


build_record = build_stage1_record
validate_record = validate_stage1_record
write_record = write_create_only


def _failure_report(message: str) -> PreflightReport:
    return PreflightReport(
        CHECKER,
        (Finding("stage1_production_contract_record", "FAIL", message),),
    )


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--evidence", type=Path, help="one-time command receipt JSON input")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--write", action="store_true")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.repo_root.resolve()
    try:
        if args.evidence is None:
            raise Stage1RecordError("--evidence is required")
        try:
            value = json.loads(args.evidence.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise Stage1RecordError(f"evidence input is invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise Stage1RecordError("evidence JSON root must be an object")
        record = build_stage1_record(root, value)
        if args.write:
            destination = write_create_only(root, record, args.output)
            print(f"WRITTEN {destination}")
        else:
            print(json.dumps(record, ensure_ascii=True, indent=2, sort_keys=True))
    except (Stage1RecordError, OSError) as exc:
        print(_failure_report(str(exc)).to_json(), end="")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
