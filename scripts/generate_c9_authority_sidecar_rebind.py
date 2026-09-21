#!/usr/bin/env python3
# ruff: noqa: TRY003
"""Prepare a non-authoritative, versioned C9 authority-sidecar rebind input.

The checked-in C9 v1 sidecar and the B7/B8 evidence candidates are immutable
predecessors.  This command only creates a new sidecar *input* below a fresh
Stage 0 evidence directory (B13 through B23); it never edits governance maps, frozen
evidence, or the predecessor sidecar itself.  A sidecar input is a projection
of exact current-checkout bytes and therefore carries an all-false authority
ceiling.
"""

from __future__ import annotations

import argparse
import ast
import datetime
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Annotated, Any


REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_REL = Path(
    "development/latest-dev-docs/development-plans/CURRENT_DEV/2026-08-30-functorial-successor-migration/evidence"
)
EXACT_REBIND_REL = EVIDENCE_REL / "exact-byte-rebind"
STAGE_PREFIX = "stage-b13-"
DEFAULT_STAGE = "stage-b13-2026-09-05"
DEFAULT_B15_STAGE = "stage-b15-2026-09-05"
DEFAULT_B16_STAGE = "stage-b16-2026-09-05"
DEFAULT_B17_STAGE = "stage-b17-2026-09-05"
DEFAULT_B18_STAGE = "stage-b18-2026-09-05"
DEFAULT_B19_STAGE = "stage-b19-2026-09-05"
DEFAULT_B23_STAGE = "stage-b23-2026-09-05"
SIDECAR_INPUT_NAME = "sidecar-inputs/C9.v2.json"
B15_SIDECAR_INPUT_NAME = "sidecar-inputs/C9.v3.json"
B16_SIDECAR_INPUT_NAME = "sidecar-inputs/C9.v4.json"
B17_SIDECAR_INPUT_NAME = "sidecar-inputs/C9.v5.json"
B18_SIDECAR_INPUT_NAME = "sidecar-inputs/C9.v6.json"
B19_SIDECAR_INPUT_NAME = "sidecar-inputs/C9.v7.json"
B23_SIDECAR_INPUT_NAME = "sidecar-inputs/C9.v8.json"

SCHEMA = "mrw.governance.generated_evidence_authority_sidecar.c9.v2"
SIDECAR_ID = "c9.generated-evidence-authority-sidecar.v2"
B15_SCHEMA = "mrw.governance.generated_evidence_authority_sidecar.c9.v3"
B15_SIDECAR_ID = "c9.generated-evidence-authority-sidecar.v3"
B15_C9_AMENDMENT = "STAGE_B15_C9_EXACT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY"
B16_SCHEMA = "mrw.governance.generated_evidence_authority_sidecar.c9.v4"
B16_SIDECAR_ID = "c9.generated-evidence-authority-sidecar.v4"
B16_C9_AMENDMENT = "STAGE_B16_C9_EXACT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY"
B17_SCHEMA = "mrw.governance.generated_evidence_authority_sidecar.c9.v5"
B17_SIDECAR_ID = "c9.generated-evidence-authority-sidecar.v5"
B17_C9_AMENDMENT = "STAGE_B17_C9_EXACT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY"
B18_SCHEMA = "mrw.governance.generated_evidence_authority_sidecar.c9.v6"
B18_SIDECAR_ID = "c9.generated-evidence-authority-sidecar.v6"
B18_C9_AMENDMENT = "STAGE_B18_C9_EXACT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY"
B19_SCHEMA = "mrw.governance.generated_evidence_authority_sidecar.c9.v7"
B19_SIDECAR_ID = "c9.generated-evidence-authority-sidecar.v7"
B19_C9_AMENDMENT = "STAGE_B19_C9_EXACT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY"
B23_SCHEMA = "mrw.governance.generated_evidence_authority_sidecar.c9.v8"
B23_SIDECAR_ID = "c9.generated-evidence-authority-sidecar.v8"
B23_C9_AMENDMENT = "STAGE_B23_C9_EXACT_BYTE_REBIND_CANDIDATE_NOT_AUTHORITY"
PREDECESSOR_REL = Path("docs/governance/generated-evidence-authority-sidecar.c9.v1.json")
B13_SIDECAR_REL = EXACT_REBIND_REL / "stage-b13-2026-09-05/sidecar-inputs/C9.v2.json"
B15_SIDECAR_REL = EXACT_REBIND_REL / "stage-b15-2026-09-05/sidecar-inputs/C9.v3.json"
B16_SIDECAR_REL = EXACT_REBIND_REL / "stage-b16-2026-09-05/sidecar-inputs/C9.v4.json"
B17_SIDECAR_REL = EXACT_REBIND_REL / "stage-b17-2026-09-05/sidecar-inputs/C9.v5.json"
B18_SIDECAR_REL = EXACT_REBIND_REL / "stage-b18-2026-09-05/sidecar-inputs/C9.v6.json"
B23_PREDECESSOR_REL = EXACT_REBIND_REL / "stage-b19-2026-09-05/sidecar-inputs/C9.v7.json"
B7_STAGE_REL = EXACT_REBIND_REL / "stage-b7-2026-09-05"
B8_STAGE_REL = EXACT_REBIND_REL / "stage-b8-2026-09-05"
B8_CANDIDATE_REL = B8_STAGE_REL / "candidates/C9/candidate.v2.json"

SOURCE_REL = Path("main/backend/app/successor_runtime/substrate/projections/c9_sources.py")
CANONICAL_SOURCE_REL = Path("main/backend/app/successor_runtime/substrate/postgres/c9_projection_sources.py")
SPEC_REL = EVIDENCE_REL / "capability-specs/C9.3.v1.json"
BUILD_REL = EVIDENCE_REL / "capability-spec-builds/C9.3.BuildManifest.v1.json"

PROJECTION_FUNCTIONS = (
    "build_agent_session_payload",
    "build_research_graph_payload",
    "build_search_payload",
)
CANONICAL_FUNCTIONS = (
    "read_runtime_session_source",
    "read_research_graph_source",
    "read_c7_search_source",
    "build_semantic_source_closure",
)
WITNESS_TESTS = (
    "main/backend/tests/successor_runtime/test_p4_c9_1_facade_contracts.py",
    "main/backend/tests/successor_runtime/test_p4_c9_2_projector_registry.py",
    "main/backend/tests/successor_runtime/test_p4_c9_3_transport_dto.py",
    "main/backend/tests/successor_runtime/test_p4_c9_4_evidence_generator.py",
    "main/backend/tests/successor_runtime/test_p4_c9_5_p1_consistency_and_public_payload.py",
    "main/backend/tests/successor_runtime/test_p4_c9_6_fragment_stability.py",
)

# Hashes are input guards, not authority grants.  They make predecessor drift
# fail closed before a new stage directory can be created.
PREDECESSOR_HASHES = {
    PREDECESSOR_REL: "63f4bae0476a968386faec6049f95d0faa414d79bea1f6891868638e12692b15",
    B7_STAGE_REL / "fragments/C9.json": "32312fec9107cbaa1d4dd3191fb0bf6c7af3f979c391c3aae70dc4f4beca2bbe",
    B7_STAGE_REL / "manifests/C9.json": "a486887a1db43e0d4b874c8ef43cc33988ceb0702c07b2d374cf7ef3dce13c4d",
    B7_STAGE_REL / "candidates/C9/candidate.v2.json": (
        "8f494dd84555fd7a307f1bf6002894897ad7651a6656e0ff12da5af4396e0c40"
    ),
    B8_STAGE_REL / "fragments/C9.json": "94996b52e41412a8c181b653bb509656b012f425d1762160698d823421e3ba0e",
    B8_STAGE_REL / "manifests/C9.json": "bc4deb263967c38e9712d23109444b4873b757ec576b42fc826b00e32f358024",
    B8_CANDIDATE_REL: "b6d977d69a234e0fd71a16dbb2c73d714d7b4308531a870a1563bd0f5226afd4",
}
B13_PREDECESSOR_HASHES = {
    B13_SIDECAR_REL: "2155083e699725c78eebf8fd6ecae008c5bf4f97c8cd28c103b777e821e8b2da",
}
B15_PREDECESSOR_HASHES = {
    B15_SIDECAR_REL: "d1c4472a1efc1b64d4a5b928547882eb61ed82ac314cd32b3ab14d9e41507b37",
}
B16_PREDECESSOR_HASHES = {
    B16_SIDECAR_REL: "eb39d379fb1696aaa8026039aceec0c191ee3c7e085fbb4fee9db3d3366b32cc",
}
B17_PREDECESSOR_HASHES = {
    B17_SIDECAR_REL: "dc3b7a9296ea2f358778081b8a1aa65a5383526f201192098c424dd6ef49ae78",
}
B19_PREDECESSOR_HASHES = {
    B18_SIDECAR_REL: "ef4ff2afea6781c5368dc5318ef92f0d84012b0c2dd3728c2c46582f25dfe13d",
}
B23_PREDECESSOR_HASHES = {
    B23_PREDECESSOR_REL: "1272158927d5d6d3ded1d5dc07a888dce6d5353b76059fc17f328666fe92edc8",
}

AUTHORITY_CEILING = {
    "canonical_source": False,
    "domain_authority": False,
    "canonical_write": False,
    "reverse_write": False,
    "promotion": False,
    "candidate_claim": False,
    "live_provider": False,
    "external_delivery": False,
    "cutover": False,
    "authority_transfer": False,
    "runtime_mutation": False,
}


class GenerationError(RuntimeError):
    """A required predecessor, candidate, or path invariant is invalid."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _content_digest(value: dict[str, Any]) -> str:
    return _sha256(_canonical_json({key: item for key, item in value.items() if key != "content_digest"}))


def _safe_relative(root: Path, relative: Path | str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts or "\\" in str(relative):
        raise GenerationError(f"path escapes repository root: {relative}")
    if not candidate.parts or any(part in {"", "."} for part in candidate.parts):
        raise GenerationError(f"illegal repository-relative path: {relative}")
    resolved = (root / candidate).resolve(strict=False)
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise GenerationError(f"path escapes repository root: {relative}") from exc
    return candidate


def _require_file(root: Path, relative: Path | str) -> Path:
    safe = _safe_relative(root, relative)
    path = root / safe
    if not path.is_file() or path.is_symlink():
        raise GenerationError(f"required input missing or not a regular file: {safe.as_posix()}")
    return path


def _raw_ref(root: Path, relative: Path | str) -> dict[str, Any]:
    safe = _safe_relative(root, relative)
    payload = _require_file(root, safe).read_bytes()
    return {
        "path": safe.as_posix(),
        "file_sha256": _sha256(payload),
        "bytes": len(payload),
        "lines": len(payload.decode("utf-8").splitlines()),
    }


def _source_slice(raw: bytes, start_line: int, end_line: int) -> dict[str, Any]:
    lines = raw.decode("utf-8").splitlines(keepends=True)
    if not (1 <= start_line <= end_line <= len(lines)):
        raise GenerationError(f"invalid source slice {start_line}:{end_line}")
    selected = "".join(lines[start_line - 1 : end_line]).encode("utf-8")
    return {
        "start_line": start_line,
        "end_line": end_line,
        "bytes": len(selected),
        "sha256": _sha256(selected),
    }


def _ast_functions(path: Path) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        raise GenerationError(f"cannot parse C9 source {path}: {exc}") from exc
    return {node.name: node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _module_binding(root: Path, relative: Path, kind: str, functions: tuple[str, ...]) -> dict[str, Any]:
    path = _require_file(root, relative)
    raw = path.read_bytes()
    lines = raw.decode("utf-8").splitlines()
    inventory = _ast_functions(path)
    missing = [name for name in functions if name not in inventory]
    if missing:
        raise GenerationError(f"C9 source functions missing from {relative}: {', '.join(missing)}")
    return {
        "kind": kind,
        "path": relative.as_posix(),
        "external_sha256": _sha256(raw),
        "bytes": len(raw),
        "lines": len(lines),
        "functions": list(functions),
        "source_slice": _source_slice(raw, 1, len(lines)),
    }


def _function_bindings(root: Path, relative: Path, kind: str, functions: tuple[str, ...]) -> list[dict[str, Any]]:
    path = _require_file(root, relative)
    raw = path.read_bytes()
    inventory = _ast_functions(path)
    module_sha = _sha256(raw)
    module_lines = len(raw.decode("utf-8").splitlines())
    result = []
    for name in functions:
        node = inventory.get(name)
        if node is None:
            raise GenerationError(f"C9 source function missing: {relative}:{name}")
        result.append(
            {
                "kind": kind,
                "function": name,
                "path": relative.as_posix(),
                "external_sha256": module_sha,
                "bytes": len(raw),
                "lines": module_lines,
                "canonical_source": False,
                "domain_authoritative": False,
                "promotion_authority": False,
                "live_or_cutover_authority": False,
                "runtime_mutation": False,
                "source_slice": _source_slice(raw, node.lineno, node.end_lineno),
            }
        )
    return result


def _load_json(root: Path, relative: Path) -> dict[str, Any]:
    try:
        value = json.loads(_require_file(root, relative).read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GenerationError(f"invalid JSON input {relative}: {exc}") from exc
    if not isinstance(value, dict):
        raise GenerationError(f"JSON input must be an object: {relative}")
    return value


def _guard_predecessors(root: Path, stage: str | None = None) -> None:
    stage_name = _validate_stage(stage) if stage is not None else DEFAULT_STAGE
    hashes = dict(PREDECESSOR_HASHES)
    if stage_name.startswith("stage-b15-"):
        hashes.update(B13_PREDECESSOR_HASHES)
    if stage_name.startswith("stage-b16-"):
        hashes.update(B13_PREDECESSOR_HASHES)
        hashes.update(B15_PREDECESSOR_HASHES)
    if stage_name.startswith("stage-b17-"):
        hashes.update(B13_PREDECESSOR_HASHES)
        hashes.update(B15_PREDECESSOR_HASHES)
        hashes.update(B16_PREDECESSOR_HASHES)
    if stage_name.startswith("stage-b18-"):
        hashes.update(B13_PREDECESSOR_HASHES)
        hashes.update(B15_PREDECESSOR_HASHES)
        hashes.update(B16_PREDECESSOR_HASHES)
        hashes.update(B17_PREDECESSOR_HASHES)
    if stage_name.startswith("stage-b23-"):
        hashes.update(B23_PREDECESSOR_HASHES)
    if stage_name.startswith("stage-b19-"):
        hashes = dict(B19_PREDECESSOR_HASHES)
    for relative, expected in hashes.items():
        actual = _sha256(_require_file(root, relative).read_bytes())
        if actual != expected:
            raise GenerationError(
                f"frozen predecessor drift: {relative.as_posix()} expected={expected} actual={actual}"
            )


def _load_candidate_checker(root: Path):
    checker_path = root / "scripts/stage_family_fragment_rebind.py"
    spec = importlib.util.spec_from_file_location("_c9_candidate_checker", checker_path)
    if spec is None or spec.loader is None:
        raise GenerationError("cannot load candidate checker")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    return checker


def _validate_candidate(root: Path, stage_name: str) -> dict[str, Any]:
    is_b15 = stage_name.startswith("stage-b15-")
    is_b16 = stage_name.startswith("stage-b16-")
    is_b17 = stage_name.startswith("stage-b17-")
    is_b18 = stage_name.startswith("stage-b18-")
    is_b19 = stage_name.startswith("stage-b19-")
    is_b23 = stage_name.startswith("stage-b23-")
    binds_same_stage_candidate = is_b15 or is_b16 or is_b17 or is_b18 or is_b19 or is_b23
    expected_amendment = (
        B23_C9_AMENDMENT if is_b23 else B19_C9_AMENDMENT if is_b19 else B18_C9_AMENDMENT if is_b18 else B17_C9_AMENDMENT if is_b17 else B16_C9_AMENDMENT if is_b16 else B15_C9_AMENDMENT
    )
    candidate_rel = (
        EXACT_REBIND_REL / stage_name / "candidates/C9/candidate.v2.json"
        if binds_same_stage_candidate
        else B8_CANDIDATE_REL
    )
    candidate_path = _require_file(root, candidate_rel)
    candidate = _load_json(root, candidate_rel)
    if candidate.get("schema") != "mrw.family_fragment_rebind.candidate.v2":
        raise GenerationError("C9 candidate schema is not candidate.v2")
    if candidate.get("family") != "C9":
        raise GenerationError("C9 candidate family mismatch")
    if candidate.get("status") != "CANDIDATE_VALID_NOT_AUTHORITY":
        raise GenerationError("C9 candidate is not valid")
    if candidate.get("content_digest") != _content_digest(candidate):
        raise GenerationError("C9 candidate content_digest mismatch")
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str) or not re.fullmatch(r"[0-9a-f]{64}", candidate_id):
        raise GenerationError("C9 candidate candidate_id is invalid")
    if binds_same_stage_candidate:
        if candidate.get("amendment") != expected_amendment:
            raise GenerationError("current-stage C9 candidate amendment mismatch")
        manifest = candidate.get("manifest")
        manifest_path = manifest.get("path") if isinstance(manifest, dict) else None
        expected_manifest = (EXACT_REBIND_REL / stage_name / "manifests/C9.json").as_posix()
        if manifest_path != expected_manifest:
            raise GenerationError("current-stage C9 candidate manifest is not in the same stage")
        fragments = candidate.get("fragments")
        expected_fragment = (EXACT_REBIND_REL / stage_name / "fragments/C9.json").as_posix()
        if (
            not isinstance(fragments, list)
            or len(fragments) != 1
            or not isinstance(fragments[0], dict)
            or fragments[0].get("path") != expected_fragment
        ):
            raise GenerationError("current-stage C9 candidate fragment is not in the same stage")
    # B8 is checked in history mode as an immutable predecessor.  A B15/B16/B17/B18/B19/B23
    # sidecar is generated only after staging, so its candidate is checked
    # against the live logical paths named by that same-stage candidate.
    checker = _load_candidate_checker(root)
    try:
        checker.check_candidate(candidate_path, repo_root=root, history_only=not binds_same_stage_candidate)
    except Exception as exc:  # checker exposes several validation error classes
        raise GenerationError(f"C9 candidate is not valid: {exc}") from exc
    return {
        "path": candidate_rel.as_posix(),
        "file_sha256": _sha256(candidate_path.read_bytes()),
        "candidate_id": candidate_id,
        "content_digest": candidate["content_digest"],
        "status": candidate["status"],
        **({"amendment": expected_amendment} if binds_same_stage_candidate else {}),
    }


def _validate_stage(stage: str) -> str:
    if stage == "B13":
        return DEFAULT_STAGE
    if stage == "B15":
        return DEFAULT_B15_STAGE
    if stage == "B16":
        return DEFAULT_B16_STAGE
    if stage == "B17":
        return DEFAULT_B17_STAGE
    if stage == "B18":
        return DEFAULT_B18_STAGE
    if stage == "B19":
        return DEFAULT_B19_STAGE
    if stage == "B23":
        return DEFAULT_B23_STAGE
    if not re.fullmatch(r"stage-b(?:13|15|16|17|18|19|23)-\d{4}-\d{2}-\d{2}", stage):
        raise GenerationError("invalid stage; expected B13/B15/B16/B17/B18/B19/B23 or stage-b13/stage-b15/stage-b16/stage-b17/stage-b18/stage-b19/stage-b23-YYYY-MM-DD")
    try:
        datetime.date.fromisoformat(re.sub(r"^stage-b(?:13|15|16|17|18|19|23)-", "", stage))
    except ValueError as exc:
        raise GenerationError("invalid stage; expected B13/B15/B16/B17/B18/B19/B23 or stage-b13/stage-b15/stage-b16/stage-b17/stage-b18/stage-b19/stage-b23-YYYY-MM-DD") from exc
    return stage


def build_documents(root: Path, stage: str) -> Annotated[
    dict[Path, bytes],
    "kit:non-authoritative derived_as=view "
    "fact_source=C9_predecessor_candidate_current_checkout_bindings "
    "witness=test:test_generate_c9_authority_sidecar_documents_metadata",
]:
    root = root.expanduser().resolve()
    stage_name = _validate_stage(stage)
    is_b15 = stage_name.startswith("stage-b15-")
    is_b16 = stage_name.startswith("stage-b16-")
    is_b17 = stage_name.startswith("stage-b17-")
    is_b18 = stage_name.startswith("stage-b18-")
    is_b19 = stage_name.startswith("stage-b19-")
    is_b23 = stage_name.startswith("stage-b23-")
    stage_rel = EXACT_REBIND_REL / stage_name
    sidecar_rel = stage_rel / (
        B23_SIDECAR_INPUT_NAME
        if is_b23
        else B19_SIDECAR_INPUT_NAME
        if is_b19
        else B18_SIDECAR_INPUT_NAME
        if is_b18
        else B17_SIDECAR_INPUT_NAME
        if is_b17
        else B16_SIDECAR_INPUT_NAME
        if is_b16
        else B15_SIDECAR_INPUT_NAME
        if is_b15
        else SIDECAR_INPUT_NAME
    )
    _safe_relative(root, sidecar_rel)
    _guard_predecessors(root, stage_name)
    candidate = _validate_candidate(root, stage_name)

    predecessor_rel = (
        B23_PREDECESSOR_REL
        if is_b23
        else B18_SIDECAR_REL
        if is_b19
        else B17_SIDECAR_REL
        if is_b18
        else B16_SIDECAR_REL
        if is_b17
        else B15_SIDECAR_REL
        if is_b16
        else B13_SIDECAR_REL
        if is_b15
        else PREDECESSOR_REL
    )
    predecessor_ref = _raw_ref(root, predecessor_rel)
    predecessor_schema = (
        B19_SCHEMA
        if is_b23
        else B18_SCHEMA
        if is_b19
        else B17_SCHEMA
        if is_b18
        else B16_SCHEMA
        if is_b17
        else B15_SCHEMA
        if is_b16
        else "mrw.governance.generated_evidence_authority_sidecar.c9.v2"
        if is_b15
        else "mrw.governance.generated_evidence_authority.sidecar.c9.v1"
    )
    bindings: list[dict[str, Any]] = [
        {
            "kind": "immutable_predecessor_sidecar",
            **predecessor_ref,
            "schema": predecessor_schema,
            "mutability": "immutable",
        },
        _module_binding(root, SOURCE_REL, "current_c9_projection_source_module", PROJECTION_FUNCTIONS),
        _module_binding(
            root,
            CANONICAL_SOURCE_REL,
            "current_c9_canonical_source_closure_reader_module",
            CANONICAL_FUNCTIONS,
        ),
        _raw_ref(root, SPEC_REL) | {"kind": "current_c9_capability_spec", "cell_id": "C9.3"},
        _raw_ref(root, BUILD_REL) | {"kind": "current_c9_capability_spec_build_manifest", "cell_id": "C9.3"},
    ]
    bindings.extend(_function_bindings(root, SOURCE_REL, "c9_projection_payload_builder", PROJECTION_FUNCTIONS))
    bindings.extend(
        _function_bindings(
            root,
            CANONICAL_SOURCE_REL,
            "c9_canonical_source_closure_reader",
            CANONICAL_FUNCTIONS,
        )
    )

    sidecar: dict[str, Any] = {
        "schema": B23_SCHEMA if is_b23 else B19_SCHEMA if is_b19 else B18_SCHEMA if is_b18 else B17_SCHEMA if is_b17 else B16_SCHEMA if is_b16 else B15_SCHEMA if is_b15 else SCHEMA,
        "sidecar_id": B23_SIDECAR_ID if is_b23 else B19_SIDECAR_ID if is_b19 else B18_SIDECAR_ID if is_b18 else B17_SIDECAR_ID if is_b17 else B16_SIDECAR_ID if is_b16 else B15_SIDECAR_ID if is_b15 else SIDECAR_ID,
        "version": "8.0.0" if is_b23 else "7.0.0" if is_b19 else "6.0.0" if is_b18 else "5.0.0" if is_b17 else "4.0.0" if is_b16 else "3.0.0" if is_b15 else "2.0.0",
        "family": "C9",
        "stage": stage_name,
        "mutability": "immutable",
        "derived_as": "view",
        "view_kind": "PROJECTION_VIEW",
        "snapshot_scope": "CURRENT_CHECKOUT_ONLY",
        "canonical_source": False,
        "artifact_identity_authoritative": False,
        "domain_authoritative": False,
        "promotion_authority": False,
        "live_or_cutover_authority": False,
        "runtime_mutation": False,
        "authority_direction": (
            "exact current-checkout C9 source/test/candidate identity -> non-authoritative projection view"
        ),
        "authority": {"reverse_write": False, "promotion": False, "candidate_claim": False},
        "authority_ceiling": dict(AUTHORITY_CEILING),
        "predecessor": predecessor_ref,
        "candidate": candidate,
        "bindings": bindings,
        "tests": [_raw_ref(root, path) for path in WITNESS_TESTS],
    }
    sidecar["content_digest"] = _content_digest(sidecar)
    return {sidecar_rel: _canonical_json(sidecar) + b"\n"}


def _guard_create_only(root: Path, documents: dict[Path, bytes]) -> None:
    for relative in documents:
        safe = _safe_relative(root, relative)
        target = root / safe
        if target.exists() or target.is_symlink():
            raise GenerationError(f"refusing to overwrite existing sidecar input: {safe.as_posix()}")


def _write_documents(root: Path, documents: dict[Path, bytes]) -> None:
    written: list[Path] = []
    try:
        for relative, payload in documents.items():
            path = root / _safe_relative(root, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Exclusive creation closes the check/write race without ever
            # truncating a pre-existing target.
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
            written.append(path)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                try:
                    path.unlink()
                except OSError:
                    pass
                raise
    except Exception:
        for path in reversed(written):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    root = args.repo_root.expanduser().resolve()
    try:
        documents = build_documents(root, args.stage)
        _guard_create_only(root, documents)
        if args.write:
            _write_documents(root, documents)
    except (GenerationError, OSError, TypeError, ValueError, KeyError) as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2

    paths = [relative.as_posix() for relative in documents]
    if not args.write:
        print(json.dumps({"paths": paths, "status": "READY"}, sort_keys=True))
        return 0
    print(json.dumps({"paths": paths, "status": "WROTE"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
