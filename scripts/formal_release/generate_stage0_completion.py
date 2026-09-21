#!/usr/bin/env python3
# ruff: noqa: E501, TRY003, TRY300, TRY301
"""Build and validate the non-authoritative Stage 0 completion record.

The command is intentionally input-driven.  A caller supplies the final
current-byte rebind and command evidence as JSON; this tool binds that evidence to the frozen
plan, live baseline/ledger, governance maps, declared-loss records, kit
applicability record, and the fixed per-family current candidates (B19 for
C2-C9 and B22 for I1).  ``--write`` is create-only and never mutates any
predecessor or progress file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Annotated, Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PLAN_REL = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release/04_production-deployment-stage-plan.v1.md"
)
PLAN_FREEZE_REL = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release/05_production-deployment-stage-plan.freeze.v1.json"
)
PLAN_FREEZE_SCHEMA_VERSION = "mrw.production-deployment-stage-plan.freeze.v1"
PLAN_SHA256 = "d04ae870b5d2a13afacdc7a07e9d5a89b7ab77e7b6c2d6cdd4bd2101151f76fa"
PLAN_BYTES = 24713
PLAN_LINES = 420
BASELINE_REL = Path("arch-baseline.json")
LEDGER_REL = Path("docs/governance/functorial-debt-zero-baseline-resolutions.v1.json")
KIT_REL = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release/stage0-evidence/kit-applicability.v1.json"
)
DECLARED_LOSS_REL = {
    "collect": Path(
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-09-04-formal-production-release/stage0-evidence/declared-loss-collect.v1.json"
    ),
    "ingest": Path(
        "development/latest-dev-docs/development-plans/CURRENT_DEV/"
        "2026-09-04-formal-production-release/stage0-evidence/declared-loss-ingest.v1.json"
    ),
}
MAP_RELS = (
    Path("docs/governance/failure-family-map.v1.json"),
    Path("docs/governance/derived-authority-map.v1.json"),
)
CANDIDATE_ROOT_PARENT_REL = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-08-30-functorial-successor-migration/evidence/exact-byte-rebind/"
)
FAMILIES = ("C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "I1")
CURRENT_CANDIDATE_STAGES = {
    family: "stage-b19-2026-09-05"
    for family in FAMILIES
    if family != "I1"
}
CURRENT_CANDIDATE_STAGES["I1"] = "stage-b22-2026-09-05"
OUTPUT_REL = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release/stage0-evidence/"
    "functorial-refactor-completion.v4.json"
)
SCHEMA = "mrw.formal_release.stage0.functorial_refactor_completion.v4"
SCHEMA_VERSION = "mrw.stage0.functorial-refactor-completion.v4"
STATUS = "FUNCTORIAL_REFACTOR_COMPLETE_NOT_PRODUCTION_QUALIFIED"
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
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_LOSS_DECISIONS = {"IMPLEMENTED", "ACCEPTED_EXPLICIT_LOSS", "NOT_APPLICABLE"}
PASS = "PASS"
CURRENT_BYTE_REBIND_EVIDENCE_KEY = "current_byte_rebind"
RECEIPT_FAILURE_PATTERNS = (
    # pytest and Playwright failure summaries can coexist with a passing count.
    r"(?m)^\s*[1-9][\d,]*\s+(?:failed|errors?|interrupted|disconnected|timed out|flaky)\b",
    r"(?m)^=+.*\b[1-9][\d,]*\s+(?:failed|errors?|interrupted)\b",
    r"(?m)^\s*[1-9][\d,]*\s+(?:did not run|not run)\b",
    # Runner and bundler failure lines use tool-specific spellings.
    r"(?m)^(?:npm (?:ERR!|error)|ERROR in\b|error during build:)",
    r"error TS\d+:",
    r"(?m)^\s+\d+:\d+\s+error\b",
    # Uppercase runner markers must start their line so harmless words embedded
    # in test titles are not mistaken for receipt failures.
    r"(?m)^(?:Traceback \(most recent call last\)|FAILED\b|ERROR\b|FATAL\b|ABORTED\b|Killed\b|Interrupted\b)",
    r"(?mi)^\s*(?:exit|exited|process)\b.*(?:non-?zero|exit code [1-9]\d*|status [1-9]\d*)",
    r"(?mi)^\s*(?:process\s+)?(?:killed|terminated|interrupted)\b",
    r"(?m)^\s*(?:SIGKILL|SIGTERM|SIGINT)\b",
    r"(?m)^EXIT=(?:[1-9]\d*)$",
)
KIT_CONSUMER_GATE_CLOSED = "CONSUMER_GATE_CLOSED"
KIT_UPSTREAM_FINDINGS_STATUS = "CONSUMER_GATE_CLOSED_WITH_UPSTREAM_FINDINGS_RETAINED"
NEGATIVE_EXCLUSION_CLASSIFICATION = "EXCLUDED_NON_STAGE0_RUNTIME_DEPENDENCY"
FRONTEND_FULL_E2E_NEGATIVE_REL = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release/stage0-evidence/"
    "frontend-full-e2e-negative.v1.json"
)
FRONTEND_FULL_E2E_NEGATIVE_SCHEMA = (
    "mrw.formal_release.stage0.frontend_full_e2e_negative.v1"
)
FRONTEND_FULL_E2E_NEGATIVE_STATUS = (
    "OBSERVED_FAILURES_RETAINED_NOT_STAGE0_DEPENDENCIES"
)
# The completion record deliberately rewrites source prose into completion
# voice.  Keep the exact current pair per test so either side cannot drift into
# an unreviewed claim while retaining the frozen v1 evidence bytes.
NEGATIVE_REASON_BINDINGS = {
    "tests/e2e/agent-chat-writing-crossflow.spec.ts:52": (
        "The scenario requires the live Codex WebSocket and backend surface rather than the Stage 0 client or mocked interpreter boundary.",
        "Requires the live Codex WebSocket and backend surface rather than the Stage 0 client or mocked interpreter boundary.",
    ),
    "tests/e2e/real-backend-business-lines.spec.ts:200": (
        "The scenario requires a named live search-discovery endpoint and runtime data fixtures that Stage 0 does not realize.",
        "Requires a named live search-discovery endpoint and runtime data fixtures that Stage 0 does not realize.",
    ),
    "tests/e2e/real-backend-business-lines.spec.ts:264": (
        "The scenario requires live writing, knowledge-graph, and Agent runtime data that belongs to the production runtime contract after Stage 0.",
        "Requires live writing, knowledge-graph, and Agent runtime data that belongs to the production runtime contract after Stage 0.",
    ),
    "tests/e2e/runtime-smoke.spec.ts:431": (
        "The scenario waits for live graph endpoints returning HTTP 200; Stage 0 validates the client and projection contracts without asserting that runtime realization.",
        "Requires live graph endpoints returning HTTP 200; Stage 0 validates the client and projection contracts without asserting that runtime realization.",
    ),
}
_EVIDENCE_DIR_REL = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/"
    "2026-09-04-formal-production-release/stage0-evidence"
)
_RECEIPT_NAMES = {
    "frontend-npm-lint": "stage0-v2-frontend-npm-lint.log",
    "frontend-build": "stage0-v2-frontend-build.log",
    "frontend-e2e": "stage0-v2-frontend-e2e.log",
    "nonpg": "stage0-v2-nonpg.log",
    "pg": "stage0-v2-pg.log",
    "root": "stage0-v2-root.log",
    "architecture": "stage0-v2-architecture.log",
    "focused": "stage0-v4-completion-focused.log",
    "candidates": "stage0-v2-current-candidates.log",
}
def _receipt_path(name: str) -> Path:
    return _EVIDENCE_DIR_REL / _RECEIPT_NAMES[name]


COMMAND_CONTRACTS: dict[str, tuple[dict[str, str], ...]] = {
    "frontend": (
        {
            "command": "npm run lint",
            "receipt_path": _receipt_path("frontend-npm-lint").as_posix(),
        },
        {
            "command": "npm run build",
            "receipt_path": _receipt_path("frontend-build").as_posix(),
        },
        {
            "command": "bounded 10-spec Playwright Stage 0 client/mocked set",
            "observed": "85 passed; 12 explicitly migrated or real-backend-only skipped",
            "receipt_path": _receipt_path("frontend-e2e").as_posix(),
        },
    ),
    "non_pg": (
        {
            "command": "WORKFLOW_GRAPH_DB_STORE_ENABLED=false PYTHONPATH=<absolute patched-kit:repo-src:backend> main/backend/.venv311/bin/python -m pytest -q -p no:cacheprovider main/backend/tests/successor_runtime",
            "observed": "1645 passed; 119 PostgreSQL-only skips; 3 warnings",
            "receipt_path": _receipt_path("nonpg").as_posix(),
        },
    ),
    "pg": (
        {
            "command": "isolated Unix-socket PostgreSQL 37-shard successor matrix; per-shard create/dropdb --force; final trap cleanup",
            "observed": "37/37 shards; 364 passed; 0 failures; 0 errors; 0 skipped; runtime reclaimed",
            "receipt_path": _receipt_path("pg").as_posix(),
        },
    ),
    "root": (
        {
            "command": "main/backend/.venv311/bin/python -m pytest -q -p no:cacheprovider tests --ignore=tests/test_architecture.py",
            "observed": "729 passed; 53 subtests; 2 warnings",
            "receipt_path": _receipt_path("root").as_posix(),
        },
        {
            "command": "PYTHONPATH=<patched-kit:repo-src> .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_architecture.py",
            "observed": "293 passed",
            "receipt_path": _receipt_path("architecture").as_posix(),
        },
        {
            "command": "main/backend/.venv311/bin/python -m pytest -q -p no:cacheprovider tests/formal_release/test_generate_stage0_completion.py tests/formal_release/test_stage0_b13_governance_maps.py",
            "observed": "32 passed",
            "receipt_path": _receipt_path("focused").as_posix(),
        },
        {
            "command": "nine current candidate live checks with scripts/stage_family_fragment_rebind.py check-candidate",
            "observed": "C2-C9 B19 PASS; I1 B22 PASS",
            "receipt_path": _receipt_path("candidates").as_posix(),
        },
    ),
}


class CompletionError(RuntimeError):
    """Raised when completion evidence cannot be established."""


GenerationError = CompletionError
ValidationError = CompletionError


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _safe(root: Path, relative: Path | str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise CompletionError(f"path escapes repository root: {relative}")
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise CompletionError(f"path escapes repository root: {relative}") from exc
    return candidate


def _read(root: Path, relative: Path | str) -> bytes:
    safe = _safe(root, relative)
    path = root / safe
    if not path.is_file() or path.is_symlink():
        raise CompletionError(f"required input missing: {safe.as_posix()}")
    return path.read_bytes()


def _load(root: Path, relative: Path | str) -> dict[str, Any]:
    try:
        value = json.loads(_read(root, relative))
    except json.JSONDecodeError as exc:
        raise CompletionError(f"invalid JSON: {Path(relative).as_posix()}: {exc}") from exc
    if not isinstance(value, dict):
        raise CompletionError(f"JSON root must be an object: {Path(relative).as_posix()}")
    return value


def _ref(root: Path, relative: Path, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = _read(root, relative)
    out: dict[str, Any] = {"path": relative.as_posix(), "sha256": sha256_bytes(payload)}
    if extra:
        out.update(extra)
    return out


def _walk(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield key, item
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _assert_authority_false(value: Any, label: str) -> None:
    for key, item in _walk(value):
        if key == "authority":
            if isinstance(item, dict):
                if any(flag is not False for flag in item.values()):
                    raise CompletionError(f"{label} contains an authority flag that is not false")
            elif item not in {"NOT_AUTHORITY", "CANDIDATE_NOT_AUTHORITY"}:
                raise CompletionError(f"{label}.authority is not a non-authority marker")
        if key == "authoritative" and item is not False:
            raise CompletionError(f"{label}.authoritative must be false")
        if key == "authority_all_false" and item is not True:
            raise CompletionError(f"{label}.authority_all_false must be true")


def _validate_maps(root: Path) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    candidate_stages = _candidate_stages(root)
    current_families: set[str] = set()
    for relative in MAP_RELS:
        payload = _load(root, relative)
        if payload.get("status") != "ACTIVE_MUTABLE_MAP":
            raise CompletionError(f"{relative.as_posix()} is not ACTIVE_MUTABLE_MAP")
        _assert_authority_false(payload, relative.as_posix())
        current_families.update(
            _validate_map_candidate_refs(
                root, payload, relative, candidate_stages
            )
        )
        for key, value in _walk(payload):
            if key == "status" and value in {"DEFERRED", "OPEN", "IMPLEMENTATION_REQUIRED"}:
                raise CompletionError(f"{relative.as_posix()} contains unresolved status {value}")
        refs.append(_ref(root, relative, extra={"status": payload["status"]}))
    if current_families != set(FAMILIES):
        raise CompletionError(
            "governance maps do not cover exactly the selected nine current families: "
            f"{sorted(current_families)!r}"
        )
    return refs


def _require_positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CompletionError(f"freeze entry {label} must be a non-negative integer")
    return value


def _validate_frozen_plan(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return strict plan, freeze manifest, and stage-plan bindings."""
    freeze = _load(root, PLAN_FREEZE_REL)
    if freeze.get("schema_version") != PLAN_FREEZE_SCHEMA_VERSION:
        raise CompletionError("stage plan freeze schema_version drift")
    if freeze.get("status") != "FROZEN_FOR_IMPLEMENTATION_V1":
        raise CompletionError("stage plan freeze is not FROZEN_FOR_IMPLEMENTATION_V1")
    frozen_files = freeze.get("frozen_files")
    if not isinstance(frozen_files, list) or len(frozen_files) != 1:
        raise CompletionError("stage plan freeze must contain exactly one frozen file")
    entry = frozen_files[0]
    if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "bytes", "lines"}:
        raise CompletionError(
            "stage plan freeze entry must contain exactly path, sha256, bytes, and lines"
        )
    if entry["path"] != PLAN_REL.as_posix():
        raise CompletionError("stage plan freeze path drift")
    plan_raw = _read(root, PLAN_REL)
    if (
        sha256_bytes(plan_raw) != PLAN_SHA256
        or len(plan_raw) != PLAN_BYTES
        or len(plan_raw.decode("utf-8", errors="strict").splitlines()) != PLAN_LINES
    ):
        raise CompletionError(
            "frozen Stage 0 plan identity drift from the module-pinned SHA256/bytes/lines contract"
        )
    plan_sha = sha256_bytes(plan_raw)
    plan_bytes = len(plan_raw)
    plan_lines = len(plan_raw.decode("utf-8").splitlines())
    if entry["sha256"] != plan_sha:
        raise CompletionError("frozen Stage 0 plan byte drift")
    if entry["bytes"] != plan_bytes:
        raise CompletionError("frozen Stage 0 plan byte count drift")
    if entry["lines"] != plan_lines:
        raise CompletionError("frozen Stage 0 plan line count drift")
    plan_binding = {"path": PLAN_REL.as_posix(), "sha256": plan_sha}
    freeze_binding = _ref(
        root,
        PLAN_FREEZE_REL,
        extra={"schema_version": freeze["schema_version"]},
    )
    return plan_binding, freeze_binding, freeze


def _candidate_stages(root: Path) -> dict[str, str]:
    missing: list[str] = []
    for family, stage in CURRENT_CANDIDATE_STAGES.items():
        relative = _candidate_relative_for_stage(family, stage)
        if not (root / relative).is_file():
            missing.append(f"{family}={stage}")
    if missing:
        raise CompletionError(f"missing current candidate files: {', '.join(missing)}")
    return dict(CURRENT_CANDIDATE_STAGES)


def _candidate_relative(root: Path, family: str) -> Path:
    if family not in CURRENT_CANDIDATE_STAGES:
        raise CompletionError(f"unknown current candidate family: {family!r}")
    return _candidate_relative_for_stage(family, CURRENT_CANDIDATE_STAGES[family])


def _candidate_relative_for_stage(family: str, stage: str) -> Path:
    return CANDIDATE_ROOT_PARENT_REL / stage / "candidates" / family / "candidate.v2.json"


def _validate_map_candidate_refs(
    root: Path, value: Any, map_path: Path, candidate_stages: dict[str, str]
) -> set[str]:
    """Check every current candidate reference carried by a governance map."""
    current_families: set[str] = set()
    if isinstance(value, dict):
        candidate_path = value.get("candidate_path", value.get("path"))
        status = value.get("status", value.get("candidate_status"))
        if (
            isinstance(candidate_path, str)
            and candidate_path.endswith("candidate.v2.json")
            and "candidate_id" in value
        ):
            is_current = status == "CANDIDATE_VALID_NOT_AUTHORITY"
            path_parts = Path(candidate_path).parts
            path_family: str | None = None
            if is_current and "candidates" in path_parts:
                path_family = path_parts[path_parts.index("candidates") + 1]
                path_stage = candidate_stages.get(path_family)
                if path_stage is not None and path_stage not in path_parts:
                    raise CompletionError(
                        f"{map_path.as_posix()} current candidate {path_family} reference does not use "
                        f"{path_stage}: {candidate_path}"
                    )
            if not is_current:
                for item in value.values():
                    current_families.update(
                        _validate_map_candidate_refs(
                            root, item, map_path, candidate_stages
                        )
                    )
                return current_families
            try:
                raw = _read(root, candidate_path)
                parsed = json.loads(raw)
            except (CompletionError, json.JSONDecodeError) as exc:
                raise CompletionError(f"{map_path.as_posix()} candidate reference is unreadable") from exc
            if not isinstance(parsed, dict):
                raise CompletionError(f"{map_path.as_posix()} candidate reference is not an object")
            if value.get("candidate_id") != parsed.get("candidate_id"):
                raise CompletionError(f"{map_path.as_posix()} candidate_id drift")
            expected_digest = parsed.get("content_digest")
            expected_file = sha256_bytes(raw)
            if value.get("candidate_content_digest", value.get("content_digest")) != expected_digest:
                raise CompletionError(f"{map_path.as_posix()} candidate content digest drift")
            if value.get("candidate_file_sha256", value.get("file_sha256")) != expected_file:
                raise CompletionError(f"{map_path.as_posix()} candidate file digest drift")
            family = parsed.get("family")
            if family not in FAMILIES:
                raise CompletionError(
                    f"{map_path.as_posix()} current candidate has unexpected family {family!r}"
                )
            if path_family is not None and path_family != family:
                raise CompletionError(
                    f"{map_path.as_posix()} current candidate path/family mismatch: "
                    f"{path_family!r} != {family!r}"
                )
            expected_stage = candidate_stages.get(family)
            if expected_stage is None or expected_stage not in Path(candidate_path).parts:
                raise CompletionError(
                    f"{map_path.as_posix()} current candidate {family} reference does not use "
                    f"{expected_stage}: {candidate_path}"
                )
            declared_stage = value.get("stage", value.get("candidate"))
            if declared_stage is not None and declared_stage != expected_stage:
                raise CompletionError(
                    f"{map_path.as_posix()} current candidate {family} stage drift: "
                    f"{declared_stage!r} != {expected_stage!r}"
                )
            current_families.add(family)
        for item in value.values():
            current_families.update(
                _validate_map_candidate_refs(
                    root, item, map_path, candidate_stages
                )
            )
    elif isinstance(value, list):
        for item in value:
            current_families.update(
                _validate_map_candidate_refs(
                    root, item, map_path, candidate_stages
                )
            )
    return current_families


def _candidate_row(root: Path, family: str) -> dict[str, Any]:
    relative = _candidate_relative(root, family)
    payload = _load(root, relative)
    raw = _read(root, relative)
    if payload.get("family") != family or payload.get("schema") != "mrw.family_fragment_rebind.candidate.v2":
        raise CompletionError(f"candidate {family} has unexpected schema/family")
    if payload.get("status") != "CANDIDATE_VALID_NOT_AUTHORITY":
        raise CompletionError(f"candidate {family} is not CANDIDATE_VALID_NOT_AUTHORITY")
    _assert_authority_false(payload, f"candidate {family}")
    candidate_id = payload.get("candidate_id")
    content_digest = payload.get("content_digest")
    if not isinstance(candidate_id, str) or HEX64.fullmatch(candidate_id) is None:
        raise CompletionError(f"candidate {family} has invalid candidate_id")
    if not isinstance(content_digest, str) or HEX64.fullmatch(content_digest) is None:
        raise CompletionError(f"candidate {family} has invalid content_digest")
    body = {key: item for key, item in payload.items() if key != "content_digest"}
    if sha256_bytes(canonical_json(body)) != content_digest:
        raise CompletionError(f"candidate {family} content_digest mismatch")
    return {
        "family": family,
        "path": relative.as_posix(),
        "candidate_id": candidate_id,
        "content_digest": content_digest,
        "file_sha256": sha256_bytes(raw),
        "status": payload["status"],
    }


def _loss_summary(root: Path, name: str, relative: Path) -> dict[str, Any]:
    payload = _load(root, relative)
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise CompletionError(f"{name} declared-loss record has no items")
    counts = {decision: 0 for decision in sorted(ALLOWED_LOSS_DECISIONS)}
    for item in items:
        if not isinstance(item, dict):
            raise CompletionError(f"{name} declared-loss item is not an object")
        decision = item.get("decision")
        if decision not in ALLOWED_LOSS_DECISIONS:
            raise CompletionError(f"{name} has unresolved declared-loss decision: {decision!r}")
        counts[decision] += 1
    return _ref(root, relative, extra={"status": payload.get("status"), "item_count": len(items), "decision_counts": counts})


def _require_commands(root: Path, evidence: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    commands = evidence.get("commands")
    if not isinstance(commands, dict):
        raise CompletionError("commands must be an object with the exact pg/non_pg/root/frontend groups")
    if set(commands) != set(COMMAND_CONTRACTS):
        raise CompletionError("command group set drifted from the Stage 0 contract")
    normalized: dict[str, list[dict[str, Any]]] = {}
    for group in ("pg", "non_pg", "root", "frontend"):
        rows = commands.get(group)
        if not isinstance(rows, list) or not rows:
            raise CompletionError(f"commands.{group} must be a non-empty list")
        normalized_rows: list[dict[str, Any]] = []
        expected_rows = COMMAND_CONTRACTS[group]
        if len(rows) != len(expected_rows):
            raise CompletionError(f"commands.{group} row count drifted from the Stage 0 contract")
        for row, expected in zip(rows, expected_rows, strict=True):
            if not isinstance(row, dict) or not isinstance(row.get("command"), str) or not row["command"].strip():
                raise CompletionError(f"commands.{group} contains an invalid command row")
            expected_fields = {"command", "result", "exit_code", "receipt"}
            if "observed" in expected:
                expected_fields.add("observed")
            if set(row) != expected_fields:
                raise CompletionError(f"commands.{group} row fields drifted from the Stage 0 contract")
            if row["command"] != expected["command"]:
                raise CompletionError(f"commands.{group} command identity drifted from the Stage 0 contract")
            if row.get("result") != PASS:
                raise CompletionError(f"commands.{group} has non-PASS result: {row.get('result')!r}")
            exit_code = row.get("exit_code")
            if isinstance(exit_code, bool) or not isinstance(exit_code, int) or exit_code != 0:
                raise CompletionError(f"commands.{group} row must record exit_code 0")
            if "receipt" not in row:
                raise CompletionError(f"commands.{group} row requires a nested evidence receipt")
            receipt = row["receipt"]
            if not isinstance(receipt, dict) or set(receipt) != {"path", "sha256"}:
                raise CompletionError(f"commands.{group} receipt must contain exactly path and sha256")
            relative = receipt.get("path")
            expected_sha = receipt.get("sha256")
            if relative != expected["receipt_path"]:
                raise CompletionError(f"commands.{group} receipt path drifted from the Stage 0 contract")
            try:
                safe_relative = _safe(root, relative)
                raw = _read(root, safe_relative)
            except CompletionError as exc:
                raise CompletionError(f"commands.{group} receipt is invalid: {exc}") from exc
            actual_sha = sha256_bytes(raw)
            if not isinstance(expected_sha, str) or expected_sha != actual_sha:
                raise CompletionError(f"commands.{group} receipt sha256 drift: {Path(relative).as_posix()}")
            if "observed" not in expected:
                if "observed" in row:
                    raise CompletionError(f"commands.{group} observed summary drifted from the Stage 0 contract")
            elif row.get("observed") != expected["observed"]:
                raise CompletionError(f"commands.{group} observed summary drifted from the Stage 0 contract")
            _validate_command_log(group, row, raw, root)
            normalized_rows.append(dict(row))
        normalized[group] = normalized_rows
    return normalized


def _single_match(pattern: str, text: str, label: str) -> re.Match[str]:
    matches = list(re.finditer(pattern, text, flags=re.MULTILINE))
    if len(matches) != 1:
        raise CompletionError(f"receipt log summary is not uniquely observable: {label}")
    return matches[0]


def _validate_receipt_failure_signals(text: str) -> None:
    for pattern in RECEIPT_FAILURE_PATTERNS:
        match = re.search(pattern, text)
        if match:
            line = text[: match.end()].splitlines()[-1][:240]
            raise CompletionError(f"receipt log contains a failure signal: {line}")


def _validate_command_log(group: str, row: dict[str, Any], raw: bytes, root: Path) -> None:
    text = raw.decode("utf-8", errors="replace")
    _validate_receipt_failure_signals(text)
    observed = row.get("observed")
    if group == "frontend":
        if row["command"] == "npm run lint":
            if "> eslint ." not in text:
                raise CompletionError("frontend lint receipt log lacks its eslint summary")
            return
        if row["command"] == "npm run build":
            if "✓ built in " not in text:
                raise CompletionError("frontend build receipt log lacks its build summary")
            return
        passed = int(_single_match(r"^\s+(\d+) passed \(", text, "frontend e2e").group(1))
        skipped = int(_single_match(r"^\s+(\d+) skipped\s*$", text, "frontend e2e").group(1))
        if observed != f"{passed} passed; {skipped} explicitly migrated or real-backend-only skipped":
            raise CompletionError("frontend e2e receipt counts drift from observed summary")
        return
    if group == "non_pg":
        match = _single_match(r"^(\d+) passed, (\d+) skipped, (\d+) warnings in ", text, "non-PG suite")
        if observed != f"{match[1]} passed; {match[2]} PostgreSQL-only skips; {match[3]} warnings":
            raise CompletionError("non-PG receipt counts drift from observed summary")
        return
    if group == "pg":
        match = _single_match(
            r"^PG_MATRIX_RESULT shards=(\d+) passed_shards=(\d+) failed_shards=(\d+) "
            r"tests=(\d+) failures=(\d+) errors=(\d+) skipped=(\d+)$",
            text,
            "PG matrix",
        )
        expected = (
            f"{match[2]}/{match[1]} shards; {match[4]} passed; {match[5]} failures; "
            f"{match[6]} errors; {match[7]} skipped; runtime reclaimed"
        )
        if observed != expected:
            raise CompletionError("PG receipt counts drift from observed summary")
        return
    if group == "root":
        if row["command"].endswith("tests --ignore=tests/test_architecture.py"):
            match = _single_match(
                r"^(\d+) passed, (\d+) warnings, (\d+) subtests passed in ",
                text,
                "root suite",
            )
            if observed != f"{match[1]} passed; {match[3]} subtests; {match[2]} warnings":
                raise CompletionError("root receipt counts drift from observed summary")
            return
        if row["command"].endswith("tests/test_architecture.py"):
            match = _single_match(r"^(\d+) passed in ", text, "architecture suite")
            if observed != f"{match[1]} passed":
                raise CompletionError("architecture receipt counts drift from observed summary")
            return
        if "test_generate_stage0_completion.py" in row["command"]:
            match = _single_match(r"^(\d+) passed in ", text, "completion focused suite")
            if observed != f"{match[1]} passed":
                raise CompletionError("completion focused receipt counts drift from observed summary")
            return
        rows = re.findall(r"FAMILY=([^\n]+)\n([^\n]+)\nEXIT=(\d+)", text)
        if len(rows) != len(FAMILIES) or [row[0] for row in rows] != list(FAMILIES):
            raise CompletionError("current-candidate receipt does not bind exactly nine families in order")
        for family, payload, exit_code in rows:
            if exit_code != "0":
                raise CompletionError(f"current-candidate receipt {family} has nonzero EXIT")
            try:
                claim = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise CompletionError(f"current-candidate receipt {family} is invalid JSON") from exc
            fresh = _candidate_row(root, family)
            if claim != {
                "candidate_id": fresh["candidate_id"],
                "family": family,
                "status": fresh["status"],
            }:
                raise CompletionError(f"current-candidate receipt {family} identity drift")
        return
    raise CompletionError(f"unknown command contract group: {group}")


def _require_non_pass_classification(
    root: Path, evidence: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    skip_block = evidence.get("skip_block", [])
    negatives = evidence.get("negative_findings", [])
    if not isinstance(skip_block, list) or not isinstance(negatives, list):
        raise CompletionError("skip_block and negative_findings must be lists")
    normalized_skip: list[dict[str, Any]] = []
    for row in skip_block:
        if not isinstance(row, dict) or row.get("classification") not in {"SKIP", "BLOCKED"}:
            raise CompletionError("skip_block rows require classification SKIP or BLOCKED")
        if not isinstance(row.get("owner"), str) or not row["owner"].strip() or not isinstance(row.get("reason"), str) or not row["reason"].strip():
            raise CompletionError("skip_block rows require owner and reason")
        raise CompletionError("any SKIP/BLOCKED result fails closed")
    if not isinstance(negatives, list):
        raise CompletionError("negative_findings must be a list")
    for row in negatives:
        if not isinstance(row, dict):
            raise CompletionError("negative_findings rows must be objects")
        if row.get("status") == PASS or row.get("result") == PASS:
            raise CompletionError("negative finding must not be marked PASS")
        if row.get("classification") != NEGATIVE_EXCLUSION_CLASSIFICATION:
            raise CompletionError(
                f"negative finding must use {NEGATIVE_EXCLUSION_CLASSIFICATION}"
            )
        if row.get("observed_result") != "FAIL":
            raise CompletionError("negative finding must preserve observed_result FAIL")
        if not isinstance(row.get("owner"), str) or not row["owner"].strip():
            raise CompletionError("negative finding is unowned")
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            raise CompletionError("negative finding requires reason")
        if not isinstance(row.get("test"), str) or not row["test"].strip():
            raise CompletionError("negative finding requires test")
    _validate_frontend_full_e2e_negatives(root, negatives)
    return normalized_skip, [dict(row) for row in negatives]


def _validate_frontend_full_e2e_negatives(
    root: Path, negatives: list[Any]
) -> None:
    source = _load(root, FRONTEND_FULL_E2E_NEGATIVE_REL)
    if source.get("schema") != FRONTEND_FULL_E2E_NEGATIVE_SCHEMA:
        raise CompletionError("frontend full E2E negative evidence schema drift")
    if source.get("status") != FRONTEND_FULL_E2E_NEGATIVE_STATUS:
        raise CompletionError("frontend full E2E negative evidence status drift")
    _assert_authority_false(
        source, FRONTEND_FULL_E2E_NEGATIVE_REL.as_posix()
    )
    source_rows = source.get("findings")
    if not isinstance(source_rows, list) or not source_rows:
        raise CompletionError("frontend full E2E negative evidence has no findings")
    summary = source.get("summary")
    if (
        not isinstance(summary, dict)
        or summary.get("failed") != len(source_rows)
    ):
        raise CompletionError("frontend full E2E negative evidence summary count drift")
    if len(negatives) != len(source_rows):
        raise CompletionError(
            "frontend full E2E negative finding count drift from bound evidence"
        )
    raw = _read(root, FRONTEND_FULL_E2E_NEGATIVE_REL)
    expected_evidence = {
        "path": FRONTEND_FULL_E2E_NEGATIVE_REL.as_posix(),
        "sha256": sha256_bytes(raw),
    }
    seen_ids: set[str] = set()
    seen_tests: set[str] = set()
    for source_row, row in zip(source_rows, negatives, strict=True):
        if not isinstance(source_row, dict):
            raise CompletionError("frontend full E2E negative source finding is not an object")
        if set(source_row) != {
            "test",
            "owner",
            "reason",
            "stage0_dependency",
            "observed_result",
        }:
            raise CompletionError("frontend full E2E negative source finding fields drifted")
        receipt = row.get("evidence")
        if not isinstance(receipt, dict) or set(receipt) != {"path", "sha256"}:
            raise CompletionError("negative finding requires an evidence receipt")
        if not isinstance(receipt["path"], str):
            raise CompletionError("negative finding evidence path must be a string")
        if receipt["path"] != expected_evidence["path"]:
            raise CompletionError("negative finding evidence binding drifted")
        if receipt != expected_evidence:
            raise CompletionError("negative finding evidence sha256 drift")
        if row.get("stage0_dependency") is not False:
            raise CompletionError("negative finding must declare stage0_dependency false")
        test = row.get("test")
        if not isinstance(test, str) or test in seen_tests:
            raise CompletionError("negative finding tests must be unique and bound")
        seen_tests.add(test)
        identity = NEGATIVE_REASON_BINDINGS.get(test)
        if identity is None:
            raise CompletionError("negative finding is outside the bound frontend full E2E set")
        source_reason, completion_reason = identity
        for key in ("owner", "test", "observed_result", "stage0_dependency"):
            if row.get(key) != source_row.get(key):
                raise CompletionError(
                    f"negative finding {key} drift from bound frontend full E2E evidence"
                )
        if source_row.get("reason") != source_reason:
            raise CompletionError("negative finding source reason drift")
        if row.get("reason") != completion_reason:
            raise CompletionError("negative finding completion reason drift")
        finding_id = row.get("id")
        if not isinstance(finding_id, str) or not finding_id or finding_id in seen_ids:
            raise CompletionError("negative finding id must be a unique string")
        seen_ids.add(finding_id)


def _kit_summary(root: Path, kit: dict[str, Any], kit_relative: Path) -> dict[str, Any]:
    if kit.get("schema") != "stage0-kit-applicability.v1":
        raise CompletionError("bound kit applicability file has unexpected schema")
    if kit.get("status") != KIT_UPSTREAM_FINDINGS_STATUS:
        raise CompletionError("bound kit applicability consumer gate is not closed with upstream findings retained")
    languages = kit.get("languages")
    if not isinstance(languages, dict) or set(languages) != {"python", "typescript", "rust"}:
        raise CompletionError("bound kit applicability must bind python, typescript, and rust")
    python = languages.get("python")
    if not isinstance(python, dict) or python.get("consumer_gate_status") != KIT_CONSUMER_GATE_CLOSED:
        raise CompletionError("kit python consumer gate is not CONSUMER_GATE_CLOSED")

    derived_languages: dict[str, Any] = {}
    for name in ("python", "typescript", "rust"):
        row = languages[name]
        if not isinstance(row, dict):
            raise CompletionError(f"kit {name} applicability must be an object")
        upstream = row.get("upstream_execution")
        if not isinstance(upstream, dict) or not isinstance(upstream.get("status"), str) or not isinstance(upstream.get("ceiling"), str):
            raise CompletionError(f"kit {name} upstream status or ceiling is missing")
        derived_languages[name] = {
            "consumer_gate_status": row.get("consumer_gate_status"),
            "upstream_execution_status": upstream["status"],
            "upstream_execution_ceiling": upstream["ceiling"],
            "ceiling": row.get("ceiling"),
        }
        if name == "python" and derived_languages[name]["consumer_gate_status"] != KIT_CONSUMER_GATE_CLOSED:
            raise CompletionError("kit python consumer gate is not CONSUMER_GATE_CLOSED")

    ceiling = kit.get("ceiling")
    if not isinstance(ceiling, list) or any(not isinstance(item, str) or not item for item in ceiling):
        raise CompletionError("bound kit applicability ceiling must be a non-empty string list")
    _assert_authority_false(kit, KIT_REL.as_posix())
    kit_sha256 = sha256_bytes(_read(root, kit_relative))
    return {
        "result": PASS,
        "derived_from": {"path": kit_relative.as_posix(), "sha256": kit_sha256},
        "status": kit["status"],
        "languages": derived_languages,
        "ceiling": list(ceiling),
    }


def _assert_current_byte_rebind_evidence(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise CompletionError(f"{label} evidence must be an object")
    if set(value) != {"result", "run_id", "authority", "candidate_stages"}:
        raise CompletionError(f"{label} evidence fields drifted")
    if value.get("result") != PASS:
        raise CompletionError(
            f"{label} result must be PASS: {value.get('result')!r}"
        )
    authority = value.get("authority")
    if not isinstance(authority, dict) or not authority:
        raise CompletionError(f"{label} must declare non-empty authority flags")
    if any(flag is not False for flag in authority.values()):
        raise CompletionError(f"{label} authority flags must all be false")
    if value.get("candidate_stages") != CURRENT_CANDIDATE_STAGES:
        raise CompletionError(
            f"{label}.candidate_stages must be exactly the current nine-family mapping"
        )
    _assert_authority_false(value, f"{label} evidence")


def build_completion_record(
    root: Path, evidence: dict[str, Any]
) -> Annotated[
    dict[str, Any],
    "kit:non-authoritative derived_as=external_claim "
    "fact_source=stage0_evidence_inputs "
    "witness=test:test_build_binds_mixed_lineage_and_nine_candidates",
]:
    """Build a deterministic record, raising on every fail-closed condition."""
    if not isinstance(evidence, dict):
        raise CompletionError("evidence root must be an object")
    if "b19" in evidence:
        raise CompletionError(
            "legacy b19 evidence key is rejected; use current_byte_rebind"
        )
    rebind_evidence = evidence.get(CURRENT_BYTE_REBIND_EVIDENCE_KEY)
    _assert_current_byte_rebind_evidence(
        rebind_evidence, CURRENT_BYTE_REBIND_EVIDENCE_KEY
    )
    observed_at = evidence.get("observed_at")
    if not isinstance(observed_at, str) or not observed_at.strip():
        raise CompletionError("observed_at is required for deterministic binding")

    stage_plan, stage_plan_freeze, _ = _validate_frozen_plan(root)

    baseline_raw = _read(root, BASELINE_REL)
    try:
        baseline_value = json.loads(baseline_raw)
    except json.JSONDecodeError as exc:
        raise CompletionError("arch-baseline.json is invalid JSON") from exc
    if not isinstance(baseline_value, list) or baseline_value:
        raise CompletionError("architecture baseline is not empty")
    ledger = _load(root, LEDGER_REL)
    entries = ledger.get("entries")
    if not isinstance(entries, dict):
        raise CompletionError("resolution ledger entries must be an object")
    if any(not isinstance(row, dict) or row.get("status") != "ACCEPTED" for row in entries.values()):
        raise CompletionError("resolution ledger contains non-ACCEPTED entry")

    kit = _load(root, KIT_REL)
    _assert_authority_false(kit, KIT_REL.as_posix())
    kit_claim = evidence.get("kit")
    if kit_claim is not None:
        if not isinstance(kit_claim, dict) or set(kit_claim) != {"result"} or kit_claim.get("result") != PASS:
            raise CompletionError("kit evidence may only declare result PASS or be omitted")
    derived_kit = _kit_summary(root, kit, KIT_REL)

    maps = _validate_maps(root)
    candidate_stages = _candidate_stages(root)
    candidates = [_candidate_row(root, family) for family in FAMILIES]
    commands = _require_commands(root, evidence)
    skip_block, negatives = _require_non_pass_classification(root, evidence)
    losses = {name: _loss_summary(root, name, path) for name, path in DECLARED_LOSS_REL.items()}

    authority = {key: False for key in AUTHORITY_KEYS}
    record: dict[str, Any] = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "record_id": "stage0-functorial-refactor-completion-v4",
        "stage": "STAGE_0",
        "status": STATUS,
        "authoritative": False,
        "derived_as": "external_claim",
        "candidate_commit": None,
        "candidate_tree": None,
        "candidate": {"commit": None, "tree": None},
        "authority": authority,
        "observed_at": observed_at,
        CURRENT_BYTE_REBIND_EVIDENCE_KEY: dict(rebind_evidence),
        "kit": derived_kit,
        "bindings": {
            "stage_plan": stage_plan,
            "stage_plan_freeze": stage_plan_freeze,
            "baseline": {"path": BASELINE_REL.as_posix(), "sha256": sha256_bytes(baseline_raw), "entry_count": 0},
            "ledger": {"path": LEDGER_REL.as_posix(), "sha256": sha256_bytes(_read(root, LEDGER_REL)), "entry_count": len(entries)},
            "declared_loss": losses,
            "kit_applicability": _ref(root, KIT_REL, extra={"status": kit.get("status")}),
            "governance_maps": maps,
            "candidate_stages": candidate_stages,
            "current_candidates": candidates,
        },
        "commands": commands,
        "skip_block": skip_block,
        "negative_findings": negatives,
    }
    validate_completion_record(root, record)
    return record


def validate_completion_record(root: Path, record: dict[str, Any]) -> None:
    """Validate a generated record and all source bytes it claims."""
    if record.get("schema") != SCHEMA or record.get("schema_version") != SCHEMA_VERSION:
        raise CompletionError("unexpected completion record schema")
    if record.get("record_id") != "stage0-functorial-refactor-completion-v4":
        raise CompletionError("unexpected completion record_id")
    if record.get("status") != STATUS:
        raise CompletionError("completion status is not the sole permitted Stage 0 status")
    if (
        record.get("authoritative") is not False
        or record.get("derived_as") != "external_claim"
        or record.get("candidate_commit") is not None
        or record.get("candidate_tree") is not None
        or record.get("candidate") != {"commit": None, "tree": None}
    ):
        raise CompletionError("Stage 0 completion record must be non-authoritative with null candidate identity")
    authority = record.get("authority")
    if not isinstance(authority, dict) or any(authority.get(key) is not False for key in AUTHORITY_KEYS):
        raise CompletionError("all Stage 0 authority flags must be false")
    _assert_authority_false(record, "completion record")
    bindings = record.get("bindings")
    if not isinstance(bindings, dict):
        raise CompletionError("bindings are required")
    if "b19" in record:
        raise CompletionError(
            "legacy b19 evidence key is rejected; use current_byte_rebind"
        )
    _assert_current_byte_rebind_evidence(
        record.get(CURRENT_BYTE_REBIND_EVIDENCE_KEY),
        CURRENT_BYTE_REBIND_EVIDENCE_KEY,
    )
    if not isinstance(record.get("kit"), dict):
        raise CompletionError("derived kit summary is required")
    if record["kit"] != _kit_summary(root, _load(root, KIT_REL), KIT_REL):
        raise CompletionError("derived kit summary drift")
    _assert_authority_false(record["kit"], "kit evidence")
    _require_commands(root, record)
    _require_non_pass_classification(root, record)
    expected_stage_plan, expected_plan_freeze, _ = _validate_frozen_plan(root)
    if bindings.get("stage_plan") != expected_stage_plan:
        raise CompletionError("stage plan binding drift")
    if bindings.get("stage_plan_freeze") != expected_plan_freeze:
        raise CompletionError("stage_plan_freeze binding drift")
    for key, relative in (("baseline", BASELINE_REL), ("ledger", LEDGER_REL), ("kit_applicability", KIT_REL)):
        ref = bindings.get(key)
        if not isinstance(ref, dict) or ref.get("path") != relative.as_posix() or ref.get("sha256") != sha256_bytes(_read(root, relative)):
            raise CompletionError(f"{key} binding drift")
    baseline_raw = _read(root, BASELINE_REL)
    try:
        baseline_value = json.loads(baseline_raw)
    except json.JSONDecodeError as exc:
        raise CompletionError("arch-baseline.json is invalid JSON") from exc
    if not isinstance(baseline_value, list):
        raise CompletionError("architecture baseline must be a list")
    if bindings["baseline"].get("entry_count") != len(baseline_value):
        raise CompletionError("baseline entry_count drift")
    ledger_value = _load(root, LEDGER_REL)
    ledger_entries = ledger_value.get("entries")
    if not isinstance(ledger_entries, dict):
        raise CompletionError("resolution ledger entries must be an object")
    if any(not isinstance(row, dict) or row.get("status") != "ACCEPTED" for row in ledger_entries.values()):
        raise CompletionError("resolution ledger contains non-ACCEPTED entry")
    if bindings["ledger"].get("entry_count") != len(ledger_entries):
        raise CompletionError("ledger entry_count drift")
    map_refs = bindings.get("governance_maps")
    if not isinstance(map_refs, list) or [item.get("path") for item in map_refs if isinstance(item, dict)] != [item.as_posix() for item in MAP_RELS]:
        raise CompletionError("governance map binding set drift")
    for ref, relative in zip(map_refs, MAP_RELS, strict=True):
        if ref.get("sha256") != sha256_bytes(_read(root, relative)):
            raise CompletionError(f"governance map binding drift: {relative.as_posix()}")
    rows = bindings.get("current_candidates")
    if not isinstance(rows, list) or [row.get("family") for row in rows] != list(FAMILIES):
        raise CompletionError("current candidate family set/order is not exactly the nine Stage 0 families")
    if "candidate_stage" in bindings:
        raise CompletionError("legacy unified candidate_stage binding is rejected")
    if bindings.get("candidate_stages") != _candidate_stages(root):
        raise CompletionError("current candidate stage drift")
    for row in rows:
        family = row["family"]
        fresh = _candidate_row(root, family)
        if row != fresh:
            raise CompletionError(
                f"current candidate {family} byte, identity, status, or non-authority binding drift"
            )
    _validate_maps(root)
    for key, path in DECLARED_LOSS_REL.items():
        expected = _loss_summary(root, key, path)
        if bindings.get("declared_loss", {}).get(key) != expected:
            raise CompletionError(f"declared-loss binding drift: {key}")


def write_create_only(root: Path, record: dict[str, Any], output: Path | None = None) -> Path:
    destination = (output or (root / OUTPUT_REL)).resolve()
    if destination.exists():
        try:
            shown = destination.relative_to(root.resolve()).as_posix()
        except ValueError:
            shown = str(destination)
        raise CompletionError(f"create-only target already exists: {shown}")
    try:
        destination.relative_to(root.resolve())
    except ValueError as exc:
        raise CompletionError("output escapes repository root") from exc
    payload = (json.dumps(record, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return destination


# Stable short aliases for focused callers and tests.
build_record = build_completion_record
validate_record = validate_completion_record
write_record = write_create_only


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument(
        "--evidence",
        type=Path,
        help="JSON input containing final current-byte rebind and command evidence",
    )
    parser.add_argument("--validate", type=Path, help="validate an existing completion record")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--write", action="store_true", help="create the target record; otherwise print deterministic JSON")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.repo_root.resolve()
    try:
        if args.validate:
            raw = args.validate.read_bytes()
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise CompletionError("record JSON root must be an object")
            validate_completion_record(root, value)
            print("PASS")
            return 0
        if not args.evidence:
            raise CompletionError("--evidence is required unless --validate is used")
        evidence = json.loads(args.evidence.read_text(encoding="utf-8"))
        record = build_completion_record(root, evidence)
        if args.write:
            print(write_create_only(root, record, args.output))
        else:
            print(json.dumps(record, ensure_ascii=True, indent=2, sort_keys=True))
        return 0
    except (CompletionError, OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
